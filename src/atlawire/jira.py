"""Read operations for self-hosted Jira."""

import re
from typing import TypedDict, TypeGuard
from urllib.parse import urlsplit

import requests

from atlawire.http import (
    AtlaWireError,
    bearer_session,
    get_json_array,
    get_json_object,
    normalize_base_url,
)

_ISSUE_KEY = r"[A-Z][A-Z0-9_]*-[0-9]+"
_SEARCH_FIELDS = "summary,status,priority,issuetype,assignee,updated"
_MY_ISSUES_QUERY = (
    "assignee = currentUser() AND statusCategory != Done ORDER BY updated DESC"
)
SEARCH_LIMIT_MIN = 1
SEARCH_LIMIT_MAX = 1000
COMMENT_PAGES_MIN = 1
COMMENT_PAGES_MAX = 1000
COMMENT_PAGES_DEFAULT = 100
_COMMENT_PAGE_SIZE = 50
_SEARCH_ALL_PAGE_SIZE = 100
USER_RESULTS_MIN = 1
USER_RESULTS_MAX = 1000
USER_RESULTS_DEFAULT = 50


class IssueRow(TypedDict):
    """A short issue row shared by the JQL text and JSON output."""

    key: str
    status: str | None
    type: str | None
    priority: str | None
    assignee: str | None
    updated: str
    summary: str


class TransitionRow(TypedDict):
    """One workflow transition offered for a Jira issue."""

    id: str
    name: str
    to_status: str | None


class CommentRow(TypedDict):
    """One Jira issue comment reduced to the fields AtlaWire exposes."""

    id: str
    author: str | None
    created: str | None
    updated: str | None
    body: str | None


class CurrentUser(TypedDict):
    """The authenticated caller's three legacy Jira identity fields."""

    name: str
    displayName: str | None
    email: str | None


def _valid_issue_key(value: object) -> TypeGuard[str]:
    """Return whether a value is one syntactically valid Jira issue key."""
    return isinstance(value, str) and re.fullmatch(_ISSUE_KEY, value) is not None


def _issue_key(key_or_url: str) -> str:
    if _valid_issue_key(key_or_url):
        return key_or_url
    message = "Expected a Jira issue key or a Jira browse URL."
    try:
        url = urlsplit(key_or_url)
        if url.scheme in {"http", "https"} and url.hostname:
            match = re.search(rf"/browse/({_ISSUE_KEY})/?\Z", url.path)
            if match:
                return match[1]
    except ValueError:
        raise AtlaWireError(message) from None
    raise AtlaWireError(message)


def get_issue(
    base_url: str,
    key_or_url: str,
    *,
    token: str,
    expand: str = "renderedFields",
    allow_http_loopback: bool = False,
) -> dict[str, object]:
    """Return the Jira issue JSON expanded by ``expand``; rendered fields by default."""
    key = _issue_key(key_or_url)
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    with bearer_session(token) as session:
        issue = get_json_object(
            session,
            f"{base}/rest/api/2/issue/{key}",
            params={"expand": expand},
        )
    # The returned key can legitimately differ from the requested one after a
    # move, so only its own syntax is checked; equality is not pinned.
    if not _valid_issue_key(issue.get("key")) or not isinstance(
        issue.get("fields"), dict
    ):
        raise AtlaWireError("Expected a Jira issue with a key and fields.")
    return issue


def get_issue_worklogs(
    base_url: str,
    key_or_url: str,
    *,
    token: str,
    allow_http_loopback: bool = False,
) -> dict[str, object]:
    """Return one issue's worklog document exactly as the server sent it.

    Only the key is taken from ``key_or_url``; every request goes to the
    configured ``base_url``. ``startAt``, ``maxResults``, ``total``, and every
    worklog row are preserved unchanged, so a capped page stays visible
    instead of being reported as complete. The fixed read is the 8.22
    ``/rest/api/2/issue/{key}/worklog`` endpoint.
    """
    key = _issue_key(key_or_url)
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    with bearer_session(token) as session:
        document = get_json_object(
            session, f"{base}/rest/api/2/issue/{key}/worklog", params={}
        )
    worklogs = document.get("worklogs")
    if not isinstance(worklogs, list):
        raise AtlaWireError("Expected a Jira worklogs array.")
    for value in worklogs:
        _reference_object(value, "worklog")
    return document


def get_issue_changelog(
    base_url: str,
    key_or_url: str,
    *,
    token: str,
    allow_http_loopback: bool = False,
) -> dict[str, object]:
    """Return one issue's changelog document exactly as the server sent it.

    The fixed read is the 8.22 issue endpoint with ``expand=changelog``. Only
    the key is taken from ``key_or_url``; every request goes to the configured
    ``base_url``. The returned document keeps ``startAt``, ``maxResults``,
    ``total``, all histories, and unknown fields unchanged. A capped history
    therefore stays visible instead of being reported as complete.
    """
    key = _issue_key(key_or_url)
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    with bearer_session(token) as session:
        issue = get_json_object(
            session,
            f"{base}/rest/api/2/issue/{key}",
            params={"expand": "changelog"},
        )
    changelog = issue.get("changelog")
    if not isinstance(changelog, dict):
        raise AtlaWireError("Expected a Jira changelog document.")
    histories = changelog.get("histories")
    if not isinstance(histories, list):
        raise AtlaWireError("Expected a Jira changelog histories array.")
    for value in histories:
        _reference_object(value, "change history")
    return changelog


def list_issue_comments(
    base_url: str,
    key_or_url: str,
    *,
    token: str,
    max_pages: int = COMMENT_PAGES_DEFAULT,
    allow_http_loopback: bool = False,
) -> list[CommentRow]:
    """Return every comment of one issue in server order.

    Only the key is taken from ``key_or_url``; every request goes to the
    configured ``base_url``. A page is accepted only when its ``startAt``,
    required ``total``, and nonempty ``maxResults`` agree with the rows read so
    far, so a server cap is followed without skipping comments. Duplicate IDs
    and any metadata drift reject the whole thread; a page cap or HTTP failure
    after valid rows also publishes nothing.
    """
    key = _issue_key(key_or_url)
    _check_comment_pages(max_pages)
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    url = f"{base}/rest/api/2/issue/{key}/comment"
    with bearer_session(token) as session:
        return _read_comments(session, url, max_pages)


def _check_comment_pages(max_pages: int) -> None:
    if (
        not isinstance(max_pages, int)
        or isinstance(max_pages, bool)
        or not COMMENT_PAGES_MIN <= max_pages <= COMMENT_PAGES_MAX
    ):
        raise AtlaWireError(
            "The page limit must be between "
            f"{COMMENT_PAGES_MIN} and {COMMENT_PAGES_MAX}."
        )


def _read_comments(
    session: requests.Session, url: str, max_pages: int
) -> list[CommentRow]:
    rows: list[CommentRow] = []
    seen_ids: set[str] = set()
    start = 0
    total: int | None = None
    for _ in range(max_pages):
        page = get_json_object(
            session,
            url,
            params={"startAt": start, "maxResults": _COMMENT_PAGE_SIZE},
        )
        comments, reported_total = _comment_page(page, start, total)
        total = reported_total
        if not comments:
            return rows
        for value in comments:
            row = _project_comment(value)
            if row["id"] in seen_ids:
                raise AtlaWireError("Jira returned duplicate comment IDs.")
            seen_ids.add(row["id"])
            rows.append(row)
        start += len(comments)
        if start == total:
            return rows
    raise AtlaWireError(
        "Jira comments exceeded the page limit; raise --max-pages or retry."
    )


def _comment_page(
    page: dict[str, object], start: int, expected_total: int | None
) -> tuple[list[object], int]:
    reported_start = page.get("startAt")
    if (
        not isinstance(reported_start, int)
        or isinstance(reported_start, bool)
        or reported_start != start
    ):
        raise AtlaWireError(
            "Expected Jira comments startAt to match the requested offset."
        )
    total = page.get("total")
    if not isinstance(total, int) or isinstance(total, bool) or total < 0:
        raise AtlaWireError("Invalid Jira comments total.")
    if expected_total is not None and total != expected_total:
        raise AtlaWireError("Jira comments total changed between pages.")
    comments = page.get("comments")
    if not isinstance(comments, list):
        raise AtlaWireError("Expected a Jira comments array.")
    if not comments:
        if total != start:
            raise AtlaWireError("Jira comments ended before all comments were read.")
        return comments, total
    advertised = page.get("maxResults")
    if (
        not isinstance(advertised, int)
        or isinstance(advertised, bool)
        or advertised <= 0
    ):
        raise AtlaWireError("Invalid Jira comments maxResults.")
    if len(comments) > advertised:
        raise AtlaWireError("Jira returned more comments than maxResults.")
    if len(comments) > _COMMENT_PAGE_SIZE:
        raise AtlaWireError("Jira returned more comments than requested.")
    if total < start + len(comments):
        raise AtlaWireError("Inconsistent Jira comments pagination metadata.")
    return comments, total


def _project_comment(value: object) -> CommentRow:
    if not isinstance(value, dict):
        raise AtlaWireError("Expected Jira comment objects.")
    comment_id = value.get("id")
    if not isinstance(comment_id, str) or not comment_id.strip():
        raise AtlaWireError("Expected a non-empty Jira comment ID.")
    return CommentRow(
        id=_comment_text(comment_id, "ID"),
        author=_comment_author(value.get("author")),
        created=_optional_comment_text(value.get("created"), "created"),
        updated=_optional_comment_text(value.get("updated"), "updated"),
        body=_optional_comment_text(value.get("body"), "body"),
    )


def _comment_author(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise AtlaWireError("Expected a Jira comment author object.")
    return _optional_comment_text(value.get("name"), "author name")


def _optional_comment_text(value: object, label: str) -> str | None:
    return None if value is None else _comment_text(value, label)


def _comment_text(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise AtlaWireError(f"Expected the Jira comment {label} as text.")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        message = f"Expected the Jira comment {label} as valid UTF-8 text."
        raise AtlaWireError(message) from None
    return value


def search_raw(
    base_url: str,
    jql: str,
    *,
    token: str,
    fields: str = "*all",
    limit: int | None = None,
    start: int = 0,
    expand: str | None = None,
    allow_http_loopback: bool = False,
) -> dict[str, object]:
    """Return one raw ``/rest/api/2/search`` envelope without any projection.

    Exactly one GET is sent: ``limit`` and ``expand`` are omitted when ``None``,
    the body is returned unchanged including unknown keys, and nothing is
    paginated or projected. Every argument is checked before a session exists.
    """
    if not isinstance(jql, str) or not jql.strip():
        raise AtlaWireError("Expected a non-empty JQL query.")
    if not isinstance(fields, str) or not fields.strip():
        raise AtlaWireError("Expected non-empty Jira search fields.")
    if not isinstance(start, int) or isinstance(start, bool) or start < 0:
        raise AtlaWireError("Expected a non-negative Jira search start index.")
    if limit is not None and (
        not isinstance(limit, int)
        or isinstance(limit, bool)
        or not SEARCH_LIMIT_MIN <= limit <= SEARCH_LIMIT_MAX
    ):
        raise AtlaWireError(
            f"The row limit must be between {SEARCH_LIMIT_MIN} and {SEARCH_LIMIT_MAX}."
        )
    if expand is not None and not isinstance(expand, str):
        raise AtlaWireError("Expected the Jira search expand as text.")
    params: dict[str, str | int] = {"jql": jql, "fields": fields, "startAt": start}
    if limit is not None:
        params["maxResults"] = limit
    if expand is not None:
        params["expand"] = expand
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    with bearer_session(token) as session:
        return get_json_object(session, f"{base}/rest/api/2/search", params=params)


def search_issues(
    base_url: str,
    query: str,
    *,
    token: str,
    limit: int = 50,
    allow_http_loopback: bool = False,
) -> list[IssueRow]:
    """Return up to ``limit`` short issue rows in Jira search order.

    Pagination stops only when the requested limit is reached or the response
    metadata proves that no matching issue remains. Any error discards rows
    already read instead of returning a partial result.
    """
    if not query.strip():
        raise AtlaWireError("Expected a non-empty JQL query.")
    if (
        not isinstance(limit, int)
        or isinstance(limit, bool)
        or not SEARCH_LIMIT_MIN <= limit <= SEARCH_LIMIT_MAX
    ):
        raise AtlaWireError(
            f"The row limit must be between {SEARCH_LIMIT_MIN} and {SEARCH_LIMIT_MAX}."
        )
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    url = f"{base}/rest/api/2/search"
    with bearer_session(token) as session:
        return _read_search(session, url, query, limit)


def search_all_issues(
    base_url: str,
    jql: str,
    *,
    token: str,
    fields: str | list[str] = "*all",
    limit: int | None = None,
    allow_http_loopback: bool = False,
) -> list[dict[str, object]]:
    """Return every matching issue object as decoded, or raise with no rows.

    ``jql`` is sent verbatim. ``fields`` is either a string sent verbatim or a
    list joined with commas in the given order; ``limit`` caps the number of
    returned issues and ``None`` means no client-side cap.

    The traversal asks from ``startAt=0`` and advances by the number of issues
    actually read, never by the requested page size. The effective page size
    comes from the ``maxResults`` echo: after a page reports a smaller value,
    later requests ask for no more than that value, up to 100. Reading stops at
    ``limit``, once ``startAt`` reaches the reported ``total``, or at an empty
    page when the response carries no ``total``; an empty page before the
    reported total fails instead of claiming a complete result. ``isLast`` is
    not part of the documented Jira 8.22 search response and is ignored. Every
    issue is returned unchanged, so unknown and nested fields are preserved; no
    projection, deduplication, or extra request is performed.
    """
    if not isinstance(jql, str) or not jql.strip():
        raise AtlaWireError("Expected a non-empty JQL query.")
    selected = _all_search_fields(fields)
    if limit is not None and (
        not isinstance(limit, int) or isinstance(limit, bool) or limit < 1
    ):
        raise AtlaWireError("The issue limit must be a positive integer.")
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    url = f"{base}/rest/api/2/search"
    with bearer_session(token) as session:
        return _read_all_issues(session, url, jql, selected, limit)


def titles(
    base_url: str,
    keys: list[str],
    *,
    token: str,
    allow_http_loopback: bool = False,
) -> dict[str, str]:
    """Map each requested issue key to its Jira summary in input order.

    Parity with ``bbk.jira.titles`` without its SQLite cache: the unique keys
    are split into input-ordered batches of 50, and each batch costs one
    ``key in (...)`` JQL read with ``fields=summary`` and ``maxResults`` equal
    to the batch size, so a long key list never overflows the request URL.
    Keys are validated before a session is created, so an empty request sends
    nothing and an invalid key never reaches the network. Issues the search
    does not return, such as deleted or hidden ones, are omitted instead of
    becoming empty titles.
    """
    if not isinstance(keys, list):
        raise AtlaWireError("Expected the Jira issue keys as a list.")
    for key in keys:
        if not _valid_issue_key(key):
            raise AtlaWireError("Expected a Jira issue key.")
    unique = list(dict.fromkeys(keys))
    if not unique:
        return {}
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    url = f"{base}/rest/api/2/search"
    found: dict[str, str] = {}
    with bearer_session(token) as session:
        # One JQL read per batch of 50; a longer IN list would overflow the URL.
        for start in range(0, len(unique), 50):
            batch = unique[start:start + 50]
            envelope = get_json_object(
                session,
                url,
                params={
                    "jql": "key in (" + ",".join(batch) + ")",
                    "fields": "summary",
                    "maxResults": len(batch),
                },
            )
            issues = envelope.get("issues")
            if not isinstance(issues, list):
                raise AtlaWireError("Expected a Jira search issues array.")
            for issue in issues:
                if not isinstance(issue, dict):
                    raise AtlaWireError("Expected Jira issue objects in search results.")
                key = issue.get("key")
                if not _valid_issue_key(key):
                    raise AtlaWireError("Expected valid Jira issue keys in search results.")
                fields = issue.get("fields")
                summary = fields.get("summary") if isinstance(fields, dict) else None
                if not isinstance(summary, str):
                    raise AtlaWireError("Expected Jira issue summaries in search results.")
                found[key] = summary
    return {key: found[key] for key in unique if key in found}


def _check_status_name(status: str) -> None:
    """Reject characters that a quoted JQL literal cannot represent safely.

    Status names are always inserted as one double-quoted literal. Quotes,
    backslashes, raw controls, and lone surrogates have no proven escape
    grammar here, so they fail instead of being passed through. The message is
    static and never echoes the requested value.
    """
    for char in status:
        code = ord(char)
        if (
            char in {'"', "\\"}
            or code < 0x20
            or 0x7F <= code <= 0x9F
            or code in {0x2028, 0x2029}
            or 0xD800 <= code <= 0xDFFF
        ):
            raise AtlaWireError(
                "Unsupported status name; use plain text without quotes, "
                "backslashes, or control characters."
            )


def list_my_issues(
    base_url: str,
    *,
    token: str,
    status: str | None = None,
    limit: int = 50,
    allow_http_loopback: bool = False,
) -> list[IssueRow]:
    """Return the caller's open issues, optionally narrowed to one status name.

    A non-empty ``status`` is quoted as a literal JQL string; an empty value
    selects every issue whose status category is not Done. The fixed query is
    passed to :func:`search_issues`, so pagination and limits are identical.
    """
    if status is not None and not isinstance(status, str):
        raise AtlaWireError("Expected the status name as text.")
    if status:
        _check_status_name(status)
        query = (
            f'assignee = currentUser() AND status = "{status}" ORDER BY updated DESC'
        )
    else:
        query = _MY_ISSUES_QUERY
    return search_issues(
        base_url,
        query,
        token=token,
        limit=limit,
        allow_http_loopback=allow_http_loopback,
    )


def list_statuses(
    base_url: str,
    *,
    token: str,
    allow_http_loopback: bool = False,
) -> list[str]:
    """Return the sorted unique status names visible on the configured instance.

    Jira Server and Data Center expose the instance-wide status list at
    ``/rest/api/2/status``. The complete response is validated before anything
    is returned, so a malformed late entry cannot yield a partial list.
    """
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    with bearer_session(token) as session:
        values = get_json_array(session, f"{base}/rest/api/2/status", params={})
    names: list[str] = []
    for value in values:
        if not isinstance(value, dict):
            raise AtlaWireError("Expected Jira status objects.")
        name = value.get("name")
        if not isinstance(name, str) or not name:
            raise AtlaWireError("Expected Jira statuses with non-empty names.")
        if any(0xD800 <= ord(char) <= 0xDFFF for char in name):
            raise AtlaWireError("Expected Jira statuses with valid Unicode names.")
        names.append(name)
    return sorted(set(names))


def list_priorities(
    base_url: str,
    *,
    token: str,
    allow_http_loopback: bool = False,
) -> list[dict[str, object]]:
    """Return every Jira priority exactly as the server sent it.

    Jira Server and Data Center expose the instance-wide priority list at
    ``/rest/api/2/priority``. Each row is a complete server object, including
    unknown and nested fields, and is returned unchanged.
    """
    return _read_reference_list(
        base_url,
        token=token,
        path="/rest/api/2/priority",
        label="priority",
        allow_http_loopback=allow_http_loopback,
    )


def list_resolutions(
    base_url: str,
    *,
    token: str,
    allow_http_loopback: bool = False,
) -> list[dict[str, object]]:
    """Return every Jira resolution exactly as the server sent it.

    The fixed read is ``/rest/api/2/resolution``. Each row is returned
    unchanged, so unknown and nested fields survive.
    """
    return _read_reference_list(
        base_url,
        token=token,
        path="/rest/api/2/resolution",
        label="resolution",
        allow_http_loopback=allow_http_loopback,
    )


def list_issue_types(
    base_url: str,
    *,
    token: str,
    allow_http_loopback: bool = False,
) -> list[dict[str, object]]:
    """Return every visible Jira issue type exactly as the server sent it.

    The fixed read is ``/rest/api/2/issuetype``. Rows are not filtered by
    subtask status and are returned unchanged.
    """
    return _read_reference_list(
        base_url,
        token=token,
        path="/rest/api/2/issuetype",
        label="issue type",
        allow_http_loopback=allow_http_loopback,
    )


def list_status_categories(
    base_url: str,
    *,
    token: str,
    allow_http_loopback: bool = False,
) -> list[dict[str, object]]:
    """Return every visible Jira status category exactly as sent.

    The fixed read is ``/rest/api/2/statuscategory``. Rows are returned
    unchanged; no status is derived from a category.
    """
    return _read_reference_list(
        base_url,
        token=token,
        path="/rest/api/2/statuscategory",
        label="status category",
        allow_http_loopback=allow_http_loopback,
    )


def list_jira_projects(
    base_url: str,
    *,
    token: str,
    allow_http_loopback: bool = False,
) -> list[dict[str, object]]:
    """Return the visible Jira project array exactly as the server sent it.

    The fixed 8.22 read is ``/rest/api/2/project``. Every row is returned
    unchanged, including unknown and nested fields. This response carries no
    pagination metadata, so the client cannot prove that no further visible
    project exists; a short array is not a completeness claim.
    """
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    with bearer_session(token) as session:
        values = get_json_array(session, f"{base}/rest/api/2/project", params={})
    return [_reference_object(value, "project") for value in values]


def _read_reference_list(
    base_url: str,
    *,
    token: str,
    path: str,
    label: str,
    allow_http_loopback: bool,
) -> list[dict[str, object]]:
    """Read one fixed reference endpoint and validate every row before returning."""
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    with bearer_session(token) as session:
        values = get_json_array(session, f"{base}{path}", params={})
    return [_reference_object(value, label) for value in values]


def _reference_object(value: object, label: str) -> dict[str, object]:
    """Return one consumed server object without dropping or coercing fields."""
    if not isinstance(value, dict):
        raise AtlaWireError(f"Expected Jira {label} objects.")
    return value


def search_users(
    base_url: str,
    username: str,
    *,
    token: str,
    start_at: int = 0,
    max_results: int = USER_RESULTS_DEFAULT,
    allow_http_loopback: bool = False,
) -> list[dict[str, object]]:
    """Return one bounded page of Jira users matching ``username``.

    The Jira 8.22 ``/rest/user/search`` endpoint takes a non-empty
    ``username`` substring and returns a bare array, not a paged envelope.
    Only the requested page is read; an empty or full page never proves that
    no further matching users exist. Inactive users are excluded by the
    server default. Raw user objects are returned unchanged. A page longer
    than ``max_results`` is rejected instead of being returned.
    """
    _check_user_search(username, start_at, max_results)
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    with bearer_session(token) as session:
        values = get_json_array(
            session,
            f"{base}/rest/api/2/user/search",
            params={
                "username": username,
                "startAt": start_at,
                "maxResults": max_results,
            },
        )
    if len(values) > max_results:
        raise AtlaWireError("Jira returned more users than maxResults.")
    return [_reference_object(value, "user") for value in values]


def _check_user_search(username: object, start_at: object, max_results: object) -> None:
    """Reject unusable user search input before a session or request exists."""
    if not isinstance(username, str) or not username.strip():
        raise AtlaWireError("Expected non-empty Jira user search text.")
    try:
        username.encode("utf-8")
    except UnicodeEncodeError:
        raise AtlaWireError(
            "Expected the Jira user search text as valid UTF-8."
        ) from None
    if not isinstance(start_at, int) or isinstance(start_at, bool) or start_at < 0:
        raise AtlaWireError("Expected a non-negative Jira user search start index.")
    if (
        not isinstance(max_results, int)
        or isinstance(max_results, bool)
        or not USER_RESULTS_MIN <= max_results <= USER_RESULTS_MAX
    ):
        raise AtlaWireError(
            "The Jira user result limit must be between "
            f"{USER_RESULTS_MIN} and {USER_RESULTS_MAX}."
        )


def list_transitions(
    base_url: str,
    key_or_url: str,
    *,
    token: str,
    allow_http_loopback: bool = False,
) -> list[TransitionRow]:
    """Return the workflow transitions offered for one issue in server order.

    Only the key is taken from ``key_or_url``; every request goes to the
    configured ``base_url``. The complete response is validated before anything
    is returned, so a malformed late entry cannot yield a partial list. No
    permission or target-status meaning is inferred beyond the returned fields.
    """
    key = _issue_key(key_or_url)
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    with bearer_session(token) as session:
        envelope = get_json_object(
            session, f"{base}/rest/api/2/issue/{key}/transitions", params={}
        )
    values = envelope.get("transitions")
    if not isinstance(values, list):
        raise AtlaWireError("Expected a Jira transitions array.")
    return [_project_transition(value) for value in values]


def _project_transition(value: object) -> TransitionRow:
    """Project one consumed transition, rejecting wrong shapes without coercion."""
    if not isinstance(value, dict):
        raise AtlaWireError("Expected Jira transition objects.")
    return TransitionRow(
        id=_transition_text(value.get("id"), "ID"),
        name=_transition_text(value.get("name"), "name"),
        to_status=_transition_status(value.get("to")),
    )


def _transition_status(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise AtlaWireError("Expected a Jira transition target object.")
    name = value.get("name")
    return None if name is None else _transition_string(name, "target status")


def _transition_text(value: object, label: str) -> str:
    """Return one required field as non-blank text that UTF-8 output can encode."""
    if not isinstance(value, str) or not value.strip():
        raise AtlaWireError(f"Expected a Jira transition {label} as non-empty text.")
    return _transition_string(value, label)


def _transition_string(value: object, label: str) -> str:
    """Return one consumed text field unchanged, including empty or whitespace."""
    if not isinstance(value, str):
        raise AtlaWireError(f"Expected a Jira transition {label} as text.")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        message = f"Expected a Jira transition {label} as valid UTF-8 text."
        raise AtlaWireError(message) from None
    return value


def list_issue_remote_links(
    base_url: str,
    key_or_url: str,
    *,
    token: str,
    allow_http_loopback: bool = False,
) -> list[dict[str, object]]:
    """Return every remote link of one issue exactly as the server sent it.

    Only the key is taken from ``key_or_url``; every request goes to the
    configured ``base_url``, including when the pasted browse URL names another
    host. The complete array is validated before anything is returned, so a
    malformed late entry cannot yield a partial list. Nested values, unknown
    fields, and ``null`` are preserved; returned URLs are data, never
    destinations, so they are not fetched.
    """
    key = _issue_key(key_or_url)
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    with bearer_session(token) as session:
        values = get_json_array(
            session, f"{base}/rest/api/2/issue/{key}/remotelink", params={}
        )
    return [_project_remote_link(value) for value in values]


def _project_remote_link(value: object) -> dict[str, object]:
    """Return one consumed link object without dropping, adding, or coercing it."""
    if not isinstance(value, dict):
        raise AtlaWireError("Expected Jira remote link objects.")
    return value


def get_current_user(
    base_url: str,
    *,
    token: str,
    allow_http_loopback: bool = False,
) -> CurrentUser:
    """Return the caller's legacy identity fields from the configured instance.

    The ``/myself`` user object is reduced to ``name``, ``displayName``, and
    ``emailAddress`` exposed as ``email``. Every other field is ignored, so the
    result carries no links, account IDs, or permission claims, and it never
    implies that the caller is anonymous or authorized.
    """
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    with bearer_session(token) as session:
        user = get_json_object(session, f"{base}/rest/api/2/myself", params={})
    return _project_current_user(user)


def _project_current_user(value: dict[str, object]) -> CurrentUser:
    """Project the identity fields, rejecting blank names and unprintable text."""
    name = _user_text(value.get("name"), "name")
    if not name.strip():
        raise AtlaWireError("Expected a Jira user with a non-empty name.")
    return CurrentUser(
        name=name,
        displayName=_optional_user_text(value.get("displayName"), "display name"),
        email=_optional_user_text(value.get("emailAddress"), "email"),
    )


def _optional_user_text(value: object, label: str) -> str | None:
    return None if value is None else _user_text(value, label)


def _user_text(value: object, label: str) -> str:
    """Return one consumed field as text that UTF-8 output can represent."""
    if not isinstance(value, str):
        raise AtlaWireError(f"Invalid Jira user {label}.")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        message = f"The Jira user {label} must be valid UTF-8 text."
        raise AtlaWireError(message) from None
    return value


def _read_search(
    session: requests.Session, url: str, query: str, limit: int
) -> list[IssueRow]:
    rows: list[IssueRow] = []
    seen_keys: set[str] = set()
    known_total: int | None = None
    while len(rows) < limit:
        start = len(rows)
        requested = limit - start
        page = get_json_object(
            session,
            url,
            params={
                "jql": query,
                "fields": _SEARCH_FIELDS,
                "startAt": start,
                "maxResults": requested,
            },
        )
        issues, reported_total = _search_page(page, start)
        if reported_total is not None:
            # A page may omit the total, but a known total is never forgotten
            # and a different later value proves the result set is unstable.
            if known_total is not None and reported_total != known_total:
                raise AtlaWireError("Jira search total changed between pages.")
            known_total = reported_total
        if known_total is not None and start + len(issues) > known_total:
            raise AtlaWireError("Inconsistent Jira search pagination metadata.")
        if not issues:
            _check_search_end(start, known_total)
            return rows
        # A server cap can return fewer rows than requested, so advance by what
        # was actually read; every continuing page adds at least one row. Rows
        # beyond the requested cap are deliberately discarded, so duplicate
        # keys are checked only for rows accepted into the result.
        for issue in issues[:requested]:
            row = _project_issue(issue)
            if row["key"] in seen_keys:
                raise AtlaWireError("Jira search returned duplicate issue keys.")
            seen_keys.add(row["key"])
            rows.append(row)
        if len(rows) == known_total:
            return rows
    return rows


def _check_search_end(offset: int, known_total: int | None) -> None:
    if known_total is None:
        raise AtlaWireError(
            "Jira search ended without a total; narrow the query or retry."
        )
    if known_total > offset:
        raise AtlaWireError(
            "Jira search returned an empty page before all matches; "
            "narrow the query or retry."
        )


def _search_page(
    page: dict[str, object], start: int
) -> tuple[list[object], int | None]:
    reported_start = page.get("startAt")
    if (
        not isinstance(reported_start, int)
        or isinstance(reported_start, bool)
        or reported_start != start
    ):
        raise AtlaWireError(
            "Expected Jira search startAt to match the requested offset."
        )
    issues = page.get("issues")
    if not isinstance(issues, list):
        raise AtlaWireError("Expected a Jira search issues array.")
    total = page.get("total")
    if total is not None and (
        not isinstance(total, int) or isinstance(total, bool) or total < 0
    ):
        raise AtlaWireError("Invalid Jira search total.")
    if issues:
        advertised = page.get("maxResults")
        if (
            not isinstance(advertised, int)
            or isinstance(advertised, bool)
            or advertised <= 0
        ):
            raise AtlaWireError("Invalid Jira search maxResults.")
        if len(issues) > advertised:
            raise AtlaWireError("Jira search returned more issues than maxResults.")
        if total is not None and total < start + len(issues):
            raise AtlaWireError("Inconsistent Jira search pagination metadata.")
    return issues, total


def _all_search_fields(fields: str | list[str]) -> str:
    """Return the ``fields`` query value, rejecting empty selections."""
    if isinstance(fields, str):
        if not fields.strip():
            raise AtlaWireError("Expected non-empty Jira search fields.")
        return fields
    if not isinstance(fields, list) or not fields:
        raise AtlaWireError("Expected Jira search fields as a non-empty list.")
    for field in fields:
        if not isinstance(field, str) or not field.strip():
            raise AtlaWireError("Expected non-empty Jira search fields.")
    return ",".join(fields)


def _read_all_issues(
    session: requests.Session,
    url: str,
    query: str,
    fields: str,
    limit: int | None,
) -> list[dict[str, object]]:
    """Page the JQL search and return every raw issue object in order."""
    rows: list[dict[str, object]] = []
    start = 0
    page_size = _SEARCH_ALL_PAGE_SIZE
    while True:
        remaining = None if limit is None else limit - len(rows)
        size = page_size if remaining is None else min(page_size, remaining)
        page = get_json_object(
            session,
            url,
            params={
                "jql": query,
                "fields": fields,
                "startAt": start,
                "maxResults": size,
            },
        )
        issues, total, advertised = _all_issues_page(
            page, start=start, requested=size
        )
        if advertised is not None:
            page_size = min(advertised, _SEARCH_ALL_PAGE_SIZE)
        if total is not None and start + len(issues) > total:
            raise AtlaWireError("Inconsistent Jira search pagination metadata.")
        rows.extend(issues)
        if limit is not None and len(rows) >= limit:
            return rows
        if not issues:
            if total is None:
                return rows
            _check_search_end(start, total)
            return rows
        if total is not None and start + len(issues) >= total:
            return rows
        start += len(issues)


def _all_issues_page(
    page: dict[str, object], *, start: int, requested: int
) -> tuple[list[dict[str, object]], int | None, int | None]:
    """Validate one page and return its issues, total, and page size."""
    reported_start = page.get("startAt")
    if reported_start is not None and (
        not isinstance(reported_start, int)
        or isinstance(reported_start, bool)
        or reported_start != start
    ):
        raise AtlaWireError(
            "Expected Jira search startAt to match the requested offset."
        )
    issues = page.get("issues")
    if not isinstance(issues, list):
        raise AtlaWireError("Expected a Jira search issues array.")
    total = page.get("total")
    if total is not None and (
        not isinstance(total, int) or isinstance(total, bool) or total < 0
    ):
        raise AtlaWireError("Invalid Jira search total.")
    advertised = page.get("maxResults")
    if advertised is not None and (
        not isinstance(advertised, int)
        or isinstance(advertised, bool)
        or advertised <= 0
    ):
        raise AtlaWireError("Invalid Jira search maxResults.")
    if len(issues) > requested or (
        advertised is not None and len(issues) > advertised
    ):
        raise AtlaWireError("Jira search returned more issues than requested.")
    rows: list[dict[str, object]] = []
    for issue in issues:
        if not isinstance(issue, dict):
            raise AtlaWireError(
                "Expected Jira issue objects in search results."
            )
        rows.append(issue)
    return rows, total, advertised


def _search_text(value: str, label: str) -> str:
    """Return projected search text unchanged only when UTF-8 can encode it."""
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        message = f"Expected Jira {label} as valid UTF-8 text in search results."
        raise AtlaWireError(message) from None
    return value


def _nested_name(value: object, label: str, property_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise AtlaWireError(f"Invalid Jira {label} in search results.")
    name = value.get(property_name)
    if name is None:
        return None
    if not isinstance(name, str):
        raise AtlaWireError(f"Invalid Jira {label} in search results.")
    return _search_text(name, label)


def _project_issue(value: object) -> IssueRow:
    if not isinstance(value, dict):
        raise AtlaWireError("Expected a Jira issue object in search results.")
    key = value.get("key")
    if not _valid_issue_key(key):
        raise AtlaWireError("Expected a valid Jira issue key in search results.")
    fields = value.get("fields")
    if not isinstance(fields, dict):
        raise AtlaWireError("Expected Jira issue fields in search results.")
    summary_value = fields.get("summary")
    if summary_value is None:
        summary = ""
    elif isinstance(summary_value, str):
        summary = _search_text(" ".join(summary_value.split()), "summary")
    else:
        raise AtlaWireError("Invalid Jira summary in search results.")
    updated_value = fields.get("updated")
    if updated_value is None:
        updated = ""
    elif isinstance(updated_value, str):
        updated = _search_text(updated_value[:10], "updated timestamp")
    else:
        raise AtlaWireError("Invalid Jira updated timestamp in search results.")
    return IssueRow(
        key=key,
        status=_nested_name(fields.get("status"), "status", "name"),
        type=_nested_name(fields.get("issuetype"), "type", "name"),
        priority=_nested_name(fields.get("priority"), "priority", "name"),
        assignee=_nested_name(fields.get("assignee"), "assignee", "displayName"),
        updated=updated,
        summary=summary,
    )
