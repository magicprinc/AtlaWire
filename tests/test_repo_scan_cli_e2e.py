"""Installed-CLI loopback checks for the planned ``scan-extension`` command.

The command is wired by another worker. These tests define the expected
``scan-extension --ext .py --json --workers 1`` contract: sorted rows over
multi-page listings, GET-only traffic with every write method recorded and
rejected, and no stdout when a later repository page fails. They fail until
that wiring lands.
"""

import json
import subprocess
import threading
from collections import Counter
from http.server import BaseHTTPRequestHandler

from tests._loopback import Request, request_record, run_installed, send_json, serving

TOKEN = "fixture-scan-extension"
JIRA_TOKEN = "wrong-product-jira-scan"
CONFLUENCE_TOKEN = "wrong-product-confluence-scan"
SENTINEL = "SCAN-EXTENSION-SENTINEL"
CONTEXT = "/scm/bitbucket"
PROJECTS_PATH = f"{CONTEXT}/rest/api/1.0/projects"
ALPHA_REPOS_PATH = f"{PROJECTS_PATH}/ALPHA/repos"
BETA_REPOS_PATH = f"{PROJECTS_PATH}/BETA/repos"
ALPHA_TOOLS_FILES = f"{ALPHA_REPOS_PATH}/alpha-tools/files"
ALPHA_DOCS_FILES = f"{ALPHA_REPOS_PATH}/alpha-docs/files"
BETA_FILES = f"{BETA_REPOS_PATH}/beta-scripts/files"


def secret_error(path: str) -> dict[str, object]:
    return {
        "message": TOKEN,
        "path": path,
        "query": "fixture-query",
        "response": SENTINEL,
    }


def fixture(scenario: str, path: str, start: int) -> tuple[int, dict[str, object]]:
    if scenario in {"scoped", "scoped-failure"}:
        if path == ALPHA_REPOS_PATH:
            return 200, {
                "values": [{"slug": "alpha-tools"}, {"slug": "alpha-docs"}],
                "isLastPage": True,
            }
        if path == ALPHA_TOOLS_FILES:
            if scenario == "scoped":
                return 200, {
                    "values": ["app.py", "tests/test_app.PY", "README.md"],
                    "isLastPage": True,
                }
            return 200, {"values": ["app.py"], "isLastPage": True}
        if path == ALPHA_DOCS_FILES:
            if scenario == "scoped":
                return 200, {"values": ["guide.md"], "isLastPage": True}
            if start == 0:
                return 200, {
                    "values": ["notes.txt"],
                    "isLastPage": False,
                    "nextPageStart": 1,
                }
            return 503, secret_error(path)
        return 400, {"unexpected": [path, start]}
    if path == PROJECTS_PATH:
        if scenario == "failure":
            return 200, {"values": [{"key": "ALPHA"}], "isLastPage": True}
        if start == 0:
            return 200, {
                "values": [{"key": "ALPHA"}],
                "isLastPage": False,
                "nextPageStart": 1,
            }
        if start == 1:
            return 200, {"values": [{"key": "BETA"}], "isLastPage": True}
        return 400, {"unexpected": [path, start]}
    if path == ALPHA_REPOS_PATH:
        if scenario == "failure":
            return 200, {
                "values": [{"slug": "alpha-tools"}, {"slug": "alpha-docs"}],
                "isLastPage": True,
            }
        if start == 0:
            return 200, {
                "values": [{"slug": "alpha-tools"}],
                "isLastPage": False,
                "nextPageStart": 1,
            }
        if start == 1:
            return 200, {
                "values": [{"slug": "alpha-docs"}],
                "isLastPage": True,
            }
        return 400, {"unexpected": [path, start]}
    if path == BETA_REPOS_PATH:
        return 200, {
            "values": [{"slug": "beta-scripts"}],
            "isLastPage": True,
        }
    if path == ALPHA_TOOLS_FILES:
        if scenario == "failure":
            return 200, {"values": ["app.py"], "isLastPage": True}
        if start == 0:
            return 200, {
                "values": ["app.py"],
                "isLastPage": False,
                "nextPageStart": 1,
            }
        if start == 1:
            return 200, {
                "values": ["tests/test_app.PY", "README.md"],
                "isLastPage": True,
            }
        return 400, {"unexpected": [path, start]}
    if path == ALPHA_DOCS_FILES:
        if scenario == "failure":
            if start == 0:
                return 200, {
                    "values": ["notes.txt"],
                    "isLastPage": False,
                    "nextPageStart": 1,
                }
            return 503, secret_error(path)
        return 200, {"values": ["guide.md"], "isLastPage": True}
    if path == BETA_FILES:
        return 200, {"values": ["run.py"], "isLastPage": True}
    return 400, {"unexpected": [path, start]}


def run_scan(
    scenario: str, *, project: str | None = None
) -> tuple[subprocess.CompletedProcess[str], list[Request]]:
    seen: list[Request] = []
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def record(self) -> Request:
            record = request_record(self)
            with lock:
                seen.append(record)
            return record

        def reject(self) -> None:
            self.record()
            send_json(self, 405, {"error": "method not allowed"})

        def do_GET(self) -> None:
            record = self.record()
            start = int(record[2].get("start", ["-1"])[0])
            status, body = fixture(scenario, record[1], start)
            send_json(self, status, body)

        def do_POST(self) -> None:
            self.reject()

        def do_PUT(self) -> None:
            self.reject()

        def do_PATCH(self) -> None:
            self.reject()

        def do_DELETE(self) -> None:
            self.reject()

        def do_OPTIONS(self) -> None:
            self.reject()

        def do_TRACE(self) -> None:
            self.reject()

        def do_CONNECT(self) -> None:
            self.reject()

        def do_HEAD(self) -> None:
            self.record()
            self.send_response(405)
            self.send_header("Content-Length", "0")
            self.end_headers()

    with serving(Handler) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        arguments = [
            "scan-extension",
            "--ext",
            ".py",
            "--workers",
            "1",
            "--json",
            "--allow-http-loopback",
            "--token-from-env",
        ]
        if project is not None:
            arguments.extend(["--project", project])
        result = run_installed(
            arguments,
            {
                "ATLAWIRE_BITBUCKET_URL": f"{origin}{CONTEXT}/",
                "ATLAWIRE_BITBUCKET_TOKEN": TOKEN,
                "ATLAWIRE_JIRA_URL": f"{origin}/wrong-jira/",
                "ATLAWIRE_JIRA_TOKEN": JIRA_TOKEN,
                "ATLAWIRE_CONFLUENCE_URL": f"{origin}/wrong-confluence/",
                "ATLAWIRE_CONFLUENCE_TOKEN": CONFLUENCE_TOKEN,
            },
        )
    return result, seen


def assert_get_only(seen: list[Request]) -> None:
    """Reject any recorded write or non-GET method."""
    assert {method for method, _, _, _ in seen} == {"GET"}


def test_scan_extension_json_returns_sorted_rows_from_bitbucket() -> None:
    result, seen = run_scan("success")

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == [
        {
            "project": "ALPHA",
            "repository": "alpha-tools",
            "files": 3,
            "matched": 2,
            "sample": ["app.py", "tests/test_app.PY"],
        },
        {
            "project": "BETA",
            "repository": "beta-scripts",
            "files": 1,
            "matched": 1,
            "sample": ["run.py"],
        },
    ]
    assert Counter(
        (path, int(query["start"][0]), int(query["limit"][0]))
        for _, path, query, _ in seen
    ) == Counter(
        {
            (PROJECTS_PATH, 0, 100): 1,
            (PROJECTS_PATH, 1, 100): 1,
            (ALPHA_REPOS_PATH, 0, 100): 1,
            (ALPHA_REPOS_PATH, 1, 100): 1,
            (BETA_REPOS_PATH, 0, 100): 1,
            (ALPHA_TOOLS_FILES, 0, 100): 1,
            (ALPHA_TOOLS_FILES, 1, 100): 1,
            (ALPHA_DOCS_FILES, 0, 100): 1,
            (BETA_FILES, 0, 100): 1,
        }
    )
    assert_get_only(seen)
    assert all(
        auth == f"Bearer {TOKEN}" and path.startswith(CONTEXT)
        for _, path, _, auth in seen
    )


def test_scan_extension_late_failure_publishes_nothing_and_hides_details() -> None:
    result, seen = run_scan("failure")

    assert result.returncode == 1
    assert result.stdout == ""
    assert "HTTP 503" in result.stderr
    for detail in (TOKEN, ALPHA_DOCS_FILES, "fixture-query", SENTINEL):
        assert detail not in result.stderr
    assert_get_only(seen)
    assert all(
        auth == f"Bearer {TOKEN}" and path.startswith(CONTEXT)
        for _, path, _, auth in seen
    )
    assert [
        (path, int(query["start"][0]), int(query["limit"][0]))
        for _, path, query, _ in seen
    ] == [
        (PROJECTS_PATH, 0, 100),
        (ALPHA_REPOS_PATH, 0, 100),
        (ALPHA_TOOLS_FILES, 0, 100),
        (ALPHA_DOCS_FILES, 0, 100),
        (ALPHA_DOCS_FILES, 1, 100),
    ]


def test_scan_extension_project_scope_lists_only_this_project() -> None:
    result, seen = run_scan("scoped", project="ALPHA")

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == [
        {
            "project": "ALPHA",
            "repository": "alpha-tools",
            "files": 3,
            "matched": 2,
            "sample": ["app.py", "tests/test_app.PY"],
        }
    ]
    assert_get_only(seen)
    assert all(
        auth == f"Bearer {TOKEN}" and path.startswith(CONTEXT)
        for _, path, _, auth in seen
    )
    assert [
        (path, int(query["start"][0]), int(query["limit"][0]))
        for _, path, query, _ in seen
    ] == [
        (ALPHA_REPOS_PATH, 0, 100),
        (ALPHA_TOOLS_FILES, 0, 100),
        (ALPHA_DOCS_FILES, 0, 100),
    ]


def test_scan_extension_project_scope_failure_publishes_nothing() -> None:
    result, seen = run_scan("scoped-failure", project="ALPHA")

    assert result.returncode == 1
    assert result.stdout == ""
    assert "HTTP 503" in result.stderr
    for detail in (TOKEN, ALPHA_DOCS_FILES, "fixture-query", SENTINEL):
        assert detail not in result.stderr
    assert_get_only(seen)
    assert all(
        auth == f"Bearer {TOKEN}" and path.startswith(CONTEXT)
        for _, path, _, auth in seen
    )
    assert [
        (path, int(query["start"][0]), int(query["limit"][0]))
        for _, path, query, _ in seen
    ] == [
        (ALPHA_REPOS_PATH, 0, 100),
        (ALPHA_TOOLS_FILES, 0, 100),
        (ALPHA_DOCS_FILES, 0, 100),
        (ALPHA_DOCS_FILES, 1, 100),
    ]
