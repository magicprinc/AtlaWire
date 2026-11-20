from collections.abc import Callable
from contextlib import nullcontext
from typing import cast

import pytest

from atlawire import bitbucket
from atlawire.http import AtlaWireError

BASE = "https://bitbucket.example.invalid/scm"
BRANCHES_URL = f"{BASE}/rest/api/1.0/projects/DEMO/repos/widgets/branches"
COMMITS_URL = f"{BASE}/rest/api/1.0/projects/DEMO/repos/widgets/commits"
FILTER = "rel/é +&?"


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


def test_branches_repeat_the_exact_filter_and_follow_the_server_cursor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = [
        {
            "values": [
                {
                    "id": "refs/heads/main",
                    "displayId": "main",
                    "latestCommit": "a" * 40,
                    "isDefault": True,
                }
            ],
            "isLastPage": False,
            "nextPageStart": 57,
        },
        {
            "values": [
                {"id": "refs/heads/release", "displayId": "release"},
                {
                    "id": "refs/heads/old",
                    "displayId": "old",
                    "latestCommit": None,
                    "isDefault": False,
                },
            ],
            "isLastPage": True,
        },
    ]

    rows, seen = call_pages(
        monkeypatch,
        pages,
        lambda: bitbucket.list_branches(
            BASE, "DEMO/widgets", token="fixture-only", filter_text=FILTER
        ),
    )

    assert rows == [
        {
            "name": "main",
            "id": "refs/heads/main",
            "commit": "a" * 40,
            "default": True,
        },
        {
            "name": "release",
            "id": "refs/heads/release",
            "commit": None,
            "default": None,
        },
        {
            "name": "old",
            "id": "refs/heads/old",
            "commit": None,
            "default": False,
        },
    ]
    assert seen == [
        {"url": BRANCHES_URL, "start": 0, "limit": 100, "filterText": FILTER},
        {"url": BRANCHES_URL, "start": 57, "limit": 100, "filterText": FILTER},
    ]


@pytest.mark.parametrize("filter_text", [None, ""])
def test_an_absent_or_empty_branch_filter_is_omitted(
    monkeypatch: pytest.MonkeyPatch, filter_text: str | None
) -> None:
    pages = [{"values": [], "isLastPage": True}]

    rows, seen = call_pages(
        monkeypatch,
        pages,
        lambda: bitbucket.list_branches(
            BASE, "DEMO/widgets", token="fixture-only", filter_text=filter_text
        ),
    )

    assert rows == []
    assert seen == [{"url": BRANCHES_URL, "start": 0, "limit": 100}]


def test_a_non_encodable_branch_filter_is_rejected_before_the_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_session(token: str) -> object:
        raise AssertionError("No session should be created.")

    monkeypatch.setattr(bitbucket, "bearer_session", unexpected_session)

    with pytest.raises(AtlaWireError, match="branch filter"):
        bitbucket.list_branches(
            BASE,
            "DEMO/widgets",
            token="fixture-only",
            filter_text="\ud800",
        )


@pytest.mark.parametrize(
    "value",
    [
        5,
        {"displayId": "", "id": "refs/heads/x"},
        {"displayId": "x"},
        {"displayId": "x", "id": "refs/heads/x", "latestCommit": 5},
        {"displayId": "x", "id": "refs/heads/x", "isDefault": 1},
        {"displayId": "x", "id": "", "isDefault": True},
    ],
    ids=[
        "not-an-object",
        "empty-name",
        "missing-id",
        "non-string-commit",
        "non-boolean-default",
        "empty-id",
    ],
)
def test_malformed_branch_metadata_is_rejected(value: object) -> None:
    with pytest.raises(AtlaWireError, match="branch"):
        bitbucket._branch(value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (
            {"id": "abc"},
            {"hash": "abc", "date": None, "author": None, "message": ""},
        ),
        (
            {"id": "abc", "message": None, "author": {}},
            {"hash": "abc", "date": None, "author": None, "message": ""},
        ),
        (
            {"id": "abc", "author": {"name": None}, "message": "raw\ntext  here"},
            {
                "hash": "abc",
                "date": None,
                "author": None,
                "message": "raw\ntext  here",
            },
        ),
        (
            {"id": "abc", "author": {"name": "li"}, "message": "raw\ttext"},
            {"hash": "abc", "date": None, "author": "li", "message": "raw\ttext"},
        ),
    ],
    ids=["minimal", "explicit-null", "null-like-author", "raw-text"],
)
def test_commit_row_keeps_the_raw_message_and_a_nullable_author(
    value: dict[str, object], expected: bitbucket.Commit
) -> None:
    assert bitbucket._commit(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        5,
        {"id": ""},
        {"id": 5},
        {"id": "abc", "message": 5},
        {"id": "abc", "author": "li"},
        {"id": "abc", "author": {"name": 5}},
    ],
    ids=[
        "not-an-object",
        "empty-hash",
        "integer-hash",
        "non-string-message",
        "non-object-author",
        "non-string-author-name",
    ],
)
def test_malformed_commit_metadata_is_rejected(value: object) -> None:
    with pytest.raises(AtlaWireError, match="commit"):
        bitbucket._commit(value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        (0, "1970-01-01 00:00"),
        (59999, "1970-01-01 00:00"),
        (60000, "1970-01-01 00:01"),
        (-1, "1969-12-31 23:59"),
        (-1000, "1969-12-31 23:59"),
        (1527228363490, "2018-05-25 06:06"),
    ],
    ids=[
        "absent",
        "epoch",
        "last-millisecond",
        "next-minute",
        "pre-epoch-millisecond",
        "pre-epoch-second",
        "ordinary-utc",
    ],
)
def test_commit_date_is_a_utc_minute_and_accepts_pre_epoch_values(
    value: int | None, expected: str | None
) -> None:
    assert bitbucket._commit_date(value) == expected


@pytest.mark.parametrize("value", [True, False, 1.5, "0", [0]])
def test_commit_date_rejects_boolean_and_non_integer_timestamps(value: object) -> None:
    with pytest.raises(AtlaWireError, match="author timestamp"):
        bitbucket._commit_date(value)


@pytest.mark.parametrize("value", [10**18, -(10**18), 2**63 - 1])
def test_commit_date_reports_an_overflow_without_echoing_the_value(
    value: int,
) -> None:
    with pytest.raises(AtlaWireError, match="author timestamp") as error:
        bitbucket._commit_date(value)
    assert str(value) not in str(error.value)


def test_commit_until_keeps_unicode_and_reserved_query_characters() -> None:
    at = "feature/ü &?+#"

    assert bitbucket._commit_params(at, None) == {"until": at}


def test_commit_until_rejects_control_characters() -> None:
    with pytest.raises(AtlaWireError, match="revision"):
        bitbucket._commit_params("release\n2", None)


@pytest.mark.parametrize("path", ["src/é +&?.py", "dir/with space/file.txt"])
def test_commit_path_is_kept_verbatim_in_the_query(path: str) -> None:
    assert bitbucket._commit_params(None, path) == {"path": path}


@pytest.mark.parametrize("path", ["a\nb", "a\x00b", 5])
def test_commit_path_filter_rejects_controls_and_non_strings(path: object) -> None:
    with pytest.raises(AtlaWireError, match="path filter"):
        bitbucket._commit_params(None, cast(str, path))


def test_commits_follow_the_offset_cursor_and_exact_remaining_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    at = "feature/ü &?+#"
    path = "src/é +&?.py"
    pages = [
        {
            "values": [
                {
                    "id": "a" * 40,
                    "authorTimestamp": 0,
                    "author": {"name": "li"},
                    "message": "first",
                },
                {"id": "b" * 40, "message": "second"},
            ],
            "isLastPage": False,
            "nextPageStart": 41,
        },
        {
            "values": [
                {"id": "c" * 40, "message": "third"},
                {"id": "d" * 40, "message": "fourth"},
                {"id": "e" * 40, "message": "fifth"},
            ],
            "isLastPage": False,
        },
    ]

    rows, seen = call_pages(
        monkeypatch,
        pages,
        lambda: bitbucket.list_commits(
            BASE,
            "DEMO/widgets",
            token="fixture-only",
            at=at,
            path=path,
            limit=5,
        ),
    )

    assert [row["hash"] for row in rows] == [
        "a" * 40,
        "b" * 40,
        "c" * 40,
        "d" * 40,
        "e" * 40,
    ]
    assert rows[0]["date"] == "1970-01-01 00:00"
    assert rows[0]["author"] == "li"
    assert [row["message"] for row in rows] == [
        "first",
        "second",
        "third",
        "fourth",
        "fifth",
    ]
    assert seen == [
        {
            "url": COMMITS_URL,
            "start": 0,
            "limit": 5,
            "until": at,
            "path": path,
        },
        {
            "url": COMMITS_URL,
            "start": 41,
            "limit": 3,
            "until": at,
            "path": path,
        },
    ]


@pytest.mark.parametrize(("at", "path"), [(None, None), ("", "")])
def test_absent_or_empty_commit_filters_are_omitted_and_the_library_defaults_to_25(
    monkeypatch: pytest.MonkeyPatch, at: str | None, path: str | None
) -> None:
    pages: list[dict[str, object]] = [{"values": [], "isLastPage": True}]

    rows, seen = call_pages(
        monkeypatch,
        pages,
        lambda: bitbucket.list_commits(
            BASE, "DEMO/widgets", token="fixture-only", at=at, path=path
        ),
    )

    assert rows == []
    assert seen == [{"url": COMMITS_URL, "start": 0, "limit": 25}]


def test_a_large_row_limit_is_requested_in_pages_of_at_most_100(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages: list[dict[str, object]] = [
        {
            "values": [{"id": f"c{index}"} for index in range(100)],
            "isLastPage": False,
            "nextPageStart": 100,
        },
        {
            "values": [{"id": f"d{index}"} for index in range(50)],
            "isLastPage": True,
        },
    ]

    rows, seen = call_pages(
        monkeypatch,
        pages,
        lambda: bitbucket.list_commits(
            BASE, "DEMO/widgets", token="fixture-only", limit=150
        ),
    )

    assert len(rows) == 150
    assert seen == [
        {"url": COMMITS_URL, "start": 0, "limit": 100},
        {"url": COMMITS_URL, "start": 100, "limit": 50},
    ]


def test_the_row_cap_stops_without_the_unused_next_page_hint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = [
        {
            "values": [{"id": "a"}, {"id": "b"}],
            "isLastPage": False,
        }
    ]

    rows, seen = call_pages(
        monkeypatch,
        pages,
        lambda: bitbucket.list_commits(
            BASE, "DEMO/widgets", token="fixture-only", limit=2
        ),
    )

    assert [row["hash"] for row in rows] == ["a", "b"]
    assert seen == [{"url": COMMITS_URL, "start": 0, "limit": 2}]


@pytest.mark.parametrize(
    "last",
    ["not-a-boolean", None],
    ids=["malformed", "absent"],
)
def test_the_row_cap_still_requires_an_exact_is_last_page_boolean(
    monkeypatch: pytest.MonkeyPatch, last: object
) -> None:
    page: dict[str, object] = {"values": [{"id": "a"}]}
    if last is not None:
        page["isLastPage"] = last

    with pytest.raises(AtlaWireError, match="isLastPage"):
        call_pages(
            monkeypatch,
            [page],
            lambda: bitbucket.list_commits(
                BASE, "DEMO/widgets", token="fixture-only", limit=1
            ),
        )


def test_the_page_cap_after_a_nonterminal_page_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages: list[dict[str, object]] = [
        {
            "values": [{"id": "a"}],
            "isLastPage": False,
            "nextPageStart": 7,
        }
    ]
    seen: list[dict[str, object]] = []

    with pytest.raises(AtlaWireError, match="page limit"):
        call_pages(
            monkeypatch,
            pages,
            lambda: bitbucket.list_commits(
                BASE,
                "DEMO/widgets",
                token="fixture-only",
                limit=2,
                max_pages=1,
            ),
            calls=seen,
        )

    assert seen == [{"url": COMMITS_URL, "start": 0, "limit": 2}]


def test_a_page_wider_than_the_row_request_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = [
        {
            "values": [{"id": "a"}, {"id": "b"}, {"id": "c"}],
            "isLastPage": False,
        }
    ]

    with pytest.raises(AtlaWireError, match="more rows"):
        call_pages(
            monkeypatch,
            pages,
            lambda: bitbucket.list_commits(
                BASE, "DEMO/widgets", token="fixture-only", limit=2
            ),
        )


def test_a_missing_terminal_marker_before_the_limit_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages: list[dict[str, object]] = [{"values": [{"id": "a"}]}]

    with pytest.raises(AtlaWireError, match="isLastPage"):
        call_pages(
            monkeypatch,
            pages,
            lambda: bitbucket.list_commits(
                BASE, "DEMO/widgets", token="fixture-only", limit=2
            ),
        )


@pytest.mark.parametrize("limit", [0, 1001, True])
def test_an_invalid_commit_limit_is_rejected_before_the_session(
    monkeypatch: pytest.MonkeyPatch, limit: object
) -> None:
    def unexpected_session(token: str) -> object:
        raise AssertionError("No session should be created.")

    monkeypatch.setattr(bitbucket, "bearer_session", unexpected_session)

    with pytest.raises(AtlaWireError, match="commit limit"):
        bitbucket.list_commits(
            BASE, "DEMO/widgets", token="fixture-only", limit=cast(int, limit)
        )


@pytest.mark.parametrize("max_pages", [0, 1001, True])
def test_an_invalid_page_limit_is_rejected_before_the_session(
    monkeypatch: pytest.MonkeyPatch, max_pages: object
) -> None:
    def unexpected_session(token: str) -> object:
        raise AssertionError("No session should be created.")

    monkeypatch.setattr(bitbucket, "bearer_session", unexpected_session)

    with pytest.raises(AtlaWireError, match="page limit"):
        bitbucket.list_branches(
            BASE,
            "DEMO/widgets",
            token="fixture-only",
            max_pages=cast(int, max_pages),
        )
