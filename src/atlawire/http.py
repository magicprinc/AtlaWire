"""Shared JSON transport for self-hosted Atlassian reads."""

import base64
import json
import math
import re
from collections.abc import Generator, Iterable, Mapping, Sequence
from typing import Never, cast
from urllib.parse import unquote, urlsplit

import requests

_TEXT_LIMIT = 1024 * 1024
# Allow more room for structured documents than raw source while bounding
# each response independently.
_JSON_LIMIT = 8 * 1024 * 1024
_CHUNK_SIZE = 64 * 1024
_TEXT_LIMIT_MESSAGE = "The text response exceeds the 1 MiB limit."
_JSON_LIMIT_MESSAGE = "The JSON response exceeds the 8 MiB limit."
_PARTIAL_RESPONSE_MESSAGE = "HTTP 206: partial content is not supported."
_SECRET_ECHO_MESSAGE = "The response contained the session bearer token."
_NO_CONTENT = object()
_BIDI_CONTROLS = frozenset(
    "\u061c\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"
)

type _JsonValue = (
    None | bool | int | float | str | Sequence[_JsonValue] | Mapping[str, _JsonValue]
)


class AtlaWireError(Exception):
    """An operation failed with a message safe for CLI diagnostics."""


class _NoRedirectSession(requests.Session):
    """Session specialisation that never resolves or drains a redirect.

    Requests 2.34.2 asks [Session.resolve_redirects][requests.Session.resolve_redirects]
    for the next request even when ``allow_redirects=False``. That generator
    first reads and decompresses the whole redirect body, so a refused 3xx would
    still be buffered before the caller can check its status or cap the body.
    Returning no next request leaves the body on the wire; the shared status
    policy refuses every 3xx, so redirects are never followed here either.
    """

    def resolve_redirects(self, *args: object, **kwargs: object) -> Generator[Never]:
        yield from ()


def normalize_base_url(value: str, *, allow_http_loopback: bool) -> str:
    invalid = "Use an HTTPS base URL without credentials, query, or fragment."
    if re.search(r"[\s\\\x00-\x1f\x7f?#]", value):
        raise AtlaWireError(invalid)
    try:
        url = urlsplit(value)
        host, port = url.hostname, url.port
    except ValueError:
        raise AtlaWireError(invalid) from None
    if not host or "@" in url.netloc or "%" in url.netloc or port == 0:
        raise AtlaWireError(invalid)
    if url.scheme != "https" and not (
        allow_http_loopback and url.scheme == "http" and host in {"127.0.0.1", "::1"}
    ):
        raise AtlaWireError(invalid)
    return value.rstrip("/")


def bearer_session(token: str) -> requests.Session:
    """Create a session that the caller must close.

    The session sends the bearer token, ignores ambient netrc/proxy settings,
    and never follows or pre-reads a redirect response.
    """
    if not re.fullmatch(r"[A-Za-z0-9._~+/=-]+", token):
        raise AtlaWireError("Missing or invalid bearer token.")
    session = _NoRedirectSession()
    # Do not let ambient netrc settings replace the explicit Authorization header.
    session.trust_env = False
    session.headers.update(
        {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    )
    return session


def _reject_constant(_: str) -> float:
    raise ValueError("Non-JSON numeric constant.")


def _finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("JSON number outside the supported range.")
    return number


def _check_status(status: int) -> None:
    """Apply the shared read-only status policy without echoing the request.

    A 206 carries only part of a representation, so it is never a successful
    complete read for this client. Every caller consumes a complete document.
    """
    if 300 <= status < 400:
        raise AtlaWireError(f"HTTP {status}: redirect refused; check the base URL.")
    if status == 401:
        raise AtlaWireError("HTTP 401: authentication rejected.")
    if status == 403:
        raise AtlaWireError("HTTP 403: access denied.")
    if status == 206:
        raise AtlaWireError(_PARTIAL_RESPONSE_MESSAGE)
    if not 200 <= status < 300:
        raise AtlaWireError(f"HTTP {status}: request failed.")


def _bearer_token(session: object) -> str | None:
    """Return the selected session's bearer token, if it has one.

    Established tests use session-like fakes without a ``headers`` mapping, so
    a missing or unrelated ``Authorization`` header keeps the previous transport
    behavior instead of failing. Only an explicit Bearer credential is read.
    """
    headers = getattr(session, "headers", None)
    if not isinstance(headers, Mapping):
        return None
    value = headers.get("Authorization")
    if not isinstance(value, str):
        return None
    scheme, separator, token = value.partition(" ")
    if not separator or scheme.lower() != "bearer":
        return None
    token = token.strip()
    return token or None


def _base64_variants(value: str) -> tuple[str, ...]:
    """Return standard and URL-safe base64 forms, padded and unpadded."""
    raw = value.encode("utf-8")
    standard = base64.b64encode(raw).decode("ascii")
    urlsafe = base64.urlsafe_b64encode(raw).decode("ascii")
    return (standard, urlsafe, standard.rstrip("="), urlsafe.rstrip("="))


def _echo_needles(token: str) -> tuple[str, ...]:
    """Return literal and common base64 spellings of the credential.

    The searched set is the token itself, its standard and URL-safe base64
    forms with or without padding, and the same forms of the complete
    ``Bearer <token>`` header. This is not exhaustive protection against every
    reversible encoding. Matching is substring-based, so a short or common
    token can collide with ordinary data; rejecting that case is the deliberate
    fail-closed trade-off.
    """
    candidates = [token]
    for value in (token, f"Bearer {token}"):
        candidates.extend(_base64_variants(value))
    return tuple(dict.fromkeys(candidates))


def _contains_token(text: str, needles: tuple[str, ...]) -> bool:
    """Match a precomputed spelling literally or after one percent-decoding.

    Decoding only runs when a percent sign is present, so ordinary text keeps
    its exact meaning and pays no copy. ``unquote`` reconstructs fully and
    partly encoded values, including either hex case; that makes an encoder
    that leaves ``/`` literal while escaping ``+`` or ``=`` detectable too.
    """
    if any(needle in text for needle in needles):
        return True
    if "%" not in text:
        return False
    decoded = unquote(text)
    return any(needle in decoded for needle in needles)


def _contains_echoed_token(value: object, needles: tuple[str, ...]) -> bool:
    """Traverse decoded JSON without copying values and inspect every scalar.

    JSON escapes are decoded by the parser before this check, so an escaped
    token is the same string here as a literal one. An explicit stack avoids a
    recursion limit and retains only references to existing values. Encoding
    candidates are computed once by the caller, never per node.

    Mapping keys and numeric leaves are inspected as well. Every JSON scalar is
    checked in the spelling JSON gives it: integers in decimal, floats in their
    normalized Python form, booleans and null as ``true``, ``false`` and
    ``null``, and strings after escape decoding. Booleans and null are already
    covered by the raw-wire scan for a real response; inspecting them here keeps
    direct callers of the explicit guard consistent. A JSON integer keeps its
    decimal spelling, but a parsed float is normalized by Python: ``1e9``
    becomes ``1000000000.0``, so the credential can appear only in the original
    wire form, only in the normalized form, or in both.
    """
    stack: list[object] = [value]
    while stack:
        node = stack.pop()
        if isinstance(node, str):
            if _contains_token(node, needles):
                return True
        elif isinstance(node, bool):
            if _contains_token("true" if node else "false", needles):
                return True
        elif node is None:
            if _contains_token("null", needles):
                return True
        elif isinstance(node, int | float):
            if _contains_token(str(node), needles):
                return True
        elif isinstance(node, Mapping):
            for key, item in node.items():
                stack.append(key)
                stack.append(item)
        elif isinstance(node, Sequence) and not isinstance(node, bytes | bytearray):
            stack.extend(node)
    return False


def _token_needles(tokens: Iterable[str]) -> tuple[str, ...]:
    """Return the unique credential spellings for the supplied tokens.

    Empty or non-string entries are ignored, which keeps a missing credential
    from becoming the empty substring that matches every value.
    """
    needles: list[str] = []
    for token in tokens:
        if isinstance(token, str) and token:
            needles.extend(_echo_needles(token))
    return tuple(dict.fromkeys(needles))


def reject_credential_echo(value: object, *, tokens: Iterable[str]) -> None:
    """Raise the fixed generic error if ``value`` exposes a supplied token.

    The caller passes explicit credentials, so this can guard fully decoded or
    rendered output that no longer resembles the wire response. ``value`` may be
    a string, mapping, or nested sequence; string values, mapping keys, and every
    other scalar leaf are inspected. Empty or non-string token entries are
    ignored, which keeps a missing credential from matching everything.

    The searched spellings are the credential itself, its common URL-encoded
    forms, and its standard or URL-safe base64 forms. This is not exhaustive
    against every reversible encoding. Substring matching means short or common
    tokens can collide with ordinary data; rejecting that case is the deliberate
    fail-closed trade-off. The raised message never contains a credential,
    inspected value, or URL.
    """
    needles = _token_needles(tokens)
    if not needles:
        return
    if _contains_echoed_token(value, needles):
        raise AtlaWireError(_SECRET_ECHO_MESSAGE)


def _reject_json_echo(wire_text: str, decoded: object, token: str) -> None:
    """Reject a decoded JSON document or its original wire text echoing ``token``.

    The raw scan sees spellings the parsed tree cannot show, such as a numeric
    literal Python normalizes (``1e9``) or a boolean literal (``true``). It
    deliberately inspects the original UTF-8 text, never a re-rendering:
    ``json.dumps`` would turn a legitimate non-ASCII response into ASCII escapes
    such as ``\\u1234`` that the server never sent, and rejecting that spelling is
    the separate job of the conversion CLI's final guard over rendered output.
    ``wire_text`` is the single decoded copy the JSON parser already requires;
    ``_contains_token`` makes one more transient copy only when the text
    contains ``%``.
    """
    needles = _token_needles((token,))
    if _contains_token(wire_text, needles) or _contains_echoed_token(decoded, needles):
        raise AtlaWireError(_SECRET_ECHO_MESSAGE)


def _reject_token_echo(session: object, value: object) -> None:
    """Fail closed when the response would disclose this session's token."""
    token = _bearer_token(session)
    if token is not None:
        reject_credential_echo(value, tokens=(token,))


def _get_json(
    session: requests.Session,
    url: str,
    *,
    params: Mapping[str, str | int],
    allow_no_content: bool = False,
) -> object:
    """Perform one streamed JSON request with the shared timeouts and cap.

    ``allow_no_content`` is used only by callers whose versioned API documents
    a 204 response with no body. It returns the private no-content sentinel
    before reading or decoding anything; every other caller keeps the existing
    behavior, where 204 is an empty body and therefore not valid JSON. A body
    whose original JSON wire text or decoded value would disclose this session's
    bearer token is rejected before any value is returned.
    """
    try:
        with session.get(
            url,
            params=params,
            timeout=(5, 30),
            allow_redirects=False,
            stream=True,
        ) as response:
            _check_status(response.status_code)
            if allow_no_content and response.status_code == 204:
                return _NO_CONTENT
            payload = _read_limited(
                response, limit=_JSON_LIMIT, message=_JSON_LIMIT_MESSAGE
            )
    except requests.Timeout:
        raise AtlaWireError("Request timed out.") from None
    except requests.RequestException:
        raise AtlaWireError(
            "Request failed; check connectivity and TLS settings."
        ) from None
    decoded = _decode_json(payload, token=_bearer_token(session))
    return decoded


def _decode_json(payload: bytes, *, token: str | None = None) -> object:
    """Decode one bounded body as strict UTF-8 JSON with the shared rules.

    The wire bytes must be valid UTF-8; no lossy replacement is allowed. One
    leading UTF-8 BOM is ignored, as RFC 8259 permits. JSON escapes such as a
    lone surrogate stay ordinary text here: the output layer decides whether a
    decoded value can be printed.

    With ``token``, both the original JSON text and the decoded value are
    checked after a successful parse. Parsing first keeps malformed JSON's
    existing diagnostic and never returns data before the check; the text
    remains the one decoded copy the parser already needs, so the added cost is
    a scan (plus at most one percent-decoded copy when ``%`` occurs), not a
    second rendering.
    """
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        raise AtlaWireError("Expected UTF-8 JSON.") from None
    text = text.removeprefix("\ufeff")
    try:
        decoded = json.loads(
            text,
            parse_constant=_reject_constant,
            parse_float=_finite_float,
        )
    except ValueError, RecursionError:
        raise AtlaWireError("Expected a valid JSON response.") from None
    if token is not None:
        _reject_json_echo(text, decoded, token)
    return decoded


def post_json_object(
    session: requests.Session, url: str, *, body: Mapping[str, object]
) -> dict[str, object]:
    """Perform one streamed JSON POST with the shared read-request policy.

    The body is sent once as JSON with the same timeouts, redirect refusal,
    decoded size cap, strict UTF-8 decoding, and finite-number parsing as
    [get_json_object][atlawire.http.get_json_object].
    Diagnostics are generic, so a failed request never echoes the URL, payload,
    query, or credentials. A successful response whose original JSON wire text
    or decoded value echoes this session's bearer token is rejected with the same
    generic diagnostic.
    """
    try:
        payload = cast(_JsonValue, dict(body))
        with session.post(
            url,
            json=payload,
            timeout=(5, 30),
            allow_redirects=False,
            stream=True,
        ) as response:
            _check_status(response.status_code)
            data = _read_limited(
                response, limit=_JSON_LIMIT, message=_JSON_LIMIT_MESSAGE
            )
    except requests.Timeout:
        raise AtlaWireError("Request timed out.") from None
    except requests.RequestException:
        raise AtlaWireError(
            "Request failed; check connectivity and TLS settings."
        ) from None
    decoded = _decode_json(data, token=_bearer_token(session))
    if not isinstance(decoded, dict):
        raise AtlaWireError("Expected a JSON object.")
    return decoded


def get_json_any(
    session: requests.Session, url: str, *, params: Mapping[str, str | int]
) -> object:
    """Read one JSON document without assuming an object or array shape."""
    return _get_json(session, url, params=params)


def get_json_object(
    session: requests.Session, url: str, *, params: Mapping[str, str | int]
) -> dict[str, object]:
    data = _get_json(session, url, params=params)
    if not isinstance(data, dict):
        raise AtlaWireError("Expected a JSON object.")
    return data


def get_json_object_allow_no_content(
    session: requests.Session, url: str, *, params: Mapping[str, str | int]
) -> dict[str, object] | None:
    """Read one JSON object, treating a documented HTTP 204 as ``None``.

    Only a 204 yields ``None``. A 200 response whose body is JSON ``null`` or
    any other non-object is rejected as an object-shape error, and malformed or
    empty 200 JSON is rejected by the shared decoder. All other statuses,
    redirects, timeouts, size limits, and strict JSON rules are unchanged.
    """
    data = _get_json(session, url, params=params, allow_no_content=True)
    if data is _NO_CONTENT:
        return None
    if not isinstance(data, dict):
        raise AtlaWireError("Expected a JSON object.")
    return data


def get_json_array(
    session: requests.Session, url: str, *, params: Mapping[str, str | int]
) -> list[object]:
    data = _get_json(session, url, params=params)
    if not isinstance(data, list):
        raise AtlaWireError("Expected a JSON array.")
    return data


def get_text(session: requests.Session, url: str, *, params: Mapping[str, str]) -> str:
    """Read one streamed UTF-8 ``text/plain`` response under a hard size limit.

    The request overrides ``Accept`` to ``text/plain`` and never follows a
    redirect. It accepts up to 1 MiB of decoded content, including bytes
    produced by decompression; an oversize or failed read returns no partial
    text. The response is always closed, and the caller owns the session.
    Validation is deliberately generic so diagnostics cannot echo the
    path, query, contents, or credentials. Text that would disclose this
    session's bearer token, including common URL-encoded or base64 spellings, is
    rejected before any of it is returned.
    """
    try:
        with session.get(
            url,
            params=params,
            headers={"Accept": "text/plain"},
            timeout=(5, 30),
            allow_redirects=False,
            stream=True,
        ) as response:
            _check_status(response.status_code)
            _check_text_type(response.headers.get("Content-Type"))
            payload = _read_limited(
                response, limit=_TEXT_LIMIT, message=_TEXT_LIMIT_MESSAGE
            )
    except requests.Timeout:
        raise AtlaWireError("Request timed out.") from None
    except requests.RequestException:
        raise AtlaWireError(
            "Request failed; check connectivity and TLS settings."
        ) from None
    text = _decode_utf8_text(payload)
    _reject_token_echo(session, text)
    return text


def _check_text_type(value: str | None) -> None:
    media_type = (value or "").split(";", 1)[0].strip().lower()
    if media_type != "text/plain":
        raise AtlaWireError("Expected a text/plain response.")


def _read_limited(response: requests.Response, *, limit: int, message: str) -> bytes:
    """Accumulate decoded chunks, rejecting the first byte beyond ``limit``.

    Content encoding is decoded by urllib3 before each chunk is counted, so a
    compressed bomb is bounded by its decoded size. Only one decoded chunk is
    held beyond the running total, which bounds memory to ``limit`` plus that
    chunk (and any temporary decompressor buffer).
    """
    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_content(chunk_size=_CHUNK_SIZE):
        total += len(chunk)
        if total > limit:
            raise AtlaWireError(message)
        chunks.append(chunk)
    return b"".join(chunks)


def _decode_utf8_text(payload: bytes) -> str:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        raise AtlaWireError("Expected UTF-8 text.") from None
    if not _has_safe_text_chars(text):
        raise AtlaWireError("Unsafe control character in the text response.")
    return text


def _has_safe_text_chars(text: str) -> bool:
    """Allow TAB, LF and paired CRLF; reject bare CR and other controls.

    BOMs, ordinary Unicode and trailing whitespace are preserved exactly. LF is
    a portable line break on its own; CR must be part of the CRLF pair. Bidi
    formatting controls are rejected because they can visually reorder text.
    """
    for index, char in enumerate(text):
        if char in {"\t", "\n"}:
            continue
        if char == "\r":
            if text[index + 1 : index + 2] != "\n":
                return False
            continue
        code = ord(char)
        if code < 0x20 or 0x7F <= code <= 0x9F or char in _BIDI_CONTROLS:
            return False
    return True
