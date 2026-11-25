"""E2E contracts for the client complaints of 2026-11-25.

Every case drives the public surface against a loopback HTTP server or a real
CLI invocation: no monkeypatched transport. Each test names the complaint it
closes, so a regression points at the reported symptom.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest
from click.testing import CliRunner

from atlawire import bitbucket, jira
from atlawire.cli import cli
from atlawire.http import AtlaWireError

TOKEN = "synthetic-complaint-token"
BB_ROOT = "/rest/api/1.0/projects/PROJ/repos/repo"
PR_PATH = BB_ROOT + "/pull-requests/7"
SHA = "a" * 40
DIFF = {"truncated": False, "diffs": [{"source": "a", "destination": "a", "hunks": []}]}


class _State:
    def __init__(self) -> None:
        self.routes: dict[str, object] = {}
        self.statuses: dict[str, int] = {}
        self.calls: list[tuple[str, dict[str, list[str]]]] = []


@pytest.fixture
def server():
    state = _State()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def do_GET(self):
            parsed = urlsplit(self.path)
            state.calls.append(
                (parsed.path, parse_qs(parsed.query, keep_blank_values=True))
            )
            status = state.statuses.get(parsed.path, 200)
            value = state.routes.get(parsed.path)
            if value is None:
                self.send_error(404)
                return
            body = json.dumps(value).encode("utf-8")
            self.send_response(status)
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


def _invoke(argv, base):
    return CliRunner().invoke(
        cli,
        [*argv, "--base-url", base, "--token-from-env", "--allow-http-loopback"],
        env={
            "ATLAWIRE_BITBUCKET_URL": base,
            "ATLAWIRE_BITBUCKET_TOKEN": TOKEN,
            "ATLAWIRE_JIRA_URL": base,
            "ATLAWIRE_JIRA_TOKEN": TOKEN,
        },
    )


# C1: one call, three files, request order preserved.
def test_c1_batch_diff_reads_several_files_in_one_call(server):
    state, base = server
    for name in ("one.txt", "two.txt", "three.txt"):
        state.routes[f"{PR_PATH}/diff/{name}"] = DIFF

    values = bitbucket.get_pull_request_diffs(
        base,
        "PROJ/repo",
        7,
        token=TOKEN,
        paths=["one.txt", "two.txt", "three.txt"],
        allow_http_loopback=True,
    )

    assert len(values) == 3
    assert [call[0] for call in state.calls] == [
        f"{PR_PATH}/diff/one.txt",
        f"{PR_PATH}/diff/two.txt",
        f"{PR_PATH}/diff/three.txt",
    ]


def test_c1_batch_diff_text_uses_one_header_for_the_whole_batch(server):
    state, base = server
    for name in ("one.txt", "two.txt"):
        state.routes[f"{PR_PATH}/diff/{name}"] = DIFF

    text = bitbucket.get_pull_request_diffs_text(
        base,
        "PROJ/repo",
        7,
        token=TOKEN,
        paths=["one.txt", "two.txt"],
        whitespace="ignore-none",
        allow_http_loopback=True,
    )

    assert text.count("# Bitbucket PR diff review") == 1
    assert "whitespace=ignore-none" in text
    assert len(state.calls) == 2


def test_c1_cli_repeated_paths_use_the_batch_reader(server):
    state, base = server
    for name in ("one.txt", "two.txt"):
        state.routes[f"{PR_PATH}/diff/{name}"] = DIFF

    result = _invoke(
        ["pr", "PROJ/repo", "7", "diff", "one.txt", "two.txt", "--json"], base
    )

    assert result.exit_code == 0, result.output
    assert len(json.loads(result.stdout)) == 2
    assert len(state.calls) == 2


def test_c1_several_paths_are_rejected_outside_diff_action(server):
    state, base = server
    state.routes[PR_PATH] = {"id": 7}

    result = _invoke(["pr", "PROJ/repo", "7", "files", "a.txt", "b.txt"], base)

    assert result.exit_code == 2
    assert state.calls == []


# C2: the server's own explanation reaches the caller, bounded and redacted.
def test_c2_rejected_request_carries_the_server_message(server):
    state, base = server
    state.routes["/rest/api/2/search"] = {
        "errorMessages": ["Field 'nosuchfield' does not exist."],
        "errors": {},
    }
    state.statuses["/rest/api/2/search"] = 400

    with pytest.raises(AtlaWireError) as caught:
        jira.search_issues(
            base,
            "nosuchfield = 1",
            token=TOKEN,
            limit=1,
            allow_http_loopback=True,
        )

    assert caught.value.http_status == 400
    assert "Field 'nosuchfield' does not exist." in str(caught.value.detail)


def test_c2_field_errors_are_reported_with_their_field_name(server):
    state, base = server
    state.routes["/rest/api/2/search"] = {
        "errorMessages": [],
        "errors": {"jql": "The value is invalid."},
    }
    state.statuses["/rest/api/2/search"] = 400

    with pytest.raises(AtlaWireError) as caught:
        jira.search_issues(base, "bad", token=TOKEN, limit=1, allow_http_loopback=True)

    assert caught.value.detail == "jql: The value is invalid."


def test_c2_a_message_echoing_the_token_is_dropped_entirely(server):
    state, base = server
    state.routes["/rest/api/2/search"] = {
        "errorMessages": [f"Rejected credential {TOKEN}"],
        "errors": {},
    }
    state.statuses["/rest/api/2/search"] = 400

    with pytest.raises(AtlaWireError) as caught:
        jira.search_issues(base, "x", token=TOKEN, limit=1, allow_http_loopback=True)

    assert TOKEN not in str(caught.value)
    assert caught.value.detail is None
    assert str(caught.value) == "HTTP 400: request failed."


def test_c2_long_messages_are_bounded(server):
    state, base = server
    state.routes["/rest/api/2/search"] = {"errorMessages": ["x" * 5000], "errors": {}}
    state.statuses["/rest/api/2/search"] = 400

    with pytest.raises(AtlaWireError) as caught:
        jira.search_issues(base, "x", token=TOKEN, limit=1, allow_http_loopback=True)

    assert len(str(caught.value.detail)) <= 400


# C3: a commit row exposes the documented `id` next to the legacy `hash`.
def test_c3_commit_row_exposes_id_and_hash_with_one_value(server):
    state, base = server
    state.routes[BB_ROOT + "/commits"] = {
        "isLastPage": True,
        "values": [
            {
                "id": SHA,
                "displayId": SHA[:12],
                "message": "m",
                "author": {"name": "alice", "emailAddress": "a@example.invalid"},
                "authorTimestamp": 1700000000000,
            }
        ],
    }

    rows = bitbucket.list_commits(
        base, "PROJ/repo", token=TOKEN, limit=1, allow_http_loopback=True
    )

    assert rows[0]["id"] == SHA
    assert rows[0]["displayId"] == SHA[:12]
    assert rows[0]["hash"] == SHA


# C7: the review header states the real whitespace mode and the truncation fact.
def test_c7_diff_header_states_mode_and_truncation_state(server):
    state, base = server
    state.routes[PR_PATH + "/diff"] = DIFF

    text = bitbucket.get_pull_request_diff_text(
        base,
        "PROJ/repo",
        7,
        token=TOKEN,
        whitespace="ignore-none",
        allow_http_loopback=True,
    )

    header = text.splitlines()[0]
    assert "whitespace=ignore-none" in header
    assert "server-declared truncation: none" in header


def test_c7_a_declared_truncation_still_raises(server):
    state, base = server
    state.routes[PR_PATH + "/diff"] = {"truncated": True, "diffs": []}

    with pytest.raises(bitbucket.DeclaredTruncationError):
        bitbucket.get_pull_request_diff(
            base, "PROJ/repo", 7, token=TOKEN, allow_http_loopback=True
        )
