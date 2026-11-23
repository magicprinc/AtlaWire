import json
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest
import requests
from atlassian import Jira

from atlawire import jira


TOKEN = "synthetic-token-issue"
SENTINEL = "synthetic-response-sentinel-issue"
ISSUE = {"key": "SPEC-42", "fields": {"summary": "hello", "customfield_999": {"x": [None, 3]}}, "unknown": {"nested": True}}


@pytest.fixture
def server():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.server.calls.append((self.command, self.path))
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


def test_get_issue_dispatches_to_sdk_with_key_and_expand(server, monkeypatch):
    httpd, base = server
    original = Jira.get_issue
    calls = []

    def spy(self, *args, **kwargs):
        calls.append((args, kwargs))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Jira, "get_issue", spy)
    jira.get_issue(base, "SPEC-42", token=TOKEN, allow_http_loopback=True)
    assert len(calls) == 1
    args, kwargs = calls[0]
    import inspect
    bound = inspect.signature(original).bind(None, *args, **kwargs)
    assert bound.arguments["issue_id_or_key"] == "SPEC-42"
    assert bound.arguments["expand"] == "renderedFields"
    assert len(httpd.calls) == 1


def test_get_issue_accepts_explicit_expand(server):
    _, base = server
    assert jira.get_issue(base, "SPEC-42", token=TOKEN, expand="renderedFields", allow_http_loopback=True) == ISSUE


def test_get_issue_wire_get_path_and_query(server):
    httpd, base = server
    jira.get_issue(base, "SPEC-42", token=TOKEN, allow_http_loopback=True)
    assert len(httpd.calls) == 1
    method, target = httpd.calls[0]
    parsed = urlsplit(target)
    assert method == "GET"
    assert parsed.path == "/rest/api/2/issue/SPEC-42"
    query = parse_qs(parsed.query)
    assert query.pop("expand") == ["renderedFields"]
    assert query in ({}, {"updateHistory": ["true"]})


def test_get_issue_preserves_unknown_response_fields(server):
    _, base = server
    assert jira.get_issue(base, "SPEC-42", token=TOKEN, allow_http_loopback=True) == ISSUE


@pytest.mark.parametrize("status", [400, 401, 403, 429])
def test_get_issue_errors_are_sanitized_and_not_retried(server, status, capsys, caplog):
    httpd, base = server
    httpd.status = status
    httpd.body = {"errorMessages": [SENTINEL, TOKEN]}
    with pytest.raises(Exception) as error:
        jira.get_issue(base, "SPEC-42", token=TOKEN, allow_http_loopback=True)
    captured = capsys.readouterr()
    text = "".join(traceback.format_exception(error.value)) + captured.out + captured.err + caplog.text
    assert SENTINEL not in text
    assert TOKEN not in text
    assert len(httpd.calls) == 1


@pytest.mark.parametrize("status", [200, 401])
def test_get_issue_closes_session_on_success_and_error(server, status, monkeypatch):
    httpd, base = server
    httpd.status = status
    closed = []
    used = []
    original_close = requests.Session.close
    original_send = requests.Session.send

    def send(self, *args, **kwargs):
        used.append(self)
        return original_send(self, *args, **kwargs)

    def close(self):
        closed.append(self)
        return original_close(self)

    monkeypatch.setattr(requests.Session, "send", send)
    monkeypatch.setattr(requests.Session, "close", close)
    if status == 200:
        jira.get_issue(base, "SPEC-42", token=TOKEN, allow_http_loopback=True)
    else:
        with pytest.raises(Exception):
            jira.get_issue(base, "SPEC-42", token=TOKEN, allow_http_loopback=True)
    assert len(httpd.calls) == 1
    assert len(used) == 1
    assert used[0] in closed
