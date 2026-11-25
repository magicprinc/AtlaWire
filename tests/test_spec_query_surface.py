"""The query surface the deployments document must be reachable through `read`.

`read` rejects every undeclared query name, so before this merge a documented
parameter such as Bitbucket's `name` or Jira's `expand` was unreachable through
the typed surface. These checks pin the merge, its precedence rule, its bounds,
and the freshness of the generated file.
"""

import importlib.util
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from atlawire import operations
from atlawire.http import AtlaWireError

ROOT = Path(__file__).resolve().parents[1]
SURFACE = ROOT / "src" / "atlawire" / "query_params.json"
TOKEN = "synthetic-query-surface-token"


def _load_builder():
    spec = importlib.util.spec_from_file_location(
        "build_query_surface", ROOT / "tools" / "build_query_surface.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def server():
    seen: list[dict[str, list[str]]] = []

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def do_GET(self):
            seen.append(parse_qs(urlsplit(self.path).query, keep_blank_values=True))
            body = b'{"values": [], "isLastPage": true}'
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


def test_committed_surface_is_the_regenerated_file():
    builder = _load_builder()

    assert builder.render(builder.build()) == SURFACE.read_text(encoding="utf-8")


def test_every_surface_entry_targets_a_registered_operation():
    document = json.loads(SURFACE.read_text(encoding="utf-8"))
    registered = {item["id"] for item in operations.list_operations()}

    orphans = sorted(set(document["operations"]) - registered)

    assert orphans == [], f"surface entries for unknown operations: {orphans[:5]}"


def test_every_surface_entry_is_actually_declared():
    """A generated row that the merge dropped would be a silent regression."""
    document = json.loads(SURFACE.read_text(encoding="utf-8"))
    declared = {
        item["id"]: {field["name"] for field in item["query"]}  # type: ignore[union-attr]
        for item in operations.list_operations()
    }

    missing = [
        f"{operation_id}:{row['name']}"
        for operation_id, rows in document["operations"].items()
        for row in rows
        if str(row["name"]) not in declared.get(operation_id, set())
    ]

    assert missing == [], f"documented but not declared: {missing[:5]}"


def test_a_documented_parameter_is_accepted_by_read(server):
    """The gap this closes: `name` is documented by Bitbucket and now usable."""
    seen, base = server

    operations.read_operation(
        "bitbucket.projects",
        base,
        token=TOKEN,
        arguments={},
        query={"name": "widgets"},
        allow_http_loopback=True,
    )

    assert seen[0]["name"] == ["widgets"]


def test_an_integer_parameter_is_validated_locally():
    with pytest.raises(AtlaWireError) as caught:
        operations.read_operation(
            "bitbucket.projects",
            "https://example.invalid",
            token=TOKEN,
            arguments={},
            query={"limit": "not-a-number"},
            allow_http_loopback=False,
        )

    assert caught.value.category == "validation"


def test_a_generated_text_parameter_rejects_controls():
    with pytest.raises(AtlaWireError):
        operations.read_operation(
            "bitbucket.projects",
            "https://example.invalid",
            token=TOKEN,
            arguments={},
            query={"name": "bad\x00name"},
            allow_http_loopback=False,
        )


def test_no_operation_declares_one_parameter_twice():
    """A merge that appended a name already declared would break validation."""
    duplicated: list[str] = []
    for described in operations.list_operations():
        names = [str(field["name"]) for field in described["query"]]  # type: ignore[union-attr]
        repeated = {name for name in names if names.count(name) > 1}
        if repeated:
            duplicated.append(f"{described['id']}: {sorted(repeated)}")

    assert duplicated == []


def test_hand_written_fields_keep_their_source_label():
    """Generated rows are marked, so the precedence rule is observable."""
    described = operations.describe_operation("bitbucket.projects")
    fields = {field["name"]: field["source"] for field in described["query"]}  # type: ignore[union-attr]

    assert "name" in fields
    assert set(fields.values()) <= {"atlawire", "server-wadl"}
    assert all(
        field["source"] in {"atlawire", "server-wadl"}
        for described in operations.list_operations()
        for field in described["query"]  # type: ignore[union-attr]
    )


def test_an_unregistered_operation_id_in_the_surface_is_ignored():
    """A stale entry must not create an operation out of nothing."""
    assert operations._query_surface().keys() <= {
        item["id"] for item in operations.list_operations()
    }


def test_no_route_declares_an_empty_parameter_name():
    document = json.loads(SURFACE.read_text(encoding="utf-8"))

    bad = [
        operation_id
        for operation_id, rows in document["operations"].items()
        for row in rows
        if not str(row.get("name") or "").strip()
    ]

    assert bad == []
