"""Regression contracts for the shared transport and file publication.

These cases were lost when the spec suite replaced the legacy suite. They are
deliberately narrow: each one fails on a removed or inverted guard.
"""

import gzip
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from atlawire import sdk
from atlawire.cli import _write_bytes
from atlawire.http import AtlaWireError, bearer_session, get_json_object

TOKEN = "synthetic-transport-safety-token"
JSON = "application/json"


class _State:
    def __init__(self) -> None:
        self.status = 200
        self.body = b""
        self.headers: dict[str, str] = {}


@pytest.fixture
def server():
    state = _State()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def do_GET(self):
            self.send_response(state.status)
            for name, value in state.headers.items():
                self.send_header(name, value)
            self.send_header("Content-Length", str(len(state.body)))
            self.end_headers()
            self.wfile.write(state.body)

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield state, f"http://127.0.0.1:{httpd.server_port}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


def _download(base, destination):
    return sdk.download_to_file(
        "jira",
        base,
        "/rest/api/2/attachment/1",
        token=TOKEN,
        destination=destination,
        allow_http_loopback=True,
    )


def _assert_no_staging(directory):
    assert list(directory.glob(".*.part")) == []


@pytest.mark.parametrize(
    "payload",
    [
        gzip.compress(b"x" * 100_000)[:32],
        gzip.compress(b"x" * 100_000)[:-8],
    ],
    ids=["truncated-member", "missing-trailer"],
)
def test_download_to_file_rejects_incomplete_gzip(server, tmp_path, payload):
    state, base = server
    state.body = payload
    state.headers = {
        "Content-Type": "application/octet-stream",
        "Content-Encoding": "gzip",
    }
    destination = tmp_path / "attachment.bin"

    with pytest.raises((sdk.SdkRequestError, AtlaWireError)):
        _download(base, destination)

    assert not destination.exists()
    _assert_no_staging(tmp_path)


def test_download_to_file_rejects_unsolicited_206(server, tmp_path):
    state, base = server
    state.status = 206
    state.body = b"partial"
    state.headers = {"Content-Type": "application/octet-stream"}
    destination = tmp_path / "attachment.bin"

    with pytest.raises((sdk.SdkRequestError, AtlaWireError)):
        _download(base, destination)

    assert not destination.exists()
    _assert_no_staging(tmp_path)


def test_download_to_file_does_not_clobber_an_existing_path(server, tmp_path):
    state, base = server
    state.body = b"new bytes"
    state.headers = {"Content-Type": "application/octet-stream"}
    destination = tmp_path / "attachment.bin"
    destination.write_bytes(b"original")

    with pytest.raises((sdk.SdkRequestError, AtlaWireError)):
        _download(base, destination)

    assert destination.read_bytes() == b"original"
    _assert_no_staging(tmp_path)


def test_request_json_rejects_a_gzip_member_missing_its_trailer(server):
    state, base = server
    state.body = gzip.compress(b'{"key": "DEMO-1"}')[:-8]
    state.headers = {"Content-Type": JSON, "Content-Encoding": "gzip"}

    with pytest.raises((sdk.SdkRequestError, AtlaWireError)):
        sdk.get_json(
            "jira", base, "/rest/api/2/myself", token=TOKEN, allow_http_loopback=True
        )


@pytest.mark.parametrize("literal", [b"1e999", b"-1e999", b"NaN", b"Infinity"])
def test_sdk_json_rejects_non_finite_numbers(server, literal):
    state, base = server
    state.body = b'{"value": ' + literal + b"}"
    state.headers = {"Content-Type": JSON}

    with pytest.raises((sdk.SdkRequestError, AtlaWireError)):
        sdk.get_json(
            "jira", base, "/rest/api/2/myself", token=TOKEN, allow_http_loopback=True
        )


@pytest.mark.parametrize("literal", [b"1e999", b"-1e999", b"NaN", b"Infinity"])
def test_http_json_rejects_non_finite_numbers(server, literal):
    state, base = server
    state.body = b'{"value": ' + literal + b"}"
    state.headers = {"Content-Type": JSON}

    with bearer_session(TOKEN) as session, pytest.raises(AtlaWireError):
        get_json_object(session, base + "/rest/api/2/myself", params={})


def test_write_bytes_does_not_clobber_an_existing_path(tmp_path):
    destination = tmp_path / "attachment.bin"
    destination.write_bytes(b"original")

    with pytest.raises(AtlaWireError, match="already exists"):
        _write_bytes(str(destination), b"new bytes")

    assert destination.read_bytes() == b"original"
    assert list(tmp_path.glob(".*.part")) == []


def test_write_bytes_publishes_a_new_file(tmp_path):
    destination = tmp_path / "attachment.bin"

    receipt = _write_bytes(str(destination), b"new bytes")

    assert destination.read_bytes() == b"new bytes"
    assert receipt["bytes"] == len(b"new bytes")
    assert list(tmp_path.glob(".*.part")) == []
