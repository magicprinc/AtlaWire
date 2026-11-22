"""Installed-CLI loopback contracts for the three semantic-read POSTs.

Each case proves the method, the fixed route, the declared body and the JSON
envelope. The negative cases prove that an undeclared body field or a missing
body is rejected before any request.
"""

import json
from http.server import BaseHTTPRequestHandler
from pathlib import Path

import pytest

from tests._loopback import run_installed, send_json, serving

TOKENS = {
    "bitbucket": "synthetic-post-bitbucket-4b1",
    "confluence": "synthetic-post-confluence-4b2",
    "jira": "synthetic-post-jira-4b3",
}


def _environment(tmp_path: Path, origin: str) -> dict[str, str]:
    """Saved credentials with the fixed tokens used by these cases."""
    document = {}
    for product, context in (
        ("jira", "/jira"),
        ("confluence", "/confluence"),
        ("bitbucket", "/bitbucket"),
    ):
        document[f"{product}_url"] = f"{origin}{context}/"
        document[f"{product}_token"] = TOKENS[product]
    path = tmp_path / "credentials.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    environment = {"BBK_CREDENTIALS": str(path)}
    for product in TOKENS:
        environment[f"ATLAWIRE_{product.upper()}_URL"] = "http://127.0.0.1:9/wrong"
        environment[f"ATLAWIRE_{product.upper()}_TOKEN"] = "wrong-token"
    return environment


class _Recorder:
    def __init__(self, payload: object) -> None:
        self.payload = payload
        self.seen: list[tuple[str, str, bytes]] = []
        self.authorization: list[str | None] = []


def _handler(recorder: _Recorder) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.0"

        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length") or "0")
            body = self.rfile.read(length)
            recorder.seen.append(("POST", self.path, body))
            recorder.authorization.append(self.headers.get("Authorization"))
            send_json(self, 200, recorder.payload)

    return Handler


CASES = [
    (
        "jira.search.post",
        "{}",
        '{"jql":"order by created DESC","maxResults":1}',
        "/jira/rest/api/2/search",
        {"issues": [{"key": "DEMO-1"}], "total": 1},
    ),
    (
        "jira.worklog.list",
        "{}",
        '{"issueIds":[1,2]}',
        "/jira/rest/api/2/worklog/list",
        [{"issueId": 1, "worklogs": []}],
    ),
    (
        "confluence.content.convert",
        '{"to": "view"}',
        '{"value":"<p>x</p>","representation":"storage"}',
        "/confluence/rest/api/contentbody/convert/view",
        {"value": "<p>x</p>", "representation": "view"},
    ),
]


@pytest.mark.parametrize(
    ("operation", "params", "body", "path", "payload"),
    CASES,
    ids=[case[0] for case in CASES],
)
def test_semantic_post_sends_the_declared_body(
    operation: str,
    params: str,
    body: str,
    path: str,
    payload: object,
    tmp_path: Path,
) -> None:
    recorder = _Recorder(payload)
    with serving(_handler(recorder)) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        result = run_installed(
            [
                "read",
                operation,
                "--params",
                params,
                "--body",
                body,
                "--allow-http-loopback",
            ],
            _environment(tmp_path, origin),
        )

    assert result.returncode == 0, result.stdout
    product = operation.split(".")[0]
    assert json.loads(result.stdout) == {
        "ok": True,
        "product": product,
        "data": payload,
    }
    assert len(recorder.seen) == 1
    method, seen_path, sent = recorder.seen[0]
    assert (method, seen_path) == ("POST", path)
    assert json.loads(sent) == json.loads(body)
    assert recorder.authorization == [f"Bearer {TOKENS[product]}"]


def test_post_requires_a_body_before_any_request(tmp_path: Path) -> None:
    recorder = _Recorder({})
    with serving(_handler(recorder)) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        result = run_installed(
            [
                "read",
                "jira.search.post",
                "--params",
                "{}",
                "--allow-http-loopback",
            ],
            _environment(tmp_path, origin),
        )

    assert result.returncode == 2
    envelope = json.loads(result.stdout)
    assert envelope["error"]["code"] == "validation_error"
    assert recorder.seen == []


def test_post_rejects_an_undeclared_body_field_without_a_request(
    tmp_path: Path,
) -> None:
    recorder = _Recorder({})
    with serving(_handler(recorder)) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        result = run_installed(
            [
                "read",
                "jira.search.post",
                "--params",
                "{}",
                "--body",
                '{"jql":"order by created DESC","unknown":1}',
                "--allow-http-loopback",
            ],
            _environment(tmp_path, origin),
        )

    assert result.returncode == 2
    assert json.loads(result.stdout)["error"]["code"] == "validation_error"
    assert recorder.seen == []


def test_post_rejects_a_missing_required_body_field(tmp_path: Path) -> None:
    recorder = _Recorder({})
    with serving(_handler(recorder)) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        result = run_installed(
            [
                "read",
                "jira.search.post",
                "--params",
                "{}",
                "--body",
                '{"maxResults":1}',
                "--allow-http-loopback",
            ],
            _environment(tmp_path, origin),
        )

    assert result.returncode == 2
    assert json.loads(result.stdout)["error"]["code"] == "validation_error"
    assert recorder.seen == []
