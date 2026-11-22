"""Installed-CLI end-to-end checks for the planned ``grep-repo`` command.

The command is wired by another worker. These tests define the expected
``grep-repo REPO PATTERN [--at REF] [--glob PATTERN] [--limit N] --json``
contract and fail until that wiring lands.
"""

import json
import subprocess

import pytest

from tests._loopback import run_installed, serving
from tests._repo_grep_fixture import (
    RAW_BASE,
    REPO,
    Backend,
    base_arguments,
    branch_row,
    environment,
    handler_for,
    origin,
    raw_default_branch,
    tag_row,
    text,
)

TOKEN = "fixture-grep-cli-token"
SHA_A = "a" * 40
SHA_B = "b" * 40


def run_grep(
    pattern: str | None, *options: str, backend: Backend
) -> subprocess.CompletedProcess[str]:
    """Run the installed command against one loopback backend."""
    with serving(handler_for(backend)) as server:
        origin_url = origin(server)
        arguments = ["grep-repo", REPO]
        if pattern is not None:
            arguments.append(pattern)
        arguments.extend(options)
        arguments.extend(base_arguments(origin_url))
        return run_installed(
            arguments,
            environment(origin_url, TOKEN),
        )


def raw_requests(backend: Backend) -> list[str]:
    """Return raw-file request paths in arrival order."""
    return [
        request[1]
        for request in backend.requests
        if request[1].startswith(f"{RAW_BASE}/raw/")
    ]


def test_grep_repo_prints_json_hits_and_pins_one_branch_commit() -> None:
    backend = Backend()
    backend.branch_rows = [branch_row("feature/x", SHA_A)]
    backend.later_branch_rows = [branch_row("feature/x", SHA_B)]
    backend.paths = ["src/a.txt", "src/b.md"]
    backend.contents = {
        "src/a.txt": text("first\nneedle\n"),
        "src/b.md": text("needle\n"),
    }

    result = run_grep(
        "needle",
        "--at",
        "feature/x",
        "--glob",
        "*.txt",
        "--limit",
        "10",
        "--json",
        backend=backend,
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    payload = json.loads(result.stdout)
    assert payload["engine"] == "fanout"
    assert payload["commit"] == SHA_A
    assert payload["at"] == "feature/x"
    assert payload["ref_kind"] == "branch"
    assert payload["glob"] == "*.txt"
    assert payload["selection"] == "explicit"
    assert payload["hits"] == [
        {"file": "src/a.txt", "line": 2, "text": "needle", "text_truncated": False}
    ]
    assert payload["files_eligible"] == 1
    assert payload["files_excluded"] == 1
    assert payload["files_scanned"] == 1
    assert payload["truncated"] is False
    assert payload["complete"] is True
    assert backend.branch_reads == 1
    assert backend.tag_reads == 1
    assert raw_requests(backend) == [f"{RAW_BASE}/raw/src/a.txt"]
    assert [
        request[2]["at"]
        for request in backend.requests
        if request[1] == f"{RAW_BASE}/files"
    ] == [[SHA_A]]
    assert all(
        request[2]["at"] == [SHA_A]
        for request in backend.requests
        if "/raw/" in request[1] or request[1].endswith("/files")
    )
    assert all(SHA_B not in repr(request[2]) for request in backend.requests)
    assert TOKEN not in result.stdout
    assert TOKEN not in result.stderr


def test_grep_repo_fails_without_stdout_when_a_file_cannot_be_read() -> None:
    backend = Backend()
    backend.branch_rows = [branch_row("feature/x", SHA_A)]
    backend.paths = ["a.txt", "b.txt"]
    backend.contents = {"a.txt": text("needle")}
    backend.failures = {"b.txt": 500}

    result = run_grep(
        "needle", "--at", "feature/x", "--json", backend=backend
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "aborted without a result" in result.stderr
    assert TOKEN not in result.stderr
    assert raw_requests(backend) == [
        f"{RAW_BASE}/raw/a.txt",
        f"{RAW_BASE}/raw/b.txt",
    ]


def test_grep_repo_reports_truncation_when_the_limit_is_reached() -> None:
    backend = Backend()
    backend.branch_rows = [branch_row("feature/x", SHA_A)]
    backend.paths = ["a.txt", "b.txt"]
    backend.contents = {
        "a.txt": text("needle\nneedle\n"),
        "b.txt": text("needle\n"),
    }

    result = run_grep(
        "needle",
        "--at",
        "feature/x",
        "--limit",
        "1",
        "--json",
        backend=backend,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["hits"] == [
        {
            "file": "a.txt",
            "line": 1,
            "text": "needle",
            "text_truncated": False,
        }
    ]
    assert payload["selection"] == "text-suffixes"
    assert payload["files_eligible"] == 2
    assert payload["files_scanned"] == 1
    assert payload["truncated"] is True
    assert payload["complete"] is False
    assert raw_requests(backend) == [f"{RAW_BASE}/raw/a.txt"]


def test_grep_repo_rejects_a_malformed_regex_before_any_request() -> None:
    backend = Backend()

    result = run_grep("(", "--json", backend=backend)

    assert result.returncode == 1
    assert result.stdout == ""
    assert "regex is invalid" in result.stderr
    assert backend.requests == []


def test_grep_repo_uses_the_default_branch_when_at_is_omitted() -> None:
    backend = Backend()
    backend.default_branch = raw_default_branch(SHA_A)
    backend.paths = ["a.txt"]
    backend.contents = {"a.txt": text("needle\n")}

    result = run_grep("needle", "--json", backend=backend)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["commit"] == SHA_A
    assert payload["at"] is None
    assert payload["ref_kind"] == "default"
    assert payload["selection"] == "text-suffixes"
    assert payload["files_excluded"] == 0
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
    assert raw_requests(backend) == [f"{RAW_BASE}/raw/a.txt"]


def test_grep_repo_lists_paths_when_the_pattern_is_omitted() -> None:
    backend = Backend()
    backend.branch_rows = [branch_row("feature/x", SHA_A)]
    backend.paths = ["src/a.txt", "src/b.py", "Makefile"]

    result = run_grep(
        None,
        "--at",
        "refs/heads/feature/x",
        "--glob",
        "*.txt",
        "--json",
        backend=backend,
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    payload = json.loads(result.stdout)
    assert payload["engine"] == "listing"
    assert payload["selection"] == "explicit"
    assert payload["files"] == ["src/a.txt"]
    assert payload["files_eligible"] == 1
    assert payload["files_excluded"] == 2
    assert payload["files_scanned"] == 0
    assert payload["hits"] == []
    assert payload["truncated"] is False
    assert payload["complete"] is True
    assert backend.file_reads == 1
    assert raw_requests(backend) == []


def test_grep_repo_accepts_a_named_tag_and_pins_its_commit() -> None:
    backend = Backend()
    backend.tags = {"release-1": tag_row("release-1", SHA_B)}
    backend.paths = ["a.txt"]
    backend.contents = {"a.txt": text("needle\n")}

    result = run_grep("needle", "--at", "release-1", "--json", backend=backend)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["commit"] == SHA_B
    assert payload["at"] == "release-1"
    assert payload["ref_kind"] == "tag"
    assert payload["hits"] == [
        {"file": "a.txt", "line": 1, "text": "needle", "text_truncated": False}
    ]
    assert backend.branch_reads == 1
    assert backend.tag_reads == 1
    assert payload["selection"] == "text-suffixes"
    assert raw_requests(backend) == [f"{RAW_BASE}/raw/a.txt"]


def test_grep_repo_preserves_unicode_file_paths_and_case_folding() -> None:
    backend = Backend()
    backend.branch_rows = [branch_row("feature/x", SHA_A)]
    backend.paths = ["папка/файл.txt"]
    backend.contents = {"папка/файл.txt": text("Needle\n")}

    result = run_grep("needle", "--at", "feature/x", "--json", backend=backend)

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ignore_case"] is True
    assert payload["hits"] == [
        {"file": "папка/файл.txt", "line": 1, "text": "Needle", "text_truncated": False}
    ]
    assert raw_requests(backend) == [
        (
            f"{RAW_BASE}/raw/%D0%BF%D0%B0%D0%BF%D0%BA%D0%B0/"
            "%D1%84%D0%B0%D0%B9%D0%BB.txt"
        )
    ]


def test_grep_repo_does_not_echo_another_product_token() -> None:
    backend = Backend()
    backend.branch_rows = [branch_row("feature/x", SHA_A)]
    backend.paths = ["a.txt"]
    backend.contents = {"a.txt": text("needle\n")}

    result = run_grep("needle", "--at", "feature/x", "--json", backend=backend)

    assert result.returncode == 0, result.stderr
    assert "wrong-product-jira-grep" not in result.stdout
    assert "wrong-product-confluence-grep" not in result.stdout
    assert "wrong-product-jira-grep" not in result.stderr
    assert "wrong-product-confluence-grep" not in result.stderr


@pytest.mark.parametrize("value", ["0", "1001", "many"], ids=["zero", "high", "text"])
def test_grep_repo_limit_is_rejected_before_any_request(value: str) -> None:
    backend = Backend()

    result = run_grep("needle", "--limit", value, "--json", backend=backend)

    assert result.returncode in {1, 2}
    assert result.stdout == ""
    assert backend.requests == []
