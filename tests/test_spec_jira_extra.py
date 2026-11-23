"""Black-box contracts: https://docs.atlassian.com/software/jira/docs/api/REST/8.22.2/ ."""
import json
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest

from atlawire import jira, jira_metadata
from atlawire.http import AtlaWireError

TOKEN = "synthetic-only-token"
BODY_MARKER = "synthetic-only-error-body"


@pytest.fixture
def server():
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self):
            self.server.calls.append((self.command, self.path, self.headers.get("Authorization"), self.headers.get("Accept")))
            status, value = self.server.responses[min(len(self.server.calls) - 1, len(self.server.responses) - 1)]
            body = json.dumps(value).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def finish(self):
            try:
                super().finish()
            finally:
                self.server.closed.set()

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    httpd.calls = []
    httpd.responses = []
    httpd.closed = threading.Event()
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd, f"http://127.0.0.1:{httpd.server_port}"
    finally:
        httpd.shutdown()
        thread.join(timeout=5)
        httpd.server_close()
        assert not thread.is_alive()


def assert_call(call, path, query):
    method, target, authorization, accept = call
    parsed = urlsplit(target)
    assert (method, parsed.path, parse_qs(parsed.query)) == ("GET", path, query)
    assert authorization == "Bearer " + TOKEN
    assert accept == "application/json"


def test_comments_follow_server_cap_and_project_fields(server):
    httpd, base = server
    httpd.responses = [
        (200, {"startAt": 0, "maxResults": 1, "total": 2, "comments": [{"id": "1", "author": {"name": "alice"}, "body": "one", "created": "c", "updated": "u", "unknown": 1}]}),
        (200, {"startAt": 1, "maxResults": 1, "total": 2, "comments": [{"id": "2", "body": "two"}]}),
    ]
    result = jira.list_issue_comments(base, "https://untrusted.example/browse/EX-1", token=TOKEN, allow_http_loopback=True)
    assert result == [{"id": "1", "author": "alice", "body": "one", "created": "c", "updated": "u"}, {"id": "2", "author": None, "body": "two", "created": None, "updated": None}]
    assert len(httpd.calls) == 2
    for call, start in zip(httpd.calls, ("0", "1")):
        assert_call(call, "/rest/api/2/issue/EX-1/comment", {"startAt": [start], "maxResults": ["50"]})
    assert httpd.closed.wait(2)


@pytest.mark.parametrize("status,jql", [(None, "assignee = currentUser() AND statusCategory != Done ORDER BY updated DESC"), ("In Progress", 'assignee = currentUser() AND status = "In Progress" ORDER BY updated DESC')])
def test_my_issues_query_and_projection(server, status, jql):
    httpd, base = server
    httpd.responses = [(200, {"startAt": 0, "maxResults": 2, "total": 1, "issues": [{"key": "EX-1", "fields": {"summary": "sample", "updated": "today", "unknown": "ignored"}}]})]
    assert jira.list_my_issues(base, token=TOKEN, status=status, limit=2, allow_http_loopback=True) == [{"key": "EX-1", "status": None, "type": None, "priority": None, "assignee": None, "updated": "today", "summary": "sample"}]
    assert len(httpd.calls) == 1
    assert_call(httpd.calls[0], "/rest/api/2/search", {"jql": [jql], "fields": ["summary,status,priority,issuetype,assignee,updated"], "startAt": ["0"], "maxResults": ["2"]})
    assert httpd.closed.wait(2)


@pytest.mark.parametrize("kind", ["categories", "users", "edit"])
def test_raw_response_preserves_unknown_members(server, kind):
    httpd, base = server
    if kind == "categories":
        value = [{"id": 2, "key": "new", "unknown": {"x": [None, 1]}}]
        expected_path, query = "/rest/api/2/statuscategory", {}
        call = lambda: jira.list_status_categories(base, token=TOKEN, allow_http_loopback=True)
    elif kind == "users":
        value = [{"name": "a+b", "active": True, "unknown": {"x": [None, 1]}}]
        expected_path, query = "/rest/api/2/user/search", {"username": ["a+b"], "startAt": ["3"], "maxResults": ["7"]}
        call = lambda: jira.search_users(base, "a+b", token=TOKEN, start_at=3, max_results=7, allow_http_loopback=True)
    else:
        value = {"fields": {"summary": {"required": True, "extra": [None]}}, "unknown": {"x": 1}}
        expected_path, query = "/rest/api/2/issue/EX-1/editmeta", {}
        call = lambda: jira_metadata.get_edit_meta(base, "EX-1", token=TOKEN, allow_http_loopback=True)
    httpd.responses = [(200, value)]
    assert call() == value
    assert len(httpd.calls) == 1
    assert_call(httpd.calls[0], expected_path, query)
    assert httpd.closed.wait(2)


@pytest.mark.parametrize("kind", ["comments", "issues", "categories", "users", "edit"])
def test_http_error_is_sanitized_and_not_retried(server, kind):
    httpd, base = server
    httpd.responses = [(403, {"errorMessages": [BODY_MARKER, TOKEN]})]
    calls = {
        "comments": lambda: jira.list_issue_comments(base, "EX-1", token=TOKEN, allow_http_loopback=True),
        "issues": lambda: jira.list_my_issues(base, token=TOKEN, allow_http_loopback=True),
        "categories": lambda: jira.list_status_categories(base, token=TOKEN, allow_http_loopback=True),
        "users": lambda: jira.search_users(base, "alice", token=TOKEN, allow_http_loopback=True),
        "edit": lambda: jira_metadata.get_edit_meta(base, "EX-1", token=TOKEN, allow_http_loopback=True),
    }
    with pytest.raises(AtlaWireError) as error:
        calls[kind]()
    assert error.value.category == "http"
    assert error.value.http_status == 403
    text = "".join(traceback.format_exception(error.value))
    assert TOKEN not in text and BODY_MARKER not in text
    assert len(httpd.calls) == 1
    assert httpd.closed.wait(2)
