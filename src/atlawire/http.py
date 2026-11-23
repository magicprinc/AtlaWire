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
_BINARY_LIMIT_MESSAGE = "The binary or text response exceeds the configured size limit."
_TRANSPORT_MESSAGE = "Request failed; check connectivity and TLS settings."
_PARTIAL_RESPONSE_MESSAGE = "HTTP 206: partial content is not supported."
_SECRET_ECHO_MESSAGE = "The response contained the session bearer token."
_NO_CONTENT = object()
_GZIP_WBITS = 16 + zlib.MAX_WBITS
_GZIP_CODINGS = frozenset({"gzip", "x-gzip"})
_BIDI_CONTROLS = frozenset(
    "\u061c\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"
)

type _JsonValue = (
    None | bool | int | float | str | Sequence[_JsonValue] | Mapping[str, _JsonValue]
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
    * ``operation`` -- the registry operation ID when known.
    * ``category`` -- one value of ``ERROR_CATEGORIES``, or ``None`` when the
      failure could not be classified without guessing.
    * ``http_status`` -- the real status of an arrived response; never inferred.
    * ``method`` / ``path`` -- the failed request when known.

    Every attribute defaults to ``None`` so a plain ``AtlaWireError(message)``
    stays a normal exception and existing raise sites keep working unchanged.
    """

    product: str | None
    operation: str | None
    category: str | None
    http_status: int | None
    method: str | None
    path: str | None

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
    ) -> None:
        super().__init__(message)
        self.product = product
        self.operation = operation
        self.category = category
        self.http_status = http_status
        self.method = method
        self.path = path


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


_BEARER_TOKEN = re.compile(r"[A-Za-z0-9._~+/=-]+")


def _validated_token(token: str) -> str:
    """Return ``token`` after the one shared credential-shape check.

    The same rule guards the direct session and the session handed to the
    library, so an invalid credential fails closed before either is created.
    """
    if not _BEARER_TOKEN.fullmatch(token):
        raise AtlaWireError("Missing or invalid bearer token.", category="credentials")
    return token


def bearer_session(token: str) -> requests.Session:
    """Create a session that the caller must close.

    The session sends the bearer token, ignores ambient netrc/proxy settings,
    and never follows or pre-reads a redirect response.
    """
    token = _validated_token(token)
    session = _NoRedirectSession()
    # Do not let ambient netrc settings replace the explicit Authorization header.
    session.trust_env = False
    session.headers.update(
        {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    )
    return session


_UNSET = object()


def _reject_redirect_or_partial(status: int, *, method: str | None) -> None:
    """Refuse a 3xx or 206 before its body is read or decoded.

    ``requests.Response.raise_for_status`` treats both as successful, so the
    library would hand a redirect page or a partial representation to a caller
    as if it were a complete document. Status, message and metadata match the
    shared policy used by the direct transport.
    """
    if 300 <= status < 400:
        raise AtlaWireError(
            f"HTTP {status}: redirect refused; check the base URL.",
            category="http",
            http_status=status,
            method=method,
        )
    if status == 206:
        raise AtlaWireError(
            _PARTIAL_RESPONSE_MESSAGE,
            category="http",
            http_status=status,
            method=method,
        )


def _media_type(response: requests.Response) -> str:
    """Return the lowercased media type without parameters."""
    return (response.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()


def _is_json_media_type(media_type: str) -> bool:
    return media_type == "application/json" or media_type.endswith("+json")


def _is_text_media_type(media_type: str) -> bool:
    return media_type.startswith("text/")


def _declared_body_length(response: requests.Response) -> int | None:
    """Return ``Content-Length`` only when it measures the decoded body.

    A content coding (gzip and friends) makes the header the compressed size, so
    it is ignored and the streamed counter enforces the same cap instead.
    """
    coding = (response.headers.get("Content-Encoding") or "").strip().lower()
    if coding and coding != "identity":
        return None
    value = response.headers.get("Content-Length")
    if value is None:
        return None
    try:
        length = int(value.strip())
    except ValueError:
        return None
    return length if length >= 0 else None


class _GuardedResponse:
    """Read-only proxy around ``requests.Response`` with the shared read policy.

    The library owns the HTTP exchange, so its own ``raise_for_status`` accepts
    3xx/206 and would buffer an unbounded body. This proxy keeps that transport
    but overrides every body accessor: ``.content``, ``.text`` and ``.json()``
    reject a redirect or partial status, cap the decoded body (8 MiB for JSON,
    ``body_limit`` otherwise, pre-checked against ``Content-Length``), and decode
    JSON strictly from the original bytes with non-finite numbers refused. Every
    other attribute is delegated unchanged, and the library may still set
    ``.encoding``.
    """

    def __init__(
        self,
        response: requests.Response,
        *,
        body_limit: int,
        method: str,
    ) -> None:
        object.__setattr__(self, "_response", response)
        object.__setattr__(self, "_body_limit", body_limit)
        object.__setattr__(self, "_method", method)
        object.__setattr__(self, "_body", _UNSET)
        object.__setattr__(self, "_text", _UNSET)
        object.__setattr__(self, "_json", _UNSET)

    def __getattr__(self, name: str) -> object:
        return getattr(object.__getattribute__(self, "_response"), name)

    def __setattr__(self, name: str, value: object) -> None:
        # The library assigns ``response.encoding`` before it reads the body.
        if name.startswith("_"):
            object.__setattr__(self, name, value)
        else:
            setattr(object.__getattribute__(self, "_response"), name, value)

    def _limit(self) -> tuple[int, str]:
        if _is_json_media_type(_media_type(self._response)):
            return _JSON_LIMIT, _JSON_LIMIT_MESSAGE
        return self._body_limit, _BINARY_LIMIT_MESSAGE

    def _load_body(self) -> bytes:
        response = object.__getattribute__(self, "_response")
        _reject_redirect_or_partial(response.status_code, method=self._method)
        limit, message = self._limit()
        declared = _declared_body_length(response)
        if declared is not None and declared > limit:
            raise AtlaWireError(message, category="upstream")
        return _read_limited(response, limit=limit, message=message)

    @property
    def content(self) -> bytes:
        body = object.__getattribute__(self, "_body")
        if body is _UNSET:
            body = self._load_body()
            object.__setattr__(self, "_body", body)
        return body

    @property
    def text(self) -> str:
        text = object.__getattribute__(self, "_text")
        if text is _UNSET:
            text = self._decode_text()
            object.__setattr__(self, "_text", text)
        return text

    def _decode_text(self) -> str:
        payload = self.content
        media_type = _media_type(self._response)
        if _is_json_media_type(media_type):
            try:
                text = payload.decode("utf-8")
            except UnicodeDecodeError:
                raise AtlaWireError("Expected UTF-8 JSON.", category="upstream") from None
            # A non-empty JSON body is parsed here, so a malformed or
            # non-finite document fails even for a library method that would
            # otherwise swallow a JSON error and fall back to the raw text.
            if text.strip():
                object.__setattr__(self, "_json", _parse_json_text(text))
            return text
        errors = "strict" if _is_text_media_type(media_type) else "replace"
        try:
            text = payload.decode(self._response.encoding or "utf-8", errors)
        except (UnicodeDecodeError, LookupError):
            raise AtlaWireError("Expected UTF-8 text.", category="upstream") from None
        return text

    def json(self) -> object:
        """Return the value decoded under the shared strict JSON rules."""
        if _is_json_media_type(_media_type(self._response)):
            _ = self.text  # выставляет кэш ``_json`` либо бросает ошибку
            value = object.__getattribute__(self, "_json")
            if value is not _UNSET:
                return value
        payload = self.content
        if len(payload) > _JSON_LIMIT:
            raise AtlaWireError(_JSON_LIMIT_MESSAGE, category="upstream")
        value = _decode_json(payload)
        object.__setattr__(self, "_json", value)
        return value

    def raise_for_status(self) -> None:
        """Raise ``HTTPError`` carrying this guarded proxy on a failed status."""
        try:
            self._response.raise_for_status()
        except requests.HTTPError as error:
            raise requests.HTTPError(str(error), response=self) from None


class _GuardedLibrarySession(_NoRedirectSession):
    """Session for the library: every response is streamed and guarded."""

    def __init__(self, *, body_limit: int) -> None:
        super().__init__()
        self._body_limit = body_limit

    def request(self, method: str, url: str, **kwargs: object) -> requests.Response:
        """Send one request with ``stream=True`` and wrap the response.

        Streaming keeps the body cap ahead of ``requests`` buffering the whole
        payload. The returned proxy is duck-typed; callers that annotate
        ``requests.Response`` keep the attributes they use.
        """
        kwargs["stream"] = True
        response = super().request(method, url, **kwargs)
        return _GuardedResponse(
            response,
            body_limit=self._body_limit,
            method=method,
        )


def library_session(token: str, *, body_limit: int) -> requests.Session:
    """Create the guarded session handed to ``atlassian-python-api``.

    The token is validated by the same rule as the direct session, ambient
    netrc/proxy state is ignored, redirects are never resolved, and every
    response is returned as a [_GuardedResponse][atlawire.http._GuardedResponse].
    ``body_limit`` caps a non-JSON body; JSON keeps the fixed 8 MiB cap. The
    caller owns the session.
    """
    _validated_token(token)
    session = _GuardedLibrarySession(body_limit=body_limit)
    session.trust_env = False
    return session


def _reject_constant(_: str) -> float:
    raise ValueError("Non-JSON numeric constant.")


def _finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("JSON number outside the supported range.")
    return number


def _check_status(
    status: int, *, method: str | None = None
) -> None:
    """Apply the shared read-only status policy without echoing the request.

    A 206 carries only part of a representation, so it is never a successful
    complete read for this client. Every caller consumes a complete document.
    """
    _reject_redirect_or_partial(status, method=method)
    if status == 401:
        raise AtlaWireError(
            "HTTP 401: authentication rejected.",
            category="http",
            http_status=status,
            method=method,
        )
    if status == 403:
        raise AtlaWireError(
            "HTTP 403: access denied.",
            category="http",
            http_status=status,
            method=method,
        )
    if not 200 <= status < 300:
        raise AtlaWireError(
            f"HTTP {status}: request failed.",
            category="http",
            http_status=status,
            method=method,
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
                response.status_code, method="GET"
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
        ) from None
    except requests.RequestException:
        raise AtlaWireError(
            _TRANSPORT_MESSAGE,
            category="transport",
            method="GET",
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
    return _parse_json_text(text, token=token)


def _parse_json_text(text: str, *, token: str | None = None) -> object:
    """Parse JSON that was decoded from one bounded UTF-8 body.

    The rules are shared by the direct transport and the guarded library
    response: one leading BOM is ignored, non-finite constants and out-of-range
    numbers are refused, and the supplied token must not appear in the wire text
    or in the decoded value. Parsing runs before the credential check, so a
    malformed document keeps its own diagnostic.
    """
    text = text.removeprefix("\ufeff")
    try:
        decoded = json.loads(
            text,
            parse_constant=_reject_constant,
            parse_float=_finite_float,
        )
    except ValueError, RecursionError:
        raise AtlaWireError("Expected a valid JSON response.", category="upstream") from None
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
                response.status_code, method="POST"
            )
            data = _read_limited(
                response, limit=_JSON_LIMIT, message=_JSON_LIMIT_MESSAGE
            )
    except requests.Timeout:
        raise AtlaWireError(
            "Request timed out.",
            category="transport",
            method="POST",
        ) from None
    except requests.RequestException:
        raise AtlaWireError(
            _TRANSPORT_MESSAGE,
            category="transport",
            method="POST",
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
            _check_status(
                response.status_code, method="GET"
            )
            _check_text_type(response.headers.get("Content-Type"))
            payload = _read_limited(
                response, limit=_TEXT_LIMIT, message=_TEXT_LIMIT_MESSAGE
            )
    except requests.Timeout:
        raise AtlaWireError(
            "Request timed out.",
            category="transport",
            method="GET",
        ) from None
    except requests.RequestException:
        raise AtlaWireError(
            _TRANSPORT_MESSAGE,
            category="transport",
            method="GET",
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
                raise AtlaWireError(
                    _TRANSPORT_MESSAGE, category="transport"
                ) from None
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
