"""Black-box contracts for the last closed parameter gaps.

A loopback server answers queued JSON documents and records every request, so
these tests pin the exact wire contract of the parameters added to close the
matrix gaps: ``search_issues(fields=...)``,
``list_pull_requests(role=/participant=...)``, ``get_page(expand=...)``, the
``search_cql_with_metadata`` rows/truncated/total/next object, and the CLI
options that expose them. Every test that targets new behavior fails on the
code before the change; the unchanged-default tests are the compatibility
guard.
"""

import json
import threading
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest
from click.testing import CliRunner

from atlawire import bitbucket, confluence, jira
from atlawire.cli import cli
from atlawire.http import AtlaWireError

TOKEN = "synthetic-closed-gap-token"
JQL = "project = SPEC ORDER BY updated DESC"
REPO = "PRJ/widgets"
AUSERNAME = "ada"
CQL = "type=page"

JIRA_SEARCH = "/rest/api/2/search"
BITBUCKET_DASHBOARD = "/rest/api/1.0/dashboard/pull-requests"
BITBUCKET_PULL_REQUESTS = "/rest/api/1.0/projects/PRJ/repos/widgets/pull-requests"
CONFLUENCE_SEARCH = "/rest/api/search"
CONFLUENCE_PAGE = "/rest/api/content/123"
CONFLUENCE_CHILDREN = "/rest/api/content/123/child/page"
PROJECTION_FIELDS = "summary,status,priority,issuetype,assignee,updated"
PAGE_EXPAND = "body.storage,version,space,ancestors"


class _Server(ThreadingHTTPServer):
    """Loopback server with a queue of responses and a request log."""

    daemon_threads = True

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _Handler)
        self.calls: list[tuple[str, str, dict[str, list[str]], str | None]] = []
        self.responses: deque[dict[str, object]] = deque()


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def log_message(self, *args: object) -> None:
        pass

    def do_GET(self) -> None:
        server = self.server
        assert isinstance(server, _Server)
        target = urlsplit(self.path)
        server.calls.append(
            (
                self.command,
                target.path,
                parse_qs(target.query, keep_blank_values=True),
                self.headers.get("Authorization"),
            )
        )
        item = (
            server.responses.popleft()
            if server.responses
            else {"status": 500, "json": {"message": "no queued response"}}
        )
        data = json.dumps(item.get("json", {})).encode()
        self.send_response(int(item.get("status", 200)))
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        headers = item.get("headers", {})
        if isinstance(headers, dict):
            for name, value in headers.items():
                self.send_header(str(name), str(value))
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture
def server():
    httpd = _Server()
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd, f"http://127.0.0.1:{httpd.server_port}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def _queue(httpd: _Server, document: object, headers: dict[str, str] | None = None) -> None:
    item: dict[str, object] = {"status": 200, "json": document}
    if headers is not None:
        item["headers"] = headers
    httpd.responses.append(item)


def _only_call(httpd: _Server):
    assert len(httpd.calls) == 1
    call = httpd.calls[0]
    assert (call[0], call[1], call[3]) == ("GET", call[1], "Bearer " + TOKEN)
    return call


# --- Jira: search_issues(fields=...) --------------------------------------


def _issue(number: int) -> dict[str, object]:
    return {
        "key": f"SPEC-{number}",
        "fields": {
            "summary": f"issue {number}",
            "status": {"name": "Open"},
            "updated": "2026-01-02T10:00:00.000+0300",
        },
    }


def _search_page(issues: list[dict[str, object]], total: int, max_results: int = 5):
    return {
        "startAt": 0,
        "maxResults": max_results,
        "total": total,
        "issues": issues,
    }


def test_search_issues_fields_string_is_sent_verbatim(server) -> None:
    """A string ``fields`` reaches the query unchanged instead of the default."""
    httpd, base = server
    _queue(httpd, _search_page([_issue(1)], total=1))

    rows = jira.search_issues(
        base,
        JQL,
        token=TOKEN,
        fields="summary,status",
        limit=5,
        allow_http_loopback=True,
    )

    assert [row["key"] for row in rows] == ["SPEC-1"]
    assert rows[0]["status"] == "Open"
    call = _only_call(httpd)
    assert call[1] == JIRA_SEARCH
    assert call[2] == {
        "jql": [JQL],
        "fields": ["summary,status"],
        "startAt": ["0"],
        "maxResults": ["5"],
    }


def test_search_issues_fields_list_is_joined_in_given_order(server) -> None:
    """A list ``fields`` is comma-joined in caller order, not sorted."""
    httpd, base = server
    _queue(httpd, _search_page([_issue(1)], total=1))

    jira.search_issues(
        base,
        JQL,
        token=TOKEN,
        fields=["status", "summary"],
        limit=5,
        allow_http_loopback=True,
    )

    assert _only_call(httpd)[2]["fields"] == ["status,summary"]


def test_search_issues_default_fields_are_unchanged(server) -> None:
    """Omitting ``fields`` keeps the historical projection list."""
    httpd, base = server
    _queue(httpd, _search_page([_issue(1)], total=1))

    jira.search_issues(base, JQL, token=TOKEN, limit=5, allow_http_loopback=True)

    assert _only_call(httpd)[2]["fields"] == [PROJECTION_FIELDS]


@pytest.mark.parametrize("fields", ["", "   ", [], [""], ["summary", " "]])
def test_search_issues_rejects_empty_fields_without_a_request(server, fields) -> None:
    """An empty selection fails before any session or request exists."""
    httpd, base = server

    with pytest.raises(AtlaWireError):
        jira.search_issues(
            base,
            JQL,
            token=TOKEN,
            fields=fields,
            limit=5,
            allow_http_loopback=True,
        )

    assert httpd.calls == []


def test_search_issues_with_metadata_accepts_fields(server) -> None:
    """The truncation-aware variant validates and forwards ``fields`` too."""
    httpd, base = server
    _queue(httpd, _search_page([_issue(1)], total=7))

    result = jira.search_issues_with_metadata(
        base,
        JQL,
        token=TOKEN,
        fields=["summary"],
        limit=1,
        allow_http_loopback=True,
    )

    assert result["rows"][0]["key"] == "SPEC-1"
    assert result["truncated"] is True
    assert result["total"] == 7
    assert _only_call(httpd)[2]["fields"] == ["summary"]


# --- Bitbucket: list_pull_requests(role=..., participant=...) --------------


def _pull_request_row(number: int) -> dict[str, object]:
    return {
        "id": number,
        "title": f"pull request {number}",
        "state": "OPEN",
        "author": {"user": {"name": AUSERNAME}},
        "fromRef": {"displayId": "feature"},
        "toRef": {"displayId": "master"},
        "updatedDate": 1767225600000,
    }


def _pull_request_page(values: list[dict[str, object]]):
    return {"values": values, "isLastPage": True}


def test_list_pull_requests_role_and_participant_send_username_and_role(server) -> None:
    """An explicit participant fills username.N and the role fills role.N."""
    httpd, base = server
    _queue(httpd, _pull_request_page([_pull_request_row(190)]))

    rows = bitbucket.list_pull_requests(
        base,
        REPO,
        token=TOKEN,
        role="REVIEWER",
        participant=AUSERNAME,
        limit=5,
        allow_http_loopback=True,
    )

    assert [row["id"] for row in rows] == [190]
    call = _only_call(httpd)
    assert call[1] == BITBUCKET_PULL_REQUESTS
    assert call[2] == {
        "state": ["OPEN"],
        "username.1": [AUSERNAME],
        "role.1": ["REVIEWER"],
        "start": ["0"],
        "limit": ["5"],
    }


def test_list_pull_requests_role_alone_resolves_authenticated_username(server) -> None:
    """A role without participant costs one identity read, never a bare role.1."""
    httpd, base = server
    _queue(
        httpd,
        {"values": [], "isLastPage": True},
        headers={"X-AUSERNAME": AUSERNAME},
    )
    _queue(httpd, _pull_request_page([_pull_request_row(190)]))

    rows = bitbucket.list_pull_requests(
        base,
        REPO,
        token=TOKEN,
        role="REVIEWER",
        limit=5,
        allow_http_loopback=True,
    )

    assert [row["id"] for row in rows] == [190]
    assert len(httpd.calls) == 2
    identity, listing = httpd.calls
    assert identity[1] == BITBUCKET_DASHBOARD
    assert identity[2] == {"state": ["OPEN"], "limit": ["1"]}
    assert listing[1] == BITBUCKET_PULL_REQUESTS
    assert listing[2] == {
        "state": ["OPEN"],
        "username.1": [AUSERNAME],
        "role.1": ["REVIEWER"],
        "start": ["0"],
        "limit": ["5"],
    }
    for call in httpd.calls:
        assert call[3] == "Bearer " + TOKEN


def test_list_pull_requests_missing_username_header_fails_closed(server) -> None:
    """Without X-AUSERNAME the role filter fails instead of listing everything."""
    httpd, base = server
    _queue(httpd, {"values": [], "isLastPage": True})

    with pytest.raises(AtlaWireError) as error:
        bitbucket.list_pull_requests(
            base,
            REPO,
            token=TOKEN,
            role="REVIEWER",
            limit=5,
            allow_http_loopback=True,
        )

    assert "participant" in str(error.value)
    assert len(httpd.calls) == 1
    assert httpd.calls[0][1] == BITBUCKET_DASHBOARD


def test_list_pull_requests_default_filter_is_unchanged(server) -> None:
    """Without the new parameters no participant filter is sent."""
    httpd, base = server
    _queue(httpd, _pull_request_page([_pull_request_row(190)]))

    bitbucket.list_pull_requests(
        base, REPO, token=TOKEN, limit=5, allow_http_loopback=True
    )

    assert _only_call(httpd)[2] == {
        "state": ["OPEN"],
        "start": ["0"],
        "limit": ["5"],
    }


def test_list_pull_requests_rejects_an_invalid_role_before_a_request(server) -> None:
    """The closed role set is enforced before any session is opened."""
    httpd, base = server

    with pytest.raises(AtlaWireError):
        bitbucket.list_pull_requests(
            base,
            REPO,
            token=TOKEN,
            role="OWNER",
            participant=AUSERNAME,
            allow_http_loopback=True,
        )

    assert httpd.calls == []


def test_list_pull_requests_rejects_author_with_role(server) -> None:
    """The historical author filter cannot be mixed with the new pair."""
    httpd, base = server

    with pytest.raises(AtlaWireError):
        bitbucket.list_pull_requests(
            base,
            REPO,
            token=TOKEN,
            author=AUSERNAME,
            role="REVIEWER",
            allow_http_loopback=True,
        )

    assert httpd.calls == []


# --- Confluence: get_page(expand=...) -------------------------------------


def _page_document() -> dict[str, object]:
    return {
        "id": "123",
        "type": "page",
        "title": "T",
        "version": {"number": 4},
        "body": {"storage": {"value": "<p>x</p>"}},
    }


def test_get_page_expand_is_sent_and_the_response_is_returned(server) -> None:
    """A custom ``expand`` replaces the fixed list and may omit the body."""
    httpd, base = server
    version_only = {
        "id": "123",
        "type": "page",
        "title": "T",
        "version": {"number": 4},
    }
    _queue(httpd, version_only)

    page = confluence.get_page(
        base, "123", token=TOKEN, expand="version", allow_http_loopback=True
    )

    assert page == version_only
    call = _only_call(httpd)
    assert call[1] == CONFLUENCE_PAGE
    assert call[2] == {"expand": ["version"]}


def test_get_page_default_expand_is_unchanged(server) -> None:
    """Omitting ``expand`` keeps the fixed body/version/space/ancestors list."""
    httpd, base = server
    _queue(httpd, _page_document())

    confluence.get_page(base, "123", token=TOKEN, allow_http_loopback=True)

    assert _only_call(httpd)[2] == {"expand": [PAGE_EXPAND]}


@pytest.mark.parametrize("expand", ["", "   "])
def test_get_page_rejects_an_empty_expand_without_a_request(server, expand) -> None:
    """An empty expansion is rejected before any session or request exists."""
    httpd, base = server

    with pytest.raises(AtlaWireError):
        confluence.get_page(
            base, "123", token=TOKEN, expand=expand, allow_http_loopback=True
        )

    assert httpd.calls == []


def test_get_page_default_expand_still_requires_the_storage_body(server) -> None:
    """The default expansion keeps validating body.storage.value as before."""
    httpd, base = server
    _queue(httpd, {"id": "123", "type": "page", "title": "T"})

    with pytest.raises(AtlaWireError):
        confluence.get_page(base, "123", token=TOKEN, allow_http_loopback=True)

    assert len(httpd.calls) == 1


# --- Confluence: search_cql_with_metadata ---------------------------------


def _cql_row(number: int) -> dict[str, object]:
    return {
        "content": {
            "id": str(number),
            "title": f"page {number}",
            "type": "page",
            "space": {"key": "SPEC"},
        },
        "url": f"/spaces/SPEC/pages/{number}",
    }


def _cql_page(
    rows: list[dict[str, object]],
    *,
    total: int,
    next_link: str | None = None,
):
    document: dict[str, object] = {
        "results": rows,
        "start": 0,
        "size": len(rows),
        "totalSize": total,
        "_links": {},
    }
    if next_link is not None:
        document["_links"] = {"next": next_link}
    return document


def test_search_cql_with_metadata_reports_truncation_total_and_next(server) -> None:
    """A capped search exposes the server's total and unfollowed next link."""
    httpd, base = server
    _queue(httpd, _cql_page([_cql_row(1)], total=3, next_link="?start=1&limit=1"))

    result = confluence.search_cql_with_metadata(
        base, CQL, token=TOKEN, limit=1, allow_http_loopback=True
    )

    assert set(result) == {"rows", "truncated", "total", "next"}
    assert result["rows"] == [
        {
            "id": "1",
            "space": "SPEC",
            "type": "page",
            "title": "page 1",
            "url": "/spaces/SPEC/pages/1",
        }
    ]
    assert result["truncated"] is True
    assert result["total"] == 3
    assert result["next"] == "?start=1&limit=1"
    call = _only_call(httpd)
    assert call[1] == CONFLUENCE_SEARCH
    assert call[2] == {"cql": [CQL], "start": ["0"], "limit": ["1"]}


def test_search_cql_with_metadata_is_complete_at_total_size(server) -> None:
    """Reaching totalSize means not truncated and no continuation is invented."""
    httpd, base = server
    _queue(httpd, _cql_page([_cql_row(1)], total=1))

    result = confluence.search_cql_with_metadata(
        base, CQL, token=TOKEN, limit=1, allow_http_loopback=True
    )

    assert result["truncated"] is False
    assert result["total"] == 1
    assert result["next"] is None


def test_search_cql_keeps_the_plain_list_and_query(server) -> None:
    """The legacy function still returns a bare list with the same request."""
    httpd, base = server
    _queue(httpd, _cql_page([_cql_row(1)], total=1))

    rows = confluence.search_cql(
        base, CQL, token=TOKEN, limit=1, allow_http_loopback=True
    )

    assert rows == [
        {
            "id": "1",
            "space": "SPEC",
            "type": "page",
            "title": "page 1",
            "url": "/spaces/SPEC/pages/1",
        }
    ]
    assert _only_call(httpd)[2] == {"cql": [CQL], "start": ["0"], "limit": ["1"]}


def test_search_cql_with_metadata_zero_limit_sends_nothing(server) -> None:
    """A zero limit returns the empty metadata object without a request."""
    httpd, base = server

    result = confluence.search_cql_with_metadata(
        base, CQL, token=TOKEN, limit=0, allow_http_loopback=True
    )

    assert result == {"rows": [], "truncated": False, "total": None, "next": None}
    assert httpd.calls == []


# --- CLI wiring -----------------------------------------------------------


def _invoke(httpd: _Server, argv: tuple[str, ...], product: str):
    base = f"http://127.0.0.1:{httpd.server_port}"
    url_name, token_name = {
        "jira": ("ATLAWIRE_JIRA_URL", "ATLAWIRE_JIRA_TOKEN"),
        "confluence": ("ATLAWIRE_CONFLUENCE_URL", "ATLAWIRE_CONFLUENCE_TOKEN"),
        "bitbucket": ("ATLAWIRE_BITBUCKET_URL", "ATLAWIRE_BITBUCKET_TOKEN"),
    }[product]
    return CliRunner().invoke(
        cli,
        [*argv, "--base-url", base, "--token-from-env", "--allow-http-loopback"],
        env={url_name: base, token_name: TOKEN},
    )


def test_prs_cli_forwards_role_and_resolves_username(server) -> None:
    """``prs --role`` sends the documented username.1 plus role.1 pair."""
    httpd, _ = server
    _queue(
        httpd,
        {"values": [], "isLastPage": True},
        headers={"X-AUSERNAME": AUSERNAME},
    )
    _queue(httpd, _pull_request_page([_pull_request_row(190)]))

    result = _invoke(httpd, ("prs", REPO, "--role", "REVIEWER", "--json"), "bitbucket")

    assert result.exit_code == 0, result.stderr
    assert [row["id"] for row in json.loads(result.stdout)] == [190]
    assert [call[1] for call in httpd.calls] == [
        BITBUCKET_DASHBOARD,
        BITBUCKET_PULL_REQUESTS,
    ]
    assert httpd.calls[1][2] == {
        "state": ["OPEN"],
        "username.1": [AUSERNAME],
        "role.1": ["REVIEWER"],
        "start": ["0"],
        "limit": ["25"],
    }


def test_cql_cli_prints_the_truncation_object(server) -> None:
    """A capped ``cql`` prints the metadata object instead of a bare array."""
    httpd, _ = server
    _queue(httpd, _cql_page([_cql_row(1)], total=3))

    result = _invoke(
        httpd, ("cql", CQL, "--limit", "1", "--json"), "confluence"
    )

    assert result.exit_code == 0, result.stderr
    printed = json.loads(result.stdout)
    assert printed["truncated"] is True
    assert printed["total"] == 3
    assert [row["id"] for row in printed["rows"]] == ["1"]


def test_children_cli_prints_the_truncation_object(server) -> None:
    """A capped ``children`` listing prints rows, truncated, and total."""
    httpd, _ = server
    _queue(
        httpd,
        {
            "results": [{"id": "9", "title": "Child", "version": {"number": 4}}],
            "start": 0,
            "size": 1,
            "totalSize": 3,
        },
    )

    result = _invoke(
        httpd, ("children", "123", "--limit", "1", "--json"), "confluence"
    )

    assert result.exit_code == 0, result.stderr
    assert json.loads(result.stdout) == {
        "rows": [{"id": "9", "title": "Child", "version": 4}],
        "truncated": True,
        "total": 3,
    }
    assert httpd.calls[0][1] == CONFLUENCE_CHILDREN


def test_new_options_are_described_in_help() -> None:
    """The new flags and their 5.10 constraint are visible in --help."""
    runner = CliRunner()

    jql_help = runner.invoke(cli, ["jql", "--help"])
    prs_help = runner.invoke(cli, ["prs", "--help"])
    page_help = runner.invoke(cli, ["page", "--help"])
    cql_help = runner.invoke(cli, ["cql", "--help"])

    assert jql_help.exit_code == 0
    assert "Comma-separated Jira fields" in jql_help.output
    assert prs_help.exit_code == 0
    assert "--role" in prs_help.output
    assert "--participant" in prs_help.output
    assert "X-AUSERNAME" in prs_help.output
    assert page_help.exit_code == 0
    assert "--expand" in page_help.output
    assert cql_help.exit_code == 0
    assert "truncated" in cql_help.output
