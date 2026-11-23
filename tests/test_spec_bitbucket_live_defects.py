"""Black-box contracts for the Bitbucket read defects found by the live run.

Every test uses only the public library surface against a loopback HTTP server:
no monkeypatching, no recorded production calls, and no real network. Two
defects are covered:

* ``file`` failed for ``README.md`` because the raw-file reader accepted only a
  literal ``text/plain`` media type (the route serves ``text/markdown``).
* ``last-modified`` with a path needs the documented explicit ``at`` commit;
  the request shape itself already matches the 5.10 reference, so the request
  assertion here is a regression guard for the documented route and query.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import NamedTuple
from urllib.parse import parse_qs, urlsplit

import pytest

from atlawire import bitbucket
from atlawire.http import AtlaWireError

TOKEN = "synthetic-live-defect-token"
SECRET = "synthetic-private-error-body"
SHA = "a" * 40
ROOT = "/rest/api/1.0/projects/PROJ/repos/repo"
MARKDOWN = "# Title\r\n\r\nПривет, README\r\n"

PR = {
    "id": 42,
    "title": "A title",
    "state": "OPEN",
    "fromRef": {
        "latestCommit": SHA,
        "repository": {"project": {"key": "FORK"}, "slug": "copy"},
    },
    "toRef": {
        "latestCommit": "b" * 40,
        "repository": {"project": {"key": "DEST"}, "slug": "target"},
    },
}


class Call(NamedTuple):
    method: str
    target: str
    accept: str | None
    authorization: str | None


class Route(NamedTuple):
    status: int
    content_type: str
    body: bytes


@pytest.fixture
def server():
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def do_GET(self):
            self.server.calls.append(  # type: ignore[attr-defined]
                Call(
                    self.command,
                    self.path,
                    self.headers.get("Accept"),
                    self.headers.get("Authorization"),
                )
            )
            path = urlsplit(self.path).path
            route = self.server.routes.get(path)  # type: ignore[attr-defined]
            if route is None:
                self.server.unexpected.append(self.path)  # type: ignore[attr-defined]
                self.send_error(404)
                return
            self.send_response(route.status)
            self.send_header("Content-Type", route.content_type)
            self.send_header("Content-Length", str(len(route.body)))
            self.end_headers()
            self.wfile.write(route.body)

        def log_message(self, format: str, *args: object) -> None:
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    httpd.calls = []  # type: ignore[attr-defined]
    httpd.unexpected = []  # type: ignore[attr-defined]
    httpd.routes = {}  # type: ignore[attr-defined]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd, f"http://127.0.0.1:{httpd.server_port}"
    finally:
        httpd.shutdown()
        thread.join(timeout=5)
        httpd.server_close()
        assert not thread.is_alive()


def route(httpd, path, *, status=200, content_type="application/json", body=None):
    if body is None:
        body = b"{}"
    if isinstance(body, dict):
        body = json.dumps(body).encode()
    httpd.routes[path] = Route(status, content_type, body)


def assert_call(httpd, path, query, *, accept, calls=1):
    assert httpd.unexpected == []
    assert len(httpd.calls) == calls
    method, target, actual_accept, authorization = httpd.calls[-1]
    parsed = urlsplit(target)
    assert method == "GET"
    assert (parsed.path, parse_qs(parsed.query, keep_blank_values=True)) == (
        path,
        query,
    )
    assert actual_accept == accept
    assert authorization == "Bearer " + TOKEN


# The live server serves a stored README.md as text/markdown; the old strict
# text/plain check turned a readable file into an upstream error.
def test_file_reads_text_markdown(server):
    httpd, base = server
    route(
        httpd,
        ROOT + "/raw/README.md",
        content_type="text/markdown; charset=utf-8",
        body=MARKDOWN.encode(),
    )
    result = bitbucket.get_repository_file(
        base,
        "PROJ/repo",
        "README.md",
        token=TOKEN,
        at="refs/heads/main",
        allow_http_loopback=True,
    )
    assert result == MARKDOWN
    assert_call(
        httpd,
        ROOT + "/raw/README.md",
        {"at": ["refs/heads/main"]},
        accept="text/plain",
    )


# Regression guard: ordinary .java/.gradle files keep the previous behavior.
def test_file_keeps_text_plain_behavior(server):
    httpd, base = server
    source = "public class A {\r\n}\r\n"
    route(
        httpd,
        ROOT + "/raw/src/main/A.java",
        content_type="text/plain; charset=utf-8",
        body=source.encode(),
    )
    assert (
        bitbucket.get_repository_file(
            base,
            "PROJ/repo",
            "src/main/A.java",
            token=TOKEN,
            at=SHA,
            allow_http_loopback=True,
        )
        == source
    )
    assert_call(
        httpd,
        ROOT + "/raw/src/main/A.java",
        {"at": [SHA]},
        accept="text/plain",
    )


# A JSON media type is an error document, never file content; the reader must
# not silently return it as text and must not retry the request.
def test_file_rejects_json_document(server):
    httpd, base = server
    document = {"errors": [{"message": SECRET, "exceptionName": None}]}
    route(httpd, ROOT + "/raw/README.md", content_type="application/json", body=document)
    with pytest.raises(AtlaWireError) as caught:
        bitbucket.get_repository_file(
            base,
            "PROJ/repo",
            "README.md",
            token=TOKEN,
            at=SHA,
            allow_http_loopback=True,
        )
    assert caught.value.category == "upstream"
    assert "JSON" in str(caught.value)
    assert SECRET not in str(caught.value)
    assert TOKEN not in str(caught.value)
    assert_call(httpd, ROOT + "/raw/README.md", {"at": [SHA]}, accept="text/plain")


# The pull request file reader shares the raw route and must accept the same
# media types, including the markdown media type of the live README.md.
def test_pull_request_file_reads_text_markdown(server):
    httpd, base = server
    route(httpd, ROOT + "/pull-requests/42", body=PR)
    route(
        httpd,
        "/rest/api/1.0/projects/FORK/repos/copy/raw/README.md",
        content_type="text/markdown",
        body=MARKDOWN.encode(),
    )
    result = bitbucket.get_pull_request_file(
        base,
        "PROJ/repo",
        42,
        "README.md",
        token=TOKEN,
        allow_http_loopback=True,
    )
    assert result == MARKDOWN
    assert [urlsplit(call.target).path for call in httpd.calls] == [
        ROOT + "/pull-requests/42",
        "/rest/api/1.0/projects/FORK/repos/copy/raw/README.md",
    ]
    assert_call(
        httpd,
        "/rest/api/1.0/projects/FORK/repos/copy/raw/README.md",
        {"at": [SHA]},
        accept="text/plain",
        calls=2,
    )


# The documented 400 states that a streaming (path) read needs an explicit
# starting commit, so a missing or empty at must fail before any request.
@pytest.mark.parametrize("at", [None, ""])
def test_last_modified_path_requires_explicit_at(server, at):
    httpd, base = server
    route(httpd, ROOT + "/last-modified/README.md", body={"files": {}, "latestCommit": {}})
    with pytest.raises(AtlaWireError) as caught:
        bitbucket.get_last_modified(
            base,
            "PROJ/repo",
            "README.md",
            token=TOKEN,
            at=at,
            allow_http_loopback=True,
        )
    assert caught.value.category == "validation"
    assert httpd.calls == []
    assert httpd.unexpected == []


# Regression guard for the documented request shape: one GET on the path
# template with at as the only query parameter, and the response preserved.
def test_last_modified_path_sends_documented_request(server):
    httpd, base = server
    value = {
        "files": {"src/main/Service.java": {"id": SHA, "displayId": SHA[:7]}},
        "latestCommit": {"id": SHA},
        "extra": [1, None],
    }
    route(httpd, ROOT + "/last-modified/src/main/Service.java", body=value)
    result = bitbucket.get_last_modified(
        base,
        "PROJ/repo",
        "src/main/Service.java",
        token=TOKEN,
        at=SHA,
        allow_http_loopback=True,
    )
    assert result == value
    assert_call(
        httpd,
        ROOT + "/last-modified/src/main/Service.java",
        {"at": [SHA]},
        accept="application/json",
    )


# The repository-root form is documented to fall back to the default branch
# tip, so the new path-only validation must not change it.
def test_last_modified_root_keeps_omitted_at(server):
    httpd, base = server
    value = {"files": {}, "latestCommit": {}}
    route(httpd, ROOT + "/last-modified", body=value)
    assert (
        bitbucket.get_last_modified(
            base, "PROJ/repo", token=TOKEN, allow_http_loopback=True
        )
        == value
    )
    assert_call(
        httpd,
        ROOT + "/last-modified",
        {},
        accept="application/json",
    )
