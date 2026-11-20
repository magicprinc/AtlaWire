from contextlib import nullcontext
from typing import cast

import pytest

from atlawire import jira
from atlawire.http import AtlaWireError

BASE = "https://jira.example.invalid/jira"


def get_issue(
    monkeypatch: pytest.MonkeyPatch, payload: object
) -> tuple[dict[str, object], list[dict[str, object]]]:
    seen: list[dict[str, object]] = []

    def fake_get_json_object(
        session: object, url: str, *, params: dict[str, str | int]
    ) -> dict[str, object]:
        seen.append({"url": url, **params})
        return cast(dict[str, object], payload)

    monkeypatch.setattr(jira, "bearer_session", lambda token: nullcontext(None))
    monkeypatch.setattr(jira, "get_json_object", fake_get_json_object)
    issue = jira.get_issue(BASE, "DEMO-42", token="fixture-only")
    return issue, seen


@pytest.mark.parametrize("returned_key", ["DEMO-42", "OPS_2-9", "MOVED-7"])
def test_get_issue_accepts_any_syntactically_valid_returned_key(
    monkeypatch: pytest.MonkeyPatch, returned_key: str
) -> None:
    payload = {"key": returned_key, "fields": {"summary": "Summary"}}

    issue, seen = get_issue(monkeypatch, payload)

    assert issue["key"] == returned_key
    assert seen == [
        {
            "url": f"{BASE}/rest/api/2/issue/DEMO-42",
            "expand": "renderedFields",
        }
    ]


@pytest.mark.parametrize(
    "returned_key",
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
        "DEMO-\ud800",
    ],
)
def test_get_issue_rejects_a_blank_or_malformed_returned_key(
    monkeypatch: pytest.MonkeyPatch, returned_key: str
) -> None:
    payload = {"key": returned_key, "fields": {}}

    with pytest.raises(AtlaWireError, match="key and fields"):
        get_issue(monkeypatch, payload)


@pytest.mark.parametrize(
    "payload",
    [
        {"key": "DEMO-42"},
        {"key": "DEMO-42", "fields": []},
        {"key": 42, "fields": {}},
    ],
    ids=["missing-fields", "non-object-fields", "non-text-key"],
)
def test_get_issue_rejects_a_malformed_issue_envelope(
    monkeypatch: pytest.MonkeyPatch, payload: object
) -> None:
    with pytest.raises(AtlaWireError, match="key and fields"):
        get_issue(monkeypatch, payload)
