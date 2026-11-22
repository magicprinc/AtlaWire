"""Installed-CLI regressions for search-summary credential reconstruction.

A token may contain ``/``; separate valid project and repository fields can
form it only when the summary joins them. The complete rendered summary must be
checked before any stdout byte is written.
"""

import json
import os
import shutil
import subprocess
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from tests._loopback import Request, request_record, send_json, serving

TOKEN = "K8F2M1P7/n9b4v6q3x7r2m8a5"
CONTEXT = "/bitbucket"
SEARCH_PATH = f"{CONTEXT}/rest/search/latest/search"
GENERIC = "The response contained the session bearer token."
MISSING_BBK = "C:/TMP/opencode/nonexistent-bbk-search-guard.json"


def clean_environment(**values: str) -> dict[str, str]:
    env = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith("ATLAWIRE_") and name != "BBK_CREDENTIALS"
    }
    env.update(values)
    return env


def search_payload(project: str, repository: str) -> dict[str, object]:
    return {
        "code": {
            "values": [
                {
                    "repository": {
                        "project": {"key": project},
                        "slug": repository,
                    },
                    "file": "src/app.py",
                    "hitCount": 1,
                    "hitContexts": [
                        [{"line": 1, "text": "<em>needle</em>"}]
                    ],
                }
            ],
            "isLastPage": True,
        }
    }


def run_search(
    token: str, payload: dict[str, object], *extra: str
) -> tuple[subprocess.CompletedProcess[str], list[Request]]:
    seen: list[Request] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length") or "0")
            if length:
                self.rfile.read(length)
            record = request_record(self)
            seen.append(record)
            if record[1] != SEARCH_PATH or record[3] != f"Bearer {token}":
                send_json(self, 404, {"message": "unexpected request"})
                return
            send_json(self, 200, payload)

        def do_GET(self) -> None:
            seen.append(request_record(self))
            send_json(self, 405, {"message": "GET refused"})

    with serving(Handler) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        env = clean_environment(
            ATLAWIRE_BITBUCKET_URL=f"{origin}{CONTEXT}/",
            ATLAWIRE_BITBUCKET_TOKEN=token,
            ATLAWIRE_JIRA_URL=f"{origin}/wrong-jira/",
            ATLAWIRE_JIRA_TOKEN="wrong-product-fixture",
            ATLAWIRE_CONFLUENCE_URL=f"{origin}/wrong-confluence/",
            ATLAWIRE_CONFLUENCE_TOKEN="wrong-product-fixture",
            BBK_CREDENTIALS=MISSING_BBK,
        )
        script = shutil.which("atlawire")
        assert script is not None, "Install AtlaWire before running its CLI tests."
        result = subprocess.run(
            [
                script,
                "search",
                "needle",
                "--limit",
                "1",
                *extra,
                "--token-from-env",
                "--allow-http-loopback",
            ],
            env=env,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    return result, seen


def test_search_summary_rejects_a_token_reconstructed_by_project_and_repo() -> None:
    result, seen = run_search(
        TOKEN, search_payload("K8F2M1P7", "n9b4v6q3x7r2m8a5")
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert GENERIC in result.stderr
    assert TOKEN not in result.stdout
    assert TOKEN not in result.stderr
    assert "Traceback" not in result.stderr
    assert len(seen) == 1
    assert seen[0][0] == "POST"
    assert seen[0][1] == SEARCH_PATH
    assert seen[0][2] == {}
    assert seen[0][3] == f"Bearer {TOKEN}"


def test_search_json_keeps_separate_project_and_repo_fragments() -> None:
    result, seen = run_search(
        TOKEN,
        search_payload("K8F2M1P7", "n9b4v6q3x7r2m8a5"),
        "--json",
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    rows = json.loads(result.stdout)
    assert rows[0]["project"] == "K8F2M1P7"
    assert rows[0]["repository"] == "n9b4v6q3x7r2m8a5"
    assert TOKEN not in result.stdout
    assert len(seen) == 1
    assert seen[0][0] == "POST"
    assert seen[0][1] == SEARCH_PATH


def test_search_summary_normal_output_is_unchanged() -> None:
    safe_token = "synthetic-search-token-normal-7q"
    payload = search_payload("SAFE", "widgets")

    result, seen = run_search(safe_token, payload)

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout == (
        "# 1 file(s) (first page only; use --all for every page)\n"
        "SAFE/widgets:src/app.py (1 hits) highlighted L1: needle\n"
    )
    assert len(seen) == 1
    assert seen[0][0] == "POST"
    assert seen[0][1] == SEARCH_PATH


def test_search_json_still_prints_the_projected_rows() -> None:
    safe_token = "synthetic-search-token-json-8r"
    payload = search_payload("SAFE", "widgets")

    result, seen = run_search(safe_token, payload, "--json")

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    rows = json.loads(result.stdout)
    assert rows[0]["project"] == "SAFE"
    assert rows[0]["repository"] == "widgets"
    assert rows[0]["file"] == "src/app.py"
    assert len(seen) == 1


def test_the_missing_bbk_credentials_path_is_synthetic() -> None:
    assert not Path(MISSING_BBK).exists()
