"""Loopback servers and installed-CLI primitives shared by E2E tests."""

import json
import os
import shutil
import subprocess
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from urllib.parse import parse_qs, urlsplit

Request = tuple[str, str, dict[str, list[str]], str | None]


def request_record(handler: BaseHTTPRequestHandler) -> Request:
    """Capture method, path, query parameters, and Authorization header."""
    url = urlsplit(handler.path)
    return (
        handler.command,
        url.path,
        parse_qs(url.query, keep_blank_values=True),
        handler.headers.get("Authorization"),
    )


def send_json(handler: BaseHTTPRequestHandler, status: int, body: object) -> None:
    payload = json.dumps(body).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(payload)))
    handler.end_headers()
    handler.wfile.write(payload)


def send_bytes(
    handler: BaseHTTPRequestHandler,
    status: int,
    body: bytes,
    *,
    content_type: str | None = "text/plain; charset=utf-8",
    content_encoding: str | None = None,
    declared_length: int | None = None,
    extra_headers: Mapping[str, str] | None = None,
) -> None:
    """Send raw bytes, optionally declaring a different length or encoding."""
    handler.send_response(status)
    if content_type is not None:
        handler.send_header("Content-Type", content_type)
    if content_encoding is not None:
        handler.send_header("Content-Encoding", content_encoding)
    for name, value in (extra_headers or {}).items():
        handler.send_header(name, value)
    length = len(body) if declared_length is None else declared_length
    handler.send_header("Content-Length", str(length))
    handler.end_headers()
    handler.wfile.write(body)


@contextmanager
def serving(handler_class: type[BaseHTTPRequestHandler]) -> Iterator[HTTPServer]:
    server = HTTPServer(("127.0.0.1", 0), handler_class)
    worker = Thread(target=server.serve_forever, args=(0.05,), daemon=True)
    started = False
    try:
        worker.start()
        started = True
        yield server
    finally:
        if started:
            server.shutdown()
            worker.join(timeout=5)
        server.server_close()
        if started:
            assert not worker.is_alive()


def confluence_environment(origin: str, *, context: str, token: str) -> dict[str, str]:
    """Build an environment where only the requested Confluence URL is valid."""
    return {
        "ATLAWIRE_CONFLUENCE_URL": f"{origin}{context}/",
        "ATLAWIRE_CONFLUENCE_TOKEN": token,
        "ATLAWIRE_JIRA_URL": f"{origin}/wrong-jira/",
        "ATLAWIRE_JIRA_TOKEN": "wrong-product-fixture",
        "ATLAWIRE_BITBUCKET_URL": f"{origin}/wrong-bitbucket/",
        "ATLAWIRE_BITBUCKET_TOKEN": "wrong-product-fixture",
    }


def run_installed(
    args: list[str], environment: Mapping[str, str]
) -> subprocess.CompletedProcess[str]:
    """Run the installed console script with the given product environment."""
    script = shutil.which("atlawire")
    if script is None:
        raise AssertionError("Install AtlaWire before running its CLI E2E suite.")
    return subprocess.run(
        [script, *args],
        env={**os.environ, **environment},
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )


def run_installed_bytes(
    args: list[str], environment: Mapping[str, str]
) -> subprocess.CompletedProcess[bytes]:
    """Run the installed console script and preserve exact stdout bytes."""
    script = shutil.which("atlawire")
    if script is None:
        raise AssertionError("Install AtlaWire before running its CLI E2E suite.")
    return subprocess.run(
        [script, *args],
        env={**os.environ, **environment},
        capture_output=True,
        timeout=15,
        check=False,
    )
