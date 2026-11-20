"""Focused checks for the indexed Bitbucket code search adapter."""

import copy
from collections.abc import Mapping
from contextlib import nullcontext
from typing import cast

import pytest

from atlawire import bitbucket_search
from atlawire.http import AtlaWireError

BASE = "https://bitbucket.example.invalid/scm"
TOKEN = "fixture-only-token"
URL = f"{BASE}/rest/search/latest/search"
MISSING = object()


def forbid_session(token: str) -> object:
    raise AssertionError("session created before validation")


def hit(
    *,
    project: str = "P",
    slug: str = "r",
    file: str = "a.py",
    hit_count: object = 1,
    contexts: object = MISSING,
) -> dict[str, object]:
    value: dict[str, object] = {
        "repository": {"project": {"key": project}, "slug": slug},
        "file": file,
    }
    if hit_count is not MISSING:
        value["hitCount"] = hit_count
    if contexts is not MISSING:
        value["hitContexts"] = contexts
    return value


def page(
    values: list[object], *, last: object = True, next_start: object = MISSING
) -> dict[str, object]:
    code: dict[str, object] = {"values": values, "isLastPage": last}
    if next_start is not MISSING:
        code["nextStart"] = next_start
    return {"code": code}


def run_search(
    monkeypatch: pytest.MonkeyPatch,
    pages: Mapping[int, object],
    seen: list[tuple[str, dict[str, object]]],
    *,
    query: str = "Needle",
    project: str | None = None,
    repo: str | None = None,
    limit: int = 20,
    every_page: bool = False,
) -> list[bitbucket_search.SearchRow]:
    def fake_post_json_object(
        session: object, url: str, *, body: dict[str, object]
    ) -> dict[str, object]:
        entities = cast(dict[str, object], body["entities"])
        code = cast(dict[str, object], entities["code"])
        start = cast(int, code["start"])
        if start not in pages:
            raise AssertionError("Unexpected extra Bitbucket search request.")
        seen.append((url, copy.deepcopy(body)))
        result = pages[start]
        if isinstance(result, Exception):
            raise result
        return cast(dict[str, object], result)

    monkeypatch.setattr(
        bitbucket_search, "bearer_session", lambda token: nullcontext(None)
    )
    monkeypatch.setattr(bitbucket_search, "post_json_object", fake_post_json_object)
    return bitbucket_search.search_code(
        BASE,
        query,
        project=project,
        repo=repo,
        limit=limit,
        every_page=every_page,
        token=TOKEN,
    )


def run_scoped(
    monkeypatch: pytest.MonkeyPatch,
    pages: Mapping[int, object],
    seen: list[tuple[str, dict[str, object]]],
    scope: Mapping[str, str],
    *,
    query: str = "Needle",
) -> list[bitbucket_search.SearchRow]:
    return run_search(
        monkeypatch,
        pages,
        seen,
        query=query,
        project=scope.get("project"),
        repo=scope.get("repo"),
    )


@pytest.mark.parametrize(
    ("scope", "effective"),
    [
        ({}, "q"),
        ({"project": "P"}, "project:P q"),
        ({"project": "~alice"}, "project:~alice q"),
        ({"repo": "P/r"}, "project:P repo:r q"),
    ],
    ids=["unscoped", "project", "user-project", "repository"],
)
def test_normal_mode_posts_one_fixed_route_with_exact_scope_and_query(
    monkeypatch: pytest.MonkeyPatch,
    scope: dict[str, str],
    effective: str,
) -> None:
    seen: list[tuple[str, dict[str, object]]] = []
    pages = {0: {"code": {"values": []}}}

    assert run_scoped(monkeypatch, pages, seen, scope, query="q") == []
    assert seen == [
        (
            URL,
            {"query": effective, "entities": {"code": {"start": 0, "limit": 20}}},
        )
    ]


def test_rows_mark_only_raw_paired_emphasis_and_decode_entities_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marked_text = "def <em>naïve</em>(x): # &amp; &lt;em&gt;literal&lt;/em&gt;"
    literal_text = "&lt;em&gt;literal&lt;/em&gt;"
    pages = {
        0: page(
            [
                hit(
                    file="a.py",
                    hit_count=2,
                    contexts=[
                        [{"line": 4, "text": marked_text}],
                        [{"line": None, "text": None}, {"line": 7}],
                    ],
                ),
                hit(
                    file="b.py",
                    hit_count=MISSING,
                    contexts=[[{"line": 1, "text": literal_text}]],
                ),
                hit(file="c.py", hit_count=0, contexts=MISSING),
            ]
        )
    }
    seen: list[tuple[str, dict[str, object]]] = []

    rows = run_search(monkeypatch, pages, seen)

    assert rows == [
        {
            "project": "P",
            "repository": "r",
            "file": "a.py",
            "hitCount": 2,
            "matchEvidence": "highlight",
            "hits": [{"line": 4, "text": "def naïve(x): # & <em>literal</em>"}],
            "context": [
                [{"line": 4, "text": "def naïve(x): # & <em>literal</em>"}],
                [{"line": None, "text": ""}, {"line": 7, "text": ""}],
            ],
        },
        {
            "project": "P",
            "repository": "r",
            "file": "b.py",
            "hitCount": None,
            "matchEvidence": "context-only",
            "hits": [],
            "context": [[{"line": 1, "text": "<em>literal</em>"}]],
        },
        {
            "project": "P",
            "repository": "r",
            "file": "c.py",
            "hitCount": 0,
            "matchEvidence": "none",
            "hits": [],
            "context": [],
        },
    ]


@pytest.mark.parametrize(
    ("scope", "row", "accepted"),
    [
        ({"project": "P"}, {"project": "p", "slug": "r"}, True),
        ({"project": "P"}, {"project": "Q", "slug": "r"}, False),
        ({"repo": "P/r"}, {"project": "p", "slug": "R"}, True),
        ({"repo": "P/r"}, {"project": "P", "slug": "other"}, False),
        ({"repo": "P/r"}, {"project": "Q", "slug": "r"}, False),
    ],
    ids=[
        "project-case",
        "project-mismatch",
        "repo-case",
        "slug-mismatch",
        "key-mismatch",
    ],
)
def test_explicit_scope_is_never_broadened(
    monkeypatch: pytest.MonkeyPatch,
    scope: dict[str, str],
    row: dict[str, str],
    accepted: bool,
) -> None:
    seen: list[tuple[str, dict[str, object]]] = []
    pages = {0: page([hit(project=row["project"], slug=row["slug"])])}

    if accepted:
        rows = run_scoped(monkeypatch, pages, seen, scope)
        assert rows[0]["project"] == row["project"]
        assert rows[0]["repository"] == row["slug"]
    else:
        with pytest.raises(AtlaWireError, match="outside the requested scope"):
            run_scoped(monkeypatch, pages, seen, scope)


def test_all_follows_a_noncontiguous_cursor_and_reuses_the_remaining_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = {
        0: page([hit(file="a.py"), hit(file="b.py")], last=False, next_start=17),
        17: page([hit(file="c.py")], last=True),
    }
    seen: list[tuple[str, dict[str, object]]] = []

    rows = run_search(
        monkeypatch,
        pages,
        seen,
        query="naïve  two",
        repo="P/r",
        limit=5,
        every_page=True,
    )

    assert [row["file"] for row in rows] == ["a.py", "b.py", "c.py"]
    assert [(body["entities"], body["query"]) for _, body in seen] == [
        ({"code": {"start": 0, "limit": 5}}, "project:P repo:r naïve  two"),
        ({"code": {"start": 17, "limit": 3}}, "project:P repo:r naïve  two"),
    ]


def test_all_stops_at_the_row_cap_without_reading_an_unused_cursor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[tuple[str, dict[str, object]]] = []
    pages = {0: page([hit(file="a.py"), hit(file="b.py")], last=False, next_start=True)}

    rows = run_search(monkeypatch, pages, seen, limit=2, every_page=True)

    assert len(rows) == 2
    assert len(seen) == 1


@pytest.mark.parametrize(
    "last",
    [MISSING, "false", 0, None],
    ids=["missing", "string", "integer", "null"],
)
def test_all_validates_the_terminal_flag_even_at_the_row_cap(
    monkeypatch: pytest.MonkeyPatch, last: object
) -> None:
    code: dict[str, object] = {
        "values": [hit(file="a.py"), hit(file="b.py")],
        "nextStart": True,
    }
    if last is not MISSING:
        code["isLastPage"] = last
    seen: list[tuple[str, dict[str, object]]] = []

    with pytest.raises(AtlaWireError, match="isLastPage"):
        run_search(monkeypatch, {0: {"code": code}}, seen, limit=2, every_page=True)

    assert len(seen) == 1


def test_unmatched_emphasis_openers_stay_literal() -> None:
    raw = "<em>" * 1000 + "tail"

    assert bitbucket_search._decode_line(raw) == (raw, False)
    assert bitbucket_search._decode_line("<em>hit</em><em>tail") == (
        "hit<em>tail",
        True,
    )


def test_an_excessive_character_reference_is_sanitized() -> None:
    with pytest.raises(AtlaWireError, match="character reference"):
        bitbucket_search._decode_line("&#" + "9" * 5000 + ";")


@pytest.mark.parametrize(
    "code",
    [
        {"values": [], "isLastPage": "false"},
        {"values": [], "isLastPage": 0},
        {"values": []},
        {"values": [], "isLastPage": False, "nextStart": True},
        {"values": [], "isLastPage": False, "nextStart": 0},
        {"values": [], "isLastPage": False, "nextStart": -1},
        {"values": [], "isLastPage": False, "nextStart": "17"},
        {"values": [], "isLastPage": False, "nextStart": 1.5},
    ],
    ids=[
        "string-terminal",
        "zero-terminal",
        "missing-terminal",
        "boolean-cursor",
        "repeat-cursor",
        "negative-cursor",
        "string-cursor",
        "float-cursor",
    ],
)
def test_all_rejects_a_malformed_terminal_flag_or_cursor(
    monkeypatch: pytest.MonkeyPatch, code: dict[str, object]
) -> None:
    seen: list[tuple[str, dict[str, object]]] = []

    with pytest.raises(AtlaWireError, match="isLastPage|nextStart"):
        run_search(monkeypatch, {0: {"code": code}}, seen, every_page=True)

    assert len(seen) == 1


def test_all_uses_at_most_twenty_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    pages = {start: page([], last=False, next_start=start + 1) for start in range(20)}
    seen: list[tuple[str, dict[str, object]]] = []

    with pytest.raises(AtlaWireError, match="page budget"):
        run_search(monkeypatch, pages, seen, limit=999, every_page=True)

    assert len(seen) == 20


def test_a_page_wider_than_the_remaining_window_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[tuple[str, dict[str, object]]] = []
    pages = {0: page([hit(file="a"), hit(file="b"), hit(file="c")])}

    with pytest.raises(AtlaWireError, match="more rows than requested"):
        run_search(monkeypatch, pages, seen, limit=2)


@pytest.mark.parametrize("limit", [1, 999])
def test_boundary_limits_are_accepted(
    monkeypatch: pytest.MonkeyPatch, limit: int
) -> None:
    seen: list[tuple[str, dict[str, object]]] = []

    assert run_search(monkeypatch, {0: page([])}, seen, limit=limit) == []
    assert seen[0][1]["entities"] == {"code": {"start": 0, "limit": min(100, limit)}}


def malformed(value: dict[str, object]) -> dict[str, object]:
    return {"code": {"values": [value], "isLastPage": True}}


@pytest.mark.parametrize(
    "response",
    [
        {"values": []},
        {"code": []},
        {"code": {"isLastPage": True}},
        {"code": {"values": {}, "isLastPage": True}},
        {"code": {"values": ["not an object"], "isLastPage": True}},
        {"code": {"values": [{}], "isLastPage": True}},
        malformed({"repository": [], "file": "a.py"}),
        malformed({"repository": {"slug": "r"}, "file": "a.py"}),
        malformed({"repository": {"project": [], "slug": "r"}, "file": "a.py"}),
        malformed(
            {"repository": {"project": {"key": "A/B"}, "slug": "r"}, "file": "a.py"}
        ),
        malformed(
            {"repository": {"project": {"key": ""}, "slug": "r"}, "file": "a.py"}
        ),
        malformed({"repository": {"project": {"key": "P"}, "slug": ".."}, "file": "a"}),
        malformed({"repository": {"project": {"key": "P"}}, "file": "a.py"}),
        malformed({"repository": {"project": {"key": "P"}, "slug": "r"}}),
        malformed({"repository": {"project": {"key": "P"}, "slug": "r"}, "file": ""}),
        malformed({"repository": {"project": {"key": "P"}, "slug": "r"}, "file": 7}),
        malformed(
            {
                "repository": {"project": {"key": "P"}, "slug": "r"},
                "file": "a.py",
                "hitCount": -1,
            }
        ),
        malformed(
            {
                "repository": {"project": {"key": "P"}, "slug": "r"},
                "file": "a.py",
                "hitCount": True,
            }
        ),
        malformed(
            {
                "repository": {"project": {"key": "P"}, "slug": "r"},
                "file": "a.py",
                "hitCount": 1.5,
            }
        ),
        malformed(
            {
                "repository": {"project": {"key": "P"}, "slug": "r"},
                "file": "a.py",
                "hitContexts": {},
            }
        ),
        malformed(
            {
                "repository": {"project": {"key": "P"}, "slug": "r"},
                "file": "a.py",
                "hitContexts": [{}],
            }
        ),
        malformed(
            {
                "repository": {"project": {"key": "P"}, "slug": "r"},
                "file": "a.py",
                "hitContexts": [[{"line": -1, "text": "x"}]],
            }
        ),
        malformed(
            {
                "repository": {"project": {"key": "P"}, "slug": "r"},
                "file": "a.py",
                "hitContexts": [[{"line": True, "text": "x"}]],
            }
        ),
        malformed(
            {
                "repository": {"project": {"key": "P"}, "slug": "r"},
                "file": "a.py",
                "hitContexts": [[{"line": "4", "text": "x"}]],
            }
        ),
        malformed(
            {
                "repository": {"project": {"key": "P"}, "slug": "r"},
                "file": "a.py",
                "hitContexts": [[{"line": 1, "text": 3}]],
            }
        ),
        malformed(
            {
                "repository": {"project": {"key": "P"}, "slug": "r"},
                "file": "a.py",
                "hitContexts": [["not an object"]],
            }
        ),
        malformed(
            {
                "repository": {"project": {"key": "P"}, "slug": "r"},
                "file": "a.py",
                "hitContexts": [[{"line": 1, "text": "\ud800"}]],
            }
        ),
        malformed(
            {
                "repository": {"project": {"key": "P"}, "slug": "r"},
                "file": "\ud800",
            }
        ),
    ],
)
def test_malformed_consumed_shapes_are_rejected(
    monkeypatch: pytest.MonkeyPatch, response: dict[str, object]
) -> None:
    seen: list[tuple[str, dict[str, object]]] = []

    with pytest.raises(AtlaWireError):
        run_search(monkeypatch, {0: response}, seen)


@pytest.mark.parametrize(
    "overrides",
    [
        {"query": ""},
        {"query": " \t\n"},
        {"query": "\ud800"},
        {"query": 5},
        {"project": "A", "repo": "A/r"},
        {"project": ""},
        {"project": "A/B"},
        {"project": "../A"},
        {"project": 5},
        {"repo": ""},
        {"repo": "A"},
        {"repo": "A/B/C"},
        {"repo": "A/.."},
        {"repo": "/r"},
        {"repo": 5},
        {"limit": 0},
        {"limit": 1000},
        {"limit": True},
        {"limit": 1.5},
        {"limit": "20"},
        {"every_page": "yes"},
    ],
    ids=[
        "empty-query",
        "blank-query",
        "surrogate-query",
        "non-string-query",
        "both-scopes",
        "empty-project",
        "path-project",
        "parent-project",
        "non-string-project",
        "empty-repo",
        "missing-slug",
        "extra-segment",
        "parent-slug",
        "empty-project-segment",
        "non-string-repo",
        "zero-limit",
        "large-limit",
        "boolean-limit",
        "float-limit",
        "string-limit",
        "non-boolean-paging",
    ],
)
def test_invalid_input_is_rejected_before_any_session(
    monkeypatch: pytest.MonkeyPatch, overrides: dict[str, object]
) -> None:
    monkeypatch.setattr(bitbucket_search, "bearer_session", forbid_session)
    arguments: dict[str, object] = {"query": "q", "token": TOKEN, **overrides}
    query = cast(str, arguments.pop("query"))

    with pytest.raises(AtlaWireError):
        bitbucket_search.search_code(BASE, query, **arguments)  # type: ignore[arg-type]


def test_normal_mode_ignores_paging_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[tuple[str, dict[str, object]]] = []
    pages = {0: {"code": {"values": [], "isLastPage": "false", "nextStart": True}}}

    assert run_search(monkeypatch, pages, seen) == []
    assert len(seen) == 1
