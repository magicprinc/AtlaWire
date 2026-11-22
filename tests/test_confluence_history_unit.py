"""Unit checks for Confluence page history and explicit historical versions.

All credentials are synthetic and ``BBK_CREDENTIALS`` points at a path that must
not exist. No test contacts a real instance.
"""

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
    Path(__file__).with_name("bbk-credentials-missing-for-history-tests.json")
)


@pytest.fixture(autouse=True)
def _synthetic_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BBK_CREDENTIALS", MISSING_BBK_CREDENTIALS)


def history_object() -> dict[str, object]:
    return {
        "latest": True,
        "createdDate": "2020-01-01T00:00:00.000Z",
        "createdBy": {"displayName": "Ada", "username": "ada"},
        "previousVersion": {"number": 6, "message": "previous"},
        "nextVersion": {"number": 8, "message": "next"},
        "lastUpdated": {"number": 7, "message": "current", "minorEdit": False},
        "_links": {
            "self": "https://elsewhere.example.invalid/history",
            "next": "https://elsewhere.example.invalid/next",
        },
        "_expandable": {"contributors": ""},
        "unknown": [None, True, 2.5],
    }


def version_page(
    *, returned_id: object = "42", returned_version: object = 7
) -> dict[str, object]:
    return {
        "id": returned_id,
        "type": "page",
        "status": "historical",
        "title": "Résumé (old)",
        "version": {
            "number": returned_version,
            "message": "snapshot",
            "minorEdit": False,
            "by": {"displayName": "Ada"},
        },
        "body": {
            "storage": {"value": "<p>Old body</p>", "representation": "storage"}
        },
        "space": {"key": "DEMO", "name": "Demo"},
        "unknown": {"kept": [1, None]},
        "_links": {
            "self": "https://elsewhere.example.invalid/content/42",
            "next": "https://elsewhere.example.invalid/next",
        },
    }


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


def assert_url(
    request_url: str, path: str, expected_query: dict[str, list[str]]
) -> None:
    split = urlsplit(request_url)
    assert f"{split.scheme}://{split.netloc}{split.path}" == path
    assert parse_qs(split.query) == expected_query


def test_the_bbk_credentials_override_is_a_missing_synthetic_path() -> None:
    assert "missing-for-history-tests" in MISSING_BBK_CREDENTIALS
    assert not Path(MISSING_BBK_CREDENTIALS).exists()


def test_history_returns_the_raw_object_from_one_fixed_get(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = history_object()
    calls = loaded(monkeypatch, payload)

    result = confluence.get_page_history(BASE, PAGE_ID, token=TOKEN)

    assert result == payload
    assert result["previousVersion"] == {"number": 6, "message": "previous"}
    assert result["lastUpdated"] == {
        "number": 7,
        "message": "current",
        "minorEdit": False,
    }
    assert result["unknown"] == [None, True, 2.5]
    links = result["_links"]
    assert isinstance(links, dict)
    assert links["next"] == "https://elsewhere.example.invalid/next"
    assert calls == [(f"{BASE}/rest/api/content/42/history", {})]


def test_history_pasted_link_supplies_only_the_page_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = history_object()
    calls = loaded(monkeypatch, payload)

    result = confluence.get_page_history(
        BASE,
        "https://elsewhere.example.invalid/display/OTHER"
        "?spaceKey=OTHER&pageId=42#fragment",
        token=TOKEN,
    )

    assert result == payload
    assert calls == [(f"{BASE}/rest/api/content/42/history", {})]


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
def test_history_invalid_page_ids_create_no_session(
    monkeypatch: pytest.MonkeyPatch, page: str | bool
) -> None:
    forbid_network(monkeypatch)

    with pytest.raises(AtlaWireError, match="pageId"):
        confluence.get_page_history(BASE, page, token=TOKEN)


@responses.activate
@pytest.mark.parametrize(
    ("status", "message"),
    [
        (401, "HTTP 401"),
        (403, "HTTP 403"),
        (404, "HTTP 404"),
        (302, "redirect refused"),
    ],
)
def test_history_http_failures_raise_without_following(
    status: int, message: str
) -> None:
    path = f"{BASE}/rest/api/content/42/history"
    headers = (
        {"Location": "https://elsewhere.example.invalid/unexpected"}
        if status == 302
        else None
    )
    responses.get(
        path,
        status=status,
        headers=headers,
        json={"message": "RESPONSE-SENTINEL"},
    )

    with pytest.raises(AtlaWireError, match=message):
        confluence.get_page_history(BASE, PAGE_ID, token=TOKEN)

    assert len(responses.calls) == 1
    request = responses.calls[0].request
    assert_url(request.url, path, {})
    assert request.headers["Authorization"] == f"Bearer {TOKEN}"


@responses.activate
def test_history_rejects_a_non_object_response() -> None:
    path = f"{BASE}/rest/api/content/42/history"
    responses.get(path, json=["not", "an", "object"])

    with pytest.raises(AtlaWireError, match="JSON object"):
        confluence.get_page_history(BASE, PAGE_ID, token=TOKEN)

    assert len(responses.calls) == 1


def test_version_returns_raw_data_and_sends_the_exact_historical_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = version_page()
    calls = loaded(monkeypatch, payload)

    result = confluence.get_page_version(BASE, PAGE_ID, 7, token=TOKEN)

    assert result == payload
    assert result["body"] == {
        "storage": {"value": "<p>Old body</p>", "representation": "storage"}
    }
    assert result["version"] == payload["version"]
    assert result["unknown"] == {"kept": [1, None]}
    assert calls == [
        (
            f"{BASE}/rest/api/content/42",
            {
                "status": "historical",
                "version": 7,
                "expand": "body.storage,version",
            },
        )
    ]


def test_version_accepts_an_integer_returned_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = version_page(returned_id=42)
    calls = loaded(monkeypatch, payload)

    result = confluence.get_page_version(BASE, PAGE_ID, 7, token=TOKEN)

    assert result == payload
    assert result["id"] == 42
    assert len(calls) == 1


def test_version_pasted_link_supplies_only_the_page_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = version_page()
    calls = loaded(monkeypatch, payload)

    result = confluence.get_page_version(
        BASE,
        "https://elsewhere.example.invalid/display/OTHER"
        "?spaceKey=OTHER&pageId=42#fragment",
        7,
        token=TOKEN,
    )

    assert result == payload
    assert calls == [
        (
            f"{BASE}/rest/api/content/42",
            {
                "status": "historical",
                "version": 7,
                "expand": "body.storage,version",
            },
        )
    ]


@pytest.mark.parametrize(
    "version",
    [
        pytest.param(0, id="zero"),
        pytest.param(-1, id="negative"),
        pytest.param(True, id="boolean"),
        pytest.param(1.5, id="float"),
        pytest.param("7", id="string"),
        pytest.param(None, id="none"),
    ],
)
def test_invalid_requested_versions_create_no_session(
    monkeypatch: pytest.MonkeyPatch, version: object
) -> None:
    forbid_network(monkeypatch)

    with pytest.raises(AtlaWireError, match="version"):
        confluence.get_page_version(BASE, PAGE_ID, version, token=TOKEN)


@pytest.mark.parametrize(
    "page",
    [
        "0",
        "007",
        "abc",
        "https://elsewhere.example.invalid/pages/viewpage.action"
        "?pageId=1&pageId=2",
        pytest.param(True, id="boolean"),
    ],
)
def test_version_invalid_page_ids_create_no_session(
    monkeypatch: pytest.MonkeyPatch, page: str | bool
) -> None:
    forbid_network(monkeypatch)

    with pytest.raises(AtlaWireError, match="pageId"):
        confluence.get_page_version(BASE, page, 7, token=TOKEN)


@pytest.mark.parametrize(
    "returned_id",
    [
        pytest.param("43", id="other-string-id"),
        pytest.param(43, id="other-integer-id"),
        pytest.param("042", id="padded-string-id"),
        pytest.param(True, id="boolean-id"),
    ],
)
def test_version_rejects_a_mismatched_returned_id(
    monkeypatch: pytest.MonkeyPatch, returned_id: object
) -> None:
    payload = version_page(returned_id=returned_id)
    calls = loaded(monkeypatch, payload)

    with pytest.raises(AtlaWireError, match="Confluence page"):
        confluence.get_page_version(BASE, PAGE_ID, 7, token=TOKEN)

    assert len(calls) == 1


@pytest.mark.parametrize(
    "returned_version",
    [
        pytest.param(8, id="other-version"),
        pytest.param(True, id="boolean"),
        pytest.param("7", id="string"),
        pytest.param(7.0, id="float"),
        pytest.param(None, id="none"),
    ],
)
def test_version_rejects_mismatched_or_malformed_version_metadata(
    monkeypatch: pytest.MonkeyPatch, returned_version: object
) -> None:
    payload = version_page(returned_version=returned_version)
    calls = loaded(monkeypatch, payload)

    with pytest.raises(AtlaWireError, match="version"):
        confluence.get_page_version(BASE, PAGE_ID, 7, token=TOKEN)

    assert len(calls) == 1


@pytest.mark.parametrize(
    "version_value",
    [
        pytest.param(None, id="null-version"),
        pytest.param([], id="array-version"),
        pytest.param({}, id="empty-version"),
        pytest.param({"number": None}, id="null-number"),
    ],
)
def test_version_rejects_a_missing_or_non_object_version(
    monkeypatch: pytest.MonkeyPatch, version_value: object
) -> None:
    payload = version_page()
    payload["version"] = version_value
    calls = loaded(monkeypatch, payload)

    with pytest.raises(AtlaWireError, match="version"):
        confluence.get_page_version(BASE, PAGE_ID, 7, token=TOKEN)

    assert len(calls) == 1


@pytest.mark.parametrize(
    "page",
    [
        pytest.param(
            {**version_page(), "type": "blogpost"}, id="wrong-type"
        ),
        pytest.param({**version_page(), "title": 5}, id="non-string-title"),
        pytest.param(
            {**version_page(), "body": {}}, id="missing-storage"
        ),
        pytest.param(
            {**version_page(), "body": {"storage": {"value": 5}}},
            id="non-string-storage-value",
        ),
    ],
)
def test_version_rejects_invalid_page_shape(
    monkeypatch: pytest.MonkeyPatch, page: dict[str, object]
) -> None:
    calls = loaded(monkeypatch, page)

    with pytest.raises(AtlaWireError, match="Confluence page"):
        confluence.get_page_version(BASE, PAGE_ID, 7, token=TOKEN)

    assert len(calls) == 1


@responses.activate
@pytest.mark.parametrize(
    ("status", "message"),
    [
        (401, "HTTP 401"),
        (403, "HTTP 403"),
        (404, "HTTP 404"),
        (302, "redirect refused"),
    ],
)
def test_version_http_failures_raise_without_following(
    status: int, message: str
) -> None:
    path = f"{BASE}/rest/api/content/42"
    headers = (
        {"Location": "https://elsewhere.example.invalid/unexpected"}
        if status == 302
        else None
    )
    responses.get(
        path,
        status=status,
        headers=headers,
        json={"message": "RESPONSE-SENTINEL"},
    )

    with pytest.raises(AtlaWireError, match=message):
        confluence.get_page_version(BASE, PAGE_ID, 7, token=TOKEN)

    assert len(responses.calls) == 1
    request = responses.calls[0].request
    assert_url(
        request.url,
        path,
        {
            "status": ["historical"],
            "version": ["7"],
            "expand": ["body.storage,version"],
        },
    )
    assert request.headers["Authorization"] == f"Bearer {TOKEN}"


@responses.activate
def test_version_rejects_a_non_object_response() -> None:
    path = f"{BASE}/rest/api/content/42"
    responses.get(path, json=["not", "an", "object"])

    with pytest.raises(AtlaWireError, match="JSON object"):
        confluence.get_page_version(BASE, PAGE_ID, 7, token=TOKEN)

    assert len(responses.calls) == 1
