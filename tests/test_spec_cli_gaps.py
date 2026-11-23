"""Black-box contracts for the CLI gaps found by the parameter matrix and E2E.

Every case drives the real click command through a loopback server bound to
``127.0.0.1:0`` and asserts the recorded request, the exit status and the
printed document. Nothing is monkeypatched and no host other than 127.0.0.1 is
reached.

The contracts covered here:

* ``jql --fields/--expand``, ``issue --expand``, ``cql --expand``, ``page
  --expand`` and ``issue-comments --limit`` reach the request or the printed
  rows, and a truncated comment thread is reported, without changing the
  default invocation.
* ``pr-files``, ``pr-comments``, ``grep`` and ``scan`` execute the same
  callback and print the same result as their canonical commands, and stay
  visible in ``--help`` and ``--catalog``.
* ``last-modified`` help documents that the default branch is resolved instead
  of the removed "at is not sent" claim.
* ``scan-extension`` without a project reports a partial result with an
  explicit incompleteness flag and repository counters instead of failing with
  no rows when the page budget is reached.
"""

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import cast
from urllib.parse import parse_qs, urlsplit

import pytest
from click.testing import CliRunner

from atlawire.cli import cli
from atlawire.http import AtlaWireError
from atlawire.repo_scan import scan_repository_extensions

TOKEN = "synthetic-cli-gap-token"
SHA = "a" * 40
JIRA_SEARCH = "/rest/api/2/search"
JIRA_ISSUE = "/rest/api/2/issue/DEMO-42"
JIRA_COMMENTS = f"{JIRA_ISSUE}/comment"
CONFLUENCE_SEARCH = "/rest/api/search"
CONFLUENCE_PAGE = "/rest/api/content/123"
BITBUCKET_REPOS = "/rest/api/1.0/projects/DEMO/repos"
BITBUCKET_FILES = f"{BITBUCKET_REPOS}/a/files"
BITBUCKET_PULL_REQUEST = "/rest/api/1.0/projects/PRJ/repos/widgets/pull-requests/7"
BITBUCKET_GREP_FILES = "/rest/api/1.0/projects/PRJ/repos/widgets/files"
BITBUCKET_DEFAULT_BRANCH = "/rest/api/1.0/projects/PRJ/repos/widgets/branches/default"
PROJECTION_FIELDS = "summary,status,priority,issuetype,assignee,updated"
PAGE_EXPAND = "body.storage,version,space,ancestors"
PAGE_LIMIT_MARKER = "page limit"

_ENVIRONMENT = {
    "jira": ("ATLAWIRE_JIRA_URL", "ATLAWIRE_JIRA_TOKEN"),
    "confluence": ("ATLAWIRE_CONFLUENCE_URL", "ATLAWIRE_CONFLUENCE_TOKEN"),
    "bitbucket": ("ATLAWIRE_BITBUCKET_URL", "ATLAWIRE_BITBUCKET_TOKEN"),
}

Call = tuple[str, str, dict[str, list[str]], str | None]


class _Server(ThreadingHTTPServer):
    """Loopback server answering configured exact paths and recording calls."""

    daemon_threads = True
    calls: list[Call]
    routes: dict[str, object]

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _Handler)
        self.calls = []
        self.routes = {}


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
        document = server.routes.get(target.path)
        status = 200 if document is not None else 404
        body = json.dumps(
            {"errorMessages": ["not found"]} if document is None else document
        )
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body.encode())))
        self.end_headers()
        self.wfile.write(body.encode())


@pytest.fixture
def server():
    """Serve one fresh loopback port with a per-test route table."""
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
    """Run one command with environment-only auth against the loopback server."""
    base = f"http://127.0.0.1:{httpd.server_port}"
    url_name, token_name = _ENVIRONMENT[product]
    return CliRunner().invoke(
        cli,
        [*argv, "--base-url", base, "--token-from-env", "--allow-http-loopback"],
        env={url_name: base, token_name: TOKEN},
    )


def _only_call(httpd: _Server) -> Call:
    """Return the single recorded request of a one-request command."""
    assert len(httpd.calls) == 1
    return httpd.calls[0]


def test_jql_fields_and_expand_change_the_search_query(server) -> None:
    """Both flags switch to one raw search request with the exact fields/expand."""
    envelope = {
        "startAt": 0,
        "maxResults": 2,
        "total": 1,
        "issues": [{"key": "DEMO-1", "fields": {"summary": "s"}}],
    }
    server.routes = {JIRA_SEARCH: envelope}

    result = _invoke(
        server,
        (
            "jql",
            "project = DEMO",
            "--fields",
            "summary,status",
            "--expand",
            "names",
            "--limit",
            "2",
        ),
        "jira",
    )

    assert result.exit_code == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == envelope
    call = _only_call(server)
    assert call[0] == "GET" and call[1] == JIRA_SEARCH
    assert call[2] == {
        "jql": ["project = DEMO"],
        "fields": ["summary,status"],
        "startAt": ["0"],
        "maxResults": ["2"],
        "expand": ["names"],
    }
    assert call[3] == f"Bearer {TOKEN}"
    assert TOKEN not in result.stdout

    server.calls.clear()
    default = _invoke(server, ("jql", "project = DEMO", "--limit", "2"), "jira")

    assert default.exit_code == 0, default.stderr
    assert default.stdout.startswith("# 1 row(s)")
    assert _only_call(server)[2] == {
        "jql": ["project = DEMO"],
        "fields": [PROJECTION_FIELDS],
        "startAt": ["0"],
        "maxResults": ["2"],
    }


def test_issue_expand_is_forwarded_and_the_default_kept(server) -> None:
    """--expand replaces the renderedFields default and is sent verbatim."""
    document = {"key": "DEMO-42", "fields": {"summary": "s"}, "changelog": {}}
    server.routes = {JIRA_ISSUE: document}

    expanded = _invoke(server, ("issue", "DEMO-42", "--expand", "changelog"), "jira")

    assert expanded.exit_code == 0, expanded.stderr
    assert json.loads(expanded.stdout) == document
    assert _only_call(server)[2] == {"expand": ["changelog"]}

    server.calls.clear()
    default = _invoke(server, ("issue", "DEMO-42"), "jira")

    assert default.exit_code == 0, default.stderr
    assert _only_call(server)[2] == {"expand": ["renderedFields"]}


def test_cql_expand_prints_the_raw_search_page(server) -> None:
    """--expand sends one raw search page instead of the projected rows."""
    document = {"results": [], "start": 0, "limit": 2, "size": 0, "totalSize": 0}
    server.routes = {CONFLUENCE_SEARCH: document}

    expanded = _invoke(
        server,
        ("cql", "type=page", "--expand", "body.view", "--limit", "2"),
        "confluence",
    )

    assert expanded.exit_code == 0, expanded.stderr
    assert json.loads(expanded.stdout) == document
    assert _only_call(server)[2] == {
        "cql": ["type=page"],
        "expand": ["body.view"],
        "start": ["0"],
        "limit": ["2"],
    }

    server.calls.clear()
    default = _invoke(server, ("cql", "type=page", "--limit", "2"), "confluence")

    assert default.exit_code == 0, default.stderr
    assert default.stdout.startswith("# 0 row(s)")
    assert _only_call(server)[2] == {
        "cql": ["type=page"],
        "start": ["0"],
        "limit": ["2"],
    }


def test_page_expand_prints_the_raw_page_and_rejects_row_views(server) -> None:
    """--expand sends its exact value and cannot mix with Markdown or storage."""
    document = {
        "id": "123",
        "type": "page",
        "title": "T",
        "body": {"storage": {"value": "<p>x</p>"}},
        "version": {"number": 2},
    }
    server.routes = {CONFLUENCE_PAGE: document}

    expanded = _invoke(server, ("page", "123", "--expand", "body.view"), "confluence")

    assert expanded.exit_code == 0, expanded.stderr
    assert json.loads(expanded.stdout) == document
    assert _only_call(server)[2] == {"expand": ["body.view"]}

    server.calls.clear()
    default = _invoke(server, ("page", "123"), "confluence")

    assert default.exit_code == 0, default.stderr
    assert json.loads(default.stdout) == document
    assert _only_call(server)[2] == {"expand": [PAGE_EXPAND]}

    server.calls.clear()
    conflict = _invoke(
        server, ("page", "123", "--expand", "version", "--markdown"), "confluence"
    )

    assert conflict.exit_code == 2
    assert conflict.stdout == ""
    assert "--expand" in conflict.stderr
    assert server.calls == []


def _comment_page(count: int, max_results: int) -> dict[str, object]:
    """Build one comments page with ``count`` rows and the echoed page size."""
    return {
        "startAt": 0,
        "maxResults": max_results,
        "total": count,
        "comments": [
            {
                "id": str(number),
                "author": {"name": "ada"},
                "body": f"comment {number}",
                "created": "2026-11-01T10:00:00.000+0300",
            }
            for number in range(1, count + 1)
        ],
    }


def test_issue_comments_limit_reaches_the_request_and_marks_truncation(server) -> None:
    """--limit becomes maxResults, and a shorter page is visibly incomplete."""
    server.routes = {JIRA_COMMENTS: _comment_page(2, 2) | {"total": 10}}

    limited = _invoke(server, ("issue-comments", "DEMO-42", "--limit", "2"), "jira")

    assert limited.exit_code == 0, limited.stderr
    printed = json.loads(limited.stdout)
    assert printed["truncated"] is True
    assert printed["total"] == 10
    assert [row["id"] for row in printed["rows"]] == ["1", "2"]
    assert "# showing 2 of 10 comment(s)" in limited.stderr
    assert _only_call(server)[2] == {"startAt": ["0"], "maxResults": ["2"]}

    server.calls.clear()
    envelope = _invoke(
        server, ("issue-comments", "DEMO-42", "--limit", "2", "--json"), "jira"
    )

    assert envelope.exit_code == 0, envelope.stderr
    assert envelope.stderr == ""
    assert json.loads(envelope.stdout) == printed
    assert _only_call(server)[2] == {"startAt": ["0"], "maxResults": ["2"]}


def test_issue_comments_complete_reads_keep_the_default_array(server) -> None:
    """A limit above the thread size and the default print every row as before."""
    server.routes = {JIRA_COMMENTS: _comment_page(10, 50)}

    capped = _invoke(server, ("issue-comments", "DEMO-42", "--limit", "100"), "jira")

    assert capped.exit_code == 0, capped.stderr
    assert capped.stderr == ""
    rows = json.loads(capped.stdout)
    assert isinstance(rows, list)
    assert [row["id"] for row in rows] == [str(number) for number in range(1, 11)]
    assert _only_call(server)[2] == {"startAt": ["0"], "maxResults": ["50"]}

    server.calls.clear()
    default = _invoke(server, ("issue-comments", "DEMO-42"), "jira")

    assert default.exit_code == 0, default.stderr
    assert default.stderr == ""
    assert json.loads(default.stdout) == rows
    assert _only_call(server)[2] == {"startAt": ["0"], "maxResults": ["50"]}

    server.calls.clear()
    metadata = _invoke(server, ("issue-comments", "DEMO-42", "--json"), "jira")

    assert metadata.exit_code == 0, metadata.stderr
    assert metadata.stdout != default.stdout
    assert json.loads(metadata.stdout) == {
        "rows": rows,
        "truncated": False,
        "total": 10,
    }
    assert _only_call(server)[2] == {"startAt": ["0"], "maxResults": ["50"]}


def test_last_modified_help_documents_default_branch_resolution() -> None:
    """Help states that the default branch is resolved, not that at is omitted."""
    result = CliRunner().invoke(cli, ["last-modified", "--help"])

    assert result.exit_code == 0, result.stderr
    output = result.output
    assert "default branch" in output
    assert "is not sent" not in output
    assert "leave the at parameter out" not in output


def _assert_same_result(
    httpd: _Server,
    product: str,
    canonical: tuple[str, ...],
    alias: tuple[str, ...],
) -> str:
    """Run both spellings and require identical stdout and identical requests."""
    first = _invoke(httpd, canonical, product)
    assert first.exit_code == 0, first.stderr
    assert first.stderr == ""
    assert first.stdout != ""
    first_calls = list(httpd.calls)

    httpd.calls.clear()
    second = _invoke(httpd, alias, product)

    assert second.exit_code == 0, second.stderr
    assert second.stderr == ""
    assert second.stdout == first.stdout
    assert httpd.calls == first_calls
    assert TOKEN not in first.stdout + second.stdout
    return first.stdout


def test_pr_files_alias_matches_the_canonical_action(server) -> None:
    """pr-files prints the same changed files as pr REPO ID files."""
    changes = {
        "isLastPage": True,
        "limit": 100,
        "size": 1,
        "start": 0,
        "values": [{"path": "src/a.py", "type": "MODIFY", "nodeType": "MODIFY"}],
    }
    server.routes = {f"{BITBUCKET_PULL_REQUEST}/changes": changes}

    printed = _assert_same_result(
        server,
        "bitbucket",
        ("pr", "PRJ/widgets", "7", "files", "--json"),
        ("pr-files", "PRJ/widgets", "7", "--json"),
    )

    assert json.loads(printed) == [
        {"path": "src/a.py", "type": "MODIFY", "node": "MODIFY"}
    ]


def test_pr_comments_alias_matches_the_canonical_action(server) -> None:
    """pr-comments prints the same comment activities as pr REPO ID comments."""
    activities = {
        "isLastPage": True,
        "values": [
            {
                "comment": {
                    "id": 11,
                    "text": "hi",
                    "author": {"name": "ada"},
                    "createdDate": 1700000000000,
                }
            }
        ],
    }
    server.routes = {f"{BITBUCKET_PULL_REQUEST}/activities": activities}

    printed = _assert_same_result(
        server,
        "bitbucket",
        ("pr", "PRJ/widgets", "7", "comments", "--json"),
        ("pr-comments", "PRJ/widgets", "7", "--json"),
    )

    rows = json.loads(printed)
    assert len(rows) == 1 and rows[0]["id"] == 11


def test_grep_alias_matches_grep_repo(server) -> None:
    """grep prints the same path listing as grep-repo."""
    server.routes = {
        BITBUCKET_DEFAULT_BRANCH: {
            "id": "refs/heads/main",
            "displayId": "main",
            "latestCommit": SHA,
            "isDefault": True,
        },
        BITBUCKET_GREP_FILES: {
            "isLastPage": True,
            "values": ["src/a.py", "docs/b.md"],
        },
    }

    printed = _assert_same_result(
        server,
        "bitbucket",
        ("grep-repo", "PRJ/widgets", "--path", "src", "--json"),
        ("grep", "PRJ/widgets", "--path", "src", "--json"),
    )

    assert json.loads(printed)["files"] == ["src/a.py"]


def test_scan_alias_matches_scan_extension(server) -> None:
    """scan prints the same complete inventory array as scan-extension."""
    server.routes = {
        BITBUCKET_REPOS: {"isLastPage": True, "values": [{"slug": "a"}]},
        BITBUCKET_FILES: {"isLastPage": True, "values": ["x.py", "y.java"]},
    }

    printed = _assert_same_result(
        server,
        "bitbucket",
        ("scan-extension", "--ext", ".py", "--project", "DEMO", "--json"),
        ("scan", "--ext", ".py", "--project", "DEMO", "--json"),
    )

    assert json.loads(printed) == [
        {
            "project": "DEMO",
            "repository": "a",
            "files": 2,
            "matched": 1,
            "sample": ["x.py"],
        }
    ]


def test_aliases_are_visible_in_catalog_and_help() -> None:
    """Every alias is an ordinary visible command, not a hidden redirect."""
    names = ("grep", "scan", "pr-files", "pr-comments")

    catalog = CliRunner().invoke(cli, ["--catalog"])
    assert catalog.exit_code == 0, catalog.stderr
    commands = json.loads(catalog.stdout)["commands"]
    for name in names:
        assert name in commands
        assert commands[name]["name"] == name
    assert commands["pr-files"]["help"].endswith("(alias of pr REPO ID files).")

    help_result = CliRunner().invoke(cli, ["--help"])
    assert help_result.exit_code == 0, help_result.stderr
    for name in names:
        assert re.search(rf"^  {re.escape(name)} ", help_result.output, re.MULTILINE), (
            name
        )


def test_scan_extension_without_project_reports_a_partial_result(server) -> None:
    """A page-budget cut keeps the rows already read and names the shortfall."""
    server.routes = {
        "/rest/api/1.0/projects": {
            "isLastPage": True,
            "values": [{"key": "DEMO", "name": "Demo"}],
        },
        BITBUCKET_REPOS: {"isLastPage": True, "values": [{"slug": "a"}, {"slug": "b"}]},
        BITBUCKET_FILES: {"isLastPage": True, "values": ["x.py"]},
        f"{BITBUCKET_REPOS}/b/files": {
            "isLastPage": False,
            "values": ["y.py"],
            "nextPageStart": 100,
        },
    }

    result = _invoke(
        server,
        ("scan-extension", "--ext", ".py", "--max-pages", "1", "--workers", "1"),
        "bitbucket",
    )

    assert result.exit_code == 0, result.stderr
    assert result.stderr == ""
    report = json.loads(result.stdout)
    assert report["complete"] is False
    assert report["repositories_scanned"] == 1
    assert report["repositories_total"] == 2
    assert PAGE_LIMIT_MARKER in report["reason"]
    assert report["rows"] == [
        {
            "project": "DEMO",
            "repository": "a",
            "files": 1,
            "matched": 1,
            "sample": ["x.py"],
        }
    ]
    assert [call[1] for call in server.calls] == [
        "/rest/api/1.0/projects",
        BITBUCKET_REPOS,
        BITBUCKET_FILES,
        f"{BITBUCKET_REPOS}/b/files",
    ]


def test_scan_extension_enumeration_cut_is_a_partial_result(server) -> None:
    """A cut before repository enumeration still exits 0 with an explicit flag."""
    server.routes = {
        "/rest/api/1.0/projects": {
            "isLastPage": False,
            "values": [{"key": "DEMO", "name": "Demo"}],
            "nextPageStart": 100,
        }
    }

    result = _invoke(
        server,
        ("scan-extension", "--ext", ".py", "--max-pages", "1", "--workers", "1"),
        "bitbucket",
    )

    assert result.exit_code == 0, result.stderr
    assert result.stderr == ""
    report = json.loads(result.stdout)
    assert report["complete"] is False
    assert report["rows"] == []
    assert report["repositories_scanned"] == 0
    assert report["repositories_total"] is None
    assert PAGE_LIMIT_MARKER in report["reason"]
    assert len(server.calls) == 1


def test_scan_repository_extensions_stays_all_or_nothing(server) -> None:
    """The list-returning library entry point still raises on a budget cut."""
    server.routes = {
        "/rest/api/1.0/projects": {
            "isLastPage": False,
            "values": [{"key": "DEMO", "name": "Demo"}],
            "nextPageStart": 100,
        }
    }
    base = f"http://127.0.0.1:{server.server_port}"

    with pytest.raises(AtlaWireError) as error:
        scan_repository_extensions(
            base,
            ".py",
            token=TOKEN,
            max_pages=1,
            allow_http_loopback=True,
        )

    assert PAGE_LIMIT_MARKER in str(error.value)
    assert len(server.calls) == 1
