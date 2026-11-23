"""Black-box security contracts for credential echo and administrative paths.

Every scenario drives the real CLI against a loopback server. Assertions come
from the exit status, the captured stdout/stderr and the server's request log,
so no test reads an internal counter, monkeypatches a guard or sends a real
request outside 127.0.0.1.

Three contracts are pinned down here:

* a successful JSON payload that echoes the bearer token must never reach
  stdout/stderr on the canonical ``read`` path or on ``api-get``/``api-request``
  (the legacy ``read-operation`` path already refused it);
* the same three commands must still succeed on a payload that does not echo
  the token and return its data, so a decoder that always fails cannot satisfy
  the suite;
* every administrative route segment, plain or percent-encoded, must be
  refused before any HTTP request, while a legal route whose name merely
  contains ``admin`` as a substring still reaches the server.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import cast
from urllib.parse import unquote, urlsplit

import pytest
from click.testing import CliRunner, Result

from atlawire.cli import cli

TOKEN = "synthetic-echo-check-token"
PROJECT = "PROJ"
REPOSITORY = "repo"
REPOSITORY_PATH = f"/rest/api/1.0/projects/{PROJECT}/repos/{REPOSITORY}"
CLEAN_PAYLOAD = {"slug": REPOSITORY, "name": "clean-repository"}

ECHO_REFUSAL = "The response contained the session bearer token."
ADMIN_REFUSAL = "Administrative REST paths are not supported."
UNSAFE_PATH_REFUSAL = "Expected a safe standard REST path."

# Contract snapshot of the administrative route policy: each segment belongs
# to an administrative or system REST route that the CLI must refuse. The list
# is spelled out here instead of imported from the implementation, so dropping
# a segment from the guard cannot silently shrink this test.
ADMIN_SEGMENTS = (
    "admin",
    "application-properties",
    "applicationrole",
    "audit",
    "auditing",
    "cluster",
    "issuesecurityschemes",
    "issuetypescheme",
    "license",
    "logs",
    "mail-server",
    "notificationscheme",
    "permissions",
    "permissionscheme",
    "priorityschemes",
    "reindex",
    "screens",
    "settings",
    "workflow",
    "workflows",
    "workflowscheme",
)


def _first_char_encoded(segment: str) -> str:
    """Percent-encode the first character, the way ``%61dmin`` names ``admin``."""
    return f"%{ord(segment[0]):02x}{segment[1:]}"


ADMIN_CASES = tuple(
    pytest.param(f"/rest/api/2/{segment}/probe", id=segment)
    for segment in ADMIN_SEGMENTS
) + tuple(
    pytest.param(
        f"/rest/api/2/{_first_char_encoded(segment)}/probe",
        id=f"{segment}-encoded",
    )
    for segment in ADMIN_SEGMENTS
)


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
    # The short poll interval keeps per-test teardown near-instant; the default
    # half second per test dominates the runtime of a large parametrized matrix.
    thread = threading.Thread(target=httpd.serve_forever, args=(0.01,), daemon=True)
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


def _error_document(result: Result) -> dict[str, object]:
    """Return the single JSON error object printed by the CLI."""
    assert result.stdout.strip(), result.output
    document = json.loads(result.stdout)
    assert document["ok"] is False, document
    error = document["error"]
    assert isinstance(error, dict), error
    return error


READ_ARGV = (
    "read",
    "bitbucket.repository.get",
    "--params",
    json.dumps({"projectKey": PROJECT, "repositorySlug": REPOSITORY}),
)
API_GET_ARGV = ("api-get", "bitbucket", REPOSITORY_PATH)
API_REQUEST_ARGV = ("api-request", "bitbucket", "GET", REPOSITORY_PATH)


@pytest.mark.parametrize(
    ("argv", "exit_code"),
    [
        pytest.param(READ_ARGV, 2, id="read"),
        pytest.param(API_GET_ARGV, 1, id="api-get"),
        pytest.param(API_REQUEST_ARGV, 1, id="api-request"),
    ],
)
def test_successful_payload_echoing_token_never_reaches_the_caller(
    server, invoke, argv, exit_code
) -> None:
    httpd, _ = server
    result = invoke(*argv)

    # The request itself succeeded; the refusal must happen on the payload.
    assert len(httpd.calls) == 1
    assert result.exit_code == exit_code, result.output
    error = _error_document(result)
    assert error["status"] is None
    assert error["code"] == "validation_error"
    assert error["classification"] == "client_error"
    assert error["message"] == ECHO_REFUSAL
    assert TOKEN not in result.stdout
    assert TOKEN not in result.stderr


@pytest.mark.parametrize(
    ("argv", "wrapped"),
    [
        pytest.param(READ_ARGV, True, id="read"),
        pytest.param(API_GET_ARGV, False, id="api-get"),
        pytest.param(API_REQUEST_ARGV, False, id="api-request"),
    ],
)
def test_clean_payload_reaches_the_caller(server, invoke, argv, wrapped) -> None:
    httpd, _ = server
    httpd.response_body = json.dumps(CLEAN_PAYLOAD).encode()
    result = invoke(*argv)

    assert result.exit_code == 0, result.output
    assert len(httpd.calls) == 1
    document = json.loads(result.stdout)
    if wrapped:
        assert document == {
            "ok": True,
            "product": "bitbucket",
            "data": CLEAN_PAYLOAD,
        }
    else:
        assert document == CLEAN_PAYLOAD
    assert TOKEN not in result.stdout


@pytest.mark.parametrize("path", ADMIN_CASES)
def test_every_admin_segment_is_refused_before_any_request(
    server, invoke, path
) -> None:
    httpd, _ = server
    result = invoke("api-get", "bitbucket", path)

    assert httpd.calls == []
    assert result.exit_code == 1, result.output
    error = _error_document(result)
    assert error["status"] is None
    assert error["code"] == "validation_error"
    assert error["classification"] == "client_error"
    assert error["message"] == ADMIN_REFUSAL


@pytest.mark.parametrize(
    ("path", "message"),
    [
        pytest.param("/rest/api/2/%61dmin/x", ADMIN_REFUSAL, id="encoded-admin"),
        pytest.param(
            "/rest/api/2/foo/%2e%2e/%2e%2e/x",
            UNSAFE_PATH_REFUSAL,
            id="encoded-traversal",
        ),
        pytest.param(
            "/rest/api/2/%2561dmin/x",
            ADMIN_REFUSAL,
            id="double-encoded-admin",
        ),
        pytest.param(
            "/rest/api/2/foo/%252e%252e/%252e%252e/x",
            UNSAFE_PATH_REFUSAL,
            id="double-encoded-traversal",
        ),
    ],
)
def test_encoded_admin_path_is_refused_before_any_request(
    server, invoke, path, message
) -> None:
    httpd, _ = server
    result = invoke("api-get", "bitbucket", path)

    assert httpd.calls == []
    assert result.exit_code == 1, result.output
    error = _error_document(result)
    assert error["code"] == "validation_error"
    assert error["classification"] == "client_error"
    assert error["message"] == message


def test_encoded_admin_path_is_refused_on_api_request(server, invoke) -> None:
    httpd, _ = server
    result = invoke("api-request", "bitbucket", "GET", "/rest/api/2/%61dmin/x")

    assert httpd.calls == []
    assert result.exit_code == 1, result.output
    error = _error_document(result)
    assert error["code"] == "validation_error"
    assert error["classification"] == "client_error"
    assert error["message"] == ADMIN_REFUSAL


@pytest.mark.parametrize(
    "leaf",
    ["my-admin-file.txt", "administrator-notes"],
    ids=["mid-name-substring", "prefixed-segment"],
)
def test_legal_path_containing_admin_substring_reaches_the_server(
    server, invoke, leaf
) -> None:
    httpd, _ = server
    httpd.response_body = json.dumps(CLEAN_PAYLOAD).encode()
    path = f"{REPOSITORY_PATH}/browse/{leaf}"
    result = invoke("api-get", "bitbucket", path)

    assert result.exit_code == 0, result.output
    assert len(httpd.calls) == 1
    assert json.loads(result.stdout) == CLEAN_PAYLOAD
    target = unquote(urlsplit(httpd.calls[0][1]).path)
    assert target == path


def test_legal_percent_encoded_path_still_reaches_the_server(server, invoke) -> None:
    httpd, _ = server
    httpd.response_body = json.dumps({"slug": REPOSITORY}).encode()
    path = f"{REPOSITORY_PATH}/browse/dir%20name/file.txt"
    result = invoke("api-get", "bitbucket", path)

    assert result.exit_code == 0, result.output
    assert len(httpd.calls) == 1
    target = urlsplit(httpd.calls[0][1]).path
    assert unquote(target) == f"{REPOSITORY_PATH}/browse/dir name/file.txt"
