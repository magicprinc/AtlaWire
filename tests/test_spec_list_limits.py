"""List commands accept --limit and stop at it; without it they are unchanged."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest
from click.testing import CliRunner

from atlawire import bitbucket
from atlawire.cli import cli
from atlawire.http import AtlaWireError

TOKEN = "synthetic-limit-token"


@pytest.fixture
def server():
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def do_GET(self):
            parsed = urlsplit(self.path)
            query = parse_qs(parsed.query)
            self.server.calls.append((parsed.path, query))
            values, last, next_start = self.server.pages.pop(0)
            requested = int(query.get("limit", ["100"])[0])
            values = values[:requested]
            body = {"values": values, "isLastPage": last}
            if next_start is not None:
                body["nextPageStart"] = next_start
            payload = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    httpd.calls = []
    httpd.pages = []
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd, f"http://127.0.0.1:{httpd.server_port}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


def _invoke(base, argv):
    return CliRunner().invoke(
        cli,
        [*argv, "--base-url", base, "--token-from-env", "--allow-http-loopback"],
        env={"ATLAWIRE_BITBUCKET_TOKEN": TOKEN},
    )


def test_repos_accepts_limit_and_stops_at_it(server):
    httpd, base = server
    httpd.pages = [([{"slug": "a"}, {"slug": "b"}, {"slug": "c"}], True, None)]

    result = _invoke(base, ["repos", "PRJ", "--json", "--limit", "2"])

    assert result.exit_code == 0, result.stderr
    rows = json.loads(result.stdout)
    assert [row["slug"] for row in rows] == ["a", "b"]


def test_repos_without_limit_returns_every_row(server):
    httpd, base = server
    httpd.pages = [([{"slug": "a"}, {"slug": "b"}, {"slug": "c"}], True, None)]

    result = _invoke(base, ["repos", "PRJ", "--json"])

    assert result.exit_code == 0, result.stderr
    assert len(json.loads(result.stdout)) == 3


@pytest.mark.parametrize(
    "command",
    [
        ["projects"],
        ["repos", "PRJ"],
        ["branches", "PRJ/repo"],
        ["files", "PRJ/repo"],
        ["ls", "PRJ/repo"],
        ["commit-changes", "PRJ/repo", "abcdef1"],
        ["pr", "PRJ/repo", "1", "comments"],
        ["pr", "PRJ/repo", "1", "commits"],
    ],
)
def test_each_list_command_documents_limit(command):
    result = CliRunner().invoke(cli, [*command, "--help"])

    assert result.exit_code == 0, result.stderr
    assert "--limit" in result.output


def test_the_library_rejects_a_non_positive_limit():
    with pytest.raises(AtlaWireError, match="row limit"):
        bitbucket.list_projects("https://example.invalid", token=TOKEN, limit=0)
    with pytest.raises(AtlaWireError, match="row limit"):
        bitbucket.list_repositories(
            "https://example.invalid", "PRJ", token=TOKEN, limit=True
        )
