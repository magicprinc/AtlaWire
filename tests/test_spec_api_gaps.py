"""Contracts for the one-call helpers, pr_compact, batch diff, and session reuse."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import pytest

from atlawire import bitbucket, confluence, jira, repo_grep
from atlawire.http import AtlaWireError

TOKEN = "synthetic-b3-token"


class _State:
    def __init__(self) -> None:
        self.routes: dict[str, object] = {}
        self.calls: list[str] = []


@pytest.fixture
def server():
    state = _State()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def do_GET(self):
            parsed = urlsplit(self.path)
            state.calls.append(parsed.path)
            value = state.routes.get(parsed.path)
            if value is None:
                self.send_error(404)
                return
            body = json.dumps(value).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield state, f"http://127.0.0.1:{httpd.server_port}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


PAGE = {
    "id": "42",
    "type": "page",
    "title": "Sample page",
    "body": {"storage": {"value": "<p>hello <b>world</b></p>"}},
}

ISSUE = {
    "key": "DEMO-7",
    "fields": {
        "summary": "Sample issue",
        "description": "raw",
        "status": {"name": "Open"},
    },
    "renderedFields": {"description": "<p>rendered text</p>"},
}

PR = {
    "id": 9,
    "title": "Sample PR",
    "state": "OPEN",
    "author": {"user": {"name": "alice"}},
    "fromRef": {"displayId": "feature"},
    "toRef": {"displayId": "main"},
    "createdDate": 1700000000000,
    "updatedDate": 1700000001000,
    "reviewers": [
        {"user": {"name": "bob", "active": True}},
        {"user": {"name": "carol", "active": False}},
        {"user": {"name": "dave"}},
    ],
    "links": {"self": [{"href": "https://x.invalid"}]},
    "permittedOperations": {"merge": True},
}

DIFF = {"truncated": False, "diffs": [{"source": "a", "destination": "a", "hunks": []}]}


def _page_routes(state):
    state.routes["/rest/api/content/42"] = PAGE
    state.routes["/rest/api/2/issue/DEMO-7"] = ISSUE
    state.routes["/rest/api/1.0/projects/PRJ/repos/widgets/pull-requests/9"] = PR


def test_confluence_one_call_helpers_reuse_one_request(server):
    state, base = server
    _page_routes(state)

    storage = confluence.get_page_storage(
        base, "42", token=TOKEN, allow_http_loopback=True
    )
    title = confluence.get_page_title(base, "42", token=TOKEN, allow_http_loopback=True)
    markdown = confluence.get_page_markdown(
        base, "42", token=TOKEN, allow_http_loopback=True
    )

    assert storage == PAGE["body"]["storage"]["value"]
    assert title == "Sample page"
    assert "hello" in markdown
    assert len(state.calls) == 3


def test_jira_issue_url_is_pure_and_keeps_a_context_path():
    assert (
        jira.issue_url("https://jira.example.com/jira", "DEMO-7")
        == "https://jira.example.com/jira/browse/DEMO-7"
    )


def test_jira_issue_markdown_is_one_request(server):
    state, base = server
    _page_routes(state)

    markdown = jira.get_issue_markdown(
        base, "DEMO-7", token=TOKEN, allow_http_loopback=True
    )

    assert "rendered text" in markdown
    assert len(state.calls) == 1


def test_pr_compact_keeps_report_fields_and_drops_service_keys(server):
    state, base = server
    _page_routes(state)

    row = bitbucket.pr_compact(
        base, "PRJ/widgets", 9, token=TOKEN, allow_http_loopback=True
    )

    assert list(row) == [
        "id",
        "title",
        "state",
        "author",
        "from",
        "to",
        "created",
        "updated",
        "reviewers_active",
        "url",
    ]
    assert row["reviewers_active"] == ["bob", "dave"]
    assert row["url"].endswith("/projects/PRJ/repos/widgets/pull-requests/9")
    assert "links" not in row and "permittedOperations" not in row


def _diff_route(state, path):
    state.routes[
        f"/rest/api/1.0/projects/PRJ/repos/widgets/pull-requests/9/diff/{path}"
    ] = DIFF


def test_batch_diff_returns_results_in_request_order(server):
    state, base = server
    _diff_route(state, "src/a.py")
    _diff_route(state, "src/b.py")

    results = bitbucket.get_pull_request_diffs(
        base,
        "PRJ/widgets",
        9,
        token=TOKEN,
        paths=["src/b.py", "src/a.py"],
        allow_http_loopback=True,
    )

    assert [call.rsplit("/", 1)[-1] for call in state.calls] == ["b.py", "a.py"]
    assert results == [DIFF, DIFF]


def test_batch_diff_rejects_duplicates_before_any_request(server):
    state, base = server

    with pytest.raises(AtlaWireError, match="Duplicate"):
        bitbucket.get_pull_request_diffs(
            base,
            "PRJ/widgets",
            9,
            token=TOKEN,
            paths=["src/a.py", "src/a.py"],
            allow_http_loopback=True,
        )

    assert state.calls == []


def test_single_path_diff_still_returns_one_object(server):
    state, base = server
    _diff_route(state, "src/a.py")

    result = bitbucket.get_pull_request_diff(
        base,
        "PRJ/widgets",
        9,
        token=TOKEN,
        path="src/a.py",
        allow_http_loopback=True,
    )

    assert result == DIFF


def test_batch_diff_rejects_an_empty_and_oversized_selection(server):
    state, base = server

    with pytest.raises(AtlaWireError):
        bitbucket.get_pull_request_diffs(
            base, "PRJ/widgets", 9, token=TOKEN, paths=[], allow_http_loopback=True
        )
    with pytest.raises(AtlaWireError):
        bitbucket.get_pull_request_diffs(
            base,
            "PRJ/widgets",
            9,
            token=TOKEN,
            paths=[f"p{index}.py" for index in range(101)],
            allow_http_loopback=True,
        )

    assert state.calls == []


def test_repository_scan_opens_one_session(server, monkeypatch):
    state, base = server
    state.routes["/rest/api/1.0/projects/PRJ/repos/widgets/raw/a.txt"] = None
    counter = {"sessions": 0}
    real = repo_grep.bearer_session

    def counting(token):
        counter["sessions"] += 1
        return real(token)

    monkeypatch.setattr(repo_grep, "bearer_session", counting)
    monkeypatch.setattr(
        repo_grep,
        "_read_repository_file_in_session",
        lambda *args, **kwargs: "x\n",
    )
    monkeypatch.setattr(repo_grep, "_match_line_numbers", lambda *a, **k: [1])

    hits, scanned, status = repo_grep._scan(
        base,
        "PRJ/widgets",
        ["a.txt", "b.txt", "c.txt"],
        token=TOKEN,
        commit="c" * 40,
        pattern="x",
        ignore_case=False,
        limit=10,
        regex_timeout_s=5.0,
        deadline=repo_grep._monotonic() + 60,
        allow_http_loopback=True,
    )

    assert counter["sessions"] == 1
    assert status == "complete"
    assert scanned == 3
    assert len(hits) == 3
