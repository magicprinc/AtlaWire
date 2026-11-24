import json
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest

from atlawire.confluence import get_page
from atlawire.http import AtlaWireError

PAGE = {
    "id": "123",
    "type": "page",
    "title": "Заголовок",
    "body": {"storage": {"value": "<p>text</p>"}},
    "version": {"number": 3},
    "space": {"key": "DOC"},
    "ancestors": [{"id": "1"}],
    "unknown": {"nested": [1, "extra"]},
}
EXPAND = "body.storage,version,space,ancestors"
TOKEN = "synthetic-token-xyz"
SENTINEL = "synthetic-response-sentinel-xyz"


@pytest.fixture
def server():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.server.calls.append(
                (self.command, self.path, self.headers.get("Authorization"))
            )
            body = self.server.body
            self.send_response(self.server.status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    httpd.calls = []
    httpd.status = 200
    httpd.body = json.dumps(PAGE, ensure_ascii=False).encode("utf-8")
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd, f"http://127.0.0.1:{httpd.server_port}"
    finally:
        httpd.shutdown()
        thread.join(timeout=5)
        httpd.server_close()


def test_get_page_wire_contract(server):
    httpd, url = server
    get_page(url, "123", token=TOKEN, allow_http_loopback=True)
    assert len(httpd.calls) == 1
    method, target, authorization = httpd.calls[0]
    assert authorization == "Bearer " + TOKEN
    parsed = urlsplit(target)
    assert method == "GET"
    assert parsed.path == "/rest/api/content/123"
    assert parse_qs(parsed.query) == {"expand": [EXPAND]}


def test_get_page_preserves_unknown_fields(server):
    _, url = server
    assert get_page(url, "123", token=TOKEN, allow_http_loopback=True) == PAGE


@pytest.mark.parametrize("status", [400, 401, 403, 404, 429])
def test_get_page_error_is_sanitized_and_not_retried(server, status, capsys, caplog):
    httpd, url = server
    httpd.status = status
    httpd.body = json.dumps({"message": SENTINEL, "token": TOKEN}).encode()
    with pytest.raises(AtlaWireError) as error:
        get_page(url, "123", token=TOKEN, allow_http_loopback=True)
    assert error.value.category == "http"
    assert error.value.http_status == status
    output = capsys.readouterr()
    diagnostic = str(error.value) + "".join(traceback.format_exception(error.value))
    diagnostic += output.out + output.err + caplog.text
    assert SENTINEL not in diagnostic
    assert TOKEN not in diagnostic
    assert len(httpd.calls) == 1
    assert httpd.calls[0][2] == "Bearer " + TOKEN
