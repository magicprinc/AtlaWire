"""Unit tests for the all-or-nothing pull request diff fallback."""

import json
from contextlib import nullcontext

import pytest

from atlawire import bitbucket
from atlawire.http import AtlaWireError

BASE = "https://bitbucket.example.invalid/scm"
TOKEN = "fixture-only-token"
REPO = "DEMO/widgets"
PR_ID = "7"
DIFF_URL = f"{BASE}/rest/api/1.0/projects/DEMO/repos/widgets/pull-requests/7/diff"
CHANGES_URL = (
    f"{BASE}/rest/api/1.0/projects/DEMO/repos/widgets/pull-requests/7/changes"
)
PARAMS: dict[str, str | int] = {
    "contextLines": 3,
    "whitespace": "ignore-all",
    "withComments": "false",
}
CHANGES_PARAMS = {"limit": 1000}
FILE_A = "src/é +&?.py"
FILE_A_URL = f"{DIFF_URL}/src/%C3%A9%20%2B%26%3F.py"
FILE_B = "docs/read me.md"
FILE_B_URL = f"{DIFF_URL}/docs/read%20me.md"


def file_diff(path: str, *, truncated: object = False) -> dict[str, object]:
    return {
        "diffs": [
            {
                "source": {"toString": path},
                "destination": {"toString": path},
                "hunks": [],
            }
        ],
        "truncated": truncated,
    }


def whole_diff(*, truncated: object = False) -> dict[str, object]:
    return file_diff("src/a.py", truncated=truncated)


def nested_truncated_diff() -> dict[str, object]:
    body = file_diff("src/a.py")
    diffs = body["diffs"]
    assert isinstance(diffs, list)
    diff = diffs[0]
    assert isinstance(diff, dict)
    diff["truncated"] = True
    return body


def change(
    path: str,
    *,
    change_type: str = "MODIFY",
    source_path: object = None,
) -> dict[str, object]:
    row: dict[str, object] = {
        "path": path,
        "type": change_type,
        "nodeType": "FILE",
    }
    if source_path is not None:
        row["srcPath"] = source_path
    return row


def changes_page(
    rows: list[object],
    *,
    limit: int = 1000,
    is_last: bool = True,
    truncated: object = None,
) -> dict[str, object]:
    body: dict[str, object] = {
        "values": rows,
        "size": len(rows),
        "limit": limit,
        "start": 0,
        "isLastPage": is_last,
    }
    if truncated is not None:
        body["truncated"] = truncated
    return body


def stub_routes(
    monkeypatch: pytest.MonkeyPatch,
    routes: dict[str, dict[str, object] | Exception],
) -> list[tuple[str, dict[str, str | int]]]:
    calls: list[tuple[str, dict[str, str | int]]] = []

    def fake_get_json_object(
        session: object, url: str, *, params: dict[str, str | int]
    ) -> dict[str, object]:
        calls.append((url, dict(params)))
        result = routes.get(url)
        if result is None:
            raise AssertionError(f"Unexpected request: {url}")
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(bitbucket, "bearer_session", lambda token: nullcontext(None))
    monkeypatch.setattr(bitbucket, "get_json_object", fake_get_json_object)
    return calls


def call_fallback() -> bitbucket.PullRequestDiffFallback:
    return bitbucket.get_pull_request_diff_with_fallback(
        BASE, REPO, PR_ID, token=TOKEN
    )


def test_a_complete_whole_diff_is_returned_without_any_follow_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = whole_diff()
    calls = stub_routes(monkeypatch, {DIFF_URL: body})

    result = call_fallback()

    assert result == {
        "fallback": False,
        "fallback_reason": None,
        "diff": body,
        "files": [],
    }
    assert result["diff"] is body
    assert calls == [(DIFF_URL, PARAMS)]


def test_declared_whole_diff_truncation_recovers_each_changed_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = file_diff(FILE_A)
    second = file_diff(FILE_B)
    calls = stub_routes(
        monkeypatch,
        {
            DIFF_URL: whole_diff(truncated=True),
            CHANGES_URL: changes_page(
                [change(FILE_A, change_type="MODIFY"), change(FILE_B)]
            ),
            FILE_A_URL: first,
            FILE_B_URL: second,
        },
    )

    result = call_fallback()

    assert result == {
        "fallback": True,
        "fallback_reason": "Bitbucket reported a truncated pull request diff.",
        "diff": None,
        "files": [
            {"path": FILE_A, "source_path": None, "diff": first},
            {"path": FILE_B, "source_path": None, "diff": second},
        ],
    }
    files = result["files"]
    assert files[0]["diff"] is first
    assert files[1]["diff"] is second
    assert calls == [
        (DIFF_URL, PARAMS),
        (CHANGES_URL, CHANGES_PARAMS),
        (FILE_A_URL, PARAMS),
        (FILE_B_URL, PARAMS),
    ]


def test_nested_declared_truncation_also_selects_the_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = file_diff(FILE_A)
    calls = stub_routes(
        monkeypatch,
        {
            DIFF_URL: nested_truncated_diff(),
            CHANGES_URL: changes_page([change(FILE_A)]),
            FILE_A_URL: body,
        },
    )

    result = call_fallback()

    assert result["fallback"] is True
    assert result["diff"] is None
    assert result["files"] == [
        {"path": FILE_A, "source_path": None, "diff": body}
    ]
    assert calls == [
        (DIFF_URL, PARAMS),
        (CHANGES_URL, CHANGES_PARAMS),
        (FILE_A_URL, PARAMS),
    ]


def test_a_malformed_whole_diff_flag_does_not_trigger_the_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = stub_routes(
        monkeypatch, {DIFF_URL: whole_diff(truncated="yes")}
    )

    with pytest.raises(AtlaWireError, match="truncation flag") as error:
        call_fallback()

    assert not isinstance(error.value, bitbucket.DeclaredTruncationError)
    assert calls == [(DIFF_URL, PARAMS)]


def test_a_malformed_diffs_shape_takes_precedence_over_root_truncation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = stub_routes(
        monkeypatch,
        {DIFF_URL: {"truncated": True, "diffs": "not-an-array"}},
    )

    with pytest.raises(AtlaWireError, match="diffs array") as error:
        call_fallback()

    assert not isinstance(error.value, bitbucket.DeclaredTruncationError)
    assert calls == [(DIFF_URL, PARAMS)]


def test_a_later_malformed_flag_takes_precedence_over_an_earlier_true_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = stub_routes(
        monkeypatch,
        {
            DIFF_URL: {
                "truncated": False,
                "diffs": [
                    {"truncated": True},
                    {"truncated": "yes"},
                ],
            }
        },
    )

    with pytest.raises(AtlaWireError, match="truncation flag") as error:
        call_fallback()

    assert not isinstance(error.value, bitbucket.DeclaredTruncationError)
    assert calls == [(DIFF_URL, PARAMS)]


@pytest.mark.parametrize(
    "failure",
    [
        AtlaWireError("HTTP 401: authentication rejected."),
        AtlaWireError("Request timed out."),
    ],
    ids=["auth", "timeout"],
)
def test_whole_diff_auth_or_transport_failure_does_not_fall_back(
    monkeypatch: pytest.MonkeyPatch, failure: AtlaWireError
) -> None:
    calls = stub_routes(monkeypatch, {DIFF_URL: failure})

    with pytest.raises(AtlaWireError) as error:
        call_fallback()

    assert error.value is failure
    assert calls == [(DIFF_URL, PARAMS)]


def test_a_capped_changes_page_fails_before_any_per_file_diff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = stub_routes(
        monkeypatch,
        {
            DIFF_URL: whole_diff(truncated=True),
            CHANGES_URL: changes_page(
                [change(FILE_A), change(FILE_B)], limit=2
            ),
        },
    )

    with pytest.raises(AtlaWireError, match="reported limit"):
        call_fallback()

    assert calls == [
        (DIFF_URL, PARAMS),
        (CHANGES_URL, CHANGES_PARAMS),
    ]


def test_an_empty_changes_page_cannot_recover_a_truncated_whole_diff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = stub_routes(
        monkeypatch,
        {
            DIFF_URL: whole_diff(truncated=True),
            CHANGES_URL: changes_page([]),
        },
    )

    with pytest.raises(AtlaWireError, match="empty changes page") as error:
        call_fallback()

    assert str(error.value) == (
        "A truncated pull request diff cannot be recovered from "
        "an empty changes page."
    )
    assert calls == [
        (DIFF_URL, PARAMS),
        (CHANGES_URL, CHANGES_PARAMS),
    ]


def test_a_declared_truncated_changes_page_fails_without_file_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = stub_routes(
        monkeypatch,
        {
            DIFF_URL: whole_diff(truncated=True),
            CHANGES_URL: changes_page(
                [change(FILE_A)], truncated=True
            ),
        },
    )

    with pytest.raises(AtlaWireError, match="truncated pull request changes"):
        call_fallback()

    assert calls == [
        (DIFF_URL, PARAMS),
        (CHANGES_URL, CHANGES_PARAMS),
    ]


def test_a_nonterminal_changes_page_fails_without_file_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = stub_routes(
        monkeypatch,
        {
            DIFF_URL: whole_diff(truncated=True),
            CHANGES_URL: changes_page([change(FILE_A)], is_last=False),
        },
    )

    with pytest.raises(AtlaWireError, match="terminal"):
        call_fallback()

    assert calls == [
        (DIFF_URL, PARAMS),
        (CHANGES_URL, CHANGES_PARAMS),
    ]


@pytest.mark.parametrize(
    "row",
    ["not-an-object", 7, None, []],
    ids=["string", "number", "null", "array"],
)
def test_a_malformed_changes_row_fails_without_file_requests(
    monkeypatch: pytest.MonkeyPatch, row: object
) -> None:
    calls = stub_routes(
        monkeypatch,
        {
            DIFF_URL: whole_diff(truncated=True),
            CHANGES_URL: changes_page([change(FILE_A), row]),
        },
    )

    with pytest.raises(AtlaWireError, match="change object"):
        call_fallback()

    assert calls == [
        (DIFF_URL, PARAMS),
        (CHANGES_URL, CHANGES_PARAMS),
    ]


def test_a_failed_changes_page_propagates_without_file_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = stub_routes(
        monkeypatch,
        {
            DIFF_URL: whole_diff(truncated=True),
            CHANGES_URL: AtlaWireError("HTTP 503: request failed."),
        },
    )

    with pytest.raises(AtlaWireError, match="HTTP 503"):
        call_fallback()

    assert calls == [
        (DIFF_URL, PARAMS),
        (CHANGES_URL, CHANGES_PARAMS),
    ]


def test_duplicate_change_paths_fail_before_any_per_file_diff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = stub_routes(
        monkeypatch,
        {
            DIFF_URL: whole_diff(truncated=True),
            CHANGES_URL: changes_page(
                [change(FILE_A), change(FILE_A)]
            ),
        },
    )

    with pytest.raises(AtlaWireError, match="Duplicate path"):
        call_fallback()

    assert calls == [
        (DIFF_URL, PARAMS),
        (CHANGES_URL, CHANGES_PARAMS),
    ]


@pytest.mark.parametrize(
    "change_type",
    ["MOVE", "COPY", "RENAME"],
    ids=["move", "copy", "rename"],
)
def test_a_renamed_change_without_a_source_path_fails_before_file_requests(
    monkeypatch: pytest.MonkeyPatch, change_type: str
) -> None:
    calls = stub_routes(
        monkeypatch,
        {
            DIFF_URL: whole_diff(truncated=True),
            CHANGES_URL: changes_page(
                [change(FILE_A, change_type=change_type)]
            ),
        },
    )

    with pytest.raises(AtlaWireError, match="source path"):
        call_fallback()

    assert calls == [
        (DIFF_URL, PARAMS),
        (CHANGES_URL, CHANGES_PARAMS),
    ]


def test_a_moved_file_sends_its_validated_source_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = file_diff(FILE_A)
    calls = stub_routes(
        monkeypatch,
        {
            DIFF_URL: whole_diff(truncated=True),
            CHANGES_URL: changes_page(
                [
                    change(
                        FILE_A,
                        change_type="MOVE",
                        source_path={
                            "toString": "old/name.py",
                            "components": ["old", "name.py"],
                            "name": "name.py",
                        },
                    )
                ]
            ),
            FILE_A_URL: body,
        },
    )

    result = call_fallback()

    assert result["files"] == [
        {"path": FILE_A, "source_path": "old/name.py", "diff": body}
    ]
    assert calls == [
        (DIFF_URL, PARAMS),
        (CHANGES_URL, CHANGES_PARAMS),
        (FILE_A_URL, {**PARAMS, "srcPath": "old/name.py"}),
    ]


def test_an_unsafe_source_path_fails_before_any_per_file_diff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = stub_routes(
        monkeypatch,
        {
            DIFF_URL: whole_diff(truncated=True),
            CHANGES_URL: changes_page(
                [
                    change(
                        FILE_A,
                        change_type="MOVE",
                        source_path="../old/name.py",
                    )
                ]
            ),
        },
    )

    with pytest.raises(AtlaWireError, match="relative file path"):
        call_fallback()

    assert calls == [
        (DIFF_URL, PARAMS),
        (CHANGES_URL, CHANGES_PARAMS),
    ]


def test_the_aggregate_retained_output_limit_rejects_valid_small_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = file_diff(FILE_A)
    second = file_diff(FILE_B)
    first_size = len(json.dumps(first, separators=(",", ":")))
    second_size = len(json.dumps(second, separators=(",", ":")))
    limit = max(first_size, second_size) + 1
    assert first_size <= limit
    assert second_size <= limit
    assert first_size + second_size > limit
    monkeypatch.setattr(bitbucket, "_DIFF_FALLBACK_RETAINED_LIMIT", limit)
    calls = stub_routes(
        monkeypatch,
        {
            DIFF_URL: whole_diff(truncated=True),
            CHANGES_URL: changes_page([change(FILE_A), change(FILE_B)]),
            FILE_A_URL: first,
            FILE_B_URL: second,
        },
    )

    with pytest.raises(AtlaWireError, match="retained-output limit") as error:
        call_fallback()

    assert not isinstance(error.value, bitbucket.DeclaredTruncationError)
    assert calls == [
        (DIFF_URL, PARAMS),
        (CHANGES_URL, CHANGES_PARAMS),
        (FILE_A_URL, PARAMS),
        (FILE_B_URL, PARAMS),
    ]


def test_a_later_failed_file_diff_aborts_without_a_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failure = AtlaWireError("HTTP 500: request failed.")
    calls = stub_routes(
        monkeypatch,
        {
            DIFF_URL: whole_diff(truncated=True),
            CHANGES_URL: changes_page([change(FILE_A), change(FILE_B)]),
            FILE_A_URL: file_diff(FILE_A),
            FILE_B_URL: failure,
        },
    )

    with pytest.raises(AtlaWireError) as error:
        call_fallback()

    assert error.value is failure
    assert calls == [
        (DIFF_URL, PARAMS),
        (CHANGES_URL, CHANGES_PARAMS),
        (FILE_A_URL, PARAMS),
        (FILE_B_URL, PARAMS),
    ]


def test_a_later_truncated_file_diff_aborts_without_a_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = stub_routes(
        monkeypatch,
        {
            DIFF_URL: whole_diff(truncated=True),
            CHANGES_URL: changes_page([change(FILE_A), change(FILE_B)]),
            FILE_A_URL: file_diff(FILE_A),
            FILE_B_URL: file_diff(FILE_B, truncated=True),
        },
    )

    with pytest.raises(bitbucket.DeclaredTruncationError):
        call_fallback()

    assert calls == [
        (DIFF_URL, PARAMS),
        (CHANGES_URL, CHANGES_PARAMS),
        (FILE_A_URL, PARAMS),
        (FILE_B_URL, PARAMS),
    ]


def test_declared_truncation_keeps_the_existing_error_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = stub_routes(
        monkeypatch, {DIFF_URL: whole_diff(truncated=True)}
    )

    with pytest.raises(AtlaWireError) as error:
        bitbucket.get_pull_request_diff(BASE, REPO, PR_ID, token=TOKEN)

    assert isinstance(error.value, bitbucket.DeclaredTruncationError)
    assert issubclass(
        bitbucket.DeclaredTruncationError, AtlaWireError
    )
    assert str(error.value) == (
        "Bitbucket reported a truncated pull request diff."
    )
    assert calls == [(DIFF_URL, PARAMS)]
