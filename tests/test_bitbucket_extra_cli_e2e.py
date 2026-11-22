"""Installed-CLI loopback tests for the extra read-only Bitbucket endpoints."""

import json
import subprocess
from collections.abc import Sequence
from http.server import BaseHTTPRequestHandler

import pytest

from tests._loopback import (
    Request,
    request_record,
    run_installed,
    send_json,
    serving,
)

TOKEN = "fixture-extra-bitbucket"
JIRA_TOKEN = "wrong-product-jira-extra"
CONFLUENCE_TOKEN = "wrong-product-confluence-extra"
SENTINEL = "EXTRA-API-SENTINEL"
CONTEXT = "/scm/bitbucket"
REPO = "DEMO/widgets"
AT = "feature/ü &?+#"
PATH = "src/é +&?.py"
PATH_ENCODED = "src/%C3%A9%20%2B%26%3F.py"
TAG_NAME = "release/ü +&?"
TAG_ENCODED = "release/%C3%BC%20%2B%26%3F"
TAG_FILTER = "rel/é +&?"
TAGS_PATH = f"{CONTEXT}/rest/api/1.0/projects/DEMO/repos/widgets/tags"
LAST_MODIFIED_PATH = (
    f"{CONTEXT}/rest/api/1.0/projects/DEMO/repos/widgets/last-modified"
)

TAG_ONE: dict[str, object] = {
    "id": "release-2.0.0",
    "displayId": "refs/tags/release-2.0.0",
    "type": "TAG",
    "latestCommit": "8d351a10fb428c0c1239530256e21cf24f136e73",
    "latestChangeset": "8d351a10fb428c0c1239530256e21cf24f136e73",
    "hash": "8d51122def5632836d1cb1026e879069e10a1e13",
    "links": {"self": [{"href": "https://evil.invalid/never-followed"}]},
    "extension": {"nested": [None, True, "α"], "count": 0},
}

TAG_TWO: dict[str, object] = {
    "id": "release/ü +&?",
    "displayId": "refs/tags/release/ü +&?",
    "type": "TAG",
    "latestCommit": None,
    "latestChangeset": None,
    "hash": "",
}

LAST_MODIFIED: dict[str, object] = {
    "files": {
        "pom.xml": {
            "id": "def0123abcdef4567abcdef8987abcdef6543abc",
            "displayId": "def0123abcd",
            "author": {
                "name": "charlie",
                "emailAddress": "charlie@example.invalid",
            },
            "authorTimestamp": 1527228363490,
            "message": "More work on feature 1",
            "unknown": {"nested": [None, 0, "α"]},
        }
    },
    "latestCommit": {
        "id": "def0123abcdef4567abcdef8987abcdef6543abc",
        "displayId": "def0123abcd",
        "parents": [{"id": "abcdef0123abcdef4567abcdef8987abcdef6543"}],
    },
    "extension": {"future": True},
}


def page(
    values: list[object],
    *,
    start: int = 0,
    limit: int = 100,
    is_last: bool = True,
    next_start: int | None = None,
) -> dict[str, object]:
    body: dict[str, object] = {
        "values": values,
        "size": len(values),
        "limit": limit,
        "start": start,
        "isLastPage": is_last,
    }
    if next_start is not None:
        body["nextPageStart"] = next_start
    return body


def environment(origin: str) -> dict[str, str]:
    """Point both products at the loopback server and keep Confluence inert."""
    return {
        "ATLAWIRE_BITBUCKET_URL": f"{origin}{CONTEXT}/",
        "ATLAWIRE_BITBUCKET_TOKEN": TOKEN,
        "ATLAWIRE_JIRA_URL": f"{origin}/wrong-jira/",
        "ATLAWIRE_JIRA_TOKEN": JIRA_TOKEN,
        "ATLAWIRE_CONFLUENCE_URL": f"{origin}/wrong-confluence/",
        "ATLAWIRE_CONFLUENCE_TOKEN": CONFLUENCE_TOKEN,
        "BBK_CREDENTIALS": (
            "C:/TMP/opencode/nonexistent-bbk-credentials-extra.json"
        ),
    }


def run_extra(
    command: str,
    *arguments: str,
    repo: str = REPO,
    responses: Sequence[tuple[int, object]],
) -> tuple[subprocess.CompletedProcess[str], list[Request], list[str]]:
    seen: list[Request] = []
    extra_methods: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            seen.append(request_record(self))
            index = len(seen) - 1
            if index >= len(responses):
                status, body = (
                    500,
                    {"errors": [{"message": "UNEXPECTED-EXTRA-REQUEST"}]},
                )
            else:
                status, body = responses[index]
            if 300 <= status < 400:
                self.send_response(status)
                self.send_header("Location", "https://evil.invalid/next")
                self.send_header("Content-Length", "0")
                self.end_headers()
            else:
                send_json(self, status, body)

        def _refuse_write(self, method: str) -> None:
            extra_methods.append(method)
            send_json(self, 405, {"errors": [{"message": "write refused"}]})

        def do_POST(self) -> None:
            self._refuse_write("POST")

        def do_PUT(self) -> None:
            self._refuse_write("PUT")

        def do_DELETE(self) -> None:
            self._refuse_write("DELETE")

        def do_PATCH(self) -> None:
            self._refuse_write("PATCH")

        def do_HEAD(self) -> None:
            extra_methods.append("HEAD")
            self.send_error(405)

        def do_OPTIONS(self) -> None:
            extra_methods.append("OPTIONS")
            self.send_error(405)

    with serving(Handler) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        result = run_installed(
            [
                command,
                repo,
                *arguments,
                "--base-url",
                f"{origin}{CONTEXT}/",
                "--allow-http-loopback",
                "--token-from-env",
            ],
            environment(origin),
        )
    return result, seen, extra_methods


def tags_request(
    start: int,
    limit: int,
    *,
    filter_text: str | None = None,
    order_by: str | None = None,
) -> Request:
    query = {"start": [str(start)], "limit": [str(limit)]}
    if filter_text is not None:
        query["filterText"] = [filter_text]
    if order_by is not None:
        query["orderBy"] = [order_by]
    return ("GET", TAGS_PATH, query, f"Bearer {TOKEN}")


def tag_request() -> Request:
    return (
        "GET",
        f"{TAGS_PATH}/{TAG_ENCODED}",
        {},
        f"Bearer {TOKEN}",
    )


def last_modified_request(
    path: str | None = None, at: str | None = AT
) -> Request:
    query = {} if at is None else {"at": [at]}
    target = LAST_MODIFIED_PATH if path is None else f"{LAST_MODIFIED_PATH}/{path}"
    return ("GET", target, query, f"Bearer {TOKEN}")


def test_tags_json_follows_a_cursor_gap_and_keeps_raw_rows() -> None:
    result, seen, extra = run_extra(
        "tags",
        "--limit",
        "2",
        "--json",
        responses=[
            (
                200,
                page(
                    [TAG_ONE],
                    start=0,
                    limit=2,
                    is_last=False,
                    next_start=57,
                ),
            ),
            (200, page([TAG_TWO], start=57, limit=1)),
        ],
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == [TAG_ONE, TAG_TWO]
    assert seen == [tags_request(0, 2), tags_request(57, 1)]
    assert extra == []


def test_tags_repeats_filters_on_every_paginated_request() -> None:
    result, seen, extra = run_extra(
        "tags",
        "--filter",
        TAG_FILTER,
        "--order",
        "MODIFICATION",
        "--limit",
        "3",
        "--json",
        responses=[
            (
                200,
                page(
                    [TAG_ONE],
                    start=0,
                    limit=3,
                    is_last=False,
                    next_start=57,
                ),
            ),
            (200, page([TAG_TWO], start=57, limit=2)),
        ],
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == [TAG_ONE, TAG_TWO]
    assert seen == [
        tags_request(
            0,
            3,
            filter_text=TAG_FILTER,
            order_by="MODIFICATION",
        ),
        tags_request(
            57,
            2,
            filter_text=TAG_FILTER,
            order_by="MODIFICATION",
        ),
    ]
    assert extra == []


@pytest.mark.parametrize(
    "order",
    ["alphabetical", "", "MODIFICATION ", "NEWEST"],
    ids=["lowercase", "empty", "trailing-space", "wrong-order"],
)
def test_tags_invalid_order_fails_before_any_request(order: str) -> None:
    result, seen, extra = run_extra(
        "tags", "--order", order, "--json", responses=[]
    )

    assert result.returncode != 0
    assert result.stdout == ""
    assert result.stderr != ""
    assert seen == []
    assert extra == []


def test_tags_exact_limit_stops_before_an_unused_next_page() -> None:
    result, seen, extra = run_extra(
        "tags",
        "--limit",
        "2",
        "--json",
        responses=[
            (
                200,
                page(
                    [TAG_ONE, TAG_TWO],
                    limit=2,
                    is_last=False,
                    next_start=99,
                ),
            )
        ],
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == [TAG_ONE, TAG_TWO]
    assert seen == [tags_request(0, 2)]
    assert extra == []


def test_tags_rejects_a_non_object_row_without_partial_stdout() -> None:
    result, seen, extra = run_extra(
        "tags",
        "--limit",
        "2",
        "--json",
        responses=[(200, page([TAG_ONE, "not-an-object"], limit=2))],
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "tag object" in result.stderr
    assert seen == [tags_request(0, 2)]
    assert extra == []


def test_tags_later_page_http_failure_is_sanitized_without_partial_stdout() -> None:
    failure = (
        503,
        {"errors": [{"message": SENTINEL}], "token": TOKEN, "x": SENTINEL},
    )

    result, seen, extra = run_extra(
        "tags",
        "--limit",
        "2",
        "--json",
        responses=[
            (
                200,
                page(
                    [TAG_ONE],
                    start=0,
                    limit=2,
                    is_last=False,
                    next_start=7,
                ),
            ),
            failure,
        ],
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "HTTP 503" in result.stderr
    for detail in (TOKEN, JIRA_TOKEN, CONFLUENCE_TOKEN, SENTINEL):
        assert detail not in result.stderr
    assert seen == [tags_request(0, 2), tags_request(7, 1)]
    assert extra == []


def test_tags_later_page_without_a_cursor_fails_without_partial_stdout() -> None:
    result, seen, extra = run_extra(
        "tags",
        "--limit",
        "2",
        "--json",
        responses=[
            (
                200,
                page(
                    [TAG_ONE],
                    start=0,
                    limit=2,
                    is_last=False,
                    next_start=7,
                ),
            ),
            (
                200,
                {
                    "values": [TAG_TWO],
                    "size": 1,
                    "limit": 1,
                    "start": 7,
                    "isLastPage": False,
                },
            ),
        ],
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "nextPageStart" in result.stderr
    assert seen == [tags_request(0, 2), tags_request(7, 1)]
    assert extra == []


def test_tag_returns_the_raw_object_from_one_encoded_get() -> None:
    result, seen, extra = run_extra(
        "tag", TAG_NAME, responses=[(200, TAG_TWO)]
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == TAG_TWO
    assert seen == [tag_request()]
    assert extra == []


@pytest.mark.parametrize(
    "name",
    [
        "../secret",
        "release/../../secret",
        "/release",
        "release/",
        "release//x",
        "release/./x",
        "a\\b",
        "a%2Fb",
    ],
    ids=[
        "parent",
        "nested-parent",
        "leading-slash",
        "trailing-slash",
        "double-slash",
        "current",
        "backslash",
        "percent-escape",
    ],
)
def test_tag_rejects_traversal_without_any_request(name: str) -> None:
    result, seen, extra = run_extra("tag", name, responses=[])

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr != ""
    assert seen == []
    assert extra == []


def test_last_modified_root_omits_the_path_and_at_query() -> None:
    result, seen, extra = run_extra(
        "last-modified", responses=[(200, LAST_MODIFIED)]
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == LAST_MODIFIED
    assert seen == [last_modified_request(at=None)]
    assert extra == []


def test_last_modified_encodes_the_path_and_sends_at_once() -> None:
    result, seen, extra = run_extra(
        "last-modified",
        PATH,
        "--at",
        AT,
        responses=[(200, LAST_MODIFIED)],
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == LAST_MODIFIED
    assert seen == [last_modified_request(PATH_ENCODED)]
    assert extra == []


@pytest.mark.parametrize(
    "path",
    ["../secret", "src/../../secret", "/src", "src/", "src//x", "src/%2e%2e/x"],
    ids=[
        "parent",
        "nested-parent",
        "leading-slash",
        "trailing-slash",
        "double-slash",
        "percent-escape",
    ],
)
def test_last_modified_rejects_traversal_without_any_request(path: str) -> None:
    result, seen, extra = run_extra(
        "last-modified", path, responses=[]
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr != ""
    assert seen == []
    assert extra == []


@pytest.mark.parametrize(
    "at",
    ["feature\nmain", "feature\r\nmain", "a\x00b"],
    ids=["lf", "crlf", "nul"],
)
def test_last_modified_rejects_an_invalid_ref_without_any_request(at: str) -> None:
    result, seen, extra = run_extra(
        "last-modified", "--at", at, responses=[]
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr != ""
    assert seen == []
    assert extra == []


@pytest.mark.parametrize(
    ("command", "arguments"),
    [
        ("tags", ("--json",)),
        ("tag", ("v1.0.0",)),
        ("last-modified", ()),
    ],
    ids=["tags", "tag", "last-modified"],
)
def test_invalid_repo_fails_before_any_request(
    command: str, arguments: tuple[str, ...]
) -> None:
    result, seen, extra = run_extra(
        command, *arguments, repo="DEMO", responses=[]
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr != ""
    assert seen == []
    assert extra == []


@pytest.mark.parametrize(
    ("status", "detail"),
    [
        (401, "HTTP 401"),
        (403, "HTTP 403"),
        (404, "HTTP 404"),
        (302, "redirect refused"),
    ],
    ids=["401", "403", "404", "redirect"],
)
@pytest.mark.parametrize(
    ("command", "arguments", "expected"),
    [
        (
            "tags",
            ("--limit", "25", "--json"),
            tags_request(0, 25),
        ),
        ("tag", (TAG_NAME,), tag_request()),
        (
            "last-modified",
            ("--at", AT),
            last_modified_request(at=AT),
        ),
    ],
    ids=["tags", "tag", "last-modified"],
)
def test_read_errors_are_sanitized_and_never_use_a_write_method(
    status: int,
    detail: str,
    command: str,
    arguments: tuple[str, ...],
    expected: Request,
) -> None:
    failure = (
        status,
        {
            "errors": [{"message": SENTINEL}],
            "token": TOKEN,
            "x": SENTINEL,
        },
    )

    result, seen, extra = run_extra(
        command, *arguments, responses=[failure]
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert detail in result.stderr
    for secret in (TOKEN, JIRA_TOKEN, CONFLUENCE_TOKEN, SENTINEL):
        assert secret not in result.stderr
    assert seen == [expected]
    assert extra == []


@pytest.mark.parametrize(
    "arguments",
    [
        ("--limit", "0", "--json"),
        ("--limit", "1001", "--json"),
        ("--max-pages", "0", "--json"),
        ("--max-pages", "1001", "--json"),
    ],
    ids=["limit-zero", "limit-over", "pages-zero", "pages-over"],
)
def test_tags_out_of_range_options_are_usage_errors(
    arguments: tuple[str, ...],
) -> None:
    result, seen, extra = run_extra("tags", *arguments, responses=[])

    assert result.returncode == 2
    assert result.stdout == ""
    assert seen == []
    assert extra == []
