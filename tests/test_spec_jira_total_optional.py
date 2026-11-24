"""Black-box contracts: optional Jira 8.22 search ``total`` and user resolution.

Jira 8.22.2 documents the ``/rest/api/2/search`` envelope with ``startAt``,
``maxResults``, ``total`` and ``issues``, and states that ``total`` may be
empty. Exhaustion is therefore proven only by an empty page, while a known
``total`` that is not reached stays an error. ``isLast`` is not documented and
must not be read. The page size is taken from the ``maxResults`` echo.
"""

import json
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest

from atlawire import jira, jira_comments_search
from atlawire.http import AtlaWireError

TOKEN = "synthetic-token-optional-total"
JQL = "project = SPEC ORDER BY key ASC"
SEARCH_FIELDS = "summary,status,priority,issuetype,assignee,updated"
COMMENT_SEARCH_FIELDS = "summary,comment,updated"
COMMENT_JQL = "updated >= -90d ORDER BY updated DESC"


@pytest.fixture
def server():
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self):
            self.server.calls.append(  # type: ignore[attr-defined]
                (
                    self.command,
                    self.path,
                    self.headers.get("Authorization"),
                )
            )
            responses = self.server.responses  # type: ignore[attr-defined]
            if not responses:
                # A reader that keeps paging past the scripted data must fail
                # fast instead of re-reading a stale terminal page.
                self.send_error(599)
                return
            status, value = responses.pop(0)
            body = json.dumps(value).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    httpd.calls = []  # type: ignore[attr-defined]
    httpd.responses = []  # type: ignore[attr-defined]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd, f"http://127.0.0.1:{httpd.server_port}"
    finally:
        httpd.shutdown()
        thread.join(timeout=5)
        httpd.server_close()
        assert not thread.is_alive()


def assert_calls(server, expected):
    assert len(server.calls) == len(expected), server.calls
    for call, (method, path, query) in zip(server.calls, expected, strict=True):
        got_method, target, authorization = call
        parsed = urlsplit(target)
        assert (got_method, parsed.path, parse_qs(parsed.query)) == (
            method,
            path,
            query,
        )
        assert authorization == "Bearer " + TOKEN


def search_page(start, issues, *, total=None, max_results=100):
    payload = {"startAt": start, "maxResults": max_results, "issues": issues}
    if total is not None:
        payload["total"] = total
    return payload


ISSUE_ONE = {
    "key": "SPEC-1",
    "fields": {"summary": "one", "updated": "2024-01-01T00:00:00.000+0000"},
}
ISSUE_TWO = {
    "key": "SPEC-2",
    "fields": {"summary": "two", "updated": "2024-01-02T00:00:00.000+0000"},
}
ISSUE_THREE = {
    "key": "SPEC-3",
    "fields": {"summary": "three", "updated": "2024-01-03T00:00:00.000+0000"},
}


def test_search_issues_pages_past_an_is_last_page_without_total(server):
    """Three issues, then an empty page: the rows come back without an error.

    The first page carries the undocumented ``isLast: true`` and no ``total``,
    so a reader that trusts either flag would stop after one request.
    """
    httpd, base = server
    httpd.responses = [
        (
            200,
            {
                **search_page(0, [ISSUE_ONE, ISSUE_TWO, ISSUE_THREE], max_results=3),
                "isLast": True,
            },
        ),
        (200, search_page(3, [], max_results=3)),
    ]
    rows = jira.search_issues(
        base, JQL, token=TOKEN, limit=10, allow_http_loopback=True
    )
    assert [row["key"] for row in rows] == ["SPEC-1", "SPEC-2", "SPEC-3"]
    assert [row["summary"] for row in rows] == ["one", "two", "three"]
    assert_calls(
        httpd,
        [
            (
                "GET",
                "/rest/api/2/search",
                {
                    "jql": [JQL],
                    "fields": [SEARCH_FIELDS],
                    "startAt": ["0"],
                    "maxResults": ["10"],
                },
            ),
            (
                "GET",
                "/rest/api/2/search",
                {
                    "jql": [JQL],
                    "fields": [SEARCH_FIELDS],
                    "startAt": ["3"],
                    # Page size comes from the echoed maxResults, not the
                    # remaining limit.
                    "maxResults": ["3"],
                },
            ),
        ],
    )


COMMENT_ISSUE = {
    "key": "SPEC-1",
    "fields": {
        "summary": "sample",
        "updated": "2024-01-01T00:00:00.000+0000",
        "comment": {
            "comments": [
                {
                    "id": "10",
                    "author": {"name": "alice"},
                    "body": "hello",
                    "created": "2024-01-01T00:00:00.000+0000",
                }
            ],
            "total": 1,
        },
    },
}


def test_author_comments_finish_on_empty_page_without_total(server):
    """A comment scan ends on the first empty search page when total is empty."""
    httpd, base = server
    httpd.responses = [
        (200, {"name": "alice", "displayName": "Alice"}),
        (200, search_page(0, [COMMENT_ISSUE], max_results=1)),
        (200, search_page(1, [], max_results=1)),
    ]
    rows = jira_comments_search.find_author_comments(
        base,
        token=TOKEN,
        allow_http_loopback=True,
    )
    assert rows == [
        {
            "key": "SPEC-1",
            "summary": "sample",
            "created": "2024-01-01T00:00:00.000+0000",
            "author": "Alice",
            "comment_id": "10",
            "url": f"{base}/browse/SPEC-1?focusedCommentId=10#comment-10",
            "body": "hello",
        }
    ]
    assert_calls(
        httpd,
        [
            ("GET", "/rest/api/2/myself", {}),
            (
                "GET",
                "/rest/api/2/search",
                {
                    "jql": [COMMENT_JQL],
                    "fields": [COMMENT_SEARCH_FIELDS],
                    "startAt": ["0"],
                    "maxResults": ["100"],
                },
            ),
            (
                "GET",
                "/rest/api/2/search",
                {
                    "jql": [COMMENT_JQL],
                    "fields": [COMMENT_SEARCH_FIELDS],
                    "startAt": ["1"],
                    "maxResults": ["1"],
                },
            ),
        ],
    )


def test_author_comments_fail_on_empty_page_before_known_total(server):
    """A total revealed later still forbids claiming a complete scan early."""
    httpd, base = server
    httpd.responses = [
        (200, {"name": "alice", "displayName": "Alice"}),
        (200, search_page(0, [COMMENT_ISSUE], max_results=1)),
        (200, search_page(1, [], total=2, max_results=1)),
    ]
    with pytest.raises(AtlaWireError, match="empty page"):
        jira_comments_search.find_author_comments(
            base,
            token=TOKEN,
            allow_http_loopback=True,
        )
    assert_calls(
        httpd,
        [
            ("GET", "/rest/api/2/myself", {}),
            (
                "GET",
                "/rest/api/2/search",
                {
                    "jql": [COMMENT_JQL],
                    "fields": [COMMENT_SEARCH_FIELDS],
                    "startAt": ["0"],
                    "maxResults": ["100"],
                },
            ),
            (
                "GET",
                "/rest/api/2/search",
                {
                    "jql": [COMMENT_JQL],
                    "fields": [COMMENT_SEARCH_FIELDS],
                    "startAt": ["1"],
                    "maxResults": ["1"],
                },
            ),
        ],
    )


def user_row(name, display=None, email=None):
    row = {"name": name}
    if display is not None:
        row["displayName"] = display
    if email is not None:
        row["emailAddress"] = email
    return row


def test_resolve_user_without_term_reads_the_current_user(server):
    """A missing term resolves /myself and keeps only the three public fields."""
    httpd, base = server
    httpd.responses = [
        (
            200,
            {
                "name": "alice",
                "displayName": "Alice",
                "emailAddress": "alice@example.org",
                "extra": 7,
            },
        )
    ]
    assert jira.resolve_user(base, token=TOKEN, allow_http_loopback=True) == {
        "name": "alice",
        "displayName": "Alice",
        "email": "alice@example.org",
    }
    assert_calls(httpd, [("GET", "/rest/api/2/myself", {})])


def test_resolve_user_prefers_the_exact_login_over_a_candidate(server):
    """The exact login wins even when a non-exact candidate comes first."""
    httpd, base = server
    httpd.responses = [
        (
            200,
            [
                user_row("alice.partner", "Partner", "partner@example.org"),
                user_row("alice", "Alice", "alice@example.org"),
            ],
        )
    ]
    assert jira.resolve_user(base, "alice", token=TOKEN, allow_http_loopback=True) == {
        "name": "alice",
        "displayName": "Alice",
        "email": "alice@example.org",
    }
    assert_calls(
        httpd,
        [
            (
                "GET",
                "/rest/api/2/user/search",
                {"username": ["alice"], "startAt": ["0"], "maxResults": ["50"]},
            )
        ],
    )


def test_resolve_user_rejects_two_equivalent_candidates(server):
    """Two distinct non-exact users fail closed and are named in the error."""
    httpd, base = server
    httpd.responses = [
        (200, []),
        (
            200,
            [
                user_row("ivan.petrov", "Petr", "petrov@example.org"),
                user_row("ivan.sidorov", "Sidor", "sidorov@example.org"),
            ],
        ),
        (200, []),
    ]
    with pytest.raises(AtlaWireError) as caught:
        jira.resolve_user(base, "иван", token=TOKEN, allow_http_loopback=True)
    message = str(caught.value)
    assert "ivan.petrov" in message
    assert "ivan.sidorov" in message
    rendered = "".join(traceback.format_exception(caught.value))
    assert TOKEN not in rendered
    assert_calls(
        httpd,
        [
            (
                "GET",
                "/rest/api/2/user/search",
                {"username": ["иван"], "startAt": ["0"], "maxResults": ["50"]},
            ),
            (
                "GET",
                "/rest/api/2/user/search",
                {"username": ["ivan"], "startAt": ["0"], "maxResults": ["50"]},
            ),
            (
                "GET",
                "/rest/api/2/user/search",
                {"username": ["ivan"], "startAt": ["2"], "maxResults": ["50"]},
            ),
        ],
    )


def test_resolve_user_transliterates_a_cyrillic_term(server):
    """A Cyrillic term is retried with its BBK transliteration."""
    httpd, base = server
    httpd.responses = [
        (200, []),
        (200, [user_row("ivanov", "Ivanov", "ivanov@example.org")]),
    ]
    assert jira.resolve_user(base, "Иванов", token=TOKEN, allow_http_loopback=True) == {
        "name": "ivanov",
        "displayName": "Ivanov",
        "email": "ivanov@example.org",
    }
    assert_calls(
        httpd,
        [
            (
                "GET",
                "/rest/api/2/user/search",
                {"username": ["Иванов"], "startAt": ["0"], "maxResults": ["50"]},
            ),
            (
                "GET",
                "/rest/api/2/user/search",
                {"username": ["ivanov"], "startAt": ["0"], "maxResults": ["50"]},
            ),
        ],
    )
