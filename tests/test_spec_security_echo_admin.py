"""Black-box security contracts for credential echo and encoded administrative paths.

Every scenario drives the real CLI against a loopback server. Assertions come
from the exit status, the captured stdout/stderr and the server's request log,
so no test reads an internal counter, monkeypatches a guard or sends a real
request outside 127.0.0.1.

The two defects these tests pin down:

* a successful JSON payload that echoes the bearer token must never reach
  stdout/stderr on the canonical ``read`` path or on ``api-get``/``api-request``
  (the legacy ``read-operation`` path already refused it);
* an administrative path hidden behind percent-encoding (``%61dmin``, encoded
  ``..`` segments, double encoding) must be refused before any HTTP request,
  while legal percent-encoding such as a space inside a file name still works.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import cast
from urllib.parse import unquote, urlsplit

import pytest
from click.testing import CliRunner

from atlawire.cli import cli

TOKEN = "synthetic-echo-check-token"
PROJECT = "PROJ"
REPOSITORY = "repo"
REPOSITORY_PATH = f"/rest/api/1.0/projects/{PROJECT}/repos/{REPOSITORY}"


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    calls: list[tuple[str, str, str | None]]
    response_body: bytes

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _Handler)
        self.calls = []
        self.response_body = json.dumps({"slug": REPOSITORY, "name": TOKEN}).encode()


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def log_message(self, format: str, *args: object) -> None:
        pass

    def do_GET(self) -> None:
        server = cast(_Server, self.server)
        server.calls.append(
            (self.command, self.path, self.headers.get("Authorization"))
        )
        body = server.response_body
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def server():
    httpd = _Server()
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd, f"http://127.0.0.1:{httpd.server_port}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


@pytest.fixture
def invoke(server):
    _, base = server
    runner = CliRunner()

    def run(*argv: str):
        return runner.invoke(
            cli,
            [
                *argv,
                "--base-url",
                base,
                "--token-from-env",
                "--allow-http-loopback",
            ],
            env={
                "ATLAWIRE_BITBUCKET_URL": base,
                "ATLAWIRE_BITBUCKET_TOKEN": TOKEN,
            },
        )

    return run


READ_ARGV = (
    "read",
    "bitbucket.repository.get",
    "--params",
    json.dumps({"projectKey": PROJECT, "repositorySlug": REPOSITORY}),
)
API_GET_ARGV = ("api-get", "bitbucket", REPOSITORY_PATH)
API_REQUEST_ARGV = ("api-request", "bitbucket", "GET", REPOSITORY_PATH)


@pytest.mark.parametrize(
    "argv",
    [READ_ARGV, API_GET_ARGV, API_REQUEST_ARGV],
    ids=["read", "api-get", "api-request"],
)
def test_successful_payload_echoing_token_never_reaches_the_caller(
    server, invoke, argv
) -> None:
    httpd, _ = server
    result = invoke(*argv)

    # The request itself succeeded; the refusal must happen on the payload.
    assert len(httpd.calls) == 1
    assert result.exit_code != 0, result.output
    assert TOKEN not in result.stdout
    assert TOKEN not in result.stderr


@pytest.mark.parametrize(
    "path",
    [
        "/rest/api/2/%61dmin/x",
        "/rest/api/2/foo/%2e%2e/%2e%2e/x",
        "/rest/api/2/%2561dmin/x",
        "/rest/api/2/foo/%252e%252e/%252e%252e/x",
    ],
    ids=[
        "encoded-admin",
        "encoded-traversal",
        "double-encoded-admin",
        "double-encoded-traversal",
    ],
)
def test_encoded_admin_path_is_refused_before_any_request(server, invoke, path) -> None:
    httpd, _ = server
    result = invoke("api-get", "bitbucket", path)

    assert result.exit_code != 0, result.output
    assert httpd.calls == []


def test_encoded_admin_path_is_refused_on_api_request(server, invoke) -> None:
    httpd, _ = server
    result = invoke("api-request", "bitbucket", "GET", "/rest/api/2/%61dmin/x")

    assert result.exit_code != 0, result.output
    assert httpd.calls == []


def test_legal_percent_encoded_path_still_reaches_the_server(server, invoke) -> None:
    httpd, _ = server
    httpd.response_body = json.dumps({"slug": REPOSITORY}).encode()
    path = f"{REPOSITORY_PATH}/browse/dir%20name/file.txt"
    result = invoke("api-get", "bitbucket", path)

    assert result.exit_code == 0, result.output
    assert len(httpd.calls) == 1
    target = urlsplit(httpd.calls[0][1]).path
    assert unquote(target) == f"{REPOSITORY_PATH}/browse/dir name/file.txt"
