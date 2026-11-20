"""Shared JSON transport for self-hosted Atlassian reads."""

import json
import math
import re
from collections.abc import Generator, Mapping, Sequence
from typing import Never, cast
from urllib.parse import urlsplit

import requests

_TEXT_LIMIT = 1024 * 1024
# Allow more room for structured documents than raw source while bounding
# each response independently.
_JSON_LIMIT = 8 * 1024 * 1024
_CHUNK_SIZE = 64 * 1024
_TEXT_LIMIT_MESSAGE = "The text response exceeds the 1 MiB limit."
_JSON_LIMIT_MESSAGE = "The JSON response exceeds the 8 MiB limit."
_PARTIAL_RESPONSE_MESSAGE = "HTTP 206: partial content is not supported."
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


def _get_json(
    session: requests.Session, url: str, *, params: Mapping[str, str | int]
) -> object:
    """Perform one streamed JSON request with the shared timeouts and cap."""
    try:
        with session.get(
            url,
            params=params,
            timeout=(5, 30),
            allow_redirects=False,
            stream=True,
        ) as response:
            _check_status(response.status_code)
            payload = _read_limited(
                response, limit=_JSON_LIMIT, message=_JSON_LIMIT_MESSAGE
            )
    except requests.Timeout:
        raise AtlaWireError("Request timed out.") from None
    except requests.RequestException:
        raise AtlaWireError(
            "Request failed; check connectivity and TLS settings."
        ) from None
    return _decode_json(payload)


def _decode_json(payload: bytes) -> object:
    """Decode one bounded body as strict UTF-8 JSON with the shared rules.

    The wire bytes must be valid UTF-8; no lossy replacement is allowed. One
    leading UTF-8 BOM is ignored, as RFC 8259 permits. JSON escapes such as a
    lone surrogate stay ordinary text here: the output layer decides whether a
    decoded value can be printed.
    """
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError:
        raise AtlaWireError("Expected UTF-8 JSON.") from None
    try:
        return json.loads(
            text.removeprefix("\ufeff"),
            parse_constant=_reject_constant,
            parse_float=_finite_float,
        )
    except ValueError, RecursionError:
        raise AtlaWireError("Expected a valid JSON response.") from None


def post_json_object(
    session: requests.Session, url: str, *, body: Mapping[str, object]
) -> dict[str, object]:
    """Perform one streamed JSON POST with the shared read-request policy.

    The body is sent once as JSON with the same timeouts, redirect refusal,
    decoded size cap, strict UTF-8 decoding, and finite-number parsing as
    [get_json_object][atlawire.http.get_json_object].
    Diagnostics are generic, so a failed request never echoes the URL, payload,
    query, or credentials.
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
    decoded = _decode_json(data)
    if not isinstance(decoded, dict):
        raise AtlaWireError("Expected a JSON object.")
    return decoded


def get_json_object(
    session: requests.Session, url: str, *, params: Mapping[str, str | int]
) -> dict[str, object]:
    data = _get_json(session, url, params=params)
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
    path, query, contents, or credentials.
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
    return _decode_utf8_text(payload)


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
