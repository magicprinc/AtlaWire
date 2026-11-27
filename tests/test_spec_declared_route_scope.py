"""api_scope_20 — the generic REST entry points cannot leave the audited registry.

The audit's finding: `api-get` and `api-request GET` accepted any non-admin
`/rest/` path, guarded only by a segment denylist. A denylist cannot show that an
unregistered route only reads. The adopted rule is the narrower of the two
options: the generic commands may call a route the read-only registry already
declares, and nothing else.

These tests pin that rule from both sides: a declared route still works, an
undeclared one is refused before any request, and the refusals callers already
rely on are unchanged.
"""

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from click.testing import CliRunner

from atlawire.cli import cli
from atlawire.http import AtlaWireError
from atlawire.operations import list_operations, require_declared_route

TOKEN = "synthetic-scope-token"


@pytest.fixture
def server():
    """A loopback product that records every request and answers 200 JSON."""

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def _reply(self):
            self.server.calls.append(self.path)
            body = b'{"ok": true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        do_GET = _reply
        do_POST = _reply

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    httpd.calls = []
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd, f"http://127.0.0.1:{httpd.server_port}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


def _invoke(product, argv, base):
    return CliRunner().invoke(
        cli,
        [
            *argv,
            "--base-url",
            base,
            "--token-from-env",
            "--allow-http-loopback",
        ],
        env={
            f"ATLAWIRE_{product.upper()}_URL": base,
            f"ATLAWIRE_{product.upper()}_TOKEN": TOKEN,
        },
    )


def test_a_declared_route_is_still_reachable(server):
    """The narrowed rule must not break a route the registry already covers."""
    httpd, base = server
    declared = next(
        entry
        for entry in list_operations()
        if entry["product"] == "jira"
        and entry["method"] == "GET"
        and entry["path"] == "/rest/api/2/myself"
    )

    result = _invoke("jira", ["api-get", "jira", declared["path"]], base)

    assert result.exit_code == 0, result.output
    assert len(httpd.calls) == 1


def test_a_declared_route_matches_by_shape_not_by_placeholder(server):
    """A real key must satisfy the registry's `{projectIdOrKey}` spelling."""
    httpd, base = server

    result = _invoke("jira", ["api-get", "jira", "/rest/api/2/project/AB"], base)

    assert result.exit_code == 0, result.output
    assert httpd.calls == ["/rest/api/2/project/AB"]


def test_an_undeclared_route_is_refused_before_any_request(server):
    """The audit's case: a path no registry entry declares is a bypass."""
    httpd, base = server

    result = _invoke(
        "jira", ["api-get", "jira", "/rest/api/2/plugin/com.example/x"], base
    )

    assert result.exit_code == 1
    document = result.stdout
    assert "not declared in the read-only registry" in document
    assert httpd.calls == [], "an undeclared route must never reach the server"


def test_an_undeclared_post_is_refused_before_any_request(server):
    httpd, base = server

    result = _invoke(
        "jira",
        [
            "api-request",
            "jira",
            "POST",
            "/rest/api/2/plugin/com.example/hook",
            "--body",
            "{}",
        ],
        base,
    )

    assert result.exit_code == 1
    assert "not declared in the read-only registry" in result.stdout
    assert httpd.calls == []


def test_a_declared_semantic_post_is_still_reachable(server):
    """The four audited read-only POSTs keep working through api-request."""
    httpd, base = server

    result = _invoke(
        "jira",
        [
            "api-request",
            "jira",
            "POST",
            "/rest/api/2/search",
            "--body",
            '{"jql":"project = AB"}',
        ],
        base,
    )

    assert result.exit_code == 0, result.output
    assert len(httpd.calls) == 1


@pytest.mark.parametrize(
    "path",
    [
        "/rest/api/2/admin/probe",
        "/rest/api/2/auditing/probe",
        "/rest/api/2/screens/probe",
    ],
)
def test_the_admin_refusal_is_unchanged(server, path):
    """`api-get` has no --allow-admin, so an admin path keeps its own message."""
    httpd, base = server

    result = _invoke("jira", ["api-get", "jira", path], base)

    assert result.exit_code == 1
    assert "Administrative REST paths are not supported." in result.stdout
    assert httpd.calls == []


def test_the_gate_is_one_function_for_callers_to_read():
    """One gate, not a check each command re-implements."""
    with pytest.raises(AtlaWireError) as raised:
        require_declared_route("jira", "GET", "/rest/api/2/plugin/x", allow_admin=False)
    assert raised.value.category == "validation"
    assert "registry" in str(raised.value)

    # A declared route returns instead of raising.
    require_declared_route("jira", "GET", "/rest/api/2/project/AB", allow_admin=False)


def test_the_registry_census_is_reachable_through_the_same_rule():
    """Every declared route must satisfy the gate the generic commands use."""
    unreachable = []
    for entry in list_operations():
        try:
            require_declared_route(
                entry["product"],
                entry["method"],
                entry["path"],
                allow_admin=True,
            )
        except AtlaWireError:
            unreachable.append(entry["id"])
    assert unreachable == []
