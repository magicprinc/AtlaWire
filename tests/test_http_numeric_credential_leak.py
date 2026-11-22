"""Numeric JSON leaves must not disclose the session bearer token.

An independently reviewed counterexample placed the token in an unknown integer
field. The earlier traversal inspected only strings and mapping keys, so the
decoded number reached any GET or POST adapter unchanged. These tests derive
the contract from that leak: the original valid UTF-8 JSON wire text and the
decoded object are both checked, including a float whose normalized Python
spelling differs from its wire spelling. Every credential and body here is
synthetic.
"""

import json
from collections.abc import Callable

import pytest
import responses

from atlawire.http import (
    AtlaWireError,
    bearer_session,
    get_json_array,
    get_json_object,
    get_json_object_allow_no_content,
    post_json_object,
    reject_credential_echo,
)

URL = "https://jira.example.invalid/rest/api/2/issue/DEMO-1"
TOKEN = "987654321"
MESSAGE = "The response contained the session bearer token."


def _assert_echo_rejected(
    call: Callable[[], object], *, token: str = TOKEN
) -> None:
    with pytest.raises(AtlaWireError) as raised:
        call()
    assert str(raised.value) == MESSAGE
    assert token not in str(raised.value)


@pytest.mark.parametrize(
    ("token", "body"),
    [
        pytest.param(
            TOKEN,
            b'{"issue":{"fields":{"unknownCount":987654321}}}',
            id="unknown-int-field",
        ),
        pytest.param(
            TOKEN,
            b'{"issue":{"fields":{"unknownCount":-987654321}}}',
            id="negative-int",
        ),
        pytest.param(
            TOKEN,
            b'{"issue":{"fields":{"values":[[[987654321]]]}}}',
            id="nested-array",
        ),
        pytest.param(
            TOKEN,
            b'{"issue":{"fields":{"unknownCount":9.87654321e8}}}',
            id="normalized-fractional-float",
        ),
        pytest.param(
            "1000000000",
            b'{"unknownCount":1e9}',
            id="normalized-scientific-float",
        ),
        pytest.param(
            "123456789",
            b'{"unknownCount":1.23456789e8}',
            id="normalized-fractional-exponent",
        ),
        pytest.param(
            "1e9",
            b'{"unknownCount":1e9}',
            id="raw-scientific-spelling",
        ),
        pytest.param(
            "1.23456789e8",
            b'{"unknownCount":1.23456789e8}',
            id="raw-fractional-exponent",
        ),
    ],
)
@responses.activate
def test_get_json_rejects_a_numeric_token_in_the_wire_or_decoded_value(
    token: str, body: bytes
) -> None:
    responses.get(URL, body=body, content_type="application/json")

    with bearer_session(token) as session:
        _assert_echo_rejected(
            lambda: get_json_object(session, URL, params={}), token=token
        )

    assert len(responses.calls) == 1


@responses.activate
def test_read_only_post_rejects_the_same_numeric_echo() -> None:
    responses.post(URL, json={"value": 987654321})

    with bearer_session(TOKEN) as session:
        _assert_echo_rejected(
            lambda: post_json_object(session, URL, body={"q": "safe"})
        )

    assert len(responses.calls) == 1


@responses.activate
def test_array_reader_rejects_a_nested_numeric_token() -> None:
    responses.get(URL, json=[{"values": [{"deep": [987654321]}]}])

    with bearer_session(TOKEN) as session:
        _assert_echo_rejected(lambda: get_json_array(session, URL, params={}))

    assert len(responses.calls) == 1


def test_explicit_guard_inspects_numeric_leaves() -> None:
    with pytest.raises(AtlaWireError) as raised:
        reject_credential_echo({"count": 987654321}, tokens=(TOKEN,))

    assert str(raised.value) == MESSAGE
    assert TOKEN not in str(raised.value)


@responses.activate
def test_benign_near_matches_and_arbitrary_shapes_are_returned_exactly() -> None:
    payload = {
        "int": 98765432,
        "other": 987654322,
        "negative": -98765432,
        "float": 9.87654322e8,
        "nested": [0, -1, 1.25, [98765432], {"n": 1000000000}],
        "text": "98765432",
        "flag": True,
        "none": None,
    }
    responses.get(URL, json=payload)

    with bearer_session(TOKEN) as session:
        assert get_json_object(session, URL, params={}) == payload

    assert len(responses.calls) == 1


@responses.activate
def test_malformed_json_keeps_its_diagnostic_with_the_token_in_the_text() -> None:
    responses.get(
        URL, body=b'{"unknownCount":987654321', content_type="application/json"
    )

    with (
        bearer_session(TOKEN) as session,
        pytest.raises(AtlaWireError) as raised,
    ):
        get_json_object(session, URL, params={})

    assert str(raised.value) == "Expected a valid JSON response."
    assert TOKEN not in str(raised.value)
    assert len(responses.calls) == 1


@responses.activate
def test_no_content_204_short_circuits_before_numeric_inspection() -> None:
    responses.get(URL, status=204)

    with bearer_session(TOKEN) as session:
        assert get_json_object_allow_no_content(session, URL, params={}) is None

    assert len(responses.calls) == 1


@responses.activate
def test_raw_u1234_response_is_not_rejected_by_a_later_rendering_escape() -> None:
    # U+1234 is one code point, not the ASCII token. The transport inspects the
    # original UTF-8 wire and must return it; only a later json.dumps rendering
    # creates the "\u1234" escape, which the conversion CLI's final guard owns.
    token = "u1234"
    payload = {"value": "<p>\u1234</p>"}
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    assert token.encode("ascii") not in raw
    responses.get(URL, body=raw, content_type="application/json")

    with bearer_session(token) as session:
        assert get_json_object(session, URL, params={}) == payload

    rendered = json.dumps(payload)
    assert token in rendered
    with pytest.raises(AtlaWireError) as raised:
        reject_credential_echo(rendered, tokens=(token,))
    assert str(raised.value) == MESSAGE


@responses.activate
def test_ascii_escaped_u1234_wire_spelling_is_rejected() -> None:
    # Here the server itself sent the ASCII escape, so the token spelling really
    # is in the original wire text even though the decoded value is U+1234.
    token = "u1234"
    raw = b'{"value":"<p>\\u1234</p>"}'
    assert token.encode("ascii") in raw
    responses.get(URL, body=raw, content_type="application/json")

    with bearer_session(token) as session:
        _assert_echo_rejected(
            lambda: get_json_object(session, URL, params={}), token=token
        )

    assert len(responses.calls) == 1
