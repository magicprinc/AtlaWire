"""Read operations for self-hosted Jira."""

import re
from typing import TypedDict, TypeGuard
from urllib.parse import quote, unquote, urlsplit

import requests

from atlawire.http import (
    AtlaWireError,
    bearer_session,
    get_json_array,
    get_json_object,
    normalize_base_url,
)
from atlawire.issue_markdown import render_issue_markdown

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
COMMENT_LIMIT_MIN = 1
COMMENT_LIMIT_MAX = 1000
_COMMENT_PAGE_SIZE = 50
_SEARCH_ALL_PAGE_SIZE = 100
_WORKLOG_PAGE_SIZE = 50
WORKLOG_PAGES_MIN = 1
WORKLOG_PAGES_MAX = 1000
WORKLOG_PAGES_DEFAULT = 100
USER_RESULTS_MIN = 1
USER_RESULTS_MAX = 1000
USER_RESULTS_DEFAULT = 50
_JIRA_ID_MAX = 2**63 - 1
_PROPERTY_KEY_MAX = 255


class IssueRow(TypedDict):
    """A short issue row shared by the JQL text and JSON output."""

    key: str
    status: str | None
    type: str | None
    priority: str | None
    assignee: str | None
    updated: str
    summary: str


class IssueSearchMetadata(TypedDict):
    """Результат поиска задач с признаком неполноты и заявленным ``total``.

    ``truncated`` истинно, когда выдача заведомо или возможно урезана:
    известный ``total`` больше ``rows`` либо сервер не сообщил ``total``, а
    лимит достигнут. ``total`` — последнее значение, которое прислал сервер;
    ``None`` означает, что сервер его не сообщил.
    """

    rows: list[IssueRow]
    truncated: bool
    total: int | None


class RawIssueSearchMetadata(TypedDict):
    """Сырые задачи Jira с тем же признаком неполноты, что у IssueSearchMetadata."""

    rows: list[dict[str, object]]
    truncated: bool
    total: int | None


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


class CommentThreadMetadata(TypedDict):
    """Комментарии задачи вместе с признаком неполноты и заявленным ``total``.

    ``truncated`` истинно, когда ``limit`` остановил чтение раньше известного
    ``total``, поэтому урезанная выдача не выглядит полной. ``total`` —
    последнее значение, которое прислал сервер; тред без страниц считается
    пустым и полным.
    """

    rows: list[CommentRow]
    truncated: bool
    total: int


class CurrentUser(TypedDict):
    """The authenticated caller's three legacy Jira identity fields."""

    name: str
    displayName: str | None
    email: str | None


class UserRefRow(TypedDict):
    """Краткая ссылка на пользователя Jira: логин и отображаемое имя."""

    name: str
    displayName: str | None


class IssueVotes(TypedDict):
    """Проекция голосов за задачу: список, свой голос и счётчик."""

    voters: list[UserRefRow]
    hasVoted: bool | None
    watchCount: int | None


class IssueWatchers(TypedDict):
    """Проекция наблюдателей задачи: список, счётчик и свой флаг."""

    watchers: list[UserRefRow]
    watchCount: int | None
    isWatching: bool | None


class SubtaskRow(TypedDict):
    """Одна подзадача: ключ, краткое описание, тип и статус."""

    key: str
    summary: str | None
    type: str | None
    status: str | None


class WorklogRow(TypedDict):
    """Одна запись о трудозатратах задачи."""

    id: str
    author: str | None
    started: str | None
    seconds: int | None
    comment: str | None


class IssueLinkRow(TypedDict):
    """Одна связь задач: тип и ключи обеих сторон."""

    id: str
    type: str | None
    inwardIssue: str | None
    outwardIssue: str | None


class IssuePropertyKeys(TypedDict):
    """Имена свойств задачи; значения читаются по одному ключу."""

    keys: list[str]


class IssueProperty(TypedDict):
    """Одно свойство задачи: ключ и произвольное значение сервера."""

    key: str
    value: object


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
    expand: str | None = "renderedFields",
    fields: str | None = None,
    properties: str | None = None,
    update_history: bool = False,
    fail_fast: bool = False,
    allow_http_loopback: bool = False,
) -> dict[str, object]:
    """Return the Jira issue JSON expanded by ``expand``; rendered fields by default.

    ``fields`` and ``properties`` are sent verbatim when given. ``expand=None``
    omits the parameter, so the server's own default applies; the default
    ``"renderedFields"`` is this library's choice, not Jira's. ``update_history``
    and ``fail_fast`` are sent as ``true`` only when requested, so a default call
    keeps the server's own defaults instead of pinning them.
    """
    key = _issue_key(key_or_url)
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    params: dict[str, str] = {} if expand is None else {"expand": expand}
    if fields is not None:
        params["fields"] = fields
    if properties is not None:
        params["properties"] = properties
    if update_history:
        params["updateHistory"] = "true"
    if fail_fast:
        params["failFast"] = "true"
    with bearer_session(token, product="jira") as session:
        issue = get_json_object(
            session,
            f"{base}/rest/api/2/issue/{key}",
            params=params,
        )
    # The returned key can legitimately differ from the requested one after a
    # move, so only its own syntax is checked; equality is not pinned.
    if not _valid_issue_key(issue.get("key")) or not isinstance(
        issue.get("fields"), dict
    ):
        raise AtlaWireError("Expected a Jira issue with a key and fields.")
    return issue


def issue_url(base_url: str, key_or_url: str) -> str:
    """Return the browser URL of one Jira issue without making a request.

    ``base_url`` is normalized with the shared rules, so a deployment context
    path such as ``/jira`` is preserved. ``key_or_url`` accepts a bare key or a
    browse/API URL; only its key is used, and the destination always comes from
    the supplied base URL, never from the argument.
    """
    key = _issue_key(key_or_url)
    base = normalize_base_url(base_url, allow_http_loopback=False)
    return f"{base}/browse/{key}"


def get_issue_markdown(
    base_url: str,
    key_or_url: str,
    *,
    token: str,
    use_wiki: bool = False,
    allow_http_loopback: bool = False,
) -> str:
    """Fetch one issue and render it as Markdown in a single call.

    Reads the issue through [get_issue][atlawire.jira.get_issue] with rendered
    fields and renders it with
    [render_issue_markdown][atlawire.issue_markdown.render_issue_markdown].
    ``use_wiki=True`` renders the raw wiki markup instead. No second request is
    made and nothing is fetched.
    """
    issue = get_issue(
        base_url,
        key_or_url,
        token=token,
        allow_http_loopback=allow_http_loopback,
    )
    return render_issue_markdown(issue, use_wiki=use_wiki)


class IssueForms(TypedDict):
    """One issue in three forms, all from a single read."""

    document: dict[str, object]
    markdown: str
    wiki_markdown: str


def issue_forms(
    base_url: str,
    key_or_url: str,
    *,
    token: str,
    allow_http_loopback: bool = False,
) -> IssueForms:
    """Return one issue as JSON, rendered Markdown, and wiki Markdown in one call.

    Exactly one GET reads the issue with rendered fields; every form is
    rendered from that document, so a caller does not pay three requests.
    """
    issue = get_issue(
        base_url,
        key_or_url,
        token=token,
        allow_http_loopback=allow_http_loopback,
    )
    return IssueForms(
        document=issue,
        markdown=render_issue_markdown(issue),
        wiki_markdown=render_issue_markdown(issue, use_wiki=True),
    )


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
    ``/rest/api/2/issue/{key}/worklog`` endpoint. Use
    :func:`list_issue_worklogs` for a validated full traversal with a budget.
    """
    key = _issue_key(key_or_url)
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    with bearer_session(token, product="jira") as session:
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
    therefore stays visible instead of being reported as complete. Use
    :func:`list_issue_changelog` for the complete history or an explicit
    truncation error.
    """
    key = _issue_key(key_or_url)
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    with bearer_session(token, product="jira") as session:
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


def list_issue_worklogs(
    base_url: str,
    key_or_url: str,
    *,
    token: str,
    max_pages: int = WORKLOG_PAGES_DEFAULT,
    allow_http_loopback: bool = False,
) -> list[dict[str, object]]:
    """Вернуть все записи о трудозатратах задачи или явно сообщить об обрезке.

    Читается ``GET /rest/api/2/issue/{key}/worklog`` со смещением ``startAt``:
    обход идёт, пока прочитанные строки не покроют заявленный ``total``,
    поэтому неполная выдача не возвращается молча. ``max_pages`` ограничивает
    число запросов (1..1000, по умолчанию 100); исчерпанный бюджет —
    ``AtlaWireError``, а не частичный список. Каждая страница проверяется до
    публикации: ``startAt`` должен совпасть с запрошенным, ``total`` — не
    меняться, строк не больше ``maxResults`` и запрошенного размера. Сервер,
    игнорирующий ``startAt`` (таков проверенный 8.22.2), отвергается по
    несовпадению эха, а не превращается в тихий повтор первой страницы. Строки
    возвращаются как пришли, включая неизвестные поля.
    """
    key = _issue_key(key_or_url)
    _check_worklog_pages(max_pages)
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    url = f"{base}/rest/api/2/issue/{key}/worklog"
    with bearer_session(token, product="jira") as session:
        return _read_worklogs(session, url, max_pages)


def _check_worklog_pages(max_pages: int) -> None:
    if (
        not isinstance(max_pages, int)
        or isinstance(max_pages, bool)
        or not WORKLOG_PAGES_MIN <= max_pages <= WORKLOG_PAGES_MAX
    ):
        raise AtlaWireError(
            "The page limit must be between "
            f"{WORKLOG_PAGES_MIN} and {WORKLOG_PAGES_MAX}."
        )


def _read_worklogs(
    session: requests.Session, url: str, max_pages: int
) -> list[dict[str, object]]:
    """Прочитать все страницы worklog и вернуть строки без потерь."""
    rows: list[dict[str, object]] = []
    seen_ids: set[str] = set()
    start = 0
    total: int | None = None
    for _ in range(max_pages):
        page = get_json_object(
            session,
            url,
            params={"startAt": start, "maxResults": _WORKLOG_PAGE_SIZE},
        )
        worklogs, reported_total = _worklog_page(page, start, total)
        total = reported_total
        if not worklogs:
            return rows
        for value in worklogs:
            row = _reference_object(value, "worklog")
            row_id = row.get("id")
            if isinstance(row_id, str):
                if row_id in seen_ids:
                    raise AtlaWireError("Jira returned duplicate worklog IDs.")
                seen_ids.add(row_id)
            rows.append(row)
        start += len(worklogs)
        if start == total:
            return rows
    raise AtlaWireError(
        "Jira worklogs exceeded the page limit; raise max_pages or retry."
    )


def _worklog_page(
    page: dict[str, object], start: int, expected_total: int | None
) -> tuple[list[object], int]:
    """Проверить одну страницу worklog и вернуть её строки и общий ``total``."""
    reported_start = page.get("startAt")
    if (
        not isinstance(reported_start, int)
        or isinstance(reported_start, bool)
        or reported_start != start
    ):
        raise AtlaWireError(
            "Expected Jira worklogs startAt to match the requested offset."
        )
    total = page.get("total")
    if not isinstance(total, int) or isinstance(total, bool) or total < 0:
        raise AtlaWireError("Invalid Jira worklogs total.")
    if expected_total is not None and total != expected_total:
        raise AtlaWireError("Jira worklogs total changed between pages.")
    worklogs = page.get("worklogs")
    if not isinstance(worklogs, list):
        raise AtlaWireError("Expected a Jira worklogs array.")
    if not worklogs:
        if total != start:
            raise AtlaWireError("Jira worklogs ended before all worklogs were read.")
        return worklogs, total
    advertised = page.get("maxResults")
    if (
        not isinstance(advertised, int)
        or isinstance(advertised, bool)
        or advertised <= 0
    ):
        raise AtlaWireError("Invalid Jira worklogs maxResults.")
    if len(worklogs) > advertised:
        raise AtlaWireError("Jira returned more worklogs than maxResults.")
    if len(worklogs) > _WORKLOG_PAGE_SIZE:
        raise AtlaWireError("Jira returned more worklogs than requested.")
    if total < start + len(worklogs):
        raise AtlaWireError("Inconsistent Jira worklogs pagination metadata.")
    return worklogs, total


def list_issue_changelog(
    base_url: str,
    key_or_url: str,
    *,
    token: str,
    allow_http_loopback: bool = False,
) -> list[dict[str, object]]:
    """Вернуть полную историю changelog задачи или явно сообщить об обрезке.

    Читается ``GET /rest/api/2/issue/{key}?expand=changelog``. На проверенном
    8.22.2 этот ответ содержит всю историю (``maxResults`` равен ``total``), а
    отдельного ресурса пагинации changelog у этой версии нет
    (``/rest/api/2/issue/{key}/changelog`` отвечает 404). Поэтому неполная
    страница не выдаётся как результат: если ``total`` больше числа
    ``histories``, поднимается ``AtlaWireError`` с обоими числами. Полная
    история возвращается как пришла, включая неизвестные поля.
    """
    key = _issue_key(key_or_url)
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    with bearer_session(token, product="jira") as session:
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
    total = changelog.get("total")
    if not isinstance(total, int) or isinstance(total, bool) or total < 0:
        raise AtlaWireError("Invalid Jira changelog total.")
    reported_start = changelog.get("startAt")
    if reported_start is not None and (
        not isinstance(reported_start, int)
        or isinstance(reported_start, bool)
        or reported_start != 0
    ):
        raise AtlaWireError("Expected Jira changelog startAt to be zero.")
    if len(histories) > total:
        raise AtlaWireError("Inconsistent Jira changelog pagination metadata.")
    if len(histories) < total:
        raise AtlaWireError(
            "Jira returned an incomplete changelog: "
            f"{len(histories)} of {total} histories; "
            "this Jira version offers no changelog paging endpoint."
        )
    return [_reference_object(value, "change history") for value in histories]


def list_issue_comments(
    base_url: str,
    key_or_url: str,
    *,
    token: str,
    limit: int | None = None,
    max_pages: int = COMMENT_PAGES_DEFAULT,
    allow_http_loopback: bool = False,
) -> list[CommentRow]:
    """Return at most ``limit`` comments of one issue in server order.

    Only the key is taken from ``key_or_url``; every request goes to the
    configured ``base_url``. A page is accepted only when its ``startAt``,
    required ``total``, and nonempty ``maxResults`` agree with the rows read so
    far, so a server cap is followed without skipping comments. ``limit`` caps
    the thread and is sent as the per-page ``maxResults``, never above the
    50-row page size, so a small limit really narrows the server response;
    ``None`` reads and validates every page. Duplicate IDs and any metadata
    drift reject the whole thread; a page cap or HTTP failure after valid rows
    also publishes nothing. The list itself cannot show that ``limit`` stopped
    the read; use :func:`list_issue_comments_with_metadata` when a cut result
    must be visible to the caller.
    """
    return list_issue_comments_with_metadata(
        base_url,
        key_or_url,
        token=token,
        limit=limit,
        max_pages=max_pages,
        allow_http_loopback=allow_http_loopback,
    )["rows"]


def list_issue_comments_with_metadata(
    base_url: str,
    key_or_url: str,
    *,
    token: str,
    limit: int | None = None,
    max_pages: int = COMMENT_PAGES_DEFAULT,
    allow_http_loopback: bool = False,
) -> CommentThreadMetadata:
    """Вернуть комментарии вместе с признаком неполноты и заявленным ``total``.

    Форма ответа — ``{"rows": [...], "truncated": bool, "total": int}``;
    :func:`list_issue_comments` остаётся прежним списком и делегирует сюда.
    ``limit`` уходит в серверный ``maxResults`` каждой страницы (не больше
    ``_COMMENT_PAGE_SIZE``), поэтому малый лимит уменьшает и сам ответ, а не
    только число возвращаемых строк. ``truncated`` истинно, когда ``limit``
    остановил чтение раньше известного ``total``, поэтому ложного «всё
    прочитано» нет. ``total`` — значение, которое сервер прислал на последней
    принятой странице; дополнительного запроса ради признака неполноты не
    делается.
    """
    key = _issue_key(key_or_url)
    _check_comment_limit(limit)
    _check_comment_pages(max_pages)
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    url = f"{base}/rest/api/2/issue/{key}/comment"
    with bearer_session(token, product="jira") as session:
        rows, truncated, total = _read_comments(session, url, max_pages, limit)
    return CommentThreadMetadata(rows=rows, truncated=truncated, total=total)


def _check_comment_limit(limit: int | None) -> None:
    if limit is not None and (
        not isinstance(limit, int)
        or isinstance(limit, bool)
        or not COMMENT_LIMIT_MIN <= limit <= COMMENT_LIMIT_MAX
    ):
        raise AtlaWireError(
            "The comment limit must be between "
            f"{COMMENT_LIMIT_MIN} and {COMMENT_LIMIT_MAX}."
        )


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
    session: requests.Session,
    url: str,
    max_pages: int,
    limit: int | None,
) -> tuple[list[CommentRow], bool, int]:
    """Прочитать не более ``limit`` комментариев: ``(rows, truncated, total)``.

    ``truncated`` истинно только тогда, когда ``limit`` остановил обход до
    известного ``total``. Размер страницы запроса не превышает ``limit`` и
    ``_COMMENT_PAGE_SIZE``, поэтому лимит уменьшает и ответ сервера, а не только
    результат. Исчерпанный бюджет страниц по-прежнему ошибка, а не частичный
    результат.
    """
    rows: list[CommentRow] = []
    seen_ids: set[str] = set()
    start = 0
    total: int | None = None
    for _ in range(max_pages):
        remaining = None if limit is None else limit - len(rows)
        requested = _COMMENT_PAGE_SIZE
        if remaining is not None:
            requested = min(requested, remaining)
        page = get_json_object(
            session,
            url,
            params={"startAt": start, "maxResults": requested},
        )
        comments, reported_total = _comment_page(page, start, total, requested)
        total = reported_total
        if not comments:
            return rows, False, total
        for value in comments:
            row = _project_comment(value)
            if row["id"] in seen_ids:
                raise AtlaWireError("Jira returned duplicate comment IDs.")
            seen_ids.add(row["id"])
            rows.append(row)
        start += len(comments)
        if limit is not None and len(rows) >= limit:
            return rows, total > len(rows), total
        if start == total:
            return rows, False, total
    raise AtlaWireError(
        "Jira comments exceeded the page limit; raise --max-pages or retry."
    )


def _comment_page(
    page: dict[str, object],
    start: int,
    expected_total: int | None,
    requested: int,
) -> tuple[list[object], int]:
    """Validate one page and return its comments and total."""
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
    if len(comments) > requested:
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
    fields: str | list[str] = "*all",
    limit: int | None = None,
    start: int = 0,
    expand: str | None = None,
    allow_http_loopback: bool = False,
) -> dict[str, object]:
    """Return one raw ``/rest/api/2/search`` envelope without any projection.

    Exactly one GET is sent: ``limit`` and ``expand`` are omitted when ``None``,
    the body is returned unchanged including unknown keys, and nothing is
    paginated or projected. Every argument is checked before a session exists.
    ``fields`` is either a string sent verbatim or a list joined with commas in
    the given order, matching :func:`search_all_issues`; an empty selection is
    rejected before any request.
    """
    if not isinstance(jql, str) or not jql.strip():
        raise AtlaWireError("Expected a non-empty JQL query.")
    selected = _search_fields_value(fields)
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
    params: dict[str, str | int] = {
        "jql": jql,
        "fields": selected,
        "startAt": start,
    }
    if limit is not None:
        params["maxResults"] = limit
    if expand is not None:
        params["expand"] = expand
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    with bearer_session(token, product="jira") as session:
        return get_json_object(session, f"{base}/rest/api/2/search", params=params)


def search_issues(
    base_url: str,
    query: str,
    *,
    token: str,
    fields: str | list[str] = _SEARCH_FIELDS,
    limit: int = 50,
    allow_http_loopback: bool = False,
) -> list[IssueRow]:
    """Return up to ``limit`` short issue rows in Jira search order.

    ``fields`` is either a string sent verbatim or a list joined with commas in
    the given order; an empty selection is rejected before any request, like
    :func:`search_raw` and :func:`search_all_issues`.

    Jira 8.22 may omit ``total`` from a search page, so an empty page is the
    only exhaustion proof when it is absent. A known ``total`` is never
    forgotten: a later page may omit it, while a changed value or an empty
    page short of it fails instead of claiming a complete result. The page
    size follows the ``maxResults`` echo, and the undocumented ``isLast``
    flag is ignored. Any error discards rows already read instead of
    returning a partial result. The list itself cannot show that more rows
    exist; use :func:`search_issues_with_metadata` when a capped result must
    be visible to the caller.
    """
    return search_issues_with_metadata(
        base_url,
        query,
        token=token,
        fields=fields,
        limit=limit,
        allow_http_loopback=allow_http_loopback,
    )["rows"]


def search_issues_with_metadata(
    base_url: str,
    query: str,
    *,
    token: str,
    fields: str | list[str] = _SEARCH_FIELDS,
    limit: int = 50,
    allow_http_loopback: bool = False,
) -> IssueSearchMetadata:
    """Вернуть строки поиска вместе с признаком неполноты и заявленным ``total``.

    Форма ответа — ``{"rows": [...], "truncated": bool, "total": int | None}``;
    :func:`search_issues` остаётся прежним списком и делегирует сюда.
    ``fields`` проверяется тем же валидатором, что у :func:`search_raw` и
    :func:`search_all_issues`, и уходит в каждый запрос.
    известный ``total`` больше числа строк, выдача урезана лимитом; если
    сервер не прислал ``total`` и лимит достигнут, полноту доказать нельзя,
    поэтому ``truncated`` тоже истинно — ложного «всё прочитано» нет.
    Дополнительного запроса ради признака неполноты не делается; ``total`` —
    последнее значение, которое прислал сервер (``None``, если не прислал).
    """
    if not query.strip():
        raise AtlaWireError("Expected a non-empty JQL query.")
    selected = _search_fields_value(fields)
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
    with bearer_session(token, product="jira") as session:
        rows, truncated, total = _read_search(session, url, query, selected, limit)
    return IssueSearchMetadata(rows=rows, truncated=truncated, total=total)


def search_all_issues(
    base_url: str,
    jql: str,
    *,
    token: str,
    fields: str | list[str] = "*all",
    limit: int | None = None,
    max_pages: int = 100,
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
    reported total fails instead of claiming a complete result. ``max_pages``
    bounds the request count: it must be between 1 and 1000, and the default
    100 pages matches the other paged readers in this module and covers up to
    10 000 issues at the 100-issue page size. A longer walk must pass a larger
    budget; an exhausted budget raises instead of returning a partial list.
    ``isLast`` is not part of the documented Jira 8.22 search response and is
    ignored. Every issue is returned unchanged, so unknown and nested fields
    are preserved; no projection, deduplication, or extra request is performed.
    The list itself cannot show that ``limit`` cut the traversal; use
    :func:`search_all_issues_with_metadata` when that must be visible.
    """
    return search_all_issues_with_metadata(
        base_url,
        jql,
        token=token,
        fields=fields,
        limit=limit,
        max_pages=max_pages,
        allow_http_loopback=allow_http_loopback,
    )["rows"]


def search_all_issues_with_metadata(
    base_url: str,
    jql: str,
    *,
    token: str,
    fields: str | list[str] = "*all",
    limit: int | None = None,
    max_pages: int = 100,
    allow_http_loopback: bool = False,
) -> RawIssueSearchMetadata:
    """Вернуть сырые задачи вместе с признаком неполноты и заявленным ``total``.

    Форма ответа — ``{"rows": [...], "truncated": bool, "total": int | None}``;
    :func:`search_all_issues` остаётся прежним списком и делегирует сюда. При
    ``limit=None`` обход полный и ``truncated`` ложно. Если лимит достигнут,
    ``truncated`` истинно при известном ``total`` больше числа строк, а при
    отсутствии ``total`` — консервативно, потому что полноту доказать нельзя.
    Дополнительного запроса ради метаданных не делается. Прочие параметры и
    ограничения совпадают с :func:`search_all_issues`.
    """
    if not isinstance(jql, str) or not jql.strip():
        raise AtlaWireError("Expected a non-empty JQL query.")
    selected = _search_fields_value(fields)
    if limit is not None and (
        not isinstance(limit, int) or isinstance(limit, bool) or limit < 1
    ):
        raise AtlaWireError("The issue limit must be a positive integer.")
    if (
        not isinstance(max_pages, int)
        or isinstance(max_pages, bool)
        or not 1 <= max_pages <= 1000
    ):
        raise AtlaWireError("The page limit must be between 1 and 1000.")
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    url = f"{base}/rest/api/2/search"
    with bearer_session(token, product="jira") as session:
        rows, truncated, total = _read_all_issues(
            session, url, jql, selected, limit, max_pages
        )
    return RawIssueSearchMetadata(rows=rows, truncated=truncated, total=total)


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
    with bearer_session(token, product="jira") as session:
        # One JQL read per batch of 50; a longer IN list would overflow the URL.
        for start in range(0, len(unique), 50):
            batch = unique[start : start + 50]
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
                    raise AtlaWireError(
                        "Expected Jira issue objects in search results."
                    )
                key = issue.get("key")
                if not _valid_issue_key(key):
                    raise AtlaWireError(
                        "Expected valid Jira issue keys in search results."
                    )
                fields = issue.get("fields")
                summary = fields.get("summary") if isinstance(fields, dict) else None
                if not isinstance(summary, str):
                    raise AtlaWireError(
                        "Expected Jira issue summaries in search results."
                    )
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
    with bearer_session(token, product="jira") as session:
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
    with bearer_session(token, product="jira") as session:
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
    with bearer_session(token, product="jira") as session:
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
    with bearer_session(token, product="jira") as session:
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
    with bearer_session(token, product="jira") as session:
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
    with bearer_session(token, product="jira") as session:
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
    with bearer_session(token, product="jira") as session:
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


# Bounded lookup used by resolve_user: Jira's user search is a bare array with
# no exhaustion marker, so a full page never proves that more users are absent.
_USER_SEARCH_LIMIT = 50
_USER_PAGE_LIMIT = 100

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


def resolve_user(
    base_url: str,
    term: str | None = None,
    *,
    token: str,
    allow_http_loopback: bool = False,
) -> CurrentUser:
    """Resolve one Jira user to ``name``, ``displayName`` and ``email``.

    ``term=None`` reads the authenticated identity from ``/rest/api/2/myself``
    and performs no user search. Any other term is looked up with the same
    policy as :func:`atlawire.jira_comments_search.find_author_comments`: the
    original term, a BBK-compatible Russian transliteration, and a four-letter
    transliterated prefix are tried in order. An exact login match wins over a
    non-exact candidate seen earlier, and a missing or blank ``displayName``
    falls back to the login.

    Jira 8.22 returns a bare user array without ``total`` or ``isLast``, so
    paging stops at the first empty page. A single non-exact candidate found
    that way is a heuristic, not proof of uniqueness; two or more distinct
    candidates are ambiguous and fail with the discovered logins named in the
    error. The bearer token never reaches that message.
    """
    if term is None:
        return get_current_user(
            base_url, token=token, allow_http_loopback=allow_http_loopback
        )
    checked = _user_lookup_term(term)
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    return _resolve_user_term(
        base, checked, token=token, allow_http_loopback=allow_http_loopback
    )


def _user_lookup_term(value: object) -> str:
    """Validate one lookup term before a session or request exists."""
    if not isinstance(value, str) or not value.strip():
        raise AtlaWireError("Expected a non-empty Jira user login or name.")
    return _user_text(value.strip(), "login or name")


def _translit_user_term(term: str) -> str:
    """Transliterate Russian text with BBK's soft-sign rule.

    A soft sign before ``е``/``ё``/``ю``/``я`` becomes ``y``, so
    ``Воробьев`` becomes ``vorobyev`` rather than ``vorobev``.
    """
    out: list[str] = []
    chars = term.lower()
    for index, char in enumerate(chars):
        if char == "ь" and index + 1 < len(chars) and chars[index + 1] in "еёюя":
            out.append("y")
            continue
        out.append(_RU2LAT.get(char, char))
    return "".join(out)


def _user_lookup_candidates(term: str) -> list[str]:
    """Return BBK-compatible lookup candidates in priority order."""
    candidates = [term]
    latin = _translit_user_term(term)
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


def _resolve_user_term(
    base: str, term: str, *, token: str, allow_http_loopback: bool
) -> CurrentUser:
    """Try each candidate in order and reject a term that matches nothing."""
    for candidate in _user_lookup_candidates(term):
        resolved = _resolve_user_candidate(
            base, candidate, token=token, allow_http_loopback=allow_http_loopback
        )
        if resolved is not None:
            return resolved
    raise AtlaWireError("No Jira user matched the requested login or name.")


def _resolve_user_candidate(
    base: str, candidate: str, *, token: str, allow_http_loopback: bool
) -> CurrentUser | None:
    """Page one candidate until empty, exact, or page-budget failure.

    Jira's user search has no total or ``isLast`` field, so the first empty page
    is the only practical exhaustion signal. The exact login stops paging
    immediately; a singleton non-exact user is a heuristic, while two distinct
    ones are ambiguous.
    """
    candidate_key = candidate.casefold()
    only_nonexact: dict[str, object] | None = None
    found: list[str] = []
    multiple_candidates = False
    seen_names: set[str] = set()
    start = 0
    for _ in range(_USER_PAGE_LIMIT):
        rows = search_users(
            base,
            candidate,
            token=token,
            start_at=start,
            max_results=_USER_SEARCH_LIMIT,
            allow_http_loopback=allow_http_loopback,
        )
        if not rows:
            if multiple_candidates:
                raise AtlaWireError(_ambiguous_user_message(found))
            if only_nonexact is not None:
                return _resolved_user(only_nonexact)
            return None
        exact: dict[str, object] | None = None
        for row in rows:
            name = _user_row_name(row)
            key = name.casefold()
            if key in seen_names:
                raise AtlaWireError(
                    "Jira user search returned a duplicate or non-advancing page; "
                    "use the exact login."
                )
            seen_names.add(key)
            found.append(name)
            if key == candidate_key:
                exact = row
            elif only_nonexact is None:
                only_nonexact = row
            else:
                multiple_candidates = True
        if exact is not None:
            return _resolved_user(exact)
        start += len(rows)
    raise AtlaWireError(
        "Jira user search exceeded the page budget; use the exact login."
    )


def _user_row_name(row: object) -> str:
    """Return the login of one user search row, rejecting wrong shapes."""
    if not isinstance(row, dict):
        raise AtlaWireError("Expected Jira user objects.")
    name = row.get("name")
    if not isinstance(name, str) or not name.strip():
        raise AtlaWireError("Expected Jira users with non-empty names.")
    return _user_text(name, "name")


def _resolved_user(row: dict[str, object]) -> CurrentUser:
    """Project one user row, falling back to the login as display name."""
    name = _user_text(row.get("name"), "name")
    if not name.strip():
        raise AtlaWireError("Expected a Jira user with a non-empty name.")
    display = _optional_user_text(row.get("displayName"), "display name")
    if display is None or not display.strip():
        display = name
    return CurrentUser(
        name=name,
        displayName=display,
        email=_optional_user_text(row.get("emailAddress"), "email"),
    )


def _ambiguous_user_message(names: list[str]) -> str:
    """Name every discovered login without exposing transport details."""
    unique = list(dict.fromkeys(names))
    return (
        "Jira user search matched more than one user: "
        + ", ".join(unique)
        + "; use the exact login."
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
    session: requests.Session, url: str, query: str, fields: str, limit: int
) -> tuple[list[IssueRow], bool, int | None]:
    """Прочитать не более ``limit`` строк и вернуть ``(rows, truncated, total)``.

    ``fields`` уже прошёл общий валидатор и уходит в каждый запрос как есть.
    ``truncated`` считается из уже полученных ответов: известный ``total``
    больше числа строк означает обрезку лимитом; если сервер не прислал
    ``total``, а лимит достигнут, полноту доказать нельзя, поэтому результат
    тоже помечается неполным. Второго запроса ради этого флага нет.
    """
    rows: list[IssueRow] = []
    seen_keys: set[str] = set()
    known_total: int | None = None
    # Requests follow the server's maxResults echo after the first page.
    page_size = limit
    while len(rows) < limit:
        start = len(rows)
        requested = min(page_size, limit - start)
        page = get_json_object(
            session,
            url,
            params={
                "jql": query,
                "fields": fields,
                "startAt": start,
                "maxResults": requested,
            },
        )
        issues, reported_total, advertised = _search_page(page, start)
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
            return rows, False, known_total
        if advertised is not None:
            page_size = advertised
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
        if known_total is not None and len(rows) == known_total:
            return rows, False, known_total
    # Лимит достигнут: без серверного ``total`` полнота не доказана.
    return rows, known_total is None or known_total > len(rows), known_total


def _check_search_end(offset: int, known_total: int | None) -> None:
    """Reject only a known total that the traversal failed to reach.

    Jira 8.22 may omit ``total``, so an empty page is the only exhaustion proof
    when the page carries no total. A total reported earlier is never
    forgotten: stopping short of it is still an error.
    """
    if known_total is not None and known_total > offset:
        raise AtlaWireError(
            "Jira search returned an empty page before all matches; "
            "narrow the query or retry."
        )


def _search_page(
    page: dict[str, object], start: int
) -> tuple[list[object], int | None, int | None]:
    """Validate one page and return its issues, total, and maxResults echo."""
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
    advertised: int | None = None
    if issues:
        advertised_value = page.get("maxResults")
        if (
            not isinstance(advertised_value, int)
            or isinstance(advertised_value, bool)
            or advertised_value <= 0
        ):
            raise AtlaWireError("Invalid Jira search maxResults.")
        advertised = advertised_value
        if len(issues) > advertised:
            raise AtlaWireError("Jira search returned more issues than maxResults.")
        if total is not None and total < start + len(issues):
            raise AtlaWireError("Inconsistent Jira search pagination metadata.")
    return issues, total, advertised


def _search_fields_value(fields: str | list[str]) -> str:
    """Вернуть значение ``fields`` для query, отвергая пустой выбор.

    Одна проверка на :func:`search_raw`, :func:`search_issues` и
    :func:`search_all_issues`: строка уходит как есть, список — через запятую
    в заданном порядке, пустая строка или список падают до запроса.
    """
    if isinstance(fields, str):
        if not fields.strip():
            raise AtlaWireError("Expected non-empty Jira search fields.")
        return fields
    if not isinstance(fields, list) or not fields:
        raise AtlaWireError("Expected non-empty Jira search fields.")
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
    max_pages: int,
) -> tuple[list[dict[str, object]], bool, int | None]:
    """Page the JQL search and return ``(rows, truncated, total)``.

    At most ``max_pages`` requests are sent; an exhausted budget raises
    instead of returning the rows read so far. ``truncated`` is true only when
    ``limit`` stopped the traversal before the server proved completeness, so
    a caller sees a cut result without an extra request.
    """
    rows: list[dict[str, object]] = []
    start = 0
    page_size = _SEARCH_ALL_PAGE_SIZE
    for _ in range(max_pages):
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
        issues, total, advertised = _all_issues_page(page, start=start, requested=size)
        if advertised is not None:
            page_size = min(advertised, _SEARCH_ALL_PAGE_SIZE)
        if total is not None and start + len(issues) > total:
            raise AtlaWireError("Inconsistent Jira search pagination metadata.")
        rows.extend(issues)
        if limit is not None and len(rows) >= limit:
            # Лимит остановил обход: полноту подтверждает только ``total``.
            truncated = total is None or total > len(rows)
            return rows, truncated, total
        if not issues:
            _check_search_end(start, total)
            return rows, False, total
        if total is not None and start + len(issues) >= total:
            return rows, False, total
        start += len(issues)
    raise AtlaWireError(
        "Jira search exceeded the page limit; narrow the query or raise max_pages."
    )


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
    if len(issues) > requested or (advertised is not None and len(issues) > advertised):
        raise AtlaWireError("Jira search returned more issues than requested.")
    rows: list[dict[str, object]] = []
    for issue in issues:
        if not isinstance(issue, dict):
            raise AtlaWireError("Expected Jira issue objects in search results.")
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


def get_issue_votes(
    base_url: str,
    key_or_url: str,
    *,
    token: str,
    allow_http_loopback: bool = False,
) -> IssueVotes:
    """Вернуть голоса одной задачи: ``voters``, ``hasVoted`` и ``watchCount``.

    Читается ``GET /rest/api/2/issue/{key}/votes`` из настроенного ``base_url``;
    из ``key_or_url`` берётся только ключ задачи. Каждый элемент ``voters`` —
    плоский ``{"name": ..., "displayName": ...}``. ``hasVoted`` и
    ``watchCount`` остаются ``None``, если сервер поле не прислал, и никогда не
    вычисляются из других ответов. В официальном ответе 8.22 у этого пути поля
    ``watchCount`` нет, поэтому на проверенном сервере там всегда ``None``.
    Сырой документ доступен через :func:`atlawire.sdk.get_json`.
    """
    key = _issue_key(key_or_url)
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    with bearer_session(token, product="jira") as session:
        document = get_json_object(
            session, f"{base}/rest/api/2/issue/{key}/votes", params={}
        )
    return _project_votes(document)


def get_issue_watchers(
    base_url: str,
    key_or_url: str,
    *,
    token: str,
    allow_http_loopback: bool = False,
) -> IssueWatchers:
    """Вернуть наблюдателей задачи: ``watchers``, ``watchCount`` и ``isWatching``.

    Читается ``GET /rest/api/2/issue/{key}/watchers``; из ``key_or_url`` берётся
    только ключ задачи. Список сервер 8.22 отдаёт целиком, без пагинации. Каждый
    элемент ``watchers`` — плоский ``{"name": ..., "displayName": ...}``;
    ``watchCount`` и ``isWatching`` остаются ``None``, если сервер их не прислал.
    Сырой документ доступен через :func:`atlawire.sdk.get_json`.
    """
    key = _issue_key(key_or_url)
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    with bearer_session(token, product="jira") as session:
        document = get_json_object(
            session, f"{base}/rest/api/2/issue/{key}/watchers", params={}
        )
    return _project_watchers(document)


def list_issue_subtasks(
    base_url: str,
    key_or_url: str,
    *,
    token: str,
    allow_http_loopback: bool = False,
) -> list[SubtaskRow]:
    """Вернуть подзадачи: ``key``, ``summary``, ``type`` и ``status``.

    Читается ``GET /rest/api/2/issue/{key}/subtask``. ``type`` и ``status`` —
    имена типа и статуса, а не вложенные объекты. Отсутствующие поля остаются
    ``None`` и не подменяются пустой строкой. Весь массив проверяется до
    возврата, поэтому поздняя некорректная запись не даёт частичного списка.
    Сырой документ доступен через :func:`atlawire.sdk.get_json`.
    """
    key = _issue_key(key_or_url)
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    with bearer_session(token, product="jira") as session:
        values = get_json_array(
            session, f"{base}/rest/api/2/issue/{key}/subtask", params={}
        )
    return [_project_subtask(value) for value in values]


def get_issue_comment(
    base_url: str,
    key_or_url: str,
    comment_id: str | int,
    *,
    token: str,
    allow_http_loopback: bool = False,
) -> CommentRow:
    """Вернуть один комментарий: ``id``, ``author``, ``body``, ``created``,
    ``updated``.

    Читается ``GET /rest/api/2/issue/{key}/comment/{id}``. ``author`` — логин
    (``name``) автора, а не объект пользователя. ``body`` — исходная wiki-строка
    сервера, отметки времени берутся у сервера без преобразования. Поля, которых
    нет в ответе, остаются ``None``. Идентификатор проверяется до запроса и не
    попадает в сообщение об ошибке. Сырой документ доступен через
    :func:`atlawire.sdk.get_json`.
    """
    key = _issue_key(key_or_url)
    checked = _jira_id(comment_id, "comment")
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    with bearer_session(token, product="jira") as session:
        document = get_json_object(
            session,
            f"{base}/rest/api/2/issue/{key}/comment/{checked}",
            params={},
        )
    return _project_comment(document)


def get_issue_worklog(
    base_url: str,
    key_or_url: str,
    worklog_id: str | int,
    *,
    token: str,
    allow_http_loopback: bool = False,
) -> WorklogRow:
    """Вернуть одну запись о трудозатратах: ``id``, ``author``, ``started``,
    ``seconds`` и ``comment``.

    Читается ``GET /rest/api/2/issue/{key}/worklog/{id}``. ``seconds`` — это
    ``timeSpentSeconds`` сервера, а не разобранная строка ``timeSpent``.
    ``author`` — логин автора. Отсутствующие ``comment``, ``started`` и
    ``seconds`` остаются ``None``. Идентификатор проверяется до запроса.
    Сырой документ доступен через :func:`atlawire.sdk.get_json`.
    """
    key = _issue_key(key_or_url)
    checked = _jira_id(worklog_id, "worklog")
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    with bearer_session(token, product="jira") as session:
        document = get_json_object(
            session,
            f"{base}/rest/api/2/issue/{key}/worklog/{checked}",
            params={},
        )
    return _project_worklog(document)


def get_issue_properties(
    base_url: str,
    key_or_url: str,
    *,
    token: str,
    allow_http_loopback: bool = False,
) -> IssuePropertyKeys:
    """Вернуть имена свойств задачи в виде ``{"keys": [...]}``.

    Читается ``GET /rest/api/2/issue/{key}/properties``; в проекцию попадают
    только ключи свойств, без ``self``-ссылок. Пустой ответ сервера даёт пустой
    список, а не ошибку. Значение читается отдельно через
    :func:`get_issue_property`. Сырой документ доступен через
    :func:`atlawire.sdk.get_json`.
    """
    key = _issue_key(key_or_url)
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    with bearer_session(token, product="jira") as session:
        document = get_json_object(
            session, f"{base}/rest/api/2/issue/{key}/properties", params={}
        )
    return IssuePropertyKeys(keys=_project_property_keys(document))


def get_issue_property(
    base_url: str,
    key_or_url: str,
    property_key: str,
    *,
    token: str,
    allow_http_loopback: bool = False,
) -> IssueProperty:
    """Вернуть одно свойство задачи: ``{"key": ..., "value": ...}``.

    Читается ``GET /rest/api/2/issue/{key}/properties/{propertyKey}``; ключ
    кодируется как один сегмент пути. ``value`` — произвольный JSON сервера,
    возвращается без изменений (``None``, если поля нет) и не разбирается по
    частям. Ключ проверяется до запроса: пустая строка, разделители пути и
    значения длиннее 255 символов отклоняются. Сырой документ доступен через
    :func:`atlawire.sdk.get_json`.
    """
    key = _issue_key(key_or_url)
    checked = _property_key(property_key)
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    segment = quote(checked, safe="")
    with bearer_session(token, product="jira") as session:
        document = get_json_object(
            session,
            f"{base}/rest/api/2/issue/{key}/properties/{segment}",
            params={},
        )
    return _project_property(document)


def get_issue_link(
    base_url: str,
    link_id: str | int,
    *,
    token: str,
    allow_http_loopback: bool = False,
) -> IssueLinkRow:
    """Вернуть связь задач: ``id``, ``type``, ``inwardIssue``, ``outwardIssue``.

    Читается ``GET /rest/api/2/issueLink/{linkId}``. ``type`` — имя типа связи;
    ``inwardIssue`` и ``outwardIssue`` — ключи задач, а не вложенные объекты.
    Сторона, которой в ответе нет, остаётся ``None``. Идентификатор проверяется
    до запроса. Сырой документ доступен через :func:`atlawire.sdk.get_json`.
    """
    checked = _jira_id(link_id, "issue link")
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    with bearer_session(token, product="jira") as session:
        document = get_json_object(
            session, f"{base}/rest/api/2/issueLink/{checked}", params={}
        )
    return _project_issue_link(document)


def _project_votes(document: dict[str, object]) -> IssueVotes:
    """Спроецировать голоса, не подставляя отсутствующие поля."""
    return IssueVotes(
        voters=_project_user_refs(document.get("voters"), "voter"),
        hasVoted=_optional_flag(document.get("hasVoted"), "hasVoted"),
        watchCount=_optional_integer(document.get("watchCount"), "watch count"),
    )


def _project_watchers(document: dict[str, object]) -> IssueWatchers:
    """Спроецировать наблюдателей, не подставляя отсутствующие поля."""
    return IssueWatchers(
        watchers=_project_user_refs(document.get("watchers"), "watcher"),
        watchCount=_optional_integer(document.get("watchCount"), "watch count"),
        isWatching=_optional_flag(document.get("isWatching"), "isWatching"),
    )


def _project_user_refs(value: object, label: str) -> list[UserRefRow]:
    """Спроецировать массив пользователей, отклоняя не-массив."""
    if not isinstance(value, list):
        raise AtlaWireError(f"Expected a Jira {label}s array.")
    return [_project_user_ref(item, label) for item in value]


def _project_user_ref(value: object, label: str) -> UserRefRow:
    """Спроецировать пользователя на ``name`` и ``displayName``."""
    if not isinstance(value, dict):
        raise AtlaWireError(f"Expected Jira {label} objects.")
    return UserRefRow(
        name=_required_project_text(value.get("name"), f"{label} name"),
        displayName=_optional_project_text(
            value.get("displayName"), f"{label} display name"
        ),
    )


def _project_subtask(value: object) -> SubtaskRow:
    """Спроецировать подзадачу, не выдумывая отсутствующие поля."""
    if not isinstance(value, dict):
        raise AtlaWireError("Expected Jira subtask objects.")
    key = value.get("key")
    if not _valid_issue_key(key):
        raise AtlaWireError("Expected a valid Jira subtask key.")
    fields = value.get("fields")
    if fields is None:
        fields = {}
    elif not isinstance(fields, dict):
        raise AtlaWireError("Expected Jira subtask fields.")
    return SubtaskRow(
        key=key,
        summary=_optional_project_text(fields.get("summary"), "subtask summary"),
        type=_project_nested_name(fields.get("issuetype"), "subtask type"),
        status=_project_nested_name(fields.get("status"), "subtask status"),
    )


def _project_worklog(value: object) -> WorklogRow:
    """Спроецировать запись о трудозатратах без разбора ``timeSpent``."""
    if not isinstance(value, dict):
        raise AtlaWireError("Expected a Jira worklog object.")
    return WorklogRow(
        id=_required_project_text(value.get("id"), "worklog ID"),
        author=_project_author(value.get("author"), "worklog author"),
        started=_optional_project_text(value.get("started"), "worklog started"),
        seconds=_optional_integer(value.get("timeSpentSeconds"), "worklog seconds"),
        comment=_optional_project_text(value.get("comment"), "worklog comment"),
    )


def _project_author(value: object, label: str) -> str | None:
    """Вернуть логин автора или ``None``, если сервер его не прислал."""
    if value is None:
        return None
    if not isinstance(value, dict):
        raise AtlaWireError(f"Invalid Jira {label}.")
    return _optional_project_text(value.get("name"), label)


def _project_issue_link(value: object) -> IssueLinkRow:
    """Спроецировать связь задач на плоские идентификаторы."""
    if not isinstance(value, dict):
        raise AtlaWireError("Expected a Jira issue link object.")
    return IssueLinkRow(
        id=_required_project_text(value.get("id"), "issue link ID"),
        type=_project_nested_name(value.get("type"), "issue link type"),
        inwardIssue=_project_issue_key(value.get("inwardIssue"), "inward issue"),
        outwardIssue=_project_issue_key(value.get("outwardIssue"), "outward issue"),
    )


def _project_issue_key(value: object, label: str) -> str | None:
    """Вернуть ключ связанной задачи или ``None``, если стороны нет."""
    if value is None:
        return None
    if not isinstance(value, dict):
        raise AtlaWireError(f"Invalid Jira {label}.")
    key = value.get("key")
    if key is None:
        return None
    if not _valid_issue_key(key):
        raise AtlaWireError(f"Invalid Jira {label} key.")
    return key


def _project_property_keys(document: dict[str, object]) -> list[str]:
    """Собрать имена свойств из массива ``keys``."""
    values = document.get("keys")
    if not isinstance(values, list):
        raise AtlaWireError("Expected a Jira property keys array.")
    keys: list[str] = []
    for value in values:
        if not isinstance(value, dict):
            raise AtlaWireError("Expected Jira property key objects.")
        keys.append(_required_project_text(value.get("key"), "property key"))
    return keys


def _project_property(document: dict[str, object]) -> IssueProperty:
    """Спроецировать свойство: ключ обязателен, значение — как есть."""
    return IssueProperty(
        key=_required_project_text(document.get("key"), "property key"),
        value=document.get("value"),
    )


def _project_nested_name(value: object, label: str) -> str | None:
    """Вернуть ``name`` вложенного объекта или ``None``, если объекта нет."""
    if value is None:
        return None
    if not isinstance(value, dict):
        raise AtlaWireError(f"Invalid Jira {label}.")
    return _optional_project_text(value.get("name"), label)


def _project_text(value: object, label: str) -> str:
    """Вернуть текстовое поле, пригодное для вывода в UTF-8."""
    if not isinstance(value, str):
        raise AtlaWireError(f"Expected the Jira {label} as text.")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        message = f"Expected the Jira {label} as valid UTF-8 text."
        raise AtlaWireError(message) from None
    return value


def _required_project_text(value: object, label: str) -> str:
    """Вернуть непустое текстовое поле проекции."""
    text = _project_text(value, label)
    if not text.strip():
        raise AtlaWireError(f"Expected the Jira {label} as non-empty text.")
    return text


def _optional_project_text(value: object, label: str) -> str | None:
    """Вернуть ``None`` для отсутствующего поля и текст иначе."""
    return None if value is None else _project_text(value, label)


def _optional_flag(value: object, label: str) -> bool | None:
    """Вернуть флаг сервера или ``None``, если поля нет."""
    if value is None:
        return None
    if not isinstance(value, bool):
        raise AtlaWireError(f"Invalid Jira {label} flag.")
    return value


def _optional_integer(value: object, label: str) -> int | None:
    """Вернуть неотрицательное целое сервера или ``None``, если поля нет."""
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise AtlaWireError(f"Invalid Jira {label} integer.")
    return value


def _jira_id(value: object, label: str) -> str:
    """Вернуть положительный идентификатор Jira строкой до любого запроса.

    Принимается ``int`` или десятичная строка; ведущие нули, знак, пустое
    значение и длина больше 19 цифр отклоняются, чтобы значение не могло
    удлинить путь или упереться в предел интерпретатора.
    """
    invalid = f"Expected a Jira {label} as a positive integer ID."
    if isinstance(value, bool):
        raise AtlaWireError(invalid)
    if isinstance(value, str):
        # Length is checked before conversion so huge digit strings cannot stall
        # or hit the interpreter's integer-string conversion limit.
        if len(value) > 19 or re.fullmatch(r"[1-9][0-9]*", value) is None:
            raise AtlaWireError(invalid)
        identifier = int(value)
    elif isinstance(value, int):
        identifier = value
    else:
        raise AtlaWireError(invalid)
    if not 1 <= identifier <= _JIRA_ID_MAX:
        raise AtlaWireError(invalid)
    return str(identifier)


def _property_key(value: object) -> str:
    """Вернуть ключ свойства как один безопасный сегмент пути."""
    invalid = (
        f"Expected a Jira property key of 1 to {_PROPERTY_KEY_MAX} characters "
        "without path separators."
    )
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > _PROPERTY_KEY_MAX
    ):
        raise AtlaWireError(invalid)
    # The component is quoted before it reaches the path, but a server that
    # decodes more than once must still never see a separator or a dot segment.
    decoded = value
    while True:
        next_value = unquote(decoded)
        if next_value == decoded:
            break
        decoded = next_value
    if "/" in decoded or "\\" in decoded or decoded in {".", ".."}:
        raise AtlaWireError(invalid)
    return _project_text(value, "property key")
