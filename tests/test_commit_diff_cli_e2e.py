import json
import subprocess
from collections.abc import Sequence
from http.server import BaseHTTPRequestHandler
from typing import cast

import pytest

from tests._loopback import (
    Request,
    request_record,
    run_installed,
    send_json,
    serving,
)

TOKEN = "fixture-commit-diff"
JIRA_TOKEN = "wrong-product-jira-commit-diff"
CONFLUENCE_TOKEN = "wrong-product-confluence-commit-diff"
SENTINEL = "COMMIT-DIFF-SENTINEL"
CONTEXT = "/scm/bitbucket"
REPO = "DEMO/widgets"
SHA = "a1b2c3d"
DIFF_PATH = f"{CONTEXT}/rest/api/1.0/projects/DEMO/repos/widgets/commits/{SHA}/diff"
FIRST_PATH = "src/é +&?.py"
SECOND_PATH = "docs/read me#1.md"
ENCODED_FIRST = "src/%C3%A9%20%2B%26%3F.py"
ENCODED_SECOND = "docs/read%20me%231.md"


def diff_payload(path: str, text: str = "import re") -> dict[str, object]:
    """Build a coherent one-file diff used by the CLI fixtures."""
    return {
        "diffs": [
            {
                "source": {"toString": path},
                "destination": {"toString": path},
                "hunks": [
                    {
                        "sourceLine": 1,
                        "sourceSpan": 1,
                        "destinationLine": 1,
                        "destinationSpan": 1,
                        "segments": [
                            {
                                "type": "ADDED",
                                "lines": [{"line": text, "truncated": False}],
                            }
                        ],
                    }
                ],
            }
        ],
        "contextLines": "3",
        "extension": {"note": SENTINEL},
    }


def run_diff(
    *arguments: str,
    sha: str = SHA,
    responses: Sequence[tuple[int, object]],
) -> tuple[subprocess.CompletedProcess[str], list[Request], list[str | None]]:
    seen: list[Request] = []
    accepts: list[str | None] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            seen.append(request_record(self))
            accepts.append(self.headers.get("Accept"))
            index = len(seen) - 1
            if index >= len(responses):
                status, body = (
                    500,
                    {"errors": [{"message": "UNEXPECTED-EXTRA-REQUEST"}]},
                )
            else:
                status, body = responses[index]
            send_json(self, status, body)

    with serving(Handler) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        result = run_installed(
            [
                "commit-diff",
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
    return result, seen, accepts


def diff_request(path: str, context: str) -> Request:
    return (
        "GET",
        path,
        {
            "contextLines": [context],
            "whitespace": ["ignore-all"],
            "withComments": ["false"],
        },
        f"Bearer {TOKEN}",
    )


def test_whole_diff_json_prints_the_decoded_object_after_one_exact_get() -> None:
    payload = diff_payload("src/app.py")

    result, seen, accepts = run_diff(
        "--json", "--context", "0", responses=[(200, payload)]
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == payload
    assert seen == [diff_request(DIFF_PATH, "0")]
    assert accepts == ["application/json"]


def test_whole_diff_text_uses_the_commit_review_label_and_default_context() -> None:
    result, seen, accepts = run_diff(responses=[(200, diff_payload("src/app.py"))])

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout == (
        "# Bitbucket commit diff review "
        "(context=3; whitespace=ignore-all; not a patch)\n"
        "\n"
        "--- a/src/app.py\n"
        "+++ b/src/app.py\n"
        "@@ -1,1 +1,1 @@\n"
        "+import re\n"
    )
    assert "PR diff review" not in result.stdout
    assert seen == [diff_request(DIFF_PATH, "3")]
    assert accepts == ["application/json"]


def test_explicit_paths_are_encoded_once_and_requested_in_input_order() -> None:
    first = diff_payload("src/é +&?.py", "first")
    second = diff_payload("docs/read me#1.md", "second")

    result, seen, accepts = run_diff(
        "--json",
        "--context",
        "0",
        FIRST_PATH,
        SECOND_PATH,
        responses=[(200, first), (200, second)],
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == [first, second]
    assert seen == [
        diff_request(f"{DIFF_PATH}/{ENCODED_FIRST}", "0"),
        diff_request(f"{DIFF_PATH}/{ENCODED_SECOND}", "0"),
    ]
    assert accepts == ["application/json", "application/json"]


def test_one_explicit_path_still_returns_a_json_array() -> None:
    payload = diff_payload("src/app.py")

    result, seen, _accepts = run_diff(
        "--json", "src/app.py", responses=[(200, payload)]
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [payload]
    assert seen == [diff_request(f"{DIFF_PATH}/src/app.py", "3")]


def test_explicit_path_text_preserves_order_under_one_commit_header() -> None:
    first = diff_payload("src/b.py", "b")
    second = diff_payload("src/a.py", "a")

    result, seen, _accepts = run_diff(
        "src/b.py", "src/a.py", responses=[(200, first), (200, second)]
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout.count("# Bitbucket commit diff review") == 1
    assert result.stdout.index("--- a/src/b.py") < result.stdout.index("--- a/src/a.py")
    assert seen == [
        diff_request(f"{DIFF_PATH}/src/b.py", "3"),
        diff_request(f"{DIFF_PATH}/src/a.py", "3"),
    ]


def test_an_empty_unflagged_diff_gets_an_honest_marker() -> None:
    result, seen, _accepts = run_diff(responses=[(200, {"diffs": []})])

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout == (
        "# Bitbucket commit diff review "
        "(context=3; whitespace=ignore-all; not a patch)\n"
        "\n"
        "(no textual hunks in the response)\n"
    )
    assert seen == [diff_request(DIFF_PATH, "3")]


def test_a_late_http_failure_on_the_second_path_leaves_no_stdout() -> None:
    responses = [
        (200, diff_payload("src/first.py")),
        (503, {"errors": [{"message": SENTINEL}], "token": TOKEN}),
    ]

    result, seen, _accepts = run_diff(
        "--json", "src/first.py", "src/second.py", responses=responses
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "HTTP 503" in result.stderr
    for detail in (TOKEN, JIRA_TOKEN, CONFLUENCE_TOKEN, SENTINEL):
        assert detail not in result.stderr
    assert seen == [
        diff_request(f"{DIFF_PATH}/src/first.py", "3"),
        diff_request(f"{DIFF_PATH}/src/second.py", "3"),
    ]


def test_nested_truncation_on_the_second_path_leaves_no_stdout() -> None:
    second = diff_payload("src/second.py")
    diffs = cast(list[dict[str, object]], second["diffs"])
    hunks = cast(list[dict[str, object]], diffs[0]["hunks"])
    segments = cast(list[dict[str, object]], hunks[0]["segments"])
    segments[0]["truncated"] = "true"

    result, seen, _accepts = run_diff(
        "src/first.py",
        "src/second.py",
        responses=[(200, diff_payload("src/first.py")), (200, second)],
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "truncated" in result.stderr
    for detail in (TOKEN, JIRA_TOKEN, CONFLUENCE_TOKEN, SENTINEL):
        assert detail not in result.stderr
    assert seen == [
        diff_request(f"{DIFF_PATH}/src/first.py", "3"),
        diff_request(f"{DIFF_PATH}/src/second.py", "3"),
    ]


@pytest.mark.parametrize(
    "paths",
    [
        ("src/ok.py", "../secret"),
        ("src/ok.py", "/absolute.py"),
        ("src/ok.py", "src/%2e%2e/x.py"),
        ("src/ok.py", "src//double.py"),
    ],
    ids=["parent-segment", "absolute", "percent-escape", "empty-segment"],
)
def test_an_invalid_later_path_rejects_before_any_request(
    paths: tuple[str, ...],
) -> None:
    result, seen, accepts = run_diff(*paths, "--json", responses=[])

    assert result.returncode == 1
    assert result.stdout == ""
    assert "relative file path" in result.stderr
    assert seen == []
    assert accepts == []


def test_more_than_one_hundred_paths_rejects_before_any_request() -> None:
    result, seen, accepts = run_diff(
        *(f"src/file{index}.py" for index in range(101)),
        "--json",
        responses=[],
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "100" in result.stderr
    assert seen == []
    assert accepts == []


@pytest.mark.parametrize(
    "sha",
    ["main", "abc123", "a" * 41, "a1b2c3d/extra"],
    ids=["branch", "too-short", "too-long", "path-injection"],
)
def test_an_invalid_commit_id_rejects_before_any_request(sha: str) -> None:
    result, seen, accepts = run_diff("--json", sha=sha, responses=[])

    assert result.returncode == 1
    assert result.stdout == ""
    assert "commit ID" in result.stderr
    for detail in (TOKEN, JIRA_TOKEN, CONFLUENCE_TOKEN, SENTINEL):
        assert detail not in result.stderr
    assert seen == []
    assert accepts == []
