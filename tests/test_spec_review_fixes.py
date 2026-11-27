"""Regression tests for the findings of the independent audit.

Each test names the defect it pins. The bug cases must fail before the fix and
pass after it; the loopback servers keep the evidence observable without a
deployment.
"""

import json
import os
import stat
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from click.testing import CliRunner

from atlawire import cli as cli_module
from atlawire import credentials as credentials_module
from atlawire.cli import cli

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "synthetic-review-token"
ENVELOPE_KEYS = {
    "status",
    "code",
    "classification",
    "message",
    "path",
    "content_type",
    "body",
    "body_json",
    "body_truncated",
}


def _server(handler_route):
    """Start one loopback server; ``handler_route`` maps a request to a reply."""

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def do_GET(self):
            self.server.calls.append(
                {
                    "path": self.path,
                    "headers": dict(self.headers),
                }
            )
            status, headers, body = handler_route(self.path)
            self.send_response(status)
            for name, value in headers.items():
                self.send_header(name, value)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    httpd.calls = []
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    return httpd, thread, base


@pytest.fixture
def revision_server():
    """A download route whose bytes depend on the requested revision."""

    def route(path):
        query = parse_qs(urlsplit(path).query)
        revision = (query.get("at") or ["default"])[0]
        return (
            200,
            {"Content-Type": "application/octet-stream"},
            f"bytes:{revision}".encode(),
        )

    httpd, thread, base = _server(route)
    try:
        yield httpd, base
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


@pytest.fixture
def option_server():
    """A route that echoes which options the caller actually sent."""

    def route(path):
        query = parse_qs(urlsplit(path).query)
        rendered = "|".join(
            f"{name}={values[0]}" for name, values in sorted(query.items())
        )
        return 200, {"Content-Type": "application/octet-stream"}, rendered.encode()

    httpd, thread, base = _server(route)
    try:
        yield httpd, base
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


def _invoke(argv, base, env_token=TOKEN):
    return CliRunner().invoke(
        cli,
        [*argv, "--base-url", base, "--token-from-env", "--allow-http-loopback"],
        env={
            "ATLAWIRE_BITBUCKET_URL": base,
            "ATLAWIRE_BITBUCKET_TOKEN": env_token,
        },
    )


def test_a_raw_download_honours_the_pinned_revision(revision_server, tmp_path):
    """binary_8: `at` was advertised but dropped, so a pinned read fetched HEAD."""
    httpd, base = revision_server
    destination = tmp_path / "raw.bin"

    result = _invoke(
        [
            "read",
            "bitbucket.repository.raw",
            "--params",
            '{"projectKey":"AB","repositorySlug":"widgets","path":"dir/file.txt"}',
            "--query",
            '{"at":"deadbeef"}',
            "--out",
            str(destination),
        ],
        base,
    )

    assert result.exit_code == 0, result.output
    assert destination.read_bytes() == b"bytes:deadbeef"
    assert len(httpd.calls) == 1
    assert parse_qs(urlsplit(httpd.calls[0]["path"]).query) == {"at": ["deadbeef"]}


def test_an_archive_download_forwards_its_declared_options(option_server, tmp_path):
    """binary_8: `format`, `path` and `prefix` were accepted, then discarded."""
    httpd, base = option_server
    destination = tmp_path / "repo.tar"

    result = _invoke(
        [
            "read",
            "bitbucket.repository.archive",
            "--params",
            '{"projectKey":"AB","repositorySlug":"widgets"}',
            "--query",
            '{"format":"tar","prefix":"pkg"}',
            "--out",
            str(destination),
        ],
        base,
    )

    assert result.exit_code == 0, result.output
    assert destination.read_bytes() == b"format=tar|prefix=pkg"
    assert parse_qs(urlsplit(httpd.calls[0]["path"]).query) == {
        "format": ["tar"],
        "prefix": ["pkg"],
    }


def test_an_avatar_download_forwards_its_size(option_server, tmp_path):
    """binary_8: the avatar `s` size was accepted, then discarded."""
    httpd, base = option_server
    destination = tmp_path / "avatar.png"

    result = _invoke(
        [
            "read",
            "bitbucket.project.avatar",
            "--params",
            '{"projectKey":"AB"}',
            "--query",
            '{"s":64}',
            "--out",
            str(destination),
        ],
        base,
    )

    assert result.exit_code == 0, result.output
    assert destination.read_bytes() == b"s=64"
    assert parse_qs(urlsplit(httpd.calls[0]["path"]).query) == {"s": ["64"]}


def test_a_download_without_options_sends_no_query(option_server, tmp_path):
    """The forwarding fix must not send an empty query object."""
    httpd, base = option_server
    destination = tmp_path / "plain.bin"

    result = _invoke(
        [
            "read",
            "bitbucket.repository.raw",
            "--params",
            '{"projectKey":"AB","repositorySlug":"widgets","path":"dir/file.txt"}',
            "--out",
            str(destination),
        ],
        base,
    )

    assert result.exit_code == 0, result.output
    assert destination.read_bytes() == b""
    assert parse_qs(urlsplit(httpd.calls[0]["path"]).query) == {}


def test_a_binary_read_rejects_an_undeclared_option(tmp_path):
    """The forwarded query still goes through the registry allowlist."""
    result = _invoke(
        [
            "read",
            "bitbucket.repository.archive",
            "--params",
            '{"projectKey":"AB","repositorySlug":"widgets"}',
            "--query",
            '{"undeclaredOption":"x"}',
            "--out",
            str(tmp_path / "never.bin"),
        ],
        "https://example.invalid",
    )

    assert result.exit_code == 2
    assert json.loads(result.stdout)["error"]["code"] == "validation_error"
    assert not (tmp_path / "never.bin").exists()


def test_read_operation_missing_required_option_is_a_json_usage_error():
    """errors_15: the legacy command printed text on stderr and no document."""
    result = CliRunner().invoke(cli, ["read-operation", "jira.project.get"])

    assert result.exit_code == 2
    document = json.loads(result.stdout)
    assert document["ok"] is False
    assert set(document["error"]) == ENVELOPE_KEYS
    assert document["error"]["code"] == "validation_error"


def test_read_operation_unknown_option_is_a_json_usage_error():
    result = CliRunner().invoke(
        cli,
        ["read-operation", "jira.project.get", "--params", "{}", "--raw"],
    )

    assert result.exit_code == 2
    assert json.loads(result.stdout)["error"]["code"] == "validation_error"


def test_api_get_malformed_params_is_a_json_usage_error():
    """errors_15: a local typo was reported as a read failure with no document."""
    result = CliRunner().invoke(
        cli,
        [
            "api-get",
            "jira",
            "/rest/api/2/myself",
            "--params",
            "not-json",
            "--base-url",
            "https://example.invalid",
            "--token-from-env",
        ],
        env={"ATLAWIRE_JIRA_TOKEN": TOKEN},
    )

    assert result.exit_code == 2
    document = json.loads(result.stdout)
    assert set(document["error"]) == ENVELOPE_KEYS
    assert document["error"]["code"] == "validation_error"


def test_api_request_malformed_body_is_a_json_usage_error():
    result = CliRunner().invoke(
        cli,
        [
            "api-request",
            "jira",
            "POST",
            "/rest/api/2/search",
            "--body",
            "not-json",
            "--base-url",
            "https://example.invalid",
            "--token-from-env",
        ],
        env={"ATLAWIRE_JIRA_TOKEN": TOKEN},
    )

    assert result.exit_code == 2
    assert json.loads(result.stdout)["error"]["code"] == "validation_error"


def test_a_missing_environment_token_exits_two():
    """errors_15: the token half of the pair answered 1 while the URL half answers 2."""
    result = CliRunner().invoke(
        cli,
        ["jira-me", "--base-url", "https://jira.example.invalid", "--token-from-env"],
        env={"ATLAWIRE_JIRA_TOKEN": ""},
    )

    assert result.exit_code == 2, result.output
    assert "ATLAWIRE_JIRA_TOKEN" in result.output


def test_an_existing_credentials_directory_keeps_its_mode(tmp_path, monkeypatch):
    """credentials_5: saving changed the mode of a directory it did not create."""
    shared = tmp_path / "shared"
    shared.mkdir(mode=0o755)
    target = shared / "credentials.json"
    monkeypatch.setenv("BBK_CREDENTIALS", str(target))

    restricted = []
    monkeypatch.setattr(
        credentials_module.os,
        "chmod",
        lambda path, mode: restricted.append((Path(path), mode)),
    )

    credentials_module.save_credentials("jira", "https://jira.example.com", TOKEN)

    assert all(path != shared for path, _ in restricted), restricted
    assert json.loads(target.read_text(encoding="utf-8"))["jira_token"] == TOKEN


def test_a_new_credentials_directory_is_created_private(tmp_path, monkeypatch):
    target = tmp_path / "private" / "credentials.json"
    monkeypatch.setenv("BBK_CREDENTIALS", str(target))

    credentials_module.save_credentials("jira", "https://jira.example.com", TOKEN)

    if os.name == "nt":
        pytest.skip("Windows expresses the boundary through the profile ACL")
    mode = stat.S_IMODE(target.parent.stat().st_mode)
    assert mode & 0o077 == 0, oct(mode)
    assert stat.S_IMODE(target.stat().st_mode) & 0o077 == 0


@pytest.fixture
def page_server():
    """A landing page that answers 302 and records every request."""

    def route(path):
        return 302, {"Location": "/login"}, b""

    httpd, thread, base = _server(route)
    try:
        yield httpd, base
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


def test_print_url_makes_no_request(page_server):
    """login_9: `--print-url` probed the deployment before printing."""
    httpd, base = page_server

    result = CliRunner().invoke(
        cli,
        [
            "login",
            "--product",
            "bitbucket",
            "--base-url",
            base,
            "--print-url",
            "--allow-http-loopback",
        ],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["url"].endswith(
        "/plugins/servlet/access-tokens/manage"
    )
    assert httpd.calls == []


def test_an_insecure_base_url_is_refused_before_the_probe(page_server):
    """login_9: a plain-HTTP URL was probed and printed instead of refused."""
    httpd, base = page_server

    result = CliRunner().invoke(
        cli,
        ["login", "--product", "bitbucket", "--base-url", base, "--print-url"],
    )

    assert result.exit_code != 0
    assert httpd.calls == []
    assert "HTTPS" in result.stderr


def test_the_page_probe_does_not_follow_a_redirect(page_server):
    httpd, base = page_server

    line = cli_module.describe_token_page(
        f"{base}/plugins/servlet/access-tokens/manage"
    )

    assert "login redirect" in line
    assert len(httpd.calls) == 1


def test_the_page_probe_ignores_ambient_netrc(page_server, tmp_path, monkeypatch):
    """login_9: a plain session applies .netrc credentials to the probe."""
    httpd, base = page_server
    netrc = tmp_path / ".netrc"
    netrc.write_text(
        "machine 127.0.0.1\n  login synthetic-user\n  password synthetic-pass\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    cli_module.describe_token_page(f"{base}/plugins/servlet/access-tokens/manage")

    # A plain `requests.get` would have sent Basic credentials from .netrc.
    assert len(httpd.calls) == 1
    assert "Authorization" not in httpd.calls[0]["headers"]


def test_the_readme_matches_the_shipped_registry():
    """docs_4: the status block quoted numbers from an older registry."""
    from atlawire.catalog import build_command_catalog
    from atlawire.operations import list_operations

    operations = list_operations()
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    expected = {
        "registered operations": len(operations),
        "visible commands": len(build_command_catalog(cli)["commands"]),
        "required inventory rows": json.loads(
            (ROOT / ".development" / "rest-inventory.json").read_text(encoding="utf-8")
        )["totals"]["required"],
    }
    for label, value in expected.items():
        assert str(value) in readme, f"README omits the current {label}: {value}"


def test_the_readme_does_not_deny_the_tracked_ci_workflow():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert (ROOT / ".github" / "workflows" / "ci.yml").is_file()
    assert "No CI workflow is configured" not in readme


def test_the_quickstart_does_not_deny_an_advertised_flag():
    """docs_4: `projects`/`repos --limit` exists while the guide said it does not."""
    from atlawire.catalog import build_command_catalog

    catalog = build_command_catalog(cli)["commands"]
    for name in ("projects", "repos"):
        options = {
            option
            for param in catalog[name]["params"]
            for option in (param.get("opts") or [])
        }
        assert "--limit" in options, f"{name} no longer takes --limit"

    guide = (ROOT / "docs" / "AGENT-QUICKSTART.md").read_text(encoding="utf-8")
    assert "not `--limit`" not in guide


def test_no_document_claims_that_nothing_is_written():
    """docs_4: `login` and `--out` write files, so an absolute claim is false."""
    claims = (
        "Nothing is written to local storage",
        "none of them writes",
        "No local file is written",
    )
    for name in ("README.md", "docs/AGENT-QUICKSTART.md", "docs/API.md"):
        text = (ROOT / name).read_text(encoding="utf-8")
        for claim in claims:
            assert claim not in text, f"{name} still claims: {claim}"


def test_the_api_reference_counts_match_the_registry():
    """docs_4: the reference quoted an older census in two separate places."""
    from atlawire.operations import list_operations

    operations = list_operations()
    with_query = sum(1 for entry in operations if entry.get("query"))
    fields = sum(len(entry["query"]) for entry in operations)
    api_doc = (ROOT / "docs" / "API.md").read_text(encoding="utf-8")

    assert f"**{len(operations)} операций**" in api_doc
    assert f"**{with_query} операций**" in api_doc
    assert f"({fields} поля)" in api_doc


def test_the_bbk_table_matches_the_committed_parity_evidence():
    """parity_10: the report said `worse 0` while the JSON recorded two."""
    parity = json.loads(
        (ROOT / "checks" / "live_tester_bbk_parity.json").read_text(
            encoding="utf-8-sig"
        )
    )
    report = (ROOT / "checks" / "TEST-FINDINGS.md").read_text(encoding="utf-8")

    assert parity["summary"]["worse"] > 0, "the fixture no longer records a regression"
    assert f"| worse | {parity['summary']['worse']} |" in report
