"""Installed-CLI loopback contracts for the canonical ``read`` command.

Credentials come from a synthetic saved file read by the real loader, so this
exercises CLI parsing, credential resolution, the shared SDK adapter, the JSON
envelope and the exit status together.
"""

import json
from http.server import BaseHTTPRequestHandler
from pathlib import Path

import pytest

from tests._loopback import (
    Request,
    request_record,
    run_installed,
    send_bytes,
    serving,
)

CONTEXTS = {
    "bitbucket": "/bitbucket",
    "confluence": "/confluence",
    "jira": "/jira",
}
TOKENS = {
    "bitbucket": "synthetic-read-bitbucket-3a1",
    "confluence": "synthetic-read-confluence-3a2",
    "jira": "synthetic-read-jira-3a3",
}
DATA = {
    "bitbucket": {"slug": "example-repository", "public": False},
    "confluence": {"key": "DEMO", "name": "Demo space"},
    "jira": {"key": "DEMO", "name": "Demo project"},
}


def saved_credentials(tmp_path: Path, origin: str) -> dict[str, str]:
    """Write a synthetic saved file and return the child environment."""
    document = {}
    for product, context in CONTEXTS.items():
        document[f"{product}_url"] = f"{origin}{context}/"
        document[f"{product}_token"] = TOKENS[product]
    path = tmp_path / "credentials.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    environment = {"BBK_CREDENTIALS": str(path)}
    # Prove saved-file mode ignores ambient product variables.
    for product in CONTEXTS:
        environment[f"ATLAWIRE_{product.upper()}_URL"] = "http://127.0.0.1:9/wrong"
        environment[f"ATLAWIRE_{product.upper()}_TOKEN"] = "wrong-token"
    return environment


def handler(
    seen: list[Request],
    *,
    status: int = 200,
    payload: object | None = None,
    body: bytes | None = None,
    empty: bool = False,
) -> type[BaseHTTPRequestHandler]:
    response = b""
    if body is not None:
        response = body
    elif not empty:
        response = json.dumps(payload if payload is not None else {"ok": True}).encode()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            seen.append(request_record(self))
            send_bytes(self, status, response, content_type="application/json")

    return Handler


CASES = [
    (
        "jira",
        "jira.project.get",
        {"projectIdOrKey": "DEMO"},
        "/jira/rest/api/2/project/DEMO",
    ),
    (
        "confluence",
        "confluence.space.get",
        {"spaceKey": "DEMO"},
        "/confluence/rest/api/space/DEMO",
    ),
    (
        "bitbucket",
        "bitbucket.repository.get",
        {"projectKey": "DEMO", "repositorySlug": "example-repository"},
        "/bitbucket/rest/api/1.0/projects/DEMO/repos/example-repository",
    ),
]


@pytest.mark.parametrize(("product", "operation", "params", "path"), CASES)
def test_read_returns_the_documented_envelope_for_each_product(
    product: str,
    operation: str,
    params: dict[str, str],
    path: str,
    tmp_path: Path,
) -> None:
    seen: list[Request] = []
    with serving(handler(seen, payload=DATA[product])) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        result = run_installed(
            [
                "read",
                operation,
                "--params",
                json.dumps(params),
                "--allow-http-loopback",
            ],
            saved_credentials(tmp_path, origin),
        )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "ok": True,
        "product": product,
        "data": DATA[product],
    }
    assert seen == [
        (
            "GET",
            path,
            {},
            f"Bearer {TOKENS[product]}",
        )
    ]


def test_read_of_an_unknown_operation_is_a_usage_error_without_requests(
    tmp_path: Path,
) -> None:
    seen: list[Request] = []
    with serving(handler(seen)) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        result = run_installed(
            [
                "read",
                "jira.not.registered",
                "--params",
                "{}",
                "--allow-http-loopback",
            ],
            saved_credentials(tmp_path, origin),
        )

    assert result.returncode == 2
    envelope = json.loads(result.stdout)
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "validation_error"
    assert envelope["error"]["status"] is None
    assert seen == []


def test_read_of_malformed_params_is_json_without_requests(tmp_path: Path) -> None:
    seen: list[Request] = []
    with serving(handler(seen)) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        result = run_installed(
            [
                "read",
                "jira.project.get",
                "--params",
                "{",
                "--allow-http-loopback",
            ],
            saved_credentials(tmp_path, origin),
        )

    assert result.returncode == 2
    envelope = json.loads(result.stdout)
    assert envelope["error"]["code"] == "validation_error"
    assert seen == []


def test_read_without_saved_credentials_is_a_json_configuration_error(
    tmp_path: Path,
) -> None:
    seen: list[Request] = []
    missing = tmp_path / "missing.json"
    with serving(handler(seen)) as server:
        assert server.server_port > 0
        result = run_installed(
            [
                "read",
                "jira.project.get",
                "--params",
                '{"projectIdOrKey":"DEMO"}',
                "--allow-http-loopback",
            ],
            {"BBK_CREDENTIALS": str(missing)},
        )

    assert result.returncode == 2
    envelope = json.loads(result.stdout)
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "credentials_error"
    assert envelope["error"]["status"] is None
    assert seen == []


def test_read_maps_an_upstream_404_and_keeps_the_status(tmp_path: Path) -> None:
    seen: list[Request] = []
    with serving(handler(seen, status=404, payload={"message": "gone"})) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        result = run_installed(
            [
                "read",
                "jira.project.get",
                "--params",
                '{"projectIdOrKey":"DEMO"}',
                "--allow-http-loopback",
            ],
            saved_credentials(tmp_path, origin),
        )

    assert result.returncode == 1
    envelope = json.loads(result.stdout)
    assert envelope["ok"] is False
    assert envelope["error"]["status"] == 404
    assert envelope["error"]["code"] == "http_404"
    assert len(seen) == 1


def test_read_rejects_a_response_of_the_wrong_shape(tmp_path: Path) -> None:
    seen: list[Request] = []
    with serving(handler(seen, payload=[])) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        result = run_installed(
            [
                "read",
                "jira.project.get",
                "--params",
                '{"projectIdOrKey":"DEMO"}',
                "--allow-http-loopback",
            ],
            saved_credentials(tmp_path, origin),
        )

    assert result.returncode == 1
    envelope = json.loads(result.stdout)
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "invalid_response"
    assert envelope["error"]["status"] == 200
    assert len(seen) == 1


def test_read_of_an_empty_200_object_is_not_treated_as_success(
    tmp_path: Path,
) -> None:
    seen: list[Request] = []
    with serving(handler(seen, empty=True)) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        result = run_installed(
            [
                "read",
                "jira.project.get",
                "--params",
                '{"projectIdOrKey":"DEMO"}',
                "--allow-http-loopback",
            ],
            saved_credentials(tmp_path, origin),
        )

    assert result.returncode == 1
    envelope = json.loads(result.stdout)
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "invalid_response"
    assert envelope["error"]["status"] == 200
    assert len(seen) == 1


def test_read_rejects_a_non_object_params_argument(tmp_path: Path) -> None:
    seen: list[Request] = []
    with serving(handler(seen)) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        result = run_installed(
            [
                "read",
                "jira.project.get",
                "--params",
                '["DEMO"]',
                "--allow-http-loopback",
            ],
            saved_credentials(tmp_path, origin),
        )

    assert result.returncode == 2
    assert json.loads(result.stdout)["error"]["code"] == "validation_error"
    assert seen == []


DEFAULT_BRANCH = "bitbucket.repository.default-branch"
DEFAULT_BRANCH_PARAMS = '{"projectKey":"DEMO","repositorySlug":"example-repository"}'
DEFAULT_BRANCH_PATH = (
    "/bitbucket/rest/api/1.0/projects/DEMO/repos/example-repository/branches/default"
)


def test_documented_204_returns_data_null(tmp_path: Path) -> None:
    seen: list[Request] = []
    with serving(handler(seen, status=204, empty=True)) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        result = run_installed(
            [
                "read",
                DEFAULT_BRANCH,
                "--params",
                DEFAULT_BRANCH_PARAMS,
                "--allow-http-loopback",
            ],
            saved_credentials(tmp_path, origin),
        )

    assert result.returncode == 0, result.stdout
    assert json.loads(result.stdout) == {
        "ok": True,
        "product": "bitbucket",
        "data": None,
    }
    assert seen == [("GET", DEFAULT_BRANCH_PATH, {}, f"Bearer {TOKENS['bitbucket']}")]


def test_200_json_null_is_not_a_no_content_success(tmp_path: Path) -> None:
    seen: list[Request] = []
    with serving(handler(seen, status=200, body=b"null")) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        result = run_installed(
            [
                "read",
                DEFAULT_BRANCH,
                "--params",
                DEFAULT_BRANCH_PARAMS,
                "--allow-http-loopback",
            ],
            saved_credentials(tmp_path, origin),
        )

    assert result.returncode == 1
    envelope = json.loads(result.stdout)
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "invalid_response"
    assert envelope["error"]["status"] == 200
    assert len(seen) == 1


def test_partial_content_206_is_never_a_complete_read(tmp_path: Path) -> None:
    seen: list[Request] = []
    with serving(handler(seen, status=206, payload={"key": "DEMO"})) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        result = run_installed(
            [
                "read",
                "jira.project.get",
                "--params",
                '{"projectIdOrKey":"DEMO"}',
                "--allow-http-loopback",
            ],
            saved_credentials(tmp_path, origin),
        )

    assert result.returncode == 1
    envelope = json.loads(result.stdout)
    assert envelope["error"]["code"] == "invalid_response"
    assert envelope["error"]["status"] == 206
    assert len(seen) == 1


def test_read_with_a_wrong_argument_name_is_a_usage_error_without_requests(
    tmp_path: Path,
) -> None:
    seen: list[Request] = []
    with serving(handler(seen)) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        result = run_installed(
            [
                "read",
                "jira.project.get",
                "--params",
                '{"projectKey":"DEMO"}',
                "--allow-http-loopback",
            ],
            saved_credentials(tmp_path, origin),
        )

    assert result.returncode == 2
    envelope = json.loads(result.stdout)
    assert envelope["error"]["code"] == "validation_error"
    assert seen == []


GENERATED_CASES = [
    (
        "jira",
        "jira.myself",
        "/jira/rest/api/2/myself",
        {"name": "ada", "displayName": "Ada"},
    ),
    (
        "confluence",
        "confluence.longtask",
        "/confluence/rest/api/longtask",
        {"results": [], "size": 0},
    ),
    (
        "bitbucket",
        "bitbucket.dashboard.pull-requests",
        "/bitbucket/rest/api/1.0/dashboard/pull-requests",
        {"values": [], "isLastPage": True},
    ),
]


@pytest.mark.parametrize(
    ("product", "operation", "path", "payload"),
    GENERATED_CASES,
    ids=[case[1] for case in GENERATED_CASES],
)
def test_generated_manifest_route_runs_through_the_canonical_cli(
    product: str,
    operation: str,
    path: str,
    payload: dict[str, object],
    tmp_path: Path,
) -> None:
    seen: list[Request] = []
    with serving(handler(seen, payload=payload)) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        result = run_installed(
            [
                "read",
                operation,
                "--params",
                "{}",
                "--allow-http-loopback",
            ],
            saved_credentials(tmp_path, origin),
        )

    assert result.returncode == 0, result.stdout
    assert json.loads(result.stdout) == {
        "ok": True,
        "product": product,
        "data": payload,
    }
    assert seen == [("GET", path, {}, f"Bearer {TOKENS[product]}")]


def test_argument_validation_precedes_credentials(tmp_path: Path) -> None:
    """A typo must be a validation error even without saved credentials."""
    result = run_installed(
        [
            "read",
            "jira.project.get",
            "--params",
            '{"projectKey":"DEMO"}',
            "--allow-http-loopback",
        ],
        {"BBK_CREDENTIALS": str(tmp_path / "missing.json")},
    )

    assert result.returncode == 2
    envelope = json.loads(result.stdout)
    assert envelope["error"]["code"] == "validation_error"
    assert "projectIdOrKey" in envelope["error"]["message"]


def test_selftest_is_the_whoami_probe_under_the_bbk_name(tmp_path: Path) -> None:
    """The BBK name stays available without a second probe implementation."""
    environment = {"BBK_CREDENTIALS": str(tmp_path / "missing.json")}
    result = run_installed(["selftest"], environment)

    assert result.returncode in {0, 1}
    payload = json.loads(result.stdout)
    assert set(payload) == {"bitbucket", "confluence", "jira"}
    assert all("ok" in check for check in payload.values())
