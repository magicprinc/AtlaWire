"""Black-box parity tests for panel, status and wiki inline-code rendering.

Confluence panel macros (``info``/``note``/``warning``/``tip``/``panel``) used
to render only a marker naming the macro, and ``status`` used to show its name
instead of a status. Jira wiki ``{{code}}`` used to be consumed by the
``{code}`` block scan and rendered as an unterminated block. Fixtures below are
plain storage/wiki strings; no HTTP request is made and no credential is read.
"""

import pytest

from atlawire.confluence_markdown import render_page_markdown
from atlawire.issue_markdown import wiki_to_markdown

PANEL_TYPES = [
    ("info", "Info"),
    ("note", "Note"),
    ("warning", "Warning"),
    ("tip", "Tip"),
    ("panel", "Panel"),
]


def _page(storage):
    return render_page_markdown(
        {"title": "Page", "body": {"storage": {"value": storage}}}
    )


def _panel(name, body, *, parameters=""):
    return (
        f'<ac:structured-macro ac:name="{name}">'
        f"{parameters}"
        f"<ac:rich-text-body>{body}</ac:rich-text-body>"
        "</ac:structured-macro>"
    )


@pytest.mark.parametrize(("name", "label"), PANEL_TYPES)
def test_each_panel_type_keeps_its_body_in_a_labelled_quote(name, label):
    body = f"Body of the {name} panel."
    markdown = _page(_panel(name, f"<p>{body}</p>"))

    assert f"> **{label}:** {body}" in markdown
    assert "Unsupported macro" not in markdown


def test_panel_title_replaces_type_label_and_keeps_body():
    storage = _panel(
        "note",
        "<p>Read this first.</p>",
        parameters='<ac:parameter ac:name="title">Heads up</ac:parameter>',
    )
    markdown = _page(storage)

    assert "> **Heads up:** Read this first." in markdown
    assert "[Unsupported macro" not in markdown


def test_panel_parameters_other_than_title_stay_readable():
    storage = _panel(
        "panel",
        "<p>Body.</p>",
        parameters='<ac:parameter ac:name="borderColor">#ff0000</ac:parameter>',
    )
    markdown = _page(storage)

    assert "borderColor" in markdown
    assert "ff0000" in markdown
    assert "> **Panel:** Body." in markdown


def test_panel_block_body_starts_after_the_label():
    markdown = _page(_panel("tip", "<ul><li>first</li><li>second</li></ul>"))

    assert "> **Tip:**\n> - first\n> - second" in markdown


def test_panel_multiple_paragraphs_stay_inside_the_quote():
    markdown = _page(_panel("warning", "<p>First line.</p><p>Second line.</p>"))

    assert "> **Warning:** First line." in markdown
    assert "> Second line." in markdown


def test_panel_without_body_still_shows_the_type():
    storage = '<ac:structured-macro ac:name="info"></ac:structured-macro>'

    assert "> **Info:**" in _page(storage)


def test_status_macro_renders_visible_status_text():
    storage = (
        "<p>State: "
        '<ac:structured-macro ac:name="status">'
        '<ac:parameter ac:name="title">In progress</ac:parameter>'
        "</ac:structured-macro> now.</p>"
    )
    markdown = _page(storage)

    assert "`[STATUS] In progress`" in markdown
    assert "State: `[STATUS] In progress` now." in markdown
    assert "Unsupported macro" not in markdown


def test_status_extra_parameter_stays_readable():
    storage = (
        '<ac:structured-macro ac:name="status">'
        '<ac:parameter ac:name="colour">Red</ac:parameter>'
        "</ac:structured-macro>"
    )
    markdown = _page(storage)

    assert "`[STATUS]`" in markdown
    assert "colour=Red" in markdown


def test_status_without_title_keeps_a_visible_marker():
    storage = '<p><ac:structured-macro ac:name="status"></ac:structured-macro></p>'

    assert "`[STATUS]`" in _page(storage)


def test_mixed_page_keeps_panel_status_link_and_code():
    storage = (
        '<p>Intro <a href="https://example.com/doc">guide</a>.</p>'
        + _panel("note", "<p>Important note body.</p>")
        + '<p>Status: <ac:structured-macro ac:name="status">'
        '<ac:parameter ac:name="title">Done</ac:parameter>'
        "</ac:structured-macro></p>"
        '<ac:structured-macro ac:name="code">'
        "<ac:plain-text-body><![CDATA[print(1)]]></ac:plain-text-body>"
        "</ac:structured-macro>"
    )
    markdown = _page(storage)

    assert "[guide](https://example.com/doc)" in markdown
    assert "> **Note:** Important note body." in markdown
    assert "`[STATUS] Done`" in markdown
    assert "print(1)" in markdown


def test_wiki_inline_code_is_not_mistaken_for_a_code_block():
    markdown = wiki_to_markdown("Use {{code}} in the description.")

    assert "Use `code` in the description." in markdown
    assert "Unterminated" not in markdown


def test_wiki_inline_code_survives_next_to_a_real_code_block():
    markdown = wiki_to_markdown("Inline {{code}} then:\n{code:java}\nint a;\n{code}")

    assert "Inline `code` then:" in markdown
    assert "```java\nint a;\n```" in markdown
    assert "Unterminated" not in markdown


def test_wiki_link_keeps_its_destination():
    markdown = wiki_to_markdown(
        "See [docs|https://example.com/a?b=1&c=2] and "
        "[path|https://example.com/a_(b)] today."
    )

    assert "[docs](<https://example.com/a?b=1&c=2>)" in markdown
    assert "[path](<https://example.com/a_(b)>)" in markdown


def test_wiki_mixed_document_keeps_every_supported_construct():
    markdown = wiki_to_markdown(
        "h2. Title\n\n"
        "*bold* and _italic_ with {{code}}.\n\n"
        "{code:python}\nprint(1)\n{code}\n\n"
        "See [docs|https://example.com/path].\n"
    )

    assert markdown.startswith("## Title")
    assert "**bold** and *italic* with `code`." in markdown
    assert "```python\nprint(1)\n```" in markdown
    assert "[docs](<https://example.com/path>)" in markdown
    assert "Unterminated" not in markdown
