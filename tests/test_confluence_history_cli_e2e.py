"""Installed-CLI loopback checks for Confluence page history and versions.

Every response comes from a synthetic loopback server, every credential is a
fixture, and ``BBK_CREDENTIALS`` points at a path that must not exist. No test
contacts a real instance or reads a real credential store.

These tests anticipate the not-yet-wired JSON commands ``page-history PAGE`` and
``page-version PAGE VERSION``.
"""

import json
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

TOKEN = "fixture-confluence-history-only"
CONTEXT = "/confluence"
PAGE_ID = "4242"
CONTENT_PATH = f"{CONTEXT}/rest/api/content/{PAGE_ID}"
HISTORY_PATH = f"{CONTENT_PATH}/history"
PASTED = (
    "https://elsewhere.example.invalid/wiki/pages/viewpage.action"
    "?spaceKey=OTHER&pageId=4242#fragment"
)
SENTINEL = "CONFLUENCE-HISTORY-CLI-SENTINEL"
MISSING_BBK_CREDENTIALS = str(
    Path(__file__).with_name("bbk-credentials-missing-for-history-cli.json")
)

type PayloadFactory = Callable[[int], dict[str, object]]
type Case = tuple[str, str, PayloadFactory, str | None, dict[str, list[str]]]

HISTORY_QUERY: dict[str, list[str]] = {}
VERSION_QUERY: dict[str, list[str]] = {
    "status": ["historical"],
    "version": ["7"],
    "expand": ["body.storage,version"],
}


def history_payload(intruder_port: int) -> dict[str, object]:
    """A history object with more metadata than the client needs."""
    return {
        "latest": True,
        "createdDate": "2020-01-01T00:00:00.000Z",
        "createdBy": {"displayName": "Ada", "username": "ada"},
        "previousVersion": {"number": 6, "message": "previous"},
        "nextVersion": {"number": 8, "message": "next"},
        "lastUpdated": {"number": 7, "message": "current", "minorEdit": False},
        "_links": {
            "self": "https://elsewhere.example.invalid/history",
            "next": f"http://127.0.0.1:{intruder_port}/stolen",
        },
        "_expandable": {"contributors": ""},
        "unknown": [None, True, 2.5],
    }


def version_payload(
    intruder_port: int,
    *,
    returned_id: str = PAGE_ID,
    returned_version: int = 7,
) -> dict[str, object]:
    """A historical page version with storage body and unknown fields."""
    return {
        "id": returned_id,
        "type": "page",
        "status": "historical",
        "title": "Résumé (v7)",
        "version": {
            "number": returned_version,
            "message": "snapshot",
            "minorEdit": False,
            "by": {"displayName": "Ada"},
        },
        "body": {
            "storage": {"value": "<p>Old body</p>", "representation": "storage"}
        },
        "space": {"key": "DEMO", "name": "Demo"},
        "unknown": {"kept": [1, None]},
        "_links": {
            "self": "https://elsewhere.example.invalid/content/4242",
            "next": f"http://127.0.0.1:{intruder_port}/stolen",
        },
    }


CASES: list[Case] = [
    ("page-history", HISTORY_PATH, history_payload, None, HISTORY_QUERY),
    ("page-version", CONTENT_PATH, version_payload, "7", VERSION_QUERY),
]


def run_case(
    command: str,
    path: str,
    payload_factory: PayloadFactory,
    *,
    page_argument: str = PAGE_ID,
    version_argument: str | None = None,
    status: int = 200,
    redirect: bool = False,
    token: str | None = TOKEN,
) -> tuple[
    subprocess.CompletedProcess[str],
    list[Request],
    list[Request],
    object,
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
        response: object = (
            payload_factory(intruder_server.server_port)
            if status == 200
            else {"message": SENTINEL}
        )

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: object) -> None:
                pass

            def do_GET(self) -> None:
                record = request_record(self)
                seen.append(record)
                if record[1] != path or record[3] != f"Bearer {TOKEN}":
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
            if token is None:
                environment.pop("ATLAWIRE_CONFLUENCE_TOKEN", None)
            arguments = [command, page_argument]
            if version_argument is not None:
                arguments.append(version_argument)
            arguments.extend(["--allow-http-loopback", "--token-from-env"])
            result = run_installed(arguments, environment)
    return result, seen, intruder, response


def expected_request(
    path: str, query: dict[str, list[str]]
) -> list[Request]:
    return [("GET", path, query, f"Bearer {TOKEN}")]


def test_the_bbk_credentials_override_is_a_missing_synthetic_path() -> None:
    assert "missing-for-history-cli" in MISSING_BBK_CREDENTIALS
    assert not Path(MISSING_BBK_CREDENTIALS).exists()


def test_installed_page_history_prints_the_raw_object() -> None:
    result, seen, intruder, payload = run_case(
        "page-history", HISTORY_PATH, history_payload
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == payload
    raw = json.loads(result.stdout)
    assert raw["previousVersion"] == {"number": 6, "message": "previous"}
    assert raw["lastUpdated"] == {
        "number": 7,
        "message": "current",
        "minorEdit": False,
    }
    assert raw["unknown"] == [None, True, 2.5]
    assert seen == expected_request(HISTORY_PATH, HISTORY_QUERY)
    assert intruder == []


def test_installed_page_version_prints_raw_historical_version() -> None:
    result, seen, intruder, payload = run_case(
        "page-version",
        CONTENT_PATH,
        version_payload,
        version_argument="7",
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == payload
    raw = json.loads(result.stdout)
    assert raw["version"]["number"] == 7
    assert raw["body"]["storage"]["value"] == "<p>Old body</p>"
    assert raw["unknown"] == {"kept": [1, None]}
    assert seen == expected_request(CONTENT_PATH, VERSION_QUERY)
    assert intruder == []


@pytest.mark.parametrize(
    ("command", "path", "payload_factory", "version_argument", "query"),
    CASES,
    ids=[case[0] for case in CASES],
)
def test_installed_history_command_uses_only_page_id_from_a_pasted_link(
    command: str,
    path: str,
    payload_factory: PayloadFactory,
    version_argument: str | None,
    query: dict[str, list[str]],
) -> None:
    result, seen, intruder, payload = run_case(
        command,
        path,
        payload_factory,
        page_argument=PASTED,
        version_argument=version_argument,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == payload
    assert seen == expected_request(path, query)
    assert intruder == []


@pytest.mark.parametrize(
    ("command", "path", "payload_factory", "version_argument", "query"),
    CASES,
    ids=[case[0] for case in CASES],
)
@pytest.mark.parametrize(
    ("status", "message"),
    [
        (401, "HTTP 401: authentication rejected."),
        (403, "HTTP 403: access denied."),
        (404, "HTTP 404: request failed."),
    ],
)
def test_installed_history_command_maps_http_errors_without_output(
    command: str,
    path: str,
    payload_factory: PayloadFactory,
    version_argument: str | None,
    query: dict[str, list[str]],
    status: int,
    message: str,
) -> None:
    result, seen, intruder, _ = run_case(
        command,
        path,
        payload_factory,
        version_argument=version_argument,
        status=status,
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert message in result.stderr
    assert SENTINEL not in result.stderr
    assert TOKEN not in result.stderr
    assert path not in result.stderr
    assert "Traceback" not in result.stderr
    assert seen == expected_request(path, query)
    assert intruder == []


@pytest.mark.parametrize(
    ("command", "path", "payload_factory", "version_argument", "query"),
    CASES,
    ids=[case[0] for case in CASES],
)
def test_installed_history_command_refuses_a_redirect_without_following(
    command: str,
    path: str,
    payload_factory: PayloadFactory,
    version_argument: str | None,
    query: dict[str, list[str]],
) -> None:
    result, seen, intruder, _ = run_case(
        command,
        path,
        payload_factory,
        version_argument=version_argument,
        redirect=True,
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "redirect refused" in result.stderr
    assert SENTINEL not in result.stderr
    assert TOKEN not in result.stderr
    assert seen == expected_request(path, query)
    assert intruder == []


@pytest.mark.parametrize(
    ("command", "path", "payload_factory", "version_argument", "query"),
    CASES,
    ids=[case[0] for case in CASES],
)
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
def test_installed_history_command_rejects_invalid_page_ids_without_a_request(
    command: str,
    path: str,
    payload_factory: PayloadFactory,
    version_argument: str | None,
    query: dict[str, list[str]],
    page_argument: str,
) -> None:
    result, seen, intruder, _ = run_case(
        command,
        path,
        payload_factory,
        page_argument=page_argument,
        version_argument=version_argument,
    )

    assert result.returncode != 0
    assert result.stdout == ""
    assert TOKEN not in result.stderr
    assert "Traceback" not in result.stderr
    assert seen == []
    assert intruder == []


@pytest.mark.parametrize(
    "version_argument",
    ["0", "-1", "abc", "1.5"],
    ids=["zero", "negative", "non-numeric", "float"],
)
def test_installed_page_version_rejects_invalid_versions_without_a_request(
    version_argument: str,
) -> None:
    result, seen, intruder, _ = run_case(
        "page-version",
        CONTENT_PATH,
        version_payload,
        version_argument=version_argument,
    )

    assert result.returncode != 0
    assert result.stdout == ""
    assert TOKEN not in result.stderr
    assert "Traceback" not in result.stderr
    assert seen == []
    assert intruder == []


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (
            lambda port: version_payload(port, returned_id="4243"),
            "Confluence page",
        ),
        (
            lambda port: version_payload(port, returned_version=8),
            "version",
        ),
        (
            lambda port: {**version_payload(port), "body": {}},
            "Confluence page",
        ),
    ],
    ids=["mismatched-id", "mismatched-version", "missing-storage-body"],
)
def test_installed_page_version_rejects_mismatched_or_incomplete_response(
    factory: PayloadFactory, message: str
) -> None:
    result, seen, intruder, _ = run_case(
        "page-version",
        CONTENT_PATH,
        factory,
        version_argument="7",
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert message in result.stderr
    assert SENTINEL not in result.stderr
    assert TOKEN not in result.stderr
    assert seen == expected_request(CONTENT_PATH, VERSION_QUERY)
    assert intruder == []
