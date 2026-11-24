import json
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest

from atlawire import confluence
from atlawire.http import AtlaWireError

TOKEN = "synthetic-token-batch"
SENTINEL = "synthetic-body-batch"
PAGE = {
    "id": "123",
    "type": "page",
    "title": "Test",
    "body": {"storage": {"value": "text"}},
    "version": {"number": 7},
    "extra": {"nested": [1]},
}


@pytest.fixture
def server():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.server.calls.append(
                (self.command, self.path, self.headers.get("Authorization"))
            )
            self.send_response(self.server.status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(self.server.payload).encode())

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    httpd.calls = []
    httpd.status = 200
    httpd.payload = {}
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd, f"http://127.0.0.1:{httpd.server_port}"
    finally:
        httpd.shutdown()
        thread.join(timeout=5)
        httpd.server_close()


# Each case supplies a complete single page, including more data than projections retain.
CASES = [
    (
        "get_page_history",
        "get_content_history",
        ("123",),
        {},
        ("123",),
        {},
        "/rest/api/content/123/history",
        {},
        {"createdDate": "today", "extra": {"nested": [1]}},
        {"createdDate": "today", "extra": {"nested": [1]}},
    ),
    (
        "get_page_version",
        "get_page_by_id",
        ("123", 7),
        {},
        ("123",),
        {"status": "historical", "version": 7, "expand": "body.storage,version"},
        "/rest/api/content/123",
        {
            "status": ["historical"],
            "version": ["7"],
            "expand": ["body.storage,version"],
        },
        PAGE,
        PAGE,
    ),
    (
        "get_page_attachments",
        "get_attachments",
        ("123",),
        {"start": 2, "limit": 3},
        ("123",),
        {"params": {"start": 2, "limit": 3}},
        "/rest/api/content/123/child/attachment",
        {"start": ["2"], "limit": ["3"]},
        {"results": [{"id": "a"}], "unknown": [1]},
        {"results": [{"id": "a"}], "unknown": [1]},
    ),
    (
        "get_page_comments",
        "get_comments",
        ("123",),
        {"start": 2, "limit": 3, "include_replies": True},
        ("123",),
        {"params": {"start": 2, "limit": 3, "expand": "body.storage", "depth": "all"}},
        "/rest/api/content/123/child/comment",
        {"start": ["2"], "limit": ["3"], "expand": ["body.storage"], "depth": ["all"]},
        {"results": [{"id": "c"}], "unknown": [1]},
        {"results": [{"id": "c"}], "unknown": [1]},
    ),
    (
        "get_page_labels",
        "get_page_labels",
        ("123",),
        {"start": 2, "limit": 3},
        ("123",),
        {"start": 2, "limit": 3},
        "/rest/api/content/123/label",
        {"start": ["2"], "limit": ["3"]},
        {"results": [{"name": "x"}], "unknown": [1]},
        {"results": [{"name": "x"}], "unknown": [1]},
    ),
    (
        "search_cql",
        "cql",
        ("type=page",),
        {"limit": 1},
        ("type=page",),
        {"start": 0, "limit": 1},
        "/rest/api/search",
        {"cql": ["type=page"], "start": ["0"], "limit": ["1"]},
        {
            "results": [
                {
                    "content": {
                        "id": "1",
                        "title": "T",
                        "type": "page",
                        "space": {"key": "S"},
                    },
                    "url": "/x",
                    "ignored": 1,
                }
            ]
        },
        [{"id": "1", "title": "T", "type": "page", "space": "S", "url": "/x"}],
    ),
    (
        "list_spaces",
        "get_spaces",
        (),
        {"limit": 1},
        (),
        {"params": {"start": 0, "limit": 1}},
        "/rest/api/space",
        {"start": ["0"], "limit": ["1"]},
        {"results": [{"key": "S", "name": "Space", "type": "global", "ignored": 1}]},
        [{"key": "S", "name": "Space", "type": "global"}],
    ),
    (
        "list_children",
        "get_page_child_by_type",
        ("123",),
        {"limit": 1},
        ("123",),
        {"type": "page", "start": 0, "limit": 1, "expand": "version"},
        "/rest/api/content/123/child/page",
        {"start": ["0"], "limit": ["1"], "expand": ["version"]},
        {
            "results": [
                {"id": "9", "title": "Child", "version": {"number": 4}, "ignored": 1}
            ]
        },
        [{"id": "9", "title": "Child", "version": 4}],
    ),
]


@pytest.mark.parametrize(
    "function,method,args,kwargs,sdk_args,sdk_kwargs,path,query,payload,expected",
    CASES,
    ids=[c[0] for c in CASES],
)
def test_wire_and_response(
    server,
    function,
    method,
    args,
    kwargs,
    sdk_args,
    sdk_kwargs,
    path,
    query,
    payload,
    expected,
):
    httpd, url = server
    httpd.payload = payload
    result = getattr(confluence, function)(
        url, *args, token=TOKEN, allow_http_loopback=True, **kwargs
    )
    assert result == expected
    assert len(httpd.calls) == 1
    verb, target, authorization = httpd.calls[0]
    assert authorization == "Bearer " + TOKEN
    parsed = urlsplit(target)
    assert (verb, parsed.path, parse_qs(parsed.query)) == ("GET", path, query)


@pytest.mark.parametrize(
    "function,method,args,kwargs,sdk_args,sdk_kwargs,path,query,payload,expected",
    CASES,
    ids=[c[0] for c in CASES],
)
@pytest.mark.parametrize("status", [400, 401, 403, 404, 429])
def test_http_errors_are_typed_and_sanitized(
    server,
    capsys,
    caplog,
    status,
    function,
    method,
    args,
    kwargs,
    sdk_args,
    sdk_kwargs,
    path,
    query,
    payload,
    expected,
):
    httpd, url = server
    httpd.status = status
    httpd.payload = {"message": SENTINEL}
    with pytest.raises(AtlaWireError) as caught:
        getattr(confluence, function)(
            url, *args, token=TOKEN, allow_http_loopback=True, **kwargs
        )
    output = capsys.readouterr()
    diagnostic = (
        str(caught.value)
        + "".join(traceback.format_exception(caught.value))
        + output.out
        + output.err
        + caplog.text
    )
    assert SENTINEL not in diagnostic
    assert TOKEN not in diagnostic
    assert len(httpd.calls) == 1
    assert httpd.calls[0][2] == "Bearer " + TOKEN
    assert caught.value.category == "http"
    assert caught.value.http_status == status


@pytest.mark.parametrize(
    "function,method,args,kwargs,sdk_args,sdk_kwargs,path,query,payload,expected",
    [c for c in CASES if c[0] not in {"search_cql", "list_spaces"}],
    ids=lambda x: x if isinstance(x, str) else None,
)
def test_invalid_page_id_is_rejected_before_request(
    server,
    function,
    method,
    args,
    kwargs,
    sdk_args,
    sdk_kwargs,
    path,
    query,
    payload,
    expected,
):
    httpd, url = server
    with pytest.raises(AtlaWireError):
        getattr(confluence, function)(
            url, "0", *args[1:], token=TOKEN, allow_http_loopback=True, **kwargs
        )
    assert httpd.calls == []


def test_comments_can_omit_reply_depth(server):
    httpd, url = server
    httpd.payload = {"results": []}
    assert confluence.get_page_comments(
        url, 123, token=TOKEN, allow_http_loopback=True, include_replies=False
    ) == {"results": []}
    assert len(httpd.calls) == 1
    assert parse_qs(urlsplit(httpd.calls[0][1]).query) == {
        "start": ["0"],
        "limit": ["25"],
        "expand": ["body.storage"],
    }


def test_history_rejects_non_object(server):
    httpd, url = server
    httpd.payload = ["invalid"]
    with pytest.raises(AtlaWireError) as caught:
        confluence.get_page_history(url, 123, token=TOKEN, allow_http_loopback=True)
    assert caught.value.category == "upstream"
    assert len(httpd.calls) == 1


def test_version_rejects_mismatched_number(server):
    httpd, url = server
    httpd.payload = PAGE
    with pytest.raises(AtlaWireError):
        confluence.get_page_version(url, 123, 8, token=TOKEN, allow_http_loopback=True)
    assert len(httpd.calls) == 1


@pytest.mark.parametrize(
    "function,args,kwargs,payload",
    [
        ("get_page_attachments", (123,), {}, [1]),
        ("get_page_comments", (123,), {}, [1]),
        ("get_page_labels", (123,), {}, [1]),
        ("search_cql", ("type=page",), {"limit": 1}, {"results": "bad"}),
        ("list_spaces", (), {"limit": 1}, {"results": "bad"}),
        ("list_children", (123,), {"limit": 1}, {"results": [42]}),
    ],
)
def test_malformed_response_is_rejected(server, function, args, kwargs, payload):
    httpd, url = server
    httpd.payload = payload
    with pytest.raises(AtlaWireError):
        getattr(confluence, function)(
            url, *args, token=TOKEN, allow_http_loopback=True, **kwargs
        )
    assert len(httpd.calls) == 1


@pytest.mark.parametrize(
    "function,args",
    [("search_cql", ("type=page",)), ("list_spaces", ()), ("list_children", (123,))],
)
def test_zero_limit_does_not_make_request(server, function, args):
    httpd, url = server
    assert (
        getattr(confluence, function)(
            url, *args, token=TOKEN, limit=0, allow_http_loopback=True
        )
        == []
    )
    assert httpd.calls == []
