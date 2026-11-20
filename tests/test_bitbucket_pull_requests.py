from collections.abc import Callable
from contextlib import nullcontext
from typing import cast

import pytest

from atlawire import bitbucket
from atlawire.http import AtlaWireError

BASE = "https://bitbucket.example.invalid/scm"
PULL_REQUESTS_URL = f"{BASE}/rest/api/1.0/projects/DEMO/repos/widgets/pull-requests"

FULL = {
    "id": 101,
    "title": "Fix ü",
    "state": "OPEN",
    "updatedDate": 0,
    "author": {"user": {"name": "tom", "emailAddress": "tom@example.invalid"}},
    "fromRef": {"displayId": "feature/ü", "repository": {"slug": "widgets"}},
    "toRef": {"displayId": "main"},
    "description": "RAW-DESCRIPTION",
    "links": {"self": [{"href": "https://secret.invalid"}]},
}
MINIMAL = {"id": 7, "title": "Second", "state": "MERGED"}


def call_pages[RowT](
    monkeypatch: pytest.MonkeyPatch,
    pages: list[dict[str, object]],
    read: Callable[[], list[RowT]],
    *,
    calls: list[dict[str, object]] | None = None,
) -> tuple[list[RowT], list[dict[str, object]]]:
    seen: list[dict[str, object]] = [] if calls is None else calls

    def fake_get_json_object(
        session: object, url: str, *, params: dict[str, str | int]
    ) -> dict[str, object]:
        if len(seen) >= len(pages):
            raise AssertionError("Unexpected extra Bitbucket request.")
        seen.append({"url": url, **params})
        return pages[len(seen) - 1]

    monkeypatch.setattr(bitbucket, "bearer_session", lambda token: nullcontext(None))
    monkeypatch.setattr(bitbucket, "get_json_object", fake_get_json_object)
    return read(), seen


def test_pull_requests_repeat_the_exact_filters_and_follow_the_server_cursor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = [
        {
            "values": [FULL],
            "isLastPage": False,
            "nextPageStart": 7,
        },
        {
            "values": [MINIMAL, {"id": 8, "title": "Third", "state": "DECLINED"}],
            "isLastPage": False,
            "nextPageStart": "unused-and-unusable",
        },
    ]

    rows, seen = call_pages(
        monkeypatch,
        pages,
        lambda: bitbucket.list_pull_requests(
            BASE,
            "DEMO/widgets",
            token="fixture-only",
            state="ALL",
            order="OLDEST",
            limit=3,
        ),
    )

    assert rows == [
        {
            "id": 101,
            "title": "Fix ü",
            "state": "OPEN",
            "author": "tom",
            "from": "feature/ü",
            "to": "main",
            "updated": 0,
        },
        {
            "id": 7,
            "title": "Second",
            "state": "MERGED",
            "author": None,
            "from": None,
            "to": None,
            "updated": None,
        },
        {
            "id": 8,
            "title": "Third",
            "state": "DECLINED",
            "author": None,
            "from": None,
            "to": None,
            "updated": None,
        },
    ]
    assert seen == [
        {
            "url": PULL_REQUESTS_URL,
            "start": 0,
            "limit": 3,
            "state": "ALL",
            "order": "OLDEST",
        },
        {
            "url": PULL_REQUESTS_URL,
            "start": 7,
            "limit": 2,
            "state": "ALL",
            "order": "OLDEST",
        },
    ]


def test_an_unspecified_order_is_omitted_and_the_default_state_is_open(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows, seen = call_pages(
        monkeypatch,
        [{"values": [], "isLastPage": True}],
        lambda: bitbucket.list_pull_requests(
            BASE, "DEMO/widgets", token="fixture-only"
        ),
    )

    assert rows == []
    assert seen == [
        {"url": PULL_REQUESTS_URL, "start": 0, "limit": 25, "state": "OPEN"}
    ]


def test_pull_request_projection_keeps_only_the_legacy_fields() -> None:
    assert bitbucket._pull_request(FULL) == {
        "id": 101,
        "title": "Fix ü",
        "state": "OPEN",
        "author": "tom",
        "from": "feature/ü",
        "to": "main",
        "updated": 0,
    }


def test_pull_request_projection_keeps_absent_optionals_null() -> None:
    assert bitbucket._pull_request(MINIMAL) == {
        "id": 7,
        "title": "Second",
        "state": "MERGED",
        "author": None,
        "from": None,
        "to": None,
        "updated": None,
    }


@pytest.mark.parametrize(
    "value",
    [
        5,
        {"id": 0, "title": "t", "state": "OPEN"},
        {"id": True, "title": "t", "state": "OPEN"},
        {"id": 1, "title": "", "state": "OPEN"},
        {"id": 1, "title": 5, "state": "OPEN"},
        {"id": 1, "title": "t", "state": ""},
        {"id": 1, "title": "t", "state": 5},
        {"id": 1, "title": "t", "state": "OPEN", "updatedDate": -1},
        {"id": 1, "title": "t", "state": "OPEN", "updatedDate": True},
        {"id": 1, "title": "t", "state": "OPEN", "updatedDate": 1.5},
        {"id": 1, "title": "t", "state": "OPEN", "author": 5},
        {"id": 1, "title": "t", "state": "OPEN", "author": {"user": 5}},
        {"id": 1, "title": "t", "state": "OPEN", "author": {"user": {"name": 5}}},
        {"id": 1, "title": "t", "state": "OPEN", "fromRef": 5},
        {"id": 1, "title": "t", "state": "OPEN", "fromRef": {"displayId": 5}},
        {"id": 1, "title": "t", "state": "OPEN", "toRef": "main"},
    ],
    ids=[
        "not-an-object",
        "zero-id",
        "boolean-id",
        "empty-title",
        "non-string-title",
        "empty-state",
        "non-string-state",
        "negative-updated",
        "boolean-updated",
        "fractional-updated",
        "non-object-author",
        "non-object-user",
        "non-string-name",
        "non-object-from",
        "non-string-from-display",
        "non-object-to",
    ],
)
def test_malformed_pull_request_metadata_is_rejected(value: object) -> None:
    with pytest.raises(AtlaWireError, match="pull request"):
        bitbucket._pull_request(value)


@pytest.mark.parametrize(
    "value",
    [
        {"id": 1, "title": "\ud800", "state": "OPEN"},
        {"id": 1, "title": "t", "state": "\ud800"},
        {
            "id": 1,
            "title": "t",
            "state": "OPEN",
            "author": {"user": {"name": "\ud800"}},
        },
        {"id": 1, "title": "t", "state": "OPEN", "fromRef": {"displayId": "\ud800"}},
        {"id": 1, "title": "t", "state": "OPEN", "toRef": {"displayId": "\ud800"}},
    ],
    ids=["title", "state", "author", "from", "to"],
)
def test_pull_request_text_that_utf8_cannot_encode_is_rejected(value: object) -> None:
    with pytest.raises(AtlaWireError, match="pull request"):
        bitbucket._pull_request(value)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"state": "open"}, "state"),
        ({"state": ""}, "state"),
        ({"order": "newest"}, "order"),
        ({"order": ""}, "order"),
        ({"limit": 0}, "pull request limit"),
        ({"limit": 1001}, "pull request limit"),
        ({"limit": True}, "pull request limit"),
        ({"max_pages": 0}, "page limit"),
        ({"max_pages": 1001}, "page limit"),
        ({"max_pages": True}, "page limit"),
    ],
)
def test_invalid_arguments_are_rejected_before_the_session(
    monkeypatch: pytest.MonkeyPatch,
    overrides: dict[str, object],
    message: str,
) -> None:
    def unexpected_session(token: str) -> object:
        raise AssertionError("No session should be created.")

    monkeypatch.setattr(bitbucket, "bearer_session", unexpected_session)

    with pytest.raises(AtlaWireError, match=message):
        bitbucket.list_pull_requests(
            BASE,
            "DEMO/widgets",
            token="fixture-only",
            state=cast(str, overrides.get("state", "OPEN")),
            order=cast(str | None, overrides.get("order")),
            limit=cast(int, overrides.get("limit", 25)),
            max_pages=cast(int, overrides.get("max_pages", 100)),
        )


@pytest.mark.parametrize(
    "last",
    ["not-a-boolean", None],
    ids=["malformed", "absent"],
)
def test_the_row_cap_still_requires_an_exact_is_last_page_boolean(
    monkeypatch: pytest.MonkeyPatch, last: object
) -> None:
    page: dict[str, object] = {"values": [MINIMAL]}
    if last is not None:
        page["isLastPage"] = last

    with pytest.raises(AtlaWireError, match="isLastPage"):
        call_pages(
            monkeypatch,
            [page],
            lambda: bitbucket.list_pull_requests(
                BASE, "DEMO/widgets", token="fixture-only", limit=1
            ),
        )


def test_the_page_cap_after_a_nonterminal_page_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages: list[dict[str, object]] = [
        {"values": [MINIMAL], "isLastPage": False, "nextPageStart": 7}
    ]
    seen: list[dict[str, object]] = []

    with pytest.raises(AtlaWireError, match="page limit"):
        call_pages(
            monkeypatch,
            pages,
            lambda: bitbucket.list_pull_requests(
                BASE,
                "DEMO/widgets",
                token="fixture-only",
                limit=2,
                max_pages=1,
            ),
            calls=seen,
        )

    assert seen == [{"url": PULL_REQUESTS_URL, "start": 0, "limit": 2, "state": "OPEN"}]
