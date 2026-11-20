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

TOKEN = "fixture-mine-statuses-only"
SEARCH_PATH = "/jira/rest/api/2/search"
STATUS_PATH = "/jira/rest/api/2/status"
FIELDS = "summary,status,priority,issuetype,assignee,updated"
DEFAULT_QUERY = (
    "assignee = currentUser() AND statusCategory != Done ORDER BY updated DESC"
)
STATUS_NAME = "Готово к деплою — QA"
STATUS_QUERY = (
    f'assignee = currentUser() AND status = "{STATUS_NAME}" ORDER BY updated DESC'
)

ISSUES = [
    {
        "key": "DEMO-1",
        "fields": {
            "summary": "  First\n summary ",
            "status": {"name": "In Progress"},
            "issuetype": {"name": "Bug"},
            "priority": {"name": "High"},
            "assignee": {"displayName": "Ada"},
            "updated": "2024-01-02T03:04:05.000+0000",
        },
    },
    {
        "key": "DEMO-2",
        "fields": {
            "summary": "Second summary",
            "status": None,
            "issuetype": {"name": "Task"},
            "priority": None,
            "assignee": None,
            "updated": None,
        },
    },
    {
        "key": "DEMO-3",
        "fields": {
            "summary": "Third summary",
            "status": {"name": "Ready for QA"},
            "issuetype": {"name": "Story"},
            "priority": {"name": "Low"},
            "assignee": {"displayName": "Ada\tLovelace"},
            "updated": "2024-03-04T05:06:07.000+0000",
        },
    },
    {
        "key": "DEMO-4",
        "fields": {
            "summary": "Fourth summary",
            "status": {"name": "Open"},
            "issuetype": None,
            "priority": {"name": "Medium"},
            "assignee": {"displayName": "Bob"},
            "updated": "2024-04-05T06:07:08.000+0000",
        },
    },
]

EXPECTED_JSON = [
    {
        "key": "DEMO-1",
        "status": "In Progress",
        "type": "Bug",
        "priority": "High",
        "assignee": "Ada",
        "updated": "2024-01-02",
        "summary": "First summary",
    },
    {
        "key": "DEMO-2",
        "status": None,
        "type": "Task",
        "priority": None,
        "assignee": None,
        "updated": "",
        "summary": "Second summary",
    },
    {
        "key": "DEMO-3",
        "status": "Ready for QA",
        "type": "Story",
        "priority": "Low",
        "assignee": "Ada\tLovelace",
        "updated": "2024-03-04",
        "summary": "Third summary",
    },
    {
        "key": "DEMO-4",
        "status": "Open",
        "type": None,
        "priority": "Medium",
        "assignee": "Bob",
        "updated": "2024-04-05",
        "summary": "Fourth summary",
    },
]

EXPECTED_TSV = (
    "# 4 row(s)\n"
    "key\tstatus\ttype\tpriority\tupdated\tsummary\n"
    "DEMO-1\tIn Progress\tBug\tHigh\t2024-01-02\tFirst summary\n"
    "DEMO-2\t\tTask\t\t\tSecond summary\n"
    "DEMO-3\tReady for QA\tStory\tLow\t2024-03-04\tThird summary\n"
    "DEMO-4\tOpen\t\tMedium\t2024-04-05\tFourth summary\n"
)

STATUS_VALUES = [
    {"name": "Zeta", "id": "9", "extra": {"opaque": True}},
    {"name": "Alpha"},
    {"name": "Zeta"},
    {"name": "Бета", "description": "ignored"},
]
EXPECTED_STATUSES = ["Alpha", "Zeta", "Бета"]


def respond_search(
    handler: BaseHTTPRequestHandler, scenario: str, params: dict[str, list[str]]
) -> None:
    start = int(params.get("startAt", ["-1"])[0])
    if scenario == "default":
        requested = int(params.get("maxResults", ["50"])[0])
        send_json(
            handler,
            200,
            {"startAt": start, "maxResults": requested, "total": 0, "issues": []},
        )
        return
    if scenario != "pages":
        send_json(handler, 500, {})
        return
    page = {0: ISSUES[:2], 2: ISSUES[2:]}.get(start, [])
    send_json(
        handler,
        200,
        {"startAt": start, "maxResults": 2, "total": 4, "issues": page},
    )


def respond_status(handler: BaseHTTPRequestHandler, scenario: str) -> None:
    if scenario == "statuses-ok":
        send_json(handler, 200, STATUS_VALUES)
        return
    if scenario == "statuses-late":
        send_json(handler, 200, [{"name": "Alpha"}, {"name": 7}])
        return
    if scenario == "statuses-surrogate":
        send_json(handler, 200, [{"name": "Open"}, {"name": "\ud800"}])
        return
    send_json(handler, 500, {})


def run_cli(
    scenario: str, *args: str
) -> tuple[
    subprocess.CompletedProcess[str],
    list[Request],
]:
    seen: list[Request] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *values: object) -> None:
            pass

        def do_GET(self) -> None:
            record = request_record(self)
            seen.append(record)
            _, path, params, authorization = record
            if authorization != f"Bearer {TOKEN}":
                send_json(self, 401, {"message": TOKEN})
                return
            if path == SEARCH_PATH:
                respond_search(self, scenario, params)
            elif path == STATUS_PATH:
                respond_status(self, scenario)
            else:
                send_json(self, 404, {})

    with serving(Handler) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        environment = {
            "ATLAWIRE_JIRA_URL": f"{origin}/jira/",
            "ATLAWIRE_JIRA_TOKEN": TOKEN,
            "ATLAWIRE_BITBUCKET_URL": f"{origin}/wrong-bitbucket/",
            "ATLAWIRE_BITBUCKET_TOKEN": "wrong-product-fixture",
            "ATLAWIRE_CONFLUENCE_URL": f"{origin}/wrong-confluence/",
            "ATLAWIRE_CONFLUENCE_TOKEN": "wrong-product-fixture",
        }
        result = run_installed(list(args), environment)
    return result, seen


def test_mine_default_uses_the_exact_open_query_without_a_preflight() -> None:
    result, seen = run_cli(
        "default",
        "mine",
        "--limit",
        "2",
        "--json",
        "--token-from-env",
        "--allow-http-loopback",
    )

    assert result.returncode == 0, result.stderr
    assert not result.stderr
    assert json.loads(result.stdout) == []
    assert seen == [
        (
            "GET",
            SEARCH_PATH,
            {
                "jql": [DEFAULT_QUERY],
                "fields": [FIELDS],
                "startAt": ["0"],
                "maxResults": ["2"],
            },
            f"Bearer {TOKEN}",
        )
    ]


def test_mine_status_tsv_continues_a_server_capped_page_without_assignee() -> None:
    result, seen = run_cli(
        "pages",
        "mine",
        "--status",
        STATUS_NAME,
        "--limit",
        "4",
        "--token-from-env",
        "--allow-http-loopback",
    )

    assert result.returncode == 0, result.stderr
    assert not result.stderr
    assert result.stdout == EXPECTED_TSV
    assert [request[2]["jql"] for request in seen] == [
        [STATUS_QUERY],
        [STATUS_QUERY],
    ]
    assert [request[2]["startAt"] for request in seen] == [["0"], ["2"]]
    assert [request[2]["maxResults"] for request in seen] == [["4"], ["2"]]


def test_mine_json_keeps_the_shared_issue_row_including_assignee() -> None:
    result, seen = run_cli(
        "pages",
        "mine",
        "--status",
        STATUS_NAME,
        "--limit",
        "4",
        "--json",
        "--token-from-env",
        "--allow-http-loopback",
    )

    assert result.returncode == 0, result.stderr
    assert not result.stderr
    assert json.loads(result.stdout) == EXPECTED_JSON
    assert len(seen) == 2


@pytest.mark.parametrize("status", ['Synthetic "label"', "Synthetic\\label"])
def test_mine_refuses_an_unsupported_status_before_any_request(
    status: str,
) -> None:
    result, seen = run_cli(
        "default",
        "mine",
        "--status",
        status,
        "--token-from-env",
        "--allow-http-loopback",
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "Unsupported status name" in result.stderr
    assert status not in result.stderr
    assert seen == []


@pytest.mark.parametrize(
    ("options", "as_json"),
    [((), False), (("--json",), True)],
)
def test_statuses_emit_sorted_unique_names_after_one_configured_request(
    options: tuple[str, ...], as_json: bool
) -> None:
    result, seen = run_cli(
        "statuses-ok",
        "statuses",
        *options,
        "--token-from-env",
        "--allow-http-loopback",
    )

    assert result.returncode == 0, result.stderr
    assert not result.stderr
    if as_json:
        assert json.loads(result.stdout) == EXPECTED_STATUSES
    else:
        assert result.stdout == "Alpha\nZeta\nБета\n"
    assert seen == [("GET", STATUS_PATH, {}, f"Bearer {TOKEN}")]


def test_statuses_malformed_late_entry_publishes_nothing() -> None:
    result, seen = run_cli(
        "statuses-late",
        "statuses",
        "--json",
        "--token-from-env",
        "--allow-http-loopback",
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "Jira statuses with non-empty names" in result.stderr
    assert TOKEN not in result.stderr
    assert len(seen) == 1
    assert seen[0][1] == STATUS_PATH
    assert seen[0][2] == {}


@pytest.mark.parametrize("options", [(), ("--json",)])
def test_statuses_lone_surrogate_late_entry_fails_without_stdout(
    options: tuple[str, ...],
) -> None:
    result, seen = run_cli(
        "statuses-surrogate",
        "statuses",
        *options,
        "--token-from-env",
        "--allow-http-loopback",
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "valid Unicode" in result.stderr
    assert "Traceback" not in result.stderr
    assert "UnicodeEncodeError" not in result.stderr
    assert len(seen) == 1
    assert seen[0][1] == STATUS_PATH
    assert seen[0][2] == {}
