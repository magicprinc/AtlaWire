"""Black-box contracts for the public transport session factory.

Every request stays on 127.0.0.1 and each assertion is driven by an observable
outcome: the status returned, the paths the loopback server received, the
Authorization header, or the exception. The machine's real proxy/CA settings
are replaced by a refused proxy so the environment cannot mask the policy.
"""

import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import cast

import pytest
import requests

from atlawire.http import AtlaWireError, new_session

TOKEN = "synthetic-session-factory-token"
BROKEN_PROXY = "http://127.0.0.1:1"
# Names that requests reads when session.trust_env is true; the developer
# machine in this session exports a live proxy for all of them.
AMBIENT = (
    "HTTP_PROXY",
    "http_proxy",
    "HTTPS_PROXY",
    "https_proxy",
    "ALL_PROXY",
    "all_proxy",
    "NO_PROXY",
    "no_proxy",
    "NODE_USE_ENV_PROXY",
    "REQUESTS_CA_BUNDLE",
    "CURL_CA_BUNDLE",
)


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    calls: list[tuple[str, str | None]]

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), _Handler)
        self.calls = []


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def log_message(self, format: str, *args: object) -> None:
        pass

    def do_GET(self) -> None:
        server = cast(_Server, self.server)
        server.calls.append((self.path, self.headers.get("Authorization")))
        if self.path == "/start":
            self.send_response(302)
            self.send_header("Location", "/next")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        body = b'{"ok": true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def server():
    httpd = _Server()
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd, f"http://127.0.0.1:{httpd.server_port}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


@pytest.fixture
def proxy_environment(monkeypatch):
    """Replace every ambient proxy/CA setting with one refused proxy."""
    for name in AMBIENT:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HTTP_PROXY", BROKEN_PROXY)


def paths(server) -> list[str]:
    return [path for path, _ in server.calls]


def diagnostic(error: BaseException) -> str:
    return "".join(traceback.format_exception(error))


def test_default_session_returns_redirect_without_requesting_location(
    server, proxy_environment
):
    httpd, base = server
    with new_session(base, TOKEN, allow_http_loopback=True) as session:
        response = session.get(base + "/start", timeout=5)
    assert response.status_code == 302
    assert response.headers["Location"] == "/next"
    assert response.history == []
    assert paths(httpd) == ["/start"]


def test_follow_redirects_session_requests_location(server, proxy_environment):
    httpd, base = server
    with new_session(
        base, TOKEN, follow_redirects=True, allow_http_loopback=True
    ) as session:
        response = session.get(base + "/start", timeout=5)
    assert response.status_code == 200
    assert response.url == base + "/next"
    assert paths(httpd) == ["/start", "/next"]
    assert [auth for _, auth in httpd.calls] == ["Bearer " + TOKEN] * 2


def test_trust_env_controls_proxy_use(server, proxy_environment):
    httpd, base = server
    with new_session(base, TOKEN, allow_http_loopback=True) as strict:
        response = strict.get(base + "/direct", timeout=5)
    assert response.status_code == 200
    assert paths(httpd) == ["/direct"]

    with (
        new_session(base, TOKEN, trust_env=True, allow_http_loopback=True) as ambient,
        pytest.raises(requests.RequestException) as caught,
    ):
        ambient.get(base + "/direct", timeout=5)
    assert isinstance(caught.value, requests.exceptions.ProxyError)
    assert paths(httpd) == ["/direct"]


def test_authorization_header_is_identical_in_both_redirect_modes(
    server, proxy_environment
):
    httpd, base = server
    with new_session(base, TOKEN, allow_http_loopback=True) as strict:
        strict.get(base + "/direct", timeout=5)
    with new_session(
        base, TOKEN, follow_redirects=True, allow_http_loopback=True
    ) as following:
        following.get(base + "/direct", timeout=5)
    assert [auth for _, auth in httpd.calls] == ["Bearer " + TOKEN] * 2


def test_tokenless_session_sends_no_authorization_header(server, proxy_environment):
    httpd, base = server
    with new_session(base, allow_http_loopback=True) as session:
        assert session.get(base + "/direct", timeout=5).status_code == 200
    assert httpd.calls == [("/direct", None)]


@pytest.mark.parametrize("token", ["", "token with space", "tok;en", "токен"])
def test_token_format_is_rejected_like_bearer_session(server, proxy_environment, token):
    httpd, base = server
    with pytest.raises(AtlaWireError) as caught:
        new_session(base, token, allow_http_loopback=True)
    assert caught.value.category == "credentials"
    assert httpd.calls == []


def test_errors_do_not_echo_the_token(server, proxy_environment):
    httpd, base = server
    malformed = TOKEN + " with spaces"
    with pytest.raises(AtlaWireError) as caught:
        new_session(base, malformed, allow_http_loopback=True)
    assert malformed not in diagnostic(caught.value)
    assert TOKEN not in diagnostic(caught.value)

    with pytest.raises(AtlaWireError) as caught:
        new_session(base + "?token=" + TOKEN, TOKEN, allow_http_loopback=True)
    assert TOKEN not in diagnostic(caught.value)

    dead = "http://127.0.0.1:1"
    with (
        new_session(dead, TOKEN, allow_http_loopback=True) as session,
        pytest.raises(requests.RequestException) as caught,
    ):
        session.get(dead + "/unreachable", timeout=5)
    assert TOKEN not in diagnostic(caught.value)
    assert httpd.calls == []
