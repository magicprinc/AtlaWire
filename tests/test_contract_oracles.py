import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest

from atlawire import bitbucket, confluence, jira


@pytest.fixture
def server():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.server.calls.append(
                (
                    self.command,
                    self.path,
                    self.headers.get("Authorization"),
                    self.headers.get("Accept"),
                )
            )
            body = self.server.body
            self.send_response(200)
            self.send_header("Content-Type", self.server.content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    httpd.calls = []
    httpd.body = b""
    httpd.content_type = "application/json"
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd, f"http://127.0.0.1:{httpd.server_port}"
    finally:
        httpd.shutdown()
        thread.join(timeout=5)
        httpd.server_close()
        assert not thread.is_alive()


def assert_request(httpd, path, query, accept=None):
    assert len(httpd.calls) == 1
    method, target, authorization, actual_accept = httpd.calls[0]
    parsed = urlsplit(target)
    assert method == "GET"
    assert parsed.path == path
    assert parse_qs(parsed.query, keep_blank_values=True) == query
    assert authorization == "Bearer oracle-token"
    if accept is not None:
        assert actual_accept == accept


def test_jira_issue_expand(server):
    # Jira 8.22.2: https://docs.atlassian.com/software/jira/docs/api/REST/8.22.2/#api/2/issue-getIssue
    # atlassian-python-api 5.0.5: atlassian/jira/jira_server.py:1435-1475 (get_issue).
    httpd, base = server
    httpd.body = json.dumps(
        {"key": "ORACLE-42", "fields": {"summary": "hello"}}
    ).encode()
    result = jira.get_issue(
        base,
        "ORACLE-42",
        token="oracle-token",
        expand="names,renderedFields",
        allow_http_loopback=True,
    )
    assert result == {"key": "ORACLE-42", "fields": {"summary": "hello"}}
    assert_request(
        httpd, "/rest/api/2/issue/ORACLE-42", {"expand": ["names,renderedFields"]}
    )


def test_jira_search_issues(server):
    # Jira 8.22.2: https://docs.atlassian.com/software/jira/docs/api/REST/8.22.2/#api/2/search-search
    # atlassian-python-api 5.0.5: atlassian/jira/jira_server.py:4136-4185 (jql).
    httpd, base = server
    httpd.body = json.dumps(
        {
            "startAt": 0,
            "maxResults": 5,
            "total": 1,
            "issues": [
                {"key": "ORACLE-42", "fields": {"summary": "hello", "updated": "today"}}
            ],
        }
    ).encode()
    result = jira.search_issues(
        base,
        "project = ORACLE",
        token="oracle-token",
        limit=5,
        allow_http_loopback=True,
    )
    assert result == [
        {
            "key": "ORACLE-42",
            "status": None,
            "type": None,
            "priority": None,
            "assignee": None,
            "updated": "today",
            "summary": "hello",
        }
    ]
    assert_request(
        httpd,
        "/rest/api/2/search",
        {
            "jql": ["project = ORACLE"],
            "fields": ["summary,status,priority,issuetype,assignee,updated"],
            "startAt": ["0"],
            "maxResults": ["5"],
        },
    )


def test_jira_search_raw(server):
    # Jira 8.22.2: https://docs.atlassian.com/software/jira/docs/api/REST/8.22.2/#api/2/search-search
    # atlassian-python-api 5.0.5: atlassian/jira/jira_server.py:4136-4185 (jql).
    httpd, base = server
    httpd.body = json.dumps(
        {"startAt": 3, "maxResults": 5, "total": 4, "issues": [{"key": "ORACLE-42"}]}
    ).encode()
    result = jira.search_raw(
        base,
        "project = ORACLE",
        token="oracle-token",
        fields="summary,description",
        start=3,
        limit=5,
        expand="names",
        allow_http_loopback=True,
    )
    assert result == {
        "startAt": 3,
        "maxResults": 5,
        "total": 4,
        "issues": [{"key": "ORACLE-42"}],
    }
    assert_request(
        httpd,
        "/rest/api/2/search",
        {
            "jql": ["project = ORACLE"],
            "fields": ["summary,description"],
            "startAt": ["3"],
            "maxResults": ["5"],
            "expand": ["names"],
        },
    )


def test_confluence_page_default_expand(server):
    # Confluence 6.6.0: https://docs.atlassian.com/atlassian-confluence/REST/6.6.0/#content-getContentById
    # atlassian-python-api 5.0.5: atlassian/confluence/server/__init__.py:513-537; default requested by user.
    httpd, base = server
    httpd.body = json.dumps(
        {
            "id": "123",
            "type": "page",
            "title": "Oracle",
            "body": {"storage": {"value": "<p>hello</p>"}},
        }
    ).encode()
    result = confluence.get_page(
        base, "123", token="oracle-token", allow_http_loopback=True
    )
    assert result == {
        "id": "123",
        "type": "page",
        "title": "Oracle",
        "body": {"storage": {"value": "<p>hello</p>"}},
    }
    assert_request(
        httpd,
        "/rest/api/content/123",
        {"expand": ["body.storage,version,space,ancestors"]},
    )


def test_bitbucket_repository_file_revision(server):
    # Bitbucket Server 5.10: https://docs.atlassian.com/bitbucket-server/rest/5.10.0/bitbucket-rest.html#idm532024747920
    # atlassian-python-api 5.0.5: atlassian/bitbucket/__init__.py:2868-2887 (get_content_of_file).
    httpd, base = server
    httpd.body = b"hello\n"
    httpd.content_type = "text/plain; charset=utf-8"
    result = bitbucket.get_repository_file(
        base,
        "PROJ/repo",
        "dir/file.txt",
        token="oracle-token",
        at="refs/heads/feature",
        allow_http_loopback=True,
    )
    assert result == "hello\n"
    assert_request(
        httpd,
        "/rest/api/1.0/projects/PROJ/repos/repo/raw/dir/file.txt",
        {"at": ["refs/heads/feature"]},
        "text/plain",
    )
