"""Nothing that changes server or user state may leave through any read path.

The registry is the advertised research surface, but a read also reaches the
deployment through `api-get`, `api-request` and the public `request_json`. A
parameter whose documented effect is a change must be refused at every one of
them, not only at the registry: Jira's `updateHistory` adds the retrieved issue
to the current user's issue history, which is an addition, not a read.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from click.testing import CliRunner

from atlawire import jira, operations, request_json
from atlawire.cli import cli
from atlawire.http import AtlaWireError

ROOT = Path(__file__).resolve().parents[1]
QUERY_SURFACE = ROOT / "src" / "atlawire" / "query_params.json"
TOKEN = "synthetic-side-effect-token"


class _State:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.body = b'{"key": "DEMO-1", "fields": {}}'


@pytest.fixture
def server():
    state = _State()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def do_GET(self):
            state.calls.append(self.path)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(state.body)))
            self.end_headers()
            self.wfile.write(state.body)

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


def test_the_generated_surface_never_offers_a_side_effect_parameter():
    document = json.loads(QUERY_SURFACE.read_text(encoding="utf-8"))

    offered = {
        f"{operation_id}:{row['name']}"
        for operation_id, rows in document["operations"].items()
        for row in rows
        if str(row["name"]).lower() == "updatehistory"
    }

    assert offered == set()


def test_read_refuses_the_side_effect_parameter_before_any_request(server):
    state, base = server

    with pytest.raises(AtlaWireError) as caught:
        operations.read_operation(
            "jira.issue.issueidorkey",
            base,
            token=TOKEN,
            arguments={"issueIdOrKey": "DEMO-1"},
            query={"updateHistory": "true"},
            allow_http_loopback=True,
        )

    assert caught.value.category == "validation"
    assert state.calls == []


def test_api_get_refuses_the_side_effect_parameter_before_any_request(server):
    state, base = server

    result = CliRunner().invoke(
        cli,
        [
            "api-get",
            "jira",
            "/rest/api/2/issue/DEMO-1",
            "--params",
            '{"updateHistory": "true"}',
            "--base-url",
            base,
            "--token-from-env",
            "--allow-http-loopback",
        ],
        env={"ATLAWIRE_JIRA_URL": base, "ATLAWIRE_JIRA_TOKEN": TOKEN},
    )

    assert result.exit_code == 1
    assert state.calls == []
    assert "updateHistory" in result.stdout


def test_public_request_json_refuses_the_side_effect_parameter(server):
    state, base = server

    with pytest.raises(AtlaWireError) as caught:
        request_json(
            "jira",
            base,
            "/rest/api/2/issue/DEMO-1",
            method="GET",
            token=TOKEN,
            params={"updateHistory": "true"},
            allow_http_loopback=True,
        )

    assert caught.value.category == "validation"
    assert state.calls == []


def test_the_parameter_name_is_matched_case_insensitively(server):
    """A server treats the name case-insensitively; the guard must too."""
    state, base = server

    with pytest.raises(AtlaWireError):
        request_json(
            "jira",
            base,
            "/rest/api/2/issue/DEMO-1",
            method="GET",
            token=TOKEN,
            params={"UPDATEHISTORY": "true"},
            allow_http_loopback=True,
        )

    assert state.calls == []


def test_an_unrelated_parameter_still_reaches_the_server(server):
    """The guard is a narrow deny-list, not a filter over every parameter."""
    state, base = server

    request_json(
        "jira",
        base,
        "/rest/api/2/issue/DEMO-1",
        method="GET",
        token=TOKEN,
        params={"expand": "renderedFields"},
        allow_http_loopback=True,
    )

    assert len(state.calls) == 1


def test_the_typed_issue_reader_no_longer_changes_view_history(server):
    """`get_issue` must not be able to add the issue to the user's history."""
    state, base = server

    jira.get_issue(base, "DEMO-1", token=TOKEN, allow_http_loopback=True)

    assert "updateHistory" not in state.calls[0]
    with pytest.raises(TypeError):
        jira.get_issue(  # type: ignore[call-arg]
            base,
            "DEMO-1",
            token=TOKEN,
            update_history=True,
            allow_http_loopback=True,
        )


def test_the_cli_no_longer_offers_the_history_flag():
    result = CliRunner().invoke(cli, ["issue", "--help"])

    assert result.exit_code == 0
    assert "--update-history" not in result.stdout
