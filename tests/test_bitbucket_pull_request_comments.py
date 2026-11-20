from contextlib import nullcontext
from typing import cast

import pytest

from atlawire import bitbucket
from atlawire.http import AtlaWireError

BASE = "https://bitbucket.example.invalid/scm"
ACTIVITIES_URL = (
    f"{BASE}/rest/api/1.0/projects/DEMO/repos/widgets/pull-requests/7/activities"
)
TOKEN = "fixture-only-token"


def page(
    values: list[object], *, last: bool, next_start: int | None = None
) -> dict[str, object]:
    body: dict[str, object] = {"values": values, "isLastPage": last}
    if next_start is not None:
        body["nextPageStart"] = next_start
    return body


def read(
    monkeypatch: pytest.MonkeyPatch,
    pages: list[dict[str, object]],
    *,
    max_pages: int = 100,
) -> tuple[list[bitbucket.PullRequestComment], list[dict[str, object]]]:
    calls: list[dict[str, object]] = []

    def fake_get_json_object(
        session: object, url: str, *, params: dict[str, str | int]
    ) -> dict[str, object]:
        calls.append({"url": url, **params})
        if len(calls) > len(pages):
            raise AssertionError("unexpected extra page request")
        return pages[len(calls) - 1]

    monkeypatch.setattr(bitbucket, "bearer_session", lambda token: nullcontext(None))
    monkeypatch.setattr(bitbucket, "get_json_object", fake_get_json_object)
    rows = bitbucket.list_pull_request_comments(
        BASE, "DEMO/widgets", "7", token=TOKEN, max_pages=max_pages
    )
    return rows, calls


def test_an_empty_first_page_does_not_end_paging_at_a_noncontiguous_cursor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = [
        page(
            [
                {"id": 1, "action": "RESCOPED", "fromHash": "a"},
                {"id": 2, "action": "APPROVED", "user": {"name": "ana"}},
            ],
            last=False,
            next_start=17,
        ),
        page(
            [
                {
                    "id": 3,
                    "comment": {
                        "id": 41,
                        "author": {"name": "li"},
                        "text": "please fix",
                        "createdDate": 1527228363421,
                    },
                    "commentAnchor": {"path": "src/main.py", "line": 12},
                }
            ],
            last=True,
        ),
    ]

    rows, calls = read(monkeypatch, pages)

    assert rows == [
        {
            "id": 41,
            "author": "li",
            "path": "src/main.py",
            "line": 12,
            "text": "please fix",
            "created": 1527228363421,
        }
    ]
    assert calls == [
        {"url": ACTIVITIES_URL, "start": 0, "limit": 100},
        {"url": ACTIVITIES_URL, "start": 17, "limit": 100},
    ]


def test_projection_keeps_raw_text_and_ignores_nested_replies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reply = {"id": 13, "author": {"name": "bob"}, "text": "a reply"}
    activity = {
        "id": 9,
        "comment": {
            "id": 12,
            "version": 2,
            "author": {"name": "ann"},
            "text": "line one\n\tline two  ",
            "createdDate": 1527228363421,
            "comments": [reply],
        },
        "commentAnchor": {"path": "docs/a b.md", "line": 0},
    }

    rows, calls = read(monkeypatch, [page([activity], last=True)])

    assert rows == [
        {
            "id": 12,
            "author": "ann",
            "path": "docs/a b.md",
            "line": 0,
            "text": "line one\n\tline two  ",
            "created": 1527228363421,
        }
    ]
    assert calls == [{"url": ACTIVITIES_URL, "start": 0, "limit": 100}]


def test_a_terminal_page_without_comments_is_a_valid_empty_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows, calls = read(
        monkeypatch,
        [
            page(
                [
                    {"id": 1, "action": "MERGED"},
                    {"id": 2, "action": "APPROVED"},
                    {"id": 3, "action": "RESCOPED"},
                ],
                last=True,
            )
        ],
    )

    assert rows == []
    assert calls == [{"url": ACTIVITIES_URL, "start": 0, "limit": 100}]


@pytest.mark.parametrize(
    "activity",
    [{}, {"comment": None}, {"id": 1, "action": "MERGED", "comment": None}],
    ids=["missing", "null", "unrelated-with-null"],
)
def test_activities_without_a_top_level_comment_are_skipped(
    monkeypatch: pytest.MonkeyPatch, activity: dict[str, object]
) -> None:
    rows, _calls = read(monkeypatch, [page([activity], last=True)])

    assert rows == []


@pytest.mark.parametrize(
    ("activity", "expected"),
    [
        (
            {
                "comment": {
                    "id": 1,
                    "author": {"name": "li"},
                    "text": "x",
                    "createdDate": 10,
                    "created": 20,
                },
                "commentAnchor": {"path": "new/path", "line": 3},
                "anchor": {"path": "old/path", "line": 9},
            },
            {
                "id": 1,
                "author": "li",
                "path": "new/path",
                "line": 3,
                "text": "x",
                "created": 10,
            },
        ),
        (
            {
                "comment": {"id": 2, "createdDate": None, "created": 0},
                "commentAnchor": None,
                "anchor": {"path": "legacy", "line": 0},
            },
            {
                "id": 2,
                "author": None,
                "path": "legacy",
                "line": 0,
                "text": "",
                "created": 0,
            },
        ),
        (
            {
                "comment": {"id": 3, "createdDate": None},
                "commentAnchor": {},
                "anchor": {"path": "legacy", "line": 4},
            },
            {
                "id": 3,
                "author": None,
                "path": None,
                "line": None,
                "text": "",
                "created": None,
            },
        ),
        (
            {
                "comment": {"id": 4, "createdDate": None, "created": None},
                "anchor": {"path": None, "line": None},
            },
            {
                "id": 4,
                "author": None,
                "path": None,
                "line": None,
                "text": "",
                "created": None,
            },
        ),
    ],
    ids=[
        "canonical-wins-over-legacy",
        "legacy-fallback-keeps-units-and-zero",
        "empty-canonical-container-blocks-fallback",
        "null-fields-stay-null",
    ],
)
def test_anchor_and_timestamp_precedence(
    monkeypatch: pytest.MonkeyPatch,
    activity: dict[str, object],
    expected: bitbucket.PullRequestComment,
) -> None:
    rows, _calls = read(monkeypatch, [page([activity], last=True)])

    assert rows == [expected]


@pytest.mark.parametrize(
    ("activity", "message"),
    [
        (None, "activity object"),
        ([], "activity object"),
        ("activity", "activity object"),
        ({"comment": "comment"}, "comment object"),
        ({"comment": []}, "comment object"),
        ({"comment": True}, "comment object"),
        ({"comment": {}}, "Invalid id"),
        ({"comment": {"id": 0}}, "Invalid id"),
        ({"comment": {"id": -1}}, "Invalid id"),
        ({"comment": {"id": True}}, "Invalid id"),
        ({"comment": {"id": "1"}}, "Invalid id"),
        ({"comment": {"id": 1, "author": "ann"}}, "Invalid author"),
        ({"comment": {"id": 1, "author": {"name": 7}}}, "Invalid author"),
        ({"comment": {"id": 1, "text": 7}}, "Invalid text"),
        ({"comment": {"id": 1, "text": False}}, "Invalid text"),
        (
            {
                "comment": {"id": 1},
                "commentAnchor": "src",
                "anchor": {"path": "ok"},
            },
            "Invalid anchor",
        ),
        ({"comment": {"id": 1}, "anchor": 7}, "Invalid anchor"),
        ({"comment": {"id": 1}, "commentAnchor": {"path": 7}}, "Invalid path"),
        ({"comment": {"id": 1}, "commentAnchor": {"line": True}}, "Invalid line"),
        ({"comment": {"id": 1}, "commentAnchor": {"line": -1}}, "Invalid line"),
        (
            {"comment": {"id": 1, "createdDate": True, "created": 5}},
            "creation time",
        ),
        ({"comment": {"id": 1, "createdDate": "1"}}, "creation time"),
        ({"comment": {"id": 1, "createdDate": -1}}, "creation time"),
        (
            {"comment": {"id": 1, "createdDate": None, "created": False}},
            "creation time",
        ),
    ],
)
def test_malformed_consumed_metadata_is_rejected(
    monkeypatch: pytest.MonkeyPatch, activity: object, message: str
) -> None:
    with pytest.raises(AtlaWireError, match=message):
        read(monkeypatch, [page([activity], last=True)])


@pytest.mark.parametrize("max_pages", [0, 1001, True, 1.5, "10"])
def test_invalid_page_limit_fails_before_any_session(
    monkeypatch: pytest.MonkeyPatch, max_pages: object
) -> None:
    def forbidden_session(token: str) -> object:
        raise AssertionError("session created before page-limit validation")

    monkeypatch.setattr(bitbucket, "bearer_session", forbidden_session)

    with pytest.raises(AtlaWireError, match="page limit"):
        bitbucket.list_pull_request_comments(
            BASE,
            "DEMO/widgets",
            "7",
            token=TOKEN,
            max_pages=cast(int, max_pages),
        )
