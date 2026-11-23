"""Black-box contract tests for ``render_page_markdown``.

A storage-format page must render links, images and macro parameters without
losing them: a reader must be able to follow every destination and see every
macro parameter. Fixtures are storage XHTML strings; no HTTP call is made.
"""

from atlawire.confluence_markdown import render_page_markdown


def _render(storage: str, *, title: str = "Title") -> str:
    page = {"title": title, "body": {"storage": {"value": storage}}}
    return render_page_markdown(page)


def test_page_link_keeps_readable_text_and_page_destination():
    storage = (
        '<p>Read <ac:link ac:anchor="Summary">'
        '<ri:page ri:content-title="Release Notes" />'
        "<ac:link-body>the notes</ac:link-body></ac:link>.</p>"
        '<p><ac:link><ri:page ri:content-title="Release Notes" /></ac:link></p>'
    )
    markdown = _render(storage)

    assert markdown.startswith("# Title\n")
    assert "[the notes](confluence:Release%20Notes#Summary)" in markdown
    assert "[Release Notes](confluence:Release%20Notes)" in markdown
    assert markdown == _render(storage)


def test_attachment_link_keeps_filename_destination():
    storage = (
        "<p>Download "
        '<ac:link><ri:attachment ri:filename="spec.pdf" /></ac:link> here.</p>'
    )
    markdown = _render(storage)

    assert "Download [spec.pdf](attachment:spec.pdf) here." in markdown


def test_url_link_keeps_original_destination():
    storage = (
        "<p>See "
        '<ac:link><ri:url ri:value="https://example.com/a?b=1" />'
        "<ac:link-body>the site</ac:link-body></ac:link>.</p>"
    )
    markdown = _render(storage)

    assert "[the site](https://example.com/a?b=1)" in markdown


def test_image_renders_attachment_and_url_destinations():
    storage = (
        '<p><ac:image ac:alt="Diagram">'
        '<ri:attachment ri:filename="diagram.png" /></ac:image></p>'
        '<p><ac:image ac:alt="Logo">'
        '<ri:url ri:value="https://example.com/logo.png" /></ac:image></p>'
    )
    markdown = _render(storage)

    assert "![Diagram](attachment:diagram.png)" in markdown
    assert "![Logo](https://example.com/logo.png)" in markdown


def test_macro_parameters_are_kept_next_to_the_macro_name():
    storage = (
        '<ac:structured-macro ac:name="view-file">'
        '<ac:parameter ac:name="name">demo.pdf</ac:parameter>'
        '<ac:parameter ac:name="page">123</ac:parameter>'
        "</ac:structured-macro>"
    )
    markdown = _render(storage)

    assert "[Unsupported macro: view-file | name=demo.pdf, page=123]" in markdown


def test_unknown_macro_keeps_name_parameters_and_body():
    storage = (
        '<ac:structured-macro ac:name="custom-widget">'
        '<ac:parameter ac:name="filter">a|b [c]</ac:parameter>'
        "<ac:rich-text-body><p>rendered body</p></ac:rich-text-body>"
        "</ac:structured-macro>"
    )
    markdown = _render(storage)

    assert "[Unsupported macro: custom-widget | filter=a\\|b \\[c\\]]" in markdown
    assert "rendered body" in markdown


def test_code_macro_keeps_language_and_other_parameters():
    storage = (
        '<ac:structured-macro ac:name="code">'
        '<ac:parameter ac:name="language">python</ac:parameter>'
        '<ac:parameter ac:name="title">Example</ac:parameter>'
        "<ac:plain-text-body><![CDATA[print(1)]]></ac:plain-text-body>"
        "</ac:structured-macro>"
    )
    markdown = _render(storage)

    assert "[Macro: code | title=Example]" in markdown
    assert "```python" in markdown
    assert "print(1)" in markdown


def test_empty_title_renders_a_bare_heading_and_keeps_body():
    markdown = _render("<p>Body text</p>", title="")

    assert markdown.splitlines()[0] == "#"
    assert "Body text" in markdown


def test_special_characters_stay_escaped_in_text_and_links():
    storage = (
        "<p>literal **bold** and [brackets]</p>"
        '<p><ac:link><ri:page ri:content-title="A (B) [C]" />'
        "<ac:link-body>label [x]</ac:link-body></ac:link></p>"
    )
    markdown = _render(storage, title="Title *with* [markup]")

    assert markdown.splitlines()[0] == "# Title \\*with\\* \\[markup\\]"
    assert "literal \\*\\*bold\\*\\*" in markdown
    assert "[label \\[x\\]](confluence:A%20%28B%29%20%5BC%5D)" in markdown
