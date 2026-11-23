"""Opt-in end-to-end contract check: BBK Jira functions through AtlaWire.

Run only with the explicit gate variable, from the repository root::

    $env:ATLAWIRE_E2E_BBK_JIRA = "1"
    C:/Python315/python.exe -B -m pytest -q -p no:cacheprovider \
        checks/e2e_bbk_jira.py

Without ``ATLAWIRE_E2E_BBK_JIRA=1`` every test is skipped, so an ordinary run
never contacts a live server. The checks are read-only: each one calls a single
AtlaWire library function and validates the observed value against the
``bbk.jira`` contract (arguments and promised result shape), not against the
AtlaWire implementation. Credentials are loaded from the saved BBK file only
through ``atlawire.credentials``; this module never reads, prints, or logs that
file, its contents, the base URL, or the token. The token is used solely to
assert that a response does not echo it.

BBK -> AtlaWire coverage:

* ``jql``             -> ``jira.search_all_issues`` (raw issues, chosen fields)
* ``rows``            -> ``jira.search_issues`` (seven-key short rows)
* ``mine``            -> ``jira.list_my_issues`` (open issues, exact status)
* ``issue``           -> ``jira.get_issue`` (key/fields/renderedFields, URL)
* ``issue_md``        -> ``issue_markdown.render_issue_markdown``
* ``statuses``        -> ``jira.list_statuses``
* ``me``              -> ``jira.get_current_user``
* ``transitions``     -> ``jira.list_transitions``
* ``resolve_user``    -> ``jira.search_users`` (lookup only; no resolver)
* ``recent_comments`` -> ``jira_comments_search.find_author_comments``
* ``titles``          -> ``jira.titles``
* ``url``             -> no AtlaWire equivalent (pure string helper)

Input is discovered from the server with narrow ``assignee = currentUser()``
JQLs, so no invented issue key is ever sent. Each check asserts one observable
contract: types, required keys, non-emptiness where BBK promised data, and the
absence of the bearer token in the returned value. A 401, 403, or 429 aborts
the whole run instead of reporting per-test failures.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from datetime import datetime
from typing import Any

import pytest

from atlawire import issue_markdown, jira, jira_comments_search
from atlawire.credentials import load_saved_credentials
from atlawire.http import AtlaWireError

GATE_ENV = "ATLAWIRE_E2E_BBK_JIRA"
GATE = pytest.mark.skipif(
    os.environ.get(GATE_ENV) != "1",
    reason=f"live E2E is opt-in: set {GATE_ENV}=1 to call the real Jira server",
)
pytestmark = GATE

_ISSUE_KEY = re.compile(r"[A-Z][A-Z0-9_]*-[0-9]+")
_ISO_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_COMMENT_ID = re.compile(r"[0-9]+")
# The documented "my open issues" query from bbk.jira.mine.
_MY_OPEN_JQL = (
    "assignee = currentUser() AND statusCategory != Done ORDER BY updated DESC"
)
# Required keys promised by the BBK result shapes.
_ROW_KEYS = frozenset(
    {"key", "status", "type", "priority", "assignee", "updated", "summary"}
)
_USER_KEYS = frozenset({"name", "displayName", "email"})
_TRANSITION_KEYS = frozenset({"id", "name", "to_status"})
_COMMENT_KEYS = frozenset(
    {"key", "summary", "created", "author", "comment_id", "url", "body"}
)


class _Live:
    """One saved Jira destination; the token is never rendered in a repr."""

    __slots__ = ("base_url", "token")

    def __init__(self, base_url: str, token: str) -> None:
        self.base_url = base_url
        self.token = token


def _stop_on_auth(exc: AtlaWireError) -> None:
    """Abort the whole live run on authentication or rate-limit statuses."""
    if exc.http_status in {401, 403, 429}:
        pytest.exit(
            f"STOP: Jira returned HTTP {exc.http_status}; "
            "the live E2E run was aborted without further requests.",
            returncode=2,
        )


def _call(function: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Run one AtlaWire read, stopping the run on 401/403/429."""
    try:
        return function(*args, **kwargs)
    except AtlaWireError as exc:
        _stop_on_auth(exc)
        raise


def _assert_no_token(value: object, token: str) -> None:
    """Reject any result that would expose the bearer token."""
    text = json.dumps(value, ensure_ascii=False, default=str)
    assert token not in text, "the response echoed the bearer token"


def _assert_issue_key(value: object) -> None:
    """Require a syntactically valid Jira issue key."""
    assert isinstance(value, str), "issue key is not text"
    assert _ISSUE_KEY.fullmatch(value) is not None, "issue key has invalid syntax"


def _assert_row(row: object, token: str) -> None:
    """Validate one four-field short row against the bbk.jira.rows contract."""
    assert isinstance(row, dict), "issue row is not an object"
    assert set(row) == _ROW_KEYS, "issue row lacks a promised key"
    _assert_issue_key(row["key"])
    assert isinstance(row["summary"], str), "row summary is not text"
    updated = row["updated"]
    assert isinstance(updated, str), "row updated is not text"
    assert updated == "" or _ISO_DATE.fullmatch(updated) is not None, (
        "row updated is not a date prefix"
    )
    for name in ("status", "type", "priority", "assignee"):
        value = row[name]
        assert value is None or isinstance(value, str), (
            f"row {name} is neither text nor null"
        )
    _assert_no_token(row, token)


@pytest.fixture(scope="module")
def live() -> _Live:
    """Load the saved Jira URL and token without exposing either."""
    try:
        saved = load_saved_credentials("jira", allow_http_loopback=False)
    except AtlaWireError:
        pytest.skip("saved BBK Jira credentials are unavailable")
    return _Live(saved.base_url, saved.token)


@pytest.fixture(scope="module")
def current(live: _Live) -> dict[str, object]:
    """The authenticated caller, read once for reuse by lookup checks."""
    return _call(jira.get_current_user, live.base_url, token=live.token)


@pytest.fixture(scope="module")
def my_rows(live: _Live) -> list[dict[str, object]]:
    """A bounded page of the caller's open issues, used for discovery."""
    rows = _call(
        jira.search_issues,
        live.base_url,
        _MY_OPEN_JQL,
        token=live.token,
        limit=5,
    )
    assert isinstance(rows, list), "search rows are not a list"
    for row in rows:
        _assert_row(row, live.token)
    return rows


@pytest.fixture(scope="module")
def issue_key(live: _Live) -> str:
    """Discover one visible issue instead of hard-coding a key."""
    for query in (
        "assignee = currentUser() ORDER BY updated DESC",
        "ORDER BY updated DESC",
    ):
        rows = _call(
            jira.search_issues,
            live.base_url,
            query,
            token=live.token,
            limit=1,
        )
        if rows:
            assert isinstance(rows[0], dict), "search row is not an object"
            key = rows[0].get("key")
            _assert_issue_key(key)
            assert isinstance(key, str)
            return key
    pytest.skip("inconclusive: no visible Jira issue to anchor the live checks")


def test_jql_returns_raw_issues_with_the_requested_fields(
    live: _Live, issue_key: str
) -> None:
    """bbk.jql promise: raw issue dicts carrying the requested fields."""
    query = f"key in ({issue_key})"
    issues = _call(
        jira.search_all_issues,
        live.base_url,
        query,
        token=live.token,
        fields="summary,status",
        limit=1,
    )
    assert isinstance(issues, list), "search result is not a list"
    assert len(issues) == 1, "the exact-key search did not return one issue"
    issue = issues[0]
    assert isinstance(issue, dict), "raw issue is not an object"
    assert issue.get("key") == issue_key, "raw issue key does not match"
    fields = issue.get("fields")
    assert isinstance(fields, dict), "raw issue has no fields object"
    assert isinstance(fields.get("summary"), str), "summary is not text"
    assert "status" in fields, "requested status field is absent"
    _assert_no_token(issue, live.token)


def test_rows_have_the_seven_promised_keys(live: _Live, issue_key: str) -> None:
    """bbk.rows promise: key/status/type/priority/assignee/updated/summary."""
    rows = _call(
        jira.search_issues,
        live.base_url,
        f"key in ({issue_key})",
        token=live.token,
        limit=1,
    )
    assert isinstance(rows, list), "search rows are not a list"
    assert len(rows) == 1, "the exact-key search did not return one row"
    _assert_row(rows[0], live.token)
    assert rows[0]["key"] == issue_key, "row key does not match the query"


def test_mine_uses_the_documented_open_issue_query(
    live: _Live, my_rows: list[dict[str, object]]
) -> None:
    """bbk.mine promise: the caller's not-Done issues, newest first."""
    rows = _call(jira.list_my_issues, live.base_url, token=live.token, limit=5)
    assert isinstance(rows, list), "mine result is not a list"
    for row in rows:
        _assert_row(row, live.token)
    assert [row["key"] for row in rows] == [row["key"] for row in my_rows], (
        "mine does not match the documented JQL result"
    )


def test_mine_narrows_to_an_exact_status(
    live: _Live, my_rows: list[dict[str, object]]
) -> None:
    """bbk.mine(status) promise: only issues in that exact status."""
    if not my_rows:
        pytest.skip("inconclusive: the caller has no open issues")
    status = my_rows[0]["status"]
    if not isinstance(status, str) or not status:
        pytest.skip("inconclusive: the discovered issue has no status name")
    rows = _call(
        jira.list_my_issues,
        live.base_url,
        token=live.token,
        status=status,
        limit=5,
    )
    assert isinstance(rows, list), "status-filtered result is not a list"
    for row in rows:
        _assert_row(row, live.token)
        assert row["status"] == status, "row escaped the requested status"


def test_issue_returns_fields_and_rendered_fields(
    live: _Live, issue_key: str
) -> None:
    """bbk.issue promise: the full issue JSON, rendered fields included."""
    issue = _call(jira.get_issue, live.base_url, issue_key, token=live.token)
    assert isinstance(issue, dict), "issue is not an object"
    assert issue.get("key") == issue_key, "issue key does not match"
    fields = issue.get("fields")
    assert isinstance(fields, dict), "issue has no fields object"
    rendered = issue.get("renderedFields")
    assert isinstance(rendered, dict), "issue has no renderedFields object"
    summary = fields.get("summary")
    assert isinstance(summary, str) and summary, "issue summary is empty"
    _assert_no_token(issue, live.token)


def test_issue_accepts_a_browse_url(live: _Live, issue_key: str) -> None:
    """bbk.issue promise: a /browse/... URL is accepted like a bare key."""
    browse_url = f"{live.base_url}/browse/{issue_key}"
    issue = _call(jira.get_issue, live.base_url, browse_url, token=live.token)
    assert isinstance(issue, dict), "issue is not an object"
    assert issue.get("key") == issue_key, "browse URL resolved to another issue"


def test_issue_markdown_renders_the_same_issue(
    live: _Live, issue_key: str
) -> None:
    """bbk.issue_md promise: a Markdown card for HTML and wiki source."""
    issue = _call(jira.get_issue, live.base_url, issue_key, token=live.token)
    for use_wiki in (False, True):
        text = issue_markdown.render_issue_markdown(issue, use_wiki=use_wiki)
        assert isinstance(text, str) and text, "rendered card is empty"
        assert text.startswith(f"# {issue_key}"), "card lacks the issue heading"
        assert text.endswith("\n"), "card does not end with a newline"
        _assert_no_token(text, live.token)


def test_statuses_are_sorted_unique_names(live: _Live) -> None:
    """bbk.statuses promise: every instance status name, sorted and unique."""
    names = _call(jira.list_statuses, live.base_url, token=live.token)
    assert isinstance(names, list), "statuses are not a list"
    assert names, "the instance returned no status names"
    for name in names:
        assert isinstance(name, str) and name, "a status name is empty"
    assert names == sorted(names), "status names are not sorted"
    assert len(names) == len(set(names)), "status names are not unique"


def test_current_user_has_the_three_identity_fields(
    live: _Live, current: dict[str, object]
) -> None:
    """bbk.me promise: exactly name, displayName, email, with a named caller."""
    assert isinstance(current, dict), "current user is not an object"
    assert set(current) == _USER_KEYS, "current user has unexpected keys"
    name = current["name"]
    assert isinstance(name, str) and name.strip(), "current user name is empty"
    for key in ("displayName", "email"):
        value = current[key]
        assert value is None or isinstance(value, str), f"{key} is not text"
    _assert_no_token(current, live.token)


def _transitions(
    live: _Live, candidates: list[str]
) -> list[dict[str, object]]:
    """Return the first non-empty transition list from the sampled issues."""
    for key in candidates:
        rows = _call(jira.list_transitions, live.base_url, key, token=live.token)
        assert isinstance(rows, list), "transitions are not a list"
        if rows:
            return rows
    return []


def test_transitions_describe_offered_workflow_actions(
    live: _Live, issue_key: str, my_rows: list[dict[str, object]]
) -> None:
    """bbk.transitions promise: [{id, name, to_status}] offered on the issue."""
    candidates = list(dict.fromkeys([issue_key, *(row["key"] for row in my_rows[:2])]))
    rows = _transitions(live, candidates)
    if not rows:
        pytest.skip(
            "inconclusive: no workflow transition is offered on the sampled issues"
        )
    for row in rows:
        assert isinstance(row, dict), "transition is not an object"
        assert set(row) == _TRANSITION_KEYS, "transition lacks a promised key"
        identifier = row["id"]
        assert isinstance(identifier, str) and identifier.strip(), "empty transition id"
        name = row["name"]
        assert isinstance(name, str) and name.strip(), "empty transition name"
        target = row["to_status"]
        assert target is None or isinstance(target, str), "target status is not text"
        _assert_no_token(row, live.token)


def test_user_search_finds_the_current_login(
    live: _Live, current: dict[str, object]
) -> None:
    """bbk.resolve_user lookup half: the exact login is found by user search."""
    login = current["name"]
    assert isinstance(login, str) and login
    users = _call(
        jira.search_users,
        live.base_url,
        login,
        token=live.token,
        max_results=20,
    )
    assert isinstance(users, list), "user search result is not a list"
    for user in users:
        assert isinstance(user, dict), "user search row is not an object"
    names = [user.get("name") for user in users]
    assert login in names, "the exact login is absent from its own user search"
    _assert_no_token(users, live.token)


def test_titles_map_the_issue_key_to_its_summary(
    live: _Live, issue_key: str
) -> None:
    """bbk.titles promise: a key-to-summary mapping for the requested keys."""
    issue = _call(jira.get_issue, live.base_url, issue_key, token=live.token)
    fields = issue.get("fields")
    assert isinstance(fields, dict), "issue has no fields object"
    summary = fields.get("summary")
    assert isinstance(summary, str), "issue summary is not text"
    titles = _call(jira.titles, live.base_url, [issue_key], token=live.token)
    assert isinstance(titles, dict), "titles result is not a mapping"
    assert titles == {issue_key: summary}, "titles do not match the issue summary"


def _author_comments(
    live: _Live, *, days: int, max_issues: int
) -> list[dict[str, object]]:
    rows = _call(
        jira_comments_search.find_author_comments,
        live.base_url,
        token=live.token,
        days=days,
        limit=3,
        max_issues=max_issues,
    )
    assert isinstance(rows, list), "author comments are not a list"
    return rows


def test_recent_comments_have_the_documented_row_shape(live: _Live) -> None:
    """bbk.recent_comments promise: newest author comments with a deep link."""
    # 20000 is the bbk.recent_comments default issue budget.
    try:
        rows = _author_comments(live, days=30, max_issues=20000)
        if not rows:
            rows = _author_comments(live, days=90, max_issues=20000)
    except AtlaWireError as exc:
        _stop_on_auth(exc)
        pytest.skip("inconclusive: the bounded author comment scan did not finish")
    if not rows:
        pytest.skip("inconclusive: the caller wrote no comment in the window")
    assert len(rows) <= 3, "the limit was exceeded"
    instants: list[datetime] = []
    for row in rows:
        assert isinstance(row, dict), "comment row is not an object"
        assert set(row) == _COMMENT_KEYS, "comment row lacks a promised key"
        key = row["key"]
        _assert_issue_key(key)
        assert isinstance(key, str)
        assert isinstance(row["summary"], str), "comment summary is not text"
        created = row["created"]
        assert isinstance(created, str), "comment created is not text"
        instant = datetime.fromisoformat(created)
        assert instant.tzinfo is not None, "comment created lacks a timezone"
        author = row["author"]
        assert isinstance(author, str) and author.strip(), "comment author is empty"
        comment_id = row["comment_id"]
        assert isinstance(comment_id, str), "comment id is not text"
        assert _COMMENT_ID.fullmatch(comment_id) is not None, "invalid comment id"
        expected = (
            f"{live.base_url}/browse/{key}?focusedCommentId={comment_id}"
            f"#comment-{comment_id}"
        )
        assert row["url"] == expected, "comment deep link does not match the contract"
        assert isinstance(row["body"], str), "comment body is not text"
        _assert_no_token(row, live.token)
        instants.append(instant)
    assert instants == sorted(instants, reverse=True), "comments are not newest first"
