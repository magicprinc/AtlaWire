"""Installed-CLI loopback E2E tests for the read-only ``attachment-get`` command.

Every response and credential is synthetic and served by a loopback HTTP
server. No test contacts a real instance or reads a real credential store.

These tests exercise the wired command
``attachment-get REPO ID --base64 [--max-bytes N]``, which calls
[get_repository_attachment][atlawire.bitbucket_attachment.get_repository_attachment]
and checks the final serialized output against the active token. The success
output contract is exactly one JSON object with one ``base64`` string field,
for example ``{"base64": "AAECAw=="}``; a bare JSON string or any other field is
rejected by these tests. A failed read prints nothing on stdout.

The server route is BBK-observed and not documented in the local Bitbucket
Server 5.10 core reference, so these tests do not claim version support.
"""

import base64
import gzip
import json
import subprocess
import zlib
from collections.abc import Callable, Sequence
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import quote

import pytest

from tests._loopback import (
    Request,
    request_record,
    run_installed,
    send_bytes,
    serving,
)

# A canonical standard-base64 token: it contains ``+`` and ``/``, so the
# percent-encoded spelling differs from the literal one, and decoding then
# re-encoding it returns the same text. That lets one test build a body whose
# base64 serialization is exactly the token.
TOKEN = base64.b64encode(b"\xfb\xff\xfe" * 8).decode("ascii")
JIRA_TOKEN = "wrong-product-jira-attachment"
CONFLUENCE_TOKEN = "wrong-product-confluence-attachment"
SENTINEL = "ATTACHMENT-CLI-SENTINEL"
CONTEXT = "/scm/bitbucket"
REPO = "DEMO/widgets"
ATTACHMENT_ID = "12345"
ATTACHMENT_PATH = (
    f"{CONTEXT}/rest/api/1.0/projects/DEMO/repos/widgets/attachments/{ATTACHMENT_ID}"
)
SECRET_MESSAGE = "Error: The response contained the session bearer token.\n"

type Response = tuple[int, bytes, dict[str, str]]


def environment(origin: str, credentials: Path) -> dict[str, str]:
    """Point Bitbucket at the loopback and keep the other products inert."""
    assert not credentials.exists()
    return {
        "ATLAWIRE_BITBUCKET_URL": f"{origin}{CONTEXT}/",
        "ATLAWIRE_BITBUCKET_TOKEN": TOKEN,
        "ATLAWIRE_JIRA_URL": f"{origin}/wrong-jira/",
        "ATLAWIRE_JIRA_TOKEN": JIRA_TOKEN,
        "ATLAWIRE_CONFLUENCE_URL": f"{origin}/wrong-confluence/",
        "ATLAWIRE_CONFLUENCE_TOKEN": CONFLUENCE_TOKEN,
        "BBK_CREDENTIALS": str(credentials),
    }


def decode_base64_json(stdout: str) -> bytes:
    """Decode the fixed ``{"base64": "<standard-base64>"}`` contract."""
    value = json.loads(stdout)
    if not isinstance(value, dict) or set(value) != {"base64"}:
        raise AssertionError('Expected exactly {"base64": "<text>"}.')
    encoded = value["base64"]
    if not isinstance(encoded, str):
        raise AssertionError("Expected the base64 field to be a string.")
    return base64.b64decode(encoded, validate=True)


def run_attachment_against(
    credentials: Path,
    handler: type[BaseHTTPRequestHandler],
    *arguments: str,
    repo: str = REPO,
    attachment_id: str = ATTACHMENT_ID,
) -> subprocess.CompletedProcess[str]:
    """Run the anticipated command against a caller-supplied loopback handler."""
    with serving(handler) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        return run_installed(
            [
                "attachment-get",
                repo,
                attachment_id,
                "--base64",
                *arguments,
                "--base-url",
                f"{origin}{CONTEXT}/",
                "--allow-http-loopback",
                "--token-from-env",
            ],
            environment(origin, credentials),
        )


def run_attachment(
    credentials: Path,
    *arguments: str,
    repo: str = REPO,
    attachment_id: str = ATTACHMENT_ID,
    responses: Sequence[Response] = (),
) -> tuple[
    subprocess.CompletedProcess[str],
    list[Request],
    list[str | None],
    list[str],
]:
    """Run the anticipated command against one synthetic loopback server."""
    seen: list[Request] = []
    accepts: list[str | None] = []
    extra_methods: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            seen.append(request_record(self))
            accepts.append(self.headers.get("Accept"))
            index = len(seen) - 1
            if index >= len(responses):
                send_bytes(
                    self,
                    500,
                    b'{"errors":[{"message":"UNEXPECTED-ATTACHMENT-REQUEST"}]}',
                    content_type="application/json",
                )
                return
            status, body, headers = responses[index]
            if 300 <= status < 400:
                send_bytes(
                    self,
                    status,
                    b"",
                    content_type=None,
                    extra_headers=headers,
                )
                return
            send_bytes(
                self,
                status,
                body,
                content_type=headers.get("Content-Type"),
                extra_headers={
                    name: value
                    for name, value in headers.items()
                    if name != "Content-Type"
                },
            )

        def _refuse_write(self, method: str) -> None:
            extra_methods.append(method)
            send_bytes(self, 405, b"", content_type=None)

        def do_POST(self) -> None:
            self._refuse_write("POST")

        def do_PUT(self) -> None:
            self._refuse_write("PUT")

        def do_DELETE(self) -> None:
            self._refuse_write("DELETE")

        def do_PATCH(self) -> None:
            self._refuse_write("PATCH")

        def do_HEAD(self) -> None:
            extra_methods.append("HEAD")
            self.send_error(405)

        def do_OPTIONS(self) -> None:
            extra_methods.append("OPTIONS")
            self.send_error(405)

    result = run_attachment_against(
        credentials,
        Handler,
        *arguments,
        repo=repo,
        attachment_id=attachment_id,
    )
    return result, seen, accepts, extra_methods


def make_get_handler(
    on_get: Callable[[BaseHTTPRequestHandler], None],
    seen: list[Request],
    accepts: list[str | None],
    extra_methods: list[str],
    *,
    protocol_version: str = "HTTP/1.0",
) -> type[BaseHTTPRequestHandler]:
    """Build a GET-only handler for a deterministic loopback wire shape."""

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            seen.append(request_record(self))
            accepts.append(self.headers.get("Accept"))
            on_get(self)

        def _refuse_write(self, method: str) -> None:
            extra_methods.append(method)
            send_bytes(self, 405, b"", content_type=None)

        def do_POST(self) -> None:
            self._refuse_write("POST")

        def do_PUT(self) -> None:
            self._refuse_write("PUT")

        def do_DELETE(self) -> None:
            self._refuse_write("DELETE")

        def do_PATCH(self) -> None:
            self._refuse_write("PATCH")

        def do_HEAD(self) -> None:
            extra_methods.append("HEAD")
            self.send_error(405)

        def do_OPTIONS(self) -> None:
            extra_methods.append("OPTIONS")
            self.send_error(405)

    Handler.protocol_version = protocol_version
    return Handler


class _GzipWire:
    """Record the compressed body and framing headers a gzip handler serves."""

    def __init__(self) -> None:
        self.bodies: list[bytes] = []
        self.encodings: list[str] = []
        self.lengths: list[str] = []


def make_gzip_handler(
    body: bytes,
    seen: list[Request],
    accepts: list[str | None],
    extra_methods: list[str],
    wire: _GzipWire,
) -> type[BaseHTTPRequestHandler]:
    """Serve one recorded gzip body with complete HTTP framing."""

    def on_get(handler: BaseHTTPRequestHandler) -> None:
        send_bytes(
            handler,
            200,
            body,
            content_type="application/octet-stream",
            content_encoding="gzip",
        )
        wire.bodies.append(body)
        wire.encodings.append("gzip")
        wire.lengths.append(str(len(body)))

    return make_get_handler(on_get, seen, accepts, extra_methods)


def attachment_request() -> Request:
    return ("GET", ATTACHMENT_PATH, {}, f"Bearer {TOKEN}")


def assert_safe_serialization(payload: bytes) -> None:
    """Keep a success fixture from tripping the CLI's final token check."""
    assert TOKEN not in base64.b64encode(payload).decode("ascii")


def assert_no_credential_echo(result: subprocess.CompletedProcess[str]) -> None:
    """No command output may print a configured product credential."""
    for secret in (TOKEN, JIRA_TOKEN, CONFLUENCE_TOKEN):
        assert secret not in result.stdout
        assert secret not in result.stderr


def test_attachment_get_returns_arbitrary_binary_exactly_via_base64_json(
    tmp_path: Path,
) -> None:
    payload = bytes(range(256)) * 4 + b"\x00\xff\r\nhttps://evil.invalid/next"
    assert_safe_serialization(payload)

    result, seen, accepts, extra = run_attachment(
        tmp_path / "missing-credentials.json",
        responses=[(200, payload, {"Content-Type": "application/octet-stream"})],
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert_no_credential_echo(result)
    assert decode_base64_json(result.stdout) == payload
    assert seen == [attachment_request()]
    assert accepts == ["*/*"]
    assert extra == []


def test_attachment_get_accepts_a_zero_byte_body(tmp_path: Path) -> None:
    result, seen, accepts, extra = run_attachment(
        tmp_path / "missing-credentials.json",
        responses=[(200, b"", {})],
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert_no_credential_echo(result)
    assert decode_base64_json(result.stdout) == b""
    assert seen == [attachment_request()]
    assert accepts == ["*/*"]
    assert extra == []


def test_attachment_get_accepts_a_body_exactly_at_the_cap(
    tmp_path: Path,
) -> None:
    payload = b"\x00binary\xff"
    assert_safe_serialization(payload)
    result, seen, accepts, extra = run_attachment(
        tmp_path / "missing-credentials.json",
        "--max-bytes",
        str(len(payload)),
        responses=[(200, payload, {})],
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert_no_credential_echo(result)
    assert decode_base64_json(result.stdout) == payload
    assert seen == [attachment_request()]
    assert accepts == ["*/*"]
    assert extra == []


def test_attachment_get_rejects_a_body_over_the_cap_without_partial_stdout(
    tmp_path: Path,
) -> None:
    payload = b"x" * 1024

    result, seen, accepts, extra = run_attachment(
        tmp_path / "missing-credentials.json",
        "--max-bytes",
        "10",
        responses=[(200, payload, {})],
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "10-byte limit" in result.stderr
    assert payload[:64].decode("ascii") not in result.stderr
    assert seen == [attachment_request()]
    assert accepts == ["*/*"]
    assert extra == []


@pytest.mark.parametrize("value", ["0", "-1"], ids=["zero", "negative"])
def test_attachment_get_rejects_a_non_positive_cap_before_any_request(
    tmp_path: Path, value: str
) -> None:
    result, seen, accepts, extra = run_attachment(
        tmp_path / "missing-credentials.json",
        "--max-bytes",
        value,
        responses=[],
    )

    assert result.returncode != 0
    assert result.stdout == ""
    assert result.stderr != ""
    assert seen == []
    assert accepts == []
    assert extra == []


def test_attachment_get_rejects_partial_content(tmp_path: Path) -> None:
    result, seen, accepts, extra = run_attachment(
        tmp_path / "missing-credentials.json",
        responses=[(206, b"partial", {})],
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "HTTP 206" in result.stderr
    assert seen == [attachment_request()]
    assert accepts == ["*/*"]
    assert extra == []


def test_attachment_get_sanitizes_an_authentication_failure(
    tmp_path: Path,
) -> None:
    body = json.dumps(
        {"errors": [{"message": SENTINEL}], "token": TOKEN, "x": SENTINEL}
    ).encode()

    result, seen, accepts, extra = run_attachment(
        tmp_path / "missing-credentials.json",
        responses=[(401, body, {"Content-Type": "application/json"})],
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "HTTP 401" in result.stderr
    for secret in (TOKEN, JIRA_TOKEN, CONFLUENCE_TOKEN, SENTINEL):
        assert secret not in result.stderr
    assert seen == [attachment_request()]
    assert accepts == ["*/*"]
    assert extra == []


def test_attachment_get_refuses_a_redirect_and_never_contacts_the_target(
    tmp_path: Path,
) -> None:
    honey_seen: list[Request] = []

    class Honeypot(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def _record(self) -> None:
            honey_seen.append(request_record(self))
            send_bytes(self, 200, b"stolen")

        def do_GET(self) -> None:
            self._record()

        def do_POST(self) -> None:
            self._record()

        def do_PUT(self) -> None:
            self._record()

        def do_DELETE(self) -> None:
            self._record()

        def do_PATCH(self) -> None:
            self._record()

        def do_HEAD(self) -> None:
            honey_seen.append(request_record(self))
            self.send_error(405)

        def do_OPTIONS(self) -> None:
            honey_seen.append(request_record(self))
            self.send_error(405)

    with serving(Honeypot) as honey:
        target = f"http://127.0.0.1:{honey.server_port}/stolen"
        result, seen, accepts, extra = run_attachment(
            tmp_path / "missing-credentials.json",
            responses=[(302, b"", {"Location": target})],
        )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "redirect refused" in result.stderr
    assert target not in result.stderr
    assert seen == [attachment_request()]
    assert accepts == ["*/*"]
    assert honey_seen == []
    assert extra == []


@pytest.mark.parametrize(
    "attachment_id",
    [
        "../secret",
        "a/b",
        "a%2Fb",
        "a%5Cb",
        "a\\b",
        "a b",
        "..",
        ".hidden",
        "a?b",
        "a#b",
        "a+b",
        "a:b",
    ],
    ids=[
        "parent",
        "separator",
        "percent-slash",
        "percent-backslash",
        "backslash",
        "space",
        "dot-dot",
        "dot-lead",
        "query",
        "fragment",
        "plus",
        "colon",
    ],
)
def test_attachment_get_rejects_a_malformed_id_before_any_request(
    tmp_path: Path, attachment_id: str
) -> None:
    result, seen, accepts, extra = run_attachment(
        tmp_path / "missing-credentials.json",
        attachment_id=attachment_id,
        responses=[],
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr != ""
    assert attachment_id not in result.stderr
    assert seen == []
    assert accepts == []
    assert extra == []


@pytest.mark.parametrize(
    "repo",
    ["DEMO", "DEMO/a/b", "../widgets", "DEMO/..", "DEMO/%2e%2e"],
    ids=[
        "missing-slug",
        "extra-segment",
        "parent-project",
        "dot-dot-slug",
        "percent-dot-dot",
    ],
)
def test_attachment_get_rejects_a_malformed_repo_before_any_request(
    tmp_path: Path, repo: str
) -> None:
    result, seen, accepts, extra = run_attachment(
        tmp_path / "missing-credentials.json",
        repo=repo,
        responses=[],
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr != ""
    assert repo not in result.stderr
    assert seen == []
    assert accepts == []
    assert extra == []


def _token_spellings() -> list[tuple[str, bytes]]:
    raw = TOKEN.encode("ascii")
    standard = base64.b64encode(raw)
    urlsafe = base64.urlsafe_b64encode(raw)
    bearer = f"Bearer {TOKEN}".encode("ascii")
    return [
        ("literal", raw),
        ("percent", quote(TOKEN, safe="").encode("ascii")),
        ("base64", standard),
        ("base64-unpadded", standard.rstrip(b"=")),
        ("base64-urlsafe", urlsafe),
        ("base64-urlsafe-unpadded", urlsafe.rstrip(b"=")),
        ("base64-bearer", base64.b64encode(bearer)),
    ]


@pytest.mark.parametrize(
    "body",
    [body for _, body in _token_spellings()],
    ids=[label for label, _ in _token_spellings()],
)
def test_attachment_get_rejects_token_spellings_in_the_body(
    tmp_path: Path, body: bytes
) -> None:
    result, seen, accepts, extra = run_attachment(
        tmp_path / "missing-credentials.json",
        responses=[(200, body, {})],
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == SECRET_MESSAGE
    assert TOKEN not in result.stderr
    assert seen == [attachment_request()]
    assert accepts == ["*/*"]
    assert extra == []


def test_attachment_get_returns_a_one_character_near_match_unchanged(
    tmp_path: Path,
) -> None:
    payload = b"-" + TOKEN[1:].encode("ascii") + b"\x00\xff"
    assert_safe_serialization(payload)

    result, seen, accepts, extra = run_attachment(
        tmp_path / "missing-credentials.json",
        responses=[(200, payload, {})],
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert_no_credential_echo(result)
    assert decode_base64_json(result.stdout) == payload
    assert seen == [attachment_request()]
    assert accepts == ["*/*"]
    assert extra == []


def test_attachment_get_rejects_a_body_whose_base64_is_the_token(
    tmp_path: Path,
) -> None:
    # The shared adapter guard inspects the raw body. This body is the decoded
    # token, so its base64 serialization is the token itself; the adapter unit
    # test proves the raw bytes pass, and only the CLI's final-output check can
    # stop it.
    payload = base64.b64decode(TOKEN, validate=True)
    assert base64.b64encode(payload) == TOKEN.encode("ascii")

    result, seen, accepts, extra = run_attachment(
        tmp_path / "missing-credentials.json",
        responses=[(200, payload, {})],
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert TOKEN not in result.stdout
    assert TOKEN not in result.stderr
    assert seen == [attachment_request()]
    assert accepts == ["*/*"]
    assert extra == []


def test_attachment_get_fails_generically_on_a_content_length_shortfall(
    tmp_path: Path,
) -> None:
    seen: list[Request] = []
    accepts: list[str | None] = []
    extra: list[str] = []
    prefix = b"PRIVATE-PREFIX"

    def on_get(handler: BaseHTTPRequestHandler) -> None:
        handler.send_response(200)
        handler.send_header("Content-Type", "application/octet-stream")
        handler.send_header("Content-Length", str(len(prefix) + 5))
        handler.end_headers()
        handler.wfile.write(prefix)
        handler.wfile.flush()
        handler.close_connection = True

    handler = make_get_handler(on_get, seen, accepts, extra)
    result = run_attachment_against(tmp_path / "missing-credentials.json", handler)

    assert result.returncode == 1
    assert result.stdout == ""
    assert "Request failed" in result.stderr
    assert_no_credential_echo(result)
    assert prefix.decode("ascii") not in result.stderr
    assert seen == [attachment_request()]
    assert accepts == ["*/*"]
    assert extra == []


def test_attachment_get_fails_generically_on_incomplete_chunked_framing(
    tmp_path: Path,
) -> None:
    seen: list[Request] = []
    accepts: list[str | None] = []
    extra: list[str] = []
    prefix = b"PRIVATE!"

    def on_get(handler: BaseHTTPRequestHandler) -> None:
        handler.send_response(200)
        handler.send_header("Content-Type", "application/octet-stream")
        handler.send_header("Transfer-Encoding", "chunked")
        handler.end_headers()
        handler.wfile.write(b"8\r\n" + prefix + b"\r\n")
        handler.wfile.flush()
        handler.close_connection = True

    handler = make_get_handler(
        on_get, seen, accepts, extra, protocol_version="HTTP/1.1"
    )
    result = run_attachment_against(tmp_path / "missing-credentials.json", handler)

    assert result.returncode == 1
    assert result.stdout == ""
    assert "Request failed" in result.stderr
    assert_no_credential_echo(result)
    assert prefix.decode("ascii") not in result.stderr
    assert seen == [attachment_request()]
    assert accepts == ["*/*"]
    assert extra == []


def test_attachment_get_accepts_gzip_exactly_at_the_decoded_cap(
    tmp_path: Path,
) -> None:
    limit = 64
    payload = b"x" * limit
    compressed = gzip.compress(payload)
    assert len(compressed) < limit
    assert_safe_serialization(payload)
    seen: list[Request] = []
    accepts: list[str | None] = []
    extra: list[str] = []

    def on_get(handler: BaseHTTPRequestHandler) -> None:
        send_bytes(
            handler,
            200,
            compressed,
            content_type="application/octet-stream",
            content_encoding="gzip",
        )

    handler = make_get_handler(on_get, seen, accepts, extra)
    result = run_attachment_against(
        tmp_path / "missing-credentials.json",
        handler,
        "--max-bytes",
        str(limit),
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert_no_credential_echo(result)
    assert decode_base64_json(result.stdout) == payload
    assert seen == [attachment_request()]
    assert accepts == ["*/*"]
    assert extra == []


def test_attachment_get_rejects_gzip_one_byte_over_the_decoded_cap(
    tmp_path: Path,
) -> None:
    limit = 64
    payload = b"x" * (limit + 1)
    compressed = gzip.compress(payload)
    assert len(compressed) < limit
    seen: list[Request] = []
    accepts: list[str | None] = []
    extra: list[str] = []

    def on_get(handler: BaseHTTPRequestHandler) -> None:
        send_bytes(
            handler,
            200,
            compressed,
            content_type="application/octet-stream",
            content_encoding="gzip",
        )

    handler = make_get_handler(on_get, seen, accepts, extra)
    result = run_attachment_against(
        tmp_path / "missing-credentials.json",
        handler,
        "--max-bytes",
        str(limit),
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "64-byte limit" in result.stderr
    assert_no_credential_echo(result)
    assert payload[:32].decode("ascii") not in result.stderr
    assert seen == [attachment_request()]
    assert accepts == ["*/*"]
    assert extra == []


def test_attachment_get_accepts_a_complete_gzip_member_with_recorded_wire(
    tmp_path: Path,
) -> None:
    payload = b"gzip-member-control-" * 8
    complete = gzip.compress(payload, mtime=0)
    assert complete.startswith(b"\x1f\x8b")
    assert_safe_serialization(payload)
    seen: list[Request] = []
    accepts: list[str | None] = []
    extra: list[str] = []
    wire = _GzipWire()
    handler = make_gzip_handler(complete, seen, accepts, extra, wire)

    result = run_attachment_against(
        tmp_path / "missing-credentials.json",
        handler,
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert_no_credential_echo(result)
    assert decode_base64_json(result.stdout) == payload
    assert seen == [attachment_request()]
    assert accepts == ["*/*"]
    assert extra == []
    assert wire.bodies == [complete]
    assert wire.encodings == ["gzip"]
    assert wire.lengths == [str(len(complete))]


def test_attachment_get_still_decodes_a_deflate_body_exactly(
    tmp_path: Path,
) -> None:
    payload = b"deflate-member-control-" * 8
    compressed = zlib.compress(payload)
    assert_safe_serialization(payload)
    seen: list[Request] = []
    accepts: list[str | None] = []
    extra: list[str] = []

    def on_get(handler: BaseHTTPRequestHandler) -> None:
        send_bytes(
            handler,
            200,
            compressed,
            content_type="application/octet-stream",
            content_encoding="deflate",
        )

    handler = make_get_handler(on_get, seen, accepts, extra)
    result = run_attachment_against(
        tmp_path / "missing-credentials.json",
        handler,
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert_no_credential_echo(result)
    assert decode_base64_json(result.stdout) == payload
    assert seen == [attachment_request()]
    assert accepts == ["*/*"]
    assert extra == []


def test_attachment_get_rejects_a_truncated_gzip_member(
    tmp_path: Path,
) -> None:
    # Hypothesis until the batched suite executes: urllib3's GzipDecoder.flush
    # only calls zlib.decompressobj.flush, which may not validate the missing
    # gzip trailer. The contract still requires an incomplete member to fail;
    # this test may expose a baseline dependency defect, not an adapter change.
    payload = b"gzip-member-control-" * 8
    complete = gzip.compress(payload, mtime=0)
    truncated = complete[:-8]
    assert truncated.startswith(b"\x1f\x8b")
    assert len(truncated) < len(complete)
    assert complete.startswith(truncated)
    seen: list[Request] = []
    accepts: list[str | None] = []
    extra: list[str] = []
    wire = _GzipWire()
    handler = make_gzip_handler(truncated, seen, accepts, extra, wire)

    result = run_attachment_against(
        tmp_path / "missing-credentials.json",
        handler,
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "Request failed" in result.stderr
    assert_no_credential_echo(result)
    assert payload[:32].decode("ascii") not in result.stderr
    assert seen == [attachment_request()]
    assert accepts == ["*/*"]
    assert extra == []
    assert wire.bodies == [truncated]
    assert wire.encodings == ["gzip"]
    assert wire.lengths == [str(len(truncated))]
    assert wire.bodies[0] == complete[: len(truncated)]
    assert complete.startswith(wire.bodies[0])


def _run_attachment_out(
    credentials: Path,
    destination: Path,
    responses: Sequence[Response],
    *,
    before_send: Callable[[], None] | None = None,
) -> tuple[subprocess.CompletedProcess[str], list[Request]]:
    """Run attachment-get with --out instead of the base64 contract.

    ``before_send`` runs inside the request handler after the CLI has opened
    its destination check but before the body is delivered. It lets a test
    create a competing file at the publication target deterministically.
    """
    seen: list[Request] = []

    def on_get(handler: BaseHTTPRequestHandler) -> None:
        if before_send is not None:
            before_send()
        status, body, headers = responses[0]
        send_bytes(handler, status, body, **headers)

    with serving(make_get_handler(on_get, seen, [], [])) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        result = run_installed(
            [
                "attachment-get",
                REPO,
                ATTACHMENT_ID,
                "--out",
                str(destination),
                "--base-url",
                f"{origin}{CONTEXT}/",
                "--token-from-env",
                "--allow-http-loopback",
            ],
            environment(origin, credentials),
        )
    return result, seen


def test_attachment_out_writes_exact_bytes_and_a_receipt(tmp_path: Path) -> None:
    payload = bytes(range(256)) + b"tail"
    destination = tmp_path / "attachment.bin"

    result, seen = _run_attachment_out(
        tmp_path / "missing-credentials.json",
        destination,
        [(200, payload, {"content_type": "application/octet-stream"})],
    )

    assert result.returncode == 0, result.stdout
    assert destination.read_bytes() == payload
    receipt = json.loads(result.stdout)
    assert receipt["path"] == str(destination)
    assert receipt["bytes"] == len(payload)
    assert receipt["sha256"] == __import__("hashlib").sha256(payload).hexdigest()
    assert seen == [attachment_request()]
    assert destination.with_name(destination.name + ".part").exists() is False


def test_attachment_out_does_not_replace_a_file_created_during_publication(
    tmp_path: Path,
) -> None:
    # The destination is absent when the CLI checks it. The loopback handler
    # creates the competing file while the body is being delivered, so the
    # publish step always sees a path it did not check. The original bytes
    # must survive and no receipt or temporary file may be published.
    destination = tmp_path / "attachment.bin"
    result, seen = _run_attachment_out(
        tmp_path / "missing-credentials.json",
        destination,
        [(200, b"new attachment", {"content_type": "application/octet-stream"})],
        before_send=lambda: destination.write_bytes(b"competing"),
    )

    assert result.returncode == 1
    assert "already exists" in result.stderr
    assert result.stdout == ""
    assert destination.read_bytes() == b"competing"
    assert list(tmp_path.glob("*.part")) == []
    assert seen == [attachment_request()]


def test_attachment_out_refuses_an_existing_file(tmp_path: Path) -> None:
    destination = tmp_path / "attachment.bin"
    destination.write_bytes(b"keep")

    result, seen = _run_attachment_out(
        tmp_path / "missing-credentials.json",
        destination,
        [(200, b"new", {"content_type": "application/octet-stream"})],
    )

    assert result.returncode == 1
    assert destination.read_bytes() == b"keep"

    result, _ = _run_attachment_out(
        tmp_path / "missing-credentials.json",
        tmp_path / "unused.bin",
        [(200, b"new", {"content_type": "application/octet-stream"})],
    )
    assert result.returncode == 0
