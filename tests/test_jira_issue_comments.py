"""Installed-CLI and paging checks for the Jira issue comment projection."""

import json
import subprocess
from collections.abc import Sequence
from contextlib import nullcontext
from http.server import BaseHTTPRequestHandler

import pytest

from atlawire import jira
from atlawire.http import AtlaWireError
from tests._loopback import (
    Request,
    request_record,
    run_installed,
    send_json,
    serving,
)

TOKEN = "fixture-jira-comments-token"
CONTEXT = "/jira"
KEY = "DEMO-42"
COMMENTS_PATH = f"{CONTEXT}/rest/api/2/issue/{KEY}/comment"
PASTED_URL = f"https://pasted.example.invalid/jira/browse/{KEY}?tab=comments"
SENTINEL = "JIRA-COMMENTS-SENTINEL"
BASE = "https://jira.example.invalid/jira"

FIRST_COMMENT: dict[str, object] = {
    "id": "10002",
    "author": {
        "name": "ada",
        "displayName": SENTINEL,
        "emailAddress": SENTINEL,
    },
    "created": "2024-01-02T03:04:05.000+0000",
    "updated": "2024-01-02T03:04:06.000+0000",
    "body": "  first\nbody  ",
    "visibility": {"type": "group", "value": SENTINEL},
    "extra": SENTINEL,
}
SECOND_COMMENT: dict[str, object] = {
    "id": "10001",
    "author": None,
    "created": None,
    "updated": None,
    "body": "\tsecond\r\nbody\n",
}
THIRD_COMMENT: dict[str, object] = {
    "id": "10003",
    "author": {"name": "", "displayName": SENTINEL},
    "created": "",
    "body": "",
    "extra": SENTINEL,
}

HAPPY_PAGES: list[dict[str, object]] = [
    {"startAt": 0, "maxResults": 1, "total": 3, "comments": [FIRST_COMMENT]},
    {
        "startAt": 1,
        "maxResults": 2,
        "total": 3,
        "comments": [SECOND_COMMENT, THIRD_COMMENT],
    },
]
EXPECTED: list[dict[str, object]] = [
    {
        "id": "10002",
        "author": "ada",
        "created": "2024-01-02T03:04:05.000+0000",
        "updated": "2024-01-02T03:04:06.000+0000",
        "body": "  first\nbody  ",
    },
    {
        "id": "10001",
        "author": None,
        "created": None,
        "updated": None,
        "body": "\tsecond\r\nbody\n",
    },
    {
        "id": "10003",
        "author": "",
        "created": "",
        "updated": None,
        "body": "",
    },
]
TWO_PAGE_FIRST: dict[str, object] = {
    "startAt": 0,
    "maxResults": 1,
    "total": 2,
    "comments": [FIRST_COMMENT],
}


def environment(origin: str) -> dict[str, str]:
    """Configure Jira for the loopback context and keep other products inert."""
    return {
        "ATLAWIRE_JIRA_URL": f"{origin}{CONTEXT}/",
        "ATLAWIRE_JIRA_TOKEN": TOKEN,
        "ATLAWIRE_BITBUCKET_URL": f"{origin}/wrong-bitbucket/",
        "ATLAWIRE_BITBUCKET_TOKEN": "wrong-product-fixture",
        "ATLAWIRE_CONFLUENCE_URL": f"{origin}/wrong-confluence/",
        "ATLAWIRE_CONFLUENCE_TOKEN": "wrong-product-fixture",
    }


def expected_requests() -> list[Request]:
    return [
        (
            "GET",
            COMMENTS_PATH,
            {"startAt": ["0"], "maxResults": ["50"]},
            f"Bearer {TOKEN}",
        ),
        (
            "GET",
            COMMENTS_PATH,
            {"startAt": ["1"], "maxResults": ["50"]},
            f"Bearer {TOKEN}",
        ),
    ]


def run_comments(
    pages: Sequence[dict[str, object] | int],
    *,
    argument: str = PASTED_URL,
    extra_args: tuple[str, ...] = (),
) -> tuple[subprocess.CompletedProcess[str], list[Request], list[str | None]]:
    """Run issue-comments from the environment against a page sequence."""
    seen: list[Request] = []
    accepts: list[str | None] = []
    responses = iter(pages)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            record = request_record(self)
            seen.append(record)
            accepts.append(self.headers.get("Accept"))
            _, path, _, authorization = record
            if path != COMMENTS_PATH or authorization != f"Bearer {TOKEN}":
                send_json(self, 401, {"message": SENTINEL})
                return
            response = next(responses, 503)
            if isinstance(response, int):
                send_json(self, response, {"message": SENTINEL})
            else:
                send_json(self, 200, response)

    with serving(Handler) as server:
        result = run_installed(
            [
                "issue-comments",
                argument,
                "--token-from-env",
                "--allow-http-loopback",
                *extra_args,
            ],
            environment(f"http://127.0.0.1:{server.server_port}"),
        )
    return result, seen, accepts


def test_installed_issue_comments_follows_a_server_cap_and_preserves_text() -> None:
    result, seen, accepts = run_comments(HAPPY_PAGES)

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == EXPECTED
    assert '"author": null' in result.stdout
    assert [list(row) for row in json.loads(result.stdout)] == [
        ["id", "author", "created", "updated", "body"]
    ] * 3
    assert SENTINEL not in result.stdout
    assert TOKEN not in result.stdout
    assert seen == expected_requests()
    assert accepts == ["application/json", "application/json"]


@pytest.mark.parametrize(
    "page",
    [
        {"startAt": 0, "total": 0, "comments": []},
        {"startAt": 0, "maxResults": 0, "total": 0, "comments": []},
    ],
    ids=["omitted-max-results", "zero-max-results"],
)
def test_installed_issue_comments_accepts_an_empty_initial_page(
    page: dict[str, object],
) -> None:
    result, seen, accepts = run_comments([page])

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == []
    assert seen == expected_requests()[:1]
    assert accepts == ["application/json"]


@pytest.mark.parametrize(
    ("pages", "diagnostic"),
    [
        (
            [
                TWO_PAGE_FIRST,
                {
                    "startAt": 1,
                    "maxResults": 1,
                    "total": 2,
                    "comments": [FIRST_COMMENT],
                },
            ],
            "duplicate comment IDs",
        ),
        (
            [
                TWO_PAGE_FIRST,
                {
                    "startAt": 1,
                    "maxResults": 1,
                    "total": 2,
                    "comments": SENTINEL,
                },
            ],
            "comments array",
        ),
        ([TWO_PAGE_FIRST, 503], "HTTP 503"),
    ],
    ids=["duplicate-id", "malformed-page", "http-failure"],
)
def test_installed_issue_comments_publishes_nothing_after_a_failed_later_page(
    pages: list[dict[str, object] | int], diagnostic: str
) -> None:
    result, seen, accepts = run_comments(pages)

    assert result.returncode == 1
    assert result.stdout == ""
    assert diagnostic in result.stderr
    assert SENTINEL not in result.stderr
    assert TOKEN not in result.stderr
    assert "Traceback" not in result.stderr
    assert seen == expected_requests()
    assert accepts == ["application/json", "application/json"]


def page(
    comments: list[dict[str, object]],
    *,
    start: int = 0,
    total: object = 0,
    max_results: object = 50,
    include_max_results: bool = True,
) -> dict[str, object]:
    value: dict[str, object] = {
        "startAt": start,
        "comments": comments,
        "total": total,
    }
    if include_max_results:
        value["maxResults"] = max_results
    return value


def read_comments(
    monkeypatch: pytest.MonkeyPatch,
    pages: list[dict[str, object]],
    *,
    max_pages: int = jira.COMMENT_PAGES_DEFAULT,
) -> tuple[list[jira.CommentRow], list[dict[str, object]]]:
    seen: list[dict[str, object]] = []

    def fake_get_json_object(
        session: object, url: str, *, params: dict[str, str | int]
    ) -> dict[str, object]:
        seen.append({"url": url, **params})
        return pages[len(seen) - 1]

    monkeypatch.setattr(jira, "bearer_session", lambda token: nullcontext(None))
    monkeypatch.setattr(jira, "get_json_object", fake_get_json_object)
    rows = jira.list_issue_comments(
        BASE, KEY, token="fixture-only", max_pages=max_pages
    )
    return rows, seen


@pytest.mark.parametrize("max_pages", [True, False, 0, 1001, 1.5, "3"])
def test_issue_comments_rejects_an_invalid_page_limit_before_any_request(
    monkeypatch: pytest.MonkeyPatch, max_pages: object
) -> None:
    def unexpected_session(token: str) -> object:
        raise AssertionError("No request should be attempted.")

    monkeypatch.setattr(jira, "bearer_session", unexpected_session)

    with pytest.raises(AtlaWireError, match="page limit"):
        jira.list_issue_comments(
            BASE,
            KEY,
            token="fixture-only",
            max_pages=max_pages,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    ("pages", "diagnostic"),
    [
        (
            [
                page([{"id": "1"}], start=0, total=2),
                page([{"id": "2"}], start=1, total=3),
            ],
            "total changed",
        ),
        ([page([], start=0, total=2)], "ended before all comments"),
        (
            [page([{"id": "1"}, {"id": "2"}], total=1, max_results=2)],
            "Inconsistent",
        ),
    ],
    ids=["total-drift", "empty-before-total", "total-below-seen"],
)
def test_issue_comments_rejects_inconsistent_pagination_metadata(
    monkeypatch: pytest.MonkeyPatch,
    pages: list[dict[str, object]],
    diagnostic: str,
) -> None:
    with pytest.raises(AtlaWireError, match=diagnostic):
        read_comments(monkeypatch, pages)


def test_issue_comments_rejects_duplicate_ids_within_one_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = [page([{"id": "7"}, {"id": "7"}], total=2, max_results=2)]

    with pytest.raises(AtlaWireError, match="duplicate comment IDs"):
        read_comments(monkeypatch, pages)


def test_issue_comments_page_cap_discards_rows_already_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pages = [page([{"id": "1"}], total=2, max_results=1)]

    with pytest.raises(AtlaWireError, match="page limit"):
        read_comments(monkeypatch, pages, max_pages=1)


@pytest.mark.parametrize(
    ("entry", "diagnostic"),
    [
        ({"id": 7}, "comment ID"),
        ({"id": "  "}, "comment ID"),
        ({"id": "1", "author": "ada"}, "author object"),
        ({"id": "1", "author": {"name": 7}}, "author name"),
        ({"id": "1", "created": 7}, "created"),
        ({"id": "1", "updated": []}, "updated"),
        ({"id": "1", "body": {}}, "body"),
        ({"id": "1", "body": "\ud800"}, "valid UTF-8"),
    ],
    ids=[
        "wrong-id-type",
        "blank-id",
        "wrong-author-shape",
        "wrong-author-name",
        "wrong-created",
        "wrong-updated",
        "wrong-body",
        "unencodable-body",
    ],
)
def test_issue_comments_rejects_a_malformed_projection(
    monkeypatch: pytest.MonkeyPatch,
    entry: dict[str, object],
    diagnostic: str,
) -> None:
    pages = [page([entry], total=1, max_results=1)]

    with pytest.raises(AtlaWireError, match=diagnostic):
        read_comments(monkeypatch, pages)
