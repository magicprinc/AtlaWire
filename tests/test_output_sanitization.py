import json

import pytest
from click.testing import CliRunner

import atlawire.cli as cli_module
from atlawire.cli import _tsv_cell, cli

BIDI_CONTROLS = (
    "\u061c\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"
)
BIDI_ESCAPES = "".join(f"\\u{ord(char):04x}" for char in BIDI_CONTROLS)

ROWS = [
    {
        "key": "DEMO-1",
        "status": "Open",
        "type": "Task",
        "priority": "Low",
        "assignee": "Ada\ud800",
        "updated": "2024-01-02",
        "summary": f"Résumé {BIDI_CONTROLS} ✓",
    }
]


def test_tsv_cell_visibly_escapes_unsafe_characters_and_keeps_unicode() -> None:
    assert _tsv_cell(f"A{BIDI_CONTROLS}B") == f"A{BIDI_ESCAPES}B"
    assert _tsv_cell("A\ud800B") == "A\\ud800B"
    assert _tsv_cell("Résumé Привет ✓ 👨\u200d👩\u200d👧 😀") == (
        "Résumé Привет ✓ 👨\u200d👩\u200d👧 😀"
    )
    assert _tsv_cell("a\tb\\c\r\nd") == "a\\tb\\\\c\\r\\nd"


def test_jql_tsv_escapes_but_json_preserves_server_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli_module, "search_issues", lambda *args, **kwargs: ROWS)
    common = [
        "jql",
        "project = DEMO",
        "--base-url",
        "https://jira.example.invalid",
        "--token-from-env",
    ]

    tsv = CliRunner().invoke(cli, common, env={"ATLAWIRE_JIRA_TOKEN": "fixture-token"})
    as_json = CliRunner().invoke(
        cli, [*common, "--json"], env={"ATLAWIRE_JIRA_TOKEN": "fixture-token"}
    )

    assert tsv.exit_code == 0, tsv.stderr
    assert not any(char in tsv.stdout for char in BIDI_CONTROLS)
    assert "\ud800" not in tsv.stdout
    assert BIDI_ESCAPES in tsv.stdout
    assert "\\ud800" in tsv.stdout
    assert "Résumé" in tsv.stdout
    assert "✓" in tsv.stdout

    assert as_json.exit_code == 0, as_json.stderr
    assert json.loads(as_json.stdout) == ROWS
