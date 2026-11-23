"""Black-box contracts for the Confluence space reads and CQL space resolution.

Every case drives a public function against a loopback HTTP server bound to
``127.0.0.1:0``, asserts the exact wire request, and never mocks the transport.
The module also pins the live defect where ``/rest/api/search`` hides the space
key inside the nested ``content._expandable.space`` instead of the flat item.
"""

import json
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import NamedTuple
from urllib.parse import parse_qs, urlsplit

import pytest

from atlawire import confluence
from atlawire.http import AtlaWireError

TOKEN = "synthetic-token-confluence-spaces"
SECRET = "synthetic-private-error-body"
JSON = "application/json"
ARCH = "ARCH"
SEARCH_PATH = "/rest/api/search"
SPACE_PATH = "/rest/api/space/ARCH"


class Call(NamedTuple):
    method: str
    target: str
    accept: str | None
    authorization: str | None


@pytest.fixture
def server():
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def do_GET(self):
            self.server.calls.append(  # type: ignore[attr-defined]
                Call(
                    self.command,
                    self.path,
                    self.headers.get("Accept"),
                    self.headers.get("Authorization"),
                )
            )
            if not self.server.responses:  # type: ignore[attr-defined]
                self.server.unexpected.append(self.path)  # type: ignore[attr-defined]
                self.send_error(500)
                return
            responses = self.server.responses  # type: ignore[attr-defined]
            status, body, content_type = responses.pop(0)
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    httpd.calls = []  # type: ignore[attr-defined]
    httpd.responses = []  # type: ignore[attr-defined]
    httpd.unexpected = []  # type: ignore[attr-defined]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd, f"http://127.0.0.1:{httpd.server_port}"
    finally:
        httpd.shutdown()
        thread.join(timeout=5)
        httpd.server_close()


def load(httpd, status, payload, content_type=JSON):
    body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    httpd.responses.append((status, body, content_type))


def assert_calls(httpd, expected):
    actual = [
        (call.method, urlsplit(call.target).path, parse_qs(urlsplit(call.target).query))
        for call in httpd.calls
    ]
    normalized = [
        (method, path, {key: value for key, value in sorted(query.items())})
        for method, path, query in actual
    ]
    wanted = [
        (method, path, {key: value for key, value in sorted(query.items())})
        for method, path, query in expected
    ]
    assert normalized == wanted
    assert httpd.unexpected == []
    assert all(call.accept == JSON for call in httpd.calls)
    assert all(call.authorization == "Bearer " + TOKEN for call in httpd.calls)


def assert_sanitized(caught, status):
    assert caught.value.category == "http"
    assert caught.value.http_status == status
    diagnostic = "".join(traceback.format_exception(caught.value))
    assert SECRET not in diagnostic
    assert TOKEN not in diagnostic


def wrapped_page(results, start=0, total=None):
    """A search page as the live server wraps every row in a content envelope."""
    return {
        "results": [
            {
                "content": content,
                "title": content["title"],
                "url": content.get("_links", {}).get("webui"),
                "excerpt": "ignored",
            }
            for content in results
        ],
        "start": start,
        "limit": len(results),
        "size": len(results),
        "totalSize": len(results) if total is None else total,
    }


def flat_page(results, start=0, total=None):
    """A search page in the flat shape older responses use."""
    return {
        "results": list(results),
        "start": start,
        "limit": len(results),
        "size": len(results),
        "totalSize": len(results) if total is None else total,
    }


# --- The confirmed space resolution defect in cql/find rows -------------------


def test_search_cql_reads_space_from_the_nested_content_expandable(server):
    httpd, url = server
    content = {
        "id": "7307751",
        "type": "page",
        "title": "Wrapped",
        "_expandable": {"space": f"/rest/api/space/{ARCH}"},
        "_links": {"webui": "/display/ARCH/Wrapped"},
    }
    load(httpd, 200, wrapped_page([content]))
    rows = confluence.search_cql(
        url,
        f'space = "{ARCH}" and type = page',
        token=TOKEN,
        limit=1,
        allow_http_loopback=True,
    )
    assert rows == [
        {
            "id": "7307751",
            "space": ARCH,
            "type": "page",
            "title": "Wrapped",
            "url": "/display/ARCH/Wrapped",
        }
    ]
    assert_calls(
        httpd,
        [
            (
                "GET",
                SEARCH_PATH,
                {
                    "cql": [f'space = "{ARCH}" and type = page'],
                    "start": ["0"],
                    "limit": ["1"],
                },
            )
        ],
    )


def test_search_cql_reads_space_from_the_flat_expandable(server):
    httpd, url = server
    item = {
        "id": "42",
        "type": "page",
        "title": "Flat",
        "url": "/display/ARCH/Flat",
        "_expandable": {"space": f"/rest/api/space/{ARCH}"},
    }
    load(httpd, 200, flat_page([item]))
    rows = confluence.search_cql(
        url, f'space = "{ARCH}"', token=TOKEN, limit=1, allow_http_loopback=True
    )
    assert rows == [
        {
            "id": "42",
            "space": ARCH,
            "type": "page",
            "title": "Flat",
            "url": "/display/ARCH/Flat",
        }
    ]
    assert_calls(
        httpd,
        [
            (
                "GET",
                SEARCH_PATH,
                {"cql": [f'space = "{ARCH}"'], "start": ["0"], "limit": ["1"]},
            )
        ],
    )


def test_search_cql_keeps_the_space_on_every_paginated_page(server):
    httpd, url = server
    first = {
        "id": "1",
        "type": "page",
        "title": "First",
        "_expandable": {"space": f"/rest/api/space/{ARCH}"},
        "_links": {"webui": "/display/ARCH/First"},
    }
    second = {
        "id": "2",
        "type": "page",
        "title": "Second",
        "_expandable": {"space": f"/rest/api/space/{ARCH}"},
        "_links": {"webui": "/display/ARCH/Second"},
    }
    first_page = wrapped_page([first], total=2)
    first_page["_links"] = {"next": "/rest/api/search?start=1&limit=1"}
    load(httpd, 200, first_page)
    load(httpd, 200, wrapped_page([second], start=1, total=2))
    rows = confluence.search_cql(
        url, "type = page", token=TOKEN, limit=2, allow_http_loopback=True
    )
    assert [row["space"] for row in rows] == [ARCH, ARCH]
    assert [row["id"] for row in rows] == ["1", "2"]
    assert_calls(
        httpd,
        [
            (
                "GET",
                SEARCH_PATH,
                {"cql": ["type = page"], "start": ["0"], "limit": ["2"]},
            ),
            (
                "GET",
                SEARCH_PATH,
                {"cql": ["type = page"], "start": ["1"], "limit": ["1"]},
            ),
        ],
    )


def test_search_cql_projects_exactly_the_five_content_fields(server):
    httpd, url = server
    content = {
        "id": "7",
        "type": "blogpost",
        "title": "Post",
        "space": {"key": "OTHER"},
        "version": {"number": 3},
        "unknown": [1, {"nested": True}],
        "_links": {"webui": "/display/OTHER/Post"},
    }
    load(httpd, 200, wrapped_page([content]))
    (row,) = confluence.search_cql(
        url, "type = blogpost", token=TOKEN, limit=1, allow_http_loopback=True
    )
    assert set(row) == {"id", "space", "type", "title", "url"}
    assert row == {
        "id": "7",
        "space": "OTHER",
        "type": "blogpost",
        "title": "Post",
        "url": "/display/OTHER/Post",
    }


def test_search_cql_http_error_never_leaks_the_response_body(server, capsys, caplog):
    httpd, url = server
    load(httpd, 404, {"message": SECRET, "token": TOKEN})
    with pytest.raises(AtlaWireError) as caught:
        confluence.search_cql(url, "type = page", token=TOKEN, allow_http_loopback=True)
    output = capsys.readouterr()
    diagnostic = str(caught.value) + "".join(traceback.format_exception(caught.value))
    diagnostic += output.out + output.err + caplog.text
    assert SECRET not in diagnostic
    assert TOKEN not in diagnostic
    assert_sanitized(caught, 404)
    assert len(httpd.calls) == 1


# --- get_space -----------------------------------------------------------------

SPACE = {
    "id": "58359809",
    "key": ARCH,
    "name": "ARCHIVE",
    "type": "global",
    "unknown": {"nested": [1]},
    "_links": {"base": "https://ignored", "webui": f"/display/{ARCH}"},
    "_expandable": {"status": ""},
}


def test_get_space_reads_the_exact_path_and_projects_five_fields(server):
    httpd, url = server
    load(httpd, 200, SPACE)
    space = confluence.get_space(url, ARCH, token=TOKEN, allow_http_loopback=True)
    assert space == {
        "key": ARCH,
        "name": "ARCHIVE",
        "type": "global",
        "status": None,
        "url": f"/display/{ARCH}",
    }
    assert set(space) == {"key", "name", "type", "status", "url"}
    assert_calls(httpd, [("GET", SPACE_PATH, {})])


def test_get_space_keeps_the_optional_status(server):
    httpd, url = server
    load(httpd, 200, {**SPACE, "status": "current"})
    space = confluence.get_space(url, ARCH, token=TOKEN, allow_http_loopback=True)
    assert space["status"] == "current"
    assert_calls(httpd, [("GET", SPACE_PATH, {})])


@pytest.mark.parametrize(
    "space_key", ["", "A/B", "..", "-ARCH", "ARCH X", "ARCH\n", True, None, 7]
)
def test_get_space_rejects_an_unsafe_space_key_before_any_request(server, space_key):
    httpd, url = server
    with pytest.raises(AtlaWireError):
        confluence.get_space(url, space_key, token=TOKEN, allow_http_loopback=True)
    assert httpd.calls == []
    assert httpd.unexpected == []


def test_get_space_rejects_a_response_for_another_space(server):
    httpd, url = server
    load(httpd, 200, {**SPACE, "key": "OTHER"})
    with pytest.raises(AtlaWireError, match="space metadata"):
        confluence.get_space(url, ARCH, token=TOKEN, allow_http_loopback=True)
    assert len(httpd.calls) == 1


@pytest.mark.parametrize(
    "payload",
    [
        {**SPACE, "name": 7},
        {**SPACE, "_links": []},
        {**SPACE, "key": None},
        {**SPACE, "type": "global\ud800"},
    ],
)
def test_get_space_rejects_invalid_metadata(server, payload):
    httpd, url = server
    load(httpd, 200, payload)
    with pytest.raises(AtlaWireError):
        confluence.get_space(url, ARCH, token=TOKEN, allow_http_loopback=True)
    assert len(httpd.calls) == 1


def test_get_space_http_error_never_leaks_the_response_body(server, capsys, caplog):
    httpd, url = server
    load(httpd, 404, {"message": SECRET, "token": TOKEN})
    with pytest.raises(AtlaWireError) as caught:
        confluence.get_space(url, ARCH, token=TOKEN, allow_http_loopback=True)
    output = capsys.readouterr()
    diagnostic = str(caught.value) + "".join(traceback.format_exception(caught.value))
    diagnostic += output.out + output.err + caplog.text
    assert SECRET not in diagnostic
    assert TOKEN not in diagnostic
    assert_sanitized(caught, 404)
    assert len(httpd.calls) == 1


# --- list_space_content ----------------------------------------------------------

SPACE_CONTENT_PATH = SPACE_PATH + "/content"
TYPE_PATH = SPACE_CONTENT_PATH + "/page"


def content_row(content_id, title, content_type="page", version=None):
    row = {
        "id": content_id,
        "type": content_type,
        "title": title,
        "status": "current",
        "_links": {"webui": f"/pages/viewpage.action?pageId={content_id}"},
        "_expandable": {"space": f"/rest/api/space/{ARCH}"},
        "unknown": [1],
    }
    if version is not None:
        row["version"] = {"number": version}
    return row


def content_bucket(rows, start=0, next_start=None):
    bucket = {
        "results": list(rows),
        "start": start,
        "limit": len(rows),
        "size": len(rows),
        "_links": {},
    }
    if next_start is not None:
        bucket["_links"]["next"] = f"{TYPE_PATH}?start={next_start}&limit=1"
    return bucket


def typed_content_page(rows, start=0, next_start=None):
    page = content_bucket(rows, start=start, next_start=next_start)
    return page


def summary(row):
    return {
        "id": row["id"],
        "title": row["title"],
        "type": row["type"],
        "version": row.get("version", {}).get("number"),
        "url": row["_links"]["webui"],
    }


def test_list_space_content_without_type_reads_the_map_path(server):
    httpd, url = server
    first = content_row("1", "First", version=3)
    second = content_row("2", "Second", version=1)
    post = content_row("3", "Post", content_type="blogpost", version=2)
    load(
        httpd,
        200,
        {
            "page": content_bucket([first, second]),
            "blogpost": content_bucket([post]),
            "_links": {"base": "https://ignored/rest/api"},
        },
    )
    result = confluence.list_space_content(
        url, ARCH, token=TOKEN, limit=10, allow_http_loopback=True
    )
    assert result == {
        "rows": [summary(first), summary(second), summary(post)],
        "truncated": False,
    }
    assert set(result) == {"rows", "truncated"}
    assert_calls(
        httpd,
        [
            (
                "GET",
                SPACE_CONTENT_PATH,
                {"expand": ["version"], "start": ["0"], "limit": ["10"]},
            )
        ],
    )


def test_list_space_content_with_type_reads_only_the_typed_path(server):
    httpd, url = server
    row = content_row("9", "Only", version=4)
    load(httpd, 200, typed_content_page([row]))
    result = confluence.list_space_content(
        url, ARCH, token=TOKEN, type="page", limit=1, allow_http_loopback=True
    )
    assert result == {"rows": [summary(row)], "truncated": False}
    assert_calls(
        httpd,
        [("GET", TYPE_PATH, {"expand": ["version"], "start": ["0"], "limit": ["1"]})],
    )


def test_list_space_content_paginates_the_typed_endpoint(server):
    httpd, url = server
    first = content_row("1", "First", version=1)
    second = content_row("2", "Second", version=2)
    third = content_row("3", "Third", version=3)
    load(httpd, 200, typed_content_page([first, second], next_start=2))
    load(httpd, 200, typed_content_page([third], start=2))
    result = confluence.list_space_content(
        url, ARCH, token=TOKEN, type="page", limit=3, allow_http_loopback=True
    )
    assert result == {
        "rows": [summary(first), summary(second), summary(third)],
        "truncated": False,
    }
    assert_calls(
        httpd,
        [
            ("GET", TYPE_PATH, {"expand": ["version"], "start": ["0"], "limit": ["3"]}),
            ("GET", TYPE_PATH, {"expand": ["version"], "start": ["2"], "limit": ["1"]}),
        ],
    )


def test_list_space_content_reports_truncation_on_the_typed_endpoint(server):
    httpd, url = server
    first = content_row("1", "First", version=1)
    second = content_row("2", "Second", version=2)
    load(httpd, 200, typed_content_page([first, second], next_start=2))
    result = confluence.list_space_content(
        url, ARCH, token=TOKEN, type="page", limit=2, allow_http_loopback=True
    )
    assert result == {"rows": [summary(first), summary(second)], "truncated": True}
    assert_calls(
        httpd,
        [("GET", TYPE_PATH, {"expand": ["version"], "start": ["0"], "limit": ["2"]})],
    )


def test_list_space_content_reports_truncation_from_an_unread_bucket(server):
    httpd, url = server
    first = content_row("1", "First", version=1)
    second = content_row("2", "Second", version=2)
    post = content_row("3", "Post", content_type="blogpost", version=2)
    load(
        httpd,
        200,
        {"page": content_bucket([first, second]), "blogpost": content_bucket([post])},
    )
    result = confluence.list_space_content(
        url, ARCH, token=TOKEN, limit=2, allow_http_loopback=True
    )
    assert result == {"rows": [summary(first), summary(second)], "truncated": True}
    assert_calls(
        httpd,
        [
            (
                "GET",
                SPACE_CONTENT_PATH,
                {"expand": ["version"], "start": ["0"], "limit": ["2"]},
            )
        ],
    )


def test_list_space_content_continues_a_bucket_when_the_budget_is_not_filled(server):
    httpd, url = server
    first = content_row("1", "First", version=1)
    second = content_row("2", "Second", version=2)
    third = content_row("3", "Third", version=3)
    load(
        httpd,
        200,
        {
            "page": content_bucket([first], next_start=1),
            "blogpost": content_bucket([]),
        },
    )
    load(httpd, 200, typed_content_page([second, third], start=1))
    result = confluence.list_space_content(
        url, ARCH, token=TOKEN, limit=3, allow_http_loopback=True
    )
    assert result == {
        "rows": [summary(first), summary(second), summary(third)],
        "truncated": False,
    }
    assert_calls(
        httpd,
        [
            (
                "GET",
                SPACE_CONTENT_PATH,
                {"expand": ["version"], "start": ["0"], "limit": ["3"]},
            ),
            ("GET", TYPE_PATH, {"expand": ["version"], "start": ["1"], "limit": ["2"]}),
        ],
    )


def test_list_space_content_reports_truncation_after_a_continuation(server):
    httpd, url = server
    first = content_row("1", "First", version=1)
    second = content_row("2", "Second", version=2)
    load(
        httpd,
        200,
        {
            "page": content_bucket([first], next_start=1),
            "blogpost": content_bucket([]),
        },
    )
    load(httpd, 200, typed_content_page([second], start=1, next_start=2))
    result = confluence.list_space_content(
        url, ARCH, token=TOKEN, limit=2, allow_http_loopback=True
    )
    assert result == {"rows": [summary(first), summary(second)], "truncated": True}
    assert_calls(
        httpd,
        [
            (
                "GET",
                SPACE_CONTENT_PATH,
                {"expand": ["version"], "start": ["0"], "limit": ["2"]},
            ),
            ("GET", TYPE_PATH, {"expand": ["version"], "start": ["1"], "limit": ["1"]}),
        ],
    )


def test_list_space_content_projects_only_the_five_content_fields(server):
    httpd, url = server
    bare = {"id": "5", "type": "page", "title": "Bare", "unknown": [1]}
    load(httpd, 200, {"page": content_bucket([bare]), "blogpost": content_bucket([])})
    result = confluence.list_space_content(
        url, ARCH, token=TOKEN, limit=2, allow_http_loopback=True
    )
    assert result["rows"] == [
        {"id": "5", "title": "Bare", "type": "page", "version": None, "url": None}
    ]
    assert set(result["rows"][0]) == {"id", "title", "type", "version", "url"}
    assert result["truncated"] is False


def test_list_space_content_zero_limit_returns_an_empty_listing_without_a_request(
    server,
):
    httpd, url = server
    result = confluence.list_space_content(
        url, ARCH, token=TOKEN, limit=0, allow_http_loopback=True
    )
    assert result == {"rows": [], "truncated": False}
    assert httpd.calls == []
    assert httpd.unexpected == []


@pytest.mark.parametrize(
    "space_key,content_type,limit",
    [
        ("A/B", None, 10),
        ("", None, 10),
        (ARCH, "page/../x", 10),
        (ARCH, "", 10),
        (ARCH, True, 10),
        (ARCH, None, -1),
        (ARCH, None, 1001),
        (ARCH, None, True),
        (ARCH, None, 1.5),
        (ARCH, "..", 10),
        (ARCH, "...", 10),
        ("A/B", None, 0),
    ],
)
def test_list_space_content_rejects_invalid_arguments_before_any_request(
    server, space_key, content_type, limit
):
    httpd, url = server
    with pytest.raises(AtlaWireError):
        confluence.list_space_content(
            url,
            space_key,
            token=TOKEN,
            type=content_type,
            limit=limit,
            allow_http_loopback=True,
        )
    assert httpd.calls == []
    assert httpd.unexpected == []


@pytest.mark.parametrize(
    "payload",
    [
        {"page": []},
        {"page": {"results": "bad", "start": 0, "size": 0, "_links": {}}},
        {"page": {"results": [], "start": 0, "size": 2, "_links": {}}},
        {"page": content_bucket([{**content_row("5", "X"), "id": True}])},
        {
            "page": content_bucket(
                [{**content_row("5", "X"), "version": {"number": -1}}]
            )
        },
        {
            "page": content_bucket([content_row("5", "X")]),
            "weird type": content_bucket([]),
        },
    ],
)
def test_list_space_content_rejects_invalid_metadata(server, payload):
    httpd, url = server
    load(httpd, 200, payload)
    with pytest.raises(AtlaWireError):
        confluence.list_space_content(
            url, ARCH, token=TOKEN, limit=5, allow_http_loopback=True
        )
    assert len(httpd.calls) == 1


def test_list_space_content_http_error_never_leaks_the_response_body(
    server, capsys, caplog
):
    httpd, url = server
    load(httpd, 404, {"message": SECRET, "token": TOKEN})
    with pytest.raises(AtlaWireError) as caught:
        confluence.list_space_content(url, ARCH, token=TOKEN, allow_http_loopback=True)
    output = capsys.readouterr()
    diagnostic = str(caught.value) + "".join(traceback.format_exception(caught.value))
    diagnostic += output.out + output.err + caplog.text
    assert SECRET not in diagnostic
    assert TOKEN not in diagnostic
    assert_sanitized(caught, 404)
    assert len(httpd.calls) == 1


def test_list_space_content_reports_truncation_from_total_size(server):
    httpd, url = server
    row = content_row("1", "First", version=1)
    load(
        httpd,
        200,
        {
            "results": [row],
            "start": 0,
            "size": 1,
            "totalSize": 5,
            "_links": {},
        },
    )
    result = confluence.list_space_content(
        url, ARCH, token=TOKEN, type="page", limit=5, allow_http_loopback=True
    )
    assert result == {"rows": [summary(row)], "truncated": True}
    assert_calls(
        httpd,
        [("GET", TYPE_PATH, {"expand": ["version"], "start": ["0"], "limit": ["5"]})],
    )


def test_list_space_content_reports_truncation_from_a_bucket_total_size(server):
    httpd, url = server
    row = content_row("1", "First", version=1)
    bucket = content_bucket([row])
    bucket["totalSize"] = 4
    load(httpd, 200, {"page": bucket, "blogpost": content_bucket([])})
    result = confluence.list_space_content(
        url, ARCH, token=TOKEN, limit=1, allow_http_loopback=True
    )
    assert result == {"rows": [summary(row)], "truncated": True}
    assert_calls(
        httpd,
        [
            (
                "GET",
                SPACE_CONTENT_PATH,
                {"expand": ["version"], "start": ["0"], "limit": ["1"]},
            )
        ],
    )


def test_list_space_content_rejects_an_empty_typed_page_before_all_matches(server):
    httpd, url = server
    load(
        httpd,
        200,
        {"results": [], "start": 0, "size": 0, "totalSize": 3, "_links": {}},
    )
    with pytest.raises(AtlaWireError, match="empty page"):
        confluence.list_space_content(
            url, ARCH, token=TOKEN, type="page", limit=3, allow_http_loopback=True
        )
    assert len(httpd.calls) == 1


def test_list_space_content_rejects_an_empty_continuation_before_all_matches(server):
    httpd, url = server
    row = content_row("1", "First", version=1)
    load(
        httpd,
        200,
        {
            "page": content_bucket([row], next_start=1),
            "blogpost": content_bucket([]),
        },
    )
    load(
        httpd,
        200,
        {"results": [], "start": 1, "size": 0, "totalSize": 2, "_links": {}},
    )
    with pytest.raises(AtlaWireError, match="empty page"):
        confluence.list_space_content(
            url, ARCH, token=TOKEN, limit=2, allow_http_loopback=True
        )
    assert len(httpd.calls) == 2
