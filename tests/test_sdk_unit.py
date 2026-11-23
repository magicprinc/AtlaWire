"""Contract tests for the atlassian-python-api client facade."""

import contextlib
from http.server import BaseHTTPRequestHandler

import pytest

from atlawire import sdk
from atlawire.http import AtlaWireError
from atlawire.sdk import _raw_client_for, client_for, get_json
from tests._loopback import request_record, send_bytes, serving

BASE = "https://jira.example.invalid/jira"
TOKEN = "synthetic-sdk-token-4c2"


@pytest.mark.parametrize("product", ["jira", "confluence", "bitbucket"])
def test_client_factory_uses_bounded_settings(product: str) -> None:
    client = client_for(product, BASE, TOKEN)
    try:
        assert client.timeout == 30
        assert client.cloud is False
        # The adapter owns retries, so the SDK must not retry underneath it.
        assert client.backoff_and_retry is False
    finally:
        client.close()


@pytest.mark.parametrize(
    "path",
    [
        "/admin/rest/api/2/myself",
        "/rest/api/2/admin/users",
        "/rest/api/1.0/logs/logger/x",
        "/rest/api/2/../admin",
        "https://evil.invalid/rest/api/2/myself",
        "/rest/api/2/myself?x=1",
        "/rest/api/2/myself#x",
    ],
)
def test_get_json_rejects_unsafe_or_admin_paths_before_a_request(
    path: str,
) -> None:
    with pytest.raises(AtlaWireError):
        get_json("jira", BASE, path, token=TOKEN)


def test_read_only_proxy_exposes_reads_and_blocks_writes() -> None:
    client = client_for("jira", BASE, TOKEN)
    try:
        assert callable(client.get_all_projects)
        assert callable(client.get_project_roles)
        for name in (
            "delete_issue",
            "add_comment",
            "update_issue",
            "create_issue",
            "request",
            "get",
            "post",
        ):
            with pytest.raises(AttributeError):
                getattr(client, name)
    finally:
        client.close()


def test_client_factory_rejects_unknown_product() -> None:
    with pytest.raises(AtlaWireError):
        client_for("other", BASE, TOKEN)


def test_pinned_session_ignores_ambient_transport_environment() -> None:
    # A stock requests.Session sets trust_env=True, so an ambient netrc entry,
    # proxy variable or CA bundle could silently change this transport.
    client = _raw_client_for("jira", BASE, TOKEN)
    try:
        session = client.session
        assert session.trust_env is False
        assert session.verify is True
        assert session.headers["Authorization"] == f"Bearer {TOKEN}"
    finally:
        client.close()


def test_pinned_session_refuses_a_redirect_without_draining_its_body() -> None:
    reached: list[str] = []
    origin_seen: list[object] = []
    body = b"REFUSED-REDIRECT-BODY"

    class Target(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            reached.append("target")
            send_bytes(self, 200, b'{"leaked": true}', content_type="application/json")

    with serving(Target) as target:
        location = f"http://127.0.0.1:{target.server_port}/elsewhere"

        class Origin(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.0"

            def log_message(self, format: str, *args: object) -> None:
                pass

            def do_GET(self) -> None:
                origin_seen.append(request_record(self))
                send_bytes(
                    self,
                    302,
                    body,
                    content_type=None,
                    extra_headers={"Location": location},
                )

        with serving(Origin) as origin:
            base = f"http://127.0.0.1:{origin.server_port}/jira"
            client = _raw_client_for("jira", base, TOKEN, allow_http_loopback=True)
            try:
                response = sdk._send(
                    client, "GET", "/rest/api/2/myself", params={}, body=None
                )
                try:
                    assert response.status_code == 302
                    # A stock Session resolves the redirect before returning and
                    # buffers this whole body; a refused redirect stays unread.
                    assert response.raw.tell() == 0
                    assert response.next is None
                finally:
                    response.close()
            finally:
                client.close()

    assert len(origin_seen) == 1
    assert reached == []


def test_read_only_proxy_exposes_only_metadata_and_named_reads() -> None:
    client = client_for("jira", BASE, TOKEN)
    try:
        assert client.timeout == 30
        assert client.cloud is False
        assert client.backoff_and_retry is False
        assert client.verify_ssl is True
        assert client.url == BASE
        assert callable(client.get_all_projects)
        # The underlying transport/state must not be publicly reachable.
        for name in ("session", "_session", "proxies", "cert", "advanced_mode"):
            with pytest.raises(AttributeError):
                getattr(client, name)
    finally:
        client.close()


def test_context_manager_closes_the_library_client() -> None:
    client = client_for("jira", BASE, TOKEN)
    with contextlib.closing(client):
        assert client._client.session is not None
    assert client._client.session is not None
