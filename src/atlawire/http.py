"""Shared JSON transport for self-hosted Atlassian reads."""

import base64
import json
import math
import re
import zlib
from collections.abc import Generator, Iterable, Iterator, Mapping, Sequence
from typing import Never, cast
from urllib.parse import unquote, urlsplit

import requests
import urllib3.exceptions

_TEXT_LIMIT = 1024 * 1024
# Allow more room for structured documents than raw source while bounding
# each response independently.
_JSON_LIMIT = 8 * 1024 * 1024
_CHUNK_SIZE = 64 * 1024
_TEXT_LIMIT_MESSAGE = "The text response exceeds the 1 MiB limit."
_JSON_LIMIT_MESSAGE = "The JSON response exceeds the 8 MiB limit."
_TRANSPORT_MESSAGE = "Request failed; check connectivity and TLS settings."
_PARTIAL_RESPONSE_MESSAGE = "HTTP 206: partial content is not supported."
_SECRET_ECHO_MESSAGE = "The response contained the session bearer token."  # noqa: S105
_NO_CONTENT = object()
_GZIP_WBITS = 16 + zlib.MAX_WBITS
_GZIP_CODINGS = frozenset({"gzip", "x-gzip"})
_BIDI_CONTROLS = frozenset(
    "\u061c\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"
)

type _JsonValue = (
    bool | int | float | str | Sequence[_JsonValue] | Mapping[str, _JsonValue] | None
)


# The fixed set of values allowed in AtlaWireError.category. A category names
# what a caller can act on; it is never inferred from the message text.
ERROR_CATEGORIES = frozenset(
    {
        "transport",
        "http",
        "validation",
        "unknown_operation",
        "credentials",
        "upstream",
    }
)


class AtlaWireError(Exception):
    """An operation failed with a message safe for CLI diagnostics.

    The message never contains a response body or excerpt, a credential, or raw
    caller arguments. A caller that needs to branch reads the optional
    structured attributes instead of parsing text:

    * ``product`` -- ``"jira"``, ``"confluence"`` or ``"bitbucket"`` when known.
      Typed product calls always fill it; a registry read fills it from the
      operation.
    * ``operation`` -- the registry operation ID. It is filled only by a read
      that goes through the operation registry; a typed function has no
      operation ID, so it stays ``None`` there.
    * ``category`` -- one value of ``ERROR_CATEGORIES``, or ``None`` when the
      failure could not be classified without guessing.
    * ``http_status`` -- the real status of an arrived response; never inferred.
    * ``method`` / ``path`` -- the failed request when known.
    * ``detail`` -- the documented reason a rejected request gave, for example
      ``limit: "abc" is not a valid value for "limit"``. It is filled only from
      the documented error fields of a client-error response (see
      [error_detail][atlawire.http]), is bounded and escaped, and never contains
      the credential. It is deliberately **not** part of ``str(error)``: the
      message stays generic so logging and tracebacks cannot publish response
      content, and a caller that wants the reason reads ``error.detail``.

    Every attribute defaults to ``None`` so a plain ``AtlaWireError(message)``
    stays a normal exception and existing raise sites keep working unchanged.
    """

    product: str | None
    operation: str | None
    category: str | None
    http_status: int | None
    method: str | None
    path: str | None
    detail: str | None

    def __init__(
        self,
        message: str,
        *,
        product: str | None = None,
        operation: str | None = None,
        category: str | None = None,
        http_status: int | None = None,
        method: str | None = None,
        path: str | None = None,
        detail: str | None = None,
    ) -> None:
        super().__init__(message)
        self.product = product
        self.operation = operation
        self.category = category
        self.http_status = http_status
        self.method = method
        self.path = path
        self.detail = detail


class _PolicySession(requests.Session):
    """Session that applies one optional default timeout to every request.

    A bare [requests.Session][requests.Session] has no default timeout, so a
    caller that omits ``timeout`` waits forever. The factory records one policy
    value instead of rewriting every call site. ``send`` is the single funnel
    [requests.Session.request][requests.Session.request] and the redirect
    machinery pass through, so the default also covers followed redirects.

    ``product`` names the Atlassian product this session reads, so a failure
    raised deep in the shared transport can report the product without every
    helper passing it down by hand.
    """

    default_timeout: float | None
    product: str | None

    def __init__(
        self, *, default_timeout: float | None = None, product: str | None = None
    ) -> None:
        super().__init__()
        self.default_timeout = default_timeout
        self.product = product

    def send(
        self, request: requests.PreparedRequest, **kwargs: object
    ) -> requests.Response:
        if kwargs.get("timeout") is None and self.default_timeout is not None:
            kwargs["timeout"] = self.default_timeout
        return super().send(request, **kwargs)


class _NoRedirectSession(_PolicySession):
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
        raise AtlaWireError(invalid, category="validation")
    try:
        url = urlsplit(value)
        host, port = url.hostname, url.port
    except ValueError:
        raise AtlaWireError(invalid, category="validation") from None
    if not host or "@" in url.netloc or "%" in url.netloc or port == 0:
        raise AtlaWireError(invalid, category="validation")
    if url.scheme != "https" and not (
        allow_http_loopback and url.scheme == "http" and host in {"127.0.0.1", "::1"}
    ):
        raise AtlaWireError(invalid, category="validation")
    return value.rstrip("/")


def new_session(
    base_url: str,
    token: str | None = None,
    *,
    follow_redirects: bool = False,
    trust_env: bool = False,
    timeout: float | None = None,
    product: str | None = None,
    allow_http_loopback: bool = False,
) -> requests.Session:
    """Create a transport session for ``base_url``; the caller must close it.

    The defaults keep the strict AtlaWire transport policy: a 3xx response is
    returned as-is and its ``Location`` is never requested, while ambient
    proxy/netrc/CA settings are ignored. ``follow_redirects=True`` restores the
    standard [requests.Session][requests.Session] behavior of following
    ``Location``, and ``trust_env=True`` lets the ambient settings apply; a
    transport adapter that must preserve the earlier ``requests`` behavior
    needs both switches.

    ``base_url`` is validated with the same rules as the product functions, so
    a bad destination fails before a session exists. The session itself does
    not bind a base URL because requests has no such concept: the caller still
    passes absolute URLs. ``timeout`` becomes the default for requests that do
    not pass their own.

    ``token`` is checked with the exact grammar of
    [bearer_session][atlawire.http.bearer_session] and sent as a Bearer header.
    ``token=None`` yields a session without an Authorization header, which lets
    a transport that selects Bearer/Basic itself (or relies on netrc) avoid a
    private class; an empty or malformed token is still rejected.
    """
    normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    return _new_session(
        token,
        follow_redirects=follow_redirects,
        trust_env=trust_env,
        timeout=timeout,
    )


def bearer_session(token: str, *, product: str | None = None) -> requests.Session:
    """Create a session that the caller must close.

    The session sends the bearer token, ignores ambient netrc/proxy settings,
    and never follows or pre-reads a redirect response. ``product`` is optional
    metadata: when given, every failure raised by this session's shared readers
    reports it in ``AtlaWireError.product``.
    """
    return _new_session(
        token,
        follow_redirects=False,
        trust_env=False,
        timeout=None,
        product=product,
    )


def _new_session(
    token: str | None,
    *,
    follow_redirects: bool,
    trust_env: bool,
    timeout: float | None,
    product: str | None = None,
) -> requests.Session:
    """Build the one session policy shared by the public factories."""
    if token is not None and not re.fullmatch(r"[A-Za-z0-9._~+/=-]+", token):
        raise AtlaWireError("Missing or invalid bearer token.", category="credentials")
    session: _PolicySession = (
        _PolicySession(default_timeout=timeout, product=product)
        if follow_redirects
        else _NoRedirectSession(default_timeout=timeout, product=product)
    )
    session.trust_env = trust_env
    headers = {"Accept": "application/json"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    session.headers.update(headers)
    return session


def _session_product(session: object) -> str | None:
    """Return the product a session was created for, when it declares one."""
    product = getattr(session, "product", None)
    return product if isinstance(product, str) and product else None


def _reject_constant(_: str) -> float:
    raise ValueError("Non-JSON numeric constant.")


def _finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("JSON number outside the supported range.")
    return number


# A rejected request usually carries the reason in documented Atlassian fields.
# Only 400 is listed: it is the status the three products actually returned for a
# malformed query, JQL or limit on the live read-only run. Other 4xx statuses are
# left generic until one is observed, so the message never guesses why.
_ERROR_DETAIL_STATUSES = frozenset({400})
_ERROR_BODY_LIMIT = 8 * 1024
_ERROR_TEXT_LIMIT = 400
_ERROR_UNSAFE = re.compile(
    "[\x00-\x1f\x7f-\x9f\u061c\u200e\u200f\u202a-\u202e\u2066-\u2069\ud800-\udfff]"
)


def _error_messages(document: Mapping[str, object]) -> list[str]:
    """Collect the documented error strings from one Atlassian error document.

    The three products publish different shapes for the same idea, so all three
    are read instead of guessing by product:

    * Jira: ``{"errorMessages": ["..."], "errors": {"field": "..."}}``.
    * Bitbucket: ``{"errors": [{"context": "field", "message": "..."}]}``.
    * Confluence: a top-level ``message`` and ``reason``.

    Anything else contributes nothing; the raw body is never used as a message.
    """
    messages: list[str] = []
    listed = document.get("errorMessages")
    if isinstance(listed, list):
        messages.extend(item for item in listed if isinstance(item, str))
    errors = document.get("errors")
    if isinstance(errors, dict):
        messages.extend(
            f"{name}: {message}"
            for name, message in errors.items()
            if isinstance(name, str) and isinstance(message, str)
        )
    elif isinstance(errors, list):
        for entry in errors:
            if not isinstance(entry, dict):
                continue
            message = entry.get("message")
            if not isinstance(message, str):
                continue
            context = entry.get("context")
            if isinstance(context, str) and context:
                messages.append(f"{context}: {message}")
            else:
                messages.append(message)
    for name in ("message", "reason"):
        value = document.get(name)
        if isinstance(value, str):
            messages.append(value)
    # A server may repeat the same sentence in several fields; one copy is
    # enough, and the documented order is preserved.
    return list(dict.fromkeys(messages))


def error_detail(raw: bytes | str, *, tokens: Iterable[str] = ()) -> str:
    """Return the documented reason from one error body, or ``""``.

    Shared by the streaming transport and the adapter layer so a caller sees the
    same sentence whichever entry point failed. Only the documented error fields
    are read (see [_error_messages][atlawire.http]); the raw body is never echoed,
    because it can carry unrelated data. The result is bounded, control and bidi
    characters are escaped, and a sentence that discloses one of the supplied
    credentials is dropped whole rather than partially shown.
    """
    if isinstance(raw, bytes):
        if len(raw) > _ERROR_BODY_LIMIT:
            raw = raw[:_ERROR_BODY_LIMIT]
        try:
            text = raw.decode("utf-8", "replace")
        except Exception:  # noqa: BLE001 - a diagnostic must never raise
            return ""
    else:
        text = raw[:_ERROR_BODY_LIMIT]
    try:
        document = json.loads(text)
    except ValueError, RecursionError:
        return ""
    if not isinstance(document, dict):
        return ""
    detail = _ERROR_UNSAFE.sub(" ", " ".join(_error_messages(document)))
    detail = " ".join(detail.split())
    if not detail:
        return ""
    needles: list[str] = []
    for token in tokens:
        if isinstance(token, str) and token:
            needles.extend(_echo_needles(token))
    if any(needle in detail for needle in needles):
        return ""
    return detail[:_ERROR_TEXT_LIMIT]


def _server_detail(response: requests.Response, session: object) -> str:
    """Read one bounded error body and return its redacted reason, or ``""``."""
    if getattr(response, "status_code", None) not in _ERROR_DETAIL_STATUSES:
        return ""
    try:
        raw = b""
        for chunk in response.iter_content(1024):
            raw += chunk
            if len(raw) >= _ERROR_BODY_LIMIT:
                break
    except Exception:  # noqa: BLE001 - a diagnostic must never mask the error
        return ""
    token = _bearer_token(session)
    return error_detail(raw, tokens=(token,) if token is not None else ())


def _check_status(
    status: int,
    *,
    method: str | None = None,
    product: str | None = None,
    detail: str = "",
) -> None:
    """Apply the shared read-only status policy without echoing the request.

    A 206 carries only part of a representation, so it is never a successful
    complete read for this client. Every caller consumes a complete document.
    """
    if 300 <= status < 400:
        raise AtlaWireError(
            f"HTTP {status}: redirect refused; check the base URL.",
            category="http",
            http_status=status,
            method=method,
            product=product,
        )
    if status == 401:
        raise AtlaWireError(
            "HTTP 401: authentication rejected.",
            category="http",
            http_status=status,
            method=method,
            product=product,
        )
    if status == 403:
        raise AtlaWireError(
            "HTTP 403: access denied.",
            category="http",
            http_status=status,
            method=method,
            product=product,
        )
    if status == 206:
        raise AtlaWireError(
            _PARTIAL_RESPONSE_MESSAGE,
            category="http",
            http_status=status,
            method=method,
            product=product,
        )
    if not 200 <= status < 300:
        raise AtlaWireError(
            f"HTTP {status}: request failed.",
            category="http",
            http_status=status,
            method=method,
            product=product,
            detail=detail or None,
        )


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
            _check_status(
                response.status_code,
                method="GET",
                product=_session_product(session),
                detail=_server_detail(response, session),
            )
            if allow_no_content and response.status_code == 204:
                return _NO_CONTENT
            payload = _read_limited(
                response, limit=_JSON_LIMIT, message=_JSON_LIMIT_MESSAGE
            )
    except requests.Timeout:
        raise AtlaWireError(
            "Request timed out.",
            category="transport",
            method="GET",
            product=_session_product(session),
        ) from None
    except requests.RequestException:
        raise AtlaWireError(
            _TRANSPORT_MESSAGE,
            category="transport",
            method="GET",
            product=_session_product(session),
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
        raise AtlaWireError("Expected UTF-8 JSON.", category="upstream") from None
    text = text.removeprefix("\ufeff")
    try:
        decoded = json.loads(
            text,
            parse_constant=_reject_constant,
            parse_float=_finite_float,
        )
    except ValueError, RecursionError:
        raise AtlaWireError(
            "Expected a valid JSON response.", category="upstream"
        ) from None
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
            _check_status(
                response.status_code,
                method="POST",
                product=_session_product(session),
                detail=_server_detail(response, session),
            )
            data = _read_limited(
                response, limit=_JSON_LIMIT, message=_JSON_LIMIT_MESSAGE
            )
    except requests.Timeout:
        raise AtlaWireError(
            "Request timed out.",
            category="transport",
            method="POST",
            product=_session_product(session),
        ) from None
    except requests.RequestException:
        raise AtlaWireError(
            _TRANSPORT_MESSAGE,
            category="transport",
            method="POST",
            product=_session_product(session),
        ) from None
    decoded = _decode_json(data, token=_bearer_token(session))
    if not isinstance(decoded, dict):
        raise AtlaWireError("Expected a JSON object.", category="upstream")
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
        raise AtlaWireError("Expected a JSON object.", category="upstream")
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
        raise AtlaWireError("Expected a JSON object.", category="upstream")
    return data


def get_json_array(
    session: requests.Session, url: str, *, params: Mapping[str, str | int]
) -> list[object]:
    data = _get_json(session, url, params=params)
    if not isinstance(data, list):
        raise AtlaWireError("Expected a JSON array.", category="upstream")
    return data


def get_text(session: requests.Session, url: str, *, params: Mapping[str, str]) -> str:
    """Read one streamed UTF-8 ``text/plain`` response under a hard size limit.

    The request overrides ``Accept`` to ``text/plain`` and never follows a
    redirect. It accepts up to 1 MiB of decoded content, including bytes
    produced by decompression; an oversize, truncated or undecodable gzip
    member returns no partial text. The response is always closed, and the
    caller owns the session.
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
            _check_status(
                response.status_code,
                method="GET",
                product=_session_product(session),
                detail=_server_detail(response, session),
            )
            _check_text_type(response.headers.get("Content-Type"))
            payload = read_encoded_limited(
                response, limit=_TEXT_LIMIT, message=_TEXT_LIMIT_MESSAGE
            )
    except requests.Timeout:
        raise AtlaWireError(
            "Request timed out.",
            category="transport",
            method="GET",
            product=_session_product(session),
        ) from None
    except requests.RequestException:
        raise AtlaWireError(
            _TRANSPORT_MESSAGE,
            category="transport",
            method="GET",
            product=_session_product(session),
        ) from None
    text = _decode_utf8_text(payload)
    _reject_token_echo(session, text)
    return text


def _check_text_type(value: str | None) -> None:
    media_type = (value or "").split(";", 1)[0].strip().lower()
    if media_type != "text/plain":
        raise AtlaWireError("Expected a text/plain response.", category="upstream")


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
            raise AtlaWireError(message, category="upstream")
        chunks.append(chunk)
    return b"".join(chunks)


def read_encoded_limited(
    response: requests.Response, *, limit: int, message: str
) -> bytes:
    """Read one body under a decoded-size cap, verifying a gzip member.

    urllib3 decodes ``Content-Encoding`` before each chunk is counted, so the
    cap applies to decoded bytes either way. Its gzip decoder does not validate
    the eight-byte member trailer (CRC32 and length): it flushes the zlib object
    and returns, so a truncated member would produce a plausible prefix. When
    the response declares exactly one gzip coding, the encoded chunks are read
    raw and decoded here with ``zlib.decompressobj(31)``, which reports
    completion only after the complete trailer was consumed. Every other coding
    (identity, deflate, unknown, or stacked) keeps the shared streamed reader
    unchanged.

    A truncated or undecodable member raises the generic transport diagnostic:
    the decoder's own message can name the host or a certificate, so it is never
    re-raised. Memory stays bounded to ``limit`` plus one raw chunk, because
    each decode call caps its own output.
    """
    if _single_content_coding(response) not in _GZIP_CODINGS:
        return _read_limited(response, limit=limit, message=message)
    return _read_gzip_limited(response, limit=limit, message=message)


def _single_content_coding(response: requests.Response) -> str | None:
    """Return the one declared content coding, or ``None`` for any other case."""
    header = response.headers.get("Content-Encoding") or ""
    codings = [part.strip().lower() for part in header.split(",") if part.strip()]
    return codings[0] if len(codings) == 1 else None


def _read_gzip_limited(
    response: requests.Response, *, limit: int, message: str
) -> bytes:
    """Decode one gzip body, rejecting an incomplete member and oversize output."""
    decoder = zlib.decompressobj(_GZIP_WBITS)
    parts: list[bytes] = []
    total = 0
    for chunk in _iter_encoded(response):
        data = chunk
        while data:
            if decoder.eof:
                # A further member follows; urllib3 accepts concatenated members.
                decoder = zlib.decompressobj(_GZIP_WBITS)
            try:
                decoded = decoder.decompress(data, limit - total + 1)
            except zlib.error:
                raise AtlaWireError(_TRANSPORT_MESSAGE, category="transport") from None
            total += len(decoded)
            if total > limit:
                raise AtlaWireError(message, category="upstream")
            parts.append(decoded)
            data = decoder.unused_data if decoder.eof else decoder.unconsumed_tail
    if not decoder.eof:
        raise AtlaWireError(_TRANSPORT_MESSAGE, category="transport")
    return b"".join(parts)


def _iter_encoded(response: requests.Response) -> Iterator[bytes]:
    """Yield the undecoded chunks of one streamed response body.

    Requests passes ``decode_content=True`` unconditionally, so the raw stream
    is used directly. Because that bypasses its exception translation, every
    read failure is reported as the same generic transport error here; the
    cause may name the host or a certificate.
    """
    raw = response.raw
    stream = getattr(raw, "stream", None)
    try:
        if stream is not None:
            yield from stream(_CHUNK_SIZE, decode_content=False)
        else:
            while chunk := raw.read(_CHUNK_SIZE, decode_content=False):
                yield chunk
    except AtlaWireError:
        raise
    except requests.RequestException, urllib3.exceptions.HTTPError, OSError:
        raise AtlaWireError(_TRANSPORT_MESSAGE, category="transport") from None


def _decode_utf8_text(payload: bytes) -> str:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        raise AtlaWireError("Expected UTF-8 text.", category="upstream") from None
    if not _has_safe_text_chars(text):
        raise AtlaWireError(
            "Unsafe control character in the text response.", category="upstream"
        )
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
