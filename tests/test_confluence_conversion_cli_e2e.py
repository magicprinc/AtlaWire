"""Installed-CLI loopback tests for the read-only ``convert-body`` command.

Every response and credential is synthetic and served by a loopback HTTP
server. No test contacts a real Confluence instance, reads a real credential
store, or depends on a live route. ``convert-body`` reads exact UTF-8 text from
stdin and prints one raw JSON result object.

The documented 6.6 conversion pairs are storage to view, export_view,
styled_view, or editor; and editor to storage. The route, target-version
support, and server-side macro or plugin effects remain unverified.
"""

import base64
import json
import os
import shutil
import subprocess
from contextlib import ExitStack
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import quote

import pytest
from click.testing import CliRunner

from atlawire.cli import cli
from atlawire.http import AtlaWireError
from tests._loopback import (
    Request,
    confluence_environment,
    request_record,
    send_bytes,
    serving,
)

TOKEN = "fixture-conversion-cli-token"
CONTEXT = "/wiki"
CONVERT_PREFIX = f"{CONTEXT}/rest/api/contentbody/convert"
SENTINEL = "CONVERSION-CLI-SENTINEL"
SECRET_MESSAGE = "The response contained the session bearer token."
REQUEST_ECHO = "The request would include the session bearer token."
MISSING_BBK_CREDENTIALS = str(
    Path(__file__).with_name("bbk-credentials-missing-for-conversion-cli.json")
)

PAIRS: list[tuple[str, str]] = [
    ("storage", "view"),
    ("storage", "export_view"),
    ("storage", "styled_view"),
    ("storage", "editor"),
    ("editor", "storage"),
]

EXACT_VALUE = (
    "  Привет, мир! 😀\n"
    "second line\twith tab\r\n"
    "\x00 leading and trailing spaces  \n"
)

type Response = tuple[int, bytes, dict[str, str]]


@dataclass
class Run:
    """One installed invocation plus the exact loopback observations."""

    result: subprocess.CompletedProcess[bytes]
    seen: list[Request]
    bodies: list[bytes]
    content_types: list[str | None]
    extra_methods: list[str]
    honey: list[Request]
    redirect_target: str | None


def json_body(payload: object) -> bytes:
    return json.dumps(payload).encode("utf-8")


def utf8_json_body(payload: object) -> bytes:
    """Send actual UTF-8 instead of ASCII-escaped JSON."""
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def run_installed_with_stdin(
    args: list[str], environment: dict[str, str], stdin: bytes
) -> subprocess.CompletedProcess[bytes]:
    """Run the installed console script with exact stdin bytes."""
    script = shutil.which("atlawire")
    if script is None:
        raise AssertionError("Install AtlaWire before running its CLI E2E suite.")
    return subprocess.run(
        [script, *args],
        input=stdin,
        env={**os.environ, **environment},
        capture_output=True,
        timeout=15,
        check=False,
    )


def run_conversion(
    stdin: bytes,
    *,
    representation: str = "storage",
    to: str = "view",
    expand: str | None = None,
    response: Response = (
        200,
        b'{"value":"<p>rendered</p>","representation":"view"}',
        {"Content-Type": "application/json"},
    ),
    redirect: bool = False,
    token: str = TOKEN,
) -> Run:
    """Run one command against a synthetic loopback POST handler."""
    seen: list[Request] = []
    bodies: list[bytes] = []
    content_types: list[str | None] = []
    extra_methods: list[str] = []
    honey: list[Request] = []
    status, body, headers = response
    redirect_target: str | None = None

    class Honeypot(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def log_message(self, format: str, *args: object) -> None:
            pass

        def _record(self) -> None:
            honey.append(request_record(self))
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
            honey.append(request_record(self))
            self.send_error(405)

        def do_OPTIONS(self) -> None:
            honey.append(request_record(self))
            self.send_error(405)

    with ExitStack() as stack:
        if redirect:
            honey_server = stack.enter_context(serving(Honeypot))
            redirect_target = (
                f"http://127.0.0.1:{honey_server.server_port}/stolen"
            )

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.0"

            def log_message(self, format: str, *args: object) -> None:
                pass

            def do_POST(self) -> None:
                seen.append(request_record(self))
                content_types.append(self.headers.get("Content-Type"))
                length = int(self.headers.get("Content-Length") or "0")
                bodies.append(self.rfile.read(length))
                if redirect_target is not None:
                    send_bytes(
                        self,
                        status,
                        b"",
                        content_type=None,
                        extra_headers={"Location": redirect_target},
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

            def _refuse(self, method: str) -> None:
                extra_methods.append(method)
                self.send_error(405)

            def do_GET(self) -> None:
                self._refuse("GET")

            def do_PUT(self) -> None:
                self._refuse("PUT")

            def do_DELETE(self) -> None:
                self._refuse("DELETE")

            def do_PATCH(self) -> None:
                self._refuse("PATCH")

            def do_HEAD(self) -> None:
                self._refuse("HEAD")

            def do_OPTIONS(self) -> None:
                self._refuse("OPTIONS")

        server = stack.enter_context(serving(Handler))
        origin = f"http://127.0.0.1:{server.server_port}"
        environment = confluence_environment(origin, context=CONTEXT, token=token)
        environment["BBK_CREDENTIALS"] = MISSING_BBK_CREDENTIALS
        arguments = [
            "convert-body",
            "--from-representation",
            representation,
            "--to",
            to,
            "--base-url",
            f"{origin}{CONTEXT}/",
            "--allow-http-loopback",
            "--token-from-env",
        ]
        if expand is not None:
            arguments.extend(["--expand", expand])
        result = run_installed_with_stdin(arguments, environment, stdin)

    return Run(
        result,
        seen,
        bodies,
        content_types,
        extra_methods,
        honey,
        redirect_target,
    )


def stderr_text(run: Run) -> str:
    return run.result.stderr.decode("utf-8", "replace")


def assert_failed(run: Run, message: str, *, token: str = TOKEN) -> None:
    """A failed conversion exits 1 with no stdout and generic diagnostics."""
    assert run.result.returncode == 1
    assert run.result.stdout == b""
    text = stderr_text(run)
    assert message in text
    assert token not in text
    assert SENTINEL not in text
    assert "Traceback" not in text


def assert_success_object(run: Run, payload: object) -> None:
    assert run.result.returncode == 0, run.result.stderr
    assert run.result.stderr == b""
    assert json.loads(run.result.stdout) == payload


def expected_request(
    target: str, expand: str | None = None, *, token: str = TOKEN
) -> list[Request]:
    query = {} if expand is None else {"expand": [expand]}
    return [("POST", f"{CONVERT_PREFIX}/{target}", query, f"Bearer {token}")]


def test_the_bbk_credentials_override_is_a_missing_synthetic_path() -> None:
    assert "missing-for-conversion-cli" in MISSING_BBK_CREDENTIALS
    assert not Path(MISSING_BBK_CREDENTIALS).exists()


@pytest.mark.parametrize(
    ("representation", "to"),
    PAIRS,
    ids=[f"{source}-to-{target}" for source, target in PAIRS],
)
def test_installed_conversion_of_all_documented_pairs_keeps_exact_stdin(
    representation: str, to: str
) -> None:
    payload: dict[str, object] = {
        "value": "<p>rendered</p>",
        # The 6.6 example returns ``storage`` for a view conversion, so the
        # response representation is preserved rather than checked against
        # the requested target.
        "representation": "storage",
        "_links": {"next": "https://elsewhere.example.invalid/next"},
        "_expandable": {"content": "/rest/api/content/1"},
        "unknown": [None, True, 2.5],
    }
    run = run_conversion(
        EXACT_VALUE.encode("utf-8"),
        representation=representation,
        to=to,
        response=(200, json_body(payload), {"Content-Type": "application/json"}),
    )

    assert_success_object(run, payload)
    assert run.seen == expected_request(to)
    assert run.content_types == ["application/json"]
    assert json.loads(run.bodies[0]) == {
        "value": EXACT_VALUE,
        "representation": representation,
    }
    assert run.extra_methods == []
    assert run.honey == []


def test_installed_conversion_sends_an_empty_stdin_and_empty_expand() -> None:
    payload = {"value": "", "representation": "view"}
    run = run_conversion(
        b"",
        expand="",
        response=(200, json_body(payload), {"Content-Type": "application/json"}),
    )

    assert_success_object(run, payload)
    assert run.seen == expected_request("view", "")
    assert json.loads(run.bodies[0]) == {"value": "", "representation": "storage"}


def test_installed_conversion_percent_encodes_expand_as_the_only_query_key() -> None:
    expand = "body.view+body.storage & x=1? # Привет/100%"
    payload = {"value": "<p>storage</p>", "representation": "storage"}
    run = run_conversion(
        EXACT_VALUE.encode("utf-8"),
        representation="editor",
        to="storage",
        expand=expand,
        response=(200, json_body(payload), {"Content-Type": "application/json"}),
    )

    assert_success_object(run, payload)
    assert run.seen == expected_request("storage", expand)
    assert set(run.seen[0][2]) == {"expand"}
    assert json.loads(run.bodies[0]) == {
        "value": EXACT_VALUE,
        "representation": "editor",
    }


@pytest.mark.parametrize(
    ("representation", "to"),
    [
        ("storage", "storage"),
        ("editor", "view"),
        ("editor", "editor"),
        ("view", "storage"),
        ("Storage", "view"),
        ("storage", "VIEW"),
    ],
    ids=[
        "storage-to-storage",
        "editor-to-view",
        "editor-to-editor",
        "view-source",
        "case-sensitive-source",
        "case-sensitive-target",
    ],
)
def test_installed_conversion_rejects_an_invalid_pair_without_a_request(
    representation: str, to: str
) -> None:
    run = run_conversion(
        b"<p>fixture</p>",
        representation=representation,
        to=to,
    )

    assert_failed(run, "supported content body conversion")
    assert run.seen == []
    assert run.bodies == []
    assert run.content_types == []
    assert run.extra_methods == []
    assert run.honey == []


def test_installed_conversion_maps_401_without_leaking_the_body() -> None:
    run = run_conversion(
        b"<p>fixture</p>",
        response=(
            401,
            json_body({"message": SENTINEL, "token": TOKEN}),
            {"Content-Type": "application/json"},
        ),
    )

    assert_failed(run, "HTTP 401")
    assert run.seen == expected_request("view")


def test_installed_conversion_refuses_a_redirect_without_contacting_it() -> None:
    run = run_conversion(
        b"<p>fixture</p>",
        response=(302, b"", {}),
        redirect=True,
    )

    assert_failed(run, "redirect refused")
    assert run.redirect_target is not None
    assert run.redirect_target not in stderr_text(run)
    assert run.seen == expected_request("view")
    assert run.honey == []


@pytest.mark.parametrize(
    ("body", "message"),
    [
        pytest.param(b"{", "valid JSON", id="truncated"),
        pytest.param(
            b'{"value":"\xff","representation":"view"}',
            "UTF-8 JSON",
            id="invalid-utf8-response",
        ),
        pytest.param(b"[]", "JSON object", id="array"),
        pytest.param(
            b'{"value":1,"representation":"view"}',
            "value and representation strings",
            id="int-value",
        ),
        pytest.param(
            b'{"value":"x"}',
            "value and representation strings",
            id="missing-representation",
        ),
        pytest.param(
            b'{"value":"x","representation":null}',
            "value and representation strings",
            id="null-representation",
        ),
    ],
)
def test_installed_conversion_maps_a_malformed_response_without_output(
    body: bytes, message: str
) -> None:
    run = run_conversion(
        b"<p>fixture</p>",
        response=(200, body, {"Content-Type": "application/json"}),
    )

    assert_failed(run, message)
    assert run.seen == expected_request("view")


def _input_echoes() -> list[tuple[str, bytes, str | None]]:
    raw = TOKEN.encode("ascii")
    standard = base64.b64encode(raw)
    return [
        ("value-literal", raw, None),
        ("value-percent", quote(TOKEN, safe="").encode("ascii"), None),
        ("value-base64", standard, None),
        ("expand-literal", b"<p>fixture</p>", TOKEN),
        ("expand-percent", b"<p>fixture</p>", quote(TOKEN, safe="")),
    ]


@pytest.mark.parametrize(
    ("stdin", "expand"),
    [(stdin, expand) for _, stdin, expand in _input_echoes()],
    ids=[label for label, _, _ in _input_echoes()],
)
def test_installed_conversion_refuses_a_request_echo_without_a_request(
    stdin: bytes, expand: str | None
) -> None:
    run = run_conversion(stdin, expand=expand)

    assert_failed(run, REQUEST_ECHO)
    assert run.seen == []
    assert run.bodies == []
    assert run.extra_methods == []
    assert run.honey == []


def _output_echoes() -> list[tuple[str, dict[str, object]]]:
    standard = base64.b64encode(TOKEN.encode("ascii")).decode("ascii")
    return [
        ("value-literal", {"value": TOKEN, "representation": "view"}),
        (
            "unknown-literal",
            {"value": "x", "representation": "view", "extra": TOKEN},
        ),
        (
            "unknown-base64",
            {"value": "x", "representation": "view", "extra": standard},
        ),
        (
            "unknown-percent",
            {
                "value": "x",
                "representation": "view",
                "extra": quote(TOKEN, safe=""),
            },
        ),
        ("key-literal", {"value": "x", "representation": "view", TOKEN: "key"}),
    ]


@pytest.mark.parametrize(
    "payload",
    [payload for _, payload in _output_echoes()],
    ids=[label for label, _ in _output_echoes()],
)
def test_installed_conversion_rejects_an_output_token_echo(
    payload: dict[str, object],
) -> None:
    run = run_conversion(
        b"<p>fixture</p>",
        response=(200, json_body(payload), {"Content-Type": "application/json"}),
    )

    assert_failed(run, SECRET_MESSAGE)
    assert run.seen == expected_request("view")


def test_installed_conversion_prints_a_serialized_u1234_escape_normally() -> None:
    # The adapter accepts this response because the decoded value contains the
    # character U+1234, not the ASCII token. Default CLI json.dumps spells it as
    # the literal "\u1234", which is ordinary serialization and is printed.
    token = "u1234"
    decoded_value = "<p>\u1234</p>"
    payload = {"value": decoded_value, "representation": "view"}
    raw = utf8_json_body(payload)
    assert token.encode("ascii") not in raw
    assert token not in decoded_value

    run = run_conversion(
        b"<p>fixture</p>",
        token=token,
        response=(200, raw, {"Content-Type": "application/json"}),
    )

    assert_success_object(run, payload)
    assert b"\\u1234" in run.result.stdout
    assert run.seen == expected_request("view", token=token)


def test_installed_conversion_keeps_a_u1235_escape_as_a_success_control() -> None:
    # One adjacent code point does not produce the token in the escaped JSON.
    token = "u1234"
    decoded_value = "<p>\u1235</p>"
    payload = {"value": decoded_value, "representation": "view"}
    raw = utf8_json_body(payload)
    assert token.encode("ascii") not in raw

    run = run_conversion(
        b"<p>fixture</p>",
        token=token,
        response=(200, raw, {"Content-Type": "application/json"}),
    )

    assert_success_object(run, payload)
    assert b"\\u1235" in run.result.stdout
    assert token.encode("ascii") not in run.result.stdout
    assert run.seen == expected_request("view", token=token)


@pytest.mark.parametrize(
    "stdin",
    [b"\xff", b"\xc3", b"valid \x80 bytes", b"\xed\xa0\x80"],
    ids=["invalid-lead", "truncated", "invalid-continuation", "surrogate"],
)
def test_installed_conversion_rejects_invalid_utf8_stdin_without_a_request(
    stdin: bytes,
) -> None:
    run = run_conversion(stdin)

    assert_failed(run, "UTF-8 text on standard input")
    assert run.seen == []
    assert run.bodies == []
    assert run.content_types == []
    assert run.extra_methods == []
    assert run.honey == []


def test_installed_conversion_keeps_a_diagnostic_that_contains_token_json() -> None:
    # The adapter reports a malformed-response message containing the ordinary
    # word "JSON" (also the accepted bearer token here). It is printed normally.
    run = run_conversion(
        b"<p>fixture</p>",
        token="JSON",
        response=(200, b"{", {"Content-Type": "application/json"}),
    )

    assert run.result.returncode == 1
    assert run.result.stdout == b""
    assert stderr_text(run).strip() == "Error: Expected a valid JSON response."
    assert run.seen == expected_request("view", token="JSON")


def test_an_empty_adapter_message_is_rendered_through_click(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The removed helper turned an empty adapter message into a silent exit.
    # The command now always renders an adapter failure as an ordinary Click
    # error, so an empty message is not special-cased.
    monkeypatch.setenv("ATLAWIRE_CONFLUENCE_TOKEN", TOKEN)

    def failing(*args: object, **kwargs: object) -> object:
        raise AtlaWireError("")

    monkeypatch.setattr("atlawire.cli.convert_content_body", failing)
    result = CliRunner().invoke(
        cli,
        [
            "convert-body",
            "--from-representation",
            "storage",
            "--to",
            "view",
            "--base-url",
            f"{CONTEXT}/",
            "--token-from-env",
        ],
        input="<p>fixture</p>",
    )

    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.stderr.strip() == "Error:"


def test_installed_conversion_keeps_the_error_prefix_when_the_token_is_error() -> None:
    # Click's fixed "Error: " prefix is ordinary CLI text; token "Error" must
    # not hide the diagnostic or the prefix.
    run = run_conversion(
        b"<p>fixture</p>",
        token="Error",
        response=(401, b"", {"Content-Type": "application/json"}),
    )

    assert run.result.returncode == 1
    assert run.result.stdout == b""
    assert stderr_text(run).strip() == "Error: HTTP 401: authentication rejected."
    assert run.seen == expected_request("view", token="Error")


def test_installed_conversion_keeps_invalid_utf8_diagnostic_for_token_error() -> None:
    # Invalid UTF-8 is diagnosed after token resolution; token "Error" must not
    # suppress the ordinary message.
    run = run_conversion(b"\xff", token="Error")

    assert run.result.returncode == 1
    assert run.result.stdout == b""
    assert (
        stderr_text(run).strip()
        == "Error: Expected UTF-8 text on standard input."
    )
    assert run.seen == []


def test_installed_conversion_keeps_a_useful_diagnostic_for_a_safe_token() -> None:
    run = run_conversion(
        b"<p>fixture</p>",
        response=(200, b"{", {"Content-Type": "application/json"}),
    )

    assert run.result.returncode == 1
    assert run.result.stdout == b""
    text = stderr_text(run)
    assert text.strip() == "Error: Expected a valid JSON response."
    assert TOKEN not in text
    assert run.seen == expected_request("view")
