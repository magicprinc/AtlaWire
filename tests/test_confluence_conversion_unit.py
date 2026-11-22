"""Unit tests for the fixed Confluence 6.6 content body conversion adapter.

The documented pair matrix is reconstructed independently from the 6.6
reference. Only synthetic responses are used; no test contacts a real instance
or reads a real credential.
"""

import base64
import json
from contextlib import nullcontext
from typing import Self, cast
from urllib.parse import parse_qs, quote, urlsplit

import pytest
import requests
import responses

from atlawire import confluence_conversion
from atlawire.confluence_conversion import convert_content_body
from atlawire.http import AtlaWireError

BASE = "https://wiki.example.invalid/wiki"
TOKEN = "fixture/conversion+token="
VALUE = "<p>Hello &amp; <strong>world</strong></p>"
PATH = f"{BASE}/rest/api/contentbody/convert"
BEARER = f"Bearer {TOKEN}"
SECRET_MESSAGE = "The response contained the session bearer token."
REQUEST_SECRET_MESSAGE = "The request would include the session bearer token."
SUPPORTED = {
    "storage": ("view", "export_view", "styled_view", "editor"),
    "editor": ("storage",),
}
VALID_PAIRS = [
    (source, target) for source, targets in SUPPORTED.items() for target in targets
]
ALL_SOURCES = ("storage", "editor", "view", "export_view", "styled_view", "unknown")
ALL_TARGETS = ("view", "export_view", "styled_view", "editor", "storage")
INVALID_PAIRS = [
    (source, target)
    for source in ALL_SOURCES
    for target in ALL_TARGETS
    if target not in SUPPORTED.get(source, ())
]


def _forbid_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail the test if invalid input creates a session or sends a request."""

    def unexpected(*args: object, **kwargs: object) -> object:
        raise AssertionError("no session or request expected")

    monkeypatch.setattr(confluence_conversion, "bearer_session", unexpected)
    monkeypatch.setattr(confluence_conversion, "post_json_object", unexpected)


def _register(to: str, payload: object) -> None:
    responses.post(f"{PATH}/{to}", json=payload)


def _request_body() -> dict[str, object]:
    request = responses.calls[0].request
    body = request.body
    assert isinstance(body, bytes | str)
    decoded = json.loads(body)
    assert isinstance(decoded, dict)
    return cast(dict[str, object], decoded)


def _request_url() -> str:
    url = responses.calls[0].request.url
    assert isinstance(url, str)
    return url


def _token_spellings() -> list[tuple[str, str]]:
    standard = base64.b64encode(TOKEN.encode("ascii")).decode("ascii")
    urlsafe = base64.urlsafe_b64encode(TOKEN.encode("ascii")).decode("ascii")
    bearer = base64.b64encode(f"Bearer {TOKEN}".encode()).decode("ascii")
    return [
        ("literal", TOKEN),
        ("percent", quote(TOKEN, safe="")),
        ("base64", standard),
        ("base64-unpadded", standard.rstrip("=")),
        ("base64-urlsafe", urlsafe),
        ("base64-urlsafe-unpadded", urlsafe.rstrip("=")),
        ("base64-bearer", bearer),
    ]


class _TrackingSession:
    """A context-managed session whose closure is observable."""

    def __init__(self) -> None:
        self.closed = False

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc_info: object) -> bool:
        self.closed = True
        return False


@responses.activate
@pytest.mark.parametrize(
    ("representation", "to"),
    VALID_PAIRS,
    ids=[f"{source}-to-{target}" for source, target in VALID_PAIRS],
)
def test_each_documented_pair_sends_the_exact_body_and_fixed_path(
    representation: str, to: str
) -> None:
    payload: dict[str, object] = {
        "value": "<p>rendered</p>",
        # The 6.6 example returns ``storage`` for a conversion to ``view``, so
        # the adapter must not require the returned representation to match.
        "representation": "storage",
        "_links": {
            "base": "https://elsewhere.example.invalid",
            "next": "https://elsewhere.example.invalid/next",
        },
        "_expandable": {"content": "/rest/api/content/1"},
        "unknown": [None, True, 2.5],
    }
    _register(to, payload)

    result = convert_content_body(
        BASE, VALUE, representation=representation, to=to, token=TOKEN
    )

    assert result == payload
    assert len(responses.calls) == 1
    request = responses.calls[0].request
    assert request.method == "POST"
    split = urlsplit(request.url)
    assert f"{split.scheme}://{split.netloc}{split.path}" == f"{PATH}/{to}"
    assert split.query == ""
    assert request.headers["Authorization"] == BEARER
    assert request.headers["Content-Type"] == "application/json"
    assert _request_body() == {"value": VALUE, "representation": representation}


@pytest.mark.parametrize(
    ("representation", "to"),
    INVALID_PAIRS,
    ids=[f"{source}-to-{target}" for source, target in INVALID_PAIRS],
)
def test_an_undocumented_pair_is_rejected_before_any_session(
    monkeypatch: pytest.MonkeyPatch, representation: str, to: str
) -> None:
    _forbid_transport(monkeypatch)

    with pytest.raises(AtlaWireError, match="supported content body conversion"):
        convert_content_body(
            BASE, VALUE, representation=representation, to=to, token=TOKEN
        )


@pytest.mark.parametrize(
    ("representation", "to"),
    [
        pytest.param("Storage", "view", id="source-case"),
        pytest.param("storage", "View", id="target-case"),
        pytest.param("EDITOR", "storage", id="editor-case"),
        pytest.param(None, "view", id="none-source"),
        pytest.param("storage", None, id="none-target"),
        pytest.param(["storage"], "view", id="list-source"),
        pytest.param("storage", ["view"], id="list-target"),
        pytest.param(1, "view", id="int-source"),
        pytest.param("storage", 1, id="int-target"),
        pytest.param(True, "view", id="bool-source"),
        pytest.param("storage", True, id="bool-target"),
    ],
)
def test_a_non_text_or_misspelled_pair_is_rejected_before_any_session(
    monkeypatch: pytest.MonkeyPatch, representation: object, to: object
) -> None:
    _forbid_transport(monkeypatch)

    with pytest.raises(AtlaWireError, match="supported content body conversion"):
        convert_content_body(
            BASE,
            VALUE,
            representation=cast(str, representation),
            to=cast(str, to),
            token=TOKEN,
        )


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(None, id="none"),
        pytest.param(123, id="int"),
        pytest.param(b"<p>x</p>", id="bytes"),
        pytest.param(["<p>x</p>"], id="list"),
        pytest.param(True, id="bool"),
        pytest.param("\ud800", id="lone-surrogate"),
        pytest.param("\udfff", id="lone-low-surrogate"),
    ],
)
def test_a_non_utf8_or_non_text_value_is_rejected_before_any_session(
    monkeypatch: pytest.MonkeyPatch, value: object
) -> None:
    _forbid_transport(monkeypatch)

    with pytest.raises(AtlaWireError, match="content body value"):
        convert_content_body(
            BASE, cast(str, value), representation="storage", to="view", token=TOKEN
        )


@pytest.mark.parametrize(
    "expand",
    [
        pytest.param(123, id="int"),
        pytest.param(True, id="bool"),
        pytest.param(b"body.view", id="bytes"),
        pytest.param(["body.view"], id="list"),
        pytest.param(object(), id="object"),
        pytest.param("\ud800", id="lone-surrogate"),
    ],
)
def test_a_non_utf8_or_non_text_expand_is_rejected_before_any_session(
    monkeypatch: pytest.MonkeyPatch, expand: object
) -> None:
    _forbid_transport(monkeypatch)

    with pytest.raises(AtlaWireError, match="expand"):
        convert_content_body(
            BASE,
            VALUE,
            representation="storage",
            to="view",
            token=TOKEN,
            expand=cast(str, expand),
        )


@responses.activate
def test_an_empty_value_and_empty_expand_are_sent_unchanged() -> None:
    payload = {"value": "", "representation": "view"}
    _register("view", payload)

    result = convert_content_body(
        BASE, "", representation="storage", to="view", token=TOKEN, expand=""
    )

    assert result == payload
    split = urlsplit(_request_url())
    assert split.path == "/wiki/rest/api/contentbody/convert/view"
    assert parse_qs(split.query, keep_blank_values=True) == {"expand": [""]}
    assert _request_body() == {"value": "", "representation": "storage"}


@responses.activate
def test_a_non_ascii_value_round_trips_in_the_json_body() -> None:
    value = "<p>Привет, мир! 😀 &amp;\t\n</p>"
    payload = {"value": value, "representation": "view"}
    _register("view", payload)

    result = convert_content_body(
        BASE, value, representation="storage", to="view", token=TOKEN
    )

    assert result == payload
    assert _request_body() == {"value": value, "representation": "storage"}


@responses.activate
def test_expand_is_the_only_query_key_and_is_percent_encoded() -> None:
    expand = "body.view&to=editor#fragment?x=1"
    _register("view", {"value": "x", "representation": "view"})

    convert_content_body(
        BASE,
        VALUE,
        representation="storage",
        to="view",
        token=TOKEN,
        expand=expand,
    )

    split = urlsplit(_request_url())
    assert split.path == "/wiki/rest/api/contentbody/convert/view"
    assert parse_qs(split.query, keep_blank_values=True) == {"expand": [expand]}
    assert "to=editor" not in split.query
    assert "x=1" not in split.query


@responses.activate
def test_an_omitted_expand_sends_no_query() -> None:
    _register("view", {"value": "x", "representation": "view"})

    convert_content_body(BASE, VALUE, representation="storage", to="view", token=TOKEN)

    assert urlsplit(_request_url()).query == ""


@responses.activate
def test_response_markup_and_links_are_returned_as_data_without_following() -> None:
    payload: dict[str, object] = {
        "value": "<script>alert(1)</script>",
        "representation": "view",
        "_links": {
            "next": "https://elsewhere.example.invalid/next",
            "download": "file:///etc/passwd",
        },
        "unknown": {"nested": [None, True, 2.5]},
    }
    _register("view", payload)

    result = convert_content_body(
        BASE, VALUE, representation="storage", to="view", token=TOKEN
    )

    assert result == payload
    assert len(responses.calls) == 1


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({}, id="empty-object"),
        pytest.param({"value": "x"}, id="missing-representation"),
        pytest.param({"representation": "view"}, id="missing-value"),
        pytest.param({"value": 1, "representation": "view"}, id="int-value"),
        pytest.param({"value": "x", "representation": None}, id="none-rep"),
        pytest.param(
            {"value": "x", "representation": ["view"]}, id="list-representation"
        ),
    ],
)
@responses.activate
def test_a_response_without_two_string_fields_is_rejected(
    payload: dict[str, object],
) -> None:
    _register("view", payload)

    with pytest.raises(AtlaWireError, match="value and representation strings"):
        convert_content_body(
            BASE, VALUE, representation="storage", to="view", token=TOKEN
        )

    assert len(responses.calls) == 1


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param([], id="array"),
        pytest.param("x", id="string"),
        pytest.param(1, id="number"),
        pytest.param(None, id="null"),
    ],
)
@responses.activate
def test_a_top_level_non_object_response_is_rejected(payload: object) -> None:
    responses.post(
        f"{PATH}/view",
        body=json.dumps(payload),
        content_type="application/json",
    )

    with pytest.raises(AtlaWireError, match="JSON object"):
        convert_content_body(
            BASE, VALUE, representation="storage", to="view", token=TOKEN
        )

    assert len(responses.calls) == 1


def test_a_non_object_transport_result_is_rejected_defensively(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The shared post transport already enforces a JSON object. This covers a
    # replaced transport so the adapter does not depend on that guarantee alone.
    monkeypatch.setattr(
        confluence_conversion, "bearer_session", lambda token: nullcontext(object())
    )
    monkeypatch.setattr(
        confluence_conversion,
        "post_json_object",
        lambda *args, **kwargs: ["not", "an", "object"],
    )

    with pytest.raises(AtlaWireError, match="value and representation strings"):
        convert_content_body(
            BASE, VALUE, representation="storage", to="view", token=TOKEN
        )


@pytest.mark.parametrize(
    ("body", "message"),
    [
        pytest.param(b"{", "valid JSON", id="truncated"),
        pytest.param(
            b'{"value":"\xff","representation":"view"}',
            "UTF-8 JSON",
            id="invalid-utf8",
        ),
        pytest.param(b"", "valid JSON", id="empty"),
    ],
)
@responses.activate
def test_malformed_or_non_utf8_json_is_rejected(body: bytes, message: str) -> None:
    responses.post(f"{PATH}/view", body=body, content_type="application/json")

    with pytest.raises(AtlaWireError, match=message):
        convert_content_body(
            BASE, VALUE, representation="storage", to="view", token=TOKEN
        )


@pytest.mark.parametrize(
    ("status", "message"),
    [
        pytest.param(401, "HTTP 401", id="401"),
        pytest.param(403, "HTTP 403", id="403"),
        pytest.param(404, "HTTP 404", id="404"),
        pytest.param(500, "HTTP 500", id="500"),
        pytest.param(206, "HTTP 206", id="206"),
    ],
)
@responses.activate
def test_an_http_failure_is_generic_and_sends_one_request(
    status: int, message: str
) -> None:
    sentinel = "RESPONSE-SENTINEL"
    responses.post(
        f"{PATH}/view",
        status=status,
        json={"message": sentinel, "token": TOKEN},
    )

    with pytest.raises(AtlaWireError, match=message) as caught:
        convert_content_body(
            BASE, VALUE, representation="storage", to="view", token=TOKEN
        )

    assert sentinel not in str(caught.value)
    assert TOKEN not in str(caught.value)
    assert len(responses.calls) == 1


@responses.activate
def test_a_redirect_is_refused_and_not_followed() -> None:
    responses.post(
        f"{PATH}/view",
        status=302,
        headers={"Location": "https://elsewhere.example.invalid/next"},
        body=b"",
    )

    with pytest.raises(AtlaWireError, match="redirect refused"):
        convert_content_body(
            BASE, VALUE, representation="storage", to="view", token=TOKEN
        )

    assert len(responses.calls) == 1


@pytest.mark.parametrize(
    ("error", "message"),
    [
        pytest.param(requests.Timeout("slow"), "Request timed out.", id="timeout"),
        pytest.param(
            requests.ConnectionError("boom"),
            "Request failed; check connectivity and TLS settings.",
            id="connection",
        ),
    ],
)
@responses.activate
def test_a_transport_error_is_sanitized(error: Exception, message: str) -> None:
    responses.post(f"{PATH}/view", body=error)

    with pytest.raises(AtlaWireError) as caught:
        convert_content_body(
            BASE, VALUE, representation="storage", to="view", token=TOKEN
        )

    assert str(caught.value) == message
    assert TOKEN not in str(caught.value)


@pytest.mark.parametrize(
    "base_url",
    [
        pytest.param("http://127.0.0.1:9/wiki", id="plain-http"),
        pytest.param("https://user:pass@host.invalid/wiki", id="credentials"),
        pytest.param("ftp://host.invalid/wiki", id="wrong-scheme"),
        pytest.param("https://host.invalid/wiki?query=1", id="query"),
        pytest.param("https://host.invalid/wiki/#fragment", id="fragment"),
        pytest.param("https://host.invalid:0/wiki", id="zero-port"),
    ],
)
def test_an_invalid_base_url_is_rejected_before_any_session(
    monkeypatch: pytest.MonkeyPatch, base_url: str
) -> None:
    _forbid_transport(monkeypatch)

    with pytest.raises(AtlaWireError, match="HTTPS base URL"):
        convert_content_body(
            base_url, VALUE, representation="storage", to="view", token=TOKEN
        )


@responses.activate
def test_loopback_http_is_accepted_only_with_the_explicit_flag() -> None:
    payload = {"value": "x", "representation": "view"}
    responses.post(
        "http://127.0.0.1:9/wiki/rest/api/contentbody/convert/view", json=payload
    )

    result = convert_content_body(
        "http://127.0.0.1:9/wiki",
        VALUE,
        representation="storage",
        to="view",
        token=TOKEN,
        allow_http_loopback=True,
    )

    assert result == payload
    assert (
        responses.calls[0].request.url
        == "http://127.0.0.1:9/wiki/rest/api/contentbody/convert/view"
    )


@pytest.mark.parametrize(
    "token",
    [
        pytest.param("", id="empty"),
        pytest.param("bad token", id="space"),
        pytest.param("a\r\nb", id="crlf"),
        pytest.param("a,b", id="comma"),
    ],
)
@responses.activate
def test_an_invalid_token_is_rejected_before_any_request(token: str) -> None:
    with pytest.raises(AtlaWireError, match="bearer token"):
        convert_content_body(
            BASE, VALUE, representation="storage", to="view", token=token
        )

    assert len(responses.calls) == 0


@pytest.mark.parametrize(
    "spelling",
    [value for _, value in _token_spellings()],
    ids=[label for label, _ in _token_spellings()],
)
def test_a_token_echo_in_the_value_is_refused_before_transmission(
    monkeypatch: pytest.MonkeyPatch, spelling: str
) -> None:
    posted: list[object] = []
    monkeypatch.setattr(
        confluence_conversion, "bearer_session", lambda token: nullcontext(object())
    )

    def unexpected(*args: object, **kwargs: object) -> object:
        posted.append((args, kwargs))
        raise AssertionError("no request may be sent")

    monkeypatch.setattr(confluence_conversion, "post_json_object", unexpected)

    with pytest.raises(AtlaWireError) as caught:
        convert_content_body(
            BASE,
            f"prefix {spelling} suffix",
            representation="storage",
            to="view",
            token=TOKEN,
        )

    assert str(caught.value) == REQUEST_SECRET_MESSAGE
    assert TOKEN not in str(caught.value)
    assert posted == []


@pytest.mark.parametrize(
    "spelling",
    [value for _, value in _token_spellings()],
    ids=[label for label, _ in _token_spellings()],
)
def test_a_token_echo_in_expand_is_refused_before_transmission(
    monkeypatch: pytest.MonkeyPatch, spelling: str
) -> None:
    posted: list[object] = []
    monkeypatch.setattr(
        confluence_conversion, "bearer_session", lambda token: nullcontext(object())
    )

    def unexpected(*args: object, **kwargs: object) -> object:
        posted.append((args, kwargs))
        raise AssertionError("no request may be sent")

    monkeypatch.setattr(confluence_conversion, "post_json_object", unexpected)

    with pytest.raises(AtlaWireError) as caught:
        convert_content_body(
            BASE,
            VALUE,
            representation="storage",
            to="view",
            token=TOKEN,
            expand=f"body.view,{spelling}",
        )

    assert str(caught.value) == REQUEST_SECRET_MESSAGE
    assert TOKEN not in str(caught.value)
    assert posted == []


@responses.activate
@pytest.mark.parametrize(
    ("token", "representation", "to", "expand"),
    [
        pytest.param("storage", "storage", "view", None, id="body-representation"),
        pytest.param("storage", "editor", "storage", None, id="path-storage"),
        pytest.param("view", "storage", "view", None, id="path-view"),
        pytest.param("convert", "storage", "view", None, id="path-convert"),
        pytest.param("editor", "storage", "editor", None, id="path-editor"),
        pytest.param(
            "export_view", "storage", "export_view", None, id="path-export-view"
        ),
        pytest.param(
            "styled_view", "storage", "styled_view", None, id="path-styled-view"
        ),
        pytest.param("representation", "storage", "view", None, id="body-key"),
        pytest.param("value", "storage", "view", None, id="value-key"),
        pytest.param("expand", "storage", "view", "body.view", id="query-key"),
    ],
)
def test_fixed_request_text_coinciding_with_the_token_does_not_block_the_request(
    token: str,
    representation: str,
    to: str,
    expand: str | None,
) -> None:
    # Fixed route names, keys, representations and serializer output are
    # protocol text, not credential-derived; only the caller's value and expand
    # are inspected. ``value`` and ``representation`` also name mandatory
    # response fields, so a successful document would always echo those tokens;
    # a controlled 401 keeps the check on the request, before any response echo.
    sentinel = "FIXED-TEXT-RESPONSE-SENTINEL"
    if token in {"value", "representation"}:
        responses.post(f"{PATH}/{to}", status=401, json={"message": sentinel})
        with pytest.raises(AtlaWireError) as caught:
            convert_content_body(
                BASE,
                VALUE,
                representation=representation,
                to=to,
                token=token,
                expand=expand,
            )
        assert str(caught.value) == "HTTP 401: authentication rejected."
        assert sentinel not in str(caught.value)
        assert token not in str(caught.value)
    else:
        payload: dict[str, object] = {
            "value": "x",
            # ``view`` is the token under test here, so return another
            # documented representation that does not contain it.
            "representation": "storage" if token == "view" else "view",
        }
        _register(to, payload)
        assert (
            convert_content_body(
                BASE,
                VALUE,
                representation=representation,
                to=to,
                token=token,
                expand=expand,
            )
            == payload
        )

    assert len(responses.calls) == 1
    request = responses.calls[0].request
    assert request.method == "POST"
    split = urlsplit(request.url)
    assert f"{split.scheme}://{split.netloc}{split.path}" == f"{PATH}/{to}"
    assert parse_qs(split.query, keep_blank_values=True) == (
        {"expand": [expand]} if expand is not None else {}
    )
    assert request.headers["Authorization"] == f"Bearer {token}"
    assert _request_body() == {"value": VALUE, "representation": representation}


@responses.activate
def test_an_ascii_escaped_unicode_value_is_caller_data_not_a_credential() -> None:
    # U+1234 is a single code point; neither it nor the mapping contains the
    # ASCII token. Serialization may spell it as the ASCII escape ``\u1234`` on
    # the wire, but serializer output is not credential-derived caller content,
    # so the conversion proceeds. A literal token in the caller value is still
    # refused by the tests above.
    token = "u1234"
    value = chr(0x1234)
    payload = {"value": "x", "representation": "view"}
    _register("view", payload)

    result = convert_content_body(
        BASE, value, representation="storage", to="view", token=token
    )

    assert result == payload
    assert len(responses.calls) == 1
    request = responses.calls[0].request
    assert request.method == "POST"
    split = urlsplit(request.url)
    assert f"{split.scheme}://{split.netloc}{split.path}" == f"{PATH}/view"
    assert split.query == ""
    assert request.headers["Authorization"] == f"Bearer {token}"
    assert _request_body() == {"value": value, "representation": "storage"}
    raw = request.body
    assert isinstance(raw, bytes | str)
    wire = raw.decode("utf-8") if isinstance(raw, bytes) else raw
    assert value in wire or "\\u1234" in wire


def test_a_request_echo_message_containing_the_token_is_preserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    posted: list[object] = []
    monkeypatch.setattr(
        confluence_conversion, "bearer_session", lambda token: nullcontext(object())
    )

    def unexpected(*args: object, **kwargs: object) -> object:
        posted.append((args, kwargs))
        raise AssertionError("no request may be sent")

    monkeypatch.setattr(confluence_conversion, "post_json_object", unexpected)

    with pytest.raises(AtlaWireError) as caught:
        convert_content_body(
            BASE,
            "prefix request suffix",
            representation="storage",
            to="view",
            token="request",
        )

    assert str(caught.value) == REQUEST_SECRET_MESSAGE
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert posted == []


@pytest.mark.parametrize(
    ("token", "message"),
    [
        pytest.param("JSON", "Expected a valid JSON response.", id="json"),
        pytest.param(
            "response", "Expected a valid JSON response.", id="response"
        ),
        pytest.param(
            "Expected", "Expected a valid JSON response.", id="expected"
        ),
        pytest.param("HTTP", "HTTP 401: authentication rejected.", id="http"),
        pytest.param(
            "ordinary-token",
            "HTTP 401: authentication rejected.",
            id="preserved",
        ),
        pytest.param(
            "",
            "HTTP 401: authentication rejected.",
            id="empty-token",
        ),
    ],
)
def test_an_error_message_is_preserved_even_when_it_contains_the_token(
    monkeypatch: pytest.MonkeyPatch, token: str, message: str
) -> None:
    monkeypatch.setattr(
        confluence_conversion, "bearer_session", lambda value: nullcontext(object())
    )

    def failing(*args: object, **kwargs: object) -> object:
        raise AtlaWireError(message)

    monkeypatch.setattr(confluence_conversion, "post_json_object", failing)

    with pytest.raises(AtlaWireError) as caught:
        convert_content_body(
            BASE, VALUE, representation="storage", to="view", token=token
        )

    assert str(caught.value) == message
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


@pytest.mark.parametrize(
    "spelling",
    [value for _, value in _token_spellings()],
    ids=[label for label, _ in _token_spellings()],
)
def test_an_encoded_token_spelling_in_a_diagnostic_is_preserved(
    monkeypatch: pytest.MonkeyPatch, spelling: str
) -> None:
    monkeypatch.setattr(
        confluence_conversion, "bearer_session", lambda value: nullcontext(object())
    )

    def failing(*args: object, **kwargs: object) -> object:
        raise AtlaWireError(f"diagnostic {spelling}")

    monkeypatch.setattr(confluence_conversion, "post_json_object", failing)

    with pytest.raises(AtlaWireError) as caught:
        convert_content_body(
            BASE, VALUE, representation="storage", to="view", token=TOKEN
        )

    assert str(caught.value) == f"diagnostic {spelling}"
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


def test_a_validation_diagnostic_containing_the_token_is_preserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_transport(monkeypatch)

    with pytest.raises(AtlaWireError) as caught:
        convert_content_body(
            BASE, VALUE, representation="view", to="storage", token="storage"
        )

    assert str(caught.value) == (
        "Expected a supported content body conversion: storage to view, "
        "export_view, styled_view, or editor, or editor to storage."
    )
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


def test_an_invalid_value_diagnostic_containing_the_token_is_preserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_transport(monkeypatch)

    with pytest.raises(AtlaWireError) as caught:
        convert_content_body(
            BASE,
            cast(str, 123),
            representation="storage",
            to="view",
            token="value",
        )

    assert str(caught.value) == (
        "Expected the content body value to be a UTF-8 string."
    )
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


def test_an_invalid_expand_diagnostic_containing_the_token_is_preserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_transport(monkeypatch)

    with pytest.raises(AtlaWireError) as caught:
        convert_content_body(
            BASE,
            VALUE,
            representation="storage",
            to="view",
            token="expand",
            expand=cast(str, 123),
        )

    assert str(caught.value) == "Expected expand to be an optional UTF-8 string."
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


def test_an_invalid_base_url_diagnostic_containing_the_token_is_preserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _forbid_transport(monkeypatch)

    with pytest.raises(AtlaWireError) as caught:
        convert_content_body(
            "https://user:pass@host.invalid/wiki",
            VALUE,
            representation="storage",
            to="view",
            token="base",
        )

    assert str(caught.value) == (
        "Use an HTTPS base URL without credentials, query, or fragment."
    )
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


def test_a_bearer_diagnostic_containing_the_token_is_preserved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing(token: str) -> object:
        raise AtlaWireError("Missing or invalid bearer token.")

    monkeypatch.setattr(confluence_conversion, "bearer_session", failing)

    with pytest.raises(AtlaWireError) as caught:
        convert_content_body(
            BASE, VALUE, representation="storage", to="view", token="bearer"
        )

    assert str(caught.value) == "Missing or invalid bearer token."
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param({"value": TOKEN, "representation": "view"}, id="value"),
        pytest.param({"value": "x", "representation": TOKEN}, id="representation"),
        pytest.param(
            {"value": "x", "representation": "view", "extra": TOKEN},
            id="unknown-field",
        ),
        pytest.param(
            {"value": "x", "representation": "view", TOKEN: "key"},
            id="mapping-key",
        ),
        pytest.param(
            {
                "value": "x",
                "representation": "view",
                "extra": base64.b64encode(TOKEN.encode()).decode(),
            },
            id="base64-unknown-field",
        ),
        pytest.param(
            {
                "value": "x",
                "representation": "view",
                "extra": quote(TOKEN, safe=""),
            },
            id="percent-unknown-field",
        ),
        pytest.param(
            {"value": ["x", TOKEN], "representation": "view"},
            id="nested-sequence",
        ),
    ],
)
def test_the_adapter_rejects_a_token_echo_in_the_returned_object(
    monkeypatch: pytest.MonkeyPatch, payload: dict[str, object]
) -> None:
    monkeypatch.setattr(
        confluence_conversion, "bearer_session", lambda token: nullcontext(object())
    )
    monkeypatch.setattr(
        confluence_conversion,
        "post_json_object",
        lambda *args, **kwargs: payload,
    )

    with pytest.raises(AtlaWireError) as caught:
        convert_content_body(
            BASE, VALUE, representation="storage", to="view", token=TOKEN
        )

    assert str(caught.value) == SECRET_MESSAGE
    assert TOKEN not in str(caught.value)


@responses.activate
def test_a_near_match_is_returned_unchanged() -> None:
    near = TOKEN[:-1] + "X"
    payload = {"value": near, "representation": "view"}
    _register("view", payload)

    result = convert_content_body(
        BASE, VALUE, representation="storage", to="view", token=TOKEN
    )

    assert result == payload
    assert len(responses.calls) == 1


def test_the_session_is_closed_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _TrackingSession()
    payload = {"value": "x", "representation": "view"}
    monkeypatch.setattr(confluence_conversion, "bearer_session", lambda token: session)
    monkeypatch.setattr(
        confluence_conversion,
        "post_json_object",
        lambda *args, **kwargs: payload,
    )

    result = convert_content_body(
        BASE, VALUE, representation="storage", to="view", token=TOKEN
    )

    assert result is payload
    assert session.closed


def test_the_session_is_closed_when_the_request_echo_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _TrackingSession()
    monkeypatch.setattr(confluence_conversion, "bearer_session", lambda token: session)
    monkeypatch.setattr(
        confluence_conversion,
        "post_json_object",
        lambda *args, **kwargs: pytest.fail("no request may be sent"),
    )

    with pytest.raises(AtlaWireError, match="request would include"):
        convert_content_body(
            BASE, TOKEN, representation="storage", to="view", token=TOKEN
        )

    assert session.closed


def test_the_session_is_closed_when_the_transport_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _TrackingSession()
    monkeypatch.setattr(confluence_conversion, "bearer_session", lambda token: session)

    def failing(*args: object, **kwargs: object) -> object:
        raise AtlaWireError("transport failed")

    monkeypatch.setattr(confluence_conversion, "post_json_object", failing)

    with pytest.raises(AtlaWireError, match="transport failed"):
        convert_content_body(
            BASE, VALUE, representation="storage", to="view", token=TOKEN
        )

    assert session.closed


def test_the_session_is_closed_when_the_returned_echo_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _TrackingSession()
    monkeypatch.setattr(confluence_conversion, "bearer_session", lambda token: session)
    monkeypatch.setattr(
        confluence_conversion,
        "post_json_object",
        lambda *args, **kwargs: {"value": TOKEN, "representation": "view"},
    )

    with pytest.raises(AtlaWireError) as caught:
        convert_content_body(
            BASE, VALUE, representation="storage", to="view", token=TOKEN
        )

    assert str(caught.value) == SECRET_MESSAGE
    assert session.closed
