"""Black-box contracts against a loopback Bitbucket Server 5.10."""

import json
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest

from atlawire import bitbucket
from atlawire.http import AtlaWireError

TOKEN = "synthetic-token-for-test"
BODY = "synthetic-private-error-body"


@pytest.fixture
def server():
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self):
            self.server.calls.append((self.command, self.path, self.headers.get("Accept"),
                                      self.headers.get("Authorization")))
            status, payload = self.server.responses.pop(0)
            data = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

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
        httpd.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


def page(values, last, next_start=None):
    result = {"values": values, "isLastPage": last}
    if next_start is not None:
        result["nextPageStart"] = next_start
    return result


def assert_calls(server, path, queries):
    assert len(server.calls) == len(queries)
    for (method, target, accept, auth), query in zip(server.calls, queries, strict=True):
        parsed = urlsplit(target)
        assert (method, parsed.path, parse_qs(parsed.query)) == ("GET", path, query)
        assert accept == "application/json"
        assert auth == "Bearer " + TOKEN
    assert server.closed.wait(3), "client did not close the HTTP connection"


# Server 5.10 paged APIs use nextPageStart, not start + size:
# https://docs.atlassian.com/bitbucket-server/rest/5.10.0/bitbucket-rest.html#paging-params
@pytest.mark.parametrize(("function", "args", "path", "rows", "expected"), [
    (bitbucket.list_projects, (), "/rest/api/1.0/projects",
     [{"key": "A", "name": "Alpha"}, {"key": "B"}],
     [{"key": "A", "name": "Alpha", "description": None, "public": None, "url": None},
      {"key": "B", "name": None, "description": None, "public": None, "url": None}]),
    (bitbucket.list_repositories, ("PRJ",), "/rest/api/1.0/projects/PRJ/repos",
     [{"slug": "one", "name": "One"}, {"slug": "two"}],
     [{"slug": "one", "name": "One", "state": None, "public": None},
      {"slug": "two", "name": None, "state": None, "public": None}]),
    (bitbucket.list_repository_files, ("PRJ/repo",),
     "/rest/api/1.0/projects/PRJ/repos/repo/files",
     ["a.txt", "dir/b.txt"], ["a.txt", "dir/b.txt"]),
])
def test_paged_lists_follow_opaque_cursor(server, function, args, path, rows, expected):
    httpd, url = server
    httpd.responses = [(200, page([rows[0]], False, 37)), (200, page([rows[1]], True))]
    assert function(url, *args, token=TOKEN, allow_http_loopback=True) == expected
    assert_calls(httpd, path, [{"start": ["0"], "limit": ["100"]},
                               {"start": ["37"], "limit": ["100"]}])


# list_directory docstring requires the nested children envelope and preserves zero size.
def test_directory_pages_and_revision(server):
    httpd, url = server
    httpd.responses = [
        (200, {"children": page([{"path": {"toString": "dir/a"}, "type": "FILE", "size": 0}], False, 8)}),
        (200, {"children": page([{"path": {"toString": "dir/b"}, "type": "DIRECTORY"}], True)}),
    ]
    assert bitbucket.list_directory(url, "PRJ/repo", "dir", token=TOKEN, at="refs/heads/main",
                                    allow_http_loopback=True) == [
        {"path": "dir/a", "type": "FILE", "size": 0},
        {"path": "dir/b", "type": "DIRECTORY", "size": None},
    ]
    assert_calls(httpd, "/rest/api/1.0/projects/PRJ/repos/repo/browse/dir", [
        {"start": ["0"], "limit": ["100"], "at": ["refs/heads/main"]},
        {"start": ["8"], "limit": ["100"], "at": ["refs/heads/main"]},
    ])


# Server endpoint and query: https://docs.atlassian.com/bitbucket-server/rest/5.10.0/bitbucket-rest.html#idm532026360144
# get_last_modified promises one request and an unchanged decoded object.
def test_last_modified_preserves_response(server):
    httpd, url = server
    value = {"latestCommit": "abc", "files": {"x": {"id": "123"}}, "extra": [1]}
    httpd.responses = [(200, value)]
    assert bitbucket.get_last_modified(url, "PRJ/repo", "dir/a b", token=TOKEN, at="main",
                                       allow_http_loopback=True) == value
    assert_calls(httpd, "/rest/api/1.0/projects/PRJ/repos/repo/last-modified/dir/a%20b",
                 [{"at": ["main"]}])


# list_projects promises a complete list or an error, never partial output.
def test_page_limit_raises_after_one_request(server):
    httpd, url = server
    httpd.responses = [(200, page([{"key": "A"}], False, 11))]
    with pytest.raises(AtlaWireError):
        bitbucket.list_projects(url, token=TOKEN, max_pages=1, allow_http_loopback=True)
    assert_calls(httpd, "/rest/api/1.0/projects", [{"start": ["0"], "limit": ["100"]}])


def test_http_error_sanitized_and_connection_closed(server):
    httpd, url = server
    httpd.responses = [(403, {"errors": [{"message": BODY + TOKEN}]})]
    with pytest.raises(AtlaWireError) as caught:
        bitbucket.list_projects(url, token=TOKEN, allow_http_loopback=True)
    assert caught.value.category == "http"
    assert caught.value.http_status == 403
    diagnostic = "".join(traceback.format_exception(caught.value))
    assert BODY not in diagnostic and TOKEN not in diagnostic
    assert_calls(httpd, "/rest/api/1.0/projects", [{"start": ["0"], "limit": ["100"]}])
