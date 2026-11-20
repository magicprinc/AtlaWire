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


class IssueRow(TypedDict):
    """A short issue row shared by the JQL text and JSON output."""

    key: str
    status: str | None
    type: str | None
    priority: str | None
    assignee: str | None
    updated: str
    summary: str


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
