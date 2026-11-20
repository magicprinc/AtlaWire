import json
import subprocess
from http.server import BaseHTTPRequestHandler

from tests._loopback import (
    Request,
    request_record,
    run_installed,
    send_json,
    serving,
)

TOKEN = "fixture-pr-commits-only"
JIRA_TOKEN = "wrong-product-jira-pr-commits"
CONFLUENCE_TOKEN = "wrong-product-confluence-pr-commits"
SENTINEL = "PR-COMMITS-PAYLOAD-SENTINEL"
CONTEXT = "/scm/bitbucket"
PR_PATH = f"{CONTEXT}/rest/api/1.0/projects/DEMO/repos/widgets/pull-requests/7"
COMMITS_PATH = f"{PR_PATH}/commits"

COMMIT_ONE = {
    "id": "a",
    "author": {"name": "Ana", "emailAddress": "ana@example.invalid"},
    "authorTimestamp": 0,
    "message": "one\n  two",
}
COMMIT_TWO = {"id": "b", "message": "second"}
EXPECTED_ROWS = [
    {
        "hash": "a",
        "date": "1970-01-01 00:00",
        "author": "Ana",
        "message": "one\n  two",
    },
    {"hash": "b", "date": None, "author": None, "message": "second"},
]
EXPECTED_TSV = (
    "# 2 row(s)\n"
    "hash\tdate\tauthor\tmessage\n"
    "a\t1970-01-01 00:00\tAna\tone two\n"
    "b\t\t\tsecond\n"
)


def expected_request(start: int) -> Request:
    return (
        "GET",
        COMMITS_PATH,
        {"start": [str(start)], "limit": ["100"]},
        f"Bearer {TOKEN}",
    )


def commits_page(
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


def commits_pages() -> list[tuple[int, object]]:
    return [
        (200, commits_page([COMMIT_ONE], last=False, next_start=7)),
        (200, commits_page([COMMIT_TWO], last=True)),
    ]


def run_commits(
    *arguments: str,
    responses: list[tuple[int, object]],
    action: str = "commits",
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
                "DEMO/widgets",
                pr_id,
                action,
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


def test_commits_follow_the_noncontiguous_cursor_and_print_legacy_tsv() -> None:
    result, seen, extra = run_commits(responses=commits_pages())

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout == EXPECTED_TSV
    assert seen == [expected_request(0), expected_request(7)]
    assert extra == []


def test_commits_json_keeps_every_raw_message_and_nullable_field() -> None:
    result, seen, extra = run_commits("--json", responses=commits_pages())

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    rows = json.loads(result.stdout)
    assert rows == EXPECTED_ROWS
    assert rows[0]["message"] == "one\n  two"
    assert seen == [expected_request(0), expected_request(7)]
    assert extra == []


def test_a_later_http_failure_after_a_valid_commit_is_sanitized() -> None:
    first = commits_page([COMMIT_ONE], last=False, next_start=7)
    failure = (
        503,
        {"errors": [{"message": SENTINEL}], "token": TOKEN, "x": SENTINEL},
    )

    result, seen, extra = run_commits(responses=[(200, first), failure])

    assert result.returncode == 1
    assert result.stdout == ""
    assert "HTTP 503" in result.stderr
    for detail in (TOKEN, JIRA_TOKEN, CONFLUENCE_TOKEN, SENTINEL):
        assert detail not in result.stderr
    assert seen == [expected_request(0), expected_request(7)]
    assert extra == []


def test_a_late_unencodable_commit_fails_without_partial_output() -> None:
    first = commits_page([COMMIT_ONE], last=False, next_start=7)
    second = commits_page([{"id": "c", "message": "\ud800"}], last=True)

    result, seen, extra = run_commits(responses=[(200, first), (200, second)])

    assert result.returncode == 1
    assert result.stdout == ""
    assert "UTF-8" in result.stderr
    assert "Traceback" not in result.stderr
    assert TOKEN not in result.stderr
    assert seen == [expected_request(0), expected_request(7)]
    assert extra == []


def test_a_page_cap_after_a_valid_commit_fails_without_an_extra_get() -> None:
    first = commits_page([COMMIT_ONE], last=False, next_start=7)

    result, seen, extra = run_commits("--max-pages", "1", responses=[(200, first)])

    assert result.returncode == 1
    assert result.stdout == ""
    assert "page limit" in result.stderr
    assert seen == [expected_request(0)]
    assert extra == []


def test_max_pages_is_still_rejected_for_the_diff_action() -> None:
    result, seen, extra = run_commits("--max-pages", "2", action="diff", responses=[])

    assert result.returncode == 2
    assert result.stdout == ""
    assert "max-pages" in result.stderr
    assert "comments" in result.stderr
    assert seen == []
    assert extra == []
