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
    return bitbucket.find_repositories(BASE, "match", token=TOKEN, max_pages=max_pages)


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
