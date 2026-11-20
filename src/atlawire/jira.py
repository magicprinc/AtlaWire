"""Read operations for self-hosted Jira."""

import re
from typing import TypedDict
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


def _issue_key(key_or_url: str) -> str:
    if re.fullmatch(_ISSUE_KEY, key_or_url):
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
    allow_http_loopback: bool = False,
) -> dict[str, object]:
    """Return the Jira issue JSON with rendered fields from the configured instance."""
    key = _issue_key(key_or_url)
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    with bearer_session(token) as session:
        issue = get_json_object(
            session,
            f"{base}/rest/api/2/issue/{key}",
            params={"expand": "renderedFields"},
        )
    returned_key = issue.get("key")
    if not isinstance(returned_key, str) or not isinstance(issue.get("fields"), dict):
        raise AtlaWireError("Expected a Jira issue with a key and fields.")
    return issue


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
    start = 0
    while len(rows) < limit:
        requested = limit - len(rows)
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
        issues, total = _search_page(page, start)
        if not issues:
            # An empty page proves exhaustion only when total is known and
            # already accounts for everything read so far.
            if total is None:
                raise AtlaWireError(
                    "Jira search ended without a total; narrow the query or retry."
                )
            if total > start:
                raise AtlaWireError(
                    "Jira search returned an empty page before all matches; "
                    "narrow the query or retry."
                )
            return rows
        # A server cap can return fewer rows than requested, so advance by what
        # was actually read; every continuing page adds at least one row.
        take = min(len(issues), requested)
        rows.extend(_project_issue(issue) for issue in issues[:take])
        start += take
        if total is not None and start >= total:
            return rows
    return rows


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
    return name


def _project_issue(value: object) -> IssueRow:
    if not isinstance(value, dict):
        raise AtlaWireError("Expected a Jira issue object in search results.")
    key = value.get("key")
    if not isinstance(key, str) or not key:
        raise AtlaWireError("Expected a non-empty Jira issue key in search results.")
    fields = value.get("fields")
    if not isinstance(fields, dict):
        raise AtlaWireError("Expected Jira issue fields in search results.")
    summary_value = fields.get("summary")
    if summary_value is None:
        summary = ""
    elif isinstance(summary_value, str):
        summary = " ".join(summary_value.split())
    else:
        raise AtlaWireError("Invalid Jira summary in search results.")
    updated_value = fields.get("updated")
    if updated_value is None:
        updated = ""
    elif isinstance(updated_value, str):
        updated = updated_value[:10]
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
