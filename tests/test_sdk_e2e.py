"""Loopback E2E for the atlassian-python-api facade."""

import json
from http.server import BaseHTTPRequestHandler

import pytest

from atlawire.sdk import SdkRequestError, client_for, get_json
from tests._loopback import Request, request_record, send_bytes, send_json, serving

TOKEN = "synthetic-sdk-e2e-token-91b"
CONTEXT = "/jira"
SENTINEL = "SDK-E2E-SENTINEL"


def _handler(
    seen: list[Request],
    *,
    status: int = 200,
    payload: object | None = None,
    location: str | None = None,
) -> type[BaseHTTPRequestHandler]:
    body = json.dumps(payload if payload is not None else {"ok": True}).encode()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            seen.append(request_record(self))
            if location is not None:
                send_bytes(
                    self,
                    302,
                    b"",
                    content_type=None,
                    extra_headers={"Location": location},
                )
                return
            send_bytes(self, status, body, content_type="application/json")

    return Handler


def test_get_json_uses_library_client_and_preserves_query() -> None:
    seen: list[Request] = []
    with serving(_handler(seen)) as server:
        base = f"http://127.0.0.1:{server.server_port}{CONTEXT}"
        result = get_json(
            "jira",
            base,
            "/rest/api/2/myself",
            token=TOKEN,
            params={"expand": "groups", "maxResults": 2},
            allow_http_loopback=True,
        )

    assert result == {"ok": True}
    assert seen == [
        (
            "GET",
            f"{CONTEXT}/rest/api/2/myself",
            {"expand": ["groups"], "maxResults": ["2"]},
            f"Bearer {TOKEN}",
        )
    ]


def test_get_json_maps_401_without_echoing_the_response_body() -> None:
    seen: list[Request] = []
    with serving(_handler(seen, status=401, payload={"message": SENTINEL})) as server:
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
    assert envelope["ok"] is False
    assert envelope["error"]["status"] == 401
    assert envelope["error"]["classification"] == "authentication"
    assert envelope["error"]["body_json"] == {"message": SENTINEL}
    assert SENTINEL in envelope["error"]["body"]
    assert len(seen) == 1


def test_library_high_level_method_hits_the_configured_context_path() -> None:
    seen: list[Request] = []
    payload = {"name": "ada", "displayName": "Ada"}
    with serving(_handler(seen, payload=payload)) as server:
        base = f"http://127.0.0.1:{server.server_port}{CONTEXT}"
        client = client_for("jira", base, TOKEN, allow_http_loopback=True)
        try:
            assert client.myself() == payload
        finally:
            client.close()

    assert seen == [
        ("GET", f"{CONTEXT}/rest/api/2/myself", {}, f"Bearer {TOKEN}")
    ]
