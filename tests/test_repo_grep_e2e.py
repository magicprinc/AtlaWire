"""Library end-to-end checks for repository grep over a loopback Bitbucket."""

from http.server import HTTPServer

import pytest

from atlawire import repo_grep
from atlawire.http import AtlaWireError
from tests._loopback import Request, serving
from tests._repo_grep_fixture import (
    CONTEXT,
    RAW_BASE,
    REPO,
    Backend,
    binary,
    branch_row,
    handler_for,
    origin,
    oversize,
    raw_default_branch,
    tag_row,
    text,
)

TOKEN = "fixture-grep-token"
SHA_A = "a" * 40
SHA_B = "b" * 40


def call(
    server: HTTPServer,
    *,
    at: str | None = None,
    glob: str | None = None,
    path: str | None = None,
    pattern: str | None = "needle",
    limit: int = 200,
    ignore_case: bool = False,
    timeout_s: float = 10.0,
    regex_timeout_s: float = 5.0,
    max_pages: int = 100,
) -> repo_grep.GrepResult:
    """Call the library against one running loopback server."""
    return repo_grep.grep_repository(
        f"{origin(server)}{CONTEXT}",
        REPO,
        pattern,
        token=TOKEN,
        at=at,
        glob=glob,
        path=path,
        ignore_case=ignore_case,
        limit=limit,
        timeout_s=timeout_s,
        regex_timeout_s=regex_timeout_s,
        max_pages=max_pages,
        allow_http_loopback=True,
    )


def raw_requests(backend: Backend) -> list[Request]:
    """Return only raw-file requests in arrival order."""
    return [
        request
        for request in backend.requests
        if request[1].startswith(f"{RAW_BASE}/raw/")
    ]


def file_requests(backend: Backend) -> list[Request]:
    """Return only path-listing requests in arrival order."""
    return [
        request
        for request in backend.requests
        if request[1] == f"{RAW_BASE}/files"
    ]


def test_branch_movement_cannot_change_any_pinned_read() -> None:
    backend = Backend()
    backend.branch_rows = [branch_row("feature/x", SHA_A)]
    backend.later_branch_rows = [branch_row("feature/x", SHA_B)]
    backend.paths = ["src/a.txt", "src/b.txt"]
    backend.contents = {
        "src/a.txt": text("first\nneedle\n"),
        "src/b.txt": text("needle\nlast\n"),
    }

    with serving(handler_for(backend)) as server:
        result = call(server, at="feature/x")

    assert result["commit"] == SHA_A
    assert result["at"] == "feature/x"
    assert backend.branch_reads == 1
    assert result["hits"] == [
        {"file": "src/a.txt", "line": 2, "text": "needle", "text_truncated": False},
        {"file": "src/b.txt", "line": 1, "text": "needle", "text_truncated": False},
    ]
    assert result["complete"] is True
    assert result["truncated"] is False
    assert [request[2]["at"] for request in file_requests(backend)] == [[SHA_A]]
    assert [request[2]["at"] for request in raw_requests(backend)] == [
        [SHA_A],
        [SHA_A],
    ]
    assert result["ref_kind"] == "branch"
    assert result["selection"] == "text-suffixes"
    assert result["files_excluded"] == 0
    assert backend.tag_reads == 1
    assert all(SHA_B not in repr(request[2]) for request in backend.requests)
    assert all(request[3] == f"Bearer {TOKEN}" for request in backend.requests)


def test_default_branch_uses_the_fixed_get_and_pins_reads() -> None:
    backend = Backend()
    backend.default_branch = raw_default_branch(SHA_A)
    backend.paths = ["src/a.txt"]
    backend.contents = {"src/a.txt": text("needle\n")}

    with serving(handler_for(backend)) as server:
        result = call(server)

    assert result["commit"] == SHA_A
    assert result["at"] is None
    assert result["ref_kind"] == "default"
    assert result["selection"] == "text-suffixes"
    assert backend.default_reads == 1
    assert backend.branch_reads == 0
    assert [
        request
        for request in backend.requests
        if request[1] == f"{RAW_BASE}/branches/default"
    ] == [
        (
            "GET",
            f"{RAW_BASE}/branches/default",
            {},
            f"Bearer {TOKEN}",
        )
    ]
    assert [request[2]["at"] for request in file_requests(backend)] == [[SHA_A]]
    assert [request[2]["at"] for request in raw_requests(backend)] == [[SHA_A]]


def test_default_branch_204_fails_without_file_requests() -> None:
    backend = Backend()
    backend.default_branch = None
    backend.paths = ["src/a.txt"]

    with (
        serving(handler_for(backend)) as server,
        pytest.raises(AtlaWireError, match="no default branch"),
    ):
        call(server)

    assert backend.default_reads == 1
    assert backend.file_reads == 0
    assert raw_requests(backend) == []


@pytest.mark.parametrize(
    "commit", [None, "deadbeef"], ids=["null-commit", "short-commit"]
)
def test_default_branch_malformed_commit_fails_without_file_requests(
    commit: str | None,
) -> None:
    backend = Backend()
    backend.default_branch = raw_default_branch(commit)
    backend.paths = ["src/a.txt"]

    with (
        serving(handler_for(backend)) as server,
        pytest.raises(AtlaWireError, match="full commit ID"),
    ):
        call(server)

    assert backend.default_reads == 1
    assert backend.file_reads == 0
    assert raw_requests(backend) == []


def test_full_commit_is_verified_and_used_without_a_branch_listing() -> None:
    backend = Backend()
    backend.commit_ids = {SHA_A}
    backend.paths = ["src/a.txt"]
    backend.contents = {"src/a.txt": text("needle\n")}

    with serving(handler_for(backend)) as server:
        result = call(server, at=SHA_A)

    assert result["commit"] == SHA_A
    assert result["ref_kind"] == "commit"
    assert result["selection"] == "text-suffixes"
    assert backend.branch_reads == 0
    assert any(
        request[1] == f"{RAW_BASE}/commits/{SHA_A}"
        for request in backend.requests
    )
    assert [request[2]["at"] for request in file_requests(backend)] == [[SHA_A]]
    assert [request[2]["at"] for request in raw_requests(backend)] == [[SHA_A]]


def test_a_lost_later_page_fails_before_any_file_read() -> None:
    backend = Backend()
    backend.branch_rows = [branch_row("feature/x", SHA_A)]
    backend.file_pages = [
        {
            "values": ["a.txt", "b.txt"],
            "isLastPage": False,
            "nextPageStart": 2,
        },
        500,
    ]

    with (
        serving(handler_for(backend)) as server,
        pytest.raises(AtlaWireError, match="HTTP 500"),
    ):
        call(server, at="feature/x")

    assert raw_requests(backend) == []


def test_a_page_budget_cap_fails_instead_of_truncating_the_path_list() -> None:
    backend = Backend()
    backend.branch_rows = [branch_row("feature/x", SHA_A)]
    backend.file_pages = [
        {
            "values": ["a.txt"],
            "isLastPage": False,
            "nextPageStart": 1,
        }
    ]

    with (
        serving(handler_for(backend)) as server,
        pytest.raises(AtlaWireError, match="page limit"),
    ):
        call(server, at="feature/x", max_pages=1)

    assert raw_requests(backend) == []


def test_a_later_file_read_failure_produces_no_result() -> None:
    backend = Backend()
    backend.branch_rows = [branch_row("feature/x", SHA_A)]
    backend.paths = ["a.txt", "b.txt"]
    backend.contents = {"a.txt": text("needle")}
    backend.failures = {"b.txt": 500}

    with (
        serving(handler_for(backend)) as server,
        pytest.raises(AtlaWireError, match="aborted without a result"),
    ):
        call(server, at="feature/x")

    assert [request[1] for request in raw_requests(backend)] == [
        f"{RAW_BASE}/raw/a.txt",
        f"{RAW_BASE}/raw/b.txt",
    ]


def test_hit_limit_stops_reads_and_reports_truncation() -> None:
    backend = Backend()
    backend.branch_rows = [branch_row("feature/x", SHA_A)]
    backend.paths = ["a.txt", "b.txt"]
    backend.contents = {
        "a.txt": text("needle\nneedle\n"),
        "b.txt": text("needle\n"),
    }

    with serving(handler_for(backend)) as server:
        result = call(server, at="feature/x", limit=1)

    assert result["hits"] == [
        {
            "file": "a.txt",
            "line": 1,
            "text": "needle",
            "text_truncated": False,
        }
    ]
    assert result["truncated"] is True
    assert result["complete"] is False
    assert result["selection"] == "text-suffixes"
    assert result["files_eligible"] == 2
    assert result["files_scanned"] == 1
    assert [request[1] for request in raw_requests(backend)] == [
        f"{RAW_BASE}/raw/a.txt"
    ]


def test_path_and_glob_filters_read_only_selected_files() -> None:
    backend = Backend()
    backend.branch_rows = [branch_row("feature/x", SHA_A)]
    backend.paths = ["src/a.py", "src/b.txt", "docs/c.py", "srcery/d.py"]
    backend.contents = {
        "src/a.py": text("needle\n"),
        "src/b.txt": text("needle\n"),
        "docs/c.py": text("needle\n"),
        "srcery/d.py": text("needle\n"),
    }

    with serving(handler_for(backend)) as server:
        result = call(server, at="feature/x", path="src", glob="*.py")

    assert result["files_eligible"] == 1
    assert result["files_excluded"] == 3
    assert result["path"] == "src"
    assert result["glob"] == "*.py"
    assert result["hits"] == [
        {"file": "src/a.py", "line": 1, "text": "needle", "text_truncated": False}
    ]
    assert [request[1] for request in raw_requests(backend)] == [
        f"{RAW_BASE}/raw/src/a.py"
    ]


def test_ignore_case_is_explicit_on_every_call() -> None:
    backend = Backend()
    backend.branch_rows = [branch_row("feature/x", SHA_A)]
    backend.paths = ["a.txt"]
    backend.contents = {"a.txt": text("Needle\n")}

    with serving(handler_for(backend)) as server:
        exact = call(server, at="feature/x", ignore_case=False)
        backend.requests.clear()
        folded = call(server, at="feature/x", ignore_case=True)

    assert exact["hits"] == []
    assert exact["complete"] is True
    assert folded["hits"] == [
        {
            "file": "a.txt",
            "line": 1,
            "text": "Needle",
            "text_truncated": False,
        }
    ]
    assert folded["ignore_case"] is True


def test_binary_file_selected_explicitly_fails_instead_of_being_skipped() -> None:
    backend = Backend()
    backend.branch_rows = [branch_row("feature/x", SHA_A)]
    backend.paths = ["asset.bin"]
    backend.contents = {"asset.bin": binary()}

    with (
        serving(handler_for(backend)) as server,
        pytest.raises(AtlaWireError, match="text/plain"),
    ):
        call(server, at="refs/heads/feature/x", glob="*")


def test_oversize_eligible_file_fails_instead_of_being_skipped() -> None:
    backend = Backend()
    backend.branch_rows = [branch_row("feature/x", SHA_A)]
    backend.paths = ["huge.txt"]
    backend.contents = {"huge.txt": oversize()}

    with (
        serving(handler_for(backend)) as server,
        pytest.raises(AtlaWireError, match="1 MiB"),
    ):
        call(server, at="feature/x")


def test_unicode_and_reserved_paths_are_encoded_exactly_once() -> None:
    backend = Backend()
    backend.branch_rows = [branch_row("feature/x", SHA_A)]
    backend.paths = [
        "src/a b#?.txt",
        "папка/файл.txt",
        "dir/100%.txt",
    ]
    backend.contents = {
        "src/a b#?.txt": text("needle\n"),
        "папка/файл.txt": text("needle\n"),
        "dir/100%.txt": text("needle\n"),
    }

    with serving(handler_for(backend)) as server:
        result = call(server, at="feature/x")

    assert [hit["file"] for hit in result["hits"]] == backend.paths
    assert [request[1] for request in raw_requests(backend)] == [
        f"{RAW_BASE}/raw/src/a%20b%23%3F.txt",
        (
            f"{RAW_BASE}/raw/%D0%BF%D0%B0%D0%BF%D0%BA%D0%B0/"
            "%D1%84%D0%B0%D0%B9%D0%BB.txt"
        ),
        f"{RAW_BASE}/raw/dir/100%25.txt",
    ]
    assert result["complete"] is True


def test_default_scope_reads_text_suffixes_and_ignores_binary_paths() -> None:
    backend = Backend()
    backend.branch_rows = [branch_row("feature/x", SHA_A)]
    backend.paths = ["src/A.JAVA", "notes.md", "assets/logo.png", "Makefile"]
    backend.contents = {
        "src/A.JAVA": text("needle\n"),
        "notes.md": text("needle\n"),
        "assets/logo.png": binary(),
        "Makefile": text("needle\n"),
    }

    with serving(handler_for(backend)) as server:
        result = call(server, at="refs/heads/feature/x")

    assert result["selection"] == "text-suffixes"
    assert result["files_eligible"] == 2
    assert result["files_excluded"] == 2
    assert result["files_scanned"] == 2
    assert result["complete"] is True
    assert [hit["file"] for hit in result["hits"]] == [
        "src/A.JAVA",
        "notes.md",
    ]
    assert [request[1] for request in raw_requests(backend)] == [
        f"{RAW_BASE}/raw/src/A.JAVA",
        f"{RAW_BASE}/raw/notes.md",
    ]


def test_no_pattern_lists_all_paths_without_reads_or_regex(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = Backend()
    backend.branch_rows = [branch_row("feature/x", SHA_A)]
    backend.paths = ["Makefile", "assets/logo.png", "src/A.java"]

    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("listing must not read files or run a regex helper")

    monkeypatch.setattr(repo_grep, "get_repository_file", forbidden)
    monkeypatch.setattr(repo_grep, "_match_line_numbers", forbidden)
    monkeypatch.setattr(repo_grep, "_validate_pattern", forbidden)

    with serving(handler_for(backend)) as server:
        result = call(server, pattern=None, at="refs/heads/feature/x")

    assert result["engine"] == "listing"
    assert result["selection"] == "all-paths"
    assert result["files"] == backend.paths
    assert result["files_eligible"] == 3
    assert result["files_excluded"] == 0
    assert result["files_scanned"] == 0
    assert result["hits"] == []
    assert result["truncated"] is False
    assert result["complete"] is True
    assert backend.file_reads == 1
    assert backend.tag_reads == 0
    assert raw_requests(backend) == []


def test_no_pattern_applies_filters_and_reports_the_output_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = Backend()
    backend.branch_rows = [branch_row("feature/x", SHA_A)]
    backend.paths = ["src/a.py", "src/b.py", "docs/c.py", "src/d.txt"]

    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("listing must not read files or run a regex helper")

    monkeypatch.setattr(repo_grep, "get_repository_file", forbidden)
    monkeypatch.setattr(repo_grep, "_match_line_numbers", forbidden)

    with serving(handler_for(backend)) as server:
        result = call(
            server,
            pattern=None,
            at="refs/heads/feature/x",
            path="src",
            glob="*.py",
            limit=1,
        )

    assert result["engine"] == "listing"
    assert result["selection"] == "explicit"
    assert result["files"] == ["src/a.py"]
    assert result["files_eligible"] == 2
    assert result["files_excluded"] == 2
    assert result["files_scanned"] == 0
    assert result["hits"] == []
    assert result["truncated"] is True
    assert result["complete"] is False
    assert raw_requests(backend) == []


def test_no_pattern_page_failure_after_rows_produces_no_result() -> None:
    backend = Backend()
    backend.branch_rows = [branch_row("feature/x", SHA_A)]
    backend.file_pages = [
        {
            "values": ["a.txt", "b.txt"],
            "isLastPage": False,
            "nextPageStart": 2,
        },
        500,
    ]

    with (
        serving(handler_for(backend)) as server,
        pytest.raises(AtlaWireError, match="HTTP 500"),
    ):
        call(server, pattern=None, at="refs/heads/feature/x")

    assert backend.file_reads == 2
    assert raw_requests(backend) == []


def test_no_pattern_missing_ref_fails_before_listing() -> None:
    backend = Backend()
    backend.branch_rows = []

    with (
        serving(handler_for(backend)) as server,
        pytest.raises(AtlaWireError, match="branch was not found"),
    ):
        call(server, pattern=None, at="refs/heads/missing")

    assert backend.file_reads == 0
    assert raw_requests(backend) == []


def test_no_pattern_default_204_fails_before_listing() -> None:
    backend = Backend()
    backend.default_branch = None

    with (
        serving(handler_for(backend)) as server,
        pytest.raises(AtlaWireError, match="no default branch"),
    ):
        call(server, pattern=None)

    assert backend.default_reads == 1
    assert backend.file_reads == 0
    assert raw_requests(backend) == []


def test_named_tag_is_checked_for_ambiguity_and_pinned() -> None:
    backend = Backend()
    backend.tags = {"release-1": tag_row("release-1", SHA_B)}
    backend.paths = ["src/a.txt"]
    backend.contents = {"src/a.txt": text("needle\n")}

    with serving(handler_for(backend)) as server:
        result = call(server, at="release-1")

    assert result["commit"] == SHA_B
    assert result["ref_kind"] == "tag"
    assert backend.branch_reads == 1
    assert backend.tag_reads == 1
    assert [request[2]["at"] for request in raw_requests(backend)] == [[SHA_B]]
    assert result["complete"] is True


def test_qualified_tag_skips_the_branch_route() -> None:
    backend = Backend()
    backend.tags = {"release-1": tag_row("release-1", SHA_B)}
    backend.paths = ["src/a.txt"]
    backend.contents = {"src/a.txt": text("needle\n")}

    with serving(handler_for(backend)) as server:
        result = call(server, at="refs/tags/release-1")

    assert result["commit"] == SHA_B
    assert result["ref_kind"] == "tag"
    assert backend.branch_reads == 0
    assert backend.tag_reads == 1
    assert [request[2]["at"] for request in raw_requests(backend)] == [[SHA_B]]


def test_qualified_branch_skips_the_tag_route() -> None:
    backend = Backend()
    backend.branch_rows = [branch_row("feature/x", SHA_A)]
    backend.paths = ["src/a.txt"]
    backend.contents = {"src/a.txt": text("needle\n")}

    with serving(handler_for(backend)) as server:
        result = call(server, at="refs/heads/feature/x")

    assert result["commit"] == SHA_A
    assert result["ref_kind"] == "branch"
    assert backend.branch_reads == 1
    assert backend.tag_reads == 0
    assert [request[2]["at"] for request in raw_requests(backend)] == [[SHA_A]]


def test_wrong_tag_identity_is_rejected_before_file_listing() -> None:
    backend = Backend()
    backend.tags = {
        "v1": tag_row(
            "v1", SHA_B, identifier="v2", display_id="refs/tags/v2"
        )
    }
    backend.paths = ["src/a.txt"]
    backend.contents = {"src/a.txt": text("needle\n")}

    with (
        serving(handler_for(backend)) as server,
        pytest.raises(AtlaWireError, match="tag identity"),
    ):
        call(server, at="refs/tags/v1")

    assert backend.tag_reads == 1
    assert backend.file_reads == 0
    assert raw_requests(backend) == []


@pytest.mark.parametrize(
    ("identifier", "display_id"),
    [
        ("v1", "refs/tags/v1"),
        ("refs/tags/v1", "v1"),
    ],
    ids=["short-id-prefixed-display", "prefixed-id-short-display"],
)
def test_tag_identity_accepts_both_documented_prefix_formats(
    identifier: str, display_id: str
) -> None:
    backend = Backend()
    backend.tags = {
        "v1": tag_row(
            "v1", SHA_B, identifier=identifier, display_id=display_id
        )
    }
    backend.paths = ["src/a.txt"]
    backend.contents = {"src/a.txt": text("needle\n")}

    with serving(handler_for(backend)) as server:
        result = call(server, at="refs/tags/v1")

    assert result["commit"] == SHA_B
    assert result["ref_kind"] == "tag"
    assert [request[2]["at"] for request in raw_requests(backend)] == [[SHA_B]]
    assert result["complete"] is True


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("id", "v1"),
        ("id", "refs/tags/v1"),
        ("displayId", "v1"),
        ("displayId", "refs/tags/v1"),
    ],
    ids=[
        "short-id-only",
        "full-id-only",
        "short-display-only",
        "full-display-only",
    ],
)
def test_tag_identity_accepts_one_documented_field(
    field: str, value: str
) -> None:
    backend = Backend()
    backend.tags = {"v1": {field: value, "latestCommit": SHA_B}}
    backend.paths = ["src/a.txt"]
    backend.contents = {"src/a.txt": text("needle\n")}

    with serving(handler_for(backend)) as server:
        result = call(server, at="refs/tags/v1")

    assert result["commit"] == SHA_B
    assert result["ref_kind"] == "tag"
    assert backend.tag_reads == 1
    assert [request[2]["at"] for request in raw_requests(backend)] == [[SHA_B]]
    assert result["complete"] is True


def test_literal_refs_tags_short_name_is_pinned() -> None:
    backend = Backend()
    backend.tags = {
        "refs/tags/v1": tag_row(
            "refs/tags/v1",
            SHA_B,
            identifier="refs/tags/refs/tags/v1",
            display_id="refs/tags/v1",
        )
    }
    backend.paths = ["src/a.txt"]
    backend.contents = {"src/a.txt": text("needle\n")}

    with serving(handler_for(backend)) as server:
        result = call(server, at="refs/tags/refs/tags/v1")

    assert result["commit"] == SHA_B
    assert result["ref_kind"] == "tag"
    assert backend.tag_reads == 1
    assert [request[2]["at"] for request in raw_requests(backend)] == [[SHA_B]]
    assert result["complete"] is True


def test_branch_and_tag_with_the_same_name_fail_before_any_read() -> None:
    backend = Backend()
    backend.branch_rows = [branch_row("feature/x", SHA_A)]
    backend.tags = {"feature/x": tag_row("feature/x", SHA_B)}
    backend.paths = ["src/a.txt"]

    with (
        serving(handler_for(backend)) as server,
        pytest.raises(AtlaWireError, match="both a branch and a tag"),
    ):
        call(server, at="feature/x")

    assert backend.branch_reads == 1
    assert backend.tag_reads == 1
    assert raw_requests(backend) == []


def test_tag_without_a_full_commit_fails_closed() -> None:
    backend = Backend()
    backend.tags = {"release-1": tag_row("release-1", None)}
    backend.paths = ["src/a.txt"]

    with (
        serving(handler_for(backend)) as server,
        pytest.raises(AtlaWireError, match="tag does not carry a full commit"),
    ):
        call(server, at="release-1")

    assert raw_requests(backend) == []


def test_hit_text_is_capped_and_short_text_is_unchanged() -> None:
    backend = Backend()
    backend.branch_rows = [branch_row("feature/x", SHA_A)]
    long_line = "x" * 350 + "needle" + "y" * 50
    backend.paths = ["long.txt", "short.txt"]
    backend.contents = {
        "long.txt": text(long_line + "\n"),
        "short.txt": text("short needle\n"),
    }

    with serving(handler_for(backend)) as server:
        result = call(
            server, at="refs/heads/feature/x", limit=10
        )

    assert result["hits"] == [
        {
            "file": "long.txt",
            "line": 1,
            "text": long_line[: repo_grep.HIT_TEXT_LIMIT],
            "text_truncated": True,
        },
        {
            "file": "short.txt",
            "line": 1,
            "text": "short needle",
            "text_truncated": False,
        },
    ]
    assert "needle" not in result["hits"][0]["text"]
    assert len(result["hits"][0]["text"]) == repo_grep.HIT_TEXT_LIMIT
    assert result["complete"] is True
