from contextlib import nullcontext

import pytest

from atlawire import jira
from atlawire.http import AtlaWireError

BASE = "https://jira.example.invalid/jira"


def read_statuses(
    monkeypatch: pytest.MonkeyPatch, values: list[object]
) -> tuple[list[str], list[tuple[str, dict[str, str | int]]]]:
    seen: list[tuple[str, dict[str, str | int]]] = []

    def fake_get_json_array(
        session: object, url: str, *, params: dict[str, str | int]
    ) -> list[object]:
        seen.append((url, dict(params)))
        return values

    monkeypatch.setattr(jira, "bearer_session", lambda token: nullcontext(None))
    monkeypatch.setattr(jira, "get_json_array", fake_get_json_array)
    return jira.list_statuses(BASE, token="fixture-only"), seen


def test_statuses_are_sorted_unique_names_and_extra_fields_are_ignored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values: list[object] = [
        {"name": "Zeta", "id": "9", "extra": {"opaque": True}},
        {"name": "Alpha"},
        {"name": "Zeta"},
        {"name": "Бета", "description": "ignored"},
    ]

    names, seen = read_statuses(monkeypatch, values)

    assert names == ["Alpha", "Zeta", "Бета"]
    assert seen == [(f"{BASE}/rest/api/2/status", {})]


def test_empty_status_list_is_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    names, seen = read_statuses(monkeypatch, [])

    assert names == []
    assert seen == [(f"{BASE}/rest/api/2/status", {})]


@pytest.mark.parametrize(
    "entry",
    [
        {},
        {"name": ""},
        {"name": None},
        {"name": 7},
        {"name": True},
        {"name": "\ud800"},
        {"name": "Open\udfff"},
        "Open",
    ],
)
def test_a_malformed_late_status_entry_rejects_the_whole_list(
    monkeypatch: pytest.MonkeyPatch, entry: object
) -> None:
    with pytest.raises(AtlaWireError, match="Jira status"):
        read_statuses(monkeypatch, [{"name": "Open"}, entry])
