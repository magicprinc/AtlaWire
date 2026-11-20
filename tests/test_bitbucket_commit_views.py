from contextlib import nullcontext

import pytest

from atlawire import bitbucket
from atlawire.http import AtlaWireError

BASE = "https://bitbucket.example.invalid/scm"
TOKEN = "fixture-only-token"
SHA = "a1b2c3d"
CHANGES_URL = f"{BASE}/rest/api/1.0/projects/DEMO/repos/widgets/commits/{SHA}/changes"
DIFF_URL = f"{BASE}/rest/api/1.0/projects/DEMO/repos/widgets/commits/{SHA}/diff"
PARAMS: dict[str, str | int] = {
    "contextLines": 3,
    "whitespace": "ignore-all",
    "withComments": "false",
}


def page(values: list[dict[str, object]], **fields: object) -> dict[str, object]:
    body: dict[str, object] = {
        "values": values,
        "isLastPage": True,
        "limit": 100,
    }
    body.update(fields)
    return body


def diff_payload(path: str) -> dict[str, object]:
    return {
        "diffs": [
            {
                "source": {"toString": path},
                "destination": {"toString": path},
                "hunks": [],
            }
        ]
    }


def stub_json(
    monkeypatch: pytest.MonkeyPatch,
    responses: list[dict[str, object]],
) -> list[tuple[str, dict[str, str | int]]]:
    calls: list[tuple[str, dict[str, str | int]]] = []
    remaining = iter(responses)

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


def test_changes_follow_a_noncontiguous_cursor_with_exact_page_params(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = stub_json(
        monkeypatch,
        [
            page(
                [{"path": "a.py", "type": "MODIFY", "nodeType": "FILE"}],
                isLastPage=False,
                nextPageStart=57,
            ),
            page([{"path": "b.py"}]),
        ],
    )

    rows = bitbucket.list_commit_changes(BASE, "DEMO/widgets", SHA, token=TOKEN)

    assert rows == [
        {"path": "a.py", "type": "MODIFY", "node": "FILE"},
        {"path": "b.py", "type": None, "node": None},
    ]
    assert calls == [
        (CHANGES_URL, {"start": 0, "limit": 100}),
        (CHANGES_URL, {"start": 57, "limit": 100}),
    ]


@pytest.mark.parametrize("flag", [True, "true"], ids=["bool", "string"])
def test_a_declared_true_changes_truncation_fails_without_rows(
    monkeypatch: pytest.MonkeyPatch, flag: object
) -> None:
    calls = stub_json(monkeypatch, [page([{"path": "a.py"}], truncated=flag)])

    with pytest.raises(AtlaWireError, match="truncated"):
        bitbucket.list_commit_changes(BASE, "DEMO/widgets", SHA, token=TOKEN)

    assert calls == [(CHANGES_URL, {"start": 0, "limit": 100})]


@pytest.mark.parametrize("flag", [None, 1, "yes"], ids=["null", "one", "word"])
def test_a_malformed_changes_truncation_flag_is_rejected(
    monkeypatch: pytest.MonkeyPatch, flag: object
) -> None:
    stub_json(monkeypatch, [page([{"path": "a.py"}], truncated=flag)])

    with pytest.raises(AtlaWireError, match="truncation flag"):
        bitbucket.list_commit_changes(BASE, "DEMO/widgets", SHA, token=TOKEN)


def test_a_lone_surrogate_in_an_optional_field_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub_json(monkeypatch, [page([{"path": "ok.py", "type": "\ud800"}])])

    with pytest.raises(AtlaWireError, match="change type"):
        bitbucket.list_commit_changes(BASE, "DEMO/widgets", SHA, token=TOKEN)


def test_the_page_cap_fails_mid_fetch_without_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = stub_json(
        monkeypatch,
        [page([{"path": "a.py"}], isLastPage=False, nextPageStart=57)],
    )

    with pytest.raises(AtlaWireError, match="page limit"):
        bitbucket.list_commit_changes(
            BASE, "DEMO/widgets", SHA, token=TOKEN, max_pages=1
        )

    assert calls == [(CHANGES_URL, {"start": 0, "limit": 100})]


@pytest.mark.parametrize(
    ("sha", "max_pages", "expected"),
    [
        ("main", 100, "commit ID"),
        ("abc123", 100, "commit ID"),
        ("a" * 41, 100, "commit ID"),
        (SHA, 0, "page limit"),
    ],
    ids=["branch", "too-short", "too-long", "page-count"],
)
def test_changes_identity_is_rejected_before_any_session(
    monkeypatch: pytest.MonkeyPatch,
    sha: str,
    max_pages: int,
    expected: str,
) -> None:
    monkeypatch.setattr(bitbucket, "bearer_session", forbidden_session)

    with pytest.raises(AtlaWireError, match=expected):
        bitbucket.list_commit_changes(
            BASE, "DEMO/widgets", sha, token=TOKEN, max_pages=max_pages
        )


def test_whole_diff_returns_one_object_with_exact_fixed_params(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = diff_payload("src/app.py")
    calls = stub_json(monkeypatch, [body])

    value = bitbucket.get_commit_diff(BASE, "DEMO/widgets", SHA, token=TOKEN)

    assert value is body
    assert calls == [(DIFF_URL, PARAMS)]


def test_explicit_paths_return_objects_in_input_order_and_encode_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = diff_payload("src/é +&?.py")
    second = diff_payload("docs/read me#1.md")
    calls = stub_json(monkeypatch, [first, second])

    values = bitbucket.get_commit_diff(
        BASE,
        "DEMO/widgets",
        SHA,
        token=TOKEN,
        paths=("src/é +&?.py", "docs/read me#1.md"),
        context=0,
    )

    assert values == [first, second]
    assert calls == [
        (f"{DIFF_URL}/src/%C3%A9%20%2B%26%3F.py", {**PARAMS, "contextLines": 0}),
        (f"{DIFF_URL}/docs/read%20me%231.md", {**PARAMS, "contextLines": 0}),
    ]


def test_one_explicit_path_returns_a_list_not_an_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = diff_payload("src/app.py")
    stub_json(monkeypatch, [body])

    values = bitbucket.get_commit_diff(
        BASE, "DEMO/widgets", SHA, token=TOKEN, paths=("src/app.py",)
    )

    assert values == [body]


@pytest.mark.parametrize(
    "paths",
    [
        ("src/ok.py", "../secret"),
        ("src/ok.py", "src//empty.py"),
        ("src/ok.py", "src/%2e%2e/x.py"),
        tuple(f"src/file{index}.py" for index in range(101)),
    ],
    ids=["parent", "empty-segment", "percent-escape", "over-cap"],
)
def test_every_explicit_path_is_validated_before_any_session(
    monkeypatch: pytest.MonkeyPatch, paths: tuple[str, ...]
) -> None:
    monkeypatch.setattr(bitbucket, "bearer_session", forbidden_session)

    with pytest.raises(AtlaWireError):
        bitbucket.get_commit_diff(BASE, "DEMO/widgets", SHA, token=TOKEN, paths=paths)


def test_nested_truncation_on_a_later_path_fails_after_both_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    second = diff_payload("src/second.py")
    diffs = second["diffs"]
    assert isinstance(diffs, list)
    diff = diffs[0]
    assert isinstance(diff, dict)
    diff["truncated"] = "true"
    calls = stub_json(monkeypatch, [diff_payload("src/first.py"), second])

    with pytest.raises(AtlaWireError, match="truncated"):
        bitbucket.get_commit_diff(
            BASE,
            "DEMO/widgets",
            SHA,
            token=TOKEN,
            paths=("src/first.py", "src/second.py"),
        )

    assert calls == [
        (f"{DIFF_URL}/src/first.py", PARAMS),
        (f"{DIFF_URL}/src/second.py", PARAMS),
    ]


@pytest.mark.parametrize(
    "context",
    [True, -1, 101, "3"],
    ids=["bool", "below-range", "above-range", "string"],
)
def test_the_diff_context_is_rejected_before_any_session(
    monkeypatch: pytest.MonkeyPatch, context: object
) -> None:
    monkeypatch.setattr(bitbucket, "bearer_session", forbidden_session)

    with pytest.raises(AtlaWireError, match="diff context"):
        bitbucket.get_commit_diff(
            BASE,
            "DEMO/widgets",
            SHA,
            token=TOKEN,
            context=context,  # type: ignore[arg-type]
        )
