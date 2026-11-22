"""Installed-CLI loopback contracts for saved BBK credential reuse."""

import http.client
import json
import os
import shutil
import subprocess
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import ClassVar
from urllib.parse import urlsplit

import pytest

from tests._loopback import Request, request_record, send_json, serving

JIRA_TOKEN = "synthetic-jira-token-7c1"
CONFLUENCE_TOKEN = "synthetic-confluence-token-7c2"
BITBUCKET_TOKEN = "synthetic-bitbucket-token-7c3"
ENVIRONMENT_TOKEN = "synthetic-environment-token-7c4"
SECRET_MARKER = "response-body-must-not-be-echoed"

JIRA_PATH = "/jira/rest/api/2/myself"
CONFLUENCE_PATH = "/confluence/rest/api/space"
BITBUCKET_PATH = "/bitbucket/rest/api/1.0/projects"
RESPONSES: dict[str, object] = {
    JIRA_PATH: {"name": "fixture-user"},
    CONFLUENCE_PATH: {"results": []},
    BITBUCKET_PATH: {"values": [], "isLastPage": True},
}


def clean_environment(**values: str) -> dict[str, str]:
    env = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith("ATLAWIRE_") and name != "BBK_CREDENTIALS"
    }
    env.update(values)
    return env


def run_cli(args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    script = shutil.which("atlawire")
    assert script is not None, "Install AtlaWire before running its CLI E2E suite."
    return subprocess.run(
        [script, *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )


def write_credentials(path: Path, document: object) -> Path:
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def product_document(origin: str) -> dict[str, str]:
    return {
        "jira_url": f"{origin}/jira/",
        "jira_token": JIRA_TOKEN,
        "confluence_url": f"{origin}/confluence/",
        "confluence_token": CONFLUENCE_TOKEN,
        "bitbucket_url": f"{origin}/bitbucket/",
        "bitbucket_token": BITBUCKET_TOKEN,
    }


class RecordingHandler(BaseHTTPRequestHandler):
    seen: ClassVar[list[Request]] = []
    responses: ClassVar[dict[str, object]] = RESPONSES

    def log_message(self, format: str, *args: object) -> None:
        pass

    def do_GET(self) -> None:
        self.seen.append(request_record(self))
        path = urlsplit(self.path).path
        body = self.responses.get(path)
        if body is None:
            send_json(self, 404, {"message": SECRET_MARKER})
            return
        send_json(self, 200, body)

    def _reject_method(self) -> None:
        """Record every non-GET method so exact sequences cannot miss one."""
        self.seen.append(request_record(self))
        send_json(self, 405, {"message": "method not allowed"})

    do_POST = _reject_method
    do_PUT = _reject_method
    do_PATCH = _reject_method
    do_DELETE = _reject_method
    do_HEAD = _reject_method
    do_OPTIONS = _reject_method
    do_TRACE = _reject_method


def recording_handler(
    responses: dict[str, object] | None = None,
) -> type[RecordingHandler]:
    selected = RESPONSES if responses is None else responses

    class Handler(RecordingHandler):
        seen: ClassVar[list[Request]] = []
        responses: ClassVar[dict[str, object]] = selected

    return Handler


@pytest.mark.parametrize(
    "method", ["POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "TRACE"]
)
def test_forbidden_method_is_recorded_and_rejected(method: str) -> None:
    Handler = recording_handler({JIRA_PATH: {"name": "fixture-user"}})
    with serving(Handler) as server:
        connection = http.client.HTTPConnection(
            "127.0.0.1", server.server_port, timeout=5
        )
        try:
            connection.request(
                method,
                JIRA_PATH,
                body=b"{}",
                headers={"Authorization": "Bearer synthetic-probe"},
            )
            response = connection.getresponse()
            response.read()
        finally:
            connection.close()

    assert response.status == 405
    assert Handler.seen == [(method, JIRA_PATH, {}, "Bearer synthetic-probe")]
    assert Handler.seen != [("GET", JIRA_PATH, {}, "Bearer synthetic-probe")]


@pytest.mark.parametrize(
    ("args", "expected_path", "expected_query", "expected_token"),
    [
        (["jira-me", "--allow-http-loopback"], JIRA_PATH, {}, JIRA_TOKEN),
        (
            ["spaces", "--limit", "1", "--allow-http-loopback"],
            CONFLUENCE_PATH,
            {"start": ["0"], "limit": ["1"]},
            CONFLUENCE_TOKEN,
        ),
        (
            ["projects", "--allow-http-loopback"],
            BITBUCKET_PATH,
            {"start": ["0"], "limit": ["100"]},
            BITBUCKET_TOKEN,
        ),
    ],
)
def test_each_saved_product_pair_routes_to_its_own_destination(
    tmp_path: Path,
    args: list[str],
    expected_path: str,
    expected_query: dict[str, list[str]],
    expected_token: str,
) -> None:
    Handler = recording_handler()
    with serving(Handler) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        credentials = write_credentials(
            tmp_path / "credentials.json", product_document(origin)
        )
        result = run_cli(args, clean_environment(BBK_CREDENTIALS=str(credentials)))

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert Handler.seen == [
        ("GET", expected_path, expected_query, f"Bearer {expected_token}")
    ]
    combined = result.stdout + result.stderr
    for token in (JIRA_TOKEN, CONFLUENCE_TOKEN, BITBUCKET_TOKEN, ENVIRONMENT_TOKEN):
        assert token not in combined


@pytest.mark.parametrize("mode", ["environment", "option"])
def test_equivalent_url_override_is_accepted(tmp_path: Path, mode: str) -> None:
    Handler = recording_handler()
    with serving(Handler) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        credentials = write_credentials(
            tmp_path / "credentials.json", product_document(origin)
        )
        env = clean_environment(BBK_CREDENTIALS=str(credentials))
        args = ["jira-me", "--allow-http-loopback"]
        supplied = f"{origin}/jira"
        if mode == "environment":
            env["ATLAWIRE_JIRA_URL"] = supplied
        else:
            args.extend(["--base-url", supplied])
        result = run_cli(args, env)

    assert result.returncode == 0, result.stderr
    assert Handler.seen == [("GET", JIRA_PATH, {}, f"Bearer {JIRA_TOKEN}")]
    assert JIRA_TOKEN not in result.stdout + result.stderr


@pytest.mark.parametrize("mode", ["environment", "option"])
def test_different_url_override_fails_before_any_request(
    tmp_path: Path, mode: str
) -> None:
    Handler = recording_handler()
    with serving(Handler) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        credentials = write_credentials(
            tmp_path / "credentials.json", product_document(origin)
        )
        env = clean_environment(BBK_CREDENTIALS=str(credentials))
        args = ["jira-me", "--allow-http-loopback"]
        supplied = f"{origin}/other"
        if mode == "environment":
            env["ATLAWIRE_JIRA_URL"] = supplied
        else:
            args.extend(["--base-url", supplied])
        result = run_cli(args, env)

    assert result.returncode == 1
    assert result.stdout == ""
    assert Handler.seen == []
    assert (
        "The supplied base URL does not match saved BBK credentials for jira"
        in result.stderr
    )
    combined = result.stdout + result.stderr
    for token in (JIRA_TOKEN, CONFLUENCE_TOKEN, BITBUCKET_TOKEN):
        assert token not in combined


@pytest.mark.parametrize(
    "stored",
    [
        b'{"jira_url": "synthetic", "jira_token": "broken',
        json.dumps(
            {
                "jira_url": "http://127.0.0.1:9/saved-jira/",
                "jira_token": JIRA_TOKEN,
            }
        ).encode(),
    ],
    ids=["malformed", "valid-different-pair"],
)
def test_explicit_environment_mode_ignores_the_saved_file(
    tmp_path: Path, stored: bytes
) -> None:
    Handler = recording_handler({"/env-jira/rest/api/2/myself": {"name": "env-user"}})
    with serving(Handler) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        path = tmp_path / "credentials.json"
        path.write_bytes(stored)
        env = clean_environment(
            BBK_CREDENTIALS=str(path),
            ATLAWIRE_JIRA_URL=f"{origin}/env-jira/",
            ATLAWIRE_JIRA_TOKEN=ENVIRONMENT_TOKEN,
        )
        result = run_cli(["jira-me", "--allow-http-loopback", "--token-from-env"], env)

    assert result.returncode == 0, result.stderr
    assert Handler.seen == [
        ("GET", "/env-jira/rest/api/2/myself", {}, f"Bearer {ENVIRONMENT_TOKEN}")
    ]
    combined = result.stdout + result.stderr
    assert ENVIRONMENT_TOKEN not in combined
    assert JIRA_TOKEN not in combined


def test_environment_mode_without_a_url_never_uses_the_saved_file(
    tmp_path: Path,
) -> None:
    Handler = recording_handler()
    with serving(Handler) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        credentials = write_credentials(
            tmp_path / "credentials.json", product_document(origin)
        )
        env = clean_environment(
            BBK_CREDENTIALS=str(credentials),
            ATLAWIRE_JIRA_TOKEN=JIRA_TOKEN,
        )
        result = run_cli(["jira-me", "--token-from-env"], env)

    assert result.returncode == 2
    assert result.stdout == ""
    assert Handler.seen == []
    assert "Missing --base-url or ATLAWIRE_JIRA_URL" in result.stderr
    assert JIRA_TOKEN not in result.stdout + result.stderr


@pytest.mark.parametrize(
    "stored",
    [
        None,
        json.dumps({}).encode(),
        json.dumps({"jira_url": "http://127.0.0.1:9/jira/"}).encode(),
        json.dumps({"jira_token": JIRA_TOKEN}).encode(),
        json.dumps({"jira_url": "http://127.0.0.1:9/jira/", "jira_token": 7}).encode(),
        json.dumps({"jira_url": "http://127.0.0.1:9/jira/", "jira_token": ""}).encode(),
        b'{"jira_url": "http://127.0.0.1:9/jira/", "jira_token": "'
        + SECRET_MARKER.encode(),
        b'{"jira_url": "\xff", "jira_token": "' + SECRET_MARKER.encode() + b'"}',
        json.dumps(
            {
                "confluence_url": "http://127.0.0.1:9/confluence/",
                "confluence_token": CONFLUENCE_TOKEN,
            }
        ).encode(),
    ],
    ids=[
        "missing",
        "empty-object",
        "missing-token",
        "missing-url",
        "non-string-token",
        "empty-token",
        "malformed-json",
        "invalid-utf8",
        "other-product-only",
    ],
)
def test_invalid_saved_configuration_fails_without_output_or_requests(
    tmp_path: Path, stored: bytes | None
) -> None:
    Handler = recording_handler()
    path = tmp_path / "credentials.json"
    if stored is not None:
        path.write_bytes(stored)
    with serving(Handler):
        result = run_cli(
            ["jira-me", "--allow-http-loopback"],
            clean_environment(BBK_CREDENTIALS=str(path)),
        )

    assert result.returncode == 1
    assert result.stdout == ""
    assert Handler.seen == []
    assert "Saved BBK credentials" in result.stderr
    assert "jira" in result.stderr
    combined = result.stdout + result.stderr
    assert JIRA_TOKEN not in combined
    assert CONFLUENCE_TOKEN not in combined
    assert SECRET_MARKER not in combined


def test_http_error_does_not_echo_the_response_body_or_token(
    tmp_path: Path,
) -> None:
    class Handler(BaseHTTPRequestHandler):
        seen: ClassVar[list[Request]] = []

        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            self.seen.append(request_record(self))
            send_json(self, 500, {"message": f"{JIRA_TOKEN} {SECRET_MARKER}"})

    with serving(Handler) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        credentials = write_credentials(
            tmp_path / "credentials.json", product_document(origin)
        )
        result = run_cli(
            ["jira-me", "--allow-http-loopback"],
            clean_environment(BBK_CREDENTIALS=str(credentials)),
        )

    assert result.returncode == 1
    assert result.stdout == ""
    assert Handler.seen == [("GET", JIRA_PATH, {}, f"Bearer {JIRA_TOKEN}")]
    assert "HTTP 500" in result.stderr
    combined = result.stdout + result.stderr
    assert JIRA_TOKEN not in combined
    assert SECRET_MARKER not in combined


@pytest.mark.parametrize("args", [["--help"], ["--version"]])
def test_help_and_version_do_not_open_the_bbk_file(
    tmp_path: Path, args: list[str]
) -> None:
    result = run_cli(args, clean_environment(BBK_CREDENTIALS=str(tmp_path)))

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert "Saved BBK credentials" not in result.stdout
