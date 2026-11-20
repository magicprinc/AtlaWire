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

TOKEN = "fixture-children-only"
CONTEXT = "/wiki/confluence"
PARENT_ID = "4242"
CHILD_PATH = f"{CONTEXT}/rest/api/content/{PARENT_ID}/child/page"
PARENT_PATH = "/display/OTHER/Pasted?spaceKey=OTHER&pageId=4242#fragment"

FIRST = {
    "id": "5001",
    "type": "page",
    "status": "current",
    "title": "Résumé — α",
    "version": {"number": 7, "by": {"displayName": "Ada"}},
    "body": {"storage": {"value": "unrequested"}},
    "_links": {"webui": "/display/DEMO/One"},
}
FIRST_WITHOUT_VERSION = {key: value for key, value in FIRST.items() if key != "version"}
SECOND = {
    "id": 5002,
    "type": "page",
    "status": "current",
    "title": "Second",
    "version": {"number": 0},
}
EXPECTED_TSV = "# 2 row(s)\nid\ttitle\tversion\n5001\tRésumé — α\t7\n5002\tSecond\t0\n"
EXPECTED_JSON = [
    {"id": "5001", "title": "Résumé — α", "version": None},
    {"id": 5002, "title": "Second", "version": 0},
]


def page(
    start: int, requested: int, *results: object, **extra: object
) -> dict[str, object]:
    return {
        "start": start,
        "limit": requested,
        "size": len(results),
        "results": list(results),
        **extra,
    }


def fixture(
    scenario: str, start: int, requested: int, intruder_port: int
) -> tuple[int, dict[str, object]]:
    if scenario == "paged":
        if start == 0:
            return 200, page(0, requested, FIRST)
        if start == 1:
            return 200, page(
                1,
                requested,
                SECOND,
                _links={
                    "next": f"http://127.0.0.1:{intruder_port}"
                    f"/elsewhere{CHILD_PATH}"
                    "?expand=body&start=2&limit=999"
                },
            )
        if start == 2:
            return 200, page(2, requested, totalSize=2)
    if scenario == "json-paged":
        if start == 0:
            return 200, page(0, requested, FIRST_WITHOUT_VERSION)
        if start == 1:
            return 200, page(1, requested, SECOND)
    if scenario == "malformed":
        if start == 0:
            return 200, page(0, requested, FIRST)
        return 200, page(
            start,
            requested,
            {"id": "5003", "title": "LEAK-TITLE", "version": {"number": True}},
        )
    return 400, {"unexpectedStart": start}


def run_children(
    scenario: str, *options: str, parent_path: str = PARENT_PATH
) -> tuple[subprocess.CompletedProcess[str], list[Request], list[str], list[str]]:
    seen: list[Request] = []
    intruder: list[str] = []
    pasted: list[str] = []

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
                    "results": [{"id": "666", "title": "Leak"}],
                },
            )

    class Pasted(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            pasted.append(self.path)
            send_json(
                self,
                200,
                {"start": 0, "limit": 1, "size": 0, "results": []},
            )

    with serving(Intruder) as intruder_server, serving(Pasted) as pasted_server:

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
            parent = f"http://127.0.0.1:{pasted_server.server_port}{parent_path}"
            result = run_installed(
                [
                    "children",
                    parent,
                    "--allow-http-loopback",
                    "--token-from-env",
                    *options,
                ],
                confluence_environment(origin, context=CONTEXT, token=TOKEN),
            )
    return result, seen, intruder, pasted


def expected_seen(calls: list[tuple[int, int]]) -> list[Request]:
    return [
        (
            "GET",
            CHILD_PATH,
            {
                "expand": ["version"],
                "start": [str(start)],
                "limit": [str(limit)],
            },
            f"Bearer {TOKEN}",
        )
        for start, limit in calls
    ]


def test_children_tsv_lists_direct_children_by_count_with_the_default_limit() -> None:
    result, seen, intruder, pasted = run_children("paged")

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout == EXPECTED_TSV
    assert seen == expected_seen([(0, 100), (1, 99), (2, 98)])
    assert intruder == []
    assert pasted == []


def test_children_json_keeps_an_absent_version_as_null_and_zero_as_zero() -> None:
    result, seen, intruder, pasted = run_children(
        "json-paged", "--json", "--limit", "2"
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    rows = json.loads(result.stdout)
    assert "version" in rows[0]
    assert rows[0]["version"] is None
    assert rows[1]["version"] == 0
    assert type(rows[1]["version"]) is int
    assert rows == EXPECTED_JSON
    assert seen == expected_seen([(0, 2), (1, 1)])
    assert intruder == []
    assert pasted == []


def test_children_malformed_version_publishes_nothing_and_hides_raw_values() -> None:
    result, seen, intruder, pasted = run_children("malformed", "--json", "--limit", "2")

    assert result.returncode == 1
    assert result.stdout == ""
    assert "Confluence child page" in result.stderr
    for raw in (TOKEN, CHILD_PATH, "5003", "LEAK-TITLE"):
        assert raw not in result.stderr
    assert seen == expected_seen([(0, 2), (1, 1)])
    assert intruder == []
    assert pasted == []


def test_children_conflicting_page_ids_send_no_request_and_echo_no_input() -> None:
    result, seen, intruder, pasted = run_children(
        "unused",
        "--json",
        parent_path=(
            "/pages/viewpage.action?pageId=4242&pageId=4243&secret=fixture-link-marker"
        ),
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "pageId" in result.stderr
    for raw in ("fixture-link-marker", "4243", "127.0.0.1"):
        assert raw not in result.stderr
    assert seen == []
    assert intruder == []
    assert pasted == []


@pytest.mark.parametrize(
    ("options", "stdout"),
    [
        (("--limit", "0", "--json"), "[]\n"),
        (("--limit", "0"), "# 0 row(s)\nid\ttitle\tversion\n"),
    ],
    ids=["zero-json", "zero-tsv"],
)
def test_children_zero_limit_sends_no_request(
    options: tuple[str, ...], stdout: str
) -> None:
    result, seen, intruder, pasted = run_children("unused", *options)

    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout == stdout
    assert seen == []
    assert intruder == []
    assert pasted == []
