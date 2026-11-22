"""Opt-in live read-only checks for the current AtlaWire command batch.

Run only by explicit path, outside the default ``tests`` tree::

    C:/Python315/python.exe -B -m pytest -q checks/test_live_read_batch.py

Each check invokes the installed ``python -P -B -m atlawire`` and lets the CLI
load the owner's saved BBK credentials. This module never reads a credential
file, never passes tokens in arguments, and never prints child output, URLs,
fixture values, tokens, or exception details. A failed check reports one fixed
category; an empty live result or an object that cannot be discovered safely
reports ``inconclusive`` instead of passing. Proxy and CA environment settings
are not a supported connectivity mechanism for AtlaWire: its bearer session
sets ``trust_env = False``.

The suite reuses six existing fixture names from ``checks/live_read_only.py``
instead of asking for per-command expected values:

``ATLAWIRE_LIVE_JIRA_ISSUE``
    Issue used for the remote-link read.
``ATLAWIRE_LIVE_CONFLUENCE_PAGE_ID``
    Page used for attachments, comments, and labels.
``ATLAWIRE_LIVE_BITBUCKET_REPO``
    ``PROJECT/slug`` with read-only access.
``ATLAWIRE_LIVE_BITBUCKET_PR_ID``
    Pull request used for mergeability.
``ATLAWIRE_LIVE_BITBUCKET_FILE_PATH``
    Relative path used for ``last-modified``.
``ATLAWIRE_LIVE_BITBUCKET_FILE_REF``
    Full 40-hex revision used for ``last-modified``.

Further objects are discovered with bounded read-only commands:

* ``jira-me`` supplies the current Jira user name for ``jira-users``.
* ``tags REPO`` supplies the first safely usable tag name for ``tag``.
* ``page PAGE`` supplies the current page version for ``page-version`` and the
  space key for the ``confluence.space.get`` registered read.

Command contract of the current CLI (confirmed by source and loopback tests,
not yet executed against a real deployment):

* Every command except ``page-url`` exits 0 and prints exactly one JSON value
  on stdout; ``page-url`` prints one absolute HTTPS URL line.
* ``issue-remote-links``, ``jira-priorities``, ``jira-resolutions``,
  ``jira-issue-types``, ``jira-status-categories``, ``jira-users``, and
  ``tags`` print a JSON array of raw server objects.
* ``tag``, ``pr-merge-status``, ``page-history``, ``page-version``,
  ``jira-edit-meta``, ``jira-create-meta``, ``jira-transition-fields``, and
  ``whoami`` print one raw server object.
* ``page-attachments``, ``page-comments``, and ``page-labels`` print one raw
  paged object. Rows are under top-level ``results`` or, for the Confluence
  content-type-keyed comment response, under a top-level object's ``results``.
* ``last-modified`` prints one raw object with a ``files`` map from path to
  last-commit metadata and an optional ``latestCommit`` object.
* ``read-operation`` prints the raw JSON result of one hardcoded registered
  non-admin operation. The live suite permits only ``jira.project.get``,
  ``jira.issue.votes``, ``jira.issue.watchers``, ``bitbucket.project.get``,
  ``bitbucket.repository.get``, and ``confluence.space.get``, with fixed string
  parameters derived from the issue, page, and repository fixtures; arbitrary
  IDs, methods, URLs, query fields, or JSON shapes are rejected before spawning
  the CLI.
* ``page-comments`` requests ``depth=all`` and ``expand=body.storage``. Every
  returned comment, including nested replies, must expose a non-empty
  ``body.storage.value``.
* Tag identities are compared after stripping a ``refs/tags/`` prefix.
  ``last-modified`` commit fields are full 40-hex object IDs.
* Empty arrays, empty page ``results``, empty ``files``, empty metadata maps,
  no offered transitions, or a known path absent from ``files`` are
  ``inconclusive``; they are never a pass.
"""

import functools
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from urllib.parse import urlsplit

import pytest

CLI_PREFIX = (sys.executable, "-P", "-B", "-m", "atlawire")
TIMEOUT_SECONDS = 30
MAX_OUTPUT_BYTES = 4 * 1024 * 1024

# Exactly the batch commands plus the two read-only discovery commands. Adding
# a command here is a deliberate contract change; no write or admin command is
# permitted.
BATCH_COMMANDS = frozenset(
    {
        "issue-remote-links",
        "jira-priorities",
        "jira-resolutions",
        "jira-issue-types",
        "jira-status-categories",
        "jira-users",
        "pr-merge-status",
        "tags",
        "tag",
        "last-modified",
        "page-attachments",
        "page-comments",
        "page-labels",
        "page-history",
        "page-version",
        "page-url",
        "jira-edit-meta",
        "jira-create-meta",
        "jira-transition-fields",
        "whoami",
        "read-operation",
    }
)
DISCOVERY_COMMANDS = frozenset({"jira-me", "page"})
_DISCOVERY_ARITY = {"jira-me": 1, "page": 2}
ALLOWED_COMMANDS = BATCH_COMMANDS | DISCOVERY_COMMANDS

# Only these exact registered non-admin operations may be called through the
# live runner. Each operation has its fixed path-argument names; the runner also
# validates every value before spawning the CLI.
_READ_OPERATION_PARAMETERS = {
    "bitbucket.project.get": ("projectKey",),
    "bitbucket.repository.get": ("projectKey", "repositorySlug"),
    "confluence.space.get": ("spaceKey",),
    "jira.issue.votes": ("issueIdOrKey",),
    "jira.issue.watchers": ("issueIdOrKey",),
    "jira.project.get": ("projectIdOrKey",),
}
_READ_OPERATION_IDS = frozenset(_READ_OPERATION_PARAMETERS)

# Force the saved BBK file path: drop product URL/token variables from the
# child so an environment credential pair cannot replace the local store, and
# keep fixture variables out of the CLI process. Proxy and CA names are carried
# only as ambient OS values; the runner does not rely on them for connectivity.
# AtlaWire's bearer_session sets trust_env=False, so its requests transport does
# not use proxy environment settings.
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
_POSITIVE_ID = re.compile(r"[1-9][0-9]{0,18}")
_PAGE_ID = re.compile(r"[1-9][0-9]{0,19}")
_COMMIT = re.compile(r"[0-9A-Fa-f]{40}")
_JIRA_PROJECT_KEY = re.compile(r"[A-Z][A-Z0-9_]*")
_JIRA_CREATE_PROJECT_KEY = re.compile(r"[A-Z][A-Z0-9_]+")
_PROJECT_KEY = re.compile(r"~?[A-Za-z0-9_][A-Za-z0-9_.-]*")
_REPOSITORY_SLUG = re.compile(r"[A-Za-z0-9_.-]+")
_SPACE_KEY = re.compile(r"~?[A-Za-z0-9_][A-Za-z0-9_.-]*")
_GIT_TAG_BAD = frozenset(" ~^:?*[\\")
_FORBIDDEN_FLAGS = frozenset(
    {"--allow-http-loopback", "--base-url", "--token-from-env"}
)


class LiveCheckError(Exception):
    """Expected check failure carrying only a fixed category."""

    def __init__(self, category: str) -> None:
        super().__init__(category)
        self.category = category


class FixtureError(Exception):
    """Missing or invalid fixture carrying only the environment variable name."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.name = name


_EXPECTED_CATEGORIES = frozenset(
    {
        "cli_failed",
        "cli_unavailable",
        "inconclusive",
        "invalid_output",
        "invalid_plan",
        "oracle_mismatch",
        "timeout",
    }
)


def _live_test(function: Callable[[], None]) -> Callable[[], None]:
    """Convert every live failure into a fixed-message pytest failure.

    ``pytrace=False`` prevents ``--showlocals`` and traceback rendering from
    exposing fixture values, URLs, or captured API output held in local
    variables.
    """

    @functools.wraps(function)
    def wrapped() -> None:
        try:
            function()
        except FixtureError:
            pytest.fail("missing_fixture", pytrace=False)
        except LiveCheckError as exc:
            category = (
                exc.category
                if exc.category in _EXPECTED_CATEGORIES
                else "unexpected_error"
            )
            pytest.fail(category, pytrace=False)
        except Exception:  # noqa: BLE001 - replace all unexpected text
            pytest.fail("unexpected_error", pytrace=False)

    return wrapped


def child_environment(base: Mapping[str, str]) -> dict[str, str]:
    """Return ordinary OS settings plus the saved BBK path, never credentials."""
    return {name: value for name, value in base.items() if name.lower() in _ALLOWED_ENV}


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Reject duplicate JSON keys without echoing their text."""
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _valid_read_operation_arguments(operation_id: str, raw: str) -> bool:
    """Accept only the exact hardcoded operation parameters."""
    expected = _READ_OPERATION_PARAMETERS.get(operation_id)
    if expected is None or not isinstance(raw, str) or len(raw) > 4096:
        return False
    try:
        params = json.loads(raw, object_pairs_hook=_unique_object)
    except ValueError, RecursionError:
        return False
    if not isinstance(params, dict) or set(params) != set(expected):
        return False

    def text(name: str) -> str:
        value = params.get(name)
        return value if isinstance(value, str) else ""

    if operation_id == "jira.project.get":
        return _JIRA_PROJECT_KEY.fullmatch(text("projectIdOrKey")) is not None
    if operation_id in {"jira.issue.votes", "jira.issue.watchers"}:
        return _ISSUE_KEY.fullmatch(text("issueIdOrKey")) is not None
    if operation_id == "bitbucket.project.get":
        return _PROJECT_KEY.fullmatch(text("projectKey")) is not None
    if operation_id == "bitbucket.repository.get":
        return (
            _PROJECT_KEY.fullmatch(text("projectKey")) is not None
            and _REPOSITORY_SLUG.fullmatch(text("repositorySlug")) is not None
        )
    if operation_id == "confluence.space.get":
        return _SPACE_KEY.fullmatch(text("spaceKey")) is not None
    return False


def _valid_read_operation_plan(args: Sequence[str]) -> bool:
    return (
        len(args) == 4
        and args[2] == "--params"
        and _valid_read_operation_arguments(args[1], args[3])
    )


def _plan_error(args: Sequence[str]) -> bool:
    """Reject unknown commands, credential flags, and option-like arguments."""
    if not args or not all(isinstance(argument, str) and argument for argument in args):
        return True
    command = args[0]
    if command not in ALLOWED_COMMANDS:
        return True
    if command in DISCOVERY_COMMANDS:
        if len(args) != _DISCOVERY_ARITY[command]:
            return True
        return command == "page" and _PAGE_ID.fullmatch(args[1]) is None
    if command == "read-operation":
        return not _valid_read_operation_plan(args)
    if command == "whoami":
        return len(args) != 1
    if command in {"page-history", "page-url"}:
        return len(args) != 2 or _PAGE_ID.fullmatch(args[1]) is None
    if command == "page-version":
        return (
            len(args) != 3
            or _PAGE_ID.fullmatch(args[1]) is None
            or _POSITIVE_ID.fullmatch(args[2]) is None
        )
    if command in {"jira-edit-meta", "jira-transition-fields"}:
        return len(args) != 2 or _ISSUE_KEY.fullmatch(args[1]) is None
    if command == "jira-create-meta":
        return (
            len(args) != 4
            or args[2] != "--project"
            or _JIRA_CREATE_PROJECT_KEY.fullmatch(args[3]) is None
        )
    for index, argument in enumerate(args):
        if argument in _FORBIDDEN_FLAGS or argument.startswith("--base-url="):
            return True
        if argument.startswith("-"):
            is_at = (
                argument == "--at"
                and command == "last-modified"
                and index == len(args) - 2
            )
            if not is_at:
                return True
    return False


def run_cli(
    args: Sequence[str],
    *,
    timeout: int = TIMEOUT_SECONDS,
    runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
    environ: Mapping[str, str] | None = None,
) -> bytes:
    """Run one fixed read-only command and return stdout bytes only.

    Captured stdout and stderr are never printed or attached to an exception.
    A nonzero exit, timeout, launch failure, or invalid output raises one fixed
    category so fixture values and server data cannot leak.
    """
    plan = tuple(args)
    if _plan_error(plan):
        raise LiveCheckError("invalid_plan")
    base = os.environ if environ is None else environ
    try:
        completed = runner(
            [*CLI_PREFIX, *plan],
            env=child_environment(base),
            capture_output=True,
            timeout=timeout,
            check=False,
            shell=False,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        raise LiveCheckError("timeout") from None
    except OSError, UnicodeError:
        raise LiveCheckError("cli_unavailable") from None
    if completed.returncode != 0:
        raise LiveCheckError("cli_failed")
    if not isinstance(completed.stdout, bytes) or not completed.stdout:
        raise LiveCheckError("invalid_output")
    if len(completed.stdout) > MAX_OUTPUT_BYTES:
        raise LiveCheckError("invalid_output")
    return completed.stdout


def run_read_operation(
    operation_id: str,
    arguments: Mapping[str, str],
    *,
    runner: Callable[..., subprocess.CompletedProcess[bytes]] = subprocess.run,
    environ: Mapping[str, str] | None = None,
) -> bytes:
    """Run one hardcoded registered read operation with fixed JSON parameters."""
    if operation_id not in _READ_OPERATION_IDS:
        raise LiveCheckError("invalid_plan")
    payload = json.dumps(dict(arguments), sort_keys=True, separators=(",", ":"))
    return run_cli(
        ("read-operation", operation_id, "--params", payload),
        runner=runner,
        environ=environ,
    )


def require_fixture(
    environ: Mapping[str, str], name: str, validator: Callable[[str], bool]
) -> str:
    """Return one required fixture or fail with the variable name only."""
    value = environ.get(name, "")
    if not value or not validator(value):
        raise FixtureError(name)
    return value


def _plain(value: str, *, limit: int) -> bool:
    return (
        bool(value)
        and len(value) <= limit
        and value == value.strip()
        and not value.startswith("-")
        and _CONTROL.search(value) is None
    )


def valid_issue(value: str) -> bool:
    return _ISSUE_KEY.fullmatch(value) is not None


def valid_positive_id(value: str) -> bool:
    return _POSITIVE_ID.fullmatch(value) is not None


def valid_page_id(value: str) -> bool:
    return _PAGE_ID.fullmatch(value) is not None


def valid_query(value: str) -> bool:
    return _plain(value, limit=500)


def valid_repo(value: str) -> bool:
    project, separator, slug = value.partition("/")
    return (
        bool(separator)
        and "/" not in slug
        and slug not in {".", ".."}
        and _PROJECT_KEY.fullmatch(project) is not None
        and _REPOSITORY_SLUG.fullmatch(slug) is not None
    )


def valid_tag(value: str) -> bool:
    if not _plain(value, limit=255) or ".." in value:
        return False
    if value.startswith("/") or value.endswith("/") or "//" in value:
        return False
    if "@{" in value:
        return False
    if any(character in _GIT_TAG_BAD for character in value):
        return False
    if value.endswith((".", ".lock")):
        return False
    return all(segment not in {"", ".", ".."} for segment in value.split("/"))


def valid_commit(value: str) -> bool:
    return _COMMIT.fullmatch(value) is not None


def valid_path(value: str) -> bool:
    if not _plain(value, limit=1024) or "\\" in value:
        return False
    if value.startswith("/") or value.endswith("/") or "//" in value:
        return False
    if re.search(r"%[0-9A-Fa-f]{2}", value):
        return False
    return all(segment not in {"", ".", ".."} for segment in value.split("/"))


def _json(raw: bytes) -> object:
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_OUTPUT_BYTES:
        raise LiveCheckError("invalid_output")
    try:
        return json.loads(raw.decode("utf-8"))
    except UnicodeDecodeError, ValueError, RecursionError:
        raise LiveCheckError("invalid_output") from None


def _object(raw: bytes) -> dict[str, object]:
    value = _json(raw)
    if not isinstance(value, dict):
        raise LiveCheckError("invalid_output")
    return value


def _nonempty_array(raw: bytes) -> list[object]:
    value = _json(raw)
    if not isinstance(value, list):
        raise LiveCheckError("invalid_output")
    if not value:
        raise LiveCheckError("inconclusive")
    return value


def _as_row(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise LiveCheckError("invalid_output")
    return value


def _text(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LiveCheckError("invalid_output")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise LiveCheckError("invalid_output") from None
    return value


def _display(value: object) -> str:
    text = _text(value)
    if _CONTROL.search(text):
        raise LiveCheckError("invalid_output")
    return text


def _identifier(value: object) -> str:
    if isinstance(value, bool):
        raise LiveCheckError("invalid_output")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str) and value.strip():
        return value
    raise LiveCheckError("invalid_output")


def _relative_path(value: object) -> str:
    if not isinstance(value, str) or not valid_path(value):
        raise LiveCheckError("invalid_output")
    return value


def _commit(value: object) -> str:
    if not isinstance(value, str) or _COMMIT.fullmatch(value) is None:
        raise LiveCheckError("invalid_output")
    return value.lower()


def _nested_commit(value: object) -> str:
    if isinstance(value, str):
        return _commit(value)
    if isinstance(value, dict):
        for key in ("id", "hash", "displayId"):
            if value.get(key) is not None:
                return _commit(value[key])
    raise LiveCheckError("invalid_output")


def _tag_name(value: object) -> str:
    if isinstance(value, str):
        return _display(value).removeprefix("refs/tags/")
    row = _as_row(value)
    for key in ("displayId", "name", "id"):
        if row.get(key) is not None:
            return _display(row[key]).removeprefix("refs/tags/")
    raise LiveCheckError("invalid_output")


def _comment_body(row: dict[str, object]) -> None:
    """Require the storage body requested by ``expand=body.storage``."""
    body = row.get("body")
    if not isinstance(body, dict):
        raise LiveCheckError("invalid_output")
    storage = body.get("storage")
    if not isinstance(storage, dict):
        raise LiveCheckError("invalid_output")
    value = storage.get("value")
    if not isinstance(value, str) or not value.strip():
        raise LiveCheckError("invalid_output")


def _comment_rows(raw: bytes) -> list[dict[str, object]]:
    """Collect root comments and nested replies from a raw comment page."""
    rows: list[dict[str, object]] = []
    seen: set[str] = set()
    stack = list(reversed(_page_rows(raw)))
    while stack:
        row = _as_row(stack.pop())
        identifier = _identifier(row.get("id"))
        if identifier in seen:
            continue
        seen.add(identifier)
        rows.append(row)
        children = row.get("children")
        if children is None:
            continue
        if not isinstance(children, dict):
            raise LiveCheckError("invalid_output")
        nested_groups: list[list[object]] = []
        direct = children.get("results")
        if isinstance(direct, list):
            nested_groups.append(direct)
        comment_children = children.get("comment")
        if isinstance(comment_children, dict):
            nested = comment_children.get("results")
            if isinstance(nested, list):
                nested_groups.append(nested)
        for group in nested_groups:
            stack.extend(reversed(group))
    if not rows:
        raise LiveCheckError("inconclusive")
    return rows


def _label_name(value: object) -> str:
    if isinstance(value, str):
        return _display(value)
    row = _as_row(value)
    for key in ("name", "label", "text"):
        if row.get(key) is not None:
            return _display(row[key])
    raise LiveCheckError("invalid_output")


def check_reference_list(raw: bytes) -> None:
    """Validate a non-empty Jira reference array with readable names."""
    named = 0
    for item in _nonempty_array(raw):
        row = _as_row(item)
        _identifier(row.get("id"))
        if row.get("name") is not None:
            _display(row["name"])
            named += 1
    if named == 0:
        raise LiveCheckError("inconclusive")


def check_remote_links(raw: bytes) -> None:
    """Validate a non-empty remote-link array with link objects."""
    for item in _nonempty_array(raw):
        row = _as_row(item)
        _identifier(row.get("id"))
        if row.get("globalId") is not None:
            _text(row["globalId"])
        if row.get("relationship") is not None:
            _text(row["relationship"])
        for key in ("application", "object"):
            if row.get(key) is not None:
                _as_row(row[key])


def check_current_user(raw: bytes) -> str:
    """Return the authenticated Jira user name for a bounded user search."""
    row = _object(raw)
    name = _text(row.get("name"))
    if not valid_query(name):
        raise LiveCheckError("invalid_output")
    if row.get("displayName") is not None and not isinstance(row["displayName"], str):
        raise LiveCheckError("invalid_output")
    if row.get("email") is not None and not isinstance(row["email"], str):
        raise LiveCheckError("invalid_output")
    return name


def check_users(raw: bytes, expected_name: str) -> None:
    """Validate a non-empty user page and require the discovered user."""
    found = False
    for item in _nonempty_array(raw):
        row = _as_row(item)
        name = _text(row.get("name"))
        _text(row.get("displayName"))
        if row.get("emailAddress") is not None and not isinstance(
            row["emailAddress"], str
        ):
            raise LiveCheckError("invalid_output")
        if "active" in row and not isinstance(row["active"], bool):
            raise LiveCheckError("invalid_output")
        if name == expected_name:
            found = True
    if not found:
        raise LiveCheckError("oracle_mismatch")


def check_merge_status(raw: bytes) -> None:
    """Validate mergeability booleans, outcome, and their local invariant."""
    row = _object(raw)
    can_merge = row.get("canMerge")
    conflicted = row.get("conflicted")
    if not isinstance(can_merge, bool) or not isinstance(conflicted, bool):
        raise LiveCheckError("invalid_output")
    _display(row.get("outcome"))
    vetoes = row.get("vetoes")
    if vetoes is not None and (
        not isinstance(vetoes, list)
        or not all(isinstance(veto, dict) for veto in vetoes)
    ):
        raise LiveCheckError("invalid_output")
    if conflicted and can_merge:
        raise LiveCheckError("oracle_mismatch")


def check_tags(raw: bytes) -> list[str]:
    """Validate a non-empty tag array and return its display names."""
    return [_tag_name(item) for item in _nonempty_array(raw)]


def check_tag(raw: bytes, expected_tag: str) -> None:
    """Validate one tag object, its identity, and any present commit fields."""
    row = _object(raw)
    identities: list[str] = []
    for key in ("displayId", "name", "tag", "id"):
        if row.get(key) is not None:
            identities.append(_display(row[key]).removeprefix("refs/tags/"))
    if not identities:
        raise LiveCheckError("invalid_output")
    if expected_tag not in identities:
        raise LiveCheckError("oracle_mismatch")
    if "type" in row and row["type"] != "TAG":
        raise LiveCheckError("invalid_output")
    for key in ("latestCommit", "latestChangeset", "commit", "hash"):
        value = row.get(key)
        if value is None or value == "":
            continue
        _nested_commit(value)


def check_last_modified(raw: bytes, expected_path: str) -> None:
    """Validate the raw ``files`` map and require the known path."""
    row = _object(raw)
    files = row.get("files")
    if not isinstance(files, dict):
        raise LiveCheckError("invalid_output")
    if not files:
        raise LiveCheckError("inconclusive")
    found = False
    for path, entry in files.items():
        safe_path = _relative_path(path)
        metadata = _as_row(entry)
        commit = None
        for key in ("id", "commit", "hash", "latestCommit", "latestChangeset"):
            if metadata.get(key) is not None:
                commit = _nested_commit(metadata[key])
                break
        if commit is None:
            raise LiveCheckError("invalid_output")
        if safe_path == expected_path:
            found = True
    latest_commit = row.get("latestCommit")
    if latest_commit is not None:
        latest = _as_row(latest_commit)
        if latest.get("id") is not None:
            _nested_commit(latest["id"])
    if not found:
        raise LiveCheckError("inconclusive")


def _page_rows(raw: bytes) -> list[object]:
    """Return rows from a flat page or a content-type-keyed Confluence page."""
    page = _object(raw)
    groups: list[list[object]] = []
    results = page.get("results")
    if results is not None:
        if not isinstance(results, list):
            raise LiveCheckError("invalid_output")
        groups.append(results)
    for value in page.values():
        if isinstance(value, dict):
            nested = value.get("results")
            if nested is not None:
                if not isinstance(nested, list):
                    raise LiveCheckError("invalid_output")
                groups.append(nested)
    rows = [row for group in groups for row in group]
    if not rows:
        raise LiveCheckError("inconclusive")
    return rows


def check_page_attachments(raw: bytes) -> None:
    """Validate a non-empty attachment page and its metadata rows."""
    for item in _page_rows(raw):
        row = _as_row(item)
        _identifier(row.get("id"))
        _display(row.get("title"))


def check_page_comments(raw: bytes) -> None:
    """Validate comments and replies, including their requested storage bodies."""
    for row in _comment_rows(raw):
        _identifier(row.get("id"))
        _comment_body(row)
        if "type" in row and row["type"] != "comment":
            raise LiveCheckError("invalid_output")


def check_page_labels(raw: bytes) -> None:
    """Validate a non-empty label page and its label rows."""
    for item in _page_rows(raw):
        row = item if isinstance(item, str) else _as_row(item)
        _label_name(item)
        if isinstance(row, dict):
            if row.get("prefix") is not None:
                _text(row["prefix"])
            if "id" in row:
                _identifier(row["id"])


def check_page_history(raw: bytes) -> None:
    """Validate a non-empty history object with at least one known field."""
    row = _object(raw)
    known = 0
    if "latest" in row:
        if not isinstance(row["latest"], bool):
            raise LiveCheckError("invalid_output")
        known += 1
    if "createdDate" in row:
        _text(row["createdDate"])
        known += 1
    if "lastUpdated" in row:
        _as_row(row["lastUpdated"])
        known += 1
    if "createdBy" in row:
        _as_row(row["createdBy"])
        known += 1
    if known == 0:
        raise LiveCheckError("inconclusive")


def _page_identity(raw: bytes, expected_page: str) -> dict[str, object]:
    row = _object(raw)
    identifier = _identifier(row.get("id"))
    if identifier != expected_page:
        raise LiveCheckError("oracle_mismatch")
    return row


def check_page_version_source(raw: bytes, expected_page: str) -> int:
    """Return the current positive version number of the known page."""
    row = _page_identity(raw, expected_page)
    version = row.get("version")
    if not isinstance(version, dict):
        raise LiveCheckError("inconclusive")
    number = version.get("number")
    if isinstance(number, bool) or not isinstance(number, int) or number < 1:
        raise LiveCheckError("inconclusive")
    return number


def check_page_space_source(raw: bytes, expected_page: str) -> str:
    """Return the known page's space key for the fixed space read."""
    row = _page_identity(raw, expected_page)
    space = row.get("space")
    if not isinstance(space, dict):
        raise LiveCheckError("inconclusive")
    key = space.get("key")
    if not isinstance(key, str) or _SPACE_KEY.fullmatch(key) is None:
        raise LiveCheckError("inconclusive")
    return key


def check_page_version(raw: bytes, expected_page: str, expected_version: int) -> None:
    """Validate one historical page version and its storage body."""
    row = _page_identity(raw, expected_page)
    if row.get("type") != "page":
        raise LiveCheckError("invalid_output")
    version = row.get("version")
    if not isinstance(version, dict):
        raise LiveCheckError("invalid_output")
    number = version.get("number")
    if isinstance(number, bool) or not isinstance(number, int):
        raise LiveCheckError("invalid_output")
    if number != expected_version:
        raise LiveCheckError("oracle_mismatch")
    if row.get("status") is not None and row["status"] != "historical":
        raise LiveCheckError("invalid_output")
    body = row.get("body")
    storage = body.get("storage") if isinstance(body, dict) else None
    value = storage.get("value") if isinstance(storage, dict) else None
    if not isinstance(value, str) or not value.strip():
        raise LiveCheckError("invalid_output")


def check_page_url(raw: bytes) -> None:
    """Validate one absolute HTTPS browser URL without credentials."""
    if not isinstance(raw, bytes) or not raw or len(raw) > 4096:
        raise LiveCheckError("invalid_output")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise LiveCheckError("invalid_output") from None
    if text.endswith("\r\n"):
        text = text[:-2]
    elif text.endswith("\n"):
        text = text[:-1]
    if (
        not text
        or _CONTROL.search(text)
        or any(character.isspace() for character in text)
    ):
        raise LiveCheckError("invalid_output")
    try:
        parts = urlsplit(text)
        host = parts.hostname
        port = parts.port
    except ValueError:
        raise LiveCheckError("invalid_output") from None
    if (
        parts.scheme != "https"
        or not host
        or parts.username is not None
        or parts.password is not None
        or port == 0
        or not parts.path.startswith("/")
    ):
        raise LiveCheckError("invalid_output")


def check_edit_meta(raw: bytes) -> None:
    """Validate a non-empty Jira edit metadata field map."""
    row = _object(raw)
    fields = row.get("fields")
    if not isinstance(fields, dict):
        raise LiveCheckError("invalid_output")
    if not fields:
        raise LiveCheckError("inconclusive")
    for value in fields.values():
        _as_row(value)


def check_create_meta(raw: bytes, expected_project: str) -> None:
    """Validate create metadata and the known project's presence."""
    row = _object(raw)
    projects = row.get("projects")
    if not isinstance(projects, list):
        raise LiveCheckError("invalid_output")
    if not projects:
        raise LiveCheckError("inconclusive")
    found = False
    for item in projects:
        project = _as_row(item)
        key = project.get("key")
        if isinstance(key, str) and key == expected_project:
            found = True
        issue_types = project.get("issuetypes")
        if issue_types is not None:
            if not isinstance(issue_types, list):
                raise LiveCheckError("invalid_output")
            for issue_type in issue_types:
                issue_row = _as_row(issue_type)
                fields = issue_row.get("fields")
                if fields is not None:
                    if not isinstance(fields, dict):
                        raise LiveCheckError("invalid_output")
                    for field in fields.values():
                        _as_row(field)
    if not found:
        raise LiveCheckError("oracle_mismatch")


def check_transition_fields(raw: bytes) -> None:
    """Validate a non-empty Jira transition list with optional field maps."""
    row = _object(raw)
    transitions = row.get("transitions")
    if not isinstance(transitions, list):
        raise LiveCheckError("invalid_output")
    if not transitions:
        raise LiveCheckError("inconclusive")
    for item in transitions:
        transition = _as_row(item)
        _identifier(transition.get("id"))
        _text(transition.get("name"))
        if transition.get("to") is not None:
            _as_row(transition["to"])
        fields = transition.get("fields")
        if fields is not None:
            if not isinstance(fields, dict):
                raise LiveCheckError("invalid_output")
            for field in fields.values():
                _as_row(field)


def check_whoami(raw: bytes) -> None:
    """Validate successful per-product identity checks from ``whoami``."""
    row = _object(raw)
    confluence = _as_row(row.get("confluence"))
    jira = _as_row(row.get("jira"))
    bitbucket = _as_row(row.get("bitbucket"))
    for entry in (confluence, jira, bitbucket):
        if entry.get("ok") is not True:
            raise LiveCheckError("oracle_mismatch")
    confluence_identity = _as_row(confluence.get("identity"))
    _text(confluence_identity.get("username"))
    if confluence_identity.get("displayName") is not None and not isinstance(
        confluence_identity["displayName"], str
    ):
        raise LiveCheckError("invalid_output")
    jira_identity = _as_row(jira.get("identity"))
    _text(jira_identity.get("name"))
    if jira_identity.get("displayName") is not None and not isinstance(
        jira_identity["displayName"], str
    ):
        raise LiveCheckError("invalid_output")
    if bitbucket.get("authenticated") is not True:
        raise LiveCheckError("oracle_mismatch")


def check_jira_project(raw: bytes, expected_project: str) -> None:
    """Validate the known Jira project key from ``jira.project.get``."""
    row = _object(raw)
    if _text(row.get("key")) != expected_project:
        raise LiveCheckError("oracle_mismatch")


def check_jira_votes(raw: bytes) -> None:
    """Validate the documented Jira votes object."""
    row = _object(raw)
    votes = row.get("votes")
    if isinstance(votes, bool) or not isinstance(votes, int) or votes < 0:
        raise LiveCheckError("invalid_output")
    if not isinstance(row.get("hasVoted"), bool):
        raise LiveCheckError("invalid_output")
    voters = row.get("voters")
    if not isinstance(voters, list) or not all(
        isinstance(voter, dict) for voter in voters
    ):
        raise LiveCheckError("invalid_output")


def check_jira_watchers(raw: bytes) -> None:
    """Validate the documented Jira watchers object."""
    row = _object(raw)
    count = row.get("watchCount")
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise LiveCheckError("invalid_output")
    watchers = row.get("watchers")
    if not isinstance(watchers, list) or not all(
        isinstance(watcher, dict) for watcher in watchers
    ):
        raise LiveCheckError("invalid_output")


def check_bitbucket_project(raw: bytes, expected_project: str) -> None:
    """Validate the known Bitbucket project key."""
    row = _object(raw)
    if _text(row.get("key")) != expected_project:
        raise LiveCheckError("oracle_mismatch")


def check_bitbucket_repository(
    raw: bytes, expected_project: str, expected_slug: str
) -> None:
    """Validate the known Bitbucket repository identity."""
    row = _object(raw)
    if _text(row.get("slug")) != expected_slug:
        raise LiveCheckError("oracle_mismatch")
    project = _as_row(row.get("project"))
    if _text(project.get("key")) != expected_project:
        raise LiveCheckError("oracle_mismatch")


def check_confluence_space(raw: bytes, expected_space: str) -> None:
    """Validate the known Confluence space key."""
    row = _object(raw)
    if _text(row.get("key")) != expected_space:
        raise LiveCheckError("oracle_mismatch")


def _jira_project(issue: str) -> str:
    project, separator, _ = issue.partition("-")
    if not separator or _JIRA_PROJECT_KEY.fullmatch(project) is None:
        raise LiveCheckError("inconclusive")
    return project


def _jira_create_project(issue: str) -> str:
    project = _jira_project(issue)
    if _JIRA_CREATE_PROJECT_KEY.fullmatch(project) is None:
        raise LiveCheckError("inconclusive")
    return project


def _repo_parts(repo: str) -> tuple[str, str]:
    project, separator, slug = repo.partition("/")
    if (
        not separator
        or _PROJECT_KEY.fullmatch(project) is None
        or _REPOSITORY_SLUG.fullmatch(slug) is None
    ):
        raise LiveCheckError("inconclusive")
    return project, slug


def _fixture(name: str, validator: Callable[[str], bool]) -> str:
    return require_fixture(os.environ, name, validator)


@_live_test
def test_jira_issue_remote_links_return_objects() -> None:
    issue = _fixture("ATLAWIRE_LIVE_JIRA_ISSUE", valid_issue)
    check_remote_links(run_cli(("issue-remote-links", issue)))


@_live_test
def test_jira_priorities_are_readable() -> None:
    check_reference_list(run_cli(("jira-priorities",)))


@_live_test
def test_jira_resolutions_are_readable() -> None:
    check_reference_list(run_cli(("jira-resolutions",)))


@_live_test
def test_jira_issue_types_are_readable() -> None:
    check_reference_list(run_cli(("jira-issue-types",)))


@_live_test
def test_jira_status_categories_are_readable() -> None:
    check_reference_list(run_cli(("jira-status-categories",)))


@_live_test
def test_jira_users_include_current_user() -> None:
    name = check_current_user(run_cli(("jira-me",)))
    check_users(run_cli(("jira-users", name)), name)


@_live_test
def test_bitbucket_pull_request_merge_status_is_readable() -> None:
    repo = _fixture("ATLAWIRE_LIVE_BITBUCKET_REPO", valid_repo)
    pr_id = _fixture("ATLAWIRE_LIVE_BITBUCKET_PR_ID", valid_positive_id)
    check_merge_status(run_cli(("pr-merge-status", repo, pr_id)))


@_live_test
def test_bitbucket_tags_and_tag_use_a_discovered_tag() -> None:
    repo = _fixture("ATLAWIRE_LIVE_BITBUCKET_REPO", valid_repo)
    names = check_tags(run_cli(("tags", repo)))
    tag = next((name for name in names if valid_tag(name)), None)
    if tag is None:
        raise LiveCheckError("inconclusive")
    check_tag(run_cli(("tag", repo, tag)), tag)


@_live_test
def test_bitbucket_last_modified_contains_known_path() -> None:
    repo = _fixture("ATLAWIRE_LIVE_BITBUCKET_REPO", valid_repo)
    path = _fixture("ATLAWIRE_LIVE_BITBUCKET_FILE_PATH", valid_path)
    ref = _fixture("ATLAWIRE_LIVE_BITBUCKET_FILE_REF", valid_commit)
    raw = run_cli(("last-modified", repo, path, "--at", ref))
    check_last_modified(raw, path)


@_live_test
def test_confluence_page_attachments_are_readable() -> None:
    page = _fixture("ATLAWIRE_LIVE_CONFLUENCE_PAGE_ID", valid_page_id)
    check_page_attachments(run_cli(("page-attachments", page)))


@_live_test
def test_confluence_page_comments_include_storage_bodies() -> None:
    page = _fixture("ATLAWIRE_LIVE_CONFLUENCE_PAGE_ID", valid_page_id)
    check_page_comments(run_cli(("page-comments", page)))


@_live_test
def test_confluence_page_labels_are_readable() -> None:
    page = _fixture("ATLAWIRE_LIVE_CONFLUENCE_PAGE_ID", valid_page_id)
    check_page_labels(run_cli(("page-labels", page)))


@_live_test
def test_confluence_page_history_is_readable() -> None:
    page = _fixture("ATLAWIRE_LIVE_CONFLUENCE_PAGE_ID", valid_page_id)
    check_page_history(run_cli(("page-history", page)))


@_live_test
def test_confluence_page_version_uses_discovered_previous_version() -> None:
    page = _fixture("ATLAWIRE_LIVE_CONFLUENCE_PAGE_ID", valid_page_id)
    current = check_page_version_source(run_cli(("page", page)), page)
    if current <= 1:
        raise LiveCheckError("inconclusive")
    version = current - 1
    check_page_version(run_cli(("page-version", page, str(version))), page, version)


@_live_test
def test_confluence_page_url_is_absolute_https() -> None:
    page = _fixture("ATLAWIRE_LIVE_CONFLUENCE_PAGE_ID", valid_page_id)
    check_page_url(run_cli(("page-url", page)))


@_live_test
def test_jira_edit_metadata_is_readable() -> None:
    issue = _fixture("ATLAWIRE_LIVE_JIRA_ISSUE", valid_issue)
    check_edit_meta(run_cli(("jira-edit-meta", issue)))


@_live_test
def test_jira_create_metadata_contains_known_project() -> None:
    issue = _fixture("ATLAWIRE_LIVE_JIRA_ISSUE", valid_issue)
    project = _jira_create_project(issue)
    check_create_meta(run_cli(("jira-create-meta", "--project", project)), project)


@_live_test
def test_jira_transition_fields_are_readable() -> None:
    issue = _fixture("ATLAWIRE_LIVE_JIRA_ISSUE", valid_issue)
    check_transition_fields(run_cli(("jira-transition-fields", issue)))


@_live_test
def test_whoami_reports_all_three_products() -> None:
    check_whoami(run_cli(("whoami",)))


@_live_test
def test_read_operation_jira_project_uses_known_issue_project() -> None:
    issue = _fixture("ATLAWIRE_LIVE_JIRA_ISSUE", valid_issue)
    project = _jira_project(issue)
    raw = run_read_operation("jira.project.get", {"projectIdOrKey": project})
    check_jira_project(raw, project)


@_live_test
def test_read_operation_jira_votes_use_known_issue() -> None:
    issue = _fixture("ATLAWIRE_LIVE_JIRA_ISSUE", valid_issue)
    raw = run_read_operation("jira.issue.votes", {"issueIdOrKey": issue})
    check_jira_votes(raw)


@_live_test
def test_read_operation_jira_watchers_use_known_issue() -> None:
    issue = _fixture("ATLAWIRE_LIVE_JIRA_ISSUE", valid_issue)
    raw = run_read_operation("jira.issue.watchers", {"issueIdOrKey": issue})
    check_jira_watchers(raw)


@_live_test
def test_read_operation_bitbucket_project_uses_known_repo() -> None:
    repo = _fixture("ATLAWIRE_LIVE_BITBUCKET_REPO", valid_repo)
    project, _ = _repo_parts(repo)
    raw = run_read_operation("bitbucket.project.get", {"projectKey": project})
    check_bitbucket_project(raw, project)


@_live_test
def test_read_operation_bitbucket_repository_uses_known_repo() -> None:
    repo = _fixture("ATLAWIRE_LIVE_BITBUCKET_REPO", valid_repo)
    project, slug = _repo_parts(repo)
    raw = run_read_operation(
        "bitbucket.repository.get",
        {"projectKey": project, "repositorySlug": slug},
    )
    check_bitbucket_repository(raw, project, slug)


@_live_test
def test_read_operation_confluence_space_uses_discovered_page_space() -> None:
    page = _fixture("ATLAWIRE_LIVE_CONFLUENCE_PAGE_ID", valid_page_id)
    space = check_page_space_source(run_cli(("page", page)), page)
    raw = run_read_operation("confluence.space.get", {"spaceKey": space})
    check_confluence_space(raw, space)
