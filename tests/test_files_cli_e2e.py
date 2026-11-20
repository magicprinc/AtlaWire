"""Installed-CLI checks for direct and pull request file reads."""

import gzip
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import cast

import pytest

from tests._loopback import (
    Request,
    request_record,
    run_installed_bytes,
    send_bytes,
    send_json,
    serving,
)

TOKEN = "fixture-file-cli"
JIRA_TOKEN = "wrong-product-jira-file-cli"
CONFLUENCE_TOKEN = "wrong-product-confluence-file-cli"
SENTINEL = "FILE-CLI-SENTINEL"
CONTEXT = "/scm/bitbucket"
RAW_BASE = f"{CONTEXT}/rest/api/1.0/projects"
PR_PATH = f"{RAW_BASE}/DEMO/repos/widgets/pull-requests/7"
PID_PATH = "папка/dir name/a#b?c%d.txt"
PID_ENCODED = "%D0%BF%D0%B0%D0%BF%D0%BA%D0%B0/dir%20name/a%23b%3Fc%25d.txt"
REF = "feature/x+y"


def environment(origin: str) -> dict[str, str]:
    return {
        "ATLAWIRE_BITBUCKET_URL": f"{origin}{CONTEXT}/",
        "ATLAWIRE_BITBUCKET_TOKEN": TOKEN,
        "ATLAWIRE_JIRA_URL": f"{origin}/wrong-jira/",
        "ATLAWIRE_JIRA_TOKEN": JIRA_TOKEN,
        "ATLAWIRE_CONFLUENCE_URL": f"{origin}/wrong-confluence/",
        "ATLAWIRE_CONFLUENCE_TOKEN": CONFLUENCE_TOKEN,
    }


def base_arguments(origin: str) -> list[str]:
    return [
        "--base-url",
        f"{origin}{CONTEXT}/",
        "--allow-http-loopback",
        "--token-from-env",
    ]


def run_file(
    *arguments: str, body: bytes
) -> tuple[
    subprocess.CompletedProcess[bytes], list[Request], list[str | None], list[str]
]:
    seen: list[Request] = []
    accepts: list[str | None] = []
    raw_paths: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            seen.append(request_record(self))
            accepts.append(self.headers.get("Accept"))
            raw_paths.append(self.path)
            send_bytes(self, 200, body)

    with serving(Handler) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        result = run_installed_bytes(
            ["file", *arguments, *base_arguments(origin)],
            environment(origin),
        )
    return result, seen, accepts, raw_paths


@pytest.mark.parametrize(
    "body",
    [
        b"\xef\xbb\xbffirst  \r\nsecond\t\r\nlast",
        b"first\nsecond\n",
        b"first\nsecond",
    ],
    ids=["bom-crlf-no-final-newline", "lf-trailing", "lf-no-trailing"],
)
def test_direct_file_writes_exact_utf8_bytes_and_encodes_path_and_ref(
    body: bytes,
) -> None:
    result, seen, accepts, raw_paths = run_file(
        "DEMO/widgets", PID_PATH, "--at", REF, body=body
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == b""
    assert result.stdout == body
    assert seen == [
        (
            "GET",
            f"{RAW_BASE}/DEMO/repos/widgets/raw/{PID_ENCODED}",
            {"at": [REF]},
            f"Bearer {TOKEN}",
        )
    ]
    assert accepts == ["text/plain"]
    assert raw_paths == [
        f"{RAW_BASE}/DEMO/repos/widgets/raw/{PID_ENCODED}?at=feature%2Fx%2By"
    ]
    for detail in (TOKEN, JIRA_TOKEN, CONFLUENCE_TOKEN, SENTINEL):
        assert detail.encode() not in result.stderr


def test_direct_file_defaults_to_master() -> None:
    result, seen, accepts, raw_paths = run_file(
        "DEMO/widgets", "plain.txt", body=b"hello"
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == b"hello"
    assert seen == [
        (
            "GET",
            f"{RAW_BASE}/DEMO/repos/widgets/raw/plain.txt",
            {"at": ["master"]},
            f"Bearer {TOKEN}",
        )
    ]
    assert accepts == ["text/plain"]
    assert raw_paths == [f"{RAW_BASE}/DEMO/repos/widgets/raw/plain.txt?at=master"]


def test_partial_content_is_rejected_without_partial_stdout() -> None:
    body = b"PARTIAL-CONTENT-SENTINEL"
    seen: list[Request] = []
    accepts: list[str | None] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            seen.append(request_record(self))
            accepts.append(self.headers.get("Accept"))
            send_bytes(
                self,
                206,
                body,
                extra_headers={
                    "Content-Range": f"bytes 0-{len(body) - 1}/{len(body) + 100}"
                },
            )

    with serving(Handler) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        result = run_installed_bytes(
            ["file", "DEMO/widgets", "a.txt", *base_arguments(origin)],
            environment(origin),
        )

    assert result.returncode != 0
    assert result.stdout == b""
    assert body not in result.stdout
    assert body not in result.stderr
    assert b"206" in result.stderr
    assert b"partial" in result.stderr.lower()
    assert seen == [
        (
            "GET",
            f"{RAW_BASE}/DEMO/repos/widgets/raw/a.txt",
            {"at": ["master"]},
            f"Bearer {TOKEN}",
        )
    ]
    assert accepts == ["text/plain"]


def pr_payload(origin: str) -> dict[str, object]:
    return {
        "id": 7,
        "title": "Talking Nerdy",
        "state": "OPEN",
        "fromRef": {
            "displayId": "fork-display",
            "latestCommit": "a" * 40,
            "repository": {
                "slug": "source",
                "project": {"key": "FORK"},
                "links": {"self": [{"href": f"{origin}/decoy/fork"}]},
            },
        },
        "toRef": {
            "displayId": "target-display",
            "latestCommit": "b" * 40,
            "repository": {
                "slug": "target",
                "project": {"key": "DEST"},
                "links": {"self": [{"href": f"{origin}/decoy/target"}]},
            },
        },
        "links": {"self": [{"href": f"{origin}/decoy/pull-request"}]},
    }


def run_pr_file(
    *arguments: str, body: bytes
) -> tuple[
    subprocess.CompletedProcess[bytes], list[Request], list[str | None], list[str]
]:
    seen: list[Request] = []
    accepts: list[str | None] = []
    raw_paths: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            seen.append(request_record(self))
            accepts.append(self.headers.get("Accept"))
            raw_paths.append(self.path)
            if self.path.startswith("/decoy/"):
                send_bytes(self, 200, b"decoy")
                return
            if len(seen) == 1:
                server = cast(HTTPServer, self.server)
                origin = f"http://127.0.0.1:{server.server_port}"
                send_json(self, 200, pr_payload(origin))
                return
            send_bytes(self, 200, body)

    with serving(Handler) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        result = run_installed_bytes(
            ["pr", "DEMO/widgets", "7", "file", *arguments, *base_arguments(origin)],
            environment(origin),
        )
    return result, seen, accepts, raw_paths


@pytest.mark.parametrize(
    ("side", "project", "slug", "commit", "body"),
    [
        ("new", "FORK", "source", "a" * 40, b"new side\r\n"),
        ("old", "DEST", "target", "b" * 40, b"old side\r\n"),
    ],
    ids=["default-new-fork", "old-target"],
)
def test_pr_file_uses_the_selected_side_repository_and_full_commit(
    side: str, project: str, slug: str, commit: str, body: bytes
) -> None:
    arguments = ("src/a b.txt",) if side == "new" else ("src/a b.txt", "--side", "old")

    result, seen, accepts, raw_paths = run_pr_file(*arguments, body=body)

    assert result.returncode == 0, result.stderr
    assert result.stderr == b""
    assert result.stdout == body
    assert seen == [
        ("GET", PR_PATH, {}, f"Bearer {TOKEN}"),
        (
            "GET",
            f"{RAW_BASE}/{project}/repos/{slug}/raw/src/a%20b.txt",
            {"at": [commit]},
            f"Bearer {TOKEN}",
        ),
    ]
    assert accepts == ["application/json", "text/plain"]
    assert raw_paths == [
        PR_PATH,
        f"{RAW_BASE}/{project}/repos/{slug}/raw/src/a%20b.txt?at={commit}",
    ]


@pytest.mark.parametrize(
    "arguments",
    [
        ("../secret",),
        ("src/../secret",),
        ("/absolute",),
        ("src/%2e%2e/secret",),
        ("src/a\\b",),
    ],
    ids=["parent", "inner-parent", "absolute", "encoded-parent", "backslash"],
)
def test_invalid_pr_path_fails_before_any_request(arguments: tuple[str, ...]) -> None:
    result, seen, accepts, raw_paths = run_pr_file(*arguments, body=b"never")

    assert result.returncode == 1
    assert result.stdout == b""
    assert "file path" in result.stderr.decode()
    assert TOKEN not in result.stderr.decode()
    assert seen == []
    assert accepts == []
    assert raw_paths == []


@pytest.mark.parametrize(
    "arguments",
    [
        ("file", "src/a.txt", "--json"),
        ("show", "src/a.txt"),
        ("file",),
        ("file", "src/a.txt", "--context", "3"),
        ("file", "src/a.txt", "--max-pages", "2"),
        ("show", "--side", "new"),
    ],
    ids=[
        "json",
        "path-with-show",
        "missing-path",
        "context",
        "max-pages",
        "side-with-show",
    ],
)
def test_irrelevant_pr_operands_and_flags_are_usage_errors_before_io(
    arguments: tuple[str, ...],
) -> None:
    seen: list[Request] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            seen.append(request_record(self))
            send_json(self, 500, {"message": SENTINEL})

    with serving(Handler) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        result = run_installed_bytes(
            ["pr", "DEMO/widgets", "7", *arguments, *base_arguments(origin)],
            environment(origin),
        )

    assert result.returncode == 2
    assert result.stdout == b""
    assert seen == []


def test_file_rejects_unknown_flags_before_any_request() -> None:
    seen: list[Request] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            seen.append(request_record(self))
            send_bytes(self, 200, b"never")

    with serving(Handler) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        result = run_installed_bytes(
            ["file", "DEMO/widgets", "a.txt", "--json", *base_arguments(origin)],
            environment(origin),
        )

    assert result.returncode == 2
    assert result.stdout == b""
    assert seen == []


def test_invalid_selected_metadata_fails_after_json_before_raw_output() -> None:
    seen: list[Request] = []
    accepts: list[str | None] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            seen.append(request_record(self))
            accepts.append(self.headers.get("Accept"))
            server = cast(HTTPServer, self.server)
            origin = f"http://127.0.0.1:{server.server_port}"
            payload = pr_payload(origin)
            from_ref = payload["fromRef"]
            assert isinstance(from_ref, dict)
            from_ref["latestCommit"] = "not-a-full-sha"
            send_json(self, 200, payload)

    with serving(Handler) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        result = run_installed_bytes(
            [
                "pr",
                "DEMO/widgets",
                "7",
                "file",
                "a.txt",
                *base_arguments(origin),
            ],
            environment(origin),
        )

    assert result.returncode == 1
    assert result.stdout == b""
    assert "metadata" in result.stderr.decode()
    assert seen == [("GET", PR_PATH, {}, f"Bearer {TOKEN}")]
    assert accepts == ["application/json"]


@pytest.mark.parametrize(
    "mode",
    [pytest.param("oversize", id="oversize"), pytest.param("short", id="short")],
)
def test_oversize_and_short_bodies_leave_no_partial_stdout(mode: str) -> None:
    if mode == "oversize":
        body = gzip.compress(b"a" * (1024 * 1024 + 1))
        encoding = "gzip"
        declared = len(body)
    else:
        body = b"short"
        encoding = None
        declared = 50
    seen: list[Request] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            seen.append(request_record(self))
            send_bytes(
                self,
                200,
                body,
                content_encoding=encoding,
                declared_length=declared,
            )

    with serving(Handler) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        result = run_installed_bytes(
            ["file", "DEMO/widgets", "a.txt", *base_arguments(origin)],
            environment(origin),
        )

    assert result.returncode == 1
    assert result.stdout == b""
    assert len(seen) == 1
    assert TOKEN.encode() not in result.stderr
    assert SENTINEL.encode() not in result.stderr
