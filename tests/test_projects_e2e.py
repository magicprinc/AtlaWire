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

TOKEN = "fixture-projects-only"
CONTEXT = "/scm/bitbucket"
PROJECT_PATH = f"{CONTEXT}/rest/api/1.0/projects"
FIRST_BASE = {
    "key": "DEMO",
    "name": "Demo\tTeam",
    "description": "Demo — α",
    "public": False,
    "type": "NORMAL",
    "id": 1,
}
SECOND = {"key": "OPS", "public": True}


def fixture(scenario: str, start: int, self_url: str) -> tuple[int, dict[str, object]]:
    if scenario == "echo-start":
        if start == 0:
            return 200, {
                "values": [FIRST_BASE],
                "isLastPage": False,
                "nextPageStart": 100,
                "start": 0,
                "size": 1,
            }
        return 200, {
            "values": [FIRST_BASE],
            "isLastPage": True,
            "start": 0,
            "size": 1,
        }
    if scenario == "echo-size":
        return 200, {"values": [FIRST_BASE], "isLastPage": True, "size": 2}
    if scenario in {"paged", "later-failure"}:
        if start == 0:
            return 200, {
                "values": [{**FIRST_BASE, "links": {"self": [{"href": self_url}]}}],
                "isLastPage": False,
                "nextPageStart": 17,
            }
        if scenario == "paged" and start == 17:
            return 200, {"values": [SECOND], "isLastPage": True}
    if scenario == "later-failure":
        return 503, {
            "message": TOKEN,
            "path": PROJECT_PATH,
            "query": "fixture-query",
            "response": "RESPONSE-SENTINEL",
        }
    return 400, {"unexpectedStart": start}


def run_projects(
    scenario: str, *options: str
) -> tuple[subprocess.CompletedProcess[str], list[Request], list[str], str]:
    seen: list[Request] = []
    intruder: list[str] = []

    class Intruder(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            intruder.append(self.path)
            send_json(self, 200, {"values": [{"key": "LEAK"}], "isLastPage": True})

    with serving(Intruder) as intruder_server:
        self_url = (
            f"http://127.0.0.1:{intruder_server.server_port}"
            "/elsewhere/DEMO?browse=true#readme"
        )

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: object) -> None:
                pass

            def do_GET(self) -> None:
                record = request_record(self)
                seen.append(record)
                params = record[2]
                try:
                    start = int(params.get("start", ["-1"])[0])
                except ValueError:
                    start = -1
                status, body = fixture(scenario, start, self_url)
                send_json(self, status, body)

        with serving(Handler) as server:
            origin = f"http://127.0.0.1:{server.server_port}"
            result = run_installed(
                ["projects", "--allow-http-loopback", "--token-from-env", *options],
                {
                    "ATLAWIRE_BITBUCKET_URL": f"{origin}{CONTEXT}/",
                    "ATLAWIRE_BITBUCKET_TOKEN": TOKEN,
                    "ATLAWIRE_JIRA_URL": f"{origin}/wrong-jira/",
                    "ATLAWIRE_JIRA_TOKEN": "wrong-product-jira",
                    "ATLAWIRE_CONFLUENCE_URL": f"{origin}/wrong-confluence/",
                    "ATLAWIRE_CONFLUENCE_TOKEN": "wrong-product-confluence",
                },
            )
    return result, seen, intruder, self_url


def expected_seen(starts: list[int]) -> list[Request]:
    return [
        (
            "GET",
            PROJECT_PATH,
            {"start": [str(start)], "limit": ["100"]},
            f"Bearer {TOKEN}",
        )
        for start in starts
    ]


def expected_json(self_url: str) -> list[dict[str, object]]:
    return [
        {
            "key": "DEMO",
            "name": "Demo\tTeam",
            "public": False,
            "description": "Demo — α",
            "url": self_url,
        },
        {
            "key": "OPS",
            "name": None,
            "public": True,
            "description": None,
            "url": None,
        },
    ]


EXPECTED_TSV = "# 2 row(s)\nkey\tname\tpublic\nDEMO\tDemo\\tTeam\tFalse\nOPS\t\tTrue\n"


def test_projects_default_tsv_keeps_legacy_columns_and_escaping() -> None:
    result, seen, intruder, _self_url = run_projects("paged")

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout == EXPECTED_TSV
    assert seen == expected_seen([0, 17])
    assert intruder == []


def test_projects_json_reports_full_semantic_rows_and_exact_booleans() -> None:
    result, seen, intruder, self_url = run_projects("paged", "--json")

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    rows = json.loads(result.stdout)
    assert rows == expected_json(self_url)
    assert rows[0]["public"] is False
    assert rows[1]["public"] is True
    assert seen == expected_seen([0, 17])
    assert intruder == []


@pytest.mark.parametrize(
    ("scenario", "options", "expected", "starts"),
    [
        ("later-failure", (), "HTTP 503", [0, 17]),
        ("paged", ("--max-pages", "1"), "page limit", [0]),
    ],
    ids=["later-failure", "cap"],
)
def test_projects_failures_publish_nothing_and_hide_request_details(
    scenario: str, options: tuple[str, ...], expected: str, starts: list[int]
) -> None:
    result, seen, intruder, _self_url = run_projects(scenario, *options)

    assert result.returncode == 1
    assert result.stdout == ""
    assert expected in result.stderr
    for detail in (TOKEN, PROJECT_PATH, "fixture-query", "RESPONSE-SENTINEL"):
        assert detail not in result.stderr
    assert seen == expected_seen(starts)
    assert intruder == []


@pytest.mark.parametrize(
    ("scenario", "expected", "starts"),
    [
        ("echo-start", "Invalid Bitbucket page start", [0, 100]),
        ("echo-size", "Invalid Bitbucket page size", [0]),
    ],
    ids=["stale-terminal-cursor", "inflated-terminal-size"],
)
def test_projects_reject_page_metadata_that_does_not_describe_the_request(
    scenario: str, expected: str, starts: list[int]
) -> None:
    # Both scenarios used to succeed: a stale cursor silently repeated a row and
    # an inflated size was never compared with the values that were published.
    result, seen, intruder, _self_url = run_projects(scenario)

    assert result.returncode == 1
    assert result.stdout == ""
    assert expected in result.stderr
    for detail in (TOKEN, PROJECT_PATH, "RESPONSE-SENTINEL"):
        assert detail not in result.stderr
    assert seen == expected_seen(starts)
    assert intruder == []
