"""Чёрный ящик: частичный результат grep-repo и видимая неполнота истории коммитов.

Тесты поднимают loopback HTTP-сервер, который отвечает только документированными
маршрутами Bitbucket Server 5.10, и вызывают публичные функции библиотеки. Сеть,
учётные данные и monkeypatching не используются.

Проверяемые инварианты:
* исчерпанный общий бюджет grep-repo не теряет уже найденные хиты: они
  возвращаются вместе со статусом неполноты и подсказкой, как получить полный
  результат;
* исчерпанный бюджет без единого хита — явная ошибка с понятным действием;
* список коммитов с лимитом меньше общего числа помечается неполным, а
  достаточный лимит подтверждает полный обход строго по серверному
  ``nextPageStart``;
* ``get_last_modified`` без ``at`` сам подставляет полный коммит ветки по
  умолчанию, а path-форма не отдаёт наружу сырой HTTP 500;
* теги с лимитом меньше общего числа помечаются неполными.
"""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import NamedTuple
from urllib.parse import parse_qs, urlsplit

import pytest

from atlawire import bitbucket, repo_grep
from atlawire.http import AtlaWireError

TOKEN = "synthetic-grep-limits-token"
SECRET = "synthetic-private-error-body"
SHA = "a" * 40
ROOT = "/rest/api/1.0/projects/PROJ/repos/repo"


class Reply(NamedTuple):
    content_type: str
    body: bytes
    delay: float = 0.0
    status: int = 200


def json_reply(payload: object, *, delay: float = 0.0, status: int = 200) -> Reply:
    return Reply("application/json", json.dumps(payload).encode(), delay, status)


def text_reply(text: str, *, delay: float = 0.0) -> Reply:
    return Reply("text/plain", text.encode(), delay)


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
                    self.headers.get("Accept"),
                    self.headers.get("Authorization"),
                )
            )
            parts = urlsplit(self.path)
            handler = self.server.routes.get(parts.path)  # type: ignore[attr-defined]
            if handler is None:
                self.server.unexpected.append(self.path)  # type: ignore[attr-defined]
                self.send_error(404)
                return
            query = parse_qs(parts.query, keep_blank_values=True)
            try:
                reply = handler(query)
            except AssertionError as failure:
                self.server.unexpected.append(f"{self.path}: {failure}")  # type: ignore[attr-defined]
                self.send_error(400)
                return
            time.sleep(reply.delay)
            self.send_response(reply.status)
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
        thread.join(timeout=5)
        httpd.server_close()
        assert not thread.is_alive()


def default_branch(httpd, *, delay: float = 0.0) -> None:
    payload = {"displayId": "main", "id": "refs/heads/main", "latestCommit": SHA}
    httpd.routes[ROOT + "/branches/default"] = lambda query: json_reply(
        payload, delay=delay
    )


def file_listing(httpd, names: list[str]) -> None:
    payload = {"values": names, "start": 0, "size": len(names), "isLastPage": True}

    def handle(query):
        assert query["at"] == [SHA], query
        return json_reply(payload)

    httpd.routes[ROOT + "/files"] = handle


def raw_file(httpd, path: str, text: str, *, delay: float = 0.0) -> None:
    def handle(query):
        assert query["at"] == [SHA], query
        return text_reply(text, delay=delay)

    httpd.routes[ROOT + "/raw/" + path] = handle


def assert_no_leak(httpd) -> None:
    assert httpd.unexpected == []
    assert all(authorization == "Bearer " + TOKEN for *_, authorization in httpd.calls)


def test_grep_keeps_collected_hits_when_budget_is_exhausted(server):
    """Найденные до исчерпания бюджета хиты возвращаются со статусом неполноты."""
    httpd, base = server
    default_branch(httpd)
    file_listing(httpd, ["a.java", "b.java"])
    raw_file(httpd, "a.java", "class A { String contact; }\n")
    # Второй файл читается дольше остатка бюджета: после него бюджет уже пуст.
    raw_file(httpd, "b.java", "class B { String contact; }\n", delay=2.2)
    result = repo_grep.grep_repository(
        base,
        "PROJ/repo",
        "contact",
        token=TOKEN,
        limit=10,
        timeout_s=2.0,
        allow_http_loopback=True,
    )
    assert [hit["file"] for hit in result["hits"]] == ["a.java"]
    assert result["status"] == "timeout"
    assert result["complete"] is False
    assert result["truncated"] is True
    assert result["files_scanned"] == 1
    assert result["files_eligible"] == 2
    message = result["message"] or ""
    assert "timeout" in message.lower()
    assert "glob" in message and "path" in message
    assert TOKEN not in message and SECRET not in message
    assert_no_leak(httpd)


def test_grep_budget_without_hits_is_an_actionable_error(server):
    """Бюджет без хитов — явная ошибка с подсказкой увеличить таймаут или сузить область."""
    httpd, base = server
    default_branch(httpd, delay=1.5)
    with pytest.raises(AtlaWireError) as caught:
        repo_grep.grep_repository(
            base,
            "PROJ/repo",
            "contact",
            token=TOKEN,
            limit=10,
            timeout_s=1.0,
            allow_http_loopback=True,
        )
    message = str(caught.value)
    assert "timeout" in message.lower()
    assert "glob" in message and "path" in message
    assert TOKEN not in message and SECRET not in message
    assert_no_leak(httpd)


def commits_route(pages: list[tuple[int, tuple[int, ...], int]]):
    """Отдать страницы по серверному курсору; порядок start задаётся тестом."""
    remaining = list(pages)

    def handle(query):
        start = int(query["start"][0])
        size = int(query["limit"][0])
        expected_start, rows, next_start = remaining.pop(0)
        assert start == expected_start, start
        taken = rows[:size]
        rest = rows[len(taken) :]
        last = not rest and not remaining
        payload: dict[str, object] = {
            "values": [
                {"id": f"{row:040x}", "message": f"commit {row}"} for row in taken
            ],
            "start": start,
            "size": len(taken),
            "limit": size,
            "isLastPage": last,
        }
        if not last:
            payload["nextPageStart"] = next_start if not rest else start + len(taken)
        return json_reply(payload)

    return handle


def test_list_commits_metadata_reports_incomplete_limited_listing(server):
    """Лимит 3 при пяти коммитах помечает список неполным, не меняя list_commits."""
    httpd, base = server
    httpd.routes[ROOT + "/commits"] = commits_route([(0, (0, 1), 3), (3, (3, 4), 0)])
    result = bitbucket.list_commits_with_metadata(
        base, "PROJ/repo", token=TOKEN, limit=3, allow_http_loopback=True
    )
    assert len(result["commits"]) == 3
    assert result["limit"] == 3
    assert result["complete"] is False
    assert [row["id"] for row in result["commits"]] == [f"{i:040x}" for i in (0, 1, 3)]
    # Текущая форма вызова остаётся прежней: список коммитов без метаданных.
    httpd.routes[ROOT + "/commits"] = commits_route([(0, (0, 1), 3), (3, (3, 4), 0)])
    rows = bitbucket.list_commits(
        base, "PROJ/repo", token=TOKEN, limit=3, allow_http_loopback=True
    )
    assert [row["id"] for row in rows] == [f"{i:040x}" for i in (0, 1, 3)]
    assert_no_leak(httpd)


def test_list_commits_metadata_walks_server_cursor_to_the_end(server):
    """Достаточный лимит обходит все страницы только по серверному nextPageStart."""
    httpd, base = server
    # Курсор второй страницы (3) не равен start+size первой (2): клиент обязан
    # использовать nextPageStart, иначе запросит чужой start и получит ошибку.
    httpd.routes[ROOT + "/commits"] = commits_route([(0, (0, 1), 3), (3, (3, 4), 0)])
    result = bitbucket.list_commits_with_metadata(
        base, "PROJ/repo", token=TOKEN, limit=10, allow_http_loopback=True
    )
    assert [row["id"] for row in result["commits"]] == [
        f"{i:040x}" for i in (0, 1, 3, 4)
    ]
    assert result["complete"] is True
    assert [urlsplit(call[1]).path for call in httpd.calls] == [ROOT + "/commits"] * 2
    assert_no_leak(httpd)


def test_last_modified_without_at_resolves_default_branch_commit(server):
    """Без at функция сама берёт коммит ветки по умолчанию и передаёт его явно."""
    httpd, base = server
    payload = {"files": {"README.md": {"id": SHA}}, "latestCommit": {"id": SHA}}
    default_branch(httpd)

    def handle(query):
        assert query == {"at": [SHA]}, query
        return json_reply(payload)

    httpd.routes[ROOT + "/last-modified"] = handle
    assert (
        bitbucket.get_last_modified(
            base, "PROJ/repo", token=TOKEN, allow_http_loopback=True
        )
        == payload
    )
    assert [urlsplit(call[1]).path for call in httpd.calls] == [
        ROOT + "/branches/default",
        ROOT + "/last-modified",
    ]
    assert_no_leak(httpd)


def test_last_modified_path_failure_is_a_clear_error(server):
    """HTTP 500 path-формы превращается в понятную ошибку, а не в сырой статус."""
    httpd, base = server
    httpd.routes[ROOT + "/last-modified/src/main/A.java"] = lambda query: json_reply(
        {"errors": [{"message": SECRET}]}, status=500
    )
    with pytest.raises(AtlaWireError) as caught:
        bitbucket.get_last_modified(
            base,
            "PROJ/repo",
            "src/main/A.java",
            token=TOKEN,
            at=SHA,
            allow_http_loopback=True,
        )
    error = caught.value
    message = str(error)
    assert error.http_status == 500
    assert "directory" in message and "root" in message
    assert "request failed" not in message
    assert TOKEN not in message and SECRET not in message
    assert_no_leak(httpd)


TAGS = [{"id": f"tag-{index}"} for index in range(5)]


def tags_route(httpd, total: int) -> None:
    def handle(query):
        start = int(query["start"][0])
        size = int(query["limit"][0])
        rows = TAGS[start : start + min(size, 2)]
        last = start + len(rows) >= total
        payload: dict[str, object] = {
            "values": rows,
            "start": start,
            "size": len(rows),
            "isLastPage": last,
        }
        if not last:
            payload["nextPageStart"] = start + len(rows)
        return json_reply(payload)

    httpd.routes[ROOT + "/tags"] = handle


def test_list_tags_metadata_reports_incomplete_and_complete(server):
    """limit=2 при 5 тегах видит неполноту, достаточный лимит подтверждает конец."""
    httpd, base = server
    tags_route(httpd, len(TAGS))
    limited = bitbucket.list_tags_with_metadata(
        base, "PROJ/repo", token=TOKEN, limit=2, allow_http_loopback=True
    )
    assert [row["id"] for row in limited["tags"]] == ["tag-0", "tag-1"]
    assert limited["limit"] == 2
    assert limited["complete"] is False
    full = bitbucket.list_tags_with_metadata(
        base, "PROJ/repo", token=TOKEN, limit=10, allow_http_loopback=True
    )
    assert [row["id"] for row in full["tags"]] == [f"tag-{index}" for index in range(5)]
    assert full["complete"] is True
    legacy = bitbucket.list_tags(
        base, "PROJ/repo", token=TOKEN, limit=2, allow_http_loopback=True
    )
    assert [row["id"] for row in legacy] == ["tag-0", "tag-1"]
    assert_no_leak(httpd)
