"""Typed failures name their product without text parsing."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from atlawire import bitbucket, confluence, jira
from atlawire.http import AtlaWireError

TOKEN = "synthetic-product-context-token"


@pytest.fixture
def server():
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def do_GET(self):
            self.send_response(404)
            body = json.dumps({"errors": [{"message": "no"}]}).encode()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_port}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


@pytest.mark.parametrize(
    ("call", "product"),
    [
        (
            lambda base: jira.get_issue(
                base, "DEMO-1", token=TOKEN, allow_http_loopback=True
            ),
            "jira",
        ),
        (
            lambda base: confluence.get_page(
                base, "1", token=TOKEN, allow_http_loopback=True
            ),
            "confluence",
        ),
        (
            lambda base: bitbucket.list_repository_files(
                base, "PRJ/repo", token=TOKEN, allow_http_loopback=True
            ),
            "bitbucket",
        ),
    ],
)
def test_a_typed_failure_names_its_product(server, call, product):
    with pytest.raises(AtlaWireError) as caught:
        call(server)

    assert caught.value.category == "http"
    assert caught.value.http_status == 404
    assert caught.value.product == product
    # A typed call has no registry operation ID, and says so honestly.
    assert caught.value.operation is None


def test_a_transport_failure_also_names_the_product(monkeypatch):
    from atlawire import http as transport

    with (
        pytest.raises(AtlaWireError) as caught,
        transport.bearer_session(TOKEN, product="jira") as session,
    ):
        transport.get_json_object(session, "http://127.0.0.1:1/none", params={})

    assert caught.value.category == "transport"
    assert caught.value.product == "jira"


def test_a_session_without_a_product_stays_none():
    from atlawire import http as transport

    with transport.bearer_session(TOKEN) as session:
        assert transport._session_product(session) is None
