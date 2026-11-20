import json
import subprocess
from http.server import BaseHTTPRequestHandler

import pytest

from tests._loopback import (
    Request,
    confluence_environment,
    request_record,
    run_installed,
    send_json,
    serving,
)

TOKEN = "fixture-spaces-only"
CONTEXT = "/wiki/confluence"
SPACE_PATH = f"{CONTEXT}/rest/api/space"

FIRST = {
    "id": 10,
    "key": "DEMO",
    "name": "Demo — α",
    "type": "global",
    "status": "current",
    "_links": {"webui": "/display/DEMO"},
}
SECOND = {"id": 11, "key": "OPS"}
EXPECTED = [
    {"key": "DEMO", "name": "Demo — α", "type": "global"},
    {"key": "OPS", "name": None, "type": None},
]
EXPECTED_TSV = "# 2 row(s)\nkey\tname\ttype\nDEMO\tDemo — α\tglobal\nOPS\t\t\n"


def fixture(
    scenario: str, start: int, requested: int, intruder_port: int
) -> tuple[int, dict[str, object]]:
    if scenario == "paged":
        if start == 0:
            return 200, {
                "start": 0,
                "limit": requested,
                "size": 1,
                "results": [FIRST],
            }
        if start == 1:
            return 200, {
                "start": 1,
                "limit": requested,
                "size": 1,
                "results": [SECOND],
                "_links": {
                    "next": f"http://127.0.0.1:{intruder_port}/elsewhere"
                    "/rest/api/space?start=2&limit=999&key=WRONG"
                },
            }
        if start == 2:
            return 200, {
                "start": 2,
                "limit": requested,
                "size": 0,
                "results": [],
            }
    if scenario == "later-failure":
        if start == 0:
            return 200, {
                "start": 0,
                "limit": requested,
                "size": 1,
                "results": [FIRST],
            }
        return 503, {
            "message": TOKEN,
            "path": SPACE_PATH,
            "query": "fixture-query",
            "response": "RESPONSE-SENTINEL",
        }
    if scenario == "malformed":
        if start == 0:
            return 200, {
                "start": 0,
                "limit": requested,
                "size": 1,
                "results": [FIRST],
            }
        return 200, {
            "start": start,
            "limit": requested,
            "size": 1,
            "results": [{"id": 12, "key": "BAD", "name": 5, "type": "global"}],
        }
    return 400, {"unexpectedStart": start}


def run_spaces(
    scenario: str, *options: str
) -> tuple[subprocess.CompletedProcess[str], list[Request], list[str]]:
    seen: list[Request] = []
    intruder: list[str] = []

    class Intruder(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            intruder.append(self.path)
            send_json(
                self,
                200,
                {
                    "start": 2,
                    "limit": 1,
                    "size": 1,
                    "results": [{"key": "LEAK", "name": "Leak", "type": "global"}],
                },
            )

    with serving(Intruder) as intruder_server:

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: object) -> None:
                pass

            def do_GET(self) -> None:
                record = request_record(self)
                seen.append(record)
                params = record[2]
                try:
                    start = int(params.get("start", ["-1"])[0])
                    requested = int(params.get("limit", ["-1"])[0])
                except ValueError:
                    start = -1
                    requested = -1
                status, body = fixture(
                    scenario, start, requested, intruder_server.server_port
                )
                send_json(self, status, body)

        with serving(Handler) as server:
            origin = f"http://127.0.0.1:{server.server_port}"
            result = run_installed(
                ["spaces", "--allow-http-loopback", "--token-from-env", *options],
                confluence_environment(origin, context=CONTEXT, token=TOKEN),
            )
    return result, seen, intruder


def expected_seen(calls: list[tuple[int, int]]) -> list[Request]:
    return [
        (
            "GET",
            SPACE_PATH,
            {"start": [str(start)], "limit": [str(limit)]},
            f"Bearer {TOKEN}",
        )
        for start, limit in calls
    ]


@pytest.mark.parametrize(
    ("options", "stdout", "calls"),
    [
        ((), EXPECTED_TSV, [(0, 100), (1, 99), (2, 98)]),
        (("--json", "--limit", "2"), json.dumps(EXPECTED) + "\n", [(0, 2), (1, 1)]),
    ],
    ids=["default-tsv", "json-explicit-limit"],
)
def test_spaces_lists_by_count_with_the_default_or_explicit_limit(
    options: tuple[str, ...], stdout: str, calls: list[tuple[int, int]]
) -> None:
    result, seen, intruder = run_spaces("paged", *options)

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout == stdout
    assert seen == expected_seen(calls)
    assert intruder == []


def test_spaces_later_failure_publishes_nothing_and_hides_request_details() -> None:
    result, seen, intruder = run_spaces("later-failure", "--json", "--limit", "2")

    assert result.returncode == 1
    assert result.stdout == ""
    assert "HTTP 503" in result.stderr
    for detail in (TOKEN, SPACE_PATH, "fixture-query", "RESPONSE-SENTINEL"):
        assert detail not in result.stderr
    assert seen == expected_seen([(0, 2), (1, 1)])
    assert intruder == []


def test_spaces_malformed_metadata_publishes_nothing() -> None:
    result, seen, intruder = run_spaces("malformed", "--json", "--limit", "2")

    assert result.returncode == 1
    assert result.stdout == ""
    assert "Confluence space" in result.stderr
    assert seen == expected_seen([(0, 2), (1, 1)])
    assert intruder == []
