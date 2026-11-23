"""Contracts for limiting a Jira issue comment read at the server boundary."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest

from atlawire import jira
from atlawire.http import AtlaWireError

TOKEN = "synthetic-only-token"
COMMENTS_PATH = "/rest/api/2/issue/DEMO-42/comment"


def _comment(number: int) -> dict[str, object]:
    return {"id": str(number), "body": f"comment {number}"}


def _page(
    start: int, max_results: int, total: int, numbers: list[int]
) -> dict[str, object]:
    return {
        "startAt": start,
        "maxResults": max_results,
        "total": total,
        "comments": [_comment(number) for number in numbers],
    }


@pytest.fixture
def server():
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self):
            self.server.calls.append(
                (self.command, self.path, self.headers.get("Authorization"))
            )
            body = json.dumps(self.server.responses.pop(0)).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def finish(self):
            try:
                super().finish()
            finally:
                self.server.closed.set()

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    httpd.calls = []
    httpd.responses = []
    httpd.closed = threading.Event()
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd, f"http://127.0.0.1:{httpd.server_port}"
    finally:
        httpd.shutdown()
        thread.join(timeout=5)
        httpd.server_close()
        assert not thread.is_alive()


def _queries(httpd) -> list[dict[str, list[str]]]:
    return [parse_qs(urlsplit(path).query) for _, path, _ in httpd.calls]


def _read(base, *, limit, httpd):
    return jira.list_issue_comments_with_metadata(
        base,
        "DEMO-42",
        token=TOKEN,
        limit=limit,
        allow_http_loopback=True,
    )


def test_limit_is_sent_as_the_page_max_results(server) -> None:
    """limit=2 asks the server for two comments and reports an incomplete thread."""
    httpd, base = server
    httpd.responses = [_page(0, 2, 5, [1, 2])]

    result = _read(base, limit=2, httpd=httpd)

    assert [row["id"] for row in result["rows"]] == ["1", "2"]
    assert result["truncated"] is True
    assert result["total"] == 5
    assert len(httpd.calls) == 1
    method, path, authorization = httpd.calls[0]
    assert (method, urlsplit(path).path) == ("GET", COMMENTS_PATH)
    assert authorization == "Bearer " + TOKEN
    assert _queries(httpd) == [{"startAt": ["0"], "maxResults": ["2"]}]
    assert httpd.closed.wait(2)


@pytest.mark.parametrize(
    ("total", "limit", "expected_ids", "expected_truncated"),
    [
        (5, 2, ["1", "2"], True),
        (2, 2, ["1", "2"], False),
        (3, 100, ["1", "2", "3"], False),
    ],
)
def test_truncated_matches_the_server_total(
    server, total, limit, expected_ids, expected_truncated
) -> None:
    """A cut thread is never reported as complete, and a full one is not cut."""
    httpd, base = server
    returned = min(total, limit)
    requested = min(50, limit)
    httpd.responses = [_page(0, requested, total, list(range(1, returned + 1)))]

    result = _read(base, limit=limit, httpd=httpd)

    assert [row["id"] for row in result["rows"]] == expected_ids
    assert result["truncated"] is expected_truncated
    assert result["total"] == total
    assert _queries(httpd)[0]["maxResults"] == [str(requested)]
    assert httpd.closed.wait(2)


def test_list_issue_comments_returns_the_same_rows_without_metadata(server) -> None:
    """The legacy list function accepts limit and returns only the rows."""
    httpd, base = server
    responses = [_page(0, 2, 5, [1, 2])]
    httpd.responses = list(responses)

    rows = jira.list_issue_comments(
        base,
        "DEMO-42",
        token=TOKEN,
        limit=2,
        allow_http_loopback=True,
    )
    httpd.responses = list(responses)
    metadata = jira.list_issue_comments_with_metadata(
        base,
        "DEMO-42",
        token=TOKEN,
        limit=2,
        allow_http_loopback=True,
    )

    assert rows == metadata["rows"]
    assert [row["id"] for row in rows] == ["1", "2"]
    assert _queries(httpd) == [
        {"startAt": ["0"], "maxResults": ["2"]},
        {"startAt": ["0"], "maxResults": ["2"]},
    ]
    assert httpd.closed.wait(2)


def test_default_call_still_pages_with_the_fixed_page_size(server) -> None:
    """Without limit the request sequence and the complete result stay unchanged."""
    httpd, base = server
    httpd.responses = [
        _page(0, 1, 2, [1]),
        _page(1, 1, 2, [2]),
    ]

    result = _read(base, limit=None, httpd=httpd)

    assert [row["id"] for row in result["rows"]] == ["1", "2"]
    assert result["truncated"] is False
    assert result["total"] == 2
    assert _queries(httpd) == [
        {"startAt": ["0"], "maxResults": ["50"]},
        {"startAt": ["1"], "maxResults": ["50"]},
    ]
    assert httpd.closed.wait(2)


def test_limit_spans_pages_and_shrinks_the_last_request(server) -> None:
    """A limit above one page keeps reading and caps the final page size."""
    httpd, base = server
    httpd.responses = [
        _page(0, 50, 60, list(range(1, 51))),
        _page(50, 10, 60, list(range(51, 61))),
    ]

    result = jira.list_issue_comments_with_metadata(
        base,
        "DEMO-42",
        token=TOKEN,
        limit=60,
        allow_http_loopback=True,
    )

    assert len(result["rows"]) == 60
    assert result["truncated"] is False
    assert result["total"] == 60
    assert _queries(httpd) == [
        {"startAt": ["0"], "maxResults": ["50"]},
        {"startAt": ["50"], "maxResults": ["10"]},
    ]
    assert httpd.closed.wait(2)


@pytest.mark.parametrize("limit", [0, 1001, True])
def test_invalid_limit_is_rejected_before_any_request(server, limit) -> None:
    """Out-of-range and non-integer limits fail without touching the network."""
    httpd, base = server

    with pytest.raises(AtlaWireError):
        jira.list_issue_comments(
            base,
            "DEMO-42",
            token=TOKEN,
            limit=limit,
            allow_http_loopback=True,
        )

    assert httpd.calls == []
