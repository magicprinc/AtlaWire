"""Black-box contracts for the Bitbucket author filters.

Bitbucket Server 5.10 documents a participant filter on the repository
``/pull-requests`` route (``username.N`` is mandatory, ``role.N`` optional) and
``direction``; ``/commits`` documents no author parameter at all. These tests
pin the observable behavior against a loopback HTTP server: the pull request
filter must travel in the request query, while the commit author selection must
happen on our side over pages the server already returned, without dropping
matches from later pages and without inventing a server filter.

Reference: https://docs.atlassian.com/bitbucket-server/rest/5.10.0/bitbucket-rest.html
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest

from atlawire import bitbucket
from atlawire.http import AtlaWireError

TOKEN = "synthetic-author-token"
ROOT = "/rest/api/1.0/projects/PROJ/repos/repo"
SHA_A = "a" * 40
SHA_B = "b" * 40
SHA_C = "c" * 40
SHA_D = "d" * 40


@pytest.fixture
def server():
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self):
            self.server.calls.append(  # type: ignore[attr-defined]
                (
                    self.command,
                    self.path,
                    self.headers.get("Accept"),
                    self.headers.get("Authorization"),
                )
            )
            status, payload = self.server.responses.pop(0)  # type: ignore[attr-defined]
            data = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def finish(self):
            try:
                super().finish()
            finally:
                self.server.closed.set()  # type: ignore[attr-defined]

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
        httpd.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


def page(values, last, next_start=None):
    result = {"values": values, "isLastPage": last}
    if next_start is not None:
        result["nextPageStart"] = next_start
    return result


def assert_call(call, path, query):
    method, target, accept, auth = call
    parsed = urlsplit(target)
    assert (method, parsed.path, parse_qs(parsed.query)) == ("GET", path, query)
    assert accept == "application/json"
    assert auth == "Bearer " + TOKEN


def assert_calls(server, path, queries):
    assert len(server.calls) == len(queries)
    for call, query in zip(server.calls, queries, strict=True):
        assert_call(call, path, query)
    assert server.closed.wait(3), "client did not close the HTTP connection"


def raw_commit(sha, author, message):
    return {"id": sha, "author": {"name": author}, "message": message}


def projected_commit(sha, author, message):
    return {"hash": sha, "date": None, "author": author, "message": message}


# 5.10 repository participant filter: username.N mandatory, role.N optional, plus
# direction. There is no participantStatus on the repository route; that
# parameter belongs to /dashboard/pull-requests only. The rows below are
# returned exactly as the server sent them, because this filter is server-side.
def test_pull_request_author_filter_is_a_server_query(server):
    httpd, url = server
    httpd.responses = [
        (
            200,
            page(
                [
                    {"id": 7, "title": "Mine", "state": "OPEN",
                     "author": {"user": {"name": "alice"}}},
                    {"id": 9, "title": "Answer", "state": "OPEN",
                     "author": {"user": {"name": "bob"}}},
                ],
                True,
            ),
        )
    ]
    rows = bitbucket.list_pull_requests(
        url,
        "PROJ/repo",
        token=TOKEN,
        state="ALL",
        order="OLDEST",
        author="alice",
        direction="OUTGOING",
        limit=50,
        allow_http_loopback=True,
    )
    assert [row["id"] for row in rows] == [7, 9]
    assert rows[0]["author"] == "alice"
    assert_calls(
        httpd,
        f"{ROOT}/pull-requests",
        [
            {
                "state": ["ALL"],
                "order": ["OLDEST"],
                "username.1": ["alice"],
                "role.1": ["AUTHOR"],
                "direction": ["OUTGOING"],
                "start": ["0"],
                "limit": ["50"],
            }
        ],
    )


# /commits has no author parameter in 5.10, so the client must filter the
# projected rows itself. The match on the second page proves that a page without
# matches is still followed through its opaque cursor instead of being treated
# as the end of history.
def test_commit_author_selection_filters_fetched_pages(server):
    httpd, url = server
    httpd.responses = [
        (200, page([raw_commit(SHA_B, "bob", "not mine")], False, 37)),
        (
            200,
            page(
                [
                    raw_commit(SHA_C, "alice", "mine"),
                    raw_commit(SHA_D, "bob", "not mine either"),
                ],
                True,
            ),
        ),
    ]
    rows = bitbucket.list_commits(
        url, "PROJ/repo", token=TOKEN, author="alice", limit=3,
        allow_http_loopback=True,
    )
    assert rows == [projected_commit(SHA_C, "alice", "mine")]
    assert_calls(
        httpd,
        f"{ROOT}/commits",
        [
            {"start": ["0"], "limit": ["3"]},
            {"start": ["37"], "limit": ["3"]},
        ],
    )


# The selection is an exact git author name: no substring and no case folding,
# so "alice" never matches "alice.b" or "Alice".
def test_commit_author_selection_is_exact(server):
    httpd, url = server
    httpd.responses = [
        (
            200,
            page(
                [
                    raw_commit(SHA_A, "alice", "exact"),
                    raw_commit(SHA_B, "alice.b", "prefix"),
                    raw_commit(SHA_C, "Alice", "case"),
                    raw_commit(SHA_D, "bob", "other"),
                ],
                True,
            ),
        )
    ]
    rows = bitbucket.list_commits(
        url, "PROJ/repo", token=TOKEN, author="alice", limit=10,
        allow_http_loopback=True,
    )
    assert rows == [projected_commit(SHA_A, "alice", "exact")]
    assert_calls(
        httpd, f"{ROOT}/commits", [{"start": ["0"], "limit": ["10"]}]
    )


# No match is an empty result, not an error, and the completeness flag says the
# whole history was seen rather than cut by the limit.
def test_commit_author_selection_without_matches_is_empty(server):
    httpd, url = server
    httpd.responses = [
        (
            200,
            page(
                [
                    raw_commit(SHA_A, "bob", "one"),
                    raw_commit(SHA_B, "carol", "two"),
                ],
                True,
            ),
        ),
        (
            200,
            page(
                [
                    raw_commit(SHA_A, "bob", "one"),
                    raw_commit(SHA_B, "carol", "two"),
                ],
                True,
            ),
        ),
    ]
    rows = bitbucket.list_commits(
        url, "PROJ/repo", token=TOKEN, author="alice", limit=5,
        allow_http_loopback=True,
    )
    listing = bitbucket.list_commits_with_metadata(
        url, "PROJ/repo", token=TOKEN, author="alice", limit=5,
        allow_http_loopback=True,
    )
    assert rows == []
    assert listing == {"commits": [], "limit": 5, "complete": True}
    assert_calls(
        httpd,
        f"{ROOT}/commits",
        [
            {"start": ["0"], "limit": ["5"]},
            {"start": ["0"], "limit": ["5"]},
        ],
    )


# The new keyword-only parameters are optional: calls that do not pass them must
# keep the previous request shape (no participant filter and no direction) and
# must not filter any rows.
def test_new_filters_do_not_change_existing_requests(server):
    httpd, url = server
    httpd.responses = [
        (200, page([{"id": 1, "title": "Title", "state": "OPEN"}], True)),
        (200, page([raw_commit(SHA_A, "bob", "message")], True)),
    ]
    assert bitbucket.list_pull_requests(
        url, "PROJ/repo", token=TOKEN, allow_http_loopback=True
    ) == [
        {
            "id": 1,
            "title": "Title",
            "state": "OPEN",
            "author": None,
            "from": None,
            "to": None,
            "updated": None,
        }
    ]
    assert bitbucket.list_commits(
        url, "PROJ/repo", token=TOKEN, allow_http_loopback=True
    ) == [projected_commit(SHA_A, "bob", "message")]
    assert len(httpd.calls) == 2
    assert_call(
        httpd.calls[0],
        f"{ROOT}/pull-requests",
        {"state": ["OPEN"], "start": ["0"], "limit": ["25"]},
    )
    assert_call(
        httpd.calls[1], f"{ROOT}/commits", {"start": ["0"], "limit": ["25"]}
    )
    assert httpd.closed.wait(3), "client did not close the HTTP connection"


# An unspecified filter is None; an empty name or an unsupported direction is a
# caller error detected before any request, never a silent "no filter".
def test_invalid_author_and_direction_rejected_before_request(server):
    httpd, url = server
    with pytest.raises(AtlaWireError):
        bitbucket.list_pull_requests(
            url, "PROJ/repo", token=TOKEN, author="", allow_http_loopback=True
        )
    with pytest.raises(AtlaWireError):
        bitbucket.list_pull_requests(
            url, "PROJ/repo", token=TOKEN, author="ali\x00ce",
            allow_http_loopback=True,
        )
    with pytest.raises(AtlaWireError):
        bitbucket.list_pull_requests(
            url, "PROJ/repo", token=TOKEN, direction="SIDEWAYS",
            allow_http_loopback=True,
        )
    with pytest.raises(AtlaWireError):
        bitbucket.list_commits(
            url, "PROJ/repo", token=TOKEN, author="", allow_http_loopback=True
        )
    with pytest.raises(AtlaWireError):
        bitbucket.list_commits_with_metadata(
            url, "PROJ/repo", token=TOKEN, author="bo\x00b",
            allow_http_loopback=True,
        )
    assert httpd.calls == []
