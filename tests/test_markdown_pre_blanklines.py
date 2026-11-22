"""Checks that HTML ``<pre>`` keeps meaningful boundary blank lines.

The expected Markdown is written by hand from the contract: only the single
structural newline after a ``<pre>`` start tag is removed; later newlines are
content. Real-CLI cases use synthetic loopback responses only.
"""

import subprocess
from http.server import BaseHTTPRequestHandler
from pathlib import Path

from atlawire._markdown import SafeMarkdownConverter, convert_html
from tests._loopback import (
    Request,
    request_record,
    run_installed,
    send_json,
    serving,
)

TOKEN = "fixture-markdown-pre-token"
SENTINEL = "MARKDOWN-PRE-SENTINEL"
MISSING_BBK_CREDENTIALS = str(
    Path(__file__).with_name("bbk-credentials-missing-for-pre.json")
)
JIRA_CONTEXT = "/jira"
JIRA_KEY = "DEMO-42"
JIRA_PATH = f"{JIRA_CONTEXT}/rest/api/2/issue/{JIRA_KEY}"
JIRA_EXPAND = {"expand": ["renderedFields"]}
CONFLUENCE_CONTEXT = "/confluence"
PAGE_ID = "123"
PAGE_PATH = f"{CONFLUENCE_CONTEXT}/rest/api/content/{PAGE_ID}"
PAGE_EXPAND = {"expand": ["body.storage,version,space,ancestors"]}


def converter() -> SafeMarkdownConverter:
    return SafeMarkdownConverter(escape_misc=True, heading_style="atx", bullets="-")


def test_convert_pre_removes_only_the_opener_line_break() -> None:
    block = converter()

    assert block.convert_pre(object(), "\nline\n", set()) == (
        "\n\n```\nline\n```\n\n"
    )
    assert block.convert_pre(object(), "line", set()) == "\n\n```\nline\n```\n\n"
    assert block.convert_pre(object(), "", set()) == ""


def test_convert_pre_keeps_two_or_more_boundary_blank_lines() -> None:
    block = converter()

    assert block.convert_pre(object(), "\n\n\nline\n\n\n", set()) == (
        "\n\n```\n\n\nline\n\n\n```\n\n"
    )


def test_convert_pre_normalizes_crlf_without_losing_blank_lines() -> None:
    block = converter()

    assert block.convert_pre(object(), "\r\n\r\n\r\nline\r\n\r\n\r\n", set()) == (
        "\n\n```\n\n\nline\n\n\n```\n\n"
    )


def test_convert_pre_still_uses_a_longer_fence_for_backticks() -> None:
    block = converter()

    assert block.convert_pre(object(), "\n```\n", set()) == (
        "\n\n````\n```\n````\n\n"
    )


def test_convert_pre_with_only_a_structural_newline_is_an_empty_fence() -> None:
    block = converter()

    assert block.convert_pre(object(), "\n", set()) == "\n\n```\n\n```\n\n"


def test_html_pre_preserves_two_or_more_boundary_blank_lines() -> None:
    rendered = convert_html("<pre>\n\n\nline\n\n\n</pre>", converter())

    assert rendered == "```\n\n\nline\n\n\n```"


def test_html_paragraph_conversion_stays_plain_text() -> None:
    assert convert_html("<p>text</p>", converter()) == "text"


def environment(origin: str) -> dict[str, str]:
    """Point both products at the loopback context and keep other sources inert."""
    return {
        "ATLAWIRE_JIRA_URL": f"{origin}{JIRA_CONTEXT}/",
        "ATLAWIRE_JIRA_TOKEN": TOKEN,
        "ATLAWIRE_CONFLUENCE_URL": f"{origin}{CONFLUENCE_CONTEXT}/",
        "ATLAWIRE_CONFLUENCE_TOKEN": TOKEN,
        "ATLAWIRE_BITBUCKET_URL": f"{origin}/wrong-bitbucket/",
        "ATLAWIRE_BITBUCKET_TOKEN": "wrong-product-fixture",
        "BBK_CREDENTIALS": MISSING_BBK_CREDENTIALS,
    }


def run_cli(
    arguments: list[str], path: str, body: object
) -> tuple[subprocess.CompletedProcess[str], list[Request]]:
    """Run the installed CLI against one synthetic response on ``path``."""
    seen: list[Request] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            record = request_record(self)
            seen.append(record)
            if record[1] != path or record[3] != f"Bearer {TOKEN}":
                send_json(self, 401, {"message": SENTINEL})
                return
            send_json(self, 200, body)

    with serving(Handler) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        result = run_installed(
            [*arguments, "--token-from-env", "--allow-http-loopback"],
            environment(origin),
        )
    return result, seen


def test_installed_issue_markdown_keeps_two_blank_lines_at_pre_boundaries() -> None:
    body = {
        "key": JIRA_KEY,
        "fields": {"summary": "Pre"},
        "renderedFields": {"description": "<pre>\n\n\ncode\n\n\n</pre>"},
    }

    result, seen = run_cli(["issue", JIRA_KEY, "--markdown"], JIRA_PATH, body)

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout == (
        f"# {JIRA_KEY}: Pre\n\n"
        "## Description\n\n"
        "```\n\n\ncode\n\n\n```\n"
    )
    assert seen == [("GET", JIRA_PATH, JIRA_EXPAND, f"Bearer {TOKEN}")]


def test_installed_page_markdown_keeps_two_blank_lines_at_pre_boundaries() -> None:
    body = {
        "id": PAGE_ID,
        "type": "page",
        "title": "Pre",
        "body": {"storage": {"value": "<pre>\n\n\ncode\n\n\n</pre>"}},
    }

    result, seen = run_cli(["page", PAGE_ID, "--markdown"], PAGE_PATH, body)

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout == "# Pre\n\n```\n\n\ncode\n\n\n```\n"
    assert seen == [("GET", PAGE_PATH, PAGE_EXPAND, f"Bearer {TOKEN}")]


def test_the_bbk_credentials_override_is_a_missing_synthetic_path() -> None:
    assert "missing-for-pre" in MISSING_BBK_CREDENTIALS
    assert not Path(MISSING_BBK_CREDENTIALS).exists()
