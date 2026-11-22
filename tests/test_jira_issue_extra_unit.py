"""Unit checks for Jira worklogs, changelog expansion, and project reads.

Every request is replaced at the adapter boundary and every credential is a
synthetic fixture; no test reads process settings or contacts a real server.
"""

from contextlib import nullcontext

import pytest

from atlawire import jira
from atlawire.http import AtlaWireError

BASE = "https://jira.example.invalid/jira"
LOOPBACK = "http://127.0.0.1:8080/jira"
TOKEN = "fixture-jira-issue-extra-token"
KEY = "DEMO-42"
SENTINEL = "JIRA-ISSUE-EXTRA-SENTINEL"
WORKLOG_PATH = f"{BASE}/rest/api/2/issue/{KEY}/worklog"
ISSUE_PATH = f"{BASE}/rest/api/2/issue/{KEY}"
PROJECTS_PATH = f"{BASE}/rest/api/2/project"

WORKLOG_ROWS: list[dict[str, object]] = [
    {
        "self": f"https://pasted.example.invalid/rest/api/2/issue/{KEY}/worklog/100028",
        "author": {
            "self": "https://pasted.example.invalid/rest/api/2/user?username=fred",
            "name": "fred",
            "key": "JIRAUSER10100",
            "displayName": "Fred F. User",
            "active": True,
            "avatarUrls": {"16x16": None},
            "pluginAuthor": {"nested": [1, None]},
        },
        "updateAuthor": None,
        "comment": "I did some work here. ✓",
        "created": None,
        "updated": "2022-02-16T10:06:48.928+0000",
        "visibility": {"type": "group", "value": "jira-developers"},
        "started": "2022-02-16T10:06:48.928+0000",
        "timeSpent": "3h 20m",
        "timeSpentSeconds": 12000,
        "id": "100028",
        "issueId": "10002",
        "pluginWorklogField": {"nested": [None, False, 2.5]},
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
        "id": "100029",
        "issueId": "10002",
    },
]

WORKLOGS_DOC: dict[str, object] = {
    "startAt": 0,
    "maxResults": 2,
    "total": 5,
    "worklogs": WORKLOG_ROWS,
    "pluginDocumentField": {"capped": True, "nested": [None]},
}

HISTORIES: list[dict[str, object]] = [
    {
        "id": "10001",
        "author": {
            "self": "https://pasted.example.invalid/rest/api/2/user?username=fred",
            "name": "fred",
            "displayName": "Fred F. User",
            "active": True,
            "pluginAuthor": {"nested": [None, 2]},
        },
        "created": "2022-02-16T10:06:48.928+0000",
        "items": [
            {
                "field": "status",
                "fieldtype": "jira",
                "from": "1",
                "fromString": "Open",
                "to": "3",
                "toString": "In Progress",
            }
        ],
        "historyMetadata": {
            "type": "issue-updated",
            "actor": {"id": "JIRAUSER10100", "displayName": "Fred"},
            "extraData": {"key": "value"},
        },
        "pluginHistoryField": {"nested": [None, 1]},
    },
    {
        "id": "10002",
        "author": None,
        "created": None,
        "items": [],
        "historyMetadata": None,
    },
]

CHANGELOG_DOC: dict[str, object] = {
    "startAt": 1,
    "maxResults": 2,
    "total": 9,
    "histories": HISTORIES,
    "pluginChangelogField": {"nested": [True, None]},
}

ISSUE_DOC: dict[str, object] = {
    "expand": "changelog",
    "id": "10002",
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
        "lead": {"name": "fred", "displayName": "Fred", "active": True},
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


def read_worklogs(
    monkeypatch: pytest.MonkeyPatch,
    document: dict[str, object],
    *,
    base: str = BASE,
    argument: str = KEY,
    allow_http_loopback: bool = False,
) -> tuple[dict[str, object], list[tuple[str, dict[str, str | int]]], list[str]]:
    """Call the worklog reader with a fake transport and record the request."""
    seen: list[tuple[str, dict[str, str | int]]] = []
    tokens: list[str] = []

    def fake_bearer_session(token: str) -> object:
        tokens.append(token)
        return nullcontext(None)

    def fake_get_json_object(
        session: object, url: str, *, params: dict[str, str | int]
    ) -> dict[str, object]:
        seen.append((url, dict(params)))
        return document

    monkeypatch.setattr(jira, "bearer_session", fake_bearer_session)
    monkeypatch.setattr(jira, "get_json_object", fake_get_json_object)
    result = jira.get_issue_worklogs(
        base, argument, token=TOKEN, allow_http_loopback=allow_http_loopback
    )
    return result, seen, tokens


def read_changelog(
    monkeypatch: pytest.MonkeyPatch,
    issue: dict[str, object],
    *,
    base: str = BASE,
    argument: str = KEY,
    allow_http_loopback: bool = False,
) -> tuple[dict[str, object], list[tuple[str, dict[str, str | int]]], list[str]]:
    """Call the changelog reader with a fake transport and record the request."""
    seen: list[tuple[str, dict[str, str | int]]] = []
    tokens: list[str] = []

    def fake_bearer_session(token: str) -> object:
        tokens.append(token)
        return nullcontext(None)

    def fake_get_json_object(
        session: object, url: str, *, params: dict[str, str | int]
    ) -> dict[str, object]:
        seen.append((url, dict(params)))
        return issue

    monkeypatch.setattr(jira, "bearer_session", fake_bearer_session)
    monkeypatch.setattr(jira, "get_json_object", fake_get_json_object)
    result = jira.get_issue_changelog(
        base, argument, token=TOKEN, allow_http_loopback=allow_http_loopback
    )
    return result, seen, tokens


def read_projects(
    monkeypatch: pytest.MonkeyPatch,
    values: list[object],
    *,
    base: str = BASE,
    allow_http_loopback: bool = False,
) -> tuple[list[dict[str, object]], list[tuple[str, dict[str, str | int]]], list[str]]:
    """Call the project reader with a fake transport and record the request."""
    seen: list[tuple[str, dict[str, str | int]]] = []
    tokens: list[str] = []

    def fake_bearer_session(token: str) -> object:
        tokens.append(token)
        return nullcontext(None)

    def fake_get_json_array(
        session: object, url: str, *, params: dict[str, str | int]
    ) -> list[object]:
        seen.append((url, dict(params)))
        return values

    monkeypatch.setattr(jira, "bearer_session", fake_bearer_session)
    monkeypatch.setattr(jira, "get_json_array", fake_get_json_array)
    rows = jira.list_jira_projects(
        base, token=TOKEN, allow_http_loopback=allow_http_loopback
    )
    return rows, seen, tokens


def test_worklogs_use_the_fixed_endpoint_and_preserve_the_whole_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document, seen, tokens = read_worklogs(monkeypatch, WORKLOGS_DOC)

    assert document == WORKLOGS_DOC
    assert document["startAt"] == 0
    assert document["maxResults"] == 2
    assert document["total"] == 5
    worklogs = document["worklogs"]
    assert isinstance(worklogs, list)
    assert len(worklogs) == 2
    assert seen == [(WORKLOG_PATH, {})]
    assert tokens == [TOKEN]


@pytest.mark.parametrize("base", [BASE, f"{BASE}/"], ids=["no-slash", "trailing-slash"])
def test_a_trailing_base_slash_does_not_change_the_worklog_url(
    monkeypatch: pytest.MonkeyPatch, base: str
) -> None:
    _, seen, _ = read_worklogs(monkeypatch, WORKLOGS_DOC, base=base)

    assert seen == [(WORKLOG_PATH, {})]


def test_a_pasted_browse_url_supplies_only_the_worklog_issue_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    argument = f"https://pasted.example.invalid/jira/browse/{KEY}?tab=worklog#top"

    document, seen, _ = read_worklogs(monkeypatch, WORKLOGS_DOC, argument=argument)

    assert document == WORKLOGS_DOC
    assert seen == [(WORKLOG_PATH, {})]


@pytest.mark.parametrize(
    "argument",
    [
        "",
        " ",
        "demo-42",
        "DEMO",
        "DEMO-42 ",
        f"https://pasted.example.invalid/browse/{KEY}/extra",
        f"https://pasted.example.invalid/browse/{KEY}\ud800",
    ],
)
def test_worklogs_reject_an_unusable_key_before_any_session(
    monkeypatch: pytest.MonkeyPatch, argument: str
) -> None:
    def unexpected_session(token: str) -> object:
        raise AssertionError("No session should be created.")

    def unexpected_object(*args: object, **kwargs: object) -> dict[str, object]:
        raise AssertionError("No request should be attempted.")

    monkeypatch.setattr(jira, "bearer_session", unexpected_session)
    monkeypatch.setattr(jira, "get_json_object", unexpected_object)

    with pytest.raises(AtlaWireError, match="issue key"):
        jira.get_issue_worklogs(BASE, argument, token=TOKEN)


def test_empty_worklogs_are_valid_and_keep_their_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = {**WORKLOGS_DOC, "worklogs": [], "total": 0}

    result, seen, _ = read_worklogs(monkeypatch, document)

    assert result == document
    assert result["total"] == 0
    assert seen == [(WORKLOG_PATH, {})]


@pytest.mark.parametrize(
    "document",
    [
        {},
        {"worklogs": None},
        {"worklogs": {}},
        {"worklogs": "text"},
        {"worklogs": 7},
    ],
    ids=["missing", "null", "object", "text", "integer"],
)
def test_worklogs_reject_a_missing_or_non_list_worklogs_member(
    monkeypatch: pytest.MonkeyPatch, document: dict[str, object]
) -> None:
    with pytest.raises(AtlaWireError, match="worklogs array"):
        read_worklogs(monkeypatch, document)


@pytest.mark.parametrize(
    "entry",
    [None, [], "text", 7, 1.5, True],
    ids=["null", "array", "text", "integer", "float", "boolean"],
)
def test_a_malformed_late_worklog_row_rejects_the_whole_document(
    monkeypatch: pytest.MonkeyPatch, entry: object
) -> None:
    document = {**WORKLOGS_DOC, "worklogs": [WORKLOG_ROWS[0], entry]}

    with pytest.raises(AtlaWireError, match="worklog objects"):
        read_worklogs(monkeypatch, document)


@pytest.mark.parametrize(
    "base",
    [
        "http://127.0.0.1:8080/jira",
        "https://synthetic-user@jira.example.invalid/jira",
        f"{BASE}?expand=changelog",
        f"{BASE}#fragment",
    ],
    ids=["http-without-opt-in", "userinfo", "query", "fragment"],
)
def test_worklogs_reject_an_unsafe_base_before_any_session(
    monkeypatch: pytest.MonkeyPatch, base: str
) -> None:
    def unexpected_session(token: str) -> object:
        raise AssertionError("No session should be created.")

    monkeypatch.setattr(jira, "bearer_session", unexpected_session)

    with pytest.raises(AtlaWireError, match="base URL"):
        jira.get_issue_worklogs(base, KEY, token=TOKEN)


def test_worklogs_accept_explicit_http_loopback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document, seen, _ = read_worklogs(
        monkeypatch, WORKLOGS_DOC, base=LOOPBACK, allow_http_loopback=True
    )

    assert document == WORKLOGS_DOC
    assert seen == [(f"{LOOPBACK}/rest/api/2/issue/{KEY}/worklog", {})]


def test_changelog_uses_the_fixed_expanded_issue_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document, seen, tokens = read_changelog(monkeypatch, ISSUE_DOC)

    assert document == CHANGELOG_DOC
    assert document["startAt"] == 1
    assert document["maxResults"] == 2
    assert document["total"] == 9
    histories = document["histories"]
    assert isinstance(histories, list)
    assert len(histories) == 2
    assert "fields" not in document
    assert "pluginIssueField" not in document
    assert seen == [(ISSUE_PATH, {"expand": "changelog"})]
    assert tokens == [TOKEN]


@pytest.mark.parametrize("base", [BASE, f"{BASE}/"], ids=["no-slash", "trailing-slash"])
def test_a_trailing_base_slash_does_not_change_the_changelog_url(
    monkeypatch: pytest.MonkeyPatch, base: str
) -> None:
    _, seen, _ = read_changelog(monkeypatch, ISSUE_DOC, base=base)

    assert seen == [(ISSUE_PATH, {"expand": "changelog"})]


def test_a_pasted_browse_url_supplies_only_the_changelog_issue_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    argument = f"https://pasted.example.invalid/jira/browse/{KEY}/?tab=history"

    document, seen, _ = read_changelog(monkeypatch, ISSUE_DOC, argument=argument)

    assert document == CHANGELOG_DOC
    assert seen == [(ISSUE_PATH, {"expand": "changelog"})]


@pytest.mark.parametrize(
    "argument",
    [
        "",
        "demo-42",
        "DEMO-42x",
        f"https://pasted.example.invalid/browse/{KEY}/extra",
        f"https://pasted.example.invalid/browse/{KEY}\ud800",
    ],
)
def test_changelog_rejects_an_unusable_key_before_any_session(
    monkeypatch: pytest.MonkeyPatch, argument: str
) -> None:
    def unexpected_session(token: str) -> object:
        raise AssertionError("No session should be created.")

    def unexpected_object(*args: object, **kwargs: object) -> dict[str, object]:
        raise AssertionError("No request should be attempted.")

    monkeypatch.setattr(jira, "bearer_session", unexpected_session)
    monkeypatch.setattr(jira, "get_json_object", unexpected_object)

    with pytest.raises(AtlaWireError, match="issue key"):
        jira.get_issue_changelog(BASE, argument, token=TOKEN)


def test_an_empty_changelog_is_valid_and_keeps_its_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    changelog = {**CHANGELOG_DOC, "histories": [], "total": 0}
    issue = {**ISSUE_DOC, "changelog": changelog}

    result, seen, _ = read_changelog(monkeypatch, issue)

    assert result == changelog
    assert result["total"] == 0
    assert seen == [(ISSUE_PATH, {"expand": "changelog"})]


@pytest.mark.parametrize(
    "issue",
    [
        {},
        {"changelog": None},
        {"changelog": []},
        {"changelog": "text"},
        {"changelog": 7},
    ],
    ids=["missing", "null", "array", "text", "integer"],
)
def test_changelog_rejects_a_missing_or_non_object_changelog(
    monkeypatch: pytest.MonkeyPatch, issue: dict[str, object]
) -> None:
    with pytest.raises(AtlaWireError, match="changelog document"):
        read_changelog(monkeypatch, issue)


@pytest.mark.parametrize(
    "changelog",
    [
        {},
        {"histories": None},
        {"histories": {}},
        {"histories": "text"},
    ],
    ids=["missing", "null", "object", "text"],
)
def test_changelog_rejects_a_missing_or_non_list_histories_member(
    monkeypatch: pytest.MonkeyPatch, changelog: dict[str, object]
) -> None:
    issue = {**ISSUE_DOC, "changelog": changelog}

    with pytest.raises(AtlaWireError, match="histories array"):
        read_changelog(monkeypatch, issue)


@pytest.mark.parametrize(
    "entry",
    [None, [], "text", 7, 1.5, True],
    ids=["null", "array", "text", "integer", "float", "boolean"],
)
def test_a_malformed_late_history_row_rejects_the_whole_changelog(
    monkeypatch: pytest.MonkeyPatch, entry: object
) -> None:
    changelog = {**CHANGELOG_DOC, "histories": [HISTORIES[0], entry]}
    issue = {**ISSUE_DOC, "changelog": changelog}

    with pytest.raises(AtlaWireError, match="change history objects"):
        read_changelog(monkeypatch, issue)


@pytest.mark.parametrize(
    "base",
    [
        "http://127.0.0.1:8080/jira",
        "https://synthetic-user@jira.example.invalid/jira",
        f"{BASE}?expand=changelog",
        f"{BASE}#fragment",
    ],
    ids=["http-without-opt-in", "userinfo", "query", "fragment"],
)
def test_changelog_rejects_an_unsafe_base_before_any_session(
    monkeypatch: pytest.MonkeyPatch, base: str
) -> None:
    def unexpected_session(token: str) -> object:
        raise AssertionError("No session should be created.")

    monkeypatch.setattr(jira, "bearer_session", unexpected_session)

    with pytest.raises(AtlaWireError, match="base URL"):
        jira.get_issue_changelog(base, KEY, token=TOKEN)


def test_changelog_accepts_explicit_http_loopback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document, seen, _ = read_changelog(
        monkeypatch, ISSUE_DOC, base=LOOPBACK, allow_http_loopback=True
    )

    assert document == CHANGELOG_DOC
    assert seen == [(f"{LOOPBACK}/rest/api/2/issue/{KEY}", {"expand": "changelog"})]


def test_projects_use_the_fixed_endpoint_and_preserve_raw_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows, seen, tokens = read_projects(monkeypatch, list(PROJECTS))

    assert rows == PROJECTS
    assert seen == [(PROJECTS_PATH, {})]
    assert tokens == [TOKEN]
    assert "pluginProjectField" in rows[0]
    assert any(value is None for row in rows for value in row.values())


@pytest.mark.parametrize("base", [BASE, f"{BASE}/"], ids=["no-slash", "trailing-slash"])
def test_a_trailing_base_slash_does_not_change_the_projects_url(
    monkeypatch: pytest.MonkeyPatch, base: str
) -> None:
    _, seen, _ = read_projects(monkeypatch, [], base=base)

    assert seen == [(PROJECTS_PATH, {})]


def test_an_empty_project_array_is_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    rows, seen, _ = read_projects(monkeypatch, [])

    assert rows == []
    assert seen == [(PROJECTS_PATH, {})]


@pytest.mark.parametrize(
    "entry",
    [None, [], "text", 7, 1.5, True],
    ids=["null", "array", "text", "integer", "float", "boolean"],
)
def test_a_malformed_late_project_row_rejects_the_whole_array(
    monkeypatch: pytest.MonkeyPatch, entry: object
) -> None:
    with pytest.raises(AtlaWireError, match="project objects"):
        read_projects(monkeypatch, [PROJECTS[0], entry])


@pytest.mark.parametrize(
    "base",
    [
        "http://127.0.0.1:8080/jira",
        "https://synthetic-user@jira.example.invalid/jira",
        f"{BASE}?recent=5",
        f"{BASE}#fragment",
    ],
    ids=["http-without-opt-in", "userinfo", "query", "fragment"],
)
def test_projects_reject_an_unsafe_base_before_any_session(
    monkeypatch: pytest.MonkeyPatch, base: str
) -> None:
    def unexpected_session(token: str) -> object:
        raise AssertionError("No session should be created.")

    monkeypatch.setattr(jira, "bearer_session", unexpected_session)

    with pytest.raises(AtlaWireError, match="base URL"):
        jira.list_jira_projects(base, token=TOKEN)


def test_projects_accept_explicit_http_loopback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows, seen, _ = read_projects(
        monkeypatch, [PROJECTS[0]], base=LOOPBACK, allow_http_loopback=True
    )

    assert rows == [PROJECTS[0]]
    assert seen == [(f"{LOOPBACK}/rest/api/2/project", {})]
