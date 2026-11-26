"""`login` stores one token without ever printing it, and never loses others."""

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from click.testing import CliRunner

from atlawire.cli import cli
from atlawire.credentials import load_saved_credentials, save_credentials
from atlawire.http import AtlaWireError

TOKEN = "synthetic-login-token-abc"
OTHER = "synthetic-other-product-token"
JIRA_URL = "https://jira.example.com"


@pytest.fixture
def credentials_file(tmp_path, monkeypatch):
    path = tmp_path / "credentials.json"
    monkeypatch.setenv("BBK_CREDENTIALS", str(path))
    return path


def test_save_keeps_entries_for_other_products_and_unrelated_keys(credentials_file):
    """Saving one product must not delete another product's token."""
    credentials_file.write_text(
        json.dumps(
            {
                "jira_url": JIRA_URL,
                "jira_token": OTHER,
                "user": "someone",
            }
        ),
        encoding="utf-8",
    )

    save_credentials("confluence", "https://confluence.example.com", TOKEN)

    document = json.loads(credentials_file.read_text(encoding="utf-8"))
    assert document == {
        "jira_url": JIRA_URL,
        "jira_token": OTHER,
        "user": "someone",
        "confluence_url": "https://confluence.example.com",
        "confluence_token": TOKEN,
    }


def test_a_saved_pair_loads_back_through_the_reader(credentials_file):
    """A written pair satisfies the same validation the read commands apply."""
    save_credentials("jira", JIRA_URL, TOKEN)

    loaded = load_saved_credentials("jira", allow_http_loopback=False)

    assert loaded.base_url == JIRA_URL
    assert loaded.token == TOKEN


def test_an_unreadable_document_is_refused_not_overwritten(credentials_file):
    """Another product's token may be inside; refusal beats silent data loss."""
    credentials_file.write_text("{ not json", encoding="utf-8")

    with pytest.raises(AtlaWireError):
        save_credentials("jira", JIRA_URL, TOKEN)

    assert credentials_file.read_text(encoding="utf-8") == "{ not json"


def test_an_invalid_token_is_refused_before_the_file_is_touched(credentials_file):
    with pytest.raises(AtlaWireError):
        save_credentials("jira", JIRA_URL, "not a token\n")

    assert not credentials_file.exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits")
def test_the_saved_file_is_owner_only(credentials_file):
    save_credentials("jira", JIRA_URL, TOKEN)

    assert credentials_file.stat().st_mode & 0o777 == 0o600


def test_login_never_prints_the_token(credentials_file):
    """The whole point: hidden input, and no echo anywhere in the output."""
    result = CliRunner().invoke(
        cli,
        ["login", "--product", "jira", "--base-url", JIRA_URL, "--no-verify"],
        input=f"{TOKEN}\n",
    )

    assert result.exit_code == 0, result.output
    assert TOKEN not in result.output
    assert TOKEN not in result.stderr
    document = json.loads(credentials_file.read_text(encoding="utf-8"))
    assert document["jira_token"] == TOKEN
    receipt = json.loads(result.stdout)
    assert receipt["ok"] is True
    assert receipt["verified"] is False


@pytest.fixture
def jira_server():
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def do_GET(self):
            self.server.calls.append(self.path)
            if self.headers.get("Authorization") != f"Bearer {TOKEN}":
                status, body = 401, b'{"errorMessages":["unauthorized"]}'
            else:
                status, body = (
                    200,
                    json.dumps({"name": "someone", "displayName": "Someone"}).encode(),
                )
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

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


def test_login_verifies_the_token_before_saving(credentials_file, jira_server):
    """A working token is proven by the documented identity read, then saved."""
    httpd, base = jira_server

    result = CliRunner().invoke(
        cli,
        [
            "login",
            "--product",
            "jira",
            "--base-url",
            base,
            "--allow-http-loopback",
        ],
        input=f"{TOKEN}\n",
    )

    assert result.exit_code == 0, result.output
    assert TOKEN not in result.output
    assert httpd.calls == ["/rest/api/2/myself"]
    document = json.loads(credentials_file.read_text(encoding="utf-8"))
    assert document["jira_token"] == TOKEN
    assert json.loads(result.stdout)["verified"] is True


def test_a_rejected_token_is_not_saved(credentials_file, jira_server):
    """A failing verification leaves the credentials file absent."""
    _, base = jira_server

    result = CliRunner().invoke(
        cli,
        [
            "login",
            "--product",
            "jira",
            "--base-url",
            base,
            "--allow-http-loopback",
        ],
        input="wrong-token\n",
    )

    assert result.exit_code != 0
    assert not credentials_file.exists()
    assert "wrong-token" not in result.output
