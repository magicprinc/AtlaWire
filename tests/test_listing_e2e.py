"""Installed-CLI checks for recursive file and direct directory listings."""

import json
import subprocess
from collections.abc import Sequence
from http.server import BaseHTTPRequestHandler

import pytest

from tests._loopback import (
    Request,
    request_record,
    run_installed,
    send_json,
    serving,
)

TOKEN = "fixture-listing-cli"
JIRA_TOKEN = "wrong-product-jira-listing"
CONFLUENCE_TOKEN = "wrong-product-confluence-listing"
SENTINEL = "LISTING-CLI-SENTINEL"
CONTEXT = "/scm/bitbucket"
REPO = "DEMO/widgets"
FILES_PATH = f"{CONTEXT}/rest/api/1.0/projects/DEMO/repos/widgets/files"
BROWSE_PATH = f"{CONTEXT}/rest/api/1.0/projects/DEMO/repos/widgets/browse"
SUBDIR = "папка/dir name/a#b?c%"
SUBDIR_ENCODED = "%D0%BF%D0%B0%D0%BF%D0%BA%D0%B0/dir%20name/a%23b%3Fc%25"
AT = "feature/ü &?+#"


def run_listing(
    command: str,
    *arguments: str,
    responses: Sequence[tuple[int, object]],
) -> tuple[
    subprocess.CompletedProcess[str],
    list[Request],
    list[str | None],
]:
    seen: list[Request] = []
    accepts: list[str | None] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            seen.append(request_record(self))
            accepts.append(self.headers.get("Accept"))
            index = len(seen) - 1
            if index >= len(responses):
                status, body = (
                    500,
                    {"errors": [{"message": "UNEXPECTED-EXTRA-REQUEST"}]},
                )
            else:
                status, body = responses[index]
            send_json(self, status, body)

    with serving(Handler) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        result = run_installed(
            [
                command,
                REPO,
                *arguments,
                "--base-url",
                f"{origin}{CONTEXT}/",
                "--allow-http-loopback",
                "--token-from-env",
            ],
            {
                "ATLAWIRE_BITBUCKET_URL": f"{origin}{CONTEXT}/",
                "ATLAWIRE_BITBUCKET_TOKEN": TOKEN,
                "ATLAWIRE_JIRA_URL": f"{origin}/wrong-jira/",
                "ATLAWIRE_JIRA_TOKEN": JIRA_TOKEN,
                "ATLAWIRE_CONFLUENCE_URL": f"{origin}/wrong-confluence/",
                "ATLAWIRE_CONFLUENCE_TOKEN": CONFLUENCE_TOKEN,
            },
        )
    return result, seen, accepts


def files_request(start: int) -> Request:
    return (
        "GET",
        FILES_PATH,
        {"start": [str(start)], "limit": ["100"], "at": [AT]},
        f"Bearer {TOKEN}",
    )


def browse_request(start: int, path: str = BROWSE_PATH) -> Request:
    return (
        "GET",
        path,
        {"start": [str(start)], "limit": ["100"]},
        f"Bearer {TOKEN}",
    )


def test_files_follows_the_noncontiguous_cursor_with_fixed_revision() -> None:
    responses = [
        (
            200,
            {
                "size": 2,
                "limit": 100,
                "isLastPage": False,
                "nextPageStart": 13,
                "values": ["src/a b.py", {"path": "legacy/ü.txt"}],
            },
        ),
        (
            200,
            {
                "size": 1,
                "limit": 100,
                "isLastPage": True,
                "values": ["README.md"],
            },
        ),
    ]

    result, seen, accepts = run_listing(
        "files", "--at", AT, "--json", responses=responses
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == ["src/a b.py", "legacy/ü.txt", "README.md"]
    assert seen == [files_request(0), files_request(13)]
    assert accepts == ["application/json", "application/json"]


def test_files_plain_output_is_one_escaped_path_per_line_without_a_header() -> None:
    responses = [
        (
            200,
            {
                "size": 2,
                "limit": 100,
                "isLastPage": True,
                "values": ["README.md", "src/a b.txt"],
            },
        )
    ]

    result, seen, _ = run_listing("files", responses=responses)

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout == "README.md\nsrc/a b.txt\n"
    assert seen == [
        ("GET", FILES_PATH, {"start": ["0"], "limit": ["100"]}, f"Bearer {TOKEN}")
    ]


def test_empty_files_page_emits_no_lines() -> None:
    result, seen, _ = run_listing(
        "files",
        responses=[
            (
                200,
                {"size": 0, "limit": 100, "isLastPage": True, "values": []},
            )
        ],
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert seen == [
        ("GET", FILES_PATH, {"start": ["0"], "limit": ["100"]}, f"Bearer {TOKEN}")
    ]


def test_ls_reads_the_nested_children_cursor_not_the_outer_browse_page() -> None:
    responses = [
        (
            200,
            {
                "isLastPage": True,
                "nextPageStart": 999,
                "children": {
                    "size": 1,
                    "limit": 100,
                    "isLastPage": False,
                    "nextPageStart": 9,
                    "values": [{"path": "README.md", "type": "FILE", "size": 0}],
                },
            },
        ),
        (
            200,
            {
                "children": {
                    "size": 1,
                    "limit": 100,
                    "isLastPage": True,
                    "values": [{"path": "src", "type": "DIRECTORY"}],
                }
            },
        ),
    ]

    result, seen, accepts = run_listing("ls", "--json", responses=responses)

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == [
        {"path": "README.md", "type": "FILE", "size": 0},
        {"path": "src", "type": "DIRECTORY", "size": None},
    ]
    assert seen == [browse_request(0), browse_request(9)]
    assert accepts == ["application/json", "application/json"]


def test_ls_encodes_a_subdirectory_once_and_fixes_the_revision() -> None:
    responses = [
        (
            200,
            {
                "children": {
                    "size": 2,
                    "limit": 100,
                    "isLastPage": True,
                    "values": [
                        {"path": "a b.txt", "type": "FILE", "size": 0},
                        {"path": "b.txt", "type": None, "size": None},
                    ],
                }
            },
        )
    ]

    result, seen, _ = run_listing("ls", SUBDIR, "--at", AT, responses=responses)

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout == (
        "# 2 row(s)\npath\ttype\tsize\na b.txt\tFILE\t0\nb.txt\t\t\n"
    )
    assert seen == [
        (
            "GET",
            f"{BROWSE_PATH}/{SUBDIR_ENCODED}",
            {"start": ["0"], "limit": ["100"], "at": [AT]},
            f"Bearer {TOKEN}",
        )
    ]


def test_a_later_files_http_failure_after_a_valid_row_is_sanitized() -> None:
    responses = [
        (
            200,
            {
                "size": 1,
                "limit": 100,
                "isLastPage": False,
                "nextPageStart": 5,
                "values": ["src/first.py"],
            },
        ),
        (
            503,
            {
                "errors": [{"message": SENTINEL}],
                "token": TOKEN,
                "x": SENTINEL,
            },
        ),
    ]

    result, seen, _ = run_listing("files", "--json", responses=responses)

    assert result.returncode == 1
    assert result.stdout == ""
    assert "HTTP 503" in result.stderr
    for detail in (TOKEN, JIRA_TOKEN, CONFLUENCE_TOKEN, SENTINEL):
        assert detail not in result.stderr
    assert seen == [
        ("GET", FILES_PATH, {"start": ["0"], "limit": ["100"]}, f"Bearer {TOKEN}"),
        ("GET", FILES_PATH, {"start": ["5"], "limit": ["100"]}, f"Bearer {TOKEN}"),
    ]


def test_a_malformed_nested_page_after_a_valid_row_fails_without_output() -> None:
    responses = [
        (
            200,
            {
                "children": {
                    "size": 1,
                    "limit": 100,
                    "isLastPage": False,
                    "nextPageStart": 5,
                    "values": [{"path": "src/first.py", "type": "FILE", "size": 1}],
                }
            },
        ),
        (
            200,
            {
                "lines": [{"text": "print('hello')"}],
                "isLastPage": True,
                "x": SENTINEL,
            },
        ),
    ]

    result, seen, _ = run_listing("ls", responses=responses)

    assert result.returncode == 1
    assert result.stdout == ""
    assert "children" in result.stderr
    for detail in (TOKEN, JIRA_TOKEN, CONFLUENCE_TOKEN, SENTINEL):
        assert detail not in result.stderr
    assert seen == [
        ("GET", BROWSE_PATH, {"start": ["0"], "limit": ["100"]}, f"Bearer {TOKEN}"),
        ("GET", BROWSE_PATH, {"start": ["5"], "limit": ["100"]}, f"Bearer {TOKEN}"),
    ]


def test_an_unsafe_directory_path_is_rejected_before_any_request() -> None:
    result, seen, _ = run_listing("ls", "../secret", responses=[])

    assert result.returncode == 1
    assert result.stdout == ""
    assert "path" in result.stderr
    assert seen == []


@pytest.mark.parametrize("value", ["0", "1001"])
@pytest.mark.parametrize("command", ["files", "ls"])
def test_page_count_outside_the_range_is_a_usage_error(
    command: str, value: str
) -> None:
    result, seen, _ = run_listing(command, "--max-pages", value, responses=[])

    assert result.returncode == 2
    assert result.stdout == ""
    assert seen == []
