"""`expand=None` must let the server apply its own default.

The WADL documents `expand` as an ordinary query parameter of `GET /issue`, so a
caller has to be able to omit it. Before this change the parameter was always
sent, which made the server default unreachable through the typed call.
"""

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest

from atlawire import jira

TOKEN = "synthetic-expand-token"
ISSUE = b'{"key": "DEMO-1", "fields": {}}'


@pytest.fixture
def server():
    calls: list[dict[str, list[str]]] = []

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def do_GET(self):
            calls.append(parse_qs(urlsplit(self.path).query, keep_blank_values=True))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(ISSUE)))
            self.end_headers()
            self.wfile.write(ISSUE)

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield calls, f"http://127.0.0.1:{httpd.server_port}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


def test_default_still_asks_for_rendered_fields(server):
    calls, base = server

    jira.get_issue(base, "DEMO-1", token=TOKEN, allow_http_loopback=True)

    assert calls[0]["expand"] == ["renderedFields"]


def test_none_omits_expand_so_the_server_decides(server):
    calls, base = server

    jira.get_issue(base, "DEMO-1", token=TOKEN, expand=None, allow_http_loopback=True)

    assert "expand" not in calls[0]


def test_an_explicit_expand_is_sent_verbatim(server):
    calls, base = server

    jira.get_issue(
        base, "DEMO-1", token=TOKEN, expand="changelog", allow_http_loopback=True
    )

    assert calls[0]["expand"] == ["changelog"]
