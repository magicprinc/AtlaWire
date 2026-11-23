"""Installed-CLI loopback tests for library-backed api-request and read.

``api-request`` reads its URL/token pair from the product environment;
``read`` uses the saved-file loader for the canonical agent-facing path. Every
response, credential and server is synthetic.
"""

import json
import subprocess
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from tests._loopback import (
    Request,
    request_record,
    run_installed,
    send_bytes,
    send_json,
    serving,
)
from tests.test_read_slice_cli_e2e import saved_credentials

TOKEN = "synthetic-api-request-token-2f7"
CONTEXTS = {"jira": "/jira", "confluence": "/confluence", "bitbucket": "/bitbucket"}
SENTINEL = "API-REQUEST-SENTINEL"
MISSING = Path(__file__).with_name("bbk-credentials-missing-sdk-cli.json")


def environment(origin: str, *, product: str = "jira") -> dict[str, str]:
    """Give only the selected product a valid loopback pair."""
    environment = {"BBK_CREDENTIALS": str(MISSING)}
    for name, context in CONTEXTS.items():
        valid = name == product
        environment[f"ATLAWIRE_{name.upper()}_URL"] = (
            f"{origin}{context}/" if valid else f"{origin}/wrong-{name}/"
        )
        environment[f"ATLAWIRE_{name.upper()}_TOKEN"] = (
            TOKEN if valid else "wrong-product"
        )
    return environment


def run(
    path: str, method: str, *, body: str | None = None, product: str = "jira"
) -> tuple[object, list[Request], list[bytes]]:
    seen: list[Request] = []
    bodies: list[bytes] = []

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            seen.append(request_record(self))
            send_json(self, 200, {"ok": True})

        def do_POST(self) -> None:
            seen.append(request_record(self))
            length = int(self.headers.get("Content-Length") or "0")
            bodies.append(self.rfile.read(length))
            send_json(self, 200, {"ok": True})

    with serving(Handler) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        args = [
            "api-request",
            product,
            method,
            path,
            "--token-from-env",
            "--allow-http-loopback",
        ]
        if body is not None:
            args += ["--body", body]
        result = run_installed(args, environment(origin, product=product))
    return result, seen, bodies


def test_api_request_get_uses_library_and_bearer() -> None:
    result, seen, _ = run("/rest/api/2/myself", "GET")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"ok": True}
    assert seen == [
        ("GET", f"{CONTEXTS['jira']}/rest/api/2/myself", {}, f"Bearer {TOKEN}")
    ]


def test_api_request_read_only_post_sends_json_body() -> None:
    body = '{"jql":"order by created DESC","maxResults":1}'
    result, seen, bodies = run("/rest/api/2/search", "POST", body=body)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"ok": True}
    assert seen == [
        ("POST", f"{CONTEXTS['jira']}/rest/api/2/search", {}, f"Bearer {TOKEN}")
    ]
    assert json.loads(bodies[0]) == {
        "jql": "order by created DESC",
        "maxResults": 1,
    }


def test_api_request_read_only_conversion_post_is_allowed() -> None:
    body = '{"value":"<p>x</p>","representation":"storage"}'
    result, seen, bodies = run(
        "/rest/api/contentbody/convert/view",
        "POST",
        body=body,
        product="confluence",
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"ok": True}
    assert seen == [
        (
            "POST",
            "/confluence/rest/api/contentbody/convert/view",
            {},
            f"Bearer {TOKEN}",
        )
    ]
    assert json.loads(bodies[0]) == {
        "value": "<p>x</p>",
        "representation": "storage",
    }


def test_api_request_rejects_conversion_post_under_the_wrong_product() -> None:
    body = '{"value":"<p>x</p>","representation":"storage"}'
    result, seen, bodies = run("/rest/api/contentbody/convert/view", "POST", body=body)
    assert result.returncode == 1
    envelope = json.loads(result.stdout)
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "validation_error"
    assert seen == []
    assert bodies == []


def test_api_request_rejects_a_mutating_post_before_a_request() -> None:
    result, seen, bodies = run("/rest/api/2/issue", "POST", body='{"fields":{}}')
    assert result.returncode == 1
    envelope = json.loads(result.stdout)
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "validation_error"
    assert seen == []
    assert bodies == []


def test_api_request_error_contains_status_and_original_body() -> None:
    seen: list[Request] = []

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            seen.append(request_record(self))
            send_bytes(
                self,
                401,
                json.dumps({"message": SENTINEL}).encode(),
                content_type="application/json",
            )

    with serving(Handler) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        result = run_installed(
            [
                "api-request",
                "jira",
                "GET",
                "/rest/api/2/myself",
                "--token-from-env",
                "--allow-http-loopback",
            ],
            environment(origin),
        )

    assert result.returncode == 1
    envelope = json.loads(result.stdout)
    assert envelope["ok"] is False
    assert envelope["error"]["status"] == 401
    assert envelope["error"]["classification"] == "authentication"
    assert envelope["error"]["body_json"] == {"message": SENTINEL}
    assert len(seen) == 1


def run_canonical_read(
    tmp_path: Path,
    on_get: Callable[[BaseHTTPRequestHandler], None],
    *arguments: str,
) -> tuple[subprocess.CompletedProcess[str], list[Request]]:
    """Run ``read`` through the saved-file loader against one loopback server."""
    seen: list[Request] = []

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            seen.append(request_record(self))
            on_get(self)

    with serving(Handler) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        result = run_installed(
            ["read", *arguments, "--allow-http-loopback"],
            saved_credentials(tmp_path, origin),
        )
    return result, seen


def _interrupted_body(handler: BaseHTTPRequestHandler, prefix: bytes) -> None:
    """Declare more bytes than are sent, then close the connection."""
    handler.send_response(200)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(prefix) + 64))
    handler.end_headers()
    handler.wfile.write(prefix)
    handler.wfile.flush()
    handler.close_connection = True


def test_canonical_json_read_reports_an_interrupted_body_as_one_error(
    tmp_path: Path,
) -> None:
    prefix = b'{"partial":'

    def on_get(handler: BaseHTTPRequestHandler) -> None:
        _interrupted_body(handler, prefix)

    result, seen = run_canonical_read(
        tmp_path,
        on_get,
        "jira.project.get",
        "--params",
        '{"projectIdOrKey":"DEMO"}',
    )

    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    assert result.stdout.count("\n") == 1
    envelope = json.loads(result.stdout)
    assert envelope["ok"] is False
    assert envelope["error"]["status"] == 200
    assert envelope["error"]["code"] == "transport_error"
    assert envelope["error"]["body"] is None
    assert prefix.decode("ascii") not in result.stdout
    assert [record[1] for record in seen] == ["/jira/rest/api/2/project/DEMO"]


def test_canonical_json_read_rejects_a_non_finite_number_in_one_error(
    tmp_path: Path,
) -> None:
    def on_get(handler: BaseHTTPRequestHandler) -> None:
        send_bytes(handler, 200, b'{"value": 1e999}', content_type="application/json")

    result, seen = run_canonical_read(
        tmp_path,
        on_get,
        "jira.project.get",
        "--params",
        '{"projectIdOrKey":"DEMO"}',
    )

    assert result.returncode == 1
    envelope = json.loads(result.stdout)
    assert envelope["ok"] is False
    assert envelope["error"]["status"] == 200
    assert envelope["error"]["code"] == "invalid_response"
    assert "Infinity" not in result.stdout
    assert len(seen) == 1


def test_canonical_binary_read_rejects_partial_content_without_publishing(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "avatar.png"

    def on_get(handler: BaseHTTPRequestHandler) -> None:
        send_bytes(
            handler,
            206,
            b"partial",
            content_type="application/octet-stream",
            extra_headers={"Content-Range": "bytes 0-6/64"},
        )

    result, seen = run_canonical_read(
        tmp_path,
        on_get,
        "jira.avatar.system",
        "--params",
        '{"type":"user"}',
        "--out",
        str(destination),
    )

    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    envelope = json.loads(result.stdout)
    assert envelope["ok"] is False
    assert envelope["error"]["status"] == 206
    assert envelope["error"]["code"] == "invalid_response"
    assert envelope["error"]["classification"] == "partial_content"
    assert "data" not in envelope
    assert not destination.exists()
    assert list(tmp_path.glob("*.part")) == []
    assert [record[1] for record in seen] == ["/jira/rest/api/2/avatar/user/system"]


def test_canonical_binary_read_reports_an_interrupted_body_as_one_error(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "avatar.png"
    prefix = b"PRIVATE-BINARY-PREFIX"

    def on_get(handler: BaseHTTPRequestHandler) -> None:
        _interrupted_body(handler, prefix)

    result, seen = run_canonical_read(
        tmp_path,
        on_get,
        "jira.avatar.system",
        "--params",
        '{"type":"user"}',
        "--out",
        str(destination),
    )

    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    assert result.stdout.count("\n") == 1
    envelope = json.loads(result.stdout)
    assert envelope["ok"] is False
    assert envelope["error"]["status"] == 200
    assert envelope["error"]["code"] == "transport_error"
    assert "data" not in envelope
    assert not destination.exists()
    assert list(tmp_path.glob("*.part")) == []
    assert prefix.decode("ascii") not in result.stdout
    assert prefix.decode("ascii") not in result.stderr
    assert len(seen) == 1
