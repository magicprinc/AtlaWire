"""Focused library checks for the visible-project repository search."""

from collections.abc import Mapping
from contextlib import nullcontext
from typing import cast

import pytest

from atlawire import bitbucket
from atlawire.http import AtlaWireError

BASE = "https://bitbucket.example.invalid/scm"
TOKEN = "fixture-only-token"
PROJECTS_URL = f"{BASE}/rest/api/1.0/projects"
A_REPOS = f"{PROJECTS_URL}/A/repos"
B_REPOS = f"{PROJECTS_URL}/B/repos"


def forbid_session(token: str) -> object:
    raise AssertionError("session created before validation")


def read(
    monkeypatch: pytest.MonkeyPatch,
    pages: Mapping[tuple[str, int], object],
    seen: list[tuple[str, int]],
    *,
    max_pages: int = 100,
    limit: int = 25,
) -> list[bitbucket.RepositoryMatch]:
    def fake_get_json_object(
        session: object, url: str, *, params: dict[str, str | int]
    ) -> dict[str, object]:
        start = cast(int, params["start"])
        if (url, start) not in pages:
            raise AssertionError("Unexpected extra Bitbucket request.")
        seen.append((url, start))
        page = pages[(url, start)]
        if isinstance(page, Exception):
            raise page
        return cast(dict[str, object], page)

    monkeypatch.setattr(bitbucket, "bearer_session", lambda token: nullcontext(None))
    monkeypatch.setattr(bitbucket, "get_json_object", fake_get_json_object)
    return bitbucket.find_repositories(
        BASE, "match", token=TOKEN, limit=limit, max_pages=max_pages
    )


@pytest.mark.parametrize(
    ("max_pages", "expected"),
    [
        (2, [(PROJECTS_URL, 0), (A_REPOS, 0)]),
        (3, [(PROJECTS_URL, 0), (A_REPOS, 0), (A_REPOS, 100)]),
    ],
    ids=["inside-repository-pages", "between-projects"],
)
def test_one_total_page_budget_fails_before_any_extra_request(
    monkeypatch: pytest.MonkeyPatch,
    max_pages: int,
    expected: list[tuple[str, int]],
) -> None:
    pages = {
        (PROJECTS_URL, 0): {
            "values": [{"key": "A"}, {"key": "B"}],
            "isLastPage": True,
        },
        (A_REPOS, 0): {
            "values": [{"slug": "unrelated"}],
            "isLastPage": False,
            "nextPageStart": 100,
        },
        (A_REPOS, 100): {"values": [{"slug": "other"}], "isLastPage": True},
    }
    seen: list[tuple[str, int]] = []

    with pytest.raises(AtlaWireError, match="page limit"):
        read(monkeypatch, pages, seen, max_pages=max_pages)

    assert expected == seen


def test_no_matches_exhausts_every_project_and_returns_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = {
        (PROJECTS_URL, 0): {"values": [{"key": "A"}], "isLastPage": True},
        (A_REPOS, 0): {
            "values": [{"slug": "other", "name": None}],
            "isLastPage": True,
        },
    }
    seen: list[tuple[str, int]] = []

    assert read(monkeypatch, pages, seen) == []
    assert seen == [(PROJECTS_URL, 0), (A_REPOS, 0)]


@pytest.mark.parametrize("name", ["", " \t\n", "\ud800"])
def test_blank_or_unencodable_search_is_rejected_before_any_session(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    monkeypatch.setattr(bitbucket, "bearer_session", forbid_session)

    with pytest.raises(AtlaWireError, match="repository search"):
        bitbucket.find_repositories(BASE, name, token=TOKEN)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("limit", 0),
        ("limit", 1001),
        ("limit", True),
        ("max_pages", 0),
        ("max_pages", 1001),
        ("max_pages", True),
    ],
)
def test_bool_or_out_of_range_limits_are_rejected_before_any_session(
    monkeypatch: pytest.MonkeyPatch, field: str, value: int
) -> None:
    monkeypatch.setattr(bitbucket, "bearer_session", forbid_session)

    with pytest.raises(AtlaWireError, match="limit"):
        if field == "limit":
            bitbucket.find_repositories(BASE, "match", token=TOKEN, limit=value)
        else:
            bitbucket.find_repositories(BASE, "match", token=TOKEN, max_pages=value)


def test_invalid_server_project_key_builds_no_repository_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[tuple[str, int]] = []

    def fake_get_json_object(
        session: object, url: str, *, params: dict[str, str | int]
    ) -> dict[str, object]:
        seen.append((url, cast(int, params["start"])))
        return {
            "values": [{"key": "../B"}],
            "isLastPage": True,
        }

    monkeypatch.setattr(bitbucket, "bearer_session", lambda token: nullcontext(None))
    monkeypatch.setattr(bitbucket, "get_json_object", fake_get_json_object)

    with pytest.raises(AtlaWireError, match="Invalid project key"):
        bitbucket.find_repositories(BASE, "match", token=TOKEN)

    assert seen == [(PROJECTS_URL, 0)]


def test_the_match_cap_stops_repository_paging_within_the_shared_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Before the early stop the first repository page was paged to exhaustion,
    # so a budget spent on the project page left no room for the next cursor
    # even though this page already held the only requested match.
    pages = {
        (PROJECTS_URL, 0): {"values": [{"key": "A"}], "isLastPage": True},
        (A_REPOS, 0): {
            "values": [{"slug": "match"}],
            "isLastPage": False,
            "nextPageStart": 100,
        },
    }
    seen: list[tuple[str, int]] = []

    rows = read(monkeypatch, pages, seen, max_pages=2, limit=1)

    assert rows == [{"project": "A", "slug": "match", "name": None, "state": None}]
    assert seen == [(PROJECTS_URL, 0), (A_REPOS, 0)]


def test_paging_continues_until_the_match_cap_is_actually_reached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = {
        (PROJECTS_URL, 0): {"values": [{"key": "A"}], "isLastPage": True},
        (A_REPOS, 0): {
            "values": [{"slug": "match"}],
            "isLastPage": False,
            "nextPageStart": 5,
        },
        (A_REPOS, 5): {
            "values": [{"slug": "other"}, {"slug": "match-two"}],
            "isLastPage": False,
            "nextPageStart": 9,
        },
    }
    seen: list[tuple[str, int]] = []

    rows = read(monkeypatch, pages, seen, limit=2)

    assert [row["slug"] for row in rows] == ["match", "match-two"]
    assert seen == [(PROJECTS_URL, 0), (A_REPOS, 0), (A_REPOS, 5)]


def test_the_project_list_is_still_read_in_full_before_the_match_cap_stops(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = {
        (PROJECTS_URL, 0): {
            "values": [{"key": "A"}],
            "isLastPage": False,
            "nextPageStart": 1,
        },
        (PROJECTS_URL, 1): {"values": [{"key": "B"}], "isLastPage": True},
        (A_REPOS, 0): {"values": [{"slug": "match"}], "isLastPage": True},
    }
    seen: list[tuple[str, int]] = []

    rows = read(monkeypatch, pages, seen, limit=1)

    assert [row["project"] for row in rows] == ["A"]
    assert seen == [(PROJECTS_URL, 0), (PROJECTS_URL, 1), (A_REPOS, 0)]


def test_a_fetched_page_is_fully_validated_before_the_match_cap_stops(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Every row of an already fetched page is projected, so a malformed tail is
    # not hidden by a match found earlier in the same page.
    pages = {
        (PROJECTS_URL, 0): {"values": [{"key": "A"}], "isLastPage": True},
        (A_REPOS, 0): {
            "values": [{"slug": "match"}, {"slug": 7}],
            "isLastPage": False,
            "nextPageStart": 100,
        },
    }
    seen: list[tuple[str, int]] = []

    with pytest.raises(AtlaWireError, match="repository"):
        read(monkeypatch, pages, seen, max_pages=2, limit=1)

    assert seen == [(PROJECTS_URL, 0), (A_REPOS, 0)]
