"""Installed-CLI checks for the federated ``find`` command.

Expected CLI contract, wired by a separate change:

    atlawire find TERM [TERM...] --json --allow-http-loopback --token-from-env

reads the three ``ATLAWIRE_<PRODUCT>_URL``/``ATLAWIRE_<PRODUCT>_TOKEN`` pairs,
calls [federated_search][atlawire.federated.federated_search] once, prints its
JSON object, and connects only with GET plus the single fixed Bitbucket search
POST. No other method or route is allowed.
"""

import json
import subprocess
from collections.abc import Sequence
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import cast
from urllib.parse import parse_qs, urlsplit

import pytest

from atlawire.federated import LIMITATIONS
from tests._loopback import run_installed, send_json, serving

CONFLUENCE_CONTEXT = "/confluence"
JIRA_CONTEXT = "/jira"
BITBUCKET_CONTEXT = "/bitbucket"
CONFLUENCE_PATH = f"{CONFLUENCE_CONTEXT}/rest/api/search"
JIRA_PATH = f"{JIRA_CONTEXT}/rest/api/2/search"
BITBUCKET_PATH = f"{BITBUCKET_CONTEXT}/rest/search/latest/search"
CONFLUENCE_TOKEN = "fixture-federated-confluence"
JIRA_TOKEN = "fixture-federated-jira"
BITBUCKET_TOKEN = "fixture-federated-bitbucket"
SECRET_SENTINEL = "RESPONSE-SENTINEL"
JIRA_FIELDS = "summary,status,priority,issuetype,assignee,updated"

Request = tuple[str, str, dict[str, list[str]], str | None, dict[str, object] | None]


def page_fixture(identifier: str, title: str, space: str = "ENG") -> dict[str, object]:
    return {
        "content": {
            "id": identifier,
            "type": "page",
            "title": title,
            "space": {"key": space},
        }
    }


def issue_fixture(key: str, summary: str) -> dict[str, object]:
    return {
        "key": key,
        "fields": {
            "summary": summary,
            "status": {"name": "Open"},
            "issuetype": {"name": "Task"},
            "priority": {"name": "Major"},
            "assignee": {"displayName": "Ann"},
            "updated": "2026-11-20T10:00:00.000+0000",
        },
    }


def code_fixture(path: str, hit_count: int | None = None) -> dict[str, object]:
    value: dict[str, object] = {
        "repository": {"project": {"key": "P"}, "slug": "widgets"},
        "file": path,
    }
    if hit_count is not None:
        value["hitCount"] = hit_count
        value["hitContexts"] = [[{"line": 1, "text": "<em>ported</em> numbers"}]]
    return value


PAGES = {
    "ported numbers": [
        page_fixture("101", "Ported numbers"),
        page_fixture("102", "Ported numbers design"),
    ],
    "ported": [
        page_fixture("103", "Porting notes"),
        page_fixture("101", "Ported numbers"),
    ],
}
ISSUES = {
    "ported numbers": [
        issue_fixture("FED-2", "Second ported issue"),
        issue_fixture("FED-1", "First ported issue"),
    ],
    "ported": [
        issue_fixture("FED-1", "First ported issue"),
        issue_fixture("FED-3", "Third ported issue"),
    ],
}
FILES = {
    "ported numbers": [
        code_fixture("src/a.py", 2),
        code_fixture("src/b.py"),
    ],
    "ported": [
        code_fixture("src/a.py", 7),
        code_fixture("src/c.py", 1),
    ],
}


def cql_term(query: str) -> str:
    prefix = 'text ~ "'
    assert query.startswith(prefix) and query.endswith('"')
    return query[len(prefix) : -1]


def jql_term(query: str) -> str:
    suffix = " ORDER BY created DESC"
    assert query.endswith(suffix)
    return cql_term(query[: -len(suffix)])


def fixture(
    scenario: str,
    method: str,
    path: str,
    params: dict[str, list[str]],
    body: dict[str, object] | None,
) -> tuple[int, dict[str, object]]:
    """Answer only the three read routes; anything else is a test failure."""
    if method == "GET" and path == CONFLUENCE_PATH:
        term = cql_term(params["cql"][0])
        start = int(params["start"][0])
        limit = int(params["limit"][0])
        rows = PAGES.get(term, [])
        returned = rows[start : start + limit]
        return 200, {
            "start": start,
            "limit": limit,
            "size": len(returned),
            "totalSize": len(rows),
            "results": returned,
        }
    if method == "GET" and path == JIRA_PATH:
        term = jql_term(params["jql"][0])
        if scenario == "jira-second-term" and term == "ported":
            return 503, {"message": SECRET_SENTINEL, "path": JIRA_PATH}
        start_at = int(params["startAt"][0])
        max_results = int(params["maxResults"][0])
        rows = ISSUES.get(term, [])
        return 200, {
            "startAt": start_at,
            "maxResults": max_results,
            "total": len(rows),
            "issues": rows[start_at : start_at + max_results],
        }
    if method == "POST" and path == BITBUCKET_PATH:
        assert body is not None
        term = cast(str, body["query"])
        if scenario == "bitbucket-cursor-gap":
            return cursor_gap_page(body)
        return 200, {"code": {"values": FILES.get(term, []), "isLastPage": True}}
    return 400, {"unexpected": SECRET_SENTINEL}


def cursor_gap_page(body: dict[str, object]) -> tuple[int, dict[str, object]]:
    """Page one skips ahead; page two answers with a non-advancing cursor."""
    entities = cast(dict[str, object], body["entities"])
    code = cast(dict[str, object], entities["code"])
    start = cast(int, code["start"])
    if start == 0:
        return 200, {
            "code": {
                "values": [code_fixture("src/a.py", 2)],
                "isLastPage": False,
                "nextStart": 5,
            }
        }
    return 200, {
        "code": {
            "values": [code_fixture("src/b.py", 1)],
            "isLastPage": False,
            "nextStart": 3,
        }
    }


def run_find(
    missing_credentials: Path, scenario: str, *terms: str
) -> tuple[subprocess.CompletedProcess[str], list[Request]]:
    """Run the installed command against one loopback origin with three contexts."""
    seen: list[Request] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def _serve(self, method: str) -> None:
            url = urlsplit(self.path)
            params = parse_qs(url.query, keep_blank_values=True)
            length = int(self.headers.get("Content-Length") or "0")
            raw = self.rfile.read(length) if length else b""
            parsed = json.loads(raw) if raw else None
            body = cast(dict[str, object], parsed) if isinstance(parsed, dict) else None
            seen.append(
                (
                    method,
                    url.path,
                    params,
                    self.headers.get("Authorization"),
                    body,
                )
            )
            status, response = fixture(scenario, method, url.path, params, body)
            send_json(self, status, response)

        def do_GET(self) -> None:
            self._serve("GET")

        def do_POST(self) -> None:
            self._serve("POST")

        def do_PUT(self) -> None:
            self._serve("PUT")

        def do_PATCH(self) -> None:
            self._serve("PATCH")

        def do_DELETE(self) -> None:
            self._serve("DELETE")

    with serving(Handler) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        environment = {
            "ATLAWIRE_CONFLUENCE_URL": f"{origin}{CONFLUENCE_CONTEXT}/",
            "ATLAWIRE_CONFLUENCE_TOKEN": CONFLUENCE_TOKEN,
            "ATLAWIRE_JIRA_URL": f"{origin}{JIRA_CONTEXT}/",
            "ATLAWIRE_JIRA_TOKEN": JIRA_TOKEN,
            "ATLAWIRE_BITBUCKET_URL": f"{origin}{BITBUCKET_CONTEXT}/",
            "ATLAWIRE_BITBUCKET_TOKEN": BITBUCKET_TOKEN,
            "BBK_CREDENTIALS": str(missing_credentials),
        }
        result = run_installed(
            [
                "find",
                *terms,
                "--json",
                "--allow-http-loopback",
                "--token-from-env",
            ],
            environment,
        )
    return result, seen


@pytest.fixture
def missing_credentials(tmp_path: Path) -> Path:
    """A path that cannot resolve saved BBK credentials."""
    return tmp_path / "fixture-missing-bbk-credentials.json"


def confluence_call(term: str, start: int, limit: int) -> Request:
    return (
        "GET",
        CONFLUENCE_PATH,
        {
            "cql": [f'text ~ "{term}"'],
            "start": [str(start)],
            "limit": [str(limit)],
        },
        f"Bearer {CONFLUENCE_TOKEN}",
        None,
    )


def jira_call(term: str) -> Request:
    return (
        "GET",
        JIRA_PATH,
        {
            "jql": [f'text ~ "{term}" ORDER BY created DESC'],
            "fields": [JIRA_FIELDS],
            "startAt": ["0"],
            "maxResults": ["20"],
        },
        f"Bearer {JIRA_TOKEN}",
        None,
    )


def bitbucket_page(term: str, start: int, limit: int) -> Request:
    return (
        "POST",
        BITBUCKET_PATH,
        {},
        f"Bearer {BITBUCKET_TOKEN}",
        {"query": term, "entities": {"code": {"start": start, "limit": limit}}},
    )


def bitbucket_call(term: str) -> Request:
    return bitbucket_page(term, 0, 20)


def expected_requests(terms: Sequence[str]) -> list[Request]:
    records: list[Request] = []
    for term in terms:
        rows = PAGES.get(term, [])
        records.append(confluence_call(term, 0, 20))
        if 0 < len(rows) < 20:
            records.append(confluence_call(term, len(rows), 20 - len(rows)))
        records.append(jira_call(term))
        records.append(bitbucket_call(term))
    return records


def expected_issue(key: str, summary: str, terms: list[str]) -> dict[str, object]:
    return {
        "key": key,
        "status": "Open",
        "type": "Task",
        "priority": "Major",
        "assignee": "Ann",
        "updated": "2026-11-20",
        "summary": summary,
        "terms": terms,
    }


def expected_payload() -> dict[str, object]:
    return {
        "terms": ["ported numbers", "ported"],
        "confluence": [
            {
                "id": "101",
                "title": "Ported numbers",
                "space": "ENG",
                "type": "page",
                "url": None,
                "terms": ["ported numbers", "ported"],
            },
            {
                "id": "102",
                "title": "Ported numbers design",
                "space": "ENG",
                "type": "page",
                "url": None,
                "terms": ["ported numbers"],
            },
            {
                "id": "103",
                "title": "Porting notes",
                "space": "ENG",
                "type": "page",
                "url": None,
                "terms": ["ported"],
            },
        ],
        "jira": [
            expected_issue("FED-2", "Second ported issue", ["ported numbers"]),
            expected_issue("FED-1", "First ported issue", ["ported numbers", "ported"]),
            expected_issue("FED-3", "Third ported issue", ["ported"]),
        ],
        "bitbucket": [
            {
                "project": "P",
                "repository": "widgets",
                "file": "src/a.py",
                "hitCount": 7,
                "matchEvidence": "highlight",
                "terms": ["ported numbers", "ported"],
            },
            {
                "project": "P",
                "repository": "widgets",
                "file": "src/b.py",
                "hitCount": None,
                "matchEvidence": "none",
                "terms": ["ported numbers"],
            },
            {
                "project": "P",
                "repository": "widgets",
                "file": "src/c.py",
                "hitCount": 1,
                "matchEvidence": "highlight",
                "terms": ["ported"],
            },
        ],
        "counts": {"confluence": 3, "jira": 3, "bitbucket": 3},
        "errors": {},
        "complete": True,
        "limits": {"per_term_per_product": 20},
        "limitations": list(LIMITATIONS),
    }


def test_find_json_merges_two_terms_and_uses_only_read_routes(
    missing_credentials: Path,
) -> None:
    result, seen = run_find(missing_credentials, "happy", "ported numbers", "ported")

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    payload = json.loads(result.stdout)
    assert payload == expected_payload()
    assert seen == expected_requests(["ported numbers", "ported"])
    assert {record[0] for record in seen} <= {"GET", "POST"}
    posts = [record[1] for record in seen if record[0] == "POST"]
    assert posts == [BITBUCKET_PATH, BITBUCKET_PATH]
    assert not missing_credentials.exists()
    warning = " ".join(cast(list[str], payload["limitations"]))
    assert "per-term limit" in warning
    assert "Bitbucket" in warning and "indexed" in warning
    assert "may be missing" in warning


def test_find_bitbucket_cursor_failure_publishes_nothing(
    missing_credentials: Path,
) -> None:
    # Bitbucket paging asks for the next page; its non-advancing cursor fails
    # that product, while its first page and the other products survive.
    result, seen = run_find(missing_credentials, "bitbucket-cursor-gap", "paged")

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    payload = json.loads(result.stdout)
    assert payload["complete"] is False
    assert "nextStart" in payload["errors"]["bitbucket"]
    # The product adapter aborts its own paging, so that product contributes
    # nothing; the other products still answer.
    assert payload["bitbucket"] == []
    assert seen == [
        confluence_call("paged", 0, 20),
        jira_call("paged"),
        bitbucket_page("paged", 0, 20),
        bitbucket_page("paged", 5, 19),
    ]
    for detail in (
        CONFLUENCE_TOKEN,
        JIRA_TOKEN,
        BITBUCKET_TOKEN,
        SECRET_SENTINEL,
    ):
        assert detail not in result.stdout


def test_find_unicode_term_reaches_each_product_verbatim(
    missing_credentials: Path,
) -> None:
    result, seen = run_find(missing_credentials, "unicode", "МВНО")

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    payload = json.loads(result.stdout)
    assert payload["terms"] == ["МВНО"]
    assert payload["counts"] == {
        "confluence": 0,
        "jira": 0,
        "bitbucket": 0,
    }
    assert seen == [
        confluence_call("МВНО", 0, 20),
        jira_call("МВНО"),
        bitbucket_call("МВНО"),
    ]


def test_find_unsafe_term_fails_before_any_request(
    missing_credentials: Path,
) -> None:
    result, seen = run_find(missing_credentials, "unsafe", 'ported" OR key = FED-1')

    assert result.returncode == 1
    assert result.stdout == ""
    assert seen == []
    assert "plain text" in result.stderr
    assert "FED-1" not in result.stderr
    assert "Traceback" not in result.stderr
    assert CONFLUENCE_TOKEN not in result.stderr


def test_find_requires_at_least_one_term(missing_credentials: Path) -> None:
    result, seen = run_find(missing_credentials, "missing-term")

    assert result.returncode == 2
    assert result.stdout == ""
    assert seen == []
    assert "Missing argument" in result.stderr


def test_find_jira_failure_on_second_term_keeps_the_other_products(
    missing_credentials: Path,
) -> None:
    result, seen = run_find(
        missing_credentials, "jira-second-term", "ported numbers", "ported"
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    payload = json.loads(result.stdout)
    assert payload["complete"] is False
    assert "jira" in payload["errors"]
    assert payload["jira"], "the first term's issues survive"
    assert payload["confluence"], "later terms still reach other products"
    assert seen == [
        *expected_requests(["ported numbers"]),
        confluence_call("ported", 0, 20),
        confluence_call("ported", 2, 18),
        jira_call("ported"),
        bitbucket_call("ported"),
    ]
    for detail in (
        SECRET_SENTINEL,
        CONFLUENCE_TOKEN,
        JIRA_TOKEN,
        BITBUCKET_TOKEN,
    ):
        assert detail not in result.stdout
