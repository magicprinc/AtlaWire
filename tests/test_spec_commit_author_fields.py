"""Black-box contracts for the commit author and time projection.

Потребителю нужны email автора, необязательный ``displayName`` и точный
``authorTimestamp`` каждого коммита. Bitbucket Server 5.10 отдаёт их только в
строке ответа ``/commits``, рядом с git-именем, поэтому проекция обязана брать
все значения из той же страницы: отдельный запрос на коммит (N+1) недопустим.
Loopback-сервер ниже отвечает только на список коммитов, а счётчик запросов
проверяет, что клиент ограничился одним GET.

Reference: https://docs.atlassian.com/bitbucket-server/rest/5.10.0/bitbucket-rest.html
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest

from atlawire import bitbucket
from atlawire.http import AtlaWireError

TOKEN = "synthetic-commit-fields-token"
ROOT = "/rest/api/1.0/projects/PROJ/repos/repo"
SHA_A = "a" * 40
SHA_B = "b" * 40
SHA_C = "c" * 40


@pytest.fixture
def server():
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
            target = urlsplit(self.path)
            if target.path == f"{ROOT}/commits":
                status, payload = self.server.responses.pop(0)  # type: ignore[attr-defined]
            else:
                # Любой неожиданный маршрут — провал теста, а не тихий обход.
                status, payload = 500, {"errors": [{"message": "unexpected route"}]}
            data = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def finish(self):
            try:
                super().finish()
            finally:
                self.server.closed.set()  # type: ignore[attr-defined]

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    httpd.calls = []
    httpd.responses = []
    httpd.closed = threading.Event()
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd, f"http://127.0.0.1:{httpd.server_port}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


def page(values, *, last=True, next_start=None):
    payload = {"values": values, "isLastPage": last}
    if next_start is not None:
        payload["nextPageStart"] = next_start
    return payload


def assert_single_commit_request(httpd, *, limit):
    assert len(httpd.calls) == 1
    method, target, accept, auth = httpd.calls[0]
    parsed = urlsplit(target)
    assert (method, parsed.path, parse_qs(parsed.query)) == (
        "GET",
        f"{ROOT}/commits",
        {"start": ["0"], "limit": [str(limit)]},
    )
    assert accept == "application/json"
    assert auth == "Bearer " + TOKEN
    assert httpd.closed.wait(3), "client did not close the HTTP connection"


# 5.10 documents the commit author as {name, emailAddress}; authorTimestamp is
# epoch milliseconds. The projection must keep the raw milliseconds (the 123 ms
# remainder proves that date and timestamp are not the same rounded value) and
# keep displayName only when the server actually sends it.
def test_projection_keeps_email_display_name_and_raw_milliseconds(server):
    """email, displayName и точные миллисекунды приходят из той же строки списка."""
    httpd, url = server
    httpd.responses = [
        (
            200,
            page(
                [
                    {
                        "id": SHA_A,
                        "author": {
                            "name": "ada",
                            "emailAddress": "ada@example.invalid",
                            "displayName": "Ada Lovelace",
                        },
                        "authorTimestamp": 1744789253123,
                        "message": "one",
                    },
                    {
                        "id": SHA_B,
                        "author": {
                            "name": "bob",
                            "emailAddress": "bob@example.invalid",
                        },
                        "authorTimestamp": 1744790460000,
                        "message": "two",
                    },
                ]
            ),
        )
    ]
    listing = bitbucket.list_commits_with_metadata(
        url, "PROJ/repo", token=TOKEN, limit=2, allow_http_loopback=True
    )
    assert listing == {
        "commits": [
            {
                "id": SHA_A,
                "displayId": None,
                "hash": SHA_A,
                "date": "2025-04-16 07:40",
                "timestamp": 1744789253123,
                "author": "ada",
                "email": "ada@example.invalid",
                "displayName": "Ada Lovelace",
                "message": "one",
            },
            {
                "id": SHA_B,
                "displayId": None,
                "hash": SHA_B,
                "date": "2025-04-16 08:01",
                "timestamp": 1744790460000,
                "author": "bob",
                "email": "bob@example.invalid",
                "displayName": None,
                "message": "two",
            },
        ],
        "limit": 2,
        "complete": True,
    }
    # Два коммита, но ровно один GET: иначе это был бы N+1.
    assert_single_commit_request(httpd, limit=2)


# The fields are optional in the schema: a missing author object or a null
# authorTimestamp must project to None instead of inventing values.
def test_missing_author_fields_are_none(server):
    """Отсутствующие author/authorTimestamp дают None, а не подставленные значения."""
    httpd, url = server
    httpd.responses = [
        (
            200,
            page(
                [
                    {"id": SHA_C, "message": "no author"},
                    {
                        "id": SHA_A,
                        "author": {},
                        "authorTimestamp": None,
                        "message": "empty author",
                    },
                ]
            ),
        )
    ]
    rows = bitbucket.list_commits(
        url, "PROJ/repo", token=TOKEN, allow_http_loopback=True
    )
    assert rows == [
        {
            "id": SHA_C,
            "displayId": None,
            "hash": SHA_C,
            "date": None,
            "timestamp": None,
            "author": None,
            "email": None,
            "displayName": None,
            "message": "no author",
        },
        {
            "id": SHA_A,
            "displayId": None,
            "hash": SHA_A,
            "date": None,
            "timestamp": None,
            "author": None,
            "email": None,
            "displayName": None,
            "message": "empty author",
        },
    ]
    # limit по умолчанию 25 уходит в запрос, но и здесь должен быть один GET.
    assert_single_commit_request(httpd, limit=25)


# The exact time must stay an integer: coercing a string or a bool would hide a
# malformed server row and produce a plausible but wrong instant.
@pytest.mark.parametrize("stamp", ["1744789253123", True])
def test_non_integer_author_timestamp_rejected(server, stamp):
    """Нецелый authorTimestamp отвергается, а не приводится к числу."""
    httpd, url = server
    httpd.responses = [
        (200, page([{"id": SHA_A, "message": "bad stamp", "authorTimestamp": stamp}]))
    ]
    with pytest.raises(AtlaWireError):
        bitbucket.list_commits(url, "PROJ/repo", token=TOKEN, allow_http_loopback=True)
    assert len(httpd.calls) == 1
    assert httpd.closed.wait(3), "client did not close the HTTP connection"


# The author filter still selects on the git author name after the projection
# grew; the extra fields must not trigger more requests or change the match.
def test_author_selection_keeps_single_list_request(server):
    """Фильтр по автору работает по name и не добавляет запросов на коммит."""
    httpd, url = server
    httpd.responses = [
        (
            200,
            page(
                [
                    {
                        "id": SHA_A,
                        "author": {
                            "name": "ada",
                            "emailAddress": "ada@example.invalid",
                        },
                        "authorTimestamp": 1744789253123,
                        "message": "mine",
                    },
                    {
                        "id": SHA_B,
                        "author": {
                            "name": "bob",
                            "emailAddress": "bob@example.invalid",
                        },
                        "authorTimestamp": 1744790460000,
                        "message": "not mine",
                    },
                ]
            ),
        )
    ]
    rows = bitbucket.list_commits(
        url, "PROJ/repo", token=TOKEN, author="ada", limit=2, allow_http_loopback=True
    )
    assert rows == [
        {
            "id": SHA_A,
            "displayId": None,
            "hash": SHA_A,
            "date": "2025-04-16 07:40",
            "timestamp": 1744789253123,
            "author": "ada",
            "email": "ada@example.invalid",
            "displayName": None,
            "message": "mine",
        }
    ]
    assert_single_commit_request(httpd, limit=2)
