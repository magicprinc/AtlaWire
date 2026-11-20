import json
import subprocess
from http.server import BaseHTTPRequestHandler

import pytest

from tests._loopback import (
    Request,
    request_record,
    run_installed,
    send_json,
    serving,
)

TOKEN = "fixture-pr-files-only"
JIRA_TOKEN = "wrong-product-jira-files"
CONFLUENCE_TOKEN = "wrong-product-confluence-files"
SENTINEL = "PR-FILES-PAYLOAD-SENTINEL"
ID_MARKER = "PR-FILES-ID-MARKER"
CONTEXT = "/scm/bitbucket"
PR_PATH = f"{CONTEXT}/rest/api/1.0/projects/DEMO/repos/widgets/pull-requests/7"
CHANGES_PATH = f"{PR_PATH}/changes"
RAW_CHANGES_PATH = f"{CHANGES_PATH}?limit=1000"
EXPECTED = ("GET", CHANGES_PATH, {"limit": ["1000"]}, f"Bearer {TOKEN}")
EXPECTED_SHOW = ("GET", PR_PATH, {}, f"Bearer {TOKEN}")

ROWS = [
    {
        "path": {
            "components": ["src", "main.py"],
            "parent": "src",
            "name": "main.py",
            "extension": "py",
            "toString": "src/main.py",
        },
        "type": "MODIFY",
        "nodeType": "FILE",
        "executable": False,
        "srcPath": {"toString": "src/old.py"},
    },
    {
        "path": "docs/weird\x07.txt",
        "type": "ADD",
        "nodeType": "FILE",
    },
    {
        "path": "README.md",
        "type": "DELETE",
        "nodeType": "DIRECTORY",
    },
    {
        "path": {"components": ["docs", "old.txt"], "name": "old.txt"},
        "type": None,
    },
]
EXPECTED_ROWS = [
    {"path": "src/main.py", "type": "MODIFY", "node": "FILE"},
    {"path": "docs/weird\x07.txt", "type": "ADD", "node": "FILE"},
    {"path": "README.md", "type": "DELETE", "node": "DIRECTORY"},
    {"path": "docs/old.txt", "type": None, "node": None},
]
EXPECTED_TSV = (
    "# 4 row(s)\n"
    "path\ttype\tnode\n"
    "src/main.py\tMODIFY\tFILE\n"
    "docs/weird\\x07.txt\tADD\tFILE\n"
    "README.md\tDELETE\tDIRECTORY\n"
    "docs/old.txt\t\t\n"
)


def changes_payload() -> dict[str, object]:
    return {
        "size": 4,
        "limit": 1000,
        "isLastPage": True,
        "start": 0,
        "nextPageStart": 4,
        "values": ROWS,
    }


def run_pr(
    *arguments: str,
    response: tuple[int, object],
    repo: str = "DEMO/widgets",
    pr_id: str = "7",
) -> tuple[
    subprocess.CompletedProcess[str], list[Request], list[str], list[str | None]
]:
    seen: list[Request] = []
    raw_paths: list[str] = []
    accepts: list[str | None] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            seen.append(request_record(self))
            raw_paths.append(self.path)
            accepts.append(self.headers.get("Accept"))
            status, body = response
            send_json(self, status, body)

    with serving(Handler) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        result = run_installed(
            [
                "pr",
                repo,
                pr_id,
                *arguments,
                "--base-url",
                f"{origin}{CONTEXT}/",
                "--allow-http-loopback",
                "--token-from-env",
            ],
            {
                "ATLAWIRE_BITBUCKET_URL": f"{origin}{CONTEXT}/",
                "ATLAWIRE_BITBUCKET_TOKEN": TOKEN,
                "ATLAWIRE_JIRA_URL": f"{origin}/wrong-jira/",
                "ATLAWIRE_JIRA_TOKEN": JIRA_TOKEN,
                "ATLAWIRE_CONFLUENCE_URL": f"{origin}/wrong-confluence/",
                "ATLAWIRE_CONFLUENCE_TOKEN": CONFLUENCE_TOKEN,
            },
        )
    return result, seen, raw_paths, accepts


def test_files_prints_legacy_tsv_after_one_configured_request() -> None:
    result, seen, raw_paths, accepts = run_pr(
        "files", response=(200, changes_payload())
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout == EXPECTED_TSV
    assert seen == [EXPECTED]
    assert raw_paths == [RAW_CHANGES_PATH]
    assert accepts == ["application/json"]


def test_files_json_is_the_projected_array_only() -> None:
    result, seen, raw_paths, accepts = run_pr(
        "files", "--json", response=(200, changes_payload())
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == EXPECTED_ROWS
    assert json.loads(result.stdout)[3]["type"] is None
    assert seen == [EXPECTED]
    assert raw_paths == [RAW_CHANGES_PATH]
    assert accepts == ["application/json"]


def test_show_with_json_remains_raw_and_unchanged() -> None:
    body = {
        "id": 7,
        "title": "Talking Nerdy — α",
        "state": "OPEN",
        "extension": {"nested": [None, True, 1.5]},
    }

    result, seen, raw_paths, accepts = run_pr(
        "show",
        "--json",
        response=(200, body),
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == body
    assert seen == [EXPECTED_SHOW]
    assert raw_paths == [PR_PATH]
    assert accepts == ["application/json"]


def test_a_page_capped_at_the_reported_limit_fails_without_output() -> None:
    body = {
        "size": 1,
        "limit": 1,
        "isLastPage": True,
        "start": 0,
        "values": [{"path": SENTINEL, "type": "ADD", "nodeType": "FILE"}],
    }

    result, seen, _raw_paths, accepts = run_pr("files", response=(200, body))

    assert result.returncode == 1
    assert result.stdout == ""
    assert "reported limit" in result.stderr
    assert SENTINEL not in result.stderr
    assert seen == [EXPECTED]
    assert accepts == ["application/json"]


def test_a_nonterminal_page_is_rejected_without_a_second_request() -> None:
    body = {
        "size": 1,
        "limit": 1000,
        "isLastPage": False,
        "nextPageStart": 1,
        "start": 0,
        "values": [{"path": "a.txt", "type": "ADD", "nodeType": "FILE"}],
    }

    result, seen, _raw_paths, accepts = run_pr("files", response=(200, body))

    assert result.returncode == 1
    assert result.stdout == ""
    assert "terminal" in result.stderr
    assert seen == [EXPECTED]
    assert accepts == ["application/json"]


def test_explicit_truncation_is_reported_distinctly() -> None:
    body = {
        "size": 2,
        "limit": 1000,
        "isLastPage": True,
        "start": 0,
        "truncated": True,
        "values": [
            {"path": "a.txt", "type": "ADD", "nodeType": "FILE"},
            {"path": "b.txt", "type": "ADD", "nodeType": "FILE"},
        ],
    }

    result, seen, _raw_paths, _accepts = run_pr("files", response=(200, body))

    assert result.returncode == 1
    assert result.stdout == ""
    assert "reported truncated" in result.stderr
    assert "reported limit" not in result.stderr
    assert seen == [EXPECTED]


def test_http_errors_are_sanitized_and_not_retried() -> None:
    body = {"errors": [{"message": SENTINEL}], "token": TOKEN, "x": SENTINEL}

    result, seen, _raw_paths, _accepts = run_pr("files", response=(500, body))

    assert result.returncode == 1
    assert result.stdout == ""
    assert "HTTP 500" in result.stderr
    for detail in (TOKEN, JIRA_TOKEN, CONFLUENCE_TOKEN, SENTINEL):
        assert detail not in result.stderr
    assert seen == [EXPECTED]


@pytest.mark.parametrize(
    ("repo", "pr_id"),
    [
        ("DEMO", "7"),
        ("DEMO/widgets/extra", "7"),
        ("DEMO/widgets", "0"),
        ("DEMO/widgets", ID_MARKER),
    ],
    ids=["repo", "extra-segment", "zero-id", "marker-id"],
)
def test_invalid_identity_fails_before_any_request(repo: str, pr_id: str) -> None:
    result, seen, raw_paths, accepts = run_pr(
        "files", response=(200, changes_payload()), repo=repo, pr_id=pr_id
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert TOKEN not in result.stderr
    assert ID_MARKER not in result.stderr
    assert seen == []
    assert raw_paths == []
    assert accepts == []
