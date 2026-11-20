import json

import pytest
from click.testing import CliRunner

import atlawire.cli as cli_module
from atlawire.cli import cli
from atlawire.http import AtlaWireError
from atlawire.issue_markdown import render_issue_markdown


def issue(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "key": "DEMO-42",
        "fields": {"summary": "Résumé"},
        "renderedFields": {"description": "<p>Details</p>"},
    }
    value.update(overrides)
    return value


def assert_no_raw_controls(text: str) -> None:
    for char in text:
        code = ord(char)
        assert char in "\t\n" or not (code < 0x20 or 0x7F <= code <= 0x9F), repr(char)


DEEP_HTML = (
    "<div>" * 1200 + "ok" + "</div>" * 1200
)  # markdownify 1.2.3 recurses per tag


def test_renders_comments_in_raw_order_and_matches_rendered_bodies_by_id() -> None:
    value = issue(
        fields={
            "summary": "Summary",
            "comment": {
                "comments": [
                    {"id": 102, "body": "raw B"},
                    {"id": "101", "body": "raw A"},
                    {"id": 103, "body": "raw C"},
                ]
            },
        },
        renderedFields={
            "comment": {
                "comments": [
                    {"id": "101", "body": "<p>Rendered A</p>"},
                    {"id": "102", "body": "<p>Rendered B</p>"},
                ]
            }
        },
    )

    rendered = render_issue_markdown(value)

    first = rendered.index("### Comment 1")
    second = rendered.index("### Comment 2")
    third = rendered.index("### Comment 3")
    assert first < rendered.index("Rendered B") < second
    assert second < rendered.index("Rendered A") < third
    assert third < rendered.index("raw C")
    assert "raw A" not in rendered
    assert "raw B" not in rendered
    assert rendered.endswith("\n")


def test_missing_or_empty_rendered_text_falls_back_to_raw_fenced_text() -> None:
    raw_description = "Wiki *text* with `ticks`\n```\ninner fence\n```\n````\nfour"
    raw_comment = "comment ``` fence `inline`"
    value = issue(
        fields={
            "summary": "Fallback",
            "description": raw_description,
            "comment": {"comments": [{"id": "1", "body": raw_comment}]},
        },
        renderedFields={
            "description": "<p> </p>",
            "comment": {"comments": [{"id": "1", "body": "<p></p>"}]},
        },
    )

    rendered = render_issue_markdown(value)

    assert "`````text\n" in rendered
    assert raw_description in rendered
    assert "````text\n" + raw_comment in rendered
    assert rendered.endswith("\n")


def test_rendered_html_keeps_basic_structure_without_active_links_or_markup() -> None:
    html = (
        "<h2>Section</h2>"
        "<p><strong>Bold</strong> and <em>italic</em> and <code>x</code></p>"
        "<ul><li>one</li><li>two</li></ul>"
        "<pre>a\n```\nb</pre>"
        '<p><a href="https://src.invalid/a">label</a> '
        '<img src="https://src.invalid/i.png" alt="alt] (x)"></p>'
        "<p>&lt;script&gt;alert(1)&lt;/script&gt;</p>"
    )

    rendered = render_issue_markdown(
        issue(
            fields={"description": "raw fallback must not appear"},
            renderedFields={"description": html},
        )
    )

    assert "## Section" in rendered
    assert "**Bold**" in rendered
    assert "*italic*" in rendered
    assert "`x`" in rendered
    assert "- one\n- two" in rendered
    assert "````\na\n```\nb\n````" in rendered
    assert "label" in rendered
    assert "alt" in rendered
    assert "https://src.invalid" not in rendered
    assert "raw fallback must not appear" not in rendered
    assert "<script>" not in rendered
    assert "\\<script\\>" in rendered
    assert "](https" not in rendered
    assert "![" not in rendered


def test_image_alt_text_cannot_inject_block_markdown() -> None:
    rendered = render_issue_markdown(
        issue(renderedFields={"description": '<img alt="# Injected heading">'})
    )

    assert "\n# Injected heading" not in rendered
    assert "\\# Injected heading" in rendered


def test_recursion_error_uses_raw_description_fallback() -> None:
    value = issue(
        fields={"description": "raw fallback text"},
        renderedFields={"description": DEEP_HTML},
    )

    rendered = render_issue_markdown(value)

    assert "```text\nraw fallback text\n```" in rendered
    assert "Rendered Markdown conversion was unavailable" not in rendered


def test_recursion_error_without_raw_description_reports_unavailable() -> None:
    rendered = render_issue_markdown(
        issue(
            fields={"summary": "No raw fallback"},
            renderedFields={"description": DEEP_HTML},
        )
    )

    assert "## Description" in rendered
    assert "_Rendered Markdown conversion was unavailable" in rendered
    assert "no raw fallback was available" in rendered


def test_recursion_error_in_comment_without_raw_body_reports_unavailable() -> None:
    value = issue(
        fields={"comment": {"comments": [{"id": 1, "body": None}]}},
        renderedFields={"comment": {"comments": [{"id": 1, "body": DEEP_HTML}]}},
    )

    rendered = render_issue_markdown(value)

    assert "### Comment 1" in rendered
    assert "_Rendered Markdown conversion was unavailable" in rendered


def test_recursion_error_in_comment_uses_raw_body_when_available() -> None:
    value = issue(
        fields={"comment": {"comments": [{"id": 1, "body": "raw comment"}]}},
        renderedFields={"comment": {"comments": [{"id": 1, "body": DEEP_HTML}]}},
    )

    rendered = render_issue_markdown(value)

    assert "```text\nraw comment\n```" in rendered
    assert "Rendered Markdown conversion was unavailable" not in rendered


def test_duplicate_rendered_ids_fall_back_to_each_raw_comment() -> None:
    value = issue(
        fields={
            "comment": {
                "comments": [
                    {"id": "1", "body": "raw one"},
                    {"id": "2", "body": "raw two"},
                ]
            }
        },
        renderedFields={
            "comment": {
                "comments": [
                    {"id": "1", "body": "<p>first version</p>"},
                    {"id": "1", "body": "<p>second version</p>"},
                    {"id": "2", "body": "<p>rendered two</p>"},
                ]
            }
        },
    )

    rendered = render_issue_markdown(value)

    first = rendered.index("### Comment 1")
    second = rendered.index("### Comment 2")
    assert first < rendered.index("raw one") < second
    assert second < rendered.index("rendered two")
    assert "first version" not in rendered
    assert "second version" not in rendered


def test_duplicate_raw_ids_fall_back_instead_of_sharing_rendered_body() -> None:
    value = issue(
        fields={
            "comment": {
                "comments": [
                    {"id": 1, "body": "raw A"},
                    {"id": 1, "body": "raw B"},
                    {"id": 2, "body": "raw C"},
                ]
            }
        },
        renderedFields={
            "comment": {
                "comments": [
                    {"id": "1", "body": "<p>rendered shared</p>"},
                    {"id": 2, "body": "<p>rendered distinct</p>"},
                ]
            }
        },
    )

    rendered = render_issue_markdown(value)

    assert "rendered shared" not in rendered
    assert "```text\nraw A\n```" in rendered
    assert "```text\nraw B\n```" in rendered
    assert "rendered distinct" in rendered


def test_raw_body_controls_are_visibly_escaped_with_layout_preserved() -> None:
    raw_description = "raw\x1b[31m red\r\n\tindented\rnext ✓"
    raw_comment = "comment\x01 raw\rline"
    value = issue(
        fields={
            "description": raw_description,
            "comment": {"comments": [{"id": "1", "body": raw_comment}]},
        },
        renderedFields={},
    )

    rendered = render_issue_markdown(value)

    assert_no_raw_controls(rendered)
    assert "\\x1b[31m" in rendered
    assert "\\x01" in rendered
    assert "\tindented\nnext ✓" in rendered
    assert "comment\\x01 raw\nline" in rendered


def test_rendered_body_controls_are_visibly_escaped_and_unicode_is_kept() -> None:
    html = "<p>rendered\x1b[2J\r\nnext ✓</p><ul><li>item\x07</li></ul>"
    value = issue(
        fields={"comment": {"comments": [{"id": "1", "body": "ignored raw"}]}},
        renderedFields={
            "description": html,
            "comment": {"comments": [{"id": "1", "body": "<p>comment\x1b[31m ✓</p>"}]},
        },
    )

    rendered = render_issue_markdown(value)

    assert_no_raw_controls(rendered)
    assert "\\x1b" in rendered
    assert "2J" in rendered
    assert "\\x07" in rendered
    assert "31m" in rendered
    assert "✓" in rendered


def test_heading_metadata_and_author_are_single_line_and_control_free() -> None:
    value = issue(
        fields={
            "summary": "Résumé\n# injected [x](https://evil.invalid)",
            "status": {"name": "In\nProgress"},
            "issuetype": {"name": "Bug\x1b[31m"},
            "priority": None,
            "assignee": {"displayName": "Ada\nLovelace"},
            "comment": {
                "comments": [
                    {
                        "id": "7",
                        "author": {"displayName": "Bob\x07\nBuilder"},
                        "created": "2024-01-02T03:04:05.000+0000",
                        "body": "text",
                    }
                ]
            },
        }
    )

    rendered = render_issue_markdown(value)

    assert rendered.startswith("# DEMO-42: Résumé # injected \\[x\\]")
    assert "\n# injected" not in rendered
    assert "\x1b" not in rendered
    assert "\x07" not in rendered
    assert "**Status:** In Progress · **Type:** Bug \\[31m" in rendered
    assert "**Priority:**" not in rendered
    assert "**Assignee:** Ada Lovelace" in rendered
    assert "### Comment 1 · Bob Builder · 2024-01-02" in rendered
    assert "](https" not in rendered


def test_bool_comment_ids_are_not_coerced_to_numbers() -> None:
    value = issue(
        fields={
            "comment": {"comments": [{"id": True, "body": "raw bool id"}]},
        },
        renderedFields={
            "comment": {"comments": [{"id": 1, "body": "<p>numeric one</p>"}]}
        },
    )

    rendered = render_issue_markdown(value)

    assert "numeric one" not in rendered
    assert "```text\nraw bool id\n```" in rendered


def test_incomplete_comment_page_is_marked_explicitly() -> None:
    value = issue(
        fields={
            "comment": {
                "total": 5,
                "comments": [{"id": "1", "body": "only one"}],
            }
        },
        renderedFields={},
    )

    rendered = render_issue_markdown(value)

    assert "## Comments" in rendered
    assert "Comments are incomplete: showing 1 of 5." in rendered


def test_empty_optional_fields_render_only_the_heading() -> None:
    rendered = render_issue_markdown(
        {"key": "DEMO-1", "fields": {}, "renderedFields": None}
    )

    assert rendered == "# DEMO-1\n"


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (issue(renderedFields=[]), "renderedFields"),
        (issue(fields={"description": 1}), "description"),
        (issue(renderedFields={"description": 1}), "description"),
        (issue(fields={"comment": []}), "comment"),
        (issue(fields={"comment": {"comments": "none"}}), "comment"),
        (issue(fields={"comment": {"comments": [], "total": True}}), "total"),
        (issue(fields={"comment": {"comments": [], "total": -1}}), "total"),
        (issue(fields={"comment": {"comments": [None]}}), "comment"),
        (issue(fields={"comment": {"comments": [{"body": 1}]}}), "body"),
        (issue(fields={"comment": {"comments": [{"author": "Ada"}]}}), "author"),
        (issue(fields={"comment": {"comments": [{"created": 1}]}}), "created"),
        (
            issue(renderedFields={"comment": {"comments": [None]}}),
            "comment",
        ),
        (
            issue(renderedFields={"comment": {"comments": [{"body": 1}]}}),
            "body",
        ),
        (issue(fields={"status": "Open"}), "status"),
        (issue(fields={"summary": 1}), "summary"),
    ],
)
def test_malformed_optional_shapes_raise_a_clean_error(
    value: dict[str, object], message: str
) -> None:
    with pytest.raises(AtlaWireError, match=message):
        render_issue_markdown(value)


def test_issue_help_documents_markdown() -> None:
    result = CliRunner().invoke(cli, ["issue", "--help"])

    assert result.exit_code == 0
    assert "--markdown" in result.output


def test_cli_default_keeps_json_and_markdown_flag_renders(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    value = issue()
    monkeypatch.setattr(cli_module, "get_issue", lambda *args, **kwargs: value)

    default = CliRunner().invoke(
        cli,
        [
            "issue",
            "DEMO-42",
            "--base-url",
            "https://jira.example.invalid",
            "--token-from-env",
        ],
    )
    markdown = CliRunner().invoke(
        cli,
        [
            "issue",
            "DEMO-42",
            "--base-url",
            "https://jira.example.invalid",
            "--token-from-env",
            "--markdown",
        ],
    )

    assert default.exit_code == 0
    assert json.loads(default.stdout) == value
    assert markdown.exit_code == 0
    assert markdown.stdout == render_issue_markdown(value)


def test_cli_malformed_issue_publishes_no_markdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        cli_module,
        "get_issue",
        lambda *args, **kwargs: issue(renderedFields=[]),
    )

    result = CliRunner().invoke(
        cli,
        [
            "issue",
            "DEMO-42",
            "--base-url",
            "https://jira.example.invalid",
            "--token-from-env",
            "--markdown",
        ],
    )

    assert result.exit_code == 1
    assert result.stdout == ""
    assert "renderedFields" in result.stderr
