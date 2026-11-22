"""Installed-CLI loopback proof that numeric bearer-token echoes never print.

The shared legacy transport must reject a token that appears as a JSON number
in the original wire text or in Python's normalized float rendering. Every
handler here is a synthetic loopback server and every credential is fake.
"""

import json
import os
import shutil
import subprocess
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from tests._loopback import (
    Request,
    request_record,
    send_bytes,
    send_json,
    serving,
)

TOKEN = "987654321"
FLOAT_TOKEN = "1000000000"
U1234_TOKEN = "u1234"
MESSAGE = "The response contained the session bearer token."
JIRA_CONTEXT = "/jira"
MYSELF_PATH = f"{JIRA_CONTEXT}/rest/api/2/myself"
WIKI_CONTEXT = "/wiki"
CONVERT_PATH = f"{WIKI_CONTEXT}/rest/api/contentbody/convert/view"
STDIN = b"<p>safe input</p>"


def _environment(missing_credentials: Path, values: dict[str, str]) -> dict[str, str]:
    """Use only synthetic product pairs and an unreadable saved-file path."""
    env = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith("ATLAWIRE_") and name != "BBK_CREDENTIALS"
    }
    env.update(values)
    env["BBK_CREDENTIALS"] = str(missing_credentials)
    assert not missing_credentials.exists()
    return env


def _run(
    arguments: list[str], environment: dict[str, str], stdin: bytes = b""
) -> subprocess.CompletedProcess[bytes]:
    """Run the installed console script with exact stdin bytes."""
    script = shutil.which("atlawire")
    if script is None:
        raise AssertionError("Install AtlaWire before running its CLI E2E suite.")
    return subprocess.run(
        [script, *arguments],
        input=stdin,
        env=environment,
        capture_output=True,
        timeout=15,
        check=False,
    )


def _assert_rejected(
    result: subprocess.CompletedProcess[bytes],
    seen: list[Request],
    expected: Request,
    *,
    token: str,
) -> None:
    assert result.returncode == 1
    assert result.stdout == b""
    # Click writes the platform line ending; the contract is the message.
    assert result.stderr.replace(b"\r\n", b"\n") == f"Error: {MESSAGE}\n".encode()
    assert token.encode("ascii") not in result.stderr
    assert seen == [expected]


def test_installed_get_rejects_the_token_as_an_unknown_integer(
    tmp_path: Path,
) -> None:
    seen: list[Request] = []

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            seen.append(request_record(self))
            send_json(
                self,
                200,
                {"name": "ada", "displayName": "Ada", "unknownCount": 987654321},
            )

    with serving(Handler) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        result = _run(
            ["jira-me", "--allow-http-loopback", "--token-from-env"],
            _environment(
                tmp_path / "missing-credentials.json",
                {
                    "ATLAWIRE_JIRA_URL": f"{origin}{JIRA_CONTEXT}/",
                    "ATLAWIRE_JIRA_TOKEN": TOKEN,
                },
            ),
        )

    _assert_rejected(
        result,
        seen,
        ("GET", MYSELF_PATH, {}, f"Bearer {TOKEN}"),
        token=TOKEN,
    )


def test_installed_get_rejects_the_normalized_float_spelling(
    tmp_path: Path,
) -> None:
    # The wire says 1e9, which does not contain the decimal token; only the
    # decoded float's normalized spelling does.
    seen: list[Request] = []
    body = b'{"name":"ada","displayName":"Ada","unknownCount":1e9}'

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            seen.append(request_record(self))
            send_bytes(self, 200, body, content_type="application/json")

    with serving(Handler) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        result = _run(
            ["jira-me", "--allow-http-loopback", "--token-from-env"],
            _environment(
                tmp_path / "missing-credentials.json",
                {
                    "ATLAWIRE_JIRA_URL": f"{origin}{JIRA_CONTEXT}/",
                    "ATLAWIRE_JIRA_TOKEN": FLOAT_TOKEN,
                },
            ),
        )

    _assert_rejected(
        result,
        seen,
        ("GET", MYSELF_PATH, {}, f"Bearer {FLOAT_TOKEN}"),
        token=FLOAT_TOKEN,
    )
