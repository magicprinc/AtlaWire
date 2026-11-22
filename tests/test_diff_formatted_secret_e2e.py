"""Installed-CLI regressions for tokens created only by diff formatting.

A synthetic bearer token ``a/example-file-token`` is formed when the review
renderer adds the ``a/`` source prefix to a raw path ``example-file-token``.
The wire response therefore contains no complete token, so only the post-render
guard can stop the formatted review. Every response is synthetic loopback data.
"""

import json
import os
import subprocess
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from tests._loopback import (
    Request,
    request_record,
    run_installed,
    send_json,
    serving,
)

TOKEN = "a/example-file-token"
MESSAGE = "The response contained the session bearer token."
CONTEXT = "/scm/bitbucket"
REPO = "DEMO/widgets"
PR_ID = "7"
SHA = "a1b2c3d"
PR_DIFF_PATH = (
    f"{CONTEXT}/rest/api/1.0/projects/DEMO/repos/widgets"
    f"/pull-requests/{PR_ID}/diff"
)
COMMIT_DIFF_PATH = (
    f"{CONTEXT}/rest/api/1.0/projects/DEMO/repos/widgets/commits/{SHA}/diff"
)
FORMATTED_TOKEN_PATH = "example-file-token"
BENIGN_PATH = "src/app.py"


def diff_payload(path: str) -> dict[str, object]:
    """Return a valid one-file diff with no textual hunks."""
    return {
        "diffs": [
            {
                "source": {"toString": path},
                "destination": {"toString": path},
                "hunks": [],
            }
        ]
    }


def environment(origin: str, missing_credentials: Path) -> dict[str, str]:
    env = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith("ATLAWIRE_") and name != "BBK_CREDENTIALS"
    }
    env.update(
        {
            "ATLAWIRE_BITBUCKET_URL": f"{origin}{CONTEXT}/",
            "ATLAWIRE_BITBUCKET_TOKEN": TOKEN,
            "ATLAWIRE_JIRA_URL": f"{origin}/wrong-jira/",
            "ATLAWIRE_JIRA_TOKEN": "wrong-product-jira-diff-secret",
            "ATLAWIRE_CONFLUENCE_URL": f"{origin}/wrong-confluence/",
            "ATLAWIRE_CONFLUENCE_TOKEN": "wrong-product-confluence-diff-secret",
            "BBK_CREDENTIALS": str(missing_credentials),
        }
    )
    assert not missing_credentials.exists()
    return env


def _run_diff(
    arguments: list[str], payload: dict[str, object], tmp_path: Path
) -> tuple[subprocess.CompletedProcess[str], list[Request]]:
    seen: list[Request] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            seen.append(request_record(self))
            send_json(self, 200, payload)

    with serving(Handler) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        result = run_installed(
            [
                *arguments,
                "--base-url",
                f"{origin}{CONTEXT}/",
                "--allow-http-loopback",
                "--token-from-env",
            ],
            environment(origin, tmp_path / "missing-credentials.json"),
        )
    return result, seen


def _diff_request(path: str) -> Request:
    return (
        "GET",
        path,
        {
            "contextLines": ["3"],
            "whitespace": ["ignore-all"],
            "withComments": ["false"],
        },
        f"Bearer {TOKEN}",
    )


def _assert_rejected(
    result: subprocess.CompletedProcess[str], seen: list[Request], path: str
) -> None:
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == f"Error: {MESSAGE}\n"
    assert TOKEN not in result.stdout
    assert TOKEN not in result.stderr
    assert "# Bitbucket" not in result.stdout
    assert "--- a/" not in result.stdout
    assert seen == [_diff_request(path)]


def test_pull_request_review_rejects_token_formed_by_the_source_prefix(
    tmp_path: Path,
) -> None:
    payload = diff_payload(FORMATTED_TOKEN_PATH)
    assert TOKEN not in json.dumps(payload)
    result, seen = _run_diff(["pr", REPO, PR_ID, "diff"], payload, tmp_path)

    _assert_rejected(result, seen, PR_DIFF_PATH)


def test_commit_review_rejects_token_formed_by_the_source_prefix(
    tmp_path: Path,
) -> None:
    payload = diff_payload(FORMATTED_TOKEN_PATH)
    assert TOKEN not in json.dumps(payload)
    result, seen = _run_diff(["commit-diff", REPO, SHA], payload, tmp_path)

    _assert_rejected(result, seen, COMMIT_DIFF_PATH)


def test_pull_request_review_still_renders_benign_paths(tmp_path: Path) -> None:
    result, seen = _run_diff(
        ["pr", REPO, PR_ID, "diff"],
        diff_payload(BENIGN_PATH),
        tmp_path,
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout == (
        "# Bitbucket PR diff review "
        "(context=3; whitespace=ignore-all; not a patch)\n"
        "\n"
        "--- a/src/app.py\n"
        "+++ b/src/app.py\n"
        "(no textual hunks in this file)\n"
    )
    assert TOKEN not in result.stdout
    assert seen == [_diff_request(PR_DIFF_PATH)]


def test_commit_review_still_renders_benign_paths(tmp_path: Path) -> None:
    result, seen = _run_diff(
        ["commit-diff", REPO, SHA],
        diff_payload(BENIGN_PATH),
        tmp_path,
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout == (
        "# Bitbucket commit diff review "
        "(context=3; whitespace=ignore-all; not a patch)\n"
        "\n"
        "--- a/src/app.py\n"
        "+++ b/src/app.py\n"
        "(no textual hunks in this file)\n"
    )
    assert TOKEN not in result.stdout
    assert seen == [_diff_request(COMMIT_DIFF_PATH)]


def test_pull_request_json_still_returns_the_unformatted_path(tmp_path: Path) -> None:
    payload = diff_payload(FORMATTED_TOKEN_PATH)
    result, seen = _run_diff(
        ["pr", REPO, PR_ID, "diff", "--json"],
        payload,
        tmp_path,
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == payload
    assert TOKEN not in result.stdout
    assert seen == [_diff_request(PR_DIFF_PATH)]


def test_commit_json_still_returns_the_unformatted_path(tmp_path: Path) -> None:
    payload = diff_payload(FORMATTED_TOKEN_PATH)
    result, seen = _run_diff(
        ["commit-diff", REPO, SHA, "--json"],
        payload,
        tmp_path,
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == payload
    assert TOKEN not in result.stdout
    assert seen == [_diff_request(COMMIT_DIFF_PATH)]
