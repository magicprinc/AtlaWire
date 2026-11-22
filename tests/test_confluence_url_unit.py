"""Unit checks for Confluence page web URL construction.

All credentials are synthetic and ``BBK_CREDENTIALS`` points at a path that must
not exist. No test contacts a real instance.
"""

from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
import responses

from atlawire import confluence
from atlawire.http import AtlaWireError

BASE = "https://wiki.example.invalid/wiki"
TOKEN = "fixture-secret-token"
PAGE_ID = 42
MISSING_BBK_CREDENTIALS = str(
    Path(__file__).with_name("bbk-credentials-missing-for-url-tests.json")
)
FALLBACK = f"{BASE}/pages/viewpage.action?pageId={PAGE_ID}"


@pytest.fixture(autouse=True)
def _synthetic_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BBK_CREDENTIALS", MISSING_BBK_CREDENTIALS)


def page(webui: object = "/display/DEMO/Page") -> dict[str, object]:
    return {
        "id": "42",
        "type": "page",
        "status": "current",
        "title": "Résumé",
        "version": {"number": 3},
        "body": {
            "storage": {"value": "<p>Body</p>", "representation": "storage"}
        },
        "_links": {
            "webui": webui,
            "self": "https://elsewhere.example.invalid/content/42",
        },
    }


def without_links() -> dict[str, object]:
    value = page()
    del value["_links"]
    return value


def fake_page(
    monkeypatch: pytest.MonkeyPatch, value: dict[str, object]
) -> list[tuple[str, object, str, bool]]:
    calls: list[tuple[str, object, str, bool]] = []

    def fake_get_page(
        base_url: str,
        page_id_or_url: str | int,
        *,
        token: str,
        allow_http_loopback: bool = False,
    ) -> dict[str, object]:
        calls.append((base_url, page_id_or_url, token, allow_http_loopback))
        return value

    monkeypatch.setattr(confluence, "get_page", fake_get_page)
    return calls


def test_the_bbk_credentials_override_is_a_missing_synthetic_path() -> None:
    assert "missing-for-url-tests" in MISSING_BBK_CREDENTIALS
    assert not Path(MISSING_BBK_CREDENTIALS).exists()


def test_source_webui_is_appended_to_the_configured_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = fake_page(
        monkeypatch, page("/display/DEMO/Résumé?x=1#section")
    )

    result = confluence.get_page_web_url(BASE, PAGE_ID, token=TOKEN)

    assert result == f"{BASE}/display/DEMO/Résumé?x=1#section"
    assert TOKEN not in result
    assert calls == [(BASE, "42", TOKEN, False)]


def test_source_webui_uses_a_normalized_base_without_doubling_the_slash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = fake_page(monkeypatch, page("/display/DEMO/Page"))

    result = confluence.get_page_web_url(BASE + "/", PAGE_ID, token=TOKEN)

    assert result == f"{BASE}/display/DEMO/Page"
    assert calls == [(BASE, "42", TOKEN, False)]


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(without_links(), id="no-links"),
        pytest.param({**page(), "_links": None}, id="null-links"),
        pytest.param({**page(), "_links": []}, id="array-links"),
        pytest.param({**page(), "_links": "links"}, id="string-links"),
        pytest.param({**page(), "_links": {}}, id="empty-links"),
        pytest.param({**page(), "_links": {"webui": None}}, id="null-webui"),
        pytest.param({**page(), "_links": {"webui": ""}}, id="empty-webui"),
        pytest.param({**page(), "_links": {"webui": 7}}, id="integer-webui"),
        pytest.param({**page(), "_links": {"webui": True}}, id="boolean-webui"),
        pytest.param({**page(), "_links": {"webui": []}}, id="array-webui"),
        pytest.param({**page(), "_links": {"webui": {}}}, id="object-webui"),
    ],
)
def test_missing_or_malformed_links_use_the_deterministic_fallback(
    monkeypatch: pytest.MonkeyPatch, value: dict[str, object]
) -> None:
    calls = fake_page(monkeypatch, value)

    result = confluence.get_page_web_url(BASE, PAGE_ID, token=TOKEN)

    assert result == FALLBACK
    assert TOKEN not in result
    assert len(calls) == 1


@pytest.mark.parametrize(
    "webui",
    [
        pytest.param("https://evil.invalid/display", id="absolute-https"),
        pytest.param("http://evil.invalid/display", id="absolute-http"),
        pytest.param("//evil.invalid/display", id="scheme-relative"),
        pytest.param("///evil.invalid/display", id="triple-slash"),
        pytest.param("/\\evil.invalid/display", id="backslash"),
        pytest.param("/%5c%5cevil.invalid/display", id="encoded-backslash"),
        pytest.param("/display/../../admin", id="literal-traversal"),
        pytest.param("/display/%2e%2e/%2e%2e/admin", id="encoded-traversal"),
        pytest.param(
            "/display/%252e%252e/admin", id="double-encoded-traversal"
        ),
        pytest.param("/display/%2E%2E/admin", id="uppercase-traversal"),
        pytest.param("/display/%2f..%2fadmin", id="encoded-slash-traversal"),
        pytest.param("/display/..%2fadmin", id="mixed-slash-traversal"),
        pytest.param("/display/..;/admin", id="semicolon-traversal"),
        pytest.param(
            "/display/%2e%2e%3b/admin", id="encoded-semicolon-traversal"
        ),
        pytest.param("/display/page\x00", id="null-control"),
        pytest.param("/display/page\n", id="newline-control"),
        pytest.param("/display/page\x7f", id="delete-control"),
        pytest.param("/display/page\u202e", id="bidi-control"),
        pytest.param("/display/page%0d%0a", id="encoded-crlf"),
        pytest.param("javascript:alert(1)", id="javascript-scheme"),
        pytest.param("file:///etc/passwd", id="file-scheme"),
        pytest.param("display/page", id="no-leading-slash"),
        pytest.param(" /display/page", id="leading-space"),
        pytest.param("\t/display/page", id="leading-tab"),
    ],
)
def test_unsafe_webui_is_never_used(
    monkeypatch: pytest.MonkeyPatch, webui: str
) -> None:
    calls = fake_page(monkeypatch, page(webui))

    result = confluence.get_page_web_url(BASE, PAGE_ID, token=TOKEN)

    assert result == FALLBACK
    assert "evil.invalid" not in result
    assert TOKEN not in result
    assert len(calls) == 1


def test_a_pasted_foreign_page_link_only_supplies_the_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = fake_page(monkeypatch, page("/display/DEMO/Page"))

    result = confluence.get_page_web_url(
        BASE,
        "https://elsewhere.example.invalid/display/OTHER"
        "?spaceKey=OTHER&pageId=42#fragment",
        token=TOKEN,
    )

    assert result == f"{BASE}/display/DEMO/Page"
    assert "elsewhere.example.invalid" not in result
    assert calls == [(BASE, "42", TOKEN, False)]


@pytest.mark.parametrize(
    "value",
    [
        "0",
        "007",
        "abc",
        "https://elsewhere.example.invalid/pages/viewpage.action"
        "?pageId=1&pageId=2",
        pytest.param(True, id="boolean"),
    ],
)
def test_invalid_page_ids_are_rejected_before_page_lookup(
    monkeypatch: pytest.MonkeyPatch, value: str | bool
) -> None:
    def unexpected_get_page(*args: object, **kwargs: object) -> object:
        raise AssertionError("No page lookup should be made.")

    monkeypatch.setattr(confluence, "get_page", unexpected_get_page)

    with pytest.raises(AtlaWireError, match="pageId"):
        confluence.get_page_web_url(BASE, value, token=TOKEN)


def test_an_invalid_base_url_is_rejected_before_page_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_get_page(*args: object, **kwargs: object) -> object:
        raise AssertionError("No page lookup should be made.")

    monkeypatch.setattr(confluence, "get_page", unexpected_get_page)

    with pytest.raises(AtlaWireError, match="HTTPS"):
        confluence.get_page_web_url(
            "http://wiki.example.invalid", PAGE_ID, token=TOKEN
        )


def test_loopback_permission_is_forwarded_to_the_page_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = fake_page(monkeypatch, page("/display/DEMO/Page"))

    result = confluence.get_page_web_url(
        "http://127.0.0.1:8123/wiki",
        PAGE_ID,
        token=TOKEN,
        allow_http_loopback=True,
    )

    assert result == "http://127.0.0.1:8123/wiki/display/DEMO/Page"
    assert calls == [
        ("http://127.0.0.1:8123/wiki", "42", TOKEN, True)
    ]


@responses.activate
def test_the_real_page_transport_supplies_the_source_url() -> None:
    path = f"{BASE}/rest/api/content/42"
    responses.get(path, json=page("/display/DEMO/Page"))

    result = confluence.get_page_web_url(BASE, PAGE_ID, token=TOKEN)

    assert result == f"{BASE}/display/DEMO/Page"
    assert len(responses.calls) == 1
    split = urlsplit(responses.calls[0].request.url)
    assert f"{split.scheme}://{split.netloc}{split.path}" == path
    assert parse_qs(split.query) == {
        "expand": ["body.storage,version,space,ancestors"]
    }
    assert responses.calls[0].request.headers["Authorization"] == (
        f"Bearer {TOKEN}"
    )


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
def test_transport_errors_raise_without_a_url(
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

    with pytest.raises(AtlaWireError, match=message) as caught:
        confluence.get_page_web_url(BASE, PAGE_ID, token=TOKEN)

    assert len(responses.calls) == 1
    assert TOKEN not in str(caught.value)
    assert "RESPONSE-SENTINEL" not in str(caught.value)
