"""Read-only regex search over one immutable Bitbucket repository snapshot.

The search is a fan-out: one paginated ``/files`` walk, then one raw read per
eligible file. No archive is downloaded, so ZIP-expansion risks are absent;
the cost is one request and one killable regex helper per eligible file.

Essential contract:

* The ref is resolved once to a full 40-hex commit, then every file listing and
  raw read sends that commit as ``at``. Full commits are verified, exact branch
  and tag names are looked up, qualified ``refs/heads/...`` and
  ``refs/tags/...`` are accepted, and a name that exists as both a branch and a
  tag is rejected rather than guessed. A tag response is used only when at least
  one documented identity matches the requested name (short or ``refs/tags/``
  form); when both fields carry values both must match, and a contradictory or
  unusable identity fails before any file listing. With no ref, the unique
  default branch in the complete branch listing is used.
* With a pattern and neither ``glob`` nor ``path``, only files with a known
  text suffix (``TEXT_SUFFIXES``) are eligible. That is reported as
  ``selection="text-suffixes"`` and excluded paths are counted in
  ``files_excluded``. Supplying either filter selects explicitly
  (``selection="explicit"``); an eligible unreadable, binary, non-UTF-8 or
  over-1-MiB file then fails the whole call instead of being skipped.
* With ``pattern=None`` the call is a filtered path listing: the same pinned
  ref and complete paginated ``/files`` walk are used, explicit glob/path
  filters apply, and all paths are listed when neither is present (no default
  text-suffix scope). No raw-file read or regex helper runs.
  ``selection="all-paths"`` without filters and ``"explicit"`` with them;
  ``files`` holds at most ``limit`` paths, ``files_eligible`` counts every
  matched path, and ``truncated``/``complete`` describe the output cap.
* The caller regex runs only in an isolated helper that receives its request on
  stdin, prints matched line numbers, and is killed on timeout with a bounded
  reap attempt. The pattern and text are not command-line arguments, and the
  helper inherits no AtlaWire token. ``timeout_s`` bounds the whole call
  cooperatively: it is checked before every ref request, before each listing or
  branch page request, after the listing, after the scan, and around every file
  read. An in-flight HTTP request is not cancelled, only bounded by the shared
  5 s connect/30 s read timeouts.
* Every listing failure, page-cap hit, read failure, ref failure or timeout
  raises [AtlaWireError][atlawire.http.AtlaWireError] without a result. Every
  success reports ``files_eligible``, ``files_scanned``, ``files_excluded``,
  ``truncated`` and ``complete``. In regex mode ``complete`` means every
  eligible file was searched and each hit keeps at most ``HIT_TEXT_LIMIT``
  (300) characters, marked by ``text_truncated``. In listing mode
  ``files_scanned`` is zero and ``complete`` means the matched list fit within
  ``limit``. The ``glob`` filter is in-process ``fnmatch`` and is not covered by
  the helper timeout.
"""

import fnmatch
import math
import re
from collections.abc import Callable, Mapping
from time import monotonic as _monotonic
from typing import Literal, Never, TypedDict

from atlawire import regex_helper
from atlawire.bitbucket import (
    get_branch,
    get_commit,
    get_repository_file,
    get_tag,
    list_repository_files,
)
from atlawire.http import AtlaWireError, normalize_base_url
from atlawire.operations import read_operation

GREP_LIMIT_MIN = 1
GREP_LIMIT_MAX = 1000
GREP_LIMIT_DEFAULT = 200
GREP_TIMEOUT_DEFAULT = 20.0
REGEX_TIMEOUT_DEFAULT = 5.0
HIT_TEXT_LIMIT = 300
TEXT_SUFFIXES = frozenset(
    {
        ".java", ".kt", ".kts", ".groovy", ".py", ".js", ".mjs", ".ts", ".tsx",
        ".jsx", ".go", ".rs", ".c", ".h", ".cpp", ".hpp", ".cs", ".rb", ".php",
        ".swift", ".scala", ".sql", ".sh", ".bash", ".ps1", ".bat", ".cmd",
        ".yml", ".yaml", ".json", ".xml", ".properties", ".md", ".txt",
        ".gradle", ".toml", ".ini", ".conf", ".html", ".css", ".proto", ".vue",
        ".lua",
    }
)

_PAGE_LIMIT_MIN = 1
_PAGE_LIMIT_MAX = 1000
_GLOB_MAX_LENGTH = 1024
_COMMIT_SHA1 = re.compile(r"[0-9A-Fa-f]{40}")
_PROJECT_KEY = re.compile(r"~?[A-Za-z0-9_][A-Za-z0-9_.-]*")
_REPOSITORY_SLUG = re.compile(r"[A-Za-z0-9_.-]+")
_UNSAFE_TEXT = re.compile(r"[\x00-\x1f\x7f-\x9f\ud800-\udfff]")
_PERCENT_ESCAPE = re.compile(r"%[0-9A-Fa-f]{2}")
_HEAD_PREFIX = "refs/heads/"
_TAG_PREFIX = "refs/tags/"
_DEFAULT_BRANCH_OPERATION = "bitbucket.repository.default-branch"

type RefKind = Literal["default", "commit", "branch", "tag"]
type Selection = Literal["text-suffixes", "explicit", "all-paths"]

# Compatibility aliases retained for the existing line-mode tests while the
# implementation lives in the reusable helper module.
_HelperTimeout = regex_helper.RegexTimeout
_HelperInvalidRegex = regex_helper.InvalidRegex
_HelperFailure = regex_helper.HelperFailure
_HELPER_SOURCE = regex_helper.HELPER_SOURCE
_split_lines = regex_helper.split_lines


class GrepHit(TypedDict):
    """One matching line: a 1-based number, capped text, and its truncation flag."""

    file: str
    line: int
    text: str
    text_truncated: bool


class GrepResult(TypedDict):
    """Truthful outcome of one repository grep or path listing."""

    engine: Literal["fanout", "listing"]
    repo: str
    commit: str
    at: str | None
    ref_kind: RefKind
    glob: str | None
    path: str | None
    selection: Selection
    ignore_case: bool
    files: list[str]
    files_eligible: int
    files_excluded: int
    files_scanned: int
    hits: list[GrepHit]
    truncated: bool
    complete: bool


def grep_repository(
    base_url: str,
    repo: str,
    pattern: str | None = None,
    *,
    token: str,
    at: str | None = None,
    glob: str | None = None,
    path: str | None = None,
    ignore_case: bool = True,
    limit: int = GREP_LIMIT_DEFAULT,
    timeout_s: float = GREP_TIMEOUT_DEFAULT,
    regex_timeout_s: float = REGEX_TIMEOUT_DEFAULT,
    max_pages: int = 100,
    allow_http_loopback: bool = False,
) -> GrepResult:
    """Search one repository snapshot or list filtered paths.

    ``repo`` is ``PROJECT/slug``. ``at`` accepts ``None`` for the unique default
    branch, a full 40-hex commit, an exact branch or tag name, or a qualified
    ``refs/heads/...`` or ``refs/tags/...`` ref. A 40-hex value is always a
    commit. An unqualified name is checked as a branch and as a tag; if it is
    both, or cannot be checked as a tag, the call fails instead of guessing.
    Every resolved ref is pinned to its full commit before any file is listed.

    With a pattern and neither ``glob`` nor ``path``, only paths whose basename
    has a ``TEXT_SUFFIXES`` suffix are eligible and the result reports
    ``selection="text-suffixes"``. Supplying either filter selects explicitly
    (``selection="explicit"``) and disables the suffix rule. ``glob`` and
    ``path`` are conjunctive: a glob without a slash also matches a basename,
    while a glob with a slash is matched against the whole path with
    case-sensitive ``fnmatch`` semantics (``*`` can cross ``/``).

    ``pattern=None`` switches to a path-listing mode that never reads file
    contents or starts a regex helper. The same pinned ref and complete
    paginated file list are used; when neither filter is supplied every path is
    selected (``selection="all-paths"``), otherwise only matching paths
    (``"explicit"``). ``files`` holds at most ``limit`` paths,
    ``files_eligible`` counts every selected path, ``files_scanned`` is zero,
    ``hits`` is empty, and ``truncated``/``complete`` describe whether the
    selected list exceeded ``limit``.

    ``pattern`` itself is a non-empty Python regular expression applied to each
    LF-delimited line without its terminator, so it cannot match across lines;
    an empty string is not a listing request. ``ignore_case`` defaults to true
    for BBK parity and is unused when listing. ``limit`` from 1 to 1000 caps
    matching lines in regex mode and listed paths in listing mode. Each hit's
    ``text`` is capped at ``HIT_TEXT_LIMIT`` (300) characters for bounded
    output and sets ``text_truncated`` when shortened; matching always uses the
    full line. ``timeout_s`` is the cooperative total budget and
    ``regex_timeout_s`` bounds one file's helper. ``files_eligible``,
    ``files_excluded``, ``files_scanned``, ``truncated`` and ``complete`` state
    the actual coverage. Every failure raises without a result.
    """
    normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    project, slug = _repo_segments(repo)
    selected_glob = _glob_filter(glob)
    selected_path = _path_filter(path)
    requested_at = _ref_text(at)
    selected_pattern = None if pattern is None else _pattern_text(pattern)
    _validate_limit(limit)
    _validate_pages(max_pages)
    if not isinstance(ignore_case, bool):
        raise AtlaWireError("The ignore-case option must be a boolean.")
    total_timeout = _timeout_value(timeout_s, "total")
    per_file_timeout = _timeout_value(regex_timeout_s, "regex")
    deadline = _monotonic() + total_timeout

    def before_request() -> None:
        _require_budget(deadline)

    if selected_pattern is not None:
        _validate_pattern(
            selected_pattern,
            ignore_case=ignore_case,
            timeout_s=min(per_file_timeout, _require_budget(deadline)),
        )
    commit, ref_kind = _resolve_ref(
        base_url,
        repo,
        project,
        slug,
        requested_at,
        token=token,
        max_pages=max_pages,
        allow_http_loopback=allow_http_loopback,
        before_request=before_request,
    )
    _require_budget(deadline)
    names = list_repository_files(
        base_url,
        repo,
        token=token,
        at=commit,
        max_pages=max_pages,
        before_page=before_request,
        allow_http_loopback=allow_http_loopback,
    )
    _require_budget(deadline)
    if selected_pattern is None:
        selected, listing_selection = _select_listing(
            names, selected_path, selected_glob
        )
        files = selected[:limit]
        truncated = len(selected) > limit
        _require_budget(deadline)
        return GrepResult(
            engine="listing",
            repo=repo,
            commit=commit,
            at=requested_at,
            ref_kind=ref_kind,
            glob=selected_glob,
            path=selected_path,
            selection=listing_selection,
            ignore_case=ignore_case,
            files=files,
            files_eligible=len(selected),
            files_excluded=len(names) - len(selected),
            files_scanned=0,
            hits=[],
            truncated=truncated,
            complete=not truncated,
        )
    eligible, selection = _select_paths(names, selected_path, selected_glob)
    hits, scanned, truncated = _scan(
        base_url,
        repo,
        eligible,
        token=token,
        commit=commit,
        pattern=selected_pattern,
        ignore_case=ignore_case,
        limit=limit,
        regex_timeout_s=per_file_timeout,
        deadline=deadline,
        allow_http_loopback=allow_http_loopback,
    )
    _require_budget(deadline)
    return GrepResult(
        engine="fanout",
        repo=repo,
        commit=commit,
        at=requested_at,
        ref_kind=ref_kind,
        glob=selected_glob,
        path=selected_path,
        selection=selection,
        ignore_case=ignore_case,
        files=[],
        files_eligible=len(eligible),
        files_excluded=len(names) - len(eligible),
        files_scanned=scanned,
        hits=hits,
        truncated=truncated,
        complete=not truncated,
    )


def _scan(
    base_url: str,
    repo: str,
    names: list[str],
    *,
    token: str,
    commit: str,
    pattern: str,
    ignore_case: bool,
    limit: int,
    regex_timeout_s: float,
    deadline: float,
    allow_http_loopback: bool,
) -> tuple[list[GrepHit], int, bool]:
    """Read and search every eligible file or raise without a result."""
    hits: list[GrepHit] = []
    scanned = 0
    for name in names:
        if len(hits) >= limit:
            return hits, scanned, True
        _require_budget(deadline)
        try:
            text = get_repository_file(
                base_url,
                repo,
                name,
                token=token,
                at=commit,
                allow_http_loopback=allow_http_loopback,
            )
        except AtlaWireError as exc:
            raise AtlaWireError(
                f"Repository grep aborted without a result: {exc}"
            ) from None
        scanned += 1
        remaining = limit - len(hits)
        lines = _split_lines(text)
        timeout_s = min(regex_timeout_s, _require_budget(deadline))
        try:
            numbers = _match_line_numbers(
                text,
                pattern,
                ignore_case=ignore_case,
                limit=remaining,
                timeout_s=timeout_s,
                line_count=len(lines),
            )
        except _HelperTimeout:
            _raise_timeout(timeout_s, regex_timeout_s)
        except _HelperInvalidRegex:
            raise AtlaWireError("The repository regex is invalid.") from None
        except _HelperFailure:
            raise AtlaWireError(
                "Repository regex evaluation failed; no result was produced."
            ) from None
        for number in numbers:
            line = lines[number - 1]
            hits.append(
                GrepHit(
                    file=name,
                    line=number,
                    text=line[:HIT_TEXT_LIMIT],
                    text_truncated=len(line) > HIT_TEXT_LIMIT,
                )
            )
        if len(numbers) == remaining:
            return hits, scanned, True
    return hits, scanned, False


def _resolve_ref(
    base_url: str,
    repo: str,
    project: str,
    slug: str,
    at: str | None,
    *,
    token: str,
    max_pages: int,
    allow_http_loopback: bool,
    before_request: Callable[[], None],
) -> tuple[str, RefKind]:
    """Resolve the requested ref once to one full commit and its kind."""
    if at is None:
        before_request()
        branch = read_operation(
            _DEFAULT_BRANCH_OPERATION,
            base_url,
            token=token,
            arguments={"projectKey": project, "repositorySlug": slug},
            allow_http_loopback=allow_http_loopback,
        )
        if branch is None:
            raise AtlaWireError("The repository has no default branch.")
        if not isinstance(branch, dict):
            raise AtlaWireError("Invalid repository default branch metadata.")
        return _default_branch_commit(branch), "default"
    if _COMMIT_SHA1.fullmatch(at):
        before_request()
        return _verified_commit(
            base_url, repo, at, token=token, allow_http_loopback=allow_http_loopback
        ), "commit"
    if at.startswith(_HEAD_PREFIX):
        name = at.removeprefix(_HEAD_PREFIX)
        before_request()
        commit = _find_branch(
            base_url,
            repo,
            name,
            token=token,
            max_pages=max_pages,
            allow_http_loopback=allow_http_loopback,
            before_page=before_request,
        )
        if commit is None:
            raise AtlaWireError("The repository branch was not found.")
        return commit, "branch"
    if at.startswith(_TAG_PREFIX):
        name = at.removeprefix(_TAG_PREFIX)
        if not _safe_tag_name(name):
            raise AtlaWireError("The repository tag name is not safe.")
        before_request()
        tag = _find_tag(
            base_url, repo, name, token=token, allow_http_loopback=allow_http_loopback
        )
        if tag is None:
            raise AtlaWireError("The repository tag was not found.")
        return _tag_commit(tag), "tag"
    if at.startswith("refs/"):
        raise AtlaWireError("Only refs/heads/ and refs/tags/ refs are supported.")
    if not _safe_tag_name(at):
        raise AtlaWireError(
            "The repository ref cannot be checked as a tag; "
            "use refs/heads/... for a branch."
        )
    return _resolve_unqualified(
        base_url,
        repo,
        at,
        token=token,
        max_pages=max_pages,
        allow_http_loopback=allow_http_loopback,
        before_request=before_request,
    )


def _resolve_unqualified(
    base_url: str,
    repo: str,
    name: str,
    *,
    token: str,
    max_pages: int,
    allow_http_loopback: bool,
    before_request: Callable[[], None],
) -> tuple[str, RefKind]:
    """Resolve an exact name as a branch or tag, rejecting ambiguity."""
    before_request()
    branch = get_branch(
        base_url,
        repo,
        name,
        token=token,
        max_pages=max_pages,
        allow_http_loopback=allow_http_loopback,
        before_page=before_request,
    )
    branch_commit = None if branch is None else _branch_commit(branch)
    before_request()
    tag = _find_tag(
        base_url, repo, name, token=token, allow_http_loopback=allow_http_loopback
    )
    tag_commit = None if tag is None else _tag_commit(tag)
    if branch_commit is not None and tag_commit is not None:
        raise AtlaWireError(
            "The repository ref is both a branch and a tag; "
            "use refs/heads/... or refs/tags/..."
        )
    if branch_commit is not None:
        return branch_commit, "branch"
    if tag_commit is not None:
        return tag_commit, "tag"
    raise AtlaWireError("The repository ref is not a full commit, branch, or tag.")


def _verified_commit(
    base_url: str,
    repo: str,
    at: str,
    *,
    token: str,
    allow_http_loopback: bool,
) -> str:
    """Verify a full commit with the commit adapter before using it."""
    value = get_commit(
        base_url, repo, at, token=token, allow_http_loopback=allow_http_loopback
    )
    identifier = value.get("id")
    if (
        not isinstance(identifier, str)
        or not _COMMIT_SHA1.fullmatch(identifier)
        or identifier.lower() != at.lower()
    ):
        raise AtlaWireError("The repository commit metadata is invalid.")
    return identifier


def _find_branch(
    base_url: str,
    repo: str,
    name: str,
    *,
    token: str,
    max_pages: int,
    allow_http_loopback: bool,
    before_page: Callable[[], None],
) -> str | None:
    """Return an exact branch's full commit or ``None`` after a complete walk."""
    branch = get_branch(
        base_url,
        repo,
        name,
        token=token,
        max_pages=max_pages,
        allow_http_loopback=allow_http_loopback,
        before_page=before_page,
    )
    return None if branch is None else _branch_commit(branch)


def _find_tag(
    base_url: str,
    repo: str,
    name: str,
    *,
    token: str,
    allow_http_loopback: bool,
) -> dict[str, object] | None:
    """Return an exact, identity-checked tag object, or ``None`` on HTTP 404."""
    try:
        value = get_tag(
            base_url, repo, name, token=token, allow_http_loopback=allow_http_loopback
        )
    except AtlaWireError as exc:
        # The shared transport's only not-found diagnostic is this exact status.
        # Every other failure is propagated so a failed check is never absence.
        if str(exc).startswith("HTTP 404:"):
            return None
        raise
    _validate_tag_identity(value, name)
    return value


def _validate_tag_identity(tag: Mapping[str, object], name: str) -> None:
    """Require a documented identity to name the requested short tag.

    A field matches when it is exactly the requested short name or exactly one
    ``refs/tags/`` prefix plus that name. This also handles a literal short name
    that itself begins ``refs/tags/`` without stripping it away. A present
    empty, non-string, wrong-namespace or contradictory value is rejected, as
    is a response with no usable identity.
    """
    invalid = "The repository tag identity does not match the requested ref."
    full = f"{_TAG_PREFIX}{name}"
    identities = 0
    for field in ("id", "displayId"):
        if field not in tag:
            continue
        value = tag[field]
        if value is None:
            continue
        if not isinstance(value, str):
            raise AtlaWireError(invalid)
        if value != name and value != full:
            raise AtlaWireError(invalid)
        identities += 1
    if not identities:
        raise AtlaWireError(invalid)


def _branch_commit(branch: Mapping[str, object]) -> str:
    """Require a branch's latest commit to be a full commit ID."""
    commit = branch.get("commit")
    if not isinstance(commit, str) or not _COMMIT_SHA1.fullmatch(commit):
        raise AtlaWireError("The repository branch does not carry a full commit ID.")
    return commit


def _default_branch_commit(branch: Mapping[str, object]) -> str:
    """Require the default-branch response to carry a full latest commit."""
    commit = branch.get("latestCommit")
    if not isinstance(commit, str) or not _COMMIT_SHA1.fullmatch(commit):
        raise AtlaWireError(
            "The repository default branch does not carry a full commit ID."
        )
    return commit


def _tag_commit(tag: Mapping[str, object]) -> str:
    """Require a tag's ``latestCommit`` to be a full commit ID."""
    commit = tag.get("latestCommit")
    if not isinstance(commit, str) or not _COMMIT_SHA1.fullmatch(commit):
        raise AtlaWireError("The repository tag does not carry a full commit ID.")
    return commit


def _safe_tag_name(name: str) -> bool:
    """Mirror the tag adapter's addressable path rules before a lookup."""
    if (
        not name
        or _UNSAFE_TEXT.search(name)
        or "\\" in name
        or _PERCENT_ESCAPE.search(name)
    ):
        return False
    return all(segment and segment not in {".", ".."} for segment in name.split("/"))


def _match_line_numbers(
    text: str,
    pattern: str,
    *,
    ignore_case: bool,
    limit: int,
    timeout_s: float,
    line_count: int,
) -> list[int]:
    """Return matching 1-based line numbers from one isolated helper run."""
    return regex_helper.match_lines(
        text,
        pattern,
        ignore_case=ignore_case,
        limit=limit,
        timeout_s=timeout_s,
        line_count=line_count,
    )


def _select_listing(
    names: list[str], path: str | None, glob: str | None
) -> tuple[list[str], Selection]:
    """Select listed paths; no filters include every path, not text suffixes."""
    if path is None and glob is None:
        return list(names), "all-paths"
    return [name for name in names if _eligible(name, path, glob)], "explicit"


def _select_paths(
    names: list[str], path: str | None, glob: str | None
) -> tuple[list[str], Selection]:
    """Apply the BBK default text scope or the explicit path/glob filters."""
    if path is None and glob is None:
        return [name for name in names if _default_text_file(name)], "text-suffixes"
    return [name for name in names if _eligible(name, path, glob)], "explicit"


def _default_text_file(name: str) -> bool:
    """Return whether a path's basename has a BBK default text suffix."""
    base = name.rsplit("/", 1)[-1]
    if "." not in base:
        return False
    suffix = f".{base.rsplit('.', 1)[1].lower()}"
    return suffix in TEXT_SUFFIXES


def _eligible(name: str, path: str | None, glob: str | None) -> bool:
    """Apply the conjunctive path-prefix and glob filters to one server path."""
    if path is not None and not (name == path or name.startswith(f"{path}/")):
        return False
    if glob is None:
        return True
    if fnmatch.fnmatchcase(name, glob):
        return True
    return "/" not in glob and fnmatch.fnmatchcase(name.rsplit("/", 1)[-1], glob)


def _validate_pattern(pattern: str, *, ignore_case: bool, timeout_s: float) -> None:
    """Reject an invalid regex through the reusable killable helper."""
    try:
        regex_helper.validate_regex(
            pattern, ignore_case=ignore_case, timeout_s=timeout_s
        )
    except _HelperInvalidRegex:
        raise AtlaWireError("The repository regex is invalid.") from None
    except _HelperTimeout:
        raise AtlaWireError(
            "Repository regex validation timed out; no result was produced."
        ) from None
    except _HelperFailure:
        raise AtlaWireError(
            "Repository regex validation failed; no result was produced."
        ) from None


def _raise_timeout(timeout_s: float, regex_timeout_s: float) -> Never:
    """Raise the timeout message that matches the binding limit."""
    if timeout_s < regex_timeout_s:
        raise AtlaWireError(
            "Repository grep time budget exhausted; no result was produced."
        )
    raise AtlaWireError(
        "Repository regex evaluation timed out; no result was produced."
    )


def _require_budget(deadline: float) -> float:
    """Return remaining budget seconds or fail before starting more work."""
    remaining = deadline - _monotonic()
    if remaining <= 0:
        raise AtlaWireError(
            "Repository grep time budget exhausted; no result was produced."
        )
    return remaining


def _repo_segments(repo: str) -> tuple[str, str]:
    """Validate ``PROJECT/slug`` and return both safe segments."""
    if not isinstance(repo, str):
        raise AtlaWireError("Expected a repository as PROJECT/slug.")
    project, separator, slug = repo.partition("/")
    if (
        not separator
        or "/" in slug
        or not _PROJECT_KEY.fullmatch(project)
        or not _REPOSITORY_SLUG.fullmatch(slug)
        or slug in {".", ".."}
    ):
        raise AtlaWireError("Expected a repository as PROJECT/slug.")
    return project, slug


def _pattern_text(value: str) -> str:
    """Require a non-empty, UTF-8-encodable regular expression."""
    if not isinstance(value, str) or not value:
        raise AtlaWireError("The repository regex must be non-empty text.")
    return _require_utf8(value, "repository regex")


def _ref_text(value: str | None) -> str | None:
    """Return the requested ref or reject control characters before any call."""
    if value is None or value == "":
        return None
    if not isinstance(value, str) or _UNSAFE_TEXT.search(value):
        raise AtlaWireError(
            "The repository ref must be non-empty text without control characters."
        )
    return _require_utf8(value, "repository ref")


def _glob_filter(value: str | None) -> str | None:
    """Return the glob filter or reject text that cannot describe a path."""
    if value is None or value == "":
        return None
    if (
        not isinstance(value, str)
        or _UNSAFE_TEXT.search(value)
        or "\\" in value
        or len(value) > _GLOB_MAX_LENGTH
    ):
        raise AtlaWireError("The repository glob must be safe relative text.")
    return value


def _path_filter(value: str | None) -> str | None:
    """Return a normalized relative directory prefix or reject it."""
    if value is None or value == "":
        return None
    if (
        not isinstance(value, str)
        or _UNSAFE_TEXT.search(value)
        or value.startswith("/")
        or "\\" in value
    ):
        raise AtlaWireError("The repository path filter must be a relative safe path.")
    normalized = value.rstrip("/")
    segments = normalized.split("/")
    if any(not segment or segment in {".", ".."} for segment in segments):
        raise AtlaWireError("The repository path filter must be a relative safe path.")
    return normalized


def _require_utf8(value: str, label: str) -> str:
    """Reject text that UTF-8 cannot encode."""
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise AtlaWireError(f"The {label} must be valid UTF-8 text.") from None
    return value


def _validate_limit(limit: int) -> None:
    """Require an exact integer hit limit in the supported range."""
    if (
        not isinstance(limit, int)
        or isinstance(limit, bool)
        or not GREP_LIMIT_MIN <= limit <= GREP_LIMIT_MAX
    ):
        raise AtlaWireError(
            f"The repository grep limit must be between {GREP_LIMIT_MIN} "
            f"and {GREP_LIMIT_MAX}."
        )


def _validate_pages(max_pages: int) -> None:
    """Require an exact integer page budget in the supported range."""
    if (
        not isinstance(max_pages, int)
        or isinstance(max_pages, bool)
        or not _PAGE_LIMIT_MIN <= max_pages <= _PAGE_LIMIT_MAX
    ):
        raise AtlaWireError("The page limit must be between 1 and 1000.")


def _timeout_value(value: float, label: str) -> float:
    """Require a finite positive timeout without accepting booleans."""
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
        or value <= 0
    ):
        raise AtlaWireError(
            f"The {label} timeout must be a finite positive number."
        )
    return float(value)
