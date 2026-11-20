"""Shared JSON transport for self-hosted Atlassian reads."""

import math
import re
from collections.abc import Mapping
from urllib.parse import urlsplit

import requests

_TEXT_LIMIT = 1024 * 1024
_TEXT_CHUNK = 64 * 1024
_BIDI_CONTROLS = frozenset(
    "\u061c\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"
)


class AtlaWireError(Exception):
    """An operation failed with a message safe for CLI diagnostics."""


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
    """Create a session that the caller must close."""
    if not re.fullmatch(r"[A-Za-z0-9._~+/=-]+", token):
        raise AtlaWireError("Missing or invalid bearer token.")
    session = requests.Session()
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
    """Apply the shared read-only status policy without echoing the request."""
    if 300 <= status < 400:
        raise AtlaWireError(f"HTTP {status}: redirect refused; check the base URL.")
    if status == 401:
        raise AtlaWireError("HTTP 401: authentication rejected.")
    if status == 403:
        raise AtlaWireError("HTTP 403: access denied.")
    if not 200 <= status < 300:
        raise AtlaWireError(f"HTTP {status}: request failed.")


def get_json_object(
    session: requests.Session, url: str, *, params: Mapping[str, str | int]
) -> dict[str, object]:
    try:
        with session.get(
            url, params=params, timeout=(5, 30), allow_redirects=False
        ) as response:
            _check_status(response.status_code)
            try:
                data: object = response.json(
                    parse_constant=_reject_constant, parse_float=_finite_float
                )
            except ValueError, RecursionError:
                raise AtlaWireError("Expected a valid JSON response.") from None
    except requests.Timeout:
        raise AtlaWireError("Request timed out.") from None
    except requests.RequestException:
        raise AtlaWireError(
            "Request failed; check connectivity and TLS settings."
        ) from None
    if not isinstance(data, dict):
        raise AtlaWireError("Expected a JSON object.")
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
            if response.status_code == 206:
                raise AtlaWireError("HTTP 206: partial content is not supported.")
            _check_text_type(response.headers.get("Content-Type"))
            payload = _read_limited(response)
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


def _read_limited(response: requests.Response) -> bytes:
    """Accumulate decoded chunks, rejecting the first byte beyond the limit."""
    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_content(chunk_size=_TEXT_CHUNK):
        total += len(chunk)
        if total > _TEXT_LIMIT:
            raise AtlaWireError("The text response exceeds the 1 MiB limit.")
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
