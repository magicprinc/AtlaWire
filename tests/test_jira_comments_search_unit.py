"""Unit checks for author-wide Jira comment discovery.

The transport, user search, and every response are synthetic. No test reads a
credential or contacts a server.
"""

from __future__ import annotations

import gc
import re
import weakref
from collections.abc import Sequence
from contextlib import nullcontext
from datetime import datetime, timedelta

import pytest

from atlawire import jira
from atlawire import jira_comments_search as comments_search
from atlawire.http import AtlaWireError
from atlawire.regex_helper import HelperFailure, InvalidRegex, RegexTimeout
from atlawire.repo_grep import REGEX_TIMEOUT_DEFAULT

BASE = "https://jira.example.invalid/jira"
TOKEN = "fixture-author-comments-token"
LOGIN = "v.baturin"
DISPLAY = "Vladislav Baturin"
OTHER = "other.user"
CREATED = "2026-11-01T10:00:00.000+0300"


class FakeRegex:
    """Independent page-batch double for the shared regex helper."""

    def __init__(self) -> None:
        self.validations: list[tuple[str, bool, float]] = []
        self.batches: list[tuple[str, list[str], bool, float]] = []
        self.validation_error: Exception | None = None
        self.match_errors: dict[int, Exception] = {}

    def validate(
        self, pattern: str, *, ignore_case: bool, timeout_s: float
    ) -> None:
        self.validations.append((pattern, ignore_case, timeout_s))
        if self.validation_error is not None:
            raise self.validation_error
        try:
            re.compile(pattern)
        except re.error:
            raise InvalidRegex from None

    def match(
        self,
        documents: Sequence[str],
        pattern: str,
        *,
        ignore_case: bool,
        timeout_s: float,
    ) -> list[bool]:
        index = len(self.batches)
        texts = list(documents)
        self.batches.append((pattern, texts, ignore_case, timeout_s))
        error = self.match_errors.get(index)
        if error is not None:
            raise error
        flags = re.IGNORECASE if ignore_case else 0
        return [re.search(pattern, text, flags) is not None for text in texts]


class FakeJira:
    """Record lookups and return canned search and thread pages."""

    def __init__(
        self,
        *,
        users: dict[str, list[dict[str, object]]] | None = None,
        user_pages: dict[str, dict[int, list[dict[str, object]]]] | None = None,
        search_pages: dict[int, object] | None = None,
        threads: dict[str, dict[int, object]] | None = None,
    ) -> None:
        self.base = BASE
        self.users = users if users is not None else {}
        self.user_pages = user_pages if user_pages is not None else {}
        self.search_pages = search_pages if search_pages is not None else {}
        self.threads = threads if threads is not None else {}
        self.user_queries: list[str] = []
        self.user_arguments: list[tuple[object, ...]] = []
        self.current_calls: list[tuple[object, ...]] = []
        self.http: list[tuple[str, dict[str, str | int]]] = []
        self.regex = FakeRegex()

    def search_users(
        self,
        base: str,
        username: str,
        *,
        token: str,
        start_at: int = 0,
        max_results: int = 50,
        allow_http_loopback: bool = False,
    ) -> list[dict[str, object]]:
        self.user_queries.append(username)
        self.user_arguments.append(
            (base, username, token, start_at, max_results, allow_http_loopback)
        )
        if username in self.user_pages:
            return list(self.user_pages[username].get(start_at, []))
        if start_at:
            return []
        return self.users.get(username, [])

    def get_json_object(
        self,
        session: object,
        url: str,
        *,
        params: dict[str, str | int],
    ) -> dict[str, object]:
        self.http.append((url, dict(params)))
        start = params["startAt"]
        assert isinstance(start, int)
        if url == f"{self.base}/rest/api/2/search":
            return self._page(self.search_pages, start, "search")
        match = re.fullmatch(
            rf"{re.escape(self.base)}/rest/api/2/issue/([^/]+)/comment", url
        )
        if match is not None:
            key = match.group(1)
            return self._page(
                self.threads.get(key, {}), start, f"thread {key}"
            )
        raise AssertionError(f"unexpected URL: {url}")

    @staticmethod
    def _page(pages: dict[int, object], start: int, label: str) -> dict[str, object]:
        if start not in pages:
            raise AssertionError(f"unexpected {label} start {start}")
        value = pages[start]
        if isinstance(value, Exception):
            raise value
        assert isinstance(value, dict)
        return value


def user(name: str = LOGIN, display: str | None = DISPLAY) -> dict[str, object]:
    row: dict[str, object] = {"name": name}
    if display is not None:
        row["displayName"] = display
    return row


def comment(
    cid: object,
    *,
    author: object = LOGIN,
    created: object = CREATED,
    body: object = "text",
) -> dict[str, object]:
    author_value = {"name": author} if isinstance(author, str) else author
    return {
        "id": str(cid),
        "author": author_value,
        "created": created,
        "body": body,
    }


def issue(
    key: object,
    *,
    comments: list[dict[str, object]] | None = None,
    total: object | None = None,
    updated: object = CREATED,
    summary: object | None = None,
) -> dict[str, object]:
    values = comments if comments is not None else []
    return {
        "key": key,
        "fields": {
            "summary": f"summary {key}" if summary is None else summary,
            "updated": updated,
            "comment": {
                "comments": values,
                "total": len(values) if total is None else total,
            },
        },
    }


def search_page(
    issues: Sequence[object],
    *,
    start: int = 0,
    total: object | None = None,
    max_results: object = 100,
    is_last: object | None = None,
) -> dict[str, object]:
    value: dict[str, object] = {
        "startAt": start,
        "maxResults": max_results,
        "total": len(issues) if total is None else total,
        "issues": list(issues),
    }
    if is_last is not None:
        value["isLast"] = is_last
    return value


def thread_page(
    comments: Sequence[object],
    *,
    start: int = 0,
    total: object | None = None,
    max_results: object = 100,
) -> dict[str, object]:
    return {
        "startAt": start,
        "maxResults": max_results,
        "total": len(comments) if total is None else total,
        "comments": list(comments),
    }


def fake_with(
    issues: Sequence[object],
    *,
    users: dict[str, list[dict[str, object]]] | None = None,
    threads: dict[str, dict[int, object]] | None = None,
    total: object | None = None,
    is_last: object | None = True,
) -> FakeJira:
    return FakeJira(
        users=users if users is not None else {LOGIN: [user()]},
        search_pages={0: search_page(issues, total=total, is_last=is_last)},
        threads=threads,
    )


_CURRENT_NOT_SET = object()


def run(
    fake: FakeJira,
    monkeypatch: pytest.MonkeyPatch,
    *,
    base: str = BASE,
    user: str | None = LOGIN,
    current_user: object = _CURRENT_NOT_SET,
    days: int = 90,
    limit: int = 10,
    project: str | None = None,
    grep: str | None = None,
    max_issues: int = 20000,
    allow_http_loopback: bool = False,
) -> list[comments_search.AuthorCommentRow]:
    fake.base = base
    fake.current_calls = []
    monkeypatch.setattr(jira, "search_users", fake.search_users)
    monkeypatch.setattr(
        comments_search, "validate_regex", fake.regex.validate
    )
    monkeypatch.setattr(
        comments_search, "match_documents", fake.regex.match
    )

    if current_user is _CURRENT_NOT_SET:

        def unexpected_current_user(*args: object, **kwargs: object) -> object:
            raise AssertionError("Unexpected current-user lookup.")

        monkeypatch.setattr(jira, "get_current_user", unexpected_current_user)
    else:

        def current_user_stub(
            base_url: str, *, token: str, allow_http_loopback: bool = False
        ) -> object:
            fake.current_calls.append((base_url, token, allow_http_loopback))
            return current_user

        monkeypatch.setattr(jira, "get_current_user", current_user_stub)

    monkeypatch.setattr(
        comments_search, "bearer_session", lambda token: nullcontext(None)
    )
    monkeypatch.setattr(comments_search, "get_json_object", fake.get_json_object)
    return comments_search.find_author_comments(
        base,
        user,
        token=TOKEN,
        days=days,
        limit=limit,
        project=project,
        grep=grep,
        max_issues=max_issues,
        allow_http_loopback=allow_http_loopback,
    )


def test_only_the_exact_author_is_kept_newest_first_with_a_deep_link(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = fake_with(
        [
            issue(
                "DEMO-1",
                comments=[
                    comment(11, created="2026-10-01T10:00:00.000+0300"),
                    comment(
                        12,
                        author=OTHER,
                        created="2026-11-09T10:00:00.000+0300",
                    ),
                ],
            ),
            issue(
                "DEMO-2",
                comments=[comment(21, created="2026-11-05T10:00:00.000+0300")],
            ),
        ]
    )

    rows = run(fake, monkeypatch, limit=5)

    assert [row["created"][:10] for row in rows] == ["2026-11-05", "2026-10-01"]
    assert {row["key"] for row in rows} == {"DEMO-1", "DEMO-2"}
    assert rows[0]["url"] == (
        f"{BASE}/browse/DEMO-2?focusedCommentId=21#comment-21"
    )
    assert rows[0]["author"] == DISPLAY
    assert rows[0]["comment_id"] == "21"
    assert rows[0]["body"] == "text"
    assert fake.user_arguments == [
        (BASE, LOGIN, TOKEN, 0, comments_search.USER_SEARCH_LIMIT, False)
    ]
    search_url, search_params = fake.http[0]
    assert search_url == f"{BASE}/rest/api/2/search"
    jql = search_params["jql"]
    assert isinstance(jql, str)
    assert jql.startswith("updated >= -90d")
    assert search_params["fields"] == "summary,comment,updated"
    assert search_params["startAt"] == 0
    assert search_params["maxResults"] == 100


def test_a_truncated_thread_is_completed_before_filtering(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = fake_with(
        [
            issue(
                "DEMO-3",
                comments=[comment(31, author=OTHER)],
                total=2,
            )
        ],
        threads={
            "DEMO-3": {
                0: thread_page(
                    [
                        comment(31, author=OTHER),
                        comment(
                            32,
                            created="2026-11-17T09:00:00.000+0300",
                            body="need an offset",
                        ),
                    ]
                )
            }
        },
    )

    rows = run(fake, monkeypatch, limit=5)

    assert ("DEMO-3", 0) in [
        (url.rsplit("/issue/", 1)[1].split("/")[0], params["startAt"])
        for url, params in fake.http
        if url.endswith("/comment")
    ]
    assert [row["comment_id"] for row in rows] == ["32"]
    assert rows[0]["body"] == "need an offset"


def test_thread_pagination_reads_every_page_with_its_true_offset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = [
        comment(
            1000 + index,
            author=OTHER,
            created=f"2026-10-01T10:{index % 60:02d}:00.000+0300",
        )
        for index in range(230)
    ]
    thread.append(
        comment(
            5000,
            created="2026-11-01T10:00:00.000+0300",
            body="found",
        )
    )
    fake = fake_with(
        [issue("DEMO-1001", comments=thread[:1], total=len(thread))],
        threads={
            "DEMO-1001": {
                0: thread_page(thread[0:100], start=0, total=len(thread)),
                100: thread_page(thread[100:200], start=100, total=len(thread)),
                200: thread_page(thread[200:], start=200, total=len(thread)),
            }
        },
    )

    rows = run(fake, monkeypatch, limit=5)

    assert [row["comment_id"] for row in rows] == ["5000"]
    starts = [
        params["startAt"]
        for url, params in fake.http
        if url.endswith("/comment")
    ]
    assert starts == [0, 100, 200]


def test_a_short_thread_page_advances_by_the_rows_actually_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    thread = [
        comment(1000 + index, author=OTHER, created=CREATED) for index in range(149)
    ]
    thread.append(comment(5000, created="2026-11-01T10:00:00.000+0300"))
    fake = fake_with(
        [issue("DEMO-1002", comments=thread[:1], total=len(thread))],
        threads={
            "DEMO-1002": {
                0: thread_page(
                    thread[:50], start=0, total=len(thread), max_results=50
                ),
                50: thread_page(
                    thread[50:], start=50, total=len(thread), max_results=100
                ),
            }
        },
    )

    rows = run(fake, monkeypatch, limit=5)

    assert [row["comment_id"] for row in rows] == ["5000"]
    starts = [
        params["startAt"]
        for url, params in fake.http
        if url.endswith("/comment")
    ]
    assert starts == [0, 50]


def test_a_short_search_page_advances_by_the_rows_actually_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    issues = [
        issue(f"DEMO-{index}", comments=[]) for index in range(60)
    ]
    issues[50] = issue(
        "DEMO-50",
        comments=[comment(1, created="2026-11-01T09:00:00.000+0300")],
    )
    fake = FakeJira(
        users={LOGIN: [user()]},
        search_pages={
            0: search_page(issues[:50], start=0, total=60, max_results=50),
            50: search_page(
                issues[50:], start=50, total=60, max_results=10, is_last=True
            ),
        },
    )

    rows = run(fake, monkeypatch, limit=1)

    assert [row["comment_id"] for row in rows] == ["1"]
    starts = [params["startAt"] for _, params in fake.http]
    assert starts == [0, 50]


def test_a_later_search_page_failure_publishes_no_partial_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeJira(
        users={LOGIN: [user()]},
        search_pages={
            0: search_page(
                [issue("DEMO-1", comments=[comment(1)])],
                start=0,
                total=2,
                is_last=False,
            ),
            1: AtlaWireError("HTTP 500: request failed."),
        },
    )

    with pytest.raises(AtlaWireError, match="HTTP 500"):
        run(fake, monkeypatch, limit=5)

    assert [params["startAt"] for _, params in fake.http] == [0, 1]


def test_a_later_thread_page_failure_publishes_no_partial_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = fake_with(
        [issue("DEMO-4", comments=[comment(41, author=OTHER)], total=3)],
        threads={
            "DEMO-4": {
                0: thread_page(
                    [
                        comment(41, author=OTHER),
                        comment(
                            42,
                            created="2026-11-02T10:00:00.000+0300",
                        ),
                    ],
                    start=0,
                    total=3,
                ),
                2: AtlaWireError("HTTP 503: request failed."),
            }
        },
    )

    with pytest.raises(AtlaWireError, match="HTTP 503"):
        run(fake, monkeypatch, limit=5)

    starts = [
        params["startAt"]
        for url, params in fake.http
        if url.endswith("/comment")
    ]
    assert starts == [0, 2]


def test_the_issue_budget_is_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = fake_with(
        [issue("DEMO-1", comments=[comment(1)])],
        total=2,
        is_last=False,
    )

    with pytest.raises(AtlaWireError, match="budget"):
        run(fake, monkeypatch, max_issues=1)

    assert len(fake.http) == 1
    assert fake.http[0][1]["maxResults"] == 1


def test_the_comment_page_limit_is_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(comments_search, "COMMENT_PAGE_LIMIT", 2)
    fake = fake_with(
        [issue("DEMO-5", comments=[comment(90, author=OTHER)], total=3)],
        threads={
            "DEMO-5": {
                0: thread_page(
                    [comment(1, author=OTHER)], start=0, total=3, max_results=1
                ),
                1: thread_page(
                    [comment(2, author=OTHER)], start=1, total=3, max_results=1
                ),
                2: thread_page(
                    [comment(3, author=OTHER)], start=2, total=3, max_results=1
                ),
            }
        },
    )

    with pytest.raises(AtlaWireError, match="page limit"):
        run(fake, monkeypatch)

    starts = [
        params["startAt"]
        for url, params in fake.http
        if url.endswith("/comment")
    ]
    assert starts == [0, 1]


def test_comment_instants_are_compared_across_offsets_and_fractions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = fake_with(
        [
            issue(
                "DEMO-1",
                comments=[
                    comment(1, created="2026-11-18T01:45:00.000+0100")
                ],
            ),
            issue(
                "DEMO-2",
                comments=[
                    comment(2, created="2026-11-18T01:15:00.900+0000")
                ],
            ),
            issue(
                "DEMO-3",
                comments=[
                    comment(3, created="2026-11-18T01:15:00.100+0000")
                ],
            ),
        ]
    )

    rows = run(fake, monkeypatch, limit=5)

    assert [row["key"] for row in rows] == ["DEMO-2", "DEMO-3", "DEMO-1"]
    assert [row["created"] for row in rows] == [
        "2026-11-18T01:15:00.900+0000",
        "2026-11-18T01:15:00.100+0000",
        "2026-11-18T01:45:00.000+0100",
    ]


def test_equal_instants_keep_the_first_seen_rows_across_pages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = "2026-11-18T10:00:00.000+0300"
    fake = FakeJira(
        users={LOGIN: [user()]},
        search_pages={
            0: search_page(
                [issue("DEMO-1", comments=[comment(1, created=created)])],
                start=0,
                total=2,
                is_last=False,
            ),
            1: search_page(
                [
                    issue(
                        "DEMO-2",
                        comments=[
                            comment(2, created=created),
                            comment(3, created=created),
                        ],
                    )
                ],
                start=1,
                total=2,
                is_last=True,
            ),
        },
    )

    rows = run(fake, monkeypatch, limit=2)

    assert [row["comment_id"] for row in rows] == ["1", "2"]
    assert [row["created"] for row in rows] == [created, created]


def test_a_newer_comment_on_a_later_page_is_not_lost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeJira(
        users={LOGIN: [user()]},
        search_pages={
            0: search_page(
                [
                    issue(
                        "DEMO-1",
                        updated="2026-11-18T10:00:00.900+0300",
                        comments=[
                            comment(
                                1, created="2026-11-18T10:00:00.100+0300"
                            )
                        ],
                    )
                ],
                start=0,
                total=2,
                is_last=False,
            ),
            1: search_page(
                [
                    issue(
                        "DEMO-2",
                        updated="2026-11-18T10:00:00.800+0300",
                        comments=[
                            comment(
                                2, created="2026-11-18T10:00:00.700+0300"
                            )
                        ],
                    )
                ],
                start=1,
                total=2,
                is_last=True,
            ),
        },
    )

    rows = run(fake, monkeypatch, limit=1)

    assert [row["comment_id"] for row in rows] == ["2"]
    assert len(fake.http) == 2


def test_every_search_page_is_scanned_after_the_limit_is_reached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeJira(
        users={LOGIN: [user()]},
        search_pages={
            0: search_page(
                [
                    issue(
                        "DEMO-1",
                        updated="2026-11-18T13:00:00.000+0300",
                        comments=[
                            comment(
                                1, created="2026-11-18T12:30:00.000+0300"
                            )
                        ],
                    )
                ],
                start=0,
                total=2,
                is_last=False,
            ),
            1: search_page(
                [
                    issue(
                        "DEMO-2",
                        updated="2026-11-18T12:00:00.000+0300",
                        comments=[
                            comment(
                                2, created="2026-11-18T11:00:00.000+0300"
                            )
                        ],
                    )
                ],
                start=1,
                total=2,
                is_last=True,
            ),
        },
    )

    rows = run(fake, monkeypatch, limit=1)

    assert [row["comment_id"] for row in rows] == ["1"]
    assert [params["startAt"] for _, params in fake.http] == [0, 1]


def test_an_ambiguous_user_is_rejected_before_the_comment_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = fake_with(
        [],
        users={
            "vlad": [
                user("v.vorobiev", "Vlad Vorobiev"),
                user("v.vorobyev", "Vladislav Vorobyev"),
            ]
        },
    )

    with pytest.raises(AtlaWireError, match="more than one"):
        run(fake, monkeypatch, user="vlad")

    assert fake.user_queries == ["vlad", "vlad"]
    assert [args[3] for args in fake.user_arguments] == [0, 2]
    assert fake.http == []


def test_a_full_user_page_with_many_candidates_is_rejected_as_ambiguous(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [
        user(f"user-{index}", f"User {index}")
        for index in range(comments_search.USER_SEARCH_LIMIT)
    ]
    fake = fake_with([], users={"ada": rows})

    with pytest.raises(AtlaWireError, match="more than one"):
        run(fake, monkeypatch, user="ada")

    assert fake.user_queries == ["ada", "ada"]
    assert [args[3] for args in fake.user_arguments] == [0, 50]
    assert fake.http == []


def test_a_singleton_user_page_must_be_confirmed_by_an_empty_next_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Jira 8.22 has no user-search total/isLast; the empty page is the only
    # practical stop signal, not proof of complete discovery.
    fake = FakeJira(
        user_pages={LOGIN: {0: [user("only.user", "Only User")]}},
        search_pages={0: search_page([], is_last=True)},
    )

    assert run(fake, monkeypatch, user=LOGIN) == []
    assert [args[3] for args in fake.user_arguments] == [0, 1]
    assert fake.user_queries == [LOGIN, LOGIN]


def test_a_second_user_on_the_next_page_makes_the_lookup_ambiguous(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeJira(
        user_pages={
            LOGIN: {
                0: [user("first.user", "First User")],
                1: [user("second.user", "Second User")],
            }
        },
        search_pages={0: search_page([], is_last=True)},
    )

    with pytest.raises(AtlaWireError, match="more than one"):
        run(fake, monkeypatch, user=LOGIN)

    assert [args[3] for args in fake.user_arguments] == [0, 1, 2]
    assert fake.http == []


def test_a_duplicate_user_page_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeJira(
        user_pages={
            LOGIN: {
                0: [user("only.user", "Only User")],
                1: [user("only.user", "Only User")],
            }
        },
        search_pages={0: search_page([], is_last=True)},
    )

    with pytest.raises(AtlaWireError, match="duplicate"):
        run(fake, monkeypatch, user=LOGIN)

    assert [args[3] for args in fake.user_arguments] == [0, 1]


def test_the_user_page_budget_is_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(comments_search, "USER_PAGE_LIMIT", 1)
    fake = FakeJira(
        user_pages={LOGIN: {0: [user("only.user", "Only User")]}},
        search_pages={0: search_page([], is_last=True)},
    )

    with pytest.raises(AtlaWireError, match="page budget"):
        run(fake, monkeypatch, user=LOGIN)

    assert [args[3] for args in fake.user_arguments] == [0]


def test_user_page_budget_fails_closed_before_a_later_exact_login(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(comments_search, "USER_PAGE_LIMIT", 1)
    fake = FakeJira(
        user_pages={
            LOGIN: {
                0: [
                    user("first.user", "First User"),
                    user("second.user", "Second User"),
                ],
                2: [user(LOGIN, DISPLAY)],
            }
        },
        search_pages={0: search_page([], is_last=True)},
    )

    with pytest.raises(AtlaWireError, match="page budget"):
        run(fake, monkeypatch, user=LOGIN)

    assert [args[3] for args in fake.user_arguments] == [0]
    assert fake.http == []


def test_an_exact_login_stops_user_paging_immediately(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeJira(
        user_pages={
            LOGIN: {
                0: [user("other.user", "Other User")],
                1: [user(LOGIN, DISPLAY)],
                2: [user("later.user", "Later User")],
            }
        },
        search_pages={0: search_page([], is_last=True)},
    )

    assert run(fake, monkeypatch, user=LOGIN) == []
    assert [args[3] for args in fake.user_arguments] == [0, 1]


def test_an_exact_login_on_a_later_page_wins_over_earlier_nonexact_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeJira(
        user_pages={
            LOGIN: {
                0: [
                    user("first.user", "First User"),
                    user("second.user", "Second User"),
                ],
                2: [user(LOGIN, DISPLAY)],
            }
        },
        search_pages={
            0: search_page(
                [
                    issue(
                        "DEMO-40",
                        comments=[
                            comment(1, author="first.user", body="first"),
                            comment(2, author=LOGIN, body="exact"),
                        ],
                    )
                ],
                is_last=True,
            )
        },
    )

    rows = run(fake, monkeypatch, user=LOGIN)

    assert [row["comment_id"] for row in rows] == ["2"]
    assert rows[0]["author"] == DISPLAY
    assert [args[3] for args in fake.user_arguments] == [0, 2]
    assert fake.user_queries == [LOGIN, LOGIN]


def test_an_exact_login_wins_over_other_search_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = fake_with(
        [
            issue(
                "DEMO-6",
                comments=[
                    comment(1, author="ada.old"),
                    comment(2, author="ada"),
                ],
            )
        ],
        users={
            "ada": [
                user("ada.old", "Ada Old"),
                user("ada", "Ada Lovelace"),
            ]
        },
    )

    rows = run(fake, monkeypatch, user="ada")

    assert [row["comment_id"] for row in rows] == ["2"]
    assert rows[0]["author"] == "Ada Lovelace"


def test_cyrillic_names_are_resolved_through_bbk_transliteration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = fake_with([], users={"baturin": [user()]})

    assert run(fake, monkeypatch, user="Батурин") == []
    assert fake.user_queries == ["Батурин", "baturin", "baturin"]


def test_a_four_letter_transliterated_prefix_is_the_last_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = fake_with(
        [],
        users={"voro": [user("v.vorobiev", "Vlad Vorobiev")]},
    )

    assert run(fake, monkeypatch, user="Воробьев") == []
    assert fake.user_queries == ["Воробьев", "vorobyev", "voro", "voro"]


def test_an_unknown_user_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = fake_with([], users={})

    with pytest.raises(AtlaWireError, match="No Jira user"):
        run(fake, monkeypatch, user="Ыванов")

    assert fake.user_queries == ["Ыванов", "yvanov", "yvan"]
    assert fake.http == []


def test_an_omitted_user_uses_the_authenticated_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = fake_with(
        [issue("DEMO-9", comments=[comment(1)])],
        users={LOGIN: [user("someone.else", "Someone Else")]},
    )

    rows = run(
        fake,
        monkeypatch,
        user=None,
        current_user={
            "name": LOGIN,
            "displayName": DISPLAY,
            "email": "ada@example.invalid",
        },
    )

    assert [row["comment_id"] for row in rows] == ["1"]
    assert rows[0]["author"] == DISPLAY
    assert fake.user_queries == []
    assert fake.current_calls == [(BASE, TOKEN, False)]


def test_the_current_user_falls_back_to_the_login_for_the_author(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = fake_with([issue("DEMO-10", comments=[comment(1)])])

    rows = run(
        fake,
        monkeypatch,
        user=None,
        current_user={"name": LOGIN},
    )

    assert rows[0]["author"] == LOGIN
    assert fake.user_queries == []


def test_a_current_user_without_a_login_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = fake_with([])

    with pytest.raises(AtlaWireError, match="non-empty name"):
        run(
            fake,
            monkeypatch,
            user=None,
            current_user={"displayName": DISPLAY},
        )

    assert fake.user_queries == []
    assert fake.http == []


def test_invalid_parameters_precede_the_current_user_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = fake_with([])

    with pytest.raises(AtlaWireError, match="day window"):
        run(fake, monkeypatch, user=None, days=0)

    assert fake.current_calls == []


@pytest.mark.parametrize(
    ("kwargs", "diagnostic"),
    [
        ({"days": 0}, "day window"),
        ({"days": True}, "day window"),
        ({"days": None}, "day window"),
        ({"limit": 0}, "result limit"),
        ({"limit": False}, "result limit"),
        ({"limit": "5"}, "result limit"),
        ({"max_issues": 0}, "issue budget"),
        ({"max_issues": True}, "issue budget"),
        ({"max_issues": 1.5}, "issue budget"),
        ({"project": 'PLAT" OR 1=1'}, "project key"),
        ({"project": "plat"}, "project key"),
        ({"project": ""}, "project key"),
        ({"grep": 7}, "grep pattern"),
        ({"user": ""}, "user login"),
        ({"user": "   "}, "user login"),
        ({"user": 7}, "user login"),
    ],
)
def test_invalid_parameters_are_rejected_before_any_lookup(
    monkeypatch: pytest.MonkeyPatch,
    kwargs: dict[str, object],
    diagnostic: str,
) -> None:
    fake = fake_with([])

    with pytest.raises(AtlaWireError, match=diagnostic):
        run(fake, monkeypatch, **kwargs)  # type: ignore[arg-type]

    assert fake.user_queries == []
    assert fake.http == []


@pytest.mark.parametrize(
    "base",
    [
        "http://127.0.0.1:8080/jira",
        "https://synthetic-user@jira.example.invalid/jira",
        f"{BASE}?window=90",
        f"{BASE}#fragment",
    ],
    ids=["http-without-opt-in", "userinfo", "query", "fragment"],
)
def test_an_unsafe_base_url_is_rejected_before_any_lookup(
    monkeypatch: pytest.MonkeyPatch, base: str
) -> None:
    fake = fake_with([])

    with pytest.raises(AtlaWireError, match="base URL"):
        run(fake, monkeypatch, base=base)

    assert fake.user_queries == []
    assert fake.http == []


def test_explicit_http_loopback_is_forwarded_to_user_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = "http://127.0.0.1:8080/jira"
    fake = fake_with([])

    assert run(fake, monkeypatch, base=base, allow_http_loopback=True) == []
    assert fake.user_arguments[0][0] == base
    assert fake.user_arguments[0][5] is True
    assert fake.http[0][0] == f"{base}/rest/api/2/search"


def test_the_project_is_a_quoted_jql_literal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = fake_with([])

    run(fake, monkeypatch, days=30, project="DEMO")

    assert fake.http[0][1]["jql"] == (
        'updated >= -30d AND project = "DEMO" ORDER BY updated DESC'
    )


def test_an_author_without_a_display_name_uses_the_login(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = fake_with(
        [issue("DEMO-7", comments=[comment(1)])],
        users={LOGIN: [user(display=None)]},
    )

    rows = run(fake, monkeypatch)

    assert rows[0]["author"] == LOGIN


@pytest.mark.parametrize(
    "issues",
    [
        [issue("DEMO-1", comments=[comment(7)]), issue("DEMO-2", comments=[comment(7)])],
        [issue("DEMO-1", comments=[comment(7), comment(7)])],
    ],
    ids=["across-issues", "within-one-issue"],
)
def test_duplicate_comment_ids_are_rejected(
    monkeypatch: pytest.MonkeyPatch, issues: list[object]
) -> None:
    fake = fake_with(issues)

    with pytest.raises(AtlaWireError, match="duplicate comment IDs"):
        run(fake, monkeypatch)


@pytest.mark.parametrize(
    ("value", "diagnostic"),
    [
        ({"id": 7, "author": {"name": LOGIN}, "created": CREATED}, "comment ID"),
        ({"id": "", "author": {"name": LOGIN}, "created": CREATED}, "comment ID"),
        ({"id": "abc", "author": {"name": LOGIN}, "created": CREATED}, "comment ID"),
        ({"id": "7", "author": "ada", "created": CREATED}, "author object"),
        ({"id": "7", "author": {"name": 7}, "created": CREATED}, "author name"),
        ({"id": "7", "author": {"name": LOGIN}, "created": 7}, "created timestamp"),
        ({"id": "7", "author": {"name": LOGIN}, "created": ""}, "created timestamp"),
        (
            {"id": "7", "author": {"name": LOGIN}, "created": "not-a-time"},
            "created timestamp",
        ),
        (
            {"id": "7", "author": {"name": LOGIN}, "created": "2026-11-01T10:00:00"},
            "timezone",
        ),
        (
            {"id": "7", "author": {"name": LOGIN}, "created": CREATED, "body": {}},
            "body as text",
        ),
    ],
)
def test_malformed_matching_comment_records_are_rejected(
    monkeypatch: pytest.MonkeyPatch, value: dict[str, object], diagnostic: str
) -> None:
    fake = fake_with([issue("DEMO-1", comments=[value])])

    with pytest.raises(AtlaWireError, match=diagnostic):
        run(fake, monkeypatch)


@pytest.mark.parametrize(
    "value",
    [
        None,
        7,
        {"comments": None, "total": 0},
        {"comments": [], "total": -1},
        {"comments": [comment(1)], "total": 0},
        {"comments": [comment(1)], "total": 1, "maxResults": 0},
        {"comments": ["text"], "total": 1},
    ],
    ids=[
        "missing",
        "wrong-type",
        "non-list-comments",
        "negative-total",
        "total-below-rows",
        "max-results-below-rows",
        "non-object-comment",
    ],
)
def test_a_malformed_comment_preview_is_rejected(
    monkeypatch: pytest.MonkeyPatch, value: object
) -> None:
    broken = issue("DEMO-1")
    fields = broken["fields"]
    assert isinstance(fields, dict)
    fields["comment"] = value
    fake = fake_with([broken])

    with pytest.raises(AtlaWireError):
        run(fake, monkeypatch)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.update({"key": "demo-1"}),
        lambda value: value.update({"fields": []}),
    ],
    ids=["lowercase-key", "non-object-fields"],
)
def test_a_malformed_issue_is_rejected(
    monkeypatch: pytest.MonkeyPatch, mutate: object
) -> None:
    broken = issue("DEMO-1")
    mutate(broken)  # type: ignore[operator]
    fake = fake_with([broken])

    with pytest.raises(AtlaWireError):
        run(fake, monkeypatch)


def test_a_non_text_summary_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broken = issue("DEMO-1")
    fields = broken["fields"]
    assert isinstance(fields, dict)
    fields["summary"] = 7
    fake = fake_with([broken])

    with pytest.raises(AtlaWireError, match="summary"):
        run(fake, monkeypatch)


@pytest.mark.parametrize(
    ("page", "diagnostic"),
    [
        (
            {
                "startAt": 1,
                "maxResults": 100,
                "total": 1,
                "issues": [issue("DEMO-1")],
            },
            "startAt",
        ),
        (
            {
                "startAt": 0,
                "maxResults": 100,
                "total": 2,
                "issues": [],
            },
            "empty page",
        ),
        (
            {
                "startAt": 0,
                "maxResults": 100,
                "total": 2,
                "issues": [issue("DEMO-1")],
                "isLast": True,
            },
            "isLast",
        ),
        (
            {
                "startAt": 0,
                "maxResults": 0,
                "total": 1,
                "issues": [issue("DEMO-1")],
            },
            "maxResults",
        ),
        (
            {
                "startAt": 0,
                "maxResults": 100,
                "total": 0,
                "issues": [issue("DEMO-1")],
            },
            "Inconsistent",
        ),
        (
            {
                "startAt": 0,
                "maxResults": 100,
                "issues": [issue("DEMO-1")],
            },
            "total",
        ),
        (
            {
                "startAt": 0,
                "maxResults": 100,
                "total": 1,
                "issues": {},
            },
            "issues array",
        ),
    ],
    ids=[
        "start-at-mismatch",
        "empty-before-total",
        "is-last-before-total",
        "zero-max-results",
        "total-below-rows",
        "missing-total",
        "non-list-issues",
    ],
)
def test_inconsistent_search_pages_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
    page: dict[str, object],
    diagnostic: str,
) -> None:
    fake = FakeJira(users={LOGIN: [user()]}, search_pages={0: page})

    with pytest.raises(AtlaWireError, match=diagnostic):
        run(fake, monkeypatch)


def test_a_search_total_that_changes_between_pages_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeJira(
        users={LOGIN: [user()]},
        search_pages={
            0: search_page(
                [issue("DEMO-1")], start=0, total=2, is_last=False
            ),
            1: search_page(
                [issue("DEMO-2")], start=1, total=3, is_last=True
            ),
        },
    )

    with pytest.raises(AtlaWireError, match="total changed"):
        run(fake, monkeypatch)


def test_a_page_that_returns_more_than_requested_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = fake_with(
        [issue("DEMO-1"), issue("DEMO-2")],
        total=2,
        is_last=False,
    )

    with pytest.raises(AtlaWireError, match="more issues than requested"):
        run(fake, monkeypatch, max_issues=1)


@pytest.mark.parametrize(
    ("thread", "diagnostic"),
    [
        (
            {
                0: {
                    "startAt": 1,
                    "maxResults": 100,
                    "total": 2,
                    "comments": [comment(1)],
                }
            },
            "startAt",
        ),
        (
            {
                0: {
                    "startAt": 0,
                    "maxResults": 100,
                    "total": 2,
                    "comments": [],
                }
            },
            "ended before all comments",
        ),
        (
            {
                0: {
                    "startAt": 0,
                    "maxResults": 0,
                    "total": 2,
                    "comments": [comment(1)],
                }
            },
            "maxResults",
        ),
        (
            {
                0: {
                    "startAt": 0,
                    "maxResults": 100,
                    "total": 2,
                    "comments": [comment(1), comment(1)],
                }
            },
            "duplicate comment IDs",
        ),
    ],
    ids=["start-at-mismatch", "empty-before-total", "zero-max-results", "duplicate"],
)
def test_inconsistent_comment_pages_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
    thread: dict[int, object],
    diagnostic: str,
) -> None:
    fake = fake_with(
        [issue("DEMO-1", comments=[comment(99, author=OTHER)], total=3)],
        threads={"DEMO-1": thread},
    )

    with pytest.raises(AtlaWireError, match=diagnostic):
        run(fake, monkeypatch)


def test_a_thread_total_that_changes_between_pages_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = fake_with(
        [issue("DEMO-1", comments=[comment(99, author=OTHER)], total=3)],
        threads={
            "DEMO-1": {
                0: thread_page(
                    [comment(1, author=OTHER)], start=0, total=2, max_results=1
                ),
                1: thread_page(
                    [comment(2, author=OTHER)], start=1, total=3, max_results=1
                ),
            }
        },
    )

    with pytest.raises(AtlaWireError, match="total changed"):
        run(fake, monkeypatch)


def test_a_thread_shorter_than_its_preview_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = fake_with(
        [
            issue(
                "DEMO-1",
                comments=[comment(98, author=OTHER), comment(99, author=OTHER)],
                total=5,
            )
        ],
        threads={
            "DEMO-1": {
                0: thread_page(
                    [comment(1, author=OTHER)], start=0, total=1, max_results=1
                )
            }
        },
    )

    with pytest.raises(AtlaWireError, match="thread metadata"):
        run(fake, monkeypatch)


def test_empty_results_are_valid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = fake_with([], is_last=True)

    assert run(fake, monkeypatch) == []
    assert len(fake.http) == 1

    matching_empty = fake_with(
        [issue("DEMO-1", comments=[comment(1, author=OTHER)])]
    )
    assert run(matching_empty, monkeypatch) == []


def test_the_limit_keeps_only_the_newest_matching_comments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = fake_with(
        [
            issue(
                "DEMO-1",
                comments=[
                    comment(1, created="2026-11-01T10:00:00.000+0300"),
                    comment(2, created="2026-11-03T10:00:00.000+0300"),
                    comment(3, created="2026-11-02T10:00:00.000+0300"),
                ],
            )
        ]
    )

    rows = run(fake, monkeypatch, limit=2)

    assert [row["comment_id"] for row in rows] == ["2", "3"]


def test_the_collector_retains_only_the_requested_number_of_rows() -> None:
    """Focused internal bound check; the public scan is covered separately.

    Comment-ID sets are cumulative in _collect and live outside this slot.
    """
    slot = comments_search._CollectorSlot(limit=3)
    base_time = datetime.fromisoformat("2026-11-01T10:00:00.000+0300")
    serial = 0

    for index in range(1000):
        row = comments_search.AuthorCommentRow(
            key="DEMO-1",
            summary="summary",
            created="2026-11-01T10:00:00.000+0300",
            author=DISPLAY,
            comment_id=str(index),
            url=(
                f"{BASE}/browse/DEMO-1?focusedCommentId={index}"
                f"#comment-{index}"
            ),
            body=f"body {index}",
        )
        serial = slot.offer(base_time + timedelta(seconds=index), row, serial)
        assert len(slot._heap) <= 3

    assert [row["comment_id"] for row in slot.finish()] == [
        "999",
        "998",
        "997",
    ]


class Body(str):
    """Weak-referenceable unique comment body for retention checks."""


class WeakPageSource:
    """Generate search pages on demand without retaining their bodies."""

    def __init__(self, *, count: int, top_n: int) -> None:
        self.count = count
        self.top_n = top_n
        self.refs: list[weakref.ReferenceType[Body]] = []
        self.starts: list[int] = []

    def get(
        self,
        session: object,
        url: str,
        *,
        params: dict[str, str | int],
    ) -> dict[str, object]:
        assert url == f"{BASE}/rest/api/2/search"
        start = params["startAt"]
        assert isinstance(start, int)
        self.starts.append(start)
        if start > self.top_n:
            gc.collect()
            released_through = start - self.top_n - 1
            for index in range(released_through + 1):
                assert self.refs[index]() is None, (
                    f"body {index} retained at page {start}"
                )
        created = f"2026-11-01T10:00:{start:02d}.000+0300"
        body = Body(f"body-{start}")
        self.refs.append(weakref.ref(body))
        page_issue = issue(
            f"DEMO-{start + 1}",
            comments=[comment(1000 + start, created=created, body=body)],
            total=1,
            updated=created,
        )
        return {
            "startAt": start,
            "maxResults": 1,
            "total": self.count,
            "issues": [page_issue],
            "isLast": start == self.count - 1,
        }


def test_public_scan_releases_bodies_evicted_from_the_top_n(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A public scan releases bodies once they leave the retained top-N.

    Checks run at page boundaries and only target pages older than the current
    page/top-N window, so active page and loop references do not create a false
    failure. Comment IDs remain cumulative and are not inspected.
    """
    page_count = 8
    top_n = 2
    source = WeakPageSource(count=page_count, top_n=top_n)
    fake = FakeJira(users={LOGIN: [user()]})

    monkeypatch.setattr(jira, "search_users", fake.search_users)
    monkeypatch.setattr(
        comments_search, "bearer_session", lambda token: nullcontext(None)
    )
    monkeypatch.setattr(comments_search, "get_json_object", source.get)

    rows = comments_search.find_author_comments(
        BASE, LOGIN, token=TOKEN, limit=top_n
    )
    gc.collect()

    assert source.starts == list(range(page_count))
    assert [row["comment_id"] for row in rows] == [
        str(1000 + page)
        for page in range(page_count - 1, page_count - top_n - 1, -1)
    ]
    assert [row["body"] for row in rows] == [
        f"body-{page}"
        for page in range(page_count - 1, page_count - top_n - 1, -1)
    ]

    # IDs remain in the cumulative duplicate-detection set; only bodies are
    # observed here. Older bodies must be released once they leave the top-N.
    for page in range(page_count - top_n):
        assert source.refs[page]() is None


def test_a_redirect_failure_is_not_retried_at_another_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeJira(
        users={LOGIN: [user()]},
        search_pages={
            0: AtlaWireError(
                "HTTP 302: redirect refused; check the base URL."
            )
        },
    )

    with pytest.raises(AtlaWireError, match="redirect refused"):
        run(fake, monkeypatch)

    assert [url for url, _ in fake.http] == [f"{BASE}/rest/api/2/search"]


def test_server_supplied_self_urls_are_never_used_as_destinations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    comment_row = comment(1)
    comment_row["self"] = "https://evil.example.invalid/rest/api/2/comment/1"
    comment_row["author"] = {
        "name": LOGIN,
        "self": "https://evil.example.invalid/rest/api/2/user?username=x",
    }
    value = issue("DEMO-8", comments=[comment_row])
    value["self"] = "https://evil.example.invalid/rest/api/2/issue/9"
    fake = fake_with([value])

    rows = run(fake, monkeypatch)

    assert rows[0]["url"].startswith(f"{BASE}/browse/DEMO-8?")
    assert all(url.startswith(BASE) for url, _ in fake.http)


def test_grep_matches_a_full_multiline_body_case_insensitively(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pattern = r"one\s+line two"
    fake = fake_with(
        [
            issue(
                "DEMO-20",
                comments=[
                    comment(1, body="Line One\nLINE TWO"),
                    comment(2, body="other"),
                ],
            )
        ]
    )

    rows = run(fake, monkeypatch, grep=pattern)

    assert [row["comment_id"] for row in rows] == ["1"]
    assert fake.regex.validations == [(pattern, True, REGEX_TIMEOUT_DEFAULT)]
    assert len(fake.regex.batches) == 1
    batch_pattern, bodies, ignore_case, timeout_s = fake.regex.batches[0]
    assert batch_pattern == pattern
    assert bodies == ["Line One\nLINE TWO", "other"]
    assert ignore_case is True
    assert timeout_s == REGEX_TIMEOUT_DEFAULT


def test_grep_no_match_returns_an_empty_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = fake_with(
        [issue("DEMO-21", comments=[comment(1, body="nothing here")])]
    )

    rows = run(fake, monkeypatch, grep="needle")

    assert rows == []
    assert len(fake.regex.batches) == 1
    assert fake.regex.batches[0][1] == ["nothing here"]


def test_invalid_grep_is_rejected_before_any_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = fake_with([])

    with pytest.raises(AtlaWireError, match="invalid"):
        run(fake, monkeypatch, grep="(")

    assert fake.regex.validations == [("(", True, REGEX_TIMEOUT_DEFAULT)]
    assert fake.user_queries == []
    assert fake.current_calls == []
    assert fake.http == []


def test_invalid_grep_is_rejected_before_the_current_user_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = fake_with([])

    with pytest.raises(AtlaWireError, match="invalid"):
        run(
            fake,
            monkeypatch,
            user=None,
            current_user={"name": LOGIN},
            grep="(",
        )

    assert fake.current_calls == []
    assert fake.user_queries == []
    assert fake.http == []


def test_grep_validation_timeout_is_rejected_before_any_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = fake_with([])
    fake.regex.validation_error = RegexTimeout()

    with pytest.raises(AtlaWireError, match="validation timed out"):
        run(fake, monkeypatch, grep="match")

    assert fake.user_queries == []
    assert fake.current_calls == []
    assert fake.http == []


def test_grep_only_batches_bodies_from_the_exact_author(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = fake_with(
        [
            issue(
                "DEMO-22",
                comments=[
                    comment(1, author=OTHER, body="match"),
                    comment(2, body="nope"),
                ],
            )
        ]
    )

    rows = run(fake, monkeypatch, grep="match")

    assert rows == []
    assert len(fake.regex.batches) == 1
    assert fake.regex.batches[0][1] == ["nope"]


def test_grep_filters_before_top_k_and_keeps_the_newest_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = fake_with(
        [
            issue(
                "DEMO-23",
                comments=[
                    comment(
                        1,
                        created="2026-11-01T10:00:00.000+0300",
                        body="match old",
                    ),
                    comment(
                        2,
                        created="2026-11-02T10:00:00.000+0300",
                        body="MATCH new",
                    ),
                ],
            )
        ]
    )

    rows = run(fake, monkeypatch, limit=1, grep="match")

    assert [row["comment_id"] for row in rows] == ["2"]
    assert fake.regex.batches[0][1] == ["match old", "MATCH new"]


def test_grep_drops_a_newer_nonmatching_comment_before_top_k(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = fake_with(
        [
            issue(
                "DEMO-32",
                comments=[
                    comment(
                        1,
                        created="2026-11-01T10:00:00.000+0300",
                        body="match old",
                    ),
                    comment(
                        2,
                        created="2026-11-02T10:00:00.000+0300",
                        body="unrelated newer text",
                    ),
                ],
            )
        ]
    )

    rows = run(fake, monkeypatch, limit=1, grep="match")

    assert [row["comment_id"] for row in rows] == ["1"]
    assert fake.regex.batches[0][1] == ["match old", "unrelated newer text"]


def test_grep_equal_instants_keep_first_seen_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = "2026-11-01T10:00:00.000+0300"
    fake = fake_with(
        [
            issue(
                "DEMO-24",
                comments=[
                    comment(1, created=created, body="match one"),
                    comment(2, created=created, body="match two"),
                    comment(3, created=created, body="match three"),
                ],
            )
        ]
    )

    rows = run(fake, monkeypatch, limit=2, grep="match")

    assert [row["comment_id"] for row in rows] == ["1", "2"]


def test_grep_matches_on_a_later_thread_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = fake_with(
        [issue("DEMO-25", comments=[comment(9, author=OTHER)], total=4)],
        threads={
            "DEMO-25": {
                0: thread_page(
                    [
                        comment(10, author=OTHER, body="context"),
                        comment(11, body="first page no"),
                    ],
                    start=0,
                    total=4,
                ),
                2: thread_page(
                    [
                        comment(12, author=OTHER, body="context"),
                        comment(13, body="later MATCH"),
                    ],
                    start=2,
                    total=4,
                ),
            }
        },
    )

    rows = run(fake, monkeypatch, grep="match")

    assert [row["comment_id"] for row in rows] == ["13"]
    assert [batch[1] for batch in fake.regex.batches] == [
        ["first page no"],
        ["later MATCH"],
    ]


def test_grep_later_thread_page_failure_yields_no_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = fake_with(
        [issue("DEMO-26", comments=[comment(9, author=OTHER)], total=3)],
        threads={
            "DEMO-26": {
                0: thread_page(
                    [
                        comment(10, author=OTHER, body="context"),
                        comment(11, body="MATCH"),
                    ],
                    start=0,
                    total=3,
                ),
                2: AtlaWireError("HTTP 503: request failed."),
            }
        },
    )

    with pytest.raises(AtlaWireError, match="HTTP 503"):
        run(fake, monkeypatch, grep="match")

    starts = [
        params["startAt"]
        for url, params in fake.http
        if url.endswith("/comment")
    ]
    assert starts == [0, 2]
    assert len(fake.regex.batches) == 1
    assert fake.regex.batches[0][1] == ["MATCH"]


def test_grep_helper_timeout_on_a_later_page_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = fake_with(
        [issue("DEMO-27", comments=[comment(9, author=OTHER)], total=2)],
        threads={
            "DEMO-27": {
                0: thread_page(
                    [comment(10, body="MATCH first")], start=0, total=2
                ),
                1: thread_page(
                    [comment(11, body="MATCH second")], start=1, total=2
                ),
            }
        },
    )
    fake.regex.match_errors[1] = RegexTimeout()

    with pytest.raises(AtlaWireError, match="timed out"):
        run(fake, monkeypatch, grep="MATCH")

    assert len(fake.regex.batches) == 2


def test_grep_helper_failure_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = fake_with(
        [issue("DEMO-28", comments=[comment(1, body="MATCH")])]
    )
    fake.regex.match_errors[0] = HelperFailure()

    with pytest.raises(AtlaWireError, match="failed"):
        run(fake, monkeypatch, grep="MATCH")

    assert fake.regex.batches[0][1] == ["MATCH"]


def test_grep_treats_a_missing_body_as_empty_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = fake_with(
        [issue("DEMO-29", comments=[comment(1, body=None)])]
    )

    rows = run(fake, monkeypatch, grep="^$")

    assert [row["comment_id"] for row in rows] == ["1"]
    assert fake.regex.batches[0][1] == [""]
    assert rows[0]["body"] == ""


def test_grep_none_or_empty_makes_no_helper_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_none = fake_with(
        [issue("DEMO-30", comments=[comment(1, body="text")])]
    )

    rows_none = run(fake_none, monkeypatch, grep=None)

    assert [row["comment_id"] for row in rows_none] == ["1"]
    assert fake_none.regex.validations == []
    assert fake_none.regex.batches == []

    fake_empty = fake_with(
        [issue("DEMO-31", comments=[comment(1, body="text")])]
    )

    rows_empty = run(fake_empty, monkeypatch, grep="")

    assert [row["comment_id"] for row in rows_empty] == ["1"]
    assert fake_empty.regex.validations == []
    assert fake_empty.regex.batches == []
