"""Black-box contracts for the missing Jira and Bitbucket read functions."""

import json
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import NamedTuple
from urllib.parse import parse_qs, urlsplit

import pytest

from atlawire import bitbucket, jira
from atlawire.http import AtlaWireError

TOKEN = "synthetic-token-missing-functions"
SECRET = "synthetic-private-error-body"
JQL = "project = SPEC ORDER BY key ASC"
JSON = "application/json"


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
        httpd.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


def load(server, status, value, content_type=JSON):
    body = value if isinstance(value, bytes) else json.dumps(value).encode()
    server.responses.append((status, body, content_type))


def assert_calls(server, expected):
    assert server.unexpected == []
    assert len(server.calls) == len(expected)
    for call, (method, path, query, accept) in zip(
        server.calls, expected, strict=True
    ):
        parsed = urlsplit(call.target)
        assert (
            call.method,
            parsed.path,
            parse_qs(parsed.query, keep_blank_values=True),
        ) == (
            method,
            path,
            query,
        )
        assert call.accept == accept
        assert call.authorization == "Bearer " + TOKEN


def assert_sanitized(error, status):
    assert (error.category, error.http_status) == ("http", status)
    diagnostic = "".join(traceback.format_exception(error))
    assert SECRET not in diagnostic
    assert TOKEN not in diagnostic


# Jira 8.22 search metadata: startAt, maxResults, total, issues. The response
# does not document isLast, and total may be absent.
def search_page(start, issues, total=None, *, max_results=100, is_last=None):
    payload = {
        "startAt": start,
        "maxResults": max_results,
        "issues": issues,
    }
    if total is not None:
        payload["total"] = total
    if is_last is not None:
        payload["isLast"] = is_last
    return payload


# Unknown top-level and nested fields must survive the raw pass-through.
ISSUE_ONE = {
    "key": "SPEC-1",
    "fields": {"summary": "one", "customfield_100": {"nested": [1, None]}},
    "unknown": True,
}
ISSUE_TWO = {"key": "SPEC-2", "fields": {"summary": "two"}, "unknown": {"x": 7}}
ISSUE_THREE = {"key": "SPEC-3", "fields": {"summary": "three"}}


def test_search_all_issues_pages_until_total(server):
    httpd, base = server
    # The server caps the page at 2 and echoes it, so the next request asks for
    # 2 rather than 100. Its undocumented isLast=true must be ignored.
    load(
        httpd,
        200,
        search_page(0, [ISSUE_ONE, ISSUE_TWO], 3, max_results=2, is_last=True),
    )
    load(httpd, 200, search_page(2, [ISSUE_THREE], 3, max_results=2))
    assert jira.search_all_issues(
        base, JQL, token=TOKEN, allow_http_loopback=True
    ) == [ISSUE_ONE, ISSUE_TWO, ISSUE_THREE]
    assert_calls(
        httpd,
        [
            (
                "GET",
                "/rest/api/2/search",
                {
                    "jql": [JQL],
                    "fields": ["*all"],
                    "startAt": ["0"],
                    "maxResults": ["100"],
                },
                JSON,
            ),
            (
                "GET",
                "/rest/api/2/search",
                {
                    "jql": [JQL],
                    "fields": ["*all"],
                    "startAt": ["2"],
                    "maxResults": ["2"],
                },
                JSON,
            ),
        ],
    )


def test_search_all_issues_stops_at_limit(server):
    httpd, base = server
    load(httpd, 200, search_page(0, [ISSUE_ONE, ISSUE_TWO], 9, max_results=3))
    load(httpd, 200, search_page(2, [ISSUE_THREE], 9, max_results=1))
    assert jira.search_all_issues(
        base,
        JQL,
        token=TOKEN,
        fields=["summary", "status"],
        limit=3,
        allow_http_loopback=True,
    ) == [ISSUE_ONE, ISSUE_TWO, ISSUE_THREE]
    assert_calls(
        httpd,
        [
            (
                "GET",
                "/rest/api/2/search",
                {
                    "jql": [JQL],
                    "fields": ["summary,status"],
                    "startAt": ["0"],
                    "maxResults": ["3"],
                },
                JSON,
            ),
            (
                "GET",
                "/rest/api/2/search",
                {
                    "jql": [JQL],
                    "fields": ["summary,status"],
                    "startAt": ["2"],
                    "maxResults": ["1"],
                },
                JSON,
            ),
        ],
    )


def test_search_all_issues_stops_when_total_is_reached(server):
    httpd, base = server
    load(
        httpd,
        200,
        search_page(0, [ISSUE_ONE, ISSUE_TWO], 2, max_results=2, is_last=False),
    )
    assert jira.search_all_issues(
        base, JQL, token=TOKEN, allow_http_loopback=True
    ) == [ISSUE_ONE, ISSUE_TWO]
    assert_calls(
        httpd,
        [
            (
                "GET",
                "/rest/api/2/search",
                {
                    "jql": [JQL],
                    "fields": ["*all"],
                    "startAt": ["0"],
                    "maxResults": ["100"],
                },
                JSON,
            )
        ],
    )


def test_search_all_issues_stops_on_empty_page_without_total(server):
    httpd, base = server
    load(httpd, 200, search_page(0, [ISSUE_ONE], max_results=2))
    load(httpd, 200, search_page(1, [], max_results=2))
    assert jira.search_all_issues(
        base, JQL, token=TOKEN, allow_http_loopback=True
    ) == [ISSUE_ONE]
    assert_calls(
        httpd,
        [
            (
                "GET",
                "/rest/api/2/search",
                {
                    "jql": [JQL],
                    "fields": ["*all"],
                    "startAt": ["0"],
                    "maxResults": ["100"],
                },
                JSON,
            ),
            (
                "GET",
                "/rest/api/2/search",
                {
                    "jql": [JQL],
                    "fields": ["*all"],
                    "startAt": ["1"],
                    "maxResults": ["2"],
                },
                JSON,
            ),
        ],
    )


def test_search_all_issues_stops_at_page_budget(server):
    httpd, base = server
    # A server that never proves the end of the traversal must not drive an
    # unbounded request series; the budget raises instead of returning rows.
    load(httpd, 200, search_page(0, [ISSUE_ONE], 9, max_results=1))
    load(httpd, 200, search_page(1, [ISSUE_TWO], 9, max_results=1))
    with pytest.raises(AtlaWireError, match="page limit"):
        jira.search_all_issues(
            base, JQL, token=TOKEN, max_pages=2, allow_http_loopback=True
        )
    assert_calls(
        httpd,
        [
            (
                "GET",
                "/rest/api/2/search",
                {
                    "jql": [JQL],
                    "fields": ["*all"],
                    "startAt": ["0"],
                    "maxResults": ["100"],
                },
                JSON,
            ),
            (
                "GET",
                "/rest/api/2/search",
                {
                    "jql": [JQL],
                    "fields": ["*all"],
                    "startAt": ["1"],
                    "maxResults": ["1"],
                },
                JSON,
            ),
        ],
    )


def test_search_all_issues_rejects_empty_page_before_total(server):
    httpd, base = server
    load(httpd, 200, search_page(0, [ISSUE_ONE], 3, max_results=2))
    load(httpd, 200, search_page(1, [], 3, max_results=2))
    with pytest.raises(AtlaWireError, match="empty page"):
        jira.search_all_issues(base, JQL, token=TOKEN, allow_http_loopback=True)
    assert_calls(
        httpd,
        [
            (
                "GET",
                "/rest/api/2/search",
                {
                    "jql": [JQL],
                    "fields": ["*all"],
                    "startAt": ["0"],
                    "maxResults": ["100"],
                },
                JSON,
            ),
            (
                "GET",
                "/rest/api/2/search",
                {
                    "jql": [JQL],
                    "fields": ["*all"],
                    "startAt": ["1"],
                    "maxResults": ["2"],
                },
                JSON,
            ),
        ],
    )


@pytest.mark.parametrize("max_pages", [0, -1, True, 1.5])
def test_search_all_issues_rejects_invalid_page_budget(server, max_pages):
    httpd, base = server
    with pytest.raises(AtlaWireError, match="page limit"):
        jira.search_all_issues(
            base,
            JQL,
            token=TOKEN,
            max_pages=max_pages,
            allow_http_loopback=True,
        )
    assert httpd.calls == []
    assert httpd.unexpected == []


def test_search_all_issues_http_error_is_sanitized(server):
    httpd, base = server
    load(httpd, 403, {"errors": [{"message": SECRET + TOKEN}]})
    with pytest.raises(AtlaWireError) as caught:
        jira.search_all_issues(base, JQL, token=TOKEN, allow_http_loopback=True)
    assert_sanitized(caught.value, 403)
    assert len(httpd.calls) == 1


# Bitbucket Server pagination follows nextPageStart and isLastPage only.
def repos_page(values, *, last, next_start=None, start=None, size=None):
    payload = {"values": values, "isLastPage": last}
    if next_start is not None:
        payload["nextPageStart"] = next_start
    if start is not None:
        payload["start"] = start
    if size is not None:
        payload["size"] = size
    return payload


REPO_ONE = {
    "slug": "alpha",
    "name": "Alpha",
    "project": {"key": "PRJ"},
    "unknownField": {"nested": [1, None]},
}
REPO_TWO = {
    "slug": "beta",
    "name": "Beta",
    "links": {"self": [{"href": "http://127.0.0.1/href"}]},
}
REPOS_PATH = "/rest/api/1.0/repos"


def test_list_all_repositories_follows_opaque_next_page_start(server):
    httpd, base = server
    load(
        httpd,
        200,
        repos_page([REPO_ONE], last=False, next_start=37, start=0, size=1),
    )
    # The terminal page still advertises nextPageStart, so stopping must be
    # driven by isLastPage rather than by the absence of a next cursor.
    load(
        httpd,
        200,
        repos_page([REPO_TWO], last=True, next_start=999, start=37, size=1),
    )
    assert bitbucket.list_all_repositories(
        base, token=TOKEN, allow_http_loopback=True
    ) == [REPO_ONE, REPO_TWO]
    assert_calls(
        httpd,
        [
            ("GET", REPOS_PATH, {"start": ["0"], "limit": ["100"]}, JSON),
            ("GET", REPOS_PATH, {"start": ["37"], "limit": ["100"]}, JSON),
        ],
    )


def test_list_all_repositories_honors_start_and_limit(server):
    httpd, base = server
    load(httpd, 200, repos_page([REPO_TWO], last=True))
    assert bitbucket.list_all_repositories(
        base, token=TOKEN, start=5, limit=2, allow_http_loopback=True
    ) == [REPO_TWO]
    assert_calls(
        httpd,
        [("GET", REPOS_PATH, {"start": ["5"], "limit": ["2"]}, JSON)],
    )


def test_list_all_repositories_http_error_is_sanitized(server):
    httpd, base = server
    load(httpd, 404, {"errors": [{"message": SECRET + TOKEN}]})
    with pytest.raises(AtlaWireError) as caught:
        bitbucket.list_all_repositories(
            base, token=TOKEN, allow_http_loopback=True
        )
    assert_sanitized(caught.value, 404)
    assert len(httpd.calls) == 1


@pytest.mark.parametrize(
    "payload",
    [
        {"values": [REPO_ONE]},
        repos_page([REPO_ONE], last="false"),
        repos_page([REPO_ONE], last=0),
    ],
)
def test_list_all_repositories_rejects_invalid_is_last_page(server, payload):
    httpd, base = server
    load(httpd, 200, payload)
    with pytest.raises(AtlaWireError, match="isLastPage"):
        bitbucket.list_all_repositories(base, token=TOKEN, allow_http_loopback=True)
    assert_calls(
        httpd,
        [("GET", REPOS_PATH, {"start": ["0"], "limit": ["100"]}, JSON)],
    )


@pytest.mark.parametrize(
    "payload",
    [
        repos_page([REPO_ONE], last=False),
        repos_page([REPO_ONE], last=False, next_start=0),
        repos_page([REPO_ONE], last=False, next_start=-3),
        repos_page([REPO_ONE], last=False, next_start="7"),
        repos_page([REPO_ONE], last=False, next_start=True),
    ],
)
def test_list_all_repositories_rejects_invalid_next_page_start(server, payload):
    httpd, base = server
    load(httpd, 200, payload)
    with pytest.raises(AtlaWireError, match="nextPageStart"):
        bitbucket.list_all_repositories(base, token=TOKEN, allow_http_loopback=True)
    assert_calls(
        httpd,
        [("GET", REPOS_PATH, {"start": ["0"], "limit": ["100"]}, JSON)],
    )


ARCHIVE = b"PK\x03\x04\x00\x01\xff\xfe binary\x80payload"
ARCHIVE_PATH = "/rest/api/1.0/projects/PRJ/repos/repo/archive"


@pytest.mark.parametrize(
    ("kwargs", "query"),
    [
        ({}, {}),
        (
            {"at": "refs/heads/main", "format": "tar.gz"},
            {"at": ["refs/heads/main"], "format": ["tar.gz"]},
        ),
    ],
)
def test_get_repository_archive_returns_exact_binary(server, kwargs, query):
    httpd, base = server
    load(httpd, 200, ARCHIVE, "application/zip")
    assert (
        bitbucket.get_repository_archive(
            base, "PRJ", "repo", token=TOKEN, allow_http_loopback=True, **kwargs
        )
        == ARCHIVE
    )
    assert_calls(httpd, [("GET", ARCHIVE_PATH, query, "*/*")])


@pytest.mark.parametrize(
    ("project", "repository", "kwargs"),
    [
        ("PRJ", "repo", {"format": "rar"}),
        ("../etc", "repo", {}),
        ("PRJ", "..", {}),
        ("PRJ", "repo", {"at": ""}),
        ("PRJ", "repo", {"max_bytes": 0}),
        ("PRJ", "repo", {"max_bytes": -1}),
        ("PRJ", "repo", {"max_bytes": True}),
        ("PRJ", "repo", {"max_bytes": 1.5}),
    ],
)
def test_get_repository_archive_rejects_invalid_arguments(
    server, project, repository, kwargs
):
    httpd, base = server
    with pytest.raises(AtlaWireError):
        bitbucket.get_repository_archive(
            base,
            project,
            repository,
            token=TOKEN,
            allow_http_loopback=True,
            **kwargs,
        )
    assert httpd.calls == []
    assert httpd.unexpected == []


def test_get_repository_archive_http_error_is_sanitized(server):
    httpd, base = server
    load(httpd, 500, {"errors": [{"message": SECRET + TOKEN}]})
    with pytest.raises(AtlaWireError) as caught:
        bitbucket.get_repository_archive(
            base, "PRJ", "repo", token=TOKEN, allow_http_loopback=True
        )
    assert_sanitized(caught.value, 500)
    assert len(httpd.calls) == 1


def test_get_repository_archive_rejects_partial_content(server):
    httpd, base = server
    load(httpd, 206, ARCHIVE, "application/zip")
    with pytest.raises(AtlaWireError) as caught:
        bitbucket.get_repository_archive(
            base, "PRJ", "repo", token=TOKEN, allow_http_loopback=True
        )
    assert_sanitized(caught.value, 206)
    assert len(httpd.calls) == 1


@pytest.mark.parametrize("status", [301, 302, 307, 308])
def test_get_repository_archive_rejects_redirects(server, status):
    httpd, base = server
    load(httpd, status, b"", "text/html")
    with pytest.raises(AtlaWireError) as caught:
        bitbucket.get_repository_archive(
            base, "PRJ", "repo", token=TOKEN, allow_http_loopback=True
        )
    assert_sanitized(caught.value, status)
    assert len(httpd.calls) == 1


def test_get_repository_archive_rejects_oversize_body(server):
    httpd, base = server
    load(httpd, 200, ARCHIVE, "application/zip")
    with pytest.raises(AtlaWireError, match="byte limit") as caught:
        bitbucket.get_repository_archive(
            base,
            "PRJ",
            "repo",
            token=TOKEN,
            max_bytes=len(ARCHIVE) - 1,
            allow_http_loopback=True,
        )
    assert caught.value.category == "upstream"
    assert len(httpd.calls) == 1


def test_get_repository_archive_accepts_body_at_the_byte_limit(server):
    httpd, base = server
    load(httpd, 200, ARCHIVE, "application/zip")
    assert (
        bitbucket.get_repository_archive(
            base,
            "PRJ",
            "repo",
            token=TOKEN,
            max_bytes=len(ARCHIVE),
            allow_http_loopback=True,
        )
        == ARCHIVE
    )
    assert_calls(httpd, [("GET", ARCHIVE_PATH, {}, "*/*")])


def test_get_repository_archive_allows_explicitly_unbounded_read(server):
    httpd, base = server
    load(httpd, 200, ARCHIVE, "application/zip")
    assert (
        bitbucket.get_repository_archive(
            base,
            "PRJ",
            "repo",
            token=TOKEN,
            max_bytes=None,
            allow_http_loopback=True,
        )
        == ARCHIVE
    )
    assert_calls(httpd, [("GET", ARCHIVE_PATH, {}, "*/*")])
