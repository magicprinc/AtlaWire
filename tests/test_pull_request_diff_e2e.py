from http.server import BaseHTTPRequestHandler

import pytest

from atlawire import bitbucket
from atlawire.http import AtlaWireError
from tests._loopback import Request, request_record, send_json, serving

TOKEN = "fixture-pr-diff-only"
CONTEXT = "/scm/bitbucket"
DIFF_PATH = f"{CONTEXT}/rest/api/1.0/projects/DEMO/repos/widgets/pull-requests/7/diff"
SENTINEL = "PR-DIFF-PAYLOAD-SENTINEL"
EXPECTED_QUERY = {
    "contextLines": ["3"],
    "whitespace": ["ignore-all"],
    "withComments": ["false"],
}
EXPECTED_REQUEST = ("GET", DIFF_PATH, EXPECTED_QUERY, f"Bearer {TOKEN}")


def diff_tree() -> tuple[dict[str, object], dict[str, dict[str, object]]]:
    """Build a complete happy-path diff with each node addressable by name."""
    line: dict[str, object] = {
        "destination": 1,
        "source": 1,
        "line": f"import re  # {SENTINEL}",
        "truncated": False,
    }
    segment: dict[str, object] = {
        "type": "ADDED",
        "lines": [line],
        "truncated": "false",
    }
    hunk: dict[str, object] = {
        "sourceLine": 1,
        "sourceSpan": 1,
        "destinationLine": 1,
        "destinationSpan": 2,
        "segments": [segment],
        "truncated": False,
    }
    diff: dict[str, object] = {
        "source": {"toString": "src/main.py"},
        "destination": {"toString": "src/main.py"},
        "hunks": [hunk],
        "truncated": "false",
        "extension": {"truncated": True, "nested": [{"truncated": True}]},
    }
    body: dict[str, object] = {
        "diffs": [diff],
        "truncated": "false",
        "contextLines": "3",
        "fromHash": "a" * 40,
        "toHash": "b" * 40,
        "whiteSpace": "SHOW",
        "extension": {"truncated": True, "payload": SENTINEL},
    }
    nodes = {
        "root": body,
        "file": diff,
        "hunk": hunk,
        "segment": segment,
        "line": line,
    }
    return body, nodes


def call_diff(
    body: object,
) -> tuple[
    dict[str, object] | None,
    AtlaWireError | None,
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
            send_json(self, 200, body)

    with serving(Handler) as server:
        base = f"http://127.0.0.1:{server.server_port}{CONTEXT}"
        try:
            value = bitbucket.get_pull_request_diff(
                base,
                "DEMO/widgets",
                "7",
                token=TOKEN,
                allow_http_loopback=True,
            )
        except AtlaWireError as error:
            return None, error, seen, accepts
    return value, None, seen, accepts


def test_one_exact_diff_get_returns_the_decoded_object_unchanged() -> None:
    payload, _nodes = diff_tree()

    value, error, seen, accepts = call_diff(payload)

    assert error is None
    assert value == payload
    assert value is not None
    assert value["truncated"] == "false"
    diffs = value["diffs"]
    assert isinstance(diffs, list)
    diff = diffs[0]
    assert isinstance(diff, dict)
    assert diff["extension"] == {
        "truncated": True,
        "nested": [{"truncated": True}],
    }
    assert seen == [EXPECTED_REQUEST]
    assert accepts == ["application/json"]


def test_source_path_without_a_path_rejects_before_any_request() -> None:
    seen: list[Request] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            seen.append(request_record(self))

    with serving(Handler) as server:
        base = f"http://127.0.0.1:{server.server_port}{CONTEXT}"
        with pytest.raises(AtlaWireError, match="diff path"):
            bitbucket.get_pull_request_diff(
                base,
                "DEMO/widgets",
                "7",
                token=TOKEN,
                source_path="old.py",
                allow_http_loopback=True,
            )

    assert seen == []


@pytest.mark.parametrize(
    ("level", "flag"),
    [
        ("file", True),
        ("file", "true"),
        ("line", True),
        ("line", "true"),
        ("hunk", "true"),
        ("segment", True),
    ],
    ids=[
        "file-bool",
        "file-string",
        "line-bool",
        "line-string",
        "hunk-string",
        "segment-bool",
    ],
)
def test_nested_declared_truncation_fails_without_a_retry(
    level: str, flag: object
) -> None:
    payload, nodes = diff_tree()
    nodes[level]["truncated"] = flag

    value, error, seen, accepts = call_diff(payload)

    assert value is None
    assert error is not None
    message = str(error)
    assert "truncated" in message
    assert "truncation flag" not in message
    for secret in (TOKEN, SENTINEL, DIFF_PATH, "127.0.0.1"):
        assert secret not in message
    assert seen == [EXPECTED_REQUEST]
    assert accepts == ["application/json"]
