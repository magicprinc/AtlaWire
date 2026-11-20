import json
import subprocess
from collections.abc import Sequence
from http.server import BaseHTTPRequestHandler

import pytest

from tests._loopback import (
    Request,
    request_record,
    run_installed,
    send_json,
    serving,
)

TOKEN = "fixture-commit-detail"
JIRA_TOKEN = "wrong-product-jira-commit-detail"
CONFLUENCE_TOKEN = "wrong-product-confluence-commit-detail"
SENTINEL = "COMMIT-DETAIL-SENTINEL"
CONTEXT = "/scm/bitbucket"
REPO = "DEMO/widgets"
SHA = "A1B2C3D"
FULL_ID = "a1b2c3d0123456789abcdef0123456789abcdef0"
COMMIT_PATH = f"{CONTEXT}/rest/api/1.0/projects/DEMO/repos/widgets/commits/{SHA}"

COMMIT: dict[str, object] = {
    "id": FULL_ID,
    "displayId": "a1b2c3d",
    "author": {"name": "charlie", "emailAddress": "charlie@example.invalid"},
    "authorTimestamp": 1527228363490,
    "committer": {"name": "charlie", "emailAddress": "charlie@example.invalid"},
    "committerTimestamp": 1527228363490,
    "message": "WIP on feature 1",
    "parents": [
        {
            "id": "deadbeef0123456789abcdef0123456789abcdef",
            "displayId": "deadbee",
        }
    ],
    "links": {"self": [{"href": "https://example.invalid/never-followed"}]},
}


def run_commit(
    *arguments: str,
    sha: str = SHA,
    responses: Sequence[tuple[int, object]],
) -> tuple[subprocess.CompletedProcess[str], list[Request], list[str]]:
    seen: list[Request] = []
    extra_methods: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            seen.append(request_record(self))
            index = len(seen) - 1
            if index >= len(responses):
                status, body = (
                    500,
                    {"errors": [{"message": "UNEXPECTED-EXTRA-REQUEST"}]},
                )
            else:
                status, body = responses[index]
            send_json(self, status, body)

        def do_HEAD(self) -> None:
            extra_methods.append("HEAD")
            self.send_error(405)

        def do_OPTIONS(self) -> None:
            extra_methods.append("OPTIONS")
            self.send_error(405)

    with serving(Handler) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        result = run_installed(
            [
                "commit",
                REPO,
                sha,
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
    return result, seen, extra_methods


def commit_request() -> Request:
    return ("GET", COMMIT_PATH, {}, f"Bearer {TOKEN}")


def test_commit_makes_one_exact_request_and_returns_the_decoded_object() -> None:
    result, seen, extra = run_commit(responses=[(200, COMMIT)])

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == COMMIT
    assert seen == [commit_request()]
    assert extra == []


@pytest.mark.parametrize(
    "body",
    [
        {**COMMIT, "id": "deadbeef0123456789abcdef0123456789abcdef"},
        {key: value for key, value in COMMIT.items() if key != "id"},
        {**COMMIT, "id": "a1b2c3d"},
    ],
    ids=["different-full-id", "missing-id", "short-id"],
)
def test_a_response_id_that_does_not_match_the_request_fails_statically(
    body: dict[str, object],
) -> None:
    result, seen, extra = run_commit(responses=[(200, body)])

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == "Error: Invalid commit identity in the response.\n"
    for detail in (TOKEN, JIRA_TOKEN, CONFLUENCE_TOKEN, SENTINEL):
        assert detail not in result.stderr
    assert seen == [commit_request()]
    assert extra == []


@pytest.mark.parametrize(
    "sha",
    ["abc123", "a1b2c3d\n", "refs/heads/main"],
    ids=["too-short", "control", "symbolic-ref"],
)
def test_an_invalid_commit_id_fails_before_any_request(sha: str) -> None:
    result, seen, extra = run_commit(sha=sha, responses=[])

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == (
        "Error: Expected a commit ID as 7 to 40 hexadecimal characters.\n"
    )
    assert seen == []
    assert extra == []
