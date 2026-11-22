"""Deterministic paging/deadline checks for repository grep."""

from contextlib import nullcontext

import pytest

from atlawire import bitbucket, repo_grep
from atlawire.http import AtlaWireError

BASE = "https://bitbucket.example.invalid/scm"
TOKEN = "fixture-only-token"
REPO = "DEMO/widgets"
SHA = "a" * 40


def install_transport(
    monkeypatch: pytest.MonkeyPatch,
    pages: list[dict[str, object]],
    clock: list[float],
    *,
    advance: float = 2.0,
) -> list[int]:
    """Install a loopback-free pager transport and count page requests."""
    calls: list[int] = []
    remaining = list(pages)

    def get_json_object(
        session: object, url: str, *, params: dict[str, object]
    ) -> dict[str, object]:
        calls.append(1)
        clock[0] = advance
        return remaining.pop(0)

    monkeypatch.setattr(
        bitbucket, "bearer_session", lambda token: nullcontext(None)
    )
    monkeypatch.setattr(bitbucket, "get_json_object", get_json_object)
    return calls


def skip_preflight_and_ref(monkeypatch: pytest.MonkeyPatch) -> None:
    def validate_ok(
        pattern: str, *, ignore_case: bool, timeout_s: float
    ) -> None:
        return None

    def resolve_ref(*args: object, **kwargs: object) -> tuple[str, str]:
        return SHA, "commit"

    def forbid_read(*args: object, **kwargs: object) -> str:
        raise AssertionError("no file read may happen after a deadline failure")

    monkeypatch.setattr(repo_grep, "_validate_pattern", validate_ok)
    monkeypatch.setattr(repo_grep, "_resolve_ref", resolve_ref)
    monkeypatch.setattr(repo_grep, "get_repository_file", forbid_read)


def test_branch_pagination_callback_runs_before_each_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = {
        "values": [
            {
                "displayId": "feature/x",
                "id": "refs/heads/feature/x",
                "latestCommit": SHA,
                "isDefault": False,
            }
        ],
        "isLastPage": False,
        "nextPageStart": 1,
    }
    calls = install_transport(monkeypatch, [page], [0.0], advance=0.0)
    checks = 0

    def before_page() -> None:
        nonlocal checks
        checks += 1
        if checks == 2:
            raise AtlaWireError("Repository grep time budget exhausted.")

    with pytest.raises(AtlaWireError, match="budget"):
        bitbucket.get_branch(
            BASE,
            REPO,
            "feature/x",
            token=TOKEN,
            before_page=before_page,
        )

    assert len(calls) == 1
    assert checks == 2


def test_nonterminal_page_crossing_deadline_does_not_issue_second_get(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = {
        "values": ["a.txt"],
        "isLastPage": False,
        "nextPageStart": 1,
    }
    clock = [0.0]
    calls = install_transport(monkeypatch, [page], clock)
    skip_preflight_and_ref(monkeypatch)
    monkeypatch.setattr(repo_grep, "_monotonic", lambda: clock[0])

    with pytest.raises(AtlaWireError, match="budget"):
        repo_grep.grep_repository(
            BASE,
            REPO,
            "needle",
            token=TOKEN,
            at=SHA,
            timeout_s=1.0,
        )

    assert len(calls) == 1


@pytest.mark.parametrize(
    "values", [[], ["assets/logo.png"]], ids=["empty", "excluded"]
)
def test_terminal_listing_past_deadline_is_not_a_complete_result(
    monkeypatch: pytest.MonkeyPatch, values: list[str]
) -> None:
    page = {"values": values, "isLastPage": True}
    clock = [0.0]
    calls = install_transport(monkeypatch, [page], clock)
    skip_preflight_and_ref(monkeypatch)
    monkeypatch.setattr(repo_grep, "_monotonic", lambda: clock[0])

    with pytest.raises(AtlaWireError, match="budget"):
        repo_grep.grep_repository(
            BASE,
            REPO,
            "needle",
            token=TOKEN,
            at=SHA,
            timeout_s=1.0,
        )

    assert len(calls) == 1
