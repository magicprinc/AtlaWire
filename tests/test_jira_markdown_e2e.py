import json
import os
import shutil
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

TOKEN = "fixture-issue-markdown-only"
PATH = "/jira/rest/api/2/issue/DEMO-42?expand=renderedFields"

RAW_DESCRIPTION = "Wiki *raw* description\n```\nfenced\n```\nand `tick`"
RAW_COMMENT = "raw C\n```\nkeep literal\n```"

ISSUE = {
    "key": "DEMO-42",
    "fields": {
        "summary": "Résumé\n# injected [x]",
        "status": {"name": "In Progress"},
        "issuetype": {"name": "Bug"},
        "priority": {"name": "High"},
        "assignee": {"displayName": "Ada\x1b[31m\nLovelace"},
        "description": RAW_DESCRIPTION,
        "comment": {
            "total": 5,
            "comments": [
                {
                    "id": 102,
                    "author": {"displayName": "Bob"},
                    "created": "2024-02-03T04:05:06.000+0000",
                    "body": "raw B should be replaced",
                },
                {
                    "id": "101",
                    "author": None,
                    "created": None,
                    "body": RAW_COMMENT,
                },
                {
                    "id": 103,
                    "author": {"displayName": "Eve"},
                    "created": "2024-03-04T05:06:07.000+0000",
                    "body": "raw D should be replaced",
                },
            ],
        },
    },
    "renderedFields": {
        "comment": {
            "comments": [
                {
                    "id": 102,
                    "body": (
                        "<p>Rendered B "
                        '<a href="https://evil.invalid/secret">label</a> '
                        '<img src="https://evil.invalid/i.png" alt="alt text">'
                        "</p>"
                    ),
                },
                {
                    "id": "103",
                    "body": (
                        "<h2>Rendered D</h2>"
                        "<p>&lt;script&gt;alert(1)&lt;/script&gt;</p>"
                    ),
                },
            ]
        }
    },
}


def run_issue(
    *options: str,
) -> tuple[subprocess.CompletedProcess[str], list[tuple[str, bool]]]:
    script = shutil.which("atlawire")
    assert script is not None, "Install AtlaWire before running its CLI E2E suite."
    seen: list[tuple[str, bool]] = []
    payload = json.dumps(ISSUE).encode()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            seen.append(
                (self.path, self.headers.get("Authorization") == f"Bearer {TOKEN}")
            )
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    with HTTPServer(("127.0.0.1", 0), Handler) as server:
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            result = subprocess.run(
                [
                    script,
                    "issue",
                    "DEMO-42",
                    "--allow-http-loopback",
                    "--token-from-env",
                    *options,
                ],
                env={
                    **os.environ,
                    "ATLAWIRE_JIRA_URL": f"http://127.0.0.1:{server.server_port}/jira/",
                    "ATLAWIRE_JIRA_TOKEN": TOKEN,
                    "ATLAWIRE_BITBUCKET_TOKEN": "wrong-product-fixture",
                },
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        finally:
            server.shutdown()
            worker.join(timeout=5)
            assert not worker.is_alive()
    return result, seen


def test_issue_without_the_flag_keeps_json_and_fetches_once() -> None:
    result, seen = run_issue()

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout == json.dumps(ISSUE) + "\n"
    assert seen == [(PATH, True)]


def test_issue_markdown_fetches_once_and_renders_by_id_with_raw_fallback() -> None:
    result, seen = run_issue("--markdown")

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert seen == [(PATH, True)]
    rendered = result.stdout
    assert rendered.endswith("\n")
    assert not rendered.endswith("\n\n")
    assert rendered.startswith("# DEMO-42: Résumé # injected \\[x\\]\n")
    assert "\n# injected" not in rendered
    assert "\x1b" not in rendered
    assert "**Status:** In Progress · **Type:** Bug · **Priority:** High" in rendered
    assert "**Assignee:** Ada \\[31m Lovelace" in rendered

    first = rendered.index("### Comment 1 · Bob · 2024-02-03")
    second = rendered.index("### Comment 2")
    third = rendered.index("### Comment 3 · Eve · 2024-03-04")
    assert first < rendered.index("Rendered B") < second
    assert "Rendered A" not in rendered
    assert second < rendered.index("````text\n", second) < third
    assert RAW_COMMENT in rendered
    assert third < rendered.index("Rendered D")

    assert "````text\n" + RAW_DESCRIPTION in rendered
    assert "Comments are incomplete: showing 3 of 5." in rendered
    assert "https://evil.invalid" not in rendered
    assert "](https" not in rendered
    assert "![" not in rendered
    assert "<script>" not in rendered
    assert "\\<script\\>alert(1)\\</script\\>" in rendered
