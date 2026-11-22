"""Focused checks for the fan-out repository grep without network access."""

import subprocess
from collections.abc import Callable
from time import monotonic as real_monotonic
from typing import cast

import pytest

from atlawire import regex_helper, repo_grep
from atlawire.http import AtlaWireError

BASE = "https://bitbucket.example.invalid/scm"
TOKEN = "fixture-only-token"
REPO = "DEMO/widgets"
SHA_A = "a" * 40
SHA_B = "b" * 40


class FakeRepository:
    """Adapter double recording the exact pins and read attempts."""

    def __init__(self) -> None:
        self.branch: dict[str, object] | None = None
        self.branch_requests = 0
        self.default_branch: object = None
        self.default_requests = 0
        self.default_arguments: list[dict[str, object]] = []
        self.default_delay = 0.0
        self.commit: str | None = None
        self.commit_requests: list[str] = []
        self.paths: list[str] = []
        self.files: dict[str, str] = {}
        self.fail_reads: set[str] = set()
        self.reads: list[tuple[str, str]] = []
        self.calls: list[tuple[str, object]] = []
        self.list_delay = 0.0
        self.read_delay = 0.0
        self.branch_delay = 0.0
        self.match_delay = 0.0
        self.clock = [0.0]
        self.match_calls: list[tuple[str, float]] = []
        self.validation_calls = 0
        self.tags: dict[str, dict[str, object]] = {}
        self.tag_requests: list[str] = []
        self.tag_error: AtlaWireError | None = None


def install(
    monkeypatch: pytest.MonkeyPatch,
    fake: FakeRepository,
    *,
    real_matcher: bool = False,
) -> None:
    """Install adapter doubles and a fake monotonic clock for one test."""

    def read_operation(
        operation_id: str,
        base_url: str,
        *,
        token: str,
        arguments: dict[str, object],
        allow_http_loopback: bool = False,
    ) -> object:
        fake.default_requests += 1
        fake.calls.append(("default", operation_id))
        fake.default_arguments.append(dict(arguments))
        fake.clock[0] += fake.default_delay
        return fake.default_branch

    def get_branch(
        base_url: str,
        repo: str,
        name: str,
        *,
        token: str,
        max_pages: int = 100,
        allow_http_loopback: bool = False,
        before_page: Callable[[], None] | None = None,
    ) -> dict[str, object] | None:
        fake.branch_requests += 1
        fake.calls.append(("branch", name))
        if before_page is not None:
            before_page()
        fake.clock[0] += fake.branch_delay
        return fake.branch

    def get_commit(
        base_url: str,
        repo: str,
        sha: str,
        *,
        token: str,
        allow_http_loopback: bool = False,
    ) -> dict[str, object]:
        fake.commit_requests.append(sha)
        fake.calls.append(("commit", sha))
        if fake.commit is None:
            raise AtlaWireError("HTTP 404: request failed.")
        return {"id": fake.commit}

    def get_tag(
        base_url: str,
        repo: str,
        name: str,
        *,
        token: str,
        allow_http_loopback: bool = False,
    ) -> dict[str, object]:
        fake.tag_requests.append(name)
        fake.calls.append(("tag", name))
        if fake.tag_error is not None:
            raise fake.tag_error
        tag = fake.tags.get(name)
        if tag is None:
            raise AtlaWireError("HTTP 404: request failed.")
        return tag

    def list_repository_files(
        base_url: str,
        repo: str,
        *,
        token: str,
        at: str | None = None,
        max_pages: int = 100,
        allow_http_loopback: bool = False,
        before_page: Callable[[], None] | None = None,
    ) -> list[str]:
        fake.calls.append(("files", at))
        if before_page is not None:
            before_page()
        fake.clock[0] += fake.list_delay
        return list(fake.paths)

    def get_repository_file(
        base_url: str,
        repo: str,
        path: str,
        *,
        token: str,
        at: str = "master",
        allow_http_loopback: bool = False,
    ) -> str:
        fake.reads.append((path, at))
        fake.clock[0] += fake.read_delay
        if path in fake.fail_reads:
            raise AtlaWireError("HTTP 500: request failed.")
        return fake.files[path]

    def match_line_numbers(
        text: str,
        pattern: str,
        *,
        ignore_case: bool,
        limit: int,
        timeout_s: float,
        line_count: int,
    ) -> list[int]:
        fake.match_calls.append((pattern, timeout_s))
        fake.clock[0] += fake.match_delay
        lines = repo_grep._split_lines(text)
        if ignore_case:
            folded = pattern.lower()
            found = [n for n, line in enumerate(lines, 1) if folded in line.lower()]
        else:
            found = [n for n, line in enumerate(lines, 1) if pattern in line]
        return found[:limit]

    def validate_ok(
        pattern: str, *, ignore_case: bool, timeout_s: float
    ) -> None:
        fake.validation_calls += 1
        return None

    monkeypatch.setattr(repo_grep, "read_operation", read_operation)
    monkeypatch.setattr(repo_grep, "get_branch", get_branch)
    monkeypatch.setattr(repo_grep, "get_commit", get_commit)
    monkeypatch.setattr(repo_grep, "get_tag", get_tag)
    monkeypatch.setattr(repo_grep, "list_repository_files", list_repository_files)
    monkeypatch.setattr(repo_grep, "get_repository_file", get_repository_file)
    monkeypatch.setattr(repo_grep, "_monotonic", lambda: fake.clock[0])
    if not real_matcher:
        monkeypatch.setattr(repo_grep, "_match_line_numbers", match_line_numbers)
        monkeypatch.setattr(regex_helper, "validate_regex", validate_ok)


def tag_object(
    commit: str | None = SHA_B,
    *,
    name: str = "release-1",
    identifier: str | None = None,
    display_id: str | None = None,
) -> dict[str, object]:
    return {
        "id": name if identifier is None else identifier,
        "displayId": f"refs/tags/{name}" if display_id is None else display_id,
        "latestCommit": commit,
        "latestChangeset": commit,
        "hash": "",
    }


def raw_default_branch(commit: str | None = SHA_A) -> dict[str, object]:
    return {
        "displayId": "main",
        "id": "refs/heads/main",
        "latestCommit": commit,
        "isDefault": True,
    }


def feature_branch(commit: str = SHA_A) -> dict[str, object]:
    return {
        "name": "feature/x",
        "id": "refs/heads/feature/x",
        "commit": commit,
        "default": False,
    }


def simple_repository() -> FakeRepository:
    fake = FakeRepository()
    fake.branch = feature_branch()
    fake.paths = ["src/a.txt"]
    fake.files = {"src/a.txt": "needle\n"}
    return fake


def test_malformed_regex_fails_before_any_repository_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeRepository()
    install(monkeypatch, fake, real_matcher=True)

    with pytest.raises(AtlaWireError, match="regex is invalid"):
        repo_grep.grep_repository(
            BASE, REPO, "(", token=TOKEN, regex_timeout_s=5.0
        )

    assert fake.calls == []
    assert fake.reads == []


def test_helper_keeps_pattern_and_text_off_argv_and_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class Process:
        returncode = 0

        def __init__(self, args: list[str], **kwargs: object) -> None:
            captured["args"] = args
            captured["kwargs"] = kwargs

        def communicate(
            self, data: bytes | None = None, timeout: float | None = None
        ) -> tuple[bytes, bytes]:
            captured["input"] = data
            captured["timeout"] = timeout
            return b'{"matches": [1]}', b""

        def poll(self) -> int:
            return self.returncode

        def kill(self) -> None:
            raise AssertionError("kill must not be needed")

        def wait(self, timeout: float | None = None) -> int:
            return self.returncode

    monkeypatch.setattr(regex_helper.subprocess, "Popen", Process)
    monkeypatch.setenv("ATLAWIRE_BITBUCKET_TOKEN", TOKEN)

    numbers = repo_grep._match_line_numbers(
        "SECRET-BODY\nmatch",
        "SECRET-PATTERN",
        ignore_case=False,
        limit=5,
        timeout_s=2.0,
        line_count=2,
    )

    assert numbers == [1]
    arguments = cast(list[str], captured["args"])
    command = " ".join(arguments)
    assert "SECRET-PATTERN" not in command
    assert "SECRET-BODY" not in command
    assert arguments[1:3] == ["-I", "-S"]
    assert arguments[3] == "-c"
    payload = cast(bytes, captured["input"])
    assert b"SECRET-PATTERN" in payload
    assert b"SECRET-BODY" in payload
    assert captured["timeout"] == 2.0
    captured_kwargs = cast(dict[str, object], captured["kwargs"])
    environment = cast(dict[str, str], captured_kwargs["env"])
    assert TOKEN not in environment.values()
    assert "ATLAWIRE_BITBUCKET_TOKEN" not in environment


def test_timed_out_helper_is_killed_and_reap_is_attempted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[object] = []

    class Process:
        returncode: int | None = None

        def __init__(self) -> None:
            self.killed = False
            self.waits = 0

        def communicate(
            self, data: bytes | None = None, timeout: float | None = None
        ) -> tuple[bytes, bytes]:
            if not self.killed:
                raise subprocess.TimeoutExpired("helper", timeout or 0)
            return b"", b""

        def poll(self) -> int | None:
            return self.returncode if self.killed else None

        def kill(self) -> None:
            self.killed = True
            self.returncode = -9

        def wait(self, timeout: float | None = None) -> int:
            self.waits += 1
            assert self.returncode is not None
            return self.returncode

    def factory(args: list[str], **kwargs: object) -> Process:
        process = Process()
        created.append(process)
        return process

    monkeypatch.setattr(regex_helper.subprocess, "Popen", factory)

    with pytest.raises(repo_grep._HelperTimeout):
        repo_grep._match_line_numbers(
            "text",
            "text",
            ignore_case=False,
            limit=1,
            timeout_s=0.1,
            line_count=1,
        )

    process = cast(Process, created[0])
    assert process.killed is True
    assert process.waits == 1


def test_pathological_pattern_is_stopped_by_the_helper_timeout() -> None:
    started = real_monotonic()

    with pytest.raises(repo_grep._HelperTimeout):
        repo_grep._match_line_numbers(
            "a" * 50_000 + "!",
            "(a+)+$",
            ignore_case=False,
            limit=1,
            timeout_s=0.5,
            line_count=1,
        )

    assert real_monotonic() - started < 10.0


def test_public_grep_fails_closed_when_a_pattern_times_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = simple_repository()
    fake.files = {"src/a.txt": "a" * 50_000 + "!"}
    install(monkeypatch, fake, real_matcher=True)

    with pytest.raises(AtlaWireError, match="regex evaluation timed out"):
        repo_grep.grep_repository(
            BASE,
            REPO,
            "(a+)+$",
            token=TOKEN,
            at="feature/x",
            timeout_s=10.0,
            regex_timeout_s=0.5,
        )

    assert fake.reads == [("src/a.txt", SHA_A)]


def test_helper_applies_case_folding_and_crlf_line_numbers() -> None:
    numbers = repo_grep._match_line_numbers(
        "one\r\nNEEDLE\r\nthree\r\n",
        "needle",
        ignore_case=True,
        limit=10,
        timeout_s=5.0,
        line_count=3,
    )

    assert numbers == [2]
    assert repo_grep._split_lines("one\r\nNEEDLE\r\nthree\r\n") == [
        "one",
        "NEEDLE",
        "three",
    ]


def test_helper_carries_regex_and_quote_escapes_as_data() -> None:
    numbers = repo_grep._match_line_numbers(
        'say "hi"\nid=42\nid=x',
        r'"hi"|id=\d+',
        ignore_case=False,
        limit=10,
        timeout_s=5.0,
        line_count=3,
    )

    assert numbers == [1, 2]


def test_helper_source_is_valid_python() -> None:
    compile(repo_grep._HELPER_SOURCE, "<repository-grep-helper>", "exec")


def test_oversized_repetition_is_reported_as_an_invalid_regex() -> None:
    with pytest.raises(repo_grep._HelperInvalidRegex):
        repo_grep._match_line_numbers(
            "",
            "a{999999999999}",
            ignore_case=False,
            limit=1,
            timeout_s=5.0,
            line_count=0,
        )


@pytest.mark.parametrize(
    ("stdout", "limit", "line_count"),
    [
        (b"not json", 5, 3),
        (b'{"matches": [2, 1]}', 5, 3),
        (b'{"matches": [0]}', 5, 3),
        (b'{"matches": [4]}', 5, 3),
        (b'{"matches": [1, 2, 3]}', 2, 3),
        (b'{"matches": ["1"]}', 5, 3),
        (b'{"matches": [true]}', 5, 3),
    ],
    ids=[
        "not-json",
        "descending",
        "zero",
        "past-eof",
        "over-limit",
        "string",
        "boolean",
    ],
)
def test_helper_result_is_validated(
    stdout: bytes, limit: int, line_count: int
) -> None:
    with pytest.raises(regex_helper.HelperFailure):
        regex_helper.decode_line_matches(
            stdout, limit=limit, line_count=line_count
        )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", []),
        ("a", ["a"]),
        ("a\n", ["a"]),
        ("a\r\n", ["a"]),
        ("a\n\n", ["a", ""]),
        ("\n", [""]),
        ("a\nb\r\nc", ["a", "b", "c"]),
    ],
    ids=["empty", "no-newline", "lf-terminated", "crlf", "blank-line", "only-newline",
         "mixed"],
)
def test_split_lines_has_one_documented_rule(
    text: str, expected: list[str]
) -> None:
    assert repo_grep._split_lines(text) == expected


@pytest.mark.parametrize(
    ("name", "path", "glob", "expected"),
    [
        ("src/a.py", None, "*.py", True),
        ("docs/a.txt", None, "*.py", False),
        ("src/a.py", "src", "*.py", True),
        ("srcery/a.py", "src", None, False),
        ("src/deep/a.py", "src", "src/*.py", True),
        ("docs/a.txt", "src", None, False),
        ("src/a.py", None, "src/*.txt", False),
        ("src/a.py", None, "*", True),
        ("a/b/c.java", None, "*.java", True),
    ],
    ids=[
        "basename-glob",
        "basename-miss",
        "path-and-glob",
        "path-boundary",
        "fnmatch-crosses-slash",
        "path-miss",
        "full-path-miss",
        "star-everything",
        "deep-basename",
    ],
)
def test_path_and_glob_filters_have_documented_matching(
    name: str, path: str | None, glob: str | None, expected: bool
) -> None:
    assert repo_grep._eligible(name, path, glob) is expected


@pytest.mark.parametrize(
    "path",
    ["../a", "/a", "a//b", "a/./b", "a/../b", "a\\b", "a\x00b", "a\nb"],
    ids=["parent", "absolute", "empty-segment", "dot", "dot-dot", "backslash",
         "nul", "lf"],
)
def test_unsafe_path_filters_are_rejected(path: str) -> None:
    with pytest.raises(AtlaWireError, match="path filter"):
        repo_grep._path_filter(path)


@pytest.mark.parametrize(
    "glob",
    ["a\x00b", "a\nb", "a\\b", "x" * 1025],
    ids=["nul", "lf", "backslash", "oversize"],
)
def test_unsafe_globs_are_rejected(glob: str) -> None:
    with pytest.raises(AtlaWireError, match="glob"):
        repo_grep._glob_filter(glob)


def test_one_trailing_slash_in_a_path_filter_is_normalized() -> None:
    assert repo_grep._path_filter("src/") == "src"
    assert repo_grep._path_filter("") is None
    assert repo_grep._path_filter(None) is None


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("src/A.JAVA", True),
        ("docs/notes.md", True),
        ("assets/logo.png", False),
        ("Makefile", False),
        ("dir.v2/file", False),
        ("src/archive.tar.gz", False),
        (".java", True),
        ("src/trailing.", False),
    ],
    ids=[
        "uppercase-java",
        "markdown",
        "png",
        "no-suffix",
        "dotted-directory",
        "double-suffix",
        "hidden-text-name",
        "trailing-dot",
    ],
)
def test_default_text_scope_uses_the_bbk_suffix_set(
    name: str, expected: bool
) -> None:
    assert repo_grep._default_text_file(name) is expected


def test_default_scope_reads_only_text_suffixes_and_counts_exclusions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeRepository()
    fake.default_branch = raw_default_branch()
    fake.paths = ["src/A.JAVA", "notes.md", "assets/logo.png", "Makefile"]
    fake.files = {"src/A.JAVA": "needle\n", "notes.md": "needle\n"}
    install(monkeypatch, fake)

    result = repo_grep.grep_repository(
        BASE, REPO, "needle", token=TOKEN, timeout_s=10.0
    )

    assert result["selection"] == "text-suffixes"
    assert result["files_eligible"] == 2
    assert result["files_excluded"] == 2
    assert result["files_scanned"] == 2
    assert result["complete"] is True
    assert fake.reads == [("src/A.JAVA", SHA_A), ("notes.md", SHA_A)]
    assert result["hits"] == [
        {
            "file": "src/A.JAVA",
            "line": 1,
            "text": "needle",
            "text_truncated": False,
        },
        {
            "file": "notes.md",
            "line": 1,
            "text": "needle",
            "text_truncated": False,
        },
    ]


def test_explicit_glob_disables_the_default_text_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeRepository()
    fake.branch = feature_branch()
    fake.paths = ["Makefile"]
    fake.files = {"Makefile": "needle"}
    install(monkeypatch, fake)

    result = repo_grep.grep_repository(
        BASE,
        REPO,
        "needle",
        token=TOKEN,
        at="refs/heads/feature/x",
        glob="*",
    )

    assert result["selection"] == "explicit"
    assert result["files_eligible"] == 1
    assert result["files_excluded"] == 0
    assert fake.reads == [("Makefile", SHA_A)]
    assert result["complete"] is True


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"limit": 0}, "limit"),
        ({"limit": 1001}, "limit"),
        ({"limit": True}, "limit"),
        ({"timeout_s": 0}, "timeout"),
        ({"timeout_s": float("inf")}, "timeout"),
        ({"regex_timeout_s": -1}, "timeout"),
        ({"max_pages": 0}, "page limit"),
        ({"max_pages": 1001}, "page limit"),
        ({"ignore_case": "yes"}, "ignore-case"),
        ({"glob": "a\x00b"}, "glob"),
        ({"path": "../a"}, "path filter"),
        ({"at": "a\nb"}, "ref"),
        ({"pattern": ""}, "regex"),
    ],
    ids=[
        "limit-zero",
        "limit-high",
        "limit-bool",
        "timeout-zero",
        "timeout-infinite",
        "regex-timeout-negative",
        "pages-zero",
        "pages-high",
        "ignore-case-type",
        "glob-control",
        "path-parent",
        "ref-control",
        "empty-pattern",
    ],
)
def test_invalid_options_fail_before_any_repository_call(
    monkeypatch: pytest.MonkeyPatch,
    kwargs: dict[str, object],
    message: str,
) -> None:
    fake = FakeRepository()
    install(monkeypatch, fake)
    arguments: dict[str, object] = {
        "token": TOKEN,
        "pattern": "needle",
        **kwargs,
    }

    with pytest.raises(AtlaWireError, match=message):
        repo_grep.grep_repository(BASE, REPO, **arguments)

    assert fake.calls == []
    assert fake.reads == []


def test_invalid_repository_fails_before_any_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeRepository()
    install(monkeypatch, fake)

    with pytest.raises(AtlaWireError, match="PROJECT/slug"):
        repo_grep.grep_repository(
            BASE, "../DEMO/widgets", "needle", token=TOKEN
        )

    assert fake.calls == []


def test_default_branch_uses_the_fixed_operation_and_pins_the_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeRepository()
    fake.default_branch = raw_default_branch()
    fake.paths = ["src/a.txt"]
    fake.files = {"src/a.txt": "needle\n"}
    install(monkeypatch, fake)

    result = repo_grep.grep_repository(
        BASE, REPO, "needle", token=TOKEN, timeout_s=10.0
    )

    assert result["engine"] == "fanout"
    assert result["commit"] == SHA_A
    assert result["at"] is None
    assert result["ref_kind"] == "default"
    assert result["selection"] == "text-suffixes"
    assert fake.default_requests == 1
    assert fake.calls == [
        ("default", repo_grep._DEFAULT_BRANCH_OPERATION),
        ("files", SHA_A),
    ]
    assert fake.default_arguments == [
        {"projectKey": "DEMO", "repositorySlug": "widgets"}
    ]
    assert fake.reads == [("src/a.txt", SHA_A)]
    assert result["hits"] == [
        {"file": "src/a.txt", "line": 1, "text": "needle", "text_truncated": False}
    ]
    assert result["files_eligible"] == 1
    assert result["files_excluded"] == 0
    assert result["files_scanned"] == 1
    assert result["truncated"] is False
    assert result["complete"] is True


def test_explicit_branch_is_resolved_once_and_every_read_is_pinned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = simple_repository()
    install(monkeypatch, fake)

    result = repo_grep.grep_repository(
        BASE, REPO, "needle", token=TOKEN, at="feature/x", timeout_s=10.0
    )

    assert result["commit"] == SHA_A
    assert result["at"] == "feature/x"
    assert result["ref_kind"] == "branch"
    assert result["selection"] == "text-suffixes"
    assert fake.branch_requests == 1
    assert fake.calls == [
        ("branch", "feature/x"),
        ("tag", "feature/x"),
        ("files", SHA_A),
    ]
    assert fake.reads == [("src/a.txt", SHA_A)]


def test_full_commit_is_verified_and_no_branch_listing_is_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = simple_repository()
    fake.branch = None
    fake.commit = SHA_B
    install(monkeypatch, fake)

    result = repo_grep.grep_repository(
        BASE, REPO, "needle", token=TOKEN, at=SHA_B, timeout_s=10.0
    )

    assert result["commit"] == SHA_B
    assert result["at"] == SHA_B
    assert result["ref_kind"] == "commit"
    assert result["selection"] == "text-suffixes"
    assert fake.commit_requests == [SHA_B]
    assert fake.branch_requests == 0
    assert fake.calls == [("commit", SHA_B), ("files", SHA_B)]
    assert fake.reads == [("src/a.txt", SHA_B)]


def test_named_tag_checks_both_namespaces_and_pins_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeRepository()
    fake.tags = {"release-1": tag_object(SHA_B)}
    fake.paths = ["src/a.txt"]
    fake.files = {"src/a.txt": "needle\n"}
    install(monkeypatch, fake)

    result = repo_grep.grep_repository(
        BASE, REPO, "needle", token=TOKEN, at="release-1", timeout_s=10.0
    )

    assert result["commit"] == SHA_B
    assert result["ref_kind"] == "tag"
    assert fake.branch_requests == 1
    assert fake.tag_requests == ["release-1"]
    assert fake.calls == [
        ("branch", "release-1"),
        ("tag", "release-1"),
        ("files", SHA_B),
    ]
    assert fake.reads == [("src/a.txt", SHA_B)]


def test_qualified_tag_does_not_look_up_a_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeRepository()
    fake.tags = {"release-1": tag_object(SHA_B)}
    fake.paths = ["src/a.txt"]
    fake.files = {"src/a.txt": "needle\n"}
    install(monkeypatch, fake)

    result = repo_grep.grep_repository(
        BASE,
        REPO,
        "needle",
        token=TOKEN,
        at="refs/tags/release-1",
        timeout_s=10.0,
    )

    assert result["commit"] == SHA_B
    assert result["ref_kind"] == "tag"
    assert fake.branch_requests == 0
    assert fake.tag_requests == ["release-1"]
    assert fake.calls == [("tag", "release-1"), ("files", SHA_B)]


def test_qualified_branch_does_not_look_up_a_tag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeRepository()
    fake.branch = feature_branch()
    fake.paths = ["src/a.txt"]
    fake.files = {"src/a.txt": "needle\n"}
    install(monkeypatch, fake)

    result = repo_grep.grep_repository(
        BASE,
        REPO,
        "needle",
        token=TOKEN,
        at="refs/heads/feature/x",
        timeout_s=10.0,
    )

    assert result["commit"] == SHA_A
    assert result["ref_kind"] == "branch"
    assert fake.branch_requests == 1
    assert fake.tag_requests == []
    assert fake.calls == [("branch", "feature/x"), ("files", SHA_A)]


@pytest.mark.parametrize(
    ("identifier", "display_id"),
    [
        ("v1", "refs/tags/v1"),
        ("refs/tags/v1", "v1"),
        ("refs/tags/v1", "refs/tags/v1"),
        ("v1", "v1"),
    ],
    ids=[
        "short-id-prefixed-display",
        "prefixed-id-short-display",
        "both-prefixed",
        "both-short",
    ],
)
def test_tag_identity_prefix_variants_are_accepted(
    monkeypatch: pytest.MonkeyPatch, identifier: str, display_id: str
) -> None:
    fake = FakeRepository()
    fake.tags = {
        "v1": tag_object(
            SHA_B, name="v1", identifier=identifier, display_id=display_id
        )
    }
    fake.paths = ["src/a.txt"]
    fake.files = {"src/a.txt": "needle\n"}
    install(monkeypatch, fake)

    result = repo_grep.grep_repository(
        BASE,
        REPO,
        "needle",
        token=TOKEN,
        at="refs/tags/v1",
        timeout_s=10.0,
    )

    assert result["commit"] == SHA_B
    assert result["ref_kind"] == "tag"
    assert fake.branch_requests == 0
    assert fake.tag_requests == ["v1"]
    assert fake.calls == [("tag", "v1"), ("files", SHA_B)]
    assert fake.reads == [("src/a.txt", SHA_B)]


def test_wrong_tag_identity_is_rejected_before_any_file_listing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeRepository()
    fake.tags = {
        "v1": tag_object(
            SHA_B, name="v1", identifier="v2", display_id="refs/tags/v2"
        )
    }
    fake.paths = ["src/a.txt"]
    install(monkeypatch, fake)

    with pytest.raises(AtlaWireError, match="tag identity"):
        repo_grep.grep_repository(
            BASE, REPO, "needle", token=TOKEN, at="refs/tags/v1"
        )

    assert fake.calls == [("tag", "v1")]
    assert fake.reads == []


@pytest.mark.parametrize(
    "tag",
    [
        {"latestCommit": SHA_B},
        {"id": None, "displayId": None, "latestCommit": SHA_B},
        {"id": "", "displayId": "refs/tags/v1", "latestCommit": SHA_B},
        {"id": "v1", "displayId": "", "latestCommit": SHA_B},
        {"id": 7, "displayId": "refs/tags/v1", "latestCommit": SHA_B},
        {"id": "v1", "displayId": {"x": 1}, "latestCommit": SHA_B},
    ],
    ids=[
        "missing-both",
        "both-null",
        "empty-id-with-match",
        "match-with-empty-display",
        "wrong-id-type-with-match",
        "match-with-wrong-display-type",
    ],
)
def test_unusable_tag_identity_is_rejected_before_listing(
    monkeypatch: pytest.MonkeyPatch, tag: dict[str, object]
) -> None:
    fake = FakeRepository()
    fake.tags = {"v1": tag}
    fake.paths = ["src/a.txt"]
    install(monkeypatch, fake)

    with pytest.raises(AtlaWireError, match="tag identity"):
        repo_grep.grep_repository(
            BASE, REPO, "needle", token=TOKEN, at="refs/tags/v1"
        )

    assert fake.calls == [("tag", "v1")]
    assert fake.reads == []


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
    monkeypatch: pytest.MonkeyPatch, field: str, value: str
) -> None:
    fake = FakeRepository()
    fake.tags = {"v1": {field: value, "latestCommit": SHA_B}}
    fake.paths = ["src/a.txt"]
    fake.files = {"src/a.txt": "needle\n"}
    install(monkeypatch, fake)

    result = repo_grep.grep_repository(
        BASE, REPO, "needle", token=TOKEN, at="refs/tags/v1", timeout_s=10.0
    )

    assert result["commit"] == SHA_B
    assert result["ref_kind"] == "tag"
    assert fake.tag_requests == ["v1"]
    assert fake.calls == [("tag", "v1"), ("files", SHA_B)]
    assert fake.reads == [("src/a.txt", SHA_B)]


def test_literal_refs_tags_short_name_is_accepted_and_pinned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeRepository()
    fake.tags = {
        "refs/tags/v1": tag_object(
            SHA_B,
            name="refs/tags/v1",
            identifier="refs/tags/refs/tags/v1",
            display_id="refs/tags/v1",
        )
    }
    fake.paths = ["src/a.txt"]
    fake.files = {"src/a.txt": "needle\n"}
    install(monkeypatch, fake)

    result = repo_grep.grep_repository(
        BASE,
        REPO,
        "needle",
        token=TOKEN,
        at="refs/tags/refs/tags/v1",
        timeout_s=10.0,
    )

    assert result["commit"] == SHA_B
    assert result["ref_kind"] == "tag"
    assert fake.tag_requests == ["refs/tags/v1"]
    assert fake.calls == [("tag", "refs/tags/v1"), ("files", SHA_B)]
    assert fake.reads == [("src/a.txt", SHA_B)]


@pytest.mark.parametrize(
    ("identifier", "display_id"),
    [
        ("refs/tags/refs/tags/v1", "refs/tags/v2"),
        ("v1", "refs/tags/v1"),
        ("refs/tags/refs/tags/v1", "v1"),
    ],
    ids=[
        "full-id-wrong-display",
        "wrong-id-valid-display",
        "full-id-short-wrong-display",
    ],
)
def test_literal_refs_tags_name_identity_mismatch_is_rejected(
    monkeypatch: pytest.MonkeyPatch, identifier: str, display_id: str
) -> None:
    fake = FakeRepository()
    fake.tags = {
        "refs/tags/v1": tag_object(
            SHA_B,
            name="refs/tags/v1",
            identifier=identifier,
            display_id=display_id,
        )
    }
    fake.paths = ["src/a.txt"]
    install(monkeypatch, fake)

    with pytest.raises(AtlaWireError, match="tag identity"):
        repo_grep.grep_repository(
            BASE,
            REPO,
            "needle",
            token=TOKEN,
            at="refs/tags/refs/tags/v1",
        )

    assert fake.calls == [("tag", "refs/tags/v1")]
    assert fake.reads == []


@pytest.mark.parametrize(
    ("identifier", "display_id"),
    [
        ("v1", "refs/tags/v2"),
        ("v2", "refs/tags/v1"),
        ("v1", "refs/heads/v1"),
        ("refs/heads/v1", "refs/tags/v1"),
    ],
    ids=[
        "id-matches-display-wrong",
        "display-matches-id-wrong",
        "display-wrong-namespace",
        "id-wrong-namespace",
    ],
)
def test_contradictory_tag_identities_are_rejected_before_listing(
    monkeypatch: pytest.MonkeyPatch, identifier: str, display_id: str
) -> None:
    fake = FakeRepository()
    fake.tags = {
        "v1": tag_object(
            SHA_B, name="v1", identifier=identifier, display_id=display_id
        )
    }
    fake.paths = ["src/a.txt"]
    install(monkeypatch, fake)

    with pytest.raises(AtlaWireError, match="tag identity"):
        repo_grep.grep_repository(
            BASE, REPO, "needle", token=TOKEN, at="refs/tags/v1"
        )

    assert fake.calls == [("tag", "v1")]
    assert fake.reads == []


def test_branch_and_tag_with_the_same_name_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeRepository()
    fake.branch = feature_branch()
    fake.tags = {"feature/x": tag_object(SHA_B, name="feature/x")}
    fake.paths = ["src/a.txt"]
    install(monkeypatch, fake)

    with pytest.raises(AtlaWireError, match="both a branch and a tag"):
        repo_grep.grep_repository(
            BASE, REPO, "needle", token=TOKEN, at="feature/x"
        )

    assert fake.calls == [("branch", "feature/x"), ("tag", "feature/x")]
    assert fake.reads == []


def test_tag_without_a_full_commit_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeRepository()
    fake.tags = {"release-1": tag_object(None)}
    fake.paths = ["src/a.txt"]
    install(monkeypatch, fake)

    with pytest.raises(AtlaWireError, match="tag does not carry a full commit"):
        repo_grep.grep_repository(
            BASE, REPO, "needle", token=TOKEN, at="release-1"
        )

    assert fake.calls == [("branch", "release-1"), ("tag", "release-1")]
    assert fake.reads == []


def test_a_non_404_tag_failure_is_not_treated_as_absence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeRepository()
    fake.tag_error = AtlaWireError("HTTP 500: request failed.")
    fake.paths = ["src/a.txt"]
    install(monkeypatch, fake)

    with pytest.raises(AtlaWireError, match="HTTP 500"):
        repo_grep.grep_repository(
            BASE, REPO, "needle", token=TOKEN, at="release-1"
        )

    assert fake.calls == [("branch", "release-1"), ("tag", "release-1")]
    assert fake.reads == []


@pytest.mark.parametrize(
    "ref",
    ["refs/remotes/origin/x", "refs/notes/x", "refs/headsx/x"],
    ids=["remote", "notes", "near-prefix"],
)
def test_other_ref_namespaces_are_rejected_before_any_adapter_call(
    monkeypatch: pytest.MonkeyPatch, ref: str
) -> None:
    fake = FakeRepository()
    install(monkeypatch, fake)

    with pytest.raises(AtlaWireError, match="refs/heads|refs/tags|not a full"):
        repo_grep.grep_repository(
            BASE, REPO, "needle", token=TOKEN, at=ref
        )

    assert fake.calls == []


def test_unqualified_name_unsafe_for_a_tag_path_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeRepository()
    install(monkeypatch, fake)

    with pytest.raises(AtlaWireError, match="cannot be checked as a tag"):
        repo_grep.grep_repository(
            BASE, REPO, "needle", token=TOKEN, at="feature/100%20"
        )

    assert fake.calls == []


def test_missing_branch_is_not_reported_as_an_empty_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = simple_repository()
    fake.branch = None
    install(monkeypatch, fake)

    with pytest.raises(
        AtlaWireError, match="not a full commit, branch, or tag"
    ):
        repo_grep.grep_repository(
            BASE, REPO, "needle", token=TOKEN, at="feature/missing"
        )

    assert fake.calls == [("branch", "feature/missing"), ("tag", "feature/missing")]
    assert fake.reads == []


def test_branch_without_a_full_commit_fails_before_listing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = simple_repository()
    fake.branch = feature_branch("deadbeef")
    install(monkeypatch, fake)

    with pytest.raises(AtlaWireError, match="full commit ID"):
        repo_grep.grep_repository(
            BASE, REPO, "needle", token=TOKEN, at="feature/x"
        )

    assert fake.calls == [("branch", "feature/x")]
    assert fake.reads == []


@pytest.mark.parametrize(
    ("default", "message"),
    [
        (None, "no default branch"),
        ({}, "full commit ID"),
        ({"latestCommit": None}, "full commit ID"),
        ({"latestCommit": "deadbeef"}, "full commit ID"),
        ({"latestCommit": 7}, "full commit ID"),
        ([], "default branch metadata"),
    ],
    ids=["204", "missing-commit", "null-commit", "short-commit", "wrong-type",
         "wrong-shape"],
)
def test_unresolvable_default_branch_fails_closed(
    monkeypatch: pytest.MonkeyPatch, default: object, message: str
) -> None:
    fake = FakeRepository()
    fake.default_branch = default
    fake.paths = ["src/a.txt"]
    install(monkeypatch, fake)

    with pytest.raises(AtlaWireError, match=message):
        repo_grep.grep_repository(BASE, REPO, "needle", token=TOKEN)

    assert fake.default_requests == 1
    assert fake.calls == [("default", repo_grep._DEFAULT_BRANCH_OPERATION)]
    assert fake.reads == []


def test_deadline_during_default_branch_resolution_fails_without_any_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeRepository()
    fake.default_branch = raw_default_branch()
    fake.paths = ["a.txt"]
    fake.files = {"a.txt": "needle"}
    fake.default_delay = 2.0
    install(monkeypatch, fake)

    with pytest.raises(AtlaWireError, match="budget"):
        repo_grep.grep_repository(
            BASE, REPO, "needle", token=TOKEN, timeout_s=1.0
        )

    assert fake.default_requests == 1
    assert fake.reads == []


@pytest.mark.parametrize(
    "paths", [[], ["assets/logo.png"]], ids=["empty", "excluded"]
)
def test_expired_listing_is_not_a_complete_result(
    monkeypatch: pytest.MonkeyPatch, paths: list[str]
) -> None:
    fake = FakeRepository()
    fake.default_branch = raw_default_branch()
    fake.paths = list(paths)
    fake.list_delay = 2.0
    install(monkeypatch, fake)

    with pytest.raises(AtlaWireError, match="budget"):
        repo_grep.grep_repository(
            BASE, REPO, "needle", token=TOKEN, timeout_s=1.0
        )

    assert fake.default_requests == 1
    assert fake.calls[-1] == ("files", SHA_A)
    assert fake.reads == []


def test_deadline_after_branch_lookup_prevents_the_tag_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeRepository()
    fake.branch = feature_branch()
    fake.branch_delay = 2.0
    fake.tags = {"feature/x": tag_object(SHA_B, name="feature/x")}
    fake.paths = ["src/a.txt"]
    install(monkeypatch, fake)

    with pytest.raises(AtlaWireError, match="budget"):
        repo_grep.grep_repository(
            BASE,
            REPO,
            "needle",
            token=TOKEN,
            at="feature/x",
            timeout_s=1.0,
        )

    assert fake.branch_requests == 1
    assert fake.tag_requests == []
    assert fake.reads == []


def test_deadline_after_the_final_match_is_not_a_complete_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeRepository()
    fake.branch = feature_branch()
    fake.paths = ["src/a.txt"]
    fake.files = {"src/a.txt": "needle"}
    fake.match_delay = 2.0
    install(monkeypatch, fake)

    with pytest.raises(AtlaWireError, match="budget"):
        repo_grep.grep_repository(
            BASE,
            REPO,
            "needle",
            token=TOKEN,
            at="refs/heads/feature/x",
            timeout_s=1.0,
        )

    assert fake.reads == [("src/a.txt", SHA_A)]


def test_deadline_during_the_final_read_returns_no_partial_hits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeRepository()
    fake.branch = feature_branch()
    fake.paths = ["a.txt", "b.txt"]
    fake.files = {"a.txt": "needle", "b.txt": "needle"}
    fake.read_delay = 0.6
    install(monkeypatch, fake)

    with pytest.raises(AtlaWireError, match="budget"):
        repo_grep.grep_repository(
            BASE,
            REPO,
            "needle",
            token=TOKEN,
            at="refs/heads/feature/x",
            timeout_s=1.0,
        )

    assert fake.reads == [("a.txt", SHA_A), ("b.txt", SHA_A)]


def test_a_later_read_failure_is_fatal_instead_of_a_partial_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeRepository()
    fake.branch = feature_branch()
    fake.paths = ["a.txt", "b.txt"]
    fake.files = {"a.txt": "needle", "b.txt": "needle"}
    fake.fail_reads = {"a.txt"}
    install(monkeypatch, fake)

    with pytest.raises(AtlaWireError, match="aborted without a result"):
        repo_grep.grep_repository(
            BASE,
            REPO,
            "needle",
            token=TOKEN,
            at="refs/heads/feature/x",
        )

    assert fake.reads == [("a.txt", SHA_A)]


def test_hit_limit_reports_truncation_instead_of_completeness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeRepository()
    fake.branch = feature_branch()
    fake.paths = ["a.txt", "b.txt"]
    fake.files = {"a.txt": "needle", "b.txt": "needle"}
    install(monkeypatch, fake)

    result = repo_grep.grep_repository(
        BASE,
        REPO,
        "needle",
        token=TOKEN,
        at="refs/heads/feature/x",
        limit=1,
    )

    assert result["hits"] == [
        {
            "file": "a.txt",
            "line": 1,
            "text": "needle",
            "text_truncated": False,
        }
    ]
    assert result["ref_kind"] == "branch"
    assert result["selection"] == "text-suffixes"
    assert result["truncated"] is True
    assert result["complete"] is False
    assert result["files_eligible"] == 2
    assert result["files_excluded"] == 0
    assert result["files_scanned"] == 1
    assert fake.reads == [("a.txt", SHA_A)]


def test_scan_without_a_cap_reports_completeness_and_exact_lines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeRepository()
    fake.branch = feature_branch()
    fake.paths = ["a.txt", "b.txt"]
    fake.files = {"a.txt": "needle\nx", "b.txt": "no\nneedle"}
    install(monkeypatch, fake)

    result = repo_grep.grep_repository(
        BASE,
        REPO,
        "needle",
        token=TOKEN,
        at="refs/heads/feature/x",
        limit=10,
    )

    assert result["hits"] == [
        {"file": "a.txt", "line": 1, "text": "needle", "text_truncated": False},
        {"file": "b.txt", "line": 2, "text": "needle", "text_truncated": False},
    ]
    assert result["files_eligible"] == 2
    assert result["files_excluded"] == 0
    assert result["files_scanned"] == 2
    assert result["truncated"] is False
    assert result["complete"] is True
    assert fake.reads == [("a.txt", SHA_A), ("b.txt", SHA_A)]


def test_hit_text_is_capped_and_short_text_is_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeRepository()
    fake.branch = feature_branch()
    long_line = "x" * 350 + "needle" + "y" * 50
    fake.paths = ["long.txt", "short.txt"]
    fake.files = {"long.txt": long_line, "short.txt": "short needle"}
    install(monkeypatch, fake)

    result = repo_grep.grep_repository(
        BASE,
        REPO,
        "needle",
        token=TOKEN,
        at="refs/heads/feature/x",
        limit=10,
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
    assert len(long_line) > repo_grep.HIT_TEXT_LIMIT
    assert result["complete"] is True


def test_no_pattern_lists_all_paths_without_reads_or_regex(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeRepository()
    fake.branch = feature_branch()
    fake.paths = ["Makefile", "assets/logo.png", "src/A.java"]
    install(monkeypatch, fake)

    result = repo_grep.grep_repository(
        BASE,
        REPO,
        pattern=None,
        token=TOKEN,
        at="refs/heads/feature/x",
        timeout_s=10.0,
    )

    assert result["engine"] == "listing"
    assert result["selection"] == "all-paths"
    assert result["files"] == fake.paths
    assert result["files_eligible"] == 3
    assert result["files_excluded"] == 0
    assert result["files_scanned"] == 0
    assert result["hits"] == []
    assert result["truncated"] is False
    assert result["complete"] is True
    assert fake.reads == []
    assert fake.match_calls == []
    assert fake.validation_calls == 0
    assert fake.calls == [("branch", "feature/x"), ("files", SHA_A)]


@pytest.mark.parametrize(
    ("limit", "truncated", "file_count"),
    [(1, True, 1), (2, False, 2), (3, False, 2)],
    ids=["below", "exact", "above"],
)
def test_no_pattern_applies_filters_and_reports_the_output_cap(
    monkeypatch: pytest.MonkeyPatch,
    limit: int,
    truncated: bool,
    file_count: int,
) -> None:
    fake = FakeRepository()
    fake.branch = feature_branch()
    fake.paths = ["src/a.py", "src/b.py", "docs/c.py", "src/d.txt"]
    install(monkeypatch, fake)

    result = repo_grep.grep_repository(
        BASE,
        REPO,
        pattern=None,
        token=TOKEN,
        at="refs/heads/feature/x",
        path="src",
        glob="*.py",
        limit=limit,
    )

    assert result["engine"] == "listing"
    assert result["selection"] == "explicit"
    assert result["files"] == ["src/a.py", "src/b.py"][:file_count]
    assert result["files_eligible"] == 2
    assert result["files_excluded"] == 2
    assert result["files_scanned"] == 0
    assert result["hits"] == []
    assert result["truncated"] is truncated
    assert result["complete"] is not truncated
    assert fake.reads == []
    assert fake.match_calls == []
    assert fake.validation_calls == 0


def test_no_pattern_missing_branch_fails_before_listing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeRepository()
    fake.branch = None
    install(monkeypatch, fake)

    with pytest.raises(AtlaWireError, match="not a full commit, branch, or tag"):
        repo_grep.grep_repository(
            BASE, REPO, pattern=None, token=TOKEN, at="feature/missing"
        )

    assert fake.calls == [("branch", "feature/missing"), ("tag", "feature/missing")]
    assert fake.reads == []


def test_no_pattern_default_204_fails_before_listing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeRepository()
    fake.default_branch = None
    install(monkeypatch, fake)

    with pytest.raises(AtlaWireError, match="no default branch"):
        repo_grep.grep_repository(BASE, REPO, pattern=None, token=TOKEN)

    assert fake.calls == [("default", repo_grep._DEFAULT_BRANCH_OPERATION)]
    assert fake.reads == []


def test_no_pattern_invalid_ref_namespace_is_rejected_before_listing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeRepository()
    install(monkeypatch, fake)

    with pytest.raises(AtlaWireError, match="Only refs/heads"):
        repo_grep.grep_repository(
            BASE,
            REPO,
            pattern=None,
            token=TOKEN,
            at="refs/remotes/origin/x",
        )

    assert fake.calls == []
    assert fake.reads == []


def test_no_eligible_file_is_a_complete_empty_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeRepository()
    fake.branch = feature_branch()
    fake.paths = ["docs/a.md"]
    install(monkeypatch, fake)

    result = repo_grep.grep_repository(
        BASE,
        REPO,
        "needle",
        token=TOKEN,
        at="refs/heads/feature/x",
        glob="*.py",
    )

    assert result["hits"] == []
    assert result["selection"] == "explicit"
    assert result["files_eligible"] == 0
    assert result["files_excluded"] == 1
    assert result["files_scanned"] == 0
    assert result["truncated"] is False
    assert result["complete"] is True
    assert fake.reads == []


def test_path_and_glob_filters_select_the_files_that_are_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeRepository()
    fake.branch = feature_branch()
    fake.paths = ["src/a.py", "src/b.txt", "docs/c.py", "srcery/d.py"]
    fake.files = {
        "src/a.py": "needle",
        "src/b.txt": "needle",
        "docs/c.py": "needle",
        "srcery/d.py": "needle",
    }
    install(monkeypatch, fake)

    result = repo_grep.grep_repository(
        BASE,
        REPO,
        "needle",
        token=TOKEN,
        at="refs/heads/feature/x",
        path="src",
        glob="*.py",
    )

    assert result["path"] == "src"
    assert result["glob"] == "*.py"
    assert result["selection"] == "explicit"
    assert result["files_eligible"] == 1
    assert result["files_excluded"] == 3
    assert fake.reads == [("src/a.py", SHA_A)]
    assert result["complete"] is True


def test_case_sensitivity_is_passed_to_every_file_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeRepository()
    fake.branch = feature_branch()
    fake.paths = ["a.txt"]
    fake.files = {"a.txt": "Needle"}
    install(monkeypatch, fake)

    result = repo_grep.grep_repository(
        BASE,
        REPO,
        "needle",
        token=TOKEN,
        at="refs/heads/feature/x",
        ignore_case=False,
    )

    assert result["hits"] == []
    assert result["ignore_case"] is False
    assert result["complete"] is True
    assert fake.match_calls[0][0] == "needle"
