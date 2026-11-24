"""End-to-end checks for the installed file command's revision default."""

import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "synthetic-file-e2e-token"
TEXT = b"line one\r\nline two\r\n"


@pytest.fixture
def server():
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def do_GET(self):
            self.server.calls.append(self.path)
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(TEXT)))
            self.end_headers()
            self.wfile.write(TEXT)

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    httpd.calls = []
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd, f"http://127.0.0.1:{httpd.server_port}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


def _run(base, *extra):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src")
    env["ATLAWIRE_BITBUCKET_URL"] = base
    env["ATLAWIRE_BITBUCKET_TOKEN"] = TOKEN
    return subprocess.run(
        [
            sys.executable,
            "-B",
            "-m",
            "atlawire",
            "file",
            "PRJ/repo",
            "dir/file.txt",
            "--base-url",
            base,
            "--token-from-env",
            "--allow-http-loopback",
            *extra,
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        env=env,
        timeout=120,
    )


def test_file_without_at_reads_the_server_default_branch(server):
    httpd, base = server

    result = _run(base)

    assert result.returncode == 0, result.stderr
    assert result.stdout == TEXT
    assert len(httpd.calls) == 1
    assert parse_qs(urlsplit(httpd.calls[0]).query) == {}


def test_file_with_at_keeps_the_explicit_revision(server):
    httpd, base = server

    result = _run(base, "--at", "master")

    assert result.returncode == 0, result.stderr
    assert parse_qs(urlsplit(httpd.calls[0]).query) == {"at": ["master"]}
