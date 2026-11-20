"""Installed-CLI checks for the Jira caller identity projection."""

import json
import subprocess
from http.server import BaseHTTPRequestHandler

import pytest

from tests._loopback import (
    Request,
    request_record,
    run_installed,
    send_json,
    serving,
)

TOKEN = "fixture-jira-me-token"
CONTEXT = "/jira"
MYSELF_PATH = f"{CONTEXT}/rest/api/2/myself"
SENTINEL = "JIRA-ME-IDENTITY-SENTINEL"

IDENTITY = {
    "self": f"https://jira.example.invalid{MYSELF_PATH}?username={SENTINEL}",
    "key": SENTINEL,
    "name": "ada",
    "displayName": "Ada Lovelace",
    "emailAddress": "ada@example.invalid",
    "active": True,
    "avatarUrls": {"48x48": f"https://example.invalid/{SENTINEL}.png"},
    "groups": {"size": 1, "items": [{"name": SENTINEL}]},
    "properties": {"inert": {"opaque": True}},
}

EXPECTED = {
    "name": "ada",
    "displayName": "Ada Lovelace",
    "email": "ada@example.invalid",
}


def environment(origin: str) -> dict[str, str]:
    """Configure Jira for the loopback context and keep other products inert."""
    return {
        "ATLAWIRE_JIRA_URL": f"{origin}{CONTEXT}/",
        "ATLAWIRE_JIRA_TOKEN": TOKEN,
        "ATLAWIRE_BITBUCKET_URL": f"{origin}/wrong-bitbucket/",
        "ATLAWIRE_BITBUCKET_TOKEN": "wrong-product-fixture",
        "ATLAWIRE_CONFLUENCE_URL": f"{origin}/wrong-confluence/",
        "ATLAWIRE_CONFLUENCE_TOKEN": "wrong-product-fixture",
    }


def run_me(
    body: object, *, status: int = 200
) -> tuple[subprocess.CompletedProcess[str], list[Request], list[str | None]]:
    """Run jira-me from the environment against one loopback identity response."""
    seen: list[Request] = []
    accepts: list[str | None] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            record = request_record(self)
            seen.append(record)
            accepts.append(self.headers.get("Accept"))
            _, path, _, authorization = record
            if path != MYSELF_PATH or authorization != f"Bearer {TOKEN}":
                send_json(self, 401, {"message": SENTINEL})
                return
            send_json(self, status, body)

    with serving(Handler) as server:
        result = run_installed(
            ["jira-me", "--token-from-env", "--allow-http-loopback"],
            environment(f"http://127.0.0.1:{server.server_port}"),
        )
    return result, seen, accepts


def expected_requests() -> list[Request]:
    return [("GET", MYSELF_PATH, {}, f"Bearer {TOKEN}")]


def test_installed_jira_me_prints_only_the_legacy_identity_fields() -> None:
    result, seen, accepts = run_me(IDENTITY)

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == EXPECTED
    assert list(json.loads(result.stdout)) == ["name", "displayName", "email"]
    assert SENTINEL not in result.stdout
    assert TOKEN not in result.stdout
    assert seen == expected_requests()
    assert accepts == ["application/json"]


@pytest.mark.parametrize(
    "body",
    [
        {"name": "bob", "self": f"https://example.invalid/{SENTINEL}"},
        {"name": "carol", "displayName": None, "emailAddress": None},
    ],
    ids=["absent", "null"],
)
def test_installed_jira_me_keeps_optional_fields_null(
    body: dict[str, object],
) -> None:
    result, seen, accepts = run_me(body)

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == {
        "name": body["name"],
        "displayName": None,
        "email": None,
    }
    assert seen == expected_requests()
    assert accepts == ["application/json"]


@pytest.mark.parametrize(
    ("body", "diagnostic"),
    [
        ({"self": f"https://example.invalid/{SENTINEL}"}, "Invalid Jira user name"),
        ({"name": "  ", "key": SENTINEL}, "non-empty name"),
        (
            {"name": "ada", "displayName": "Ada\ud800", "properties": SENTINEL},
            "valid UTF-8",
        ),
    ],
    ids=["missing", "blank", "unencodable"],
)
def test_installed_jira_me_publishes_nothing_for_a_malformed_identity(
    body: dict[str, object], diagnostic: str
) -> None:
    result, seen, accepts = run_me(body)

    assert result.returncode == 1
    assert result.stdout == ""
    assert diagnostic in result.stderr
    assert SENTINEL not in result.stderr
    assert "Traceback" not in result.stderr
    assert seen == expected_requests()
    assert accepts == ["application/json"]


def test_installed_jira_me_reports_a_rejected_token_without_details() -> None:
    result, seen, accepts = run_me({"message": SENTINEL}, status=401)

    assert result.returncode == 1
    assert result.stdout == ""
    assert "HTTP 401" in result.stderr
    assert SENTINEL not in result.stderr
    assert TOKEN not in result.stderr
    assert seen == expected_requests()
    assert accepts == ["application/json"]
