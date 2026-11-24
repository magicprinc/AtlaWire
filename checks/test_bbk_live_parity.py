"""Opt-in live differential checks: AtlaWire versus BBK.

Run only by explicit path, outside the default ``tests`` tree::

    C:/Python315/python.exe -B -m pytest -q -p no:cacheprovider \
        checks/test_bbk_live_parity.py

Five read-only workflows are compared with real subprocess entrypoints:

* ``jql``: ordered Jira issue keys from one identical JQL query.
* ``cql``: ordered Confluence content IDs from one identical CQL query.
* ``search``: ordered ``(project, repository, path)`` triples from one
  identical indexed-code query scoped to the same repository.
* ``jira-author-comments``: ``(issue key, comment ID)`` pairs for the current
  user in one project and a 90-day issue-update window. BBK runs with
  ``--strict`` so an incomplete scan fails instead of returning partial rows.
* ``repo-grep``: ``(file, line)`` hits for one regex-escaped literal term in one
  known file at the immutable commit named by
  ``ATLAWIRE_LIVE_BITBUCKET_FILE_REF``. Both tools receive ``--ref`` with that
  commit. The command names differ: BBK spells it ``grep`` and AtlaWire
  ``grep-repo``, so each tool has its own plan and its own allowlist entry. BBK
  has text-only grep output, so only its documented ``file:line:`` prefixes are
  parsed. A repository-wide grep is deliberately excluded; it needs a separate
  explicit heavy test.

Each tool reads the saved BBK credential store locally (``BBK_CREDENTIALS`` or
``~/.config/atlassian/credentials.json``); this module never opens that file,
accepts no token argument, and prints no child output. Product URL and token
overrides are removed from the child environment, so both tools resolve the same
saved pair. Only stable identifiers are compared: summaries, prose, statuses,
highlights, URLs, and other volatile fields are ignored. The first three
workflows compare ordered lists element by element. Author comments and grep
compare sets, because live changes and BBK's archive/fanout versus AtlaWire's
fanout engine can change order.

Live data changes and server caps can make two sequential calls disagree even
when both tools are correct. These five workflows are a smoke-level replacement
check, not proof of full BBK parity, and they do not cover pagination,
permissions, version differences, writes, or repository-wide grep.

The BBK child is ``python -P -B -m bbk`` with ``PYTHONPATH`` set to the BBK
package root. That root defaults to ``D:/zcache/bbk`` and can be overridden with
``ATLAWIRE_PARITY_BBK_ROOT``; the Windows ``bbk.cmd`` launcher would otherwise
need a shell. The AtlaWire child is ``python -P -B -m atlawire``. Both use
``shell=False``, stdin from ``DEVNULL``, a fixed 60-second timeout, and a strict
allowlist: ``jql``, ``cql``, the fixed read-only ``search`` POST, ``comments``
(BBK) or ``jira-author-comments`` (AtlaWire), and one-file ``grep`` (BBK) or
``grep-repo`` (AtlaWire). Missing or option-like fixtures fail before any
subprocess starts, except the BBK package root: when BBK's package is absent
the whole suite is skipped with one fixed reason instead of failing. A failure
reports only the check name and one fixed category, or a fixed fixture name
for a missing fixture.
Inconclusive results are nonzero ``inconclusive:...`` failures, not passes.
Expected and unexpected failures use ``pytest.fail(..., pytrace=False)``, so
``--showlocals`` cannot print fixture, query, or captured output values.
``subprocess.run(capture_output=True)`` buffers each complete stream before the
4 MiB stdout check, so that check limits accepted output, not capture memory.

Limits: ``jql`` 10 rows, ``cql`` 10 rows, ``search`` 5 files, author comments
10 rows in a 90-day project window, and grep 20 hits in one file. The expected
identifier must be inside the bounded result of both tools. The identical plans
include::

    jql QUERY --json --limit 10
    cql QUERY --json --limit 10
    search QUERY --repo PROJECT/slug --json --limit 5
    comments --days 90 --limit 10 --project KEY --strict --json   (BBK)
    jira-author-comments --days 90 --limit 10 --project KEY --json
    grep REPO PATTERN --glob FILE --ref COMMIT --limit 20        (BBK, text)
    grep-repo REPO PATTERN --glob FILE --ref COMMIT --limit 20 --json (AtlaWire)

An empty ``jql``/``cql``/``search`` result fails. Author comments and grep
instead return a fixed ``inconclusive:...`` failure when the reused fixture
cannot prove a match. Inconclusive is never reported as a pass.

The fixtures are the existing live-read-only names, shared with
``checks/live_read_only.py``:

``ATLAWIRE_LIVE_JIRA_JQL``
    Non-empty JQL query, preferably with an explicit ``ORDER BY``.
``ATLAWIRE_LIVE_JIRA_ISSUE``
    Issue key that must be among the first 10 keys from both tools. Its project
    prefix is also the bounded project for author comments.
``ATLAWIRE_LIVE_JIRA_COMMENT_ID``
    Expected comment ID on ``ATLAWIRE_LIVE_JIRA_ISSUE``. It must be by the
    current user and inside the 90-day project window; otherwise author comments
    are inconclusive.
``ATLAWIRE_LIVE_CONFLUENCE_CQL``
    Non-empty CQL query.
``ATLAWIRE_LIVE_CONFLUENCE_PAGE_ID``
    Confluence content ID that must be among the first 10 IDs from both tools.
``ATLAWIRE_LIVE_BITBUCKET_SEARCH_QUERY``
    Non-empty indexed-code search text. It is also the literal, regex-escaped
    grep term; a multi-term or index-only match may produce no grep hit and is
    inconclusive.
``ATLAWIRE_LIVE_BITBUCKET_REPO``
    ``PROJECT/slug`` scope passed to both ``search`` commands and both bounded
    grep commands. Use the server's canonical project key and repository slug;
    identifier comparison is exact even though both tools accept case-insensitive
    scope filters.
``ATLAWIRE_LIVE_BITBUCKET_SEARCH_PATH``
    Repository-relative ``.java`` file path that must be among the first 5
    files from both tools. It is also the exact full-path ``--glob`` target for
    grep, so the grep check does not scan the repository. If this file or the
    literal term is absent at the pinned commit, grep is inconclusive.
``ATLAWIRE_LIVE_BITBUCKET_FILE_REF``
    Full 40-hex commit passed as ``--ref`` to both grep commands, so both read
    the same immutable snapshot instead of two moving default-branch reads.

Intentional BBK/AtlaWire differences are not hidden:

* BBK ``grep`` has no JSON mode; its documented ``file:line:`` text lines are
  parsed. AtlaWire ``grep-repo`` always prints JSON. Text and ordering are not
  compared. A path whose own punctuation makes the prefix ambiguous is rejected
  as invalid output rather than guessed.
* BBK ``comments`` can return partial rows with a stderr warning. This check
  passes ``--strict`` so an incomplete scan fails; AtlaWire already fails on an
  incomplete scan. Such a failure is reported as a tool failure, not converted
  into an inconclusive match. BBK also normalizes/truncates comment prose, so
  only the issue key and comment ID are compared. The author-comment workflow is
  bounded to one project and 90 days, but it still reads every issue in that
  window; a high-volume project can be slow or exceed the scan budget.
* BBK ``grep`` may use an archive or fanout engine while AtlaWire ``grep-repo``
  uses fanout. File/line sets are compared, not engine order or diagnostics.
  Both are pinned to ``ATLAWIRE_LIVE_BITBUCKET_FILE_REF``, but engine selection
  can still differ.
* If BBK reports ``partial=True``, AtlaWire reports ``truncated``/incomplete, or
  either side reaches the 20-hit cap, the grep result is inconclusive rather
  than passed.

The BBK package root defaults to ``D:/zcache/bbk``, the data directory that
survives the package split. Set ``ATLAWIRE_PARITY_BBK_ROOT`` only to override
it; it must be an absolute directory containing ``bbk/__main__.py``. When the
directory is missing or no longer contains the ``bbk`` package, every check is
skipped with one fixed reason; a missing package is not a parity failure. No
credential file is read.

This module is opt-in: the default ``tests`` tree does not collect or run it.
Its five plans are fixed tuples validated by the read-only allowlist before any
child process starts.
"""

import json
import os
import re
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

import pytest

BBK_ROOT_ENV = "ATLAWIRE_PARITY_BBK_ROOT"
# BBK's data directory survives the package split that removes its code.
DEFAULT_BBK_ROOT = "D:/zcache/bbk"
# Unavailable BBK is a precondition, not a parity failure; the reason is fixed.
BBK_ROOT_SKIP_REASON = (
    "BBK package is unavailable at the configured root; parity checks need "
    "bbk/__main__.py (set ATLAWIRE_PARITY_BBK_ROOT to the BBK package root)."
)
JQL_QUERY_ENV = "ATLAWIRE_LIVE_JIRA_JQL"
JQL_KEY_ENV = "ATLAWIRE_LIVE_JIRA_ISSUE"
CQL_QUERY_ENV = "ATLAWIRE_LIVE_CONFLUENCE_CQL"
CQL_ID_ENV = "ATLAWIRE_LIVE_CONFLUENCE_PAGE_ID"
SEARCH_QUERY_ENV = "ATLAWIRE_LIVE_BITBUCKET_SEARCH_QUERY"
SEARCH_REPO_ENV = "ATLAWIRE_LIVE_BITBUCKET_REPO"
SEARCH_PATH_ENV = "ATLAWIRE_LIVE_BITBUCKET_SEARCH_PATH"
JIRA_COMMENT_ENV = "ATLAWIRE_LIVE_JIRA_COMMENT_ID"
GREP_REF_ENV = "ATLAWIRE_LIVE_BITBUCKET_FILE_REF"

FIXTURE_NAMES = frozenset(
    {
        BBK_ROOT_ENV,
        JQL_QUERY_ENV,
        JQL_KEY_ENV,
        JIRA_COMMENT_ENV,
        CQL_QUERY_ENV,
        CQL_ID_ENV,
        SEARCH_QUERY_ENV,
        SEARCH_REPO_ENV,
        SEARCH_PATH_ENV,
        GREP_REF_ENV,
    }
)

JQL_LIMIT = 10
CQL_LIMIT = 10
SEARCH_LIMIT = 5
AUTHOR_COMMENT_DAYS = 90
AUTHOR_COMMENT_LIMIT = 10
GREP_LIMIT = 20
TIMEOUT_SECONDS = 60
# subprocess.run(capture_output=True) buffers the complete stream before this
# check, so this is an acceptance limit for parsed stdout, not a hard capture
# or child-memory bound.
MAX_OUTPUT_BYTES = 4 * 1024 * 1024

BBK_PREFIX = (sys.executable, "-P", "-B", "-m", "bbk")
ATLAWIRE_PREFIX = (sys.executable, "-P", "-B", "-m", "atlawire")
_PREFIXES = {"bbk": BBK_PREFIX, "atlawire": ATLAWIRE_PREFIX}

# Exactly the read-only workflows compared here, per tool. The search command is
# the one fixed read-only POST through the Bitbucket Search plugin. No write or
# arbitrary command is allowed, and every plan has an exact shape checked before
# a child starts. Only the repository grep workflow is spelled differently: BBK
# registers ``grep`` and AtlaWire registers ``grep-repo``, so neither command
# name may be used with the other tool.
BBK_COMMANDS = frozenset({"jql", "cql", "search", "comments", "grep"})
ATLAWIRE_COMMANDS = frozenset(
    {"jql", "cql", "search", "jira-author-comments", "grep-repo"}
)
COMMANDS_BY_TOOL = {"bbk": BBK_COMMANDS, "atlawire": ATLAWIRE_COMMANDS}
ALLOWED_COMMANDS = BBK_COMMANDS | ATLAWIRE_COMMANDS

# Ordinary OS settings plus the shared saved credential path. Product URL and
# token variables, fixture variables, AWS settings, and PYTHONPATH are dropped
# so each child reads its own local store and cannot be redirected by ambient
# overrides. Proxy and CA names are kept for clients that honor them, including
# BBK's requests calls. AtlaWire's bearer_session sets trust_env=False and
# ignores ambient proxy, CA, and netrc settings, so these names do not affect
# AtlaWire reachability.
_ALLOWED_ENV = frozenset(
    {
        "all_proxy",
        "appdata",
        "bbk_credentials",
        "home",
        "homedrive",
        "homepath",
        "http_proxy",
        "https_proxy",
        "lang",
        "lc_all",
        "lc_ctype",
        "localappdata",
        "no_proxy",
        "path",
        "requests_ca_bundle",
        "ssl_cert_dir",
        "ssl_cert_file",
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

_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f\ud800-\udfff]")
_ISSUE_KEY = re.compile(r"[A-Z][A-Z0-9_]*-[0-9]+")
_CONTENT_ID = re.compile(r"[1-9][0-9]{0,19}")
_COMMENT_ID = re.compile(r"[1-9][0-9]{0,18}")
_JIRA_PROJECT = re.compile(r"[A-Z][A-Z0-9_]+")
_COMMIT = re.compile(r"[0-9A-Fa-f]{40}")
_PROJECT_KEY = re.compile(r"~?[A-Za-z0-9_][A-Za-z0-9_.-]*")
_REPOSITORY_SLUG = re.compile(r"[A-Za-z0-9_.-]+")
_LIMIT = re.compile(r"[1-9][0-9]{0,3}")
_BBK_GREP_HEADER = re.compile(
    r"# (?P<count>[0-9]+) hit\(s\), engine=(?:archive|fanout|listing), "
    r"scanned=[0-9]+, partial=(?P<partial>True|False)"
)
_BBK_GREP_HIT = re.compile(r"^(?P<file>.+):(?P<line>[1-9][0-9]*): (?P<text>.*)$")

# Every failure category this suite may report. A typo is a harness bug, not a
# server result, and is rejected before it can be shown as a check outcome.
PARITY_CATEGORIES = frozenset(
    {
        "invalid_plan",
        "timeout",
        "tool_unavailable",
        "tool_failed",
        "invalid_output",
        "empty_result",
        "parity_mismatch",
    }
)

# Fixed reasons for an explicit inconclusive failure. These are nonzero failures,
# never passes, and carry no query, fixture value, comment text, or file content.
INCONCLUSIVE_REASONS = frozenset(
    {
        "author_comment_fixture_not_in_both",
        "grep_fixture_no_hit",
        "grep_partial",
        "grep_limit_reached",
    }
)


class ParityError(Exception):
    """Expected check failure carrying only a fixed category."""

    def __init__(self, category: str) -> None:
        if category not in PARITY_CATEGORIES:
            raise ValueError("unknown parity category")
        super().__init__(category)
        self.category = category


class InconclusiveError(Exception):
    """Fixed reason that the reused fixture cannot prove a match."""

    def __init__(self, reason: str) -> None:
        if reason not in INCONCLUSIVE_REASONS:
            raise ValueError("unknown inconclusive reason")
        super().__init__(reason)
        self.reason = reason


class FixtureError(Exception):
    """Missing or invalid fixture carrying only the environment variable name."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.name = name


def _plain(value: object, *, limit: int) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and len(value) <= limit
        and value == value.strip()
        and not value.startswith("-")
        and _CONTROL.search(value) is None
    )


def valid_query(value: object) -> bool:
    return _plain(value, limit=500)


def valid_issue(value: object) -> bool:
    return isinstance(value, str) and _ISSUE_KEY.fullmatch(value) is not None


def valid_content_id(value: object) -> bool:
    return isinstance(value, str) and _CONTENT_ID.fullmatch(value) is not None


def valid_comment_id(value: object) -> bool:
    return isinstance(value, str) and _COMMENT_ID.fullmatch(value) is not None


def valid_project(value: object) -> bool:
    return isinstance(value, str) and _PROJECT_KEY.fullmatch(value) is not None


def valid_jira_project(value: object) -> bool:
    """BBK requires an uppercase Jira project key with at least two characters."""
    return isinstance(value, str) and _JIRA_PROJECT.fullmatch(value) is not None


def valid_pattern(value: object) -> bool:
    """Accept the escaped literal grep pattern, including backslashes."""
    return _plain(value, limit=2000)


def valid_commit(value: object) -> bool:
    return isinstance(value, str) and _COMMIT.fullmatch(value) is not None


def valid_repo(value: object) -> bool:
    if not isinstance(value, str) or len(value) > 512:
        return False
    project, separator, slug = value.partition("/")
    return (
        bool(separator)
        and "/" not in slug
        and slug not in {".", ".."}
        and _PROJECT_KEY.fullmatch(project) is not None
        and _REPOSITORY_SLUG.fullmatch(slug) is not None
    )


def valid_path(value: object) -> bool:
    """Accept only one repository-relative path with no dot segments."""
    if not isinstance(value, str) or not _plain(value, limit=1024):
        return False
    if "\\" in value:
        return False
    if value.startswith("/") or value.endswith("/") or "//" in value:
        return False
    if re.search(r"%[0-9A-Fa-f]{2}", value):
        return False
    return all(segment not in {"", ".", ".."} for segment in value.split("/"))


def valid_search_path(value: object) -> bool:
    """Match the shared live fixture rule: a repository-relative Java path."""
    return (
        isinstance(value, str) and valid_path(value) and value.lower().endswith(".java")
    )


def valid_grep_glob(value: object) -> bool:
    """Accept one exact full Java path with no glob metacharacters."""
    return (
        isinstance(value, str)
        and valid_search_path(value)
        and not any(character in value for character in "*?[]")
    )


def _limit_ok(value: str, maximum: int) -> bool:
    return _LIMIT.fullmatch(value) is not None and int(value) <= maximum


def _json_plan(command: str, query: str, limit: int) -> tuple[str, ...]:
    return (command, query, "--json", "--limit", str(limit))


def search_plan(query: str, repo: str) -> tuple[str, ...]:
    return (
        "search",
        query,
        "--repo",
        repo,
        "--json",
        "--limit",
        str(SEARCH_LIMIT),
    )


def author_comment_plans(project: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return the fixed BBK and AtlaWire author-comment plans."""
    days = str(AUTHOR_COMMENT_DAYS)
    limit = str(AUTHOR_COMMENT_LIMIT)
    bbk = (
        "comments",
        "--days",
        days,
        "--limit",
        limit,
        "--project",
        project,
        "--strict",
        "--json",
    )
    atlawire = (
        "jira-author-comments",
        "--days",
        days,
        "--limit",
        limit,
        "--project",
        project,
        "--json",
    )
    return bbk, atlawire


def repo_grep_plans(
    repo: str, pattern: str, path: str, ref: str
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return the fixed BBK ``grep`` and AtlaWire ``grep-repo`` plans."""
    limit = str(GREP_LIMIT)
    bbk = (
        "grep",
        repo,
        pattern,
        "--glob",
        path,
        "--ref",
        ref,
        "--limit",
        limit,
    )
    atlawire = (
        "grep-repo",
        repo,
        pattern,
        "--glob",
        path,
        "--ref",
        ref,
        "--limit",
        limit,
        "--json",
    )
    return bbk, atlawire


def _plan_error(tool: str, args: Sequence[str]) -> bool:
    """Reject every command and argument outside this tool's read-only set."""
    commands = COMMANDS_BY_TOOL.get(tool)
    if commands is None:
        return True
    if not args or not all(isinstance(argument, str) and argument for argument in args):
        return True
    if any(_CONTROL.search(argument) for argument in args):
        return True
    command = args[0]
    if command not in commands:
        return True
    if command in {"jql", "cql"}:
        return not (
            len(args) == 5
            and args[2] == "--json"
            and args[3] == "--limit"
            and valid_query(args[1])
            and _limit_ok(args[4], 1000)
        )
    if command == "search":
        return not (
            len(args) == 7
            and args[2] == "--repo"
            and valid_repo(args[3])
            and args[4] == "--json"
            and args[5] == "--limit"
            and valid_query(args[1])
            and _limit_ok(args[6], 999)
        )
    if command == "comments":
        return not (
            tool == "bbk"
            and len(args) == 9
            and args[1] == "--days"
            and args[2] == str(AUTHOR_COMMENT_DAYS)
            and args[3] == "--limit"
            and args[4] == str(AUTHOR_COMMENT_LIMIT)
            and args[5] == "--project"
            and valid_jira_project(args[6])
            and args[7] == "--strict"
            and args[8] == "--json"
        )
    if command == "jira-author-comments":
        return not (
            tool == "atlawire"
            and len(args) == 8
            and args[1] == "--days"
            and args[2] == str(AUTHOR_COMMENT_DAYS)
            and args[3] == "--limit"
            and args[4] == str(AUTHOR_COMMENT_LIMIT)
            and args[5] == "--project"
            and valid_jira_project(args[6])
            and args[7] == "--json"
        )
    if command == "grep":
        return not (
            tool == "bbk"
            and len(args) == 9
            and valid_repo(args[1])
            and valid_pattern(args[2])
            and args[3] == "--glob"
            and valid_grep_glob(args[4])
            and args[5] == "--ref"
            and valid_commit(args[6])
            and args[7] == "--limit"
            and args[8] == str(GREP_LIMIT)
        )
    if command == "grep-repo":
        return not (
            tool == "atlawire"
            and len(args) == 10
            and valid_repo(args[1])
            and valid_pattern(args[2])
            and args[3] == "--glob"
            and valid_grep_glob(args[4])
            and args[5] == "--ref"
            and valid_commit(args[6])
            and args[7] == "--limit"
            and args[8] == str(GREP_LIMIT)
            and args[9] == "--json"
        )
    return True


def bbk_root(base: Mapping[str, str]) -> str:
    """Return the existing BBK package root without ever echoing the path.

    The root defaults to ``DEFAULT_BBK_ROOT``. An explicit
    ``ATLAWIRE_PARITY_BBK_ROOT`` value replaces it and is validated instead of
    falling back, so a bad override never silently selects the default. A
    missing root or a root without the ``bbk`` package raises ``FixtureError``;
    the autouse fixture below turns that into an honest skip.
    """
    override = base.get(BBK_ROOT_ENV, "")
    if override:
        if (
            not isinstance(override, str)
            or len(override) > 4096
            or override.startswith("-")
            or _CONTROL.search(override) is not None
        ):
            raise FixtureError(BBK_ROOT_ENV)
        value = override
    else:
        value = DEFAULT_BBK_ROOT
    try:
        root = Path(value)
        valid = (
            root.is_absolute()
            and root.is_dir()
            and (root / "bbk" / "__main__.py").is_file()
        )
    except OSError, ValueError:
        valid = False
    if not valid:
        raise FixtureError(BBK_ROOT_ENV)
    return str(root)


@pytest.fixture(autouse=True)
def _require_bbk_package() -> None:
    """Skip the suite when BBK's package is no longer installed.

    The package split removes the ``bbk`` code while keeping its data
    directory, so an absent package is an expected precondition, not a parity
    defect. The skip reason is fixed and never echoes the configured path.
    """
    try:
        bbk_root(os.environ)
    except FixtureError:
        pytest.skip(BBK_ROOT_SKIP_REASON)


def child_environment(base: Mapping[str, str], *, tool: str) -> dict[str, str]:
    """Return ordinary OS settings only, plus a deterministic UTF-8 mode."""
    environment = {
        name: value for name, value in base.items() if name.lower() in _ALLOWED_ENV
    }
    environment["PYTHONIOENCODING"] = "utf-8"
    environment["PYTHONUTF8"] = "1"
    if tool == "bbk":
        environment["PYTHONPATH"] = bbk_root(base)
    return environment


def run_tool(
    tool: str,
    args: Sequence[str],
    *,
    timeout: int = TIMEOUT_SECONDS,
    runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
    environ: Mapping[str, str] | None = None,
) -> bytes:
    """Run one fixed read-only command and return stdout bytes only.

    Captured stdout and stderr are never printed or attached to an exception.
    A nonzero exit, timeout, launch failure, or invalid output raises one fixed
    category, so fixture values and server data cannot leak. The 4 MiB check is
    applied after ``capture_output=True`` buffers the complete stream; it limits
    accepted output and does not bound capture memory.
    """
    if tool not in _PREFIXES:
        raise ParityError("invalid_plan")
    plan = tuple(args)
    if _plan_error(tool, plan):
        raise ParityError("invalid_plan")
    base = os.environ if environ is None else environ
    environment = child_environment(base, tool=tool)
    try:
        completed = runner(
            [*_PREFIXES[tool], *plan],
            env=environment,
            capture_output=True,
            timeout=timeout,
            check=False,
            shell=False,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        raise ParityError("timeout") from None
    except OSError, UnicodeError:
        raise ParityError("tool_unavailable") from None
    try:
        returncode = completed.returncode
        output = completed.stdout
    except AttributeError:
        raise ParityError("tool_unavailable") from None
    if returncode != 0:
        raise ParityError("tool_failed")
    if not isinstance(output, bytes) or not output:
        raise ParityError("invalid_output")
    if len(output) > MAX_OUTPUT_BYTES:
        raise ParityError("invalid_output")
    return output


def run_pair(
    bbk_args: Sequence[str],
    atlawire_args: Sequence[str],
    *,
    runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
    environ: Mapping[str, str],
) -> tuple[bytes, bytes]:
    """Run the fixed BBK and AtlaWire plans in that order."""
    bbk_output = run_tool("bbk", bbk_args, runner=runner, environ=environ)
    atlawire_output = run_tool(
        "atlawire", atlawire_args, runner=runner, environ=environ
    )
    return bbk_output, atlawire_output


def run_both(
    args: Sequence[str],
    *,
    runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
    environ: Mapping[str, str],
) -> tuple[bytes, bytes]:
    """Run the identical plan through BBK first and AtlaWire second."""
    return run_pair(args, args, runner=runner, environ=environ)


def require_fixture(
    environ: Mapping[str, str], name: str, validator: Callable[[object], bool]
) -> str:
    """Return one required fixture or fail with the variable name only."""
    value = environ.get(name, "")
    if not isinstance(value, str) or not value or not validator(value):
        raise FixtureError(name)
    return value


def _json(raw: bytes) -> object:
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_OUTPUT_BYTES:
        raise ParityError("invalid_output")
    try:
        return json.loads(raw.decode("utf-8"))
    except UnicodeDecodeError, ValueError, RecursionError:
        raise ParityError("invalid_output") from None


def _list_rows(raw: bytes, limit: int) -> list[dict[str, object]]:
    value = _json(raw)
    if not isinstance(value, list):
        raise ParityError("invalid_output")
    if len(value) > limit:
        raise ParityError("invalid_output")
    rows: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, dict):
            raise ParityError("invalid_output")
        rows.append(item)
    return rows


def _rows(raw: bytes, limit: int) -> list[dict[str, object]]:
    rows = _list_rows(raw, limit)
    if not rows:
        raise ParityError("empty_result")
    return rows


def _positive_id_text(value: object) -> str:
    if isinstance(value, bool):
        raise ParityError("invalid_output")
    if isinstance(value, int):
        text = str(value)
    elif isinstance(value, str):
        text = value
    else:
        raise ParityError("invalid_output")
    if _COMMENT_ID.fullmatch(text) is None:
        raise ParityError("invalid_output")
    return text


def _jql_keys(raw: bytes, limit: int = JQL_LIMIT) -> list[str]:
    keys: list[str] = []
    for row in _rows(raw, limit):
        key = row.get("key")
        if not isinstance(key, str) or _ISSUE_KEY.fullmatch(key) is None:
            raise ParityError("invalid_output")
        keys.append(key)
    if len(set(keys)) != len(keys):
        raise ParityError("invalid_output")
    return keys


def _content_ids(raw: bytes, limit: int = CQL_LIMIT) -> list[str]:
    identifiers: list[str] = []
    for row in _rows(raw, limit):
        value = row.get("id")
        if isinstance(value, bool):
            raise ParityError("invalid_output")
        if isinstance(value, int):
            text = str(value)
        elif isinstance(value, str):
            text = value
        else:
            raise ParityError("invalid_output")
        if _CONTENT_ID.fullmatch(text) is None:
            raise ParityError("invalid_output")
        identifiers.append(text)
    if len(set(identifiers)) != len(identifiers):
        raise ParityError("invalid_output")
    return identifiers


def _search_ids(raw: bytes, limit: int = SEARCH_LIMIT) -> list[tuple[str, str, str]]:
    identifiers: list[tuple[str, str, str]] = []
    for row in _rows(raw, limit):
        project = row.get("project")
        repository = row.get("repository")
        path = row.get("file")
        if not isinstance(project, str) or not valid_project(project):
            raise ParityError("invalid_output")
        if (
            not isinstance(repository, str)
            or _REPOSITORY_SLUG.fullmatch(repository) is None
            or repository in {".", ".."}
        ):
            raise ParityError("invalid_output")
        if not valid_path(path):
            raise ParityError("invalid_output")
        identifiers.append((project, repository, path))
    if len(set(identifiers)) != len(identifiers):
        raise ParityError("invalid_output")
    return identifiers


def _author_comment_pairs(
    raw: bytes, limit: int = AUTHOR_COMMENT_LIMIT
) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for row in _list_rows(raw, limit):
        key = row.get("key")
        if not isinstance(key, str) or _ISSUE_KEY.fullmatch(key) is None:
            raise ParityError("invalid_output")
        pairs.append((key, _positive_id_text(row.get("comment_id"))))
    if len(set(pairs)) != len(pairs):
        raise ParityError("invalid_output")
    return pairs


def _decode_text(raw: bytes) -> str:
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_OUTPUT_BYTES:
        raise ParityError("invalid_output")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        raise ParityError("invalid_output") from None


def _bbk_grep_page(
    raw: bytes, limit: int = GREP_LIMIT
) -> tuple[list[tuple[str, int]], bool]:
    lines = _decode_text(raw).splitlines()
    if not lines:
        raise ParityError("invalid_output")
    header = _BBK_GREP_HEADER.fullmatch(lines[0])
    if header is None:
        raise ParityError("invalid_output")
    declared = int(header.group("count"))
    if declared > limit:
        raise ParityError("invalid_output")
    hits: list[tuple[str, int]] = []
    for line in lines[1:]:
        if not line or line.startswith("#"):
            continue
        hit = _BBK_GREP_HIT.fullmatch(line)
        if hit is None:
            raise ParityError("invalid_output")
        path = hit.group("file")
        if not valid_path(path):
            raise ParityError("invalid_output")
        hits.append((path, int(hit.group("line"))))
    if len(hits) != declared or len(set(hits)) != len(hits):
        raise ParityError("invalid_output")
    return hits, header.group("partial") == "True"


def _atlawire_grep_page(
    raw: bytes, limit: int = GREP_LIMIT
) -> tuple[list[tuple[str, int]], bool, bool]:
    value = _json(raw)
    if not isinstance(value, dict):
        raise ParityError("invalid_output")
    hit_rows = value.get("hits")
    complete = value.get("complete")
    truncated = value.get("truncated")
    if (
        not isinstance(hit_rows, list)
        or not isinstance(complete, bool)
        or not isinstance(truncated, bool)
        or len(hit_rows) > limit
    ):
        raise ParityError("invalid_output")
    hits: list[tuple[str, int]] = []
    for item in hit_rows:
        if not isinstance(item, dict):
            raise ParityError("invalid_output")
        path = item.get("file")
        number = item.get("line")
        if not valid_path(path):
            raise ParityError("invalid_output")
        if isinstance(number, bool) or not isinstance(number, int) or number < 1:
            raise ParityError("invalid_output")
        hits.append((path, number))
    if len(set(hits)) != len(hits):
        raise ParityError("invalid_output")
    return hits, complete, truncated


def check_author_comment_parity(
    bbk_raw: bytes,
    atlawire_raw: bytes,
    expected_issue: str,
    expected_comment_id: str,
    limit: int = AUTHOR_COMMENT_LIMIT,
) -> None:
    """Compare stable issue/comment pairs and require the fixture anchor."""
    expected = (expected_issue, _positive_id_text(expected_comment_id))
    bbk_pairs = _author_comment_pairs(bbk_raw, limit)
    atlawire_pairs = _author_comment_pairs(atlawire_raw, limit)
    if expected not in bbk_pairs or expected not in atlawire_pairs:
        raise InconclusiveError("author_comment_fixture_not_in_both")
    if set(bbk_pairs) != set(atlawire_pairs):
        raise ParityError("parity_mismatch")


def check_repo_grep_parity(
    bbk_raw: bytes,
    atlawire_raw: bytes,
    expected_path: str,
    limit: int = GREP_LIMIT,
) -> None:
    """Compare stable file/line hits and require the expected file in both."""
    bbk_hits, bbk_partial = _bbk_grep_page(bbk_raw, limit)
    atlawire_hits, complete, truncated = _atlawire_grep_page(atlawire_raw, limit)
    if bbk_partial:
        raise InconclusiveError("grep_partial")
    if truncated:
        raise InconclusiveError("grep_limit_reached")
    if not complete:
        raise InconclusiveError("grep_partial")
    if len(bbk_hits) >= limit or len(atlawire_hits) >= limit:
        raise InconclusiveError("grep_limit_reached")
    bbk_files = {path for path, _ in bbk_hits}
    atlawire_files = {path for path, _ in atlawire_hits}
    if expected_path not in bbk_files or expected_path not in atlawire_files:
        raise InconclusiveError("grep_fixture_no_hit")
    if set(bbk_hits) != set(atlawire_hits):
        raise ParityError("parity_mismatch")


def _compare(
    bbk_ids: Sequence[object],
    atlawire_ids: Sequence[object],
    expected: object,
) -> None:
    if expected not in bbk_ids or expected not in atlawire_ids:
        raise ParityError("parity_mismatch")
    if list(bbk_ids) != list(atlawire_ids):
        raise ParityError("parity_mismatch")


def check_jql_parity(
    bbk_raw: bytes, atlawire_raw: bytes, expected_key: str, limit: int = JQL_LIMIT
) -> None:
    """Compare ordered Jira issue keys and require the expected key."""
    _compare(
        list(_jql_keys(bbk_raw, limit)),
        list(_jql_keys(atlawire_raw, limit)),
        expected_key,
    )


def check_cql_parity(
    bbk_raw: bytes, atlawire_raw: bytes, expected_id: str, limit: int = CQL_LIMIT
) -> None:
    """Compare ordered Confluence content IDs and require the expected ID."""
    _compare(
        list(_content_ids(bbk_raw, limit)),
        list(_content_ids(atlawire_raw, limit)),
        expected_id,
    )


def check_search_parity(
    bbk_raw: bytes,
    atlawire_raw: bytes,
    expected_repo: str,
    expected_path: str,
    limit: int = SEARCH_LIMIT,
) -> None:
    """Compare ordered search triples and require the expected repository path."""
    project, _, repository = expected_repo.partition("/")
    expected = (project, repository, expected_path)
    _compare(
        list(_search_ids(bbk_raw, limit)),
        list(_search_ids(atlawire_raw, limit)),
        expected,
    )


def _live_jql(
    environ: Mapping[str, str],
    runner: Callable[..., subprocess.CompletedProcess[bytes]],
) -> None:
    query = require_fixture(environ, JQL_QUERY_ENV, valid_query)
    expected = require_fixture(environ, JQL_KEY_ENV, valid_issue)
    bbk_raw, atlawire_raw = run_both(
        _json_plan("jql", query, JQL_LIMIT), runner=runner, environ=environ
    )
    check_jql_parity(bbk_raw, atlawire_raw, expected)


def _live_cql(
    environ: Mapping[str, str],
    runner: Callable[..., subprocess.CompletedProcess[bytes]],
) -> None:
    query = require_fixture(environ, CQL_QUERY_ENV, valid_query)
    expected = require_fixture(environ, CQL_ID_ENV, valid_content_id)
    bbk_raw, atlawire_raw = run_both(
        _json_plan("cql", query, CQL_LIMIT), runner=runner, environ=environ
    )
    check_cql_parity(bbk_raw, atlawire_raw, expected)


def _live_search(
    environ: Mapping[str, str],
    runner: Callable[..., subprocess.CompletedProcess[bytes]],
) -> None:
    query = require_fixture(environ, SEARCH_QUERY_ENV, valid_query)
    repo = require_fixture(environ, SEARCH_REPO_ENV, valid_repo)
    path = require_fixture(environ, SEARCH_PATH_ENV, valid_search_path)
    bbk_raw, atlawire_raw = run_both(
        search_plan(query, repo), runner=runner, environ=environ
    )
    check_search_parity(bbk_raw, atlawire_raw, repo, path)


def _live_author_comments(
    environ: Mapping[str, str],
    runner: Callable[..., subprocess.CompletedProcess[bytes]],
) -> None:
    issue = require_fixture(environ, JQL_KEY_ENV, valid_issue)
    comment_id = require_fixture(environ, JIRA_COMMENT_ENV, valid_comment_id)
    project = issue.split("-", 1)[0]
    if not valid_jira_project(project):
        raise FixtureError(JQL_KEY_ENV)
    bbk_plan, atlawire_plan = author_comment_plans(project)
    bbk_raw, atlawire_raw = run_pair(
        bbk_plan, atlawire_plan, runner=runner, environ=environ
    )
    check_author_comment_parity(bbk_raw, atlawire_raw, issue, comment_id)


def _live_repo_grep(
    environ: Mapping[str, str],
    runner: Callable[..., subprocess.CompletedProcess[bytes]],
) -> None:
    repo = require_fixture(environ, SEARCH_REPO_ENV, valid_repo)
    query = require_fixture(environ, SEARCH_QUERY_ENV, valid_query)
    path = require_fixture(environ, SEARCH_PATH_ENV, valid_grep_glob)
    ref = require_fixture(environ, GREP_REF_ENV, valid_commit)
    pattern = re.escape(query)
    if not valid_pattern(pattern):
        raise FixtureError(SEARCH_QUERY_ENV)
    bbk_plan, atlawire_plan = repo_grep_plans(repo, pattern, path, ref)
    bbk_raw, atlawire_raw = run_pair(
        bbk_plan, atlawire_plan, runner=runner, environ=environ
    )
    check_repo_grep_parity(bbk_raw, atlawire_raw, path)


def _run_live_check(check: Callable[[], None]) -> None:
    """Run one live check and report only a fixed category.

    ``pytest.fail(..., pytrace=False)`` prevents ``--showlocals`` from printing
    fixture, query, or captured output values. An unexpected ``Exception`` is
    reported as ``unexpected_error``. A fixture failure becomes
    ``fixture:<known-name>``, or ``fixture_error`` for an unrecognized name.
    An inconclusive fixture result becomes ``inconclusive:<reason>``.
    ``BaseException`` such as ``KeyboardInterrupt`` or ``SystemExit`` is not
    caught, so real aborts are not converted into check failures.
    """
    failure: str | None = None
    try:
        check()
    except ParityError as exc:
        failure = exc.category
    except InconclusiveError as exc:
        failure = f"inconclusive:{exc.reason}"
    except FixtureError as exc:
        failure = (
            f"fixture:{exc.name}" if exc.name in FIXTURE_NAMES else "fixture_error"
        )
    except Exception:  # noqa: BLE001 - intentional: report a fixed category
        failure = "unexpected_error"
    if failure is None:
        return
    pytest.fail(failure, pytrace=False)


def test_bbk_jql_issue_keys_match_atlawire() -> None:
    _run_live_check(lambda: _live_jql(os.environ, subprocess.run))


def test_bbk_cql_content_ids_match_atlawire() -> None:
    _run_live_check(lambda: _live_cql(os.environ, subprocess.run))


def test_bbk_search_repository_paths_match_atlawire() -> None:
    _run_live_check(lambda: _live_search(os.environ, subprocess.run))


def test_bbk_jira_author_comments_match_atlawire() -> None:
    _run_live_check(lambda: _live_author_comments(os.environ, subprocess.run))


def test_bbk_repo_grep_matches_atlawire() -> None:
    _run_live_check(lambda: _live_repo_grep(os.environ, subprocess.run))
