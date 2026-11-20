from contextlib import nullcontext
from typing import cast

import pytest

from atlawire import bitbucket
from atlawire.http import AtlaWireError

BASE = "https://bitbucket.example.invalid/scm"
PROJECTS_URL = f"{BASE}/rest/api/1.0/projects"
TOKEN = "fixture-only-token"
FIRST = {
    "key": "DEMO",
    "name": "Demo",
    "description": "First project",
    "public": False,
    "type": "NORMAL",
    "id": 1,
    "links": {
        "self": [{"href": "relative/self?x=1#frag"}, {"href": "ignored"}],
        "html": {"href": "ignored"},
    },
}
EXPECTED_FIRST = {
    "key": "DEMO",
    "name": "Demo",
    "public": False,
    "description": "First project",
    "url": "relative/self?x=1#frag",
}
SECOND = {"key": "OPS"}
EXPECTED_SECOND = {
    "key": "OPS",
    "name": None,
    "public": None,
    "description": None,
    "url": None,
}


def read(
    monkeypatch: pytest.MonkeyPatch,
    pages: list[dict[str, object]],
    *,
    max_pages: int = 100,
) -> tuple[list[bitbucket.Project], list[dict[str, object]]]:
    calls: list[dict[str, object]] = []

    def fake_get_json_object(
        session: object, url: str, *, params: dict[str, str | int]
    ) -> dict[str, object]:
        calls.append({"url": url, **params})
        return pages[len(calls) - 1]

    monkeypatch.setattr(bitbucket, "bearer_session", lambda token: nullcontext(None))
    monkeypatch.setattr(bitbucket, "get_json_object", fake_get_json_object)
    rows = bitbucket.list_projects(BASE, token=TOKEN, max_pages=max_pages)
    return rows, calls


def test_projects_use_the_fixed_endpoint_and_follow_next_page_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = [
        {"values": [FIRST], "isLastPage": False, "nextPageStart": 17},
        {"values": [SECOND], "isLastPage": True},
    ]

    rows, calls = read(monkeypatch, pages)

    assert rows == [EXPECTED_FIRST, EXPECTED_SECOND]
    assert calls == [
        {"url": PROJECTS_URL, "start": 0, "limit": 100},
        {"url": PROJECTS_URL, "start": 17, "limit": 100},
    ]


def test_an_empty_last_page_is_a_valid_terminal_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = [
        {"values": [FIRST], "isLastPage": False, "nextPageStart": 3},
        {"values": [], "isLastPage": True},
    ]

    rows, calls = read(monkeypatch, pages)

    assert rows == [EXPECTED_FIRST]
    assert [call["start"] for call in calls] == [0, 3]


def test_a_last_page_fits_a_cap_of_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = [{"values": [], "isLastPage": True}]

    rows, calls = read(monkeypatch, pages, max_pages=1)

    assert rows == []
    assert calls == [{"url": PROJECTS_URL, "start": 0, "limit": 100}]


def test_a_cap_reached_on_a_nonlast_page_is_an_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = [{"values": [FIRST], "isLastPage": False, "nextPageStart": 17}]

    with pytest.raises(AtlaWireError, match="page limit"):
        read(monkeypatch, pages, max_pages=1)


@pytest.mark.parametrize("max_pages", [0, 1001, True, 1.5])
def test_page_limit_requires_an_integer_within_range(
    monkeypatch: pytest.MonkeyPatch, max_pages: object
) -> None:
    def forbidden_session(token: str) -> object:
        raise AssertionError("session created before page-limit validation")

    monkeypatch.setattr(bitbucket, "bearer_session", forbidden_session)
    with pytest.raises(AtlaWireError, match="page limit"):
        bitbucket.list_projects(BASE, token=TOKEN, max_pages=cast(int, max_pages))


@pytest.mark.parametrize(
    ("page", "message"),
    [
        ({"isLastPage": True}, "values array"),
        ({"values": {}, "isLastPage": True}, "values array"),
        ({"values": [], "isLastPage": "true"}, "isLastPage"),
        ({"values": [], "isLastPage": None}, "isLastPage"),
    ],
)
def test_malformed_page_envelope_is_rejected(
    monkeypatch: pytest.MonkeyPatch, page: dict[str, object], message: str
) -> None:
    with pytest.raises(AtlaWireError, match=message):
        read(monkeypatch, [page])


@pytest.mark.parametrize("next_start", [-1, 0, True, "17", None, 0.5])
def test_noninteger_or_nonadvancing_cursor_is_rejected(
    monkeypatch: pytest.MonkeyPatch, next_start: object
) -> None:
    page = {"values": [FIRST], "isLastPage": False, "nextPageStart": next_start}

    with pytest.raises(AtlaWireError, match="nextPageStart"):
        read(monkeypatch, [page])


@pytest.mark.parametrize(
    "row",
    [
        None,
        "project",
        {},
        {"key": ""},
        {"key": 7},
        {"key": "DEMO", "name": False},
        {"key": "DEMO", "description": 3},
        {"key": "DEMO", "public": 0},
        {"key": "DEMO", "public": 1},
        {"key": "DEMO", "public": "false"},
    ],
)
def test_invalid_consumed_fields_are_rejected(
    monkeypatch: pytest.MonkeyPatch, row: object
) -> None:
    page = {"values": [row], "isLastPage": True}

    with pytest.raises(AtlaWireError):
        read(monkeypatch, [page])


@pytest.mark.parametrize(
    ("row", "expected_url"),
    [
        ({"key": "DEMO"}, None),
        ({"key": "DEMO", "links": None}, None),
        ({"key": "DEMO", "links": {}}, None),
        ({"key": "DEMO", "links": {"self": None}}, None),
        ({"key": "DEMO", "links": {"self": []}}, None),
        ({"key": "DEMO", "links": {"self": [{}]}}, None),
        ({"key": "DEMO", "links": {"self": [{"href": None}]}}, None),
        ({"key": "DEMO", "links": {"self": [{"href": ""}]}}, ""),
    ],
)
def test_absent_or_null_self_metadata_yields_null_and_empty_href_is_preserved(
    monkeypatch: pytest.MonkeyPatch, row: dict[str, object], expected_url: str | None
) -> None:
    page = {"values": [row], "isLastPage": True}

    rows, _ = read(monkeypatch, [page])

    assert rows[0]["url"] == expected_url


@pytest.mark.parametrize(
    "links",
    [
        "http://127.0.0.1:1/secret",
        {"self": "http://127.0.0.1:1/secret"},
        {"self": [None]},
        {"self": [{"href": ["http://127.0.0.1:1/secret"]}]},
    ],
)
def test_wrong_self_metadata_types_are_rejected_without_echoing_them(
    monkeypatch: pytest.MonkeyPatch, links: object
) -> None:
    page = {"values": [{"key": "DEMO", "links": links}], "isLastPage": True}

    with pytest.raises(AtlaWireError, match="Invalid links") as error:
        read(monkeypatch, [page])

    assert "127.0.0.1" not in str(error.value)


def test_matching_echoed_start_and_size_describe_each_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = [
        {
            "values": [FIRST],
            "isLastPage": False,
            "nextPageStart": 17,
            "start": 0,
            "size": 1,
        },
        {"values": [SECOND], "isLastPage": True, "start": 17, "size": 1},
    ]

    rows, calls = read(monkeypatch, pages)

    assert rows == [EXPECTED_FIRST, EXPECTED_SECOND]
    assert calls == [
        {"url": PROJECTS_URL, "start": 0, "limit": 100},
        {"url": PROJECTS_URL, "start": 17, "limit": 100},
    ]


def test_a_terminal_page_echoing_the_previous_cursor_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Before this check the stale cursor was ignored, so the repeated row was
    # published twice as a successful result.
    pages = [
        {"values": [FIRST], "isLastPage": False, "nextPageStart": 100, "start": 0},
        {"values": [FIRST], "isLastPage": True, "start": 0},
    ]

    with pytest.raises(AtlaWireError, match="page start"):
        read(monkeypatch, pages)


@pytest.mark.parametrize(
    ("page", "message"),
    [
        ({"values": [], "isLastPage": True, "start": 1}, "page start"),
        ({"values": [], "isLastPage": True, "start": False}, "page start"),
        ({"values": [], "isLastPage": True, "start": True}, "page start"),
        ({"values": [], "isLastPage": True, "start": 0.0}, "page start"),
        ({"values": [], "isLastPage": True, "start": "0"}, "page start"),
        ({"values": [FIRST], "isLastPage": True, "size": 2}, "page size"),
        ({"values": [FIRST], "isLastPage": True, "size": 0}, "page size"),
        ({"values": [], "isLastPage": True, "size": False}, "page size"),
        ({"values": [FIRST], "isLastPage": True, "size": True}, "page size"),
        ({"values": [FIRST], "isLastPage": True, "size": 1.0}, "page size"),
        ({"values": [FIRST], "isLastPage": True, "size": "1"}, "page size"),
    ],
    ids=[
        "start-mismatch",
        "start-false",
        "start-true",
        "start-float",
        "start-string",
        "size-too-large",
        "size-too-small",
        "size-false",
        "size-true",
        "size-float",
        "size-string",
    ],
)
def test_a_malformed_echoed_cursor_metadata_value_is_rejected(
    monkeypatch: pytest.MonkeyPatch, page: dict[str, object], message: str
) -> None:
    with pytest.raises(AtlaWireError, match=message):
        read(monkeypatch, [page])
