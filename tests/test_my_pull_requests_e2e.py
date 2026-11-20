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

TOKEN = "fixture-my-pull-requests"
JIRA_TOKEN = "wrong-product-jira-my-prs"
CONFLUENCE_TOKEN = "wrong-product-confluence-my-prs"
SENTINEL = "MY-PRS-SENTINEL"
CONTEXT = "/scm/bitbucket"
DASHBOARD_PATH = f"{CONTEXT}/rest/api/1.0/dashboard/pull-requests"
TARGET = {"repository": {"slug": "widgets", "project": {"key": "DEMO"}}}
FULL = {
    "id": 101,
    "title": "Fix\tü",
    "state": "OPEN",
    "createdDate": 0,
    "author": {
        "user": {"name": "tom", "emailAddress": "tom@example.invalid"},
        "role": "AUTHOR",
    },
    "fromRef": {
        "displayId": "feature/from-fork",
        "repository": {"slug": "widgets-fork", "project": {"key": "FORK"}},
    },
    "toRef": {
        "displayId": "main",
        "repository": {
            "slug": "widgets",
            "project": {"key": "DEMO"},
            "links": {"self": [{"href": "https://secret.invalid/repo"}]},
        },
    },
    "reviewers": [
        {"user": {"name": "jcitizen", "active": True}},
        {"user": {"name": "dick", "active": False, "emailAddress": "d@x.invalid"}},
        {"user": {"name": "absent"}},
    ],
    "participants": [
        {"user": {"name": "dick", "active": False}},
        {"user": {"name": "zoe", "active": False}},
    ],
    "description": "RAW-DESCRIPTION-SENTINEL",
    "links": {"self": [{"href": "https://secret.invalid/pr"}]},
}
MINIMAL = {"id": 7, "title": "Second", "state": "MERGED", "toRef": TARGET}
THIRD = {
    "id": 8,
    "title": "Third",
    "state": "DECLINED",
    "createdDate": 1359085920,
    "toRef": TARGET,
}
PROJECTED_FULL = {
    "repo": "DEMO/widgets",
    "id": 101,
    "title": "Fix\tü",
    "state": "OPEN",
    "author": "tom",
    "reviewers_inactive": ["dick", "zoe"],
    "created": 0,
}
PROJECTED_MINIMAL = {
    "repo": "DEMO/widgets",
    "id": 7,
    "title": "Second",
    "state": "MERGED",
    "author": None,
    "reviewers_inactive": [],
    "created": None,
}
PROJECTED_THIRD = {
    "repo": "DEMO/widgets",
    "id": 8,
    "title": "Third",
    "state": "DECLINED",
    "author": None,
    "reviewers_inactive": [],
    "created": 1359085920,
}


def run_my_prs(
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
                "my-prs",
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


def dashboard_request(
    start: int,
    limit: int,
    *,
    state: str = "OPEN",
    role: str = "AUTHOR",
    participant_status: str | None = None,
) -> Request:
    query = {
        "start": [str(start)],
        "limit": [str(limit)],
        "state": [state],
        "role": [role],
    }
    if participant_status is not None:
        query["participantStatus"] = [participant_status]
    return ("GET", DASHBOARD_PATH, query, f"Bearer {TOKEN}")


def test_my_prs_repeats_the_exact_filters_and_stops_at_the_row_cap() -> None:
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
            200,
            {"size": 2, "limit": 2, "isLastPage": False, "values": [MINIMAL, THIRD]},
        ),
    ]

    result, seen = run_my_prs(
        "--state",
        "MERGED",
        "--role",
        "REVIEWER",
        "--participant-status",
        "UNAPPROVED,APPROVED",
        "--limit",
        "3",
        "--json",
        responses=responses,
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout == (
        json.dumps([PROJECTED_FULL, PROJECTED_MINIMAL, PROJECTED_THIRD]) + "\n"
    )
    assert seen == [
        dashboard_request(
            0,
            3,
            state="MERGED",
            role="REVIEWER",
            participant_status="UNAPPROVED,APPROVED",
        ),
        dashboard_request(
            7,
            2,
            state="MERGED",
            role="REVIEWER",
            participant_status="UNAPPROVED,APPROVED",
        ),
    ]


def test_my_prs_projects_only_the_legacy_fields_in_json_and_tsv() -> None:
    body = {"size": 2, "limit": 25, "isLastPage": True, "values": [FULL, MINIMAL]}

    raw, seen_json = run_my_prs("--json", responses=[(200, body)])

    assert raw.returncode == 0, raw.stderr
    assert raw.stderr == ""
    assert raw.stdout == json.dumps([PROJECTED_FULL, PROJECTED_MINIMAL]) + "\n"
    for excluded in (
        "FORK",
        "widgets-fork",
        "example.invalid",
        "d@x.invalid",
        "RAW-DESCRIPTION-SENTINEL",
        "secret.invalid",
        "AUTHOR",
    ):
        assert excluded not in raw.stdout
    assert seen_json == [dashboard_request(0, 25)]

    text, seen_tsv = run_my_prs(responses=[(200, body)])

    assert text.returncode == 0, text.stderr
    assert text.stderr == ""
    assert text.stdout == (
        "# 2 row(s)\n"
        "repo\tid\ttitle\tstate\tauthor\treviewers_inactive\tcreated\n"
        'DEMO/widgets\t101\tFix\\tü\tOPEN\ttom\t["dick", "zoe"]\t0\n'
        "DEMO/widgets\t7\tSecond\tMERGED\t\t[]\t\n"
    )
    assert seen_tsv == [dashboard_request(0, 25)]


@pytest.mark.parametrize(
    ("second", "expected"),
    [
        pytest.param(
            (503, {"errors": [{"message": SENTINEL}], "token": TOKEN}),
            "HTTP 503",
            id="http-error",
        ),
        pytest.param(
            (
                200,
                {
                    "values": [
                        {
                            "id": True,
                            "title": "T",
                            "state": "OPEN",
                            "toRef": TARGET,
                            "description": SENTINEL,
                        }
                    ],
                    "isLastPage": True,
                },
            ),
            "pull request",
            id="malformed-row",
        ),
    ],
)
def test_a_late_failure_after_a_valid_row_withholds_all_output(
    second: tuple[int, object], expected: str
) -> None:
    responses = [
        (
            200,
            {
                "size": 1,
                "limit": 2,
                "isLastPage": False,
                "nextPageStart": 7,
                "values": [FULL],
            },
        ),
        second,
    ]

    result, seen = run_my_prs("--limit", "2", "--json", responses=responses)

    assert result.returncode == 1
    assert result.stdout == ""
    assert expected in result.stderr
    for detail in (TOKEN, JIRA_TOKEN, CONFLUENCE_TOKEN, SENTINEL):
        assert detail not in result.stderr
    assert seen == [dashboard_request(0, 2), dashboard_request(7, 1)]


@pytest.mark.parametrize(
    "arguments",
    [
        ("--state", "ALL"),
        ("--state", "open"),
        ("--role", "all"),
        ("--role", "author"),
        ("--limit", "0"),
        ("--max-pages", "0"),
    ],
)
def test_invalid_input_is_a_usage_error_before_any_request(
    arguments: tuple[str, str],
) -> None:
    result, seen = run_my_prs(*arguments, responses=[])

    assert result.returncode == 2
    assert result.stdout == ""
    assert seen == []


def test_an_empty_participant_status_is_rejected_before_any_request() -> None:
    result, seen = run_my_prs("--participant-status", "", responses=[])

    assert result.returncode == 1
    assert result.stdout == ""
    assert "participant status" in result.stderr
    assert seen == []
