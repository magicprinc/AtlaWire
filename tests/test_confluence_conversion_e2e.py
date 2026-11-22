"""Loopback E2E tests for the Confluence content body conversion adapter.

Every request is served by a real HTTP server bound to 127.0.0.1; every
credential, response, and target is synthetic. No test contacts a real
instance. The route and its response shape remain version-specific and
unverified against a live Confluence 6.6 server.
"""

import base64
import gzip
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import quote

import pytest

from atlawire.confluence_conversion import convert_content_body
from atlawire.http import AtlaWireError
from tests._loopback import Request, request_record, send_bytes, serving

CONTEXT = "/wiki"
TOKEN = "fixture-conversion-loopback-token"
BEARER = f"Bearer {TOKEN}"
VALUE = "<p>Hello &amp; <strong>world</strong></p>"
SENTINEL = "CONVERSION-RESPONSE-SENTINEL"
SECRET_MESSAGE = "The response contained the session bearer token."
REQUEST_SECRET_MESSAGE = "The request would include the session bearer token."
JSON_LIMIT = 8 * 1024 * 1024

type Response = tuple[int, bytes, dict[str, str]]


def _json(payload: object) -> bytes:
    return json.dumps(payload).encode("utf-8")


def make_handler(
    seen: list[Request],
    bodies: list[bytes],
    content_types: list[str | None],
    response: Response,
    extra_methods: list[str],
) -> type[BaseHTTPRequestHandler]:
    """Serve one fixed POST response and record the received wire shape."""

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_POST(self) -> None:
            seen.append(request_record(self))
            content_types.append(self.headers.get("Content-Type"))
            length = int(self.headers.get("Content-Length") or "0")
            bodies.append(self.rfile.read(length))
            status, body, headers = response
            if 300 <= status < 400:
                send_bytes(
                    self,
                    status,
                    b"",
                    content_type=None,
                    extra_headers=headers,
                )
                return
            encoding = headers.get("Content-Encoding")
            send_bytes(
                self,
                status,
                body,
                content_type=headers.get("Content-Type"),
                content_encoding=encoding,
                extra_headers={
                    name: value
                    for name, value in headers.items()
                    if name not in {"Content-Type", "Content-Encoding"}
                },
            )

        def _refuse(self, method: str) -> None:
            extra_methods.append(method)
            self.send_error(405)

        def do_GET(self) -> None:
            self._refuse("GET")

        def do_PUT(self) -> None:
            self._refuse("PUT")

        def do_DELETE(self) -> None:
            self._refuse("DELETE")

        def do_PATCH(self) -> None:
            self._refuse("PATCH")

        def do_HEAD(self) -> None:
            self._refuse("HEAD")

        def do_OPTIONS(self) -> None:
            self._refuse("OPTIONS")

    return Handler


def convert_against(
    server: HTTPServer,
    *,
    value: str = VALUE,
    representation: str = "storage",
    to: str = "view",
    expand: str | None = None,
    token: str = TOKEN,
) -> dict[str, object]:
    base = f"http://127.0.0.1:{server.server_port}{CONTEXT}"
    return convert_content_body(
        base,
        value,
        representation=representation,
        to=to,
        token=token,
        expand=expand,
        allow_http_loopback=True,
    )


def test_loopback_success_sends_exact_wire_shape_and_preserves_response() -> None:
    seen: list[Request] = []
    bodies: list[bytes] = []
    content_types: list[str | None] = []
    extra: list[str] = []
    value = "<p>Привет, мир! 😀 &amp;</p>"
    payload: dict[str, object] = {
        "value": "<p>rendered</p>",
        # The 6.6 example returns ``storage`` for a conversion to ``view``, so a
        # matching target representation is not part of the contract.
        "representation": "storage",
        "_links": {
            "base": "https://elsewhere.example.invalid",
            "next": "https://elsewhere.example.invalid/next",
        },
        "_expandable": {"content": "/rest/api/content/1"},
        "unknown": [None, True, 2.5],
    }
    handler = make_handler(
        seen,
        bodies,
        content_types,
        (200, _json(payload), {"Content-Type": "application/json"}),
        extra,
    )

    with serving(handler) as server:
        result = convert_against(server, value=value)

    assert result == payload
    assert seen == [
        (
            "POST",
            f"{CONTEXT}/rest/api/contentbody/convert/view",
            {},
            BEARER,
        )
    ]
    assert content_types == ["application/json"]
    assert json.loads(bodies[0]) == {
        "value": value,
        "representation": "storage",
    }
    assert extra == []


def test_loopback_editor_to_storage_preserves_the_expand_query() -> None:
    seen: list[Request] = []
    bodies: list[bytes] = []
    content_types: list[str | None] = []
    extra: list[str] = []
    handler = make_handler(
        seen,
        bodies,
        content_types,
        (
            200,
            _json({"value": "<p>storage</p>", "representation": "storage"}),
            {"Content-Type": "application/json"},
        ),
        extra,
    )

    with serving(handler) as server:
        result = convert_against(
            server,
            representation="editor",
            to="storage",
            expand="body.view,body.storage",
        )

    assert result == {
        "value": "<p>storage</p>",
        "representation": "storage",
    }
    assert seen == [
        (
            "POST",
            f"{CONTEXT}/rest/api/contentbody/convert/storage",
            {"expand": ["body.view,body.storage"]},
            BEARER,
        )
    ]
    assert json.loads(bodies[0]) == {
        "value": VALUE,
        "representation": "editor",
    }
    assert extra == []


def test_loopback_allows_an_empty_value_and_an_empty_expand() -> None:
    seen: list[Request] = []
    bodies: list[bytes] = []
    content_types: list[str | None] = []
    extra: list[str] = []
    handler = make_handler(
        seen,
        bodies,
        content_types,
        (200, _json({"value": "", "representation": "view"}), {}),
        extra,
    )

    with serving(handler) as server:
        result = convert_against(server, value="", expand="")

    assert result == {"value": "", "representation": "view"}
    assert seen[0][2] == {"expand": [""]}
    assert json.loads(bodies[0]) == {"value": "", "representation": "storage"}
    assert extra == []


def test_loopback_401_is_generic_and_does_not_leak_the_response_body() -> None:
    seen: list[Request] = []
    bodies: list[bytes] = []
    content_types: list[str | None] = []
    extra: list[str] = []
    handler = make_handler(
        seen,
        bodies,
        content_types,
        (
            401,
            _json({"message": SENTINEL, "token": TOKEN}),
            {"Content-Type": "application/json"},
        ),
        extra,
    )

    with (
        serving(handler) as server,
        pytest.raises(AtlaWireError, match="HTTP 401") as caught,
    ):
        convert_against(server)

    assert SENTINEL not in str(caught.value)
    assert TOKEN not in str(caught.value)
    assert len(seen) == 1
    assert extra == []


def test_loopback_redirect_is_refused_without_contacting_the_target() -> None:
    honey_seen: list[Request] = []

    class Honeypot(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def _record(self) -> None:
            honey_seen.append(request_record(self))
            send_bytes(self, 200, b"stolen")

        def do_GET(self) -> None:
            self._record()

        def do_POST(self) -> None:
            self._record()

        def do_PUT(self) -> None:
            self._record()

        def do_DELETE(self) -> None:
            self._record()

        def do_PATCH(self) -> None:
            self._record()

        def do_HEAD(self) -> None:
            honey_seen.append(request_record(self))
            self.send_error(405)

        def do_OPTIONS(self) -> None:
            honey_seen.append(request_record(self))
            self.send_error(405)

    seen: list[Request] = []
    bodies: list[bytes] = []
    content_types: list[str | None] = []
    extra: list[str] = []

    with serving(Honeypot) as honey:
        target = f"http://127.0.0.1:{honey.server_port}/stolen"
        handler = make_handler(
            seen,
            bodies,
            content_types,
            (302, b"", {"Location": target}),
            extra,
        )
        with (
            serving(handler) as server,
            pytest.raises(AtlaWireError, match="redirect refused") as caught,
        ):
            convert_against(server)

    assert target not in str(caught.value)
    assert honey_seen == []
    assert len(seen) == 1
    assert extra == []


def test_loopback_an_oversize_response_is_rejected_without_partial_output() -> None:
    seen: list[Request] = []
    bodies: list[bytes] = []
    content_types: list[str | None] = []
    extra: list[str] = []
    decoded = b'{"value":"' + b"a" * (JSON_LIMIT + 1) + b'","representation":"view"}'
    compressed = gzip.compress(decoded)
    assert len(compressed) < JSON_LIMIT
    handler = make_handler(
        seen,
        bodies,
        content_types,
        (
            200,
            compressed,
            {
                "Content-Type": "application/json",
                "Content-Encoding": "gzip",
            },
        ),
        extra,
    )

    with serving(handler) as server, pytest.raises(AtlaWireError, match="8 MiB"):
        convert_against(server)

    assert len(seen) == 1
    assert extra == []


@pytest.mark.parametrize(
    ("body", "message"),
    [
        pytest.param(b"{", "valid JSON", id="truncated"),
        pytest.param(
            b'{"value":"\xff","representation":"view"}',
            "UTF-8 JSON",
            id="invalid-utf8",
        ),
        pytest.param(b"[]", "JSON object", id="array"),
        pytest.param(
            b'{"value":1,"representation":"view"}',
            "value and representation strings",
            id="int-value",
        ),
        pytest.param(
            b'{"value":"x"}',
            "value and representation strings",
            id="missing-representation",
        ),
    ],
)
def test_loopback_malformed_or_wrong_shape_responses_fail_closed(
    body: bytes, message: str
) -> None:
    seen: list[Request] = []
    bodies: list[bytes] = []
    content_types: list[str | None] = []
    extra: list[str] = []
    handler = make_handler(
        seen,
        bodies,
        content_types,
        (200, body, {"Content-Type": "application/json"}),
        extra,
    )

    with serving(handler) as server, pytest.raises(AtlaWireError, match=message):
        convert_against(server)

    assert len(seen) == 1
    assert extra == []


def _echo_payloads() -> list[tuple[str, dict[str, object]]]:
    standard = base64.b64encode(TOKEN.encode()).decode("ascii")
    return [
        ("literal-value", {"value": TOKEN, "representation": "view"}),
        (
            "literal-unknown",
            {"value": "x", "representation": "view", "extra": TOKEN},
        ),
        ("literal-key", {"value": "x", "representation": "view", TOKEN: "key"}),
        (
            "base64-unknown",
            {"value": "x", "representation": "view", "extra": standard},
        ),
        (
            "percent-unknown",
            {
                "value": "x",
                "representation": "view",
                "extra": quote(TOKEN, safe=""),
            },
        ),
    ]


@pytest.mark.parametrize(
    "payload",
    [payload for _, payload in _echo_payloads()],
    ids=[label for label, _ in _echo_payloads()],
)
def test_loopback_a_token_echo_in_the_response_is_rejected(
    payload: dict[str, object],
) -> None:
    seen: list[Request] = []
    bodies: list[bytes] = []
    content_types: list[str | None] = []
    extra: list[str] = []
    handler = make_handler(
        seen,
        bodies,
        content_types,
        (200, _json(payload), {"Content-Type": "application/json"}),
        extra,
    )

    with serving(handler) as server, pytest.raises(AtlaWireError) as caught:
        convert_against(server)

    assert str(caught.value) == SECRET_MESSAGE
    assert TOKEN not in str(caught.value)
    assert len(seen) == 1
    assert extra == []


def test_loopback_untrusted_links_and_markup_are_returned_not_followed() -> None:
    honey_seen: list[Request] = []

    class Honeypot(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            honey_seen.append(request_record(self))
            send_bytes(self, 200, b"stolen")

        def do_POST(self) -> None:
            honey_seen.append(request_record(self))
            send_bytes(self, 200, b"stolen")

    seen: list[Request] = []
    bodies: list[bytes] = []
    content_types: list[str | None] = []
    extra: list[str] = []

    with serving(Honeypot) as honey:
        target = f"http://127.0.0.1:{honey.server_port}/next"
        payload: dict[str, object] = {
            "value": "<script>alert(1)</script>",
            "representation": "view",
            "_links": {"next": target, "download": "file:///etc/passwd"},
            "unknown": {"nested": [None, True, 2.5]},
        }
        handler = make_handler(
            seen,
            bodies,
            content_types,
            (200, _json(payload), {"Content-Type": "application/json"}),
            extra,
        )
        with serving(handler) as server:
            result = convert_against(server)

    assert result == payload
    assert honey_seen == []
    assert len(seen) == 1
    assert extra == []


@pytest.mark.parametrize(
    ("value", "representation", "to", "expand", "message"),
    [
        pytest.param(
            VALUE,
            "storage",
            "storage",
            None,
            "supported content body conversion",
            id="unsupported-pair",
        ),
        pytest.param(
            VALUE,
            "view",
            "storage",
            None,
            "supported content body conversion",
            id="view-source",
        ),
        pytest.param(
            VALUE,
            "Storage",
            "view",
            None,
            "supported content body conversion",
            id="case-sensitive-source",
        ),
        pytest.param(
            "\ud800",
            "storage",
            "view",
            None,
            "content body value",
            id="non-utf8-value",
        ),
        pytest.param(
            VALUE,
            "storage",
            "view",
            "\ud800",
            "expand",
            id="non-utf8-expand",
        ),
    ],
)
def test_loopback_invalid_input_makes_no_request(
    value: str,
    representation: str,
    to: str,
    expand: str | None,
    message: str,
) -> None:
    seen: list[Request] = []
    bodies: list[bytes] = []
    content_types: list[str | None] = []
    extra: list[str] = []
    handler = make_handler(seen, bodies, content_types, (200, b"{}", {}), extra)

    with serving(handler) as server, pytest.raises(AtlaWireError, match=message):
        convert_against(
            server,
            value=value,
            representation=representation,
            to=to,
            expand=expand,
        )

    assert seen == []
    assert bodies == []
    assert content_types == []
    assert extra == []


@pytest.mark.parametrize(
    ("value", "expand"),
    [
        pytest.param(TOKEN, None, id="value-literal"),
        pytest.param(VALUE, TOKEN, id="expand-literal"),
        pytest.param(VALUE, quote(TOKEN, safe=""), id="expand-percent"),
    ],
)
def test_loopback_a_request_echo_makes_no_request(
    value: str, expand: str | None
) -> None:
    seen: list[Request] = []
    bodies: list[bytes] = []
    content_types: list[str | None] = []
    extra: list[str] = []
    handler = make_handler(seen, bodies, content_types, (200, b"{}", {}), extra)

    with (
        serving(handler) as server,
        pytest.raises(AtlaWireError, match="request would include") as caught,
    ):
        convert_against(server, value=value, expand=expand)

    assert TOKEN not in str(caught.value)
    assert seen == []
    assert bodies == []
    assert content_types == []
    assert extra == []


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
def test_loopback_fixed_request_text_coinciding_with_the_token_is_sent(
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
    seen: list[Request] = []
    bodies: list[bytes] = []
    content_types: list[str | None] = []
    extra: list[str] = []
    if token in {"value", "representation"}:
        response: Response = (
            401,
            _json({"message": sentinel}),
            {"Content-Type": "application/json"},
        )
    else:
        payload: dict[str, object] = {
            "value": "x",
            # ``view`` is the token under test here, so return another
            # documented representation that does not contain it.
            "representation": "storage" if token == "view" else "view",
        }
        response = (200, _json(payload), {"Content-Type": "application/json"})
    handler = make_handler(seen, bodies, content_types, response, extra)

    with serving(handler) as server:
        if token in {"value", "representation"}:
            with pytest.raises(AtlaWireError) as caught:
                convert_against(
                    server,
                    representation=representation,
                    to=to,
                    expand=expand,
                    token=token,
                )
            assert str(caught.value) == "HTTP 401: authentication rejected."
            assert str(caught.value) != REQUEST_SECRET_MESSAGE
            assert sentinel not in str(caught.value)
            assert token not in str(caught.value)
        else:
            assert (
                convert_against(
                    server,
                    representation=representation,
                    to=to,
                    expand=expand,
                    token=token,
                )
                == payload
            )

    assert seen == [
        (
            "POST",
            f"{CONTEXT}/rest/api/contentbody/convert/{to}",
            {"expand": [expand]} if expand is not None else {},
            f"Bearer {token}",
        )
    ]
    assert content_types == ["application/json"]
    assert json.loads(bodies[0]) == {"value": VALUE, "representation": representation}
    assert extra == []


def test_loopback_a_short_token_is_preserved_in_a_malformed_response_error() -> None:
    seen: list[Request] = []
    bodies: list[bytes] = []
    content_types: list[str | None] = []
    extra: list[str] = []
    short_token = "JSON"
    handler = make_handler(
        seen,
        bodies,
        content_types,
        (200, b"{", {"Content-Type": "application/json"}),
        extra,
    )

    with (
        serving(handler) as server,
        pytest.raises(AtlaWireError) as caught,
    ):
        convert_against(server, token=short_token)

    assert str(caught.value) == "Expected a valid JSON response."
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None
    assert len(seen) == 1
    assert extra == []


def test_loopback_unicode_escape_spelling_the_token_is_data() -> None:
    seen: list[Request] = []
    bodies: list[bytes] = []
    content_types: list[str | None] = []
    extra: list[str] = []
    value = chr(0x1234)
    token = "u1234"
    payload = {"value": "x", "representation": "view"}
    handler = make_handler(
        seen,
        bodies,
        content_types,
        (200, _json(payload), {"Content-Type": "application/json"}),
        extra,
    )

    with serving(handler) as server:
        result = convert_against(server, value=value, token=token)

    # The raw value and mapping contain only U+1234; the wire text may spell the
    # ASCII escape, but that serializer output is not credential-derived data.
    # A literal token in the caller text is still refused by the request-echo
    # tests above.
    assert result == payload
    assert seen == [
        (
            "POST",
            f"{CONTEXT}/rest/api/contentbody/convert/view",
            {},
            f"Bearer {token}",
        )
    ]
    assert content_types == ["application/json"]
    assert json.loads(bodies[0]) == {"value": value, "representation": "storage"}
    assert value.encode("utf-8") in bodies[0] or b"\\u1234" in bodies[0]
    assert extra == []


def test_loopback_a_nearby_unicode_value_not_spelling_the_token_succeeds() -> None:
    seen: list[Request] = []
    bodies: list[bytes] = []
    content_types: list[str | None] = []
    extra: list[str] = []
    value = chr(0x1235)
    payload = {"value": value, "representation": "view"}
    handler = make_handler(
        seen,
        bodies,
        content_types,
        (200, _json(payload), {"Content-Type": "application/json"}),
        extra,
    )

    with serving(handler) as server:
        result = convert_against(server, value=value, token="u1234")

    assert result == payload
    assert len(seen) == 1
    assert content_types == ["application/json"]
    assert json.loads(bodies[0]) == {"value": value, "representation": "storage"}
    assert extra == []
