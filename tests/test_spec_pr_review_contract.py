"""Contracts for the review packet's bounds and URL parsing."""

import pytest
from click.testing import CliRunner

from atlawire.cli import cli
from atlawire.http import AtlaWireError
from atlawire.pr_review import (
    _capped,
    _no_diff_checks,
    _partial_reasons,
    _render_symbols_markdown,
    parse_pr_link,
)


def test_parse_pr_link_accepts_a_normal_url():
    assert parse_pr_link(
        "https://host/projects/PRJ/repos/widgets/pull-requests/123"
    ) == ("PRJ/widgets", 123)


def test_parse_pr_link_rejects_an_oversized_id():
    url = "https://host/projects/PRJ/repos/widgets/pull-requests/" + "9" * 5000

    with pytest.raises(AtlaWireError):
        parse_pr_link(url)


def test_pr_review_cli_rejects_an_oversized_url_without_a_traceback():
    url = "https://host/projects/PRJ/repos/widgets/pull-requests/" + "9" * 5000

    result = CliRunner().invoke(cli, ["pr-review", url, "--token-from-env"])

    assert result.exit_code != 0
    assert "Traceback" not in result.output
    assert "pull-requests" in result.output


def test_capped_flags_a_dropped_tail():
    values, truncated = _capped([1, 2, 3], 2)

    assert values == [1, 2]
    assert truncated is True
    assert _capped([1, 2], 2) == ([1, 2], False)


def test_no_diff_checks_reports_totals_and_the_name_cap():
    packet = {
        "files_total": 1200,
        "commits_total": 700,
        "description": "text",
    }

    checks = _no_diff_checks(
        packet, [], [], [f"test_{index}.py" for index in range(12)]
    )

    assert checks["files_total"] == 1200
    assert checks["commits"] == 700
    assert len(checks["test_names"]) == 10
    assert checks["truncated"] == ["test_names"]


def test_partial_reasons_name_a_shortened_check_list():
    packet = {
        "description_truncated": False,
        "commits_truncated": False,
        "commits": [],
        "files_truncated": False,
        "diff": {
            "requested": True,
            "text_truncated": False,
            "counts_complete": True,
        },
        "ticket": None,
        "checks": {
            "analysis_complete": True,
            "analysis_limited": False,
            "files_not_analyzed": [],
            "unavailable_files": [],
            "truncated": ["red_flags", "big_methods"],
        },
    }

    reasons = _partial_reasons(packet)

    assert any("red_flags" in reason and "big_methods" in reason for reason in reasons)


def test_markdown_symbols_names_the_display_cap():
    symbol = {
        "status": "added",
        "name": "m",
        "kind": "method",
        "file": "A.java",
        "line": 1,
        "lines_before": 0,
        "lines_after": 1,
        "complexity": 1,
        "javadoc": False,
    }
    checks = {"symbols": [dict(symbol, line=index) for index in range(41)]}

    rendered = "\n".join(_render_symbols_markdown(checks))

    assert "Showing the first 40 of 41 changed symbols" in rendered
