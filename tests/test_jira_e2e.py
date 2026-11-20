import json
import os
import shutil
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

import pytest

TOKEN = "fixture-jira-only"
ISSUE = {
    "key": "DEMO-42",
    "fields": {"summary": "Résumé"},
    "renderedFields": {"description": "<p>Details</p>"},
}


@pytest.mark.parametrize(
    ("argument", "status", "payload", "expected_error", "requests_expected"),
    [
        ("DEMO-42", 200, json.dumps(ISSUE), None, 1),
        (
            "https://other.example.invalid/jira/browse/DEMO-42?x=1",
            200,
            json.dumps(ISSUE),
            None,
            1,
        ),
        (
            "https://other.example.invalid/browse/DEMO-42/extra",
            200,
            "{}",
            "issue key",
            0,
        ),
        ("DEMO-42", 404, json.dumps({"message": TOKEN}), "HTTP 404", 1),
        ("DEMO-42", 200, "[]", "JSON object", 1),
        ("DEMO-42", 200, "{}", "Jira issue with a key and fields", 1),
        (
            "DEMO-42",
            200,
            json.dumps({"key": "", "fields": {}}),
            "Jira issue with a key and fields",
            1,
        ),
        (
            "DEMO-42",
            200,
            json.dumps({"key": "demo-42", "fields": {}}),
            "Jira issue with a key and fields",
            1,
        ),
        ("DEMO-42", 200, '{"key":"DEMO-42","fields":{"value":NaN}}', "JSON", 1),
        ("DEMO-42", 200, '{"key":"DEMO-42","fields":{"value":1e400}}', "JSON", 1),
    ],
)
def test_installed_issue_command(
    argument: str,
    status: int,
    payload: str,
    expected_error: str | None,
    requests_expected: int,
) -> None:
    script = shutil.which("atlawire")
    assert script is not None, "Install AtlaWire before running its CLI E2E suite."
    seen: list[tuple[str, bool]] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            seen.append(
                (self.path, self.headers.get("Authorization") == f"Bearer {TOKEN}")
            )
            body = payload.encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    with HTTPServer(("127.0.0.1", 0), Handler) as server:
        worker = Thread(target=server.serve_forever, args=(0.05,), daemon=True)
        worker.start()
        try:
            result = subprocess.run(
                [
                    script,
                    "issue",
                    argument,
                    "--allow-http-loopback",
                    "--token-from-env",
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

    assert seen == [("/jira/rest/api/2/issue/DEMO-42?expand=renderedFields", True)] * (
        requests_expected
    )
    if expected_error:
        assert result.returncode == 1, result.stderr
        assert result.stdout == ""
        assert expected_error in result.stderr
        assert TOKEN not in result.stderr
    else:
        assert result.returncode == 0, result.stderr
        assert not result.stderr
        assert json.loads(result.stdout) == ISSUE


def run_issue(
    payload: object, *options: str
) -> tuple[subprocess.CompletedProcess[str], list[tuple[str, bool]]]:
    script = shutil.which("atlawire")
    assert script is not None, "Install AtlaWire before running its CLI E2E suite."
    seen: list[tuple[str, bool]] = []
    body = json.dumps(payload).encode()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            seen.append(
                (self.path, self.headers.get("Authorization") == f"Bearer {TOKEN}")
            )
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    with HTTPServer(("127.0.0.1", 0), Handler) as server:
        worker = Thread(target=server.serve_forever, args=(0.05,), daemon=True)
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


@pytest.mark.parametrize("options", [(), ("--markdown",)], ids=["json", "markdown"])
def test_installed_issue_rejects_a_malformed_key_in_both_output_modes(
    options: tuple[str, ...],
) -> None:
    result, seen = run_issue({"key": "demo-42", "fields": {}}, *options)

    assert seen == [("/jira/rest/api/2/issue/DEMO-42?expand=renderedFields", True)]
    assert result.returncode == 1
    assert result.stdout == ""
    assert "Jira issue with a key and fields" in result.stderr
    assert TOKEN not in result.stderr


@pytest.mark.parametrize("options", [(), ("--markdown",)], ids=["json", "markdown"])
def test_installed_issue_keeps_a_moved_structurally_valid_key(
    options: tuple[str, ...],
) -> None:
    issue = {**ISSUE, "key": "MOVED-7"}

    result, seen = run_issue(issue, *options)

    assert seen == [("/jira/rest/api/2/issue/DEMO-42?expand=renderedFields", True)]
    assert result.returncode == 0, result.stderr
    assert not result.stderr
    if options:
        assert result.stdout.startswith("# MOVED-7:")
    else:
        assert json.loads(result.stdout)["key"] == "MOVED-7"
