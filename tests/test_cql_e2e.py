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

TOKEN = "fixture-cql-only"
CONTEXT = "/wiki/confluence"
SEARCH_PATH = f"{CONTEXT}/rest/api/search"
QUERY = 'space = DEMO AND text ~ "Résumé & 100%? +more"'

FIRST = {
    "content": {
        "id": "101",
        "type": "page",
        "title": "Résumé — α",
        "space": {"key": "DEMO"},
        "_links": {"webui": "/content-link/101"},
    },
    "id": "999",
    "type": "blogpost",
    "title": "Top title is ignored",
    "space": {"key": "OTHER"},
    "url": "/top-url-is-ignored",
    "_links": {"webui": "/display/DEMO/Résumé"},
}
SECOND = {
    "content": {},
    "id": 202,
    "type": "blogpost",
    "title": "Fallback\tTitle",
    "space": {"key": "OTHER"},
    "url": "/pages/viewpage.action?pageId=202",
    "_expandable": {"space": "/rest/api/space/IGNORED"},
}
OVERLAP_FIRST = {
    "content": {
        "id": "101",
        "type": "page",
        "title": "First",
        "space": {"key": "DEMO"},
    }
}
OVERLAP_SECOND = {
    "content": {
        "id": "202",
        "type": "page",
        "title": "Second",
        "space": {"key": "DEMO"},
    }
}
OVERLAP_SECOND_CHANGED = {
    "content": {
        "id": "202",
        "type": "page",
        "title": "Second with changed metadata",
        "space": {"key": "DEMO"},
    }
}
OVERLAP_THIRD = {
    "content": {
        "id": "303",
        "type": "page",
        "title": "Third",
        "space": {"key": "DEMO"},
    }
}
SURROGATE = {
    "content": {
        "id": "101",
        "type": "page",
        "title": "Cost \ud800",
        "space": {"key": "DEMO"},
    }
}
EXPECTED = [
    {
        "id": "101",
        "space": "DEMO",
        "type": "page",
        "title": "Résumé — α",
        "url": "/display/DEMO/Résumé",
    },
    {
        "id": 202,
        "space": "OTHER",
        "type": "blogpost",
        "title": "Fallback\tTitle",
        "url": "/pages/viewpage.action?pageId=202",
    },
]
EXPECTED_TSV = (
    "# 2 row(s)\n"
    "id\tspace\ttype\ttitle\turl\n"
    "101\tDEMO\tpage\tRésumé — α\t/display/DEMO/Résumé\n"
    "202\tOTHER\tblogpost\tFallback\\tTitle\t/pages/viewpage.action?pageId=202\n"
)


def fixture(
    scenario: str, start: int, intruder_port: int
) -> tuple[int, dict[str, object]]:
    if scenario == "paged":
        if start == 0:
            return 200, {"start": 0, "size": 1, "results": [FIRST]}
        if start == 1:
            return 200, {
                "start": 1,
                "size": 1,
                "results": [SECOND],
                "_links": {
                    "next": f"http://127.0.0.1:{intruder_port}/elsewhere/rest/api/search"
                    "?cql=space%20%3D%20WRONG&start=2&limit=99"
                },
            }
        if start == 2:
            return 200, {"start": 2, "size": 0, "results": [], "totalSize": 2}
    if scenario == "later-failure":
        if start == 0:
            return 200, {"start": 0, "size": 1, "results": [FIRST]}
        return 503, {
            "message": TOKEN,
            "query": QUERY,
            "url": SEARCH_PATH,
            "response": "RESPONSE-SENTINEL",
        }
    if scenario == "capped":
        return 200, {
            "start": start,
            "size": 1,
            "results": [FIRST],
            "_links": {"next": 5},
        }
    if scenario == "overlap":
        if start == 0:
            return 200, {
                "start": 0,
                "size": 2,
                "results": [OVERLAP_FIRST, OVERLAP_SECOND],
            }
        return 200, {
            "start": start,
            "size": 2,
            "results": [OVERLAP_SECOND_CHANGED, OVERLAP_THIRD],
        }
    if scenario == "forgotten-total":
        if start == 0:
            return 200, {
                "start": 0,
                "size": 1,
                "results": [FIRST],
                "totalSize": 2,
            }
        return 200, {"start": start, "size": 0, "results": []}
    if scenario == "surrogate":
        if start == 0:
            return 200, {
                "start": 0,
                "size": 1,
                "results": [SURROGATE],
                "totalSize": 1,
            }
        return 200, {"start": start, "size": 0, "results": [], "totalSize": 1}
    return 400, {"unexpectedStart": start}


def run_cql(
    scenario: str, *options: str, query: str = QUERY
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
                    "size": 1,
                    "results": [
                        {"content": {"id": "666", "type": "page", "title": "Leak"}}
                    ],
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
                except ValueError:
                    start = -1
                status, body = fixture(scenario, start, intruder_server.server_port)
                send_json(self, status, body)

        with serving(Handler) as server:
            origin = f"http://127.0.0.1:{server.server_port}"
            result = run_installed(
                ["cql", query, "--allow-http-loopback", "--token-from-env", *options],
                confluence_environment(origin, context=CONTEXT, token=TOKEN),
            )
    return result, seen, intruder


@pytest.mark.parametrize("output", [("--json",), ()], ids=["json", "tsv"])
def test_cql_projects_rows_and_pages_by_count(output: tuple[str, ...]) -> None:
    result, seen, intruder = run_cql("paged", "--limit", "3", *output)

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    if output:
        assert json.loads(result.stdout) == EXPECTED
    else:
        assert result.stdout == EXPECTED_TSV
    assert seen == [
        (
            "GET",
            SEARCH_PATH,
            {"cql": [QUERY], "start": ["0"], "limit": ["3"]},
            f"Bearer {TOKEN}",
        ),
        (
            "GET",
            SEARCH_PATH,
            {"cql": [QUERY], "start": ["1"], "limit": ["2"]},
            f"Bearer {TOKEN}",
        ),
        (
            "GET",
            SEARCH_PATH,
            {"cql": [QUERY], "start": ["2"], "limit": ["1"]},
            f"Bearer {TOKEN}",
        ),
    ]
    assert intruder == []


def test_cql_partial_overlap_fails_without_publishing_rows() -> None:
    result, seen, intruder = run_cql("overlap", "--limit", "4", "--json")

    assert result.returncode == 1
    assert result.stdout == ""
    assert "repeated" in result.stderr
    assert len(seen) == 2
    assert intruder == []


def test_cql_empty_page_cannot_forget_a_known_total_size() -> None:
    result, seen, intruder = run_cql("forgotten-total", "--limit", "3", "--json")

    assert result.returncode == 1
    assert result.stdout == ""
    assert "empty page" in result.stderr
    assert len(seen) == 2
    assert intruder == []


@pytest.mark.parametrize("output", [("--json",), ()], ids=["json", "tsv"])
def test_cql_lone_surrogate_title_fails_without_partial_output(
    output: tuple[str, ...],
) -> None:
    result, _seen, intruder = run_cql("surrogate", "--limit", "3", *output)

    assert result.returncode == 1
    assert result.stdout == ""
    assert "content metadata" in result.stderr
    assert "Traceback" not in result.stderr
    assert "UnicodeEncodeError" not in result.stderr
    assert intruder == []


def test_cql_later_failure_publishes_nothing_and_hides_request_details() -> None:
    result, seen, intruder = run_cql("later-failure", "--limit", "3", "--json")

    assert result.returncode == 1
    assert result.stdout == ""
    assert "HTTP 503" in result.stderr
    for detail in (TOKEN, QUERY, SEARCH_PATH, "RESPONSE-SENTINEL"):
        assert detail not in result.stderr
    assert seen == [
        (
            "GET",
            SEARCH_PATH,
            {"cql": [QUERY], "start": ["0"], "limit": ["3"]},
            f"Bearer {TOKEN}",
        ),
        (
            "GET",
            SEARCH_PATH,
            {"cql": [QUERY], "start": ["1"], "limit": ["2"]},
            f"Bearer {TOKEN}",
        ),
    ]
    assert intruder == []


def test_cql_exact_limit_ignores_an_unused_malformed_continuation() -> None:
    result, seen, intruder = run_cql("capped", "--limit", "1", "--json")

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == EXPECTED[:1]
    assert len(seen) == 1
    assert seen[0][2] == {"cql": [QUERY], "start": ["0"], "limit": ["1"]}
    assert intruder == []


@pytest.mark.parametrize(
    ("query", "options", "code", "stdout"),
    [
        (QUERY, ("--limit", "0", "--json"), 0, "[]\n"),
        (
            QUERY,
            ("--limit", "0"),
            0,
            "# 0 row(s)\nid\tspace\ttype\ttitle\turl\n",
        ),
        (QUERY, ("--limit", "1001", "--json"), 2, ""),
        (QUERY, ("--limit", "-1", "--json"), 2, ""),
        (QUERY, ("--limit", "many", "--json"), 2, ""),
        ("", ("--json",), 2, ""),
        ("   ", ("--json",), 2, ""),
    ],
    ids=[
        "zero-json",
        "zero-tsv",
        "above-range",
        "negative",
        "not-a-number",
        "blank",
        "spaces",
    ],
)
def test_cql_invalid_or_zero_limit_sends_no_request(
    query: str, options: tuple[str, ...], code: int, stdout: str
) -> None:
    result, seen, intruder = run_cql("unused", *options, query=query)

    assert result.returncode == code
    assert result.stdout == stdout
    assert seen == []
    assert intruder == []
