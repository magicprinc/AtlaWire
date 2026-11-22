"""Installed-CLI loopback proof that an echoed bearer token never reaches output.

Each handler answers a normal HTTP 200 with the synthetic token embedded in its
body. The CLI must fail closed with a fixed diagnostic, so the credential cannot
appear on stdout or stderr. No test contacts a real Atlassian instance, reads
saved credentials, or uses a real secret.
"""

import base64
import json
import os
import subprocess
from http.server import BaseHTTPRequestHandler
from pathlib import Path

import pytest

from tests._loopback import (
    Request,
    request_record,
    run_installed,
    send_bytes,
    send_json,
    serving,
)

# The standard and URL-safe base64 forms differ for this synthetic token and
# for its complete Bearer header.
TOKEN = "Pg~V~neQ"
MESSAGE = "The response contained the session bearer token."
JIRA_CONTEXT = "/jira"
MYSELF_PATH = f"{JIRA_CONTEXT}/rest/api/2/myself"
BITBUCKET_CONTEXT = "/bitbucket"
FILE_PATH = (
    f"{BITBUCKET_CONTEXT}/rest/api/1.0/projects/DEMO/repos/widgets/raw/notes.txt"
)
SEARCH_PATH = f"{BITBUCKET_CONTEXT}/rest/search/latest/search"


def _b64(value: str, *, urlsafe: bool = False, pad: bool = True) -> str:
    raw = value.encode("utf-8")
    encoder = base64.urlsafe_b64encode if urlsafe else base64.b64encode
    encoded = encoder(raw).decode("ascii")
    return encoded if pad else encoded.rstrip("=")


TOKEN_B64 = _b64(TOKEN)
TOKEN_B64_URL_UNPADDED = _b64(TOKEN, urlsafe=True, pad=False)
HEADER_B64 = _b64(f"Bearer {TOKEN}")


def environment(origin: str, missing_credentials: Path) -> dict[str, str]:
    """Use only synthetic environment pairs and an unreadable saved-file path."""
    env = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith("ATLAWIRE_") and name != "BBK_CREDENTIALS"
    }
    env.update(
        {
            "ATLAWIRE_JIRA_URL": f"{origin}{JIRA_CONTEXT}/",
            "ATLAWIRE_JIRA_TOKEN": TOKEN,
            "ATLAWIRE_BITBUCKET_URL": f"{origin}{BITBUCKET_CONTEXT}/",
            "ATLAWIRE_BITBUCKET_TOKEN": TOKEN,
            "ATLAWIRE_CONFLUENCE_URL": f"{origin}/wrong-confluence/",
            "ATLAWIRE_CONFLUENCE_TOKEN": "wrong-product-fixture",
            "BBK_CREDENTIALS": str(missing_credentials),
        }
    )
    assert not missing_credentials.exists()
    return env


def _assert_rejected(
    result: subprocess.CompletedProcess[str], seen: list[Request], expected: Request
) -> None:
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == f"Error: {MESSAGE}\n"
    assert TOKEN not in result.stderr
    assert seen == [expected]


def _search_body(text: str) -> dict[str, object]:
    """A structurally valid Bitbucket search page with one highlighted row."""
    return {
        "code": {
            "values": [
                {
                    "repository": {"project": {"key": "DEMO"}, "slug": "widgets"},
                    "file": "src/a.py",
                    "hitCount": 1,
                    "hitContexts": [[{"line": 1, "text": text}]],
                }
            ],
            "isLastPage": True,
        }
    }


def _run_search(
    body: dict[str, object], tmp_path: Path, *, as_json: bool
) -> tuple[subprocess.CompletedProcess[str], list[Request]]:
    seen: list[Request] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_POST(self) -> None:
            seen.append(request_record(self))
            length = int(self.headers.get("Content-Length", "0"))
            self.rfile.read(length)
            send_json(self, 200, body)

    arguments = ["search", "Widget"]
    if as_json:
        arguments.append("--json")
    arguments.extend(["--allow-http-loopback", "--token-from-env"])
    with serving(Handler) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        result = run_installed(
            arguments,
            environment(origin, tmp_path / "missing-credentials.json"),
        )
    return result, seen


def test_installed_cli_rejects_a_json_response_echoing_the_token(
    tmp_path: Path,
) -> None:
    seen: list[Request] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            seen.append(request_record(self))
            send_json(
                self,
                200,
                {"name": "ada", "displayName": TOKEN},
            )

    with serving(Handler) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        result = run_installed(
            ["jira-me", "--allow-http-loopback", "--token-from-env"],
            environment(origin, tmp_path / "missing-credentials.json"),
        )

    _assert_rejected(
        result,
        seen,
        ("GET", MYSELF_PATH, {}, f"Bearer {TOKEN}"),
    )


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(
            {"name": "ada", "displayName": TOKEN_B64},
            id="base64",
        ),
        pytest.param(
            {"name": "ada", "displayName": TOKEN_B64_URL_UNPADDED},
            id="base64-urlsafe-unpadded",
        ),
        pytest.param(
            {"name": "ada", "displayName": HEADER_B64},
            id="base64-header",
        ),
    ],
)
def test_installed_cli_rejects_base64_echoes(
    body: dict[str, object], tmp_path: Path
) -> None:
    seen: list[Request] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            seen.append(request_record(self))
            send_json(self, 200, body)

    with serving(Handler) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        result = run_installed(
            ["jira-me", "--allow-http-loopback", "--token-from-env"],
            environment(origin, tmp_path / "missing-credentials.json"),
        )

    _assert_rejected(
        result,
        seen,
        ("GET", MYSELF_PATH, {}, f"Bearer {TOKEN}"),
    )


def test_installed_cli_rejects_a_text_response_echoing_the_token(
    tmp_path: Path,
) -> None:
    seen: list[Request] = []
    body = f"line one\n{TOKEN}\nline three\n".encode()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            seen.append(request_record(self))
            send_bytes(self, 200, body, content_type="text/plain; charset=utf-8")

    with serving(Handler) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        result = run_installed(
            [
                "file",
                "DEMO/widgets",
                "notes.txt",
                "--base-url",
                f"{origin}{BITBUCKET_CONTEXT}/",
                "--allow-http-loopback",
                "--token-from-env",
            ],
            environment(origin, tmp_path / "missing-credentials.json"),
        )

    _assert_rejected(
        result,
        seen,
        ("GET", FILE_PATH, {"at": ["master"]}, f"Bearer {TOKEN}"),
    )


def test_installed_cli_rejects_a_read_only_post_response_echoing_the_token(
    tmp_path: Path,
) -> None:
    result, seen = _run_search(_search_body(TOKEN), tmp_path, as_json=False)

    _assert_rejected(
        result,
        seen,
        ("POST", SEARCH_PATH, {}, f"Bearer {TOKEN}"),
    )


def test_installed_cli_rejects_split_highlight_text_in_json_search(
    tmp_path: Path,
) -> None:
    split = TOKEN.replace("V", "<em>V</em>", 1)
    assert TOKEN not in split
    result, seen = _run_search(_search_body(split), tmp_path, as_json=True)

    _assert_rejected(
        result,
        seen,
        ("POST", SEARCH_PATH, {}, f"Bearer {TOKEN}"),
    )


def test_installed_cli_rejects_entity_encoded_token_in_summary_search(
    tmp_path: Path,
) -> None:
    encoded = TOKEN.replace("~", "&#x7e;", 1)
    assert TOKEN not in encoded
    result, seen = _run_search(_search_body(encoded), tmp_path, as_json=False)

    _assert_rejected(
        result,
        seen,
        ("POST", SEARCH_PATH, {}, f"Bearer {TOKEN}"),
    )


def test_installed_cli_still_prints_a_normal_identity(tmp_path: Path) -> None:
    seen: list[Request] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            seen.append(request_record(self))
            send_json(
                self,
                200,
                {"name": "ada", "displayName": "Ada aGVsbG8= b3RoZXI="},
            )

    with serving(Handler) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        result = run_installed(
            ["jira-me", "--allow-http-loopback", "--token-from-env"],
            environment(origin, tmp_path / "missing-credentials.json"),
        )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == {
        "name": "ada",
        "displayName": "Ada aGVsbG8= b3RoZXI=",
        "email": None,
    }
    assert TOKEN not in result.stdout
    assert seen == [("GET", MYSELF_PATH, {}, f"Bearer {TOKEN}")]
