import json
import os
import shutil
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from urllib.parse import parse_qs, urlsplit

import pytest

TOKEN = "fixture-jql-only"
PATH = "/jira/rest/api/2/search"
QUERY = "project = DEMO ORDER BY key"
FIELDS = "summary,status,priority,issuetype,assignee,updated"

FIRST = {
    "key": "DEMO-1",
    "fields": {
        "summary": "  First\n summary ",
        "status": {"name": "In Progress"},
        "issuetype": {"name": "Bug"},
        "priority": {"name": "High"},
        "assignee": {"displayName": "Ada"},
        "updated": "2024-01-02T03:04:05.000+0000",
    },
}
SECOND = {
    "key": "DEMO-2",
    "fields": {
        "summary": "Second summary",
        "status": None,
        "issuetype": {"name": "Task"},
        "priority": None,
        "assignee": None,
        "updated": None,
    },
}
THIRD = {
    "key": "DEMO-3",
    "fields": {
        "summary": "Third summary",
        "status": {"name": "Done"},
        "issuetype": {"name": "Story"},
        "priority": {"name": "Low"},
        "assignee": {"displayName": "Ada\tLovelace"},
        "updated": "2024-03-04T05:06:07.000+0000",
    },
}
FOURTH = {
    "key": "DEMO-4",
    "fields": {
        "summary": "Fourth summary",
        "status": {"name": "Open"},
        "issuetype": None,
        "priority": {"name": "Medium"},
        "assignee": {"displayName": "Bob"},
        "updated": "2024-04-05T06:07:08.000+0000",
    },
}
FIFTH = {
    "key": "DEMO-5",
    "fields": {
        "summary": None,
        "status": {"name": "Closed"},
        "issuetype": {"name": "Task"},
        "priority": {"name": "Low"},
        "assignee": {},
        "updated": "",
    },
}
EXPECTED = [
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
        "status": "Done",
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
    {
        "key": "DEMO-5",
        "status": "Closed",
        "type": "Task",
        "priority": "Low",
        "assignee": None,
        "updated": "",
        "summary": "",
    },
]
EXPECTED_TSV = (
    "# 5 row(s)\n"
    "key\tstatus\ttype\tpriority\tassignee\tupdated\tsummary\n"
    "DEMO-1\tIn Progress\tBug\tHigh\tAda\t2024-01-02\tFirst summary\n"
    "DEMO-2\t\tTask\t\t\t\tSecond summary\n"
    "DEMO-3\tDone\tStory\tLow\tAda\\tLovelace\t2024-03-04\tThird summary\n"
    "DEMO-4\tOpen\t\tMedium\tBob\t2024-04-05\tFourth summary\n"
    "DEMO-5\tClosed\tTask\tLow\t\t\t\n"
)

Seen = tuple[str, str, dict[str, list[str]], bool]


def run_jql(
    scenario: str, *options: str, query: str = QUERY
) -> tuple[subprocess.CompletedProcess[str], list[Seen]]:
    script = shutil.which("atlawire")
    assert script is not None, "Install AtlaWire before running its CLI E2E suite."
    seen: list[Seen] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            url = urlsplit(self.path)
            params = parse_qs(url.query)
            authorized = self.headers.get("Authorization") == f"Bearer {TOKEN}"
            seen.append((self.command, url.path, params, authorized))
            start = int(params.get("startAt", ["-1"])[0])
            status = 200
            if url.path != PATH or not authorized or scenario == "unauthorized":
                status, body = 401, {"message": TOKEN, "query": QUERY}
            elif scenario == "redirect":
                self.send_response(302)
                self.send_header("Location", "/unexpected")
                self.end_headers()
                return
            else:
                status, body = fixture(scenario, start, params)
            payload = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    with HTTPServer(("127.0.0.1", 0), Handler) as server:
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            env = {
                **os.environ,
                "ATLAWIRE_JIRA_URL": f"http://127.0.0.1:{server.server_port}/jira/",
                "ATLAWIRE_JIRA_TOKEN": TOKEN,
                "ATLAWIRE_BITBUCKET_TOKEN": "wrong-product-fixture",
            }
            result = subprocess.run(
                [
                    script,
                    "jql",
                    query,
                    "--allow-http-loopback",
                    "--token-from-env",
                    *options,
                ],
                env=env,
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        finally:
            server.shutdown()
            worker.join(timeout=5)
            assert not worker.is_alive()
    return result, seen


def fixture(
    scenario: str, start: int, params: dict[str, list[str]]
) -> tuple[int, dict[str, object]]:
    if scenario == "pages":
        if start == 0:
            return 200, {
                "startAt": 0,
                "maxResults": 5,
                "total": 5,
                "issues": [FIRST, SECOND],
            }
        if start == 2:
            return 200, {
                "startAt": 2,
                "maxResults": 3,
                "total": 5,
                "issues": [THIRD, FOURTH, FIFTH],
            }
        return 200, {"startAt": start, "maxResults": 50, "total": 5, "issues": []}
    if scenario == "capped":
        if start == 0:
            return 200, {
                "startAt": 0,
                "maxResults": 2,
                "total": 5,
                "issues": [FIRST, SECOND],
            }
        if start == 2:
            return 200, {
                "startAt": 2,
                "maxResults": 3,
                "total": 5,
                "issues": [THIRD, FOURTH, FIFTH],
            }
        return 200, {"startAt": start, "maxResults": 3, "total": 5, "issues": []}
    if scenario == "empty":
        return 200, {"startAt": start, "maxResults": 50, "total": 0, "issues": []}
    if scenario == "later-failure":
        if start == 0:
            return 200, {
                "startAt": 0,
                "maxResults": 1,
                "total": 3,
                "issues": [FIRST],
            }
        return 503, {"message": TOKEN, "query": QUERY, "path": PATH}
    if scenario == "bounded":
        return 200, {
            "startAt": start,
            "maxResults": 1,
            "total": 1000,
            "issues": [
                {
                    "key": f"DEMO-{start + 1}",
                    "fields": {
                        "summary": f"Row {start}",
                        "status": {"name": "Open"},
                        "issuetype": {"name": "Task"},
                        "priority": {"name": "Low"},
                        "assignee": None,
                        "updated": "2024-01-02T03:04:05.000+0000",
                    },
                }
            ],
        }
    if scenario == "bad-start":
        return 200, {"startAt": 1, "maxResults": 50, "total": 5, "issues": []}
    if scenario == "contradictory":
        return 200, {
            "startAt": 0,
            "maxResults": 50,
            "total": 0,
            "issues": [FIRST],
        }
    if scenario == "bad-total":
        return 200, {"startAt": 0, "maxResults": 50, "total": True, "issues": []}
    if scenario == "missing-max-results":
        return 200, {"startAt": 0, "total": 1, "issues": [FIRST]}
    if scenario == "duplicate-key":
        return 200, {
            "startAt": start,
            "maxResults": 1,
            "total": 2,
            "issues": [FIRST],
        }
    if scenario == "contradictory-total":
        if start == 0:
            return 200, {
                "startAt": 0,
                "maxResults": 1,
                "total": 3,
                "issues": [FIRST],
            }
        return 200, {"startAt": start, "maxResults": 1, "total": 1, "issues": []}
    if scenario == "forgotten-total":
        if start == 0:
            return 200, {
                "startAt": 0,
                "maxResults": 1,
                "total": 3,
                "issues": [FIRST],
            }
        return 200, {"startAt": start, "maxResults": 1, "issues": []}
    if scenario == "malformed-key":
        return 200, {
            "startAt": start,
            "maxResults": 50,
            "total": 1,
            "issues": [{"key": "demo-1", "fields": {}}],
        }
    if scenario == "surrogate-summary":
        return 200, {
            "startAt": start,
            "maxResults": 50,
            "total": 1,
            "issues": [{"key": "DEMO-1", "fields": {"summary": "Cost \ud800"}}],
        }
    raise AssertionError(f"Unknown scenario {scenario}.")


def test_jql_json_follows_a_short_page_by_consumed_rows() -> None:
    result, seen = run_jql("pages", "--limit", "5", "--json")

    assert result.returncode == 0, result.stderr
    assert not result.stderr
    assert json.loads(result.stdout) == EXPECTED
    assert seen == [
        (
            "GET",
            PATH,
            {
                "jql": [QUERY],
                "fields": [FIELDS],
                "startAt": ["0"],
                "maxResults": ["5"],
            },
            True,
        ),
        (
            "GET",
            PATH,
            {
                "jql": [QUERY],
                "fields": [FIELDS],
                "startAt": ["2"],
                "maxResults": ["3"],
            },
            True,
        ),
    ]


def test_jql_tsv_uses_bbk_column_order_and_escapes_cells() -> None:
    result, _ = run_jql("pages", "--limit", "5")

    assert result.returncode == 0, result.stderr
    assert not result.stderr
    assert result.stdout == EXPECTED_TSV


def test_jql_uses_remaining_limit_after_a_server_page_cap() -> None:
    result, seen = run_jql("capped", "--limit", "5", "--json")

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == EXPECTED
    assert [request[2]["startAt"] for request in seen] == [["0"], ["2"]]
    assert [request[2]["maxResults"] for request in seen] == [["5"], ["3"]]


@pytest.mark.parametrize(
    ("options", "as_json"),
    [
        (("--json",), True),
        ((), False),
    ],
)
def test_jql_empty_result_uses_the_requested_limit(
    options: tuple[str, ...], as_json: bool
) -> None:
    result, seen = run_jql("empty", *options)

    assert result.returncode == 0, result.stderr
    assert not result.stderr
    if as_json:
        assert json.loads(result.stdout) == []
    else:
        assert result.stdout == (
            "# 0 row(s)\nkey\tstatus\ttype\tpriority\tassignee\tupdated\tsummary\n"
        )
    assert seen == [
        (
            "GET",
            PATH,
            {
                "jql": [QUERY],
                "fields": [FIELDS],
                "startAt": ["0"],
                "maxResults": ["50"],
            },
            True,
        )
    ]


def test_jql_later_failure_publishes_nothing_and_hides_the_response() -> None:
    result, seen = run_jql("later-failure", "--json")

    assert result.returncode == 1
    assert result.stdout == ""
    assert "HTTP 503" in result.stderr
    assert TOKEN not in result.stderr
    assert QUERY not in result.stderr
    assert [request[2]["startAt"] for request in seen] == [["0"], ["1"]]


def test_jql_redirect_is_refused_without_a_second_request() -> None:
    result, seen = run_jql("redirect", "--json")

    assert result.returncode == 1
    assert result.stdout == ""
    assert "redirect" in result.stderr
    assert TOKEN not in result.stderr
    assert QUERY not in result.stderr
    assert seen == [
        (
            "GET",
            PATH,
            {
                "jql": [QUERY],
                "fields": [FIELDS],
                "startAt": ["0"],
                "maxResults": ["50"],
            },
            True,
        )
    ]


@pytest.mark.parametrize(
    ("scenario", "message"),
    [
        ("bad-start", "startAt"),
        ("contradictory", "Inconsistent"),
        ("bad-total", "total"),
        ("missing-max-results", "maxResults"),
        ("unauthorized", "HTTP 401"),
    ],
)
def test_jql_invalid_metadata_fails_without_publishing_rows(
    scenario: str, message: str
) -> None:
    result, _ = run_jql(scenario, "--json")

    assert result.returncode == 1
    assert result.stdout == ""
    assert message in result.stderr
    assert TOKEN not in result.stderr
    assert QUERY not in result.stderr


def test_jql_duplicate_issue_keys_fail_without_publishing_rows() -> None:
    result, seen = run_jql("duplicate-key", "--limit", "2", "--json")

    assert result.returncode == 1
    assert result.stdout == ""
    assert "duplicate issue keys" in result.stderr
    assert [request[2]["startAt"] for request in seen] == [["0"], ["1"]]


@pytest.mark.parametrize(
    ("scenario", "message"),
    [
        ("contradictory-total", "total changed"),
        ("forgotten-total", "empty page"),
    ],
    ids=["contradictory-terminal-total", "terminal-page-omits-known-total"],
)
def test_jql_terminal_total_inconsistency_fails_without_rows(
    scenario: str, message: str
) -> None:
    result, seen = run_jql(scenario, "--json")

    assert result.returncode == 1
    assert result.stdout == ""
    assert message in result.stderr
    assert [request[2]["startAt"] for request in seen] == [["0"], ["1"]]


def test_jql_malformed_search_key_fails_without_rows() -> None:
    result, _ = run_jql("malformed-key", "--json")

    assert result.returncode == 1
    assert result.stdout == ""
    assert "issue key" in result.stderr


@pytest.mark.parametrize("options", [("--json",), ()], ids=["json", "tsv"])
def test_jql_lone_surrogate_summary_fails_without_partial_output(
    options: tuple[str, ...],
) -> None:
    result, _ = run_jql("surrogate-summary", *options)

    assert result.returncode == 1
    assert result.stdout == ""
    assert "summary" in result.stderr
    assert "Traceback" not in result.stderr
    assert "UnicodeEncodeError" not in result.stderr


def test_jql_stops_at_the_limit_when_total_never_proves_exhaustion() -> None:
    result, seen = run_jql("bounded", "--limit", "3", "--json")

    assert result.returncode == 0, result.stderr
    rows = json.loads(result.stdout)
    assert [row["key"] for row in rows] == ["DEMO-1", "DEMO-2", "DEMO-3"]
    assert [request[2]["startAt"] for request in seen] == [["0"], ["1"], ["2"]]
    assert [request[2]["maxResults"] for request in seen] == [["3"], ["2"], ["1"]]


@pytest.mark.parametrize(
    ("query", "options"),
    [
        ("", ("--json",)),
        ("   ", ("--json",)),
        (QUERY, ("--limit", "0")),
        (QUERY, ("--limit", "1001")),
        (QUERY, ("--limit", "many")),
    ],
)
def test_jql_parse_errors_fail_before_any_request(
    query: str, options: tuple[str, ...]
) -> None:
    result, seen = run_jql("empty", *options, query=query)

    assert result.returncode == 2
    assert result.stdout == ""
    assert seen == []
