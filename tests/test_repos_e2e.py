import json
import os
import shutil
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from urllib.parse import parse_qs, urlsplit

import pytest

TOKEN = "fixture-only-value"
PATH = "/scm/rest/api/1.0/projects/DEMO/repos"
FIRST = {"slug": "one", "name": "First", "state": "AVAILABLE", "public": False}
SECOND = {"slug": "two", "name": "Second", "state": "AVAILABLE", "public": True}


def run_repos(
    scenario: str, *options: str
) -> tuple[subprocess.CompletedProcess[str], list[tuple[str, str, bool]]]:
    script = shutil.which("atlawire")
    assert script is not None, "Install AtlaWire before running its CLI E2E suite."
    seen: list[tuple[str, str, bool]] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            url = urlsplit(self.path)
            start = parse_qs(url.query).get("start", [""])[0]
            authorized = self.headers.get("Authorization") == f"Bearer {TOKEN}"
            seen.append((url.path, start, authorized))
            status = 200
            if url.path != PATH or not authorized or scenario == "unauthorized":
                status, body = 401, {"error": TOKEN}
            elif scenario == "redirect":
                self.send_response(302)
                self.send_header("Location", "/unexpected")
                self.end_headers()
                return
            elif start == "0":
                body = {"values": [FIRST], "isLastPage": False, "nextPageStart": 7}
                if scenario == "missing-marker":
                    del body["isLastPage"]
                elif scenario == "repeated-cursor":
                    body["nextPageStart"] = 0
                elif scenario == "controls":
                    body = {
                        "values": [{**FIRST, "name": "A\tB\nC\x1b[2J"}],
                        "isLastPage": True,
                    }
            elif start != "7" or scenario == "later-failure":
                status, body = 503, {"error": TOKEN}
            else:
                body = {"values": [SECOND], "isLastPage": True}
            payload = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    with HTTPServer(("127.0.0.1", 0), Handler) as server:
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            env = {**os.environ, "ATLAWIRE_BITBUCKET_TOKEN": TOKEN}
            result = subprocess.run(
                [
                    script,
                    "repos",
                    "DEMO",
                    "--base-url",
                    f"http://127.0.0.1:{server.server_port}/scm/",
                    "--allow-http-loopback",
                    "--token-from-env",
                    *options,
                ],
                env=env,
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        finally:
            server.shutdown()
            worker.join(timeout=5)
            assert not worker.is_alive()
    return result, seen


def test_follow_server_cursor_and_keep_repo_fields() -> None:
    result, seen = run_repos("ok", "--json")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [FIRST, SECOND]
    assert not result.stderr
    assert seen == [(PATH, "0", True), (PATH, "7", True)]


def test_default_output_matches_bbk_tsv() -> None:
    result, _ = run_repos("ok")
    assert result.returncode == 0, result.stderr
    assert result.stdout == (
        "# 2 row(s)\nslug\tname\tstate\tpublic\n"
        "one\tFirst\tAVAILABLE\tFalse\ntwo\tSecond\tAVAILABLE\tTrue\n"
    )


def test_control_characters_do_not_break_tsv_or_change_json_values() -> None:
    result, _ = run_repos("controls")
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "# 1 row(s)",
        "slug\tname\tstate\tpublic",
        "one\tA\\tB\\nC\\x1b[2J\tAVAILABLE\tFalse",
    ]
    result, _ = run_repos("controls", "--json")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)[0]["name"] == "A\tB\nC\x1b[2J"


@pytest.mark.parametrize(
    ("scenario", "options", "expected_error", "starts"),
    [
        ("later-failure", (), "HTTP 503", ["0", "7"]),
        ("missing-marker", (), "isLastPage", ["0"]),
        ("repeated-cursor", (), "nextPageStart", ["0"]),
        ("unauthorized", (), "HTTP 401", ["0"]),
        ("ok", ("--max-pages", "1"), "page limit", ["0"]),
        ("redirect", (), "redirect", ["0"]),
    ],
)
def test_failures_do_not_publish_partial_rows_or_follow_redirects(
    scenario: str, options: tuple[str, ...], expected_error: str, starts: list[str]
) -> None:
    result, seen = run_repos(scenario, "--json", *options)
    assert result.returncode == 1
    assert result.stdout == ""
    assert expected_error in result.stderr
    assert TOKEN not in result.stderr
    assert seen == [(PATH, start, True) for start in starts]
