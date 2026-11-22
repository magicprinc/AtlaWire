from collections.abc import Callable, Iterator
from io import BytesIO
from typing import cast

import pytest
import requests
import responses
from requests.adapters import BaseAdapter
from urllib3.response import HTTPResponse

from atlawire.http import (
    AtlaWireError,
    bearer_session,
    get_json_array,
    get_json_object,
    get_json_object_allow_no_content,
    get_text,
    post_json_object,
)

URL = "https://jira.example.invalid/rest/api/2/status"
TOKEN = "fixture-only"
JSON_LIMIT = 8 * 1024 * 1024


def _oversized_object() -> bytes:
    """A valid JSON object whose decoded form is one byte over the limit."""
    pad = b"a" * (JSON_LIMIT - 9)
    body = b'{"pad":"' + pad + b'"}'
    assert len(body) == JSON_LIMIT + 1
    return body


def _exact_limit_object() -> bytes:
    pad = b"a" * (JSON_LIMIT - 10)
    body = b'{"pad":"' + pad + b'"}'
    assert len(body) == JSON_LIMIT
    return body


@responses.activate
def test_post_json_object_keeps_the_shared_object_and_number_rules() -> None:
    responses.post(URL, json={"ok": True})
    responses.post(URL, body="[1e999]", content_type="application/json")
    responses.post(URL, json=["not", "an", "object"])

    with bearer_session(TOKEN) as session:
        assert post_json_object(session, URL, body={"q": "x"}) == {"ok": True}
    for match in ("valid JSON", "JSON object"):
        with (
            bearer_session(TOKEN) as session,
            pytest.raises(AtlaWireError, match=match),
        ):
            post_json_object(session, URL, body={"q": "x"})


@responses.activate
def test_post_json_object_refuses_a_redirect_without_following_it() -> None:
    responses.post(URL, status=302, headers={"Location": "https://evil.invalid/"})

    with (
        bearer_session(TOKEN) as session,
        pytest.raises(AtlaWireError, match="redirect refused"),
    ):
        post_json_object(session, URL, body={"q": "x"})

    assert len(responses.calls) == 1


@responses.activate
def test_json_readers_reject_a_partial_response_before_decoding() -> None:
    responses.get(URL, status=206, json={"ok": True})
    responses.get(URL, status=206, body="not json", content_type="application/json")
    responses.post(URL, status=206, json={"ok": True})

    for _ in range(2):
        with (
            bearer_session(TOKEN) as session,
            pytest.raises(AtlaWireError, match="HTTP 206"),
        ):
            get_json_object(session, URL, params={})
    with (
        bearer_session(TOKEN) as session,
        pytest.raises(AtlaWireError, match="HTTP 206"),
    ):
        post_json_object(session, URL, body={"q": "x"})

    assert [call.request.method for call in responses.calls] == ["GET", "GET", "POST"]


@responses.activate
def test_get_json_array_accepts_a_list_and_rejects_an_object() -> None:
    responses.get(URL, json=[{"name": "Open"}])

    with bearer_session(TOKEN) as session:
        assert get_json_array(session, URL, params={}) == [{"name": "Open"}]
    with (
        bearer_session(TOKEN) as session,
        pytest.raises(AtlaWireError, match="JSON object"),
    ):
        get_json_object(session, URL, params={})


@responses.activate
def test_get_json_object_accepts_an_object_and_rejects_a_list() -> None:
    responses.get(URL, json={"name": "Open"})

    with bearer_session(TOKEN) as session:
        assert get_json_object(session, URL, params={}) == {"name": "Open"}
    with (
        bearer_session(TOKEN) as session,
        pytest.raises(AtlaWireError, match="JSON array"),
    ):
        get_json_array(session, URL, params={})


@responses.activate
def test_array_reader_keeps_the_shared_finite_number_parser() -> None:
    responses.get(URL, body="[1e999]", content_type="application/json")

    with (
        bearer_session(TOKEN) as session,
        pytest.raises(AtlaWireError, match="valid JSON"),
    ):
        get_json_array(session, URL, params={})


@responses.activate
def test_get_json_object_rejects_invalid_wire_utf8_instead_of_replacing_it() -> None:
    responses.get(URL, body=b'{"name":"x\xffy"}', content_type="application/json")

    with (
        bearer_session(TOKEN) as session,
        pytest.raises(AtlaWireError, match="UTF-8"),
    ):
        get_json_object(session, URL, params={})


@responses.activate
def test_post_json_object_rejects_invalid_wire_utf8_instead_of_replacing_it() -> None:
    responses.post(URL, body=b'{"name":"x\xffy"}', content_type="application/json")

    with (
        bearer_session(TOKEN) as session,
        pytest.raises(AtlaWireError, match="UTF-8"),
    ):
        post_json_object(session, URL, body={"q": "x"})


@responses.activate
def test_json_reader_keeps_accepting_an_escaped_lone_surrogate() -> None:
    # JSON escapes are text, not invalid wire bytes; the output layer owns the
    # decision about unprintable characters, so the transport must not reject it.
    responses.get(URL, body=b'{"name":"\\ud800"}', content_type="application/json")

    with bearer_session(TOKEN) as session:
        assert get_json_object(session, URL, params={}) == {"name": "\ud800"}


@responses.activate
def test_json_reader_ignores_one_leading_utf8_bom() -> None:
    responses.get(
        URL,
        body=b'\xef\xbb\xbf{"name":"Open"}',
        content_type="application/json; charset=utf-8",
    )

    with bearer_session(TOKEN) as session:
        assert get_json_object(session, URL, params={}) == {"name": "Open"}


@responses.activate
def test_get_json_object_accepts_a_body_at_the_decoded_byte_limit() -> None:
    responses.get(URL, body=_exact_limit_object(), content_type="application/json")

    with bearer_session(TOKEN) as session:
        value = get_json_object(session, URL, params={})

    pad = value["pad"]
    assert isinstance(pad, str)
    assert len(pad) == JSON_LIMIT - 10


@responses.activate
@pytest.mark.parametrize("verb", ["get", "post"])
def test_json_reader_rejects_a_decoded_body_over_the_limit(verb: str) -> None:
    getattr(responses, verb)(
        URL, body=_oversized_object(), content_type="application/json"
    )

    with (
        bearer_session(TOKEN) as session,
        pytest.raises(AtlaWireError, match="8 MiB"),
    ):
        if verb == "get":
            get_json_object(session, URL, params={})
        else:
            post_json_object(session, URL, body={"q": "x"})


class _CountingRaw:
    """A urllib3-like raw body that records every byte it hands out."""

    def __init__(self, body: bytes) -> None:
        self._body = BytesIO(body)
        self.consumed = 0
        self.closed = False

    def stream(
        self, chunk_size: int | None, decode_content: bool = True
    ) -> Iterator[bytes]:
        while chunk := self.read(chunk_size, decode_content):
            yield chunk

    def read(
        self, amount: int | None = None, decode_content: bool | None = None
    ) -> bytes:
        del decode_content
        chunk = self._body.read(amount)
        self.consumed += len(chunk)
        return chunk

    def release_conn(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True
        self._body.close()


class _SyntheticAdapter(BaseAdapter):
    """Return one fixed response without any network access."""

    def __init__(
        self, *, status: int, body: bytes, location: str | None = None
    ) -> None:
        self._status = status
        self._body = body
        self._location = location
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
        self.raw = _CountingRaw(self._body)
        response.raw = cast(HTTPResponse, self.raw)
        return response

    def close(self) -> None:
        pass


def _json_get(session: requests.Session, url: str) -> object:
    return get_json_object(session, url, params={})


def _json_post(session: requests.Session, url: str) -> object:
    return post_json_object(session, url, body={"q": "x"})


def _text_get(session: requests.Session, url: str) -> object:
    return get_text(session, url, params={})


@pytest.mark.parametrize(
    "reader",
    [_json_get, _json_post, _text_get],
    ids=["json-get", "json-post", "text-get"],
)
def test_refused_redirect_body_is_never_consumed(
    reader: Callable[[requests.Session, str], object],
) -> None:
    # Requests 2.34.2 builds the next-request hint for allow_redirects=False by
    # draining the redirect body; the transport must keep it on the wire instead.
    adapter = _SyntheticAdapter(
        status=302,
        body=b'{"pad":"' + b"a" * 4096 + b'"}',
        location="https://evil.invalid/next",
    )

    with bearer_session(TOKEN) as session:
        session.mount(URL, adapter)
        with pytest.raises(AtlaWireError, match="redirect refused"):
            reader(session, URL)

    assert adapter.calls == 1
    assert adapter.raw is not None
    assert adapter.raw.consumed == 0
    assert adapter.raw.closed


def test_failed_status_is_reported_without_reading_the_body() -> None:
    adapter = _SyntheticAdapter(status=500, body=_oversized_object())

    with bearer_session(TOKEN) as session:
        session.mount(URL, adapter)
        with pytest.raises(AtlaWireError, match="HTTP 500"):
            get_json_object(session, URL, params={})

    assert adapter.raw is not None
    assert adapter.raw.consumed == 0


@pytest.mark.parametrize("reader", [_json_get, _json_post], ids=["get", "post"])
def test_oversized_json_stops_before_reading_the_entire_body(
    reader: Callable[[requests.Session, str], object],
) -> None:
    body = b"x" * (JSON_LIMIT + 1024 * 1024)
    adapter = _SyntheticAdapter(status=200, body=body)

    with bearer_session(TOKEN) as session:
        session.mount(URL, adapter)
        with pytest.raises(AtlaWireError, match="8 MiB"):
            reader(session, URL)

    assert adapter.raw is not None
    assert JSON_LIMIT < adapter.raw.consumed < len(body)
    assert adapter.raw.closed


class _NoContentResponse:
    """A 204 response that records closure and rejects body reads."""

    status_code = 204
    headers: dict[str, str] = {}

    def __init__(self) -> None:
        self.closed = False

    def __enter__(self) -> "_NoContentResponse":
        return self

    def __exit__(self, *exc_info: object) -> bool:
        self.closed = True
        return False

    def iter_content(self, chunk_size: int) -> Iterator[bytes]:
        raise AssertionError("A 204 body must not be read")


class _NoContentSession:
    """A caller-owned session that records close and the single GET."""

    def __init__(self) -> None:
        self.response = _NoContentResponse()
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.closed = False

    def get(self, url: str, **kwargs: object) -> _NoContentResponse:
        self.calls.append((url, dict(kwargs)))
        return self.response

    def close(self) -> None:
        self.closed = True

    def __enter__(self) -> "_NoContentSession":
        return self

    def __exit__(self, *exc_info: object) -> bool:
        self.close()
        return False


def test_allow_no_content_204_closes_response_and_session() -> None:
    session = _NoContentSession()

    with session:
        assert get_json_object_allow_no_content(session, URL, params={}) is None

    assert session.response.closed
    assert session.closed
    assert len(session.calls) == 1
    url, kwargs = session.calls[0]
    assert url == URL
    assert kwargs["params"] == {}
    assert kwargs["allow_redirects"] is False


@responses.activate
def test_allow_no_content_204_returns_none_with_the_real_reader() -> None:
    responses.get(URL, status=204)

    with bearer_session(TOKEN) as session:
        assert get_json_object_allow_no_content(session, URL, params={}) is None

    assert len(responses.calls) == 1


@responses.activate
def test_allow_no_content_rejects_200_null_malformed_and_empty_json() -> None:
    responses.get(URL, body="null", content_type="application/json")
    responses.get(URL, body="{", content_type="application/json")
    responses.get(URL, body="", content_type="application/json")

    for match in ("JSON object", "valid JSON", "valid JSON"):
        with (
            bearer_session(TOKEN) as session,
            pytest.raises(AtlaWireError, match=match),
        ):
            get_json_object_allow_no_content(session, URL, params={})

    assert len(responses.calls) == 3


@responses.activate
def test_existing_object_reader_still_rejects_204() -> None:
    responses.get(URL, status=204)

    with (
        bearer_session(TOKEN) as session,
        pytest.raises(AtlaWireError, match="valid JSON"),
    ):
        get_json_object(session, URL, params={})

    assert len(responses.calls) == 1


@responses.activate
def test_allow_no_content_refuses_a_redirect_without_following_it() -> None:
    responses.get(URL, status=302, headers={"Location": "https://evil.invalid/"})

    with (
        bearer_session(TOKEN) as session,
        pytest.raises(AtlaWireError, match="redirect refused"),
    ):
        get_json_object_allow_no_content(session, URL, params={})

    assert len(responses.calls) == 1
