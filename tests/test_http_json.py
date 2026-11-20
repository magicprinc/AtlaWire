import pytest
import responses

from atlawire.http import (
    AtlaWireError,
    bearer_session,
    get_json_array,
    get_json_object,
)

URL = "https://jira.example.invalid/rest/api/2/status"
TOKEN = "fixture-only"


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
