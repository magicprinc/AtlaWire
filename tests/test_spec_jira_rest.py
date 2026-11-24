"""Jira Server REST contract checks over the real HTTP transport."""

import json
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from atlawire import jira
from atlawire.http import AtlaWireError

# Jira Server 8.22.2 REST: https://docs.atlassian.com/software/jira/docs/api/REST/8.22.2/
# atlassian-python-api 5.0.5: atlassian/jira/jira_server.py, reference reads.
# list_statuses, list_transitions and get_current_user return the documented
# projections from their docstrings/TypedDicts; only documented fields survive.
CASES = [
    (jira.get_issue_worklogs, True, "/rest/api/2/issue/ABC-123/worklog", {"startAt": 0, "maxResults": 20, "total": 1, "worklogs": [{"id": "1", "extra": {"x": 1}}], "extra": 7}, {"startAt": 0, "maxResults": 20, "total": 1, "worklogs": [{"id": "1", "extra": {"x": 1}}], "extra": 7}),
    (jira.get_issue_changelog, True, "/rest/api/2/issue/ABC-123?expand=changelog", {"changelog": {"startAt": 0, "maxResults": 20, "total": 1, "histories": [{"id": "1", "extra": 7}], "extra": 8}}, {"startAt": 0, "maxResults": 20, "total": 1, "histories": [{"id": "1", "extra": 7}], "extra": 8}),
    (jira.list_statuses, False, "/rest/api/2/status", [{"id": "1", "name": "Open", "extra": 7}], ["Open"]),
    (jira.list_priorities, False, "/rest/api/2/priority", [{"id": "1", "name": "High", "extra": {"x": 1}}], [{"id": "1", "name": "High", "extra": {"x": 1}}]),
    (jira.list_resolutions, False, "/rest/api/2/resolution", [{"id": "1", "name": "Done", "extra": 7}], [{"id": "1", "name": "Done", "extra": 7}]),
    (jira.list_issue_types, False, "/rest/api/2/issuetype", [{"id": "1", "name": "Bug", "extra": 7}], [{"id": "1", "name": "Bug", "extra": 7}]),
    (jira.list_jira_projects, False, "/rest/api/2/project", [{"id": "1", "key": "ABC", "extra": 7}], [{"id": "1", "key": "ABC", "extra": 7}]),
    (jira.list_transitions, True, "/rest/api/2/issue/ABC-123/transitions", {"transitions": [{"id": "1", "name": "Start", "to": {"name": "Open"}, "extra": 7}]}, [{"id": "1", "name": "Start", "to_status": "Open"}]),
    (jira.list_issue_remote_links, True, "/rest/api/2/issue/ABC-123/remotelink", [{"id": 1, "object": {"url": "https://example.org/", "title": "Link", "extra": 7}, "extra": 8}], [{"id": 1, "object": {"url": "https://example.org/", "title": "Link", "extra": 7}, "extra": 8}]),
    (jira.get_current_user, False, "/rest/api/2/myself", {"name": "alice", "displayName": "Alice", "emailAddress": "alice@example.org", "extra": 7}, {"name": "alice", "displayName": "Alice", "email": "alice@example.org"}),
]

TOKEN = "test-token-not-a-credential"


@pytest.fixture
def server():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.server.paths.append(self.path)
            body = self.server.response if isinstance(self.server.response, bytes) else json.dumps(self.server.response).encode()
            self.send_response(self.server.status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    httpd.paths = []
    httpd.status = 200
    httpd.response = None
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd, f"http://127.0.0.1:{httpd.server_port}"
    finally:
        httpd.shutdown()
        thread.join(timeout=5)
        httpd.server_close()


def invoke(function, issue, base):
    args = (base, "ABC-123") if issue else (base,)
    return function(*args, token=TOKEN, allow_http_loopback=True)


@pytest.mark.parametrize("function,issue,path,payload,expected", CASES, ids=lambda value: getattr(value, "__name__", str(value)) if callable(value) else None)
def test_success_preserves_server_fields(server, function, issue, path, payload, expected):
    httpd, base = server
    httpd.response = payload
    result = invoke(function, issue, base)
    assert httpd.paths == [path]
    assert result == expected


def test_empty_collections(server):
    # Jira 8.22.2 returns collection envelopes for worklog, changelog and transitions;
    # the reference endpoints return arrays. /myself has no empty collection response.
    httpd, base = server
    empty = [
        ({"startAt": 0, "maxResults": 20, "total": 0, "worklogs": []}, {"startAt": 0, "maxResults": 20, "total": 0, "worklogs": []}),
        ({"changelog": {"startAt": 0, "maxResults": 20, "total": 0, "histories": []}}, {"startAt": 0, "maxResults": 20, "total": 0, "histories": []}),
        ([], []), ([], []), ([], []), ([], []), ([], []),
        ({"transitions": []}, []), ([], []),
    ]
    for (function, issue, path, _, _), (payload, expected) in zip(CASES, empty):
        httpd.paths.clear()
        httpd.response = payload
        assert invoke(function, issue, base) == expected, function.__name__
        assert httpd.paths == [path]


def test_empty_http_body_is_rejected(server):
    # Jira 8.22.2 documents JSON representations for these GET operations.
    httpd, base = server
    httpd.response = b""
    failures = []
    for function, issue, path, _, _ in CASES:
        httpd.paths.clear()
        try:
            invoke(function, issue, base)
        except AtlaWireError:
            pass
        else:
            failures.append(function.__name__)
        if httpd.paths != [path]:
            failures.append(f"{function.__name__}: unexpected requests")
    assert not failures, failures


def test_http_errors_do_not_disclose_response_or_token(server):
    httpd, base = server
    failures = []
    for function, issue, path, _, _ in CASES:
        for status in (400, 401, 403, 404, 429):
            httpd.paths.clear()
            httpd.status = status
            httpd.response = {"error": "private-response-sentinel", "token": TOKEN}
            try:
                invoke(function, issue, base)
            except AtlaWireError as error:
                rendered = "".join(traceback.format_exception(error))
                if error.category != "http" or error.http_status != status:
                    failures.append((function.__name__, status, "wrong classification"))
                if TOKEN in rendered or "private-response-sentinel" in rendered:
                    failures.append((function.__name__, status, "secret disclosed"))
            else:
                failures.append((function.__name__, status, "no AtlaWireError"))
            if httpd.paths != [path]:
                failures.append((function.__name__, status, "unexpected requests"))
    assert not failures, failures
