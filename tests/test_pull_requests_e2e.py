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

TOKEN = "fixture-pull-requests"
JIRA_TOKEN = "wrong-product-jira-pull-requests"
CONFLUENCE_TOKEN = "wrong-product-confluence-pull-requests"
SENTINEL = "PULL-REQUESTS-SENTINEL"
CONTEXT = "/scm/bitbucket"
REPO = "DEMO/widgets"
PULL_REQUESTS_PATH = f"{CONTEXT}/rest/api/1.0/projects/DEMO/repos/widgets/pull-requests"

FULL = {
    "id": 101,
    "title": "Fix\tü",
    "state": "OPEN",
    "updatedDate": 0,
    "author": {
        "user": {"name": "tom", "emailAddress": "tom@example.invalid"},
        "role": "AUTHOR",
    },
    "fromRef": {"displayId": "feature/ü", "repository": {"slug": "widgets"}},
    "toRef": {"displayId": "main"},
    "description": "RAW-DESCRIPTION-SENTINEL",
    "links": {"self": [{"href": "https://secret.invalid"}]},
}
MINIMAL = {"id": 7, "title": "Second", "state": "MERGED"}
THIRD = {"id": 8, "title": "Third", "state": "DECLINED", "updatedDate": 1359085920}


def run_pull_requests(
    *arguments: str,
    responses: Sequence[tuple[int, object]],
) -> tuple[subprocess.CompletedProcess[str], list[Request]]:
    seen: list[Request] = []

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

    with serving(Handler) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        result = run_installed(
            [
                "prs",
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
    return result, seen


def pull_requests_request(
    start: int, limit: int, *, state: str = "OPEN", order: str | None = None
) -> Request:
    query = {"start": [str(start)], "limit": [str(limit)], "state": [state]}
    if order is not None:
        query["order"] = [order]
    return ("GET", PULL_REQUESTS_PATH, query, f"Bearer {TOKEN}")


def test_prs_repeats_the_exact_filters_and_stops_at_the_row_cap() -> None:
    responses = [
        (
            200,
            {
                "size": 1,
                "limit": 1,
                "isLastPage": False,
                "nextPageStart": 7,
                "values": [FULL],
            },
        ),
        (
            200,
            {"size": 2, "limit": 2, "isLastPage": False, "values": [MINIMAL, THIRD]},
        ),
    ]

    result, seen = run_pull_requests(
        "--state",
        "ALL",
        "--order",
        "OLDEST",
        "--limit",
        "3",
        "--json",
        responses=responses,
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == [
        {
            "id": 101,
            "title": "Fix\tü",
            "state": "OPEN",
            "author": "tom",
            "from": "feature/ü",
            "to": "main",
            "updated": 0,
        },
        {
            "id": 7,
            "title": "Second",
            "state": "MERGED",
            "author": None,
            "from": None,
            "to": None,
            "updated": None,
        },
        {
            "id": 8,
            "title": "Third",
            "state": "DECLINED",
            "author": None,
            "from": None,
            "to": None,
            "updated": 1359085920,
        },
    ]
    assert seen == [
        pull_requests_request(0, 3, state="ALL", order="OLDEST"),
        pull_requests_request(7, 2, state="ALL", order="OLDEST"),
    ]


def test_prs_projects_only_the_legacy_fields_in_json_and_tsv() -> None:
    body = {"size": 2, "limit": 25, "isLastPage": True, "values": [FULL, MINIMAL]}

    raw, seen_json = run_pull_requests("--json", responses=[(200, body)])

    assert raw.returncode == 0, raw.stderr
    assert raw.stderr == ""
    assert json.loads(raw.stdout) == [
        {
            "id": 101,
            "title": "Fix\tü",
            "state": "OPEN",
            "author": "tom",
            "from": "feature/ü",
            "to": "main",
            "updated": 0,
        },
        {
            "id": 7,
            "title": "Second",
            "state": "MERGED",
            "author": None,
            "from": None,
            "to": None,
            "updated": None,
        },
    ]
    for excluded in (
        "emailAddress",
        "tom@example.invalid",
        "RAW-DESCRIPTION-SENTINEL",
        "secret.invalid",
        "AUTHOR",
    ):
        assert excluded not in raw.stdout
    assert seen_json == [pull_requests_request(0, 25)]

    text, seen_tsv = run_pull_requests(responses=[(200, body)])

    assert text.returncode == 0, text.stderr
    assert text.stderr == ""
    assert text.stdout == (
        "# 2 row(s)\n"
        "id\ttitle\tstate\tauthor\tfrom\tto\tupdated\n"
        "101\tFix\\tü\tOPEN\ttom\tfeature/ü\tmain\t0\n"
        "7\tSecond\tMERGED\t\t\t\t\n"
    )
    assert seen_tsv == [pull_requests_request(0, 25)]


def test_a_late_failure_after_a_valid_row_is_sanitized() -> None:
    responses = [
        (
            200,
            {
                "size": 1,
                "limit": 3,
                "isLastPage": False,
                "nextPageStart": 7,
                "values": [FULL],
            },
        ),
        (
            503,
            {"errors": [{"message": SENTINEL}], "token": TOKEN, "x": SENTINEL},
        ),
    ]

    result, seen = run_pull_requests("--limit", "3", "--json", responses=responses)

    assert result.returncode == 1
    assert result.stdout == ""
    assert "HTTP 503" in result.stderr
    for detail in (TOKEN, JIRA_TOKEN, CONFLUENCE_TOKEN, SENTINEL):
        assert detail not in result.stderr
    assert seen == [pull_requests_request(0, 3), pull_requests_request(7, 2)]


@pytest.mark.parametrize(
    "arguments",
    [
        ("--state", "open"),
        ("--order", "bogus"),
        ("--limit", "0"),
        ("--max-pages", "0"),
    ],
)
def test_invalid_input_is_a_usage_error_before_any_request(
    arguments: tuple[str, str],
) -> None:
    result, seen = run_pull_requests(*arguments, responses=[])

    assert result.returncode == 2
    assert result.stdout == ""
    assert seen == []
