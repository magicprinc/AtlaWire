"""End-to-end grep runs against a loopback Bitbucket snapshot."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest

from atlawire.repo_grep import grep_repository

TOKEN = "synthetic-grep-token"
SHA = "c" * 40
REPO_PATH = "/rest/api/1.0/projects/PRJ/repos/widgets"


@pytest.fixture
def server():
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def do_GET(self):
            parsed = urlsplit(self.path)
            if parsed.path == f"{REPO_PATH}/commits/{SHA}":
                self._json({"id": SHA})
            elif parsed.path == f"{REPO_PATH}/files":
                query = parse_qs(parsed.query)
                assert query.get("at") == [SHA]
                self._json(
                    {
                        "values": ["a.txt", "b.txt"],
                        "isLastPage": True,
                        "start": 0,
                        "size": 2,
                        "limit": 100,
                    }
                )
            elif parsed.path.startswith(f"{REPO_PATH}/raw/"):
                name = parsed.path.rsplit("/", 1)[-1]
                body = b"x\nx\n" if name in {"a.txt", "b.txt"} else b"nope\n"
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_error(404)

        def _json(self, value):
            body = json.dumps(value).encode("utf-8")
            self.send_response(200)
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


def _grep(base, limit):
    return grep_repository(
        base,
        "PRJ/widgets",
        "x",
        token=TOKEN,
        at=SHA,
        glob="*.txt",
        limit=limit,
        allow_http_loopback=True,
    )


def test_cap_reached_on_the_first_of_two_files_is_truncated(server):
    result = _grep(server, 2)

    assert result["status"] == "truncated"
    assert result["truncated"] is True
    assert result["complete"] is False
    assert len(result["hits"]) == 2


def test_cap_reached_after_the_last_file_is_complete(server):
    result = _grep(server, 4)

    assert result["status"] == "complete"
    assert result["truncated"] is False
    assert result["complete"] is True
    assert len(result["hits"]) == 4
