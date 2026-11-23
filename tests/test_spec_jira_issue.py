import json
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest
from atlawire.http import AtlaWireError
from atlawire import jira


TOKEN = "synthetic-token-issue"
SENTINEL = "synthetic-response-sentinel-issue"
ISSUE = {"key": "SPEC-42", "fields": {"summary": "hello", "customfield_999": {"x": [None, 3]}}, "unknown": {"nested": True}}


@pytest.fixture
def server():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.server.calls.append((self.command, self.path, self.headers.get("Authorization")))
            body = json.dumps(self.server.body).encode()
            self.send_response(self.server.status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    httpd.calls = []
    httpd.status = 200
    httpd.body = ISSUE
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd, f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()
    thread.join(timeout=5)
    httpd.server_close()
    assert not thread.is_alive()




def test_get_issue_accepts_explicit_expand(server):
    httpd, base = server
    assert jira.get_issue(base, "SPEC-42", token=TOKEN, expand="names,renderedFields", allow_http_loopback=True) == ISSUE
    assert len(httpd.calls) == 1
    method, target, authorization = httpd.calls[0]
    assert method == "GET" and authorization == "Bearer " + TOKEN
    assert urlsplit(target).path == "/rest/api/2/issue/SPEC-42"
    assert parse_qs(urlsplit(target).query) == {"expand": ["names,renderedFields"]}


def test_get_issue_wire_get_path_and_query(server):
    httpd, base = server
    jira.get_issue(base, "SPEC-42", token=TOKEN, allow_http_loopback=True)
    assert len(httpd.calls) == 1
    method, target, authorization = httpd.calls[0]
    assert authorization == "Bearer " + TOKEN
    parsed = urlsplit(target)
    assert method == "GET"
    assert parsed.path == "/rest/api/2/issue/SPEC-42"
    query = parse_qs(parsed.query)
    assert query.pop("expand") == ["renderedFields"]
    assert query == {}


def test_get_issue_uses_fixed_expand_without_extra_query(server):
    httpd, base = server
    jira.get_issue(base, "SPEC-42", token=TOKEN, allow_http_loopback=True)
    assert len(httpd.calls) == 1
    assert parse_qs(urlsplit(httpd.calls[0][1]).query) == {"expand": ["renderedFields"]}


def test_get_issue_preserves_unknown_response_fields(server):
    _, base = server
    assert jira.get_issue(base, "SPEC-42", token=TOKEN, allow_http_loopback=True) == ISSUE


@pytest.mark.parametrize("status", [400, 401, 403, 404, 429])
def test_get_issue_errors_are_sanitized_and_not_retried(server, status, capsys, caplog):
    httpd, base = server
    httpd.status = status
    httpd.body = {"errorMessages": [SENTINEL, TOKEN]}
    with pytest.raises(AtlaWireError) as error:
        jira.get_issue(base, "SPEC-42", token=TOKEN, allow_http_loopback=True)
    assert error.value.category == "http"
    assert error.value.http_status == status
    captured = capsys.readouterr()
    text = "".join(traceback.format_exception(error.value)) + captured.out + captured.err + caplog.text
    assert SENTINEL not in text
    assert TOKEN not in text
    assert len(httpd.calls) == 1
    assert httpd.calls[0][2] == "Bearer " + TOKEN


def test_get_issue_sends_every_documented_query_option(server):
    httpd, base = server
    assert (
        jira.get_issue(
            base,
            "SPEC-42",
            token=TOKEN,
            expand="names",
            fields="summary,status",
            properties="alpha,beta",
            update_history=True,
            fail_fast=True,
            allow_http_loopback=True,
        )
        == ISSUE
    )
    assert parse_qs(urlsplit(httpd.calls[0][1]).query) == {
        "expand": ["names"],
        "fields": ["summary,status"],
        "properties": ["alpha,beta"],
        "updateHistory": ["true"],
        "failFast": ["true"],
    }
