"""Black-box contracts for the bounded Confluence readers' truncation signal.

The live server caps one page by ``limit`` and marks the remainder only through
``totalSize`` (when it sends one) or a ``_links.next`` continuation. These
loopback tests prove that ``list_children_with_metadata``,
``get_page_comments_with_metadata`` and ``get_page_attachments_with_metadata``
surface that signal in the first response, never invent ``total``, and treat an
empty page as complete.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest

from atlawire import confluence
from atlawire.http import AtlaWireError

TOKEN = "synthetic-token-truncation"
PAGE_ID = 123
_MISSING = object()

CHILD_PATH = f"/rest/api/content/{PAGE_ID}/child/page"
COMMENT_PATH = f"/rest/api/content/{PAGE_ID}/child/comment"
ATTACHMENT_PATH = f"/rest/api/content/{PAGE_ID}/child/attachment"


def _child(number):
    return {
        "id": str(number),
        "title": f"Child {number}",
        "version": {"number": number},
    }


def _child_row(number):
    return {"id": str(number), "title": f"Child {number}", "version": number}


def _content(kind, number):
    return {"id": f"{kind}-{number}", "title": f"{kind} {number}"}


FAMILIES = {
    "children": {
        "function": "list_children_with_metadata",
        "path": CHILD_PATH,
        "make_row": _child,
        "project": lambda row: {
            "id": row["id"],
            "title": row["title"],
            "version": row["version"]["number"],
        },
        "exposes_next": False,
    },
    "comments": {
        "function": "get_page_comments_with_metadata",
        "path": COMMENT_PATH,
        "make_row": lambda number: _content("comment", number),
        "project": lambda row: row,
        "exposes_next": True,
    },
    "attachments": {
        "function": "get_page_attachments_with_metadata",
        "path": ATTACHMENT_PATH,
        "make_row": lambda number: _content("attachment", number),
        "project": lambda row: row,
        "exposes_next": True,
    },
}


@pytest.fixture
def server():
    """Loopback server that answers with queued payloads and records every GET."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlsplit(self.path)
            self.server.calls.append(
                (
                    self.command,
                    parsed.path,
                    parse_qs(parsed.query),
                    self.headers.get("Authorization"),
                )
            )
            if self.server.payloads:
                status, payload = 200, self.server.payloads.pop(0)
            else:
                # An unexpected extra request must fail loudly, never reuse data.
                status, payload = 500, {"message": "no queued payload"}
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(payload).encode())

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    httpd.calls = []
    httpd.payloads = []
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd, f"http://127.0.0.1:{httpd.server_port}"
    finally:
        httpd.shutdown()
        thread.join(timeout=5)
        httpd.server_close()


def _payload(rows, *, start=0, total=_MISSING, next_start=None):
    document = {"results": rows, "start": start, "size": len(rows), "_links": {}}
    if total is not _MISSING:
        document["totalSize"] = total
    if next_start is not None:
        document["_links"]["next"] = f"?start={next_start}&limit=1"
    return document


def _call(url, family, **kwargs):
    spec = FAMILIES[family]
    return getattr(confluence, spec["function"])(
        url, PAGE_ID, token=TOKEN, allow_http_loopback=True, **kwargs
    )


def _assert_keys(result, family):
    expected = {"rows", "truncated", "total"}
    if FAMILIES[family]["exposes_next"]:
        expected.add("next")
    assert set(result) == expected


@pytest.mark.parametrize("family", FAMILIES, ids=FAMILIES)
def test_more_rows_than_limit_reports_truncation(server, family):
    httpd, url = server
    spec = FAMILIES[family]
    row = spec["make_row"](1)
    # Children keep a plain pager, so totalSize alone must mark truncation; the
    # raw content readers also expose the server's continuation link.
    if family == "children":
        httpd.payloads = [_payload([row], total=3)]
    else:
        httpd.payloads = [_payload([row], total=3, next_start=1)]
    result = _call(url, family, limit=1)
    _assert_keys(result, family)
    assert result["rows"] == [spec["project"](row)]
    assert result["truncated"] is True
    assert result["total"] == 3
    if spec["exposes_next"]:
        assert result["next"] == "?start=1&limit=1"
    assert len(httpd.calls) == 1


@pytest.mark.parametrize("family", FAMILIES, ids=FAMILIES)
def test_exact_limit_is_not_truncated(server, family):
    httpd, url = server
    spec = FAMILIES[family]
    rows = [spec["make_row"](number) for number in (1, 2, 3)]
    httpd.payloads = [_payload(rows, total=3)]
    result = _call(url, family, limit=3)
    _assert_keys(result, family)
    assert result["rows"] == [spec["project"](row) for row in rows]
    assert result["truncated"] is False
    assert result["total"] == 3
    if spec["exposes_next"]:
        assert result["next"] is None
    assert len(httpd.calls) == 1


@pytest.mark.parametrize("family", FAMILIES, ids=FAMILIES)
def test_missing_total_size_is_not_invented(server, family):
    httpd, url = server
    spec = FAMILIES[family]
    row = spec["make_row"](1)
    httpd.payloads = [_payload([row], next_start=1)]
    result = _call(url, family, limit=1)
    _assert_keys(result, family)
    assert result["rows"] == [spec["project"](row)]
    assert result["truncated"] is True
    assert result["total"] is None
    if spec["exposes_next"]:
        assert result["next"] == "?start=1&limit=1"
    assert len(httpd.calls) == 1


@pytest.mark.parametrize("family", FAMILIES, ids=FAMILIES)
def test_empty_page_is_not_truncated(server, family):
    httpd, url = server
    httpd.payloads = [_payload([])]
    result = _call(url, family, limit=5)
    _assert_keys(result, family)
    assert result["rows"] == []
    assert result["truncated"] is False
    assert result["total"] is None
    if FAMILIES[family]["exposes_next"]:
        assert result["next"] is None
    assert len(httpd.calls) == 1


@pytest.mark.parametrize("family", ("comments", "attachments"))
def test_total_size_without_next_marks_truncation(server, family):
    httpd, url = server
    row = FAMILIES[family]["make_row"](1)
    httpd.payloads = [_payload([row], total=4)]
    result = _call(url, family, limit=1)
    assert result["truncated"] is True
    assert result["total"] == 4
    assert result["next"] is None


@pytest.mark.parametrize("family", ("comments", "attachments"))
def test_total_is_compared_with_the_start_offset(server, family):
    httpd, url = server
    row = FAMILIES[family]["make_row"](3)
    # start=2 + one row reaches totalSize=3, so the page is complete even though
    # its size is smaller than totalSize.
    httpd.payloads = [_payload([row], start=2, total=3)]
    result = _call(url, family, start=2, limit=1)
    assert result["truncated"] is False
    assert result["total"] == 3
    assert result["rows"] == [FAMILIES[family]["project"](row)]


def test_children_total_size_overrides_a_trailing_next_link(server):
    httpd, url = server
    rows = [_child(1), _child(2)]
    # A leftover continuation at the exact limit must not claim more rows than
    # totalSize reports.
    httpd.payloads = [_payload(rows, total=2, next_start=2)]
    result = confluence.list_children_with_metadata(
        url, PAGE_ID, token=TOKEN, limit=2, allow_http_loopback=True
    )
    assert result["rows"] == [_child_row(1), _child_row(2)]
    assert result["truncated"] is False
    assert result["total"] == 2


@pytest.mark.parametrize(
    ("family", "expected_query"),
    [
        ("children", {"expand": ["version"], "start": ["0"], "limit": ["1"]}),
        (
            "comments",
            {
                "depth": ["all"],
                "expand": ["body.storage"],
                "start": ["0"],
                "limit": ["1"],
            },
        ),
        ("attachments", {"start": ["0"], "limit": ["1"]}),
    ],
)
def test_wire_request_uses_the_legacy_endpoint(server, family, expected_query):
    httpd, url = server
    row = FAMILIES[family]["make_row"](1)
    httpd.payloads = [_payload([row])]
    result = _call(url, family, limit=1)
    assert result["truncated"] is False
    verb, path, query, authorization = httpd.calls[0]
    assert (verb, path) == ("GET", FAMILIES[family]["path"])
    assert query == expected_query
    assert authorization == "Bearer " + TOKEN


def test_comments_without_replies_omit_the_depth_parameter(server):
    httpd, url = server
    httpd.payloads = [_payload([_content("comment", 1)])]
    result = confluence.get_page_comments_with_metadata(
        url,
        PAGE_ID,
        token=TOKEN,
        limit=1,
        include_replies=False,
        allow_http_loopback=True,
    )
    assert result["truncated"] is False
    assert httpd.calls[0][2] == {
        "expand": ["body.storage"],
        "start": ["0"],
        "limit": ["1"],
    }


@pytest.mark.parametrize("family", FAMILIES, ids=FAMILIES)
def test_malformed_results_are_rejected(server, family):
    httpd, url = server
    httpd.payloads = [{"results": "not-a-list"}]
    with pytest.raises(AtlaWireError):
        _call(url, family, limit=1)
    assert len(httpd.calls) == 1
