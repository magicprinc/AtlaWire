"""Markdown quality: inert link destinations, whitespace noise, no active HTML."""

import re

from atlawire._markdown import collapse_blank_lines
from atlawire.confluence_markdown import render_page_markdown
from atlawire.issue_markdown import render_issue_markdown

ACTIVE_HTML = re.compile(r"(?<!\\)<[a-zA-Z/][^>]*>")


def _issue(description_html: str) -> dict:
    return {
        "key": "DEMO-1",
        "fields": {"summary": "sample", "description": "raw"},
        "renderedFields": {"description": description_html},
    }


def test_a_plain_link_keeps_its_destination_as_inert_text():
    markdown = render_issue_markdown(
        _issue('<p>See <a href="https://example.invalid/a">the guide</a>.</p>')
    )

    assert "the guide (https://example.invalid/a)" in markdown
    assert "](" not in markdown


def test_a_link_whose_label_is_the_url_is_not_duplicated():
    markdown = render_issue_markdown(
        _issue(
            '<p><a href="https://example.invalid/a">https://example.invalid/a</a></p>'
        )
    )

    assert markdown.count("https://example.invalid/a") == 1


def test_a_user_mention_stays_a_mention_not_a_link():
    markdown = render_issue_markdown(
        _issue(
            '<p><a href="https://jira.invalid/secure/ViewProfile.jspa?name=jdoe">'
            "John Doe</a> here</p>"
        )
    )

    assert "John Doe (jdoe)" in markdown
    assert "ViewProfile" not in markdown


def test_no_active_html_survives_conversion():
    markdown = render_issue_markdown(
        _issue("<p>a <b>bold</b> word, a <script>x</script> tag</p>")
    )

    assert ACTIVE_HTML.findall(markdown) == []


def test_a_confluence_link_keeps_its_destination():
    page = {
        "id": "1",
        "title": "T",
        "body": {
            "storage": {"value": '<p><a href="https://example.invalid/x">label</a></p>'}
        },
    }

    markdown = render_page_markdown(page)

    assert "https://example.invalid/x" in markdown


def test_collapse_blank_lines_folds_runs_outside_fences():
    text = "a\n\n\n\nb\n\nc"

    assert collapse_blank_lines(text) == "a\n\nb\n\nc"


def test_collapse_blank_lines_preserves_fenced_content():
    text = "before\n\n\n```text\nx\n\n\n\ny\n```\n\n\nafter"

    collapsed = collapse_blank_lines(text)

    assert "x\n\n\n\ny" in collapsed
    assert "\n\n\n" not in collapsed.split("```")[0]
    assert collapsed.endswith("after")


def test_issue_markdown_has_no_long_blank_runs():
    markdown = render_issue_markdown(_issue("<p>one</p>" * 1 + "<p>two</p>"))

    assert "\n\n\n" not in markdown
