"""Focused library checks for recursive file and direct directory listings."""

from collections.abc import Callable, Mapping, Sequence
from contextlib import nullcontext
from typing import cast

import pytest

from atlawire import bitbucket
from atlawire.http import AtlaWireError

BASE = "https://bitbucket.example.invalid/scm"
TOKEN = "fixture-only-token"
FILES_URL = f"{BASE}/rest/api/1.0/projects/DEMO/repos/widgets/files"
BROWSE_URL = f"{BASE}/rest/api/1.0/projects/DEMO/repos/widgets/browse"
SUBDIR = "папка/dir name/a#b?c%"
SUBDIR_ENCODED = "%D0%BF%D0%B0%D0%BF%D0%BA%D0%B0/dir%20name/a%23b%3Fc%25"
AT = "feature/ü &?+#"


def forbid_session(token: str) -> object:
    raise AssertionError("session created before validation")


def call_pages[RowT](
    monkeypatch: pytest.MonkeyPatch,
    pages: Sequence[Mapping[str, object]],
    read: Callable[[], list[RowT]],
) -> tuple[list[RowT], list[dict[str, object]]]:
    seen: list[dict[str, object]] = []

    def fake_get_json_object(
        session: object, url: str, *, params: dict[str, str | int]
    ) -> dict[str, object]:
        if len(seen) >= len(pages):
            raise AssertionError("Unexpected extra Bitbucket request.")
        seen.append({"url": url, **params})
        return dict(pages[len(seen) - 1])

    monkeypatch.setattr(bitbucket, "bearer_session", lambda token: nullcontext(None))
    monkeypatch.setattr(bitbucket, "get_json_object", fake_get_json_object)
    return read(), seen


def test_files_follow_the_noncontiguous_cursor_and_project_legacy_shapes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = [
        {
            "values": [
                "src/a b.py",
                {"path": "src/ü.txt"},
                {"toString": "top/legacy.txt"},
            ],
            "isLastPage": False,
            "nextPageStart": 37,
        },
        {
            "values": [{"path": {"toString": "nested/x", "components": ["unused"]}}],
            "isLastPage": True,
        },
    ]

    rows, seen = call_pages(
        monkeypatch,
        pages,
        lambda: bitbucket.list_repository_files(
            BASE, "DEMO/widgets", token=TOKEN, at=AT
        ),
    )

    assert rows == ["src/a b.py", "src/ü.txt", "top/legacy.txt", "nested/x"]
    assert seen == [
        {"url": FILES_URL, "start": 0, "limit": 100, "at": AT},
        {"url": FILES_URL, "start": 37, "limit": 100, "at": AT},
    ]


@pytest.mark.parametrize("at", [None, ""])
def test_files_omit_an_absent_or_empty_revision(
    monkeypatch: pytest.MonkeyPatch, at: str | None
) -> None:
    rows, seen = call_pages(
        monkeypatch,
        [{"values": [], "isLastPage": True}],
        lambda: bitbucket.list_repository_files(
            BASE, "DEMO/widgets", token=TOKEN, at=at
        ),
    )

    assert rows == []
    assert seen == [{"url": FILES_URL, "start": 0, "limit": 100}]


@pytest.mark.parametrize("value", ["", 5, {"path": ""}, {"path": None}])
def test_files_reject_empty_or_malformed_paths(value: object) -> None:
    with pytest.raises(AtlaWireError, match="path"):
        bitbucket._repository_file_path(value)


def test_files_reject_an_unencodable_projected_path() -> None:
    with pytest.raises(AtlaWireError, match="UTF-8"):
        bitbucket._repository_file_path("src/\ud800.txt")


@pytest.mark.parametrize("at", ["\n", "\ud800"])
def test_an_invalid_revision_is_rejected_before_the_session(
    monkeypatch: pytest.MonkeyPatch, at: str
) -> None:
    monkeypatch.setattr(bitbucket, "bearer_session", forbid_session)

    with pytest.raises(AtlaWireError, match="revision"):
        bitbucket.list_repository_files(BASE, "DEMO/widgets", token=TOKEN, at=at)


@pytest.mark.parametrize("max_pages", [0, 1001, True])
@pytest.mark.parametrize("command", ["files", "ls"])
def test_an_invalid_page_limit_is_rejected_before_the_session(
    monkeypatch: pytest.MonkeyPatch, command: str, max_pages: object
) -> None:
    monkeypatch.setattr(bitbucket, "bearer_session", forbid_session)

    with pytest.raises(AtlaWireError, match="page limit"):
        if command == "files":
            bitbucket.list_repository_files(
                BASE, "DEMO/widgets", token=TOKEN, max_pages=cast(int, max_pages)
            )
        else:
            bitbucket.list_directory(
                BASE, "DEMO/widgets", token=TOKEN, max_pages=cast(int, max_pages)
            )


def test_ls_reads_the_nested_children_cursor_not_the_conflicting_outer_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = [
        {
            "children": {
                "values": [{"path": "README.md", "type": "FILE", "size": 0}],
                "isLastPage": False,
                "nextPageStart": 9,
            },
            "isLastPage": True,
            "nextPageStart": 999,
        },
        {
            "children": {
                "values": [{"path": "src", "type": "DIRECTORY"}],
                "isLastPage": True,
            }
        },
    ]

    rows, seen = call_pages(
        monkeypatch,
        pages,
        lambda: bitbucket.list_directory(BASE, "DEMO/widgets", token=TOKEN),
    )

    assert rows == [
        {"path": "README.md", "type": "FILE", "size": 0},
        {"path": "src", "type": "DIRECTORY", "size": None},
    ]
    assert seen == [
        {"url": BROWSE_URL, "start": 0, "limit": 100},
        {"url": BROWSE_URL, "start": 9, "limit": 100},
    ]


def test_ls_encodes_a_subdirectory_once_and_repeats_the_fixed_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = [
        {
            "children": {
                "values": [{"path": "a b.txt", "type": "FILE", "size": 0}],
                "isLastPage": False,
                "nextPageStart": 3,
            }
        },
        {
            "children": {
                "values": [{"path": "c.txt", "type": "FILE", "size": 12}],
                "isLastPage": True,
            }
        },
    ]

    rows, seen = call_pages(
        monkeypatch,
        pages,
        lambda: bitbucket.list_directory(
            BASE, "DEMO/widgets", SUBDIR, token=TOKEN, at=AT
        ),
    )

    assert [row["path"] for row in rows] == ["a b.txt", "c.txt"]
    assert seen == [
        {
            "url": f"{BROWSE_URL}/{SUBDIR_ENCODED}",
            "start": 0,
            "limit": 100,
            "at": AT,
        },
        {
            "url": f"{BROWSE_URL}/{SUBDIR_ENCODED}",
            "start": 3,
            "limit": 100,
            "at": AT,
        },
    ]


@pytest.mark.parametrize(
    "path",
    [
        "/absolute",
        "trailing/",
        "empty//segment",
        ".",
        "..",
        "dir/../secret",
        "back\\slash",
        "surrogate\ud800",
    ],
)
def test_ls_rejects_an_unsafe_directory_path_before_the_session(
    monkeypatch: pytest.MonkeyPatch, path: str
) -> None:
    monkeypatch.setattr(bitbucket, "bearer_session", forbid_session)

    with pytest.raises(AtlaWireError, match="path"):
        bitbucket.list_directory(BASE, "DEMO/widgets", path, token=TOKEN)


@pytest.mark.parametrize(
    "page",
    [
        {"lines": [{"text": "print('hello')"}], "isLastPage": True},
        {"children": [], "isLastPage": True},
        {"children": None, "isLastPage": True},
    ],
    ids=["file-lines", "list-children", "null-children"],
)
def test_ls_rejects_a_missing_or_malformed_children_envelope(
    monkeypatch: pytest.MonkeyPatch, page: dict[str, object]
) -> None:
    with pytest.raises(AtlaWireError, match="children"):
        call_pages(
            monkeypatch,
            [page],
            lambda: bitbucket.list_directory(BASE, "DEMO/widgets", token=TOKEN),
        )


def test_ls_rejects_malformed_nested_children_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = {"children": {"values": "not-a-list", "isLastPage": True}}

    with pytest.raises(AtlaWireError, match="values"):
        call_pages(
            monkeypatch,
            [page],
            lambda: bitbucket.list_directory(BASE, "DEMO/widgets", token=TOKEN),
        )


def test_ls_validates_a_children_next_page_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = {
        "children": {
            "values": [{"path": "a.txt"}],
            "isLastPage": False,
            "nextPageStart": 0,
        }
    }

    with pytest.raises(AtlaWireError, match="nextPageStart"):
        call_pages(
            monkeypatch,
            [page],
            lambda: bitbucket.list_directory(BASE, "DEMO/widgets", token=TOKEN),
        )


def test_the_page_cap_after_a_nonterminal_page_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = {
        "children": {
            "values": [{"path": "a.txt"}],
            "isLastPage": False,
            "nextPageStart": 7,
        }
    }

    with pytest.raises(AtlaWireError, match="page limit"):
        call_pages(
            monkeypatch,
            [page],
            lambda: bitbucket.list_directory(
                BASE, "DEMO/widgets", token=TOKEN, max_pages=1
            ),
        )


@pytest.mark.parametrize(
    "value",
    [
        {"path": "a.txt", "type": 5},
        {"path": "a.txt", "size": True},
        {"path": "a.txt", "size": -1},
        {"path": "a.txt", "size": "5"},
        {"path": None},
        {"path": ""},
        {"path": {"components": []}},
        5,
    ],
    ids=[
        "non-string-type",
        "boolean-size",
        "negative-size",
        "string-size",
        "null-path",
        "empty-path",
        "empty-components",
        "not-an-object",
    ],
)
def test_ls_rejects_malformed_child_metadata(value: object) -> None:
    with pytest.raises(AtlaWireError, match="child|path"):
        bitbucket._directory_entry(value)


def test_ls_keeps_a_zero_size_and_the_shared_path_priority() -> None:
    value = {
        "path": {
            "toString": "src/full.txt",
            "components": ["unused"],
            "name": "full.txt",
        },
        "type": "FILE",
        "size": 0,
    }

    assert bitbucket._directory_entry(value) == {
        "path": "src/full.txt",
        "type": "FILE",
        "size": 0,
    }


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ({"path": "src/\ud800.txt"}, "child path"),
        ({"path": "ok.txt", "type": "FILE\ud800"}, "child type"),
    ],
)
def test_ls_rejects_unencodable_projected_metadata(
    value: dict[str, object], message: str
) -> None:
    with pytest.raises(AtlaWireError, match=message):
        bitbucket._directory_entry(value)
