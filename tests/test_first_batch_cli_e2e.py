"""Installed-CLI loopback contracts for the first adapter and discovery batch.

Every response comes from a synthetic loopback server, every credential is a
fixture, and ``BBK_CREDENTIALS`` points at a path that must not exist. No test
contacts a real instance, reads a real credential store, or mutates server state.
"""

import json
import os
import shutil
import subprocess
from http.server import BaseHTTPRequestHandler
from pathlib import Path

import pytest

from atlawire.cli import cli
from tests._loopback import (
    Request,
    request_record,
    send_bytes,
    send_json,
    serving,
)

JIRA_TOKEN = "synthetic-jira-remote-links-token-5a1"
BITBUCKET_TOKEN = "synthetic-bitbucket-merge-token-5b2"
SENTINEL = "FIRST-BATCH-CLI-SENTINEL"
MISSING_BBK_CREDENTIALS = str(
    Path(__file__).with_name("bbk-credentials-missing-first-batch.json")
)

REMOTE_LINKS_PATH = "/jira/rest/api/2/issue/DEMO-42/remotelink"
MERGE_PATH = (
    "/bitbucket/rest/api/1.0/projects/DEMO/repos/widgets"
    "/pull-requests/7/merge"
)

REMOTE_LINKS: list[dict[str, object]] = [
    {
        "id": 10000,
        "self": (
            "https://pasted.example.invalid/rest/api/2/issue/"
            "DEMO-42/remotelink/10000"
        ),
        "globalId": "system=https://tracker.example.invalid/&id=TSTSUP-111",
        "application": {"type": "com.acme.tracker", "name": "Acme Tracker"},
        "relationship": "causes",
        "object": {
            "url": "https://tracker.example.invalid/TSTSUP-111",
            "title": "TSTSUP-111",
            "summary": "Résumé ✓ — многострочный\nsummary",
            "icon": {"url16x16": None, "title": "Support Ticket", "link": None},
            "status": {"resolved": True, "icon": {"title": "Case Closed"}},
        },
        "cliUnknown": {"nested": [1, 2.5, None, False, {"deep": []}]},
    },
    {
        "id": 10001,
        "self": None,
        "globalId": None,
        "application": None,
        "object": {"url": None, "title": None, "summary": None, "icon": None},
    },
]

MERGE_STATUS: dict[str, object] = {
    "canMerge": False,
    "conflicted": True,
    "outcome": "CONFLICTED",
    "vetoes": [
        {
            "summaryMessage": "You may not merge after 6pm on a Friday.",
            "detailedMessage": "Please try again on Monday.",
            "cliUnknown": {"nested": [None, True, 0.5]},
        }
    ],
}


def clean_environment(**values: str) -> dict[str, str]:
    """Strip ambient AtlaWire/BBK settings before adding synthetic fixtures."""
    env = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith("ATLAWIRE_") and name != "BBK_CREDENTIALS"
    }
    env.update(values)
    return env


def environment(origin: str) -> dict[str, str]:
    """Point both products at the loopback origin and keep other sources inert."""
    return clean_environment(
        ATLAWIRE_JIRA_URL=f"{origin}/jira/",
        ATLAWIRE_JIRA_TOKEN=JIRA_TOKEN,
        ATLAWIRE_BITBUCKET_URL=f"{origin}/bitbucket/",
        ATLAWIRE_BITBUCKET_TOKEN=BITBUCKET_TOKEN,
        ATLAWIRE_CONFLUENCE_URL=f"{origin}/wrong-confluence/",
        ATLAWIRE_CONFLUENCE_TOKEN="wrong-product-fixture",
        BBK_CREDENTIALS=MISSING_BBK_CREDENTIALS,
    )


def run_cli(
    args: list[str], env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
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


def run_case(
    args: list[str],
    path: str,
    token: str,
    body: object,
    *,
    status: int = 200,
    location: str | None = None,
) -> tuple[subprocess.CompletedProcess[str], list[Request]]:
    """Run one installed command against one synthetic response."""
    seen: list[Request] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            record = request_record(self)
            seen.append(record)
            _, request_path, _, authorization = record
            if request_path != path or authorization != f"Bearer {token}":
                send_json(self, 401, {"message": SENTINEL})
                return
            if location is not None:
                send_bytes(
                    self,
                    302,
                    b"",
                    content_type=None,
                    extra_headers={"Location": location},
                )
                return
            if status != 200:
                send_json(self, status, {"message": SENTINEL})
                return
            send_json(self, 200, body)

        def do_POST(self) -> None:
            seen.append(request_record(self))
            send_json(self, 405, {"message": SENTINEL})

    with serving(Handler) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        result = run_cli(args, environment(origin))
    return result, seen


def remote_links_args(argument: str = "DEMO-42") -> list[str]:
    return [
        "issue-remote-links",
        argument,
        "--token-from-env",
        "--allow-http-loopback",
    ]


def merge_status_args() -> list[str]:
    return [
        "pr-merge-status",
        "DEMO/widgets",
        "7",
        "--token-from-env",
        "--allow-http-loopback",
    ]


def expected_get(path: str, token: str) -> list[Request]:
    return [("GET", path, {}, f"Bearer {token}")]


def test_issue_remote_links_prints_complete_json_from_the_fixed_get() -> None:
    result, seen = run_case(
        remote_links_args(), REMOTE_LINKS_PATH, JIRA_TOKEN, REMOTE_LINKS
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == REMOTE_LINKS
    assert seen == expected_get(REMOTE_LINKS_PATH, JIRA_TOKEN)
    # Field completeness is asserted independently of the adapter: a projection
    # would drop the unknown key, the nested list, or the nulls.
    first = json.loads(result.stdout)[0]
    assert list(first) == list(REMOTE_LINKS[0])
    assert first["cliUnknown"] == REMOTE_LINKS[0]["cliUnknown"]
    assert first["object"] == REMOTE_LINKS[0]["object"]
    assert json.loads(result.stdout)[1]["globalId"] is None
    assert SENTINEL not in result.stdout
    assert JIRA_TOKEN not in result.stdout


def test_issue_remote_links_accepts_an_empty_array() -> None:
    result, seen = run_case(remote_links_args(), REMOTE_LINKS_PATH, JIRA_TOKEN, [])

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == []
    assert seen == expected_get(REMOTE_LINKS_PATH, JIRA_TOKEN)


def test_pr_merge_status_prints_complete_json_from_the_fixed_get() -> None:
    result, seen = run_case(
        merge_status_args(), MERGE_PATH, BITBUCKET_TOKEN, MERGE_STATUS
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == MERGE_STATUS
    assert seen == expected_get(MERGE_PATH, BITBUCKET_TOKEN)
    assert list(json.loads(result.stdout)) == list(MERGE_STATUS)
    assert json.loads(result.stdout)["vetoes"] == MERGE_STATUS["vetoes"]
    assert SENTINEL not in result.stdout
    assert BITBUCKET_TOKEN not in result.stdout
    assert JIRA_TOKEN not in result.stdout


def test_pr_merge_status_accepts_an_empty_object() -> None:
    result, seen = run_case(merge_status_args(), MERGE_PATH, BITBUCKET_TOKEN, {})

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == {}
    assert seen == expected_get(MERGE_PATH, BITBUCKET_TOKEN)


@pytest.mark.parametrize(
    ("argument", "body"),
    [
        ("DEMO-42", [REMOTE_LINKS[0], 7]),
        ("DEMO-42", [REMOTE_LINKS[0], "not-a-link"]),
        ("DEMO-42", [REMOTE_LINKS[0], None]),
        ("DEMO-42", [REMOTE_LINKS[0], []]),
    ],
    ids=["integer", "text", "null", "array-row"],
)
def test_issue_remote_links_discards_everything_for_a_malformed_late_row(
    argument: str, body: list[object]
) -> None:
    result, seen = run_case(
        remote_links_args(argument), REMOTE_LINKS_PATH, JIRA_TOKEN, body
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "remote link objects" in result.stderr
    assert SENTINEL not in result.stderr
    assert JIRA_TOKEN not in result.stderr
    assert "Traceback" not in result.stderr
    assert seen == expected_get(REMOTE_LINKS_PATH, JIRA_TOKEN)


def test_issue_remote_links_rejects_a_non_array_body_without_partial_output() -> None:
    result, seen = run_case(
        remote_links_args(),
        REMOTE_LINKS_PATH,
        JIRA_TOKEN,
        {"values": REMOTE_LINKS},
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "Expected a JSON array" in result.stderr
    assert SENTINEL not in result.stderr
    assert seen == expected_get(REMOTE_LINKS_PATH, JIRA_TOKEN)


@pytest.mark.parametrize(
    "body",
    [[], "text", 7, None, True],
    ids=["array", "text", "number", "null", "boolean"],
)
def test_pr_merge_status_rejects_a_wrong_non_object_body(body: object) -> None:
    result, seen = run_case(merge_status_args(), MERGE_PATH, BITBUCKET_TOKEN, body)

    assert result.returncode == 1
    assert result.stdout == ""
    assert "Expected a JSON object" in result.stderr
    assert SENTINEL not in result.stderr
    assert seen == expected_get(MERGE_PATH, BITBUCKET_TOKEN)


@pytest.mark.parametrize(
    ("args", "path", "token"),
    [
        (remote_links_args(), REMOTE_LINKS_PATH, JIRA_TOKEN),
        (merge_status_args(), MERGE_PATH, BITBUCKET_TOKEN),
    ],
    ids=["remote-links", "merge-status"],
)
@pytest.mark.parametrize(
    ("status", "message"),
    [
        (401, "HTTP 401: authentication rejected."),
        (403, "HTTP 403: access denied."),
    ],
    ids=["401", "403"],
)
def test_rejected_requests_exit_without_stdout(
    args: list[str],
    path: str,
    token: str,
    status: int,
    message: str,
) -> None:
    result, seen = run_case(args, path, token, {}, status=status)

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == f"Error: {message}\n"
    assert SENTINEL not in result.stderr
    assert seen == expected_get(path, token)


@pytest.mark.parametrize(
    ("args", "path", "token"),
    [
        (remote_links_args(), REMOTE_LINKS_PATH, JIRA_TOKEN),
        (merge_status_args(), MERGE_PATH, BITBUCKET_TOKEN),
    ],
    ids=["remote-links", "merge-status"],
)
def test_a_redirect_is_refused_and_never_followed(
    args: list[str], path: str, token: str
) -> None:
    honeypot: list[Request] = []

    class Honeypot(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            honeypot.append(request_record(self))
            send_json(self, 200, {"message": SENTINEL})

    with serving(Honeypot) as target:
        location = f"http://127.0.0.1:{target.server_port}/stolen"
        result, seen = run_case(args, path, token, {}, location=location)

    assert result.returncode == 1
    assert result.stdout == ""
    assert "redirect refused" in result.stderr
    assert SENTINEL not in result.stdout + result.stderr
    assert seen == expected_get(path, token)
    assert honeypot == []


def test_a_foreign_browse_url_cannot_change_the_request_destination() -> None:
    foreign = (
        "https://foreign.example.invalid/jira/browse/DEMO-42"
        "?tab=links&x=1#fragment"
    )

    result, seen = run_case(
        remote_links_args(foreign), REMOTE_LINKS_PATH, JIRA_TOKEN, REMOTE_LINKS
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == REMOTE_LINKS
    # The pasted URL supplies only the key; the configured instance is the only
    # destination and no link from the response is requested.
    assert seen == expected_get(REMOTE_LINKS_PATH, JIRA_TOKEN)


def test_the_batch_sends_no_post_and_no_extra_request() -> None:
    remote_result, remote_seen = run_case(
        remote_links_args(), REMOTE_LINKS_PATH, JIRA_TOKEN, REMOTE_LINKS
    )
    merge_result, merge_seen = run_case(
        merge_status_args(), MERGE_PATH, BITBUCKET_TOKEN, MERGE_STATUS
    )

    assert remote_result.returncode == 0, remote_result.stderr
    assert merge_result.returncode == 0, merge_result.stderr
    assert [request[0] for request in remote_seen] == ["GET"]
    assert [request[0] for request in merge_seen] == ["GET"]
    assert remote_seen == expected_get(REMOTE_LINKS_PATH, JIRA_TOKEN)
    assert merge_seen == expected_get(MERGE_PATH, BITBUCKET_TOKEN)


def test_catalog_lists_every_command_without_tokens_or_requests() -> None:
    seen: list[Request] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            seen.append(request_record(self))
            send_json(self, 500, {"message": SENTINEL})

        def do_POST(self) -> None:
            seen.append(request_record(self))
            send_json(self, 500, {"message": SENTINEL})

    with serving(Handler) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        result = run_cli(["--catalog"], environment(origin))

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    catalog = json.loads(result.stdout)
    assert result.stdout == json.dumps(catalog) + "\n"

    commands = catalog["commands"]
    expected = {
        name for name, command in cli.commands.items() if not command.hidden
    }
    assert set(commands) == expected
    assert {"issue-remote-links", "pr-merge-status"} <= set(commands)
    assert "ATLAWIRE_JIRA_TOKEN" in result.stdout

    combined = result.stdout + result.stderr
    assert JIRA_TOKEN not in combined
    assert BITBUCKET_TOKEN not in combined
    assert "wrong-product-fixture" not in combined
    assert MISSING_BBK_CREDENTIALS not in combined
    assert seen == []


def test_the_bbk_credentials_override_is_a_missing_synthetic_path() -> None:
    assert "missing" in MISSING_BBK_CREDENTIALS
    assert not Path(MISSING_BBK_CREDENTIALS).exists()
