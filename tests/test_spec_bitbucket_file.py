import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest

from atlawire.bitbucket import get_repository_file
from atlawire.http import AtlaWireError

TOKEN = "synthetic-token-xyz"
SENTINEL = "synthetic-response-sentinel-xyz"
TEXT = "\ufeffПривет\r\nsecond\r\n"


@pytest.fixture
def server():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.server.calls.append((self.command, self.path, self.headers.get("Accept"), self.headers.get("Authorization")))
            body = self.server.body
            self.send_response(self.server.status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
                pass

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    httpd.calls = []
    httpd.status = 200
    httpd.body = TEXT.encode("utf-8")
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd, f"http://127.0.0.1:{httpd.server_port}"
    finally:
        httpd.shutdown()
        thread.join(timeout=5)
        httpd.server_close()




def test_file_wire_contract(server):
    httpd, url = server
    get_repository_file(url, "PROJ/repo", "dir/file.txt", token=TOKEN,
                        at="refs/heads/feature", allow_http_loopback=True)
    assert len(httpd.calls) == 1
    method, target, accept, authorization = httpd.calls[0]
    assert authorization == "Bearer " + TOKEN
    parsed = urlsplit(target)
    assert method == "GET"
    assert parsed.path == "/rest/api/1.0/projects/PROJ/repos/repo/raw/dir/file.txt"
    assert parse_qs(parsed.query) == {"at": ["refs/heads/feature"]}
    assert accept == "text/plain"


def test_file_preserves_utf8_bom_and_crlf(server):
    _, url = server
    result = get_repository_file(url, "PROJ/repo", "dir/file.txt", token=TOKEN,
                                 allow_http_loopback=True)
    assert result == TEXT
    assert result.encode("utf-8") == TEXT.encode("utf-8")


@pytest.mark.parametrize("status", [400, 401, 403, 404, 429])
def test_file_error_is_sanitized_and_not_retried(server, status, capsys, caplog):
    httpd, url = server
    httpd.status = status
    httpd.body = f"{SENTINEL} {TOKEN}".encode()
    with pytest.raises(AtlaWireError) as error:
        get_repository_file(url, "PROJ/repo", "dir/file.txt", token=TOKEN,
                            allow_http_loopback=True)
    assert error.value.category == "http"
    assert error.value.http_status == status
    output = capsys.readouterr()
    diagnostic = str(error.value) + "".join(traceback.format_exception(error.value))
    diagnostic += output.out + output.err + caplog.text
    assert SENTINEL not in diagnostic
    assert TOKEN not in diagnostic
    assert len(httpd.calls) == 1
    assert httpd.calls[0][3] == "Bearer " + TOKEN


def test_file_rejects_more_than_one_mib(server):
    httpd, url = server
    httpd.body = b"a" * (1024 * 1024 + 1)
    with pytest.raises(AtlaWireError, match="1 MiB"):
        get_repository_file(url, "PROJ/repo", "dir/file.txt", token=TOKEN,
                            allow_http_loopback=True)
    assert len(httpd.calls) == 1


def test_file_accepts_exactly_one_mib(server):
    httpd, url = server
    httpd.body = b"a" * (1024 * 1024)
    assert get_repository_file(url, "PROJ/repo", "dir/file.txt", token=TOKEN,
                               allow_http_loopback=True) == "a" * (1024 * 1024)
