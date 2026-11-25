"""The server reason is a structured field; the message stays sanitized.

Two guarantees are pinned together: a caller can read the documented reason from
``error.detail``, and ``str(error)`` plus any traceback still never carry
response content. The CLI is the one surface that prints the reason, on its own
line, because a terminal is where it is useful.
"""

import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from click.testing import CliRunner

from atlawire import bitbucket, confluence, get_json, jira
from atlawire.cli import cli
from atlawire.http import AtlaWireError

TOKEN = "synthetic-error-detail-token"
SENTINEL = "synthetic-body-sentinel"


class _State:
    def __init__(self) -> None:
        self.body: bytes = b"{}"
        self.status: int = 400


@pytest.fixture
def server():
    state = _State()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def do_GET(self):
            self.send_response(state.status)
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


def _jira_error(state, base, body: bytes) -> AtlaWireError:
    state.body = body
    with pytest.raises(AtlaWireError) as caught:
        jira.search_issues(base, "x", token=TOKEN, limit=1, allow_http_loopback=True)
    return caught.value


def _bb_error(state, base) -> AtlaWireError:
    with pytest.raises(AtlaWireError) as caught:
        bitbucket.list_projects(base, token=TOKEN, limit=1, allow_http_loopback=True)
    return caught.value


def test_jira_error_messages_and_field_errors(server):
    state, base = server
    error = _jira_error(
        state, base, b'{"errorMessages":["Top level."],"errors":{"jql":"Bad value."}}'
    )

    assert error.detail is not None
    assert "Top level." in error.detail
    assert "jql: Bad value." in error.detail


def test_bitbucket_errors_array_with_context(server):
    state, base = server
    state.body = (
        b'{"errors":[{"context":"limit","message":"Must be a positive integer.",'
        b'"exceptionName":null}]}'
    )

    assert _bb_error(state, base).detail == "limit: Must be a positive integer."


def test_bitbucket_errors_array_without_context(server):
    state, base = server
    state.body = b'{"errors":[{"context":null,"message":"Repository not found."}]}'

    assert _bb_error(state, base).detail == "Repository not found."


def test_confluence_message_and_reason(server):
    state, base = server
    state.body = b'{"statusCode":400,"message":"Bad Request","reason":"Unknown macro."}'

    with pytest.raises(AtlaWireError) as caught:
        confluence.list_spaces(base, token=TOKEN, limit=1, allow_http_loopback=True)

    assert caught.value.detail == "Bad Request Unknown macro."


def test_repeated_sentences_are_reported_once(server):
    state, base = server
    error = _jira_error(state, base, b'{"message":"Same text.","reason":"Same text."}')

    assert error.detail == "Same text."


def test_an_unrelated_body_field_is_never_quoted(server):
    """Only documented error fields count; a stray field is not a message."""
    state, base = server
    body = b'{"message":"Documented reason.","token":"' + SENTINEL.encode() + b'"}'

    error = _jira_error(state, base, body)

    assert error.detail == "Documented reason."
    assert SENTINEL not in str(error)
    assert SENTINEL not in "".join(traceback.format_exception(error))


def test_a_non_document_body_yields_no_detail(server):
    state, base = server
    error = _jira_error(state, base, b"<html>gateway page</html>")

    assert error.detail is None
    assert str(error) == "HTTP 400: request failed."


def test_a_500_keeps_no_detail(server):
    """Only statuses about the caller's own input explain it."""
    state, base = server
    state.status = 500

    error = _jira_error(state, base, b'{"message":"Internal boom"}')

    assert error.detail is None
    assert str(error) == "HTTP 500: request failed."


def test_a_detail_echoing_the_token_is_dropped(server):
    state, base = server
    error = _jira_error(
        state, base, b'{"message":"Rejected credential ' + TOKEN.encode() + b'"}'
    )

    assert error.detail is None


def test_adapter_layer_records_the_same_reason(server):
    state, base = server
    state.body = (
        b'{"errors":[{"context":"limit","message":"Must be numeric.",'
        b'"exceptionName":null}]}'
    )

    with pytest.raises(AtlaWireError) as adapter:
        get_json(
            "bitbucket",
            base,
            "/rest/api/1.0/projects",
            token=TOKEN,
            params={"limit": "abc"},
            allow_http_loopback=True,
        )
    with pytest.raises(AtlaWireError) as typed:
        jira.search_issues(base, "x", token=TOKEN, limit=1, allow_http_loopback=True)

    assert adapter.value.detail == typed.value.detail == "limit: Must be numeric."


def test_cli_prints_the_reason_on_its_own_line(server):
    state, base = server
    state.body = (
        b'{"errors":[{"context":"limit","message":"Must be numeric.",'
        b'"exceptionName":null}]}'
    )

    result = CliRunner().invoke(
        cli,
        ["projects", "--limit", "5", "--token-from-env", "--allow-http-loopback"],
        env={
            "ATLAWIRE_BITBUCKET_URL": base,
            "ATLAWIRE_BITBUCKET_TOKEN": TOKEN,
        },
    )

    assert result.exit_code == 1
    assert "HTTP 400: request failed." in result.stderr
    assert "limit: Must be numeric." in result.stderr
    assert TOKEN not in result.stderr


def test_cli_omits_the_second_line_when_no_reason_exists(server):
    state, base = server
    state.body = b"<html>gateway</html>"

    result = CliRunner().invoke(
        cli,
        ["projects", "--limit", "5", "--token-from-env", "--allow-http-loopback"],
        env={
            "ATLAWIRE_BITBUCKET_URL": base,
            "ATLAWIRE_BITBUCKET_TOKEN": TOKEN,
        },
    )

    assert result.exit_code == 1
    assert result.stderr.strip().endswith("HTTP 400: request failed.")
