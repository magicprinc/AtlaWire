"""Read operations for self-hosted Bitbucket."""

import re
from collections.abc import Callable
from typing import TypedDict
from urllib.parse import quote

import requests

from atlawire.http import (
    AtlaWireError,
    bearer_session,
    get_json_object,
    get_text,
    normalize_base_url,
)

_PROJECT_KEY = re.compile(r"~?[A-Za-z0-9_][A-Za-z0-9_.-]*")
_REPOSITORY_SLUG = re.compile(r"[A-Za-z0-9_.-]+")
_FILE_UNSAFE = re.compile(r"[\\\x00-\x1f\x7f-\x9f\ud800-\udfff]")
_FILE_PERCENT_ESCAPE = re.compile(r"%[0-9A-Fa-f]{2}")
_REVISION_UNSAFE = re.compile(r"[\x00-\x1f\x7f-\x9f\ud800-\udfff]")
_COMMIT_SHA1 = re.compile(r"[0-9A-Fa-f]{40}")
_PULL_REQUEST_ID_MAX = 2**63 - 1
_CHANGES_LIMIT = 1000
_DIFF_CONTEXT_MAX = 100
_DIFF_REVIEW_HEADER = (
    "# Bitbucket PR diff review (context={context}; whitespace=ignore-all; not a patch)"
)
_DIFF_NO_HUNKS = "(no textual hunks in the response)"
_DIFF_NO_FILE_HUNKS = "(no textual hunks in this file)"
_DIFF_RANGE_KEYS = ("sourceLine", "sourceSpan", "destinationLine", "destinationSpan")
_DIFF_SEGMENT_PREFIXES = {"CONTEXT": " ", "ADDED": "+", "REMOVED": "-"}
# JSON can decode \uD800-style escapes into lone surrogates, which UTF-8 output
# cannot encode; escaping them keeps the review view printable and single-line.
_DIFF_TEXT_UNSAFE = re.compile(
    r"[\\\x00-\x1f\x7f-\x9f\u061c\u200e\u200f\u2028-\u202e\u2066-\u2069"
    r"\ud800-\udfff]"
)
_DIFF_LINE_BREAKS = ("\r", "\n", "\u2028", "\u2029")


class Repository(TypedDict):
    slug: str
    name: str | None
    state: str | None
    public: bool | None


class Project(TypedDict):
    key: str
    name: str | None
    public: bool | None
    description: str | None
    url: str | None


class PullRequestFile(TypedDict):
    path: str
    type: str | None
    node: str | None


class PullRequestComment(TypedDict):
    id: int
    author: str | None
    path: str | None
    line: int | None
    text: str
    created: int | None


def list_projects(
    base_url: str,
    *,
    token: str,
    max_pages: int = 100,
    allow_http_loopback: bool = False,
) -> list[Project]:
    """List visible projects in server order or raise without a partial list."""
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    if (
        not isinstance(max_pages, int)
        or isinstance(max_pages, bool)
        or not 1 <= max_pages <= 1000
    ):
        raise AtlaWireError("The page limit must be between 1 and 1000.")
    url = f"{base}/rest/api/1.0/projects"
    with bearer_session(token) as session:
        return _read_pages(session, url, max_pages, project=_project)


def list_repositories(
    base_url: str,
    project: str,
    *,
    token: str,
    max_pages: int = 100,
    allow_http_loopback: bool = False,
) -> list[Repository]:
    """List repositories in server order or raise without returning a partial list."""
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    if not _PROJECT_KEY.fullmatch(project):
        raise AtlaWireError("Expected a Bitbucket project key or ~user project.")
    if not 1 <= max_pages <= 1000:
        raise AtlaWireError("The page limit must be between 1 and 1000.")
    url = f"{base}/rest/api/1.0/projects/{project}/repos"
    with bearer_session(token) as session:
        return _read_pages(session, url, max_pages, project=_repository)


def get_pull_request(
    base_url: str,
    repo: str,
    pr_id: str | int,
    *,
    token: str,
    allow_http_loopback: bool = False,
) -> dict[str, object]:
    """Return one pull request exactly as the server sent it.

    ``repo`` is ``PROJECT/slug``. ``pr_id`` accepts a canonical positive decimal
    string or ``int``; the request carries its canonical decimal form. The result
    is the decoded server object, so unknown and nested fields are preserved, and
    links in it are never followed.
    """
    _, url, identifier = _pull_request_target(
        base_url, repo, pr_id, allow_http_loopback=allow_http_loopback
    )
    with bearer_session(token) as session:
        value = get_json_object(session, url, params={})
    _validate_pull_request(value, identifier)
    return value


def get_repository_file(
    base_url: str,
    repo: str,
    path: str,
    *,
    token: str,
    at: str = "master",
    allow_http_loopback: bool = False,
) -> str:
    """Return one repository file at a revision as exact UTF-8 text.

    ``repo`` is ``PROJECT/slug`` and ``path`` is a relative Git path with safe
    segments. The revision defaults to ``master`` and is sent only as the
    ``at`` query parameter. The call makes one streamed raw request with
    ``Accept: text/plain``; content is limited and validated by
    [get_text][atlawire.http.get_text], so an oversize, non-text, or non-UTF-8
    response raises without returning partial text.
    """
    revision = _revision(at)
    segments = _file_segments(path)
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    project, slug = _split_repo(repo)
    with bearer_session(token) as session:
        return get_text(
            session,
            _raw_file_url(base, project, slug, segments),
            params={"at": revision},
        )


def get_pull_request_file(
    base_url: str,
    repo: str,
    pr_id: str | int,
    path: str,
    *,
    token: str,
    side: str = "new",
    allow_http_loopback: bool = False,
) -> str:
    """Return one pull request file from its ``new`` or ``old`` side.

    ``new`` selects ``fromRef`` and ``old`` selects ``toRef``; the raw request
    targets the selected ref repository (which may be a fork) on the same
    configured instance, using only its project key, slug, and full 40-hex
    ``latestCommit``. Display IDs, caller repository data, opposite refs, and
    response links are never used. Side and path are validated before any
    request; malformed selected metadata fails after the pull request request
    but before the raw request.
    """
    selected_side = _file_side(side)
    segments = _file_segments(path)
    base, url, identifier = _pull_request_target(
        base_url, repo, pr_id, allow_http_loopback=allow_http_loopback
    )
    with bearer_session(token) as session:
        value = get_json_object(session, url, params={})
        _validate_pull_request(value, identifier)
        project, slug, commit = _selected_file_ref(value, selected_side)
        return get_text(
            session,
            _raw_file_url(base, project, slug, segments),
            params={"at": commit},
        )


def list_pull_request_files(
    base_url: str,
    repo: str,
    pr_id: str | int,
    *,
    token: str,
    allow_http_loopback: bool = False,
) -> list[PullRequestFile]:
    """List the changed files of one pull request from a single terminal page.

    ``repo`` is ``PROJECT/slug`` and ``pr_id`` follows the same canonical
    positive decimal rules as [get_pull_request][atlawire.bitbucket.get_pull_request].
    Rows are projected in server order with ``path``, ``type`` and ``node``
    fields; the path is read from the representation the server supplied and is
    never opened or requested.

    Bitbucket Server 5.10 documents ``/changes`` as not pageable: it returns one
    page, ignores ``start``, and silently truncates to the request limit or its
    own hard limit, whichever is smaller. The response envelope cannot tell a
    complete page from one capped exactly at the reported limit, so a page whose
    row count equals the reported limit is rejected as possibly incomplete rather
    than followed with another request or reported as a complete result. Only a
    terminal page carrying fewer rows than its reported limit is accepted.
    """
    _, url, _ = _pull_request_target(
        base_url, repo, pr_id, allow_http_loopback=allow_http_loopback
    )
    with bearer_session(token) as session:
        page = get_json_object(
            session, f"{url}/changes", params={"limit": _CHANGES_LIMIT}
        )
    return _pull_request_files(page)


def get_pull_request_diff(
    base_url: str,
    repo: str,
    pr_id: str | int,
    *,
    token: str,
    context: int = 3,
    allow_http_loopback: bool = False,
) -> dict[str, object]:
    """Return the server's decoded diff object for one pull request.

    ``repo`` is ``PROJECT/slug`` and ``pr_id`` follows the same canonical
    positive decimal rules as [get_pull_request][atlawire.bitbucket.get_pull_request].
    The whole-diff endpoint is requested once with ``contextLines=context``,
    ``whitespace=ignore-all`` and ``withComments=false``; ``context`` must be an
    ``int`` from 0 to 100 and is validated before any session is created.

    The decoded object is returned unchanged, so declared and unknown fields are
    preserved. Bitbucket Server 5.10 documents this endpoint as unpaged and
    capped server-side, so a declared ``truncated`` flag never triggers a
    fallback request: the call fails instead. Validation checks the
    ``truncated`` flags declared at the documented envelope, file, hunk,
    segment and line nodes, accepting a missing flag and the exact
    ``false``/``"false"`` values while failing on a declared true value and
    rejecting any other present value. Nested collections that carry those
    nodes must be lists of objects when present, but omitted ``hunks``,
    ``segments`` and ``lines`` are accepted.

    This validates declared flags only; it cannot prove that an unflagged
    stream was complete, and unknown metadata is not scanned for truncation.
    Sources and links carried by the object are never fetched.
    """
    if (
        not isinstance(context, int)
        or isinstance(context, bool)
        or not 0 <= context <= _DIFF_CONTEXT_MAX
    ):
        raise AtlaWireError("The diff context must be an integer from 0 to 100.")
    _, url, _ = _pull_request_target(
        base_url, repo, pr_id, allow_http_loopback=allow_http_loopback
    )
    with bearer_session(token) as session:
        value = get_json_object(
            session,
            f"{url}/diff",
            params={
                "contextLines": context,
                "whitespace": "ignore-all",
                "withComments": "false",
            },
        )
    _validate_pull_request_diff(value)
    return value


def get_pull_request_diff_text(
    base_url: str,
    repo: str,
    pr_id: str | int,
    *,
    token: str,
    context: int = 3,
    allow_http_loopback: bool = False,
) -> str:
    """Return a terminal-safe review view of one pull request diff.

    The call makes exactly one whole-diff request through
    [get_pull_request_diff][atlawire.bitbucket.get_pull_request_diff], so it
    inherits its context bounds, fixed ``whitespace=ignore-all`` request and
    declared-truncation checks. The header describes that request, not metadata
    echoed by the response.

    The result is a readable unified-diff-like view, never an applyable Git
    patch: it omits index, binary and rename markers, preserves ordinary
    Unicode and spaces, and escapes controls, bidi formatting characters,
    surrogate code points and backslashes. Missing or empty hunk collections
    produce an explicit no-textual-hunks marker rather than a claim that
    nothing changed. The text is built completely before it is returned, so a
    later malformed node raises without producing partial output.
    """
    value = get_pull_request_diff(
        base_url,
        repo,
        pr_id,
        token=token,
        context=context,
        allow_http_loopback=allow_http_loopback,
    )
    return _render_pull_request_diff_text(value, context=context)


def list_pull_request_comments(
    base_url: str,
    repo: str,
    pr_id: str | int,
    *,
    token: str,
    max_pages: int = 100,
    allow_http_loopback: bool = False,
) -> list[PullRequestComment]:
    """List comment activities of one pull request in server order.

    ``repo`` is ``PROJECT/slug`` and ``pr_id`` follows the same canonical
    positive decimal rules as [get_pull_request][atlawire.bitbucket.get_pull_request].
    Every page is read from the fixed ``/activities`` endpoint; an activity
    without a top-level comment is skipped without consuming a row, while an
    activity carrying a malformed comment or anchor fails the whole call.

    This is a comment-activity view, not a canonical thread export: nested
    replies are neither flattened nor deduplicated, edits are not merged, and
    anchor metadata is only projected, never followed or acted upon.
    """
    _, url, _ = _pull_request_target(
        base_url, repo, pr_id, allow_http_loopback=allow_http_loopback
    )
    if (
        not isinstance(max_pages, int)
        or isinstance(max_pages, bool)
        or not 1 <= max_pages <= 1000
    ):
        raise AtlaWireError("The page limit must be between 1 and 1000.")
    with bearer_session(token) as session:
        return _read_pages(
            session, f"{url}/activities", max_pages, project=_pull_request_comment
        )


def _pull_request_target(
    base_url: str,
    repo: str,
    pr_id: str | int,
    *,
    allow_http_loopback: bool,
) -> tuple[str, str, int]:
    """Build the canonical pull request URL and its validated identity."""
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    project, slug = _split_repo(repo)
    identifier = _pull_request_id(pr_id)
    url = (
        f"{base}/rest/api/1.0/projects/{quote(project, safe='')}"
        f"/repos/{quote(slug, safe='')}/pull-requests/{identifier}"
    )
    return base, url, identifier


def _split_repo(repo: str) -> tuple[str, str]:
    """Split ``PROJECT/slug`` into two safe path segments."""
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


def _file_side(value: str) -> str:
    """Return the selected PR file side or reject before any request."""
    if not isinstance(value, str) or value not in {"new", "old"}:
        raise AtlaWireError('The file side must be "new" or "old".')
    return value


def _file_segments(path: str) -> tuple[str, ...]:
    """Validate a relative Git path and return its literal, unencoded segments.

    Percent followed by two hex digits is rejected rather than encoded so a
    proxy cannot reinterpret a literal name as an escape. A normal literal
    percent is allowed and is encoded exactly once by ``_raw_file_url``.
    """
    invalid = "Expected a relative file path with safe segments."
    if (
        not isinstance(path, str)
        or not path
        or _FILE_UNSAFE.search(path)
        or _FILE_PERCENT_ESCAPE.search(path)
    ):
        raise AtlaWireError(invalid)
    segments = path.split("/")
    if any(not segment or segment in {".", ".."} for segment in segments):
        raise AtlaWireError(invalid)
    return tuple(segments)


def _revision(value: str) -> str:
    """Validate a non-empty, control-free revision sent only as ``at``."""
    if not isinstance(value, str) or not value or _REVISION_UNSAFE.search(value):
        raise AtlaWireError("Expected a non-empty revision without control characters.")
    return value


def _raw_file_url(base: str, project: str, slug: str, segments: tuple[str, ...]) -> str:
    """Build a repository raw URL with each safe segment encoded once."""
    encoded = "/".join(quote(segment, safe="") for segment in segments)
    return (
        f"{base}/rest/api/1.0/projects/{quote(project, safe='')}"
        f"/repos/{quote(slug, safe='')}/raw/{encoded}"
    )


def _selected_file_ref(value: dict[str, object], side: str) -> tuple[str, str, str]:
    """Return the selected ref's validated project, slug, and full commit."""
    invalid = "Invalid pull request file metadata."
    ref = value.get("fromRef" if side == "new" else "toRef")
    if not isinstance(ref, dict):
        raise AtlaWireError(invalid)
    commit = ref.get("latestCommit")
    repository = ref.get("repository")
    if not isinstance(commit, str) or not _COMMIT_SHA1.fullmatch(commit):
        raise AtlaWireError(invalid)
    if not isinstance(repository, dict):
        raise AtlaWireError(invalid)
    project = repository.get("project")
    key = project.get("key") if isinstance(project, dict) else None
    slug = repository.get("slug")
    if (
        not isinstance(key, str)
        or not _PROJECT_KEY.fullmatch(key)
        or not isinstance(slug, str)
        or not _REPOSITORY_SLUG.fullmatch(slug)
        or slug in {".", ".."}
    ):
        raise AtlaWireError(invalid)
    return key, slug, commit


def _pull_request_id(value: str | int) -> int:
    """Return a canonical positive signed 64-bit ID or reject before I/O."""
    invalid = "Expected a pull request ID as a positive signed 64-bit integer."
    if isinstance(value, bool):
        raise AtlaWireError(invalid)
    if isinstance(value, int):
        identifier = value
    elif isinstance(value, str):
        # Length is checked before conversion so huge digit strings cannot stall
        # or hit the interpreter's integer-string conversion limit.
        if len(value) > 19 or not re.fullmatch(r"[1-9][0-9]*", value):
            raise AtlaWireError(invalid)
        identifier = int(value)
    else:
        raise AtlaWireError(invalid)
    if not 1 <= identifier <= _PULL_REQUEST_ID_MAX:
        raise AtlaWireError(invalid)
    return identifier


def _validate_pull_request(value: dict[str, object], pr_id: int) -> None:
    """Require the identity requested and the fields this slice promises."""
    identifier = value.get("id")
    title = value.get("title")
    state = value.get("state")
    if (
        not isinstance(identifier, int)
        or isinstance(identifier, bool)
        or identifier != pr_id
        or not isinstance(title, str)
        or not isinstance(state, str)
    ):
        raise AtlaWireError("Invalid pull request identity or fields.")


def _pull_request_files(page: dict[str, object]) -> list[PullRequestFile]:
    """Validate the single 5.10 changes envelope and project its rows."""
    values = page.get("values")
    if not isinstance(values, list):
        raise AtlaWireError("Expected a Bitbucket values array.")
    if page.get("isLastPage") is not True:
        raise AtlaWireError("Expected a terminal Bitbucket changes page.")
    limit = page.get("limit")
    if (
        not isinstance(limit, int)
        or isinstance(limit, bool)
        or not 1 <= limit <= _CHANGES_LIMIT
    ):
        raise AtlaWireError("Expected a Bitbucket changes limit between 1 and 1000.")
    if "size" in page:
        size = page["size"]
        if not isinstance(size, int) or isinstance(size, bool) or size != len(values):
            raise AtlaWireError("Invalid Bitbucket changes size.")
    if "start" in page:
        start = page["start"]
        if not isinstance(start, int) or isinstance(start, bool) or start != 0:
            raise AtlaWireError("Invalid Bitbucket changes start.")
    if "truncated" in page:
        truncated = page["truncated"]
        if not isinstance(truncated, bool):
            raise AtlaWireError("Invalid Bitbucket changes truncation flag.")
        if truncated:
            raise AtlaWireError("Bitbucket reported truncated pull request changes.")
    if len(values) >= limit:
        raise AtlaWireError(
            "The pull request changes reached the reported limit; "
            "the result may be truncated."
        )
    return [_pull_request_file(value) for value in values]


def _pull_request_file(value: object) -> PullRequestFile:
    if not isinstance(value, dict):
        raise AtlaWireError("Expected a Bitbucket change object.")
    path = _change_path(value.get("path"))
    change_type = value.get("type")
    node = value.get("nodeType")
    if (change_type is not None and not isinstance(change_type, str)) or (
        node is not None and not isinstance(node, str)
    ):
        raise AtlaWireError("Invalid fields in a Bitbucket change.")
    return PullRequestFile(path=path, type=change_type, node=node)


def _change_path(value: object) -> str:
    """Return the best full path representation the server supplied.

    Server 5.10 may send the path as a plain string or as an object with
    ``toString``, ``components`` and ``name``. A full representation wins over
    components, which win over the basename; missing optional metadata in an
    unused representation is irrelevant.
    """
    invalid = "Invalid path in a Bitbucket change."
    if isinstance(value, str):
        if not value:
            raise AtlaWireError(invalid)
        return value
    if not isinstance(value, dict):
        raise AtlaWireError(invalid)
    full = value.get("toString")
    if full is not None:
        if not isinstance(full, str):
            raise AtlaWireError(invalid)
        if full:
            return full
    components = value.get("components")
    if components is not None:
        if (
            not isinstance(components, list)
            or not components
            or any(not isinstance(part, str) or not part for part in components)
        ):
            raise AtlaWireError(invalid)
        return "/".join(components)
    name = value.get("name")
    if not isinstance(name, str) or not name:
        raise AtlaWireError(invalid)
    return name


def _validate_pull_request_diff(value: dict[str, object]) -> None:
    """Reject declared truncation and malformed truncation-bearing collections.

    Only the documented envelope, file, hunk, segment and line nodes are
    inspected; unknown metadata is left untouched and is not searched for
    flags.
    """
    _check_diff_truncation(value)
    diffs = value.get("diffs")
    if not isinstance(diffs, list):
        raise AtlaWireError("Expected a Bitbucket diffs array.")
    for diff in diffs:
        if not isinstance(diff, dict):
            raise AtlaWireError("Expected a Bitbucket diff object.")
        _check_diff_truncation(diff)
        if "hunks" not in diff:
            continue
        hunks = diff["hunks"]
        if not isinstance(hunks, list):
            raise AtlaWireError("Invalid hunks in a Bitbucket diff.")
        for hunk in hunks:
            _check_diff_hunk(hunk)


def _check_diff_hunk(hunk: object) -> None:
    """Validate one file hunk and its segments, if declared."""
    if not isinstance(hunk, dict):
        raise AtlaWireError("Expected a Bitbucket diff hunk object.")
    _check_diff_truncation(hunk)
    if "segments" not in hunk:
        return
    segments = hunk["segments"]
    if not isinstance(segments, list):
        raise AtlaWireError("Invalid segments in a Bitbucket diff hunk.")
    for segment in segments:
        _check_diff_segment(segment)


def _check_diff_segment(segment: object) -> None:
    """Validate one hunk segment and its lines, if declared."""
    if not isinstance(segment, dict):
        raise AtlaWireError("Expected a Bitbucket diff segment object.")
    _check_diff_truncation(segment)
    if "lines" not in segment:
        return
    lines = segment["lines"]
    if not isinstance(lines, list):
        raise AtlaWireError("Invalid lines in a Bitbucket diff segment.")
    for line in lines:
        if not isinstance(line, dict):
            raise AtlaWireError("Expected a Bitbucket diff line object.")
        _check_diff_truncation(line)


def _check_diff_truncation(value: dict[str, object]) -> None:
    """Accept an omitted or exact false flag; reject true and any other value.

    Server 5.10 emits both bare booleans and the lowercase strings ``"true"``
    and ``"false"`` across the envelope levels, so those exact strings are
    accepted alongside the booleans. Truthiness is deliberately not used:
    ``"false"`` must never be mistaken for a truncation report.
    """
    if "truncated" not in value:
        return
    flag = value["truncated"]
    if flag is True or flag == "true":
        raise AtlaWireError("Bitbucket reported a truncated pull request diff.")
    if flag is False or flag == "false":
        return
    raise AtlaWireError("Invalid Bitbucket diff truncation flag.")


def _render_pull_request_diff_text(value: dict[str, object], *, context: int) -> str:
    """Build the full review view without I/O or partial output.

    The view is deliberately not an applyable Git patch. Declared numeric ranges
    are printed exactly as integers, including zero, and are never derived from
    per-line positions. Hunk and segment counts are never assumed to agree.
    """
    diffs = value.get("diffs")
    if not isinstance(diffs, list):
        raise AtlaWireError("Expected a Bitbucket diffs array.")
    lines = [_DIFF_REVIEW_HEADER.format(context=context), ""]
    if not diffs:
        lines.append(_DIFF_NO_HUNKS)
        return "\n".join(lines) + "\n"
    for diff in diffs:
        lines.extend(_diff_text_file(diff))
    return "\n".join(lines) + "\n"


def _diff_text_file(value: object) -> list[str]:
    """Render one file header and its hunks in declared order."""
    if not isinstance(value, dict):
        raise AtlaWireError("Expected a Bitbucket diff object.")
    source = _diff_side_path(value, "source")
    destination = _diff_side_path(value, "destination")
    if source is None and destination is None:
        raise AtlaWireError("A Bitbucket diff must declare a path.")
    lines = ["--- " + _diff_side(source, "a"), "+++ " + _diff_side(destination, "b")]
    hunks = value.get("hunks")
    if "hunks" not in value or hunks == []:
        lines.append(_DIFF_NO_FILE_HUNKS)
        return lines
    if not isinstance(hunks, list):
        raise AtlaWireError("Invalid hunks in a Bitbucket diff.")
    for hunk in hunks:
        lines.extend(_diff_hunk_text(hunk))
    return lines


def _diff_side_path(diff: dict[str, object], key: str) -> str | None:
    """Return one declared path, treating an absent or null side as missing."""
    value = diff.get(key)
    return None if value is None else _change_path(value)


def _diff_side(path: str | None, prefix: str) -> str:
    """Prefix a present path; a missing side is the unprefixed null device."""
    if path is None:
        return "/dev/null"
    return f"{prefix}/" + _diff_text(path, reject_breaks=False)


def _diff_hunk_text(value: object) -> list[str]:
    """Render one hunk header and its segments in declared order."""
    if not isinstance(value, dict):
        raise AtlaWireError("Expected a Bitbucket diff hunk object.")
    numbers = [_diff_range_number(value, key) for key in _DIFF_RANGE_KEYS]
    lines = [f"@@ -{numbers[0]},{numbers[1]} +{numbers[2]},{numbers[3]} @@"]
    lines.extend(_diff_segment_lines(value))
    return lines


def _diff_range_number(hunk: dict[str, object], key: str) -> int:
    """Return an exact declared nonnegative integer, preserving zero."""
    value = hunk.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise AtlaWireError("Invalid line range in a Bitbucket diff hunk.")
    return value


def _diff_segment_lines(hunk: dict[str, object]) -> list[str]:
    """Render nonempty segments, rejecting unsupported types."""
    segments = hunk.get("segments")
    if not isinstance(segments, list) or not segments:
        raise AtlaWireError("Invalid segments in a Bitbucket diff hunk.")
    lines: list[str] = []
    for segment in segments:
        if not isinstance(segment, dict):
            raise AtlaWireError("Expected a Bitbucket diff segment object.")
        kind = segment.get("type")
        prefix = _DIFF_SEGMENT_PREFIXES.get(kind) if isinstance(kind, str) else None
        if prefix is None:
            raise AtlaWireError("Unsupported type in a Bitbucket diff segment.")
        lines.extend(prefix + text for text in _diff_line_texts(segment))
    return lines


def _diff_line_texts(segment: dict[str, object]) -> list[str]:
    """Require nonempty lines with string text and no literal line breaks."""
    entries = segment.get("lines")
    if not isinstance(entries, list) or not entries:
        raise AtlaWireError("Invalid lines in a Bitbucket diff segment.")
    texts: list[str] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise AtlaWireError("Expected a Bitbucket diff line object.")
        text = entry.get("line")
        if not isinstance(text, str):
            raise AtlaWireError("Invalid text in a Bitbucket diff line.")
        texts.append(_diff_text(text, reject_breaks=True))
    return texts


def _diff_text(value: str, *, reject_breaks: bool) -> str:
    """Escape controls and surrogate code points, preserving ordinary text."""
    if reject_breaks and any(char in value for char in _DIFF_LINE_BREAKS):
        raise AtlaWireError("Invalid line break in a Bitbucket diff line.")
    return _DIFF_TEXT_UNSAFE.sub(lambda match: ascii(match[0])[1:-1], value)


def _pull_request_comment(value: object) -> PullRequestComment | None:
    """Project one activity row, or ``None`` for an unrelated activity."""
    if not isinstance(value, dict):
        raise AtlaWireError("Expected a Bitbucket activity object.")
    comment = value.get("comment")
    if comment is None:
        return None
    if not isinstance(comment, dict):
        raise AtlaWireError("Expected a Bitbucket comment object.")
    identifier = comment.get("id")
    if (
        not isinstance(identifier, int)
        or isinstance(identifier, bool)
        or identifier <= 0
    ):
        raise AtlaWireError("Invalid id in a Bitbucket comment.")
    text = comment.get("text")
    if text is None:
        text = ""
    elif not isinstance(text, str):
        raise AtlaWireError("Invalid text in a Bitbucket comment.")
    path, line = _comment_anchor(value)
    return PullRequestComment(
        id=identifier,
        author=_comment_author(comment.get("author")),
        path=path,
        line=line,
        text=text,
        created=_comment_created(comment),
    )


def _comment_author(value: object) -> str | None:
    """Return ``comment.author.name`` when it is a string, or ``None``."""
    if value is None:
        return None
    if not isinstance(value, dict):
        raise AtlaWireError("Invalid author in a Bitbucket comment.")
    name = value.get("name")
    if name is not None and not isinstance(name, str):
        raise AtlaWireError("Invalid author in a Bitbucket comment.")
    return name


def _comment_anchor(activity: dict[str, object]) -> tuple[str | None, int | None]:
    """Prefer ``commentAnchor`` and fall back to legacy ``anchor`` when absent."""
    anchor: object = activity.get("commentAnchor")
    if anchor is None:
        anchor = activity.get("anchor")
    if anchor is None:
        return None, None
    if not isinstance(anchor, dict):
        raise AtlaWireError("Invalid anchor in a Bitbucket comment activity.")
    path = anchor.get("path")
    line = anchor.get("line")
    if path is not None and not isinstance(path, str):
        raise AtlaWireError("Invalid path in a Bitbucket comment activity.")
    if line is not None and (
        not isinstance(line, int) or isinstance(line, bool) or line < 0
    ):
        raise AtlaWireError("Invalid line in a Bitbucket comment activity.")
    return path, line


def _comment_created(comment: dict[str, object]) -> int | None:
    """Prefer ``createdDate`` and fall back to legacy ``created`` when absent."""
    created: object = comment.get("createdDate")
    if created is None:
        created = comment.get("created")
    if created is None:
        return None
    if not isinstance(created, int) or isinstance(created, bool) or created < 0:
        raise AtlaWireError("Invalid creation time in a Bitbucket comment.")
    return created


def _read_pages[RowT](
    session: requests.Session,
    url: str,
    max_pages: int,
    *,
    project: Callable[[object], RowT | None],
) -> list[RowT]:
    start = 0
    rows: list[RowT] = []
    for _ in range(max_pages):
        page = get_json_object(session, url, params={"start": start, "limit": 100})
        values = page.get("values")
        if not isinstance(values, list):
            raise AtlaWireError("Expected a Bitbucket values array.")
        last = page.get("isLastPage")
        if not isinstance(last, bool):
            raise AtlaWireError("Expected a Bitbucket isLastPage boolean.")
        for value in values:
            row = project(value)
            if row is not None:
                rows.append(row)
        if last:
            return rows
        next_start = page.get("nextPageStart")
        if (
            not isinstance(next_start, int)
            or isinstance(next_start, bool)
            or next_start <= start
        ):
            raise AtlaWireError("Invalid or non-advancing Bitbucket nextPageStart.")
        start = next_start
    raise AtlaWireError("Bitbucket page limit reached; increase --max-pages.")


def _project(value: object) -> Project:
    if not isinstance(value, dict):
        raise AtlaWireError("Expected a Bitbucket project object.")
    key, name, description, public = (
        value.get(field) for field in ("key", "name", "description", "public")
    )
    if (
        not isinstance(key, str)
        or not key
        or (name is not None and not isinstance(name, str))
        or (description is not None and not isinstance(description, str))
        or (public is not None and not isinstance(public, bool))
    ):
        raise AtlaWireError("Invalid fields in a Bitbucket project.")
    return Project(
        key=key,
        name=name,
        public=public,
        description=description,
        url=_self_url(value.get("links")),
    )


def _self_url(links: object) -> str | None:
    """Return the first self href verbatim, or ``None`` when it is absent."""
    if links is None:
        return None
    if not isinstance(links, dict):
        raise AtlaWireError("Invalid links in a Bitbucket project.")
    self_links = links.get("self")
    if self_links is None:
        return None
    if not isinstance(self_links, list):
        raise AtlaWireError("Invalid links in a Bitbucket project.")
    if not self_links:
        return None
    first = self_links[0]
    if not isinstance(first, dict):
        raise AtlaWireError("Invalid links in a Bitbucket project.")
    href = first.get("href")
    if href is None:
        return None
    if not isinstance(href, str):
        raise AtlaWireError("Invalid links in a Bitbucket project.")
    return href


def _repository(value: object) -> Repository:
    if not isinstance(value, dict):
        raise AtlaWireError("Expected a Bitbucket repository object.")
    slug, name, state, public = (
        value.get(key) for key in ("slug", "name", "state", "public")
    )
    if (
        not isinstance(slug, str)
        or not slug
        or (name is not None and not isinstance(name, str))
        or (state is not None and not isinstance(state, str))
        or (public is not None and not isinstance(public, bool))
    ):
        raise AtlaWireError("Invalid fields in a Bitbucket repository.")
    return Repository(slug=slug, name=name, state=state, public=public)
