"""Installed-CLI regressions for credential-echo guards on rendered output.

The server responses are valid HTML/JSON; only HTML entity decoding in the
Markdown renderers reconstructs the active bearer token. The command must fail
with a fixed generic error and publish no transformed bytes.
"""

import os
import shutil
import subprocess
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from tests._loopback import Request, request_record, send_json, serving

TOKEN = "synthetic-entity-token-9k"
ENTITY_TOKEN = "synth&#101;tic-entity-token-9k"
JIRA_PATH = "/jira/rest/api/2/issue/DEMO-42"
CONFLUENCE_PATH = "/confluence/rest/api/content/123"
MISSING_BBK = str(
    Path(__file__).with_name("bbk-credentials-missing-guard-cli.json")
)
GENERIC = "The response contained the session bearer token."


def clean_environment(**values: str) -> dict[str, str]:
    env = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith("ATLAWIRE_") and name != "BBK_CREDENTIALS"
    }
    env.update(values)
    return env


def run_cli(
    args: list[str], path: str, payload: dict[str, object]
) -> tuple[subprocess.CompletedProcess[str], list[Request]]:
    seen: list[Request] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            record = request_record(self)
            seen.append(record)
            if record[1] != path or record[3] != f"Bearer {TOKEN}":
                send_json(self, 404, {"message": "unexpected request"})
                return
            send_json(self, 200, payload)

    with serving(Handler) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        env = clean_environment(
            ATLAWIRE_JIRA_URL=f"{origin}/jira/",
            ATLAWIRE_JIRA_TOKEN=TOKEN,
            ATLAWIRE_CONFLUENCE_URL=f"{origin}/confluence/",
            ATLAWIRE_CONFLUENCE_TOKEN=TOKEN,
            ATLAWIRE_BITBUCKET_URL=f"{origin}/wrong-bitbucket/",
            ATLAWIRE_BITBUCKET_TOKEN="wrong-product-fixture",
            BBK_CREDENTIALS=MISSING_BBK,
        )
        script = shutil.which("atlawire")
        assert script is not None, "Install AtlaWire before running its CLI tests."
        result = subprocess.run(
            [script, *args, "--token-from-env", "--allow-http-loopback"],
            env=env,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    return result, seen


def issue_payload() -> dict[str, object]:
    return {
        "key": "DEMO-42",
        "fields": {
            "summary": "Guard test",
            "status": {"name": "Open"},
            "issuetype": {"name": "Task"},
            "priority": None,
            "assignee": None,
            "description": "raw fallback",
        },
        "renderedFields": {
            "description": f"<p>{ENTITY_TOKEN}</p>",
        },
    }


def page_payload() -> dict[str, object]:
    return {
        "id": "123",
        "type": "page",
        "title": "Guard test",
        "version": {"number": 1},
        "space": {"key": "DEMO"},
        "body": {
            "storage": {
                "value": f"<p>{ENTITY_TOKEN}</p>",
                "representation": "storage",
            }
        },
    }


def assert_guarded(result: subprocess.CompletedProcess[str]) -> None:
    assert result.returncode == 1
    assert result.stdout == ""
    assert GENERIC in result.stderr
    assert TOKEN not in result.stderr
    assert TOKEN not in result.stdout
    assert "Traceback" not in result.stderr


def test_issue_markdown_rejects_an_entity_split_token() -> None:
    result, seen = run_cli(
        ["issue", "DEMO-42", "--markdown"], JIRA_PATH, issue_payload()
    )

    assert_guarded(result)
    assert seen == [
        (
            "GET",
            JIRA_PATH,
            {"expand": ["renderedFields"]},
            f"Bearer {TOKEN}",
        )
    ]


def test_page_markdown_rejects_an_entity_split_token() -> None:
    result, seen = run_cli(
        ["page", "123", "--markdown"], CONFLUENCE_PATH, page_payload()
    )

    assert_guarded(result)
    assert seen == [
        (
            "GET",
            CONFLUENCE_PATH,
            {"expand": ["body.storage,version,space,ancestors"]},
            f"Bearer {TOKEN}",
        )
    ]


def test_the_missing_bbk_credentials_path_is_synthetic() -> None:
    assert not Path(MISSING_BBK).exists()
