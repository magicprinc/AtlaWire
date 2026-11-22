"""Installed-CLI loopback contract for the cross-product ``whoami`` probe.

Expected CLI contract, wired by a separate change (the library API and its
contract are already implemented here):

    atlawire whoami --json --allow-http-loopback [--token-from-env]

prints the JSON object returned by [whoami][atlawire.identity.whoami] and makes
exactly three GET requests: Confluence ``/rest/api/user/current``, Jira
``/rest/api/2/myself``, and the Bitbucket dashboard
``/rest/api/1.0/dashboard/pull-requests?state=OPEN&role=AUTHOR&start=0&limit=1``.
Without ``--token-from-env`` the three matched pairs come from the saved BBK
file; with it they come from the three ``ATLAWIRE_<PRODUCT>_URL``/TOKEN pairs.
The exit status is 0 only when all three products succeed and 1 with the
complete JSON document when any product fails, so a partial answer can never
look complete. No other method, route, redirect target, or origin is contacted.

A saved product pair that cannot be resolved must not abort the command: the
CLI passes ``None`` for that product only (see
[whoami][atlawire.identity.whoami]), probes the other two, and reports the
missing product as ``configuration is missing or invalid``.
"""

import json
import os
import shutil
import subprocess
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from tests._loopback import Request, request_record, send_json, serving

CONFLUENCE_CONTEXT = "/confluence"
JIRA_CONTEXT = "/jira"
BITBUCKET_CONTEXT = "/bitbucket"
CONFLUENCE_PATH = f"{CONFLUENCE_CONTEXT}/rest/api/user/current"
JIRA_PATH = f"{JIRA_CONTEXT}/rest/api/2/myself"
BITBUCKET_PATH = f"{BITBUCKET_CONTEXT}/rest/api/1.0/dashboard/pull-requests"
CONFLUENCE_TOKEN = "fixture-whoami-confluence"
JIRA_TOKEN = "fixture-whoami-jira"
BITBUCKET_TOKEN = "fixture-whoami-bitbucket"
SECRET_MARKER = "RESPONSE-SENTINEL"
PRODUCTS = [
    ("confluence", "Confluence"),
    ("jira", "Jira"),
    ("bitbucket", "Bitbucket"),
]

CONFLUENCE_USER = {
    "type": "known",
    "username": "fixture-confluence-user",
    "displayName": "Fixture Confluence User",
    "_links": {"self": "http://elsewhere.invalid/confluence/user"},
}
JIRA_USER = {
    "name": "fixture-jira-user",
    "displayName": "Fixture Jira User",
    "emailAddress": "fixture@example.test",
    "self": "http://elsewhere.invalid/jira/user",
}
BITBUCKET_DASHBOARD = {"values": [], "isLastPage": True}


def clean_environment(**values: str) -> dict[str, str]:
    env = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith("ATLAWIRE_") and name != "BBK_CREDENTIALS"
    }
    env.update(values)
    return env


def run_cli(args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    script = shutil.which("atlawire")
    assert script is not None, "Install AtlaWire before running its CLI E2E suite."
    return subprocess.run(
        [script, *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )


def send_redirect(handler: BaseHTTPRequestHandler, location: str) -> None:
    """Answer with a redirect that must never be resolved or followed."""
    handler.send_response(302)
    handler.send_header("Location", location)
    handler.send_header("Content-Length", "0")
    handler.end_headers()


def handler_for(
    scenario: str, seen: list[Request]
) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def _serve(self, method: str) -> None:
            seen.append(request_record(self))
            if method != "GET":
                send_json(self, 405, {"message": SECRET_MARKER})
                return
            path = urlsplit(self.path).path
            if path == CONFLUENCE_PATH:
                if scenario == "confluence-anonymous":
                    send_json(
                        self, 200, {"type": "anonymous", "username": "anonymous"}
                    )
                    return
                send_json(self, 200, CONFLUENCE_USER)
                return
            if path == JIRA_PATH:
                if scenario == "jira-401":
                    body = {"message": f"{JIRA_TOKEN} {SECRET_MARKER}"}
                    send_json(self, 401, body)
                    return
                if scenario == "jira-redirect":
                    port = self.server.server_port
                    send_redirect(self, f"http://127.0.0.1:{port}/elsewhere")
                    return
                send_json(self, 200, JIRA_USER)
                return
            if path == BITBUCKET_PATH:
                if scenario == "bitbucket-403":
                    send_json(self, 403, {"message": SECRET_MARKER})
                    return
                send_json(self, 200, BITBUCKET_DASHBOARD)
                return
            send_json(self, 404, {"message": SECRET_MARKER})

        def do_GET(self) -> None:
            self._serve("GET")

        def do_POST(self) -> None:
            self._serve("POST")

        def do_PUT(self) -> None:
            self._serve("PUT")

        def do_PATCH(self) -> None:
            self._serve("PATCH")

        def do_DELETE(self) -> None:
            self._serve("DELETE")

        def do_HEAD(self) -> None:
            self._serve("HEAD")

        def do_OPTIONS(self) -> None:
            self._serve("OPTIONS")

        def do_TRACE(self) -> None:
            self._serve("TRACE")

    return Handler


def saved_document(origin: str) -> dict[str, str]:
    return {
        "confluence_url": f"{origin}{CONFLUENCE_CONTEXT}/",
        "confluence_token": CONFLUENCE_TOKEN,
        "jira_url": f"{origin}{JIRA_CONTEXT}/",
        "jira_token": JIRA_TOKEN,
        "bitbucket_url": f"{origin}{BITBUCKET_CONTEXT}/",
        "bitbucket_token": BITBUCKET_TOKEN,
    }


def environment_pairs(origin: str) -> dict[str, str]:
    return {
        "ATLAWIRE_CONFLUENCE_URL": f"{origin}{CONFLUENCE_CONTEXT}/",
        "ATLAWIRE_CONFLUENCE_TOKEN": CONFLUENCE_TOKEN,
        "ATLAWIRE_JIRA_URL": f"{origin}{JIRA_CONTEXT}/",
        "ATLAWIRE_JIRA_TOKEN": JIRA_TOKEN,
        "ATLAWIRE_BITBUCKET_URL": f"{origin}{BITBUCKET_CONTEXT}/",
        "ATLAWIRE_BITBUCKET_TOKEN": BITBUCKET_TOKEN,
    }


def incomplete_document(
    slot: str, omission: str
) -> Callable[[str], dict[str, str]]:
    """Build a saved document that lacks one product's pair or token."""

    def build(origin: str) -> dict[str, str]:
        document = saved_document(origin)
        if omission == "pair":
            document.pop(f"{slot}_url")
            document.pop(f"{slot}_token")
        else:
            document.pop(f"{slot}_token")
        return document

    return build


def run_whoami(
    tmp_path: Path,
    mode: str,
    scenario: str,
    *,
    saved_factory: Callable[[str], dict[str, str]] | None = None,
) -> tuple[subprocess.CompletedProcess[str], list[Request]]:
    """Run the installed command against one loopback origin."""
    seen: list[Request] = []
    handler = handler_for(scenario, seen)
    with serving(handler) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        if mode == "env":
            env = clean_environment(**environment_pairs(origin))
            env["BBK_CREDENTIALS"] = str(tmp_path / "missing-credentials.json")
            args = ["whoami", "--json", "--allow-http-loopback", "--token-from-env"]
        else:
            credentials = tmp_path / "credentials.json"
            document = (
                saved_document(origin)
                if saved_factory is None
                else saved_factory(origin)
            )
            credentials.write_text(json.dumps(document), encoding="utf-8")
            env = clean_environment(BBK_CREDENTIALS=str(credentials))
            args = ["whoami", "--json", "--allow-http-loopback"]
        result = run_cli(args, env)
    return result, seen


def expected_requests(*, exclude: str | None = None) -> list[Request]:
    requests = [
        ("GET", CONFLUENCE_PATH, {}, f"Bearer {CONFLUENCE_TOKEN}"),
        ("GET", JIRA_PATH, {}, f"Bearer {JIRA_TOKEN}"),
        (
            "GET",
            BITBUCKET_PATH,
            {
                "state": ["OPEN"],
                "role": ["AUTHOR"],
                "start": ["0"],
                "limit": ["1"],
            },
            f"Bearer {BITBUCKET_TOKEN}",
        ),
    ]
    if exclude is None:
        return requests
    index = {"confluence": 0, "jira": 1, "bitbucket": 2}[exclude]
    return [
        record for position, record in enumerate(requests) if position != index
    ]


def expected_payload() -> dict[str, object]:
    return {
        "confluence": {
            "ok": True,
            "identity": {
                "username": "fixture-confluence-user",
                "displayName": "Fixture Confluence User",
            },
        },
        "jira": {
            "ok": True,
            "identity": {
                "name": "fixture-jira-user",
                "displayName": "Fixture Jira User",
            },
        },
        "bitbucket": {"ok": True, "authenticated": True},
    }


def assert_no_secrets(result: subprocess.CompletedProcess[str]) -> None:
    combined = result.stdout + result.stderr
    for detail in (
        CONFLUENCE_TOKEN,
        JIRA_TOKEN,
        BITBUCKET_TOKEN,
        SECRET_MARKER,
        "fixture@example.test",
        "127.0.0.1",
        "elsewhere.invalid",
    ):
        assert detail not in combined


@pytest.mark.parametrize("mode", ["env", "saved"])
def test_whoami_reports_all_three_identities_over_fixed_read_routes(
    tmp_path: Path, mode: str
) -> None:
    result, seen = run_whoami(tmp_path, mode, "happy")

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == expected_payload()
    assert seen == expected_requests()
    assert {record[0] for record in seen} == {"GET"}
    assert_no_secrets(result)


@pytest.mark.parametrize(
    ("scenario", "slot", "reason"),
    [
        (
            "confluence-anonymous",
            "confluence",
            "no authenticated identity was returned",
        ),
        ("jira-401", "jira", "authentication rejected"),
        ("bitbucket-403", "bitbucket", "access denied"),
    ],
    ids=["confluence-anonymous", "jira-401", "bitbucket-403"],
)
def test_whoami_reports_a_failure_without_hiding_the_other_products(
    tmp_path: Path, scenario: str, slot: str, reason: str
) -> None:
    result, seen = run_whoami(tmp_path, "env", scenario)

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert set(payload) == {"confluence", "jira", "bitbucket"}
    assert payload[slot]["ok"] is False
    assert reason in payload[slot]["error"]
    for other in {"confluence", "jira", "bitbucket"} - {slot}:
        assert payload[other]["ok"] is True
    assert seen == expected_requests()
    assert "Traceback" not in result.stderr
    assert_no_secrets(result)


@pytest.mark.parametrize(("slot", "label"), PRODUCTS)
@pytest.mark.parametrize(
    "omission", ["pair", "token"], ids=["missing-pair", "missing-token"]
)
def test_whoami_reports_a_missing_saved_pair_and_probes_the_other_two(
    tmp_path: Path, slot: str, label: str, omission: str
) -> None:
    # A saved file missing one product (or one half of its pair) must not abort
    # the command: the other two pairs are still resolved and read.
    result, seen = run_whoami(
        tmp_path,
        "saved",
        "happy",
        saved_factory=incomplete_document(slot, omission),
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert set(payload) == {"confluence", "jira", "bitbucket"}
    assert payload[slot] == {
        "ok": False,
        "error": f"{label} check failed: configuration is missing or invalid.",
    }
    for other in {"confluence", "jira", "bitbucket"} - {slot}:
        assert payload[other]["ok"] is True
    assert seen == expected_requests(exclude=slot)
    assert len(seen) == 2
    assert {record[0] for record in seen} == {"GET"}
    assert "Traceback" not in result.stderr
    assert_no_secrets(result)


def test_whoami_never_follows_a_server_returned_redirect(tmp_path: Path) -> None:
    # The refused redirect must not become a fourth request to /elsewhere or an
    # external origin.
    result, seen = run_whoami(tmp_path, "env", "jira-redirect")

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["jira"]["ok"] is False
    assert "redirect refused" in payload["jira"]["error"]
    assert payload["confluence"]["ok"] is True
    assert payload["bitbucket"]["ok"] is True
    assert seen == expected_requests()
    assert [record[1] for record in seen if "elsewhere" in record[1]] == []
    assert "Traceback" not in result.stderr
    assert_no_secrets(result)


def test_whoami_env_mode_does_not_require_the_saved_bbk_file(
    tmp_path: Path,
) -> None:
    result, seen = run_whoami(tmp_path, "env", "happy")
    missing = tmp_path / "missing-credentials.json"

    assert not missing.exists()
    assert result.returncode == 0, result.stderr
    assert len(seen) == 3
