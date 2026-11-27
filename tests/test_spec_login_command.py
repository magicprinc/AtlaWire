"""`login` stores one token without ever printing it, and never loses others."""

import json
import os
import pathlib
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from click.testing import CliRunner

from atlawire import cli as cli_module
from atlawire.cli import cli
from atlawire.credentials import load_saved_credentials, save_credentials
from atlawire.http import AtlaWireError

TOKEN = "synthetic-login-token-abc"
OTHER = "synthetic-other-product-token"
JIRA_URL = "https://jira.example.com"
SOURCE = pathlib.Path(__file__).resolve().parents[1] / "src"


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
    # One probe of the token page, then exactly one identity read: the prompt
    # must not send anything else to the product.
    assert len(httpd.calls) == 2
    assert httpd.calls[0].startswith("/secure/ViewProfile.jspa")
    assert httpd.calls[1] == "/rest/api/2/myself"
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


def test_a_piped_stdin_is_refused_instead_of_blocking(credentials_file):
    """Real subprocess: a hidden prompt cannot read a pipe, so it must not try.

    On Windows ``getpass`` goes to the console even when stdin is a pipe, so
    without this guard the command waits forever. The timeout turns a
    regression into a failure instead of a hang.
    """
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(SOURCE)
    environment["BBK_CREDENTIALS"] = str(credentials_file)

    completed = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "atlawire",
            "login",
            "--product",
            "jira",
            "--base-url",
            JIRA_URL,
            "--no-verify",
        ],
        input=f"{TOKEN}\n",
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
        timeout=120,
        check=False,
    )

    assert completed.returncode != 0
    assert "interactive terminal" in completed.stderr
    assert TOKEN not in completed.stdout
    assert TOKEN not in completed.stderr
    assert not credentials_file.exists()


@pytest.mark.parametrize(
    ("product", "path"),
    [
        (
            "jira",
            (
                "/secure/ViewProfile.jspa?selectedTab="
                "com.atlassian.pats.pats-plugin:jira-user-personal-access-tokens"
            ),
        ),
        ("confluence", "/plugins/personalaccesstokens/usertokens.action"),
        ("bitbucket", "/plugins/servlet/access-tokens/manage"),
    ],
)
def test_the_token_page_url_keeps_the_deployment_context_path(product, path):
    """A context path such as /jira must survive, exactly as other reads keep it."""
    assert (
        cli_module.token_page_url("https://host.example.com/jira", product)
        == f"https://host.example.com/jira{path}"
    )


def test_a_trailing_slash_does_not_double_the_separator():
    assert (
        cli_module.token_page_url("https://host.example.com/", "confluence")
        == "https://host.example.com/plugins/personalaccesstokens/usertokens.action"
    )


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (200, "open it in your browser"),
        (401, "needs your browser session"),
        (403, "needs your browser session"),
        (302, "login redirect"),
        (404, "no token page at this address"),
        (500, "unexpected status"),
    ],
)
def test_the_page_status_is_reported_as_a_fixed_sentence(status, expected):
    """A wrong URL is visible immediately; no server text is echoed."""
    assert expected in cli_module._classify_token_page(status)


def test_print_url_answers_without_a_prompt_or_a_terminal(
    credentials_file, monkeypatch
):
    """The agent path: print the link and exit, even with a piped stdin."""
    monkeypatch.setattr(cli_module, "describe_token_page", lambda url: "HTTP 302 — ok")

    completed = subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "atlawire",
            "login",
            "--product",
            "bitbucket",
            "--base-url",
            JIRA_URL,
            "--print-url",
        ],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={
            **os.environ,
            "PYTHONPATH": str(SOURCE),
            "BBK_CREDENTIALS": str(credentials_file),
        },
        timeout=120,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["product"] == "bitbucket"
    assert payload["url"].endswith("/plugins/servlet/access-tokens/manage")
    assert "https://jira.example.com" in payload["url"]
    assert not credentials_file.exists()
