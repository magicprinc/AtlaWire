from collections.abc import Callable
from contextlib import nullcontext
from typing import cast

import pytest

from atlawire import bitbucket
from atlawire.http import AtlaWireError

BASE = "https://bitbucket.example.invalid/scm"
DASHBOARD_URL = f"{BASE}/rest/api/1.0/dashboard/pull-requests"
REPO = {"repository": {"slug": "widgets", "project": {"key": "DEMO"}}}
FULL = {
    "id": 101,
    "title": "Fix\tü",
    "state": "OPEN",
    "createdDate": 0,
    "author": {
        "user": {"name": "tom", "emailAddress": "tom@example.invalid"},
        "role": "AUTHOR",
    },
    "fromRef": {
        "displayId": "feature/from-fork",
        "repository": {"slug": "widgets-fork", "project": {"key": "FORK"}},
    },
    "toRef": {
        "displayId": "main",
        "repository": {
            "slug": "widgets",
            "project": {"key": "DEMO"},
            "links": {"self": [{"href": "https://secret.invalid/repo"}]},
        },
    },
    "reviewers": [
        {"user": {"name": "jcitizen", "active": True, "emailAddress": "j@x.invalid"}},
        {"user": {"name": "dick", "active": False, "emailAddress": "d@x.invalid"}},
        {"user": {"name": "absent"}},
        {"user": {"name": "harry", "active": True}},
    ],
    "participants": [
        {"user": {"name": "dick", "active": False}},
        {"user": {"name": "zoe", "active": False}},
        {"user": None},
        {},
    ],
    "description": "RAW-DESCRIPTION-SENTINEL",
    "links": {"self": [{"href": "https://secret.invalid/pr"}]},
}
MINIMAL = {"id": 7, "title": "Second", "state": "MERGED", "toRef": REPO}
THIRD = {
    "id": 8,
    "title": "Third",
    "state": "DECLINED",
    "createdDate": 1359085920,
    "toRef": REPO,
}


def row(**overrides: object) -> dict[str, object]:
    """Build a minimally valid dashboard row for projection failure cases."""
    value: dict[str, object] = {
        "id": 1,
        "title": "T",
        "state": "OPEN",
        "toRef": REPO,
    }
    value.update(overrides)
    return value


def call_pages[RowT](
    monkeypatch: pytest.MonkeyPatch,
    pages: list[dict[str, object]],
    read: Callable[[], list[RowT]],
) -> tuple[list[RowT], list[dict[str, object]]]:
    seen: list[dict[str, object]] = []

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


def test_my_pull_requests_repeat_the_exact_filters_and_follow_the_server_cursor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = [
        {"values": [FULL], "isLastPage": False, "nextPageStart": 7},
        {
            "values": [MINIMAL, THIRD],
            "isLastPage": False,
            "nextPageStart": "unused-and-unusable",
        },
    ]

    rows, seen = call_pages(
        monkeypatch,
        pages,
        lambda: bitbucket.list_my_pull_requests(
            BASE,
            token="fixture-only",
            state="MERGED",
            role="REVIEWER",
            participant_status="APPROVED,NEEDS_WORK,UNAPPROVED",
            limit=3,
        ),
    )

    assert rows == [
        {
            "repo": "DEMO/widgets",
            "id": 101,
            "title": "Fix\tü",
            "state": "OPEN",
            "author": "tom",
            "reviewers_inactive": ["dick", "zoe"],
            "created": 0,
        },
        {
            "repo": "DEMO/widgets",
            "id": 7,
            "title": "Second",
            "state": "MERGED",
            "author": None,
            "reviewers_inactive": [],
            "created": None,
        },
        {
            "repo": "DEMO/widgets",
            "id": 8,
            "title": "Third",
            "state": "DECLINED",
            "author": None,
            "reviewers_inactive": [],
            "created": 1359085920,
        },
    ]
    assert seen == [
        {
            "url": DASHBOARD_URL,
            "start": 0,
            "limit": 3,
            "state": "MERGED",
            "role": "REVIEWER",
            "participantStatus": "APPROVED,NEEDS_WORK,UNAPPROVED",
        },
        {
            "url": DASHBOARD_URL,
            "start": 7,
            "limit": 2,
            "state": "MERGED",
            "role": "REVIEWER",
            "participantStatus": "APPROVED,NEEDS_WORK,UNAPPROVED",
        },
    ]


def test_my_pull_requests_omit_absent_participant_status_and_default_filters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows, seen = call_pages(
        monkeypatch,
        [{"values": [], "isLastPage": True}],
        lambda: bitbucket.list_my_pull_requests(BASE, token="fixture-only"),
    )

    assert rows == []
    assert seen == [
        {
            "url": DASHBOARD_URL,
            "start": 0,
            "limit": 25,
            "state": "OPEN",
            "role": "AUTHOR",
        }
    ]


def test_my_pull_request_projection_uses_the_target_repository_and_known_names() -> (
    None
):
    projected = bitbucket._my_pull_request(FULL)

    assert projected == {
        "repo": "DEMO/widgets",
        "id": 101,
        "title": "Fix\tü",
        "state": "OPEN",
        "author": "tom",
        "reviewers_inactive": ["dick", "zoe"],
        "created": 0,
    }
    rendered = repr(projected)
    for excluded in (
        "FORK",
        "widgets-fork",
        "example.invalid",
        "j@x.invalid",
        "d@x.invalid",
        "RAW-DESCRIPTION-SENTINEL",
        "secret.invalid",
        "AUTHOR",
    ):
        assert excluded not in rendered


def test_a_missing_active_flag_does_not_mark_a_named_user_inactive() -> None:
    projected = bitbucket._my_pull_request(
        row(
            reviewers=[
                {"user": {"name": "absent"}},
                {"user": {"name": "null-active", "active": None}},
                {"user": {"name": "false-active", "active": False}},
            ]
        )
    )

    assert projected["reviewers_inactive"] == ["false-active"]


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(5, id="not-an-object"),
        pytest.param(row(id=0), id="zero-id"),
        pytest.param(row(id=True), id="boolean-id"),
        pytest.param(row(title=""), id="empty-title"),
        pytest.param(row(title=5), id="non-string-title"),
        pytest.param(row(state=""), id="empty-state"),
        pytest.param(row(state=5), id="non-string-state"),
        pytest.param(row(createdDate=-1), id="negative-created"),
        pytest.param(row(createdDate=True), id="boolean-created"),
        pytest.param(row(createdDate=1.5), id="fractional-created"),
        pytest.param(row(author=5), id="non-object-author"),
        pytest.param(row(author={"user": 5}), id="non-object-user"),
        pytest.param(row(author={"user": {"name": 5}}), id="non-string-author-name"),
        pytest.param(row(toRef=5), id="non-object-target"),
        pytest.param(row(toRef={}), id="target-without-repository"),
        pytest.param(row(toRef={"repository": 5}), id="non-object-repository"),
        pytest.param(
            row(toRef={"repository": {"slug": "widgets"}}),
            id="repository-without-project",
        ),
        pytest.param(
            row(toRef={"repository": {"project": {"key": "DEMO"}}}),
            id="repository-without-slug",
        ),
        pytest.param(
            row(toRef={"repository": {"project": {"key": "BAD KEY"}, "slug": "w"}}),
            id="unsafe-project-key",
        ),
        pytest.param(
            row(toRef={"repository": {"project": {"key": "DEMO"}, "slug": ".."}}),
            id="unsafe-slug",
        ),
        pytest.param(row(reviewers=5), id="non-list-reviewers"),
        pytest.param(row(reviewers=[5]), id="non-object-reviewer"),
        pytest.param(row(reviewers=[{"user": 5}]), id="non-object-reviewer-user"),
        pytest.param(row(reviewers=[{"user": {"active": 0}}]), id="integer-active"),
        pytest.param(
            row(reviewers=[{"user": {"active": "false"}}]), id="string-active"
        ),
        pytest.param(
            row(reviewers=[{"user": {"name": 5}}]), id="non-string-reviewer-name"
        ),
        pytest.param(row(participants=5), id="non-list-participants"),
        pytest.param(row(participants=[None]), id="non-object-participant"),
    ],
)
def test_malformed_dashboard_rows_are_rejected(value: object) -> None:
    with pytest.raises(AtlaWireError, match="pull request"):
        bitbucket._my_pull_request(value)


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(row(title="\ud800"), id="title"),
        pytest.param(row(state="\ud800"), id="state"),
        pytest.param(row(author={"user": {"name": "\ud800"}}), id="author"),
        pytest.param(
            row(reviewers=[{"user": {"name": "\ud800", "active": False}}]),
            id="inactive-name",
        ),
    ],
)
def test_dashboard_text_that_utf8_cannot_encode_is_rejected(value: object) -> None:
    with pytest.raises(AtlaWireError, match="UTF-8"):
        bitbucket._my_pull_request(value)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"state": "ALL"}, "state"),
        ({"state": "open"}, "state"),
        ({"state": ""}, "state"),
        ({"role": "all"}, "role"),
        ({"role": "author"}, "role"),
        ({"role": ""}, "role"),
        ({"participant_status": ""}, "participant status"),
        ({"participant_status": "approved"}, "participant status"),
        ({"participant_status": "APPROVED,"}, "participant status"),
        ({"participant_status": "APPROVED,APPROVED"}, "participant status"),
        (
            {"participant_status": "APPROVED,NEEDS_WORK,UNAPPROVED,APPROVED"},
            "participant status",
        ),
        ({"participant_status": "APPROVED, NEEDS_WORK"}, "participant status"),
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
        bitbucket.list_my_pull_requests(
            BASE,
            token="fixture-only",
            state=cast(str, overrides.get("state", "OPEN")),
            role=cast(str, overrides.get("role", "AUTHOR")),
            participant_status=cast(str | None, overrides.get("participant_status")),
            limit=cast(int, overrides.get("limit", 25)),
            max_pages=cast(int, overrides.get("max_pages", 100)),
        )
