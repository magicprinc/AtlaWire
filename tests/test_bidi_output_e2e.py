"""Installed-CLI E2E: synthetic bidi and surrogate content stays visible.

The fixtures are harmless local loopback payloads. They use the control code
points that an untrusted server could return inside JSON strings; no external
service, credential, or real content is involved.
"""

import subprocess
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit

from tests._loopback import Request, request_record, run_installed, send_json, serving

JIRA_TOKEN = "fixture-bidi-jira"
CONFLUENCE_TOKEN = "fixture-bidi-confluence"
BIDI_CONTROLS = (
    "\u061c\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"
)
BIDI_ESCAPES = "".join(f"\\u{ord(char):04x}" for char in BIDI_CONTROLS)

ISSUE = {
    "key": "DEMO-42",
    "fields": {
        "summary": f"Résumé {BIDI_CONTROLS} ✓",
        "status": {"name": f"St{BIDI_CONTROLS}atus"},
        "issuetype": {"name": "Bug"},
        "priority": {"name": "High"},
        "assignee": {"displayName": f"Привет{BIDI_CONTROLS}"},
        "description": f"raw {BIDI_CONTROLS} 日本語",
        "comment": {
            "total": 1,
            "comments": [
                {
                    "id": "1",
                    "author": {"displayName": f"Bob{BIDI_CONTROLS}"},
                    "created": "2024-01-02T03:04:05.000+0000",
                    "body": f"comment {BIDI_CONTROLS} \ud800",
                }
            ],
        },
    },
    "renderedFields": {"description": f"<p>rendered {BIDI_CONTROLS} 日本語 ✓</p>"},
}

SEARCH = {
    "startAt": 0,
    "maxResults": 50,
    "total": 1,
    "issues": [
        {
            "key": "DEMO-1",
            "fields": {
                "summary": f"Row {BIDI_CONTROLS}",
                "status": {"name": "Open"},
                "issuetype": {"name": "Task"},
                "priority": {"name": "Low"},
                "assignee": {"displayName": f"Ada{BIDI_CONTROLS}"},
                "updated": "2024-01-02T03:04:05.000+0000",
            },
        }
    ],
}

PAGE = {
    "id": "123",
    "type": "page",
    "status": "current",
    "title": f"Résumé {BIDI_CONTROLS} \ud800",
    "space": {"key": "DEMO", "name": "Demo Space"},
    "version": {"number": 1},
    "body": {
        "storage": {
            "value": (
                f"<p>Параграф {BIDI_CONTROLS} 日本語 ✓</p>"
                '<ac:structured-macro ac:name="noformat"><ac:plain-text-body>'
                f"<![CDATA[code {BIDI_CONTROLS}]]></ac:plain-text-body>"
                "</ac:structured-macro>"
            ),
            "representation": "storage",
        }
    },
}

JIRA_ISSUE_PATH = "/jira/rest/api/2/issue/DEMO-42"
JIRA_SEARCH_PATH = "/jira/rest/api/2/search"
CONFLUENCE_PAGE_PATH = "/confluence/rest/api/content/123"


def run_human_command(
    args: list[str],
) -> tuple[subprocess.CompletedProcess[str], list[Request]]:
    seen: list[Request] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            seen.append(request_record(self))
            path = urlsplit(self.path).path
            if path == JIRA_ISSUE_PATH:
                send_json(self, 200, ISSUE)
            elif path == JIRA_SEARCH_PATH:
                send_json(self, 200, SEARCH)
            elif path == CONFLUENCE_PAGE_PATH:
                send_json(self, 200, PAGE)
            else:
                send_json(self, 404, {"message": "fixture route not found"})

    with serving(Handler) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        environment = {
            "ATLAWIRE_JIRA_URL": f"{origin}/jira/",
            "ATLAWIRE_JIRA_TOKEN": JIRA_TOKEN,
            "ATLAWIRE_CONFLUENCE_URL": f"{origin}/confluence/",
            "ATLAWIRE_CONFLUENCE_TOKEN": CONFLUENCE_TOKEN,
        }
        result = run_installed(args, environment)
    return result, seen


def test_issue_markdown_visibly_escapes_untrusted_controls() -> None:
    result, seen = run_human_command(
        ["issue", "DEMO-42", "--markdown", "--allow-http-loopback", "--token-from-env"]
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert seen == [
        (
            "GET",
            JIRA_ISSUE_PATH,
            {"expand": ["renderedFields"]},
            f"Bearer {JIRA_TOKEN}",
        )
    ]
    assert not any(char in result.stdout for char in BIDI_CONTROLS)
    assert "\ud800" not in result.stdout
    assert BIDI_ESCAPES in result.stdout
    assert "\\ud800" in result.stdout
    assert f"# DEMO-42: Résumé {BIDI_ESCAPES} ✓" in result.stdout
    assert f"**Assignee:** Привет{BIDI_ESCAPES}" in result.stdout
    assert f"rendered {BIDI_ESCAPES} 日本語" in result.stdout
    assert f"comment {BIDI_ESCAPES} \\ud800" in result.stdout
    assert "Résumé" in result.stdout
    assert "Привет" in result.stdout
    assert "日本語" in result.stdout
    assert "✓" in result.stdout


def test_jql_tsv_visibly_escapes_controls_and_does_not_crash() -> None:
    result, seen = run_human_command(
        [
            "jql",
            "project = DEMO",
            "--allow-http-loopback",
            "--token-from-env",
        ]
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert [request[1] for request in seen] == [JIRA_SEARCH_PATH]
    assert not any(char in result.stdout for char in BIDI_CONTROLS)
    assert BIDI_ESCAPES in result.stdout
    assert f"DEMO-1\tOpen\tTask\tLow\tAda{BIDI_ESCAPES}" in result.stdout
    assert f"Row {BIDI_ESCAPES}" in result.stdout


def test_page_markdown_visibly_escapes_untrusted_controls() -> None:
    result, seen = run_human_command(
        ["page", "123", "--markdown", "--allow-http-loopback", "--token-from-env"]
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert [request[1] for request in seen] == [CONFLUENCE_PAGE_PATH]
    assert not any(char in result.stdout for char in BIDI_CONTROLS)
    assert "\ud800" not in result.stdout
    assert BIDI_ESCAPES in result.stdout
    assert "\\ud800" in result.stdout
    assert f"# Résumé {BIDI_ESCAPES} \\ud800" in result.stdout
    assert f"Параграф {BIDI_ESCAPES} 日本語" in result.stdout
    assert f"code {BIDI_ESCAPES}" in result.stdout
    assert "Résumé" in result.stdout
    assert "Параграф" in result.stdout
    assert "日本語" in result.stdout
    assert "✓" in result.stdout
