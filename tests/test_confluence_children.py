from contextlib import nullcontext

import pytest
from click.testing import CliRunner

from atlawire import confluence
from atlawire.cli import cli
from atlawire.http import AtlaWireError

BASE = "https://wiki.example.invalid/wiki"
CHILD_URL = f"{BASE}/rest/api/content/42/child/page"
ROW = {"id": "7", "title": "One", "version": {"number": 3}}


def children(
    monkeypatch: pytest.MonkeyPatch,
    pages: list[dict[str, object]],
    *,
    limit: int = 100,
    seen: list[dict[str, object]] | None = None,
) -> tuple[list[confluence.ChildRow], list[dict[str, object]]]:
    calls: list[dict[str, object]] = [] if seen is None else seen

    def fake_get_json_object(
        session: object, url: str, *, params: dict[str, str | int]
    ) -> dict[str, object]:
        calls.append({"url": url, **params})
        return pages[len(calls) - 1]

    monkeypatch.setattr(confluence, "bearer_session", lambda token: nullcontext(None))
    monkeypatch.setattr(confluence, "get_json_object", fake_get_json_object)
    rows = confluence.list_children(BASE, 42, token="fixture-only", limit=limit)
    return rows, calls


def test_children_request_the_fixed_expansion_and_keep_server_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = [{"results": [ROW, {"id": 8, "title": "Two"}], "start": 0, "size": 2}]

    rows, seen = children(monkeypatch, pages, limit=2)

    assert rows == [
        {"id": "7", "title": "One", "version": 3},
        {"id": 8, "title": "Two", "version": None},
    ]
    assert seen == [
        {"url": CHILD_URL, "expand": "version", "start": 0, "limit": 2},
    ]


def test_a_pasted_parent_link_supplies_only_the_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[dict[str, object]] = []

    def fake_get_json_object(
        session: object, url: str, *, params: dict[str, str | int]
    ) -> dict[str, object]:
        seen.append({"url": url, **params})
        return {"results": [ROW], "start": 0, "size": 1}

    monkeypatch.setattr(confluence, "bearer_session", lambda token: nullcontext(None))
    monkeypatch.setattr(confluence, "get_json_object", fake_get_json_object)

    rows = confluence.list_children(
        BASE,
        "https://elsewhere.invalid/display/OTHER?spaceKey=OTHER&pageId=42#part",
        token="fixture-only",
        limit=1,
    )

    assert [row["id"] for row in rows] == ["7"]
    assert seen == [
        {"url": CHILD_URL, "expand": "version", "start": 0, "limit": 1},
    ]


def test_a_capped_short_page_advances_by_the_rows_actually_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = [
        {
            "results": [ROW],
            "start": 0,
            "size": 1,
            "_links": {"next": "/rest/api/content/42/child/page?start=1&limit=99"},
        },
        {"results": [], "start": 1, "size": 0},
    ]

    rows, seen = children(monkeypatch, pages, limit=5)

    assert [row["id"] for row in rows] == ["7"]
    assert [call["start"] for call in seen] == [0, 1]
    assert [call["limit"] for call in seen] == [5, 4]


def test_zero_limit_validates_the_parent_and_base_without_a_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_session(token: str) -> object:
        raise AssertionError("No session should be created.")

    monkeypatch.setattr(confluence, "bearer_session", unexpected_session)

    assert confluence.list_children(BASE, 42, token="fixture-only", limit=0) == []
    with pytest.raises(AtlaWireError, match="pageId"):
        confluence.list_children(BASE, "0", token="fixture-only", limit=0)
    with pytest.raises(AtlaWireError, match="HTTPS"):
        confluence.list_children(
            "http://elsewhere.invalid", 42, token="fixture-only", limit=0
        )


@pytest.mark.parametrize("limit", [-1, 1001, True])
def test_invalid_child_limit_is_rejected_before_any_session(
    monkeypatch: pytest.MonkeyPatch, limit: int
) -> None:
    def unexpected_session(token: str) -> object:
        raise AssertionError("No session should be created.")

    monkeypatch.setattr(confluence, "bearer_session", unexpected_session)

    with pytest.raises(AtlaWireError):
        confluence.list_children(BASE, 42, token="fixture-only", limit=limit)


def test_the_same_child_id_is_a_repeated_page_even_with_changed_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages: list[dict[str, object]] = [
        {"results": [{"id": "7", "title": "Old", "version": {"number": 1}}]},
        {"results": [{"id": 7, "title": "New", "version": {"number": 2}}]},
    ]
    seen: list[dict[str, object]] = []

    with pytest.raises(AtlaWireError, match="repeated"):
        children(monkeypatch, pages, limit=2, seen=seen)

    assert len(seen) == 2


def test_distinct_child_ids_with_equal_titles_are_not_repeated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages: list[dict[str, object]] = [
        {"results": [{"id": "7", "title": "Same"}]},
        {"results": [{"id": "8", "title": "Same"}]},
    ]

    rows, seen = children(monkeypatch, pages, limit=2)

    assert [row["id"] for row in rows] == ["7", "8"]
    assert len(seen) == 2


def test_a_repeated_page_without_ids_falls_back_to_raw_equality(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = {"title": "Same", "version": {"number": 1}}
    pages = [
        {"results": [row], "start": 0},
        {"results": [dict(row)], "start": 1},
    ]

    with pytest.raises(AtlaWireError, match="repeated"):
        children(monkeypatch, pages, limit=2)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ({}, {"id": None, "title": None, "version": None}),
        (
            {"id": "7", "title": "", "version": None},
            {"id": "7", "title": "", "version": None},
        ),
        (
            {"id": 7, "title": "Seven", "version": {}},
            {"id": 7, "title": "Seven", "version": None},
        ),
        (
            {"id": "7", "title": "Seven", "version": {"number": None}},
            {"id": "7", "title": "Seven", "version": None},
        ),
        (
            {"id": "7", "title": "Seven", "version": {"number": 0}},
            {"id": "7", "title": "Seven", "version": 0},
        ),
        (
            {"id": "7", "version": {"number": 0, "minorEdit": True}},
            {"id": "7", "title": None, "version": 0},
        ),
    ],
    ids=[
        "all-absent",
        "explicit-null-version",
        "empty-version",
        "null-number",
        "zero-number",
        "extra-version-fields-ignored",
    ],
)
def test_child_row_projects_only_id_title_and_version_number(
    value: object, expected: confluence.ChildRow
) -> None:
    assert confluence._child_row(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        5,
        {"id": True},
        {"id": 1.5},
        {"id": ["7"]},
        {"title": 5},
        {"title": True},
        {"version": 5},
        {"version": []},
        {"version": {"number": True}},
        {"version": {"number": 1.5}},
        {"version": {"number": "1"}},
        {"version": {"number": -1}},
    ],
    ids=[
        "not-an-object",
        "boolean-id",
        "float-id",
        "list-id",
        "non-string-title",
        "boolean-title",
        "non-object-version",
        "list-version",
        "boolean-number",
        "float-number",
        "string-number",
        "negative-number",
    ],
)
def test_malformed_child_metadata_is_rejected(value: object) -> None:
    with pytest.raises(AtlaWireError, match="child page metadata"):
        confluence._child_row(value)


def test_children_help_documents_the_limit_range() -> None:
    result = CliRunner().invoke(cli, ["children", "--help"])

    assert result.exit_code == 0
    assert "0-1000" in result.output
    assert "100" in result.output
    assert "--json" in result.output
