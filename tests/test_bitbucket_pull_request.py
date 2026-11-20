from contextlib import nullcontext
from typing import cast

import pytest

from atlawire import bitbucket
from atlawire.http import AtlaWireError

BASE = "https://bitbucket.example.invalid/scm"
TOKEN = "fixture-only-token"
INVALID_ID = "Expected a pull request ID"
INVALID_REPO = "PROJECT/slug"


def pull_request(pr_id: int = 1) -> dict[str, object]:
    return {
        "id": pr_id,
        "version": 1,
        "title": "Talking Nerdy",
        "description": None,
        "state": "OPEN",
        "fromRef": {
            "id": "refs/heads/feature-ABC-123",
            "repository": {
                "slug": "fork",
                "name": None,
                "project": {"key": "OPS"},
            },
        },
        "extension": {"nested": [None, "α", True]},
    }


def read(
    monkeypatch: pytest.MonkeyPatch,
    *,
    repo: str = "DEMO/widgets",
    pr_id: str | int = "1",
    body: dict[str, object] | None = None,
) -> tuple[dict[str, object], list[tuple[str, dict[str, object]]]]:
    calls: list[tuple[str, dict[str, object]]] = []
    response = pull_request() if body is None else body

    def fake_get_json_object(
        session: object, url: str, *, params: dict[str, str | int]
    ) -> dict[str, object]:
        calls.append((url, dict(params)))
        return response

    monkeypatch.setattr(bitbucket, "bearer_session", lambda token: nullcontext(None))
    monkeypatch.setattr(bitbucket, "get_json_object", fake_get_json_object)
    return bitbucket.get_pull_request(BASE, repo, pr_id, token=TOKEN), calls


def forbidden_session(token: str) -> object:
    raise AssertionError("session created before validation")


def test_one_get_and_the_server_object_are_returned_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = pull_request()

    result, calls = read(monkeypatch, body=body)

    assert result is body
    assert calls == [
        (
            f"{BASE}/rest/api/1.0/projects/DEMO/repos/widgets/pull-requests/1",
            {},
        )
    ]


@pytest.mark.parametrize(
    ("pr_id", "expected"),
    [
        ("1", 1),
        (1, 1),
        ("7", 7),
        ("9223372036854775807", 2**63 - 1),
        (2**63 - 1, 2**63 - 1),
    ],
    ids=["string", "int", "other", "max-string", "max-int"],
)
def test_positive_ids_are_canonicalised_into_the_single_request(
    monkeypatch: pytest.MonkeyPatch, pr_id: str | int, expected: int
) -> None:
    result, calls = read(monkeypatch, pr_id=pr_id, body=pull_request(expected))

    assert result["id"] == expected
    assert calls == [
        (
            (
                f"{BASE}/rest/api/1.0/projects/DEMO/repos/widgets"
                f"/pull-requests/{expected}"
            ),
            {},
        )
    ]


def test_personal_project_is_a_valid_repo_segment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, calls = read(monkeypatch, repo="~user/widgets")

    assert calls[0][0] == (
        f"{BASE}/rest/api/1.0/projects/~user/repos/widgets/pull-requests/1"
    )


def test_minimal_response_with_a_new_state_is_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body: dict[str, object] = {"id": 1, "title": "", "state": "FUTURE_STATE"}

    result, _ = read(monkeypatch, body=body)

    assert result is body


@pytest.mark.parametrize(
    "repo",
    [
        "DEMO",
        "",
        "DEMO/",
        "/widgets",
        "DEMO/widgets/extra",
        "DEMO/.",
        "DEMO/..",
        "../widgets",
        "./widgets",
        "DEMO/wid gets",
        "DEMO/wídgets",
        "DEMO/wid%2Fgets",
        "DEMO\\widgets",
        "https://example.invalid/DEMO/widgets",
        "DEMO!/widgets",
        "DEMO/widgets?x=1",
        "DEMO/widgets#frag",
    ],
)
def test_repo_must_be_exactly_project_and_slug(
    monkeypatch: pytest.MonkeyPatch, repo: str
) -> None:
    monkeypatch.setattr(bitbucket, "bearer_session", forbidden_session)

    with pytest.raises(AtlaWireError, match=INVALID_REPO) as error:
        bitbucket.get_pull_request(BASE, repo, "1", token=TOKEN)

    if repo:
        assert repo not in str(error.value)


@pytest.mark.parametrize(
    "pr_id",
    [
        "",
        "0",
        "00",
        "01",
        "+1",
        "-1",
        " 1",
        "1 ",
        "1\n",
        "١",
        "１２",
        "1.0",
        "9223372036854775808",
        "1" * 20,
        "1" * 5000,
        True,
        False,
        0,
        -1,
        2**63,
        1.0,
        None,
    ],
)
def test_invalid_ids_are_rejected_before_any_session(
    monkeypatch: pytest.MonkeyPatch, pr_id: object
) -> None:
    monkeypatch.setattr(bitbucket, "bearer_session", forbidden_session)

    with pytest.raises(AtlaWireError, match=INVALID_ID):
        bitbucket.get_pull_request(
            BASE, "DEMO/widgets", cast(str | int, pr_id), token=TOKEN
        )


@pytest.mark.parametrize(
    "body",
    [
        {"id": True, "title": "Talking Nerdy", "state": "OPEN"},
        {"id": "1", "title": "Talking Nerdy", "state": "OPEN"},
        {"id": 2, "title": "Talking Nerdy", "state": "OPEN"},
        {"title": "Talking Nerdy", "state": "OPEN"},
        {"id": 1, "title": None, "state": "OPEN"},
        {"id": 1, "title": 7, "state": "OPEN"},
        {"id": 1, "state": "OPEN"},
        {"id": 1, "title": "Talking Nerdy"},
        {"id": 1, "title": "Talking Nerdy", "state": ["OPEN"]},
    ],
)
def test_response_identity_and_required_fields_are_checked(
    monkeypatch: pytest.MonkeyPatch, body: dict[str, object]
) -> None:
    with pytest.raises(AtlaWireError, match="Invalid pull request") as error:
        read(monkeypatch, body=body)

    assert "OPEN" not in str(error.value)
