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

TOKEN = "fixture-pr-comments-only"
JIRA_TOKEN = "wrong-product-jira-comments"
CONFLUENCE_TOKEN = "wrong-product-confluence-comments"
SENTINEL = "PR-COMMENTS-PAYLOAD-SENTINEL"
CONTEXT = "/scm/bitbucket"
PR_PATH = f"{CONTEXT}/rest/api/1.0/projects/DEMO/repos/widgets/pull-requests/7"
ACTIVITIES_PATH = f"{PR_PATH}/activities"

INLINE_COMMENT = {
    "id": 5,
    "action": "COMMENTED",
    "commentAction": "ADDED",
    "comment": {
        "id": 41,
        "version": 1,
        "author": {"name": "li", "displayName": "Li"},
        "text": "first line\n\tsecond   line  ",
        "createdDate": 1527228363421,
        "updatedDate": 1527228363421,
        "comments": [
            {
                "id": 99,
                "author": {"name": "bob"},
                "text": "nested reply",
                "createdDate": 1527228363500,
                "comments": [],
            }
        ],
    },
    "commentAnchor": {"line": 7, "lineType": "CONTEXT", "path": "src/app.py"},
}
GENERAL_COMMENT = {
    "id": 6,
    "action": "COMMENTED",
    "commentAction": "ADDED",
    "comment": {
        "id": 42,
        "text": "general\tnote",
        "createdDate": None,
        "created": 0,
    },
}
EXPECTED_ROWS = [
    {
        "id": 41,
        "author": "li",
        "path": "src/app.py",
        "line": 7,
        "text": "first line\n\tsecond   line  ",
        "created": 1527228363421,
    },
    {
        "id": 42,
        "author": None,
        "path": None,
        "line": None,
        "text": "general\tnote",
        "created": 0,
    },
]
EXPECTED_TSV = (
    "# 2 row(s)\n"
    "id\tauthor\tpath\tline\ttext\n"
    "41\tli\tsrc/app.py\t7\tfirst line second line\n"
    "42\t\t\t\tgeneral note\n"
)


def expected_request(start: int) -> Request:
    return (
        "GET",
        ACTIVITIES_PATH,
        {"start": [str(start)], "limit": ["100"]},
        f"Bearer {TOKEN}",
    )


def activity_page(
    values: list[object], *, last: bool, next_start: int | None = None
) -> dict[str, object]:
    body: dict[str, object] = {
        "size": len(values),
        "limit": 100,
        "isLastPage": last,
        "values": values,
    }
    if next_start is not None:
        body["nextPageStart"] = next_start
    return body


def comments_pages() -> list[tuple[int, object]]:
    return [
        (
            200,
            activity_page(
                [
                    {"id": 1, "action": "APPROVED", "user": {"name": "ana"}},
                    {
                        "id": 2,
                        "action": "RESCOPED",
                        "fromHash": "a",
                        "toHash": "b",
                    },
                ],
                last=False,
                next_start=17,
            ),
        ),
        (200, activity_page([INLINE_COMMENT, GENERAL_COMMENT], last=True)),
    ]


def run_comments(
    *arguments: str,
    responses: list[tuple[int, object]],
    repo: str = "DEMO/widgets",
    pr_id: str = "7",
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
    return result, seen, extra_methods


def test_comments_prints_legacy_tsv_after_following_the_cursor() -> None:
    result, seen, extra = run_comments("comments", responses=comments_pages())

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout == EXPECTED_TSV
    assert seen == [expected_request(0), expected_request(17)]
    assert extra == []


def test_comments_json_keeps_raw_text_and_every_projected_column() -> None:
    result, seen, extra = run_comments("comments", "--json", responses=comments_pages())

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == EXPECTED_ROWS
    assert json.loads(result.stdout)[0]["text"] == "first line\n\tsecond   line  "
    assert "nested reply" not in result.stdout
    assert seen == [expected_request(0), expected_request(17)]
    assert extra == []


def test_a_page_cap_after_a_valid_comment_fails_without_partial_output() -> None:
    first = activity_page([INLINE_COMMENT], last=False, next_start=17)

    result, seen, extra = run_comments(
        "comments", "--max-pages", "1", responses=[(200, first)]
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "page limit" in result.stderr
    assert TOKEN not in result.stderr
    assert seen == [expected_request(0)]
    assert extra == []


def test_a_later_http_failure_after_a_valid_comment_is_sanitized() -> None:
    first = activity_page([INLINE_COMMENT], last=False, next_start=17)
    failure = (
        503,
        {"errors": [{"message": SENTINEL}], "token": TOKEN, "x": SENTINEL},
    )

    result, seen, extra = run_comments("comments", responses=[(200, first), failure])

    assert result.returncode == 1
    assert result.stdout == ""
    assert "HTTP 503" in result.stderr
    for detail in (TOKEN, JIRA_TOKEN, CONFLUENCE_TOKEN, SENTINEL):
        assert detail not in result.stderr
    assert seen == [expected_request(0), expected_request(17)]
    assert extra == []


@pytest.mark.parametrize(
    "arguments",
    [
        ("show", "--max-pages", "2"),
        ("files", "--max-pages", "2"),
        ("--max-pages", "2"),
    ],
    ids=["show", "files", "omitted-action"],
)
def test_max_pages_is_rejected_outside_comments(
    arguments: tuple[str, ...],
) -> None:
    result, seen, extra = run_comments(*arguments, responses=[])

    assert result.returncode == 2
    assert result.stdout == ""
    assert "max-pages" in result.stderr
    assert "comments" in result.stderr
    assert seen == []
    assert extra == []


@pytest.mark.parametrize("value", ["0", "1001"])
def test_max_pages_outside_the_range_is_a_usage_error(value: str) -> None:
    result, seen, extra = run_comments("comments", "--max-pages", value, responses=[])

    assert result.returncode == 2
    assert result.stdout == ""
    assert seen == []
    assert extra == []
