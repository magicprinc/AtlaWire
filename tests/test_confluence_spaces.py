from contextlib import nullcontext

import pytest
from click.testing import CliRunner

from atlawire import confluence
from atlawire.cli import cli
from atlawire.http import AtlaWireError

BASE = "https://wiki.example.invalid/wiki"
SPACE_URL = f"{BASE}/rest/api/space"
ROW = {"id": 10, "key": "DEMO", "name": "Demo", "type": "global"}


def spaces(
    monkeypatch: pytest.MonkeyPatch,
    pages: list[dict[str, object]],
    *,
    limit: int = 100,
    seen: list[dict[str, object]] | None = None,
) -> tuple[list[confluence.SpaceRow], list[dict[str, object]]]:
    calls: list[dict[str, object]] = [] if seen is None else seen

    def fake_get_json_object(
        session: object, url: str, *, params: dict[str, str | int]
    ) -> dict[str, object]:
        calls.append({"url": url, **params})
        return pages[len(calls) - 1]

    monkeypatch.setattr(confluence, "bearer_session", lambda token: nullcontext(None))
    monkeypatch.setattr(confluence, "get_json_object", fake_get_json_object)
    rows = confluence.list_spaces(BASE, token="fixture-only", limit=limit)
    return rows, calls


def test_spaces_request_only_start_and_limit_and_keep_server_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = [{"results": [ROW, {"key": "OPS"}], "start": 0, "size": 2}]

    rows, seen = spaces(monkeypatch, pages, limit=2)

    assert rows == [
        {"key": "DEMO", "name": "Demo", "type": "global"},
        {"key": "OPS", "name": None, "type": None},
    ]
    assert seen == [{"url": SPACE_URL, "start": 0, "limit": 2}]


def test_a_capped_short_page_advances_by_the_rows_actually_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = [
        {
            "results": [ROW],
            "start": 0,
            "size": 1,
            "_links": {"next": "/rest/api/space?start=1&limit=99"},
        },
        {"results": [], "start": 1, "size": 0},
    ]

    rows, seen = spaces(monkeypatch, pages, limit=5)

    assert [row["key"] for row in rows] == ["DEMO"]
    assert [call["start"] for call in seen] == [0, 1]
    assert [call["limit"] for call in seen] == [5, 4]


def test_missing_space_metadata_stays_null() -> None:
    assert confluence._space_row({"id": 7, "key": "DEMO"}) == {
        "key": "DEMO",
        "name": None,
        "type": None,
    }


@pytest.mark.parametrize(
    "value",
    [
        5,
        {"key": 5},
        {"name": True},
        {"type": ["global"]},
    ],
    ids=["not-an-object", "non-string-key", "boolean-name", "list-type"],
)
def test_malformed_space_metadata_is_rejected(value: object) -> None:
    with pytest.raises(AtlaWireError, match="space metadata"):
        confluence._space_row(value)


def test_the_same_key_is_a_repeated_page_even_with_changed_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = [
        {"results": [{"key": "DEMO", "name": "Old", "type": "global"}], "start": 0},
        {"results": [{"key": "DEMO", "name": "New", "type": "global"}], "start": 1},
    ]
    seen: list[dict[str, object]] = []

    with pytest.raises(AtlaWireError, match="repeated"):
        spaces(monkeypatch, pages, limit=2, seen=seen)

    assert len(seen) == 2


def test_distinct_keys_with_equal_names_are_not_repeated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = [
        {"results": [{"key": "DEMO", "name": "Same"}], "start": 0},
        {"results": [{"key": "OPS", "name": "Same"}], "start": 1},
    ]

    rows, seen = spaces(monkeypatch, pages, limit=2)

    assert [row["key"] for row in rows] == ["DEMO", "OPS"]
    assert len(seen) == 2


def test_a_repeated_page_without_keys_falls_back_to_raw_equality(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = {"name": "Same", "type": "global"}
    pages = [
        {"results": [row], "start": 0},
        {"results": [dict(row)], "start": 1},
    ]

    with pytest.raises(AtlaWireError, match="repeated"):
        spaces(monkeypatch, pages, limit=2)


@pytest.mark.parametrize(
    "page",
    [
        {"results": [], "start": 0, "size": 0, "totalSize": 1},
        {
            "results": [],
            "start": 0,
            "size": 0,
            "_links": {"next": "/rest/api/space?start=0"},
        },
    ],
    ids=["outstanding-total", "empty-with-next"],
)
def test_a_contradictory_empty_page_is_rejected(
    monkeypatch: pytest.MonkeyPatch, page: dict[str, object]
) -> None:
    with pytest.raises(AtlaWireError, match="empty page"):
        spaces(monkeypatch, [page], limit=2)


def test_zero_limit_returns_nothing_without_a_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_session(token: str) -> object:
        raise AssertionError("No session should be created.")

    monkeypatch.setattr(confluence, "bearer_session", unexpected_session)

    assert confluence.list_spaces(BASE, token="fixture-only", limit=0) == []


@pytest.mark.parametrize("limit", [-1, 1001, True])
def test_invalid_space_limit_is_rejected_before_any_session(
    monkeypatch: pytest.MonkeyPatch, limit: int
) -> None:
    def unexpected_session(token: str) -> object:
        raise AssertionError("No session should be created.")

    monkeypatch.setattr(confluence, "bearer_session", unexpected_session)

    with pytest.raises(AtlaWireError):
        confluence.list_spaces(BASE, token="fixture-only", limit=limit)


def test_spaces_help_documents_the_limit_range() -> None:
    result = CliRunner().invoke(cli, ["spaces", "--help"])

    assert result.exit_code == 0
    assert "0-1000" in result.output
    assert "100" in result.output
    assert "--json" in result.output
