"""Installed-CLI loopback checks for Jira reference reads and user search.

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

TOKEN = "fixture-jira-reference-cli-token"
CONTEXT = "/jira"
USER_PATH = f"{CONTEXT}/rest/api/2/user/search"
SENTINEL = "JIRA-REFERENCE-CLI-SENTINEL"
MISSING_BBK_CREDENTIALS = str(
    Path(__file__).with_name("bbk-credentials-missing-for-tests.json")
)

PRIORITIES: list[dict[str, object]] = [
    {
        "self": "https://pasted.example.invalid/rest/api/2/priority/1",
        "statusColor": "#ff0000",
        "description": "Blocks work.",
        "iconUrl": "https://pasted.example.invalid/icons/blocker.png",
        "name": "Blocker",
        "id": "1",
        "cliUnknown": {"nested": [None, True, 2.5]},
    },
    {
        "self": None,
        "statusColor": None,
        "description": None,
        "iconUrl": None,
        "name": "Minor",
        "id": "4",
    },
]

RESOLUTIONS: list[dict[str, object]] = [
    {
        "self": "https://pasted.example.invalid/rest/api/2/resolution/1",
        "description": "Fixed in a build.",
        "iconUrl": "https://pasted.example.invalid/icons/fixed.png",
        "name": "Fixed",
        "id": "1",
        "cliUnknown": {"order": [1, None]},
    },
    {
        "self": None,
        "description": None,
        "iconUrl": None,
        "name": "Won't Fix",
        "id": "2",
    },
]

ISSUE_TYPES: list[dict[str, object]] = [
    {
        "self": "https://pasted.example.invalid/rest/api/2/issueType/1",
        "id": "1",
        "description": "A problem with the software.",
        "iconUrl": "https://pasted.example.invalid/icons/bug.png",
        "name": "Bug",
        "subtask": False,
        "avatarId": 10002,
        "cliUnknown": {"nested": {"level": 0}},
    },
    {
        "self": None,
        "id": "5",
        "description": None,
        "iconUrl": None,
        "name": "Sub-task",
        "subtask": True,
        "avatarId": 10003,
    },
]

STATUS_CATEGORIES: list[dict[str, object]] = [
    {
        "self": "https://pasted.example.invalid/rest/api/2/statuscategory/2",
        "id": 2,
        "key": "new",
        "colorName": "blue-gray",
        "name": "To Do",
        "cliUnknown": {"nested": [None, False]},
    },
    {
        "self": None,
        "id": 3,
        "key": "undefined",
        "colorName": None,
        "name": None,
    },
]

USERS: list[dict[str, object]] = [
    {
        "self": "https://pasted.example.invalid/rest/api/2/user?username=ada",
        "key": "JIRAUSER20000",
        "name": "ada",
        "emailAddress": "ada@example.invalid",
        "avatarUrls": {
            "48x48": "https://pasted.example.invalid/avatar/ada",
            "16x16": None,
        },
        "displayName": "Ada Lovelace",
        "active": True,
        "deleted": False,
        "timeZone": "Europe/London",
        "locale": "en_UK",
        "groups": {"size": 1, "items": [{"name": "jira-users", "self": None}]},
        "cliUnknown": [1, None, {"nested": True}],
    },
    {
        "self": None,
        "key": None,
        "name": "grace",
        "emailAddress": None,
        "avatarUrls": {},
        "displayName": "Grace Hopper",
        "active": False,
        "deleted": False,
    },
]

REFERENCE_CASES: list[
    tuple[str, str, list[dict[str, object]], str]
] = [
    ("jira-priorities", f"{CONTEXT}/rest/api/2/priority", PRIORITIES, "priority"),
    ("jira-resolutions", f"{CONTEXT}/rest/api/2/resolution", RESOLUTIONS, "resolution"),
    ("jira-issue-types", f"{CONTEXT}/rest/api/2/issuetype", ISSUE_TYPES, "issue type"),
    (
        "jira-status-categories",
        f"{CONTEXT}/rest/api/2/statuscategory",
        STATUS_CATEGORIES,
        "status category",
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


def run_reference(
    command: str,
    path: str,
    body: object,
    *,
    status: int = 200,
    location: str | None = None,
    extra_args: tuple[str, ...] = (),
) -> tuple[
    subprocess.CompletedProcess[str],
    list[Request],
    list[str | None],
    list[str],
]:
    """Run one installed command against one synthetic response."""
    seen: list[Request] = []
    accepts: list[str | None] = []
    raw_paths: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            record = request_record(self)
            seen.append(record)
            accepts.append(self.headers.get("Accept"))
            raw_paths.append(self.path)
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
                "--token-from-env",
                "--allow-http-loopback",
                *extra_args,
            ],
            environment(origin),
        )
    return result, seen, accepts, raw_paths


def expected_get(path: str) -> list[Request]:
    return [("GET", path, {}, f"Bearer {TOKEN}")]


@pytest.mark.parametrize(
    ("command", "path", "payload", "label"),
    REFERENCE_CASES,
    ids=["priorities", "resolutions", "issue-types", "status-categories"],
)
def test_installed_reference_command_prints_complete_json_array(
    command: str,
    path: str,
    payload: list[dict[str, object]],
    label: str,
) -> None:
    result, seen, accepts, _ = run_reference(command, path, payload)

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == payload
    assert SENTINEL not in result.stdout
    assert TOKEN not in result.stdout
    assert seen == expected_get(path)
    assert accepts == ["application/json"]
    # Field completeness and nested values are asserted independently of the
    # adapter: a projection would lose the unknown key or the nulls.
    assert list(json.loads(result.stdout)[0]) == list(payload[0])
    assert "cliUnknown" in json.loads(result.stdout)[0]


@pytest.mark.parametrize(
    ("command", "path", "payload", "label"),
    REFERENCE_CASES,
    ids=["priorities", "resolutions", "issue-types", "status-categories"],
)
def test_installed_reference_command_accepts_an_empty_array(
    command: str,
    path: str,
    payload: list[dict[str, object]],
    label: str,
) -> None:
    result, seen, accepts, _ = run_reference(command, path, [])

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == []
    assert seen == expected_get(path)
    assert accepts == ["application/json"]


@pytest.mark.parametrize(
    ("command", "path", "payload", "label"),
    REFERENCE_CASES,
    ids=["priorities", "resolutions", "issue-types", "status-categories"],
)
def test_installed_reference_command_discards_everything_for_a_malformed_late_row(
    command: str,
    path: str,
    payload: list[dict[str, object]],
    label: str,
) -> None:
    result, seen, accepts, _ = run_reference(
        command, path, [payload[0], 7]
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert f"{label} objects" in result.stderr
    assert SENTINEL not in result.stderr
    assert TOKEN not in result.stderr
    assert "Traceback" not in result.stderr
    assert seen == expected_get(path)
    assert accepts == ["application/json"]


@pytest.mark.parametrize(
    ("command", "path", "payload", "label"),
    REFERENCE_CASES,
    ids=["priorities", "resolutions", "issue-types", "status-categories"],
)
def test_installed_reference_command_rejects_a_non_array_body(
    command: str,
    path: str,
    payload: list[dict[str, object]],
    label: str,
) -> None:
    result, seen, accepts, _ = run_reference(
        command, path, {"values": payload}
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "JSON array" in result.stderr
    assert SENTINEL not in result.stderr
    assert TOKEN not in result.stderr
    assert seen == expected_get(path)
    assert accepts == ["application/json"]


@pytest.mark.parametrize(
    ("command", "path", "payload", "label"),
    REFERENCE_CASES,
    ids=["priorities", "resolutions", "issue-types", "status-categories"],
)
def test_installed_reference_command_reports_authentication_rejection(
    command: str,
    path: str,
    payload: list[dict[str, object]],
    label: str,
) -> None:
    result, seen, accepts, _ = run_reference(command, path, payload, status=401)

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == "Error: HTTP 401: authentication rejected.\n"
    assert SENTINEL not in result.stderr
    assert TOKEN not in result.stderr
    assert seen == expected_get(path)
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
def test_installed_reference_command_maps_http_errors(
    status: int, message: str
) -> None:
    command, path, payload, _ = REFERENCE_CASES[0]

    result, seen, _, _ = run_reference(command, path, payload, status=status)

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == f"Error: {message}\n"
    assert SENTINEL not in result.stderr
    assert seen == expected_get(path)


def test_installed_reference_command_refuses_a_redirect_without_following_it() -> None:
    command, path, payload, _ = REFERENCE_CASES[0]
    honeypot: list[Request] = []

    class Honeypot(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            honeypot.append(request_record(self))
            send_json(self, 200, {"message": SENTINEL})

    with serving(Honeypot) as target:
        location = (
            f"http://127.0.0.1:{target.server_port}/stolen"
        )
        result, seen, _, _ = run_reference(
            command, path, payload, location=location
        )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "redirect refused" in result.stderr
    assert SENTINEL not in result.stdout + result.stderr
    assert seen == expected_get(path)
    assert honeypot == []


def run_users(
    body: object,
    *,
    query: str = "ada",
    extra_args: tuple[str, ...] = (),
    status: int = 200,
) -> tuple[
    subprocess.CompletedProcess[str],
    list[Request],
    list[str | None],
    list[str],
]:
    return run_reference(
        "jira-users",
        USER_PATH,
        body,
        status=status,
        extra_args=(query, *extra_args),
    )


def expected_user_request(start_at: int, max_results: int) -> list[Request]:
    return [
        (
            "GET",
            USER_PATH,
            {
                "username": ["ada"],
                "startAt": [str(start_at)],
                "maxResults": [str(max_results)],
            },
            f"Bearer {TOKEN}",
        )
    ]


def test_installed_jira_users_prints_one_page_and_sends_documented_parameters() -> None:
    result, seen, accepts, _ = run_users(
        USERS, query="Ada Lovelace", extra_args=("--start-at", "5", "--limit", "25")
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == USERS
    assert SENTINEL not in result.stdout
    assert TOKEN not in result.stdout
    assert seen == [
        (
            "GET",
            USER_PATH,
            {
                "username": ["Ada Lovelace"],
                "startAt": ["5"],
                "maxResults": ["25"],
            },
            f"Bearer {TOKEN}",
        )
    ]
    assert accepts == ["application/json"]
    assert list(json.loads(result.stdout)[0]) == list(USERS[0])


def test_installed_jira_users_uses_documented_defaults_when_flags_are_omitted() -> None:
    result, seen, _, _ = run_users(USERS)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == USERS
    assert seen == expected_user_request(0, 50)


@pytest.mark.parametrize("start_at", [0, 7])
def test_installed_jira_users_accepts_an_explicit_non_negative_start(
    start_at: int,
) -> None:
    result, seen, _, _ = run_users(
        USERS, extra_args=("--start-at", str(start_at))
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == USERS
    assert seen == expected_user_request(start_at, 50)


@pytest.mark.parametrize(
    ("limit", "payload"),
    [(1, USERS[:1]), (1000, USERS)],
    ids=["minimum", "maximum"],
)
def test_installed_jira_users_accepts_the_result_limit_bounds(
    limit: int, payload: list[dict[str, object]]
) -> None:
    result, seen, _, _ = run_users(
        payload, extra_args=("--limit", str(limit))
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == payload
    assert seen == expected_user_request(0, limit)


def test_installed_jira_users_percent_encodes_non_ascii_query_text() -> None:
    result, seen, _, raw_paths = run_users(USERS, query="Бета ✓")

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == USERS
    assert seen == [
        (
            "GET",
            USER_PATH,
            {
                "username": ["Бета ✓"],
                "startAt": ["0"],
                "maxResults": ["50"],
            },
            f"Bearer {TOKEN}",
        )
    ]
    assert "username=%D0%91" in raw_paths[0]
    assert "%E2%9C%93" in raw_paths[0]


def test_installed_jira_users_does_not_request_another_full_page() -> None:
    page = [USERS[0], USERS[1]]

    result, seen, _, _ = run_users(page, extra_args=("--limit", "2"))

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == page
    assert len(seen) == 1
    assert seen == expected_user_request(0, 2)


def test_installed_jira_users_rejects_a_page_longer_than_the_requested_limit() -> None:
    result, seen, accepts, _ = run_users(USERS, extra_args=("--limit", "1"))

    assert result.returncode == 1
    assert result.stdout == ""
    assert "more users than maxResults" in result.stderr
    assert SENTINEL not in result.stderr
    assert TOKEN not in result.stderr
    assert "Traceback" not in result.stderr
    assert seen == expected_user_request(0, 1)
    assert accepts == ["application/json"]


def test_installed_jira_users_accepts_an_empty_page() -> None:
    result, seen, _, _ = run_users([])

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == []
    assert seen == expected_user_request(0, 50)


def test_installed_jira_users_discards_everything_for_a_malformed_late_row() -> None:
    result, seen, _, _ = run_users([USERS[0], "not-a-user"])

    assert result.returncode == 1
    assert result.stdout == ""
    assert "user objects" in result.stderr
    assert SENTINEL not in result.stderr
    assert TOKEN not in result.stderr
    assert "Traceback" not in result.stderr
    assert seen == expected_user_request(0, 50)


def test_installed_jira_users_rejects_a_non_array_body() -> None:
    result, seen, _, _ = run_users({"values": USERS})

    assert result.returncode == 1
    assert result.stdout == ""
    assert "JSON array" in result.stderr
    assert SENTINEL not in result.stderr
    assert seen == expected_user_request(0, 50)


def test_installed_jira_users_reports_authentication_rejection() -> None:
    result, seen, _, _ = run_users(USERS, status=401)

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == "Error: HTTP 401: authentication rejected.\n"
    assert SENTINEL not in result.stderr
    assert seen == expected_user_request(0, 50)


@pytest.mark.parametrize(
    "extra_args",
    [
        (),
        ("--start-at", "-1"),
        ("--limit", "0"),
        ("--limit", "1001"),
    ],
    ids=["blank-query", "negative-start", "zero-limit", "too-large-limit"],
)
def test_installed_jira_users_rejects_unusable_input_without_a_request(
    extra_args: tuple[str, ...],
) -> None:
    query = "   " if not extra_args else "ada"

    result, seen, accepts, _ = run_users(
        USERS, query=query, extra_args=extra_args
    )

    assert result.returncode != 0
    assert result.stdout == ""
    assert seen == []
    assert accepts == []
    assert TOKEN not in result.stderr
    assert "Traceback" not in result.stderr


def test_installed_jira_users_rejects_an_empty_query_without_a_request() -> None:
    result, seen, accepts, _ = run_users(USERS, query="")

    assert result.returncode != 0
    assert result.stdout == ""
    assert seen == []
    assert accepts == []
    assert TOKEN not in result.stderr
    assert "Traceback" not in result.stderr


def test_the_bbk_credentials_override_is_a_missing_synthetic_path() -> None:
    assert "missing-for-tests" in MISSING_BBK_CREDENTIALS
    assert not Path(MISSING_BBK_CREDENTIALS).exists()
