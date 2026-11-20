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

TOKEN = "fixture-repository-history"
JIRA_TOKEN = "wrong-product-jira-history"
CONFLUENCE_TOKEN = "wrong-product-confluence-history"
SENTINEL = "REPOSITORY-HISTORY-SENTINEL"
CONTEXT = "/scm/bitbucket"
REPO = "DEMO/widgets"
BRANCHES_PATH = f"{CONTEXT}/rest/api/1.0/projects/DEMO/repos/widgets/branches"
COMMITS_PATH = f"{CONTEXT}/rest/api/1.0/projects/DEMO/repos/widgets/commits"
FILTER = "rel/é +&?"
AT = "feature/ü &?+#"
PATH = "src/é +&?.py"

MAIN = {
    "id": "refs/heads/main",
    "displayId": "main",
    "type": "BRANCH",
    "latestCommit": "a" * 40,
    "isDefault": True,
}
RELEASE = {
    "id": "refs/heads/release/ü",
    "displayId": "release/ü+&?",
    "type": "BRANCH",
    "latestCommit": None,
    "isDefault": None,
}

COMMIT_ONE = {
    "id": "a" * 40,
    "author": {"name": "li", "emailAddress": "li@example.invalid"},
    "authorTimestamp": 1527228363490,
    "message": "raw\nline\twith  spaces",
}
COMMIT_TWO = {"id": "b" * 40, "authorTimestamp": 0, "message": None}
COMMIT_THREE = {"id": "c" * 40, "message": "third"}
COMMIT_FOUR = {
    "id": "d" * 40,
    "author": {"name": None},
    "authorTimestamp": -1000,
    "message": "fourth",
}
COMMIT_FIVE = {"id": "e" * 40, "authorTimestamp": 59999, "message": "fifth"}
LONG_RAW = "  one\t two \n" + "x" * 100 + "\x1b[2J" + "y" * 100


def run_history(
    command: str,
    *arguments: str,
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
                command,
                REPO,
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


def branch_request(start: int, filter_text: str | None = FILTER) -> Request:
    query = {"start": [str(start)], "limit": ["100"]}
    if filter_text is not None:
        query["filterText"] = [filter_text]
    return ("GET", BRANCHES_PATH, query, f"Bearer {TOKEN}")


def commit_request(start: int, limit: int) -> Request:
    return (
        "GET",
        COMMITS_PATH,
        {
            "start": [str(start)],
            "limit": [str(limit)],
            "until": [AT],
            "path": [PATH],
        },
        f"Bearer {TOKEN}",
    )


def test_branches_follow_the_noncontiguous_cursor_and_repeat_the_exact_filter() -> None:
    responses = [
        (
            200,
            {
                "size": 1,
                "limit": 100,
                "isLastPage": False,
                "nextPageStart": 57,
                "values": [MAIN],
            },
        ),
        (
            200,
            {
                "size": 1,
                "limit": 100,
                "isLastPage": True,
                "values": [RELEASE],
            },
        ),
    ]

    result, seen, extra = run_history(
        "branches", "--filter", FILTER, "--json", responses=responses
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == [
        {
            "name": "main",
            "id": "refs/heads/main",
            "commit": "a" * 40,
            "default": True,
        },
        {
            "name": "release/ü+&?",
            "id": "refs/heads/release/ü",
            "commit": None,
            "default": None,
        },
    ]
    assert seen == [branch_request(0), branch_request(57)]
    assert extra == []


def test_branches_tsv_keeps_the_legacy_columns_and_server_order() -> None:
    responses = [
        (
            200,
            {"size": 2, "limit": 100, "isLastPage": True, "values": [MAIN, RELEASE]},
        )
    ]

    result, seen, extra = run_history("branches", responses=responses)

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout == (
        f"# 2 row(s)\nname\tcommit\tdefault\nmain\t{'a' * 40}\tTrue\nrelease/ü+&?\t\t\n"
    )
    assert seen == [branch_request(0, filter_text=None)]
    assert extra == []


def test_commits_request_remaining_rows_and_keep_raw_json_and_utc_dates() -> None:
    responses = [
        (
            200,
            {
                "size": 2,
                "limit": 5,
                "isLastPage": False,
                "nextPageStart": 41,
                "values": [COMMIT_ONE, COMMIT_TWO],
            },
        ),
        (
            200,
            {
                "size": 3,
                "limit": 3,
                "isLastPage": False,
                "values": [COMMIT_THREE, COMMIT_FOUR, COMMIT_FIVE],
            },
        ),
    ]

    result, seen, extra = run_history(
        "commits",
        "--at",
        AT,
        "--path",
        PATH,
        "--limit",
        "5",
        "--json",
        responses=responses,
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == [
        {
            "hash": "a" * 40,
            "date": "2018-05-25 06:06",
            "author": "li",
            "message": "raw\nline\twith  spaces",
        },
        {"hash": "b" * 40, "date": "1970-01-01 00:00", "author": None, "message": ""},
        {"hash": "c" * 40, "date": None, "author": None, "message": "third"},
        {
            "hash": "d" * 40,
            "date": "1969-12-31 23:59",
            "author": None,
            "message": "fourth",
        },
        {
            "hash": "e" * 40,
            "date": "1970-01-01 00:00",
            "author": None,
            "message": "fifth",
        },
    ]
    assert seen == [commit_request(0, 5), commit_request(41, 3)]
    assert extra == []


def test_commit_json_keeps_the_raw_message_while_tsv_collapses_then_cuts() -> None:
    body = {
        "size": 1,
        "limit": 15,
        "isLastPage": True,
        "values": [
            {"id": "f" * 40, "authorTimestamp": 1527228363490, "message": LONG_RAW}
        ],
    }

    raw, _, _ = run_history("commits", "--json", responses=[(200, body)])

    assert raw.returncode == 0, raw.stderr
    assert json.loads(raw.stdout)[0]["message"] == LONG_RAW

    expected_message = "one two " + "x" * 100 + r"\x1b[2J" + "y" * 48
    text, seen, extra = run_history("commits", responses=[(200, body)])

    assert text.returncode == 0, text.stderr
    assert text.stderr == ""
    assert text.stdout == (
        "# 1 row(s)\n"
        "hash\tdate\tauthor\tmessage\n"
        f"{'f' * 40}\t2018-05-25 06:06\t\t{expected_message}\n"
    )
    assert seen == [
        ("GET", COMMITS_PATH, {"start": ["0"], "limit": ["15"]}, f"Bearer {TOKEN}")
    ]
    assert extra == []


@pytest.mark.parametrize(
    "last",
    ["not-a-boolean", None],
    ids=["malformed", "absent"],
)
def test_an_exact_commit_row_cap_still_requires_is_last_page(last: object) -> None:
    body: dict[str, object] = {"values": [COMMIT_THREE]}
    if last is not None:
        body["isLastPage"] = last

    result, seen, extra = run_history(
        "commits", "--limit", "1", "--json", responses=[(200, body)]
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "isLastPage" in result.stderr
    assert seen == [
        ("GET", COMMITS_PATH, {"start": ["0"], "limit": ["1"]}, f"Bearer {TOKEN}")
    ]
    assert extra == []


@pytest.mark.parametrize(
    ("command", "path", "first", "next_start", "arguments", "first_limit"),
    [
        (
            "branches",
            BRANCHES_PATH,
            {
                "size": 1,
                "limit": 100,
                "isLastPage": False,
                "nextPageStart": 57,
                "values": [MAIN],
            },
            57,
            (),
            100,
        ),
        (
            "commits",
            COMMITS_PATH,
            {
                "size": 1,
                "limit": 2,
                "isLastPage": False,
                "nextPageStart": 41,
                "values": [COMMIT_ONE],
            },
            41,
            ("--limit", "2"),
            2,
        ),
    ],
    ids=["branches", "commits"],
)
def test_a_later_http_failure_after_a_valid_row_is_sanitized(
    command: str,
    path: str,
    first: dict[str, object],
    next_start: int,
    arguments: tuple[str, ...],
    first_limit: int,
) -> None:
    failure = (
        503,
        {"errors": [{"message": SENTINEL}], "token": TOKEN, "x": SENTINEL},
    )

    result, seen, extra = run_history(
        command, *arguments, "--json", responses=[(200, first), failure]
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "HTTP 503" in result.stderr
    for detail in (TOKEN, JIRA_TOKEN, CONFLUENCE_TOKEN, SENTINEL):
        assert detail not in result.stderr
    assert [request[0:2] for request in seen] == [("GET", path), ("GET", path)]
    assert seen[0][2]["start"] == ["0"]
    assert seen[0][2]["limit"] == [str(first_limit)]
    assert seen[1][2]["start"] == [str(next_start)]
    assert seen[1][2]["limit"] == ["1" if command == "commits" else "100"]
    assert extra == []


@pytest.mark.parametrize("value", ["0", "1001"])
def test_page_count_outside_the_range_is_a_usage_error(value: str) -> None:
    for command in ("branches", "commits"):
        result, seen, extra = run_history(command, "--max-pages", value, responses=[])

        assert result.returncode == 2
        assert result.stdout == ""
        assert seen == []
        assert extra == []


@pytest.mark.parametrize("value", ["0", "1001"])
def test_commit_count_outside_the_range_is_a_usage_error(value: str) -> None:
    result, seen, extra = run_history("commits", "--limit", value, responses=[])

    assert result.returncode == 2
    assert result.stdout == ""
    assert seen == []
    assert extra == []


def test_commit_help_documents_the_default_and_range() -> None:
    result = run_installed(["commits", "--help"], {})

    assert result.returncode == 0
    assert "1-1000" in result.stdout
    assert "15" in result.stdout
