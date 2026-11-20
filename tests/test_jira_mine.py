from contextlib import nullcontext

import pytest

from atlawire import jira
from atlawire.http import AtlaWireError

BASE = "https://jira.example.invalid/jira"
DEFAULT_QUERY = (
    "assignee = currentUser() AND statusCategory != Done ORDER BY updated DESC"
)
FIELDS = "summary,status,priority,issuetype,assignee,updated"


def run_mine(
    monkeypatch: pytest.MonkeyPatch,
    *,
    status: str | None = None,
    limit: int = 50,
) -> list[dict[str, object]]:
    seen: list[dict[str, object]] = []

    def fake_get_json_object(
        session: object, url: str, *, params: dict[str, str | int]
    ) -> dict[str, object]:
        seen.append({"url": url, **params})
        return {"startAt": 0, "maxResults": 50, "total": 0, "issues": []}

    monkeypatch.setattr(jira, "bearer_session", lambda token: nullcontext(None))
    monkeypatch.setattr(jira, "get_json_object", fake_get_json_object)
    assert (
        jira.list_my_issues(BASE, token="fixture-only", status=status, limit=limit)
        == []
    )
    return seen


def search_request(query: str, *, limit: int = 50) -> dict[str, object]:
    return {
        "url": f"{BASE}/rest/api/2/search",
        "jql": query,
        "fields": FIELDS,
        "startAt": 0,
        "maxResults": limit,
    }


@pytest.mark.parametrize("status", [None, ""])
def test_my_issues_default_query_selects_everything_not_done(
    monkeypatch: pytest.MonkeyPatch, status: str | None
) -> None:
    assert run_mine(monkeypatch, status=status) == [search_request(DEFAULT_QUERY)]


@pytest.mark.parametrize(
    "status",
    ["В работе", "In Progress", "AND", "  spaced  ", "Готово к деплою — QA"],
)
def test_supported_status_is_one_exact_quoted_literal(
    monkeypatch: pytest.MonkeyPatch, status: str
) -> None:
    seen = run_mine(monkeypatch, status=status, limit=7)

    assert seen == [
        search_request(
            f'assignee = currentUser() AND status = "{status}" ORDER BY updated DESC',
            limit=7,
        )
    ]


@pytest.mark.parametrize(
    "status",
    [
        'Synthetic "label"',
        "Synthetic\\label",
        "Synthetic\x00label",
        "Synthetic\x7flabel",
        "Synthetic\x85label",
        "Synthetic\u2028label",
        "Synthetic\u2029label",
        "Synthetic\ud800label",
    ],
)
def test_unsupported_status_fails_before_opening_a_session(
    monkeypatch: pytest.MonkeyPatch, status: str
) -> None:
    def unexpected_session(token: str) -> object:
        raise AssertionError("No request should be attempted.")

    monkeypatch.setattr(jira, "bearer_session", unexpected_session)

    with pytest.raises(AtlaWireError) as error:
        jira.list_my_issues(BASE, token="fixture-only", status=status)

    assert "Unsupported status name" in str(error.value)
    assert status not in str(error.value)
