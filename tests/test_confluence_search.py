from contextlib import nullcontext

import pytest
from click.testing import CliRunner

from atlawire import confluence
from atlawire.cli import cli
from atlawire.http import AtlaWireError

BASE = "https://wiki.example.invalid/wiki"
QUERY = 'space = DEMO AND text ~ "Résumé"'
ROW = {"content": {"id": "1", "type": "page", "title": "One", "space": {"key": "DEMO"}}}
BACKGROUND = {
    "content": {"id": "2", "type": "page", "title": "Two", "space": {"key": "OPS"}}
}


def search(
    monkeypatch: pytest.MonkeyPatch,
    pages: list[dict[str, object]],
    *,
    limit: int = 25,
    fail_at: int | None = None,
    seen: list[dict[str, object]] | None = None,
) -> tuple[list[confluence.ContentRow], list[dict[str, object]]]:
    calls: list[dict[str, object]] = [] if seen is None else seen

    def fake_get_json_object(
        session: object, url: str, *, params: dict[str, str | int]
    ) -> dict[str, object]:
        if fail_at is not None and len(calls) == fail_at:
            raise AtlaWireError("HTTP 503: request failed.")
        calls.append({"url": url, **params})
        return pages[len(calls) - 1]

    monkeypatch.setattr(confluence, "bearer_session", lambda token: nullcontext(None))
    monkeypatch.setattr(confluence, "get_json_object", fake_get_json_object)
    rows = confluence.search_cql(BASE, QUERY, token="fixture-only", limit=limit)
    return rows, calls


def test_content_values_win_over_top_level_fallbacks() -> None:
    row = confluence._content_row(
        {
            "content": {
                "id": "101",
                "space": {"key": "DEMO"},
                "type": "page",
                "title": "Content title",
                "_links": {"webui": "/content-link"},
            },
            "id": "999",
            "space": {"key": "OTHER"},
            "type": "blogpost",
            "title": "Top title",
            "url": "/top-url",
            "_links": {"webui": "/item-link"},
        }
    )

    assert row == {
        "id": "101",
        "space": "DEMO",
        "type": "page",
        "title": "Content title",
        "url": "/item-link",
    }


def test_explicit_empty_content_text_wins_over_a_top_level_fallback() -> None:
    row = confluence._content_row({"content": {"title": ""}, "title": "Top"})

    assert row["title"] == ""


@pytest.mark.parametrize(
    ("item", "url"),
    [
        ({"url": "/top-url", "content": {"_links": {"webui": "/content"}}}, "/top-url"),
        ({"content": {"_links": {"webui": "/content"}}}, "/content"),
        ({"content": {"id": "1"}, "url": None}, None),
    ],
    ids=["documented-url-before-content-link", "content-link", "no-link"],
)
def test_url_uses_item_link_then_item_url_then_content_link(
    item: dict[str, object], url: str | None
) -> None:
    assert confluence._content_row(item)["url"] == url


def test_missing_metadata_stays_null_and_integer_id_is_kept() -> None:
    row = confluence._content_row(
        {"content": {}, "id": 202, "space": {"name": "no key"}}
    )

    assert row == {
        "id": 202,
        "space": None,
        "type": None,
        "title": None,
        "url": None,
    }


@pytest.mark.parametrize(
    ("path", "space"),
    [("/rest/api/space/OPS", "OPS"), ("/rest/api/space/OPS/", None), ("", None)],
    ids=["terminal", "trailing-slash", "empty"],
)
def test_space_falls_back_to_the_expandable_path_terminal_segment(
    path: str, space: str | None
) -> None:
    row = confluence._content_row(
        {"content": {}, "id": "1", "_expandable": {"space": path}}
    )

    assert row["space"] == space


@pytest.mark.parametrize(
    "item",
    [
        {"content": 5},
        {"content": {"id": True}},
        {"content": {"id": 1.5}},
        {"content": {"title": 5}},
        {"content": {"space": "DEMO"}},
        {"content": {"space": {"key": 5}}},
        {"content": {"_links": []}},
        {"content": {"_links": {"webui": 5}}},
        {"_links": []},
        {"_links": {"webui": 5}},
        {"url": 5},
        {"space": {"key": 5}},
        {"_expandable": []},
        {"_expandable": {"space": 5}},
    ],
    ids=[
        "content-not-object",
        "boolean-content-id",
        "float-content-id",
        "non-string-content-title",
        "content-space-not-object",
        "non-string-content-space-key",
        "content-links-not-object",
        "non-string-content-webui",
        "item-links-not-object",
        "non-string-item-webui",
        "non-string-item-url",
        "non-string-item-space-key",
        "expandable-not-object",
        "non-string-expandable-space",
    ],
)
def test_malformed_result_shapes_are_rejected(item: dict[str, object]) -> None:
    with pytest.raises(AtlaWireError, match="content metadata"):
        confluence._content_row(item)


@pytest.mark.parametrize(
    ("case", "value", "message"),
    [
        ("missing-results", {"start": 0, "size": 0}, "results"),
        ("results-not-list", {"results": {}, "start": 0, "size": 0}, "results"),
        ("results-not-objects", {"results": [1], "start": 0, "size": 1}, "results"),
        (
            "oversized-results",
            {"results": [ROW, ROW], "start": 0, "size": 2},
            "more results",
        ),
        ("mismatched-start", {"results": [], "start": 1, "size": 0}, "start"),
        ("boolean-start", {"results": [], "start": True, "size": 0}, "start"),
        ("string-start", {"results": [], "start": "0", "size": 0}, "start"),
        ("mismatched-size", {"results": [ROW], "start": 0, "size": 2}, "size"),
        ("boolean-size", {"results": [ROW], "start": 0, "size": True}, "size"),
        (
            "negative-total",
            {"results": [], "start": 0, "size": 0, "totalSize": -1},
            "totalSize",
        ),
        (
            "boolean-total",
            {"results": [ROW], "start": 0, "size": 1, "totalSize": True},
            "totalSize",
        ),
        (
            "string-total",
            {"results": [ROW], "start": 0, "size": 1, "totalSize": "1"},
            "totalSize",
        ),
        (
            "links-not-object",
            {"results": [ROW], "start": 0, "size": 1, "_links": []},
            "links",
        ),
        (
            "null-links",
            {"results": [ROW], "start": 0, "size": 1, "_links": None},
            "links",
        ),
        (
            "empty-with-outstanding-total",
            {"results": [], "start": 0, "size": 0, "totalSize": 1},
            "empty page",
        ),
        (
            "empty-with-next",
            {
                "results": [],
                "start": 0,
                "size": 0,
                "_links": {"next": "/rest/api/search?start=0"},
            },
            "empty page",
        ),
    ],
    ids=[
        "missing-results",
        "results-not-list",
        "results-not-objects",
        "oversized-results",
        "mismatched-start",
        "boolean-start",
        "string-start",
        "mismatched-size",
        "boolean-size",
        "negative-total",
        "boolean-total",
        "string-total",
        "links-not-object",
        "null-links",
        "empty-with-outstanding-total",
        "empty-with-next",
    ],
)
def test_malformed_page_metadata_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    case: str,
    value: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(AtlaWireError, match=message):
        search(monkeypatch, [value], limit=1)


@pytest.mark.parametrize(
    ("link", "message"),
    [
        (5, "continuation"),
        ("/rest/api/search?cql=x", "continuation offset"),
        ("/rest/api/search?start=2", "continuation offset"),
        ("/rest/api/search?start=1&start=1", "continuation offset"),
        ("/rest/api/search?start=01", "continuation offset"),
        ("/rest/api/search?start=", "continuation offset"),
        ("http://[::1/rest/api/search?start=1", "continuation"),
    ],
    ids=[
        "non-string",
        "missing-start",
        "wrong-start",
        "duplicate-start",
        "non-canonical-start",
        "blank-start",
        "unparsable",
    ],
)
def test_bad_continuation_links_are_rejected(
    monkeypatch: pytest.MonkeyPatch, link: object, message: str
) -> None:
    page = {
        "results": [ROW],
        "start": 0,
        "size": 1,
        "_links": {"next": link},
    }

    with pytest.raises(AtlaWireError, match=message):
        search(monkeypatch, [page], limit=3)


@pytest.mark.parametrize(
    "link",
    [" /rest/api/search?start=1", "/rest/api/search?start=\t1"],
    ids=["leading-space", "embedded-tab"],
)
def test_raw_whitespace_in_a_used_next_hint_is_rejected(
    monkeypatch: pytest.MonkeyPatch, link: str
) -> None:
    pages = [
        {"results": [ROW], "start": 0, "size": 1, "_links": {"next": link}},
        {"results": [BACKGROUND], "start": 1, "size": 1, "totalSize": 2},
    ]

    with pytest.raises(AtlaWireError, match="continuation link"):
        search(monkeypatch, pages, limit=2)


def test_percent_encoded_next_offset_is_still_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = [
        {
            "results": [ROW],
            "start": 0,
            "size": 1,
            "_links": {"next": "/rest/api/search?start=%31"},
        },
        {"results": [BACKGROUND], "start": 1, "size": 1, "totalSize": 2},
    ]

    rows, seen = search(monkeypatch, pages, limit=2)

    assert [row["id"] for row in rows] == ["1", "2"]
    assert seen[1]["start"] == 1


def test_raw_whitespace_in_an_unused_next_hint_is_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = [
        {
            "results": [ROW, BACKGROUND],
            "start": 0,
            "size": 2,
            "_links": {"next": " /rest/api/search?start=2"},
        }
    ]

    rows, seen = search(monkeypatch, pages, limit=2)

    assert [row["id"] for row in rows] == ["1", "2"]
    assert len(seen) == 1


def test_short_page_without_a_next_link_continues_by_consumed_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = [
        {"results": [ROW], "start": 0, "size": 1},
        {"results": [BACKGROUND], "start": 1, "size": 1},
    ]

    rows, seen = search(monkeypatch, pages, limit=2)

    assert [row["id"] for row in rows] == ["1", "2"]
    assert seen == [
        {"url": f"{BASE}/rest/api/search", "cql": QUERY, "start": 0, "limit": 2},
        {"url": f"{BASE}/rest/api/search", "cql": QUERY, "start": 1, "limit": 1},
    ]


def test_absolute_next_link_is_only_an_offset_hint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = [
        {
            "results": [ROW],
            "start": 0,
            "size": 1,
            "_links": {
                "next": "http://127.0.0.1:1/rest/api/space?cql=other&start=1&limit=99"
            },
        },
        {"results": [BACKGROUND], "start": 1, "size": 1, "totalSize": 2},
    ]

    rows, seen = search(monkeypatch, pages, limit=2)

    assert [row["id"] for row in rows] == ["1", "2"]
    assert seen[1] == {
        "url": f"{BASE}/rest/api/search",
        "cql": QUERY,
        "start": 1,
        "limit": 1,
    }


def test_exact_cap_ignores_the_unused_continuation_link(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = [
        {"results": [ROW], "start": 0, "size": 1},
        {
            "results": [BACKGROUND],
            "start": 1,
            "size": 1,
            "_links": {"next": "/rest/api/search?cursor=ignored"},
        },
    ]

    rows, seen = search(monkeypatch, pages, limit=2)

    assert [row["id"] for row in rows] == ["1", "2"]
    assert len(seen) == 2


@pytest.mark.parametrize(
    "pages",
    [
        [{"results": [], "start": 0, "size": 0}],
        [{"results": [], "start": 0, "size": 0, "totalSize": 0}],
        [
            {"results": [ROW], "start": 0, "size": 1},
            {"results": [], "start": 1, "size": 0, "totalSize": 1},
        ],
    ],
    ids=["no-total", "zero-total", "total-equal-to-offset"],
)
def test_a_valid_empty_page_is_terminal(
    monkeypatch: pytest.MonkeyPatch, pages: list[dict[str, object]]
) -> None:
    rows, seen = search(monkeypatch, pages, limit=25)

    assert len(rows) == len(pages) - 1
    assert len(seen) == len(pages)


def test_repeated_results_are_rejected_even_when_the_envelope_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = [
        {"results": [ROW], "start": 0, "size": 1},
        {"results": [dict(ROW)], "start": 1, "size": 1, "totalSize": 10},
    ]

    with pytest.raises(AtlaWireError, match="repeated"):
        search(monkeypatch, pages, limit=2)


def nested_rows(
    ids: list[str | int], *, note: str, title: str = "Same title"
) -> list[dict[str, object]]:
    return [
        {
            "content": {
                "id": content_id,
                "type": "page",
                "title": title,
                "space": {"key": "DEMO"},
            },
            "excerpt": note,
            "friendly": {"note": note},
        }
        for content_id in ids
    ]


@pytest.mark.parametrize(
    ("first_ids", "second_ids"),
    [(["101", "102"], ["101", "102"]), ([101, 102], ["101", "102"])],
    ids=["same-text-ids", "integer-versus-text-ids"],
)
def test_repeated_nested_content_ids_are_rejected_despite_changed_metadata(
    monkeypatch: pytest.MonkeyPatch,
    first_ids: list[str | int],
    second_ids: list[str | int],
) -> None:
    pages = [
        {
            "results": nested_rows(first_ids, note="first", title="First title"),
            "start": 0,
            "size": 2,
        },
        {
            "results": nested_rows(second_ids, note="second", title="Second title"),
            "start": 2,
            "size": 2,
        },
    ]
    seen: list[dict[str, object]] = []

    with pytest.raises(AtlaWireError, match="repeated"):
        search(monkeypatch, pages, limit=4, seen=seen)

    assert len(seen) == 2


def test_distinct_nested_content_ids_are_not_repeated_even_with_equal_titles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = [
        {"results": nested_rows(["101", "102"], note="first"), "start": 0, "size": 2},
        {"results": nested_rows(["201", "202"], note="first"), "start": 2, "size": 2},
    ]

    rows, seen = search(monkeypatch, pages, limit=4)

    assert [row["id"] for row in rows] == ["101", "102", "201", "202"]
    assert len(seen) == 2


def test_repeated_page_without_nested_ids_falls_back_to_raw_equality(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = {"id": "1", "type": "page", "title": "Top", "space": {"key": "DEMO"}}
    pages = [
        {"results": [row], "start": 0, "size": 1},
        {"results": [dict(row)], "start": 1, "size": 1, "totalSize": 2},
    ]

    with pytest.raises(AtlaWireError, match="repeated"):
        search(monkeypatch, pages, limit=2)


def test_a_later_request_failure_raises_instead_of_returning_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = [{"results": [ROW], "start": 0, "size": 1}]

    with pytest.raises(AtlaWireError, match="HTTP 503"):
        search(monkeypatch, pages, limit=2, fail_at=1)


def test_zero_limit_returns_nothing_without_a_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_session(token: str) -> object:
        raise AssertionError("No session should be created.")

    monkeypatch.setattr(confluence, "bearer_session", unexpected_session)

    assert confluence.search_cql(BASE, QUERY, token="fixture-only", limit=0) == []


@pytest.mark.parametrize(
    ("query", "limit"),
    [("", 25), ("   ", 25), (QUERY, -1), (QUERY, 1001), (QUERY, True)],
)
def test_invalid_query_or_limit_is_rejected_before_any_session(
    monkeypatch: pytest.MonkeyPatch, query: str, limit: int
) -> None:
    def unexpected_session(token: str) -> object:
        raise AssertionError("No session should be created.")

    monkeypatch.setattr(confluence, "bearer_session", unexpected_session)

    with pytest.raises(AtlaWireError):
        confluence.search_cql(BASE, query, token="fixture-only", limit=limit)


def test_cql_help_documents_the_limit_range() -> None:
    result = CliRunner().invoke(cli, ["cql", "--help"])

    assert result.exit_code == 0
    assert "0-1000" in result.output
    assert "--json" in result.output
