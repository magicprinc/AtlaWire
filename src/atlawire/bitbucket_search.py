"""Read-only indexed code search for self-hosted Bitbucket.

The index is served by the Bitbucket Search plugin at one fixed route. The
route is not part of the documented Bitbucket Server 5.10 REST API, and the
plugin answers only POST, so a single POST is used here as a read-only search
request with no write semantics.
"""

import re
from html import unescape
from typing import Literal, TypedDict

import requests

from atlawire.http import (
    AtlaWireError,
    bearer_session,
    normalize_base_url,
    post_json_object,
)

SEARCH_LIMIT_MIN = 1
SEARCH_LIMIT_MAX = 999
SEARCH_LIMIT_DEFAULT = 20

_PAGE_SIZE = 100
_MAX_REQUESTS = 20
_PROJECT_KEY = re.compile(r"~?[A-Za-z0-9_][A-Za-z0-9_.-]*")
_REPOSITORY_SLUG = re.compile(r"[A-Za-z0-9_.-]+")
_EMPHASIS = re.compile(r"<em>(.*?)</em>", re.DOTALL)

MatchEvidence = Literal["highlight", "context-only", "none"]


class SearchLine(TypedDict):
    line: int | None
    text: str


class SearchRow(TypedDict):
    project: str
    repository: str
    file: str
    hitCount: int | None
    matchEvidence: MatchEvidence
    hits: list[SearchLine]
    context: list[list[SearchLine]]


def search_code(
    base_url: str,
    query: str,
    *,
    project: str | None = None,
    repo: str | None = None,
    limit: int = SEARCH_LIMIT_DEFAULT,
    every_page: bool = False,
    token: str,
    allow_http_loopback: bool = False,
) -> list[SearchRow]:
    """Search indexed Bitbucket code at the one fixed plugin route.

    ``project`` and ``repo`` (``KEY/slug``) are mutually exclusive scope
    filters. The exact query is preserved after the fixed ``project:KEY`` and
    optional ``repo:SLUG`` prefix, so caller text is never rewritten. A result
    whose project or repository disagrees with an explicit scope, ignoring
    case, fails the whole call instead of widening the result.

    ``limit`` is an exact integer from 1 to 999. Without ``every_page`` exactly
    one request is made, so the result is the first page only. With
    ``every_page`` the call reads at most 20 requests, follows the exact
    ``isLastPage`` boolean and a strictly advancing integer ``nextStart``,
    stops at the row cap or the terminal page, and never requires the unused
    next cursor on the final page. Any later transport, cursor, or malformed
    page failure raises without returning partial rows.

    Rows keep the legacy fields ``project``, ``repository``, ``file``,
    ``hitCount``, ``matchEvidence``, ``hits`` and ``context``. Only a raw,
    paired ``<em>...</em>`` literal marks a highlighted line. Entity decoding
    happens once, after those raw markers are removed, so an entity-encoded
    ``<em>`` stays ordinary context text. ``hits`` never includes context-only
    lines.

    The index covers only what the plugin indexed (typically the default
    branch), matches exact terms, and has no regex or extension filter. No
    current-user lookup, cache, retry, fallback, or response link is used.
    """
    _validate_query(query)
    scope_project, scope_slug = _scope(project, repo)
    _validate_limit(limit)
    if not isinstance(every_page, bool):
        raise AtlaWireError("The search paging option must be a boolean.")
    effective = _effective_query(query, scope_project, scope_slug)
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    url = f"{base}/rest/search/latest/search"
    with bearer_session(token) as session:
        return _search_pages(
            session,
            url,
            effective,
            limit=limit,
            every_page=every_page,
            project=scope_project,
            slug=scope_slug,
        )


def _validate_query(query: str) -> None:
    if not isinstance(query, str) or not query.strip():
        raise AtlaWireError("The search query must be non-empty text.")
    _require_encodable(query, "search query")


def _scope(project: str | None, repo: str | None) -> tuple[str | None, str | None]:
    """Return the validated explicit scope, rejecting both filters together."""
    if project is not None and repo is not None:
        raise AtlaWireError("Use a project or a repository, not both.")
    if project is not None:
        if not isinstance(project, str) or not _PROJECT_KEY.fullmatch(project):
            raise AtlaWireError("Expected a Bitbucket project key or ~user project.")
        return project, None
    if repo is not None:
        repo_project, repo_slug = _split_repo(repo)
        return repo_project, repo_slug
    return None, None


def _split_repo(repo: str) -> tuple[str, str]:
    """Split ``PROJECT/slug`` into two safe segments."""
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


def _validate_limit(limit: int) -> None:
    if (
        not isinstance(limit, int)
        or isinstance(limit, bool)
        or not SEARCH_LIMIT_MIN <= limit <= SEARCH_LIMIT_MAX
    ):
        raise AtlaWireError("The search limit must be between 1 and 999.")


def _effective_query(query: str, project: str | None, slug: str | None) -> str:
    """Prefix the fixed scope while preserving the exact caller query."""
    scope: list[str] = []
    if project is not None:
        scope.append(f"project:{project}")
    if slug is not None:
        scope.append(f"repo:{slug}")
    return " ".join([*scope, query]) if scope else query


def _search_pages(
    session: requests.Session,
    url: str,
    query: str,
    *,
    limit: int,
    every_page: bool,
    project: str | None,
    slug: str | None,
) -> list[SearchRow]:
    rows: list[SearchRow] = []
    start = 0
    for _ in range(_MAX_REQUESTS):
        size = min(_PAGE_SIZE, limit - len(rows))
        page = post_json_object(
            session,
            url,
            body={
                "query": query,
                "entities": {"code": {"start": start, "limit": size}},
            },
        )
        code = _code_page(page)
        values = _page_values(code)
        if len(values) > size:
            raise AtlaWireError("Bitbucket search returned more rows than requested.")
        for value in values:
            rows.append(_search_row(value, project=project, slug=slug))
        if not every_page:
            return rows
        last = code.get("isLastPage")
        if not isinstance(last, bool):
            raise AtlaWireError("Expected a Bitbucket search isLastPage boolean.")
        if len(rows) >= limit:
            return rows
        if last:
            return rows
        start = _next_start(code, start)
    raise AtlaWireError("Bitbucket search page budget reached; narrow the search.")


def _code_page(page: dict[str, object]) -> dict[str, object]:
    code = page.get("code")
    if not isinstance(code, dict):
        raise AtlaWireError("Expected a Bitbucket search code page.")
    return code


def _page_values(code: dict[str, object]) -> list[object]:
    values = code.get("values")
    if not isinstance(values, list):
        raise AtlaWireError("Expected a Bitbucket search values array.")
    return values


def _next_start(code: dict[str, object], start: int) -> int:
    """Return an advancing integer cursor, rejecting a boolean or a repeat."""
    next_start = code.get("nextStart")
    if (
        not isinstance(next_start, int)
        or isinstance(next_start, bool)
        or next_start <= start
    ):
        raise AtlaWireError("Invalid or non-advancing Bitbucket search nextStart.")
    return next_start


def _search_row(value: object, *, project: str | None, slug: str | None) -> SearchRow:
    if not isinstance(value, dict):
        raise AtlaWireError("Expected a Bitbucket search result object.")
    repository = value.get("repository")
    if not isinstance(repository, dict):
        raise AtlaWireError("Invalid repository metadata in a Bitbucket search result.")
    project_value = repository.get("project")
    key = project_value.get("key") if isinstance(project_value, dict) else None
    repository_slug = repository.get("slug")
    file = value.get("file")
    if not isinstance(key, str) or not _PROJECT_KEY.fullmatch(key):
        raise AtlaWireError("Invalid project key in a Bitbucket search result.")
    if (
        not isinstance(repository_slug, str)
        or not _REPOSITORY_SLUG.fullmatch(repository_slug)
        or repository_slug in {".", ".."}
    ):
        raise AtlaWireError("Invalid repository slug in a Bitbucket search result.")
    if not isinstance(file, str) or not file:
        raise AtlaWireError("Invalid file path in a Bitbucket search result.")
    _require_encodable(file, "search file path")
    _check_scope(key, repository_slug, project, slug)
    hit_count = value.get("hitCount")
    if hit_count is not None and (
        not isinstance(hit_count, int) or isinstance(hit_count, bool) or hit_count < 0
    ):
        raise AtlaWireError("Invalid hit count in a Bitbucket search result.")
    context, hits = _hit_contexts(value.get("hitContexts"))
    evidence: MatchEvidence = (
        "highlight" if hits else ("context-only" if any(context) else "none")
    )
    return SearchRow(
        project=key,
        repository=repository_slug,
        file=file,
        hitCount=hit_count,
        matchEvidence=evidence,
        hits=hits,
        context=context,
    )


def _check_scope(
    key: str, repository_slug: str, project: str | None, slug: str | None
) -> None:
    """Fail rather than broaden when a row disagrees with the explicit scope."""
    if project is not None and key.lower() != project.lower():
        raise AtlaWireError(
            "Bitbucket search returned a result outside the requested scope."
        )
    if slug is not None and (
        project is None
        or key.lower() != project.lower()
        or repository_slug.lower() != slug.lower()
    ):
        raise AtlaWireError(
            "Bitbucket search returned a result outside the requested scope."
        )


def _hit_contexts(
    raw: object,
) -> tuple[list[list[SearchLine]], list[SearchLine]]:
    """Decode context groups in order and collect the highlighted lines."""
    if raw is None:
        return [], []
    if not isinstance(raw, list):
        raise AtlaWireError("Invalid hit contexts in a Bitbucket search result.")
    context: list[list[SearchLine]] = []
    hits: list[SearchLine] = []
    for group in raw:
        if not isinstance(group, list):
            raise AtlaWireError(
                "Invalid hit context group in a Bitbucket search result."
            )
        lines: list[SearchLine] = []
        for item in group:
            line, highlighted = _context_line(item)
            lines.append(line)
            if highlighted:
                hits.append(line)
        context.append(lines)
    return context, hits


def _context_line(item: object) -> tuple[SearchLine, bool]:
    if not isinstance(item, dict):
        raise AtlaWireError("Expected a Bitbucket search line object.")
    line = item.get("line")
    if line is not None and (
        not isinstance(line, int) or isinstance(line, bool) or line < 0
    ):
        raise AtlaWireError("Invalid line number in a Bitbucket search result.")
    text = item.get("text")
    if text is None:
        text = ""
    elif not isinstance(text, str):
        raise AtlaWireError("Invalid line text in a Bitbucket search result.")
    decoded, highlighted = _decode_line(text)
    return SearchLine(line=line, text=decoded), highlighted


def _decode_line(raw: str) -> tuple[str, bool]:
    """Strip only raw paired emphasis markers, then unescape entities once.

    Detection happens before decoding, so an entity-encoded ``<em>`` is
    ordinary text and can never be reported as server-highlighted evidence.
    Matching is bounded to the prefix through the last raw closing marker:
    every opening considered there has a close unless an earlier non-overlapping
    match already consumed it, and a trailing unmatched opening stays literal.
    This keeps repeated unmatched ``<em>`` markers linear instead of rescanning
    the whole line for each one.
    """
    boundary = raw.rfind("</em>")
    if boundary < 0:
        return _unescape_line(raw), False
    boundary += len("</em>")
    stripped, count = _EMPHASIS.subn(lambda match: match.group(1), raw[:boundary])
    if not count:
        return _unescape_line(raw), False
    return _unescape_line(stripped + raw[boundary:]), True


def _unescape_line(raw: str) -> str:
    """Decode entities once, sanitizing interpreter character-reference limits."""
    try:
        decoded = unescape(raw)
    except ValueError:
        raise AtlaWireError(
            "Invalid character reference in a Bitbucket search result."
        ) from None
    _require_encodable(decoded, "search line text")
    return decoded


def _require_encodable(value: str, label: str) -> str:
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise AtlaWireError(f"The {label} must be valid UTF-8 text.") from None
    return value
