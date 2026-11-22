"""Unit checks for bounded Confluence attachment, comment, and label reads.

Comment reads request replies and storage bodies by default. All credentials are
synthetic and ``BBK_CREDENTIALS`` points at a path that must not exist. No test
contacts a real instance.
"""

from collections.abc import Callable
from contextlib import nullcontext
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
import responses

from atlawire import confluence
from atlawire.http import AtlaWireError

BASE = "https://wiki.example.invalid/wiki"
TOKEN = "fixture-only"
PAGE_ID = 42
MISSING_BBK_CREDENTIALS = str(
    Path(__file__).with_name("bbk-credentials-missing-for-extra-tests.json")
)

type Reader = Callable[..., dict[str, object]]

CASES = [
    pytest.param(
        confluence.get_page_attachments,
        "/rest/api/content/42/child/attachment",
        confluence.ATTACHMENT_LIMIT_DEFAULT,
        {},
        id="attachments",
    ),
    pytest.param(
        confluence.get_page_comments,
        "/rest/api/content/42/child/comment",
        confluence.COMMENT_LIMIT_DEFAULT,
        {"expand": "body.storage", "depth": "all"},
        id="comments",
    ),
    pytest.param(
        confluence.get_page_labels,
        "/rest/api/content/42/label",
        confluence.LABEL_LIMIT_DEFAULT,
        {},
        id="labels",
    ),
]


@pytest.fixture(autouse=True)
def _synthetic_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BBK_CREDENTIALS", MISSING_BBK_CREDENTIALS)


def loaded(
    monkeypatch: pytest.MonkeyPatch, payload: dict[str, object]
) -> list[tuple[str, dict[str, str | int]]]:
    """Replace the session and transport with one recorded fixed response."""
    calls: list[tuple[str, dict[str, str | int]]] = []

    def fake_get_json_object(
        session: object, url: str, *, params: dict[str, str | int]
    ) -> dict[str, object]:
        calls.append((url, dict(params)))
        return payload

    monkeypatch.setattr(
        confluence, "bearer_session", lambda token: nullcontext(object())
    )
    monkeypatch.setattr(confluence, "get_json_object", fake_get_json_object)
    return calls


def forbid_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail the test if invalid input reaches session creation or transport."""

    def unexpected_session(token: str) -> object:
        raise AssertionError("No session should be created.")

    def unexpected_request(*args: object, **kwargs: object) -> object:
        raise AssertionError("No request should be made.")

    monkeypatch.setattr(confluence, "bearer_session", unexpected_session)
    monkeypatch.setattr(confluence, "get_json_object", unexpected_request)


def expected_query(
    fixed_params: dict[str, str], start: int, limit: int
) -> dict[str, str | int]:
    return {**fixed_params, "start": start, "limit": limit}


def test_the_bbk_credentials_override_is_a_missing_synthetic_path() -> None:
    assert "missing-for-extra-tests" in MISSING_BBK_CREDENTIALS
    assert not Path(MISSING_BBK_CREDENTIALS).exists()


@pytest.mark.parametrize(
    ("reader", "suffix", "default_limit", "fixed_params"), CASES
)
def test_one_bounded_request_returns_the_raw_object_unchanged(
    monkeypatch: pytest.MonkeyPatch,
    reader: Reader,
    suffix: str,
    default_limit: int,
    fixed_params: dict[str, str],
) -> None:
    payload: dict[str, object] = {
        "results": [
            {
                "id": "fixture-1",
                "type": "attachment",
                "metadata": {"mediaType": "application/pdf", "comment": None},
            }
        ],
        "start": 7,
        "limit": 3,
        "size": 1,
        "totalSize": 9,
        "_links": {
            "base": "https://elsewhere.example.invalid",
            "next": f"{BASE}{suffix}?start=8&limit=3",
        },
        "unknown": [None, True, 2.5],
    }
    calls = loaded(monkeypatch, payload)

    result = reader(BASE, PAGE_ID, token=TOKEN, start=7, limit=3)

    assert result == payload
    assert result["results"] == payload["results"]
    assert result["totalSize"] == 9
    assert result["unknown"] == [None, True, 2.5]
    links = result["_links"]
    assert isinstance(links, dict)
    assert links["next"] == f"{BASE}{suffix}?start=8&limit=3"
    # Only the fixed endpoint query and explicit pagination are sent; the
    # continuation link above is never followed.
    assert calls == [(f"{BASE}{suffix}", expected_query(fixed_params, 7, 3))]


@pytest.mark.parametrize(
    ("reader", "suffix", "default_limit", "fixed_params"), CASES
)
def test_default_pagination_is_sent_explicitly(
    monkeypatch: pytest.MonkeyPatch,
    reader: Reader,
    suffix: str,
    default_limit: int,
    fixed_params: dict[str, str],
) -> None:
    calls = loaded(monkeypatch, {"fixture": True})

    result = reader(BASE, PAGE_ID, token=TOKEN)

    assert result == {"fixture": True}
    assert calls == [
        (f"{BASE}{suffix}", expected_query(fixed_params, 0, default_limit))
    ]


@pytest.mark.parametrize(
    ("reader", "suffix", "default_limit", "fixed_params"), CASES
)
def test_the_maximum_page_limit_is_sent_as_is(
    monkeypatch: pytest.MonkeyPatch,
    reader: Reader,
    suffix: str,
    default_limit: int,
    fixed_params: dict[str, str],
) -> None:
    calls = loaded(monkeypatch, {"fixture": True})

    reader(BASE, PAGE_ID, token=TOKEN, start=0, limit=confluence.PAGE_LIMIT_MAX)

    assert calls == [
        (
            f"{BASE}{suffix}",
            expected_query(fixed_params, 0, confluence.PAGE_LIMIT_MAX),
        )
    ]


def test_a_pasted_page_link_supplies_only_its_page_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = loaded(monkeypatch, {"results": []})

    result = confluence.get_page_attachments(
        BASE,
        "https://elsewhere.example.invalid/display/OTHER"
        "?spaceKey=OTHER&pageId=42#fragment",
        token=TOKEN,
        start=1,
        limit=2,
    )

    assert result == {"results": []}
    assert calls == [
        (
            f"{BASE}/rest/api/content/42/child/attachment",
            {"start": 1, "limit": 2},
        )
    ]


def test_comments_preserve_the_documented_content_type_map(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Confluence 6.6.0 documents this endpoint as a map keyed by content type,
    # so the adapter must not look for a top-level results array.
    payload: dict[str, object] = {
        "page": {
            "results": [{"id": "c1", "type": "comment", "title": "Re: Page"}],
            "size": 1,
            "start": 6,
            "limit": 2,
            "_links": {"next": "https://elsewhere.example.invalid/next"},
        },
        "space": {"results": [], "size": 0},
    }
    calls = loaded(monkeypatch, payload)

    result = confluence.get_page_comments(
        BASE, PAGE_ID, token=TOKEN, start=6, limit=2
    )

    assert result == payload
    assert "results" not in result
    assert calls == [
        (
            f"{BASE}/rest/api/content/42/child/comment",
            expected_query(
                {"expand": "body.storage", "depth": "all"}, 6, 2
            ),
        )
    ]


def test_comments_can_request_root_comments_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload: dict[str, object] = {
        "page": {
            "results": [{"id": "c1", "type": "comment"}],
            "size": 1,
            "start": 6,
            "limit": 2,
        }
    }
    calls = loaded(monkeypatch, payload)

    result = confluence.get_page_comments(
        BASE,
        PAGE_ID,
        token=TOKEN,
        start=6,
        limit=2,
        include_replies=False,
    )

    assert result == payload
    # Root-only relies on the documented server default, so ``depth`` is
    # omitted instead of sending an empty value of uncertain meaning.
    assert calls == [
        (
            f"{BASE}/rest/api/content/42/child/comment",
            expected_query({"expand": "body.storage"}, 6, 2),
        )
    ]


@pytest.mark.parametrize(
    ("include_replies", "expected_params"),
    [
        (
            True,
            {
                "expand": "body.storage",
                "depth": "all",
                "start": 6,
                "limit": 2,
            },
        ),
        (
            False,
            {"expand": "body.storage", "start": 6, "limit": 2},
        ),
    ],
    ids=["all-replies", "root-only"],
)
def test_comments_query_has_exact_parameters_for_each_mode(
    monkeypatch: pytest.MonkeyPatch,
    include_replies: bool,
    expected_params: dict[str, str | int],
) -> None:
    calls = loaded(monkeypatch, {"fixture": True})

    result = confluence.get_page_comments(
        BASE,
        PAGE_ID,
        token=TOKEN,
        start=6,
        limit=2,
        include_replies=include_replies,
    )

    assert result == {"fixture": True}
    assert calls == [
        (f"{BASE}/rest/api/content/42/child/comment", expected_params)
    ]


@pytest.mark.parametrize(
    "include_replies",
    [0, 1, "all", None],
    ids=["zero", "one", "string", "none"],
)
def test_invalid_include_replies_is_rejected_before_any_session(
    monkeypatch: pytest.MonkeyPatch, include_replies: object
) -> None:
    forbid_network(monkeypatch)

    with pytest.raises(AtlaWireError, match="include_replies"):
        confluence.get_page_comments(
            BASE, PAGE_ID, token=TOKEN, include_replies=include_replies
        )


def test_labels_preserve_a_response_without_documented_pagination_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The 6.6.0 documentation publishes no label response schema, so an unknown
    # object shape must pass through untouched.
    payload: dict[str, object] = {
        "labels": [{"prefix": "global", "name": "docs"}],
        "nextStart": 1,
    }
    calls = loaded(monkeypatch, payload)

    result = confluence.get_page_labels(BASE, PAGE_ID, token=TOKEN, start=0, limit=2)

    assert result == payload
    assert calls == [
        (f"{BASE}/rest/api/content/42/label", {"start": 0, "limit": 2})
    ]


@pytest.mark.parametrize(
    ("reader", "suffix", "default_limit", "fixed_params"), CASES
)
@pytest.mark.parametrize(
    "page",
    [
        "0",
        "007",
        "abc",
        "/pages/42",
        "",
        "https://elsewhere.example.invalid/pages/viewpage.action"
        "?pageId=1&pageId=2",
        pytest.param(True, id="boolean"),
    ],
)
def test_invalid_page_ids_create_no_session(
    monkeypatch: pytest.MonkeyPatch,
    reader: Reader,
    suffix: str,
    default_limit: int,
    fixed_params: dict[str, str],
    page: str | bool,
) -> None:
    forbid_network(monkeypatch)

    with pytest.raises(AtlaWireError, match="pageId"):
        reader(BASE, page, token=TOKEN, start=0, limit=2)


@pytest.mark.parametrize(
    ("reader", "suffix", "default_limit", "fixed_params"), CASES
)
@pytest.mark.parametrize(
    "start",
    [
        pytest.param(-1, id="negative"),
        pytest.param(True, id="boolean"),
        pytest.param(1.5, id="float"),
        pytest.param("0", id="string"),
    ],
)
def test_invalid_start_is_rejected_before_any_session(
    monkeypatch: pytest.MonkeyPatch,
    reader: Reader,
    suffix: str,
    default_limit: int,
    fixed_params: dict[str, str],
    start: int | bool | float | str,
) -> None:
    forbid_network(monkeypatch)

    with pytest.raises(AtlaWireError, match="start"):
        reader(BASE, PAGE_ID, token=TOKEN, start=start, limit=2)


@pytest.mark.parametrize(
    ("reader", "suffix", "default_limit", "fixed_params"), CASES
)
@pytest.mark.parametrize(
    "limit",
    [
        pytest.param(0, id="zero"),
        pytest.param(-1, id="negative"),
        pytest.param(1001, id="too-large"),
        pytest.param(True, id="boolean"),
        pytest.param(1.5, id="float"),
        pytest.param("10", id="string"),
    ],
)
def test_invalid_limit_is_rejected_before_any_session(
    monkeypatch: pytest.MonkeyPatch,
    reader: Reader,
    suffix: str,
    default_limit: int,
    fixed_params: dict[str, str],
    limit: int | bool | float | str,
) -> None:
    forbid_network(monkeypatch)

    with pytest.raises(AtlaWireError, match="limit"):
        reader(BASE, PAGE_ID, token=TOKEN, start=0, limit=limit)


@responses.activate
@pytest.mark.parametrize(
    ("reader", "suffix", "default_limit", "fixed_params"), CASES
)
@pytest.mark.parametrize(
    ("status", "message"),
    [
        (401, "HTTP 401"),
        (403, "HTTP 403"),
        (404, "HTTP 404"),
        (302, "redirect refused"),
    ],
)
def test_http_failures_raise_without_following_the_response(
    reader: Reader,
    suffix: str,
    default_limit: int,
    fixed_params: dict[str, str],
    status: int,
    message: str,
) -> None:
    url = f"{BASE}{suffix}"
    headers = (
        {"Location": "https://elsewhere.example.invalid/unexpected"}
        if status == 302
        else None
    )
    responses.get(
        url,
        status=status,
        headers=headers,
        json={"message": "RESPONSE-SENTINEL"},
    )

    with pytest.raises(AtlaWireError, match=message):
        reader(BASE, PAGE_ID, token=TOKEN, start=3, limit=2)

    assert len(responses.calls) == 1
    request = responses.calls[0].request
    split = urlsplit(request.url)
    assert f"{split.scheme}://{split.netloc}{split.path}" == url
    assert parse_qs(split.query) == {
        key: [str(value)]
        for key, value in expected_query(fixed_params, 3, 2).items()
    }
    assert request.headers["Authorization"] == f"Bearer {TOKEN}"


@responses.activate
@pytest.mark.parametrize(
    ("reader", "suffix", "default_limit", "fixed_params"), CASES
)
def test_a_top_level_array_is_rejected(
    reader: Reader,
    suffix: str,
    default_limit: int,
    fixed_params: dict[str, str],
) -> None:
    responses.get(f"{BASE}{suffix}", json=["not", "an", "object"])

    with pytest.raises(AtlaWireError, match="JSON object"):
        reader(BASE, PAGE_ID, token=TOKEN, start=0, limit=2)

    assert len(responses.calls) == 1
