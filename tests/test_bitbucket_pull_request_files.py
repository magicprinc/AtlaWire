from contextlib import nullcontext

import pytest

from atlawire import bitbucket
from atlawire.http import AtlaWireError

BASE = "https://bitbucket.example.invalid/scm"
TOKEN = "fixture-only-token"
CHANGES_URL = f"{BASE}/rest/api/1.0/projects/DEMO/repos/widgets/pull-requests/1/changes"


def page(values: object, **fields: object) -> dict[str, object]:
    body: dict[str, object] = {
        "values": values,
        "isLastPage": True,
        "limit": 1000,
    }
    body.update(fields)
    return body


def attempt(
    monkeypatch: pytest.MonkeyPatch,
    body: dict[str, object],
    *,
    repo: str = "DEMO/widgets",
    pr_id: str | int = "1",
) -> tuple[
    list[bitbucket.PullRequestFile] | None,
    list[tuple[str, dict[str, str | int]]],
    AtlaWireError | None,
]:
    calls: list[tuple[str, dict[str, str | int]]] = []

    def fake_get_json_object(
        session: object, url: str, *, params: dict[str, str | int]
    ) -> dict[str, object]:
        calls.append((url, dict(params)))
        return body

    monkeypatch.setattr(bitbucket, "bearer_session", lambda token: nullcontext(None))
    monkeypatch.setattr(bitbucket, "get_json_object", fake_get_json_object)
    try:
        rows = bitbucket.list_pull_request_files(BASE, repo, pr_id, token=TOKEN)
    except AtlaWireError as error:
        return None, calls, error
    return rows, calls, None


def forbidden_session(token: str) -> object:
    raise AssertionError("session created before validation")


def test_one_configured_get_projects_rows_in_server_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = page(
        [
            {
                "path": {
                    "toString": "src/main.py",
                    "components": ["unused"],
                    "name": "main.py",
                },
                "type": "MODIFY",
                "nodeType": "FILE",
            },
            {"path": "README.md", "type": "ADD", "nodeType": "DIRECTORY"},
            {"path": {"name": "basename-only.txt"}},
        ],
        size=3,
        start=0,
        truncated=False,
    )

    rows, calls, error = attempt(monkeypatch, body)

    assert error is None
    assert rows == [
        {"path": "src/main.py", "type": "MODIFY", "node": "FILE"},
        {"path": "README.md", "type": "ADD", "node": "DIRECTORY"},
        {"path": "basename-only.txt", "type": None, "node": None},
    ]
    assert calls == [(CHANGES_URL, {"limit": 1000})]


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("src/main.py", "src/main.py"),
        (
            {"toString": "a/b.txt", "components": ["ignored"], "name": "b.txt"},
            "a/b.txt",
        ),
        (
            {"toString": None, "components": ["a", "b.txt"], "name": "b.txt"},
            "a/b.txt",
        ),
        ({"toString": "", "components": ["a", "b.txt"], "name": "b.txt"}, "a/b.txt"),
        ({"name": "b.txt"}, "b.txt"),
        ({"toString": "", "name": "b.txt"}, "b.txt"),
        ({"toString": None, "components": None, "name": "b.txt"}, "b.txt"),
    ],
    ids=[
        "plain-string",
        "full-path-wins",
        "components-without-full-path",
        "empty-full-path-falls-through",
        "basename-only",
        "empty-full-path-and-name",
        "null-metadata-and-name",
    ],
)
def test_path_representation_priority(
    monkeypatch: pytest.MonkeyPatch, path: object, expected: str
) -> None:
    rows, _calls, error = attempt(monkeypatch, page([{"path": path}]))

    assert error is None
    assert rows == [{"path": expected, "type": None, "node": None}]


def test_nullable_type_and_node_are_preserved_verbatim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = page(
        [
            {"path": "a", "type": None, "nodeType": None},
            {"path": "b", "type": "MOVE", "nodeType": "FILE"},
            {"path": "c", "type": "", "nodeType": ""},
        ]
    )

    rows, _calls, error = attempt(monkeypatch, body)

    assert error is None
    assert rows == [
        {"path": "a", "type": None, "node": None},
        {"path": "b", "type": "MOVE", "node": "FILE"},
        {"path": "c", "type": "", "node": ""},
    ]


def test_an_empty_terminal_page_is_a_valid_empty_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows, calls, error = attempt(monkeypatch, page([], size=0, start=0))

    assert error is None
    assert rows == []
    assert calls == [(CHANGES_URL, {"limit": 1000})]


def test_next_page_start_is_ignored_and_never_followed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = page([{"path": "a"}], nextPageStart=1, start=0, size=1)

    rows, calls, error = attempt(monkeypatch, body)

    assert error is None
    assert rows == [{"path": "a", "type": None, "node": None}]
    assert calls == [(CHANGES_URL, {"limit": 1000})]


@pytest.mark.parametrize(
    ("values", "limit", "accepted"),
    [
        ([{"path": "a"}], 1, False),
        ([{"path": "a"}, {"path": "b"}], 2, False),
        ([{"path": "a"}, {"path": "b"}], 3, True),
        ([{"path": "a"}], 2, True),
        ([], 1, True),
    ],
    ids=["equal-one", "equal-two", "below", "one-below", "empty"],
)
def test_reported_limit_is_checked_against_the_row_count(
    monkeypatch: pytest.MonkeyPatch,
    values: list[dict[str, object]],
    limit: int,
    accepted: bool,
) -> None:
    rows, calls, error = attempt(monkeypatch, page(values, limit=limit))

    assert calls == [(CHANGES_URL, {"limit": 1000})]
    if accepted:
        assert error is None
        assert rows is not None
        assert len(rows) == len(values)
    else:
        assert error is not None
        assert "reported limit" in str(error)
        assert rows is None


def test_server_reported_limit_not_the_requested_one_controls_the_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows, calls, error = attempt(
        monkeypatch, page([{"path": "a"}], limit=1, isLastPage=True)
    )

    assert calls == [(CHANGES_URL, {"limit": 1000})]
    assert rows is None
    assert error is not None
    assert "reported limit" in str(error)


def test_explicit_truncation_is_distinct_from_a_capped_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows, calls, error = attempt(monkeypatch, page([{"path": "a"}], truncated=True))

    assert rows is None
    assert calls == [(CHANGES_URL, {"limit": 1000})]
    assert error is not None
    assert "reported truncated" in str(error)
    assert "reported limit" not in str(error)


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("", "path"),
        (None, "path"),
        (7, "path"),
        (True, "path"),
        ([], "path"),
        ({}, "path"),
        ({"toString": 7}, "path"),
        ({"toString": False}, "path"),
        ({"components": {}}, "path"),
        ({"components": []}, "path"),
        ({"components": ["a", 1]}, "path"),
        ({"components": ["a", ""]}, "path"),
        ({"components": [""]}, "path"),
        ({"components": None, "name": None}, "path"),
        ({"components": [], "name": "fallback"}, "path"),
        ({"name": 7}, "path"),
        ({"name": ""}, "path"),
        ({"name": None}, "path"),
    ],
)
def test_malformed_paths_are_rejected_without_coercion(
    monkeypatch: pytest.MonkeyPatch, path: object, expected: str
) -> None:
    rows, _calls, error = attempt(monkeypatch, page([{"path": path}]))

    assert rows is None
    assert error is not None
    assert expected in str(error)


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("type", 7, "Invalid fields"),
        ("type", [], "Invalid fields"),
        ("nodeType", 7, "Invalid fields"),
        ("nodeType", {"x": 1}, "Invalid fields"),
    ],
)
def test_malformed_projected_fields_are_rejected(
    monkeypatch: pytest.MonkeyPatch, field: str, value: object, expected: str
) -> None:
    rows, _calls, error = attempt(monkeypatch, page([{"path": "a", field: value}]))

    assert rows is None
    assert error is not None
    assert expected in str(error)


def test_non_object_change_entries_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows, _calls, error = attempt(monkeypatch, page([{"path": "a"}, "b"]))

    assert rows is None
    assert error is not None
    assert "change object" in str(error)


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ({}, "values array"),
        ({"values": None, "isLastPage": True, "limit": 1000}, "values array"),
        ({"values": {}, "isLastPage": True, "limit": 1000}, "values array"),
        ({"values": [], "limit": 1000}, "terminal"),
        ({"values": [], "isLastPage": False, "limit": 1000}, "terminal"),
        ({"values": [], "isLastPage": 1, "limit": 1000}, "terminal"),
        ({"values": [], "isLastPage": "true", "limit": 1000}, "terminal"),
        ({"values": [], "isLastPage": None, "limit": 1000}, "terminal"),
        ({"values": [], "isLastPage": True}, "limit"),
        ({"values": [], "isLastPage": True, "limit": 0}, "limit"),
        ({"values": [], "isLastPage": True, "limit": 1001}, "limit"),
        ({"values": [], "isLastPage": True, "limit": True}, "limit"),
        ({"values": [], "isLastPage": True, "limit": "1000"}, "limit"),
        ({"values": [], "isLastPage": True, "limit": 1000.0}, "limit"),
        ({"values": [], "isLastPage": True, "limit": None}, "limit"),
        (
            {"values": [{"path": "a"}], "isLastPage": True, "limit": 1000, "size": 2},
            "size",
        ),
        (
            {"values": [{"path": "a"}], "isLastPage": True, "limit": 1000, "size": 0},
            "size",
        ),
        (
            {
                "values": [{"path": "a"}],
                "isLastPage": True,
                "limit": 1000,
                "size": True,
            },
            "size",
        ),
        (
            {
                "values": [{"path": "a"}],
                "isLastPage": True,
                "limit": 1000,
                "size": "1",
            },
            "size",
        ),
        (
            {
                "values": [{"path": "a"}],
                "isLastPage": True,
                "limit": 1000,
                "size": None,
            },
            "size",
        ),
        (
            {"values": [], "isLastPage": True, "limit": 1000, "start": 1},
            "start",
        ),
        (
            {"values": [], "isLastPage": True, "limit": 1000, "start": -1},
            "start",
        ),
        (
            {"values": [], "isLastPage": True, "limit": 1000, "start": False},
            "start",
        ),
        (
            {"values": [], "isLastPage": True, "limit": 1000, "start": "0"},
            "start",
        ),
        (
            {"values": [], "isLastPage": True, "limit": 1000, "start": None},
            "start",
        ),
        (
            {
                "values": [],
                "isLastPage": True,
                "limit": 1000,
                "truncated": "true",
            },
            "truncation flag",
        ),
        (
            {"values": [], "isLastPage": True, "limit": 1000, "truncated": 1},
            "truncation flag",
        ),
        (
            {"values": [], "isLastPage": True, "limit": 1000, "truncated": None},
            "truncation flag",
        ),
    ],
)
def test_malformed_envelopes_are_rejected(
    monkeypatch: pytest.MonkeyPatch, body: dict[str, object], expected: str
) -> None:
    rows, _calls, error = attempt(monkeypatch, body)

    assert rows is None
    assert error is not None
    assert expected in str(error)


@pytest.mark.parametrize(
    ("repo", "pr_id", "expected"),
    [
        ("DEMO", "1", "PROJECT/slug"),
        ("DEMO/widgets/extra", "1", "PROJECT/slug"),
        ("../widgets", "1", "PROJECT/slug"),
        ("DEMO/widgets", "0", "pull request ID"),
        ("DEMO/widgets", "01", "pull request ID"),
        ("DEMO/widgets", "1\n", "pull request ID"),
        ("DEMO/widgets", 2**63, "pull request ID"),
    ],
)
def test_identity_is_rejected_before_any_session(
    monkeypatch: pytest.MonkeyPatch,
    repo: str,
    pr_id: str | int,
    expected: str,
) -> None:
    monkeypatch.setattr(bitbucket, "bearer_session", forbidden_session)

    with pytest.raises(AtlaWireError, match=expected):
        bitbucket.list_pull_request_files(BASE, repo, pr_id, token=TOKEN)


def test_transport_errors_propagate_without_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, str | int]] = []

    def failing_get_json_object(
        session: object, url: str, *, params: dict[str, str | int]
    ) -> dict[str, object]:
        calls.append(dict(params))
        raise AtlaWireError("HTTP 500: request failed.")

    monkeypatch.setattr(bitbucket, "bearer_session", lambda token: nullcontext(None))
    monkeypatch.setattr(bitbucket, "get_json_object", failing_get_json_object)

    with pytest.raises(AtlaWireError, match="HTTP 500"):
        bitbucket.list_pull_request_files(BASE, "DEMO/widgets", "1", token=TOKEN)

    assert calls == [{"limit": 1000}]
