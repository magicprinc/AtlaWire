"""Installed-CLI checks for the indexed Bitbucket code search."""

import json
import subprocess
from http.server import BaseHTTPRequestHandler
from typing import cast

import pytest

from tests._loopback import run_installed, send_json, serving

TOKEN = "fixture-search-token"
CONTEXT = "/scm/bitbucket"
SEARCH_PATH = f"{CONTEXT}/rest/search/latest/search"
Record = tuple[str, str, str | None, str | None, str | None, bytes]

MARKED_TEXT = "def <em>naïve</em>(x): &amp; &lt;em&gt;literal&lt;/em&gt;"
LITERAL_TEXT = "&lt;em&gt;literal&lt;/em&gt;"


def row(
    file: str,
    *,
    project: str = "P",
    slug: str = "r",
    hit_count: object = 1,
    contexts: object = ...,
) -> dict[str, object]:
    value: dict[str, object] = {
        "repository": {"project": {"key": project}, "slug": slug},
        "file": file,
    }
    if hit_count is not ...:
        value["hitCount"] = hit_count
    if contexts is not ...:
        value["hitContexts"] = contexts
    return value


SIMPLE_VALUES = [
    row("a.py", hit_count=2, contexts=[[{"line": 4, "text": MARKED_TEXT}]]),
    row("b.py", hit_count=..., contexts=[[{"line": 1, "text": LITERAL_TEXT}]]),
    row("c.py", hit_count=0),
]
SIMPLE_BODY = {"code": {"values": SIMPLE_VALUES, "isLastPage": False, "nextStart": 17}}
SIMPLE_EXPECTED = [
    {
        "project": "P",
        "repository": "r",
        "file": "a.py",
        "hitCount": 2,
        "matchEvidence": "highlight",
        "hits": [{"line": 4, "text": "def naïve(x): & <em>literal</em>"}],
        "context": [[{"line": 4, "text": "def naïve(x): & <em>literal</em>"}]],
    },
    {
        "project": "P",
        "repository": "r",
        "file": "b.py",
        "hitCount": None,
        "matchEvidence": "context-only",
        "hits": [],
        "context": [[{"line": 1, "text": "<em>literal</em>"}]],
    },
    {
        "project": "P",
        "repository": "r",
        "file": "c.py",
        "hitCount": 0,
        "matchEvidence": "none",
        "hits": [],
        "context": [],
    },
]
FIRST_PAGE = {
    "code": {
        "values": [
            row("a.py", contexts=[[{"line": 1, "text": "<em>a</em>"}]]),
            row("b.py"),
        ],
        "isLastPage": False,
        "nextStart": 17,
    }
}
LAST_PAGE = {
    "code": {
        "values": [row("c.py", contexts=[[{"line": 2, "text": "<em>c</em>"}]])],
        "isLastPage": True,
    }
}
MALFORMED_TEXT = "&#" + "9" * 5000 + ";"
MALFORMED_BODY = {
    "code": {
        "values": [
            row("a.py", contexts=[[{"line": 1, "text": "<em>ok</em>"}]]),
            row("b.py", contexts=[[{"line": 2, "text": MALFORMED_TEXT}]]),
        ],
        "isLastPage": True,
    }
}
PLAIN_BODY = {
    "code": {
        "values": [
            row(
                "a.py",
                contexts=[
                    [
                        {
                            "line": 2,
                            "text": "\u001b[31m<em>danger</em>\n\u0007 &amp; next",
                        }
                    ]
                ],
            ),
            row("b.py", hit_count=..., contexts=[[{"line": 3, "text": LITERAL_TEXT}]]),
            row("c.py", hit_count=0),
        ],
        "isLastPage": True,
    }
}


def secret_error() -> dict[str, object]:
    return {
        "message": TOKEN,
        "path": SEARCH_PATH,
        "query": "fixture-query",
        "response": "RESPONSE-SENTINEL",
    }


def start_of(body: dict[str, object]) -> int:
    entities = cast(dict[str, object], body["entities"])
    code = cast(dict[str, object], entities["code"])
    return cast(int, code["start"])


def responder(scenario: str, body: dict[str, object]) -> tuple[int, object]:
    start = start_of(body)
    if scenario == "simple":
        return 200, SIMPLE_BODY
    if scenario == "plain":
        return 200, PLAIN_BODY
    if scenario == "malformed-line":
        return 200, MALFORMED_BODY
    if scenario == "wrong-scope":
        return 200, {
            "code": {
                "values": [row("a.py", project="Q")],
                "isLastPage": True,
            }
        }
    if start == 0:
        return 200, FIRST_PAGE
    if scenario == "second-error":
        return 503, secret_error()
    if scenario == "second-bad-cursor":
        return 200, {
            "code": {
                "values": [row("c.py")],
                "isLastPage": False,
                "nextStart": 17,
            }
        }
    return 200, LAST_PAGE


def run_search(
    scenario: str, *arguments: str
) -> tuple[subprocess.CompletedProcess[str], list[Record]]:
    seen: list[Record] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length)
            seen.append(
                (
                    self.command,
                    self.path,
                    self.headers.get("Content-Type"),
                    self.headers.get("Accept"),
                    self.headers.get("Authorization"),
                    raw,
                )
            )
            body = json.loads(raw)
            status, payload = responder(scenario, body)
            send_json(self, status, payload)

        def do_GET(self) -> None:
            seen.append((self.command, self.path, None, None, None, b""))
            send_json(self, 400, {"unexpected": "GET"})

    with serving(Handler) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        result = run_installed(
            ["search", *arguments, "--allow-http-loopback", "--token-from-env"],
            {
                "ATLAWIRE_BITBUCKET_URL": f"{origin}{CONTEXT}/",
                "ATLAWIRE_BITBUCKET_TOKEN": TOKEN,
                "ATLAWIRE_JIRA_URL": f"{origin}/wrong-jira/",
                "ATLAWIRE_JIRA_TOKEN": "wrong-product-jira",
                "ATLAWIRE_CONFLUENCE_URL": f"{origin}/wrong-confluence/",
                "ATLAWIRE_CONFLUENCE_TOKEN": "wrong-product-confluence",
            },
        )
    return result, seen


def test_search_json_posts_once_with_exact_scope_query_and_evidence() -> None:
    result, seen = run_search("simple", "naïve", "--repo", "P/r", "--json")

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == SIMPLE_EXPECTED
    assert len(seen) == 1
    method, path, content_type, accept, authorization, raw = seen[0]
    assert method == "POST"
    assert path == SEARCH_PATH
    assert content_type == "application/json"
    assert accept == "application/json"
    assert authorization == f"Bearer {TOKEN}"
    assert json.loads(raw) == {
        "query": "project:P repo:r naïve",
        "entities": {"code": {"start": 0, "limit": 20}},
    }


@pytest.mark.parametrize(
    ("options", "bodies"),
    [
        (
            ("--all",),
            [
                {"query": "needle", "entities": {"code": {"start": 0, "limit": 100}}},
                {"query": "needle", "entities": {"code": {"start": 17, "limit": 100}}},
            ],
        ),
        (
            ("--project", "P", "--all", "--limit", "5"),
            [
                {
                    "query": "project:P needle",
                    "entities": {"code": {"start": 0, "limit": 5}},
                },
                {
                    "query": "project:P needle",
                    "entities": {"code": {"start": 17, "limit": 3}},
                },
            ],
        ),
    ],
    ids=["default-full-cap", "explicit-remaining-window"],
)
def test_search_all_follows_a_noncontiguous_cursor(
    options: tuple[str, ...], bodies: list[dict[str, object]]
) -> None:
    result, seen = run_search("two-pages", "needle", *options, "--json")

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert [json.loads(raw) for *_, raw in seen] == bodies
    assert [item["file"] for item in json.loads(result.stdout)] == [
        "a.py",
        "b.py",
        "c.py",
    ]


@pytest.mark.parametrize(
    ("scenario", "message"),
    [
        ("second-error", "HTTP 503"),
        ("second-bad-cursor", "nextStart"),
    ],
    ids=["later-http-error", "later-bad-cursor"],
)
def test_search_all_late_failures_print_nothing_and_hide_details(
    scenario: str, message: str
) -> None:
    result, seen = run_search(
        scenario, "needle", "--project", "P", "--all", "--limit", "5"
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert message in result.stderr
    assert [start_of(json.loads(raw)) for *_, raw in seen] == [0, 17]
    for detail in (TOKEN, SEARCH_PATH, "fixture-query", "RESPONSE-SENTINEL", "needle"):
        assert detail not in result.stderr


@pytest.mark.parametrize(
    ("arguments", "code"),
    [
        (("q", "--project", "A", "--repo", "A/r"), 2),
        (("q", "--project", "../A"), 1),
        (("q", "--repo", "A/.."), 1),
    ],
    ids=["both-scopes", "invalid-project", "invalid-repo"],
)
def test_invalid_scope_is_rejected_without_http(
    arguments: tuple[str, ...], code: int
) -> None:
    result, seen = run_search("simple", *arguments, "--json")

    assert result.returncode == code
    assert result.stdout == ""
    assert seen == []
    assert TOKEN not in result.stderr


def test_search_malformed_line_after_a_valid_result_publishes_nothing() -> None:
    result, seen = run_search("malformed-line", "needle", "--json")

    assert result.returncode == 1
    assert result.stdout == ""
    assert len(seen) == 1
    method, path, _, _, _, _ = seen[0]
    assert method == "POST"
    assert path == SEARCH_PATH
    assert result.stderr == (
        "Error: Invalid character reference in a Bitbucket search result.\n"
    )
    assert "Traceback" not in result.stderr
    for detail in (TOKEN, SEARCH_PATH, "needle", "RESPONSE-SENTINEL"):
        assert detail not in result.stderr


def test_a_server_row_outside_the_requested_scope_is_rejected() -> None:
    result, seen = run_search("wrong-scope", "q", "--project", "A", "--json")

    assert result.returncode == 1
    assert result.stdout == ""
    assert len(seen) == 1
    assert "outside the requested scope" in result.stderr
    for detail in (TOKEN, SEARCH_PATH):
        assert detail not in result.stderr


def test_plain_summary_labels_evidence_and_escapes_terminal_controls() -> None:
    result, seen = run_search("plain", "needle")

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert len(seen) == 1
    assert result.stdout == (
        "# 3 file(s) (first page only; use --all for every page)\n"
        "P/r:a.py (1 hits) highlighted L2: \\x1b[31mdanger \\x07 & next\n"
        "P/r:b.py (unknown hits) context L3: <em>literal</em>\n"
        "P/r:c.py (0 hits) no context\n"
    )
    assert "\x1b" not in result.stdout
    assert "\x07" not in result.stdout
    assert "<em>danger" not in result.stdout
