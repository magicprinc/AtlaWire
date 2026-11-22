"""Unit tests for the additional read-only Bitbucket Server 5.10 adapters."""

from contextlib import nullcontext
from typing import Self, cast
from urllib.parse import parse_qs, urlsplit

import pytest
import responses

from atlawire import bitbucket
from atlawire.http import AtlaWireError

BASE = "https://bitbucket.example.invalid/scm"
TOKEN = "fixture-only-token"
REPO = "DEMO/widgets"
TAGS_URL = f"{BASE}/rest/api/1.0/projects/DEMO/repos/widgets/tags"
LAST_MODIFIED_URL = (
    f"{BASE}/rest/api/1.0/projects/DEMO/repos/widgets/last-modified"
)
AT = "feature/ü &?+#"
PATH = "src/é +&?.py"
TAG_NAME = "release/ü +&?"
TAG_FILTER = "rel/é +&?"
TAG_URL = f"{TAGS_URL}/release/%C3%BC%20%2B%26%3F"
PATH_URL = f"{LAST_MODIFIED_URL}/src/%C3%A9%20%2B%26%3F.py"

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
            "author": {"name": "charlie", "emailAddress": "charlie@example.invalid"},
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


def stub_json(
    monkeypatch: pytest.MonkeyPatch,
    bodies: list[dict[str, object]],
) -> list[tuple[str, dict[str, str | int]]]:
    calls: list[tuple[str, dict[str, str | int]]] = []
    remaining = iter(bodies)

    def fake_get_json_object(
        session: object, url: str, *, params: dict[str, str | int]
    ) -> dict[str, object]:
        calls.append((url, dict(params)))
        return next(remaining)

    monkeypatch.setattr(bitbucket, "bearer_session", lambda token: nullcontext(None))
    monkeypatch.setattr(bitbucket, "get_json_object", fake_get_json_object)
    return calls


def forbidden_session(token: str) -> object:
    raise AssertionError("session created before validation")


class TrackingSession:
    """A context manager that records whether the adapter closed it."""

    def __init__(self) -> None:
        self.closed = False

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self.closed = True


def test_list_tags_returns_raw_rows_in_server_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = stub_json(monkeypatch, [page([TAG_ONE, TAG_TWO], limit=25)])

    rows = bitbucket.list_tags(BASE, REPO, token=TOKEN)

    assert rows == [TAG_ONE, TAG_TWO]
    assert rows[0] is TAG_ONE
    assert rows[1] is TAG_TWO
    assert calls == [(TAGS_URL, {"start": 0, "limit": 25})]


def test_list_tags_follows_a_cursor_gap_after_a_short_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = stub_json(
        monkeypatch,
        [
            page([TAG_ONE], start=0, limit=3, is_last=False, next_start=57),
            page([TAG_TWO], start=57, limit=2),
        ],
    )

    rows = bitbucket.list_tags(BASE, REPO, token=TOKEN, limit=3)

    assert rows == [TAG_ONE, TAG_TWO]
    assert calls == [
        (TAGS_URL, {"start": 0, "limit": 3}),
        (TAGS_URL, {"start": 57, "limit": 2}),
    ]


def test_list_tags_stops_at_the_limit_without_reading_the_next_hint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = stub_json(
        monkeypatch,
        [page([TAG_ONE, TAG_TWO], limit=2, is_last=False, next_start=99)],
    )

    rows = bitbucket.list_tags(BASE, REPO, token=TOKEN, limit=2)

    assert rows == [TAG_ONE, TAG_TWO]
    assert calls == [(TAGS_URL, {"start": 0, "limit": 2})]


def test_tag_filters_are_repeated_on_every_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = stub_json(
        monkeypatch,
        [
            page([TAG_ONE], start=0, limit=3, is_last=False, next_start=57),
            page([TAG_TWO], start=57, limit=2),
        ],
    )

    rows = bitbucket.list_tags(
        BASE,
        REPO,
        token=TOKEN,
        filter_text=TAG_FILTER,
        order_by="MODIFICATION",
        limit=3,
    )

    assert rows == [TAG_ONE, TAG_TWO]
    assert calls == [
        (
            TAGS_URL,
            {
                "filterText": TAG_FILTER,
                "orderBy": "MODIFICATION",
                "start": 0,
                "limit": 3,
            },
        ),
        (
            TAGS_URL,
            {
                "filterText": TAG_FILTER,
                "orderBy": "MODIFICATION",
                "start": 57,
                "limit": 2,
            },
        ),
    ]


@pytest.mark.parametrize(
    "order_by",
    ["ALPHABETICAL", "MODIFICATION"],
    ids=["alphabetical", "modification"],
)
def test_each_documented_order_is_sent_exactly(
    monkeypatch: pytest.MonkeyPatch, order_by: str
) -> None:
    calls = stub_json(monkeypatch, [page([TAG_ONE])])

    rows = bitbucket.list_tags(
        BASE, REPO, token=TOKEN, filter_text="", order_by=order_by
    )

    assert rows == [TAG_ONE]
    assert calls == [
        (TAGS_URL, {"orderBy": order_by, "start": 0, "limit": 25})
    ]


@pytest.mark.parametrize(
    "order_by",
    ["", "alphabetical", "ALPHABETICAL ", "MODIFICATION\n", "NEWEST", 7, True, [], {}],
    ids=[
        "empty",
        "lowercase",
        "trailing-space",
        "newline",
        "wrong-order",
        "number",
        "boolean",
        "array",
        "object",
    ],
)
def test_list_tags_rejects_an_invalid_order_before_any_session(
    monkeypatch: pytest.MonkeyPatch, order_by: object
) -> None:
    monkeypatch.setattr(bitbucket, "bearer_session", forbidden_session)

    with pytest.raises(AtlaWireError, match="tag order"):
        bitbucket.list_tags(
            BASE, REPO, token=TOKEN, order_by=cast(str | None, order_by)
        )


@pytest.mark.parametrize(
    "filter_text",
    [7, True, [], {}, "\ud800"],
    ids=["number", "boolean", "array", "object", "lone-surrogate"],
)
def test_list_tags_rejects_an_invalid_filter_before_any_session(
    monkeypatch: pytest.MonkeyPatch, filter_text: object
) -> None:
    monkeypatch.setattr(bitbucket, "bearer_session", forbidden_session)

    with pytest.raises(AtlaWireError, match="tag filter"):
        bitbucket.list_tags(
            BASE, REPO, token=TOKEN, filter_text=cast(str | None, filter_text)
        )


@pytest.mark.parametrize(
    "row",
    ["tag", 7, None, [], True, {"id": "valid-looking"}],
    ids=["string", "number", "null", "array", "boolean", "object"],
)
def test_every_tag_row_must_be_an_object(
    monkeypatch: pytest.MonkeyPatch, row: object
) -> None:
    stub_json(monkeypatch, [page([TAG_ONE, row])])

    if isinstance(row, dict):
        rows = bitbucket.list_tags(BASE, REPO, token=TOKEN)
        assert rows == [TAG_ONE, row]
    else:
        with pytest.raises(AtlaWireError, match="tag object"):
            bitbucket.list_tags(BASE, REPO, token=TOKEN)


@pytest.mark.parametrize(
    ("second", "detail"),
    [
        ({"values": [], "isLastPage": "true"}, "isLastPage"),
        ({"values": [], "isLastPage": False}, "nextPageStart"),
        ({"values": {}, "isLastPage": True}, "values array"),
        (
            {"values": [], "isLastPage": True, "start": 8, "size": 0},
            "page start",
        ),
        (
            {"values": [], "isLastPage": True, "start": 7, "size": 1},
            "page size",
        ),
    ],
    ids=["bad-boolean", "missing-cursor", "bad-values", "bad-start", "bad-size"],
)
def test_a_malformed_later_page_raises_without_returning_rows(
    monkeypatch: pytest.MonkeyPatch, second: dict[str, object], detail: str
) -> None:
    first = page([TAG_ONE], is_last=False, next_start=7)
    calls = stub_json(monkeypatch, [first, second])

    with pytest.raises(AtlaWireError, match=detail):
        bitbucket.list_tags(BASE, REPO, token=TOKEN)

    assert calls == [
        (TAGS_URL, {"start": 0, "limit": 25}),
        (TAGS_URL, {"start": 7, "limit": 24}),
    ]


def test_the_page_cap_raises_after_a_valid_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub_json(
        monkeypatch,
        [page([TAG_ONE], is_last=False, next_start=7)],
    )

    with pytest.raises(AtlaWireError, match="page limit"):
        bitbucket.list_tags(BASE, REPO, token=TOKEN, max_pages=1)


@pytest.mark.parametrize(
    "limit",
    [0, 1001, True, False, "1", 1.0, None],
    ids=["zero", "over-max", "true", "false", "string", "float", "none"],
)
def test_list_tags_rejects_an_invalid_limit_before_any_session(
    monkeypatch: pytest.MonkeyPatch, limit: object
) -> None:
    monkeypatch.setattr(bitbucket, "bearer_session", forbidden_session)

    with pytest.raises(AtlaWireError, match="tag limit"):
        bitbucket.list_tags(BASE, REPO, token=TOKEN, limit=cast(int, limit))


@pytest.mark.parametrize(
    "max_pages",
    [0, 1001, True, False, "100", 1.0, None],
    ids=["zero", "over-max", "true", "false", "string", "float", "none"],
)
def test_list_tags_rejects_an_invalid_page_budget_before_any_session(
    monkeypatch: pytest.MonkeyPatch, max_pages: object
) -> None:
    monkeypatch.setattr(bitbucket, "bearer_session", forbidden_session)

    with pytest.raises(AtlaWireError, match="page limit"):
        bitbucket.list_tags(
            BASE, REPO, token=TOKEN, max_pages=cast(int, max_pages)
        )


@pytest.mark.parametrize(
    "repo",
    ["DEMO", "", "DEMO/", "/widgets", "DEMO/widgets/extra", "DEMO/..", "../widgets"],
)
def test_list_tags_rejects_an_invalid_repo_before_any_session(
    monkeypatch: pytest.MonkeyPatch, repo: str
) -> None:
    monkeypatch.setattr(bitbucket, "bearer_session", forbidden_session)

    with pytest.raises(AtlaWireError, match="PROJECT/slug"):
        bitbucket.list_tags(BASE, repo, token=TOKEN)


@responses.activate
def test_list_tags_real_transport_uses_one_get_and_keeps_server_links() -> None:
    responses.get(TAGS_URL, json=page([TAG_ONE], limit=25))

    rows = bitbucket.list_tags(BASE, REPO, token=TOKEN)

    assert rows == [TAG_ONE]
    assert len(responses.calls) == 1
    request = responses.calls[0].request
    assert request.method == "GET"
    assert request.url.split("?")[0] == TAGS_URL
    assert parse_qs(urlsplit(request.url).query) == {
        "start": ["0"],
        "limit": ["25"],
    }
    assert request.headers["Authorization"] == f"Bearer {TOKEN}"


@responses.activate
@pytest.mark.parametrize(
    ("status", "message"),
    [
        (401, "authentication rejected"),
        (403, "access denied"),
        (404, "HTTP 404"),
        (500, "HTTP 500"),
    ],
    ids=["401", "403", "404", "500"],
)
def test_list_tags_propagates_shared_http_errors(status: int, message: str) -> None:
    responses.get(TAGS_URL, status=status, json={"errors": [{"message": "x"}]})

    with pytest.raises(AtlaWireError, match=message):
        bitbucket.list_tags(BASE, REPO, token=TOKEN)

    assert len(responses.calls) == 1


@responses.activate
def test_list_tags_refuses_a_redirect_without_following_it() -> None:
    responses.get(
        TAGS_URL,
        status=302,
        headers={"Location": "https://evil.invalid/next"},
    )

    with pytest.raises(AtlaWireError, match="redirect refused"):
        bitbucket.list_tags(BASE, REPO, token=TOKEN)

    assert len(responses.calls) == 1
    assert "evil.invalid" not in responses.calls[0].request.url


def test_get_tag_returns_the_raw_object_from_one_get(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = stub_json(monkeypatch, [TAG_TWO])

    value = bitbucket.get_tag(BASE, REPO, TAG_NAME, token=TOKEN)

    assert value is TAG_TWO
    assert calls == [(TAG_URL, {})]


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("simple", f"{TAGS_URL}/simple"),
        (TAG_NAME, TAG_URL),
        ("release/100% done", f"{TAGS_URL}/release/100%25%20done"),
        ("release/a b", f"{TAGS_URL}/release/a%20b"),
        ("release/a?b#c", f"{TAGS_URL}/release/a%3Fb%23c"),
    ],
    ids=["single", "unicode-and-reserved", "percent-literal", "space", "query-chars"],
)
def test_tag_names_keep_slashes_and_encode_each_segment_once(
    monkeypatch: pytest.MonkeyPatch, name: str, expected: str
) -> None:
    calls = stub_json(monkeypatch, [TAG_ONE])

    value = bitbucket.get_tag(BASE, REPO, name, token=TOKEN)

    assert value is TAG_ONE
    assert calls == [(expected, {})]


@pytest.mark.parametrize(
    "name",
    [
        "",
        "/release",
        "release/",
        "release//x",
        "../x",
        "release/../x",
        "release/./x",
        "release/..",
        "a\\b",
        "a\x00b",
        "a\x7fb",
        "a%2Fb",
        "a%2fb",
        7,
        None,
    ],
    ids=[
        "empty",
        "leading-slash",
        "trailing-slash",
        "double-slash",
        "parent",
        "nested-parent",
        "current",
        "parent-last",
        "backslash",
        "nul",
        "delete",
        "percent-escape",
        "lowercase-escape",
        "number",
        "null",
    ],
)
def test_get_tag_rejects_unsafe_names_before_any_session(
    monkeypatch: pytest.MonkeyPatch, name: object
) -> None:
    monkeypatch.setattr(bitbucket, "bearer_session", forbidden_session)

    with pytest.raises(AtlaWireError, match="tag name"):
        bitbucket.get_tag(BASE, REPO, cast(str, name), token=TOKEN)


def test_get_tag_rejects_an_invalid_repo_before_any_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(bitbucket, "bearer_session", forbidden_session)

    with pytest.raises(AtlaWireError, match="PROJECT/slug"):
        bitbucket.get_tag(BASE, "DEMO", "v1", token=TOKEN)


@responses.activate
def test_get_tag_real_transport_sends_one_encoded_get() -> None:
    responses.get(TAG_URL, json=TAG_TWO)

    value = bitbucket.get_tag(BASE, REPO, TAG_NAME, token=TOKEN)

    assert value == TAG_TWO
    assert len(responses.calls) == 1
    request = responses.calls[0].request
    assert request.method == "GET"
    assert request.url == TAG_URL
    assert request.headers["Authorization"] == f"Bearer {TOKEN}"


@responses.activate
@pytest.mark.parametrize(
    "body",
    [[], "text", 7, None, True],
    ids=["array", "string", "number", "null", "boolean"],
)
def test_get_tag_rejects_a_non_object_response(body: object) -> None:
    if body is None:
        responses.get(TAG_URL, body="null", content_type="application/json")
    else:
        responses.get(TAG_URL, json=body)

    with pytest.raises(AtlaWireError, match="Expected a JSON object"):
        bitbucket.get_tag(BASE, REPO, TAG_NAME, token=TOKEN)

    assert len(responses.calls) == 1


def test_get_last_modified_root_sends_no_path_or_at(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = stub_json(monkeypatch, [LAST_MODIFIED])

    value = bitbucket.get_last_modified(BASE, REPO, token=TOKEN)

    assert value is LAST_MODIFIED
    assert calls == [(LAST_MODIFIED_URL, {})]


@pytest.mark.parametrize(
    ("path", "at"),
    [(None, None), ("", None), (None, ""), ("", "")],
    ids=["none", "empty-path", "empty-at", "both-empty"],
)
def test_empty_path_and_at_are_omitted(
    monkeypatch: pytest.MonkeyPatch, path: str | None, at: str | None
) -> None:
    calls = stub_json(monkeypatch, [LAST_MODIFIED])

    value = bitbucket.get_last_modified(BASE, REPO, path, token=TOKEN, at=at)

    assert value is LAST_MODIFIED
    assert calls == [(LAST_MODIFIED_URL, {})]


def test_last_modified_encodes_the_relative_path_and_sends_at_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = stub_json(monkeypatch, [LAST_MODIFIED])

    value = bitbucket.get_last_modified(BASE, REPO, PATH, token=TOKEN, at=AT)

    assert value is LAST_MODIFIED
    assert calls == [(PATH_URL, {"at": AT})]


@pytest.mark.parametrize(
    "path",
    [
        "../secret",
        "src/../../secret",
        "src/..",
        "src/.",
        "/src",
        "src/",
        "src//x",
        "src\\x",
        "src/\x00x",
        "src/%2e%2e/x",
        7,
        [],
    ],
    ids=[
        "parent",
        "nested-parent",
        "parent-last",
        "current",
        "leading-slash",
        "trailing-slash",
        "double-slash",
        "backslash",
        "nul",
        "percent-escape",
        "number",
        "array",
    ],
)
def test_get_last_modified_rejects_unsafe_paths_before_any_session(
    monkeypatch: pytest.MonkeyPatch, path: object
) -> None:
    monkeypatch.setattr(bitbucket, "bearer_session", forbidden_session)

    with pytest.raises(AtlaWireError, match="relative file path"):
        bitbucket.get_last_modified(
            BASE, REPO, cast(str | None, path), token=TOKEN
        )


@pytest.mark.parametrize(
    "at",
    ["\n", "feature\r\nmain", "a\x00b", 7, True, [], {}],
    ids=["lf", "crlf", "nul", "number", "boolean", "array", "object"],
)
def test_get_last_modified_rejects_an_invalid_at_before_any_session(
    monkeypatch: pytest.MonkeyPatch, at: object
) -> None:
    monkeypatch.setattr(bitbucket, "bearer_session", forbidden_session)

    with pytest.raises(AtlaWireError, match="revision"):
        bitbucket.get_last_modified(
            BASE, REPO, token=TOKEN, at=cast(str | None, at)
        )


def test_get_last_modified_rejects_an_invalid_repo_before_any_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(bitbucket, "bearer_session", forbidden_session)

    with pytest.raises(AtlaWireError, match="PROJECT/slug"):
        bitbucket.get_last_modified(BASE, "DEMO", token=TOKEN)


@responses.activate
def test_get_last_modified_real_transport_sends_one_get_with_at() -> None:
    responses.get(PATH_URL, json=LAST_MODIFIED)

    value = bitbucket.get_last_modified(
        BASE, REPO, PATH, token=TOKEN, at=AT
    )

    assert value == LAST_MODIFIED
    assert len(responses.calls) == 1
    request = responses.calls[0].request
    assert request.method == "GET"
    assert request.url.split("?")[0] == PATH_URL
    assert parse_qs(urlsplit(request.url).query) == {"at": [AT]}
    assert request.headers["Authorization"] == f"Bearer {TOKEN}"


@responses.activate
@pytest.mark.parametrize(
    "body",
    [[], "text", 7, None, True],
    ids=["array", "string", "number", "null", "boolean"],
)
def test_get_last_modified_rejects_a_non_object_response(body: object) -> None:
    if body is None:
        responses.get(
            LAST_MODIFIED_URL, body="null", content_type="application/json"
        )
    else:
        responses.get(LAST_MODIFIED_URL, json=body)

    with pytest.raises(AtlaWireError, match="Expected a JSON object"):
        bitbucket.get_last_modified(BASE, REPO, token=TOKEN)

    assert len(responses.calls) == 1


@responses.activate
@pytest.mark.parametrize(
    ("status", "message"),
    [
        (401, "authentication rejected"),
        (403, "access denied"),
        (404, "HTTP 404"),
        (500, "HTTP 500"),
    ],
    ids=["401", "403", "404", "500"],
)
def test_get_last_modified_propagates_shared_http_errors(
    status: int, message: str
) -> None:
    responses.get(
        LAST_MODIFIED_URL, status=status, json={"errors": [{"message": "x"}]}
    )

    with pytest.raises(AtlaWireError, match=message):
        bitbucket.get_last_modified(BASE, REPO, token=TOKEN)

    assert len(responses.calls) == 1


@responses.activate
def test_get_last_modified_refuses_a_redirect_without_following_it() -> None:
    responses.get(
        LAST_MODIFIED_URL,
        status=302,
        headers={"Location": "https://evil.invalid/next"},
    )

    with pytest.raises(AtlaWireError, match="redirect refused"):
        bitbucket.get_last_modified(BASE, REPO, token=TOKEN)

    assert len(responses.calls) == 1
    assert "evil.invalid" not in responses.calls[0].request.url


def test_list_tags_closes_the_session_after_a_successful_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = TrackingSession()
    bodies = iter([page([TAG_ONE])])

    def fake_get_json_object(
        active: object, url: str, *, params: dict[str, str | int]
    ) -> dict[str, object]:
        assert active is session
        return next(bodies)

    monkeypatch.setattr(bitbucket, "bearer_session", lambda token: session)
    monkeypatch.setattr(bitbucket, "get_json_object", fake_get_json_object)

    rows = bitbucket.list_tags(BASE, REPO, token=TOKEN)

    assert rows == [TAG_ONE]
    assert session.closed


def test_get_tag_closes_the_session_when_the_transport_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = TrackingSession()

    def failing_get_json_object(
        active: object, url: str, *, params: dict[str, str | int]
    ) -> dict[str, object]:
        assert active is session
        raise AtlaWireError("HTTP 500: request failed.")

    monkeypatch.setattr(bitbucket, "bearer_session", lambda token: session)
    monkeypatch.setattr(bitbucket, "get_json_object", failing_get_json_object)

    with pytest.raises(AtlaWireError, match="HTTP 500"):
        bitbucket.get_tag(BASE, REPO, TAG_NAME, token=TOKEN)

    assert session.closed


def test_get_last_modified_closes_the_session_after_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = TrackingSession()

    def fake_get_json_object(
        active: object, url: str, *, params: dict[str, str | int]
    ) -> dict[str, object]:
        assert active is session
        return LAST_MODIFIED

    monkeypatch.setattr(bitbucket, "bearer_session", lambda token: session)
    monkeypatch.setattr(bitbucket, "get_json_object", fake_get_json_object)

    value = bitbucket.get_last_modified(BASE, REPO, token=TOKEN)

    assert value is LAST_MODIFIED
    assert session.closed
