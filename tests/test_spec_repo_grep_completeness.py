"""The grep result distinguishes an exact cap from a genuinely truncated walk."""

import time

from atlawire import repo_grep


def _scan(monkeypatch, names, matches, limit):
    monkeypatch.setattr(
        repo_grep, "_read_repository_file_in_session", lambda *args, **kwargs: "a\nb\n"
    )

    def fake_match(text, pattern, *, ignore_case, limit, timeout_s, line_count=None):
        return matches[:limit]

    monkeypatch.setattr(repo_grep, "_match_line_numbers", fake_match)
    return repo_grep._scan(
        "https://example.invalid",
        "PROJ/repo",
        names,
        token="synthetic-token",
        commit="abc1234",
        pattern="x",
        ignore_case=False,
        limit=limit,
        regex_timeout_s=1.0,
        deadline=time.monotonic() + 60,
        allow_http_loopback=False,
    )


def test_exact_cap_on_the_last_file_is_complete(monkeypatch):
    hits, scanned, status = _scan(monkeypatch, ["only.txt"], [1, 2], limit=2)

    assert status == "complete"
    assert len(hits) == 2
    assert scanned == 1


def test_exact_cap_before_another_file_is_truncated(monkeypatch):
    hits, scanned, status = _scan(
        monkeypatch, ["first.txt", "second.txt"], [1, 2], limit=2
    )

    assert status == "truncated"
    assert len(hits) == 2
    assert scanned == 1


def test_more_matches_than_the_cap_are_reported_as_truncated(monkeypatch):
    hits, scanned, status = _scan(monkeypatch, ["only.txt"], [1, 2, 3], limit=2)

    assert status == "truncated"
    assert len(hits) == 2
    assert scanned == 1
