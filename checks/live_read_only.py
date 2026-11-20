"""Explicitly invoked read-only live checks for AtlaWire.

Outside ``tests``; contacts a product only with ``--live`` plus complete settings.
Captured output is never printed; failures name one fixed check and category.
"""

import hashlib
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from typing import TextIO
from urllib.parse import urlsplit

EXIT_OK, EXIT_FAIL, EXIT_USAGE = 0, 1, 2
# ``-P`` keeps the current directory off sys.path but keeps the per-user install.
CLI_PREFIX = (sys.executable, "-P", "-B", "-m", "atlawire")
READ_COMMANDS = frozenset(
    {"jql", "issue", "issue-comments", "cql", "page", "search", "pr", "file"}
)

_TIMEOUT_MIN, _TIMEOUT_MAX = 5, 300
_LIMIT = 10
_TOKEN_FLAG = "--token-from-env"
_ISSUE_KEY = re.compile(r"[A-Z][A-Z0-9_]*-[0-9]+")
_POSITIVE_ID = re.compile(r"[1-9][0-9]{0,18}")
_PAGE_ID = re.compile(r"[1-9][0-9]{0,19}")
_SHA256 = re.compile(r"[0-9A-Fa-f]{64}")
_COMMIT = re.compile(r"[0-9A-Fa-f]{40}")
_PROJECT_KEY = re.compile(r"~?[A-Za-z0-9_][A-Za-z0-9_.-]*")
_REPOSITORY_SLUG = re.compile(r"[A-Za-z0-9_.-]+")
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f\ud800-\udfff]")
_JIRA, _CONFLUENCE, _BITBUCKET = (
    "ATLAWIRE_JIRA",
    "ATLAWIRE_CONFLUENCE",
    "ATLAWIRE_BITBUCKET",
)
_MARKER = "ATLAWIRE_LIVE_CONFLUENCE_MARKER"

_ALLOWED_ENV = frozenset(
    {
        "appdata",
        "home",
        "homedrive",
        "homepath",
        "lang",
        "lc_all",
        "lc_ctype",
        "localappdata",
        "path",
        "systemdrive",
        "systemroot",
        "temp",
        "tmp",
        "tmpdir",
        "tz",
        "userprofile",
        "windir",
    }
)

_HELP = """\
Usage: python -B checks/live_read_only.py --live [--timeout SECONDS]

Nine fixed read-only checks; --live and complete settings are required. Captured
output is never printed; failures name a fixed check and category. SECONDS is
5-300 (default 30). File refs are full 40-hex commits. Bound: nine subprocesses,
at most 27 HTTP requests, one timeout each. Missing settings are listed by name;
see docs/AGENT-QUICKSTART.md for names and fixtures.
"""


class LiveCheckError(Exception):
    """Expected check failure carrying only a fixed category."""

    def __init__(self, category: str) -> None:
        super().__init__(category)
        self.category = category


type Product = tuple[str, str]
type Config = tuple[Product, Product, Product, Mapping[str, str]]
type Check = tuple[str, tuple[str, ...], Mapping[str, str], str, tuple[str, ...]]
Runner = Callable[..., subprocess.CompletedProcess[bytes]]


def _valid_url(value: str) -> bool:
    if (
        not value
        or len(value) > 2048
        or _CONTROL.search(value)
        or any(char.isspace() for char in value)
        or any(mark in value for mark in ("\\", "?", "#"))
    ):
        return False
    try:
        parts = urlsplit(value)
        host, port = parts.hostname, parts.port
    except ValueError:
        return False
    return (
        parts.scheme == "https"
        and bool(host)
        and parts.username is None
        and parts.password is None
        and "%" not in parts.netloc
        and port != 0
    )


def _valid_token(value: str) -> bool:
    return (
        bool(value)
        and len(value) <= 8192
        and re.fullmatch(r"[A-Za-z0-9._~+/=-]+", value) is not None
    )


def _valid_query(value: str) -> bool:
    return (
        bool(value)
        and value == value.strip()
        and not value.startswith("-")
        and len(value) <= 500
        and not _CONTROL.search(value)
    )


def _valid_repo(value: str) -> bool:
    project, separator, slug = value.partition("/")
    return (
        bool(separator)
        and "/" not in slug
        and slug not in {".", ".."}
        and _PROJECT_KEY.fullmatch(project) is not None
        and _REPOSITORY_SLUG.fullmatch(slug) is not None
    )


def _valid_path(value: str) -> bool:
    if (
        not value
        or len(value) > 1024
        or _CONTROL.search(value)
        or "\\" in value
        or value.startswith(("/", "-"))
        or value.endswith("/")
        or "//" in value
        or re.search(r"%[0-9A-Fa-f]{2}", value)
    ):
        return False
    return all(s and s not in {".", ".."} for s in value.split("/"))


def _valid_java(value: str) -> bool:
    return _valid_path(value) and value.lower().endswith(".java")


def _matches(pattern: re.Pattern[str]) -> Callable[[str], bool]:
    return lambda value: pattern.fullmatch(value) is not None


_FIXTURE_SPECS = {
    "jira_jql": ("ATLAWIRE_LIVE_JIRA_JQL", _valid_query),
    "jira_issue": ("ATLAWIRE_LIVE_JIRA_ISSUE", _matches(_ISSUE_KEY)),
    "jira_comment_id": ("ATLAWIRE_LIVE_JIRA_COMMENT_ID", _matches(_POSITIVE_ID)),
    "confluence_page_id": ("ATLAWIRE_LIVE_CONFLUENCE_PAGE_ID", _matches(_PAGE_ID)),
    "confluence_cql": ("ATLAWIRE_LIVE_CONFLUENCE_CQL", _valid_query),
    "bitbucket_repo": ("ATLAWIRE_LIVE_BITBUCKET_REPO", _valid_repo),
    "bitbucket_search_query": ("ATLAWIRE_LIVE_BITBUCKET_SEARCH_QUERY", _valid_query),
    "bitbucket_search_path": ("ATLAWIRE_LIVE_BITBUCKET_SEARCH_PATH", _valid_java),
    "bitbucket_pr_id": ("ATLAWIRE_LIVE_BITBUCKET_PR_ID", _matches(_POSITIVE_ID)),
    "bitbucket_pr_path": ("ATLAWIRE_LIVE_BITBUCKET_PR_PATH", _valid_path),
    "bitbucket_file_path": ("ATLAWIRE_LIVE_BITBUCKET_FILE_PATH", _valid_java),
    "bitbucket_file_ref": ("ATLAWIRE_LIVE_BITBUCKET_FILE_REF", _matches(_COMMIT)),
    "bitbucket_file_sha256": ("ATLAWIRE_LIVE_BITBUCKET_FILE_SHA256", _matches(_SHA256)),
}


def _fixtures(
    environ: Mapping[str, str], problems: list[tuple[str, str]]
) -> Mapping[str, str]:
    values: dict[str, str] = {}
    for attribute, (name, valid) in _FIXTURE_SPECS.items():
        value = environ.get(name, "")
        if not value:
            problems.append(("missing", name))
        elif not valid(value):
            problems.append(("invalid", name))
        values[attribute] = value
    marker = environ.get(_MARKER, "")
    if marker and (len(marker) > 200 or _CONTROL.search(marker)):
        problems.append(("invalid", _MARKER))
    values["confluence_marker"] = marker
    return values


def _load_config(
    environ: Mapping[str, str],
) -> tuple[Config | None, tuple[tuple[str, str], ...]]:
    problems: list[tuple[str, str]] = []
    products: list[Product] = []
    for prefix in (_JIRA, _CONFLUENCE, _BITBUCKET):
        pair: list[str] = []
        for suffix, valid in (("URL", _valid_url), ("TOKEN", _valid_token)):
            name = f"{prefix}_{suffix}"
            value = environ.get(name, "")
            if not value:
                problems.append(("missing", name))
            elif not valid(value):
                problems.append(("invalid", name))
            pair.append(value)
        products.append((pair[0], pair[1]))
    fixtures = _fixtures(environ, problems)
    if problems:
        return None, tuple(problems)
    return (products[0], products[1], products[2], fixtures), ()


def _env(
    prefix: str, credentials: Product, base: Mapping[str, str]
) -> Mapping[str, str]:
    """Whitelist ordinary OS keys (case-insensitively) plus one product pair."""
    environment = {
        name: value for name, value in base.items() if name.lower() in _ALLOWED_ENV
    }
    environment[f"{prefix}_URL"] = credentials[0]
    environment[f"{prefix}_TOKEN"] = credentials[1]
    return environment


def build_plan(c: Config, base: Mapping[str, str]) -> tuple[Check, ...]:
    j, co, b, f = c
    je = _env(_JIRA, j, base)
    ce = _env(_CONFLUENCE, co, base)
    be = _env(_BITBUCKET, b, base)
    i, pg, r = f["jira_issue"], f["confluence_page_id"], f["bitbucket_repo"]
    pr, T = f["bitbucket_pr_id"], _TOKEN_FLAG
    cid, marker = f["jira_comment_id"], f["confluence_marker"]
    spath, ppath = f["bitbucket_search_path"], f["bitbucket_pr_path"]
    sha = f["bitbucket_file_sha256"]
    jql = ("jql", f["jira_jql"], "--json", "--limit", "10", T)
    cql = ("cql", f["confluence_cql"], "--json", "--limit", "10", T)
    search = (
        "search",
        f["bitbucket_search_query"],
        "--repo",
        r,
        "--limit",
        "10",
        "--json",
        T,
    )
    file_args = (
        "file",
        r,
        f["bitbucket_file_path"],
        "--at",
        f["bitbucket_file_ref"],
        T,
    )
    return (
        ("jira.discovery", jql, je, "keys", (i,)),
        ("jira.issue", ("issue", i, T), je, "issue", (i,)),
        (
            "jira.comments",
            ("issue-comments", i, "--max-pages", "1", T),
            je,
            "comments",
            (cid,),
        ),
        ("confluence.search_page", cql, ce, "cql", (pg,)),
        ("confluence.page", ("page", pg, T), ce, "page", (pg, marker)),
        ("bitbucket.indexed_search", search, be, "search", (r, spath)),
        ("bitbucket.pull_request", ("pr", r, pr, "show", T), be, "pr", (pr,)),
        (
            "bitbucket.pull_request_files",
            ("pr", r, pr, "files", "--json", T),
            be,
            "files",
            (ppath,),
        ),
        ("bitbucket.java_file", file_args, be, "digest", (sha,)),
    )


def _json(raw: bytes, limit: int = 4 * 1024 * 1024) -> object:
    if not isinstance(raw, bytes) or len(raw) > limit:
        raise LiveCheckError("invalid_output")
    try:
        return json.loads(raw.decode("utf-8"))
    except UnicodeDecodeError, ValueError, RecursionError:
        raise LiveCheckError("invalid_output")


def _string(value: object, *, numbers: bool = False) -> str:
    if isinstance(value, bool) or not isinstance(value, (str, int) if numbers else str):
        raise LiveCheckError("invalid_output")
    return str(value)


def _rows(raw: bytes, limit: int | None = None) -> list[dict[str, object]]:
    value = _json(raw)
    if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
        raise LiveCheckError("invalid_output")
    if limit is not None and len(value) > limit:
        raise LiveCheckError("invalid_output")
    if not value:
        raise LiveCheckError("oracle_mismatch")
    return value


_LIST_KINDS = {
    "keys": ("key", _LIMIT, False),
    "cql": ("id", _LIMIT, True),
    "files": ("path", None, False),
}


def _validate(kind: str, raw: bytes, expected: tuple[str, ...]) -> None:
    if kind in _LIST_KINDS:
        field, limit, numbers = _LIST_KINDS[kind]
        values = [_string(row.get(field), numbers=numbers) for row in _rows(raw, limit)]
        if expected[0] not in values:
            raise LiveCheckError("oracle_mismatch")
    elif kind == "issue":
        _issue(raw, expected[0])
    elif kind == "comments":
        _comments(raw, expected[0])
    elif kind == "page":
        _page(raw, *expected)
    elif kind == "search":
        _search(raw, *expected)
    elif kind == "pr":
        _pr(raw, expected[0])
    elif kind == "digest":
        _digest(raw, expected[0])
    else:
        raise LiveCheckError("invalid_plan")


def _issue(raw: bytes, issue: str) -> None:
    value = _json(raw)
    if not isinstance(value, dict):
        raise LiveCheckError("invalid_output")
    key = value.get("key")
    if not isinstance(key, str) or not isinstance(value.get("fields"), dict):
        raise LiveCheckError("invalid_output")
    if key != issue:
        raise LiveCheckError("oracle_mismatch")


def _comments(raw: bytes, comment_id: str) -> None:
    found = False
    for row in _rows(raw):
        identifier = _string(row.get("id"))
        body = row.get("body")
        if "body" not in row or (body is not None and not isinstance(body, str)):
            raise LiveCheckError("invalid_output")
        if identifier == comment_id and isinstance(body, str) and body.strip():
            found = True
    if not found:
        raise LiveCheckError("oracle_mismatch")


def _page(raw: bytes, page_id: str, marker: str) -> None:
    value = _json(raw)
    if not isinstance(value, dict):
        raise LiveCheckError("invalid_output")
    if _string(value.get("id"), numbers=True) != page_id:
        raise LiveCheckError("oracle_mismatch")
    body = value.get("body")
    storage = body.get("storage") if isinstance(body, dict) else None
    content = storage.get("value") if isinstance(storage, dict) else None
    if not isinstance(content, str):
        raise LiveCheckError("invalid_output")
    if not content.strip() or (marker and marker not in content):
        raise LiveCheckError("oracle_mismatch")


def _search(raw: bytes, repo: str, path: str) -> None:
    project, slug = repo.split("/", 1)
    matched = False
    for row in _rows(raw, _LIMIT):
        row_project = row.get("project")
        row_repository = row.get("repository")
        row_file = row.get("file")
        evidence, hits = row.get("matchEvidence"), row.get("hits")
        if (
            not isinstance(row_project, str)
            or not isinstance(row_repository, str)
            or not isinstance(row_file, str)
            or not isinstance(evidence, str)
            or evidence not in {"highlight", "context-only", "none"}
            or not isinstance(hits, list)
            or row_project.lower() != project.lower()
            or row_repository.lower() != slug.lower()
            or any(
                not isinstance(hit, dict) or not isinstance(hit.get("text"), str)
                for hit in hits
            )
        ):
            raise LiveCheckError("invalid_output")
        if row_file == path and evidence == "highlight" and hits:
            matched = True
    if not matched:
        raise LiveCheckError("oracle_mismatch")


def _pr(raw: bytes, pr_id: str) -> None:
    value = _json(raw)
    if not isinstance(value, dict):
        raise LiveCheckError("invalid_output")
    identifier = value.get("id")
    if isinstance(identifier, bool) or not isinstance(identifier, int):
        raise LiveCheckError("invalid_output")
    title = _string(value.get("title"))
    state = _string(value.get("state"))
    if str(identifier) != pr_id or not title or not state:
        raise LiveCheckError("oracle_mismatch")


def _digest(raw: bytes, expected: str) -> None:
    if not raw or len(raw) > 1024 * 1024:
        raise LiveCheckError("invalid_output")
    if hashlib.sha256(raw).hexdigest().lower() != expected.lower():
        raise LiveCheckError("oracle_mismatch")


def _execute(
    args: tuple[str, ...], env: Mapping[str, str], timeout: int, runner: Runner
) -> bytes:
    if not args or args[0] not in READ_COMMANDS:
        raise LiveCheckError("invalid_plan")
    argv = [*CLI_PREFIX, *args]
    try:
        completed = runner(
            argv,
            env=dict(env),
            capture_output=True,
            timeout=timeout,
            check=False,
            shell=False,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        raise LiveCheckError("timeout")
    except OSError, UnicodeError:
        raise LiveCheckError("cli_unavailable")
    if completed.returncode != 0:
        raise LiveCheckError("cli_failed")
    if not isinstance(completed.stdout, bytes):
        raise LiveCheckError("invalid_output")
    return completed.stdout


def _run_plan(
    config: Config,
    base: Mapping[str, str],
    *,
    timeout: int,
    runner: Runner,
    out: TextIO,
) -> int:
    plan = build_plan(config, base)
    for name, args, env, kind, expected in plan:
        try:
            _validate(kind, _execute(args, env, timeout, runner), expected)
        except LiveCheckError as exc:
            print(f"{name}: FAIL {exc.category}", file=out)
            print("live-read-only: FAIL", file=out)
            return EXIT_FAIL
        print(f"{name}: ok", file=out)
    print(f"live-read-only: PASS ({len(plan)} checks)", file=out)
    return EXIT_OK


def _parse(argv: Sequence[str]) -> tuple[bool, int, bool] | None:
    live, timeout, help_seen, seen, index = False, 30, False, False, 0
    while index < len(argv):
        token = argv[index]
        if token in {"--help", "-h"}:
            help_seen, index = True, index + 1
        elif token == "--live":
            if live:
                return None
            live, index = True, index + 1
        elif token == "--timeout" or token.startswith("--timeout="):
            if seen:
                return None
            seen = True
            if token == "--timeout":
                if index + 1 >= len(argv):
                    return None
                value = argv[index + 1]
            else:
                value = token.partition("=")[2]
            if len(value) > 3 or not value.isascii() or not value.isdigit():
                return None
            seconds = int(value)
            if not _TIMEOUT_MIN <= seconds <= _TIMEOUT_MAX:
                return None
            timeout = seconds
            index += 2 if token == "--timeout" else 1
        else:
            return None
    return live, timeout, help_seen


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    runner: Runner | None = None,
    out: TextIO | None = None,
    err: TextIO | None = None,
) -> int:
    """Run checks; without valid ``--live`` configuration nothing starts."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    base = os.environ if environ is None else environ
    execute = subprocess.run if runner is None else runner
    stdout = sys.stdout if out is None else out
    stderr = sys.stderr if err is None else err
    parsed = _parse(arguments)
    if parsed is None:
        print("live-read-only: invalid arguments; use --help", file=stderr)
        return EXIT_USAGE
    live, timeout, help_seen = parsed
    if help_seen:
        print(_HELP, file=stdout)
        return EXIT_OK
    if not live:
        print("live-read-only: opt-in required; pass --live", file=stderr)
        return EXIT_USAGE
    config, problems = _load_config(base)
    if problems:
        for kind, name in problems:
            print(f"{kind}: {name}", file=stderr)
        print("live-read-only: FAIL configuration", file=stderr)
        return EXIT_USAGE
    assert config is not None
    return _run_plan(config, base, timeout=timeout, runner=execute, out=stdout)


if __name__ == "__main__":
    sys.exit(main())
