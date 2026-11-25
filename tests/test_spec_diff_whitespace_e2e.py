"""End-to-end contracts for the diff whitespace mode.

Every case goes through the public library or the real CLI against a loopback
HTTP server: no monkeypatching and no mocked transport. Bitbucket 5.10
documents ``ignore-all``; its deployment accepted ``ignore-trailing`` and
``ignore-none`` in the live read-only run, so all three are supported, default
to ``ignore-all``, and are validated before any request.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest
from click.testing import CliRunner

from atlawire import bitbucket
from atlawire.cli import cli
from atlawire.http import AtlaWireError

TOKEN = "synthetic-whitespace-token"
ROOT = "/rest/api/1.0/projects/PROJ/repos/repo"
PR_PATH = ROOT + "/pull-requests/7"
SHA = "a" * 40
DIFF = {"truncated": False, "diffs": [{"source": "a", "destination": "a", "hunks": []}]}


class _State:
    def __init__(self) -> None:
        self.routes: dict[str, object] = {}
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


def _query(state: _State, index: int = -1) -> dict[str, list[str]]:
    return state.calls[index][1]


def test_pull_request_diff_ignores_whitespace_by_default(server):
    # Why: ignore-all is the documented value and the historical default, so an
    # unchanged caller must keep sending exactly that.
    state, base = server
    state.routes[PR_PATH + "/diff"] = DIFF
    result = bitbucket.get_pull_request_diff(
        base, "PROJ/repo", 7, token=TOKEN, allow_http_loopback=True
    )
    assert result == DIFF
    assert _query(state) == {
        "contextLines": ["3"],
        "whitespace": ["ignore-all"],
        "withComments": ["false"],
    }


def test_pull_request_diff_can_show_whitespace_only_changes(server):
    # Why: ignore-none is the mode that keeps whitespace-only hunks; it is sent
    # verbatim because the deployment accepts the documented flag family.
    state, base = server
    state.routes[PR_PATH + "/diff"] = DIFF
    bitbucket.get_pull_request_diff(
        base,
        "PROJ/repo",
        7,
        token=TOKEN,
        whitespace="ignore-none",
        allow_http_loopback=True,
    )
    assert _query(state) == {
        "contextLines": ["3"],
        "whitespace": ["ignore-none"],
        "withComments": ["false"],
    }


@pytest.mark.parametrize("mode", ["ignore-all", "ignore-trailing", "ignore-none"])
def test_every_supported_whitespace_mode_is_sent_verbatim(server, mode):
    state, base = server
    state.routes[PR_PATH + "/diff"] = DIFF
    bitbucket.get_pull_request_diff(
        base,
        "PROJ/repo",
        7,
        token=TOKEN,
        whitespace=mode,
        allow_http_loopback=True,
    )
    assert _query(state)["whitespace"] == [mode]


def test_unknown_whitespace_mode_fails_before_any_request(server):
    state, base = server
    state.routes[PR_PATH + "/diff"] = DIFF
    with pytest.raises(AtlaWireError):
        bitbucket.get_pull_request_diff(
            base,
            "PROJ/repo",
            7,
            token=TOKEN,
            whitespace="ignore-some",
            allow_http_loopback=True,
        )
    assert state.calls == []


def test_batch_pull_request_diffs_share_the_whitespace_choice(server):
    state, base = server
    state.routes[PR_PATH + "/diff/first.txt"] = DIFF
    state.routes[PR_PATH + "/diff/second.txt"] = DIFF
    values = bitbucket.get_pull_request_diffs(
        base,
        "PROJ/repo",
        7,
        paths=["first.txt", "second.txt"],
        token=TOKEN,
        whitespace="ignore-none",
        allow_http_loopback=True,
    )
    assert values == [DIFF, DIFF]
    assert [call[0] for call in state.calls] == [
        PR_PATH + "/diff/first.txt",
        PR_PATH + "/diff/second.txt",
    ]
    for index in (0, 1):
        assert _query(state, index) == {
            "contextLines": ["3"],
            "whitespace": ["ignore-none"],
            "withComments": ["false"],
        }


def test_commit_diff_honours_the_whitespace_choice(server):
    state, base = server
    state.routes[ROOT + f"/commits/{SHA}/diff"] = DIFF
    value = bitbucket.get_commit_diff(
        base,
        "PROJ/repo",
        SHA,
        token=TOKEN,
        whitespace="ignore-none",
        allow_http_loopback=True,
    )
    assert value == DIFF
    assert _query(state) == {
        "contextLines": ["3"],
        "whitespace": ["ignore-none"],
        "withComments": ["false"],
    }


def test_cli_pr_diff_sends_the_selected_whitespace_mode(server):
    state, base = server
    state.routes[PR_PATH + "/diff"] = DIFF
    result = CliRunner().invoke(
        cli,
        [
            "pr",
            "PROJ/repo",
            "7",
            "diff",
            "--whitespace",
            "ignore-none",
            "--base-url",
            base,
            "--token-from-env",
            "--allow-http-loopback",
        ],
        env={
            "ATLAWIRE_BITBUCKET_URL": base,
            "ATLAWIRE_BITBUCKET_TOKEN": TOKEN,
        },
    )
    assert result.exit_code == 0, result.output
    assert _query(state) == {
        "contextLines": ["3"],
        "whitespace": ["ignore-none"],
        "withComments": ["false"],
    }


def test_cli_commit_diff_defaults_to_ignoring_whitespace(server):
    state, base = server
    state.routes[ROOT + f"/commits/{SHA}/diff"] = DIFF
    result = CliRunner().invoke(
        cli,
        [
            "commit-diff",
            "PROJ/repo",
            SHA,
            "--base-url",
            base,
            "--token-from-env",
            "--allow-http-loopback",
        ],
        env={
            "ATLAWIRE_BITBUCKET_URL": base,
            "ATLAWIRE_BITBUCKET_TOKEN": TOKEN,
        },
    )
    assert result.exit_code == 0, result.output
    assert _query(state)["whitespace"] == ["ignore-all"]
