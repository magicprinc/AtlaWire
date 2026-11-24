"""Every JSON command accepts --json; the flag changes output only where text is default."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from click.testing import CliRunner

from atlawire.catalog import build_command_catalog
from atlawire.cli import _JSON_FLAG_EXCEPTIONS, cli

TOKEN = "synthetic-json-flag-token"


def _catalog():
    with __import__("click").Context(cli) as context:
        return context.to_info_dict()["command"]["commands"]


def test_every_visible_command_takes_json_except_the_documented_exception():
    missing = []
    for name, body in _catalog().items():
        if body.get("hidden") is True:
            continue
        opts = {opt for param in body.get("params", []) for opt in param.get("opts", [])}
        if "--json" not in opts and name not in _JSON_FLAG_EXCEPTIONS:
            missing.append(name)

    assert missing == []
    assert _JSON_FLAG_EXCEPTIONS == frozenset({"attachment-get"})


@pytest.fixture
def server():
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def do_GET(self):
            self.server.calls.append(self.path)
            body = self.server.body
            self.send_response(200)
            self.send_header("Content-Type", self.server.content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    httpd.calls = []
    httpd.body = b"line one\r\nline two\r\n"
    httpd.content_type = "text/plain; charset=utf-8"
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
        env={"ATLAWIRE_BITBUCKET_TOKEN": TOKEN, "ATLAWIRE_CONFLUENCE_TOKEN": TOKEN},
    )


def test_file_json_prints_a_receipt_and_the_exact_text(server):
    _, base = server

    result = _invoke(base, ["file", "PRJ/repo", "dir/file.txt", "--json"])

    assert result.exit_code == 0, result.stderr
    document = json.loads(result.stdout)
    assert set(document) == {"path", "at", "bytes", "sha256", "text"}
    assert document["text"] == "line one\r\nline two\r\n"
    assert document["at"] is None
    assert document["bytes"] == len(b"line one\r\nline two\r\n")


def test_file_without_json_keeps_the_exact_bytes(server):
    httpd, base = server

    result = _invoke(base, ["file", "PRJ/repo", "dir/file.txt"])

    assert result.exit_code == 0, result.stderr
    assert result.stdout_bytes == httpd.body


PAGE = {
    "id": "1",
    "type": "page",
    "title": "T",
    "body": {"storage": {"value": "<p>x</p>"}},
    "_links": {"webui": "/pages/1"},
}


def test_page_url_json_wraps_the_same_url(server):
    httpd, base = server
    httpd.content_type = "application/json"
    httpd.body = json.dumps(PAGE).encode()

    plain = _invoke(base, ["page-url", "1"])
    wrapped = _invoke(base, ["page-url", "1", "--json"])

    assert plain.exit_code == wrapped.exit_code == 0, plain.stderr + wrapped.stderr
    assert json.loads(wrapped.stdout) == {"url": plain.stdout.strip()}


@pytest.mark.parametrize(
    "argv",
    [
        ["issue", "DEMO-1", "--json", "--markdown"],
        ["issue", "DEMO-1", "--json", "--wiki"],
        ["page", "1", "--json", "--markdown"],
        ["page", "1", "--json", "--storage"],
    ],
)
def test_json_refuses_a_conflicting_output_mode_before_any_request(argv, server):
    httpd, base = server

    result = _invoke(base, argv)

    assert result.exit_code == 2
    assert result.stdout == ""
    assert "not both" in result.stderr
    assert httpd.calls == []


def test_json_is_a_no_op_on_an_already_json_command():
    without = CliRunner().invoke(cli, ["operations"])
    with_flag = CliRunner().invoke(cli, ["operations", "--json"])

    assert with_flag.exit_code == without.exit_code == 0
    assert with_flag.stdout == without.stdout


def test_json_selects_json_where_tsv_is_the_default(server):
    httpd, base = server
    httpd.content_type = "application/json"
    httpd.body = json.dumps(
        {"values": [{"key": "A"}], "isLastPage": True}
    ).encode()

    with_flag = _invoke(base, ["projects", "--json"])
    without = _invoke(base, ["projects"])

    assert with_flag.exit_code == without.exit_code == 0, with_flag.stderr + without.stderr
    assert json.loads(with_flag.stdout)[0]["key"] == "A"
    assert without.stdout.startswith("# ") and "key\tname" in without.stdout
