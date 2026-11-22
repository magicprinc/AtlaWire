"""Installed-CLI loopback checks for author-wide Jira comment discovery.

The command is expected to be wired as ``jira-author-comments`` over
:func:`atlawire.jira_comments_search.find_author_comments`. Every response comes
from a synthetic loopback server, every credential is a fixture, and
``BBK_CREDENTIALS`` points at a path that must not exist.
"""

from __future__ import annotations

import json
import subprocess
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from tests._loopback import (
    Request,
    request_record,
    run_installed,
    send_bytes,
    send_json,
    serving,
)

TOKEN = "fixture-jira-author-comments-cli-token"
CONTEXT = "/jira"
USER = "ada"
DISPLAY = "Ada Lovelace"
SENTINEL = "JIRA-AUTHOR-COMMENTS-CLI-SENTINEL"
USER_PATH = f"{CONTEXT}/rest/api/2/user/search"
MYSELF_PATH = f"{CONTEXT}/rest/api/2/myself"
SEARCH_PATH = f"{CONTEXT}/rest/api/2/search"
COMMENT_PATH = f"{CONTEXT}/rest/api/2/issue/DEMO-1/comment"
MISSING_BBK_CREDENTIALS = str(
    Path(__file__).with_name("bbk-credentials-missing-for-author-comments.json")
)


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


class State:
    """Serve user, search, and comment responses and record every request."""

    def __init__(
        self,
        *,
        users: dict[str, list[dict[str, object]]] | None = None,
        user_pages: dict[str, dict[int, list[dict[str, object]]]] | None = None,
        current: dict[str, object] | None = None,
        search: dict[int, object] | None = None,
        threads: dict[str, dict[int, object]] | None = None,
    ) -> None:
        self.users = users if users is not None else {}
        self.user_pages = user_pages if user_pages is not None else {}
        self.current = current
        self.search = search if search is not None else {}
        self.threads = threads if threads is not None else {}
        self.redirects: dict[str, str] = {}
        self.seen: list[Request] = []
        self.accepts: list[str | None] = []

    def handle(self, handler: BaseHTTPRequestHandler) -> None:
        record = request_record(handler)
        self.seen.append(record)
        self.accepts.append(handler.headers.get("Accept"))
        _, path, query, authorization = record
        if authorization != f"Bearer {TOKEN}":
            send_json(handler, 401, {"message": SENTINEL})
            return
        location = self.redirects.get(path)
        if location is not None:
            send_bytes(
                handler,
                302,
                b"",
                content_type=None,
                extra_headers={"Location": location},
            )
            return
        if path == MYSELF_PATH:
            if self.current is None:
                send_json(handler, 404, {"message": SENTINEL})
            else:
                send_json(handler, 200, self.current)
            return
        if path == USER_PATH:
            username = query.get("username", [""])[0]
            start = int(query.get("startAt", ["0"])[0])
            if username in self.user_pages:
                rows = self.user_pages[username].get(start, [])
            elif start == 0:
                rows = self.users.get(username, [])
            else:
                rows = []
            send_json(handler, 200, rows)
            return
        if path == SEARCH_PATH:
            start = int(query.get("startAt", ["0"])[0])
            self._respond(handler, self.search, start)
            return
        prefix = f"{CONTEXT}/rest/api/2/issue/"
        if path.startswith(prefix) and path.endswith("/comment"):
            key = path[len(prefix) : -len("/comment")]
            start = int(query.get("startAt", ["0"])[0])
            self._respond(handler, self.threads.get(key, {}), start)
            return
        send_json(handler, 404, {"message": SENTINEL})

    @staticmethod
    def _respond(
        handler: BaseHTTPRequestHandler, pages: dict[int, object], start: int
    ) -> None:
        value = pages.get(start)
        if value is None:
            send_json(handler, 404, {"message": SENTINEL})
            return
        if isinstance(value, int):
            send_json(handler, value, {"message": SENTINEL})
            return
        send_json(handler, 200, value)


def user_row(name: str = USER, display: str = DISPLAY) -> dict[str, object]:
    return {"name": name, "displayName": display}


def comment(
    cid: str,
    *,
    author: str = USER,
    created: str = "2026-11-05T10:00:00.000+0300",
    body: str = "text",
) -> dict[str, object]:
    return {
        "id": cid,
        "author": {"name": author},
        "created": created,
        "body": body,
    }


def issue(
    *,
    key: str = "DEMO-1",
    summary: str = "Fix the parser",
    comments: list[dict[str, object]],
    total: int,
    updated: str = "2026-11-06T10:00:00.000+0300",
) -> dict[str, object]:
    return {
        "key": key,
        "fields": {
            "summary": summary,
            "updated": updated,
            "comment": {
                "comments": comments,
                "total": total,
                "maxResults": len(comments),
            },
        },
    }


def search_page(
    issues: list[object],
    *,
    start: int = 0,
    total: int = 0,
    max_results: int = 100,
    is_last: bool = True,
) -> dict[str, object]:
    return {
        "startAt": start,
        "maxResults": max_results,
        "total": total,
        "issues": issues,
        "isLast": is_last,
    }


def thread_page(
    comments: list[object],
    *,
    start: int = 0,
    total: int = 0,
    max_results: int = 100,
) -> dict[str, object]:
    return {
        "startAt": start,
        "maxResults": max_results,
        "total": total,
        "comments": comments,
    }


def run_cli(
    state: State, *arguments: str, user: str | None = USER
) -> tuple[subprocess.CompletedProcess[str], list[Request], list[str | None], str]:
    """Run the expected command against one synthetic loopback server."""
    command = ["jira-author-comments"]
    if user is not None:
        command.append(user)
    command.extend([*arguments, "--token-from-env", "--allow-http-loopback"])

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            state.handle(self)

    with serving(Handler) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        result = run_installed(command, environment(origin))
    return result, state.seen, state.accepts, origin


def request(
    path: str, query: dict[str, list[str]]
) -> Request:
    return ("GET", path, query, f"Bearer {TOKEN}")


def test_installed_author_comments_completes_a_truncated_thread() -> None:
    other = comment(
        "2001",
        author="grace",
        created="2026-11-04T10:00:00.000+0300",
        body="context",
    )
    target = comment(
        "2002",
        created="2026-11-05T10:00:00.000+0300",
        body="line1\nline2",
    )
    state = State(
        users={USER: [user_row()]},
        search={
            0: search_page(
                [issue(comments=[other], total=2)],
                total=1,
            )
        },
        threads={"DEMO-1": {0: thread_page([other, target], total=2)}},
    )

    result, seen, accepts, origin = run_cli(
        state,
        "--days",
        "30",
        "--limit",
        "1",
        "--project",
        "DEMO",
        "--json",
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == [
        {
            "key": "DEMO-1",
            "summary": "Fix the parser",
            "created": "2026-11-05T10:00:00.000+0300",
            "author": DISPLAY,
            "comment_id": "2002",
            "url": (
                f"{origin}{CONTEXT}/browse/DEMO-1"
                "?focusedCommentId=2002#comment-2002"
            ),
            "body": "line1\nline2",
        }
    ]
    assert SENTINEL not in result.stdout
    assert TOKEN not in result.stdout
    assert seen == [
        request(
            USER_PATH,
            {"username": [USER], "startAt": ["0"], "maxResults": ["50"]},
        ),
        request(
            SEARCH_PATH,
            {
                "jql": [
                    (
                        'updated >= -30d AND project = "DEMO" '
                        "ORDER BY updated DESC"
                    )
                ],
                "startAt": ["0"],
                "maxResults": ["100"],
                "fields": ["summary,comment,updated"],
            },
        ),
        request(COMMENT_PATH, {"startAt": ["0"], "maxResults": ["100"]}),
    ]
    assert accepts == ["application/json", "application/json", "application/json"]


def test_installed_author_comments_uses_the_authenticated_user_by_default() -> None:
    target = comment("3002", body="line1\nline2")
    state = State(
        current={
            "name": USER,
            "displayName": DISPLAY,
            "emailAddress": "ada@example.invalid",
        },
        search={0: search_page([issue(comments=[target], total=1)], total=1)},
    )

    result, seen, accepts, origin = run_cli(
        state,
        "--days",
        "30",
        "--limit",
        "1",
        "--project",
        "DEMO",
        "--json",
        user=None,
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == [
        {
            "key": "DEMO-1",
            "summary": "Fix the parser",
            "created": "2026-11-05T10:00:00.000+0300",
            "author": DISPLAY,
            "comment_id": "3002",
            "url": (
                f"{origin}{CONTEXT}/browse/DEMO-1"
                "?focusedCommentId=3002#comment-3002"
            ),
            "body": "line1\nline2",
        }
    ]
    assert SENTINEL not in result.stdout
    assert TOKEN not in result.stdout
    assert seen == [
        request(MYSELF_PATH, {}),
        request(
            SEARCH_PATH,
            {
                "jql": [
                    (
                        'updated >= -30d AND project = "DEMO" '
                        "ORDER BY updated DESC"
                    )
                ],
                "startAt": ["0"],
                "maxResults": ["100"],
                "fields": ["summary,comment,updated"],
            },
        ),
    ]
    assert accepts == ["application/json", "application/json"]


def test_installed_author_comments_returns_an_empty_array() -> None:
    state = State(
        users={USER: [user_row()]},
        search={0: search_page([], total=0)},
    )

    result, seen, _, _ = run_cli(
        state, "--days", "7", "--limit", "3", "--json"
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == []
    assert seen == [
        request(
            USER_PATH,
            {"username": [USER], "startAt": ["0"], "maxResults": ["50"]},
        ),
        request(
            SEARCH_PATH,
            {
                "jql": ["updated >= -7d ORDER BY updated DESC"],
                "startAt": ["0"],
                "maxResults": ["100"],
                "fields": ["summary,comment,updated"],
            },
        ),
    ]


def test_installed_author_comments_rejects_an_ambiguous_user_without_searching() -> None:
    state = State(
        users={
            USER: [
                user_row("ada.one", "Ada One"),
                user_row("ada.two", "Ada Two"),
            ]
        }
    )

    result, seen, _, _ = run_cli(state, "--json")

    assert result.returncode != 0
    assert result.stdout == ""
    assert "more than one" in result.stderr
    assert TOKEN not in result.stderr
    assert seen == [
        request(
            USER_PATH,
            {"username": [USER], "startAt": ["0"], "maxResults": ["50"]},
        ),
        request(
            USER_PATH,
            {"username": [USER], "startAt": ["2"], "maxResults": ["50"]},
        ),
    ]


def test_installed_author_comments_exact_login_wins_on_a_later_user_page() -> None:
    state = State(
        user_pages={
            USER: {
                0: [
                    user_row("ada.one", "Ada One"),
                    user_row("ada.two", "Ada Two"),
                ],
                2: [user_row()],
            }
        },
        search={
            0: search_page(
                [
                    issue(
                        comments=[
                            comment("5001", author="ada.one", body="wrong"),
                            comment("5002", author=USER, body="right"),
                        ],
                        total=2,
                    )
                ],
                total=1,
            )
        },
    )

    result, seen, _, _ = run_cli(state, "--limit", "5", "--json")

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    rows = json.loads(result.stdout)
    assert [row["comment_id"] for row in rows] == ["5002"]
    assert rows[0]["author"] == DISPLAY
    assert SENTINEL not in result.stdout
    assert TOKEN not in result.stdout
    assert seen == [
        request(
            USER_PATH,
            {"username": [USER], "startAt": ["0"], "maxResults": ["50"]},
        ),
        request(
            USER_PATH,
            {"username": [USER], "startAt": ["2"], "maxResults": ["50"]},
        ),
        request(
            SEARCH_PATH,
            {
                "jql": ["updated >= -90d ORDER BY updated DESC"],
                "startAt": ["0"],
                "maxResults": ["100"],
                "fields": ["summary,comment,updated"],
            },
        ),
    ]


def test_installed_author_comments_rejects_an_invalid_project_before_any_request() -> None:
    state = State()

    result, seen, accepts, _ = run_cli(
        state, "--project", 'BAD" OR 1=1', "--json"
    )

    assert result.returncode != 0
    assert result.stdout == ""
    assert "project" in result.stderr.lower()
    assert TOKEN not in result.stderr
    assert seen == []
    assert accepts == []


def test_installed_author_comments_reports_an_unknown_user() -> None:
    state = State(users={})

    result, seen, _, _ = run_cli(state, "--json")

    assert result.returncode != 0
    assert result.stdout == ""
    assert "No Jira user" in result.stderr
    assert TOKEN not in result.stderr
    assert seen == [
        request(
            USER_PATH,
            {"username": [USER], "startAt": ["0"], "maxResults": ["50"]},
        )
    ]


def test_installed_author_comments_publishes_nothing_after_a_later_page_failure() -> None:
    target = comment("2002", body="partial")
    state = State(
        users={USER: [user_row()]},
        search={
            0: search_page(
                [issue(comments=[target], total=1)],
                total=2,
                is_last=False,
            ),
            1: 500,
        },
    )

    result, seen, accepts, _ = run_cli(state, "--limit", "5", "--json")

    assert result.returncode == 1
    assert result.stdout == ""
    assert "HTTP 500" in result.stderr
    assert SENTINEL not in result.stderr
    assert TOKEN not in result.stderr
    assert "Traceback" not in result.stderr
    assert seen == [
        request(
            USER_PATH,
            {"username": [USER], "startAt": ["0"], "maxResults": ["50"]},
        ),
        request(
            SEARCH_PATH,
            {
                "jql": ["updated >= -90d ORDER BY updated DESC"],
                "startAt": ["0"],
                "maxResults": ["100"],
                "fields": ["summary,comment,updated"],
            },
        ),
        request(
            SEARCH_PATH,
            {
                "jql": ["updated >= -90d ORDER BY updated DESC"],
                "startAt": ["1"],
                "maxResults": ["100"],
                "fields": ["summary,comment,updated"],
            },
        ),
    ]
    assert accepts == ["application/json", "application/json", "application/json"]


def test_installed_author_comments_refuses_a_cross_host_redirect() -> None:
    honeypot: list[Request] = []

    class Honeypot(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            honeypot.append(request_record(self))
            send_json(self, 200, {"message": SENTINEL})

    with serving(Honeypot) as target:
        state = State(
            users={USER: [user_row()]},
            search={0: search_page([], total=0)},
        )
        state.redirects[SEARCH_PATH] = (
            f"http://127.0.0.1:{target.server_port}/stolen"
        )

        result, seen, _, _ = run_cli(state, "--json")

    assert result.returncode == 1
    assert result.stdout == ""
    assert "redirect refused" in result.stderr
    assert SENTINEL not in result.stdout + result.stderr
    assert TOKEN not in result.stderr
    assert seen == [
        request(
            USER_PATH,
            {"username": [USER], "startAt": ["0"], "maxResults": ["50"]},
        ),
        request(
            SEARCH_PATH,
            {
                "jql": ["updated >= -90d ORDER BY updated DESC"],
                "startAt": ["0"],
                "maxResults": ["100"],
                "fields": ["summary,comment,updated"],
            },
        ),
    ]
    assert honeypot == []


def test_installed_author_comments_rejects_a_malformed_created_timestamp() -> None:
    target = comment("2002", created="2026-11-05T10:00:00")
    state = State(
        users={USER: [user_row()]},
        search={0: search_page([issue(comments=[target], total=1)], total=1)},
    )

    result, seen, _, _ = run_cli(state, "--json")

    assert result.returncode == 1
    assert result.stdout == ""
    assert "timezone" in result.stderr
    assert SENTINEL not in result.stderr
    assert TOKEN not in result.stderr
    assert "Traceback" not in result.stderr
    assert seen == [
        request(
            USER_PATH,
            {"username": [USER], "startAt": ["0"], "maxResults": ["50"]},
        ),
        request(
            SEARCH_PATH,
            {
                "jql": ["updated >= -90d ORDER BY updated DESC"],
                "startAt": ["0"],
                "maxResults": ["100"],
                "fields": ["summary,comment,updated"],
            },
        ),
    ]


def test_installed_author_comments_applies_grep_to_the_full_body() -> None:
    target = comment("4001", body="Line One\nLINE TWO")
    other = comment("4002", body="other")
    state = State(
        users={USER: [user_row()]},
        search={
            0: search_page(
                [issue(comments=[target, other], total=2)],
                total=1,
            )
        },
    )

    result, seen, _, _ = run_cli(
        state,
        "--limit",
        "5",
        "--grep",
        r"one\s+line two",
        "--json",
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    rows = json.loads(result.stdout)
    assert [row["comment_id"] for row in rows] == ["4001"]
    assert rows[0]["body"] == "Line One\nLINE TWO"
    assert SENTINEL not in result.stdout
    assert TOKEN not in result.stdout
    assert seen == [
        request(
            USER_PATH,
            {"username": [USER], "startAt": ["0"], "maxResults": ["50"]},
        ),
        request(
            SEARCH_PATH,
            {
                "jql": ["updated >= -90d ORDER BY updated DESC"],
                "startAt": ["0"],
                "maxResults": ["100"],
                "fields": ["summary,comment,updated"],
            },
        ),
    ]


def test_installed_author_comments_grep_scans_later_thread_pages() -> None:
    state = State(
        users={USER: [user_row()]},
        search={
            0: search_page(
                [
                    issue(
                        comments=[comment("4099", author="grace")],
                        total=4,
                    )
                ],
                total=1,
            )
        },
        threads={
            "DEMO-1": {
                0: thread_page(
                    [
                        comment("4100", author="grace", body="context"),
                        comment("4101", body="first page no"),
                    ],
                    start=0,
                    total=4,
                ),
                2: thread_page(
                    [
                        comment("4102", author="grace", body="context"),
                        comment("4103", body="later MATCH"),
                    ],
                    start=2,
                    total=4,
                ),
            }
        },
    )

    result, seen, _, _ = run_cli(
        state, "--grep", "match", "--json"
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    rows = json.loads(result.stdout)
    assert [row["comment_id"] for row in rows] == ["4103"]
    comment_requests = [
        record for record in seen if record[1] == COMMENT_PATH
    ]
    assert comment_requests == [
        request(COMMENT_PATH, {"startAt": ["0"], "maxResults": ["100"]}),
        request(COMMENT_PATH, {"startAt": ["2"], "maxResults": ["100"]}),
    ]


def test_installed_author_comments_grep_no_match_returns_empty_array() -> None:
    target = comment("4201", body="nothing here")
    state = State(
        users={USER: [user_row()]},
        search={0: search_page([issue(comments=[target], total=1)], total=1)},
    )

    result, seen, _, _ = run_cli(state, "--grep", "needle", "--json")

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == []
    assert seen == [
        request(
            USER_PATH,
            {"username": [USER], "startAt": ["0"], "maxResults": ["50"]},
        ),
        request(
            SEARCH_PATH,
            {
                "jql": ["updated >= -90d ORDER BY updated DESC"],
                "startAt": ["0"],
                "maxResults": ["100"],
                "fields": ["summary,comment,updated"],
            },
        ),
    ]


def test_installed_author_comments_rejects_invalid_grep_before_any_request() -> None:
    state = State()

    result, seen, accepts, _ = run_cli(state, "--grep", "(", "--json")

    assert result.returncode != 0
    assert result.stdout == ""
    assert "invalid" in result.stderr.lower()
    assert TOKEN not in result.stderr
    assert seen == []
    assert accepts == []


def test_the_bbk_credentials_override_is_a_missing_synthetic_path() -> None:
    assert "missing-for-author-comments" in MISSING_BBK_CREDENTIALS
    assert not Path(MISSING_BBK_CREDENTIALS).exists()
