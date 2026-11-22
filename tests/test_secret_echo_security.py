"""Fail-closed checks for a response that echoes the session bearer token.

Every credential and body here is synthetic. The tests prove that the shared
transport rejects the leak before data reaches a caller, while ordinary
responses, 204 handling, and session-like fakes stay unchanged.
"""

import base64
import json
import re
from collections.abc import Callable, Iterator
from typing import cast
from urllib.parse import quote, quote_plus

import pytest
import requests
import responses

from atlawire.http import (
    AtlaWireError,
    bearer_session,
    get_json_array,
    get_json_object,
    get_json_object_allow_no_content,
    get_text,
    post_json_object,
    reject_credential_echo,
)

URL = "https://jira.example.invalid/rest/api/2/issue/DEMO-1"
TEXT_URL = "https://bitbucket.example.invalid/rest/api/1.0/raw/notes.txt"
TOKEN = "Fixture/S3cret+Token=="
OTHER_TOKEN = "fixture-other-credential"
# This token produces different standard and URL-safe base64 spellings for
# both the token and the complete Bearer header.
URLSAFE_TOKEN = "Pg~V~neQ"
ECHO_MESSAGE = "The response contained the session bearer token."


def _lower_percent_escapes(value: str) -> str:
    return re.sub(r"%[0-9A-Fa-f]{2}", lambda match: match.group(0).lower(), value)


def _escaped(token: str) -> str:
    """Spell every character as a JSON Unicode escape."""
    return "".join(f"\\u{ord(char):04x}" for char in token)


def _b64(value: str, *, urlsafe: bool = False, pad: bool = True) -> str:
    raw = value.encode("utf-8")
    encoder = base64.urlsafe_b64encode if urlsafe else base64.b64encode
    encoded = encoder(raw).decode("ascii")
    return encoded if pad else encoded.rstrip("=")


QUOTED = quote(TOKEN, safe="")
QUOTED_PLUS = quote_plus(TOKEN, safe="")
# A path encoder may leave "/" literal while escaping the query-sensitive "+"
# and "=". Standard quote/quote_plus forms alone would miss this mixture.
PARTIALLY_QUOTED = TOKEN.replace("+", "%2B").replace("=", "%3D")
FULLY_QUOTED = "".join(f"%{ord(char):02X}" for char in TOKEN)
TOKEN_B64 = _b64(TOKEN)
TOKEN_B64_UNPADDED = _b64(TOKEN, pad=False)
HEADER_B64 = _b64(f"Bearer {TOKEN}")
HEADER_B64_URL_UNPADDED = _b64(f"Bearer {TOKEN}", urlsafe=True, pad=False)
OTHER_HEADER_B64 = _b64(f"Bearer {OTHER_TOKEN}")

JSON_ECHO_BODIES = [
    pytest.param(json.dumps({"outer": [{"value": TOKEN}]}).encode(), id="nested-value"),
    pytest.param(json.dumps({"outer": [{TOKEN: "safe"}]}).encode(), id="nested-key"),
    pytest.param(
        f'{{"outer":[{{"value":"{_escaped(TOKEN)}"}}]}}'.encode(),
        id="escaped-value",
    ),
    pytest.param(
        f'{{"outer":[{{"{_escaped(TOKEN)}":"safe"}}]}}'.encode(),
        id="escaped-key",
    ),
    pytest.param(
        json.dumps({"outer": {"value": QUOTED}}).encode(),
        id="url-encoded-value",
    ),
    pytest.param(
        json.dumps({"outer": {QUOTED: "safe"}}).encode(),
        id="url-encoded-key",
    ),
    pytest.param(
        json.dumps({"outer": {"value": _lower_percent_escapes(QUOTED)}}).encode(),
        id="url-encoded-lowercase-value",
    ),
    pytest.param(
        json.dumps({"outer": {"value": PARTIALLY_QUOTED}}).encode(),
        id="url-partially-encoded-value",
    ),
    pytest.param(
        json.dumps({"outer": {"value": FULLY_QUOTED}}).encode(),
        id="url-fully-encoded-value",
    ),
    pytest.param(
        json.dumps({"outer": {"value": TOKEN_B64}}).encode(),
        id="base64-value",
    ),
    pytest.param(
        json.dumps({"outer": {TOKEN_B64_UNPADDED: "safe"}}).encode(),
        id="base64-unpadded-key",
    ),
    pytest.param(
        json.dumps({"outer": {"value": HEADER_B64}}).encode(),
        id="base64-header-value",
    ),
    pytest.param(
        json.dumps({"outer": {HEADER_B64_URL_UNPADDED: "safe"}}).encode(),
        id="base64-header-unpadded-key",
    ),
]

TEXT_ECHO_BODIES = [
    pytest.param(f"before\n{TOKEN}\nafter\n", id="literal"),
    pytest.param(f"token={QUOTED}\n", id="url-encoded"),
    pytest.param(f"token={QUOTED_PLUS}\n", id="url-encoded-plus"),
    pytest.param(
        f"token={_lower_percent_escapes(QUOTED)}\n",
        id="url-encoded-lowercase",
    ),
    pytest.param(f"token={PARTIALLY_QUOTED}\n", id="url-partially-encoded"),
    pytest.param(f"token={TOKEN_B64}\n", id="base64"),
    pytest.param(f"token={TOKEN_B64_UNPADDED}\n", id="base64-unpadded"),
    pytest.param(f"token={HEADER_B64}\n", id="base64-header"),
    pytest.param(f"token={HEADER_B64_URL_UNPADDED}\n", id="base64-header-unpadded"),
]


def _assert_echo_rejected(
    call: Callable[[], object], *, token: str = TOKEN
) -> None:
    with pytest.raises(AtlaWireError) as raised:
        call()
    assert str(raised.value) == ECHO_MESSAGE
    assert token not in str(raised.value)


@responses.activate
@pytest.mark.parametrize("body", JSON_ECHO_BODIES)
def test_json_get_rejects_token_in_nested_keys_values_and_escapes(
    body: bytes,
) -> None:
    responses.get(URL, body=body, content_type="application/json")

    with bearer_session(TOKEN) as session:
        _assert_echo_rejected(lambda: get_json_object(session, URL, params={}))


@responses.activate
def test_json_array_reader_rejects_a_nested_token() -> None:
    responses.get(URL, json=[{"values": ["safe", {"deep": [TOKEN]}]}])

    with bearer_session(TOKEN) as session:
        _assert_echo_rejected(lambda: get_json_array(session, URL, params={}))


@responses.activate
@pytest.mark.parametrize(
    "body",
    [
        pytest.param(
            {"outer": {"value": _b64(URLSAFE_TOKEN, urlsafe=True, pad=False)}},
            id="token-value",
        ),
        pytest.param(
            {
                "outer": {
                    _b64(f"Bearer {URLSAFE_TOKEN}", urlsafe=True, pad=False): "safe"
                }
            },
            id="header-key",
        ),
    ],
)
def test_urlsafe_base64_forms_are_rejected(body: dict[str, object]) -> None:
    responses.get(URL, json=body)

    with bearer_session(URLSAFE_TOKEN) as session:
        _assert_echo_rejected(
            lambda: get_json_object(session, URL, params={}),
            token=URLSAFE_TOKEN,
        )


@responses.activate
@pytest.mark.parametrize("body", TEXT_ECHO_BODIES)
def test_text_get_rejects_literal_and_url_encoded_tokens(body: str) -> None:
    responses.get(TEXT_URL, body=body.encode(), content_type="text/plain")

    with bearer_session(TOKEN) as session:
        _assert_echo_rejected(lambda: get_text(session, TEXT_URL, params={}))


@responses.activate
def test_read_only_post_rejects_a_token_in_its_successful_response() -> None:
    responses.post(URL, json={"issues": [{"fields": {"summary": TOKEN}}]})

    with bearer_session(TOKEN) as session:
        _assert_echo_rejected(
            lambda: post_json_object(session, URL, body={"jql": "project = DEMO"})
        )


@responses.activate
def test_unrelated_text_is_returned_exactly_without_scrubbing() -> None:
    body = (
        "  first  line\n"
        "S3cret + Token / fixture %2F %2B\n"
        f"unrelated={OTHER_HEADER_B64} hello=aGVsbG8=\n\n"
        "last line  "
    )
    responses.get(TEXT_URL, body=body.encode(), content_type="text/plain")

    with bearer_session(TOKEN) as session:
        assert get_text(session, TEXT_URL, params={}) == body


@responses.activate
def test_unrelated_json_and_post_results_keep_exact_semantics() -> None:
    payload = {
        "name": "fixture",
        "nested": {
            "values": ["S3cret + Token", "fixture/secret"],
            "encoded": ["aGVsbG8=", OTHER_HEADER_B64],
            "flags": [True, None, 1.5],
        },
    }
    responses.get(URL, json=payload)
    responses.post(URL, json={"ok": True})

    with bearer_session(TOKEN) as session:
        assert get_json_object(session, URL, params={}) == payload
        assert post_json_object(session, URL, body={"q": "safe"}) == {"ok": True}


def test_explicit_credential_check_covers_multiple_tokens_and_keys() -> None:
    value = {"ordinary": [{TOKEN: "safe"}]}

    with pytest.raises(AtlaWireError) as raised:
        reject_credential_echo(value, tokens=(OTHER_TOKEN, TOKEN))

    assert str(raised.value) == ECHO_MESSAGE
    assert TOKEN not in str(raised.value)


def test_explicit_credential_check_accepts_rendered_text() -> None:
    with pytest.raises(AtlaWireError) as raised:
        reject_credential_echo(f"rendered value: {TOKEN_B64}", tokens=(TOKEN,))

    assert str(raised.value) == ECHO_MESSAGE
    assert TOKEN_B64 not in str(raised.value)


def test_explicit_credential_check_ignores_empty_tokens() -> None:
    # An absent credential must never become the empty substring that matches
    # every value.
    reject_credential_echo("ordinary text", tokens=())
    reject_credential_echo("ordinary text", tokens=("",))


@responses.activate
def test_a_different_credential_is_not_the_selected_session_token() -> None:
    body = f"other={OTHER_TOKEN}\nheader={OTHER_HEADER_B64}\n"
    responses.get(TEXT_URL, body=body.encode(), content_type="text/plain")

    with bearer_session(TOKEN) as session:
        assert get_text(session, TEXT_URL, params={}) == body


@responses.activate
def test_no_content_reader_still_returns_none_for_204() -> None:
    responses.get(URL, status=204)

    with bearer_session(TOKEN) as session:
        assert get_json_object_allow_no_content(session, URL, params={}) is None


@responses.activate
def test_existing_object_reader_still_rejects_204() -> None:
    responses.get(URL, status=204)

    with (
        bearer_session(TOKEN) as session,
        pytest.raises(AtlaWireError, match="valid JSON"),
    ):
        get_json_object(session, URL, params={})


class _TextResponse:
    status_code = 200
    headers = {"Content-Type": "text/plain"}

    def __init__(self, body: bytes) -> None:
        self._body = body
        self.closed = False

    def __enter__(self) -> "_TextResponse":
        return self

    def __exit__(self, *exc_info: object) -> bool:
        self.closed = True
        return False

    def iter_content(self, chunk_size: int) -> Iterator[bytes]:
        yield self._body


class _SessionWithoutHeaders:
    """A session-like fake used by established tests: no headers mapping."""

    def __init__(self, body: bytes) -> None:
        self.response = _TextResponse(body)

    def get(self, *args: object, **kwargs: object) -> _TextResponse:
        return self.response


def test_session_fake_without_headers_keeps_the_previous_behavior() -> None:
    body = f"fake session data\n{TOKEN}\n"
    session = _SessionWithoutHeaders(body.encode())

    assert get_text(cast(requests.Session, session), TEXT_URL, params={}) == body
    assert session.response.closed
