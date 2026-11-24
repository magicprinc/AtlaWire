"""End-to-end checks for the pr-review packet through the installed CLI."""

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "synthetic-pr-review-token"
BASE = "/rest/api/1.0/projects/PRJ/repos/widgets/pull-requests/5"
HASH_A = "a" * 40
HASH_B = "b" * 40


def _issue_file(index: int) -> dict[str, object]:
    return {
        "path": f"src/test/java/Sample{index}Test.java",
        "type": "MODIFY",
        "node": HASH_B,
    }


@pytest.fixture
def server(tmp_path):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path == BASE:
                body = {
                    "id": 5,
                    "title": "Sample change",
                    "state": "OPEN",
                    "description": "Synthetic",
                    "fromRef": {"displayId": "feature", "latestCommit": HASH_A},
                    "toRef": {"displayId": "main", "latestCommit": HASH_B},
                }
            elif path == f"{BASE}/commits":
                body = {"values": [], "isLastPage": True}
            elif path == f"{BASE}/changes":
                body = {
                    "values": [_issue_file(index) for index in range(12)],
                    "isLastPage": True,
                    "start": 0,
                    "size": 12,
                    "limit": 1000,
                }
            elif path == f"{BASE}/diff":
                # The diff names one file the changed list does not carry: a
                # push landed between the two reads.
                body = {
                    "diffs": [
                        {
                            "source": "src/extra/Unlisted.java",
                            "destination": "src/extra/Unlisted.java",
                            "hunks": [],
                        }
                    ]
                }
            else:
                self.send_error(404)
                return
            payload = json.dumps(body).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_port}", tmp_path / "missing.json"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


def _run(argv, *, base, credentials):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src")
    env["ATLAWIRE_BITBUCKET_TOKEN"] = TOKEN
    env["ATLAWIRE_BITBUCKET_URL"] = base
    env["BBK_CREDENTIALS"] = str(credentials)
    for name in ("ATLAWIRE_JIRA_URL", "ATLAWIRE_JIRA_TOKEN"):
        env.pop(name, None)
    return subprocess.run(
        [sys.executable, "-B", "-m", "atlawire", *argv],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )


def test_pr_review_no_diff_reports_the_shortened_test_name_list(server):
    base, credentials = server
    result = _run(
        [
            "pr-review",
            "PRJ/widgets",
            "5",
            "--no-diff",
            "--base-url",
            base,
            "--token-from-env",
            "--allow-http-loopback",
            "--json",
        ],
        base=base,
        credentials=credentials,
    )

    assert result.returncode == 0, result.stderr
    packet = json.loads(result.stdout)
    assert packet["checks"]["truncated"] == ["test_names"]
    assert len(packet["checks"]["test_names"]) == 10
    assert any(
        "test_names" in reason for reason in packet["profile"]["partial_reasons"]
    )
    assert packet["profile"]["partial"] is True


def test_pr_review_flags_a_diff_file_missing_from_the_changed_list(server):
    base, credentials = server
    result = _run(
        [
            "pr-review",
            "PRJ/widgets",
            "5",
            "--base-url",
            base,
            "--token-from-env",
            "--allow-http-loopback",
            "--json",
        ],
        base=base,
        credentials=credentials,
    )

    assert result.returncode == 0, result.stderr
    packet = json.loads(result.stdout)
    assert packet["diff"]["counts_complete"] is False
    assert any(
        "no matching diff entry" in reason
        for reason in packet["profile"]["partial_reasons"]
    )
    assert packet["profile"]["partial"] is True


def test_pr_review_rejects_an_oversized_url_without_a_traceback(server):
    base, credentials = server
    url = (
        "http://127.0.0.1/projects/PRJ/repos/widgets/pull-requests/"
        + "9" * 5000
    )

    result = _run(
        ["pr-review", url, "--base-url", base, "--token-from-env"],
        base=base,
        credentials=credentials,
    )

    assert result.returncode != 0
    assert "Traceback" not in result.stderr
    assert "pull-requests" in result.stderr
