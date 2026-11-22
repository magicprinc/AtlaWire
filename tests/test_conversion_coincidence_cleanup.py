"""Coincidence boundaries for the fixed Confluence 6.6 conversion POST.

The previous guard rejected any token spelling found anywhere in the fixed
protocol text or in Requests' ASCII escape of caller data. That turned ordinary
content into a preflight failure. These tests pin the intended boundary:

* fixed text ``storage``, ``view`` and ``convert``, or an ASCII escape such as
  ``\\u1234`` produced from the caller's U+1234, is not a credential echo;
* the token literally present in the caller's ``value`` or ``expand`` stays a
  refusal before any request;
* a server response that echoes the token still must not be exposed.

Every credential, origin, request and response here is synthetic. Expected
paths, bodies and messages are derived from the documented conversion contract
and the existing fixed diagnostics, not from production URL or serializer
helpers. No test contacts a real instance.
"""

import json
from typing import cast
from urllib.parse import urlsplit

import pytest
import requests
import responses

from atlawire.confluence_conversion import convert_content_body
from atlawire.http import AtlaWireError

BASE = "https://wiki.example.invalid/wiki"
CONVERT_PATH = f"{BASE}/rest/api/contentbody/convert"
VALUE = "<p>Hello &amp; <strong>world</strong></p>"
BENIGN_TOKEN = "synthetic-benign-conversion-token"
# Long enough to be a genuine credential rather than a coincidental substring
# of protocol text or ordinary content.
DISTINCTIVE_TOKEN = "SYNTHETIC-CONVERSION-CREDENTIAL-7f3a9"
UNAUTHORIZED_MESSAGE = "HTTP 401: authentication rejected."
PREFLIGHT_MESSAGE = "The request would include the session bearer token."
RESPONSE_ECHO_MESSAGE = "The response contained the session bearer token."


def _only_request() -> requests.PreparedRequest:
    """Return the single recorded request, proving exactly one was sent."""
    assert len(responses.calls) == 1
    return responses.calls[0].request


def _request_json_body(request: requests.PreparedRequest) -> dict[str, object]:
    body = request.body
    assert isinstance(body, bytes | str)
    decoded = json.loads(body)
    assert isinstance(decoded, dict)
    return cast(dict[str, object], decoded)


def _assert_fixed_endpoint(request: requests.PreparedRequest, to: str) -> None:
    split = urlsplit(request.url)
    assert f"{split.scheme}://{split.netloc}{split.path}" == f"{CONVERT_PATH}/{to}"
    assert split.query == ""


@pytest.mark.parametrize(
    "token",
    [
        pytest.param("storage", id="body-representation"),
        pytest.param("view", id="path-target"),
        pytest.param("convert", id="route-segment"),
    ],
)
@responses.activate
def test_protocol_text_coinciding_with_the_token_does_not_block_the_post(
    token: str,
) -> None:
    sentinel = "COINCIDENCE-401-SENTINEL"
    responses.post(f"{CONVERT_PATH}/view", status=401, json={"message": sentinel})

    with pytest.raises(AtlaWireError) as caught:
        convert_content_body(
            BASE, VALUE, representation="storage", to="view", token=token
        )

    assert str(caught.value) == UNAUTHORIZED_MESSAGE
    assert "would include" not in str(caught.value)
    assert sentinel not in str(caught.value)
    assert token not in str(caught.value)
    request = _only_request()
    assert request.method == "POST"
    _assert_fixed_endpoint(request, "view")
    assert request.headers["Authorization"] == f"Bearer {token}"
    assert _request_json_body(request) == {
        "value": VALUE,
        "representation": "storage",
    }


@responses.activate
def test_unicode_code_point_spelling_the_token_is_data_not_a_credential() -> None:
    token = "u1234"
    value = f"<p>before {chr(0x1234)} after</p>"
    payload = {"value": "<p>safe</p>", "representation": "view"}
    responses.post(f"{CONVERT_PATH}/view", json=payload)

    result = convert_content_body(
        BASE, value, representation="storage", to="view", token=token
    )

    assert result == payload
    request = _only_request()
    assert request.method == "POST"
    _assert_fixed_endpoint(request, "view")
    assert request.headers["Authorization"] == "Bearer u1234"
    assert _request_json_body(request) == {
        "value": value,
        "representation": "storage",
    }
    raw = request.body
    assert isinstance(raw, bytes | str)
    wire = raw.decode("utf-8") if isinstance(raw, bytes) else raw
    # The caller's one code point may reach the wire literally or as the ASCII
    # escape ``\u1234``. Either spelling decodes to the exact caller value and
    # neither is a credential disclosure.
    assert chr(0x1234) in wire or "\\u1234" in wire


@pytest.mark.parametrize(
    ("value", "expand"),
    [
        pytest.param(f"<p>{DISTINCTIVE_TOKEN}</p>", None, id="value"),
        pytest.param(VALUE, f"body.view,{DISTINCTIVE_TOKEN}", id="expand"),
    ],
)
@responses.activate
def test_a_distinctive_token_in_caller_text_is_refused_before_the_post(
    value: str, expand: str | None
) -> None:
    with pytest.raises(AtlaWireError) as caught:
        convert_content_body(
            BASE,
            value,
            representation="storage",
            to="view",
            token=DISTINCTIVE_TOKEN,
            expand=expand,
        )

    assert str(caught.value) == PREFLIGHT_MESSAGE
    assert DISTINCTIVE_TOKEN not in str(caught.value)
    assert len(responses.calls) == 0


@responses.activate
def test_a_server_response_echoing_the_distinctive_token_is_not_exposed() -> None:
    payload = {
        "value": f"<p>{DISTINCTIVE_TOKEN}</p>",
        "representation": "view",
    }
    responses.post(f"{CONVERT_PATH}/view", json=payload)

    with pytest.raises(AtlaWireError) as caught:
        convert_content_body(
            BASE,
            VALUE,
            representation="storage",
            to="view",
            token=DISTINCTIVE_TOKEN,
        )

    assert str(caught.value) == RESPONSE_ECHO_MESSAGE
    assert DISTINCTIVE_TOKEN not in str(caught.value)
    assert payload["value"] not in str(caught.value)
    request = _only_request()
    assert request.method == "POST"
    _assert_fixed_endpoint(request, "view")


@responses.activate
def test_a_redirect_is_still_refused_and_not_followed() -> None:
    redirect_target = "https://elsewhere.example.invalid/next"
    responses.post(
        f"{CONVERT_PATH}/view",
        status=302,
        headers={"Location": redirect_target},
        body=b"",
    )

    with pytest.raises(AtlaWireError, match="redirect refused") as caught:
        convert_content_body(
            BASE,
            VALUE,
            representation="storage",
            to="view",
            token=BENIGN_TOKEN,
        )

    assert redirect_target not in str(caught.value)
    assert len(responses.calls) == 1
    assert responses.calls[0].request.method == "POST"
    assert all(
        "elsewhere.example.invalid" not in call.request.url
        for call in responses.calls
    )


@responses.activate
def test_a_benign_401_is_still_the_ordinary_generic_error() -> None:
    sentinel = "COINCIDENCE-401-SENTINEL"
    responses.post(
        f"{CONVERT_PATH}/view",
        status=401,
        json={"message": sentinel, "token": BENIGN_TOKEN},
    )

    with pytest.raises(AtlaWireError) as caught:
        convert_content_body(
            BASE,
            VALUE,
            representation="storage",
            to="view",
            token=BENIGN_TOKEN,
        )

    assert str(caught.value) == UNAUTHORIZED_MESSAGE
    assert BENIGN_TOKEN not in str(caught.value)
    assert sentinel not in str(caught.value)
    request = _only_request()
    assert request.method == "POST"
    _assert_fixed_endpoint(request, "view")
    assert request.headers["Authorization"] == f"Bearer {BENIGN_TOKEN}"
