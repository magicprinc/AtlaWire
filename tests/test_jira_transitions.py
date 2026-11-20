"""Installed-CLI checks for the Jira issue transition projection."""

import json
import subprocess
from http.server import BaseHTTPRequestHandler

import pytest

from tests._loopback import (
    Request,
    request_record,
    run_installed,
    send_json,
    serving,
)

TOKEN = "fixture-jira-transitions-token"
CONTEXT = "/jira"
KEY = "DEMO-42"
TRANSITIONS_PATH = f"{CONTEXT}/rest/api/2/issue/{KEY}/transitions"
PASTED_URL = f"https://pasted.example.invalid/jira/browse/{KEY}?tab=workflow"
SENTINEL = "JIRA-TRANSITIONS-SENTINEL"

ROWS = [
    {
        "id": "41",
        "name": "Start Progress",
        "to": {"id": "3", "name": "In Progress", "extra": SENTINEL},
        "href": f"https://pasted.example.invalid/{SENTINEL}",
    },
    {"id": "02", "name": "Ready to deploy", "to": {"id": "100", "name": "Deployed"}},
    {"id": "11", "name": "Reopen", "to": None},
    {"id": "12", "name": "Close", "to": {"id": "6"}},
    {"id": "13", "name": "Review", "to": {"id": "9", "name": ""}},
    {"id": "14", "name": "Hand over", "to": {"id": "10", "name": " "}},
]

EXPECTED = [
    {"id": "41", "name": "Start Progress", "to_status": "In Progress"},
    {"id": "02", "name": "Ready to deploy", "to_status": "Deployed"},
    {"id": "11", "name": "Reopen", "to_status": None},
    {"id": "12", "name": "Close", "to_status": None},
    {"id": "13", "name": "Review", "to_status": ""},
    {"id": "14", "name": "Hand over", "to_status": " "},
]


def environment(origin: str) -> dict[str, str]:
    """Configure Jira for the loopback context and keep other products inert."""
    return {
        "ATLAWIRE_JIRA_URL": f"{origin}{CONTEXT}/",
        "ATLAWIRE_JIRA_TOKEN": TOKEN,
        "ATLAWIRE_BITBUCKET_URL": f"{origin}/wrong-bitbucket/",
        "ATLAWIRE_BITBUCKET_TOKEN": "wrong-product-fixture",
        "ATLAWIRE_CONFLUENCE_URL": f"{origin}/wrong-confluence/",
        "ATLAWIRE_CONFLUENCE_TOKEN": "wrong-product-fixture",
    }


def run_transitions(
    body: object,
    *,
    argument: str = PASTED_URL,
    extra_args: tuple[str, ...] = (),
    status: int = 200,
) -> tuple[subprocess.CompletedProcess[str], list[Request], list[str | None]]:
    """Run the installed command against one loopback transitions response."""
    seen: list[Request] = []
    accepts: list[str | None] = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            record = request_record(self)
            seen.append(record)
            accepts.append(self.headers.get("Accept"))
            _, path, _, authorization = record
            if path != TRANSITIONS_PATH or authorization != f"Bearer {TOKEN}":
                send_json(self, 401, {"message": SENTINEL})
                return
            send_json(self, status, body)

    with serving(Handler) as server:
        result = run_installed(
            [
                "transitions",
                argument,
                "--token-from-env",
                "--allow-http-loopback",
                *extra_args,
            ],
            environment(f"http://127.0.0.1:{server.server_port}"),
        )
    return result, seen, accepts


def expected_requests() -> list[Request]:
    return [("GET", TRANSITIONS_PATH, {}, f"Bearer {TOKEN}")]


def test_installed_transitions_prints_tsv_rows_in_server_order() -> None:
    result, seen, accepts = run_transitions({"transitions": ROWS})

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout == (
        "# 6 row(s)\n"
        "id\tname\tto_status\n"
        "41\tStart Progress\tIn Progress\n"
        "02\tReady to deploy\tDeployed\n"
        "11\tReopen\t\n"
        "12\tClose\t\n"
        "13\tReview\t\n"
        "14\tHand over\t \n"
    )
    assert SENTINEL not in result.stdout
    assert TOKEN not in result.stdout
    assert seen == expected_requests()
    assert accepts == ["application/json"]


def test_installed_transitions_json_keeps_exact_fields_and_null_target() -> None:
    result, seen, accepts = run_transitions(
        {"transitions": ROWS}, extra_args=("--json",)
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == EXPECTED
    assert SENTINEL not in result.stdout
    assert seen == expected_requests()
    assert accepts == ["application/json"]


@pytest.mark.parametrize(
    ("body", "stdout", "diagnostic"),
    [
        ({"transitions": []}, "# 0 row(s)\nid\tname\tto_status\n", None),
        ({"expand": "transitions", "inert": SENTINEL}, "", "transitions array"),
    ],
    ids=["empty", "missing-envelope"],
)
def test_installed_transitions_distinguishes_empty_from_missing_envelope(
    body: dict[str, object], stdout: str, diagnostic: str | None
) -> None:
    result, seen, accepts = run_transitions(body)

    assert result.stdout == stdout
    if diagnostic is None:
        assert result.returncode == 0, result.stderr
        assert result.stderr == ""
    else:
        assert result.returncode == 1
        assert diagnostic in result.stderr
        assert SENTINEL not in result.stderr
    assert seen == expected_requests()
    assert accepts == ["application/json"]


@pytest.mark.parametrize(
    ("entry", "diagnostic"),
    [
        ({"id": 41, "name": "Broken", "to": {"name": "Done"}}, "transition ID"),
        ({"id": "42", "name": "Broken", "to": "Done"}, "transition target"),
        ({"id": "42", "name": "Broken", "to": {"name": 7}}, "target status"),
        ({"id": "42", "name": "  ", "to": None}, "transition name"),
        (
            {"id": "42", "name": "Broken", "to": {"name": "Done\ud800"}},
            "valid UTF-8",
        ),
    ],
    ids=[
        "wrong-id-type",
        "wrong-target-shape",
        "target-name-type",
        "blank-name",
        "unencodable-target",
    ],
)
def test_installed_transitions_discards_everything_for_a_malformed_late_entry(
    entry: dict[str, object], diagnostic: str
) -> None:
    result, seen, accepts = run_transitions({"transitions": [ROWS[0], entry]})

    assert result.returncode == 1
    assert result.stdout == ""
    assert diagnostic in result.stderr
    assert SENTINEL not in result.stderr
    assert "Traceback" not in result.stderr
    assert seen == expected_requests()
    assert accepts == ["application/json"]


def test_installed_transitions_rejects_an_unusable_argument_without_requests() -> None:
    result, seen, accepts = run_transitions(
        {"transitions": ROWS},
        argument=f"https://pasted.example.invalid/{KEY}",
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "issue key" in result.stderr
    assert SENTINEL not in result.stderr
    assert seen == []
    assert accepts == []
