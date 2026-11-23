import inspect
import json
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest
import requests
from atlassian import Jira

from atlawire import jira


TOKEN = "synthetic-token-search"
SENTINEL = "synthetic-response-sentinel-search"
JQL = 'project = SPEC AND summary ~ "hello world" ORDER BY created DESC'
ISSUE = {"key": "SPEC-42", "fields": {"summary": "hello", "updated": "today", "customfield_999": [1, None]}, "unknown": True}
ENVELOPE = {"startAt": 0, "maxResults": 5, "total": 1, "issues": [ISSUE], "unknownEnvelope": {"x": 7}}


@pytest.fixture
def server():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.server.calls.append((self.command, self.path))
            status, value = self.server.responses[min(len(self.server.calls) - 1, len(self.server.responses) - 1)]
            body = json.dumps(value).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    httpd.calls = []
    httpd.responses = [(200, ENVELOPE)]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd, f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()
    thread.join(timeout=5)
    httpd.server_close()
    assert not thread.is_alive()


def test_search_dispatches_to_sdk_with_jql_and_limit(server, monkeypatch):
    httpd, base = server
    original = Jira.jql
    calls = []

    def spy(self, *args, **kwargs):
        calls.append((args, kwargs))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Jira, "jql", spy)
    jira.search_issues(base, JQL, token=TOKEN, limit=5, allow_http_loopback=True)
    assert len(calls) == 1
    args, kwargs = calls[0]
    bound = inspect.signature(original).bind(None, *args, **kwargs)
    bound.apply_defaults()
    assert bound.arguments["jql"] == JQL
    assert bound.arguments["fields"] == "summary,status,priority,issuetype,assignee,updated"
    assert bound.arguments["start"] == 0
    assert bound.arguments["limit"] == 5
    assert bound.arguments["expand"] is None
    assert bound.arguments["validate_query"] is None
    assert len(httpd.calls) == 1


def test_search_raw_forwards_caller_arguments_to_sdk(server, monkeypatch):
    httpd, base = server
    original = Jira.jql
    calls = []

    def spy(self, *args, **kwargs):
        calls.append(inspect.signature(original).bind(self, *args, **kwargs))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Jira, "jql", spy)
    httpd.responses = [(200, {**ENVELOPE, "startAt": 3, "total": 4})]
    jira.search_raw(base, JQL, token=TOKEN, fields="summary,customfield_999", start=3, limit=5, expand="names", allow_http_loopback=True)
    assert len(calls) == 1
    calls[0].apply_defaults()
    assert calls[0].arguments["jql"] == JQL
    assert calls[0].arguments["fields"] == "summary,customfield_999"
    assert calls[0].arguments["start"] == 3
    assert calls[0].arguments["limit"] == 5
    assert calls[0].arguments["expand"] == "names"
    assert calls[0].arguments["validate_query"] is None


def test_search_raw_accepts_start_offset(server):
    httpd, base = server
    httpd.responses = [(200, {**ENVELOPE, "startAt": 3, "total": 4})]
    jira.search_raw(base, JQL, token=TOKEN, start=3, limit=5, allow_http_loopback=True)
    assert parse_qs(urlsplit(httpd.calls[0][1]).query)["startAt"] == ["3"]

def test_search_wire_get_path_and_default_sdk_query(server):
    httpd, base = server
    jira.search_raw(base, JQL, token=TOKEN, limit=5, allow_http_loopback=True)
    assert len(httpd.calls) == 1
    method, target = httpd.calls[0]
    parsed = urlsplit(target)
    assert method == "GET"
    assert parsed.path == "/rest/api/2/search"
    assert parse_qs(parsed.query) == {"jql": [JQL], "fields": ["*all"], "startAt": ["0"], "maxResults": ["5"]}


def test_search_raw_preserves_envelope_and_issue_fields(server):
    _, base = server
    assert jira.search_raw(base, JQL, token=TOKEN, limit=5, allow_http_loopback=True) == ENVELOPE


def test_search_issues_preserves_projection(server):
    _, base = server
    assert jira.search_issues(base, JQL, token=TOKEN, limit=5, allow_http_loopback=True) == [
        {"key": "SPEC-42", "status": None, "type": None, "priority": None,
         "assignee": None, "updated": "today", "summary": "hello"}
    ]


@pytest.mark.parametrize("status", [400, 401, 403, 429])
def test_search_raw_errors_are_sanitized_and_not_retried(server, status, capsys, caplog):
    httpd, base = server
    httpd.responses = [(status, {"errorMessages": [SENTINEL, TOKEN]})]
    with pytest.raises(Exception) as error:
        jira.search_raw(base, JQL, token=TOKEN, limit=5, allow_http_loopback=True)
    captured = capsys.readouterr()
    text = "".join(traceback.format_exception(error.value)) + captured.out + captured.err + caplog.text
    assert SENTINEL not in text
    assert TOKEN not in text
    assert len(httpd.calls) == 1



@pytest.mark.parametrize("status", [200, 401])
def test_search_raw_closes_session_on_success_and_error(server, status, monkeypatch):
    httpd, base = server
    httpd.responses = [(status, ENVELOPE)]
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
        jira.search_raw(base, JQL, token=TOKEN, limit=5, allow_http_loopback=True)
    else:
        with pytest.raises(Exception):
            jira.search_raw(base, JQL, token=TOKEN, limit=5, allow_http_loopback=True)
    assert len(httpd.calls) == 1
    assert len(used) == 1
    assert used[0] in closed
