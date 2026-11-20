"""Installed-CLI checks for the visible-project repository search walk."""

import json
import subprocess
from http.server import BaseHTTPRequestHandler

import pytest

from tests._loopback import Request, request_record, run_installed, send_json, serving

TOKEN = "fixture-find-repos"
CONTEXT = "/scm/bitbucket"
PROJECTS_PATH = f"{CONTEXT}/rest/api/1.0/projects"
ALPHA_PATH = f"{PROJECTS_PATH}/ALPHA/repos"
BETA_PATH = f"{PROJECTS_PATH}/BETA/repos"
ALPHA_ROWS = [
    {"slug": "widgets", "name": "Widgets UI", "state": "AVAILABLE"},
    {"slug": "tools", "name": "Widget Utilities", "state": "AVAILABLE"},
    {"slug": "other", "name": "Nope", "state": "AVAILABLE"},
    {"slug": "WIDGET-core", "name": None, "state": None},
]


def fixture(scenario: str, path: str, start: int) -> tuple[int, dict[str, object]]:
    if path == PROJECTS_PATH and start == 0:
        return 200, {"values": [{"key": "ALPHA"}, {"key": "BETA"}], "isLastPage": True}
    if path == ALPHA_PATH:
        if scenario == "second-page" and start == 0:
            return 200, {
                "values": [{"slug": "match", "name": "Match"}],
                "isLastPage": False,
                "nextPageStart": 5,
            }
        if scenario == "second-page":
            return 503, secret_error()
        if scenario == "later-project":
            return 200, {
                "values": [{"slug": "match", "name": "Match", "state": "AVAILABLE"}],
                "isLastPage": True,
            }
        return 200, {"values": ALPHA_ROWS, "isLastPage": True}
    if path == BETA_PATH:
        if scenario == "later-project":
            return 503, secret_error()
        return 200, {"values": [{"slug": "widget-beta"}], "isLastPage": True}
    return 400, {"unexpected": [path, start]}


def secret_error() -> dict[str, object]:
    return {
        "message": TOKEN,
        "path": PROJECTS_PATH,
        "query": "fixture-query",
        "response": "RESPONSE-SENTINEL",
    }


def run_find(
    scenario: str, name: str, *options: str
) -> tuple[subprocess.CompletedProcess[str], list[Request]]:
    seen: list[Request] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            record = request_record(self)
            seen.append(record)
            start = int(record[2].get("start", ["-1"])[0])
            status, body = fixture(scenario, record[1], start)
            send_json(self, status, body)

    with serving(Handler) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        result = run_installed(
            [
                "find-repos",
                name,
                "--allow-http-loopback",
                "--token-from-env",
                *options,
            ],
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


def expected(starts: list[tuple[str, int]]) -> list[Request]:
    return [
        ("GET", path, {"start": [str(start)], "limit": ["100"]}, f"Bearer {TOKEN}")
        for path, start in starts
    ]


def test_find_repos_tsv_keeps_legacy_order_and_stops_at_the_exact_cap() -> None:
    result, seen = run_find("cap", "WiDgEt", "--limit", "2")

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout == (
        "# 2 row(s)\nproject\tslug\tname\tstate\n"
        "ALPHA\twidgets\tWidgets UI\tAVAILABLE\n"
        "ALPHA\ttools\tWidget Utilities\tAVAILABLE\n"
    )
    assert seen == expected([(PROJECTS_PATH, 0), (ALPHA_PATH, 0)])


def test_find_repos_json_projects_slug_name_matches_without_extra_fields() -> None:
    result, seen = run_find("cap", "widget", "--json", "--limit", "3")

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == [
        {
            "project": "ALPHA",
            "slug": "widgets",
            "name": "Widgets UI",
            "state": "AVAILABLE",
        },
        {
            "project": "ALPHA",
            "slug": "tools",
            "name": "Widget Utilities",
            "state": "AVAILABLE",
        },
        {"project": "ALPHA", "slug": "WIDGET-core", "name": None, "state": None},
    ]
    assert seen == expected([(PROJECTS_PATH, 0), (ALPHA_PATH, 0)])


@pytest.mark.parametrize(
    ("scenario", "starts"),
    [
        ("later-project", [(PROJECTS_PATH, 0), (ALPHA_PATH, 0), (BETA_PATH, 0)]),
        ("second-page", [(PROJECTS_PATH, 0), (ALPHA_PATH, 0), (ALPHA_PATH, 5)]),
    ],
    ids=["later-project", "second-repository-page"],
)
def test_find_repos_late_failures_publish_nothing_and_hide_request_details(
    scenario: str, starts: list[tuple[str, int]]
) -> None:
    result, seen = run_find(scenario, "match")

    assert result.returncode == 1
    assert result.stdout == ""
    assert "HTTP 503" in result.stderr
    for detail in (TOKEN, PROJECTS_PATH, "fixture-query", "RESPONSE-SENTINEL"):
        assert detail not in result.stderr
    assert seen == expected(starts)
