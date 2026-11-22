"""Loopback contracts for the shared SDK read adapter.

Each test drives the real ``atlassian-python-api`` client against a synthetic
server. No credentials, no external network and no real product are used.
"""

import json
import time
from http.server import BaseHTTPRequestHandler

import pytest

from atlawire import sdk
from atlawire.http import AtlaWireError
from atlawire.sdk import SdkRequestError, get_json, request_json
from tests._loopback import request_record, send_bytes, send_json, serving

TOKEN = "synthetic-transport-token-7c2"
CONTEXT = "/jira"


def _error_code(exc: SdkRequestError) -> str:
    return exc.code


def test_redirect_is_refused_without_contacting_its_destination() -> None:
    reached: list[str] = []

    class Target(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            reached.append("target")
            send_json(self, 200, {"leaked": True})

    with serving(Target) as target:
        location = f"http://127.0.0.1:{target.server_port}/elsewhere"
        origin_seen: list[object] = []

        class Origin(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.0"

            def log_message(self, format: str, *args: object) -> None:
                pass

            def do_GET(self) -> None:
                origin_seen.append(request_record(self))
                send_bytes(
                    self,
                    302,
                    b"",
                    content_type=None,
                    extra_headers={"Location": location},
                )

        with serving(Origin) as origin:
            base = f"http://127.0.0.1:{origin.server_port}{CONTEXT}"
            with pytest.raises(SdkRequestError) as caught:
                get_json(
                    "jira",
                    base,
                    "/rest/api/2/myself",
                    token=TOKEN,
                    allow_http_loopback=True,
                )

    assert len(origin_seen) == 1
    assert reached == []
    assert caught.value.status == 302
    assert caught.value.classification == "unexpected_redirect"


def test_repeated_503_stops_after_three_attempts_and_keeps_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[object] = []
    sleeps: list[float] = []

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            seen.append(request_record(self))
            send_bytes(
                self, 503, b'{"message":"busy"}', content_type="application/json"
            )

    monkeypatch.setattr(time, "sleep", sleeps.append)
    with serving(Handler) as server:
        base = f"http://127.0.0.1:{server.server_port}{CONTEXT}"
        with pytest.raises(SdkRequestError) as caught:
            get_json(
                "jira",
                base,
                "/rest/api/2/myself",
                token=TOKEN,
                allow_http_loopback=True,
            )

    assert len(seen) == 3
    assert sleeps == [1.0, 2.0]
    assert caught.value.status == 503
    assert caught.value.code == "http_503"


def test_retry_after_beyond_budget_does_not_sleep_or_repeat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[object] = []

    def refuse(seconds: float) -> None:
        raise AssertionError(f"unexpected sleep of {seconds} seconds")

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            seen.append(request_record(self))
            send_bytes(
                self,
                429,
                b'{"message":"slow down"}',
                content_type="application/json",
                extra_headers={"Retry-After": "90"},
            )

    monkeypatch.setattr(time, "sleep", refuse)
    with serving(Handler) as server:
        base = f"http://127.0.0.1:{server.server_port}{CONTEXT}"
        with pytest.raises(SdkRequestError) as caught:
            get_json(
                "jira",
                base,
                "/rest/api/2/myself",
                token=TOKEN,
                allow_http_loopback=True,
            )

    assert len(seen) == 1
    assert caught.value.status == 429
    assert caught.value.code == "http_429"


def test_dropped_connection_recovers_on_the_second_attempt() -> None:
    attempts: list[int] = []

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            attempts.append(1)
            if len(attempts) == 1:
                self.close_connection = True
                return
            send_json(self, 200, {"name": "ada"})

    with serving(Handler) as server:
        base = f"http://127.0.0.1:{server.server_port}{CONTEXT}"
        result = get_json(
            "jira",
            base,
            "/rest/api/2/myself",
            token=TOKEN,
            allow_http_loopback=True,
        )

    assert result == {"name": "ada"}
    assert len(attempts) == 2


def test_non_json_success_is_an_error_not_a_string() -> None:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            send_bytes(self, 200, b"<html>login</html>", content_type="text/html")

    with serving(Handler) as server:
        base = f"http://127.0.0.1:{server.server_port}{CONTEXT}"
        with pytest.raises(SdkRequestError) as caught:
            get_json(
                "jira",
                base,
                "/rest/api/2/myself",
                token=TOKEN,
                allow_http_loopback=True,
            )

    assert caught.value.code == "invalid_response"
    assert caught.value.status == 200
    body = caught.value.to_dict(product="jira", token=TOKEN)["error"]
    assert "login" in body["body"]
    assert body["body_json"] is None


def test_non_finite_json_number_is_rejected() -> None:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            send_bytes(self, 200, b'{"value": NaN}', content_type="application/json")

    with serving(Handler) as server:
        base = f"http://127.0.0.1:{server.server_port}{CONTEXT}"
        with pytest.raises(SdkRequestError) as caught:
            get_json(
                "jira",
                base,
                "/rest/api/2/myself",
                token=TOKEN,
                allow_http_loopback=True,
            )

    assert caught.value.code == "invalid_response"


def test_oversized_body_without_length_is_refused_while_streaming(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A client that waits for EOF or buffers the whole body fails here."""
    monkeypatch.setattr(sdk, "_JSON_LIMIT", 512)
    chunk = b"x" * 4096
    total_chunks = 2048  # 8 MiB, far beyond any loopback send buffer
    written: list[int] = []

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            # No Content-Length and a body larger than the configured limit.
            self.connection.settimeout(2)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            for _ in range(total_chunks):
                try:
                    self.wfile.write(chunk)
                    self.wfile.flush()
                except OSError:
                    return
                written.append(1)
            self.close_connection = True

    with serving(Handler) as server:
        base = f"http://127.0.0.1:{server.server_port}{CONTEXT}"
        with pytest.raises(SdkRequestError) as caught:
            get_json(
                "jira",
                base,
                "/rest/api/2/myself",
                token=TOKEN,
                allow_http_loopback=True,
            )

    assert caught.value.code == "invalid_response"
    assert caught.value.status == 200
    assert len(written) < total_chunks


def test_oversized_http_error_keeps_status_and_truncates_excerpt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sdk, "_BODY_LIMIT", 64)
    body = json.dumps({"message": "x" * 500}).encode()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            send_bytes(self, 400, body, content_type="application/json")

    with serving(Handler) as server:
        base = f"http://127.0.0.1:{server.server_port}{CONTEXT}"
        with pytest.raises(SdkRequestError) as caught:
            get_json(
                "jira",
                base,
                "/rest/api/2/myself",
                token=TOKEN,
                allow_http_loopback=True,
            )

    envelope = caught.value.to_dict(product="jira", token=TOKEN)
    assert envelope["error"]["status"] == 400
    assert envelope["error"]["body_truncated"] is True
    assert envelope["error"]["body_json"] is None
    assert len(envelope["error"]["body"]) <= 64


def test_semantic_post_is_not_retried_on_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[object] = []

    def refuse(seconds: float) -> None:
        raise AssertionError("a semantic POST must not be retried")

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length") or "0")
            self.rfile.read(length)
            seen.append(request_record(self))
            send_bytes(self, 503, b"{}", content_type="application/json")

    monkeypatch.setattr(time, "sleep", refuse)
    with serving(Handler) as server:
        base = f"http://127.0.0.1:{server.server_port}{CONTEXT}"
        with pytest.raises(SdkRequestError) as caught:
            request_json(
                "jira",
                base,
                "/rest/api/2/search",
                method="POST",
                token=TOKEN,
                body={"jql": "order by created DESC"},
                allow_http_loopback=True,
            )

    assert len(seen) == 1
    assert caught.value.status == 503


@pytest.mark.parametrize("value", [["a", "b"], {"nested": 1}, True, None])
def test_query_values_must_be_scalars(value: object) -> None:
    with pytest.raises(AtlaWireError, match="strings or integers"):
        get_json(
            "jira",
            "https://example.invalid",
            "/rest/api/2/myself",
            token=TOKEN,
            params={"bad": value},
        )
