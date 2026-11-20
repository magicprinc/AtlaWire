import copy
import json
import os
import shutil
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from urllib.parse import parse_qs, urlsplit

import pytest

TOKEN = "fixture-confluence-only"
PATH = "/confluence/rest/api/content/123"
EXPAND = {"expand": ["body.storage,version,space,ancestors"]}
PAGE: dict[str, object] = {
    "id": "123",
    "type": "page",
    "status": "current",
    "title": "Résumé",
    "space": {"key": "DEMO", "name": "Demo Space"},
    "version": {"number": 7, "by": {"displayName": "Ada"}},
    "ancestors": [{"id": "100", "title": "Parent"}],
    "body": {
        "storage": {"value": "<p>Details</p>", "representation": "storage"},
        "view": {"value": "<p>unrequested</p>"},
    },
    "extensions": {"fixtureNote": "LEAK-SENTINEL", "unknown": ["kept", 1, None]},
    "links": {"webui": "/display/DEMO/Resume"},
}


MARKDOWN_STORAGE = (
    "<h2>Overview</h2>"
    "<p><strong>Bold</strong> and <em>italic</em> and <code>inline</code></p>"
    "<ul><li>alpha</li><li>beta</li></ul>"
    "<table><tbody><tr><th>Key</th><th>Value</th></tr>"
    "<tr><td>one</td><td>1</td></tr></tbody></table>"
    '<ac:structured-macro ac:name="code">'
    '<ac:parameter ac:name="language">python</ac:parameter>'
    "<ac:plain-text-body><![CDATA[def f():\n"
    '    return "```"\n'
    "\n"
    "# blank line above\n"
    "\n"
    'print("done")]]></ac:plain-text-body>'
    "</ac:structured-macro>"
    '<ac:structured-macro ac:name="mystery">'
    '<ac:parameter ac:name="secret">PARAM-SENTINEL</ac:parameter>'
    "<ac:rich-text-body><p>Readable <em>rich</em> body</p></ac:rich-text-body>"
    "</ac:structured-macro>"
    '<p><a href="https://evil.invalid/secret">label</a> '
    '<img src="https://evil.invalid/i.png" alt="diagram alt"></p>'
    '<ac:link><ri:page ri:content-title="Other Page"/></ac:link> '
    '<ac:image ac:alt="attachment alt">'
    '<ri:url ri:value="https://evil.invalid/pic.png"/></ac:image>'
)


def without(key: str) -> dict[str, object]:
    page = copy.deepcopy(PAGE)
    del page[key]
    return page


def markdown_page() -> dict[str, object]:
    return {
        **PAGE,
        "title": "Résumé\n# injected",
        "body": {"storage": {"value": MARKDOWN_STORAGE, "representation": "storage"}},
    }


MALFORMED_PAGES = [
    ("cross-id", {**PAGE, "id": "124"}),
    ("cross-integer-id", {**PAGE, "id": 124}),
    ("padded-id", {**PAGE, "id": "0123"}),
    ("missing-id", without("id")),
    ("boolean-id", {**PAGE, "id": True}),
    ("wrong-type", {**PAGE, "type": "blogpost"}),
    ("missing-type", without("type")),
    ("non-string-title", {**PAGE, "title": 5}),
    ("missing-title", without("title")),
    ("missing-body", without("body")),
    ("body-not-object", {**PAGE, "body": []}),
    ("missing-storage", {**PAGE, "body": {}}),
    ("storage-not-object", {**PAGE, "body": {"storage": []}}),
    ("missing-value", {**PAGE, "body": {"storage": {}}}),
    ("value-not-string", {**PAGE, "body": {"storage": {"value": 5}}}),
]


def run_page(
    argument: str,
    *options: str,
    status: int = 200,
    payload: object | None = None,
    token: str | None = TOKEN,
    token_flag: bool = True,
    explicit_base_url: bool = False,
    confluence_env_path: str = "/confluence/",
) -> tuple[
    subprocess.CompletedProcess[str],
    list[tuple[str, str, dict[str, list[str]], str | None]],
]:
    script = shutil.which("atlawire")
    assert script is not None, "Install AtlaWire before running its CLI E2E suite."
    seen: list[tuple[str, str, dict[str, list[str]], str | None]] = []
    response = json.dumps(PAGE if payload is None else payload).encode()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            url = urlsplit(self.path)
            seen.append(
                (
                    self.command,
                    url.path,
                    parse_qs(url.query, keep_blank_values=True),
                    self.headers.get("Authorization"),
                )
            )
            self.send_response(status)
            if 300 <= status < 400:
                self.send_header("Location", "/unexpected")
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)

    with HTTPServer(("127.0.0.1", 0), Handler) as server:
        worker = Thread(target=server.serve_forever, args=(0.05,), daemon=True)
        worker.start()
        try:
            base_url = f"http://127.0.0.1:{server.server_port}/confluence/"
            origin = f"http://127.0.0.1:{server.server_port}"
            env = {
                **os.environ,
                "ATLAWIRE_CONFLUENCE_URL": f"{origin}{confluence_env_path}",
                "ATLAWIRE_CONFLUENCE_TOKEN": TOKEN,
                "ATLAWIRE_JIRA_URL": f"{origin}/wrong-jira/",
                "ATLAWIRE_JIRA_TOKEN": "wrong-product-fixture",
                "ATLAWIRE_BITBUCKET_URL": f"{origin}/wrong-bitbucket/",
                "ATLAWIRE_BITBUCKET_TOKEN": "wrong-product-fixture",
            }
            if token is None:
                env.pop("ATLAWIRE_CONFLUENCE_TOKEN", None)
            command = [script, "page", argument]
            if explicit_base_url:
                command.extend(["--base-url", base_url])
            command.append("--allow-http-loopback")
            if token_flag:
                command.append("--token-from-env")
            command.extend(options)
            result = subprocess.run(
                command,
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


def assert_single_request(
    seen: list[tuple[str, str, dict[str, list[str]], str | None]],
) -> None:
    assert seen == [("GET", PATH, EXPAND, f"Bearer {TOKEN}")]


def test_page_by_id_returns_full_json_from_the_configured_instance() -> None:
    result, seen = run_page("123")

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == PAGE
    assert_single_request(seen)


def test_markdown_is_opt_in_and_renders_storage_without_extra_requests() -> None:
    payload = markdown_page()

    default, default_seen = run_page("123", payload=payload)
    markdown, markdown_seen = run_page("123", "--markdown", payload=payload)

    assert default.returncode == 0, default.stderr
    assert default.stdout == json.dumps(payload) + "\n"
    assert_single_request(default_seen)
    assert markdown.returncode == 0, markdown.stderr
    assert markdown.stderr == ""
    assert_single_request(markdown_seen)

    rendered = markdown.stdout
    assert rendered.startswith("# Résumé # injected\n")
    assert "\n# injected" not in rendered
    assert "## Overview" in rendered
    assert "**Bold**" in rendered
    assert "*italic*" in rendered
    assert "`inline`" in rendered
    assert "- alpha\n- beta" in rendered
    assert "| Key | Value |" in rendered
    assert "| one | 1 |" in rendered
    assert (
        "````python\ndef f():\n"
        '    return "```"\n'
        "\n"
        "# blank line above\n"
        "\n"
        'print("done")\n'
        "````"
    ) in rendered
    assert "[Unsupported macro: mystery]" in rendered
    assert "Readable *rich* body" in rendered
    assert "PARAM-SENTINEL" not in rendered
    assert "label" in rendered
    assert "diagram alt" in rendered
    assert "Other Page" in rendered
    assert "attachment alt" in rendered
    assert "https://evil.invalid" not in rendered
    assert "](https" not in rendered
    assert "![" not in rendered
    assert rendered.endswith("\n")
    assert not rendered.endswith("\n\n")


def test_empty_page_markdown_succeeds_with_only_the_heading() -> None:
    payload = {**PAGE, "body": {"storage": {"value": ""}}}

    result, seen = run_page("123", "--markdown", payload=payload)

    assert result.returncode == 0, result.stderr
    assert result.stdout == "# Résumé\n"
    assert result.stderr == ""
    assert_single_request(seen)


def test_pasted_page_link_supplies_only_the_id_to_the_request() -> None:
    argument = (
        "https://elsewhere.example.invalid/wiki/pages/viewpage.action"
        "?spaceKey=OTHER&pageId=123&x=1#fragment"
    )

    result, seen = run_page(argument)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == PAGE
    assert_single_request(seen)


def test_percent_encoded_ascii_digits_still_resolve_to_the_id() -> None:
    argument = (
        "https://elsewhere.example.invalid/pages/viewpage.action?pageId=%31%32%33"
    )

    result, seen = run_page(argument)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == PAGE
    assert_single_request(seen)


def test_base_url_option_overrides_the_environment_url() -> None:
    result, seen = run_page(
        "123",
        explicit_base_url=True,
        confluence_env_path="/wrong-confluence/",
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == PAGE
    assert_single_request(seen)


def test_integer_id_in_response_is_accepted_without_mutating_the_payload() -> None:
    payload = {**PAGE, "id": 123}

    result, seen = run_page("123", payload=payload)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == payload
    assert json.loads(result.stdout)["id"] == 123
    assert_single_request(seen)


def test_empty_storage_value_is_a_valid_page() -> None:
    payload = {**PAGE, "body": {"storage": {"value": ""}}}

    result, seen = run_page("123", payload=payload)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == payload
    assert_single_request(seen)


def test_missing_confluence_token_does_not_use_other_product_tokens() -> None:
    result, seen = run_page("123", token=None)

    assert result.returncode == 1
    assert result.stdout == ""
    assert "token" in result.stderr
    assert seen == []


def test_token_from_env_must_be_selected_explicitly() -> None:
    result, seen = run_page("123", token_flag=False)

    assert result.returncode == 2
    assert result.stdout == ""
    assert "Select --token-from-env" in result.stderr
    assert seen == []


@pytest.mark.parametrize(
    ("status", "expected_error"),
    [(403, "HTTP 403"), (404, "HTTP 404")],
)
def test_http_errors_publish_nothing_and_echo_no_request_details(
    status: int, expected_error: str
) -> None:
    result, seen = run_page("123", status=status, payload={"message": TOKEN})

    assert result.returncode == 1
    assert result.stdout == ""
    assert expected_error in result.stderr
    assert TOKEN not in result.stderr
    assert PATH not in result.stderr
    assert_single_request(seen)


def test_markdown_http_failure_publishes_nothing_and_echoes_no_response_body() -> None:
    result, seen = run_page(
        "123",
        "--markdown",
        status=500,
        payload={"message": "RESPONSE-SENTINEL", "token": TOKEN},
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "HTTP 500" in result.stderr
    assert "RESPONSE-SENTINEL" not in result.stderr
    assert TOKEN not in result.stderr
    assert PATH not in result.stderr
    assert_single_request(seen)


def test_pasted_link_is_not_echoed_on_http_error() -> None:
    argument = (
        "https://elsewhere.example.invalid/pages/viewpage.action"
        "?pageId=123&secret=fixture-link-marker"
    )

    result, seen = run_page(argument, status=404)

    assert result.returncode == 1
    assert result.stdout == ""
    assert "fixture-link-marker" not in result.stderr
    assert "elsewhere.example.invalid" not in result.stderr
    assert_single_request(seen)


def test_redirect_is_refused_and_not_followed() -> None:
    result, seen = run_page("123", status=302)

    assert result.returncode == 1
    assert result.stdout == ""
    assert "redirect refused" in result.stderr
    assert PATH not in result.stderr
    assert_single_request(seen)


@pytest.mark.parametrize(
    ("case", "payload"),
    MALFORMED_PAGES,
    ids=[case for case, _ in MALFORMED_PAGES],
)
def test_invalid_page_shape_publishes_nothing(
    case: str, payload: dict[str, object]
) -> None:
    result, seen = run_page("123", payload=payload)

    assert result.returncode == 1, case
    assert result.stdout == ""
    assert "Confluence page" in result.stderr
    assert "LEAK-SENTINEL" not in result.stderr
    assert_single_request(seen)


@pytest.mark.parametrize(
    "argument",
    [
        "0",
        "007",
        "abc",
        "/pages/123",
        "https://wiki.example.invalid/pages/viewpage.action",
        "https://wiki.example.invalid/pages/viewpage.action?pageId=123&pageId=124",
        "https://wiki.example.invalid/pages/viewpage.action?pageId=0",
        "https://wiki.example.invalid/pages/viewpage.action?pageId=",
        pytest.param(
            " https://wiki.example.invalid/pages/viewpage.action?pageId=123",
            id="leading-space",
        ),
        pytest.param(
            "https://wiki.example.invalid/pages/viewpage.action?pageId=12\n3",
            id="embedded-newline",
        ),
        pytest.param(
            "https://wiki.example.invalid/pages/viewpage.action?pageId=12\t3",
            id="embedded-tab",
        ),
    ],
)
def test_invalid_or_ambiguous_ids_send_no_request(argument: str) -> None:
    result, seen = run_page(argument)

    assert result.returncode == 1
    assert result.stdout == ""
    assert "pageId" in result.stderr
    assert seen == []
