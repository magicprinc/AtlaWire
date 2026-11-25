"""The vendor names and the `hash` compatibility alias must stay in lockstep.

New code reads `id` and `displayId`. Code written before 0.9.2 reads `hash`, and
must keep getting the same full identifier so an upgrade does not break a caller
mid-flight. A silent removal of the alias is exactly the regression this pins.
"""

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from atlawire import bitbucket

TOKEN = "synthetic-alias-token"
SHA = "a" * 40
SHORT = SHA[:12]
ROOT = "/rest/api/1.0/projects/PROJ/repos/repo"


@pytest.fixture
def server():
    payload = (
        '{"isLastPage": true, "values": [{"id": "'
        + SHA
        + '", "displayId": "'
        + SHORT
        + '", "message": "m", "author": {"name": "alice"}, '
        '"authorTimestamp": 1700000000000}]}'
    ).encode()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

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


@pytest.fixture
def row(server):
    return bitbucket.list_commits(
        server, "PROJ/repo", token=TOKEN, limit=1, allow_http_loopback=True
    )[0]


def test_vendor_names_are_present(row):
    assert row["id"] == SHA
    assert row["displayId"] == SHORT


def test_hash_keeps_pointing_at_the_full_identifier(row):
    """An old caller passes `hash` back into `get_commit`; that must still work."""
    assert row["hash"] == row["id"] == SHA


def test_short_identifier_is_never_confused_with_the_full_one(row):
    assert row["displayId"] != row["id"]
    assert row["id"].startswith(row["displayId"])


def test_the_projection_exposes_exactly_the_documented_keys(row):
    """No third spelling of one value may appear."""
    assert set(row) == {
        "id",
        "displayId",
        "hash",
        "date",
        "timestamp",
        "author",
        "email",
        "displayName",
        "message",
    }
