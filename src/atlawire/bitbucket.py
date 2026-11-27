"""Read operations for self-hosted Bitbucket."""

import json
import re
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import TypedDict
from urllib.parse import quote

import requests

from atlawire.http import (
    _TRANSPORT_MESSAGE,
    TEXT_LIMIT,
    TEXT_LIMIT_MESSAGE,
    AtlaWireError,
    _check_status,
    _decode_utf8_text,
    bearer_session,
    get_json_array,
    get_json_object,
    get_json_object_allow_no_content,
    normalize_base_url,
    read_encoded_limited,
    reject_credential_echo,
)

# One grammar per concept, shared with every other module that validates it, so a
# Bitbucket key can never be validated against Jira's rules by accident.
from atlawire.identifiers import BITBUCKET_PROJECT_KEY as _PROJECT_KEY
from atlawire.identifiers import COMMIT_SHA1 as _COMMIT_SHA1
from atlawire.identifiers import DIFF_CONTEXT_MAX as _DIFF_CONTEXT_MAX
from atlawire.identifiers import PAGE_SIZE as _PAGE_SIZE
from atlawire.identifiers import PULL_REQUEST_ID_MAX as _PULL_REQUEST_ID_MAX
from atlawire.identifiers import REPOSITORY_SLUG as _REPOSITORY_SLUG


class PageLimitError(AtlaWireError):
    """A bounded page walk stopped at its configured request budget.

    The dedicated type lets a caller that intentionally reports a partial
    result recognize this stop without matching diagnostic text.
    """


_FILE_UNSAFE = re.compile(r"[\\\x00-\x1f\x7f-\x9f\ud800-\udfff]")
_FILE_PERCENT_ESCAPE = re.compile(r"%[0-9A-Fa-f]{2}")
_REVISION_UNSAFE = re.compile(r"[\x00-\x1f\x7f-\x9f\ud800-\udfff]")
_COMMIT_ID = re.compile(r"[0-9A-Fa-f]{7,40}")
_CHANGES_LIMIT = 1000
_ARCHIVE_FORMATS = frozenset({"zip", "tar", "tar.gz", "tgz"})
# Default transport bound on archive bytes returned as one in-memory value, not
# a claim about expected archive sizes; the body is never truncated.
_ARCHIVE_LIMIT_DEFAULT = 64 * 1024 * 1024
# The shared reader requires an integer limit; None opts out of the byte cap.
_ARCHIVE_LIMIT_UNBOUNDED = 2**63 - 1
_COMMIT_LIMIT_DEFAULT = 25
_FIND_LIMIT_DEFAULT = 25
_PULL_REQUEST_LIMIT_DEFAULT = 25
_TAG_LIMIT_DEFAULT = 25
_PULL_REQUEST_STATES = frozenset({"OPEN", "MERGED", "DECLINED", "ALL"})
_PULL_REQUEST_ORDERS = frozenset({"NEWEST", "OLDEST"})
_PULL_REQUEST_DIRECTIONS = frozenset({"INCOMING", "OUTGOING"})
_PULL_REQUEST_ROLES = frozenset({"AUTHOR", "REVIEWER", "PARTICIPANT"})
# Bitbucket Server 5.10 публикует роль в фильтре участников через
# обязательный username.N; отдельного role.N без username.N нет.
_DASHBOARD_PULL_REQUESTS_PATH = "/rest/api/1.0/dashboard/pull-requests"
_TAG_ORDERS = frozenset({"ALPHABETICAL", "MODIFICATION"})
_SOURCE_PATH_CHANGE_TYPES = frozenset({"MOVE", "COPY", "RENAME"})
# Four times the shared 8 MiB JSON response budget in atlawire.http. This is a
# simple aggregate ceiling for retained per-file fallback output, represented
# as encoded JSON rather than exact Python heap usage.
_DIFF_FALLBACK_RETAINED_LIMIT = 4 * 8 * 1024 * 1024
_DIFF_FALLBACK_RETAINED_MESSAGE = (
    "The pull request diff fallback output exceeds the retained-output limit; "
    "request fewer files or use explicit per-file diffs."
)
_DASHBOARD_STATES = frozenset({"OPEN", "MERGED", "DECLINED"})
_DASHBOARD_ROLES = frozenset({"AUTHOR", "REVIEWER", "PARTICIPANT"})
_DASHBOARD_PARTICIPANT_STATUSES = frozenset({"UNAPPROVED", "NEEDS_WORK", "APPROVED"})
_DASHBOARD_PARTICIPANT_STATUS_MAX = 3
_COMMIT_DIFF_PATH_MAX = 100
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_DIFF_REVIEW_HEADER = (
    "# Bitbucket {subject} diff review "
    "(context={context}; whitespace={whitespace}; "
    "server-declared truncation: none; not a patch)"
)
_DIFF_SUBJECT_PULL_REQUEST = "PR"
_DIFF_SUBJECT_COMMIT = "commit"
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


class DeclaredTruncationError(AtlaWireError):
    """A server explicitly declared a response truncated.

    This is a subtype of [AtlaWireError][atlawire.http.AtlaWireError], so
    existing callers keep catching the base type and the existing message stays
    unchanged. The distinct type lets the pull request diff fallback react only
    to a declared truncation, never to auth, transport, or malformed-shape
    failures.
    """


class Repository(TypedDict):
    slug: str
    name: str | None
    state: str | None
    public: bool | None


class RepositoryMatch(TypedDict):
    project: str
    slug: str
    name: str | None
    state: str | None


class Project(TypedDict):
    key: str
    name: str | None
    public: bool | None
    description: str | None
    url: str | None


class ChangedFile(TypedDict):
    path: str
    type: str | None
    node: str | None


# The pull request file listing shares the changed-file projection.
PullRequestFile = ChangedFile


class PullRequestComment(TypedDict):
    id: int
    author: str | None
    path: str | None
    line: int | None
    text: str
    created: int | None


PullRequest = TypedDict(
    "PullRequest",
    {
        "id": int,
        "title": str,
        "state": str,
        "author": str | None,
        "from": str | None,
        "to": str | None,
        "updated": int | None,
    },
)


class MyPullRequest(TypedDict):
    repo: str
    id: int
    title: str
    state: str
    author: str | None
    reviewers_inactive: list[str]
    created: int | None


class PullRequestFallbackFile(TypedDict):
    path: str
    source_path: str | None
    diff: dict[str, object]


class PullRequestDiffFallback(TypedDict):
    fallback: bool
    fallback_reason: str | None
    diff: dict[str, object] | None
    files: list[PullRequestFallbackFile]


class _PullRequestFallbackChange(TypedDict):
    path: str
    source_path: str | None


class Branch(TypedDict):
    name: str
    id: str
    commit: str | None
    default: bool | None


class Commit(TypedDict):
    """Строка проекции коммита из ответа ``/commits``.

    ``author``, ``email`` и ``displayName`` берутся из вложенного ``author``
    (поля ``name``, ``emailAddress`` и ``displayName``) той же строки ответа,
    поэтому отдельных запросов на коммит нет. Bitbucket Server 5.10 в схеме
    ``/commits`` документирует у автора только ``name`` и ``emailAddress``,
    поэтому ``displayName`` обычно ``None``; присланное значение сохраняется,
    если сервер его всё-таки отдал. ``date`` — человекочитаемое UTC-время с
    точностью до минуты (``YYYY-MM-DD HH:MM``), ``timestamp`` — исходный
    ``authorTimestamp`` в миллисекундах epoch без округления; отсутствующее
    поле даёт ``None`` в обоих.

    Идентификатор коммита отдаётся под теми именами, что в документации
    ``/commits``: ``id`` — полный SHA-1, ``displayId`` — сокращённая форма для
    показа человеку. Своё имя для сокращённой формы (например ``short_id``) не
    вводится: одно значение под двумя именами заставляет потом вспоминать, чем
    они различаются.

    ``hash`` остаётся только для совместимости с кодом, написанным до 0.9.2, и
    содержит то же, что ``id``. Новый код должен читать ``id``; алиас будет
    удалён в следующей мажорной версии.
    """

    id: str
    displayId: str | None
    hash: str
    date: str | None
    timestamp: int | None
    author: str | None
    email: str | None
    displayName: str | None
    message: str


class CommitListing(TypedDict):
    """Коммиты репозитория вместе с честным признаком полноты выборки.

    ``complete=True`` значит, что сервер отдал терминальную страницу
    (``isLastPage=True``) и все строки уложились в ``limit``; ``complete=False``
    значит, что выборка оборвана лимитом и коммитов может быть больше.
    Общее число не сообщается: Bitbucket Server 5.10 не отдаёт ``totalCount``
    в ответе ``/commits``, поэтому признак неполноты — единственный надёжный
    сигнал.
    """

    commits: list[Commit]
    limit: int
    complete: bool


class TagListing(TypedDict):
    """Теги репозитория вместе с честным признаком полноты выборки.

    ``complete=True`` значит, что сервер отдал терминальную страницу
    (``isLastPage=True``) и все теги уложились в ``limit``; ``complete=False``
    значит, что выборка оборвана лимитом и тегов может быть больше. Общее число
    не сообщается: ответ ``/tags`` 5.10 не содержит ``totalCount``.
    """

    tags: list[dict[str, object]]
    limit: int
    complete: bool


class DirectoryEntry(TypedDict):
    path: str
    type: str | None
    size: int | None


class BlameLine(TypedDict):
    line: int
    author: str | None
    email: str | None
    date: str | None
    commit: str | None


class ProjectDetail(TypedDict):
    key: str
    name: str | None
    description: str | None
    public: bool | None
    type: str | None


class RepositoryDetail(TypedDict):
    slug: str
    name: str | None
    state: str | None
    public: bool | None
    defaultBranch: str | None


class BranchDetail(TypedDict):
    id: str
    displayId: str | None
    latestCommit: str | None
    isDefault: bool | None


class CommitComment(TypedDict):
    id: int
    author: str | None
    text: str
    createdDate: int | None


class ParticipantRow(TypedDict):
    name: str | None
    displayName: str | None
    role: str | None


class RepositoryLink(TypedDict):
    slug: str
    project: str | None
    state: str | None


def list_projects(
    base_url: str,
    *,
    token: str,
    limit: int | None = None,
    max_pages: int = 100,
    allow_http_loopback: bool = False,
) -> list[Project]:
    """List visible projects in server order or raise without a partial list.

    ``limit`` caps returned rows and stops the page walk once it is reached;
    ``None`` keeps the full walk.
    """
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    if (
        not isinstance(max_pages, int)
        or isinstance(max_pages, bool)
        or not 1 <= max_pages <= 1000
    ):
        raise AtlaWireError("The page limit must be between 1 and 1000.")
    _check_row_limit(limit)
    url = f"{base}/rest/api/1.0/projects"
    with bearer_session(token, product="bitbucket") as session:
        return _read_pages(session, url, max_pages, project=_project, limit=limit)


def list_repositories(
    base_url: str,
    project: str,
    *,
    token: str,
    limit: int | None = None,
    max_pages: int = 100,
    allow_http_loopback: bool = False,
) -> list[Repository]:
    """List repositories in server order or raise without returning a partial list.

    ``limit`` caps returned rows and stops the page walk once it is reached;
    ``None`` keeps the full walk.
    """
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    if not _PROJECT_KEY.fullmatch(project):
        raise AtlaWireError("Expected a Bitbucket project key or ~user project.")
    _validate_page_limit(max_pages)
    _check_row_limit(limit)
    url = f"{base}/rest/api/1.0/projects/{project}/repos"
    with bearer_session(token, product="bitbucket") as session:
        return _read_pages(session, url, max_pages, project=_repository, limit=limit)


def list_all_repositories(
    base_url: str,
    *,
    token: str,
    start: int = 0,
    limit: int = _PAGE_SIZE,
    max_pages: int = 100,
    allow_http_loopback: bool = False,
) -> list[dict[str, object]]:
    """List every visible repository on the instance in server order.

    One GET reads the instance-wide ``/rest/api/1.0/repos`` collection.
    ``start`` is the initial cursor and ``limit`` is the requested page size;
    the next cursor is never computed from them. Every nonterminal page is
    followed through its own opaque ``nextPageStart`` until the exact
    ``isLastPage`` boolean, so a noncontiguous or short page is never mistaken
    for the end. Rows are returned exactly as decoded, preserving unknown and
    nested fields, and links carried by a row are never followed. ``max_pages``
    bounds the traversal; reaching it raises instead of returning a partial
    list.
    """
    _validate_page_limit(max_pages)
    if not isinstance(start, int) or isinstance(start, bool) or start < 0:
        raise AtlaWireError("Expected a non-negative Bitbucket start index.")
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 1000:
        raise AtlaWireError("The repository page size must be between 1 and 1000.")
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    url = f"{base}/rest/api/1.0/repos"
    rows: list[dict[str, object]] = []
    cursor = start
    with bearer_session(token, product="bitbucket") as session:
        for _ in range(max_pages):
            page = get_json_object(
                session, url, params={"start": cursor, "limit": limit}
            )
            values = page.get("values")
            if not isinstance(values, list):
                raise AtlaWireError("Expected a Bitbucket values array.")
            _check_page_echo(page, start=cursor, rows=len(values))
            for value in values:
                if not isinstance(value, dict):
                    raise AtlaWireError("Expected a Bitbucket repository object.")
                rows.append(value)
            last = page.get("isLastPage")
            if not isinstance(last, bool):
                raise AtlaWireError("Expected a Bitbucket isLastPage boolean.")
            if last:
                return rows
            cursor = _next_page_start(page, cursor)
    raise PageLimitError("Bitbucket page limit reached; increase --max-pages.")


def find_repositories(
    base_url: str,
    name: str,
    *,
    token: str,
    limit: int = _FIND_LIMIT_DEFAULT,
    max_pages: int = 100,
    allow_http_loopback: bool = False,
) -> list[RepositoryMatch]:
    """Find repositories across the visible projects by name or slug substring.

    The search is case-insensitive through ``lower()``: a repository matches
    when the needle is a substring of its slug or of a non-null name. The exact
    nonblank needle is preserved, project and repository order is the server's,
    and only ``project``, ``slug``, ``name`` and ``state`` are projected.

    The legacy visible-project walk is reproduced: the project list is read to
    exhaustion first in server order, then each project's repositories are paged
    in order and paging stops as soon as ``limit`` matching rows have been
    projected, so a repository list is not read past the match cap and no
    further project is started. Every row of a fetched page is still projected
    and validated before that early stop, and the unused next-page hint of the
    final page is never requested. ``max_pages`` is one total request-attempt
    budget shared by the project list and every repository page, not a
    per-project allowance. Any later cursor, transport, or budget failure raises
    without returning partial rows. Server project keys are validated before a
    repository path is built and response links are never followed.
    """
    needle = _repository_needle(name)
    _validate_row_limit(limit)
    _validate_page_limit(max_pages)
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    with bearer_session(token, product="bitbucket") as session:
        return _find_in_projects(
            session,
            f"{base}/rest/api/1.0/projects",
            needle,
            limit=limit,
            max_pages=max_pages,
        )


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
    with bearer_session(token, product="bitbucket") as session:
        value = get_json_object(session, url, params={})
    _validate_pull_request(value, identifier)
    return value


def get_pull_request_merge_status(
    base_url: str,
    repo: str,
    pr_id: str | int,
    *,
    token: str,
    allow_http_loopback: bool = False,
) -> dict[str, object]:
    """Return the server's mergeability object for one pull request.

    ``repo`` is ``PROJECT/slug`` and ``pr_id`` follows the same canonical
    positive decimal rules as
    [get_pull_request][atlawire.bitbucket.get_pull_request]. Exactly one GET
    targets the fixed ``/merge`` route without query parameters through the
    shared bearer and JSON transport.

    The decoded object is returned unchanged, so documented fields such as
    ``canMerge``, ``conflicted``, ``outcome`` and ``vetoes`` keep their raw
    nested values and unknown fields are preserved. This read only asks whether
    the pull request can be merged: it never sends the prohibited merge POST,
    requests another route, or follows response links. Only the shared object
    shape is required; no additional field validation is applied.
    """
    _, url, _ = _pull_request_target(
        base_url, repo, pr_id, allow_http_loopback=allow_http_loopback
    )
    with bearer_session(token, product="bitbucket") as session:
        return get_json_object(session, f"{url}/merge", params={})


def pr_compact(
    base_url: str,
    repo: str,
    pr_id: str | int,
    *,
    token: str,
    allow_http_loopback: bool = False,
) -> dict[str, object]:
    """Return a compact pull request projection for reports and agents.

    One ``GET`` reads the pull request through
    [get_pull_request][atlawire.bitbucket.get_pull_request]; the result keeps the
    stable fields and drops service metadata such as ``links``,
    ``permittedOperations`` and avatars. Field order is fixed.
    """
    value = get_pull_request(
        base_url, repo, pr_id, token=token, allow_http_loopback=allow_http_loopback
    )
    base, _, identifier = _pull_request_target(
        base_url, repo, pr_id, allow_http_loopback=allow_http_loopback
    )
    row = _pull_request(value)
    created = value.get("createdDate")
    if created is not None and (
        not isinstance(created, int) or isinstance(created, bool) or created < 0
    ):
        raise AtlaWireError("Invalid fields in a Bitbucket pull request.")
    project, slug = _split_repo(repo)
    return {
        "id": row["id"],
        "title": row["title"],
        "state": row["state"],
        "author": row["author"],
        "from": row["from"],
        "to": row["to"],
        "created": created,
        "updated": row["updated"],
        "reviewers_active": _active_reviewers(value),
        "url": (
            f"{base}/projects/{quote(project, safe='')}"
            f"/repos/{quote(slug, safe='')}/pull-requests/{identifier}"
        ),
    }


def get_repository_file(
    base_url: str,
    repo: str,
    path: str,
    *,
    token: str,
    at: str | None = None,
    allow_http_loopback: bool = False,
) -> str:
    """Return one repository file at a revision as exact UTF-8 text.

    ``repo`` is ``PROJECT/slug`` and ``path`` is a relative Git path with safe
    segments. The revision is optional: omitting it reads the server's default
    branch, exactly like the listing readers, so a list-then-read workflow stays
    on the same branch. A non-empty ``at`` is sent only as the ``at`` query
    parameter; pass a commit id when one exact snapshot is required. The call
    makes one streamed raw request with
    ``Accept: text/plain``; this server refuses the raw route without it. The
    route serves the stored bytes with a media type derived from the file, so
    ``.java`` and ``.gradle`` arrive as ``text/plain`` while ``.md`` arrives as
    ``text/markdown``. The reader therefore follows the reference client
    (``atlassian-python-api`` ``get_content_of_file`` with
    ``not_json_response``): a body whose media type is not JSON is the file
    text. Size, UTF-8, control-character, and credential-echo rules stay the
    shared ones, so an oversize or binary response raises without returning
    partial text, while a JSON document is treated as an error response.
    """
    params = _revision_params(at)
    segments = _file_segments(path)
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    project, slug = _split_repo(repo)
    with bearer_session(token, product="bitbucket") as session:
        return _read_raw_file_text(
            session,
            _raw_file_url(base, project, slug, segments),
            params=params,
            token=token,
        )


def read_repository_file_in_session(
    session: requests.Session,
    base_url: str,
    repo: str,
    path: str,
    *,
    token: str,
    at: str | None = None,
    allow_http_loopback: bool = False,
) -> str:
    """Read one repository file through a caller-owned session.

    Validation, destination and body rules are exactly those of
    [get_repository_file][atlawire.bitbucket.get_repository_file]; only session
    ownership differs. The caller keeps one session for a bounded multi-file
    read, so a per-file scan does not open a new connection pool each time.
    """
    params = _revision_params(at)
    segments = _file_segments(path)
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    project, slug = _split_repo(repo)
    return _read_raw_file_text(
        session,
        _raw_file_url(base, project, slug, segments),
        params=params,
        token=token,
    )


def get_repository_archive(
    base_url: str,
    project_key: str,
    repository_slug: str,
    *,
    token: str,
    at: str | None = None,
    format: str | None = None,
    max_bytes: int | None = _ARCHIVE_LIMIT_DEFAULT,
    allow_http_loopback: bool = False,
) -> bytes:
    """Download one repository archive and return its exact bytes.

    The fixed ``/rest/api/1.0/projects/{project}/repos/{slug}/archive`` route
    is requested exactly once with ``Accept: */*``. A nonempty ``at`` selects
    the revision and ``format`` selects the streamed archive format; the server
    defaults to ``zip`` when no format is given. The project and repository
    identities, ``at``, ``format``, and ``max_bytes`` are validated before any
    session exists.

    The whole archive is returned as one ``bytes`` value, so the decoded-size
    bound exists to keep a single call's memory use bounded and predictable; it
    is a transport guard, not a claim about expected archive sizes. The bound is
    ``max_bytes``: it defaults to 64 MiB and a caller may raise it or pass
    ``None`` to disable it, but neither removes the buffering. Archives that may
    exceed available memory must be fetched with a streaming client instead of
    this function. The response is read without a UTF-8 or content-type
    assumption, so a binary archive is returned unchanged and is never
    truncated. A redirect, HTTP 206, an authorization failure, any other non-2xx
    status, a transport failure, or an oversize body raises a sanitized
    [AtlaWireError][atlawire.http.AtlaWireError] without a partial body;
    diagnostics never contain the URL, path, body, or credential. Nothing is
    written to local storage and response links are never followed.
    """
    if not isinstance(project_key, str) or not _PROJECT_KEY.fullmatch(project_key):
        raise AtlaWireError("Expected a Bitbucket project key.")
    if (
        not isinstance(repository_slug, str)
        or not _REPOSITORY_SLUG.fullmatch(repository_slug)
        or repository_slug in {".", ".."}
    ):
        raise AtlaWireError("Expected a Bitbucket repository slug.")
    params: dict[str, str] = {}
    if at is not None:
        params["at"] = _revision(at)
    if format is not None:
        params["format"] = _archive_format(format)
    if max_bytes is not None and (
        not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes < 1
    ):
        raise AtlaWireError(
            "The archive byte limit must be a positive integer or None."
        )
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    url = (
        f"{base}/rest/api/1.0/projects/{quote(project_key, safe='')}"
        f"/repos/{quote(repository_slug, safe='')}/archive"
    )
    with bearer_session(token, product="bitbucket") as session:
        try:
            with session.get(
                url,
                params=params,
                headers={"Accept": "*/*"},
                timeout=(5, 30),
                allow_redirects=False,
                stream=True,
            ) as response:
                _check_status(response.status_code, method="GET", product="bitbucket")
                if max_bytes is None:
                    limit = _ARCHIVE_LIMIT_UNBOUNDED
                    message = "The repository archive exceeds the byte limit."
                else:
                    limit = max_bytes
                    message = (
                        "The repository archive exceeds the "
                        f"{max_bytes}-byte limit; raise max_bytes or "
                        "use a streaming client."
                    )
                return read_encoded_limited(
                    response,
                    limit=limit,
                    message=message,
                )
        except requests.Timeout:
            raise AtlaWireError(
                "Request timed out.", category="transport", method="GET"
            ) from None
        except requests.RequestException:
            raise AtlaWireError(
                _TRANSPORT_MESSAGE, category="transport", method="GET"
            ) from None


def get_file_blame(
    base_url: str,
    repo: str,
    path: str,
    *,
    token: str,
    at: str | None = None,
    allow_http_loopback: bool = False,
) -> list[BlameLine]:
    """Return per-line blame for one repository file in server order.

    ``repo`` is ``PROJECT/slug`` and ``path`` is a relative Git path with the
    same safe segments as
    [get_repository_file][atlawire.bitbucket.get_repository_file]. The fixed
    ``/browse`` route is requested exactly once with ``blame=true`` and
    ``noContent=true``; a nonempty ``at`` is sent only as the revision query.
    Path, revision, and repository are validated before any session exists.

    Only the blame-only bare JSON array is supported. The documented paged
    file-content envelope is rejected rather than interpreted, no page cursor
    or metadata is read, and no alternate response shape or request is tried.

    Rows are projected in array order with a 1-based ``line`` for every entry,
    including repeated commits. ``author`` and ``email`` come from
    ``author.name`` and ``author.emailAddress`` and may be null. ``date`` is a
    UTC ``YYYY-MM-DD`` from integer ``authorTimestamp`` milliseconds, preserving
    zero and pre-epoch values. ``commit`` prefers a nonempty ``commitHash`` and
    falls back to a nonempty ``id``; both absent, null, or empty yield null.
    The whole array is projected before it is returned, so a malformed later
    entry raises without partial rows.
    """
    segments = _file_segments(path)
    params = _revision_params(at)
    params["blame"] = "true"
    params["noContent"] = "true"
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    url = _repository_url(base, repo)
    with bearer_session(token, product="bitbucket") as session:
        values = get_json_array(session, _browse_url(url, segments), params=params)
    return [_blame_line(number, value) for number, value in enumerate(values, start=1)]


def list_repository_files(
    base_url: str,
    repo: str,
    *,
    token: str,
    at: str | None = None,
    limit: int | None = None,
    max_pages: int = 100,
    before_page: Callable[[], None] | None = None,
    allow_http_loopback: bool = False,
) -> list[str]:
    """List every file path under the repository root in server order.

    ``repo`` is ``PROJECT/slug``. The fixed ``/files`` endpoint searches
    recursively from the root. A nonempty ``at`` is sent only as the revision
    query; ``None`` and the empty string are omitted so the server uses its
    default branch. Rows are projected from the documented nonempty string
    values, with the legacy object representation read through the shared path
    reader. Each page is followed through its own ``nextPageStart``, and the
    whole list is built before it is returned, so a later failure yields no
    partial list. The optional ``before_page`` callback runs before every page
    request and propagates its exception; it is not a cancellation mechanism for
    an in-flight request.
    """
    _validate_page_limit(max_pages)
    _check_row_limit(limit)
    params = _revision_params(at)
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    url = _repository_url(base, repo)
    with bearer_session(token, product="bitbucket") as session:
        return _read_pages(
            session,
            f"{url}/files",
            max_pages,
            project=_repository_file_path,
            params=params,
            limit=limit,
            before_page=before_page,
        )


def list_directory(
    base_url: str,
    repo: str,
    path: str = "",
    *,
    token: str,
    at: str | None = None,
    limit: int | None = None,
    max_pages: int = 100,
    allow_http_loopback: bool = False,
) -> list[DirectoryEntry]:
    """List the direct children of one repository directory in server order.

    ``repo`` is ``PROJECT/slug`` and ``path`` is a relative directory path with
    the same safe segments as
    [get_repository_file][atlawire.bitbucket.get_repository_file]; the empty
    string means the repository root. The fixed ``/browse`` endpoint is
    requested once per cursor page, and every page reads the nested ``children``
    envelope rather than the outer browse metadata. A file ``lines`` response
    or a missing/malformed ``children`` object fails the whole call instead of
    looking empty. ``size`` is kept exactly, including zero, and no parent path,
    link, or URL is reconstructed or followed.
    """
    _validate_page_limit(max_pages)
    _check_row_limit(limit)
    segments = _directory_segments(path)
    params = _revision_params(at)
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    url = _repository_url(base, repo)
    with bearer_session(token, product="bitbucket") as session:
        return _read_pages(
            session,
            _browse_url(url, segments),
            max_pages,
            project=_directory_entry,
            params=params,
            limit=limit,
            transform=_children_envelope,
        )


def get_last_modified(
    base_url: str,
    repo: str,
    path: str | None = None,
    *,
    token: str,
    at: str | None = None,
    allow_http_loopback: bool = False,
) -> dict[str, object]:
    """Вернуть метаданные последних изменений репозитория или относительного пути.

    ``repo`` — ``PROJECT/slug``. ``None`` и пустая строка выбирают корень
    репозитория; иначе ``path`` — относительный Git-путь, каждый сегмент
    которого кодируется ровно один раз. Явный ``at`` уходит единственным
    query-параметром ``at``.

    Документация 5.10 обещает 200 и без ``at``, но живая проверка (2026-11-23)
    показывает HTTP 400 «No at commit was specified» на обеих формах: маршрут
    всегда требует стартовый коммит. Поэтому при ``None``/пустой строке ``at``
    библиотека сама разрешает ветку по умолчанию через
    [get_default_branch][atlawire.bitbucket.get_default_branch] и отправляет её
    ``latestCommit`` как явный полный 40-hex коммит. Нет ветки или её коммит не
    является полным 40-hex ID — понятная ошибка до запроса last-modified.

    Ровно один GET уходит на ``/last-modified`` с выбранным path-суффиксом и
    обязательным ``at``. Декодированный объект возвращается без изменений:
    ``files``, ``latestCommit`` и неизвестные вложенные поля сохраняются, ссылки
    ответа не открываются.

    Живая проверка (2026-11-23) показала серверный дефект: path-форма для пути,
    который указывает на файл, отвечает HTTP 500, хотя для каталога и для
    root-формы с тем же коммитом сервер отвечает 200. Сырой HTTP 500 наружу не
    отдаётся: он преобразуется в понятную ошибку с подсказкой использовать
    root-форму или путь каталога. Это остаётся ошибкой — тихого успеха нет.
    """
    suffix = _last_modified_suffix(path)
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    url = _repository_url(base, repo)
    if at is None or at == "":
        project, slug = _split_repo(repo)
        branch = get_default_branch(
            base,
            project,
            slug,
            token=token,
            allow_http_loopback=allow_http_loopback,
        )
        if branch is None:
            raise AtlaWireError("The repository has no default branch.")
        commit = branch.get("latestCommit")
        if not isinstance(commit, str) or not _COMMIT_SHA1.fullmatch(commit):
            raise AtlaWireError(
                "The repository default branch does not carry a full commit ID."
            )
        revision = commit
    else:
        revision = _revision(at)
    with bearer_session(token, product="bitbucket") as session:
        try:
            return get_json_object(
                session, f"{url}/last-modified{suffix}", params={"at": revision}
            )
        except AtlaWireError as exc:
            if not suffix or exc.http_status != 500:
                raise
            # Подтверждено живым сервером: path-форма для файла падает внутри
            # сервера, хотя документированный запрос совпадает с каталогом.
            raise AtlaWireError(
                "Bitbucket Server failed the last-modified path form; this server "
                "fails when the path names a file. Use the repository-root form "
                "or pass a directory path.",
                category="upstream",
                http_status=500,
                method="GET",
            ) from None


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

    The selected file is read with the same non-JSON media-type rule as
    [get_repository_file][atlawire.bitbucket.get_repository_file].
    """
    selected_side = _file_side(side)
    segments = _file_segments(path)
    base, url, identifier = _pull_request_target(
        base_url, repo, pr_id, allow_http_loopback=allow_http_loopback
    )
    with bearer_session(token, product="bitbucket") as session:
        value = get_json_object(session, url, params={})
        _validate_pull_request(value, identifier)
        project, slug, commit = _selected_file_ref(value, selected_side)
        return _read_raw_file_text(
            session,
            _raw_file_url(base, project, slug, segments),
            params={"at": commit},
            token=token,
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
    with bearer_session(token, product="bitbucket") as session:
        page = get_json_object(
            session, f"{url}/changes", params={"limit": _CHANGES_LIMIT}
        )
    return _pull_request_files(page)


def _pull_request_fallback_changes(
    base_url: str,
    repo: str,
    pr_id: str | int,
    *,
    token: str,
    allow_http_loopback: bool,
) -> list[_PullRequestFallbackChange]:
    """Read and validate the complete changes page used by the fallback."""
    _, url, _ = _pull_request_target(
        base_url, repo, pr_id, allow_http_loopback=allow_http_loopback
    )
    with bearer_session(token, product="bitbucket") as session:
        page = get_json_object(
            session, f"{url}/changes", params={"limit": _CHANGES_LIMIT}
        )
    return _fallback_changes(page)


def get_pull_request_diff(
    base_url: str,
    repo: str,
    pr_id: str | int,
    *,
    token: str,
    context: int = 3,
    path: str | None = None,
    source_path: str | None = None,
    whitespace: str = "ignore-all",
    allow_http_loopback: bool = False,
) -> dict[str, object]:
    """Return the server's decoded diff object for one pull request.

    ``repo`` is ``PROJECT/slug`` and ``pr_id`` follows the same canonical
    positive decimal rules as [get_pull_request][atlawire.bitbucket.get_pull_request].
    The whole-diff endpoint is requested once with ``contextLines=context``,
    ``withComments=false`` and ``whitespace``, which must be ``ignore-all``
    (the default), ``ignore-trailing`` or ``ignore-none``. ``ignore-none``
    keeps whitespace-only changes. Both arguments are validated before any
    session is created; ``context`` must be an ``int`` from 0 to 100.

    An explicit relative ``path`` instead requests that one file's diff once,
    with each validated segment encoded exactly once. ``source_path`` is only
    permitted with ``path``: it is validated as relative repository text and
    sent verbatim as ``srcPath`` so Requests encodes it once. It is required by
    the server for a renamed, copied or moved file, but this call makes no
    inference about a missing source path and never adds another route.

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

    Use [get_pull_request_diffs][atlawire.bitbucket.get_pull_request_diffs] when
    several files are needed in one call.
    """
    _diff_context(context)
    _, url, _ = _pull_request_target(
        base_url, repo, pr_id, allow_http_loopback=allow_http_loopback
    )
    target, params = _pull_request_diff_request(
        url, context, path, source_path, whitespace=whitespace
    )
    with bearer_session(token, product="bitbucket") as session:
        value = get_json_object(session, target, params=params)
    _validate_diff(value, subject="pull request")
    return value


def get_pull_request_diffs(
    base_url: str,
    repo: str,
    pr_id: str | int,
    *,
    token: str,
    paths: Sequence[str],
    context: int = 3,
    whitespace: str = "ignore-all",
    allow_http_loopback: bool = False,
) -> list[dict[str, object]]:
    """Read several per-file pull request diffs in one call.

    One fixed ``/diff/{path}`` GET is sent per entry and the results are
    returned in request order. Duplicates, an empty sequence, non-string
    entries and more than [_COMMIT_DIFF_PATH_MAX][atlawire.bitbucket] entries
    are rejected before any request. One session serves the whole batch; any
    later failure raises without returning a partial list.
    """
    _diff_context(context)
    _, url, _ = _pull_request_target(
        base_url, repo, pr_id, allow_http_loopback=allow_http_loopback
    )
    return _pull_request_diff_paths(url, context, paths, token, whitespace=whitespace)


def _pull_request_diff_paths(
    url: str,
    context: int,
    paths: Sequence[str],
    token: str,
    *,
    whitespace: str = "ignore-all",
) -> list[dict[str, object]]:
    """Read one validated per-path diff per entry, in request order."""
    if not isinstance(paths, Sequence) or isinstance(paths, (str, bytes)):
        raise AtlaWireError("Expected pull request diff paths as a sequence.")
    if not paths:
        raise AtlaWireError("Expected at least one pull request diff path.")
    if len(paths) > _COMMIT_DIFF_PATH_MAX:
        raise AtlaWireError(
            f"At most {_COMMIT_DIFF_PATH_MAX} pull request diff paths are supported."
        )
    targets: list[tuple[str, dict[str, str | int]]] = []
    seen: set[str] = set()
    for path in paths:
        if not isinstance(path, str):
            raise AtlaWireError("Expected pull request diff paths as strings.")
        if path in seen:
            raise AtlaWireError("Duplicate pull request diff path.")
        seen.add(path)
        targets.append(
            _pull_request_diff_request(url, context, path, None, whitespace=whitespace)
        )
    results: list[dict[str, object]] = []
    with bearer_session(token, product="bitbucket") as session:
        for target, params in targets:
            value = get_json_object(session, target, params=params)
            _validate_diff(value, subject="pull request")
            results.append(value)
    return results


def get_pull_request_diff_with_fallback(
    base_url: str,
    repo: str,
    pr_id: str | int,
    *,
    token: str,
    context: int = 3,
    allow_http_loopback: bool = False,
) -> PullRequestDiffFallback:
    """Return a whole pull request diff or an all-or-nothing file fallback.

    Exactly one whole-diff request is made first through
    [get_pull_request_diff][atlawire.bitbucket.get_pull_request_diff]. A
    successful response is returned unchanged with ``fallback=False``.

    Only a [DeclaredTruncationError][atlawire.bitbucket.DeclaredTruncationError]
    from that whole-diff response triggers the fallback. Auth, transport,
    malformed flags, and malformed shapes propagate unchanged without another
    request. The fallback then reads the one documented ``/changes`` page and
    requires it to be terminal, untruncated, and below its reported limit;
    capped, truncated, malformed, or failed changes fail the call. Every changed
    path is validated before any per-file request, duplicate destination paths
    fail, and copied, moved, or renamed entries must carry a valid ``srcPath``.

    Each changed file is then fetched once through the explicit per-file diff
    contract, including ``srcPath`` when present, and every response is
    validated with the same declared-truncation rules. Any later failure aborts
    the whole call without a partial result. An empty changes page after a
    declared whole-diff truncation is rejected as inconsistent rather than
    returned as a recovered empty result. The returned ``files`` list keeps each
    decoded diff object unchanged and in server order; ``fallback=True`` and
    ``fallback_reason`` identify why the whole diff was not used.

    This proves only that the server declared the whole diff truncated. It does
    not prove completeness against an unflagged server cap, and no response
    link is followed. Requests are not snapshot-pinned: if the pull request
    changes between the whole-diff read, the changes read, and the per-file
    reads, the fallback can mix revisions. A successful result therefore does
    not assert snapshot consistency.

    Retained per-file diffs are capped in aggregate at four times the shared
    8 MiB JSON response budget (32 MiB), measured as encoded-JSON size per
    object rather than exact Python heap usage. A valid but very large PR whose
    recovered diffs exceed this guard fails with no partial result and must use
    explicit per-file diff requests instead.
    """
    try:
        whole = get_pull_request_diff(
            base_url,
            repo,
            pr_id,
            token=token,
            context=context,
            allow_http_loopback=allow_http_loopback,
        )
    except DeclaredTruncationError as error:
        reason = str(error)
    else:
        return PullRequestDiffFallback(
            fallback=False,
            fallback_reason=None,
            diff=whole,
            files=[],
        )
    changes = _pull_request_fallback_changes(
        base_url,
        repo,
        pr_id,
        token=token,
        allow_http_loopback=allow_http_loopback,
    )
    files: list[PullRequestFallbackFile] = []
    retained = 0
    for change in changes:
        diff = get_pull_request_diff(
            base_url,
            repo,
            pr_id,
            token=token,
            context=context,
            path=change["path"],
            source_path=change["source_path"],
            allow_http_loopback=allow_http_loopback,
        )
        retained += _retained_diff_size(diff)
        if retained > _DIFF_FALLBACK_RETAINED_LIMIT:
            raise AtlaWireError(_DIFF_FALLBACK_RETAINED_MESSAGE)
        files.append(
            PullRequestFallbackFile(
                path=change["path"],
                source_path=change["source_path"],
                diff=diff,
            )
        )
    return PullRequestDiffFallback(
        fallback=True,
        fallback_reason=reason,
        diff=None,
        files=files,
    )


def get_pull_request_diffs_text(
    base_url: str,
    repo: str,
    pr_id: str | int,
    *,
    token: str,
    paths: Sequence[str],
    context: int = 3,
    whitespace: str = "ignore-all",
    allow_http_loopback: bool = False,
) -> str:
    """Return one review view over several per-file pull request diffs.

    This is the batch text form of
    [get_pull_request_diffs][atlawire.bitbucket.get_pull_request_diffs]: one
    ``/diff/{path}`` request per entry, rendered under a single header in input
    order, so a caller pays one call instead of one call per file. Duplicates,
    an empty sequence, non-string entries and more than 100 paths are rejected
    before any request; a later failure raises without returning partial text.
    ``whitespace`` and ``context`` are the same validated values as the single
    file readers.
    """
    _diff_context(context)
    _, url, _ = _pull_request_target(
        base_url, repo, pr_id, allow_http_loopback=allow_http_loopback
    )
    values = _pull_request_diff_paths(url, context, paths, token, whitespace=whitespace)
    text = _render_pull_request_diffs_text(
        values, context=context, whitespace=whitespace
    )
    reject_credential_echo(text, tokens=(token,))
    return text


def get_pull_request_diff_text(
    base_url: str,
    repo: str,
    pr_id: str | int,
    *,
    token: str,
    context: int = 3,
    path: str | None = None,
    source_path: str | None = None,
    whitespace: str = "ignore-all",
    allow_http_loopback: bool = False,
) -> str:
    """Return a terminal-safe review view of one pull request diff.

    The call makes exactly one diff request through
    [get_pull_request_diff][atlawire.bitbucket.get_pull_request_diff], so it
    inherits its context bounds, fixed ``whitespace=ignore-all`` request,
    explicit ``path``/``source_path`` selection and declared-truncation checks.
    The header describes that request, not metadata echoed by the response.

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
        path=path,
        source_path=source_path,
        whitespace=whitespace,
        allow_http_loopback=allow_http_loopback,
    )
    text = _render_pull_request_diff_text(value, context=context, whitespace=whitespace)
    reject_credential_echo(text, tokens=(token,))
    return text


def list_pull_request_comments(
    base_url: str,
    repo: str,
    pr_id: str | int,
    *,
    token: str,
    limit: int | None = None,
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
    _check_row_limit(limit)
    with bearer_session(token, product="bitbucket") as session:
        return _read_pages(
            session,
            f"{url}/activities",
            max_pages,
            project=_pull_request_comment,
            limit=limit,
        )


def list_pull_request_commits(
    base_url: str,
    repo: str,
    pr_id: str | int,
    *,
    token: str,
    limit: int | None = None,
    max_pages: int = 100,
    allow_http_loopback: bool = False,
) -> list[Commit]:
    """List the commits of one pull request in server order.

    ``repo`` is ``PROJECT/slug`` and ``pr_id`` follows the same canonical
    positive decimal rules as [get_pull_request][atlawire.bitbucket.get_pull_request].
    The fixed ``/commits`` endpoint is read from ``start=0`` with ``limit=100``
    and every nonterminal page is followed through its own noncontiguous
    ``nextPageStart`` until the exact ``isLastPage`` boolean. Unlike the
    repository history view there is no implicit row cap, so every projected
    commit is returned in server order.

    No pull request metadata or count flags are sent and no additional route is
    requested. A later malformed row, transport failure, or page-cap hit raises
    without returning partial rows.
    """
    _validate_page_limit(max_pages)
    _check_row_limit(limit)
    _, url, _ = _pull_request_target(
        base_url, repo, pr_id, allow_http_loopback=allow_http_loopback
    )
    with bearer_session(token, product="bitbucket") as session:
        return _read_pages(
            session, f"{url}/commits", max_pages, project=_commit, limit=limit
        )


def list_pull_requests(
    base_url: str,
    repo: str,
    *,
    token: str,
    state: str = "OPEN",
    order: str | None = None,
    author: str | None = None,
    direction: str | None = None,
    role: str | None = None,
    participant: str | None = None,
    limit: int = _PULL_REQUEST_LIMIT_DEFAULT,
    max_pages: int = 100,
    allow_http_loopback: bool = False,
) -> list[PullRequest]:
    """List a repository's pull requests in server order, stopping at ``limit``.

    ``repo`` is ``PROJECT/slug``. ``state`` must be exactly ``OPEN``,
    ``MERGED``, ``DECLINED`` or ``ALL`` and is sent on every page; an explicit
    ``order`` must be exactly ``NEWEST`` or ``OLDEST`` and is sent only when
    given. ``direction`` must be exactly ``INCOMING`` or ``OUTGOING`` and is
    sent only when given, so otherwise the server default applies. ``author``
    must be a nonempty Bitbucket participant username: 5.10 documents no
    ``author`` parameter, but its participant filter selects by username, so
    exactly ``username.1=<author>`` and ``role.1=AUTHOR`` are sent.

    ``role`` selects pull requests where one participant holds that exact role
    (``AUTHOR``, ``REVIEWER``, or ``PARTICIPANT``). The 5.10 reference makes
    ``role.N`` optional only next to a mandatory ``username.N``, and the live
    5.10.0 server silently ignores a bare ``role.1``, so this function never
    sends one: an explicit ``participant`` fills ``username.1`` and a given
    ``role`` fills ``role.1``. With ``role`` alone the authenticated user's
    username is read from the server's ``X-AUSERNAME`` header in one bounded
    dashboard request, which the REST reference does not document. ``author``
    cannot be combined with ``role`` or ``participant``.

    Both ``author`` and ``direction`` are genuine server-side filters;
    ``participantStatus`` exists only on ``/dashboard/pull-requests``, is not
    documented for this endpoint, and is never sent here. The fixed
    ``/pull-requests`` route is paged from ``start=0`` with no more than the
    missing rows per request, following each page's exact ``nextPageStart``
    until ``limit`` rows are projected or the terminal page is reached, so an
    unused next-page hint is never required. No client-side filtering,
    reordering, metadata lookup, or link request is performed.

    Only ``id``, ``title``, ``state``, ``author``, ``from``, ``to`` and
    ``updated`` are projected; the author name comes from ``author.user.name``
    and the branch names from the respective ``displayId`` values. A later
    malformed row, transport failure, or page-cap hit raises without returning
    partial rows or printing anything.
    """
    _validate_page_limit(max_pages)
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 1000:
        raise AtlaWireError("The pull request limit must be between 1 and 1000.")
    params = _pull_request_params(state, order, author, direction)
    participant_name, participant_role = _participant_filter(author, participant, role)
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    url = f"{_repository_url(base, repo)}/pull-requests"
    with bearer_session(token, product="bitbucket") as session:
        if participant_role is not None and participant_name is None:
            participant_name = _authenticated_username(session, base)
        if participant_name is not None:
            params["username.1"] = participant_name
        if participant_role is not None:
            params["role.1"] = participant_role
        return _read_pages(
            session,
            url,
            max_pages,
            project=_pull_request,
            params=params,
            limit=limit,
        )


def list_my_pull_requests(
    base_url: str,
    *,
    token: str,
    state: str = "OPEN",
    role: str = "AUTHOR",
    participant_status: str | None = None,
    limit: int = _PULL_REQUEST_LIMIT_DEFAULT,
    max_pages: int = 100,
    allow_http_loopback: bool = False,
) -> list[MyPullRequest]:
    """List pull requests where the authenticated user takes part.

    Reads only ``/rest/api/1.0/dashboard/pull-requests`` under the base URL's
    configured context; no metadata, current-user, or repository request is
    made. ``state`` must be exactly ``OPEN``, ``MERGED``, or ``DECLINED``
    (``ALL`` is rejected before any request) and ``role`` must be exactly
    ``AUTHOR``, ``REVIEWER``, or ``PARTICIPANT``. ``participant_status`` is
    either ``None`` or a comma-separated list of up to three distinct values
    from ``UNAPPROVED``, ``NEEDS_WORK``, and ``APPROVED``; its exact spelling
    and order are sent only when given. Those filters stay fixed on every page,
    no order or closed-since option is sent, and paging stops at ``limit`` rows
    without needing an unused next-page hint.

    Only ``repo``, ``id``, ``title``, ``state``, ``author``,
    ``reviewers_inactive``, and ``created`` are projected. ``repo`` comes from
    ``toRef``'s repository rather than ``fromRef`` (which may name a fork), and
    ``reviewers_inactive`` is the deduplicated lexical order of known names
    whose ``user.active`` is literally ``False``. A later malformed row,
    transport failure, or page-cap hit raises without returning partial rows or
    printing anything.
    """
    _validate_page_limit(max_pages)
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 1000:
        raise AtlaWireError("The pull request limit must be between 1 and 1000.")
    params = _dashboard_params(state, role, participant_status)
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    url = f"{base}{_DASHBOARD_PULL_REQUESTS_PATH}"
    with bearer_session(token, product="bitbucket") as session:
        return _read_pages(
            session,
            url,
            max_pages,
            project=_my_pull_request,
            params=params,
            limit=limit,
        )


def list_branches(
    base_url: str,
    repo: str,
    *,
    token: str,
    filter_text: str | None = None,
    limit: int | None = None,
    max_pages: int = 100,
    before_page: Callable[[], None] | None = None,
    allow_http_loopback: bool = False,
) -> list[Branch]:
    """List repository branches in server order or raise without partial rows.

    ``repo`` is ``PROJECT/slug``. A nonempty ``filter_text`` is sent verbatim as
    ``filterText`` on every page request; ``None`` and the empty string omit the
    filter. Text that UTF-8 cannot encode is rejected before any request. Only
    ``displayId``, ``id``, ``latestCommit`` and ``isDefault`` are projected, and
    each page is followed through its own ``nextPageStart``. The optional
    ``before_page`` callback runs before every page request and propagates its
    exception.
    """
    _validate_page_limit(max_pages)
    _check_row_limit(limit)
    params = _branch_filter(filter_text)
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    url = _repository_url(base, repo)
    with bearer_session(token, product="bitbucket") as session:
        return _read_pages(
            session,
            f"{url}/branches",
            max_pages,
            project=_branch,
            params=params,
            limit=limit,
            before_page=before_page,
        )


def get_branch(
    base_url: str,
    repo: str,
    name: str,
    *,
    token: str,
    max_pages: int = 100,
    before_page: Callable[[], None] | None = None,
    allow_http_loopback: bool = False,
) -> Branch | None:
    """Return the branch whose display name is exactly ``name``.

    ``name`` is one literal display name: it is never trimmed, lowercased, or
    prefixed with ``refs/heads/``, because Git refs may differ only by case.
    It must be non-blank UTF-8 text without control characters and is sent
    verbatim as ``filterText`` on every page. The validated ``/branches`` route
    is traversed to exhaustion through the shared pager, and the first
    projected row whose ``displayId`` equals ``name`` byte for byte is
    returned. The optional ``before_page`` callback runs before every page
    request and propagates its exception.

    ``None`` means a complete successful traversal contained no exact match.
    A malformed later page, a non-advancing cursor, a transport failure, or
    the page cap still raises after an earlier candidate, so a partial walk is
    never reported as the absence of a branch. No default-branch, metadata, or
    link request is made.
    """
    wanted = _revision(name)
    if not wanted.strip():
        raise AtlaWireError("The branch name must be non-blank text.")
    if before_page is None:
        rows = list_branches(
            base_url,
            repo,
            token=token,
            filter_text=wanted,
            max_pages=max_pages,
            allow_http_loopback=allow_http_loopback,
        )
    else:
        rows = list_branches(
            base_url,
            repo,
            token=token,
            filter_text=wanted,
            max_pages=max_pages,
            before_page=before_page,
            allow_http_loopback=allow_http_loopback,
        )
    for row in rows:
        if row["name"] == wanted:
            return row
    return None


def list_tags(
    base_url: str,
    repo: str,
    *,
    token: str,
    filter_text: str | None = None,
    order_by: str | None = None,
    limit: int = _TAG_LIMIT_DEFAULT,
    max_pages: int = 100,
    allow_http_loopback: bool = False,
) -> list[dict[str, object]]:
    """List repository tags in server order, stopping at ``limit`` rows.

    ``repo`` is ``PROJECT/slug``. The fixed ``/tags`` route is paged from
    ``start=0``; each request asks for no more than the rows still missing and
    follows the server's opaque ``nextPageStart``, even after a short page.
    Every row must be a JSON object and is returned unchanged, so declared and
    unknown nested fields are preserved, and no response link is followed.

    A nonempty ``filter_text`` is sent verbatim as ``filterText`` and
    ``order_by`` must be exactly ``ALPHABETICAL`` or ``MODIFICATION`` when
    given. Both filters are repeated on every page; ``None`` and the empty
    filter string omit ``filterText``, and ``None`` omits ``orderBy``.

    Reaching ``limit`` stops the traversal without reading or requiring the
    final page's unused next-page hint. Exactly ``limit`` rows therefore only
    proves that the cap was reached, not that the repository has no more tags;
    completeness needs a larger limit or a traversal to the terminal page.
    Признак полноты в списке не передаётся: его сообщает
    [list_tags_with_metadata][atlawire.bitbucket.list_tags_with_metadata].
    """
    return list_tags_with_metadata(
        base_url,
        repo,
        token=token,
        filter_text=filter_text,
        order_by=order_by,
        limit=limit,
        max_pages=max_pages,
        allow_http_loopback=allow_http_loopback,
    )["tags"]


def list_tags_with_metadata(
    base_url: str,
    repo: str,
    *,
    token: str,
    filter_text: str | None = None,
    order_by: str | None = None,
    limit: int = _TAG_LIMIT_DEFAULT,
    max_pages: int = 100,
    allow_http_loopback: bool = False,
) -> TagListing:
    """Вернуть теги вместе с признаком полноты выборки.

    Вызов и пагинация совпадают с [list_tags][atlawire.bitbucket.list_tags]:
    ``/tags`` читается от ``start=0``, каждый следующий курсор берётся только
    из серверного ``nextPageStart``, а ``isLastPage`` обязан быть boolean.
    Фильтры ``filter_text``/``order_by`` повторяются на каждой странице.

    В отличие от голого списка, ``complete`` отделяет честную полную выборку
    от обрезанной лимитом: ``True`` только когда сервер отдал терминальную
    страницу и все строки поместились в ``limit``. Это позволяет агенту не
    считать ``limit`` доказательством полноты: ``complete=False`` значит, что
    тегов может быть больше.

    Любая ошибка страницы, битый курсор или превышение ``max_pages``
    поднимают [AtlaWireError][atlawire.http.AtlaWireError] без частичного
    результата; ``limit`` 1-1000 и ``max_pages`` 1-1000 проверяются до запроса.
    """
    _validate_page_limit(max_pages)
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 1000:
        raise AtlaWireError("The tag limit must be between 1 and 1000.")
    params = _tag_params(filter_text, order_by)
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    url = f"{_repository_url(base, repo)}/tags"
    with bearer_session(token, product="bitbucket") as session:
        rows, complete = _read_pages_result(
            session,
            url,
            max_pages,
            project=_tag_row,
            params=params,
            limit=limit,
        )
    return TagListing(tags=rows, limit=limit, complete=complete)


def get_tag(
    base_url: str,
    repo: str,
    name: str,
    *,
    token: str,
    allow_http_loopback: bool = False,
) -> dict[str, object]:
    """Return one tag by exact name exactly as the server sent it.

    ``repo`` is ``PROJECT/slug``. ``name`` is a slash-delimited Git tag path:
    each segment must be nonempty, must not be ``.`` or ``..``, and must not
    contain control characters, backslashes, or a literal percent escape. Safe
    segments are encoded exactly once while slashes remain separators, so the
    request cannot escape the fixed ``/tags`` route. Exactly one GET targets
    that route without query parameters; the decoded object is returned
    unchanged, and response links are never followed.
    """
    segments = _tag_segments(name)
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    url = _repository_url(base, repo)
    with bearer_session(token, product="bitbucket") as session:
        return get_json_object(
            session, f"{url}/tags/{_encoded_path(segments)}", params={}
        )


def list_commits(
    base_url: str,
    repo: str,
    *,
    token: str,
    at: str | None = None,
    path: str | None = None,
    author: str | None = None,
    limit: int = _COMMIT_LIMIT_DEFAULT,
    max_pages: int = 100,
    allow_http_loopback: bool = False,
) -> list[Commit]:
    """List repository commits newest first, stopping at ``limit`` rows.

    ``repo`` is ``PROJECT/slug``. A nonempty ``at`` is sent only as ``until``
    and a nonempty ``path`` only as ``path``; absent and empty filters are
    omitted. Bitbucket 5.10's ``/commits`` documents no author parameter, so
    ``author`` (``None`` for no selection) selects on our side after each
    fetched page is projected: only rows whose exact git ``author.name``
    equals the given name are kept, and the pager keeps following pages until
    ``limit`` matches are collected or the terminal page is reached. The
    server never applies that filter. The pager requests no more than the
    missing rows on each page, follows the server's ``nextPageStart`` even
    after a short page, and returns as soon as ``limit`` rows are projected,
    so an unused next-page hint on the final page is never required. Every
    projected row keeps the git author ``name``, the author ``emailAddress`` as
    ``email``, the optional author ``displayName`` (``None`` when the server does
    not send it) and the raw ``authorTimestamp`` milliseconds as ``timestamp``,
    all from the same response row, so no per-commit request is made. The row
    also carries the raw commit message; only the TSV view normalizes it.
    Признак полноты в списке не передаётся: его сообщает
    [list_commits_with_metadata][atlawire.bitbucket.list_commits_with_metadata].
    """
    return list_commits_with_metadata(
        base_url,
        repo,
        token=token,
        at=at,
        path=path,
        author=author,
        limit=limit,
        max_pages=max_pages,
        allow_http_loopback=allow_http_loopback,
    )["commits"]


def list_commits_with_metadata(
    base_url: str,
    repo: str,
    *,
    token: str,
    at: str | None = None,
    path: str | None = None,
    author: str | None = None,
    limit: int = _COMMIT_LIMIT_DEFAULT,
    max_pages: int = 100,
    allow_http_loopback: bool = False,
) -> CommitListing:
    """Вернуть коммиты вместе с признаком полноты выборки.

    Вызов и пагинация совпадают с [list_commits][atlawire.bitbucket.list_commits]:
    ``at`` уходит только как ``until``, ``path`` — только как ``path``;
    каждый следующий курсор берётся из серверного ``nextPageStart``, а не
    вычисляется из ``start + size``.

    Фильтра по автору серверный ``/commits`` в 5.10 не документирует: в
    описании endpoint только ``followRenames``, ``ignoreMissing``, ``merges``,
    ``path``, ``since``, ``until`` и ``withCounts``. Поэтому ``author`` —
    фильтрация на нашей стороне: каждая уже полученная страница проецируется,
    и остаются только строки с точным ``author.name`` (git-имя автора, а не
    аккаунт Bitbucket). Сервер этот фильтр не применяет. Пагинатор идёт
    дальше, пока не наберёт ``limit`` совпадений, пока не увидит терминальную
    страницу или пока не исчерпает ``max_pages``, поэтому совпадения с дальних
    страниц не теряются; ``complete=True`` означает, что вся история в
    пределах ``max_pages`` просмотрена. Для редкого автора цена — чтение
    истории, поэтому сужайте выборку ``at``/``path``.

    В отличие от голого списка, ``complete`` отделяет полную выборку от
    обрезанной лимитом: ``True`` только когда сервер отдал терминальную
    страницу и все строки поместились в ``limit``. Для репозитория с 971
    коммитом запрос с ``limit=100`` честно возвращает ``complete=False``, чтобы
    агент не считал 100 строк всей историей. ``totalCount`` в ответе 5.10
    отсутствует, поэтому состояние ограничивается этим признаком.

    Каждая строка проекции несёт ``author`` (git-имя), ``email`` из
    ``author.emailAddress``, ``displayName`` (``None``, если сервер его не
    прислал: схема 5.10 для автора коммита документирует только ``name`` и
    ``emailAddress``) и сырые миллисекунды ``authorTimestamp`` как ``timestamp``
    рядом с человекочитаемым ``date``. Всё это — поля той же строки ответа, без
    отдельных запросов на коммит.

    Любая ошибка страницы, битый курсор или превышение ``max_pages``
    поднимают [AtlaWireError][atlawire.http.AtlaWireError] без частичного
    результата; ``limit`` 1-1000 и ``max_pages`` 1-1000 проверяются до запроса.
    """
    _validate_page_limit(max_pages)
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 1000:
        raise AtlaWireError("The commit limit must be between 1 and 1000.")
    params = _commit_params(at, path)
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    url = _repository_url(base, repo)
    with bearer_session(token, product="bitbucket") as session:
        rows, complete = _read_pages_result(
            session,
            f"{url}/commits",
            max_pages,
            project=_commit if author is None else _author_matcher(author),
            params=params,
            limit=limit,
        )
    return CommitListing(commits=rows, limit=limit, complete=complete)


def get_commit(
    base_url: str,
    repo: str,
    sha: str,
    *,
    token: str,
    allow_http_loopback: bool = False,
) -> dict[str, object]:
    """Return one commit exactly as the server sent it.

    ``repo`` is ``PROJECT/slug`` and ``sha`` must be 7 to 40 ASCII hexadecimal
    characters; symbolic refs are rejected and no ``path`` filter is sent,
    because 5.10 documents that a path may return a different commit. Exactly
    one GET targets the configured repository's ``/commits/{sha}`` route with no
    query parameters, and no link carried by the response is followed.

    The object must carry an ``id`` of exactly 40 ASCII hexadecimal characters
    that equals the requested full ID or starts with the requested abbreviation,
    compared case-insensitively. A wrong, missing, or malformed ID fails with a
    static error. All other fields are returned unchanged: this is an exact
    lookup, including an abbreviated ID resolved by the server, not a claim that
    an abbreviation is unique outside the server's rules.
    """
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    requested = _commit_id(sha)
    url = f"{_repository_url(base, repo)}/commits/{requested}"
    with bearer_session(token, product="bitbucket") as session:
        value = get_json_object(session, url, params={})
    _validate_commit_response(value, requested)
    return value


def list_commit_changes(
    base_url: str,
    repo: str,
    sha: str,
    *,
    token: str,
    limit: int | None = None,
    max_pages: int = 100,
    allow_http_loopback: bool = False,
) -> list[ChangedFile]:
    """List the files changed by one commit in server order.

    ``repo`` is ``PROJECT/slug`` and ``sha`` must be 7 to 40 hexadecimal
    characters: branch and symbolic refs are rejected before any request, so no
    caller text reaches the URL path. Unlike the single-response pull request
    changes view, this endpoint is paged: the existing cursor starts at ``0``
    with ``limit=100`` and follows each page's ``nextPageStart``, failing on a
    malformed or non-advancing cursor, an HTTP error, or the page cap without
    returning partial rows.

    A page declaring ``truncated`` as ``true`` (bare boolean or the exact
    lowercase string) fails the call, any other present value is a malformed
    flag, and an omitted flag or the exact ``false``/``"false"`` values are
    accepted. This checks declared flags only: the server's documented hard cap
    may cut a page short without setting one, and this view does not claim to
    detect that case.
    """
    _validate_page_limit(max_pages)
    _check_row_limit(limit)
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    commit = _commit_id(sha)
    url = f"{_repository_url(base, repo)}/commits/{commit}/changes"
    with bearer_session(token, product="bitbucket") as session:
        return _read_pages(
            session,
            url,
            max_pages,
            project=_changed_file,
            limit=limit,
            transform=_commit_changes_page,
        )


def get_commit_diff(
    base_url: str,
    repo: str,
    sha: str,
    *,
    token: str,
    paths: Sequence[str] | None = None,
    context: int = 3,
    whitespace: str = "ignore-all",
    allow_http_loopback: bool = False,
) -> dict[str, object] | list[dict[str, object]]:
    """Return the decoded diff for one commit or for explicit relative paths.

    ``repo`` is ``PROJECT/slug`` and ``sha`` is validated as 7 to 40 hexadecimal
    characters before any request. Without paths exactly one whole-commit
    request is made and the decoded object is returned unchanged. With explicit
    paths every relative path is validated before the session is created; the
    call then makes one ``/diff/{path}`` request per path in input order and
    returns the decoded objects in the same order, even for a single path. At
    most 100 paths are accepted, and there is no implicit fallback.

    Every request sends only ``contextLines`` (an exact integer from 0 to 100),
    the validated ``whitespace`` mode and ``withComments=false``; ``autoSrcPath``,
    ``since`` and other filters are never sent. Declared truncation and
    malformed truncation-bearing collections fail the whole call, so no partial
    result is returned. Sources and links carried by a response are never
    fetched.
    """
    _diff_context(context)
    targets = _commit_diff_targets(paths)
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    commit = _commit_id(sha)
    url = f"{_repository_url(base, repo)}/commits/{commit}/diff"
    params = _diff_params(context, whitespace=whitespace)
    with bearer_session(token, product="bitbucket") as session:
        if targets is None:
            value = get_json_object(session, url, params=params)
            _validate_diff(value, subject="commit")
            return value
        return [
            _read_commit_file_diff(session, url, segments, params=params)
            for segments in targets
        ]


def get_commit_diff_text(
    base_url: str,
    repo: str,
    sha: str,
    *,
    token: str,
    paths: Sequence[str] | None = None,
    context: int = 3,
    whitespace: str = "ignore-all",
    allow_http_loopback: bool = False,
) -> str:
    """Return a terminal-safe review view of one commit diff.

    Requests, path rules and declared truncation checks are inherited from
    [get_commit_diff][atlawire.bitbucket.get_commit_diff]. The header names the
    commit request rather than a pull request, every explicit path response is
    rendered in input order under that one header, and an empty response gets an
    explicit no-textual-hunks marker. The result is a readable review view, not
    an applyable Git patch, and it is built completely before it is returned.
    """
    value = get_commit_diff(
        base_url,
        repo,
        sha,
        token=token,
        paths=paths,
        context=context,
        whitespace=whitespace,
        allow_http_loopback=allow_http_loopback,
    )
    values = [value] if isinstance(value, dict) else value
    text = _render_diff_text(
        values,
        context=context,
        subject=_DIFF_SUBJECT_COMMIT,
        whitespace=whitespace,
    )
    reject_credential_echo(text, tokens=(token,))
    return text


def get_project(
    base_url: str,
    project_key: str,
    *,
    token: str,
    raw: bool = False,
    allow_http_loopback: bool = False,
) -> ProjectDetail | dict[str, object]:
    """Вернуть один проект Bitbucket Server 5.10.

    ``project_key`` проверяется до создания сессии и кодируется как один сегмент
    пути. Ровно один GET уходит на ``/rest/api/1.0/projects/{projectKey}`` без query;
    ссылки из ответа не читаются.

    По умолчанию возвращается плоская проекция [ProjectDetail][atlawire.bitbucket.ProjectDetail]
    с полями ``key``, ``name``, ``description``, ``public`` и ``type``. Поле, которого
    нет в ответе, проецируется как ``None``; ``key`` обязателен и должен быть ключом
    проекта. ``raw=True`` возвращает декодированный объект сервера без проекции,
    поэтому сохраняются ``id``, ``links`` и любые неизвестные поля.

    Неуспешный HTTP-статус, транспортная ошибка или битая форма ответа поднимают
    [AtlaWireError][atlawire.http.AtlaWireError] с обезличенной диагностикой: ни
    URL, ни тело ответа, ни токен в неё не попадают.
    """
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    url = _project_url(base, project_key)
    with bearer_session(token, product="bitbucket") as session:
        value = get_json_object(session, url, params={})
    if raw:
        return value
    return _project_detail(value)


def get_repository(
    base_url: str,
    project_key: str,
    slug: str,
    *,
    token: str,
    raw: bool = False,
    allow_http_loopback: bool = False,
) -> RepositoryDetail | dict[str, object]:
    """Вернуть один репозиторий Bitbucket Server 5.10.

    ``project_key`` и ``slug`` проверяются до создания сессии: слэш, ``.`` и ``..``
    отклоняются, каждый сегмент кодируется ровно один раз. Ровно один GET уходит на
    ``/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}`` без query.

    По умолчанию возвращается плоская проекция
    [RepositoryDetail][atlawire.bitbucket.RepositoryDetail] с полями ``slug``, ``name``,
    ``state``, ``public`` и ``defaultBranch``. Сервер 5.10 не включает ``defaultBranch``
    в объект репозитория (см. живое наблюдение в
    [get_default_branch][atlawire.bitbucket.get_default_branch]), поэтому это поле
    обычно ``None``; отсутствующие необязательные поля тоже проецируются как ``None``.
    ``raw=True`` возвращает декодированный объект сервера без проекции, включая
    ``project``, ``links`` и неизвестные поля.
    """
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    url = _scoped_repository_url(base, project_key, slug)
    with bearer_session(token, product="bitbucket") as session:
        value = get_json_object(session, url, params={})
    if raw:
        return value
    return _repository_detail(value)


def get_default_branch(
    base_url: str,
    project_key: str,
    slug: str,
    *,
    token: str,
    raw: bool = False,
    allow_http_loopback: bool = False,
) -> BranchDetail | dict[str, object] | None:
    """Вернуть ветку по умолчанию одного репозитория Bitbucket Server 5.10.

    Ровно один GET уходит на ``/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/branches/default``
    без query. Документированный ответ 204 (пустой репозиторий без ветки по
    умолчанию) возвращается как ``None``, а не как ошибка; любой другой не-200
    статус поднимает [AtlaWireError][atlawire.http.AtlaWireError].

    По умолчанию возвращается плоская проекция
    [BranchDetail][atlawire.bitbucket.BranchDetail] с полями ``id``, ``displayId``,
    ``latestCommit`` и ``isDefault``; отсутствующее необязательное поле становится
    ``None``. ``raw=True`` возвращает декодированный объект сервера без проекции
    (например, с ``type`` и ``latestChangeset``).
    """
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    url = f"{_scoped_repository_url(base, project_key, slug)}/branches/default"
    with bearer_session(token, product="bitbucket") as session:
        value = get_json_object_allow_no_content(session, url, params={})
    if value is None:
        return None
    if raw:
        return value
    return _branch_detail(value)


def get_repository_changes(
    base_url: str,
    project_key: str,
    slug: str,
    until: str,
    *,
    token: str,
    since: str | None = None,
    limit: int | None = None,
    max_pages: int = 100,
    raw: bool = False,
    allow_http_loopback: bool = False,
) -> list[ChangedFile] | list[dict[str, object]]:
    """Перечислить изменения между двумя состояниями репозитория.

    Маршрут ``/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/changes``
    сравнивает ``until`` с ``since``; без ``since`` сервер сравнивает с первым
    родителем ``until``. ``until`` обязателен (его отсутствие — документированный
    400) и вместе с ``since`` принимает ID коммита или ref; оба значения
    проверяются до создания сессии и уходят только как query-параметры.

    ``limit`` ограничивает число строк-изменений (``None`` — без клиентского
    предела, 1-1000 иначе). Страницы читаются строго по серверным ``isLastPage``
    и ``nextPageStart``; курсор не вычисляется из ``start + size``, поэтому
    непрозрачный курсор и короткая страница обрабатываются как у остальных
    paged-функций модуля. Битый курсор, отсутствующий ``isLastPage``, ошибка,
    транспортный сбой или исчерпанный ``max_pages`` поднимают
    [AtlaWireError][atlawire.http.AtlaWireError] без частичного списка.

    Строки по умолчанию проецируются в [ChangedFile][atlawire.bitbucket.ChangedFile]
    (``path``, ``type``, ``node``): 5.10 отдаёт здесь изменённые файлы, а не refs.
    ``raw=True`` возвращает строки сервера без проекции.
    """
    _validate_page_limit(max_pages)
    params = _changes_params(until, since)
    floor = _row_limit(limit, "change")
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    url = f"{_scoped_repository_url(base, project_key, slug)}/changes"
    with bearer_session(token, product="bitbucket") as session:
        if raw:
            return _read_pages(
                session, url, max_pages, project=_dict_row, params=params, limit=floor
            )
        return _read_pages(
            session, url, max_pages, project=_changed_file, params=params, limit=floor
        )


def list_commit_comments(
    base_url: str,
    project_key: str,
    slug: str,
    commit_id: str,
    *,
    token: str,
    path: str | None = None,
    limit: int | None = None,
    max_pages: int = 100,
    raw: bool = False,
    allow_http_loopback: bool = False,
) -> list[CommitComment] | list[dict[str, object]]:
    """Перечислить комментарии одного коммита.

    ``commit_id`` — 7-40 шестнадцатеричных символов, проверяются до запроса. Путь
    ``/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/commits/{commitId}/comments``
    документирует ``path`` как необязательный фильтр, но живой сервер 5.10
    отвечает 400 «The path query parameter is required when retrieving comments.»,
    поэтому на этом сервере ``path`` фактически обязателен: заданный безопасный
    относительный путь уходит как ``path``, отсутствующий не отправляется. Кривой
    `path` отклоняется до создания сессии.

    ``limit`` ограничивает число строк (``None`` — без клиентского предела,
    1-1000 иначе); страницы читаются по ``isLastPage``/``nextPageStart``, а не по
    арифметике ``start + limit``. По умолчанию строки проецируются в
    [CommitComment][atlawire.bitbucket.CommitComment] с плоскими полями ``id``,
    ``author``, ``text``, ``createdDate``; ``raw=True`` возвращает строки сервера
    без проекции (включая вложенные ответы и неизвестные поля).
    """
    _validate_page_limit(max_pages)
    commit = _commit_id(commit_id)
    floor = _row_limit(limit, "comment")
    params: dict[str, str] = {}
    selected_path = _comment_path(path)
    if selected_path is not None:
        params["path"] = selected_path
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    url = f"{_scoped_repository_url(base, project_key, slug)}/commits/{commit}/comments"
    with bearer_session(token, product="bitbucket") as session:
        if raw:
            return _read_pages(
                session, url, max_pages, project=_dict_row, params=params, limit=floor
            )
        return _read_pages(
            session, url, max_pages, project=_commit_comment, params=params, limit=floor
        )


def get_commit_comment(
    base_url: str,
    project_key: str,
    slug: str,
    commit_id: str,
    comment_id: str | int,
    *,
    token: str,
    raw: bool = False,
    allow_http_loopback: bool = False,
) -> CommitComment | dict[str, object]:
    """Вернуть один комментарий коммита.

    ``commit_id`` (7-40 hex) и ``comment_id`` (положительный ID) проверяются до
    запроса. Ровно один GET уходит на
    ``/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/commits/{commitId}/comments/{commentId}``
    без query; ответ обязан нести тот же ``id``, иначе поднимается
    [AtlaWireError][atlawire.http.AtlaWireError] (защита от чужого ресурса).

    По умолчанию возвращается проекция [CommitComment][atlawire.bitbucket.CommitComment];
    отсутствующие необязательные ``author``/``createdDate`` — ``None``.
    ``raw=True`` возвращает декодированный объект сервера без проекции.
    """
    commit = _commit_id(commit_id)
    identifier = _comment_id(comment_id)
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    url = (
        f"{_scoped_repository_url(base, project_key, slug)}"
        f"/commits/{commit}/comments/{identifier}"
    )
    with bearer_session(token, product="bitbucket") as session:
        value = get_json_object(session, url, params={})
    returned = value.get("id")
    if (
        not isinstance(returned, int)
        or isinstance(returned, bool)
        or returned != identifier
    ):
        raise AtlaWireError("Bitbucket returned a different comment.")
    if raw:
        return value
    return _commit_comment(value)


def list_repository_participants(
    base_url: str,
    project_key: str,
    slug: str,
    *,
    token: str,
    max_pages: int = 100,
    raw: bool = False,
    allow_http_loopback: bool = False,
) -> list[ParticipantRow] | list[dict[str, object]]:
    """Перечислить участников pull request'ов репозитория.

    Страницы ``/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/participants``
    читаются до терминальной страницы по ``isLastPage``/``nextPageStart``; фильтры
    ``direction``, ``filter`` и ``role`` не отправляются. Пустой ответ — это пустой
    список, а не ошибка.

    5.10 документирует строки как пользователей (``name``, ``displayName`` и т.д.) и
    не кладёт в ответ ``role``, поэтому по умолчанию плоская проекция
    [ParticipantRow][atlawire.bitbucket.ParticipantRow] содержит ``role=None``;
    ``role`` заполняется только если сервер реально вернул его в строке (например,
    обёртку участника PR). ``raw=True`` возвращает строки сервера без проекции.
    """
    _validate_page_limit(max_pages)
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    url = f"{_scoped_repository_url(base, project_key, slug)}/participants"
    with bearer_session(token, product="bitbucket") as session:
        if raw:
            return _read_pages(session, url, max_pages, project=_dict_row)
        return _read_pages(session, url, max_pages, project=_participant_row)


def list_repository_forks(
    base_url: str,
    project_key: str,
    slug: str,
    *,
    token: str,
    max_pages: int = 100,
    raw: bool = False,
    allow_http_loopback: bool = False,
) -> list[RepositoryLink] | list[dict[str, object]]:
    """Перечислить непосредственные форки репозитория.

    ``/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/forks`` пагинируется
    по ``isLastPage``/``nextPageStart``; возвращаются только прямые форки, без
    «внуков» (так документирован маршрут). Пустой ответ — пустой список.

    Строки по умолчанию проецируются в [RepositoryLink][atlawire.bitbucket.RepositoryLink]
    (``slug``, ``project``, ``state``), где ``project`` — плоский ключ проекта
    (``PRJ`` или ``~user``), а не вложенный объект. ``raw=True`` возвращает строки
    сервера без проекции.
    """
    _validate_page_limit(max_pages)
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    url = f"{_scoped_repository_url(base, project_key, slug)}/forks"
    return _read_repository_links(url, token, max_pages, raw)


def get_related_repositories(
    base_url: str,
    project_key: str,
    slug: str,
    *,
    token: str,
    max_pages: int = 100,
    raw: bool = False,
    allow_http_loopback: bool = False,
) -> list[RepositoryLink] | list[dict[str, object]]:
    """Перечислить репозитории, связанные с данным по иерархии.

    ``/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/related`` пагинируется
    по ``isLastPage``/``nextPageStart``. Несмотря на имя, функция возвращает список
    строк, как и [list_repository_forks][atlawire.bitbucket.list_repository_forks],
    и проецирует их в тот же плоский [RepositoryLink][atlawire.bitbucket.RepositoryLink]
    (``slug``, ``project``, ``state``). ``raw=True`` возвращает строки сервера без
    проекции; пустой ответ — пустой список.
    """
    _validate_page_limit(max_pages)
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    url = f"{_scoped_repository_url(base, project_key, slug)}/related"
    return _read_repository_links(url, token, max_pages, raw)


def _read_commit_file_diff(
    session: requests.Session,
    url: str,
    segments: tuple[str, ...],
    *,
    params: Mapping[str, str | int],
) -> dict[str, object]:
    """Request and validate one explicit commit file diff."""
    value = get_json_object(session, f"{url}/{_encoded_path(segments)}", params=params)
    _validate_diff(value, subject="commit")
    return value


def _pull_request_target(
    base_url: str,
    repo: str,
    pr_id: str | int,
    *,
    allow_http_loopback: bool,
) -> tuple[str, str, int]:
    """Build the canonical pull request URL and its validated identity."""
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    identifier = _pull_request_id(pr_id)
    url = f"{_repository_url(base, repo)}/pull-requests/{identifier}"
    return base, url, identifier


def _repository_url(base: str, repo: str) -> str:
    """Build the validated repository URL under an already-normalized base."""
    project, slug = _split_repo(repo)
    return (
        f"{base}/rest/api/1.0/projects/{quote(project, safe='')}"
        f"/repos/{quote(slug, safe='')}"
    )


def _project_url(base: str, project_key: str) -> str:
    """Вернуть проверенный URL проекта под уже нормализованным base."""
    if not isinstance(project_key, str) or not _PROJECT_KEY.fullmatch(project_key):
        raise AtlaWireError("Expected a Bitbucket project key.")
    return f"{base}/rest/api/1.0/projects/{quote(project_key, safe='')}"


def _scoped_repository_url(base: str, project_key: str, slug: str) -> str:
    """Вернуть проверенный URL репозитория по отдельным project key и slug."""
    if (
        not isinstance(slug, str)
        or not _REPOSITORY_SLUG.fullmatch(slug)
        or slug in {".", ".."}
    ):
        raise AtlaWireError("Expected a Bitbucket repository slug.")
    return f"{_project_url(base, project_key)}/repos/{quote(slug, safe='')}"


def _read_repository_links(
    url: str, token: str, max_pages: int, raw: bool
) -> list[RepositoryLink] | list[dict[str, object]]:
    """Прочитать paged-список форков или связанных репозиториев."""
    with bearer_session(token, product="bitbucket") as session:
        if raw:
            return _read_pages(session, url, max_pages, project=_dict_row)
        return _read_pages(session, url, max_pages, project=_repository_link)


def _validate_page_limit(max_pages: int) -> None:
    if (
        not isinstance(max_pages, int)
        or isinstance(max_pages, bool)
        or not 1 <= max_pages <= 1000
    ):
        raise AtlaWireError("The page limit must be between 1 and 1000.")


def _repository_needle(name: str) -> str:
    """Return the preserved lowercase needle or reject it before any request."""
    if not isinstance(name, str) or not name.strip():
        raise AtlaWireError("The repository search must be non-empty text.")
    return _require_encodable(name, "repository search").lower()


def _validate_row_limit(limit: int) -> None:
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 1000:
        raise AtlaWireError("The repository limit must be between 1 and 1000.")


def _row_limit(limit: int | None, label: str) -> int | None:
    """Принять None или положительный предел строк, понятный общему pager'у."""
    if limit is None:
        return None
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 1000:
        raise AtlaWireError(f"The {label} limit must be between 1 and 1000.")
    return limit


def _find_in_projects(
    session: requests.Session,
    projects_url: str,
    needle: str,
    *,
    limit: int,
    max_pages: int,
) -> list[RepositoryMatch]:
    """Walk the project list and each repository list under one shared budget."""
    remaining = max_pages

    def take_pages() -> int:
        if remaining <= 0:
            raise PageLimitError("Bitbucket page limit reached; increase --max-pages.")
        return remaining

    def spent_page() -> None:
        nonlocal remaining
        remaining -= 1

    found: list[RepositoryMatch] = []
    projects = _read_pages(
        session, projects_url, take_pages(), project=_project, on_page=spent_page
    )
    for project in projects:
        key = _server_project_key(project["key"])
        repositories = _read_pages(
            session,
            f"{projects_url}/{quote(key, safe='')}/repos",
            take_pages(),
            project=lambda value: _matching_repository(value, needle),
            limit=limit - len(found),
            read_full_pages=True,
            on_page=spent_page,
        )
        found.extend(_repository_match(key, repository) for repository in repositories)
        if len(found) == limit:
            return found
    return found


def _matching_repository(value: object, needle: str) -> Repository | None:
    repository = _repository(value)
    return repository if _repository_matches(repository, needle) else None


def _server_project_key(value: str) -> str:
    """Validate a server-supplied project key before building any path."""
    if not _PROJECT_KEY.fullmatch(value):
        raise AtlaWireError("Invalid project key in a Bitbucket project.")
    return value


def _repository_matches(repository: Repository, needle: str) -> bool:
    """Match the needle against the slug or a non-null name, ignoring case."""
    name = repository["name"]
    return needle in repository["slug"].lower() or (
        name is not None and needle in name.lower()
    )


def _repository_match(project: str, repository: Repository) -> RepositoryMatch:
    """Project a match, rejecting values UTF-8 cannot encode."""
    return RepositoryMatch(
        project=project,
        slug=_require_encodable(repository["slug"], "repository slug"),
        name=_optional_encodable(repository["name"], "repository name"),
        state=_optional_encodable(repository["state"], "repository state"),
    )


def _branch_filter(value: str | None) -> dict[str, str] | None:
    """Return the fixed branch filter or reject it before any request.

    A string that UTF-8 cannot encode cannot become a query value; rejecting it
    here keeps the failure a sanitized [AtlaWireError][atlawire.http.AtlaWireError]
    instead of a transport preparation error. Valid Unicode and reserved
    characters pass unchanged.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        raise AtlaWireError("The branch filter must be a string.")
    if not value:
        return None
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise AtlaWireError("The branch filter must be valid UTF-8 text.") from None
    return {"filterText": value}


def _tag_params(filter_text: str | None, order_by: str | None) -> dict[str, str]:
    """Validate optional tag filters before any request.

    ``filter_text`` is sent verbatim when it is nonempty; ``None`` and the empty
    string omit it. ``order_by`` must be exactly ``ALPHABETICAL`` or
    ``MODIFICATION`` when present. Returning one mapping lets the shared pager
    repeat both filters unchanged on every page.
    """
    params: dict[str, str] = {}
    if filter_text is not None:
        if not isinstance(filter_text, str):
            raise AtlaWireError("The tag filter must be a string.")
        if filter_text:
            params["filterText"] = _require_encodable(filter_text, "tag filter")
    if order_by is not None:
        if not isinstance(order_by, str) or order_by not in _TAG_ORDERS:
            raise AtlaWireError("The tag order must be ALPHABETICAL or MODIFICATION.")
        params["orderBy"] = order_by
    return params


def _commit_params(at: str | None, path: str | None) -> dict[str, str]:
    """Build the optional ``until`` and ``path`` commit query filters."""
    params: dict[str, str] = {}
    if at is not None and at != "":
        params["until"] = _revision(at)
    if path is not None and path != "":
        if not isinstance(path, str) or _REVISION_UNSAFE.search(path):
            raise AtlaWireError("Expected a path filter without control characters.")
        params["path"] = path
    return params


def _author_matcher(author: str) -> Callable[[object], Commit | None]:
    """Отобрать коммиты по точному git-имени автора на нашей стороне.

    Сервер 5.10 не документирует фильтр по автору у ``/commits``, поэтому
    ``None`` для несовпадения возвращается только после проекции строки:
    ``_read_pages_result`` продолжает читать страницы до ``limit`` совпадений.
    """
    expected = _author_name(author)

    def keep(value: object) -> Commit | None:
        row = _commit(value)
        return row if row["author"] == expected else None

    return keep


def _author_name(value: str) -> str:
    """Проверить непустое точное имя автора до любого запроса."""
    if not isinstance(value, str) or not value or _REVISION_UNSAFE.search(value):
        raise AtlaWireError(
            "Expected a nonempty author name without control characters."
        )
    return _require_encodable(value, "author name")


def _changes_params(until: str, since: str | None) -> dict[str, str]:
    """Собрать документированные селекторы ``/changes`` до любого запроса."""
    params = {"until": _revision(until)}
    if since is not None and since != "":
        params["since"] = _revision(since)
    return params


def _commit_id(value: str) -> str:
    """Accept only a 7-40 character ASCII hexadecimal commit ID."""
    if not isinstance(value, str) or not _COMMIT_ID.fullmatch(value):
        raise AtlaWireError("Expected a commit ID as 7 to 40 hexadecimal characters.")
    return value


def _validate_commit_response(value: dict[str, object], requested: str) -> None:
    """Require a full response ID matching the requested ID or abbreviation."""
    identifier = value.get("id")
    if (
        not isinstance(identifier, str)
        or not _COMMIT_SHA1.fullmatch(identifier)
        or not identifier.lower().startswith(requested.lower())
    ):
        raise AtlaWireError("Invalid commit identity in the response.")


def _commit_diff_targets(
    paths: Sequence[str] | None,
) -> tuple[tuple[str, ...], ...] | None:
    """Validate every explicit path before I/O; empty selects the whole diff."""
    if paths is None:
        return None
    if not isinstance(paths, Sequence) or isinstance(paths, (str, bytes)):
        raise AtlaWireError("Expected commit diff paths as a sequence.")
    if not paths:
        return None
    if len(paths) > _COMMIT_DIFF_PATH_MAX:
        raise AtlaWireError("At most 100 commit diff paths are supported.")
    return tuple(_file_segments(path) for path in paths)


_DIFF_WHITESPACE = ("ignore-all", "ignore-trailing", "ignore-none")


def _diff_whitespace(value: str) -> str:
    """Accept one documented diff whitespace mode.

    Bitbucket 5.10 documents ``ignore-all``; its deployment accepts
    ``ignore-trailing`` and ``ignore-none`` as well, and the live read-only run
    confirmed all three. The value is validated before any request so a typo
    cannot silently change what a review diff contains.
    """
    if not isinstance(value, str) or value not in _DIFF_WHITESPACE:
        raise AtlaWireError(
            "The diff whitespace mode must be ignore-all, ignore-trailing, "
            "or ignore-none."
        )
    return value


def _diff_params(
    context: int, *, whitespace: str = "ignore-all"
) -> dict[str, str | int]:
    """Build the diff query shared by pull request and commit requests."""
    return {
        "contextLines": context,
        "whitespace": _diff_whitespace(whitespace),
        "withComments": "false",
    }


def _pull_request_diff_request(
    url: str,
    context: int,
    path: str | None,
    source_path: str | None,
    *,
    whitespace: str = "ignore-all",
) -> tuple[str, dict[str, str | int]]:
    """Build one PR diff route and query without issuing a request.

    ``path=None`` keeps the existing whole-diff route and parameters exactly.
    Otherwise the validated segments are encoded once, and an optional source
    path is validated as relative text before being sent verbatim as
    ``srcPath``; Requests then encodes the query value once itself.
    """
    params = _diff_params(context, whitespace=whitespace)
    if path is None:
        if source_path is not None:
            raise AtlaWireError("Expected a diff path when a source path is given.")
        return f"{url}/diff", params
    segments = _file_segments(path)
    if source_path is not None:
        _file_segments(source_path)
        params["srcPath"] = source_path
    return f"{url}/diff/{_encoded_path(segments)}", params


def _diff_context(value: int) -> int:
    """Accept an exact integer context from 0 to 100."""
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or not 0 <= value <= _DIFF_CONTEXT_MAX
    ):
        raise AtlaWireError("The diff context must be an integer from 0 to 100.")
    return value


def _split_repo(repo: str) -> tuple[str, str]:
    """Split ``PROJECT/slug`` into two safe path segments."""
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


def _comment_path(path: str | None) -> str | None:
    """Проверить необязательный путь комментария и вернуть его без изменений."""
    if path is None or path == "":
        return None
    return "/".join(_file_segments(path))


def _revision(value: str) -> str:
    """Validate a non-empty, control-free revision sent only as ``at``."""
    if not isinstance(value, str) or not value or _REVISION_UNSAFE.search(value):
        raise AtlaWireError("Expected a non-empty revision without control characters.")
    return value


def _revision_params(at: str | None) -> dict[str, str]:
    """Send a nonempty revision as ``at``; ``None`` and empty omit it."""
    if at is None or at == "":
        return {}
    return {"at": _revision(at)}


def _archive_format(value: str) -> str:
    """Return one documented archive format or reject it before any request."""
    if not isinstance(value, str) or value not in _ARCHIVE_FORMATS:
        raise AtlaWireError("The archive format must be zip, tar, tar.gz, or tgz.")
    return value


def _directory_segments(path: str) -> tuple[str, ...]:
    """Validate an optional relative directory path; empty means the root."""
    if path == "":
        return ()
    return _file_segments(path)


def _tag_segments(name: str) -> tuple[str, ...]:
    """Reuse the safe relative-path rules for a slash-delimited tag name.

    Git tag names may contain slashes, so each segment is validated and encoded
    separately while the slash stays a path separator. Traversal, empty
    segments, control characters, backslashes, and literal percent escapes are
    rejected before any request.
    """
    if not isinstance(name, str) or not name:
        raise AtlaWireError("Expected a tag name with safe path segments.")
    try:
        return _file_segments(name)
    except AtlaWireError:
        raise AtlaWireError("Expected a tag name with safe path segments.") from None


def _last_modified_suffix(path: str | None) -> str:
    """Return the validated path suffix; ``None`` and empty mean the root."""
    if path is None or path == "":
        return ""
    return "/" + _encoded_path(_file_segments(path))


def _browse_url(repository_url: str, segments: tuple[str, ...]) -> str:
    """Build the browse URL with each safe segment encoded exactly once."""
    if not segments:
        return f"{repository_url}/browse"
    return f"{repository_url}/browse/{_encoded_path(segments)}"


def _encoded_path(segments: tuple[str, ...]) -> str:
    """Join literal relative segments, encoding each exactly once."""
    return "/".join(quote(segment, safe="") for segment in segments)


def _require_encodable(value: str, label: str) -> str:
    """Reject text that UTF-8 cannot encode while keeping valid Unicode intact."""
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise AtlaWireError(f"The {label} must be valid UTF-8 text.") from None
    return value


def _optional_encodable(value: str | None, label: str) -> str | None:
    """Reject an optional text field that UTF-8 cannot encode."""
    return None if value is None else _require_encodable(value, label)


def _raw_file_url(base: str, project: str, slug: str, segments: tuple[str, ...]) -> str:
    """Build a repository raw URL with each safe segment encoded once."""
    encoded = _encoded_path(segments)
    return (
        f"{base}/rest/api/1.0/projects/{quote(project, safe='')}"
        f"/repos/{quote(slug, safe='')}/raw/{encoded}"
    )


def _read_raw_file_text(
    session: requests.Session, url: str, *, params: Mapping[str, str], token: str
) -> str:
    """Read one raw repository file as exact UTF-8 text.

    Mirrors [get_text][atlawire.http.get_text] for the request policy: one
    streamed GET with ``Accept: text/plain`` (this server refuses the raw route
    without it), no redirect, the shared 5 s connect and 30 s read timeouts,
    the 1 MiB decoded-size bound, strict UTF-8, the control-character guard, and
    the credential-echo rejection.

    Only the media-type decision differs: the raw route derives the media type
    from the stored file (``text/plain`` for ``.java``, ``text/markdown`` for
    ``.md``, and so on), so the reference client's rule is used instead of a
    ``text/plain`` whitelist -- a JSON media type is an error document and every
    other body is file text (``atlassian-python-api`` ``get_content_of_file``
    with ``not_json_response``). A binary body still fails the strict UTF-8 or
    control-character guard without returning partial text.
    """
    try:
        with session.get(
            url,
            params=params,
            headers={"Accept": "text/plain"},
            timeout=(5, 30),
            allow_redirects=False,
            stream=True,
        ) as response:
            _check_status(response.status_code, method="GET", product="bitbucket")
            _check_raw_file_media_type(response.headers.get("Content-Type"))
            payload = read_encoded_limited(
                response, limit=TEXT_LIMIT, message=TEXT_LIMIT_MESSAGE
            )
    except requests.Timeout:
        raise AtlaWireError(
            "Request timed out.", category="transport", method="GET"
        ) from None
    except requests.RequestException:
        raise AtlaWireError(
            _TRANSPORT_MESSAGE, category="transport", method="GET"
        ) from None
    text = _decode_utf8_text(payload)
    reject_credential_echo(text, tokens=(token,))
    return text


def _check_raw_file_media_type(value: str | None) -> None:
    """Reject a JSON error document and accept any other raw-file body as text.

    Bitbucket chooses the raw-file media type from the stored file, so a
    readable ``README.md`` arrives as ``text/markdown``; the earlier
    ``text/plain``-only check rejected it. The reference client treats the body
    as content unless it is a JSON document (``not_json_response``), which is the
    rule kept here.
    """
    media_type = (value or "").split(";", 1)[0].strip().lower()
    if media_type == "application/json" or media_type.endswith("+json"):
        raise AtlaWireError("Expected a text response, not JSON.", category="upstream")


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


def _comment_id(value: str | int) -> int:
    """Вернуть положительный ID комментария или отклонить его до запроса."""
    invalid = "Expected a comment ID as a positive integer."
    if isinstance(value, bool):
        raise AtlaWireError(invalid)
    if isinstance(value, int):
        identifier = value
    elif isinstance(value, str):
        if not re.fullmatch(r"[1-9][0-9]{0,18}", value):
            raise AtlaWireError(invalid)
        identifier = int(value)
    else:
        raise AtlaWireError(invalid)
    if not 1 <= identifier <= _PULL_REQUEST_ID_MAX:
        raise AtlaWireError(invalid)
    return identifier


def _pull_request_params(
    state: str, order: str | None, author: str | None, direction: str | None
) -> dict[str, str]:
    """Validate the fixed server-side filters before any request is made."""
    if not isinstance(state, str) or state not in _PULL_REQUEST_STATES:
        raise AtlaWireError(
            "The pull request state must be OPEN, MERGED, DECLINED, or ALL."
        )
    if order is not None and (
        not isinstance(order, str) or order not in _PULL_REQUEST_ORDERS
    ):
        raise AtlaWireError("The pull request order must be NEWEST or OLDEST.")
    params = {"state": state}
    if order is not None:
        params["order"] = order
    if author is not None:
        # 5.10 participant filter: username.N is mandatory, role.N optional.
        params["username.1"] = _author_name(author)
        params["role.1"] = "AUTHOR"
    if direction is not None:
        if not isinstance(direction, str) or direction not in _PULL_REQUEST_DIRECTIONS:
            raise AtlaWireError(
                "The pull request direction must be INCOMING or OUTGOING."
            )
        params["direction"] = direction
    return params


def _participant_filter(
    author: str | None, participant: str | None, role: str | None
) -> tuple[str | None, str | None]:
    """Проверить документированный фильтр участников до любого запроса.

    Справочник 5.10 описывает фильтр как обязательный ``username.N`` плюс
    необязательный ``role.N``; отдельный ``role.1`` фильтром не является и
    живой сервер 5.10.0 его молча игнорирует. Поэтому наружу не уходит
    ``role.1`` без ``username.1``. Пустой ``participant`` означает, что имя
    аутентифицированного пользователя ещё нужно разрешить через заголовок
    ``X-AUSERNAME``. ``author`` сохраняет исторический смысл (``username.1``
    с ``role.1=AUTHOR``) и не смешивается с новой парой.
    """
    if role is not None and (
        not isinstance(role, str) or role not in _PULL_REQUEST_ROLES
    ):
        raise AtlaWireError(
            "The pull request role must be AUTHOR, REVIEWER, or PARTICIPANT."
        )
    if author is not None and (participant is not None or role is not None):
        raise AtlaWireError("Use author or the role/participant filter, not both.")
    if participant is not None:
        return _author_name(participant), role
    return None, role


def _authenticated_username(session: requests.Session, base: str) -> str:
    """Узнать имя аутентифицированного пользователя одним bounded-чтением.

    Справочник 5.10 не публикует маршрут текущего пользователя, но живой
    сервер возвращает его в заголовке ``X-AUSERNAME`` любого успешного
    авторизованного ответа. Запрашивается одна страница dashboard с
    ``limit=1``; тело не читается, проверяется только заголовок. Отсутствие,
    пустое значение или control-символы дают явную ошибку с подсказкой
    передать ``participant``; имя никогда не печатается и уходит только в
    query как ``username.1``.
    """
    try:
        with session.get(
            f"{base}{_DASHBOARD_PULL_REQUESTS_PATH}",
            params={"state": "OPEN", "limit": 1},
            timeout=(5, 30),
            allow_redirects=False,
            stream=True,
        ) as response:
            _check_status(response.status_code, method="GET", product="bitbucket")
            value = response.headers.get("X-AUSERNAME")
    except requests.Timeout:
        raise AtlaWireError(
            "Request timed out.", category="transport", method="GET"
        ) from None
    except requests.RequestException:
        raise AtlaWireError(
            _TRANSPORT_MESSAGE, category="transport", method="GET"
        ) from None
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or _REVISION_UNSAFE.search(value)
    ):
        raise AtlaWireError(
            "Bitbucket did not report the authenticated username; "
            "pass participant explicitly."
        )
    return _require_encodable(value, "username")


def _dashboard_params(
    state: str, role: str, participant_status: str | None
) -> dict[str, str]:
    """Validate the fixed dashboard filters before any request is made."""
    if not isinstance(state, str) or state not in _DASHBOARD_STATES:
        raise AtlaWireError("The pull request state must be OPEN, MERGED, or DECLINED.")
    if not isinstance(role, str) or role not in _DASHBOARD_ROLES:
        raise AtlaWireError(
            "The pull request role must be AUTHOR, REVIEWER, or PARTICIPANT."
        )
    params = {"state": state, "role": role}
    if participant_status is not None:
        params["participantStatus"] = _participant_status(participant_status)
    return params


def _participant_status(value: str) -> str:
    """Validate up to three distinct statuses, preserving the given order."""
    invalid = (
        "The participant status must be a comma-separated list of at most "
        "three distinct UNAPPROVED, NEEDS_WORK, or APPROVED values."
    )
    if not isinstance(value, str) or not value:
        raise AtlaWireError(invalid)
    statuses = value.split(",")
    if (
        len(statuses) > _DASHBOARD_PARTICIPANT_STATUS_MAX
        or len(set(statuses)) != len(statuses)
        or any(status not in _DASHBOARD_PARTICIPANT_STATUSES for status in statuses)
    ):
        raise AtlaWireError(invalid)
    return _require_encodable(value, "participant status")


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


def _pull_request_files(page: dict[str, object]) -> list[ChangedFile]:
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
    return [_changed_file(value) for value in values]


def _fallback_changes(
    page: dict[str, object],
) -> list[_PullRequestFallbackChange]:
    """Validate the fallback changes page and its rename source metadata."""
    rows = _pull_request_files(page)
    values = page.get("values")
    if not isinstance(values, list):
        raise AtlaWireError("Expected a Bitbucket values array.")
    if not values:
        raise AtlaWireError(
            "A truncated pull request diff cannot be recovered from "
            "an empty changes page."
        )
    changes: list[_PullRequestFallbackChange] = []
    seen: set[str] = set()
    for value, row in zip(values, rows, strict=True):
        change = _fallback_change(value, row)
        if change["path"] in seen:
            raise AtlaWireError("Duplicate path in Bitbucket pull request changes.")
        seen.add(change["path"])
        changes.append(change)
    return changes


def _retained_diff_size(value: dict[str, object]) -> int:
    """Return one encoded-JSON size proxy for a retained file diff."""
    return len(json.dumps(value, separators=(",", ":")))


def _fallback_change(value: object, row: ChangedFile) -> _PullRequestFallbackChange:
    """Return one validated fallback path and its optional source path."""
    if not isinstance(value, dict):
        raise AtlaWireError("Expected a Bitbucket change object.")
    _file_segments(row["path"])
    source = value.get("srcPath")
    if source is None:
        if row["type"] in _SOURCE_PATH_CHANGE_TYPES:
            raise AtlaWireError(
                "A copied, moved, or renamed Bitbucket change requires a source path."
            )
        return _PullRequestFallbackChange(path=row["path"], source_path=None)
    source_path = _require_encodable(_change_path(source), "change source path")
    _file_segments(source_path)
    return _PullRequestFallbackChange(path=row["path"], source_path=source_path)


def _changed_file(value: object) -> ChangedFile:
    """Project one change, rejecting text that UTF-8 cannot encode."""
    if not isinstance(value, dict):
        raise AtlaWireError("Expected a Bitbucket change object.")
    path = _require_encodable(_change_path(value.get("path")), "change path")
    change_type = value.get("type")
    node = value.get("nodeType")
    if (change_type is not None and not isinstance(change_type, str)) or (
        node is not None and not isinstance(node, str)
    ):
        raise AtlaWireError("Invalid fields in a Bitbucket change.")
    return ChangedFile(
        path=path,
        type=_optional_encodable(change_type, "change type"),
        node=_optional_encodable(node, "change node"),
    )


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


def _check_row_limit(value: int | None) -> None:
    """Accept ``None`` or a positive row cap; reject a bool or a non-positive one."""
    if value is None:
        return
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise AtlaWireError("The row limit must be a positive integer.")


def _repository_file_path(value: object) -> str:
    """Project one ``/files`` value, accepting the legacy object wrapper.

    Server 5.10 documents nonempty strings. A legacy object may carry the path
    under ``path`` or expose it at the top level through the shared path
    reader; every consumed representation must still yield a nonempty,
    UTF-8-encodable path.
    """
    raw = value["path"] if isinstance(value, dict) and "path" in value else value
    return _require_encodable(_change_path(raw), "file path")


def _directory_entry(value: object) -> DirectoryEntry:
    """Project one ``children.values`` row without reconstructing its path."""
    if not isinstance(value, dict):
        raise AtlaWireError("Expected a Bitbucket child object.")
    invalid = "Invalid fields in a Bitbucket child."
    path = _require_encodable(_change_path(value.get("path")), "child path")
    kind = value.get("type")
    if kind is not None:
        if not isinstance(kind, str):
            raise AtlaWireError(invalid)
        _require_encodable(kind, "child type")
    size = value.get("size")
    if size is not None and (
        not isinstance(size, int) or isinstance(size, bool) or size < 0
    ):
        raise AtlaWireError(invalid)
    return DirectoryEntry(path=path, type=kind, size=size)


def _children_envelope(page: dict[str, object]) -> dict[str, object]:
    """Return the nested browse children page, rejecting file ``lines`` pages."""
    children = page.get("children")
    if not isinstance(children, dict):
        raise AtlaWireError("Expected a Bitbucket children page.")
    return children


def _validate_diff(value: dict[str, object], *, subject: str) -> None:
    """Reject malformed shapes/flags, then declared truncation.

    Only the documented envelope, file, hunk, segment and line nodes are
    inspected; unknown metadata is left untouched and is not searched for
    flags. All documented shapes and flags are validated before a declared true
    flag is reported, so a malformed sibling always takes precedence over
    truncation. ``subject`` only names the request in diagnostics.
    """
    truncated = _diff_truncation_flag(value)
    diffs = value.get("diffs")
    if not isinstance(diffs, list):
        raise AtlaWireError("Expected a Bitbucket diffs array.")
    for diff in diffs:
        if not isinstance(diff, dict):
            raise AtlaWireError("Expected a Bitbucket diff object.")
        truncated = _diff_truncation_flag(diff) or truncated
        if "hunks" not in diff:
            continue
        hunks = diff["hunks"]
        if not isinstance(hunks, list):
            raise AtlaWireError("Invalid hunks in a Bitbucket diff.")
        for hunk in hunks:
            truncated = _check_diff_hunk(hunk) or truncated
    if truncated:
        raise DeclaredTruncationError(f"Bitbucket reported a truncated {subject} diff.")


def _check_diff_hunk(hunk: object) -> bool:
    """Validate one file hunk and return whether any node declares truncation."""
    if not isinstance(hunk, dict):
        raise AtlaWireError("Expected a Bitbucket diff hunk object.")
    truncated = _diff_truncation_flag(hunk)
    if "segments" not in hunk:
        return truncated
    segments = hunk["segments"]
    if not isinstance(segments, list):
        raise AtlaWireError("Invalid segments in a Bitbucket diff hunk.")
    for segment in segments:
        truncated = _check_diff_segment(segment) or truncated
    return truncated


def _check_diff_segment(segment: object) -> bool:
    """Validate one hunk segment and return whether it or a line is truncated."""
    if not isinstance(segment, dict):
        raise AtlaWireError("Expected a Bitbucket diff segment object.")
    truncated = _diff_truncation_flag(segment)
    if "lines" not in segment:
        return truncated
    lines = segment["lines"]
    if not isinstance(lines, list):
        raise AtlaWireError("Invalid lines in a Bitbucket diff segment.")
    for line in lines:
        if not isinstance(line, dict):
            raise AtlaWireError("Expected a Bitbucket diff line object.")
        truncated = _diff_truncation_flag(line) or truncated
    return truncated


def _diff_truncation_flag(value: dict[str, object]) -> bool:
    """Return whether a node declares truncation; malformed values raise.

    Server 5.10 emits both bare booleans and the lowercase strings ``"true"``
    and ``"false"`` across the envelope levels, so those exact strings are
    accepted alongside the booleans. Truthiness is deliberately not used:
    ``"false"`` must never be mistaken for a truncation report.
    """
    if "truncated" not in value:
        return False
    flag = value["truncated"]
    if flag is True or flag == "true":
        return True
    if flag is False or flag == "false":
        return False
    raise AtlaWireError("Invalid Bitbucket diff truncation flag.")


def _check_changes_truncation(page: dict[str, object]) -> None:
    """Reject a declared true changes-page flag; malformed values also fail."""
    if "truncated" not in page:
        return
    flag = page["truncated"]
    if flag is True or flag == "true":
        raise AtlaWireError("Bitbucket reported truncated commit changes.")
    if flag is False or flag == "false":
        return
    raise AtlaWireError("Invalid Bitbucket changes truncation flag.")


def _commit_changes_page(page: dict[str, object]) -> dict[str, object]:
    """Validate a commit changes page and return it unchanged."""
    _check_changes_truncation(page)
    return page


def _render_diff_text(
    values: Sequence[dict[str, object]],
    *,
    context: int,
    subject: str,
    whitespace: str = "ignore-all",
) -> str:
    """Build the full review view without I/O or partial output.

    The view is deliberately not an applyable Git patch. Declared numeric ranges
    are printed exactly as integers, including zero, and are never derived from
    per-line positions. Hunk and segment counts are never assumed to agree.
    Each response without file diffs gets an explicit marker rather than a claim
    that nothing changed.
    """
    header = _DIFF_REVIEW_HEADER.format(
        subject=subject, context=context, whitespace=whitespace
    )
    lines = [header, ""]
    for value in values:
        diffs = value.get("diffs")
        if not isinstance(diffs, list):
            raise AtlaWireError("Expected a Bitbucket diffs array.")
        if not diffs:
            lines.append(_DIFF_NO_HUNKS)
            continue
        for diff in diffs:
            lines.extend(_diff_text_file(diff))
    return "\n".join(lines) + "\n"


def _render_pull_request_diff_text(
    value: dict[str, object], *, context: int, whitespace: str = "ignore-all"
) -> str:
    """Render one pull request diff review under the PR label."""
    return _render_diff_text(
        [value],
        context=context,
        subject=_DIFF_SUBJECT_PULL_REQUEST,
        whitespace=whitespace,
    )


def _render_pull_request_diffs_text(
    values: Sequence[dict[str, object]], *, context: int, whitespace: str
) -> str:
    """Render an ordered batch of per-file pull request diffs under one header."""
    return _render_diff_text(
        list(values),
        context=context,
        subject=_DIFF_SUBJECT_PULL_REQUEST,
        whitespace=whitespace,
    )


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
    params: Mapping[str, str] | None = None,
    limit: int | None = None,
    read_full_pages: bool = False,
    transform: Callable[[dict[str, object]], dict[str, object]] | None = None,
    on_page: Callable[[], None] | None = None,
    before_page: Callable[[], None] | None = None,
) -> list[RowT]:
    """Прочитать страницы курсора и вернуть только спроецированные строки.

    Тонкая обёртка над [_read_pages_result]: признак полноты не нужен
    большинству вызывающих, которые либо требуют всю коллекцию, либо падают.
    """
    rows, _ = _read_pages_result(
        session,
        url,
        max_pages,
        project=project,
        params=params,
        limit=limit,
        read_full_pages=read_full_pages,
        transform=transform,
        on_page=on_page,
        before_page=before_page,
    )
    return rows


def _read_pages_result[RowT](
    session: requests.Session,
    url: str,
    max_pages: int,
    *,
    project: Callable[[object], RowT | None],
    params: Mapping[str, str] | None = None,
    limit: int | None = None,
    read_full_pages: bool = False,
    transform: Callable[[dict[str, object]], dict[str, object]] | None = None,
    on_page: Callable[[], None] | None = None,
    before_page: Callable[[], None] | None = None,
) -> tuple[list[RowT], bool]:
    """Прочитать страницы курсора и сообщить, полон ли результат.

    ``params`` — фиксированные фильтры, повторяемые в каждом запросе;
    ``start`` и ``limit`` выставляет сама функция. Каждая страница обязана
    нести точный boolean ``isLastPage``; при строковом ``limit`` в запрос
    уходит не больше недостающих строк, а страница шире запроса отклоняется.
    Проектор с фильтрацией может включить ``read_full_pages``, чтобы просить
    страницы обычного размера, даже когда нужна одна строка. Каждая полученная
    страница валидируется, а при достижении лимита строк вызов возвращается без
    неиспользованной подсказки следующей страницы. ``transform`` заменяет
    страницу до чтения курсора и строк; ``on_page`` наблюдает завершённые
    запросы; ``before_page`` выполняется перед каждым запросом, включая первый,
    и пробрасывает своё исключение, но не отменяет уже летящий запрос.

    Второй элемент результата — признак полноты: ``True`` только когда сервер
    отдал терминальную страницу (``isLastPage=True``) и ни одна строка не была
    отброшена лимитом. ``False`` значит, что строк может быть больше, и
    вызывающий не имеет права считать выборку полной. Битый курсор, отсутствие
    ``isLastPage``, ошибка HTTP или страничный предел поднимают
    [AtlaWireError][atlawire.http.AtlaWireError] без частичного результата.

    Присутствующий эхо-``start`` обязан равняться курсору этого запроса, а
    присутствующий эхо-``size`` — числу значений; отсутствующее эхо не
    требуется. Оба проверяются на каждой прочитанной странице, включая
    терминальную, до проекции строк. Следующий курсор всегда берётся только из
    серверного ``nextPageStart``, никогда из арифметики над запрошенным start
    или эхом размера страницы.
    """
    extras = {} if params is None else dict(params)
    start = 0
    rows: list[RowT] = []
    for _ in range(max_pages):
        if before_page is not None:
            before_page()
        remaining = None if limit is None or read_full_pages else limit - len(rows)
        size = _PAGE_SIZE if remaining is None else min(_PAGE_SIZE, remaining)
        page = get_json_object(
            session, url, params={**extras, "start": start, "limit": size}
        )
        if on_page is not None:
            on_page()
        if transform is not None:
            page = transform(page)
        values = page.get("values")
        if not isinstance(values, list):
            raise AtlaWireError("Expected a Bitbucket values array.")
        _check_page_echo(page, start=start, rows=len(values))
        if remaining is not None and len(values) > size:
            raise AtlaWireError("Bitbucket returned more rows than requested.")
        last = page.get("isLastPage")
        if not isinstance(last, bool):
            raise AtlaWireError("Expected a Bitbucket isLastPage boolean.")
        for value in values:
            row = project(value)
            if row is not None:
                rows.append(row)
        if limit is not None and len(rows) >= limit:
            capped = rows[:limit] if len(rows) > limit else rows
            return capped, last and len(rows) == limit
        if last:
            return rows, True
        start = _next_page_start(page, start)
    raise PageLimitError("Bitbucket page limit reached; increase --max-pages.")


def _check_page_echo(page: dict[str, object], *, start: int, rows: int) -> None:
    """Validate optional echoed cursor metadata before the page is consumed.

    Server 5.10 responses may omit ``start`` and ``size``; a present value must
    describe the page just requested: ``start`` equals this request's own cursor
    (never a value derived from the previous page) and ``size`` equals the
    number of values. Booleans are rejected explicitly because ``bool`` is an
    ``int`` subclass.
    """
    if "start" in page:
        echoed = page["start"]
        if not isinstance(echoed, int) or isinstance(echoed, bool) or echoed != start:
            raise AtlaWireError("Invalid Bitbucket page start.")
    if "size" in page:
        echoed = page["size"]
        if not isinstance(echoed, int) or isinstance(echoed, bool) or echoed != rows:
            raise AtlaWireError("Invalid Bitbucket page size.")


def _next_page_start(page: dict[str, object], start: int) -> int:
    """Return an advancing cursor, rejecting a missing or malformed one."""
    next_start = page.get("nextPageStart")
    if (
        not isinstance(next_start, int)
        or isinstance(next_start, bool)
        or next_start <= start
    ):
        raise AtlaWireError("Invalid or non-advancing Bitbucket nextPageStart.")
    return next_start


def _tag_row(value: object) -> dict[str, object]:
    """Require one tag row to be an object and return it without projection."""
    if not isinstance(value, dict):
        raise AtlaWireError("Expected a Bitbucket tag object.")
    return value


def _dict_row(value: object) -> dict[str, object]:
    """Вернуть строку ответа без проекции, требуя JSON-объект."""
    if not isinstance(value, dict):
        raise AtlaWireError("Expected a JSON object.")
    return value


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


def _project_detail(value: object) -> ProjectDetail:
    """Спроецировать проект в плоскую строку, отсутствующее поле — None."""
    if not isinstance(value, dict):
        raise AtlaWireError("Expected a Bitbucket project object.")
    key = value.get("key")
    name = value.get("name")
    description = value.get("description")
    public = value.get("public")
    kind = value.get("type")
    if not isinstance(key, str) or not _PROJECT_KEY.fullmatch(key):
        raise AtlaWireError("Invalid fields in a Bitbucket project.")
    if (
        (name is not None and not isinstance(name, str))
        or (description is not None and not isinstance(description, str))
        or (public is not None and not isinstance(public, bool))
        or (kind is not None and not isinstance(kind, str))
    ):
        raise AtlaWireError("Invalid fields in a Bitbucket project.")
    return ProjectDetail(
        key=_require_encodable(key, "project key"),
        name=_optional_encodable(name, "project name"),
        description=_optional_encodable(description, "project description"),
        public=public,
        type=_optional_encodable(kind, "project type"),
    )


def _repository_detail(value: object) -> RepositoryDetail:
    """Спроецировать репозиторий; 5.10 не отдаёт defaultBranch — тогда None."""
    if not isinstance(value, dict):
        raise AtlaWireError("Expected a Bitbucket repository object.")
    slug = value.get("slug")
    name = value.get("name")
    state = value.get("state")
    public = value.get("public")
    default_branch = value.get("defaultBranch")
    if not isinstance(slug, str) or not slug:
        raise AtlaWireError("Invalid fields in a Bitbucket repository.")
    if (
        (name is not None and not isinstance(name, str))
        or (state is not None and not isinstance(state, str))
        or (public is not None and not isinstance(public, bool))
        or (default_branch is not None and not isinstance(default_branch, str))
    ):
        raise AtlaWireError("Invalid fields in a Bitbucket repository.")
    return RepositoryDetail(
        slug=_require_encodable(slug, "repository slug"),
        name=_optional_encodable(name, "repository name"),
        state=_optional_encodable(state, "repository state"),
        public=public,
        defaultBranch=_optional_encodable(default_branch, "default branch"),
    )


def _branch_detail(value: object) -> BranchDetail:
    """Спроецировать ветку по умолчанию в плоскую строку."""
    if not isinstance(value, dict):
        raise AtlaWireError("Expected a Bitbucket branch object.")
    identifier = value.get("id")
    display = value.get("displayId")
    commit = value.get("latestCommit")
    default = value.get("isDefault")
    if not isinstance(identifier, str) or not identifier:
        raise AtlaWireError("Invalid fields in a Bitbucket branch.")
    if (
        (display is not None and not isinstance(display, str))
        or (commit is not None and not isinstance(commit, str))
        or (default is not None and not isinstance(default, bool))
    ):
        raise AtlaWireError("Invalid fields in a Bitbucket branch.")
    return BranchDetail(
        id=_require_encodable(identifier, "branch ID"),
        displayId=_optional_encodable(display, "branch display name"),
        latestCommit=_optional_encodable(commit, "branch commit"),
        isDefault=default,
    )


def _commit_comment(value: object) -> CommitComment:
    """Спроецировать комментарий коммита в плоскую строку."""
    if not isinstance(value, dict):
        raise AtlaWireError("Expected a Bitbucket comment object.")
    identifier = value.get("id")
    text = value.get("text")
    if (
        not isinstance(identifier, int)
        or isinstance(identifier, bool)
        or identifier <= 0
    ):
        raise AtlaWireError("Invalid id in a Bitbucket comment.")
    if text is None:
        text = ""
    elif not isinstance(text, str):
        raise AtlaWireError("Invalid text in a Bitbucket comment.")
    return CommitComment(
        id=identifier,
        author=_optional_encodable(
            _comment_author(value.get("author")), "comment author"
        ),
        text=_require_encodable(text, "comment text"),
        createdDate=_comment_created(value),
    )


def _participant_row(value: object) -> ParticipantRow:
    """Спроецировать участника; 5.10 отдаёт пользователя без role — тогда None."""
    if not isinstance(value, dict):
        raise AtlaWireError("Expected a Bitbucket participant object.")
    user = value.get("user")
    person = value if user is None else user
    if not isinstance(person, dict):
        raise AtlaWireError("Invalid fields in a Bitbucket participant.")
    name = person.get("name")
    display_name = person.get("displayName")
    role = value.get("role")
    if (
        (name is not None and not isinstance(name, str))
        or (display_name is not None and not isinstance(display_name, str))
        or (role is not None and not isinstance(role, str))
    ):
        raise AtlaWireError("Invalid fields in a Bitbucket participant.")
    return ParticipantRow(
        name=_optional_encodable(name, "participant name"),
        displayName=_optional_encodable(display_name, "participant display name"),
        role=_optional_encodable(role, "participant role"),
    )


def _repository_link(value: object) -> RepositoryLink:
    """Спроецировать форк или связанный репозиторий в плоскую строку."""
    if not isinstance(value, dict):
        raise AtlaWireError("Expected a Bitbucket repository object.")
    slug = value.get("slug")
    project = value.get("project")
    state = value.get("state")
    key: object = None
    if project is not None:
        if not isinstance(project, dict):
            raise AtlaWireError("Invalid fields in a Bitbucket repository.")
        key = project.get("key")
        if not isinstance(key, str) or not _PROJECT_KEY.fullmatch(key):
            raise AtlaWireError("Invalid fields in a Bitbucket repository.")
    if not isinstance(slug, str) or not slug:
        raise AtlaWireError("Invalid fields in a Bitbucket repository.")
    if state is not None and not isinstance(state, str):
        raise AtlaWireError("Invalid fields in a Bitbucket repository.")
    return RepositoryLink(
        slug=_require_encodable(slug, "repository slug"),
        project=_optional_encodable(key, "repository project"),
        state=_optional_encodable(state, "repository state"),
    )


def _pull_request(value: object) -> PullRequest:
    """Project one pull request row without links, email addresses, or raw payloads."""
    if not isinstance(value, dict):
        raise AtlaWireError("Expected a Bitbucket pull request object.")
    identifier, title, state = _pull_request_identity(value)
    updated = value.get("updatedDate")
    if updated is not None and (
        not isinstance(updated, int) or isinstance(updated, bool) or updated < 0
    ):
        raise AtlaWireError("Invalid fields in a Bitbucket pull request.")
    row: PullRequest = {
        "id": identifier,
        "title": _require_encodable(title, "pull request title"),
        "state": _require_encodable(state, "pull request state"),
        "author": _optional_encodable(
            _pull_request_author(value.get("author")), "pull request author"
        ),
        "from": _optional_encodable(
            _pull_request_ref(value.get("fromRef")), "pull request source branch"
        ),
        "to": _optional_encodable(
            _pull_request_ref(value.get("toRef")), "pull request target branch"
        ),
        "updated": updated,
    }
    return row


def _pull_request_identity(value: dict[str, object]) -> tuple[int, str, str]:
    """Require the identity fields shared by both pull request projections."""
    identifier = value.get("id")
    title = value.get("title")
    state = value.get("state")
    if (
        not isinstance(identifier, int)
        or isinstance(identifier, bool)
        or not 1 <= identifier <= _PULL_REQUEST_ID_MAX
        or not isinstance(title, str)
        or not title
        or not isinstance(state, str)
        or not state
    ):
        raise AtlaWireError("Invalid fields in a Bitbucket pull request.")
    return identifier, title, state


def _my_pull_request(value: object) -> MyPullRequest:
    """Project one dashboard row without links, email addresses, or raw payloads."""
    if not isinstance(value, dict):
        raise AtlaWireError("Expected a Bitbucket dashboard pull request object.")
    identifier, title, state = _pull_request_identity(value)
    created = value.get("createdDate")
    if created is not None and (
        not isinstance(created, int) or isinstance(created, bool) or created < 0
    ):
        raise AtlaWireError("Invalid fields in a Bitbucket dashboard pull request.")
    row: MyPullRequest = {
        "repo": _dashboard_repo(value.get("toRef")),
        "id": identifier,
        "title": _require_encodable(title, "pull request title"),
        "state": _require_encodable(state, "pull request state"),
        "author": _optional_encodable(
            _pull_request_author(value.get("author")), "pull request author"
        ),
        "reviewers_inactive": _inactive_reviewers(value),
        "created": created,
    }
    return row


def _dashboard_repo(value: object) -> str:
    """Return the target repository as ``PROJECT/slug``, never following links."""
    invalid = "Invalid repository in a Bitbucket dashboard pull request."
    if not isinstance(value, dict):
        raise AtlaWireError(invalid)
    repository = value.get("repository")
    if not isinstance(repository, dict):
        raise AtlaWireError(invalid)
    project = repository.get("project")
    if not isinstance(project, dict):
        raise AtlaWireError(invalid)
    key = project.get("key")
    slug = repository.get("slug")
    if not isinstance(key, str) or not _PROJECT_KEY.fullmatch(key):
        raise AtlaWireError(invalid)
    if (
        not isinstance(slug, str)
        or not _REPOSITORY_SLUG.fullmatch(slug)
        or slug in {".", ".."}
    ):
        raise AtlaWireError(invalid)
    return f"{key}/{slug}"


def _active_reviewers(value: dict[str, object]) -> list[str]:
    """Collect known reviewer names whose ``user.active`` is not literally false.

    A missing or null ``active`` says nothing, so that person counts as active;
    only an explicit ``false`` excludes a name. Names are deduplicated and
    sorted for a stable report.
    """
    invalid = "Invalid reviewers in a Bitbucket pull request."
    names: set[str] = set()
    reviewers = value.get("reviewers")
    if reviewers is None:
        return []
    if not isinstance(reviewers, list):
        raise AtlaWireError(invalid)
    for person in reviewers:
        if not isinstance(person, dict):
            raise AtlaWireError(invalid)
        user = person.get("user")
        if user is None:
            continue
        if not isinstance(user, dict):
            raise AtlaWireError(invalid)
        active = user.get("active")
        if active is not None and not isinstance(active, bool):
            raise AtlaWireError(invalid)
        name = user.get("name")
        if name is not None and not isinstance(name, str):
            raise AtlaWireError(invalid)
        if active is not False and name:
            names.add(_require_encodable(name, "reviewer name"))
    return sorted(names)


def _inactive_reviewers(value: dict[str, object]) -> list[str]:
    """Collect known names whose ``user.active`` is literally false, deduplicated.

    Missing or null people arrays are empty; a missing or null ``active`` says
    nothing about a person's activity and never counts as inactive.
    """
    invalid = "Invalid reviewers in a Bitbucket dashboard pull request."
    names: set[str] = set()
    for field in ("reviewers", "participants"):
        people = value.get(field)
        if people is None:
            continue
        if not isinstance(people, list):
            raise AtlaWireError(invalid)
        for person in people:
            if not isinstance(person, dict):
                raise AtlaWireError(invalid)
            user = person.get("user")
            if user is None:
                continue
            if not isinstance(user, dict):
                raise AtlaWireError(invalid)
            active = user.get("active")
            if active is not None and not isinstance(active, bool):
                raise AtlaWireError(invalid)
            name = user.get("name")
            if name is not None and not isinstance(name, str):
                raise AtlaWireError(invalid)
            if active is False and name:
                names.add(_require_encodable(name, "inactive reviewer name"))
    return sorted(names)


def _pull_request_author(value: object) -> str | None:
    """Return ``author.user.name`` when every present wrapper is well formed."""
    if value is None:
        return None
    if not isinstance(value, dict):
        raise AtlaWireError("Invalid fields in a Bitbucket pull request.")
    user = value.get("user")
    if user is None:
        return None
    if not isinstance(user, dict):
        raise AtlaWireError("Invalid fields in a Bitbucket pull request.")
    name = user.get("name")
    if name is not None and not isinstance(name, str):
        raise AtlaWireError("Invalid fields in a Bitbucket pull request.")
    return name


def _pull_request_ref(value: object) -> str | None:
    """Return a ref's ``displayId`` when present, rejecting malformed wrappers."""
    if value is None:
        return None
    if not isinstance(value, dict):
        raise AtlaWireError("Invalid fields in a Bitbucket pull request.")
    display = value.get("displayId")
    if display is not None and not isinstance(display, str):
        raise AtlaWireError("Invalid fields in a Bitbucket pull request.")
    return display


def _branch(value: object) -> Branch:
    """Project one branch, requiring its name and full ref identity."""
    if not isinstance(value, dict):
        raise AtlaWireError("Expected a Bitbucket branch object.")
    name = value.get("displayId")
    identifier = value.get("id")
    commit = value.get("latestCommit")
    default = value.get("isDefault")
    if (
        not isinstance(name, str)
        or not name
        or not isinstance(identifier, str)
        or not identifier
        or (commit is not None and not isinstance(commit, str))
        or (default is not None and not isinstance(default, bool))
    ):
        raise AtlaWireError("Invalid fields in a Bitbucket branch.")
    return Branch(
        name=_require_encodable(name, "branch name"),
        id=_require_encodable(identifier, "branch ID"),
        commit=_optional_encodable(commit, "branch commit"),
        default=default,
    )


def _commit(value: object) -> Commit:
    """Project one commit, keeping the raw message for the JSON view."""
    if not isinstance(value, dict):
        raise AtlaWireError("Expected a Bitbucket commit object.")
    identifier = value.get("id")
    if not isinstance(identifier, str) or not identifier:
        raise AtlaWireError("Invalid fields in a Bitbucket commit.")
    message = value.get("message")
    if message is None:
        message = ""
    elif not isinstance(message, str):
        raise AtlaWireError("Invalid fields in a Bitbucket commit.")
    author, email, display_name = _commit_author_identity(value.get("author"))
    timestamp = _commit_timestamp(value.get("authorTimestamp"))
    moment = _utc_timestamp(
        timestamp, error="Invalid author timestamp in a Bitbucket commit."
    )
    short = value.get("displayId")
    if short is not None and (not isinstance(short, str) or not short):
        raise AtlaWireError("Invalid fields in a Bitbucket commit.")
    full = _require_encodable(identifier, "commit id")
    return Commit(
        id=full,
        displayId=_optional_encodable(short, "commit display id"),
        hash=full,
        date=_commit_date(moment),
        timestamp=timestamp,
        author=_optional_encodable(author, "commit author"),
        email=_optional_encodable(email, "commit email"),
        displayName=_optional_encodable(display_name, "commit author display name"),
        message=_require_encodable(message, "commit message"),
    )


def _commit_author_identity(
    value: object,
) -> tuple[str | None, str | None, str | None]:
    """Return the optional ``name``, ``emailAddress`` and ``displayName``.

    All three fields belong to the same ``author`` object of the commit row, so
    the projection never needs a per-commit request. 5.10 documents only ``name``
    and ``emailAddress`` for a commit author, hence ``displayName`` stays ``None``
    unless the server actually sends it.
    """
    if value is None:
        return None, None, None
    if not isinstance(value, dict):
        raise AtlaWireError("Invalid author in a Bitbucket commit.")
    return (
        _optional_author_text(value.get("name")),
        _optional_author_text(value.get("emailAddress")),
        _optional_author_text(value.get("displayName")),
    )


def _optional_author_text(value: object) -> str | None:
    """Accept an optional author string of a commit row and reject other types."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise AtlaWireError("Invalid author in a Bitbucket commit.")
    return value


def _commit_timestamp(value: object) -> int | None:
    """Keep the raw ``authorTimestamp`` epoch milliseconds of the same row.

    The exact instant is passed through as the server sent it instead of being
    rounded through the formatted ``date``; ``None`` stays ``None``, while any
    other non-integer (including ``bool``) fails the projection.
    """
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise AtlaWireError("Invalid author timestamp in a Bitbucket commit.")
    return value


def _commit_date(moment: datetime | None) -> str | None:
    """Format an optional UTC instant as ``YYYY-MM-DD HH:MM``.

    The exact instant remains available as the raw ``timestamp`` milliseconds;
    this human-readable view keeps the legacy minute precision.
    """
    if moment is None:
        return None
    return (
        f"{moment.year:04d}-{moment.month:02d}-{moment.day:02d} "
        f"{moment.hour:02d}:{moment.minute:02d}"
    )


def _blame_line(number: int, value: object) -> BlameLine:
    """Project one blame array entry, rejecting malformed consumed fields."""
    if not isinstance(value, dict):
        raise AtlaWireError("Expected a Bitbucket blame object.")
    author, email = _blame_author(value.get("author"))
    return BlameLine(
        line=number,
        author=author,
        email=email,
        date=_blame_date(value.get("authorTimestamp")),
        commit=_blame_commit(value),
    )


def _blame_author(value: object) -> tuple[str | None, str | None]:
    """Return the optional name and email address from a blame author object."""
    if value is None:
        return None, None
    if not isinstance(value, dict):
        raise AtlaWireError("Invalid author in a Bitbucket blame row.")
    name = value.get("name")
    email = value.get("emailAddress")
    if (name is not None and not isinstance(name, str)) or (
        email is not None and not isinstance(email, str)
    ):
        raise AtlaWireError("Invalid author in a Bitbucket blame row.")
    return (
        _optional_encodable(name, "blame author"),
        _optional_encodable(email, "blame email"),
    )


def _blame_commit(value: dict[str, object]) -> str | None:
    """Prefer a nonempty ``commitHash`` and fall back to a nonempty ``id``."""
    preferred = value.get("commitHash")
    if preferred is not None and not isinstance(preferred, str):
        raise AtlaWireError("Invalid commit in a Bitbucket blame row.")
    if isinstance(preferred, str) and preferred:
        return _require_encodable(preferred, "blame commit")
    identifier = value.get("id")
    if identifier is not None and not isinstance(identifier, str):
        raise AtlaWireError("Invalid commit in a Bitbucket blame row.")
    if isinstance(identifier, str) and identifier:
        return _require_encodable(identifier, "blame commit")
    return None


def _blame_date(value: object) -> str | None:
    """Format optional epoch milliseconds as a UTC ``YYYY-MM-DD`` date."""
    moment = _utc_timestamp(
        value, error="Invalid author timestamp in a Bitbucket blame row."
    )
    if moment is None:
        return None
    return f"{moment.year:04d}-{moment.month:02d}-{moment.day:02d}"


def _utc_timestamp(value: object, *, error: str) -> datetime | None:
    """Convert optional epoch milliseconds to a UTC instant with integer math.

    Division is floor-based and subtracting the offset never uses a float, so
    zero and negative values keep the instant the commit view already used.
    A value outside the representable calendar fails with ``error``.
    """
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise AtlaWireError(error)
    try:
        return _EPOCH + timedelta(seconds=divmod(value, 1000)[0])
    except OverflowError, ValueError:
        raise AtlaWireError(error) from None
