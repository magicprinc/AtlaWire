import json
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest

from atlawire import jira
from atlawire.http import AtlaWireError

TOKEN = "synthetic-token-search"
SENTINEL = "synthetic-response-sentinel-search"
JQL = 'project = SPEC AND summary ~ "hello world" ORDER BY created DESC'
ISSUE = {
    "key": "SPEC-42",
    "fields": {"summary": "hello", "updated": "today", "customfield_999": [1, None]},
    "unknown": True,
}
ENVELOPE = {
    "startAt": 0,
    "maxResults": 5,
    "total": 1,
    "issues": [ISSUE],
    "unknownEnvelope": {"x": 7},
}


@pytest.fixture
def server():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.server.calls.append(
                (self.command, self.path, self.headers.get("Authorization"))
            )
            status, value = self.server.responses[
                min(len(self.server.calls) - 1, len(self.server.responses) - 1)
            ]
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


def test_search_sends_jql_projection_and_limit(server):
    httpd, base = server
    assert jira.search_issues(
        base, JQL, token=TOKEN, limit=5, allow_http_loopback=True
    ) == [
        {
            "key": "SPEC-42",
            "status": None,
            "type": None,
            "priority": None,
            "assignee": None,
            "updated": "today",
            "summary": "hello",
        }
    ]
    assert len(httpd.calls) == 1
    method, target, authorization = httpd.calls[0]
    assert method == "GET" and authorization == "Bearer " + TOKEN
    assert urlsplit(target).path == "/rest/api/2/search"
    assert parse_qs(urlsplit(target).query) == {
        "jql": [JQL],
        "fields": ["summary,status,priority,issuetype,assignee,updated"],
        "startAt": ["0"],
        "maxResults": ["5"],
    }
    assert len(httpd.calls) == 1


def test_search_raw_forwards_caller_arguments(server):
    httpd, base = server
    payload = {**ENVELOPE, "startAt": 3, "total": 4}
    httpd.responses = [(200, payload)]
    assert (
        jira.search_raw(
            base,
            JQL,
            token=TOKEN,
            fields="summary,customfield_999",
            start=3,
            limit=5,
            expand="names",
            allow_http_loopback=True,
        )
        == payload
    )
    assert len(httpd.calls) == 1
    method, target, authorization = httpd.calls[0]
    assert method == "GET" and authorization == "Bearer " + TOKEN
    assert urlsplit(target).path == "/rest/api/2/search"
    assert parse_qs(urlsplit(target).query) == {
        "jql": [JQL],
        "fields": ["summary,customfield_999"],
        "startAt": ["3"],
        "maxResults": ["5"],
        "expand": ["names"],
    }


def test_search_raw_accepts_start_offset(server):
    httpd, base = server
    httpd.responses = [(200, {**ENVELOPE, "startAt": 3, "total": 4})]
    jira.search_raw(base, JQL, token=TOKEN, start=3, limit=5, allow_http_loopback=True)
    assert parse_qs(urlsplit(httpd.calls[0][1]).query)["startAt"] == ["3"]


def test_search_wire_get_path_and_default_query(server):
    httpd, base = server
    jira.search_raw(base, JQL, token=TOKEN, limit=5, allow_http_loopback=True)
    assert len(httpd.calls) == 1
    method, target, authorization = httpd.calls[0]
    assert authorization == "Bearer " + TOKEN
    parsed = urlsplit(target)
    assert method == "GET"
    assert parsed.path == "/rest/api/2/search"
    assert parse_qs(parsed.query) == {
        "jql": [JQL],
        "fields": ["*all"],
        "startAt": ["0"],
        "maxResults": ["5"],
    }


def test_search_raw_preserves_envelope_and_issue_fields(server):
    _, base = server
    assert (
        jira.search_raw(base, JQL, token=TOKEN, limit=5, allow_http_loopback=True)
        == ENVELOPE
    )


def test_search_issues_preserves_projection(server):
    _, base = server
    assert jira.search_issues(
        base, JQL, token=TOKEN, limit=5, allow_http_loopback=True
    ) == [
        {
            "key": "SPEC-42",
            "status": None,
            "type": None,
            "priority": None,
            "assignee": None,
            "updated": "today",
            "summary": "hello",
        }
    ]


@pytest.mark.parametrize("status", [400, 401, 403, 404, 429])
def test_search_raw_errors_are_sanitized_and_not_retried(
    server, status, capsys, caplog
):
    httpd, base = server
    httpd.responses = [(status, {"errorMessages": [SENTINEL, TOKEN]})]
    with pytest.raises(AtlaWireError) as error:
        jira.search_raw(base, JQL, token=TOKEN, limit=5, allow_http_loopback=True)
    assert error.value.category == "http"
    assert error.value.http_status == status
    captured = capsys.readouterr()
    text = (
        "".join(traceback.format_exception(error.value))
        + captured.out
        + captured.err
        + caplog.text
    )
    assert SENTINEL not in text
    assert TOKEN not in text
    assert len(httpd.calls) == 1
    assert httpd.calls[0][2] == "Bearer " + TOKEN
