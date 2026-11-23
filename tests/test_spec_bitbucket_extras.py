"""Black-box contracts for the Bitbucket Server 5.10 repository extras.

Every request goes to a loopback server: the test asserts the exact path, the
exact query, the flat default projection, the raw mode, paging strictly by the
server-provided ``nextPageStart``/``isLastPage``, and sanitized failures.
"""

import json
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest

from atlawire import bitbucket
from atlawire.http import AtlaWireError

TOKEN = "synthetic-token-for-extras"
BODY = "synthetic-private-error-body"


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
            data = b"" if status == 204 else json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            if data:
                self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            if data:
                self.wfile.write(data)

        def finish(self):
            try:
                super().finish()
            finally:
                self.server.closed.set()  # type: ignore[attr-defined]

        def log_message(self, format: str, *args: object) -> None:
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    httpd.calls = []  # type: ignore[attr-defined]
    httpd.responses = []  # type: ignore[attr-defined]
    httpd.closed = threading.Event()  # type: ignore[attr-defined]
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


def reply(httpd, status, payload):
    httpd.responses.append((status, payload))


def assert_calls(server, path, queries):
    paths = [path] * len(queries) if isinstance(path, str) else path
    assert len(server.calls) == len(queries) == len(paths)
    for (method, target, accept, auth), query, expected_path in zip(
        server.calls, queries, paths, strict=True
    ):
        parsed = urlsplit(target)
        assert (method, parsed.path, parse_qs(parsed.query)) == (
            "GET",
            expected_path,
            query,
        )
        assert accept == "application/json"
        assert auth == "Bearer " + TOKEN
    assert server.closed.wait(3), "client did not close the HTTP connection"


PROJECT = {
    "key": "AB",
    "id": 7,
    "name": "Address Book",
    "description": "Address book services",
    "public": False,
    "type": "NORMAL",
    "links": {"self": [{"href": "http://example.invalid/projects/AB"}]},
    "unknown": {"nested": [1, None]},
}


# 5.10 GET /projects/{projectKey}: project object with id/links beyond the projection.
def test_get_project_projection_and_raw(server):
    httpd, url = server
    reply(httpd, 200, PROJECT)
    reply(httpd, 200, {"key": "B"})
    reply(httpd, 200, PROJECT)

    assert bitbucket.get_project(url, "AB", token=TOKEN, allow_http_loopback=True) == {
        "key": "AB",
        "name": "Address Book",
        "description": "Address book services",
        "public": False,
        "type": "NORMAL",
    }
    # Missing optional fields are projected as None, never guessed.
    assert bitbucket.get_project(url, "B", token=TOKEN, allow_http_loopback=True) == {
        "key": "B",
        "name": None,
        "description": None,
        "public": None,
        "type": None,
    }
    # Raw mode returns the decoded response untouched, unknown fields included.
    assert (
        bitbucket.get_project(
            url, "AB", token=TOKEN, raw=True, allow_http_loopback=True
        )
        == PROJECT
    )
    assert_calls(
        httpd,
        [
            "/rest/api/1.0/projects/AB",
            "/rest/api/1.0/projects/B",
            "/rest/api/1.0/projects/AB",
        ],
        [{}, {}, {}],
    )


REPOSITORY = {
    "slug": "address-book-api",
    "id": 12,
    "name": "address-book-api",
    "scmId": "git",
    "state": "AVAILABLE",
    "statusMessage": "Available",
    "forkable": True,
    "project": {"key": "AB", "id": 1, "name": "Address Book", "public": False},
    "public": False,
    "links": {"self": [{"href": "http://example.invalid/repo"}]},
}


# Live 5.10: the repository representation carries no defaultBranch, so the
# projected field stays None; a server that does send it is projected as text.
def test_get_repository_projection_default_branch_is_optional(server):
    httpd, url = server
    reply(httpd, 200, REPOSITORY)
    reply(httpd, 200, {**REPOSITORY, "defaultBranch": "main"})
    reply(httpd, 200, REPOSITORY)

    assert bitbucket.get_repository(
        url, "AB", "address-book-api", token=TOKEN, allow_http_loopback=True
    ) == {
        "slug": "address-book-api",
        "name": "address-book-api",
        "state": "AVAILABLE",
        "public": False,
        "defaultBranch": None,
    }
    assert (
        bitbucket.get_repository(
            url, "AB", "address-book-api", token=TOKEN, allow_http_loopback=True
        )["defaultBranch"]
        == "main"
    )
    raw = bitbucket.get_repository(
        url,
        "AB",
        "address-book-api",
        token=TOKEN,
        raw=True,
        allow_http_loopback=True,
    )
    assert isinstance(raw, dict) and raw == REPOSITORY
    assert_calls(
        httpd,
        "/rest/api/1.0/projects/AB/repos/address-book-api",
        [{}, {}, {}],
    )


BRANCH = {
    "id": "refs/heads/master",
    "displayId": "master",
    "type": "BRANCH",
    "latestCommit": "8d51122def5632836d1cb1026e879069e10a1e13",
    "latestChangeset": "8d51122def5632836d1cb1026e879069e10a1e13",
    "isDefault": True,
}


# 5.10 documents 204 for a repository with no default branch; that is not an error.
def test_get_default_branch_projection_and_empty_repository(server):
    httpd, url = server
    reply(httpd, 200, BRANCH)
    reply(httpd, 204, None)

    assert bitbucket.get_default_branch(
        url, "AB", "address-book-api", token=TOKEN, allow_http_loopback=True
    ) == {
        "id": "refs/heads/master",
        "displayId": "master",
        "latestCommit": "8d51122def5632836d1cb1026e879069e10a1e13",
        "isDefault": True,
    }
    assert (
        bitbucket.get_default_branch(
            url, "AB", "address-book-api", token=TOKEN, allow_http_loopback=True
        )
        is None
    )
    assert_calls(
        httpd,
        "/rest/api/1.0/projects/AB/repos/address-book-api/branches/default",
        [{}, {}],
    )


def change(path):
    return {
        "contentId": "abcdef0123abcdef4567abcdef8987abcdef6543",
        "fromContentId": "bcdef0123abcdef4567abcdef8987abcdef6543a",
        "path": {
            "toString": path,
            "components": path.split("/"),
            "parent": path.partition("/")[0],
            "name": path.rpartition("/")[2],
            "extension": "java",
        },
        "type": "MODIFY",
        "nodeType": "FILE",
        "percentUnchanged": 98,
        "links": {"self": [{"href": "http://example.invalid/change"}]},
    }


# 5.10 /changes rows are changed files; paging follows the opaque cursor and the
# since/until selectors are sent only as documented query parameters.
def test_repository_changes_cursor_projection_and_selectors(server):
    httpd, url = server
    reply(httpd, 200, page([change("src/App.java")], False, 37))
    reply(httpd, 200, page([change("src/Other.java")], True))

    assert bitbucket.get_repository_changes(
        url,
        "AB",
        "repo",
        "825966b0",
        token=TOKEN,
        since="be656317",
        allow_http_loopback=True,
    ) == [
        {"path": "src/App.java", "type": "MODIFY", "node": "FILE"},
        {"path": "src/Other.java", "type": "MODIFY", "node": "FILE"},
    ]
    assert_calls(
        httpd,
        "/rest/api/1.0/projects/AB/repos/repo/changes",
        [
            {
                "until": ["825966b0"],
                "since": ["be656317"],
                "start": ["0"],
                "limit": ["100"],
            },
            {
                "until": ["825966b0"],
                "since": ["be656317"],
                "start": ["37"],
                "limit": ["100"],
            },
        ],
    )


# The row cap stops the walk without reading the unused next-page hint; the
# shortened request size proves the cap is applied before the request.
def test_repository_changes_limit_stops_without_terminal_page(server):
    httpd, url = server
    reply(httpd, 200, page([change("src/App.java")], False, 5))

    assert bitbucket.get_repository_changes(
        url, "AB", "repo", "825966b0", token=TOKEN, limit=1, allow_http_loopback=True
    ) == [{"path": "src/App.java", "type": "MODIFY", "node": "FILE"}]
    assert_calls(
        httpd,
        "/rest/api/1.0/projects/AB/repos/repo/changes",
        [{"until": ["825966b0"], "start": ["0"], "limit": ["1"]}],
    )


# Neither `start += limit` nor a missing flag may be guessed: a non-advancing
# cursor and a non-boolean isLastPage are rejected instead of silently looping.
@pytest.mark.parametrize(
    "payload",
    [
        {"values": [], "isLastPage": False, "nextPageStart": 0},
        {"values": [], "isLastPage": False},
        {"values": [], "isLastPage": "true"},
        {"values": [], "isLastPage": False, "nextPageStart": True},
    ],
)
def test_repository_changes_rejects_bad_page_cursor(server, payload):
    httpd, url = server
    reply(httpd, 200, {"start": 0, "size": 0, **payload})
    with pytest.raises(AtlaWireError):
        bitbucket.get_repository_changes(
            url, "AB", "repo", "825966b0", token=TOKEN, allow_http_loopback=True
        )
    assert len(httpd.calls) == 1


COMMENT = {
    "id": 4,
    "version": 0,
    "text": "Please add tests.",
    "author": {
        "name": "jcitizen",
        "emailAddress": "jane@example.invalid",
        "displayName": "Jane Citizen",
    },
    "createdDate": 1527228363421,
    "comments": [{"id": 5, "text": "A reply."}],
    "permittedOperations": {"editable": True, "deletable": True},
}


# The observed server requires `path` although 5.10 marks it optional; the
# function sends it verbatim when given and lets the server reject its absence.
def test_list_commit_comments_path_query_projection_and_raw(server):
    httpd, url = server
    reply(httpd, 200, page([COMMENT], True))
    reply(httpd, 200, page([COMMENT], True))
    reply(httpd, 200, page([COMMENT], True))

    expected = [
        {
            "id": 4,
            "author": "jcitizen",
            "text": "Please add tests.",
            "createdDate": 1527228363421,
        }
    ]
    assert (
        bitbucket.list_commit_comments(
            url,
            "AB",
            "repo",
            "abcdef1",
            token=TOKEN,
            path="src/App.java",
            allow_http_loopback=True,
        )
        == expected
    )
    # No client-side path is invented when the caller passes none.
    assert (
        bitbucket.list_commit_comments(
            url, "AB", "repo", "abcdef1", token=TOKEN, allow_http_loopback=True
        )
        == expected
    )
    assert bitbucket.list_commit_comments(
        url,
        "AB",
        "repo",
        "abcdef1",
        token=TOKEN,
        raw=True,
        allow_http_loopback=True,
    ) == [COMMENT]
    assert_calls(
        httpd,
        "/rest/api/1.0/projects/AB/repos/repo/commits/abcdef1/comments",
        [
            {"path": ["src/App.java"], "start": ["0"], "limit": ["100"]},
            {"start": ["0"], "limit": ["100"]},
            {"start": ["0"], "limit": ["100"]},
        ],
    )


# The single-comment read must not accept a foreign object: the returned id
# has to equal the requested one before any projection is returned.
def test_get_commit_comment_projection_raw_and_identity_guard(server):
    httpd, url = server
    reply(httpd, 200, COMMENT)
    reply(httpd, 200, COMMENT)
    reply(httpd, 200, {**COMMENT, "id": 5})

    assert bitbucket.get_commit_comment(
        url, "AB", "repo", "abcdef1", 4, token=TOKEN, allow_http_loopback=True
    ) == {
        "id": 4,
        "author": "jcitizen",
        "text": "Please add tests.",
        "createdDate": 1527228363421,
    }
    assert (
        bitbucket.get_commit_comment(
            url,
            "AB",
            "repo",
            "abcdef1",
            4,
            token=TOKEN,
            raw=True,
            allow_http_loopback=True,
        )
        == COMMENT
    )
    with pytest.raises(AtlaWireError):
        bitbucket.get_commit_comment(
            url, "AB", "repo", "abcdef1", 4, token=TOKEN, allow_http_loopback=True
        )
    assert_calls(
        httpd,
        "/rest/api/1.0/projects/AB/repos/repo/commits/abcdef1/comments/4",
        [{}, {}, {}],
    )


USER = {
    "name": "jcitizen",
    "emailAddress": "jane@example.invalid",
    "id": 101,
    "displayName": "Jane Citizen",
    "active": True,
    "slug": "jcitizen",
    "type": "NORMAL",
    "links": {"self": [{"href": "http://example.invalid/users/jcitizen"}]},
}


# Live 5.10 returns users (no role); a participant wrapper keeps its role.
def test_list_repository_participants_role_is_optional(server):
    httpd, url = server
    reply(httpd, 200, page([USER], False, 21))
    reply(httpd, 200, page([{**USER, "name": "harry"}], True))
    reply(httpd, 200, page([{"user": USER, "role": "REVIEWER"}], True))
    reply(httpd, 200, page([USER], True))

    assert bitbucket.list_repository_participants(
        url, "AB", "repo", token=TOKEN, allow_http_loopback=True
    ) == [
        {"name": "jcitizen", "displayName": "Jane Citizen", "role": None},
        {"name": "harry", "displayName": "Jane Citizen", "role": None},
    ]
    assert bitbucket.list_repository_participants(
        url, "AB", "repo", token=TOKEN, allow_http_loopback=True
    ) == [{"name": "jcitizen", "displayName": "Jane Citizen", "role": "REVIEWER"}]
    assert bitbucket.list_repository_participants(
        url, "AB", "repo", token=TOKEN, raw=True, allow_http_loopback=True
    ) == [USER]
    assert_calls(
        httpd,
        "/rest/api/1.0/projects/AB/repos/repo/participants",
        [
            {"start": ["0"], "limit": ["100"]},
            {"start": ["21"], "limit": ["100"]},
            {"start": ["0"], "limit": ["100"]},
            {"start": ["0"], "limit": ["100"]},
        ],
    )


LINKED = {
    "slug": "fork-one",
    "id": 9,
    "name": "fork",
    "state": "AVAILABLE",
    "project": {"key": "~JDOE", "id": 2, "name": "John Doe", "type": "PERSONAL"},
    "links": {"self": [{"href": "http://example.invalid/fork"}]},
}


# Forks and related repositories share the documented repository row and the
# same flat projection (project is a key, not a nested object).
@pytest.mark.parametrize(
    ("function", "suffix"),
    [
        (bitbucket.list_repository_forks, "/rest/api/1.0/projects/AB/repos/repo/forks"),
        (
            bitbucket.get_related_repositories,
            "/rest/api/1.0/projects/AB/repos/repo/related",
        ),
    ],
)
def test_repository_links_flat_projection(server, function, suffix):
    httpd, url = server
    reply(httpd, 200, page([LINKED], False, 11))
    reply(httpd, 200, page([{**LINKED, "slug": "fork-two"}], True))
    reply(httpd, 200, page([LINKED], True))

    assert function(url, "AB", "repo", token=TOKEN, allow_http_loopback=True) == [
        {"slug": "fork-one", "project": "~JDOE", "state": "AVAILABLE"},
        {"slug": "fork-two", "project": "~JDOE", "state": "AVAILABLE"},
    ]
    assert function(
        url, "AB", "repo", token=TOKEN, raw=True, allow_http_loopback=True
    ) == [LINKED]
    assert_calls(
        httpd,
        suffix,
        [
            {"start": ["0"], "limit": ["100"]},
            {"start": ["11"], "limit": ["100"]},
            {"start": ["0"], "limit": ["100"]},
        ],
    )


def extras_calls(url):
    return [
        (
            lambda: bitbucket.get_project(
                url, "AB", token=TOKEN, allow_http_loopback=True
            ),
            "/rest/api/1.0/projects/AB",
            {},
        ),
        (
            lambda: bitbucket.get_repository(
                url, "AB", "repo", token=TOKEN, allow_http_loopback=True
            ),
            "/rest/api/1.0/projects/AB/repos/repo",
            {},
        ),
        (
            lambda: bitbucket.get_default_branch(
                url, "AB", "repo", token=TOKEN, allow_http_loopback=True
            ),
            "/rest/api/1.0/projects/AB/repos/repo/branches/default",
            {},
        ),
        (
            lambda: bitbucket.get_repository_changes(
                url, "AB", "repo", "abcdef1", token=TOKEN, allow_http_loopback=True
            ),
            "/rest/api/1.0/projects/AB/repos/repo/changes",
            {"until": ["abcdef1"], "start": ["0"], "limit": ["100"]},
        ),
        (
            lambda: bitbucket.list_commit_comments(
                url,
                "AB",
                "repo",
                "abcdef1",
                token=TOKEN,
                path="src/App.java",
                allow_http_loopback=True,
            ),
            "/rest/api/1.0/projects/AB/repos/repo/commits/abcdef1/comments",
            {"path": ["src/App.java"], "start": ["0"], "limit": ["100"]},
        ),
        (
            lambda: bitbucket.get_commit_comment(
                url, "AB", "repo", "abcdef1", 4, token=TOKEN, allow_http_loopback=True
            ),
            "/rest/api/1.0/projects/AB/repos/repo/commits/abcdef1/comments/4",
            {},
        ),
        (
            lambda: bitbucket.list_repository_participants(
                url, "AB", "repo", token=TOKEN, allow_http_loopback=True
            ),
            "/rest/api/1.0/projects/AB/repos/repo/participants",
            {"start": ["0"], "limit": ["100"]},
        ),
        (
            lambda: bitbucket.list_repository_forks(
                url, "AB", "repo", token=TOKEN, allow_http_loopback=True
            ),
            "/rest/api/1.0/projects/AB/repos/repo/forks",
            {"start": ["0"], "limit": ["100"]},
        ),
        (
            lambda: bitbucket.get_related_repositories(
                url, "AB", "repo", token=TOKEN, allow_http_loopback=True
            ),
            "/rest/api/1.0/projects/AB/repos/repo/related",
            {"start": ["0"], "limit": ["100"]},
        ),
    ]


# Every read surfaces a sanitized HTTP error: the status/category survive, the
# private response body and the bearer token never appear in the diagnostic.
def test_not_found_is_sanitized_for_every_function(server):
    httpd, url = server
    for call, path, query in extras_calls(url):
        httpd.responses = [(404, {"errors": [{"message": BODY + TOKEN}]})]
        httpd.calls = []
        with pytest.raises(AtlaWireError) as caught:
            call()
        error = caught.value
        assert (error.category, error.http_status) == ("http", 404)
        diagnostic = "".join(traceback.format_exception(error))
        assert BODY not in diagnostic and TOKEN not in diagnostic
        assert_calls(httpd, path, [query])


@pytest.mark.parametrize(
    "call",
    [
        lambda url: bitbucket.get_project(url, "AB/CD", token=TOKEN),
        lambda url: bitbucket.get_repository(url, "AB", "..", token=TOKEN),
        lambda url: bitbucket.get_default_branch(url, "~", "repo", token=TOKEN),
        lambda url: bitbucket.get_repository_changes(
            url, "AB", "repo", "", token=TOKEN
        ),
        lambda url: bitbucket.get_repository_changes(
            url, "AB", "repo", "abcdef1", token=TOKEN, limit=0
        ),
        lambda url: bitbucket.list_commit_comments(
            url, "AB", "repo", "not-a-commit", token=TOKEN
        ),
        lambda url: bitbucket.list_commit_comments(
            url, "AB", "repo", "abcdef1", token=TOKEN, path="../secret"
        ),
        lambda url: bitbucket.get_commit_comment(
            url, "AB", "repo", "abcdef1", True, token=TOKEN
        ),
        lambda url: bitbucket.get_commit_comment(
            url, "AB", "repo", "abcdef1", 0, token=TOKEN
        ),
        lambda url: bitbucket.list_repository_participants(
            url, "AB", "repo", token=TOKEN, max_pages=0
        ),
        lambda url: bitbucket.list_repository_forks(
            url, "AB", "repo", token=TOKEN, max_pages=1001
        ),
    ],
)
def test_invalid_input_is_rejected_before_any_request(server, call):
    httpd, url = server
    with pytest.raises(AtlaWireError):
        call(url)
    assert httpd.calls == []
