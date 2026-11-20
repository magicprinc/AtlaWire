import pytest

import atlawire.confluence_markdown as markdown_module
from atlawire.confluence_markdown import render_page_markdown


def page(storage: str, title: str = "Page") -> dict[str, object]:
    return {
        "id": "123",
        "type": "page",
        "title": title,
        "body": {"storage": {"value": storage, "representation": "storage"}},
    }


BIDI_CONTROLS = (
    "\u061c\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"
)
BIDI_ESCAPES = "".join(f"\\u{ord(char):04x}" for char in BIDI_CONTROLS)


def assert_no_raw_controls(text: str) -> None:
    for char in text:
        code = ord(char)
        assert char in "\t\n" or not (
            code < 0x20
            or 0x7F <= code <= 0x9F
            or char in BIDI_CONTROLS
            or 0xD800 <= code <= 0xDFFF
        ), repr(char)


def test_regular_structure_is_kept_without_active_links_or_images() -> None:
    storage = (
        "<h2>Overview</h2>"
        "<p><strong>Bold</strong> and <em>italic</em> and <code>inline</code></p>"
        "<ul><li>alpha</li><li>beta</li></ul>"
        "<ol><li>first</li><li>second</li></ol>"
        "<table><tbody><tr><th>Key</th><th>Value</th></tr>"
        "<tr><td>one</td><td>1</td></tr></tbody></table>"
        '<p><a href="https://evil.invalid/a">label</a> '
        '<img src="https://evil.invalid/i.png" alt="alt] (x)"></p>'
    )

    rendered = render_page_markdown(page(storage))

    assert rendered.startswith("# Page\n")
    assert "## Overview" in rendered
    assert "**Bold**" in rendered
    assert "*italic*" in rendered
    assert "`inline`" in rendered
    assert "- alpha\n- beta" in rendered
    assert "1. first\n2. second" in rendered
    assert "| Key | Value |" in rendered
    assert "| one | 1 |" in rendered
    assert "label" in rendered
    assert "alt" in rendered
    assert "https://evil.invalid" not in rendered
    assert "](https" not in rendered
    assert "![" not in rendered


def test_empty_storage_is_a_successful_heading_only_page() -> None:
    assert render_page_markdown(page("")) == "# Page\n"
    assert render_page_markdown(page(" \r\n\t ")) == "# Page\n"


def test_title_becomes_one_literal_heading_line() -> None:
    rendered = render_page_markdown(
        page("<p>body</p>", title="Résumé\n# injected [x]\x1b[31m")
    )

    assert rendered.startswith("# Résumé # injected \\[x\\] \\[31m\n")
    assert "\n# injected" not in rendered
    assert_no_raw_controls(rendered)


@pytest.mark.parametrize(
    ("title", "expected_heading"),
    [
        ("Troubleshooting", "# Troubleshooting\n"),
        ("Hash#Inside", "# Hash#Inside\n"),
        ("Troubleshooting###", "# Troubleshooting###\n"),
        ("Troubleshooting ###", "# Troubleshooting \\#\\#\\#\n"),
        ("Troubleshooting #", "# Troubleshooting \\#\n"),
    ],
)
def test_heading_escapes_only_trailing_atx_delimiter_runs(
    title: str, expected_heading: str
) -> None:
    rendered = render_page_markdown(page("<p>body</p>", title=title))

    assert rendered.startswith(expected_heading)


def test_code_macro_preserves_blank_lines_and_uses_a_longer_fence() -> None:
    code = 'def f():\n    return "```"\n\n# spaced\n\nprint("done")\n\n'
    storage = (
        '<ac:structured-macro ac:name="code">'
        '<ac:parameter ac:name="language">python</ac:parameter>'
        '<ac:parameter ac:name="secret">PARAM-SENTINEL</ac:parameter>'
        f"<ac:plain-text-body><![CDATA[{code}]]></ac:plain-text-body>"
        "</ac:structured-macro>"
    )

    rendered = render_page_markdown(page(storage))

    assert "````python\n" + code + "````" in rendered
    assert "PARAM-SENTINEL" not in rendered
    assert "Code conversion fallback" not in rendered


@pytest.mark.parametrize("name", ["code", "noformat"])
def test_code_macro_without_plain_text_keeps_rich_body_with_fallback_marker(
    name: str,
) -> None:
    storage = (
        f'<ac:structured-macro ac:name="{name}">'
        '<ac:parameter ac:name="language">python</ac:parameter>'
        '<ac:parameter ac:name="secret">PARAM-SENTINEL</ac:parameter>'
        "<ac:rich-text-body><p>Readable <em>fallback</em></p></ac:rich-text-body>"
        "</ac:structured-macro>"
    )

    rendered = render_page_markdown(page(storage))

    assert "Code conversion fallback" in rendered
    assert "no plain-text code payload" in rendered
    assert "Readable *fallback*" in rendered
    assert "PARAM-SENTINEL" not in rendered
    assert "```" not in rendered


@pytest.mark.parametrize("name", ["code", "noformat"])
def test_code_macro_without_any_body_shows_marker_alone(name: str) -> None:
    storage = (
        f'<ac:structured-macro ac:name="{name}">'
        '<ac:parameter ac:name="secret">PARAM-SENTINEL</ac:parameter>'
        "</ac:structured-macro>"
    )

    rendered = render_page_markdown(page(storage))

    assert rendered == (
        "# Page\n\n"
        "_Code conversion fallback: no plain-text code payload was available._\n"
    )
    assert "PARAM-SENTINEL" not in rendered


def test_bidi_controls_and_surrogates_are_visibly_escaped() -> None:
    storage = (
        f"<p>Параграф {BIDI_CONTROLS} 日本語 ✓ 👨\u200d👩\u200d👧</p>"
        '<ac:structured-macro ac:name="noformat"><ac:plain-text-body>'
        f"<![CDATA[code {BIDI_CONTROLS}]]></ac:plain-text-body>"
        "</ac:structured-macro>"
    )

    rendered = render_page_markdown(
        page(storage, title=f"Résumé {BIDI_CONTROLS} \ud800")
    )

    assert_no_raw_controls(rendered)
    for char in BIDI_CONTROLS:
        assert char not in rendered
        assert f"\\u{ord(char):04x}" in rendered
    assert f"# Résumé {BIDI_ESCAPES} \\ud800" in rendered
    assert f"Параграф {BIDI_ESCAPES} 日本語" in rendered
    assert f"code {BIDI_ESCAPES}" in rendered
    assert "\\ud800" in rendered
    assert "Résumé" in rendered
    assert "Параграф" in rendered
    assert "日本語" in rendered
    assert "✓" in rendered
    assert "👨\u200d👩\u200d👧" in rendered


def test_code_macro_escapes_controls_visibly() -> None:
    storage = (
        '<ac:structured-macro ac:name="noformat"><ac:plain-text-body>'
        "<![CDATA[line\x1b[2J\n\nnext]]></ac:plain-text-body>"
        "</ac:structured-macro>"
    )

    rendered = render_page_markdown(page(storage))

    assert "line\\x1b[2J\n\nnext" in rendered
    assert_no_raw_controls(rendered)


@pytest.mark.parametrize(
    "language",
    ["python`x", "obj c", "a\nb", "x" * 40],
)
def test_unsafe_code_language_label_is_omitted(language: str) -> None:
    storage = (
        '<ac:structured-macro ac:name="code">'
        f'<ac:parameter ac:name="language">{language}</ac:parameter>'
        "<ac:plain-text-body><![CDATA[x]]></ac:plain-text-body>"
        "</ac:structured-macro>"
    )

    rendered = render_page_markdown(page(storage))

    assert "```\nx\n```" in rendered
    assert language not in rendered


def test_unknown_macro_shows_a_marker_and_keeps_its_rich_body_only() -> None:
    storage = (
        '<ac:structured-macro ac:name="mystery">'
        '<ac:parameter ac:name="secret">PARAM-SENTINEL</ac:parameter>'
        "<ac:rich-text-body><p>Readable <em>body</em></p>"
        '<ac:structured-macro ac:name="inner"><ac:rich-text-body>'
        "<p>nested text</p></ac:rich-text-body></ac:structured-macro>"
        "</ac:rich-text-body></ac:structured-macro>"
    )

    rendered = render_page_markdown(page(storage))

    assert "[Unsupported macro: mystery]" in rendered
    assert "Readable *body*" in rendered
    assert "[Unsupported macro: inner]" in rendered
    assert "nested text" in rendered
    assert "PARAM-SENTINEL" not in rendered


def test_macro_inside_a_list_keeps_readable_content() -> None:
    storage = (
        "<ul><li>before "
        '<ac:structured-macro ac:name="mystery"><ac:rich-text-body>'
        "<p>inside</p></ac:rich-text-body></ac:structured-macro>"
        " after</li></ul>"
    )

    rendered = render_page_markdown(page(storage))

    assert "before" in rendered
    assert "[Unsupported macro: mystery]" in rendered
    assert "inside" in rendered
    assert "after" in rendered


def test_code_macro_inside_a_list_keeps_its_text_readable() -> None:
    storage = (
        "<ul><li>step "
        '<ac:structured-macro ac:name="code"><ac:plain-text-body>'
        "<![CDATA[print('nested')\n\nnext]]></ac:plain-text-body>"
        "</ac:structured-macro></li></ul>"
    )

    rendered = render_page_markdown(page(storage))

    assert "```" in rendered
    assert "print('nested')\n\n  next" in rendered


def test_unknown_macro_name_is_presented_as_data() -> None:
    storage = '<ac:structured-macro ac:name="# injected `x`"></ac:structured-macro>'

    rendered = render_page_markdown(page(storage))

    assert "\n# injected" not in rendered
    assert "[Unsupported macro: \\# injected \\`x\\`]" in rendered
    assert render_page_markdown(page("<p>x</p>")).count("Unsupported macro") == 0


def test_missing_macro_name_uses_a_clear_marker() -> None:
    rendered = render_page_markdown(page("<ac:structured-macro></ac:structured-macro>"))

    assert "[Unsupported macro: unknown]" in rendered


def test_deep_storage_falls_back_to_a_literal_fenced_block() -> None:
    storage = "<div>" * 1200 + "deep storage text" + "</div>" * 1200

    rendered = render_page_markdown(page(storage))

    assert "_Page storage is nested too deeply" in rendered
    assert "```xml\n" in rendered
    assert "deep storage text" in rendered
    assert rendered.endswith("```\n")


def test_oversized_storage_falls_back_without_converting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(markdown_module, "_MAX_STORAGE_CHARS", 20)
    storage = "<p>source text longer than the limit</p>"

    rendered = render_page_markdown(page(storage))

    assert "_Page storage is too large" in rendered
    assert "```xml\n" + storage + "\n```" in rendered
