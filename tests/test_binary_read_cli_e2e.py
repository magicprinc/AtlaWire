"""Installed-CLI loopback contracts for binary reads.

The response bytes are written to an explicit destination and reported with a
receipt. Nothing is published on failure, and an existing file is never
overwritten.
"""

import hashlib
import json
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from tests._loopback import Request, request_record, run_installed, send_bytes, serving
from tests.test_read_slice_cli_e2e import saved_credentials

PNG = b"\x89PNG\r\n\x1a\n" + bytes(range(64))
RAW = b"line one\nline two\x00binary\xff\n"


def _handler(
    seen: list[Request],
    body: bytes,
    status: int = 200,
    before_send: Callable[[], None] | None = None,
):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            seen.append(request_record(self))
            if before_send is not None:
                before_send()
            send_bytes(self, status, body, content_type="application/octet-stream")

    return Handler


def test_binary_read_writes_exact_bytes_and_a_receipt(tmp_path: Path) -> None:
    seen: list[Request] = []
    destination = tmp_path / "avatar.png"
    with serving(_handler(seen, PNG)) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        result = run_installed(
            [
                "read",
                "jira.avatar.system",
                "--params",
                '{"type":"user"}',
                "--out",
                str(destination),
                "--allow-http-loopback",
            ],
            saved_credentials(tmp_path, origin),
        )

    assert result.returncode == 0, result.stdout
    envelope = json.loads(result.stdout)
    assert envelope["ok"] is True
    assert envelope["product"] == "jira"
    assert envelope["data"] == {
        "path": str(destination),
        "bytes": len(PNG),
        "sha256": hashlib.sha256(PNG).hexdigest(),
        "content_type": "application/octet-stream",
    }
    assert destination.read_bytes() == PNG
    assert seen == [
        (
            "GET",
            "/jira/rest/api/2/avatar/user/system",
            {},
            "Bearer synthetic-read-jira-3a3",
        )
    ]


def test_binary_read_never_overwrites_an_existing_file(tmp_path: Path) -> None:
    destination = tmp_path / "archive.zip"
    destination.write_bytes(b"keep me")
    seen: list[Request] = []
    with serving(_handler(seen, b"new")) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        result = run_installed(
            [
                "read",
                "bitbucket.repository.archive",
                "--params",
                '{"projectKey":"DEMO","repositorySlug":"repo"}',
                "--out",
                str(destination),
                "--allow-http-loopback",
            ],
            saved_credentials(tmp_path, origin),
        )

    assert result.returncode == 2
    assert json.loads(result.stdout)["error"]["code"] == "validation_error"
    assert destination.read_bytes() == b"keep me"
    assert seen == []


def test_binary_read_does_not_replace_a_file_created_during_publication(
    tmp_path: Path,
) -> None:
    # Absent during the CLI's early check, created while the body streams:
    # publishing must refuse and leave the competitor's bytes untouched.
    destination = tmp_path / "avatar.png"
    seen: list[Request] = []
    handler = _handler(
        seen,
        PNG,
        before_send=lambda: destination.write_bytes(b"competing"),
    )
    with serving(handler) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        result = run_installed(
            [
                "read",
                "jira.avatar.system",
                "--params",
                '{"type":"user"}',
                "--out",
                str(destination),
                "--allow-http-loopback",
            ],
            saved_credentials(tmp_path, origin),
        )

    # A destination conflict is a local validation failure, as it already is
    # for a file present before the request: one JSON error and no receipt.
    assert result.returncode == 2
    envelope = json.loads(result.stdout)
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "validation_error"
    assert "already exists" in envelope["error"]["message"]
    assert "data" not in envelope
    assert destination.read_bytes() == b"competing"
    assert list(tmp_path.glob("*.part")) == []
    assert seen == [
        (
            "GET",
            "/jira/rest/api/2/avatar/user/system",
            {},
            "Bearer synthetic-read-jira-3a3",
        )
    ]


def test_binary_read_over_the_limit_leaves_no_file(tmp_path: Path) -> None:
    destination = tmp_path / "raw.bin"
    seen: list[Request] = []
    with serving(_handler(seen, b"x" * 4096)) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        result = run_installed(
            [
                "read",
                "bitbucket.repository.raw",
                "--params",
                '{"projectKey":"DEMO","repositorySlug":"repo"}',
                "--out",
                str(destination),
                "--max-bytes",
                "1024",
                "--allow-http-loopback",
            ],
            saved_credentials(tmp_path, origin),
        )

    assert result.returncode == 1
    envelope = json.loads(result.stdout)
    assert envelope["error"]["code"] == "invalid_response"
    assert not destination.exists()
    assert list(tmp_path.glob("*.part")) == []


def test_binary_operation_without_out_is_a_usage_error(tmp_path: Path) -> None:
    seen: list[Request] = []
    with serving(_handler(seen, b"x")) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        result = run_installed(
            [
                "read",
                "jira.avatar.system",
                "--params",
                '{"type":"user"}',
                "--allow-http-loopback",
            ],
            saved_credentials(tmp_path, origin),
        )

    assert result.returncode == 2
    assert json.loads(result.stdout)["error"]["code"] == "validation_error"
    assert seen == []


def test_jira_attachment_content_downloads_to_a_file(tmp_path: Path) -> None:
    payload = b"attachment body \x00\x01"
    seen: list[Request] = []
    destination = tmp_path / "attachment.bin"
    with serving(_handler(seen, payload)) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        result = run_installed(
            [
                "read",
                "jira.attachment.content",
                "--params",
                '{"id":"10001"}',
                "--out",
                str(destination),
                "--allow-http-loopback",
            ],
            saved_credentials(tmp_path, origin),
        )

    assert result.returncode == 0, result.stdout
    assert destination.read_bytes() == payload
    assert seen == [
        (
            "GET",
            "/jira/rest/api/2/attachment/10001/content",
            {},
            "Bearer synthetic-read-jira-3a3",
        )
    ]
