"""Regression tests for the tester pass and the two owner feedback reports.

Each test names the report it pins. The loopback servers keep the evidence
observable without a deployment.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from click.testing import CliRunner

from atlawire.cli import cli

TOKEN = "synthetic-report-token"


def _server(reply):
    """Start one loopback product; ``reply(path)`` returns (status, body)."""

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def do_GET(self):
            self.server.calls.append(self.path)
            status, body = reply(self.path)
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        do_POST = do_GET

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    httpd.daemon_threads = True
    httpd.calls = []
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_port}"
    return httpd, thread, base


@pytest.fixture(scope="module")
def product_server():
    """One long-lived loopback product for the whole module.

    A server per test proved flaky on Windows: after several servers were
    created and shut down in one process, an occasional connection failed
    before reaching the handler. The product's own transport passed 30/30
    attempts against a single server, so the churn was the test harness, not
    the code under test. One stateless server removes the churn.
    """

    def jira_row():
        return {
            "key": "AB-1",
            "fields": {
                "summary": "one",
                "status": {"name": "Open"},
                "issuetype": {"name": "Bug"},
                "priority": {"name": "High"},
                "assignee": {"displayName": "Someone"},
                "updated": "2026-01-02T10:00:00.000+0300",
            },
        }

    def search_row():
        def line(text, highlighted=False):
            # The server marks a highlighted line with paired <em> markers.
            return {"line": 1, "text": f"<em>{text}</em>" if highlighted else text}

        return {
            "repository": {"slug": "widgets", "project": {"key": "AB"}},
            "file": "src/Widget.java",
            "hitCount": 2,
            "hitContexts": [
                [line("before one"), line("before two"), line("before three")],
                [line("class Widget {", highlighted=True), line("after two")],
            ],
        }

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def _reply(self):
            # Read the POST body before answering: a response on a connection
            # with an unread body is reset on some platforms, which looked like
            # an intermittent transport failure in the product under test.
            length = int(self.headers.get("Content-Length") or 0)
            if length:
                self.rfile.read(length)
            self.server.calls.append(self.path)
            if self.path.startswith("/rest/api/2/search"):
                document = {
                    "startAt": 0,
                    "maxResults": 1,
                    "total": 1740,
                    "issues": [jira_row()],
                }
            elif self.path.startswith("/rest/search/latest/search"):
                document = {"code": {"values": [search_row()], "isLastPage": True}}
            else:
                document = {}
            body = json.dumps(document).encode()
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
    httpd.daemon_threads = True
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


@pytest.fixture
def jira_search(product_server):
    return product_server


@pytest.fixture
def bitbucket_search(product_server):
    return product_server


def _invoke(product, argv, base, input_text=None):
    return CliRunner().invoke(
        cli,
        [*argv, "--base-url", base, "--token-from-env", "--allow-http-loopback"],
        env={
            f"ATLAWIRE_{product.upper()}_URL": base,
            f"ATLAWIRE_{product.upper()}_TOKEN": TOKEN,
        },
        input=input_text,
    )


def test_jql_json_keeps_the_server_total(jira_search):
    """total_lost_22: the server's total was dropped, so a cap looked complete."""
    _, base = jira_search

    result = _invoke("jira", ["jql", "project = AB", "--limit", "1", "--json"], base)

    assert result.exit_code == 0, result.output
    document = json.loads(result.stdout)
    assert document["total"] == 1740
    assert document["truncated"] is True
    assert len(document["rows"]) == 1
    assert "of 1740" in result.stderr


def test_jql_tsv_warns_about_truncation_on_stderr(jira_search):
    _, base = jira_search

    result = _invoke("jira", ["jql", "project = AB", "--limit", "1"], base)

    assert result.exit_code == 0, result.output
    assert result.stdout.splitlines()[0].startswith("# 1 row(s)")
    assert "of 1740" in result.stderr


def test_jql_refuses_json_with_fields(jira_search):
    """flag_collision_23: --json was silently ignored beside --fields."""
    httpd, base = jira_search
    before = len(httpd.calls)

    result = _invoke(
        "jira", ["jql", "project = AB", "--json", "--fields", "summary"], base
    )

    assert result.exit_code == 2
    assert "--json without --fields" in result.stderr
    assert len(httpd.calls) == before, "the refusal must happen before any request"


def test_jql_refuses_json_with_expand(jira_search):
    httpd, base = jira_search
    before = len(httpd.calls)

    result = _invoke(
        "jira", ["jql", "project = AB", "--json", "--expand", "renderedFields"], base
    )

    assert result.exit_code == 2
    assert len(httpd.calls) == before


def test_brief_catalog_is_small_and_keeps_every_name():
    """discovery_cost_24: the full catalog is several hundred kilobytes."""
    full = CliRunner().invoke(cli, ["--catalog"])
    brief = CliRunner().invoke(cli, ["--catalog", "--brief"])

    assert full.exit_code == brief.exit_code == 0
    assert len(full.stdout.encode()) > 100_000
    assert len(brief.stdout.encode()) < 40_000, "brief must be readable, not 'smaller'"

    document = json.loads(brief.stdout)
    full_document = json.loads(full.stdout)
    assert set(document["commands"]) == set(full_document["commands"])
    assert document["counts"]["operations"] == sum(
        len(ids) for ids in document["operations"].values()
    )
    # Every command is reduced to its help line; the schema is gone.
    assert all(
        isinstance(help_text, str) for help_text in document["commands"].values()
    )
    assert all(
        "parameters" not in entry for entry in full_document["commands"].values()
    ), "the fixture assumption about the full catalog changed"


def test_brief_does_not_open_credentials_or_the_network(monkeypatch, tmp_path):
    monkeypatch.setenv("BBK_CREDENTIALS", str(tmp_path / "absent.json"))

    result = CliRunner().invoke(cli, ["--catalog", "--brief"])

    assert result.exit_code == 0
    assert not (tmp_path / "absent.json").exists()


def test_search_context_flag_bounds_each_group(bitbucket_search):
    """bitbucket_search_context: context was 62% of a 69 KB payload."""
    _, base = bitbucket_search

    result = _invoke(
        "bitbucket",
        ["search", "Widget", "--limit", "1", "--json", "--context", "1"],
        base,
    )

    assert result.exit_code == 0, result.output
    rows = json.loads(result.stdout)
    assert [len(group) for group in rows[0]["context"]] == [1, 1]
    # The match evidence is never trimmed.
    assert rows[0]["hits"][0]["text"] == "class Widget {"
    assert rows[0]["matchEvidence"] == "highlight"


def test_search_context_zero_drops_surrounding_lines_only(bitbucket_search):
    _, base = bitbucket_search

    result = _invoke(
        "bitbucket",
        ["search", "Widget", "--limit", "1", "--json", "--context", "0"],
        base,
    )

    assert result.exit_code == 0, result.output
    rows = json.loads(result.stdout)
    assert rows[0]["context"] == [[], []]
    assert rows[0]["hits"]


def test_search_without_context_flag_is_unchanged(bitbucket_search):
    """The original, fuller payload must stay available."""
    _, base = bitbucket_search

    result = _invoke("bitbucket", ["search", "Widget", "--limit", "1", "--json"], base)

    assert result.exit_code == 0, result.output
    rows = json.loads(result.stdout)
    assert [len(group) for group in rows[0]["context"]] == [3, 2]


def test_search_context_flag_does_not_affect_the_summary_lane(bitbucket_search):
    _, base = bitbucket_search

    result = _invoke(
        "bitbucket", ["search", "Widget", "--limit", "1", "--context", "0"], base
    )

    assert result.exit_code == 0, result.output
    assert "src/Widget.java" in result.stdout
