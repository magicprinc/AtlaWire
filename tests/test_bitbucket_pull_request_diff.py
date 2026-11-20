from contextlib import nullcontext
from typing import cast

import pytest

from atlawire import bitbucket
from atlawire.http import AtlaWireError

BASE = "https://bitbucket.example.invalid/scm"
TOKEN = "fixture-only-token"
DIFF_URL = f"{BASE}/rest/api/1.0/projects/DEMO/repos/widgets/pull-requests/1/diff"
PARAMS: dict[str, str | int] = {
    "contextLines": 3,
    "whitespace": "ignore-all",
    "withComments": "false",
}
LEVELS = ["root", "file", "hunk", "segment", "line"]


def attempt(
    monkeypatch: pytest.MonkeyPatch,
    body: dict[str, object],
    *,
    context: int = 3,
) -> tuple[
    dict[str, object] | None,
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
        value = bitbucket.get_pull_request_diff(
            BASE, "DEMO/widgets", "1", token=TOKEN, context=context
        )
    except AtlaWireError as error:
        return None, calls, error
    return value, calls, None


def forbidden_session(token: str) -> object:
    raise AssertionError("session created before validation")


def diff_tree() -> tuple[dict[str, object], dict[str, dict[str, object]]]:
    """Build one complete diff and return each node addressable by name."""
    line: dict[str, object] = {"destination": 1, "source": 1, "line": "x"}
    segment: dict[str, object] = {"type": "ADDED", "lines": [line]}
    hunk: dict[str, object] = {"sourceLine": 1, "segments": [segment]}
    diff: dict[str, object] = {"hunks": [hunk]}
    body: dict[str, object] = {"diffs": [diff]}
    nodes = {
        "root": body,
        "file": diff,
        "hunk": hunk,
        "segment": segment,
        "line": line,
    }
    return body, nodes


def flagged(level: str, flag: object) -> dict[str, object]:
    body, nodes = diff_tree()
    nodes[level]["truncated"] = flag
    return body


def test_one_configured_get_returns_the_decoded_object_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = {
        "diffs": [
            {
                "source": {"toString": "src/main.py"},
                "destination": {"toString": "src/main.py"},
                "hunks": [
                    {
                        "sourceLine": 1,
                        "segments": [
                            {
                                "type": "ADDED",
                                "lines": [
                                    {
                                        "destination": 1,
                                        "source": 1,
                                        "line": "import re",
                                        "truncated": False,
                                    }
                                ],
                                "truncated": "false",
                            }
                        ],
                        "truncated": False,
                    }
                ],
                "truncated": "false",
                "extension": {"truncated": True, "nested": [{"truncated": True}]},
            }
        ],
        "truncated": "false",
        "contextLines": "3",
        "extension": {"truncated": True, "payload": "kept"},
    }

    value, calls, error = attempt(monkeypatch, body)

    assert error is None
    assert value is body
    assert calls == [(DIFF_URL, PARAMS)]


@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("flag", [False, "false"], ids=["bool-false", "string-false"])
def test_exact_false_flags_are_accepted_at_every_documented_node(
    monkeypatch: pytest.MonkeyPatch, level: str, flag: object
) -> None:
    body = flagged(level, flag)

    value, calls, error = attempt(monkeypatch, body)

    assert error is None
    assert value is body
    assert calls == [(DIFF_URL, PARAMS)]


@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("flag", [True, "true"], ids=["bool-true", "string-true"])
def test_declared_true_truncation_fails_at_every_documented_node(
    monkeypatch: pytest.MonkeyPatch, level: str, flag: object
) -> None:
    value, calls, error = attempt(monkeypatch, flagged(level, flag))

    assert value is None
    assert calls == [(DIFF_URL, PARAMS)]
    assert error is not None
    assert "truncated" in str(error)
    assert "truncation flag" not in str(error)
    assert TOKEN not in str(error)


@pytest.mark.parametrize(
    ("level", "flag"),
    [
        ("root", None),
        ("root", 0),
        ("root", 1),
        ("root", "True"),
        ("root", "TRUE"),
        ("root", "yes"),
        ("root", ""),
        ("root", []),
        ("root", {}),
        ("file", 1),
        ("line", None),
    ],
    ids=[
        "null",
        "zero",
        "one",
        "capitalized",
        "uppercase",
        "other-word",
        "empty-string",
        "list",
        "object",
        "nested-one",
        "nested-null",
    ],
)
def test_other_present_truncation_flags_are_invalid(
    monkeypatch: pytest.MonkeyPatch, level: str, flag: object
) -> None:
    value, calls, error = attempt(monkeypatch, flagged(level, flag))

    assert value is None
    assert calls == [(DIFF_URL, PARAMS)]
    assert error is not None
    assert "truncation flag" in str(error)
    assert "truncated" not in str(error)


def test_an_empty_diffs_array_is_a_valid_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body: dict[str, object] = {"diffs": [], "truncated": "false"}

    value, calls, error = attempt(monkeypatch, body)

    assert error is None
    assert value is body
    assert calls == [(DIFF_URL, PARAMS)]


@pytest.mark.parametrize(
    "body",
    [
        {"diffs": [{}]},
        {"diffs": [{"hunks": [{}]}]},
        {"diffs": [{"hunks": [{"segments": [{}]}]}]},
        {"diffs": [{"hunks": [{"segments": [{"lines": []}]}]}]},
    ],
    ids=["no-hunks", "no-segments", "no-lines", "empty-lines"],
)
def test_omitted_nested_collections_are_accepted(
    monkeypatch: pytest.MonkeyPatch, body: dict[str, object]
) -> None:
    value, calls, error = attempt(monkeypatch, body)

    assert error is None
    assert value is body
    assert calls == [(DIFF_URL, PARAMS)]


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ({}, "diffs array"),
        ({"diffs": None}, "diffs array"),
        ({"diffs": {}}, "diffs array"),
        ({"diffs": ["x"]}, "diff object"),
        ({"diffs": [{"hunks": {}}]}, "hunks"),
        ({"diffs": [{"hunks": None}]}, "hunks"),
        ({"diffs": [{"hunks": ["x"]}]}, "hunk object"),
        ({"diffs": [{"hunks": [{"segments": {}}]}]}, "segments"),
        ({"diffs": [{"hunks": [{"segments": None}]}]}, "segments"),
        ({"diffs": [{"hunks": [{"segments": ["x"]}]}]}, "segment object"),
        ({"diffs": [{"hunks": [{"segments": [{"lines": {}}]}]}]}, "lines"),
        ({"diffs": [{"hunks": [{"segments": [{"lines": None}]}]}]}, "lines"),
        ({"diffs": [{"hunks": [{"segments": [{"lines": ["x"]}]}]}]}, "line object"),
    ],
)
def test_malformed_truncation_bearing_collections_are_rejected(
    monkeypatch: pytest.MonkeyPatch, body: dict[str, object], expected: str
) -> None:
    value, calls, error = attempt(monkeypatch, body)

    assert value is None
    assert calls == [(DIFF_URL, PARAMS)]
    assert error is not None
    assert expected in str(error)


@pytest.mark.parametrize("context", [0, 100])
def test_context_accepts_the_inclusive_bounds(
    monkeypatch: pytest.MonkeyPatch, context: int
) -> None:
    value, calls, error = attempt(monkeypatch, {"diffs": []}, context=context)

    assert error is None
    assert value == {"diffs": []}
    assert calls == [(DIFF_URL, {**PARAMS, "contextLines": context})]


@pytest.mark.parametrize("context", [-1, 101, True, False, 3.0, "3", None])
def test_invalid_context_is_rejected_before_any_session(
    monkeypatch: pytest.MonkeyPatch, context: object
) -> None:
    monkeypatch.setattr(bitbucket, "bearer_session", forbidden_session)

    with pytest.raises(AtlaWireError, match="diff context"):
        bitbucket.get_pull_request_diff(
            BASE, "DEMO/widgets", "1", token=TOKEN, context=cast(int, context)
        )


@pytest.mark.parametrize(
    ("repo", "pr_id", "expected"),
    [
        ("DEMO", "1", "PROJECT/slug"),
        ("DEMO/widgets/extra", "1", "PROJECT/slug"),
        ("DEMO/widgets", "0", "pull request ID"),
    ],
)
def test_identity_is_rejected_before_any_session(
    monkeypatch: pytest.MonkeyPatch, repo: str, pr_id: str, expected: str
) -> None:
    monkeypatch.setattr(bitbucket, "bearer_session", forbidden_session)

    with pytest.raises(AtlaWireError, match=expected):
        bitbucket.get_pull_request_diff(BASE, repo, pr_id, token=TOKEN)


def test_transport_errors_propagate_without_a_second_request(
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
        bitbucket.get_pull_request_diff(BASE, "DEMO/widgets", "1", token=TOKEN)

    assert calls == [PARAMS]
