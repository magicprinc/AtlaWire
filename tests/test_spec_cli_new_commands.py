"""Black-box contracts for the new Jira, Bitbucket and Confluence read commands.

Every test drives the real CLI through click's runner against a loopback server
that records each request. Assertions come only from the exit status, the
captured streams and that request log, so no test monkeypatches a guard or
reaches a host other than 127.0.0.1.

One table describes all nineteen commands: the exact request the command must
send, the server document, the projection ``--json`` must print and the raw
document ``--raw`` must print. The fixtures deliberately carry unknown server
fields and nested objects, so a command that prints the raw document instead of
the projection fails, and the recorded path/query makes a wrong route fail.
"""

import json
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import cast
from urllib.parse import parse_qs, urlsplit

import pytest
from click.testing import CliRunner

from atlawire.cli import cli

TOKEN = "synthetic-cli-wiring-token"
BASE_URL_ENV = "ATLAWIRE_{product}_URL"
TOKEN_ENV = "ATLAWIRE_{product}_TOKEN"
JIRA_ISSUE = "/rest/api/2/issue/DEMO-42"
BITBUCKET_REPO = "/rest/api/1.0/projects/PRJ/repos/widgets"
BITBUCKET_COMMIT = "825966b0"
CONFLUENCE_SPACE = "ARCH"


@dataclass(frozen=True)
class Case:
    """One command with its exact request, server document and projections."""

    argv: tuple[str, ...]
    product: str
    path: str
    query: dict[str, list[str]]
    document: object
    projection: object
    raw_query: dict[str, list[str]] | None = None
    raw_document: object | None = None


VOTES_DOCUMENT = {
    "self": "https://jira.example.invalid/rest/api/2/issue/DEMO-42/votes",
    "voters": [
        {
            "self": "https://jira.example.invalid/rest/api/2/user?name=ada",
            "name": "ada",
            "displayName": "Ada Lovelace",
            "emailAddress": "ada@example.invalid",
        }
    ],
    "hasVoted": False,
    "watchCount": 7,
}

WATCHERS_DOCUMENT = {
    "self": "https://jira.example.invalid/rest/api/2/issue/DEMO-42/watchers",
    "isWatching": True,
    "watchCount": 3,
    "watchers": [
        {
            "self": "https://jira.example.invalid/rest/api/2/user?name=ada",
            "name": "ada",
            "displayName": "Ada Lovelace",
        }
    ],
}

SUBTASKS_DOCUMENT = [
    {
        "self": "https://jira.example.invalid/rest/api/2/issue/DEMO-43",
        "key": "DEMO-43",
        "fields": {
            "summary": "Sub one",
            "issuetype": {"name": "Sub-task", "subtask": True},
            "status": {"name": "To Do", "id": "1"},
            "unknown": {"nested": True},
        },
    }
]

COMMENT_DOCUMENT = {
    "self": "https://jira.example.invalid/rest/api/2/issue/DEMO-42/comment/10001",
    "id": "10001",
    "author": {"name": "ada", "displayName": "Ada Lovelace"},
    "body": "hello",
    "created": "2026-11-01T10:00:00.000+0300",
    "updated": "2026-11-02T10:00:00.000+0300",
}

WORKLOG_DOCUMENT = {
    "self": "https://jira.example.invalid/rest/api/2/issue/DEMO-42/worklog/20001",
    "id": "20001",
    "author": {"name": "ada"},
    "started": "2026-11-01T09:00:00.000+0300",
    "timeSpentSeconds": 3600,
    "timeSpent": "1h",
    "comment": "work",
}

PROPERTIES_DOCUMENT = {
    "keys": [
        {
            "self": "https://jira.example.invalid/rest/api/2/issue/DEMO-42/properties/demo.flag",
            "key": "demo.flag",
        },
        {
            "self": "https://jira.example.invalid/rest/api/2/issue/DEMO-42/properties/demo.other",
            "key": "demo.other",
        },
    ]
}

PROPERTY_DOCUMENT = {
    "self": "https://jira.example.invalid/rest/api/2/issue/DEMO-42/properties/demo.flag",
    "key": "demo.flag",
    "value": {"enabled": True, "nested": [1, 2]},
}

LINK_DOCUMENT = {
    "self": "https://jira.example.invalid/rest/api/2/issueLink/55",
    "id": "55",
    "type": {
        "id": "1",
        "name": "Blocks",
        "inward": "is blocked by",
        "outward": "blocks",
    },
    "inwardIssue": {"key": "DEMO-1", "fields": {"summary": "First"}},
    "outwardIssue": {"key": "DEMO-2", "fields": {"summary": "Second"}},
}

PROJECT_DOCUMENT = {
    "key": "PRJ",
    "name": "Project One",
    "description": "demo project",
    "public": False,
    "type": "NORMAL",
    "id": 7,
    "links": {"self": [{"href": "https://bitbucket.example.invalid/projects/PRJ"}]},
}

REPOSITORY_DOCUMENT = {
    "slug": "widgets",
    "name": "Widgets",
    "state": "AVAILABLE",
    "public": True,
    "project": {"key": "PRJ", "name": "Project One"},
    "links": {
        "self": [
            {"href": "https://bitbucket.example.invalid/projects/PRJ/repos/widgets"}
        ]
    },
}

BRANCH_DOCUMENT = {
    "id": "refs/heads/main",
    "displayId": "main",
    "type": "BRANCH",
    "latestCommit": BITBUCKET_COMMIT,
    "latestChangeset": BITBUCKET_COMMIT,
    "isDefault": True,
}

CHANGES_DOCUMENT = {
    "size": 1,
    "start": 0,
    "isLastPage": True,
    "values": [
        {
            "path": "src/app.py",
            "type": "MODIFY",
            "nodeType": BITBUCKET_COMMIT,
            "unknown": {"nested": True},
        }
    ],
}

COMMIT_COMMENTS_DOCUMENT = {
    "isLastPage": True,
    "values": [
        {
            "id": 3,
            "author": {"name": "ada", "displayName": "Ada Lovelace"},
            "text": "first",
            "createdDate": 1700000000000,
            "unknown": {"nested": True},
        }
    ],
}

COMMIT_COMMENT_DOCUMENT = {
    "id": 3,
    "author": {"name": "ada"},
    "text": "first",
    "createdDate": 1700000000000,
    "unknown": {"nested": True},
}

PARTICIPANTS_DOCUMENT = {
    "isLastPage": True,
    "values": [
        {
            "user": {
                "name": "ada",
                "displayName": "Ada Lovelace",
                "emailAddress": "ada@example.invalid",
            },
            "role": "AUTHOR",
            "unknown": {"nested": True},
        }
    ],
}

FORKS_DOCUMENT = {
    "isLastPage": True,
    "values": [
        {
            "slug": "widgets-fork",
            "project": {"key": "FORK", "name": "Fork Project"},
            "state": "AVAILABLE",
            "links": {
                "self": [
                    {
                        "href": "https://bitbucket.example.invalid/projects/FORK/repos/widgets-fork"
                    }
                ]
            },
        }
    ],
}

RELATED_DOCUMENT = {
    "isLastPage": True,
    "values": [
        {
            "slug": "widgets-parent",
            "project": {"key": "PARENT", "name": "Parent Project"},
            "state": "AVAILABLE",
            "unknown": {"nested": True},
        }
    ],
}

SPACE_DOCUMENT = {
    "id": 10,
    "key": CONFLUENCE_SPACE,
    "name": "Architecture",
    "type": "global",
    "status": "current",
    "extra": {"nested": True},
    "_links": {
        "webui": "/display/ARCH",
        "self": "https://confluence.example.invalid/rest/api/space/ARCH",
    },
}

SPACE_CONTENT_DOCUMENT = {
    "page": {
        "start": 0,
        "limit": 100,
        "size": 1,
        "results": [
            {
                "id": "123",
                "type": "page",
                "title": "Home",
                "version": {"number": 5, "when": "2026-11-01T10:00:00.000+0300"},
                "extra": {"nested": True},
                "_links": {"webui": "/display/ARCH/Home"},
            }
        ],
        "_links": {
            "self": "https://confluence.example.invalid/rest/api/space/ARCH/content/page"
        },
    },
    "blogpost": {
        "start": 0,
        "limit": 100,
        "size": 0,
        "results": [],
        "_links": {
            "self": "https://confluence.example.invalid/rest/api/space/ARCH/content/blogpost"
        },
    },
    "_links": {
        "self": "https://confluence.example.invalid/rest/api/space/ARCH/content"
    },
}

CASES = (
    Case(
        argv=("issue-votes", "DEMO-42"),
        product="jira",
        path=f"{JIRA_ISSUE}/votes",
        query={},
        document=VOTES_DOCUMENT,
        projection={
            "voters": [{"name": "ada", "displayName": "Ada Lovelace"}],
            "hasVoted": False,
            "watchCount": 7,
        },
    ),
    Case(
        argv=("issue-watchers", "DEMO-42"),
        product="jira",
        path=f"{JIRA_ISSUE}/watchers",
        query={},
        document=WATCHERS_DOCUMENT,
        projection={
            "watchers": [{"name": "ada", "displayName": "Ada Lovelace"}],
            "watchCount": 3,
            "isWatching": True,
        },
    ),
    Case(
        argv=("issue-subtasks", "DEMO-42"),
        product="jira",
        path=f"{JIRA_ISSUE}/subtask",
        query={},
        document=SUBTASKS_DOCUMENT,
        projection=[
            {
                "key": "DEMO-43",
                "summary": "Sub one",
                "type": "Sub-task",
                "status": "To Do",
            }
        ],
    ),
    Case(
        argv=("issue-comment", "DEMO-42", "10001"),
        product="jira",
        path=f"{JIRA_ISSUE}/comment/10001",
        query={},
        document=COMMENT_DOCUMENT,
        projection={
            "id": "10001",
            "author": "ada",
            "created": "2026-11-01T10:00:00.000+0300",
            "updated": "2026-11-02T10:00:00.000+0300",
            "body": "hello",
        },
    ),
    Case(
        argv=("issue-worklog", "DEMO-42", "20001"),
        product="jira",
        path=f"{JIRA_ISSUE}/worklog/20001",
        query={},
        document=WORKLOG_DOCUMENT,
        projection={
            "id": "20001",
            "author": "ada",
            "started": "2026-11-01T09:00:00.000+0300",
            "seconds": 3600,
            "comment": "work",
        },
    ),
    Case(
        argv=("issue-properties", "DEMO-42"),
        product="jira",
        path=f"{JIRA_ISSUE}/properties",
        query={},
        document=PROPERTIES_DOCUMENT,
        projection={"keys": ["demo.flag", "demo.other"]},
    ),
    Case(
        argv=("issue-property", "DEMO-42", "demo.flag"),
        product="jira",
        path=f"{JIRA_ISSUE}/properties/demo.flag",
        query={},
        document=PROPERTY_DOCUMENT,
        projection={"key": "demo.flag", "value": {"enabled": True, "nested": [1, 2]}},
    ),
    Case(
        argv=("issue-link", "55"),
        product="jira",
        path="/rest/api/2/issueLink/55",
        query={},
        document=LINK_DOCUMENT,
        projection={
            "id": "55",
            "type": "Blocks",
            "inwardIssue": "DEMO-1",
            "outwardIssue": "DEMO-2",
        },
    ),
    Case(
        argv=("project", "PRJ"),
        product="bitbucket",
        path="/rest/api/1.0/projects/PRJ",
        query={},
        document=PROJECT_DOCUMENT,
        projection={
            "key": "PRJ",
            "name": "Project One",
            "description": "demo project",
            "public": False,
            "type": "NORMAL",
        },
    ),
    Case(
        argv=("repository", "PRJ", "widgets"),
        product="bitbucket",
        path=BITBUCKET_REPO,
        query={},
        document=REPOSITORY_DOCUMENT,
        projection={
            "slug": "widgets",
            "name": "Widgets",
            "state": "AVAILABLE",
            "public": True,
            "defaultBranch": None,
        },
    ),
    Case(
        argv=("default-branch", "PRJ", "widgets"),
        product="bitbucket",
        path=f"{BITBUCKET_REPO}/branches/default",
        query={},
        document=BRANCH_DOCUMENT,
        projection={
            "id": "refs/heads/main",
            "displayId": "main",
            "latestCommit": BITBUCKET_COMMIT,
            "isDefault": True,
        },
    ),
    Case(
        argv=("repo-changes", "PRJ", "widgets", "main"),
        product="bitbucket",
        path=f"{BITBUCKET_REPO}/changes",
        query={"until": ["main"], "start": ["0"], "limit": ["100"]},
        document=CHANGES_DOCUMENT,
        raw_document=CHANGES_DOCUMENT["values"],
        projection=[{"path": "src/app.py", "type": "MODIFY", "node": BITBUCKET_COMMIT}],
    ),
    Case(
        argv=("commit-comments", "PRJ", "widgets", BITBUCKET_COMMIT),
        product="bitbucket",
        path=f"{BITBUCKET_REPO}/commits/{BITBUCKET_COMMIT}/comments",
        query={"start": ["0"], "limit": ["100"]},
        document=COMMIT_COMMENTS_DOCUMENT,
        raw_document=COMMIT_COMMENTS_DOCUMENT["values"],
        projection=[
            {"id": 3, "author": "ada", "text": "first", "createdDate": 1700000000000}
        ],
    ),
    Case(
        argv=("commit-comment", "PRJ", "widgets", BITBUCKET_COMMIT, "3"),
        product="bitbucket",
        path=f"{BITBUCKET_REPO}/commits/{BITBUCKET_COMMIT}/comments/3",
        query={},
        document=COMMIT_COMMENT_DOCUMENT,
        projection={
            "id": 3,
            "author": "ada",
            "text": "first",
            "createdDate": 1700000000000,
        },
    ),
    Case(
        argv=("repo-participants", "PRJ", "widgets"),
        product="bitbucket",
        path=f"{BITBUCKET_REPO}/participants",
        query={"start": ["0"], "limit": ["100"]},
        document=PARTICIPANTS_DOCUMENT,
        raw_document=PARTICIPANTS_DOCUMENT["values"],
        projection=[{"name": "ada", "displayName": "Ada Lovelace", "role": "AUTHOR"}],
    ),
    Case(
        argv=("repo-forks", "PRJ", "widgets"),
        product="bitbucket",
        path=f"{BITBUCKET_REPO}/forks",
        query={"start": ["0"], "limit": ["100"]},
        document=FORKS_DOCUMENT,
        raw_document=FORKS_DOCUMENT["values"],
        projection=[{"slug": "widgets-fork", "project": "FORK", "state": "AVAILABLE"}],
    ),
    Case(
        argv=("related-repos", "PRJ", "widgets"),
        product="bitbucket",
        path=f"{BITBUCKET_REPO}/related",
        query={"start": ["0"], "limit": ["100"]},
        document=RELATED_DOCUMENT,
        raw_document=RELATED_DOCUMENT["values"],
        projection=[
            {"slug": "widgets-parent", "project": "PARENT", "state": "AVAILABLE"}
        ],
    ),
    Case(
        argv=("space", CONFLUENCE_SPACE),
        product="confluence",
        path=f"/rest/api/space/{CONFLUENCE_SPACE}",
        query={},
        document=SPACE_DOCUMENT,
        projection={
            "key": CONFLUENCE_SPACE,
            "name": "Architecture",
            "type": "global",
            "status": "current",
            "url": "/display/ARCH",
        },
    ),
    Case(
        argv=("space-content", CONFLUENCE_SPACE),
        product="confluence",
        path=f"/rest/api/space/{CONFLUENCE_SPACE}/content",
        query={"expand": ["version"], "start": ["0"], "limit": ["100"]},
        document=SPACE_CONTENT_DOCUMENT,
        projection={
            "rows": [
                {
                    "id": "123",
                    "title": "Home",
                    "type": "page",
                    "version": 5,
                    "url": "/display/ARCH/Home",
                }
            ],
            "truncated": False,
        },
        raw_query={},
    ),
)


class _Server(ThreadingHTTPServer):
    """Loopback server that answers every route with one configured document."""

    daemon_threads = True
    calls: list[tuple[str, str, dict[str, list[str]], str | None]]

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _Handler)
        self.calls = []
        self.status = 200
        self.document: object = {}


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def log_message(self, format: str, *args: object) -> None:
        pass

    def do_GET(self) -> None:
        server = cast(_Server, self.server)
        target = urlsplit(self.path)
        server.calls.append(
            (
                self.command,
                target.path,
                parse_qs(target.query, keep_blank_values=True),
                self.headers.get("Authorization"),
            )
        )
        body = b"" if server.status == 404 else json.dumps(server.document).encode()
        self.send_response(server.status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)


@pytest.fixture
def server():
    """Serve one configurable document on a fresh loopback port."""
    httpd = _Server()
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


def _invoke(httpd: _Server, argv: tuple[str, ...], product: str):
    """Run one command against the loopback server with environment-only auth."""
    base = f"http://127.0.0.1:{httpd.server_port}"
    upper = product.upper()
    return CliRunner().invoke(
        cli,
        [*argv, "--base-url", base, "--token-from-env", "--allow-http-loopback"],
        env={
            BASE_URL_ENV.format(product=upper): base,
            TOKEN_ENV.format(product=upper): TOKEN,
        },
    )


def _expected_calls(
    path: str, query: dict[str, list[str]]
) -> list[tuple[str, str, dict[str, list[str]], str | None]]:
    """Return the one expected request: GET, exact path and query, bearer auth."""
    return [("GET", path, query, f"Bearer {TOKEN}")]


@pytest.mark.parametrize("case", CASES, ids=[case.argv[0] for case in CASES])
def test_projection_raw_and_missing_resource_contract(server, case: Case) -> None:
    """Each command sends one exact request and prints projection then raw then fails."""
    server.document = case.document

    projected = _invoke(server, (*case.argv, "--json"), case.product)
    assert projected.exit_code == 0, projected.stderr
    assert projected.stderr == ""
    assert json.loads(projected.stdout) == case.projection
    assert server.calls == _expected_calls(case.path, case.query)
    assert TOKEN not in projected.stdout + projected.stderr

    server.calls.clear()
    raw = _invoke(server, (*case.argv, "--raw"), case.product)
    raw_query = case.query if case.raw_query is None else case.raw_query
    assert raw.exit_code == 0, raw.stderr
    assert raw.stderr == ""
    expected_raw = case.document if case.raw_document is None else case.raw_document
    assert json.loads(raw.stdout) == expected_raw
    assert json.loads(raw.stdout) != case.projection
    assert server.calls == _expected_calls(case.path, raw_query)
    assert TOKEN not in raw.stdout + raw.stderr

    server.calls.clear()
    server.status = 404
    missing = _invoke(server, (*case.argv, "--json"), case.product)
    assert missing.exit_code != 0
    assert missing.stdout == ""
    assert "404" in missing.stderr
    assert TOKEN not in missing.stdout + missing.stderr
    assert len(server.calls) == 1
    assert server.calls[0][1] == case.path


def test_default_branch_without_a_branch_prints_null(server) -> None:
    """A documented HTTP 204 becomes null in both output modes, not an error."""
    server.status = 204
    for flag in ("--json", "--raw"):
        server.calls.clear()
        result = _invoke(
            server, ("default-branch", "PRJ", "widgets", flag), "bitbucket"
        )

        assert result.exit_code == 0, result.stderr
        assert json.loads(result.stdout) is None
        assert server.calls == _expected_calls(f"{BITBUCKET_REPO}/branches/default", {})


def test_conflicting_output_flags_fail_before_any_request(server) -> None:
    """Passing both output modes is a usage error with no credential or HTTP use."""
    result = _invoke(server, ("project", "PRJ", "--json", "--raw"), "bitbucket")

    assert result.exit_code == 2
    assert result.stdout == ""
    assert "not both" in result.stderr
    assert server.calls == []


@pytest.mark.parametrize(
    ("argv", "product", "path"),
    [
        (("project", "PRJ"), "bitbucket", "/rest/api/1.0/projects/PRJ"),
        (("issue-votes", "DEMO-42"), "jira", f"{JIRA_ISSUE}/votes"),
    ],
    ids=["bitbucket-project", "jira-votes"],
)
@pytest.mark.parametrize("flag", ["--json", "--raw"], ids=["json", "raw"])
def test_response_echoing_the_token_is_refused(
    server, argv, product, path, flag
) -> None:
    """A server document containing the bearer token never reaches either stream."""
    server.document = {"echo": TOKEN}

    result = _invoke(server, (*argv, flag), product)

    assert result.exit_code != 0
    assert result.stdout == ""
    assert TOKEN not in result.stdout + result.stderr
    assert server.calls == _expected_calls(path, {})


@pytest.mark.parametrize("case", CASES, ids=[case.argv[0] for case in CASES])
def test_help_describes_the_projection_and_raw_output(case: Case) -> None:
    """Every command documents what it returns and both output flags."""
    result = CliRunner().invoke(cli, [case.argv[0], "--help"])

    assert result.exit_code == 0, result.stderr
    assert "--raw" in result.output
    assert "projection" in result.output
    assert case.product in result.output or case.argv[0] in result.output
