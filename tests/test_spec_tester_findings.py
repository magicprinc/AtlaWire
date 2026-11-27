"""Regression tests for the defects the live tester found.

Each test pins one finding so it cannot come back silently. They are offline: the
assertion is on the registry the tools read, not on a live answer.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from atlawire import operations

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = {entry["id"]: entry for entry in operations.list_operations()}
SYNTHETIC_TOKEN = "synthetic-findings-token"
IMAGE_BYTES = b"\x89PNG\r\n\x1a\n fake avatar"


@pytest.fixture
def loopback():
    """One loopback product that records each request and answers like the server."""

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def _reply(self, body: bytes, content_type: str) -> None:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            self.server.calls.append(
                {"method": "GET", "path": self.path, "headers": dict(self.headers)}
            )
            # An image route refuses the JSON Accept the shared session sends.
            if self.headers.get("Accept") == "application/json":
                self.send_response(406)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self._reply(IMAGE_BYTES, "image/png")

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length)
            self.server.calls.append(
                {
                    "method": "POST",
                    "path": self.path,
                    "headers": dict(self.headers),
                    "body": body,
                }
            )
            self._reply(b'{"issues": []}', "application/json")

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    httpd.calls = []
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_port}"
    try:
        yield httpd, base
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


def _field(operation_id: str, name: str) -> dict[str, object]:
    operation = REGISTRY[operation_id]
    for field in operation["query"] + operation["body"]:
        if field["name"] == name:
            return field
    raise AssertionError(f"{operation_id} does not declare {name}")


@pytest.mark.parametrize(
    ("operation_id", "name"),
    [
        ("bitbucket.admin.groups.more-members", "context"),
        ("bitbucket.admin.groups.more-non-members", "context"),
        ("bitbucket.admin.users.more-members", "context"),
        ("bitbucket.admin.users.more-non-members", "context"),
        ("bitbucket.projects.projectkey.repos.repositoryslug.changes", "until"),
        ("bitbucket.projects.projectkey.repos.repositoryslug.diff.path", "until"),
        (
            (
                "bitbucket.projects.projectkey.repos.repositoryslug"
                ".pull-requests.pullrequestid.comments"
            ),
            "path",
        ),
        ("bitbucket.repository.commit-comments", "path"),
        ("confluence.search", "cql"),
    ],
)
def test_a_parameter_the_server_requires_is_marked_required(operation_id, name):
    """D1: the deployment refuses these without the parameter; the registry said optional."""
    assert _field(operation_id, name)["required"] is True


def test_the_bare_raw_route_is_not_declared_as_a_query_read():
    """D2: `/raw?path=` answers 400; only `/raw/{path:.*}` serves a file."""
    raw = REGISTRY["bitbucket.repository.raw"]
    assert raw["path"].endswith("/raw/{path:.*}")
    assert raw["response"]["kind"] == "binary"
    assert "path" not in {field["name"] for field in raw["query"]}
    assert "path" in {argument["name"] for argument in raw["arguments"]}


def test_the_worklog_body_field_is_the_one_the_server_accepts():
    """D3: `issueIds` is rejected with 'Unrecognized field'; `ids` is accepted."""
    body = REGISTRY["jira.worklog.list"]["body"]
    assert [field["name"] for field in body] == ["ids"]
    assert body[0]["required"] is True


def test_memberof_declares_the_exactly_one_rule():
    """D4: sending both key and username answers 400 on the deployment."""
    rules = REGISTRY["confluence.user.memberof"]["query_rules"]
    assert rules["exactly_one"] == ["key", "username"]


def test_a_post_read_is_reachable_from_the_library_entry_point(loopback):
    """D8: a POST used to raise 'requires the library transport' for a library caller."""
    httpd, base = loopback

    result = operations.read_operation(
        "jira.search.post",
        base,
        token=SYNTHETIC_TOKEN,
        arguments={},
        body={"jql": "project = DEMO"},
        allow_http_loopback=True,
    )

    assert result == {"issues": []}
    assert httpd.calls[0]["method"] == "POST"
    assert json.loads(httpd.calls[0]["body"]) == {"jql": "project = DEMO"}


def test_the_binary_reader_states_what_it_accepts(loopback, tmp_path):
    """D5: an image route answers 406 to the JSON Accept the session sends."""
    httpd, base = loopback
    destination = tmp_path / "avatar.png"

    operations.read_binary(
        "bitbucket.project.avatar",
        base,
        token=SYNTHETIC_TOKEN,
        arguments={"projectKey": "AB"},
        destination=str(destination),
        allow_http_loopback=True,
    )

    assert httpd.calls[0]["headers"].get("Accept") == "*/*"
    assert destination.read_bytes() == IMAGE_BYTES


def test_a_wildcard_file_route_is_never_declared_as_json():
    """The generator must defer `/raw/{path:.*}`; kind json would parse a file as JSON."""
    manifest = json.loads(
        (ROOT / "src" / "atlawire" / "manifest.json").read_text(encoding="utf-8")
    )
    offenders = [
        entry["id"]
        for entry in manifest["operations"]
        if "/raw/" in entry["path"] and entry["path"].endswith("{path:.*}")
    ]
    assert offenders == []


def test_a_binary_operation_is_refused_by_the_json_reader():
    """D10: a binary route answers 406 to a JSON Accept; refuse before the request.

    The JSON reader used to fall through to a JSON read for `kind: binary`, so a
    working download reported a transport error. The refusal must name the entry
    point that does work.
    """
    from atlawire.http import AtlaWireError

    binary = [
        entry for entry in REGISTRY.values() if entry["response"]["kind"] == "binary"
    ]
    assert binary, "no binary operation to test"

    for entry in binary:
        with pytest.raises(AtlaWireError) as raised:
            operations.read_operation(
                entry["id"],
                "https://example.invalid",
                token="synthetic-token",
                arguments={},
            )
        assert raised.value.category == "validation"
        assert "read_binary" in str(raised.value)


def test_every_registered_route_is_declared_once():
    """A duplicate declaration is how a broken route hid behind a working one."""
    seen = {}
    for entry in REGISTRY.values():
        key = (entry["product"], entry["method"], entry["path"])
        seen.setdefault(key, []).append(entry["id"])
    duplicates = {key: ids for key, ids in seen.items() if len(ids) > 1}
    assert duplicates == {}
