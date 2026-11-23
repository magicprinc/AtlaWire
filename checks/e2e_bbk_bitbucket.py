"""Opt-in end-to-end checks: AtlaWire reads a real Bitbucket server, and every
observed result is validated against the BBK (``bbk`` package) function contract.

Run only by explicit path, with the gate set and with the saved BBK credential
pair already configured::

    C:/Python315/python.exe -B -m pytest -q -p no:cacheprovider checks/e2e_bbk_bitbucket.py

with ``ATLAWIRE_E2E_BBK_BITBUCKET=1`` in the environment. Without the gate the
whole module is skipped and contacts nothing, so it never joins the ordinary
``tests`` run.

The fixture data is not hardcoded: real project, repository, file, commit and
pull request identifiers are discovered through AtlaWire's own narrow read
commands, and the defaults come from one visible project of the authenticated
user. Read-only throughout: every child process runs one command from a fixed
read-only allowlist, with ``shell=False`` and stdin closed, so this module
cannot change a server, send chat messages, or edit schedules.

Coverage, BBK contract -> AtlaWire call (the AtlaWire JSON output is the same
projection the AtlaWire library function returns):

* ``bbk.bitbucket.search_code``          -> ``search`` (SearchRow)
* ``bbk.bitbucket.projects``             -> ``projects`` (Project)
* ``bbk.bitbucket.repos``                -> ``repos`` (Repository)
* ``bbk.bitbucket.list_files``           -> ``files`` (list[str], paged to the end)
* ``bbk.bitbucket.file_at``              -> ``file`` (exact text)
* ``bbk.bitbucket.pr``                   -> ``pr REPO ID show`` (raw PR object)
* ``bbk.bitbucket.pr_files``             -> ``pr REPO ID files`` (ChangedFile)
* ``bbk.bitbucket.pr_comments``          -> ``pr REPO ID comments`` (PullRequestComment)
* ``bbk.bitbucket.prs``                  -> ``prs`` (PullRequest)
* ``bbk.bitbucket.my_prs`` (dashboard)   -> ``my-prs`` (MyPullRequest)
* ``bbk.repo.ls``                        -> ``ls`` (DirectoryEntry)
* ``bbk.repo.blame``                     -> ``blame`` (BlameLine)
* ``bbk.repo.branches``                  -> ``branches`` (Branch)
* ``bbk.repo.commits``                   -> ``commits`` (Commit)
* ``bbk.repo.commit``                    -> ``commit`` (raw commit object)
* ``bbk.repo.pr_commits``                -> ``pr REPO ID commits`` (Commit)
* ``bbk.repo.find_repos``                -> ``find-repos`` (RepositoryMatch)
* ``bbk.repo_grep.grep_ex``              -> ``grep-repo`` (GrepResult)
* ``bbk.repo_grep.commit_changes``       -> ``commit-changes`` (ChangedFile)
* ``bbk.repo_grep.commit_diff``          -> ``commit-diff`` (review text)
* ``bbk.bitbucket.repos_with_extension`` -> ``scan-extension`` (ExtensionMatch)

Every check covers the observable BBK shape: the result type, the required
fields, the key sets, pagination when the endpoint pages, and the documented
"not partial" grip result. A dedicated check proves that the active token never
appears in any captured child stdout or stderr. Unexpected HTTP 401/403/429
stops the run with a fixed category instead of retrying.

Deliberately not covered here:

* ``bbk.attachments.attachment_download``: AtlaWire has ``attachment-get`` with
  the same contract, but no AtlaWire read lists attachment IDs, so an ID cannot
  be discovered without inventing one. Skip rather than guess.
* ``bbk.bitbucket.pr_diff`` and ``bbk.bitbucket.pr_file``: outside the
  requested contract set; AtlaWire exposes ``pr ... diff`` and ``pr ... file``.
* Multi-page pull request comments/commits were not observed on the discovered
  pull request (single page), so their terminal page is unproven here; the files
  listing and a scoped ``search --all`` do prove page following and a terminal
  page.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections.abc import Mapping, Sequence
from typing import Any

import pytest

GATE_ENV = "ATLAWIRE_E2E_BBK_BITBUCKET"
_PRODUCT = "bitbucket"
_STRIPPED_ENV = frozenset({"ATLAWIRE_BITBUCKET_URL", "ATLAWIRE_BITBUCKET_TOKEN"})
_CLI = (sys.executable, "-P", "-B", "-m", "atlawire")
_TIMEOUT_SECONDS = 120
_MAX_OUTPUT_BYTES = 16 * 1024 * 1024
_SEARCH_QUERY = "public class"
_SEARCH_EVERY_PAGE_LIMIT = 999
_MULTI_PAGE_FILES_PROBES = (2, 8)
_MAX_PROJECTS = 2
_MAX_REPOS = 8

_READ_COMMANDS = frozenset(
    {
        "projects",
        "repos",
        "files",
        "file",
        "pr",
        "prs",
        "my-prs",
        "search",
        "grep-repo",
        "ls",
        "blame",
        "branches",
        "commits",
        "commit",
        "commit-changes",
        "commit-diff",
        "find-repos",
        "scan-extension",
    }
)

_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f\ud800-\udfff]")
_AUTH_STATUS = re.compile(r"HTTP (401|403|429)\b")
_PAGE_LIMIT = re.compile(r"page limit reached", re.IGNORECASE)
_SHA = re.compile(r"[0-9A-Fa-f]{40}")
_PROJECT_KEY = re.compile(r"~?[A-Za-z0-9_][A-Za-z0-9_.-]*")
_REPOSITORY_SLUG = re.compile(r"[A-Za-z0-9_.-]+")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}(?: \d{2}:\d{2})?")
_PR_STATES = frozenset({"OPEN", "MERGED", "DECLINED"})
_MATCH_EVIDENCE = frozenset({"highlight", "context-only", "none"})
_DIRECTORY_TYPES = frozenset({"FILE", "DIRECTORY"})
_TEXT_SUFFIXES = frozenset(
    {
        ".java",
        ".kt",
        ".kts",
        ".groovy",
        ".py",
        ".js",
        ".ts",
        ".md",
        ".yml",
        ".yaml",
        ".json",
        ".xml",
        ".properties",
        ".gradle",
        ".txt",
        ".sql",
        ".sh",
        ".toml",
        ".html",
        ".css",
    }
)
_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]{7,}")

Row = dict[str, object]
State: dict[str, str | None] = {"stop": None}
_Token: list[str] = []
_Captured: list[str] = []

pytestmark = pytest.mark.skipif(
    os.environ.get(GATE_ENV) != "1",
    reason=f"opt-in live Bitbucket E2E; set {GATE_ENV}=1 to run",
)


# --------------------------------------------------------------- tiny helpers
def _fail(category: str) -> None:
    pytest.fail(category, pytrace=False)


def _require(condition: object, category: str) -> None:
    if not condition:
        _fail(category)


def _is_str(value: object) -> bool:
    return isinstance(value, str)


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _require_dict(value: object) -> Row:
    _require(isinstance(value, dict), "invalid_output")
    return value  # type: ignore[return-value]


def _require_list(value: object) -> list[object]:
    _require(isinstance(value, list), "invalid_output")
    return value  # type: ignore[return-value]


def _require_str(value: object) -> str:
    _require(isinstance(value, str) and bool(value), "invalid_output")
    return value  # type: ignore[return-value]


def _require_optional_str(value: object) -> str | None:
    _require(value is None or isinstance(value, str), "invalid_output")
    return value  # type: ignore[return-value]


def _require_keys(row: Mapping[str, object], keys: frozenset[str]) -> None:
    _require(set(row) == keys, "contract")


def _require_sha(value: object) -> str:
    _require(isinstance(value, str) and _SHA.fullmatch(value) is not None, "contract")
    return value  # type: ignore[return-value]


def _decode_json(raw: str) -> object:
    try:
        return json.loads(raw)
    except ValueError, RecursionError:
        _fail("invalid_output")


def _decode_json_rows(raw: str) -> list[Row]:
    values = _require_list(_decode_json(raw))
    rows: list[Row] = []
    for value in values:
        rows.append(_require_dict(value))
    return rows


def _child_env() -> dict[str, str]:
    """Ordinary OS settings only, so the child resolves its own credentials."""
    stripped = {name.upper() for name in _STRIPPED_ENV}
    environment = {
        name: value
        for name, value in os.environ.items()
        if name.upper() not in stripped
    }
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["PYTHONUTF8"] = "1"
    return environment


def _token() -> str:
    """Return the active token in memory only; it is never printed or logged."""
    if not _Token:
        try:
            from atlawire.credentials import load_saved_credentials

            saved = load_saved_credentials(_PRODUCT, allow_http_loopback=False)
        except Exception:  # noqa: BLE001 - fixed category; detail is never shown
            _fail("credentials")
        _Token.append(saved.token)
    return _Token[0]


def _check_plan(args: Sequence[str]) -> None:
    if not args or not all(isinstance(value, str) and value for value in args):
        _fail("invalid_plan")
    if args[0] not in _READ_COMMANDS:
        _fail("invalid_plan")
    if any(_CONTROL.search(value) for value in args):
        _fail("invalid_plan")


def _decode_output(data: object) -> str:
    _require(isinstance(data, bytes), "invalid_output")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        _fail("invalid_output")
    _require(len(text) <= _MAX_OUTPUT_BYTES, "invalid_output")
    return text


def _invoke(args: tuple[str, ...]) -> tuple[bool, str, str]:
    """Run one fixed read-only AtlaWire command.

    Returns ``(ok, stdout, stderr)``. A non-zero exit is returned so a check can
    assert a documented refusal, except 401/403/429, which stop the whole run.
    Captured output never leaks a token: a hit fails the run with a fixed
    category before it can be used.
    """
    if State["stop"] is not None:
        _fail(State["stop"])
    _check_plan(args)
    token = _token()
    try:
        completed = subprocess.run(
            [*_CLI, *args],
            env=_child_env(),
            capture_output=True,
            timeout=_TIMEOUT_SECONDS,
            check=False,
            shell=False,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        _fail("timeout")
    except OSError:
        _fail("cli_unavailable")
    stdout = _decode_output(completed.stdout)
    stderr = _decode_output(completed.stderr)
    _Captured.extend((stdout, stderr))
    if token in stdout or token in stderr:
        _fail("token_leak")
    if completed.returncode != 0:
        matched = _AUTH_STATUS.search(stderr) or _AUTH_STATUS.search(stdout)
        if matched is not None:
            category = f"auth:{matched.group(1)}"
            State["stop"] = category
            _fail(category)
    return completed.returncode == 0, stdout, stderr


def _expect_ok(args: tuple[str, ...]) -> str:
    ok, stdout, _ = _invoke(args)
    _require(ok, "unexpected_failure")
    return stdout


def _expect_json(args: tuple[str, ...]) -> object:
    return _decode_json(_expect_ok(args))


def _expect_rows(args: tuple[str, ...]) -> list[Row]:
    return _decode_json_rows(_expect_ok(args))


def _read_list(args: tuple[str, ...]) -> list[Row]:
    rows = _decode_json_rows(_expect_ok(args))
    _require(bool(rows), "oracle_mismatch")
    return rows


def _refused_with_page_limit(args: tuple[str, ...]) -> None:
    ok, _, stderr = _invoke(args)
    _require(not ok, "contract")
    _require(_PAGE_LIMIT.search(stderr) is not None, "contract")


# ------------------------------------------------------------------ discovery
def _discover_project() -> list[Row]:
    projects = _expect_rows(("projects", "--json", "--max-pages", "1"))
    _require(bool(projects), "oracle_mismatch")
    return projects


def _discover_container(projects: list[Row]) -> tuple[str, list[Row], dict[str, Any]]:
    for project in projects[:_MAX_PROJECTS]:
        key = _require_str(project.get("key"))
        repositories = _expect_rows(("repos", key, "--json", "--max-pages", "1"))
        if not repositories:
            continue
        files = _discover_files_fixtures(key, repositories)
        if files["paged"] is not None:
            return key, repositories, files
    _fail("fixture:no_multipage_files")
    raise AssertionError("unreachable")


def _is_text_path(path: object) -> bool:
    return (
        isinstance(path, str)
        and "." in path
        and (f".{path.rsplit('.', 1)[1].lower()}" in _TEXT_SUFFIXES)
    )


def _pick_text_path(paths: list[str]) -> str:
    for path in paths:
        if _is_text_path(path) and path.lower().endswith(".java"):
            return path
    for path in paths:
        if _is_text_path(path):
            return path
    _fail("fixture:no_text_file")
    raise AssertionError("unreachable")


def _discover_files_fixtures(project: str, repositories: list[Row]) -> dict[str, Any]:
    """Find a small repo and a repository whose file list needs a second page."""
    small: dict[str, Any] | None = None
    paged: dict[str, Any] | None = None
    for row in repositories[:_MAX_REPOS]:
        slug = _require_str(row.get("slug"))
        repository = f"{project}/{slug}"
        ok, stdout, stderr = _invoke(
            ("files", repository, "--json", "--max-pages", "1")
        )
        if ok:
            paths = _as_paths(_decode_json(stdout))
            if small is None and any(_is_text_path(path) for path in paths):
                small = {"repo": slug, "paths": paths}
            continue
        _require(_PAGE_LIMIT.search(stderr) is not None, "unexpected_failure")
        for pages in _MULTI_PAGE_FILES_PROBES:
            ok, stdout, stderr = _invoke(
                ("files", repository, "--json", "--max-pages", str(pages))
            )
            if ok:
                paths = _as_paths(_decode_json(stdout))
                if len(paths) > 100:
                    paged = {"repo": slug, "paths": paths, "pages": pages}
                    break
            else:
                _require(_PAGE_LIMIT.search(stderr) is not None, "unexpected_failure")
        if paged is not None:
            break
    return {"small": small, "paged": paged}


def _as_paths(value: object) -> list[str]:
    paths: list[str] = []
    for item in _require_list(value):
        paths.append(_require_str(item))
    return paths


def _discover_file(project: str, paged: Mapping[str, Any], path: str) -> dict[str, Any]:
    repository = f"{project}/{paged['repo']}"
    commits = _read_list(("commits", repository, "--limit", "1", "--json"))
    sha = _require_sha(commits[0].get("hash"))
    text = _expect_ok(("file", repository, path, "--at", sha))
    blame = _expect_rows(("blame", repository, path, "--at", sha, "--json"))
    directory = path.rsplit("/", 1)[0] if "/" in path else ""
    ls_args: tuple[str, ...] = (
        ("ls", repository, directory, "--at", sha, "--json")
        if directory
        else ("ls", repository, "--at", sha, "--json")
    )
    entries = _expect_rows(ls_args)
    return {
        "repo": paged["repo"],
        "path": path,
        "sha": sha,
        "text": text,
        "blame": blame,
        "entries": entries,
        "commits": commits,
    }


def _discover_history(project: str, repo_slug: str) -> dict[str, Any]:
    repository = f"{project}/{repo_slug}"
    rows = _read_list(("commits", repository, "--limit", "10", "--json"))
    for row in rows[:5]:
        sha = _require_sha(row.get("hash"))
        commit = _require_dict(_expect_json(("commit", repository, sha, "--json")))
        parents = commit.get("parents")
        if not isinstance(parents, list) or len(parents) > 1:
            continue
        changes = _expect_rows(("commit-changes", repository, sha, "--json"))
        if changes:
            return {"sha": sha, "object": commit, "changes": changes, "rows": rows}
    _fail("fixture:no_nonmerge_commit")
    raise AssertionError("unreachable")


def _discover_pull_request(project: str, repositories: list[Row]) -> dict[str, Any]:
    for row in repositories[:_MAX_REPOS]:
        slug = _require_str(row.get("slug"))
        repository = f"{project}/{slug}"
        pull_requests = _expect_rows(
            ("prs", repository, "--state", "ALL", "--limit", "10", "--json")
        )
        if not pull_requests:
            continue
        for pull_request in pull_requests[:4]:
            identifier = pull_request.get("id")
            _require(_is_int(identifier), "invalid_output")
            comments = _expect_rows(
                ("pr", repository, str(identifier), "comments", "--json")
            )
            if not comments:
                continue
            return {
                "repo": slug,
                "id": identifier,
                "show": _require_dict(
                    _expect_json(("pr", repository, str(identifier), "show"))
                ),
                "files": _expect_rows(
                    ("pr", repository, str(identifier), "files", "--json")
                ),
                "comments": comments,
                "commits": _expect_rows(
                    ("pr", repository, str(identifier), "commits", "--json")
                ),
                "prs": pull_requests,
            }
    _fail("fixture:pr_with_comments")
    raise AssertionError("unreachable")


def _discover_search_and_grep(
    project: str, discovered: dict[str, Any]
) -> dict[str, Any]:
    rows = _read_list(("search", _SEARCH_QUERY, "--limit", "5", "--json"))
    repository = f"{rows[0]['project']}/{rows[0]['repository']}"
    scoped = _read_list(
        ("search", _SEARCH_QUERY, "--repo", repository, "--limit", "5", "--json")
    )
    scoped_all = _expect_rows(
        (
            "search",
            _SEARCH_QUERY,
            "--repo",
            repository,
            "--all",
            "--limit",
            str(_SEARCH_EVERY_PAGE_LIMIT),
            "--json",
        )
    )
    file_info = discovered["file"]
    pattern = _literal_pattern(file_info["text"])
    grep = _require_dict(
        _expect_json(
            (
                "grep-repo",
                f"{project}/{file_info['repo']}",
                pattern,
                "--glob",
                file_info["path"],
                "--ref",
                file_info["sha"],
                "--limit",
                "20",
                "--json",
            )
        )
    )
    listing = _require_dict(
        _expect_json(
            (
                "grep-repo",
                f"{project}/{file_info['repo']}",
                "--glob",
                file_info["path"],
                "--ref",
                file_info["sha"],
                "--limit",
                "20",
                "--json",
            )
        )
    )
    return {
        "rows": rows,
        "scoped": scoped,
        "scoped_all": scoped_all,
        "pattern": pattern,
        "grep": grep,
        "listing": listing,
    }


def _literal_pattern(text: str) -> str:
    for line in text.splitlines():
        matched = _WORD.search(line)
        if matched is not None:
            return re.escape(matched.group(0))
    _fail("fixture:no_grep_term")
    raise AssertionError("unreachable")


def _discover_extra(project: str, discovered: dict[str, Any]) -> dict[str, Any]:
    paged_repository = f"{project}/{discovered['paged']['repo']}"
    branches = _expect_rows(
        ("branches", paged_repository, "--json", "--max-pages", "2")
    )
    needle = discovered["paged"]["repo"]
    if discovered["small"] is not None:
        needle = discovered["small"]["repo"]
    found = _expect_rows(("find-repos", needle, "--json", "--limit", "10"))
    scan = _discover_extension_scan(project)
    return {"branches": branches, "find": found, "scan": scan}


def _discover_extension_scan(project: str) -> list[Row] | None:
    for pages in (2, 8):
        ok, stdout, stderr = _invoke(
            (
                "scan-extension",
                "--project",
                project,
                "--ext",
                ".java",
                "--max-pages",
                str(pages),
                "--workers",
                "2",
                "--json",
            )
        )
        if ok:
            return _decode_json_rows(stdout)
        _require(_PAGE_LIMIT.search(stderr) is not None, "unexpected_failure")
    return None


@pytest.fixture(scope="session")
def live() -> dict[str, Any]:
    """Discover real fixtures through AtlaWire narrow read commands."""
    projects = _discover_project()
    project_key, repositories, files = _discover_container(projects)
    path = _pick_text_path(files["paged"]["paths"])
    discovered: dict[str, Any] = {
        "project": project_key,
        "projects": projects,
        "repositories": repositories,
        "small": files["small"],
        "paged": files["paged"],
    }
    discovered["file"] = _discover_file(project_key, files["paged"], path)
    discovered["history"] = _discover_history(project_key, files["paged"]["repo"])
    discovered["history"]["diff"] = _expect_ok(
        (
            "commit-diff",
            f"{project_key}/{files['paged']['repo']}",
            discovered["history"]["sha"],
        )
    )
    changed_path = _require_str(discovered["history"]["changes"][0].get("path"))
    discovered["history"]["path"] = changed_path
    discovered["history"]["path_diff"] = _expect_ok(
        (
            "commit-diff",
            f"{project_key}/{files['paged']['repo']}",
            discovered["history"]["sha"],
            changed_path,
        )
    )
    discovered["pull_request"] = _discover_pull_request(project_key, repositories)
    discovered.update(_discover_search_and_grep(project_key, discovered))
    discovered.update(_discover_extra(project_key, discovered))
    return discovered


# ------------------------------------------------------------------ contracts
_PROJECT_KEYS = frozenset({"key", "name", "public", "description", "url"})
_REPOSITORY_KEYS = frozenset({"slug", "name", "state", "public"})
_CHANGED_FILE_KEYS = frozenset({"path", "type", "node"})
_COMMENT_KEYS = frozenset({"id", "author", "path", "line", "text", "created"})
_PULL_REQUEST_KEYS = frozenset(
    {"id", "title", "state", "author", "from", "to", "updated"}
)
_MY_PULL_REQUEST_KEYS = frozenset(
    {"repo", "id", "title", "state", "author", "reviewers_inactive", "created"}
)
_BRANCH_KEYS = frozenset({"name", "id", "commit", "default"})
_COMMIT_KEYS = frozenset({"hash", "date", "author", "message"})
_DIRECTORY_KEYS = frozenset({"path", "type", "size"})
_BLAME_KEYS = frozenset({"line", "author", "email", "date", "commit"})
_SEARCH_KEYS = frozenset(
    {"project", "repository", "file", "hitCount", "matchEvidence", "hits", "context"}
)
_SEARCH_LINE_KEYS = frozenset({"line", "text"})
_GREP_KEYS = frozenset(
    {
        "engine",
        "repo",
        "commit",
        "at",
        "ref_kind",
        "glob",
        "path",
        "selection",
        "ignore_case",
        "files",
        "files_eligible",
        "files_excluded",
        "files_scanned",
        "hits",
        "truncated",
        "complete",
        "status",
        "message",
    }
)
_GREP_HIT_KEYS = frozenset({"file", "line", "text", "text_truncated"})
_EXTENSION_KEYS = frozenset({"project", "repository", "files", "matched", "sample"})


def _check_project_rows(rows: list[Row]) -> None:
    keys: set[str] = set()
    for row in rows:
        _require_keys(row, _PROJECT_KEYS)
        key = _require_str(row.get("key"))
        _require(_PROJECT_KEY.fullmatch(key) is not None, "contract")
        _require_optional_str(row.get("name"))
        _require(
            row.get("public") is None or isinstance(row.get("public"), bool), "contract"
        )
        _require_optional_str(row.get("description"))
        url = _require_optional_str(row.get("url"))
        if url is not None:
            _require(key in url, "contract")
        _require(key not in keys, "contract")
        keys.add(key)


def _check_repository_rows(rows: list[Row]) -> None:
    slugs: set[str] = set()
    for row in rows:
        _require_keys(row, _REPOSITORY_KEYS)
        slug = _require_str(row.get("slug"))
        _require(_REPOSITORY_SLUG.fullmatch(slug) is not None, "contract")
        _require_optional_str(row.get("name"))
        _require_optional_str(row.get("state"))
        _require(
            row.get("public") is None or isinstance(row.get("public"), bool), "contract"
        )
        _require(slug not in slugs, "contract")
        slugs.add(slug)


def _check_file_paths(paths: list[str]) -> None:
    _require(bool(paths), "oracle_mismatch")
    for path in paths:
        _require(path, "contract")
        _require(not path.startswith("/") and "\\" not in path, "contract")
        _require(
            all(part and part not in {".", ".."} for part in path.split("/")),
            "contract",
        )
    _require(len(set(paths)) == len(paths), "contract")


def _check_changed_files(rows: list[Row]) -> None:
    paths: set[str] = set()
    for row in rows:
        _require_keys(row, _CHANGED_FILE_KEYS)
        path = _require_str(row.get("path"))
        _require_optional_str(row.get("type"))
        _require_optional_str(row.get("node"))
        _require(path not in paths, "contract")
        paths.add(path)


def _check_comment_rows(rows: list[Row]) -> None:
    identifiers: set[int] = set()
    for row in rows:
        _require_keys(row, _COMMENT_KEYS)
        identifier = row.get("id")
        _require(_is_int(identifier) and identifier > 0, "contract")
        _require(identifier not in identifiers, "contract")
        identifiers.add(identifier)
        _require_optional_str(row.get("author"))
        _require_optional_str(row.get("path"))
        _require(isinstance(row.get("text"), str), "contract")
        _require(row.get("created") is None or _is_int(row.get("created")), "contract")
        line = row.get("line")
        _require(line is None or (_is_int(line) and line >= 1), "contract")


def _check_commit_rows(rows: list[Row], *, newest_first: bool = True) -> None:
    hashes: set[str] = set()
    dates: list[str] = []
    for row in rows:
        _require_keys(row, _COMMIT_KEYS)
        sha = _require_sha(row.get("hash"))
        _require(sha not in hashes, "contract")
        hashes.add(sha)
        _require_optional_str(row.get("author"))
        _require(isinstance(row.get("message"), str), "contract")
        date = _require_optional_str(row.get("date"))
        if date is not None:
            _require(_DATE.fullmatch(date) is not None, "contract")
            dates.append(date)
    if newest_first:
        _require(dates == sorted(dates, reverse=True), "contract")


def _check_pull_request_rows(rows: list[Row]) -> None:
    identifiers: set[int] = set()
    for row in rows:
        _require_keys(row, _PULL_REQUEST_KEYS)
        identifier = row.get("id")
        _require(_is_int(identifier) and identifier > 0, "contract")
        _require(identifier not in identifiers, "contract")
        identifiers.add(identifier)
        _require_str(row.get("title"))
        _require(row.get("state") in _PR_STATES, "contract")
        _require_optional_str(row.get("author"))
        _require_optional_str(row.get("from"))
        _require_optional_str(row.get("to"))
        _require(row.get("updated") is None or _is_int(row.get("updated")), "contract")


def _check_my_pull_request_rows(rows: list[Row]) -> None:
    pairs: set[tuple[str, int]] = set()
    for row in rows:
        _require_keys(row, _MY_PULL_REQUEST_KEYS)
        repository = _require_str(row.get("repo"))
        project, separator, slug = repository.partition("/")
        _require(
            bool(separator) and _PROJECT_KEY.fullmatch(project) is not None, "contract"
        )
        _require(_REPOSITORY_SLUG.fullmatch(slug) is not None, "contract")
        identifier = row.get("id")
        _require(_is_int(identifier) and identifier > 0, "contract")
        _require((repository, identifier) not in pairs, "contract")
        pairs.add((repository, identifier))
        _require_str(row.get("title"))
        _require(row.get("state") in _PR_STATES, "contract")
        _require_optional_str(row.get("author"))
        inactive = row.get("reviewers_inactive")
        _require(
            isinstance(inactive, list) and all(_is_str(v) for v in inactive), "contract"
        )
        _require(row.get("created") is None or _is_int(row.get("created")), "contract")


def _check_branch_rows(rows: list[Row]) -> None:
    names: set[str] = set()
    defaults = 0
    for row in rows:
        _require_keys(row, _BRANCH_KEYS)
        name = _require_str(row.get("name"))
        identifier = _require_str(row.get("id"))
        _require(identifier == f"refs/heads/{name}", "contract")
        _require(name not in names, "contract")
        names.add(name)
        commit = row.get("commit")
        _require(commit is None or _is_str(commit), "contract")
        if commit is not None:
            _require_sha(commit)
        _require(isinstance(row.get("default"), bool), "contract")
        defaults += int(bool(row.get("default")))
    _require(defaults == 1, "contract")


def _check_directory_rows(rows: list[Row], expected_file: str) -> None:
    _require(bool(rows), "oracle_mismatch")
    paths: set[str] = set()
    for row in rows:
        _require_keys(row, _DIRECTORY_KEYS)
        path = _require_str(row.get("path"))
        _require(path not in paths, "contract")
        paths.add(path)
        _require(row.get("type") in _DIRECTORY_TYPES, "contract")
        size = row.get("size")
        _require(size is None or (_is_int(size) and size >= 0), "contract")
    # The browse children carry the entry name relative to the listed directory
    # (the same ``path.toString`` projection BBK ls returns).
    _require(expected_file.rsplit("/", 1)[-1] in paths, "oracle_mismatch")


def _check_blame_rows(rows: list[Row], text: str) -> None:
    lines = text.splitlines()
    _require(bool(lines), "oracle_mismatch")
    # Bitbucket blame entries cover spans of lines (``spannedLines``); BBK and
    # AtlaWire both project one row per server entry, so the sequential ``line``
    # is the entry index, not a per-file-line proof.
    _require(1 <= len(rows) <= len(lines), "contract")
    for number, row in enumerate(rows, start=1):
        _require_keys(row, _BLAME_KEYS)
        _require(row.get("line") == number, "contract")
        _require_optional_str(row.get("author"))
        _require_optional_str(row.get("email"))
        date = _require_optional_str(row.get("date"))
        if date is not None:
            _require(_DATE.fullmatch(date) is not None, "contract")
        _require(
            row.get("commit") is None
            or _SHA.fullmatch(str(row.get("commit"))) is not None,
            "contract",
        )


def _check_search_rows(rows: list[Row]) -> None:
    triples: set[tuple[str, str, str]] = set()
    for row in rows:
        _require_keys(row, _SEARCH_KEYS)
        project = _require_str(row.get("project"))
        repository = _require_str(row.get("repository"))
        path = _require_str(row.get("file"))
        _require((project, repository, path) not in triples, "contract")
        triples.add((project, repository, path))
        count = row.get("hitCount")
        _require(count is None or (_is_int(count) and count >= 0), "contract")
        _require(row.get("matchEvidence") in _MATCH_EVIDENCE, "contract")
        for group in _require_list(row.get("context") or []):
            for line in _require_list(group):
                line_row = _require_dict(line)
                _require_keys(line_row, _SEARCH_LINE_KEYS)
                _require(
                    line_row.get("line") is None or _is_int(line_row.get("line")),
                    "contract",
                )
                _require(isinstance(line_row.get("text"), str), "contract")
        for hit in _require_list(row.get("hits")):
            hit_row = _require_dict(hit)
            _require_keys(hit_row, _SEARCH_LINE_KEYS)
            _require(
                hit_row.get("line") is None or _is_int(hit_row.get("line")), "contract"
            )
            _require(isinstance(hit_row.get("text"), str), "contract")


# ------------------------------------------------------------------ the checks
def test_bbk_projects_contract(live: dict[str, Any]) -> None:
    rows = _expect_rows(("projects", "--json", "--max-pages", "1"))
    _require(bool(rows), "oracle_mismatch")
    _check_project_rows(rows)
    keys = {row.get("key") for row in rows}
    _require(live["project"] in keys, "oracle_mismatch")


def test_bbk_repos_contract(live: dict[str, Any]) -> None:
    rows = _expect_rows(("repos", live["project"], "--json", "--max-pages", "1"))
    _check_repository_rows(rows)
    slugs = {row.get("slug") for row in rows}
    _require(live["paged"]["repo"] in slugs, "oracle_mismatch")


def test_bbk_list_files_contract_and_pagination(live: dict[str, Any]) -> None:
    repository = f"{live['project']}/{live['paged']['repo']}"
    _refused_with_page_limit(("files", repository, "--json", "--max-pages", "1"))
    args = ("files", repository, "--json", "--max-pages", str(live["paged"]["pages"]))
    paths = _as_paths(_expect_json(args))
    _check_file_paths(paths)
    _require(len(paths) > 100, "contract")
    _require(paths == live["paged"]["paths"], "contract")
    if live["small"] is not None:
        small_repository = f"{live['project']}/{live['small']['repo']}"
        _check_file_paths(
            _as_paths(_expect_json(("files", small_repository, "--json")))
        )


def test_bbk_raw_file_contract(live: dict[str, Any]) -> None:
    file_info = live["file"]
    repository = f"{live['project']}/{file_info['repo']}"
    text = _expect_ok(("file", repository, file_info["path"], "--at", file_info["sha"]))
    _require(isinstance(text, str), "contract")
    _require(bool(text), "oracle_mismatch")
    _require("\x00" not in text, "contract")
    _require(text.splitlines() == file_info["text"].splitlines(), "contract")
    _require_sha(file_info["sha"])


def test_bbk_ls_contract(live: dict[str, Any]) -> None:
    file_info = live["file"]
    repository = f"{live['project']}/{file_info['repo']}"
    directory = file_info["path"].rsplit("/", 1)[0] if "/" in file_info["path"] else ""
    args: tuple[str, ...] = (
        ("ls", repository, directory, "--at", file_info["sha"], "--json")
        if directory
        else ("ls", repository, "--at", file_info["sha"], "--json")
    )
    rows = _expect_rows(args)
    _check_directory_rows(rows, file_info["path"])


def test_bbk_blame_contract(live: dict[str, Any]) -> None:
    file_info = live["file"]
    repository = f"{live['project']}/{file_info['repo']}"
    rows = _expect_rows(
        ("blame", repository, file_info["path"], "--at", file_info["sha"], "--json")
    )
    _check_blame_rows(rows, file_info["text"])


def test_bbk_branches_contract(live: dict[str, Any]) -> None:
    repository = f"{live['project']}/{live['paged']['repo']}"
    rows = _expect_rows(("branches", repository, "--json", "--max-pages", "2"))
    _check_branch_rows(rows)


def test_bbk_commits_contract(live: dict[str, Any]) -> None:
    repository = f"{live['project']}/{live['paged']['repo']}"
    rows = _expect_rows(("commits", repository, "--limit", "10", "--json"))
    _check_commit_rows(rows)
    _require(len(rows) <= 10, "contract")
    _require(rows[0].get("hash") == live["file"]["sha"], "oracle_mismatch")


def test_bbk_commit_contract(live: dict[str, Any]) -> None:
    history = live["history"]
    repository = f"{live['project']}/{live['paged']['repo']}"
    value = _require_dict(
        _expect_json(("commit", repository, history["sha"], "--json"))
    )
    _require(value.get("id") == history["sha"], "contract")
    _require(str(value.get("id")) == str(history["object"].get("id")), "contract")
    _require(isinstance(value.get("message"), str), "contract")
    _require(isinstance(value.get("authorTimestamp"), int), "contract")
    parents = _require_list(value.get("parents"))
    _require(len(parents) <= 1, "contract")
    for parent in parents:
        _require_sha(_require_dict(parent).get("id"))


def test_bbk_pr_commits_contract(live: dict[str, Any]) -> None:
    pull_request = live["pull_request"]
    repository = f"{live['project']}/{pull_request['repo']}"
    rows = _expect_rows(
        ("pr", repository, str(pull_request["id"]), "commits", "--json")
    )
    _check_commit_rows(rows, newest_first=False)
    _require(bool(rows), "oracle_mismatch")


def test_bbk_pr_comments_contract(live: dict[str, Any]) -> None:
    pull_request = live["pull_request"]
    repository = f"{live['project']}/{pull_request['repo']}"
    rows = _expect_rows(
        ("pr", repository, str(pull_request["id"]), "comments", "--json")
    )
    _check_comment_rows(rows)
    _require(bool(rows), "oracle_mismatch")


def test_bbk_pr_files_contract(live: dict[str, Any]) -> None:
    pull_request = live["pull_request"]
    repository = f"{live['project']}/{pull_request['repo']}"
    rows = _expect_rows(("pr", repository, str(pull_request["id"]), "files", "--json"))
    _check_changed_files(rows)
    _require(bool(rows), "oracle_mismatch")


def test_bbk_pr_contract(live: dict[str, Any]) -> None:
    pull_request = live["pull_request"]
    repository = f"{live['project']}/{pull_request['repo']}"
    value = _require_dict(
        _expect_json(("pr", repository, str(pull_request["id"]), "show"))
    )
    _require(
        _is_int(value.get("id")) and value.get("id") == pull_request["id"], "contract"
    )
    _require(isinstance(value.get("version"), int), "contract")
    _require_str(value.get("title"))
    _require(value.get("state") in _PR_STATES, "contract")
    _require(isinstance(value.get("author"), dict), "contract")
    _require(isinstance(value.get("fromRef"), dict), "contract")
    _require(isinstance(value.get("toRef"), dict), "contract")
    _require(isinstance(value.get("updatedDate"), int), "contract")


def test_bbk_prs_contract(live: dict[str, Any]) -> None:
    pull_request = live["pull_request"]
    repository = f"{live['project']}/{pull_request['repo']}"
    rows = _expect_rows(
        ("prs", repository, "--state", "ALL", "--limit", "10", "--json")
    )
    _check_pull_request_rows(rows)
    _require(bool(rows), "oracle_mismatch")
    merged = _expect_rows(
        ("prs", repository, "--state", "MERGED", "--limit", "10", "--json")
    )
    _check_pull_request_rows(merged)
    for row in merged:
        _require(row.get("state") == "MERGED", "contract")


def test_bbk_dashboard_contract(live: dict[str, Any]) -> None:
    rows = _expect_rows(("my-prs", "--state", "MERGED", "--limit", "10", "--json"))
    _check_my_pull_request_rows(rows)
    for row in rows:
        _require(row.get("state") == "MERGED", "contract")
    opened = _expect_rows(("my-prs", "--state", "OPEN", "--limit", "10", "--json"))
    _check_my_pull_request_rows(opened)
    for row in opened:
        _require(row.get("state") == "OPEN", "contract")
    ok, _, _ = _invoke(("my-prs", "--state", "ALL"))
    _require(not ok, "contract")


def test_bbk_repo_grep_contract(live: dict[str, Any]) -> None:
    file_info = live["file"]
    repository = f"{live['project']}/{file_info['repo']}"
    value = _require_dict(
        _expect_json(
            (
                "grep-repo",
                repository,
                live["pattern"],
                "--glob",
                file_info["path"],
                "--ref",
                file_info["sha"],
                "--limit",
                "20",
                "--json",
            )
        )
    )
    _require_keys(value, _GREP_KEYS)
    _require(value.get("engine") == "fanout", "contract")
    _require(value.get("repo") == repository, "contract")
    _require(value.get("commit") == file_info["sha"], "contract")
    _require(value.get("at") == file_info["sha"], "contract")
    _require(value.get("ref_kind") == "commit", "contract")
    _require(value.get("glob") == file_info["path"], "contract")
    _require(value.get("path") is None, "contract")
    _require(value.get("selection") == "explicit", "contract")
    _require(value.get("ignore_case") is True, "contract")
    _require(value.get("files") == [], "contract")
    _require(
        _is_int(value.get("files_eligible")) and value.get("files_eligible") >= 1,
        "contract",
    )
    _require(
        _is_int(value.get("files_scanned")) and value.get("files_scanned") >= 1,
        "contract",
    )
    _require(_is_int(value.get("files_excluded")), "contract")
    # BBK grep_ex partial=False maps to the new complete/status contract.
    _require(value.get("complete") is True, "contract")
    _require(value.get("truncated") is False, "contract")
    _require(value.get("status") == "complete", "contract")
    _require(value.get("message") is None, "contract")
    hits = _require_list(value.get("hits"))
    _require(bool(hits), "oracle_mismatch")
    for hit in hits:
        hit_row = _require_dict(hit)
        _require_keys(hit_row, _GREP_HIT_KEYS)
        _require(hit_row.get("file") == file_info["path"], "contract")
        _require(_is_int(hit_row.get("line")) and hit_row.get("line") >= 1, "contract")
        text = _require_str(hit_row.get("text"))
        _require(isinstance(hit_row.get("text_truncated"), bool), "contract")
        _require(
            re.search(live["pattern"], text, re.IGNORECASE) is not None, "contract"
        )


def test_bbk_repo_grep_listing_contract(live: dict[str, Any]) -> None:
    file_info = live["file"]
    repository = f"{live['project']}/{file_info['repo']}"
    value = _require_dict(
        _expect_json(
            (
                "grep-repo",
                repository,
                "--glob",
                file_info["path"],
                "--ref",
                file_info["sha"],
                "--limit",
                "20",
                "--json",
            )
        )
    )
    _require_keys(value, _GREP_KEYS)
    _require(value.get("engine") == "listing", "contract")
    _require(value.get("hits") == [], "contract")
    _require(value.get("complete") is True, "contract")
    _require(value.get("truncated") is False, "contract")
    _require(value.get("status") == "complete", "contract")
    _require(value.get("message") is None, "contract")
    files = _require_list(value.get("files"))
    _require(files == [file_info["path"]], "contract")


def test_bbk_commit_changes_contract(live: dict[str, Any]) -> None:
    history = live["history"]
    repository = f"{live['project']}/{live['paged']['repo']}"
    rows = _expect_rows(("commit-changes", repository, history["sha"], "--json"))
    _check_changed_files(rows)
    _require(bool(rows), "oracle_mismatch")


def test_bbk_commit_diff_contract(live: dict[str, Any]) -> None:
    history = live["history"]
    repository = f"{live['project']}/{live['paged']['repo']}"
    whole = _expect_ok(("commit-diff", repository, history["sha"]))
    for text in (whole, history["diff"], history["path_diff"]):
        _require(isinstance(text, str), "contract")
        _require(text.startswith("# Bitbucket commit diff review ("), "contract")
        _require("not a patch" in text, "contract")
        _require("\x00" not in text, "contract")
    _require(bool(whole.strip()), "oracle_mismatch")
    _require(history["path"] in whole, "contract")
    _require(history["path"] in history["path_diff"], "contract")


def test_bbk_find_repos_contract(live: dict[str, Any]) -> None:
    needle = live["paged"]["repo"]
    if live["small"] is not None:
        needle = live["small"]["repo"]
    rows = _expect_rows(("find-repos", needle, "--json", "--limit", "10"))
    _require(bool(rows), "oracle_mismatch")
    pairs: set[tuple[str, str]] = set()
    for row in rows:
        _require_keys(row, frozenset({"project", "slug", "name", "state"}))
        project = _require_str(row.get("project"))
        slug = _require_str(row.get("slug"))
        _require((project, slug) not in pairs, "contract")
        pairs.add((project, slug))
        _require_optional_str(row.get("name"))
        _require_optional_str(row.get("state"))
        _require(needle.lower() in slug.lower(), "contract")
    _require((live["project"], needle) in pairs, "oracle_mismatch")


def test_bbk_search_code_contract(live: dict[str, Any]) -> None:
    rows = _expect_rows(("search", _SEARCH_QUERY, "--limit", "5", "--json"))
    _check_search_rows(rows)
    _require(bool(rows), "oracle_mismatch")
    _require(len(rows) <= 5, "contract")
    _require(
        any(row.get("matchEvidence") == "highlight" for row in rows), "oracle_mismatch"
    )
    scope = f"{rows[0]['project']}/{rows[0]['repository']}"
    scoped = _expect_rows(
        ("search", _SEARCH_QUERY, "--repo", scope, "--limit", "5", "--json")
    )
    _check_search_rows(scoped)
    _require(bool(scoped), "oracle_mismatch")
    for row in scoped:
        where = f"{row.get('project')}/{row.get('repository')}"
        _require(where.lower() == scope.lower(), "contract")


def test_bbk_search_code_pages_to_end(live: dict[str, Any]) -> None:
    rows = live["scoped_all"]
    _check_search_rows(rows)
    _require(bool(rows), "oracle_mismatch")
    _require(len(rows) <= _SEARCH_EVERY_PAGE_LIMIT, "contract")
    # A scoped query that ends before the row cap proves the terminal page was
    # reached without a page-budget error (AtlaWire raises on a short budget).
    if len(rows) < _SEARCH_EVERY_PAGE_LIMIT:
        _require(len(rows) >= len(live["scoped"]), "contract")


def test_bbk_scan_extension_contract(live: dict[str, Any]) -> None:
    rows = live["scan"]
    if rows is None:
        pytest.skip("scan-extension cannot list this project within the page budget")
    _require(bool(rows), "oracle_mismatch")
    matched_values: list[int] = []
    pairs: set[tuple[str, str]] = set()
    for row in rows:
        _require_keys(row, _EXTENSION_KEYS)
        _require(row.get("project") == live["project"], "contract")
        repository = _require_str(row.get("repository"))
        _require((live["project"], repository) not in pairs, "contract")
        pairs.add((live["project"], repository))
        files = row.get("files")
        matched = row.get("matched")
        _require(_is_int(files) and _is_int(matched), "contract")
        _require(1 <= matched <= files, "contract")
        matched_values.append(matched)
        sample = _require_list(row.get("sample"))
        _require(1 <= len(sample) <= 5, "contract")
        for path in sample:
            _require(
                isinstance(path, str) and path.lower().endswith(".java"), "contract"
            )
    _require(matched_values == sorted(matched_values, reverse=True), "contract")
    if live["small"] is not None:
        _require((live["project"], live["small"]["repo"]) in pairs, "oracle_mismatch")


def test_aw_output_never_contains_the_token() -> None:
    token = _token()
    _require(bool(_Captured), "oracle_mismatch")
    for text in _Captured:
        _require(token not in text, "token_leak")
