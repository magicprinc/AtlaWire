import pytest
import responses

from atlawire.http import (
    AtlaWireError,
    bearer_session,
    get_json_array,
    get_json_object,
    post_json_object,
)

URL = "https://jira.example.invalid/rest/api/2/status"
TOKEN = "fixture-only"


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
