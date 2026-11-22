"""Installed-CLI loopback checks for raw Confluence storage output.

Every response is synthetic, every credential is a fixture, and the saved BBK
path points at a missing file. Output is compared as exact bytes.
"""

import json
import os
import shutil
import subprocess
from http.server import BaseHTTPRequestHandler
from pathlib import Path

import pytest

from tests._loopback import Request, request_record, send_json, serving

TOKEN = "synthetic-page-storage-token-9a"
CONTEXT = "/confluence"
PAGE_ID = "123"
CONTENT_PATH = f"{CONTEXT}/rest/api/content/{PAGE_ID}"
EXPAND = {"expand": ["body.storage,version,space,ancestors"]}
STORAGE = "<p>Résumé ✓</p>\r\n<p>строка ✓</p>\r\n"
MISSING_BBK = str(
    Path(__file__).with_name("bbk-credentials-missing-page-storage.json")
)


def page_payload(storage: str) -> dict[str, object]:
    return {
        "id": PAGE_ID,
        "type": "page",
        "title": "Fixture ✓",
        "version": {"number": 3},
        "space": {"key": "DEMO"},
        "body": {
            "storage": {"value": storage, "representation": "storage"}
        },
    }


def clean_environment(**values: str) -> dict[str, str]:
    env = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith("ATLAWIRE_") and name != "BBK_CREDENTIALS"
    }
    env.update(values)
    return env


def run_page(
    *flags: str, payload: object | None = None
) -> tuple[subprocess.CompletedProcess[bytes], list[Request]]:
    """Run the installed command and preserve exact stdout bytes."""
    seen: list[Request] = []
    body = page_payload(STORAGE) if payload is None else payload

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            record = request_record(self)
            seen.append(record)
            _, path, _, authorization = record
            if path != CONTENT_PATH or authorization != f"Bearer {TOKEN}":
                send_json(self, 404, {"message": "unexpected request"})
                return
            send_json(self, 200, body)

        def do_POST(self) -> None:
            seen.append(request_record(self))
            send_json(self, 405, {"message": "write refused"})

    with serving(Handler) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        env = clean_environment(
            ATLAWIRE_CONFLUENCE_URL=f"{origin}{CONTEXT}/",
            ATLAWIRE_CONFLUENCE_TOKEN=TOKEN,
            ATLAWIRE_JIRA_URL=f"{origin}/wrong-jira/",
            ATLAWIRE_JIRA_TOKEN="wrong-product-fixture",
            ATLAWIRE_BITBUCKET_URL=f"{origin}/wrong-bitbucket/",
            ATLAWIRE_BITBUCKET_TOKEN="wrong-product-fixture",
            BBK_CREDENTIALS=MISSING_BBK,
        )
        script = shutil.which("atlawire")
        assert script is not None, "Install AtlaWire before running its CLI tests."
        result = subprocess.run(
            [
                script,
                "page",
                PAGE_ID,
                *flags,
                "--token-from-env",
                "--allow-http-loopback",
            ],
            env=env,
            capture_output=True,
            timeout=15,
            check=False,
        )
    return result, seen


def expected_request() -> list[Request]:
    return [("GET", CONTENT_PATH, EXPAND, f"Bearer {TOKEN}")]


def test_page_storage_writes_exact_utf8_without_a_trailing_newline() -> None:
    result, seen = run_page("--storage")

    assert result.returncode == 0, result.stderr
    assert result.stderr == b""
    assert result.stdout == STORAGE.encode("utf-8")
    assert seen == expected_request()


def test_page_html_alias_writes_the_same_exact_storage_bytes() -> None:
    result, seen = run_page("--html")

    assert result.returncode == 0, result.stderr
    assert result.stderr == b""
    assert result.stdout == STORAGE.encode("utf-8")
    assert seen == expected_request()


def test_page_storage_empty_body_writes_zero_bytes() -> None:
    result, seen = run_page("--storage", payload=page_payload(""))

    assert result.returncode == 0, result.stderr
    assert result.stderr == b""
    assert result.stdout == b""
    assert seen == expected_request()


def test_page_default_remains_json() -> None:
    payload = page_payload(STORAGE)

    result, seen = run_page(payload=payload)

    assert result.returncode == 0, result.stderr
    assert result.stderr == b""
    assert json.loads(result.stdout) == payload
    assert seen == expected_request()


@pytest.mark.parametrize(
    "flags",
    [("--markdown", "--storage"), ("--markdown", "--html")],
    ids=["storage", "html"],
)
def test_page_storage_and_markdown_are_mutually_exclusive_before_requests(
    flags: tuple[str, str],
) -> None:
    result, seen = run_page(*flags)

    assert result.returncode == 2
    assert result.stdout == b""
    assert b"not both" in result.stderr
    assert seen == []


def test_page_storage_malformed_response_prints_no_stdout() -> None:
    payload = {**page_payload(STORAGE), "body": {}}

    result, seen = run_page("--storage", payload=payload)

    assert result.returncode == 1
    assert result.stdout == b""
    assert b"Confluence page" in result.stderr
    assert TOKEN.encode() not in result.stderr
    assert seen == expected_request()


def test_page_storage_unencodable_text_fails_before_stdout() -> None:
    result, seen = run_page("--storage", payload=page_payload("\ud800"))

    assert result.returncode == 1
    assert result.stdout == b""
    assert b"storage text is not valid UTF-8" in result.stderr
    assert TOKEN.encode() not in result.stderr
    assert seen == expected_request()


def test_page_storage_refuses_a_response_that_echoes_the_bearer_token() -> None:
    result, seen = run_page("--storage", payload=page_payload(TOKEN))

    assert result.returncode == 1
    assert result.stdout == b""
    assert TOKEN.encode() not in result.stdout
    assert TOKEN.encode() not in result.stderr
    assert seen == expected_request()


def test_the_missing_bbk_credentials_path_is_synthetic() -> None:
    assert not Path(MISSING_BBK).exists()
