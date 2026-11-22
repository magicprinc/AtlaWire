"""Unit checks for Jira reference lists and the bounded user search.

Every request is replaced at the adapter boundary and every credential is a
synthetic fixture; no test reads process settings or contacts a real server.
"""

from collections.abc import Callable
from contextlib import nullcontext
from copy import deepcopy

import pytest

from atlawire import jira
from atlawire.http import AtlaWireError

BASE = "https://jira.example.invalid/jira"
LOOPBACK = "http://127.0.0.1:8080/jira"
TOKEN = "fixture-jira-reference-token"
SENTINEL = "JIRA-REFERENCE-SENTINEL"

PRIORITIES: list[dict[str, object]] = [
    {
        "self": "https://pasted.example.invalid/rest/api/2/priority/3",
        "statusColor": "#009900",
        "description": "Major loss of function.",
        "iconUrl": "https://pasted.example.invalid/icons/major.png",
        "name": "Major",
        "id": "3",
        "pluginRank": {"order": [2, None, False]},
    },
    {
        "self": None,
        "statusColor": None,
        "description": None,
        "iconUrl": None,
        "name": "Trivial",
        "id": "5",
    },
]

RESOLUTIONS: list[dict[str, object]] = [
    {
        "self": "https://pasted.example.invalid/rest/api/2/resolution/1",
        "description": "A fix is checked into the tree and tested. ✓",
        "iconUrl": "https://pasted.example.invalid/icons/resolved.png",
        "name": "Fixed",
        "id": "1",
        "pluginField": {"nested": {"empty": [], "null": None}},
    },
    {
        "self": None,
        "description": None,
        "iconUrl": None,
        "name": "Works as designed",
        "id": "3",
    },
]

ISSUE_TYPES: list[dict[str, object]] = [
    {
        "self": "https://pasted.example.invalid/rest/api/2/issueType/3",
        "id": "3",
        "description": "A task that needs to be done.",
        "iconUrl": "https://pasted.example.invalid/icons/task.png",
        "name": "Task",
        "subtask": False,
        "avatarId": 1,
        "pluginField": {"hierarchyLevel": 0},
    },
    {
        "self": None,
        "id": "5",
        "description": None,
        "iconUrl": None,
        "name": "Sub-task",
        "subtask": True,
        "avatarId": 10002,
    },
]

STATUS_CATEGORIES: list[dict[str, object]] = [
    {
        "self": "https://pasted.example.invalid/rest/api/2/statuscategory/1",
        "id": 1,
        "key": "in-flight",
        "colorName": "yellow",
        "name": "In Progress",
        "pluginField": {"nested": [1, None]},
    },
    {
        "self": None,
        "id": 9,
        "key": "completed",
        "colorName": "green",
        "name": None,
    },
]

USERS: list[dict[str, object]] = [
    {
        "self": "https://pasted.example.invalid/rest/api/2/user?username=fred",
        "key": "JIRAUSER10100",
        "name": "fred",
        "emailAddress": "fred@example.com",
        "avatarUrls": {
            "48x48": "https://pasted.example.invalid/avatar?size=large",
            "16x16": None,
        },
        "displayName": "Fred F. User",
        "active": True,
        "deleted": False,
        "timeZone": "Australia/Sydney",
        "locale": "en_AU",
        "groups": {
            "size": 1,
            "items": [{"name": "jira-users", "self": None}],
        },
        "pluginField": [1, 2.5, {"nested": None}],
    },
    {
        "self": None,
        "key": None,
        "name": "andrew",
        "emailAddress": None,
        "avatarUrls": {},
        "displayName": "Andrew Anderson",
        "active": False,
        "deleted": False,
        "expand": None,
    },
]

REFERENCE_ENDPOINTS: list[
    tuple[Callable[..., list[dict[str, object]]], str, str, list[dict[str, object]]]
] = [
    (jira.list_priorities, "/rest/api/2/priority", "priority", PRIORITIES),
    (jira.list_resolutions, "/rest/api/2/resolution", "resolution", RESOLUTIONS),
    (jira.list_issue_types, "/rest/api/2/issuetype", "issue type", ISSUE_TYPES),
    (
        jira.list_status_categories,
        "/rest/api/2/statuscategory",
        "status category",
        STATUS_CATEGORIES,
    ),
]


def test_user_result_constants_match_the_documented_822_bounds() -> None:
    assert jira.USER_RESULTS_MIN == 1
    assert jira.USER_RESULTS_MAX == 1000
    assert jira.USER_RESULTS_DEFAULT == 50


def read_reference(
    monkeypatch: pytest.MonkeyPatch,
    function: Callable[..., list[dict[str, object]]],
    values: list[object],
    *,
    base: str = BASE,
    allow_http_loopback: bool = False,
) -> tuple[list[dict[str, object]], list[tuple[str, dict[str, str | int]]], list[str]]:
    """Call one reference reader with a fake transport and record the request."""
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
    rows = function(base, token=TOKEN, allow_http_loopback=allow_http_loopback)
    return rows, seen, tokens


@pytest.mark.parametrize(
    ("function", "path", "label", "expected"),
    REFERENCE_ENDPOINTS,
    ids=["priorities", "resolutions", "issue-types", "status-categories"],
)
def test_each_reference_reader_uses_its_fixed_endpoint_without_parameters(
    monkeypatch: pytest.MonkeyPatch,
    function: Callable[..., list[dict[str, object]]],
    path: str,
    label: str,
    expected: list[dict[str, object]],
) -> None:
    rows, seen, tokens = read_reference(monkeypatch, function, list(expected))

    assert rows == expected
    assert seen == [(f"{BASE}{path}", {})]
    assert tokens == [TOKEN]


@pytest.mark.parametrize(
    ("function", "path", "label", "expected"),
    REFERENCE_ENDPOINTS,
    ids=["priorities", "resolutions", "issue-types", "status-categories"],
)
def test_a_trailing_base_slash_does_not_change_a_reference_url(
    monkeypatch: pytest.MonkeyPatch,
    function: Callable[..., list[dict[str, object]]],
    path: str,
    label: str,
    expected: list[dict[str, object]],
) -> None:
    _, seen, _ = read_reference(monkeypatch, function, [], base=f"{BASE}/")

    assert seen == [(f"{BASE}{path}", {})]


@pytest.mark.parametrize(
    ("function", "path", "label", "expected"),
    REFERENCE_ENDPOINTS,
    ids=["priorities", "resolutions", "issue-types", "status-categories"],
)
def test_an_empty_reference_array_is_valid(
    monkeypatch: pytest.MonkeyPatch,
    function: Callable[..., list[dict[str, object]]],
    path: str,
    label: str,
    expected: list[dict[str, object]],
) -> None:
    rows, seen, _ = read_reference(monkeypatch, function, [])

    assert rows == []
    assert seen == [(f"{BASE}{path}", {})]


@pytest.mark.parametrize(
    ("function", "path", "label", "expected"),
    REFERENCE_ENDPOINTS,
    ids=["priorities", "resolutions", "issue-types", "status-categories"],
)
def test_each_reference_reader_preserves_raw_unknown_and_nested_fields(
    monkeypatch: pytest.MonkeyPatch,
    function: Callable[..., list[dict[str, object]]],
    path: str,
    label: str,
    expected: list[dict[str, object]],
) -> None:
    rows, _, _ = read_reference(monkeypatch, function, deepcopy(expected))

    assert rows == expected
    for row in rows:
        assert isinstance(row, dict)
    # Unknown keys are neither dropped nor renamed by a projection.
    extension_field = "pluginRank" if label == "priority" else "pluginField"
    assert rows[0][extension_field] == expected[0][extension_field]
    assert any(value is None for row in rows for value in row.values())


@pytest.mark.parametrize(
    ("function", "path", "label", "expected"),
    REFERENCE_ENDPOINTS,
    ids=["priorities", "resolutions", "issue-types", "status-categories"],
)
@pytest.mark.parametrize(
    "entry",
    [None, [], "text", 7, 1.5, True],
    ids=["null", "array", "text", "integer", "float", "boolean"],
)
def test_a_malformed_late_reference_row_rejects_the_whole_array(
    monkeypatch: pytest.MonkeyPatch,
    function: Callable[..., list[dict[str, object]]],
    path: str,
    label: str,
    expected: list[dict[str, object]],
    entry: object,
) -> None:
    seen: list[tuple[str, dict[str, str | int]]] = []

    def fake_bearer_session(token: str) -> object:
        return nullcontext(None)

    def fake_get_json_array(
        session: object, url: str, *, params: dict[str, str | int]
    ) -> list[object]:
        seen.append((url, dict(params)))
        return [expected[0], entry]

    monkeypatch.setattr(jira, "bearer_session", fake_bearer_session)
    monkeypatch.setattr(jira, "get_json_array", fake_get_json_array)

    with pytest.raises(AtlaWireError, match=f"{label} objects"):
        function(BASE, token=TOKEN)
    assert seen == [(f"{BASE}{path}", {})]


@pytest.mark.parametrize(
    ("function", "path", "label", "expected"),
    REFERENCE_ENDPOINTS,
    ids=["priorities", "resolutions", "issue-types", "status-categories"],
)
def test_each_reference_reader_rejects_http_loopback_without_opt_in(
    monkeypatch: pytest.MonkeyPatch,
    function: Callable[..., list[dict[str, object]]],
    path: str,
    label: str,
    expected: list[dict[str, object]],
) -> None:
    def unexpected_session(token: str) -> object:
        raise AssertionError("No session should be created.")

    monkeypatch.setattr(jira, "bearer_session", unexpected_session)

    with pytest.raises(AtlaWireError, match="base URL"):
        function(LOOPBACK, token=TOKEN)


@pytest.mark.parametrize(
    ("function", "path", "label", "expected"),
    REFERENCE_ENDPOINTS,
    ids=["priorities", "resolutions", "issue-types", "status-categories"],
)
def test_each_reference_reader_accepts_explicit_http_loopback(
    monkeypatch: pytest.MonkeyPatch,
    function: Callable[..., list[dict[str, object]]],
    path: str,
    label: str,
    expected: list[dict[str, object]],
) -> None:
    rows, seen, _ = read_reference(
        monkeypatch, function, [expected[0]], base=LOOPBACK, allow_http_loopback=True
    )

    assert rows == [expected[0]]
    assert seen == [(f"{LOOPBACK}{path}", {})]


def read_users(
    monkeypatch: pytest.MonkeyPatch,
    values: list[object],
    *,
    username: str = "fred",
    start_at: int = 0,
    max_results: int = jira.USER_RESULTS_DEFAULT,
    base: str = BASE,
    allow_http_loopback: bool = False,
) -> tuple[
    list[dict[str, object]], list[tuple[str, dict[str, str | int]]], list[str]
]:
    """Call the user search with a fake transport and record the request."""
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
    rows = jira.search_users(
        base,
        username,
        token=TOKEN,
        start_at=start_at,
        max_results=max_results,
        allow_http_loopback=allow_http_loopback,
    )
    return rows, seen, tokens


def test_user_search_sends_documented_parameters_and_preserves_users(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows, seen, tokens = read_users(monkeypatch, list(USERS))

    assert rows == USERS
    assert seen == [
        (
            f"{BASE}/rest/api/2/user/search",
            {"username": "fred", "startAt": 0, "maxResults": 50},
        )
    ]
    assert tokens == [TOKEN]
    assert any("pluginField" in row for row in rows)
    assert any(value is None for row in rows for value in row.values())


def test_user_search_accepts_explicit_bounds_and_non_ascii_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows, seen, _ = read_users(
        monkeypatch,
        list(USERS),
        username="Бета ✓ Lovelace",
        start_at=25,
        max_results=1000,
    )

    assert rows == USERS
    assert seen == [
        (
            f"{BASE}/rest/api/2/user/search",
            {"username": "Бета ✓ Lovelace", "startAt": 25, "maxResults": 1000},
        )
    ]


@pytest.mark.parametrize("max_results", [1, 50, 1000])
def test_user_search_accepts_every_supported_result_limit(
    monkeypatch: pytest.MonkeyPatch, max_results: int
) -> None:
    _, seen, _ = read_users(monkeypatch, [], max_results=max_results)

    assert seen[0][1]["maxResults"] == max_results


@pytest.mark.parametrize("start_at", [0, 1, 10_000])
def test_user_search_accepts_any_non_negative_start_index(
    monkeypatch: pytest.MonkeyPatch, start_at: int
) -> None:
    _, seen, _ = read_users(monkeypatch, [], start_at=start_at)

    assert seen[0][1]["startAt"] == start_at


def test_user_search_returns_an_empty_page_as_valid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows, seen, _ = read_users(monkeypatch, [])

    assert rows == []
    assert len(seen) == 1


def test_user_search_reads_only_one_page_even_when_it_is_full(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = [USERS[0], USERS[1], {**USERS[0], "name": "third"}]

    rows, seen, _ = read_users(monkeypatch, page, max_results=3)

    assert rows == page
    assert len(seen) == 1


def test_user_search_rejects_a_page_longer_than_the_requested_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[tuple[str, dict[str, str | int]]] = []

    def fake_bearer_session(token: str) -> object:
        return nullcontext(None)

    def fake_get_json_array(
        session: object, url: str, *, params: dict[str, str | int]
    ) -> list[object]:
        seen.append((url, dict(params)))
        return [USERS[0], USERS[1]]

    monkeypatch.setattr(jira, "bearer_session", fake_bearer_session)
    monkeypatch.setattr(jira, "get_json_array", fake_get_json_array)

    with pytest.raises(AtlaWireError, match="more users than maxResults"):
        jira.search_users(BASE, "fred", token=TOKEN, max_results=1)
    assert seen == [
        (
            f"{BASE}/rest/api/2/user/search",
            {"username": "fred", "startAt": 0, "maxResults": 1},
        )
    ]


@pytest.mark.parametrize(
    "entry",
    [None, [], "text", 7, 1.5, True],
    ids=["null", "array", "text", "integer", "float", "boolean"],
)
def test_a_malformed_late_user_row_rejects_the_whole_page(
    monkeypatch: pytest.MonkeyPatch, entry: object
) -> None:
    seen: list[tuple[str, dict[str, str | int]]] = []

    def fake_bearer_session(token: str) -> object:
        return nullcontext(None)

    def fake_get_json_array(
        session: object, url: str, *, params: dict[str, str | int]
    ) -> list[object]:
        seen.append((url, dict(params)))
        return [USERS[0], entry]

    monkeypatch.setattr(jira, "bearer_session", fake_bearer_session)
    monkeypatch.setattr(jira, "get_json_array", fake_get_json_array)

    with pytest.raises(AtlaWireError, match="user objects"):
        jira.search_users(BASE, "fred", token=TOKEN)
    assert seen == [
        (
            f"{BASE}/rest/api/2/user/search",
            {"username": "fred", "startAt": 0, "maxResults": 50},
        )
    ]


def unexpected_request(monkeypatch: pytest.MonkeyPatch) -> None:
    def unexpected_session(token: str) -> object:
        raise AssertionError("No session should be created.")

    def unexpected_array(*args: object, **kwargs: object) -> list[object]:
        raise AssertionError("No request should be attempted.")

    monkeypatch.setattr(jira, "bearer_session", unexpected_session)
    monkeypatch.setattr(jira, "get_json_array", unexpected_array)


@pytest.mark.parametrize(
    ("username", "message"),
    [
        ("", "non-empty Jira user search text"),
        (" ", "non-empty Jira user search text"),
        ("\t\n", "non-empty Jira user search text"),
        ("\u00a0", "non-empty Jira user search text"),
        (None, "non-empty Jira user search text"),
        (7, "non-empty Jira user search text"),
        ("\ud800", "valid UTF-8"),
        ("ok\udfff", "valid UTF-8"),
    ],
    ids=["empty", "space", "controls", "nbsp", "none", "integer", "surrogate", "tail"],
)
def test_user_search_rejects_an_unusable_query_before_any_request(
    monkeypatch: pytest.MonkeyPatch, username: object, message: str
) -> None:
    unexpected_request(monkeypatch)

    with pytest.raises(AtlaWireError, match=message):
        jira.search_users(BASE, username, token=TOKEN)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "start_at",
    [-1, -10, True, 1.5, "0", None],
    ids=["negative", "very-negative", "boolean", "float", "text", "none"],
)
def test_user_search_rejects_an_invalid_start_index_before_any_request(
    monkeypatch: pytest.MonkeyPatch, start_at: object
) -> None:
    unexpected_request(monkeypatch)

    with pytest.raises(AtlaWireError, match="start index"):
        jira.search_users(
            BASE,
            "fred",
            token=TOKEN,
            start_at=start_at,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    "max_results",
    [0, -1, 1001, True, 1.5, "50", None],
    ids=["zero", "negative", "too-large", "boolean", "float", "text", "none"],
)
def test_user_search_rejects_an_invalid_result_limit_before_any_request(
    monkeypatch: pytest.MonkeyPatch, max_results: object
) -> None:
    unexpected_request(monkeypatch)

    with pytest.raises(AtlaWireError, match="result limit"):
        jira.search_users(
            BASE,
            "fred",
            token=TOKEN,
            max_results=max_results,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    "base",
    [
        "http://127.0.0.1:8080/jira",
        "https://synthetic-user@jira.example.invalid/jira",
        f"{BASE}?username=fred",
        f"{BASE}#fragment",
    ],
    ids=["http-without-opt-in", "userinfo", "query", "fragment"],
)
def test_user_search_rejects_an_unsafe_base_before_any_session(
    monkeypatch: pytest.MonkeyPatch, base: str
) -> None:
    unexpected_request(monkeypatch)

    with pytest.raises(AtlaWireError, match="base URL"):
        jira.search_users(base, "fred", token=TOKEN)


def test_user_search_accepts_explicit_http_loopback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows, seen, _ = read_users(
        monkeypatch, [USERS[1]], base=LOOPBACK, allow_http_loopback=True
    )

    assert rows == [USERS[1]]
    assert seen == [
        (
            f"{LOOPBACK}/rest/api/2/user/search",
            {"username": "fred", "startAt": 0, "maxResults": 50},
        )
    ]
