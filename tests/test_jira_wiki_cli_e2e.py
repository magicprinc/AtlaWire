"""Installed-CLI loopback checks for ``atlawire issue KEY --wiki``.

Every response comes from a synthetic loopback server and every credential is a
fixture. ``BBK_CREDENTIALS`` points at a path that must not exist. The expected
Markdown is written by hand; the renderer never follows a link in the body.
"""

import json
import re
import secrets
import subprocess
from http.server import BaseHTTPRequestHandler
from pathlib import Path

import pytest

from tests._loopback import (
    Request,
    request_record,
    run_installed,
    send_json,
    serving,
)

TOKEN = "fixture-jira-wiki-cli-token"
CONTEXT = "/jira"
KEY = "DEMO-42"
ISSUE_PATH = f"{CONTEXT}/rest/api/2/issue/{KEY}"
EXPAND = {"expand": ["renderedFields"]}
SENTINEL = "JIRA-WIKI-CLI-SENTINEL"
MISSING_BBK_CREDENTIALS = str(
    Path(__file__).with_name("bbk-credentials-missing-for-wiki.json")
)
BIDI = "\u202e"


def issue_document(link: str) -> dict[str, object]:
    return {
        "key": KEY,
        "fields": {
            "summary": "Wiki E2E",
            "status": {"name": "In Progress"},
            "issuetype": {"name": "Bug"},
            "priority": {"name": "High"},
            "assignee": {"displayName": "Ada"},
            "description": (
                "h2. Details\n"
                "\n"
                f"*Bold* and [Docs|{link}].\n"
                "\n"
                "{code}\n"
                "line *1*\n"
                "{code}"
            ),
            "comment": {
                "total": 2,
                "comments": [
                    {
                        "id": 1,
                        "author": {"displayName": "Bob"},
                        "created": "2024-02-03T04:05:06.000+0000",
                        "body": "First *raw* comment?",
                    },
                    {
                        "id": 2,
                        "author": {"displayName": "Eve"},
                        "created": None,
                        "body": "Second [bad|javascript:alert(1)] comment",
                    },
                ],
            },
        },
        "renderedFields": {
            "description": "<p>rendered ignored</p>",
            "comment": {"comments": [{"id": 1, "body": "<p>rendered ignored</p>"}]},
        },
    }


def expected_markdown(link: str) -> str:
    return (
        f"# {KEY}: Wiki E2E\n\n"
        "**Status:** In Progress · **Type:** Bug · **Priority:** High"
        " · **Assignee:** Ada\n\n"
        "## Description\n\n"
        "## Details\n\n"
        f"**Bold** and [Docs](<{link}>).\n\n"
        "```\n"
        "line *1*\n"
        "```\n\n"
        "## Comments\n\n"
        "### Comment 1 · Bob · 2024-02-03\n\n"
        "First **raw** comment?\n\n"
        "### Comment 2 · Eve\n\n"
        "Second `[unsupported Jira link target]` "
        "\\[bad\\|javascript:alert\\(1\\)\\] comment\n"
    )


def environment(origin: str, token: str = TOKEN) -> dict[str, str]:
    """Point Jira at the loopback context and keep every other source inert."""
    return {
        "ATLAWIRE_JIRA_URL": f"{origin}{CONTEXT}/",
        "ATLAWIRE_JIRA_TOKEN": token,
        "ATLAWIRE_BITBUCKET_URL": f"{origin}/wrong-bitbucket/",
        "ATLAWIRE_BITBUCKET_TOKEN": "wrong-product-fixture",
        "ATLAWIRE_CONFLUENCE_URL": f"{origin}/wrong-confluence/",
        "ATLAWIRE_CONFLUENCE_TOKEN": "wrong-product-fixture",
        "BBK_CREDENTIALS": MISSING_BBK_CREDENTIALS,
    }


def run_issue(
    arguments: tuple[str, ...],
    body: object,
    *,
    status: int = 200,
    token: str = TOKEN,
) -> tuple[
    subprocess.CompletedProcess[str],
    list[Request],
    list[str | None],
]:
    """Run the installed ``issue`` command against one synthetic response."""
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
            if path != ISSUE_PATH or authorization != f"Bearer {token}":
                send_json(self, 401, {"message": SENTINEL})
                return
            if status != 200:
                send_json(self, status, {"message": SENTINEL})
                return
            send_json(self, 200, body)

    with serving(Handler) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        result = run_installed(
            [
                "issue",
                *arguments,
                "--token-from-env",
                "--allow-http-loopback",
            ],
            environment(origin, token),
        )
    return result, seen, accepts


def expected_request(token: str = TOKEN) -> list[Request]:
    return [("GET", ISSUE_PATH, EXPAND, f"Bearer {token}")]


def test_installed_issue_wiki_renders_markdown_without_following_links() -> None:
    honeypot: list[Request] = []

    class Honeypot(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            honeypot.append(request_record(self))
            send_json(self, 200, {"message": SENTINEL})

    with serving(Honeypot) as target:
        link = f"http://127.0.0.1:{target.server_port}/stolen"
        body = issue_document(link)
        result, seen, accepts = run_issue((KEY, "--wiki"), body)

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout == expected_markdown(link)
    assert not result.stdout.startswith("{")
    assert "rendered ignored" not in result.stdout
    assert SENTINEL not in result.stdout + result.stderr
    assert TOKEN not in result.stdout + result.stderr
    assert seen == expected_request()
    assert accepts == ["application/json"]
    assert honeypot == []


def test_installed_issue_without_wiki_keeps_json() -> None:
    body = issue_document("https://docs.example.invalid/spec")

    result, seen, accepts = run_issue((KEY,), body)

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout == json.dumps(body) + "\n"
    assert seen == expected_request()
    assert accepts == ["application/json"]


def test_installed_issue_wiki_pins_a_pasted_url_to_the_configured_server() -> None:
    body = issue_document("https://docs.example.invalid/spec")
    pasted = f"https://pasted.example.invalid/jira/browse/{KEY}?tab=wiki#top"

    result, seen, accepts = run_issue((pasted, "--wiki"), body)

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout == expected_markdown("https://docs.example.invalid/spec")
    assert seen == expected_request()
    assert accepts == ["application/json"]


def test_installed_issue_wiki_keeps_controls_out_of_stdout() -> None:
    body = {
        "key": KEY,
        "fields": {
            "summary": f"Wiki {BIDI} E2E",
            "description": "control \x1b[31m red",
        },
        "renderedFields": {},
    }

    result, seen, _ = run_issue((KEY, "--wiki"), body)

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout == (
        f"# {KEY}: Wiki \\u202e E2E\n\n"
        "## Description\n\n"
        "control \\[31m red\n"
    )
    assert "\x1b" not in result.stdout
    assert BIDI not in result.stdout
    assert seen == expected_request()


@pytest.mark.parametrize(
    ("body", "diagnostic"),
    [
        ({"key": KEY, "fields": {}, "renderedFields": []}, "renderedFields"),
        (
            {
                "key": KEY,
                "fields": {"comment": {"comments": [{"body": 1}]}},
                "renderedFields": {},
            },
            "body",
        ),
        (
            {
                "key": KEY,
                "fields": {"description": 1},
                "renderedFields": {},
            },
            "description",
        ),
    ],
    ids=["rendered-fields", "comment-body", "description"],
)
def test_installed_issue_wiki_publishes_nothing_for_a_malformed_issue(
    body: dict[str, object], diagnostic: str
) -> None:
    result, seen, _ = run_issue((KEY, "--wiki"), body)

    assert result.returncode == 1
    assert result.stdout == ""
    assert diagnostic in result.stderr
    assert SENTINEL not in result.stderr
    assert TOKEN not in result.stderr
    assert "Traceback" not in result.stderr
    assert seen == expected_request()


def test_installed_issue_wiki_reports_authentication_rejection() -> None:
    result, seen, _ = run_issue(
        (KEY, "--wiki"),
        issue_document("https://docs.example.invalid/spec"),
        status=401,
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == "Error: HTTP 401: authentication rejected.\n"
    assert SENTINEL not in result.stderr
    assert TOKEN not in result.stderr
    assert seen == expected_request()


def test_installed_issue_wiki_escapes_a_literal_exclamation_before_a_link() -> None:
    body = {
        "key": KEY,
        "fields": {
            "description": "![Preview|https://example.invalid/tracker]",
            "comment": {
                "comments": [
                    {
                        "id": 1,
                        "body": "![Preview|https://example.invalid/tracker]",
                    }
                ]
            },
        },
        "renderedFields": {},
    }

    result, seen, accepts = run_issue((KEY, "--wiki"), body)

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout == (
        f"# {KEY}\n\n"
        "## Description\n\n"
        "\\![Preview](<https://example.invalid/tracker>)\n\n"
        "## Comments\n\n"
        "### Comment 1\n\n"
        "\\![Preview](<https://example.invalid/tracker>)\n"
    )
    assert re.search(r"(?<!\\)!\[Preview\]\(", result.stdout) is None
    assert seen == expected_request()
    assert accepts == ["application/json"]


def test_installed_issue_wiki_marks_an_incomplete_comment_page() -> None:
    body = {
        "key": KEY,
        "fields": {
            "comment": {
                "total": 5,
                "comments": [
                    {"id": 1, "author": {"displayName": "A"}, "body": "first"},
                    {"id": 2, "body": ""},
                    {"id": 3, "body": "third"},
                ],
            }
        },
        "renderedFields": {},
    }

    result, seen, _ = run_issue((KEY, "--wiki"), body)

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout == (
        f"# {KEY}\n\n"
        "## Comments\n\n"
        "_Comments are incomplete: showing 3 of 5._\n\n"
        "### Comment 1 · A\n\n"
        "first\n\n"
        "### Comment 2\n\n"
        "_Empty comment body._\n\n"
        "### Comment 3\n\n"
        "third\n"
    )
    assert seen == expected_request()


def test_installed_issue_markdown_rejects_a_token_assembled_only_by_rendering() -> None:
    token = secrets.token_hex(16)
    split = len(token) // 2
    start, end = token[:split], token[split:]
    body = {
        "key": KEY,
        "fields": {"summary": "Guard"},
        "renderedFields": {
            "description": (
                '<p><a href="https://example.invalid/guard">'
                f"{start}</a>{end}</p>"
            )
        },
    }
    assert token not in json.dumps(body)

    plain, plain_seen, _ = run_issue((KEY,), body, token=token)
    rejected, rejected_seen, _ = run_issue(
        (KEY, "--markdown"), body, token=token
    )

    assert plain.returncode == 0, plain.stderr
    assert plain.stderr == ""
    assert json.loads(plain.stdout) == body
    assert token not in plain.stdout
    assert plain_seen == expected_request(token)
    assert rejected.returncode == 1
    assert rejected.stdout == ""
    assert rejected.stderr == (
        "Error: The response contained the session bearer token.\n"
    )
    assert token not in rejected.stderr
    assert rejected_seen == expected_request(token)


def test_installed_issue_wiki_rejects_a_token_rebuilt_by_its_own_label() -> None:
    # The raw JSON has no token: the wiki converter creates the word
    # "unsupported" when it labels the unsupported {panel} macro.
    body = {
        "key": KEY,
        "fields": {"summary": "Wiki guard", "description": "{panel}"},
        "renderedFields": {},
    }

    plain, plain_seen, _ = run_issue((KEY,), body, token="unsupported")
    wiki, wiki_seen, _ = run_issue((KEY, "--wiki"), body, token="unsupported")

    assert plain.returncode == 0, plain.stderr
    assert plain.stderr == ""
    assert json.loads(plain.stdout) == body
    assert "unsupported" not in plain.stdout
    assert plain_seen == expected_request("unsupported")

    assert wiki.returncode == 1
    assert wiki.stdout == ""
    assert wiki.stderr == (
        "Error: The response contained the session bearer token.\n"
    )
    assert "unsupported" not in wiki.stderr
    assert wiki_seen == expected_request("unsupported")


def test_the_bbk_credentials_override_is_a_missing_synthetic_path() -> None:
    assert "missing-for-wiki" in MISSING_BBK_CREDENTIALS
    assert not Path(MISSING_BBK_CREDENTIALS).exists()
