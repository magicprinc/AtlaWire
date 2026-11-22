"""Installed-CLI loopback security checks for the ``jira-me`` command.

Every response and credential is synthetic. The tests cover numeric and word
tokens that coincide with Click diagnostics or with default JSON escaping: such
ordinary output is kept, while a decoded response that actually echoes a
distinctive token is still rejected. Success controls prove ordinary output and
messages still appear.
"""

import json
import subprocess
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from tests._loopback import (
    Request,
    request_record,
    run_installed,
    send_bytes,
    serving,
)

CONTEXT = "/jira"
MYSELF_PATH = f"{CONTEXT}/rest/api/2/myself"
SENTINEL = "JIRA-ME-SECURITY-SENTINEL"
MISSING_BBK_CREDENTIALS = str(
    Path(__file__).with_name("bbk-credentials-missing-jira-me-security.json")
)


def identity(display_name: str) -> dict[str, object]:
    return {
        "name": "ada",
        "displayName": display_name,
        "emailAddress": "ada@example.invalid",
    }


def projected(display_name: str) -> dict[str, object]:
    return {
        "name": "ada",
        "displayName": display_name,
        "email": "ada@example.invalid",
    }


def utf8_json(payload: object) -> bytes:
    """Send actual UTF-8 JSON without ASCII escaping."""
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def environment(origin: str, token: str) -> dict[str, str]:
    return {
        "ATLAWIRE_JIRA_URL": f"{origin}{CONTEXT}/",
        "ATLAWIRE_JIRA_TOKEN": token,
        "ATLAWIRE_BITBUCKET_URL": f"{origin}/wrong-bitbucket/",
        "ATLAWIRE_BITBUCKET_TOKEN": "wrong-product-fixture",
        "ATLAWIRE_CONFLUENCE_URL": f"{origin}/wrong-confluence/",
        "ATLAWIRE_CONFLUENCE_TOKEN": "wrong-product-fixture",
        "BBK_CREDENTIALS": MISSING_BBK_CREDENTIALS,
    }


def run_me(
    token: str, *, status: int = 200, body: bytes = b"{}"
) -> tuple[subprocess.CompletedProcess[str], list[Request], list[str]]:
    """Run ``jira-me`` against one synthetic identity response."""
    seen: list[Request] = []
    extra_methods: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            seen.append(request_record(self))
            send_bytes(self, status, body, content_type="application/json")

        def _refuse(self, method: str) -> None:
            extra_methods.append(method)
            self.send_error(405)

        def do_POST(self) -> None:
            self._refuse("POST")

        def do_PUT(self) -> None:
            self._refuse("PUT")

        def do_DELETE(self) -> None:
            self._refuse("DELETE")

        def do_PATCH(self) -> None:
            self._refuse("PATCH")

        def do_HEAD(self) -> None:
            self._refuse("HEAD")

        def do_OPTIONS(self) -> None:
            self._refuse("OPTIONS")

    with serving(Handler) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        result = run_installed(
            ["jira-me", "--token-from-env", "--allow-http-loopback"],
            environment(origin, token),
        )
    return result, seen, extra_methods


def expected_requests(token: str) -> list[Request]:
    return [("GET", MYSELF_PATH, {}, f"Bearer {token}")]


def test_the_bbk_credentials_override_is_a_missing_synthetic_path() -> None:
    assert "missing-jira-me-security" in MISSING_BBK_CREDENTIALS
    assert not Path(MISSING_BBK_CREDENTIALS).exists()


def test_installed_jira_me_keeps_a_403_token_in_the_status_diagnostic() -> None:
    token = "403"
    body = json.dumps({"message": SENTINEL}).encode("utf-8")
    result, seen, extra = run_me(token, status=403, body=body)

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr.strip() == "Error: HTTP 403: access denied."
    assert SENTINEL not in result.stderr
    assert seen == expected_requests(token)
    assert extra == []


def test_installed_jira_me_keeps_a_json_token_in_a_malformed_response() -> None:
    token = "JSON"
    result, seen, extra = run_me(token, body=b"{")

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr.strip() == "Error: Expected a valid JSON response."
    assert seen == expected_requests(token)
    assert extra == []


def test_installed_jira_me_keeps_an_error_token_in_a_failure_diagnostic() -> None:
    token = "Error"
    result, seen, extra = run_me(token, status=404, body=b"{}")

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr.strip() == "Error: HTTP 404: request failed."
    assert seen == expected_requests(token)
    assert extra == []


def test_installed_jira_me_keeps_the_normal_403_diagnostic_for_a_safe_token() -> None:
    token = "fixture-jira-me-security-token"
    result, seen, extra = run_me(token, status=403, body=b"{}")

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr.strip() == "Error: HTTP 403: access denied."
    assert token not in result.stderr
    assert seen == expected_requests(token)
    assert extra == []


def test_installed_jira_me_keeps_the_normal_json_diagnostic_for_a_safe_token() -> None:
    token = "fixture-jira-me-security-token"
    result, seen, extra = run_me(token, body=b"{")

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr.strip() == "Error: Expected a valid JSON response."
    assert token not in result.stderr
    assert seen == expected_requests(token)
    assert extra == []


def test_installed_jira_me_prints_a_serialized_u1234_escape_normally() -> None:
    # The adapter accepts raw U+1234. Default json.dumps turns it into the
    # literal "\u1234", which is ordinary serialization; the command prints it.
    token = "u1234"
    body = utf8_json(identity("\u1234"))
    assert token.encode("ascii") not in body

    result, seen, extra = run_me(token, body=body)

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == projected("\u1234")
    assert "\\u1234" in result.stdout
    assert seen == expected_requests(token)
    assert extra == []


def test_installed_jira_me_prints_a_u1235_identity_success_control() -> None:
    token = "u1234"
    body = utf8_json(identity("\u1235"))
    assert token.encode("ascii") not in body

    result, seen, extra = run_me(token, body=body)

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == projected("\u1235")
    assert "\\u1235" in result.stdout
    assert token not in result.stdout
    assert seen == expected_requests(token)
    assert extra == []


def test_installed_jira_me_keeps_normal_output_for_a_safe_token() -> None:
    token = "fixture-jira-me-security-token"
    body = utf8_json(identity("Ada Lovelace"))

    result, seen, extra = run_me(token, body=body)

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == projected("Ada Lovelace")
    assert token not in result.stdout
    assert seen == expected_requests(token)
    assert extra == []
