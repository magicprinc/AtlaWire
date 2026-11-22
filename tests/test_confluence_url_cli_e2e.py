"""Installed-CLI loopback checks for Confluence page web URLs.

Every response comes from a synthetic loopback server, every credential is a
fixture, and ``BBK_CREDENTIALS`` points at a path that must not exist. No test
contacts a real instance or reads a real credential store.

These tests anticipate the not-yet-wired ``page-url PAGE`` command.
"""

import subprocess
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler
from pathlib import Path

import pytest

from tests._loopback import (
    Request,
    confluence_environment,
    request_record,
    run_installed,
    send_bytes,
    send_json,
    serving,
)

TOKEN = "fixture-confluence-url-only"
CONTEXT = "/confluence"
PAGE_ID = "4242"
CONTENT_PATH = f"{CONTEXT}/rest/api/content/{PAGE_ID}"
PASTED = (
    "https://elsewhere.example.invalid/wiki/pages/viewpage.action"
    "?spaceKey=OTHER&pageId=4242#fragment"
)
SENTINEL = "CONFLUENCE-URL-CLI-SENTINEL"
MISSING_BBK_CREDENTIALS = str(
    Path(__file__).with_name("bbk-credentials-missing-for-url-cli.json")
)
EXPAND_QUERY: dict[str, list[str]] = {
    "expand": ["body.storage,version,space,ancestors"]
}

type PayloadFactory = Callable[[int], dict[str, object]]


def page_payload(webui: object = "/display/DEMO/Page") -> dict[str, object]:
    return {
        "id": PAGE_ID,
        "type": "page",
        "status": "current",
        "title": "Résumé",
        "version": {"number": 3},
        "body": {
            "storage": {"value": "<p>Body</p>", "representation": "storage"}
        },
        "_links": {
            "webui": webui,
            "self": "https://elsewhere.example.invalid/content/4242",
        },
    }


def page_without_links() -> dict[str, object]:
    value = page_payload()
    del value["_links"]
    return value


def run_url(
    *,
    page_argument: str = PAGE_ID,
    payload: dict[str, object] | None = None,
    payload_factory: PayloadFactory | None = None,
    status: int = 200,
    redirect: bool = False,
) -> tuple[
    subprocess.CompletedProcess[str],
    list[Request],
    list[Request],
    object,
    str,
]:
    """Run one installed command against one synthetic loopback response."""
    seen: list[Request] = []
    intruder: list[Request] = []

    class Intruder(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            intruder.append(request_record(self))
            send_json(self, 200, {"message": SENTINEL})

    with serving(Intruder) as intruder_server:
        response: object
        if status != 200:
            response = {"message": SENTINEL}
        elif payload_factory is not None:
            response = payload_factory(intruder_server.server_port)
        else:
            response = payload if payload is not None else page_payload()

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: object) -> None:
                pass

            def do_GET(self) -> None:
                record = request_record(self)
                seen.append(record)
                if record[1] != CONTENT_PATH or record[3] != f"Bearer {TOKEN}":
                    send_json(self, 404, {"message": SENTINEL})
                    return
                if redirect:
                    send_bytes(
                        self,
                        302,
                        b"",
                        content_type=None,
                        extra_headers={
                            "Location": (
                                f"http://127.0.0.1:{intruder_server.server_port}"
                                "/stolen"
                            )
                        },
                    )
                    return
                send_json(self, status, response)

        with serving(Handler) as server:
            origin = f"http://127.0.0.1:{server.server_port}"
            environment = confluence_environment(
                origin, context=CONTEXT, token=TOKEN
            )
            environment["BBK_CREDENTIALS"] = MISSING_BBK_CREDENTIALS
            result = run_installed(
                [
                    "page-url",
                    page_argument,
                    "--allow-http-loopback",
                    "--token-from-env",
                ],
                environment,
            )
    return result, seen, intruder, response, f"{origin}{CONTEXT}"


def expected_request() -> list[Request]:
    return [
        ("GET", CONTENT_PATH, EXPAND_QUERY, f"Bearer {TOKEN}")
    ]


def test_the_bbk_credentials_override_is_a_missing_synthetic_path() -> None:
    assert "missing-for-url-cli" in MISSING_BBK_CREDENTIALS
    assert not Path(MISSING_BBK_CREDENTIALS).exists()


def test_installed_page_url_prints_context_plus_source_webui() -> None:
    result, seen, intruder, _, base_url = run_url(
        payload=page_payload("/display/DEMO/Résumé?x=1#section")
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout == f"{base_url}/display/DEMO/Résumé?x=1#section\n"
    assert TOKEN not in result.stdout
    assert seen == expected_request()
    assert intruder == []


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(page_without_links(), id="no-links"),
        pytest.param({**page_payload(), "_links": None}, id="null-links"),
        pytest.param({**page_payload(), "_links": []}, id="array-links"),
        pytest.param({**page_payload(), "_links": {}}, id="empty-links"),
        pytest.param(
            {**page_payload(), "_links": {"webui": None}},
            id="null-webui",
        ),
        pytest.param(
            {**page_payload(), "_links": {"webui": ""}},
            id="empty-webui",
        ),
        pytest.param(
            {**page_payload(), "_links": {"webui": 7}},
            id="integer-webui",
        ),
    ],
)
def test_installed_page_url_uses_the_deterministic_fallback(
    payload: dict[str, object],
) -> None:
    result, seen, intruder, _, base_url = run_url(payload=payload)

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout == (
        f"{base_url}/pages/viewpage.action?pageId={PAGE_ID}\n"
    )
    assert seen == expected_request()
    assert intruder == []


@pytest.mark.parametrize(
    "webui",
    [
        pytest.param("https://evil.invalid/display", id="absolute-https"),
        pytest.param("//evil.invalid/display", id="scheme-relative"),
        pytest.param("/\\evil.invalid/display", id="backslash"),
        pytest.param("/%5c%5cevil.invalid/display", id="encoded-backslash"),
        pytest.param("/display/../../admin", id="literal-traversal"),
        pytest.param("/display/%2e%2e/%2e%2e/admin", id="encoded-traversal"),
        pytest.param(
            "/display/%252e%252e/admin", id="double-encoded-traversal"
        ),
        pytest.param("/display/..;/admin", id="semicolon-traversal"),
        pytest.param(
            "/display/%2e%2e%3b/admin", id="encoded-semicolon-traversal"
        ),
        pytest.param("/display/page\x00", id="null-control"),
        pytest.param("/display/page\n", id="newline-control"),
        pytest.param("/display/%0d%0a", id="encoded-crlf"),
        pytest.param("javascript:alert(1)", id="javascript-scheme"),
        pytest.param("display/page", id="no-leading-slash"),
    ],
)
def test_installed_page_url_never_uses_a_suspicious_webui(webui: str) -> None:
    result, seen, intruder, _, base_url = run_url(
        payload=page_payload(webui)
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout == (
        f"{base_url}/pages/viewpage.action?pageId={PAGE_ID}\n"
    )
    assert "evil.invalid" not in result.stdout
    assert seen == expected_request()
    assert intruder == []


def test_installed_page_url_does_not_follow_an_absolute_webui() -> None:
    def payload(port: int) -> dict[str, object]:
        return page_payload(f"http://127.0.0.1:{port}/stolen")

    result, seen, intruder, _, base_url = run_url(
        payload_factory=payload
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == (
        f"{base_url}/pages/viewpage.action?pageId={PAGE_ID}\n"
    )
    assert seen == expected_request()
    assert intruder == []


def test_installed_page_url_uses_only_the_id_from_a_pasted_link() -> None:
    result, seen, intruder, _, base_url = run_url(
        page_argument=PASTED,
        payload=page_payload("/display/DEMO/Page"),
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout == f"{base_url}/display/DEMO/Page\n"
    assert "elsewhere.example.invalid" not in result.stdout
    assert seen == expected_request()
    assert intruder == []


@pytest.mark.parametrize(
    ("status", "message"),
    [
        (401, "HTTP 401: authentication rejected."),
        (403, "HTTP 403: access denied."),
        (404, "HTTP 404: request failed."),
    ],
)
def test_installed_page_url_maps_http_errors_without_output(
    status: int, message: str
) -> None:
    result, seen, intruder, _, _ = run_url(status=status)

    assert result.returncode == 1
    assert result.stdout == ""
    assert message in result.stderr
    assert SENTINEL not in result.stderr
    assert TOKEN not in result.stderr
    assert CONTENT_PATH not in result.stderr
    assert "Traceback" not in result.stderr
    assert seen == expected_request()
    assert intruder == []


def test_installed_page_url_refuses_a_redirect_without_following() -> None:
    result, seen, intruder, _, _ = run_url(redirect=True)

    assert result.returncode == 1
    assert result.stdout == ""
    assert "redirect refused" in result.stderr
    assert SENTINEL not in result.stderr
    assert TOKEN not in result.stderr
    assert seen == expected_request()
    assert intruder == []


@pytest.mark.parametrize(
    "page_argument",
    [
        "0",
        "007",
        "abc",
        "https://elsewhere.example.invalid/pages/viewpage.action"
        "?pageId=4242&pageId=4243",
    ],
    ids=["zero", "padded", "non-numeric", "conflicting-page-ids"],
)
def test_installed_page_url_rejects_invalid_page_ids_without_a_request(
    page_argument: str,
) -> None:
    result, seen, intruder, _, _ = run_url(page_argument=page_argument)

    assert result.returncode != 0
    assert result.stdout == ""
    assert TOKEN not in result.stderr
    assert "Traceback" not in result.stderr
    assert seen == []
    assert intruder == []


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (
            {**page_payload(), "id": "9999"},
            "Confluence page",
        ),
        (
            {**page_payload(), "body": {}},
            "Confluence page",
        ),
    ],
    ids=["mismatched-id", "missing-storage-body"],
)
def test_installed_page_url_publishes_nothing_for_an_invalid_page(
    payload: dict[str, object], message: str
) -> None:
    result, seen, intruder, _, _ = run_url(payload=payload)

    assert result.returncode == 1
    assert result.stdout == ""
    assert message in result.stderr
    assert SENTINEL not in result.stderr
    assert TOKEN not in result.stderr
    assert seen == expected_request()
    assert intruder == []
