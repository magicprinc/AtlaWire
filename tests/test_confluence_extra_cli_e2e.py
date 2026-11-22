"""Installed-CLI loopback checks for Confluence page attachments, comments, labels.

Every response comes from a synthetic loopback server, every credential is a
fixture, and ``BBK_CREDENTIALS`` points at a path that must not exist. No test
contacts a real instance or reads a real credential store.

These tests anticipate the not-yet-wired commands ``page-attachments``,
``page-comments``, and ``page-labels``, which print one raw JSON object. The
comments command also accepts ``--root-only``.
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

TOKEN = "fixture-confluence-extra-only"
CONTEXT = "/confluence"
PAGE_ID = "4242"
CONTENT_PATH = f"{CONTEXT}/rest/api/content/{PAGE_ID}"
ATTACHMENT_PATH = f"{CONTENT_PATH}/child/attachment"
COMMENT_PATH = f"{CONTENT_PATH}/child/comment"
LABEL_PATH = f"{CONTENT_PATH}/label"
PASTED = (
    "https://elsewhere.example.invalid/wiki/pages/viewpage.action"
    "?spaceKey=OTHER&pageId=4242#fragment"
)
SENTINEL = "CONFLUENCE-EXTRA-CLI-SENTINEL"
MISSING_BBK_CREDENTIALS = str(
    Path(__file__).with_name("bbk-credentials-missing-for-extra-cli.json")
)

type PayloadFactory = Callable[[int], dict[str, object]]


def attachments_payload(intruder_port: int) -> dict[str, object]:
    """A flat attachment page with metadata the adapter must not project."""
    return {
        "results": [
            {
                "id": "att1",
                "type": "attachment",
                "status": "current",
                "title": "Résumé.pdf",
                "metadata": {"mediaType": "application/pdf", "comment": "fixture"},
                "extensions": {"unknown": [None, True, 2.5]},
                "_links": {
                    "self": "https://elsewhere.example.invalid/att1",
                    "webui": "/display/DEMO/Attach",
                },
            }
        ],
        "start": 5,
        "limit": 2,
        "size": 1,
        "totalSize": 6,
        "_links": {
            "base": "https://elsewhere.example.invalid",
            "next": (
                f"http://127.0.0.1:{intruder_port}"
                f"{ATTACHMENT_PATH}?start=6&limit=2"
            ),
        },
    }


def comments_payload(intruder_port: int) -> dict[str, object]:
    """The 6.6.0 content-type-keyed map, not a flat paged object."""
    return {
        "page": {
            "results": [
                {
                    "id": "comment1",
                    "type": "comment",
                    "title": "Re: Résumé",
                    "extensions": {"inlineProperties": {"originalSelection": "x"}},
                    "body": {
                        "storage": {
                            "value": "<p>A reply body</p>",
                            "representation": "storage",
                        }
                    },
                    "_links": {"webui": "/display/DEMO/Comment"},
                }
            ],
            "size": 1,
            "start": 6,
            "limit": 2,
            "_links": {
                "next": (
                    f"http://127.0.0.1:{intruder_port}"
                    f"{COMMENT_PATH}?start=7&limit=2"
                ),
            },
        },
        "unknownTopLevel": {"kept": [1, None]},
    }


def labels_payload(intruder_port: int) -> dict[str, object]:
    """A label page plus undocumented fields; no schema is assumed."""
    return {
        "results": [
            {
                "prefix": "global",
                "name": "docs",
                "id": "label1",
                "_links": {"self": "https://elsewhere.example.invalid/label1"},
            }
        ],
        "start": 3,
        "limit": 2,
        "size": 1,
        "totalSize": 4,
        "nextStart": 5,
        "_links": {
            "next": (
                f"http://127.0.0.1:{intruder_port}"
                f"{LABEL_PATH}?start=5&limit=2"
            ),
        },
    }


CASES: list[tuple[str, str, PayloadFactory, int, int, dict[str, str]]] = [
    ("page-attachments", ATTACHMENT_PATH, attachments_payload, 5, 2, {}),
    (
        "page-comments",
        COMMENT_PATH,
        comments_payload,
        6,
        2,
        {"expand": "body.storage", "depth": "all"},
    ),
    ("page-labels", LABEL_PATH, labels_payload, 3, 2, {}),
]


def run_page(
    command: str,
    path: str,
    *,
    payload_factory: PayloadFactory | None = None,
    status: int = 200,
    redirect: bool = False,
    page_argument: str = PAGE_ID,
    start: int = 5,
    limit: int = 2,
    options: tuple[str, ...] | None = None,
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
            if status == 200 and payload_factory is not None
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
            arguments = [
                command,
                page_argument,
                "--allow-http-loopback",
                "--token-from-env",
            ]
            if options is None:
                arguments.extend(["--start", str(start), "--limit", str(limit)])
            else:
                arguments.extend(options)
            result = run_installed(arguments, environment)
    return result, seen, intruder, response


def expected_request(
    path: str, start: int, limit: int, fixed_params: dict[str, str]
) -> list[Request]:
    query = {**fixed_params, "start": str(start), "limit": str(limit)}
    return [
        (
            "GET",
            path,
            {key: [value] for key, value in query.items()},
            f"Bearer {TOKEN}",
        )
    ]


def test_the_bbk_credentials_override_is_a_missing_synthetic_path() -> None:
    assert "missing-for-extra-cli" in MISSING_BBK_CREDENTIALS
    assert not Path(MISSING_BBK_CREDENTIALS).exists()


def test_installed_page_attachments_prints_raw_metadata_for_one_page() -> None:
    result, seen, intruder, payload = run_page(
        "page-attachments",
        ATTACHMENT_PATH,
        payload_factory=attachments_payload,
        start=5,
        limit=2,
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == payload
    raw = json.loads(result.stdout)
    assert raw["start"] == 5
    assert raw["limit"] == 2
    assert raw["size"] == 1
    assert raw["totalSize"] == 6
    assert raw["results"][0]["extensions"] == {"unknown": [None, True, 2.5]}
    assert seen == expected_request(ATTACHMENT_PATH, 5, 2, {})
    assert intruder == []


def test_installed_page_comments_preserves_the_content_type_map() -> None:
    result, seen, intruder, payload = run_page(
        "page-comments",
        COMMENT_PATH,
        payload_factory=comments_payload,
        start=6,
        limit=2,
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == payload
    raw = json.loads(result.stdout)
    assert "results" not in raw
    assert raw["page"]["size"] == 1
    assert raw["page"]["_links"]["next"].endswith(
        f"{COMMENT_PATH}?start=7&limit=2"
    )
    assert seen == expected_request(
        COMMENT_PATH, 6, 2, {"expand": "body.storage", "depth": "all"}
    )
    assert intruder == []


def test_installed_page_comments_root_only_omits_depth_and_keeps_expansion() -> None:
    result, seen, intruder, payload = run_page(
        "page-comments",
        COMMENT_PATH,
        payload_factory=comments_payload,
        options=("--start", "6", "--limit", "2", "--root-only"),
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == payload
    raw = json.loads(result.stdout)
    assert raw["page"]["results"][0]["body"]["storage"]["value"] == (
        "<p>A reply body</p>"
    )
    # Root-only relies on the server's documented default; no empty depth value
    # is sent, and the body expansion remains requested.
    assert seen == expected_request(
        COMMENT_PATH, 6, 2, {"expand": "body.storage"}
    )
    assert intruder == []


def test_installed_page_labels_preserves_undocumented_fields() -> None:
    result, seen, intruder, payload = run_page(
        "page-labels",
        LABEL_PATH,
        payload_factory=labels_payload,
        start=3,
        limit=2,
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == payload
    raw = json.loads(result.stdout)
    assert raw["nextStart"] == 5
    assert raw["results"][0] == {
        "prefix": "global",
        "name": "docs",
        "id": "label1",
        "_links": {"self": "https://elsewhere.example.invalid/label1"},
    }
    assert seen == expected_request(LABEL_PATH, 3, 2, {})
    assert intruder == []


def test_installed_page_command_uses_only_the_page_id_from_a_pasted_link() -> None:
    result, seen, intruder, payload = run_page(
        "page-attachments",
        ATTACHMENT_PATH,
        payload_factory=attachments_payload,
        page_argument=PASTED,
        start=5,
        limit=2,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == payload
    assert seen == expected_request(ATTACHMENT_PATH, 5, 2, {})
    assert intruder == []


@pytest.mark.parametrize(
    ("command", "path", "payload_factory", "start", "limit", "fixed_params"),
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
def test_installed_page_command_maps_http_errors_without_output(
    command: str,
    path: str,
    payload_factory: PayloadFactory,
    start: int,
    limit: int,
    fixed_params: dict[str, str],
    status: int,
    message: str,
) -> None:
    result, seen, intruder, _ = run_page(
        command,
        path,
        payload_factory=payload_factory,
        status=status,
        start=start,
        limit=limit,
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert message in result.stderr
    assert SENTINEL not in result.stderr
    assert TOKEN not in result.stderr
    assert path not in result.stderr
    assert "Traceback" not in result.stderr
    assert seen == expected_request(path, start, limit, fixed_params)
    assert intruder == []


@pytest.mark.parametrize(
    ("command", "path", "payload_factory", "start", "limit", "fixed_params"),
    CASES,
    ids=[case[0] for case in CASES],
)
def test_installed_page_command_refuses_a_redirect_without_following_it(
    command: str,
    path: str,
    payload_factory: PayloadFactory,
    start: int,
    limit: int,
    fixed_params: dict[str, str],
) -> None:
    result, seen, intruder, _ = run_page(
        command,
        path,
        payload_factory=payload_factory,
        redirect=True,
        start=start,
        limit=limit,
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "redirect refused" in result.stderr
    assert SENTINEL not in result.stderr
    assert TOKEN not in result.stderr
    assert seen == expected_request(path, start, limit, fixed_params)
    assert intruder == []


@pytest.mark.parametrize(
    ("command", "path", "payload_factory", "start", "limit", "fixed_params"),
    CASES,
    ids=[case[0] for case in CASES],
)
@pytest.mark.parametrize(
    "options",
    [
        ("--start", "-1"),
        ("--limit", "0"),
        ("--limit", "1001"),
    ],
    ids=["negative-start", "zero-limit", "too-large-limit"],
)
def test_installed_page_command_rejects_invalid_pagination_without_a_request(
    command: str,
    path: str,
    payload_factory: PayloadFactory,
    start: int,
    limit: int,
    fixed_params: dict[str, str],
    options: tuple[str, ...],
) -> None:
    result, seen, intruder, _ = run_page(
        command,
        path,
        payload_factory=payload_factory,
        options=options,
    )

    assert result.returncode != 0
    assert result.stdout == ""
    assert result.stderr != ""
    assert TOKEN not in result.stderr
    assert "Traceback" not in result.stderr
    assert seen == []
    assert intruder == []


@pytest.mark.parametrize(
    ("command", "path", "payload_factory", "start", "limit", "fixed_params"),
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
def test_installed_page_command_rejects_invalid_page_ids_without_a_request(
    command: str,
    path: str,
    payload_factory: PayloadFactory,
    start: int,
    limit: int,
    fixed_params: dict[str, str],
    page_argument: str,
) -> None:
    result, seen, intruder, _ = run_page(
        command,
        path,
        payload_factory=payload_factory,
        page_argument=page_argument,
    )

    assert result.returncode != 0
    assert result.stdout == ""
    assert TOKEN not in result.stderr
    assert "Traceback" not in result.stderr
    assert seen == []
    assert intruder == []


def test_installed_page_attachments_without_a_token_sends_no_request() -> None:
    result, seen, intruder, _ = run_page(
        "page-attachments",
        ATTACHMENT_PATH,
        payload_factory=attachments_payload,
        token=None,
    )

    assert result.returncode != 0
    assert result.stdout == ""
    assert "token" in result.stderr
    assert seen == []
    assert intruder == []
