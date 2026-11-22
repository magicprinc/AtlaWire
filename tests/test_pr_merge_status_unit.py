"""Unit tests for the read-only pull request mergeability adapter."""

from contextlib import nullcontext
from typing import Self, cast

import pytest
import responses

from atlawire import bitbucket
from atlawire.http import AtlaWireError

BASE = "https://bitbucket.example.invalid/scm"
TOKEN = "fixture-only-token"


def merge_url(
    identifier: int = 1, *, project: str = "DEMO", slug: str = "widgets"
) -> str:
    return (
        f"{BASE}/rest/api/1.0/projects/{project}"
        f"/repos/{slug}/pull-requests/{identifier}/merge"
    )


MERGE_URL = merge_url()


def mergeable(
    *,
    can_merge: bool = False,
    conflicted: bool = True,
    outcome: str = "CONFLICTED",
) -> dict[str, object]:
    return {
        "canMerge": can_merge,
        "conflicted": conflicted,
        "outcome": outcome,
        "vetoes": [
            {
                "summaryMessage": "You may not merge after 6pm on a Friday.",
                "detailedMessage": "Please try again on Monday.",
            }
        ],
    }


def stub(
    monkeypatch: pytest.MonkeyPatch,
    body: dict[str, object],
    *,
    base_url: str = BASE,
    repo: str = "DEMO/widgets",
    pr_id: str | int = "1",
) -> tuple[dict[str, object], list[tuple[str, dict[str, str | int]]]]:
    calls: list[tuple[str, dict[str, str | int]]] = []

    def fake_get_json_object(
        session: object, url: str, *, params: dict[str, str | int]
    ) -> dict[str, object]:
        calls.append((url, dict(params)))
        return body

    monkeypatch.setattr(bitbucket, "bearer_session", lambda token: nullcontext(None))
    monkeypatch.setattr(bitbucket, "get_json_object", fake_get_json_object)
    result = bitbucket.get_pull_request_merge_status(base_url, repo, pr_id, token=TOKEN)
    return result, calls


def forbidden_session(token: str) -> object:
    raise AssertionError("session created before validation")


class TrackingSession:
    """A context manager that records whether the adapter closed it."""

    def __init__(self) -> None:
        self.closed = False

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self.closed = True


def test_one_get_returns_the_server_object_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = mergeable()

    result, calls = stub(monkeypatch, body)

    assert result is body
    assert calls == [(MERGE_URL, {})]


@pytest.mark.parametrize(
    ("pr_id", "identifier"),
    [
        ("1", 1),
        (1, 1),
        ("7", 7),
        ("9223372036854775807", 2**63 - 1),
        (2**63 - 1, 2**63 - 1),
    ],
    ids=["string", "int", "other", "max-string", "max-int"],
)
def test_positive_ids_are_canonicalised_into_the_single_merge_get(
    monkeypatch: pytest.MonkeyPatch, pr_id: str | int, identifier: int
) -> None:
    result, calls = stub(monkeypatch, mergeable(), pr_id=pr_id)

    assert result["canMerge"] is False
    assert calls == [(merge_url(identifier), {})]


def test_context_path_and_personal_project_form_the_shared_merge_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = mergeable(can_merge=True, conflicted=False, outcome="CLEAN")

    result, calls = stub(monkeypatch, body, base_url=f"{BASE}/", repo="~user/my.repo")

    assert result is body
    assert calls == [(merge_url(project="~user", slug="my.repo"), {})]
    assert "?" not in calls[0][0]


@pytest.mark.parametrize(
    "body",
    [
        mergeable(),
        {
            "canMerge": True,
            "conflicted": False,
            "outcome": "CLEAN",
            "vetoes": [],
        },
        {},
        {"canMerge": True},
        {
            "canMerge": None,
            "conflicted": "unknown",
            "outcome": 7,
            "vetoes": None,
            "extension": {"nested": [None, True, "α"], "count": 0},
        },
    ],
    ids=["documented", "clean", "empty", "minimal", "unvalidated"],
)
def test_optional_and_unknown_fields_are_returned_without_validation(
    monkeypatch: pytest.MonkeyPatch, body: dict[str, object]
) -> None:
    result, calls = stub(monkeypatch, body)

    assert result is body
    assert calls == [(MERGE_URL, {})]


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
        "DEMO/widgets?x=1",
        "DEMO/widgets#frag",
    ],
)
def test_invalid_repo_is_rejected_before_any_session(
    monkeypatch: pytest.MonkeyPatch, repo: str
) -> None:
    monkeypatch.setattr(bitbucket, "bearer_session", forbidden_session)

    with pytest.raises(AtlaWireError, match="PROJECT/slug") as error:
        bitbucket.get_pull_request_merge_status(BASE, repo, "1", token=TOKEN)

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
def test_invalid_id_is_rejected_before_any_session(
    monkeypatch: pytest.MonkeyPatch, pr_id: object
) -> None:
    monkeypatch.setattr(bitbucket, "bearer_session", forbidden_session)

    with pytest.raises(AtlaWireError, match="pull request ID"):
        bitbucket.get_pull_request_merge_status(
            BASE, "DEMO/widgets", cast(str | int, pr_id), token=TOKEN
        )


def test_session_is_closed_after_a_successful_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = TrackingSession()
    received: list[object] = []

    def fake_get_json_object(
        active: object, url: str, *, params: dict[str, str | int]
    ) -> dict[str, object]:
        received.append(active)
        return {"canMerge": True}

    monkeypatch.setattr(bitbucket, "bearer_session", lambda token: session)
    monkeypatch.setattr(bitbucket, "get_json_object", fake_get_json_object)

    result = bitbucket.get_pull_request_merge_status(
        BASE, "DEMO/widgets", "1", token=TOKEN
    )

    assert result == {"canMerge": True}
    assert received == [session]
    assert session.closed


def test_session_is_closed_when_the_shared_transport_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = TrackingSession()

    def failing_get_json_object(
        active: object, url: str, *, params: dict[str, str | int]
    ) -> dict[str, object]:
        raise AtlaWireError("HTTP 500: request failed.")

    monkeypatch.setattr(bitbucket, "bearer_session", lambda token: session)
    monkeypatch.setattr(bitbucket, "get_json_object", failing_get_json_object)

    with pytest.raises(AtlaWireError, match="HTTP 500"):
        bitbucket.get_pull_request_merge_status(BASE, "DEMO/widgets", "1", token=TOKEN)

    assert session.closed


@responses.activate
def test_real_transport_sends_exactly_one_authenticated_get() -> None:
    body = mergeable()
    responses.get(MERGE_URL, json=body)

    result = bitbucket.get_pull_request_merge_status(
        BASE, "DEMO/widgets", "1", token=TOKEN
    )

    assert result == body
    assert len(responses.calls) == 1
    request = responses.calls[0].request
    assert request.method == "GET"
    assert request.url == MERGE_URL
    assert request.headers["Authorization"] == f"Bearer {TOKEN}"


@responses.activate
@pytest.mark.parametrize(
    ("payload", "literal_null"),
    [([], False), ("text", False), (7, False), (None, True), (True, False)],
    ids=["array", "string", "number", "null", "boolean"],
)
def test_non_object_json_is_rejected_by_the_shared_transport(
    payload: object, literal_null: bool
) -> None:
    if literal_null:
        # ``responses`` omits the body for json=None, so send JSON null literally.
        responses.get(MERGE_URL, body="null", content_type="application/json")
    else:
        responses.get(MERGE_URL, json=payload)

    with pytest.raises(AtlaWireError, match="Expected a JSON object"):
        bitbucket.get_pull_request_merge_status(BASE, "DEMO/widgets", "1", token=TOKEN)

    assert len(responses.calls) == 1


@responses.activate
@pytest.mark.parametrize(
    ("status", "message"),
    [
        (206, "partial content"),
        (401, "authentication rejected"),
        (403, "access denied"),
        (404, "HTTP 404"),
        (409, "HTTP 409"),
        (500, "HTTP 500"),
    ],
)
def test_shared_http_errors_propagate_after_one_get(status: int, message: str) -> None:
    responses.get(MERGE_URL, status=status, json={"errors": [{"message": "x"}]})

    with pytest.raises(AtlaWireError, match=message):
        bitbucket.get_pull_request_merge_status(BASE, "DEMO/widgets", "1", token=TOKEN)

    assert len(responses.calls) == 1


@responses.activate
def test_redirect_is_refused_and_never_followed() -> None:
    responses.get(
        MERGE_URL,
        status=302,
        headers={"Location": "https://evil.invalid/merge"},
    )

    with pytest.raises(AtlaWireError, match="redirect refused"):
        bitbucket.get_pull_request_merge_status(BASE, "DEMO/widgets", "1", token=TOKEN)

    assert len(responses.calls) == 1
    assert responses.calls[0].request.url == MERGE_URL
