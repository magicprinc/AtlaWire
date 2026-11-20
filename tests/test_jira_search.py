from contextlib import nullcontext

import pytest
from click.testing import CliRunner

from atlawire import jira
from atlawire.cli import cli
from atlawire.http import AtlaWireError

BASE = "https://jira.example.invalid/jira"
QUERY = "project = DEMO ORDER BY key"
FIELDS = "summary,status,priority,issuetype,assignee,updated"


def search(
    monkeypatch: pytest.MonkeyPatch,
    pages: list[dict[str, object]],
    *,
    limit: int = 50,
    query: str = QUERY,
    fail_at: int | None = None,
) -> tuple[list[jira.IssueRow], list[dict[str, object]]]:
    seen: list[dict[str, object]] = []

    def fake_get_json_object(
        session: object, url: str, *, params: dict[str, str | int]
    ) -> dict[str, object]:
        if fail_at is not None and len(seen) == fail_at:
            raise AtlaWireError("HTTP 503: request failed.")
        seen.append({"url": url, **params})
        return pages[len(seen) - 1]

    monkeypatch.setattr(jira, "bearer_session", lambda token: nullcontext(None))
    monkeypatch.setattr(jira, "get_json_object", fake_get_json_object)
    rows = jira.search_issues(BASE, query, token="fixture-only", limit=limit)
    return rows, seen


def issue(key: str) -> dict[str, object]:
    return {"key": key, "fields": {}}


def page(
    issues: list[dict[str, object]],
    *,
    start: int = 0,
    max_results: object = 50,
    total: object = None,
    include_total: bool = True,
    include_max_results: bool = True,
) -> dict[str, object]:
    value: dict[str, object] = {"startAt": start, "issues": issues}
    if include_max_results:
        value["maxResults"] = max_results
    if include_total:
        value["total"] = total
    return value


def test_project_issue_normalizes_text_and_keeps_optional_fields_optional() -> None:
    row = jira._project_issue(
        {
            "key": "DEMO-1",
            "fields": {
                "summary": "  Résumé\n\tdetails ",
                "status": {"name": "In Progress"},
                "issuetype": {"name": "Bug"},
                "priority": None,
                "assignee": {"displayName": "Ada"},
                "updated": "2024-01-02T03:04:05.000+0000",
            },
        }
    )

    assert row == {
        "key": "DEMO-1",
        "status": "In Progress",
        "type": "Bug",
        "priority": None,
        "assignee": "Ada",
        "updated": "2024-01-02",
        "summary": "Résumé details",
    }


@pytest.mark.parametrize(
    "fields",
    [
        {},
        {
            "summary": None,
            "status": None,
            "issuetype": {},
            "priority": {"name": None},
            "assignee": {},
            "updated": None,
        },
    ],
)
def test_project_issue_uses_none_for_missing_or_null_links(
    fields: dict[str, object],
) -> None:
    row = jira._project_issue({"key": "DEMO-2", "fields": fields})

    assert row == {
        "key": "DEMO-2",
        "status": None,
        "type": None,
        "priority": None,
        "assignee": None,
        "updated": "",
        "summary": "",
    }


def test_project_issue_keeps_an_explicit_empty_link_name_as_empty_text() -> None:
    row = jira._project_issue(
        {
            "key": "DEMO-3",
            "fields": {
                "status": {"name": ""},
                "issuetype": {"name": ""},
                "priority": {"name": ""},
                "assignee": {"displayName": ""},
            },
        }
    )

    assert row["status"] == ""
    assert row["type"] == ""
    assert row["priority"] == ""
    assert row["assignee"] == ""


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (None, "issue object"),
        ({}, "issue key"),
        ({"key": 1, "fields": {}}, "issue key"),
        ({"key": "", "fields": {}}, "issue key"),
        ({"key": "DEMO-1"}, "issue fields"),
        ({"key": "DEMO-1", "fields": []}, "issue fields"),
        ({"key": "DEMO-1", "fields": {"summary": 1}}, "summary"),
        ({"key": "DEMO-1", "fields": {"updated": 1}}, "updated"),
        ({"key": "DEMO-1", "fields": {"status": "open"}}, "status"),
        ({"key": "DEMO-1", "fields": {"status": {"name": 1}}}, "status"),
        ({"key": "DEMO-1", "fields": {"issuetype": {"name": False}}}, "type"),
        ({"key": "DEMO-1", "fields": {"priority": {"name": []}}}, "priority"),
        ({"key": "DEMO-1", "fields": {"assignee": "Ada"}}, "assignee"),
        ({"key": "DEMO-1", "fields": {"assignee": {"displayName": 1}}}, "assignee"),
    ],
)
def test_project_issue_rejects_malformed_rows(value: object, message: str) -> None:
    with pytest.raises(AtlaWireError, match=message):
        jira._project_issue(value)


def test_short_page_advances_by_consumed_rows_and_requests_only_remaining_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = [
        page([issue("DEMO-1"), issue("DEMO-2")], start=0, max_results=5, total=5),
        page(
            [issue("DEMO-3"), issue("DEMO-4"), issue("DEMO-5")],
            start=2,
            max_results=3,
            total=5,
        ),
    ]

    rows, seen = search(monkeypatch, pages, limit=5)

    assert [row["key"] for row in rows] == [
        "DEMO-1",
        "DEMO-2",
        "DEMO-3",
        "DEMO-4",
        "DEMO-5",
    ]
    assert seen == [
        {
            "url": f"{BASE}/rest/api/2/search",
            "jql": QUERY,
            "fields": FIELDS,
            "startAt": 0,
            "maxResults": 5,
        },
        {
            "url": f"{BASE}/rest/api/2/search",
            "jql": QUERY,
            "fields": FIELDS,
            "startAt": 2,
            "maxResults": 3,
        },
    ]


def test_server_page_cap_is_followed_without_skipping_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = [
        page([issue("DEMO-1"), issue("DEMO-2")], start=0, max_results=2, total=5),
        page(
            [issue("DEMO-3"), issue("DEMO-4"), issue("DEMO-5")],
            start=2,
            max_results=3,
            total=5,
        ),
    ]

    rows, seen = search(monkeypatch, pages, limit=5)

    assert [row["key"] for row in rows] == [
        "DEMO-1",
        "DEMO-2",
        "DEMO-3",
        "DEMO-4",
        "DEMO-5",
    ]
    assert [request["startAt"] for request in seen] == [0, 2]


def test_limit_is_enforced_when_server_returns_more_rows_than_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = [
        page(
            [issue("DEMO-1"), issue("DEMO-2"), issue("DEMO-3")],
            start=0,
            max_results=5,
            total=10,
        )
    ]

    rows, seen = search(monkeypatch, pages, limit=2)

    assert [row["key"] for row in rows] == ["DEMO-1", "DEMO-2"]
    assert len(seen) == 1


def test_page_larger_than_advertised_max_results_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = [
        page(
            [issue("DEMO-1"), issue("DEMO-2"), issue("DEMO-3")],
            start=0,
            max_results=2,
            total=10,
        )
    ]

    with pytest.raises(AtlaWireError, match="more issues than maxResults"):
        search(monkeypatch, pages, limit=5)


def test_unknown_total_continues_until_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    pages = [
        page([issue("DEMO-1")], start=0, max_results=50, include_total=False),
        page([issue("DEMO-2")], start=1, max_results=50, include_total=False),
    ]

    rows, seen = search(monkeypatch, pages, limit=2)

    assert [row["key"] for row in rows] == ["DEMO-1", "DEMO-2"]
    assert [request["startAt"] for request in seen] == [0, 1]


def test_empty_first_page_with_zero_total_is_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = [page([], start=0, max_results=50, total=0)]

    rows, seen = search(monkeypatch, pages, limit=50)

    assert rows == []
    assert len(seen) == 1


def test_empty_page_after_a_shrinking_total_is_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = [
        page([issue("DEMO-1")], start=0, max_results=50, total=3),
        page([], start=1, max_results=50, total=1),
    ]

    rows, seen = search(monkeypatch, pages, limit=50)

    assert [row["key"] for row in rows] == ["DEMO-1"]
    assert [request["startAt"] for request in seen] == [0, 1]


def test_empty_page_with_outstanding_total_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = [page([], start=0, max_results=50, total=2)]

    with pytest.raises(AtlaWireError, match="empty page"):
        search(monkeypatch, pages, limit=50)


def test_empty_page_with_unknown_total_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = [page([], start=0, max_results=50, include_total=False)]

    with pytest.raises(AtlaWireError, match="without a total"):
        search(monkeypatch, pages, limit=50)


def test_unknown_total_then_empty_page_does_not_return_partial_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = [
        page([issue("DEMO-1")], start=0, max_results=50, include_total=False),
        page([], start=1, max_results=50, include_total=False),
    ]

    with pytest.raises(AtlaWireError, match="without a total"):
        search(monkeypatch, pages, limit=50)


def test_limit_bounds_the_number_of_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = [
        page([issue(f"DEMO-{index}")], start=index, max_results=1, total=1000)
        for index in range(3)
    ]

    rows, seen = search(monkeypatch, pages, limit=3)

    assert [row["key"] for row in rows] == ["DEMO-0", "DEMO-1", "DEMO-2"]
    assert [request["startAt"] for request in seen] == [0, 1, 2]


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ({"issues": [], "total": 0, "maxResults": 50}, "startAt"),
        (
            {
                "startAt": 1,
                "issues": [],
                "total": 0,
                "maxResults": 50,
            },
            "startAt",
        ),
        (
            {
                "startAt": True,
                "issues": [],
                "total": 0,
                "maxResults": 50,
            },
            "startAt",
        ),
        (
            {
                "startAt": -1,
                "issues": [],
                "total": 0,
                "maxResults": 50,
            },
            "startAt",
        ),
        ({"startAt": 0, "total": 0, "maxResults": 50}, "issues"),
        ({"startAt": 0, "issues": {}, "total": 0}, "issues"),
        (
            {
                "startAt": 0,
                "issues": [issue("DEMO-1")],
                "total": 1,
            },
            "maxResults",
        ),
        (
            {
                "startAt": 0,
                "issues": [issue("DEMO-1")],
                "total": 1,
                "maxResults": 0,
            },
            "maxResults",
        ),
        (
            {
                "startAt": 0,
                "issues": [issue("DEMO-1")],
                "total": 1,
                "maxResults": True,
            },
            "maxResults",
        ),
        (
            {
                "startAt": 0,
                "issues": [],
                "total": -1,
                "maxResults": 50,
            },
            "total",
        ),
        (
            {
                "startAt": 0,
                "issues": [issue("DEMO-1")],
                "total": True,
                "maxResults": 50,
            },
            "total",
        ),
        (
            {
                "startAt": 0,
                "issues": [issue("DEMO-1")],
                "total": 0,
                "maxResults": 50,
            },
            "Inconsistent",
        ),
        (
            {
                "startAt": 0,
                "issues": [issue("DEMO-1"), issue("DEMO-2")],
                "total": 1,
                "maxResults": 50,
            },
            "Inconsistent",
        ),
    ],
)
def test_invalid_or_contradictory_pagination_metadata_is_rejected(
    monkeypatch: pytest.MonkeyPatch, value: dict[str, object], message: str
) -> None:
    with pytest.raises(AtlaWireError, match=message):
        search(monkeypatch, [value], limit=50)


def test_a_later_request_failure_raises_instead_of_returning_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = [page([issue("DEMO-1")], start=0, max_results=50, total=3)]

    with pytest.raises(AtlaWireError, match="HTTP 503"):
        search(monkeypatch, pages, limit=50, fail_at=1)


@pytest.mark.parametrize(
    ("query", "limit"),
    [("", 50), ("   ", 50), (QUERY, 0), (QUERY, 1001)],
)
def test_invalid_query_or_limit_fails_before_creating_a_session(
    monkeypatch: pytest.MonkeyPatch, query: str, limit: int
) -> None:
    def unexpected_session(token: str) -> object:
        raise AssertionError("No request should be attempted.")

    monkeypatch.setattr(jira, "bearer_session", unexpected_session)

    with pytest.raises(AtlaWireError):
        jira.search_issues(BASE, query, token="fixture-only", limit=limit)


def test_jql_help_documents_the_limit_range() -> None:
    result = CliRunner().invoke(cli, ["jql", "--help"])

    assert result.exit_code == 0
    assert "1-1000" in result.output
    assert "--json" in result.output
