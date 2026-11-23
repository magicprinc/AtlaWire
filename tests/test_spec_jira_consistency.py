"""Чёрный ящик: согласованность полей search_raw и видимая неполнота Jira-чтений.

Тесты поднимают loopback HTTP-сервер, который отвечает только документированными
маршрутами Jira 8.22, и вызывают публичные функции библиотеки. Сеть, учётные
данные и monkeypatching не используются.

Проверяемые инварианты:
* ``search_raw`` и ``search_all_issues`` принимают ``fields`` и строкой, и
  списком; строка уходит как есть, список — через запятую, пустой выбор падает
  до запроса;
* ограниченный поиск отдаёт ``rows`` вместе с ``truncated`` и заявленным
  ``total``, поэтому неполнота видна вызывающему без второго запроса;
* полный список worklog обходит страницы до ``total`` и падает явной ошибкой
  при исчерпании бюджета, а не отдаёт молча часть строк;
* changelog с неполной страницей — явная ошибка, полная история возвращается
  без потерь;
* ни токен, ни тело ответа не попадают в текст ошибки.
"""

import json
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import NamedTuple
from urllib.parse import parse_qs, urlsplit

import pytest

from atlawire import jira
from atlawire.http import AtlaWireError

TOKEN = "synthetic-jira-consistency-token"
SECRET = "synthetic-private-error-body"
JQL = "assignee = currentUser() ORDER BY updated DESC"
JSON = "application/json"
SEARCH_PATH = "/rest/api/2/search"
ISSUE_PATH = "/rest/api/2/issue/ABC-123"
WORKLOG_PATH = ISSUE_PATH + "/worklog"
SEARCH_FIELDS = "summary,status,priority,issuetype,assignee,updated"


class Reply(NamedTuple):
    content_type: str
    body: bytes


def json_reply(payload: object) -> Reply:
    return Reply(JSON, json.dumps(payload).encode())


def http_error(status: int, payload: object) -> Reply:
    return Reply(JSON, json.dumps(payload).encode())


@pytest.fixture
def server():
    """Loopback-сервер с таблицей маршрутов «путь -> функция запроса»."""

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self):
            self.server.calls.append(  # type: ignore[attr-defined]
                (
                    self.command,
                    self.path,
                    self.headers.get("Authorization"),
                )
            )
            parts = urlsplit(self.path)
            route = self.server.routes.get(parts.path)  # type: ignore[attr-defined]
            if route is None:
                self.server.unexpected.append(self.path)  # type: ignore[attr-defined]
                self.send_error(404)
                return
            query = parse_qs(parts.query, keep_blank_values=True)
            status, reply = route(query)
            self.send_response(status)
            self.send_header("Content-Type", reply.content_type)
            self.send_header("Content-Length", str(len(reply.body)))
            self.end_headers()
            self.wfile.write(reply.body)

        def log_message(self, format: str, *args: object) -> None:
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    httpd.calls = []  # type: ignore[attr-defined]
    httpd.unexpected = []  # type: ignore[attr-defined]
    httpd.routes = {}  # type: ignore[attr-defined]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd, f"http://127.0.0.1:{httpd.server_port}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


def route_ok(httpd, path: str, payload: object) -> None:
    httpd.routes[path] = lambda query: (200, json_reply(payload))


def route_pages(httpd, path: str, pages: dict[int, object]) -> None:
    """Отдать страницы по запрошенному ``startAt``; чужой offset — 400."""

    def handle(query):
        start = int(query["startAt"][0])
        if start not in pages:
            httpd.unexpected.append(f"{path}: startAt={start}")
            return 400, json_reply({"errorMessages": [SECRET + TOKEN]})
        return 200, json_reply(pages[start])

    httpd.routes[path] = handle


def assert_no_leak(httpd) -> None:
    assert httpd.unexpected == []
    assert all(authorization == "Bearer " + TOKEN for *_, authorization in httpd.calls)
    for method, target, _ in httpd.calls:
        assert method == "GET"
        assert TOKEN not in target


def assert_calls(httpd, expected: list[tuple[str, dict[str, list[str]]]]) -> None:
    """Сравнить путь и query каждого запроса, сохранив порядок вызовов."""
    assert len(httpd.calls) == len(expected), httpd.calls
    for (method, target, _), (path, query) in zip(httpd.calls, expected, strict=True):
        parsed = urlsplit(target)
        assert (method, parsed.path, parse_qs(parsed.query)) == (
            "GET",
            path,
            query,
        )


def issue_row(index: int) -> dict[str, object]:
    return {
        "key": f"SPEC-{index}",
        "fields": {
            "summary": f"issue {index}",
            "updated": "2024-01-01T00:00:00.000+0000",
        },
    }


def projected_row(index: int) -> dict[str, object]:
    return {
        "key": f"SPEC-{index}",
        "status": None,
        "type": None,
        "priority": None,
        "assignee": None,
        "updated": "2024-01-01",
        "summary": f"issue {index}",
    }


def worklog_row(index: int) -> dict[str, object]:
    return {
        "id": str(index),
        "author": {"name": "alice"},
        "started": "2024-01-01T00:00:00.000+0000",
        "timeSpentSeconds": 60 * index,
        "comment": f"work {index}",
        "unknown": {"nested": [index, None]},
    }


# --- 1. Одинаковый ``fields`` у search_raw и search_all_issues -----------------


def test_search_raw_fields_string_and_list_are_identical(server):
    """Строка и список полей дают один и тот же query, а пустой выбор падает."""
    httpd, base = server
    envelope = {"startAt": 0, "maxResults": 5, "total": 0, "issues": []}
    route_ok(httpd, SEARCH_PATH, envelope)
    assert (
        jira.search_raw(base, JQL, token=TOKEN, fields="summary,status", limit=5,
                        allow_http_loopback=True)
        == envelope
    )
    assert (
        jira.search_raw(base, JQL, token=TOKEN, fields=["summary", "status"],
                        limit=5, allow_http_loopback=True)
        == envelope
    )
    # Без явного fields обе функции используют один и тот же дефолт.
    assert jira.search_raw(base, JQL, token=TOKEN, limit=5,
                           allow_http_loopback=True) == envelope
    assert jira.search_all_issues(
        base, JQL, token=TOKEN, fields=["summary", "status"],
        allow_http_loopback=True,
    ) == []
    first = parse_qs(urlsplit(httpd.calls[0][1]).query)
    second = parse_qs(urlsplit(httpd.calls[1][1]).query)
    assert first == second
    assert first["fields"] == ["summary,status"]
    assert parse_qs(urlsplit(httpd.calls[2][1]).query)["fields"] == ["*all"]
    assert parse_qs(urlsplit(httpd.calls[3][1]).query)["fields"] == [
        "summary,status"
    ]
    calls_before = len(httpd.calls)
    for fields in ("", "   ", [], [""], ["summary", " "]):
        with pytest.raises(AtlaWireError):
            jira.search_raw(base, JQL, token=TOKEN, fields=fields, limit=5,
                            allow_http_loopback=True)
        with pytest.raises(AtlaWireError):
            jira.search_all_issues(base, JQL, token=TOKEN, fields=fields,
                                   allow_http_loopback=True)
    assert len(httpd.calls) == calls_before
    assert_no_leak(httpd)

# --- 2. Неполнота поиска видна без второго запроса ----------------------------


def test_search_issues_with_metadata_reports_truncation_without_extra_request(
    server,
):
    """total=244 при limit=5: пять строк помечены неполными одним запросом."""
    httpd, base = server
    route_ok(
        httpd,
        SEARCH_PATH,
        {"startAt": 0, "maxResults": 5, "total": 244,
         "issues": [issue_row(i) for i in range(5)]},
    )
    result = jira.search_issues_with_metadata(
        base, JQL, token=TOKEN, limit=5, allow_http_loopback=True
    )
    assert [row["key"] for row in result["rows"]] == [
        f"SPEC-{i}" for i in range(5)
    ]
    assert result["rows"] == [projected_row(i) for i in range(5)]
    assert result["truncated"] is True
    assert result["total"] == 244
    assert len(httpd.calls) == 1
    # Старая форма вызова не сломана: search_issues по-прежнему отдаёт список.
    assert jira.search_issues(
        base, JQL, token=TOKEN, limit=5, allow_http_loopback=True
    ) == [projected_row(i) for i in range(5)]
    assert len(httpd.calls) == 2
    assert_no_leak(httpd)


def test_search_issues_with_metadata_reports_complete_when_total_reached(server):
    """total равен числу строк: результат полный и total сохранён."""
    httpd, base = server
    route_ok(
        httpd,
        SEARCH_PATH,
        {"startAt": 0, "maxResults": 2, "total": 2,
         "issues": [issue_row(0), issue_row(1)]},
    )
    result = jira.search_issues_with_metadata(
        base, JQL, token=TOKEN, limit=5, allow_http_loopback=True
    )
    assert [row["key"] for row in result["rows"]] == ["SPEC-0", "SPEC-1"]
    assert result["truncated"] is False
    assert result["total"] == 2
    assert_no_leak(httpd)


def test_search_issues_with_metadata_marks_cap_without_total_as_incomplete(
    server,
):
    """Без серверного total достигнутый лимит нельзя считать полным ответом."""
    httpd, base = server
    route_ok(
        httpd,
        SEARCH_PATH,
        {"startAt": 0, "maxResults": 2,
         "issues": [issue_row(0), issue_row(1)]},
    )
    result = jira.search_issues_with_metadata(
        base, JQL, token=TOKEN, limit=2, allow_http_loopback=True
    )
    assert [row["key"] for row in result["rows"]] == ["SPEC-0", "SPEC-1"]
    assert result["truncated"] is True
    assert result["total"] is None
    assert len(httpd.calls) == 1
    assert_no_leak(httpd)


def test_search_all_issues_with_metadata_reports_limit_truncation(server):
    """Лимит меньше total: сырые строки возвращаются с признаком обрезки."""
    httpd, base = server
    route_ok(
        httpd,
        SEARCH_PATH,
        {"startAt": 0, "maxResults": 2, "total": 9,
         "issues": [issue_row(0), issue_row(1)]},
    )
    result = jira.search_all_issues_with_metadata(
        base, JQL, token=TOKEN, limit=2, allow_http_loopback=True
    )
    assert result["rows"] == [issue_row(0), issue_row(1)]
    assert result["truncated"] is True
    assert result["total"] == 9
    # Старая форма вызова не сломана: search_all_issues по-прежнему отдаёт список.
    assert jira.search_all_issues(
        base, JQL, token=TOKEN, limit=2, allow_http_loopback=True
    ) == [issue_row(0), issue_row(1)]
    assert len(httpd.calls) == 2
    assert_no_leak(httpd)


def test_search_all_issues_with_metadata_walks_to_total(server):
    """Достаточный лимит обходит все страницы и подтверждает полный результат."""
    httpd, base = server
    route_pages(
        httpd,
        SEARCH_PATH,
        {
            0: {"startAt": 0, "maxResults": 2, "total": 3,
                "issues": [issue_row(0), issue_row(1)]},
            2: {"startAt": 2, "maxResults": 1, "total": 3,
                "issues": [issue_row(2)]},
        },
    )
    result = jira.search_all_issues_with_metadata(
        base, JQL, token=TOKEN, limit=10, allow_http_loopback=True
    )
    assert result["rows"] == [issue_row(0), issue_row(1), issue_row(2)]
    assert result["truncated"] is False
    assert result["total"] == 3
    assert len(httpd.calls) == 2
    assert_no_leak(httpd)




# --- 3. Worklog: полный обход с бюджетом --------------------------------------


def test_list_issue_worklogs_walks_every_page(server):
    """Worklog обходится до total, строки возвращаются без потерь."""
    httpd, base = server
    route_pages(
        httpd,
        WORKLOG_PATH,
        {
            0: {"startAt": 0, "maxResults": 2, "total": 5,
                "worklogs": [worklog_row(1), worklog_row(2)]},
            2: {"startAt": 2, "maxResults": 2, "total": 5,
                "worklogs": [worklog_row(3), worklog_row(4)]},
            4: {"startAt": 4, "maxResults": 1, "total": 5,
                "worklogs": [worklog_row(5)]},
        },
    )
    rows = jira.list_issue_worklogs(
        base, "ABC-123", token=TOKEN, allow_http_loopback=True
    )
    assert [row["id"] for row in rows] == ["1", "2", "3", "4", "5"]
    assert rows == [worklog_row(i) for i in range(1, 6)]
    assert_calls(
        httpd,
        [
            (WORKLOG_PATH, {"startAt": ["0"], "maxResults": ["50"]}),
            (WORKLOG_PATH, {"startAt": ["2"], "maxResults": ["50"]}),
            (WORKLOG_PATH, {"startAt": ["4"], "maxResults": ["50"]}),
        ],
    )
    assert_no_leak(httpd)


def test_list_issue_worklogs_exhausted_budget_is_explicit_error(server):
    """Бюджет страниц кончился до total: явная ошибка вместо частичного списка."""
    httpd, base = server
    route_pages(
        httpd,
        WORKLOG_PATH,
        {
            0: {"startAt": 0, "maxResults": 2, "total": 5,
                "worklogs": [worklog_row(1), worklog_row(2)]},
            2: {"startAt": 2, "maxResults": 2, "total": 5,
                "worklogs": [worklog_row(3), worklog_row(4)]},
        },
    )
    with pytest.raises(AtlaWireError) as caught:
        jira.list_issue_worklogs(
            base, "ABC-123", token=TOKEN, max_pages=2,
            allow_http_loopback=True,
        )
    message = str(caught.value)
    assert "page limit" in message
    assert TOKEN not in message and SECRET not in message
    assert len(httpd.calls) == 2
    assert_no_leak(httpd)


def test_list_issue_worklogs_rejects_wrong_offset_instead_of_silent_repeat(
    server,
):
    """Сервер, игнорирующий startAt, даёт явную ошибку, а не тихую выдачу."""
    httpd, base = server

    offsets: list[int] = []

    def handle(query):
        # Эталонный сервер 8.22.2 игнорирует startAt и всегда отдаёт первый
        # лист; повторная страница должна быть замечена по эху startAt.
        offsets.append(int(query["startAt"][0]))
        return 200, json_reply(
            {"startAt": 0, "maxResults": 2, "total": 5,
             "worklogs": [worklog_row(1), worklog_row(2)]}
        )

    httpd.routes[WORKLOG_PATH] = handle
    with pytest.raises(AtlaWireError) as caught:
        jira.list_issue_worklogs(
            base, "ABC-123", token=TOKEN, allow_http_loopback=True
        )
    assert "startAt" in str(caught.value)
    # Второй запрос ушёл, но повторную страницу библиотека отвергла.
    assert offsets == [0, 2]
    assert len(httpd.calls) == 2
    assert_no_leak(httpd)


def test_list_issue_worklogs_http_error_is_sanitized(server):
    """HTTP-ошибка worklog не раскрывает тело ответа и токен."""
    httpd, base = server
    httpd.routes[WORKLOG_PATH] = lambda query: (
        403,
        http_error(403, {"errorMessages": [SECRET + TOKEN]}),
    )
    with pytest.raises(AtlaWireError) as caught:
        jira.list_issue_worklogs(
            base, "ABC-123", token=TOKEN, allow_http_loopback=True
        )
    rendered = "".join(traceback.format_exception(caught.value))
    assert SECRET not in rendered and TOKEN not in rendered
    assert caught.value.http_status == 403
    assert_no_leak(httpd)


# --- 4. Changelog: полная история или явная обрезка ---------------------------


def test_list_issue_changelog_returns_complete_history(server):
    """Полная история changelog возвращается как есть, вместе с неизвестными полями."""
    httpd, base = server
    histories = [
        {"id": "10", "author": {"name": "alice"}, "unknown": 7},
        {"id": "11", "author": {"name": "bob"}},
    ]
    route_ok(
        httpd,
        ISSUE_PATH,
        {"key": "ABC-123",
         "changelog": {"startAt": 0, "maxResults": 2, "total": 2,
                       "histories": histories}},
    )
    assert jira.list_issue_changelog(
        base, "ABC-123", token=TOKEN, allow_http_loopback=True
    ) == histories
    assert_calls(httpd, [(ISSUE_PATH, {"expand": ["changelog"]})])
    assert_no_leak(httpd)


def test_list_issue_changelog_incomplete_page_is_explicit_error(server):
    """Неполная история changelog — явная ошибка, а не тихие первые строки."""
    httpd, base = server
    route_ok(
        httpd,
        ISSUE_PATH,
        {"key": "ABC-123",
         "changelog": {"startAt": 0, "maxResults": 20, "total": 5,
                       "histories": [{"id": "10"}, {"id": "11"}]}},
    )
    with pytest.raises(AtlaWireError) as caught:
        jira.list_issue_changelog(
            base, "ABC-123", token=TOKEN, allow_http_loopback=True
        )
    message = str(caught.value)
    assert "changelog" in message.lower()
    assert "2" in message and "5" in message
    assert TOKEN not in message and SECRET not in message
    assert len(httpd.calls) == 1
    assert_no_leak(httpd)
