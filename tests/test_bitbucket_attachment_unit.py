"""Unit tests for the read-only Bitbucket attachment download adapter.

The route is BBK-observed and not documented in the local Bitbucket Server 5.10
core reference, so these tests pin only the adapter contract: one fixed GET,
exact bytes, a caller bound, and the shared transport policy. Every response is
synthetic.
"""

import base64
import gzip
import inspect
from collections.abc import Callable, Iterator
from typing import Self, cast
from urllib.parse import quote

import pytest
import requests
import responses
from requests.adapters import BaseAdapter
from urllib3.exceptions import ProtocolError
from urllib3.response import HTTPResponse

from atlawire import bitbucket_attachment, http
from atlawire.bitbucket_attachment import get_repository_attachment
from atlawire.http import AtlaWireError, bearer_session

BASE = "https://bitbucket.example.invalid/scm"
TOKEN = "fixture/attachment+token="
REPO = "DEMO/widgets"
ATTACHMENT_ID = "12345"
URL = (
    f"{BASE}/rest/api/1.0/projects/DEMO/repos/widgets"
    f"/attachments/{ATTACHMENT_ID}"
)
PAYLOAD = (
    bytes(range(256)) * 3
    + b"\x00\xff\r\nhttps://evil.invalid/never-followed"
)
BEARER_HEADER = f"Bearer {TOKEN}"
SECRET_MESSAGE = "The response contained the session bearer token."


def _forbidden_session(token: str) -> object:
    raise AssertionError("session created before argument validation")


def _no_session(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bitbucket_attachment, "bearer_session", _forbidden_session)


@responses.activate
def test_returns_exact_arbitrary_bytes_from_one_accept_any_get() -> None:
    responses.get(URL, body=PAYLOAD, content_type="application/octet-stream")

    result = get_repository_attachment(BASE, REPO, ATTACHMENT_ID, token=TOKEN)

    assert result == PAYLOAD
    assert len(responses.calls) == 1
    request = responses.calls[0].request
    assert request.method == "GET"
    assert request.url == URL
    assert request.headers["Accept"] == "*/*"
    assert request.headers["Authorization"] == BEARER_HEADER


@responses.activate
def test_project_and_slug_are_rebuilt_from_validated_segments() -> None:
    expected = (
        f"{BASE}/rest/api/1.0/projects/~team.name/repos/repo-1.0"
        "/attachments/12345"
    )
    responses.get(expected, body=b"ok")

    result = get_repository_attachment(
        BASE, "~team.name/repo-1.0", ATTACHMENT_ID, token=TOKEN
    )

    assert result == b"ok"
    assert responses.calls[0].request.url == expected


@responses.activate
def test_a_link_in_the_body_is_returned_not_followed() -> None:
    body = b"see https://evil.invalid/next for details"
    responses.get(URL, body=body)

    assert get_repository_attachment(BASE, REPO, ATTACHMENT_ID, token=TOKEN) == body
    assert len(responses.calls) == 1


@pytest.mark.parametrize(
    "repo",
    [
        "DEMO",
        "",
        "/widgets",
        "DEMO/",
        "DEMO/a/b",
        "../widgets",
        "DEMO/..",
        "DEMO/.",
        "DEMO/%2e%2e",
        "DEMO/a%2Fb",
        "DEMO/a b",
        "DEMO/a\\b",
        "DEMO//x",
    ],
    ids=[
        "missing-slug",
        "empty",
        "missing-project",
        "empty-slug",
        "extra-segment",
        "parent-project",
        "dot-dot-slug",
        "dot-slug",
        "percent-dot-dot",
        "percent-separator",
        "space",
        "backslash",
        "double-separator",
    ],
)
def test_invalid_repo_is_rejected_before_any_session(
    monkeypatch: pytest.MonkeyPatch, repo: str
) -> None:
    _no_session(monkeypatch)

    with pytest.raises(AtlaWireError, match="PROJECT/slug"):
        get_repository_attachment(BASE, repo, ATTACHMENT_ID, token=TOKEN)


@pytest.mark.parametrize("repo", [None, 123], ids=["none", "int"])
def test_non_text_repo_is_rejected_before_any_session(
    monkeypatch: pytest.MonkeyPatch, repo: object
) -> None:
    _no_session(monkeypatch)

    with pytest.raises(AtlaWireError, match="PROJECT/slug"):
        get_repository_attachment(
            BASE, cast(str, repo), ATTACHMENT_ID, token=TOKEN
        )


@pytest.mark.parametrize(
    "attachment_id",
    [
        "",
        "../secret",
        "a/b",
        "a%2Fb",
        "a%5Cb",
        "a\\b",
        "a b",
        "a\nb",
        "a\x00b",
        "..",
        ".hidden",
        "a?b",
        "a#b",
        "a+b",
        "a:b",
    ],
    ids=[
        "empty",
        "parent",
        "separator",
        "percent-slash",
        "percent-backslash",
        "backslash",
        "space",
        "lf",
        "nul",
        "dot-dot",
        "dot-lead",
        "query",
        "fragment",
        "plus",
        "colon",
    ],
)
def test_invalid_attachment_id_is_rejected_before_any_session(
    monkeypatch: pytest.MonkeyPatch, attachment_id: str
) -> None:
    _no_session(monkeypatch)

    with pytest.raises(AtlaWireError, match="attachment ID"):
        get_repository_attachment(
            BASE, REPO, attachment_id, token=TOKEN
        )


@pytest.mark.parametrize("attachment_id", [None, 123], ids=["none", "int"])
def test_non_text_attachment_id_is_rejected_before_any_session(
    monkeypatch: pytest.MonkeyPatch, attachment_id: object
) -> None:
    _no_session(monkeypatch)

    with pytest.raises(AtlaWireError, match="attachment ID"):
        get_repository_attachment(
            BASE, REPO, cast(str, attachment_id), token=TOKEN
        )


@pytest.mark.parametrize(
    "max_bytes",
    [0, -1, True, False, 1.0, "1", None],
    ids=["zero", "negative", "true", "false", "float", "text", "none"],
)
def test_max_bytes_must_be_a_positive_integer(
    monkeypatch: pytest.MonkeyPatch, max_bytes: object
) -> None:
    _no_session(monkeypatch)

    with pytest.raises(AtlaWireError, match="positive integer"):
        get_repository_attachment(
            BASE,
            REPO,
            ATTACHMENT_ID,
            token=TOKEN,
            max_bytes=cast(int, max_bytes),
        )


def test_default_bound_matches_the_shared_json_budget() -> None:
    default = inspect.signature(get_repository_attachment).parameters[
        "max_bytes"
    ].default

    assert default == http._JSON_LIMIT
    assert bitbucket_attachment._DEFAULT_MAX_BYTES == http._JSON_LIMIT


@responses.activate
def test_zero_byte_attachment_is_returned_as_empty_bytes() -> None:
    responses.get(URL, body=b"")

    assert get_repository_attachment(BASE, REPO, ATTACHMENT_ID, token=TOKEN) == b""


@responses.activate
def test_a_body_exactly_at_the_explicit_bound_is_accepted() -> None:
    body = b"\x00abc\xff"
    responses.get(URL, body=body)

    result = get_repository_attachment(
        BASE, REPO, ATTACHMENT_ID, token=TOKEN, max_bytes=len(body)
    )

    assert result == body


@responses.activate
def test_one_byte_over_the_explicit_bound_raises_without_partial_bytes() -> None:
    responses.get(URL, body=b"abcd")

    with pytest.raises(AtlaWireError, match="3-byte limit"):
        get_repository_attachment(
            BASE, REPO, ATTACHMENT_ID, token=TOKEN, max_bytes=3
        )


@pytest.mark.parametrize(
    "base_url",
    [
        "http://127.0.0.1:1",
        "https://user:pass@host.invalid",
        "ftp://host.invalid",
        "https://host.invalid/path?query=1",
        "https://host.invalid/#fragment",
        "https://host.invalid:0",
    ],
    ids=[
        "plain-http",
        "credentials",
        "wrong-scheme",
        "query",
        "fragment",
        "zero-port",
    ],
)
def test_invalid_base_url_is_rejected_before_any_session(
    monkeypatch: pytest.MonkeyPatch, base_url: str
) -> None:
    _no_session(monkeypatch)

    with pytest.raises(AtlaWireError, match="HTTPS base URL"):
        get_repository_attachment(base_url, REPO, ATTACHMENT_ID, token=TOKEN)


@pytest.mark.parametrize(
    "token",
    ["", "bad token", "a\r\nb", "a,b"],
    ids=["empty", "space", "crlf", "comma"],
)
@responses.activate
def test_invalid_token_is_rejected_before_any_request(token: str) -> None:
    with pytest.raises(AtlaWireError, match="bearer token"):
        get_repository_attachment(BASE, REPO, ATTACHMENT_ID, token=token)

    assert len(responses.calls) == 0


def _token_spellings(token: str) -> list[tuple[str, bytes]]:
    raw = token.encode("ascii")
    standard = base64.b64encode(raw)
    urlsafe = base64.urlsafe_b64encode(raw)
    bearer = f"Bearer {token}".encode("ascii")
    return [
        ("literal", raw),
        ("percent", quote(token, safe="").encode("ascii")),
        ("base64", standard),
        ("base64-unpadded", standard.rstrip(b"=")),
        ("base64-urlsafe", urlsafe),
        ("base64-urlsafe-unpadded", urlsafe.rstrip(b"=")),
        ("base64-bearer", base64.b64encode(bearer)),
        ("embedded", b"\x00prefix" + raw + b"\xffsuffix"),
    ]


@pytest.mark.parametrize(
    "body",
    [body for _, body in _token_spellings(TOKEN)],
    ids=[label for label, _ in _token_spellings(TOKEN)],
)
@responses.activate
def test_token_spellings_in_the_body_are_rejected(body: bytes) -> None:
    responses.get(URL, body=body)

    with pytest.raises(AtlaWireError) as caught:
        get_repository_attachment(BASE, REPO, ATTACHMENT_ID, token=TOKEN)

    assert str(caught.value) == SECRET_MESSAGE
    assert TOKEN not in str(caught.value)
    assert len(responses.calls) == 1


@responses.activate
def test_a_near_match_is_returned_unchanged() -> None:
    body = TOKEN[:-1].encode("ascii") + b"\x00\xff"
    responses.get(URL, body=body)

    assert get_repository_attachment(BASE, REPO, ATTACHMENT_ID, token=TOKEN) == body


@responses.activate
def test_a_body_whose_base64_is_the_token_is_not_rejected_by_the_adapter() -> None:
    # The shared guard inspects the raw body. A crafted body whose *base64
    # serialization* is the token is therefore the CLI serializer's problem:
    # the CLI owner checks the final serialized output before printing it.
    token = base64.b64encode(b"\xfb\xff\xfe" * 8).decode("ascii")
    body = base64.b64decode(token, validate=True)
    assert base64.b64encode(body) == token.encode("ascii")
    responses.get(URL, body=body)

    assert get_repository_attachment(BASE, REPO, ATTACHMENT_ID, token=token) == body


class _CountingRaw:
    """A urllib3-like raw body that records bytes, close, and release calls."""

    def __init__(self, body: bytes) -> None:
        self._body = body
        self._offset = 0
        self.consumed = 0
        self.closed = False
        self.close_calls = 0
        self.release_conn_calls = 0

    def stream(
        self, chunk_size: int | None, decode_content: bool = True
    ) -> Iterator[bytes]:
        del decode_content
        while chunk := self.read(chunk_size):
            yield chunk

    def read(
        self, amount: int | None = None, decode_content: bool | None = None
    ) -> bytes:
        del decode_content
        end = len(self._body) if amount is None else self._offset + amount
        chunk = self._body[self._offset : end]
        self._offset += len(chunk)
        self.consumed += len(chunk)
        return chunk

    def release_conn(self) -> None:
        self.release_conn_calls += 1

    def close(self) -> None:
        self.close_calls += 1
        self.closed = True


class _GzipDecodingRaw(_CountingRaw):
    """A raw body whose stream yields gzip-decoded content."""

    def __init__(self, body: bytes) -> None:
        super().__init__(body)
        self._decoded = gzip.decompress(body)

    def stream(
        self, chunk_size: int | None, decode_content: bool = True
    ) -> Iterator[bytes]:
        if not decode_content:
            raise AssertionError("the adapter must request decoded content")
        if not self._decoded:
            return
        size = len(self._decoded) if chunk_size is None else chunk_size
        for offset in range(0, len(self._decoded), size):
            chunk = self._decoded[offset : offset + size]
            self.consumed += len(chunk)
            yield chunk


class _FailingRaw(_CountingRaw):
    """A raw body that yields one prefix and then raises a stream error."""

    def __init__(self, body: bytes, error: Exception) -> None:
        super().__init__(body)
        self._error = error

    def stream(
        self, chunk_size: int | None, decode_content: bool = True
    ) -> Iterator[bytes]:
        del chunk_size, decode_content
        if self._body:
            self.consumed += len(self._body)
            yield self._body
        raise self._error


class _SyntheticAdapter(BaseAdapter):
    """Return one fixed response without any network access."""

    def __init__(
        self,
        *,
        status: int,
        body: bytes,
        location: str | None = None,
        raw_factory: Callable[[bytes], _CountingRaw] | None = None,
    ) -> None:
        self._status = status
        self._body = body
        self._location = location
        self._raw_factory = raw_factory or _CountingRaw
        self.calls = 0
        self.raw: _CountingRaw | None = None

    def send(
        self,
        request: requests.PreparedRequest,
        stream: bool = False,
        timeout: object = None,
        verify: object = True,
        cert: object = None,
        proxies: dict[str, str] | None = None,
    ) -> requests.Response:
        del stream, timeout, verify, cert, proxies
        self.calls += 1
        response = requests.Response()
        response.status_code = self._status
        response.url = request.url or ""
        response.request = request
        if self._location is not None:
            response.headers["Location"] = self._location
        self.raw = self._raw_factory(self._body)
        response.raw = cast(HTTPResponse, self.raw)
        return response

    def close(self) -> None:
        pass


class _TrackingSession:
    """A real no-redirect session whose closure and calls are recorded."""

    def __init__(self, adapter: BaseAdapter) -> None:
        self._session = bearer_session(TOKEN)
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.closed = False

    def get(
        self,
        url: str,
        *,
        headers: dict[str, str],
        timeout: tuple[int, int],
        allow_redirects: bool,
        stream: bool,
    ) -> requests.Response:
        self.calls.append(
            (
                url,
                {
                    "headers": headers,
                    "timeout": timeout,
                    "allow_redirects": allow_redirects,
                    "stream": stream,
                },
            )
        )
        return self._session.get(
            url,
            headers=headers,
            timeout=timeout,
            allow_redirects=allow_redirects,
            stream=stream,
        )

    def close(self) -> None:
        self.closed = True
        self._session.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> bool:
        self.close()
        return False


def _install(
    monkeypatch: pytest.MonkeyPatch, adapter: BaseAdapter
) -> _TrackingSession:
    session = _TrackingSession(adapter)
    monkeypatch.setattr(
        bitbucket_attachment, "bearer_session", lambda token: session
    )
    return session


def _assert_released(raw: _CountingRaw) -> None:
    """An exhausted body is returned to the pool without closing the raw.

    Installed Requests 2.34.2 ``Response.close`` calls ``raw.close()`` only
    while ``_content_consumed`` is false; it always calls ``release_conn``.
    """
    assert raw.release_conn_calls == 1
    assert raw.close_calls == 0
    assert not raw.closed


def _assert_closed_and_released(raw: _CountingRaw) -> None:
    """An unread or abandoned stream is both closed and returned to the pool."""
    assert raw.close_calls == 1
    assert raw.release_conn_calls == 1
    assert raw.closed


def test_success_releases_the_exhausted_response_and_closes_the_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = b"\x00\x01\xff" * 50
    adapter = _SyntheticAdapter(status=200, body=body)
    session = _install(monkeypatch, adapter)

    result = get_repository_attachment(BASE, REPO, ATTACHMENT_ID, token=TOKEN)

    assert result == body
    assert adapter.calls == 1
    assert adapter.raw is not None
    assert adapter.raw.consumed == len(body)
    _assert_released(adapter.raw)
    assert session.closed
    assert len(session.calls) == 1
    url, kwargs = session.calls[0]
    assert url == URL
    assert kwargs["headers"] == {"Accept": "*/*"}
    assert kwargs["timeout"] == (5, 30)
    assert kwargs["allow_redirects"] is False
    assert kwargs["stream"] is True


def test_loopback_http_is_accepted_only_with_the_explicit_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _SyntheticAdapter(status=200, body=b"ok")
    session = _install(monkeypatch, adapter)

    result = get_repository_attachment(
        "http://127.0.0.1:9/scm",
        REPO,
        ATTACHMENT_ID,
        token=TOKEN,
        allow_http_loopback=True,
    )

    assert result == b"ok"
    assert session.calls[0][0] == (
        "http://127.0.0.1:9/scm/rest/api/1.0/projects/DEMO/repos/widgets"
        "/attachments/12345"
    )
    assert adapter.raw is not None
    _assert_released(adapter.raw)
    assert session.closed


@pytest.mark.parametrize(
    ("status", "detail"),
    [
        (206, "HTTP 206"),
        (401, "HTTP 401"),
        (403, "HTTP 403"),
        (404, "HTTP 404"),
        (500, "HTTP 500"),
    ],
    ids=["206", "401", "403", "404", "500"],
)
def test_failed_status_never_reads_the_body_and_closes_everything(
    monkeypatch: pytest.MonkeyPatch, status: int, detail: str
) -> None:
    body = b"x" * (1024 * 1024)
    adapter = _SyntheticAdapter(status=status, body=body)
    session = _install(monkeypatch, adapter)

    with pytest.raises(AtlaWireError, match=detail) as caught:
        get_repository_attachment(BASE, REPO, ATTACHMENT_ID, token=TOKEN)

    assert TOKEN not in str(caught.value)
    assert adapter.raw is not None
    assert adapter.raw.consumed == 0
    _assert_closed_and_released(adapter.raw)
    assert session.closed
    assert len(session.calls) == 1


def test_redirect_is_refused_without_draining_or_following(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _SyntheticAdapter(
        status=302,
        body=b"x" * 65536,
        location="https://evil.invalid/next",
    )
    session = _install(monkeypatch, adapter)

    with pytest.raises(AtlaWireError, match="redirect refused"):
        get_repository_attachment(BASE, REPO, ATTACHMENT_ID, token=TOKEN)

    assert adapter.calls == 1
    assert adapter.raw is not None
    assert adapter.raw.consumed == 0
    _assert_closed_and_released(adapter.raw)
    assert session.closed


def test_a_location_header_on_success_does_not_create_a_second_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = _SyntheticAdapter(
        status=200,
        body=b"ok",
        location="https://evil.invalid/next",
    )
    session = _install(monkeypatch, adapter)

    assert get_repository_attachment(BASE, REPO, ATTACHMENT_ID, token=TOKEN) == b"ok"
    assert adapter.calls == 1
    assert adapter.raw is not None
    _assert_released(adapter.raw)
    assert session.closed


def test_over_cap_stops_streaming_before_the_whole_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limit = 10
    body = b"x" * (2 * 64 * 1024)
    adapter = _SyntheticAdapter(status=200, body=body)
    session = _install(monkeypatch, adapter)

    with pytest.raises(AtlaWireError, match="10-byte limit"):
        get_repository_attachment(
            BASE, REPO, ATTACHMENT_ID, token=TOKEN, max_bytes=limit
        )

    assert adapter.raw is not None
    assert limit < adapter.raw.consumed < len(body)
    _assert_closed_and_released(adapter.raw)
    assert session.closed


def test_token_echo_rejection_releases_the_exhausted_response_and_closes_the_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = TOKEN.encode("ascii")
    adapter = _SyntheticAdapter(status=200, body=body)
    session = _install(monkeypatch, adapter)

    with pytest.raises(AtlaWireError) as caught:
        get_repository_attachment(BASE, REPO, ATTACHMENT_ID, token=TOKEN)

    assert str(caught.value) == SECRET_MESSAGE
    assert adapter.raw is not None
    assert adapter.raw.consumed == len(body)
    _assert_released(adapter.raw)
    assert session.closed


def test_compressed_body_exactly_at_the_decoded_cap_is_returned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = b"x" * 64
    compressed = gzip.compress(payload)
    assert len(compressed) < len(payload)
    adapter = _SyntheticAdapter(
        status=200, body=compressed, raw_factory=_GzipDecodingRaw
    )
    session = _install(monkeypatch, adapter)

    result = get_repository_attachment(
        BASE, REPO, ATTACHMENT_ID, token=TOKEN, max_bytes=len(payload)
    )

    assert result == payload
    assert adapter.raw is not None
    assert adapter.raw.consumed == len(payload)
    _assert_released(adapter.raw)
    assert session.closed


def test_compressed_body_one_byte_over_the_decoded_cap_raises_and_closes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limit = 64
    payload = b"x" * (limit + 1)
    compressed = gzip.compress(payload)
    assert len(compressed) < limit
    adapter = _SyntheticAdapter(
        status=200, body=compressed, raw_factory=_GzipDecodingRaw
    )
    session = _install(monkeypatch, adapter)

    with pytest.raises(AtlaWireError, match="64-byte limit"):
        get_repository_attachment(
            BASE, REPO, ATTACHMENT_ID, token=TOKEN, max_bytes=limit
        )

    assert adapter.raw is not None
    assert adapter.raw.consumed == len(payload)
    _assert_closed_and_released(adapter.raw)
    assert session.closed


@pytest.mark.parametrize(
    "error",
    [
        ProtocolError(
            "Connection broken: IncompleteRead(7 bytes read, 3 more expected)"
        ),
        ProtocolError("Response ended prematurely"),
    ],
    ids=["content-length-shortfall", "incomplete-chunked"],
)
def test_truncated_stream_after_a_prefix_fails_generically_and_closes(
    monkeypatch: pytest.MonkeyPatch, error: ProtocolError
) -> None:
    prefix = b"PRIVATE-PREFIX"
    adapter = _SyntheticAdapter(
        status=200,
        body=prefix,
        raw_factory=lambda body: _FailingRaw(body, error),
    )
    session = _install(monkeypatch, adapter)

    with pytest.raises(AtlaWireError) as caught:
        get_repository_attachment(BASE, REPO, ATTACHMENT_ID, token=TOKEN)

    assert str(caught.value) == (
        "Request failed; check connectivity and TLS settings."
    )
    assert prefix.decode("ascii") not in str(caught.value)
    assert adapter.raw is not None
    assert adapter.raw.consumed == len(prefix)
    _assert_closed_and_released(adapter.raw)
    assert session.closed


def test_streaming_exception_text_with_a_credential_is_not_echoed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prefix = b"prefix-" + TOKEN.encode("ascii")
    error = ProtocolError(f"Connection broken: {TOKEN}")
    adapter = _SyntheticAdapter(
        status=200,
        body=prefix,
        raw_factory=lambda body: _FailingRaw(body, error),
    )
    session = _install(monkeypatch, adapter)

    with pytest.raises(AtlaWireError) as caught:
        get_repository_attachment(BASE, REPO, ATTACHMENT_ID, token=TOKEN)

    assert str(caught.value) == (
        "Request failed; check connectivity and TLS settings."
    )
    assert TOKEN not in str(caught.value)
    assert prefix.decode("ascii") not in str(caught.value)
    assert adapter.raw is not None
    # The prefix (and its credential) was consumed before the failure; only the
    # generic exception may escape, never a partial return value.
    assert adapter.raw.consumed == len(prefix)
    _assert_closed_and_released(adapter.raw)
    assert session.closed


class _RaisingSession:
    """A caller-owned session whose single GET raises a transport error."""

    def __init__(self, error: Exception) -> None:
        self.error = error
        self.calls = 0
        self.closed = False

    def get(self, url: str, **kwargs: object) -> requests.Response:
        del url, kwargs
        self.calls += 1
        raise self.error

    def close(self) -> None:
        self.closed = True

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> bool:
        self.close()
        return False


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (requests.Timeout("slow"), "Request timed out."),
        (
            requests.ConnectionError("boom"),
            "Request failed; check connectivity and TLS settings.",
        ),
    ],
    ids=["timeout", "connection"],
)
def test_transport_errors_are_sanitized_and_close_the_session(
    monkeypatch: pytest.MonkeyPatch, error: Exception, message: str
) -> None:
    session = _RaisingSession(error)
    monkeypatch.setattr(
        bitbucket_attachment, "bearer_session", lambda token: session
    )

    with pytest.raises(AtlaWireError) as caught:
        get_repository_attachment(BASE, REPO, ATTACHMENT_ID, token=TOKEN)

    assert str(caught.value) == message
    assert TOKEN not in str(caught.value)
    assert session.calls == 1
    assert session.closed
