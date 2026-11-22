"""Unit checks for the Jira issue remote link adapter.

Every request is replaced at the adapter boundary and every credential is a
synthetic fixture; no test reads process settings or contacts a real server.
"""

from contextlib import nullcontext
from typing import cast

import pytest

from atlawire import jira
from atlawire.http import AtlaWireError

BASE = "https://jira.example.invalid/jira"
LOOPBACK = "http://127.0.0.1:8080/jira"
TOKEN = "fixture-jira-remote-links-token"
KEY = "DEMO-42"
SENTINEL = "JIRA-REMOTE-LINKS-SENTINEL"
REMOTE_LINK_PATH = f"{BASE}/rest/api/2/issue/{KEY}/remotelink"

# Complete server-shaped links, written out independently of the adapter. The
# second link deliberately omits fields and uses nulls so a projection that
# drops unknown, nested, or null values fails equality.
LINKS: list[dict[str, object]] = [
    {
        "id": 10000,
        "self": f"https://pasted.example.invalid{REMOTE_LINK_PATH}/10000",
        "globalId": f"system=https://tracker.example.invalid/&id={SENTINEL}",
        "application": {"type": "com.acme.tracker", "name": "Acme Tracker"},
        "relationship": "causes",
        "object": {
            "url": "https://tracker.example.invalid/TSTSUP-111",
            "title": "TSTSUP-111",
            "summary": "Résumé ✓ \u2014 многострочный\nsummary",
            "icon": {
                "url16x16": "https://tracker.example.invalid/ticket.png",
                "title": "Support Ticket",
                "link": None,
            },
            "status": {
                "resolved": True,
                "icon": {
                    "url16x16": "https://tracker.example.invalid/closed.png",
                    "title": "Case Closed",
                    "link": "https://tracker.example.invalid/details?closed=1",
                },
            },
        },
        "pluginField": {"nested": [1, 2.5, None, False, {"deep": []}]},
    },
    {
        "id": 10001,
        "self": None,
        "globalId": None,
        "application": None,
        "object": {
            "url": None,
            "title": None,
            "summary": None,
            "icon": None,
            "status": {"resolved": False, "icon": None},
        },
    },
]


def read_links(
    monkeypatch: pytest.MonkeyPatch,
    values: list[object],
    *,
    base: str = BASE,
    argument: str = KEY,
    allow_http_loopback: bool = False,
) -> tuple[list[dict[str, object]], list[tuple[str, dict[str, str | int]]], list[str]]:
    """Call the adapter with a fake transport and record URL, params, and token."""
    seen: list[tuple[str, dict[str, str | int]]] = []
    tokens: list[str] = []

    def fake_bearer_session(token: str) -> object:
        tokens.append(token)
        return nullcontext(None)

    def fake_get_json_array(
        session: object, url: str, *, params: dict[str, str | int]
    ) -> list[object]:
        seen.append((url, dict(params)))
        return values

    monkeypatch.setattr(jira, "bearer_session", fake_bearer_session)
    monkeypatch.setattr(jira, "get_json_array", fake_get_json_array)
    rows = jira.list_issue_remote_links(
        base,
        argument,
        token=TOKEN,
        allow_http_loopback=allow_http_loopback,
    )
    return rows, seen, tokens


def test_remote_links_request_the_fixed_endpoint_with_no_query_parameters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows, seen, tokens = read_links(monkeypatch, [LINKS[0]])

    assert rows == [LINKS[0]]
    assert seen == [(REMOTE_LINK_PATH, {})]
    assert tokens == [TOKEN]


@pytest.mark.parametrize("base", [BASE, f"{BASE}/"], ids=["no-slash", "trailing-slash"])
def test_a_trailing_base_slash_does_not_change_the_request_url(
    monkeypatch: pytest.MonkeyPatch, base: str
) -> None:
    _, seen, _ = read_links(monkeypatch, [], base=base)

    assert seen == [(REMOTE_LINK_PATH, {})]


def test_multiple_links_keep_every_nested_field_null_and_unknown_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows, seen, _ = read_links(monkeypatch, list(LINKS))

    assert rows == LINKS
    assert seen == [(REMOTE_LINK_PATH, {})]
    first, second = rows
    assert list(first) == [
        "id",
        "self",
        "globalId",
        "application",
        "relationship",
        "object",
        "pluginField",
    ]
    assert isinstance(first["id"], int) and not isinstance(first["id"], bool)
    assert first["object"] == LINKS[0]["object"]
    assert first["pluginField"] == LINKS[0]["pluginField"]
    assert second["globalId"] is None
    assert second["application"] is None
    assert cast(dict[str, object], second["object"])["status"] == {
        "resolved": False,
        "icon": None,
    }


def test_an_empty_remote_link_array_is_a_valid_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows, seen, _ = read_links(monkeypatch, [])

    assert rows == []
    assert seen == [(REMOTE_LINK_PATH, {})]


@pytest.mark.parametrize(
    "argument",
    [
        KEY,
        f"https://pasted.example.invalid/jira/browse/{KEY}",
        f"https://pasted.example.invalid/jira/browse/{KEY}/?tab=links#frag",
        f"http://pasted.example.invalid/browse/{KEY}",
    ],
    ids=["key", "foreign-browse-url", "foreign-url-with-query", "foreign-http-url"],
)
def test_a_pasted_browse_url_supplies_only_the_key(
    monkeypatch: pytest.MonkeyPatch, argument: str
) -> None:
    rows, seen, _ = read_links(monkeypatch, [LINKS[1]], argument=argument)

    assert rows == [LINKS[1]]
    # The destination stays the configured instance; only the key is reused.
    assert seen == [(REMOTE_LINK_PATH, {})]


@pytest.mark.parametrize(
    "argument",
    [
        "",
        " ",
        "demo-42",
        "DEMO",
        "DEMO-",
        "-42",
        "DEMO-42 ",
        " DEMO-42",
        "DEMO-42x",
        "DEMO-42/extra",
        f"https://pasted.example.invalid/browse/{KEY}/extra",
        "https://pasted.example.invalid/secure/Dashboard.jspa",
        f"https://pasted.example.invalid/browse/{KEY}\ud800",
    ],
)
def test_an_unusable_key_is_rejected_before_any_session_or_request(
    monkeypatch: pytest.MonkeyPatch, argument: str
) -> None:
    def unexpected_session(token: str) -> object:
        raise AssertionError("No session should be created.")

    def unexpected_array(*args: object, **kwargs: object) -> list[object]:
        raise AssertionError("No request should be attempted.")

    monkeypatch.setattr(jira, "bearer_session", unexpected_session)
    monkeypatch.setattr(jira, "get_json_array", unexpected_array)

    with pytest.raises(AtlaWireError, match="issue key"):
        jira.list_issue_remote_links(BASE, argument, token=TOKEN)


@pytest.mark.parametrize(
    "entry",
    [None, [], "text", 7, 1.5, True],
    ids=["null", "array", "text", "integer", "float", "boolean"],
)
def test_a_malformed_late_entry_rejects_the_whole_array(
    monkeypatch: pytest.MonkeyPatch, entry: object
) -> None:
    seen: list[tuple[str, dict[str, str | int]]] = []

    def fake_bearer_session(token: str) -> object:
        return nullcontext(None)

    def fake_get_json_array(
        session: object, url: str, *, params: dict[str, str | int]
    ) -> list[object]:
        seen.append((url, dict(params)))
        return [LINKS[0], entry]

    monkeypatch.setattr(jira, "bearer_session", fake_bearer_session)
    monkeypatch.setattr(jira, "get_json_array", fake_get_json_array)

    with pytest.raises(AtlaWireError, match="remote link objects"):
        jira.list_issue_remote_links(BASE, KEY, token=TOKEN)
    assert seen == [(REMOTE_LINK_PATH, {})]


@pytest.mark.parametrize(
    "base",
    [
        "http://127.0.0.1:8080/jira",
        "https://synthetic-user@jira.example.invalid/jira",
        f"{BASE}?expand=all",
        f"{BASE}#fragment",
    ],
    ids=["http-without-opt-in", "userinfo", "query", "fragment"],
)
def test_an_unsafe_base_url_is_rejected_before_any_session(
    monkeypatch: pytest.MonkeyPatch, base: str
) -> None:
    def unexpected_session(token: str) -> object:
        raise AssertionError("No session should be created.")

    monkeypatch.setattr(jira, "bearer_session", unexpected_session)

    with pytest.raises(AtlaWireError, match="base URL"):
        jira.list_issue_remote_links(base, KEY, token=TOKEN)


def test_http_loopback_is_used_only_when_explicitly_allowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows, seen, _ = read_links(
        monkeypatch, [LINKS[0]], base=LOOPBACK, allow_http_loopback=True
    )

    assert rows == [LINKS[0]]
    assert seen == [(f"{LOOPBACK}/rest/api/2/issue/{KEY}/remotelink", {})]
