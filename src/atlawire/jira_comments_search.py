"""Author-wide Jira comment discovery.

The search window uses ``updated >= -Ndays``. That predicate filters the
*issue* update timestamp, not a comment's creation timestamp: an old comment on
a recently updated issue is included, while a recent comment on an issue whose
update timestamp is older than the window can be missed. The window is a
bounded candidate set, not a comment-date index.

Pagination is fail-closed. Jira search pages and truncated comment threads are
read with real ``startAt`` offsets and stable totals; any malformed or
inconsistent pagination metadata or consumed record, later HTTP failure,
duplicate record, issue-budget exhaustion, or comment page limit raises
:class:`AtlaWireError`, and no partial result is returned. A short page is never
treated as proof of exhaustion, and a last issue's ``updated`` value is never
used as an early stop. Completed thread pages are streamed into a bounded
collector, so only the newest ``limit`` rows are retained while scanning; a
later failure still discards the whole result. User resolution, search pages,
and thread completion are separate requests, so the result is not claimed to be
a consistent snapshot.

The optional ``grep`` filter uses the isolated, killable regex helper through
one evaluation call per comment page. Matching is case-insensitive
``re.search`` over each complete comment body, after the exact-author filter.
Patterns are validated before any request; a helper timeout or failure fails
the whole scan instead of returning partial results.

User lookup cannot prove complete discovery from the Jira 8.22 response: the
user search is a bare array with no ``total`` or ``isLast`` metadata, so paging
stops at the first empty page. If exactly one nonexact user was found, that
singleton is selected as a heuristic; pass the exact login when uniqueness
matters.
"""

import heapq
import re
from collections.abc import Iterator
from datetime import datetime
from typing import TypedDict, TypeGuard

import requests

from atlawire import jira as _jira
from atlawire.http import (
    AtlaWireError,
    bearer_session,
    get_json_object,
    normalize_base_url,
)
from atlawire.regex_helper import (
    HelperFailure,
    InvalidRegex,
    RegexTimeout,
    match_documents,
    validate_regex,
)
from atlawire.repo_grep import REGEX_TIMEOUT_DEFAULT

_API = "rest/api/2"
_SEARCH_FIELDS = "summary,comment,updated"
_SEARCH_PAGE_SIZE = 100
_COMMENT_PAGE_SIZE = 100
_ISSUE_KEY = re.compile(r"[A-Z][A-Z0-9_]*-[0-9]+")
_PROJECT_KEY = re.compile(r"[A-Z][A-Z0-9_]+")
_COMMENT_ID = re.compile(r"[0-9]+")

DEFAULT_DAYS = 90
DEFAULT_LIMIT = 10
DEFAULT_MAX_ISSUES = 20000
COMMENT_PAGE_LIMIT = 100
USER_SEARCH_LIMIT = 50
# Hard bound on pages read for one user-lookup candidate.
USER_PAGE_LIMIT = 100

_RU2LAT = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "e",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "kh",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "shch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
}


class AuthorCommentRow(TypedDict):
    """One comment by the resolved author, ready for JSON output."""

    key: str
    summary: str
    created: str
    author: str
    comment_id: str
    url: str
    body: str


class _ResolvedAuthor(TypedDict):
    name: str
    display_name: str


def find_author_comments(
    base_url: str,
    user: str | None = None,
    *,
    token: str,
    days: int = DEFAULT_DAYS,
    limit: int = DEFAULT_LIMIT,
    project: str | None = None,
    grep: str | None = None,
    max_issues: int = DEFAULT_MAX_ISSUES,
    allow_http_loopback: bool = False,
) -> list[AuthorCommentRow]:
    """Return the newest comments by one exact Jira author.

    When ``user`` is omitted, the authenticated identity is read with
    :func:`atlawire.jira.get_current_user` and no user search is performed.
    Otherwise ``user`` is resolved with :func:`atlawire.jira.search_users`.
    The original term, a BBK-compatible transliteration, and a short
    transliterated prefix are tried in order. Paging stops at the first empty
    page. Jira 8.22 returns a bare user array without ``total`` or ``isLast``,
    so an empty page is treated as practical exhaustion, not proof that no
    further users exist. An exact login match stops paging immediately. If
    paging ends with exactly one nonexact candidate, that candidate is selected
    as a heuristic, not proven uniqueness or complete discovery; multiple
    distinct nonexact candidates are rejected as ambiguous. Pass the exact
    login for unambiguous use. Only comments whose ``author.name`` exactly
    equals the resolved login are kept.

    ``grep`` is an optional BBK-compatible regular expression. A non-empty
    pattern is validated before any request, then evaluated with
    case-insensitive ``re.search`` over each complete matching-author comment
    body in one killable helper call per page. ``None`` or an empty string
    disables filtering. A helper timeout or failure aborts the whole scan.

    ``days`` bounds the Jira *issue update* window, not comment creation; see
    the module docstring. Rows are sorted by timezone-aware comment creation
    instant, newest first, then truncated to ``limit``. Each row preserves the
    issue key, summary, original created text, author display name, comment ID,
    body, and a deep link on the configured base URL.

    The complete matching issue set must fit ``max_issues``. If it does not, or
    if a comment thread exceeds :data:`COMMENT_PAGE_LIMIT` pages, the call
    raises instead of returning an incomplete list.
    """
    _validate_parameters(
        days=days, limit=limit, max_issues=max_issues, project=project
    )
    if grep is not None and not isinstance(grep, str):
        raise AtlaWireError("Expected the grep pattern as text.")
    pattern = grep or None
    if not isinstance(base_url, str):
        raise AtlaWireError("Expected the Jira base URL as text.")
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    if pattern is not None:
        _validate_grep_pattern(pattern)
    if user is None:
        author = _current_author(
            base,
            token=token,
            allow_http_loopback=allow_http_loopback,
        )
    else:
        author = _resolve_author(
            base,
            _user_term(user),
            token=token,
            allow_http_loopback=allow_http_loopback,
        )
    query = _build_jql(days, project)
    with bearer_session(token) as session:
        return _collect(
            session,
            base,
            query,
            author,
            limit=limit,
            grep=pattern,
            max_issues=max_issues,
        )


def _validate_parameters(
    *, days: object, limit: object, max_issues: object, project: object
) -> None:
    """Reject unusable arguments before any user lookup or HTTP request."""
    if not _is_int(days) or days < 1:
        raise AtlaWireError("The day window must be a positive integer.")
    if not _is_int(limit) or limit < 1:
        raise AtlaWireError("The result limit must be a positive integer.")
    if not _is_int(max_issues) or max_issues < 1:
        raise AtlaWireError("The issue budget must be a positive integer.")
    if project is not None and (
        not isinstance(project, str) or _PROJECT_KEY.fullmatch(project) is None
    ):
        raise AtlaWireError("Expected an uppercase Jira project key.")


def _user_term(user: object) -> str:
    """Return the stripped login or display-name fragment, or reject it."""
    if not isinstance(user, str) or not user.strip():
        raise AtlaWireError("Expected a non-empty Jira user login or name.")
    return _check_text(user.strip(), "Jira user login or name")


def _build_jql(days: int, project: str | None) -> str:
    clauses = [f"updated >= -{days}d"]
    if project is not None:
        clauses.append(f'project = "{project}"')
    return " AND ".join(clauses) + " ORDER BY updated DESC"


def _validate_grep_pattern(pattern: str) -> None:
    """Reject an invalid or unvalidatable pattern before any request."""
    try:
        validate_regex(
            pattern,
            ignore_case=True,
            timeout_s=REGEX_TIMEOUT_DEFAULT,
        )
    except InvalidRegex:
        raise AtlaWireError("The grep regular expression is invalid.") from None
    except RegexTimeout:
        raise AtlaWireError(
            "Grep regex validation timed out; no result was produced."
        ) from None
    except HelperFailure:
        raise AtlaWireError(
            "Grep regex validation failed; no result was produced."
        ) from None


def _grep_match_documents(bodies: list[str], pattern: str) -> list[bool]:
    """Match one page of full bodies in the isolated regex helper."""
    try:
        matches = match_documents(
            bodies,
            pattern,
            ignore_case=True,
            timeout_s=REGEX_TIMEOUT_DEFAULT,
        )
    except InvalidRegex:
        raise AtlaWireError("The grep regular expression is invalid.") from None
    except RegexTimeout:
        raise AtlaWireError(
            "Grep regex evaluation timed out; no result was produced."
        ) from None
    except HelperFailure:
        raise AtlaWireError(
            "Grep regex evaluation failed; no result was produced."
        ) from None
    if len(matches) != len(bodies):
        raise AtlaWireError(
            "Grep regex evaluation failed; no result was produced."
        )
    return matches


def _translit(term: str) -> str:
    """Transliterate Russian text with BBK's soft-sign rule.

    A soft sign before ``е``/``ё``/``ю``/``я`` becomes ``y``, so
    ``Воробьев`` becomes ``vorobyev`` rather than ``vorobev``.
    """
    out: list[str] = []
    chars = term.lower()
    for index, char in enumerate(chars):
        if (
            char == "ь"
            and index + 1 < len(chars)
            and chars[index + 1] in "еёюя"
        ):
            out.append("y")
            continue
        out.append(_RU2LAT.get(char, char))
    return "".join(out)


def _user_candidates(term: str) -> list[str]:
    """Return BBK-compatible lookup candidates in priority order."""
    candidates = [term]
    latin = _translit(term)
    if latin != term.lower():
        candidates.append(latin)
        if len(latin) >= 4:
            candidates.append(latin[:4])
    unique: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate not in seen:
            seen.add(candidate)
            unique.append(candidate)
    return unique


def _resolve_author(
    base: str,
    term: str,
    *,
    token: str,
    allow_http_loopback: bool,
) -> _ResolvedAuthor:
    """Resolve one login without guessing between several matching users."""
    for candidate in _user_candidates(term):
        resolved = _resolve_user_candidate(
            base,
            candidate,
            token=token,
            allow_http_loopback=allow_http_loopback,
        )
        if resolved is not None:
            return resolved
    raise AtlaWireError("No Jira user matched the requested login or name.")


def _resolve_user_candidate(
    base: str,
    candidate: str,
    *,
    token: str,
    allow_http_loopback: bool,
) -> _ResolvedAuthor | None:
    """Page one candidate until empty, exact, or page-budget failure.

    Jira's user search has no total or ``isLast`` field. The first empty page is
    therefore the only practical exhaustion signal, and selecting a singleton
    nonexact user after it is a heuristic rather than proof of uniqueness.
    """
    ambiguous = "Jira user search matched more than one user; use the exact login."
    duplicate = (
        "Jira user search returned a duplicate or non-advancing page; "
        "use the exact login."
    )
    candidate_key = candidate.casefold()
    only_nonexact: object | None = None
    multiple_candidates = False
    seen_names: set[str] = set()
    start = 0
    for _ in range(USER_PAGE_LIMIT):
        rows = _jira.search_users(
            base,
            candidate,
            token=token,
            start_at=start,
            max_results=USER_SEARCH_LIMIT,
            allow_http_loopback=allow_http_loopback,
        )
        if not rows:
            if multiple_candidates:
                raise AtlaWireError(ambiguous)
            if only_nonexact is not None:
                return _resolved_author(only_nonexact)
            return None
        exact_rows: list[object] = []
        for row in rows:
            name = _user_name(row)
            key = name.casefold()
            if key in seen_names:
                raise AtlaWireError(duplicate)
            seen_names.add(key)
            if key == candidate_key:
                exact_rows.append(row)
            elif only_nonexact is None:
                only_nonexact = row
            else:
                multiple_candidates = True
        if len(exact_rows) > 1:
            raise AtlaWireError(ambiguous)
        if exact_rows:
            return _resolved_author(exact_rows[0])
        start += len(rows)
    raise AtlaWireError(
        "Jira user search exceeded the page budget; use the exact login."
    )


def _user_name(row: object) -> str:
    if not isinstance(row, dict):
        raise AtlaWireError("Expected Jira user objects.")
    name = row.get("name")
    if not isinstance(name, str) or not name.strip():
        raise AtlaWireError("Expected Jira users with non-empty names.")
    return _check_text(name, "Jira user name")


def _current_author(
    base: str, *, token: str, allow_http_loopback: bool
) -> _ResolvedAuthor:
    """Resolve the authenticated identity without searching for users."""
    current = _jira.get_current_user(
        base, token=token, allow_http_loopback=allow_http_loopback
    )
    return _author_identity(current.get("name"), current.get("displayName"))


def _resolved_author(row: object) -> _ResolvedAuthor:
    if not isinstance(row, dict):
        raise AtlaWireError("Expected Jira user objects.")
    return _author_identity(row.get("name"), row.get("displayName"))


def _author_identity(name: object, display: object) -> _ResolvedAuthor:
    """Validate one identity and fall back to the login for the display name."""
    if not isinstance(name, str) or not name.strip():
        raise AtlaWireError("Expected a Jira user with a non-empty name.")
    checked_name = _check_text(name, "Jira user name")
    if display is None:
        return _ResolvedAuthor(name=checked_name, display_name=checked_name)
    if not isinstance(display, str):
        raise AtlaWireError("Expected the Jira user display name as text.")
    _check_text(display, "Jira user display name")
    if not display.strip():
        return _ResolvedAuthor(name=checked_name, display_name=checked_name)
    return _ResolvedAuthor(name=checked_name, display_name=display)


class _CollectorSlot:
    """Bounded newest-first collector with stable first-seen tie order.

    The heap root is the row currently ranked last: the oldest timestamp, and
    for equal timestamps the row seen most recently. A later equal-timestamp
    row therefore cannot evict an earlier one, while a newer timestamp can.
    """

    def __init__(self, *, limit: int) -> None:
        self._limit = limit
        self._heap: list[tuple[datetime, int, AuthorCommentRow]] = []

    def offer(
        self, timestamp: datetime, row: AuthorCommentRow, serial: int
    ) -> int:
        """Offer one row and return the next arrival serial."""
        entry = (timestamp, -serial, row)
        if len(self._heap) < self._limit:
            heapq.heappush(self._heap, entry)
        elif entry > self._heap[0]:
            heapq.heapreplace(self._heap, entry)
        return serial + 1

    def finish(self) -> list[AuthorCommentRow]:
        """Return the retained rows newest first, ties in first-seen order."""
        return [
            row
            for _, _, row in sorted(
                self._heap,
                key=lambda item: (item[0], item[1]),
                reverse=True,
            )
        ]


def _collect(
    session: requests.Session,
    base: str,
    query: str,
    author: _ResolvedAuthor,
    *,
    limit: int,
    grep: str | None,
    max_issues: int,
) -> list[AuthorCommentRow]:
    """Scan every candidate issue and retain only the newest ``limit`` rows."""
    url = f"{base}/{_API}/search"
    slot = _CollectorSlot(limit=limit)
    seen_comment_ids: set[str] = set()
    seen_keys: set[str] = set()
    serial = 0
    start = 0
    total: int | None = None
    while total is None or start < total:
        remaining = max_issues - start
        if remaining < 1:
            raise AtlaWireError(
                "The Jira issue budget was exhausted before the search completed."
            )
        requested = min(_SEARCH_PAGE_SIZE, remaining)
        page = get_json_object(
            session,
            url,
            params={
                "jql": query,
                "startAt": start,
                "maxResults": requested,
                "fields": _SEARCH_FIELDS,
            },
        )
        issues, reported_total = _search_page(page, start, requested, total)
        if reported_total > max_issues:
            raise AtlaWireError(
                "The Jira search exceeds the issue budget; narrow the query "
                "or raise the budget."
            )
        total = reported_total
        if not issues:
            break
        for issue in issues:
            for timestamp, row in _issue_comments(
                session,
                base,
                issue,
                author,
                seen_comment_ids=seen_comment_ids,
                seen_keys=seen_keys,
                grep=grep,
            ):
                serial = slot.offer(timestamp, row, serial)
        start += len(issues)
        if start == total:
            break
    return slot.finish()


def _search_page(
    page: dict[str, object],
    start: int,
    requested: int,
    known_total: int | None,
) -> tuple[list[object], int]:
    """Validate one search page and return its issues and stable total."""
    reported_start = page.get("startAt")
    if not _is_int(reported_start) or reported_start != start:
        raise AtlaWireError(
            "Expected Jira search startAt to match the requested offset."
        )
    issues = page.get("issues")
    if not isinstance(issues, list):
        raise AtlaWireError("Expected a Jira search issues array.")
    total = page.get("total")
    if not _is_int(total) or total < 0:
        raise AtlaWireError("Invalid Jira search total.")
    if known_total is not None and total != known_total:
        raise AtlaWireError("Jira search total changed between pages.")
    if issues:
        advertised = page.get("maxResults")
        if not _is_int(advertised) or advertised <= 0:
            raise AtlaWireError("Invalid Jira search maxResults.")
        if len(issues) > advertised:
            raise AtlaWireError("Jira search returned more issues than maxResults.")
        if len(issues) > requested:
            raise AtlaWireError("Jira search returned more issues than requested.")
        if total < start + len(issues):
            raise AtlaWireError("Inconsistent Jira search pagination metadata.")
    elif start != total:
        raise AtlaWireError(
            "Jira search returned an empty page before all matches."
        )
    is_last = page.get("isLast")
    if is_last is not None and not isinstance(is_last, bool):
        raise AtlaWireError("Invalid Jira search isLast flag.")
    if is_last is True and start + len(issues) < total:
        raise AtlaWireError("Jira search isLast disagreed with its total.")
    return issues, total


def _issue_comments(
    session: requests.Session,
    base: str,
    issue: object,
    author: _ResolvedAuthor,
    *,
    seen_comment_ids: set[str],
    seen_keys: set[str],
    grep: str | None,
) -> Iterator[tuple[datetime, AuthorCommentRow]]:
    """Validate one issue and stream its complete comment thread."""
    if not isinstance(issue, dict):
        raise AtlaWireError("Expected Jira issue objects in search results.")
    key = issue.get("key")
    if not isinstance(key, str) or _ISSUE_KEY.fullmatch(key) is None:
        raise AtlaWireError("Expected a valid Jira issue key in search results.")
    if key in seen_keys:
        raise AtlaWireError("Jira search returned duplicate issue keys.")
    seen_keys.add(key)
    fields = issue.get("fields")
    if not isinstance(fields, dict):
        raise AtlaWireError("Expected Jira issue fields in search results.")
    summary = _summary(fields.get("summary"))
    comments, block_total = _comment_block(fields.get("comment"))
    if block_total > len(comments):
        for batch in _read_thread_pages(
            session, base, key, block_total=block_total
        ):
            for entry in _page_entries(
                batch,
                base=base,
                key=key,
                summary=summary,
                author=author,
                seen_comment_ids=seen_comment_ids,
                grep=grep,
            ):
                yield entry
        return
    for entry in _page_entries(
        comments,
        base=base,
        key=key,
        summary=summary,
        author=author,
        seen_comment_ids=seen_comment_ids,
        grep=grep,
    ):
        yield entry


def _comment_block(value: object) -> tuple[list[dict[str, object]], int]:
    """Validate the comment preview embedded in a search result."""
    if not isinstance(value, dict):
        raise AtlaWireError("Expected a Jira comment field in search results.")
    comments = value.get("comments")
    if not isinstance(comments, list):
        raise AtlaWireError("Expected a Jira comments array in search results.")
    total = value.get("total")
    if not _is_int(total) or total < 0:
        raise AtlaWireError("Invalid Jira comment total in search results.")
    if total < len(comments):
        raise AtlaWireError("Inconsistent Jira comment metadata in search results.")
    advertised = value.get("maxResults")
    if advertised is not None:
        if not _is_int(advertised) or advertised < 0:
            raise AtlaWireError("Invalid Jira comment maxResults in search results.")
        if len(comments) > advertised:
            raise AtlaWireError("Jira returned more comments than maxResults.")
    checked: list[dict[str, object]] = []
    for item in comments:
        if not isinstance(item, dict):
            raise AtlaWireError("Expected Jira comment objects.")
        checked.append(item)
    return checked, total


def _read_thread_pages(
    session: requests.Session,
    base: str,
    key: str,
    *,
    block_total: int,
) -> Iterator[list[dict[str, object]]]:
    """Stream one truncated thread as bounded, validated page batches."""
    url = f"{base}/{_API}/issue/{key}/comment"
    seen: set[str] = set()
    start = 0
    total: int | None = None
    for _ in range(COMMENT_PAGE_LIMIT):
        page = get_json_object(
            session,
            url,
            params={"startAt": start, "maxResults": _COMMENT_PAGE_SIZE},
        )
        batch, reported_total = _comment_page(page, start, total)
        total = reported_total
        if not batch:
            break
        checked: list[dict[str, object]] = []
        for value in batch:
            if not isinstance(value, dict):
                raise AtlaWireError("Expected Jira comment objects.")
            comment_id = _comment_id(value)
            if comment_id in seen:
                raise AtlaWireError("Jira returned duplicate comment IDs.")
            seen.add(comment_id)
            checked.append(value)
        yield checked
        start += len(checked)
        if start == total:
            break
    else:
        raise AtlaWireError(
            "Jira comment thread exceeded the page limit; raise the budget "
            "or narrow the query."
        )
    if total is None or start != total:
        raise AtlaWireError("Jira comments ended before the thread was complete.")
    if total < block_total:
        raise AtlaWireError("Inconsistent Jira comment thread metadata.")


def _comment_page(
    page: dict[str, object],
    start: int,
    known_total: int | None,
) -> tuple[list[object], int]:
    """Validate one comment page and return its rows and stable total."""
    reported_start = page.get("startAt")
    if not _is_int(reported_start) or reported_start != start:
        raise AtlaWireError(
            "Expected Jira comments startAt to match the requested offset."
        )
    total = page.get("total")
    if not _is_int(total) or total < 0:
        raise AtlaWireError("Invalid Jira comments total.")
    if known_total is not None and total != known_total:
        raise AtlaWireError("Jira comments total changed between pages.")
    comments = page.get("comments")
    if not isinstance(comments, list):
        raise AtlaWireError("Expected a Jira comments array.")
    if comments:
        advertised = page.get("maxResults")
        if not _is_int(advertised) or advertised <= 0:
            raise AtlaWireError("Invalid Jira comments maxResults.")
        if len(comments) > advertised:
            raise AtlaWireError("Jira returned more comments than maxResults.")
        if len(comments) > _COMMENT_PAGE_SIZE:
            raise AtlaWireError("Jira returned more comments than requested.")
        if total < start + len(comments):
            raise AtlaWireError("Inconsistent Jira comments pagination metadata.")
    elif start != total:
        raise AtlaWireError("Jira comments ended before all comments were read.")
    return comments, total


def _comment_row(
    value: object,
    *,
    base: str,
    key: str,
    summary: str,
    author: _ResolvedAuthor,
    seen_comment_ids: set[str],
) -> tuple[datetime, AuthorCommentRow] | None:
    """Validate one comment, returning a row only for the exact login."""
    if not isinstance(value, dict):
        raise AtlaWireError("Expected Jira comment objects.")
    comment_id = _comment_id(value)
    if comment_id in seen_comment_ids:
        raise AtlaWireError("Jira returned duplicate comment IDs.")
    seen_comment_ids.add(comment_id)
    author_value = value.get("author")
    if author_value is None:
        return None
    if not isinstance(author_value, dict):
        raise AtlaWireError("Expected a Jira comment author object.")
    name = author_value.get("name")
    if name is None:
        return None
    if not isinstance(name, str):
        raise AtlaWireError("Expected a Jira comment author name as text.")
    _check_text(name, "Jira comment author name")
    if name != author["name"]:
        return None
    created = value.get("created")
    if not isinstance(created, str) or not created.strip():
        raise AtlaWireError("Expected a Jira comment created timestamp.")
    _check_text(created, "Jira comment created timestamp")
    instant = _comment_instant(created)
    body_value = value.get("body")
    if body_value is None:
        body = ""
    elif isinstance(body_value, str):
        body = _check_text(body_value, "Jira comment body")
    else:
        raise AtlaWireError("Expected the Jira comment body as text.")
    return (
        instant,
        AuthorCommentRow(
            key=key,
            summary=summary,
            created=created,
            author=author["display_name"],
            comment_id=comment_id,
            url=(
                f"{base}/browse/{key}?focusedCommentId={comment_id}"
                f"#comment-{comment_id}"
            ),
            body=body,
        ),
    )


def _page_entries(
    values: list[dict[str, object]],
    *,
    base: str,
    key: str,
    summary: str,
    author: _ResolvedAuthor,
    seen_comment_ids: set[str],
    grep: str | None,
) -> list[tuple[datetime, AuthorCommentRow]]:
    """Validate one page, then apply the page-batched grep filter."""
    entries: list[tuple[datetime, AuthorCommentRow]] = []
    for value in values:
        entry = _comment_row(
            value,
            base=base,
            key=key,
            summary=summary,
            author=author,
            seen_comment_ids=seen_comment_ids,
        )
        if entry is not None:
            entries.append(entry)
    if grep and entries:
        bodies = [entry[1]["body"] for entry in entries]
        matches = _grep_match_documents(bodies, grep)
        entries = [
            entry
            for entry, is_match in zip(entries, matches, strict=True)
            if is_match
        ]
    return entries


def _comment_id(value: object) -> str:
    if not isinstance(value, dict):
        raise AtlaWireError("Expected Jira comment objects.")
    comment_id = value.get("id")
    if not isinstance(comment_id, str) or _COMMENT_ID.fullmatch(comment_id) is None:
        raise AtlaWireError("Expected a non-empty numeric Jira comment ID.")
    return comment_id


def _summary(value: object) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise AtlaWireError("Invalid Jira summary in search results.")
    return " ".join(_check_text(value, "Jira summary").split())


def _comment_instant(value: str) -> datetime:
    """Parse a timezone-aware Jira timestamp for instant-based ordering."""
    try:
        instant = datetime.fromisoformat(value.strip())
    except ValueError:
        raise AtlaWireError("Invalid Jira comment created timestamp.") from None
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise AtlaWireError(
            "Jira comment created timestamp must include a timezone."
        )
    return instant


def _is_int(value: object) -> TypeGuard[int]:
    return isinstance(value, int) and not isinstance(value, bool)


def _check_text(value: str, label: str) -> str:
    """Return text unchanged only when UTF-8 output can represent it."""
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise AtlaWireError(f"Expected {label} as valid UTF-8 text.") from None
    return value


__all__ = ["AuthorCommentRow", "find_author_comments"]
