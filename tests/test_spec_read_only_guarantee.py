"""The registry must never be able to change server state.

A GET is not proof of a read: Jira documents `GET /issue/{key}/subtask/move`,
which changes state. These tests pin both halves of the promise - every declared
operation is a read, and the one administrative escape hatch requires an explicit
opt-in.
"""

import importlib.util
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from click.testing import CliRunner

from atlawire import operations
from atlawire.cli import cli
from atlawire.http import AtlaWireError

ROOT = Path(__file__).resolve().parents[1]
ADMIN_SURFACE = ROOT / "src" / "atlawire" / "admin_operations.json"
TOKEN = "synthetic-read-only-token"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_declared_operation_is_provably_a_read():
    checker = _load("check_read_only", ROOT / "tools" / "check_read_only.py")

    assert checker.audit() == []


def test_no_operation_uses_a_write_method():
    methods = {str(item["method"]) for item in operations.list_operations()}

    assert methods <= {"GET", "POST"}


def test_the_only_posts_are_the_audited_semantic_reads():
    checker = _load("check_read_only", ROOT / "tools" / "check_read_only.py")
    posted = {
        str(item["id"])
        for item in operations.list_operations()
        if str(item["method"]) == "POST"
    }

    assert posted == set(checker.AUDITED_POSTS)


def test_the_state_changing_get_is_not_declared():
    """Jira documents `GET .../subtask/move`, which moves a subtask."""
    paths = {str(item["path"]) for item in operations.list_operations()}

    assert "/rest/api/2/issue/{issueIdOrKey}/subtask/move" not in paths


def test_the_generator_refused_the_dangerous_routes():
    deferred = json.loads(ADMIN_SURFACE.read_text(encoding="utf-8"))["deferred"]
    paths = {row["path"] for row in deferred}

    assert "/issue/{issueIdOrKey}/subtask/move" in paths
    assert all(row["reason"] for row in deferred)


def test_admin_surface_is_get_only():
    document = json.loads(ADMIN_SURFACE.read_text(encoding="utf-8"))

    assert {row["method"] for row in document["operations"]} == {"GET"}


def test_admin_operations_require_the_opt_in():
    admin = [item for item in operations.list_operations() if item["scope"] == "admin"]
    assert admin
    with pytest.raises(AtlaWireError) as caught:
        operations.read_operation(
            admin[0]["id"],
            "https://example.invalid",
            token=TOKEN,
            arguments={},
        )

    assert caught.value.category == "validation"
    assert "--allow-admin" in str(caught.value)


def test_a_read_operation_needs_no_opt_in():
    read = [item for item in operations.list_operations() if item["scope"] == "read"]
    assert read

    # Reaches the destination check only when the scope gate does not refuse it.
    with pytest.raises(AtlaWireError) as caught:
        operations.read_operation(
            read[0]["id"],
            "https://example.invalid",
            token=TOKEN,
            arguments={},
        )

    assert "--allow-admin" not in str(caught.value)


def test_describe_reports_the_scope():
    for described in operations.list_operations():
        assert described["scope"] in {"read", "admin"}, described["id"]


@pytest.fixture
def server():
    seen: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def do_GET(self):
            seen.append(self.path)
            body = b'{"ok": true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield seen, f"http://127.0.0.1:{httpd.server_port}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


def test_allow_admin_makes_the_request_and_nothing_else(server):
    """The opt-in opens the read; it does not change the method or add a body."""
    seen, base = server
    admin = next(
        item for item in operations.list_operations() if item["scope"] == "admin"
    )

    operations.read_operation(
        admin["id"],
        base,
        token=TOKEN,
        arguments={},
        allow_http_loopback=True,
        allow_admin=True,
    )

    assert len(seen) == 1


def test_cli_refuses_an_admin_operation_without_the_flag(server):
    seen, base = server
    admin = next(
        item for item in operations.list_operations() if item["scope"] == "admin"
    )

    result = CliRunner().invoke(
        cli,
        [
            "read",
            admin["id"],
            "--params",
            "{}",
            "--base-url",
            base,
            "--token-from-env",
            "--allow-http-loopback",
        ],
        env={"ATLAWIRE_BITBUCKET_URL": base, "ATLAWIRE_BITBUCKET_TOKEN": TOKEN},
    )

    assert result.exit_code == 2
    assert "--allow-admin" in result.stdout
    assert seen == []


def test_cli_reads_an_admin_operation_with_the_flag(server):
    seen, base = server
    admin = next(
        item
        for item in operations.list_operations()
        if item["scope"] == "admin" and item["product"] == "bitbucket"
    )

    result = CliRunner().invoke(
        cli,
        [
            "read",
            admin["id"],
            "--params",
            "{}",
            "--base-url",
            base,
            "--token-from-env",
            "--allow-http-loopback",
            "--allow-admin",
        ],
        env={"ATLAWIRE_BITBUCKET_URL": base, "ATLAWIRE_BITBUCKET_TOKEN": TOKEN},
    )

    assert result.exit_code == 0, result.stdout
    assert len(seen) == 1
