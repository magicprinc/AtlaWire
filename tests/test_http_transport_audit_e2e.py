"""Installed-CLI checks for the bounded, strict-UTF-8 JSON transport.

Every response is produced by a synthetic loopback server; no test contacts a
real Jira or Bitbucket instance or uses a real credential.
"""

import gzip
import json
import subprocess
from http.server import BaseHTTPRequestHandler

from tests._loopback import Request, request_record, run_installed, send_bytes, serving

TOKEN = "fixture-transport-audit-token"
JSON_LIMIT = 8 * 1024 * 1024
JIRA_CONTEXT = "/jira"
MYSELF_PATH = f"{JIRA_CONTEXT}/rest/api/2/myself"
BITBUCKET_CONTEXT = "/bitbucket"
SEARCH_PATH = f"{BITBUCKET_CONTEXT}/rest/search/latest/search"
CAP_MESSAGE = "Error: The JSON response exceeds the 8 MiB limit.\n"


def environment(origin: str) -> dict[str, str]:
    """Point both products at the loopback server and keep Confluence inert."""
    return {
        "ATLAWIRE_JIRA_URL": f"{origin}{JIRA_CONTEXT}/",
        "ATLAWIRE_JIRA_TOKEN": TOKEN,
        "ATLAWIRE_BITBUCKET_URL": f"{origin}{BITBUCKET_CONTEXT}/",
        "ATLAWIRE_BITBUCKET_TOKEN": TOKEN,
        "ATLAWIRE_CONFLUENCE_URL": f"{origin}/wrong-confluence/",
        "ATLAWIRE_CONFLUENCE_TOKEN": "wrong-product-fixture",
    }


def _identity_with_pad(pad_size: int) -> bytes:
    """A valid ``/myself`` object padded to a known decoded size."""
    return b'{"name":"ada","displayName":"Ada","pad":"' + b"a" * pad_size + b'"}'


def _run_jira_me(
    body: bytes, encoding: str | None = None
) -> tuple[subprocess.CompletedProcess[str], list[Request]]:
    seen: list[Request] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            seen.append(request_record(self))
            send_bytes(
                self,
                200,
                body,
                content_type="application/json",
                content_encoding=encoding,
            )

    with serving(Handler) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        result = run_installed(
            ["jira-me", "--allow-http-loopback", "--token-from-env"],
            environment(origin),
        )
    return result, seen


def test_installed_cli_rejects_a_compressed_json_body_over_the_decoded_limit() -> None:
    # The wire body is a few KiB; only the decoded size crosses the cap.
    result, seen = _run_jira_me(gzip.compress(_identity_with_pad(JSON_LIMIT)), "gzip")

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == CAP_MESSAGE
    assert TOKEN not in result.stderr
    assert seen == [("GET", MYSELF_PATH, {}, f"Bearer {TOKEN}")]


def test_installed_cli_accepts_a_compressed_json_body_at_the_decoded_limit() -> None:
    prefix, suffix = b'{"name":"ada","displayName":"Ada","pad":"', b'"}'
    body = prefix + b"a" * (JSON_LIMIT - len(prefix) - len(suffix)) + suffix
    assert len(body) == JSON_LIMIT
    result, seen = _run_jira_me(gzip.compress(body), "gzip")

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "name": "ada",
        "displayName": "Ada",
        "email": None,
    }
    assert len(seen) == 1


def test_installed_cli_rejects_invalid_wire_utf8_in_a_json_response() -> None:
    result, seen = _run_jira_me(b'{"name":"ada","displayName":"x\xffy"}')

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == "Error: Expected UTF-8 JSON.\n"
    assert TOKEN not in result.stderr
    assert len(seen) == 1


def test_installed_cli_rejects_an_oversized_read_only_post_response() -> None:
    # Search uses the plugin's read-only POST; its response is capped the same way.
    seen: list[Request] = []
    body = gzip.compress(_identity_with_pad(JSON_LIMIT))

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_POST(self) -> None:
            seen.append(request_record(self))
            send_bytes(
                self,
                200,
                body,
                content_type="application/json",
                content_encoding="gzip",
            )

    with serving(Handler) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        result = run_installed(
            ["search", "Widget", "--allow-http-loopback", "--token-from-env"],
            environment(origin),
        )

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == CAP_MESSAGE
    assert seen == [("POST", SEARCH_PATH, {}, f"Bearer {TOKEN}")]
