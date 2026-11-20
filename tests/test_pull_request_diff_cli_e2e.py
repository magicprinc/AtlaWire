import json
import subprocess
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

TOKEN = "fixture-pr-diff-cli"
JIRA_TOKEN = "wrong-product-jira-diff-cli"
CONFLUENCE_TOKEN = "wrong-product-confluence-diff-cli"
SENTINEL = "PR-DIFF-CLI-SENTINEL"
CONTEXT = "/scm/bitbucket"
PR_PATH = f"{CONTEXT}/rest/api/1.0/projects/DEMO/repos/widgets/pull-requests/7"
DIFF_PATH = f"{PR_PATH}/diff"


def diff_payload(context: str) -> dict[str, object]:
    """Build a structurally coherent one-hunk diff response."""
    path = {
        "components": ["src", "app.py"],
        "parent": "src",
        "name": "app.py",
        "extension": "py",
        "toString": "src/app.py",
    }
    return {
        "diffs": [
            {
                "source": path,
                "destination": dict(path),
                "hunks": [
                    {
                        "sourceLine": 1,
                        "sourceSpan": 2,
                        "destinationLine": 1,
                        "destinationSpan": 3,
                        "segments": [
                            {
                                "type": "CONTEXT",
                                "lines": [
                                    {
                                        "destination": 1,
                                        "source": 1,
                                        "line": "import os",
                                        "truncated": False,
                                    }
                                ],
                                "truncated": False,
                            },
                            {
                                "type": "REMOVED",
                                "lines": [
                                    {
                                        "destination": 1,
                                        "source": 2,
                                        "line": f"import sys  # {SENTINEL}",
                                        "truncated": False,
                                    }
                                ],
                                "truncated": False,
                            },
                            {
                                "type": "ADDED",
                                "lines": [
                                    {
                                        "destination": 1,
                                        "source": 3,
                                        "line": "import re",
                                        "truncated": False,
                                    },
                                    {
                                        "destination": 2,
                                        "source": 3,
                                        "line": "import json",
                                        "truncated": False,
                                    },
                                ],
                                "truncated": False,
                            },
                        ],
                        "truncated": False,
                    }
                ],
                "lineComments": [],
                "truncated": "false",
                "contextLines": context,
                "whiteSpace": "SHOW",
                "extension": {"truncated": True, "note": "kept"},
            }
        ],
        "truncated": "false",
        "contextLines": context,
        "fromHash": "a" * 40,
        "toHash": "b" * 40,
        "whiteSpace": "SHOW",
        "extension": {"trace": ["τ", None, 1.5], "truncated": True},
    }


EXPECTED_DIFF: dict[str, object] = {
    "diffs": [
        {
            "source": {
                "components": ["src", "app.py"],
                "parent": "src",
                "name": "app.py",
                "extension": "py",
                "toString": "src/app.py",
            },
            "destination": {
                "components": ["src", "app.py"],
                "parent": "src",
                "name": "app.py",
                "extension": "py",
                "toString": "src/app.py",
            },
            "hunks": [
                {
                    "sourceLine": 1,
                    "sourceSpan": 2,
                    "destinationLine": 1,
                    "destinationSpan": 3,
                    "segments": [
                        {
                            "type": "CONTEXT",
                            "lines": [
                                {
                                    "destination": 1,
                                    "source": 1,
                                    "line": "import os",
                                    "truncated": False,
                                }
                            ],
                            "truncated": False,
                        },
                        {
                            "type": "REMOVED",
                            "lines": [
                                {
                                    "destination": 1,
                                    "source": 2,
                                    "line": f"import sys  # {SENTINEL}",
                                    "truncated": False,
                                }
                            ],
                            "truncated": False,
                        },
                        {
                            "type": "ADDED",
                            "lines": [
                                {
                                    "destination": 1,
                                    "source": 3,
                                    "line": "import re",
                                    "truncated": False,
                                },
                                {
                                    "destination": 2,
                                    "source": 3,
                                    "line": "import json",
                                    "truncated": False,
                                },
                            ],
                            "truncated": False,
                        },
                    ],
                    "truncated": False,
                }
            ],
            "lineComments": [],
            "truncated": "false",
            "contextLines": "0",
            "whiteSpace": "SHOW",
            "extension": {"truncated": True, "note": "kept"},
        }
    ],
    "truncated": "false",
    "contextLines": "0",
    "fromHash": "a" * 40,
    "toHash": "b" * 40,
    "whiteSpace": "SHOW",
    "extension": {"trace": ["τ", None, 1.5], "truncated": True},
}


def truncated_line_payload() -> dict[str, object]:
    payload = diff_payload("0")
    diffs = cast(list[dict[str, object]], payload["diffs"])
    hunks = cast(list[dict[str, object]], diffs[0]["hunks"])
    segments = cast(list[dict[str, object]], hunks[0]["segments"])
    added = cast(dict[str, object], segments[2])
    lines = cast(list[dict[str, object]], added["lines"])
    lines[0]["truncated"] = True
    return payload


def expected_request(context: str) -> Request:
    return (
        "GET",
        DIFF_PATH,
        {
            "contextLines": [context],
            "whitespace": ["ignore-all"],
            "withComments": ["false"],
        },
        f"Bearer {TOKEN}",
    )


def expected_raw_path(context: str) -> str:
    query = f"contextLines={context}&whitespace=ignore-all&withComments=false"
    return f"{DIFF_PATH}?{query}"


def run_pr_diff(
    *arguments: str,
    responses: list[tuple[int, object]],
) -> tuple[
    subprocess.CompletedProcess[str],
    list[Request],
    list[str],
    list[str | None],
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
            index = len(seen) - 1
            if index >= len(responses):
                send_json(self, 500, {"errors": [{"message": "EXTRA-REQUEST"}]})
                return
            status, body = responses[index]
            send_json(self, status, body)

    with serving(Handler) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        result = run_installed(
            [
                "pr",
                "DEMO/widgets",
                "7",
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


def test_diff_context_zero_prints_raw_json_after_one_exact_get() -> None:
    result, seen, raw_paths, accepts = run_pr_diff(
        "diff", "--json", "--context", "0", responses=[(200, diff_payload("0"))]
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    decoded = json.loads(result.stdout)
    assert decoded == EXPECTED_DIFF
    assert decoded["truncated"] == "false"
    assert decoded["diffs"][0]["truncated"] == "false"
    assert decoded["diffs"][0]["hunks"][0]["truncated"] is False
    assert decoded["diffs"][0]["extension"] == {"truncated": True, "note": "kept"}
    assert decoded["contextLines"] == "0"
    assert seen == [expected_request("0")]
    assert raw_paths == [expected_raw_path("0")]
    assert accepts == ["application/json"]


def test_diff_default_context_is_three() -> None:
    result, seen, raw_paths, accepts = run_pr_diff(
        "diff", "--json", responses=[(200, diff_payload("3"))]
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == diff_payload("3")
    assert seen == [expected_request("3")]
    assert raw_paths == [expected_raw_path("3")]
    assert accepts == ["application/json"]


def test_nested_true_truncation_exits_one_without_output_or_retry() -> None:
    result, seen, raw_paths, accepts = run_pr_diff(
        "diff",
        "--json",
        "--context",
        "0",
        responses=[(200, truncated_line_payload())],
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "truncated" in result.stderr
    for detail in (TOKEN, JIRA_TOKEN, CONFLUENCE_TOKEN, SENTINEL):
        assert detail not in result.stderr
    assert seen == [expected_request("0")]
    assert raw_paths == [expected_raw_path("0")]
    assert accepts == ["application/json"]


def test_diff_without_json_is_a_usage_error_before_any_request() -> None:
    result, seen, raw_paths, accepts = run_pr_diff("diff", responses=[])

    assert result.returncode == 2
    assert result.stdout == ""
    assert "json" in result.stderr
    assert seen == []
    assert raw_paths == []
    assert accepts == []


@pytest.mark.parametrize(
    "arguments",
    [
        ("show", "--context", "2"),
        ("files", "--context", "2"),
        ("--context", "2"),
    ],
    ids=["show", "files", "omitted-action"],
)
def test_context_is_rejected_outside_diff_before_any_request(
    arguments: tuple[str, ...],
) -> None:
    result, seen, raw_paths, accepts = run_pr_diff(*arguments, responses=[])

    assert result.returncode == 2
    assert result.stdout == ""
    assert "context" in result.stderr
    assert "diff" in result.stderr
    assert seen == []
    assert raw_paths == []
    assert accepts == []


@pytest.mark.parametrize(
    "arguments",
    [("--context=-1",), ("--context", "101"), ("--context", "not-a-number")],
    ids=["below-range", "above-range", "not-an-integer"],
)
def test_context_outside_its_range_is_a_usage_error_before_any_request(
    arguments: tuple[str, ...],
) -> None:
    result, seen, raw_paths, accepts = run_pr_diff(
        "diff", "--json", *arguments, responses=[]
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert "context" in result.stderr
    assert seen == []
    assert raw_paths == []
    assert accepts == []


def test_max_pages_is_still_rejected_for_diff() -> None:
    result, seen, raw_paths, accepts = run_pr_diff(
        "diff", "--json", "--max-pages", "2", responses=[]
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert "max-pages" in result.stderr
    assert "comments" in result.stderr
    assert seen == []
    assert raw_paths == []
    assert accepts == []
