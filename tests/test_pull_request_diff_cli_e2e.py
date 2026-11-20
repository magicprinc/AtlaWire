import json
import subprocess
from copy import deepcopy
from http.server import BaseHTTPRequestHandler
from typing import cast
from urllib.parse import quote_plus

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
DESTINATION_PATH = "src/é +&?.py"
DESTINATION_ENCODED = "src/%C3%A9%20%2B%26%3F.py"
SOURCE_PATH = "old/é +&?#%.py"


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


def readable_payload() -> dict[str, object]:
    """Build a response whose metadata differs from the default request."""
    payload = diff_payload("0")
    payload["extension"] = {"note": SENTINEL}
    diffs = cast(list[dict[str, object]], payload["diffs"])
    hunks = cast(list[dict[str, object]], diffs[0]["hunks"])
    segments = cast(list[dict[str, object]], hunks[0]["segments"])
    context_lines = cast(list[dict[str, object]], segments[0]["lines"])
    context_lines[0]["line"] = "import os  "
    removed_lines = cast(list[dict[str, object]], segments[1]["lines"])
    removed_lines[0]["line"] = "import sys  # old"
    added_lines = cast(list[dict[str, object]], segments[2]["lines"])
    added_lines[0]["line"] = ""
    added_lines[1]["line"] = "danger\x1b[31m"
    return payload


def missing_destination_payload() -> dict[str, object]:
    """Build a deleted-file view with zero ranges and an empty removed line."""
    payload = diff_payload("5")
    diffs = cast(list[dict[str, object]], payload["diffs"])
    diff = diffs[0]
    diff["destination"] = None
    hunks = cast(list[dict[str, object]], diff["hunks"])
    hunk = hunks[0]
    hunk["sourceLine"] = 7
    hunk["sourceSpan"] = 0
    hunk["destinationLine"] = 0
    hunk["destinationSpan"] = 0
    hunk["segments"] = [
        {
            "type": "REMOVED",
            "lines": [{"source": 7, "destination": 0, "line": ""}],
        }
    ]
    return payload


def surrogate_payload() -> dict[str, object]:
    """Build a response with lone surrogates in a path and a line."""
    payload = diff_payload("3")
    diffs = cast(list[dict[str, object]], payload["diffs"])
    diff = diffs[0]
    diff["source"] = {"toString": "src/\ud800.py"}
    diff["destination"] = {"toString": "src/\ud800.py"}
    hunks = cast(list[dict[str, object]], diff["hunks"])
    segments = cast(list[dict[str, object]], hunks[0]["segments"])
    context_lines = cast(list[dict[str, object]], segments[0]["lines"])
    context_lines[0]["line"] = "keep \ud800"
    removed_lines = cast(list[dict[str, object]], segments[1]["lines"])
    removed_lines[0]["line"] = "old"
    return payload


def two_file_payload() -> dict[str, object]:
    """Build a valid first file followed by a copy that tests can corrupt."""
    payload = diff_payload("3")
    diffs = cast(list[dict[str, object]], payload["diffs"])
    second = deepcopy(diffs[0])
    second["source"] = {"toString": "src/second.py"}
    second["destination"] = {"toString": "src/second.py"}
    diffs.append(second)
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


def expected_file_request(context: str, *, source: str | None = None) -> Request:
    query: dict[str, list[str]] = {
        "contextLines": [context],
        "whitespace": ["ignore-all"],
        "withComments": ["false"],
    }
    if source is not None:
        query["srcPath"] = [source]
    return (
        "GET",
        f"{PR_PATH}/diff/{DESTINATION_ENCODED}",
        query,
        f"Bearer {TOKEN}",
    )


def expected_file_raw_path(context: str, *, source: str | None = None) -> str:
    raw = (
        f"{PR_PATH}/diff/{DESTINATION_ENCODED}"
        f"?contextLines={context}&whitespace=ignore-all&withComments=false"
    )
    if source is not None:
        raw += f"&srcPath={quote_plus(source)}"
    return raw


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


def test_diff_without_json_prints_a_readable_text_review() -> None:
    result, seen, raw_paths, accepts = run_pr_diff(
        "diff", responses=[(200, readable_payload())]
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout == (
        "# Bitbucket PR diff review "
        "(context=3; whitespace=ignore-all; not a patch)\n"
        "\n"
        "--- a/src/app.py\n"
        "+++ b/src/app.py\n"
        "@@ -1,2 +1,3 @@\n"
        " import os  \n"
        "-import sys  # old\n"
        "+\n"
        "+danger\\x1b[31m\n"
    )
    assert SENTINEL not in result.stdout
    assert seen == [expected_request("3")]
    assert raw_paths == [expected_raw_path("3")]
    assert accepts == ["application/json"]


def test_text_header_uses_the_requested_context_not_response_metadata() -> None:
    result, seen, raw_paths, accepts = run_pr_diff(
        "diff", "--context", "0", responses=[(200, diff_payload("99"))]
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith(
        "# Bitbucket PR diff review (context=0; whitespace=ignore-all; not a patch)\n"
    )
    assert seen == [expected_request("0")]
    assert raw_paths == [expected_raw_path("0")]
    assert accepts == ["application/json"]


def test_one_file_diff_sends_the_encoded_path_and_decoded_source_path() -> None:
    result, seen, raw_paths, accepts = run_pr_diff(
        "diff",
        DESTINATION_PATH,
        "--source-path",
        SOURCE_PATH,
        "--json",
        "--context",
        "0",
        responses=[(200, diff_payload("0"))],
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == diff_payload("0")
    assert seen == [expected_file_request("0", source=SOURCE_PATH)]
    assert seen[0][2]["srcPath"] == [SOURCE_PATH]
    assert raw_paths == [expected_file_raw_path("0", source=SOURCE_PATH)]
    assert accepts == ["application/json"]


def test_a_destination_without_a_rename_omits_srcpath() -> None:
    result, seen, raw_paths, accepts = run_pr_diff(
        "diff", DESTINATION_PATH, "--json", responses=[(200, diff_payload("3"))]
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == diff_payload("3")
    assert seen == [expected_file_request("3")]
    assert "srcPath" not in seen[0][2]
    assert "srcPath=" not in raw_paths[0]
    assert accepts == ["application/json"]


def test_one_file_diff_without_json_uses_the_review_renderer() -> None:
    result, seen, raw_paths, accepts = run_pr_diff(
        "diff", DESTINATION_PATH, responses=[(200, readable_payload())]
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout == (
        "# Bitbucket PR diff review "
        "(context=3; whitespace=ignore-all; not a patch)\n"
        "\n"
        "--- a/src/app.py\n"
        "+++ b/src/app.py\n"
        "@@ -1,2 +1,3 @@\n"
        " import os  \n"
        "-import sys  # old\n"
        "+\n"
        "+danger\\x1b[31m\n"
    )
    assert seen == [expected_file_request("3")]
    assert raw_paths == [expected_file_raw_path("3")]
    assert accepts == ["application/json"]


def test_one_file_nested_truncation_fails_without_a_fallback_request() -> None:
    result, seen, raw_paths, accepts = run_pr_diff(
        "diff", DESTINATION_PATH, "--json", responses=[(200, truncated_line_payload())]
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "truncated" in result.stderr
    for detail in (TOKEN, JIRA_TOKEN, CONFLUENCE_TOKEN, SENTINEL):
        assert detail not in result.stderr
    assert seen == [expected_file_request("3")]
    assert raw_paths == [expected_file_raw_path("3")]
    assert accepts == ["application/json"]


def test_diff_text_escapes_lone_surrogates_as_visible_ascii() -> None:
    result, seen, raw_paths, accepts = run_pr_diff(
        "diff", responses=[(200, surrogate_payload())]
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout == (
        "# Bitbucket PR diff review "
        "(context=3; whitespace=ignore-all; not a patch)\n"
        "\n"
        "--- a/src/\\ud800.py\n"
        "+++ b/src/\\ud800.py\n"
        "@@ -1,2 +1,3 @@\n"
        " keep \\ud800\n"
        "-old\n"
        "+import re\n"
        "+import json\n"
    )
    assert "\ud800" not in result.stdout
    assert seen == [expected_request("3")]
    assert raw_paths == [expected_raw_path("3")]
    assert accepts == ["application/json"]


def test_diff_text_uses_null_device_for_a_missing_side_and_zero_spans() -> None:
    result, seen, raw_paths, accepts = run_pr_diff(
        "diff", responses=[(200, missing_destination_payload())]
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout == (
        "# Bitbucket PR diff review "
        "(context=3; whitespace=ignore-all; not a patch)\n"
        "\n"
        "--- a/src/app.py\n"
        "+++ /dev/null\n"
        "@@ -7,0 +0,0 @@\n"
        "-\n"
    )
    assert seen == [expected_request("3")]
    assert raw_paths == [expected_raw_path("3")]
    assert accepts == ["application/json"]


@pytest.mark.parametrize(
    ("node", "expected"),
    [
        ("hunk", "segments"),
        ("segment", "lines"),
        ("line", "text"),
        ("break", "line break"),
    ],
    ids=["empty-segments", "empty-lines", "non-string-text", "literal-break"],
)
def test_a_malformed_later_file_fails_without_partial_text(
    node: str, expected: str
) -> None:
    payload = two_file_payload()
    diffs = cast(list[dict[str, object]], payload["diffs"])
    hunks = cast(list[dict[str, object]], diffs[1]["hunks"])
    segments = cast(list[dict[str, object]], hunks[0]["segments"])
    lines = cast(list[dict[str, object]], segments[0]["lines"])
    if node == "hunk":
        hunks[0]["segments"] = []
    elif node == "segment":
        segments[0]["lines"] = []
    elif node == "line":
        lines[0]["line"] = 7
    else:
        lines[0]["line"] = "two\nlines"

    result, seen, raw_paths, accepts = run_pr_diff("diff", responses=[(200, payload)])

    assert result.returncode == 1
    assert result.stdout == ""
    assert expected in result.stderr
    for detail in (TOKEN, JIRA_TOKEN, CONFLUENCE_TOKEN, SENTINEL):
        assert detail not in result.stderr
    assert seen == [expected_request("3")]
    assert raw_paths == [expected_raw_path("3")]
    assert accepts == ["application/json"]


def test_diff_text_rejects_a_flagged_payload_before_output() -> None:
    result, seen, raw_paths, accepts = run_pr_diff(
        "diff", responses=[(200, truncated_line_payload())]
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "truncated" in result.stderr
    for detail in (TOKEN, JIRA_TOKEN, CONFLUENCE_TOKEN, SENTINEL):
        assert detail not in result.stderr
    assert seen == [expected_request("3")]
    assert raw_paths == [expected_raw_path("3")]
    assert accepts == ["application/json"]


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


@pytest.mark.parametrize(
    ("arguments", "code"),
    [
        (("show", "--source-path", "old.py"), 2),
        (("files", "--source-path", "old.py"), 2),
        (("file", "src/app.py", "--source-path", "old.py"), 2),
        (("diff", "--source-path", "old.py"), 2),
        (("diff", "src/app.py", "--side", "old"), 2),
        (("diff", "--source-path", "", "src/app.py"), 1),
        (("diff", "--source-path", "../old.py", "src/app.py"), 1),
        (("diff", "--source-path", "/abs/old.py", "src/app.py"), 1),
        (("diff", "--source-path", "old/%2e%2e/x.py", "src/app.py"), 1),
        (("diff", "/abs/new.py"), 1),
        (("diff", "src//new.py"), 1),
    ],
    ids=[
        "source-with-show",
        "source-with-files",
        "source-with-file",
        "source-without-path",
        "side-with-diff",
        "empty-source",
        "parent-source",
        "absolute-source",
        "escaped-source",
        "absolute-destination",
        "empty-destination-segment",
    ],
)
def test_invalid_diff_options_and_paths_fail_before_any_request(
    arguments: tuple[str, ...], code: int
) -> None:
    result, seen, raw_paths, accepts = run_pr_diff(*arguments, "--json", responses=[])

    assert result.returncode == code
    assert result.stdout == ""
    assert seen == []
    assert raw_paths == []
    assert accepts == []
