"""Installed-CLI loopback checks for Jira worklogs, changelog, and projects.

Every response comes from a synthetic loopback server, every credential is a
fixture, and ``BBK_CREDENTIALS`` points at a path that must not exist. No test
contacts a real instance or reads a real credential store.
"""

import json
import subprocess
from http.server import BaseHTTPRequestHandler
from pathlib import Path

import pytest

from tests._loopback import (
    Request,
    request_record,
    run_installed,
    send_bytes,
    send_json,
    serving,
)

TOKEN = "fixture-jira-issue-extra-cli-token"
CONTEXT = "/jira"
KEY = "DEMO-42"
SENTINEL = "JIRA-ISSUE-EXTRA-CLI-SENTINEL"
WORKLOG_PATH = f"{CONTEXT}/rest/api/2/issue/{KEY}/worklog"
ISSUE_PATH = f"{CONTEXT}/rest/api/2/issue/{KEY}"
PROJECTS_PATH = f"{CONTEXT}/rest/api/2/project"
MISSING_BBK_CREDENTIALS = str(
    Path(__file__).with_name("bbk-credentials-missing-for-extras.json")
)

WORKLOG_ROWS: list[dict[str, object]] = [
    {
        "self": f"https://pasted.example.invalid/rest/api/2/issue/{KEY}/worklog/20001",
        "author": {
            "name": "ada",
            "displayName": "Ada Lovelace",
            "active": True,
            "avatarUrls": {"48x48": "https://pasted.example.invalid/avatar/ada"},
            "pluginAuthor": {"nested": [None, 1]},
        },
        "updateAuthor": None,
        "comment": "Investigated the report. ✓",
        "created": None,
        "updated": "2023-04-05T06:07:08.000+0000",
        "visibility": {"type": "role", "value": "Developers"},
        "started": "2023-04-05T06:00:00.000+0000",
        "timeSpent": "1h 30m",
        "timeSpentSeconds": 5400,
        "id": "20001",
        "issueId": "20000",
        "pluginWorklogField": {"nested": [False, None]},
    },
    {
        "self": None,
        "author": None,
        "updateAuthor": None,
        "comment": None,
        "created": None,
        "updated": None,
        "visibility": None,
        "started": None,
        "timeSpent": None,
        "timeSpentSeconds": 0,
        "id": "20002",
        "issueId": "20000",
    },
]

WORKLOGS_DOC: dict[str, object] = {
    "startAt": 2,
    "maxResults": 2,
    "total": 7,
    "worklogs": WORKLOG_ROWS,
    "pluginDocumentField": {"capped": True, "nested": [None]},
}

HISTORIES: list[dict[str, object]] = [
    {
        "id": "30001",
        "author": {
            "name": "grace",
            "displayName": "Grace Hopper",
            "active": True,
            "pluginAuthor": {"nested": [2, None]},
        },
        "created": "2023-05-06T07:08:09.000+0000",
        "items": [
            {
                "field": "assignee",
                "fieldtype": "jira",
                "from": None,
                "fromString": None,
                "to": "JIRAUSER20000",
                "toString": "Ada Lovelace",
            }
        ],
        "historyMetadata": {
            "type": "issue-updated",
            "actor": {"id": "JIRAUSER20001", "displayName": "Grace"},
            "extraData": {"key": "value"},
        },
        "pluginHistoryField": {"nested": [None, 3]},
    },
    {
        "id": "30002",
        "author": None,
        "created": None,
        "items": [],
        "historyMetadata": None,
    },
]

CHANGELOG_DOC: dict[str, object] = {
    "startAt": 3,
    "maxResults": 2,
    "total": 8,
    "histories": HISTORIES,
    "pluginChangelogField": {"nested": [True, None]},
}

ISSUE_DOC: dict[str, object] = {
    "expand": "changelog",
    "id": "20000",
    "self": f"https://pasted.example.invalid/rest/api/2/issue/{KEY}",
    "key": KEY,
    "fields": {"summary": SENTINEL, "pluginIssueField": {"nested": [None]}},
    "changelog": CHANGELOG_DOC,
    "pluginIssueField": SENTINEL,
}

PROJECTS: list[dict[str, object]] = [
    {
        "self": "https://pasted.example.invalid/rest/api/2/project/EX",
        "id": "10000",
        "key": "EX",
        "name": "Example",
        "avatarUrls": {
            "48x48": "https://pasted.example.invalid/avatar?size=large",
            "16x16": None,
        },
        "projectCategory": {
            "self": "https://pasted.example.invalid/rest/api/2/projectCategory/10000",
            "id": "10000",
            "name": "FIRST",
            "description": "First Project Category",
        },
        "lead": {"name": "ada", "displayName": "Ada", "active": True},
        "components": [{"id": "10000", "name": "Component", "lead": None}],
        "issueTypes": [{"id": "1", "name": "Bug", "subtask": False}],
        "versions": [{"id": "10000", "name": "1.0", "released": True}],
        "pluginProjectField": {"nested": [None, 1]},
    },
    {
        "self": None,
        "id": "10001",
        "key": "ABC",
        "name": "Alphabetical",
        "description": None,
        "lead": None,
        "projectCategory": None,
        "avatarUrls": {},
        "archived": False,
    },
]

EXTRA_CASES: list[
    tuple[
        str,
        str,
        dict[str, list[str]],
        object,
        object,
        tuple[str, ...],
    ]
] = [
    (
        "issue-worklogs",
        WORKLOG_PATH,
        {},
        WORKLOGS_DOC,
        WORKLOGS_DOC,
        (KEY,),
    ),
    (
        "issue-changelog",
        ISSUE_PATH,
        {"expand": ["changelog"]},
        ISSUE_DOC,
        CHANGELOG_DOC,
        (KEY,),
    ),
    (
        "jira-projects",
        PROJECTS_PATH,
        {},
        PROJECTS,
        PROJECTS,
        (),
    ),
]


def environment(origin: str) -> dict[str, str]:
    """Point Jira at the loopback context and keep every other source inert."""
    return {
        "ATLAWIRE_JIRA_URL": f"{origin}{CONTEXT}/",
        "ATLAWIRE_JIRA_TOKEN": TOKEN,
        "ATLAWIRE_BITBUCKET_URL": f"{origin}/wrong-bitbucket/",
        "ATLAWIRE_BITBUCKET_TOKEN": "wrong-product-fixture",
        "ATLAWIRE_CONFLUENCE_URL": f"{origin}/wrong-confluence/",
        "ATLAWIRE_CONFLUENCE_TOKEN": "wrong-product-fixture",
        "BBK_CREDENTIALS": MISSING_BBK_CREDENTIALS,
    }


def run_extra(
    command: str,
    path: str,
    body: object,
    *,
    arguments: tuple[str, ...] = (),
    status: int = 200,
    location: str | None = None,
) -> tuple[
    subprocess.CompletedProcess[str],
    list[Request],
    list[str | None],
]:
    """Run one installed command against one synthetic response."""
    seen: list[Request] = []
    accepts: list[str | None] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            record = request_record(self)
            seen.append(record)
            accepts.append(self.headers.get("Accept"))
            _, request_path, _, authorization = record
            if request_path != path or authorization != f"Bearer {TOKEN}":
                send_json(self, 401, {"message": SENTINEL})
                return
            if location is not None:
                send_bytes(
                    self,
                    302,
                    b"",
                    content_type=None,
                    extra_headers={"Location": location},
                )
                return
            if status != 200:
                send_json(self, status, {"message": SENTINEL})
                return
            send_json(self, 200, body)

    with serving(Handler) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        result = run_installed(
            [
                command,
                *arguments,
                "--token-from-env",
                "--allow-http-loopback",
            ],
            environment(origin),
        )
    return result, seen, accepts


def expected_get(path: str, query: dict[str, list[str]]) -> list[Request]:
    return [("GET", path, query, f"Bearer {TOKEN}")]


@pytest.mark.parametrize(
    ("command", "path", "query", "body", "expected", "arguments"),
    EXTRA_CASES,
    ids=["worklogs", "changelog", "projects"],
)
def test_installed_extra_command_prints_the_documented_json(
    command: str,
    path: str,
    query: dict[str, list[str]],
    body: object,
    expected: object,
    arguments: tuple[str, ...],
) -> None:
    result, seen, accepts = run_extra(
        command, path, body, arguments=arguments
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == expected
    assert SENTINEL not in result.stdout
    assert TOKEN not in result.stdout
    assert seen == expected_get(path, query)
    assert accepts == ["application/json"]


def test_installed_worklogs_keep_capped_pagination_metadata_and_read_once() -> None:
    result, seen, accepts = run_extra(
        "issue-worklogs", WORKLOG_PATH, WORKLOGS_DOC, arguments=(KEY,)
    )

    assert result.returncode == 0, result.stderr
    document = json.loads(result.stdout)
    assert document["startAt"] == 2
    assert document["maxResults"] == 2
    assert document["total"] == 7
    assert len(document["worklogs"]) == 2
    assert document["total"] > len(document["worklogs"])
    assert len(seen) == 1
    assert accepts == ["application/json"]


def test_installed_changelog_keeps_capped_metadata_and_omits_issue_fields() -> None:
    result, seen, accepts = run_extra(
        "issue-changelog", ISSUE_PATH, ISSUE_DOC, arguments=(KEY,)
    )

    assert result.returncode == 0, result.stderr
    document = json.loads(result.stdout)
    assert document["startAt"] == 3
    assert document["maxResults"] == 2
    assert document["total"] == 8
    assert len(document["histories"]) == 2
    assert document["total"] > len(document["histories"])
    assert "fields" not in document
    assert "pluginIssueField" not in document
    assert len(seen) == 1
    assert accepts == ["application/json"]


@pytest.mark.parametrize(
    ("command", "path", "query", "body", "expected", "arguments"),
    EXTRA_CASES[:2],
    ids=["worklogs", "changelog"],
)
def test_installed_issue_extra_command_pins_a_foreign_pasted_url_to_the_server(
    command: str,
    path: str,
    query: dict[str, list[str]],
    body: object,
    expected: object,
    arguments: tuple[str, ...],
) -> None:
    pasted = f"https://pasted.example.invalid/jira/browse/{KEY}?tab=activity#top"

    result, seen, accepts = run_extra(
        command, path, body, arguments=(pasted,)
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == expected
    assert seen == expected_get(path, query)
    assert accepts == ["application/json"]


@pytest.mark.parametrize(
    ("command", "path", "query", "body", "expected", "arguments"),
    EXTRA_CASES[:2],
    ids=["worklogs", "changelog"],
)
@pytest.mark.parametrize(
    "argument",
    [
        "DEMO",
        "demo-42",
        "DEMO-42x",
        f"https://pasted.example.invalid/browse/{KEY}/extra",
        "https://pasted.example.invalid/secure/Dashboard.jspa",
    ],
)
def test_installed_issue_extra_command_rejects_an_unusable_key_without_a_request(
    command: str,
    path: str,
    query: dict[str, list[str]],
    body: object,
    expected: object,
    arguments: tuple[str, ...],
    argument: str,
) -> None:
    result, seen, accepts = run_extra(
        command, path, body, arguments=(argument,)
    )

    assert result.returncode != 0
    assert result.stdout == ""
    assert "issue key" in result.stderr
    assert TOKEN not in result.stderr
    assert seen == []
    assert accepts == []


@pytest.mark.parametrize(
    ("command", "path", "query", "body", "expected", "arguments"),
    EXTRA_CASES,
    ids=["worklogs", "changelog", "projects"],
)
def test_installed_extra_command_reports_authentication_rejection(
    command: str,
    path: str,
    query: dict[str, list[str]],
    body: object,
    expected: object,
    arguments: tuple[str, ...],
) -> None:
    result, seen, accepts = run_extra(
        command, path, body, arguments=arguments, status=401
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == "Error: HTTP 401: authentication rejected.\n"
    assert SENTINEL not in result.stderr
    assert TOKEN not in result.stderr
    assert seen == expected_get(path, query)
    assert accepts == ["application/json"]


@pytest.mark.parametrize(
    ("status", "message"),
    [
        (403, "HTTP 403: access denied."),
        (404, "HTTP 404: request failed."),
        (500, "HTTP 500: request failed."),
        (206, "HTTP 206: partial content is not supported."),
    ],
)
def test_installed_worklogs_map_http_errors(status: int, message: str) -> None:
    result, seen, _ = run_extra(
        "issue-worklogs",
        WORKLOG_PATH,
        WORKLOGS_DOC,
        arguments=(KEY,),
        status=status,
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == f"Error: {message}\n"
    assert SENTINEL not in result.stderr
    assert seen == expected_get(WORKLOG_PATH, {})


@pytest.mark.parametrize(
    ("command", "path", "query", "body", "expected", "arguments"),
    EXTRA_CASES,
    ids=["worklogs", "changelog", "projects"],
)
def test_installed_extra_command_refuses_a_redirect_without_following_it(
    command: str,
    path: str,
    query: dict[str, list[str]],
    body: object,
    expected: object,
    arguments: tuple[str, ...],
) -> None:
    honeypot: list[Request] = []

    class Honeypot(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            honeypot.append(request_record(self))
            send_json(self, 200, {"message": SENTINEL})

    with serving(Honeypot) as target:
        location = f"http://127.0.0.1:{target.server_port}/stolen"
        result, seen, _ = run_extra(
            command, path, body, arguments=arguments, location=location
        )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "redirect refused" in result.stderr
    assert SENTINEL not in result.stdout + result.stderr
    assert seen == expected_get(path, query)
    assert honeypot == []


@pytest.mark.parametrize(
    ("command", "path", "query", "body", "expected", "arguments"),
    EXTRA_CASES,
    ids=["worklogs", "changelog", "projects"],
)
def test_installed_extra_command_accepts_empty_content(
    command: str,
    path: str,
    query: dict[str, list[str]],
    body: object,
    expected: object,
    arguments: tuple[str, ...],
) -> None:
    if command == "jira-projects":
        empty_body: object = []
        empty_expected: object = []
    elif command == "issue-worklogs":
        empty_body = {**WORKLOGS_DOC, "worklogs": [], "total": 0}
        empty_expected = empty_body
    else:
        empty_doc = {**CHANGELOG_DOC, "histories": [], "total": 0}
        empty_body = {**ISSUE_DOC, "changelog": empty_doc}
        empty_expected = empty_doc

    result, seen, _ = run_extra(
        command, path, empty_body, arguments=arguments
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == empty_expected
    assert seen == expected_get(path, query)


@pytest.mark.parametrize(
    ("body", "diagnostic"),
    [
        ({"startAt": 0, "maxResults": 2, "total": 2}, "worklogs array"),
        ({"worklogs": "text"}, "worklogs array"),
    ],
    ids=["missing-worklogs", "non-list-worklogs"],
)
def test_installed_worklogs_reject_a_malformed_document(
    body: dict[str, object], diagnostic: str
) -> None:
    result, seen, _ = run_extra(
        "issue-worklogs", WORKLOG_PATH, body, arguments=(KEY,)
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert diagnostic in result.stderr
    assert SENTINEL not in result.stderr
    assert TOKEN not in result.stderr
    assert seen == expected_get(WORKLOG_PATH, {})


@pytest.mark.parametrize(
    ("body", "diagnostic"),
    [
        ({"key": KEY, "fields": {}}, "changelog document"),
        ({"changelog": []}, "changelog document"),
        ({"changelog": {}}, "histories array"),
        ({"changelog": {"histories": {}}}, "histories array"),
    ],
    ids=[
        "missing-changelog",
        "non-object-changelog",
        "missing-histories",
        "non-list-histories",
    ],
)
def test_installed_changelog_rejects_a_malformed_document(
    body: dict[str, object], diagnostic: str
) -> None:
    result, seen, _ = run_extra(
        "issue-changelog", ISSUE_PATH, body, arguments=(KEY,)
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert diagnostic in result.stderr
    assert SENTINEL not in result.stderr
    assert TOKEN not in result.stderr
    assert seen == expected_get(ISSUE_PATH, {"expand": ["changelog"]})


def test_installed_worklogs_discard_everything_for_a_malformed_late_row() -> None:
    body = {**WORKLOGS_DOC, "worklogs": [WORKLOG_ROWS[0], 7]}

    result, seen, _ = run_extra(
        "issue-worklogs", WORKLOG_PATH, body, arguments=(KEY,)
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "worklog objects" in result.stderr
    assert SENTINEL not in result.stderr
    assert TOKEN not in result.stderr
    assert "Traceback" not in result.stderr
    assert seen == expected_get(WORKLOG_PATH, {})


def test_installed_changelog_discards_everything_for_a_malformed_late_row() -> None:
    body = {
        **ISSUE_DOC,
        "changelog": {**CHANGELOG_DOC, "histories": [HISTORIES[0], 7]},
    }

    result, seen, _ = run_extra(
        "issue-changelog", ISSUE_PATH, body, arguments=(KEY,)
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "change history objects" in result.stderr
    assert SENTINEL not in result.stderr
    assert TOKEN not in result.stderr
    assert "Traceback" not in result.stderr
    assert seen == expected_get(ISSUE_PATH, {"expand": ["changelog"]})


def test_installed_projects_discard_everything_for_a_malformed_late_row() -> None:
    result, seen, _ = run_extra(
        "jira-projects", PROJECTS_PATH, [PROJECTS[0], 7]
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "project objects" in result.stderr
    assert SENTINEL not in result.stderr
    assert TOKEN not in result.stderr
    assert "Traceback" not in result.stderr
    assert seen == expected_get(PROJECTS_PATH, {})


@pytest.mark.parametrize(
    ("command", "path", "query", "body", "expected", "arguments"),
    [
        ("issue-worklogs", WORKLOG_PATH, {}, [], WORKLOGS_DOC, (KEY,)),
        (
            "issue-changelog",
            ISSUE_PATH,
            {"expand": ["changelog"]},
            [],
            ISSUE_DOC,
            (KEY,),
        ),
        ("jira-projects", PROJECTS_PATH, {}, {"values": PROJECTS}, PROJECTS, ()),
    ],
    ids=["worklogs", "changelog", "projects"],
)
def test_installed_extra_command_rejects_a_non_object_or_non_array_body(
    command: str,
    path: str,
    query: dict[str, list[str]],
    body: object,
    expected: object,
    arguments: tuple[str, ...],
) -> None:
    result, seen, _ = run_extra(command, path, body, arguments=arguments)

    assert result.returncode == 1
    assert result.stdout == ""
    assert "Expected a JSON" in result.stderr
    assert SENTINEL not in result.stderr
    assert seen == expected_get(path, query)


def test_the_bbk_credentials_override_is_a_missing_synthetic_path() -> None:
    assert "missing-for-extras" in MISSING_BBK_CREDENTIALS
    assert not Path(MISSING_BBK_CREDENTIALS).exists()
