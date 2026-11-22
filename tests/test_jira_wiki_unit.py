"""Unit checks for the read-only Jira wiki renderer.

Every expected Markdown string below is written by hand from the documented
contract; it is not produced by the renderer. No test contacts a network, reads
a credential store, or executes wiki content.
"""

import re

import pytest

from atlawire.http import AtlaWireError
from atlawire.issue_markdown import render_issue_markdown, wiki_to_markdown

BIDI_CONTROLS = (
    "\u061c\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069"
)
BIDI_ESCAPES = "".join(f"\\u{ord(char):04x}" for char in BIDI_CONTROLS)


def issue(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "key": "DEMO-42",
        "fields": {"summary": "Summary"},
        "renderedFields": {"description": "<p>Rendered description</p>"},
    }
    value.update(overrides)
    return value


def assert_no_raw_controls(text: str) -> None:
    for char in text:
        code = ord(char)
        assert char in "\t\n" or not (
            code < 0x20
            or 0x7F <= code <= 0x9F
            or char in BIDI_CONTROLS
            or 0xD800 <= code <= 0xDFFF
        ), repr(char)


WIKI_ISSUE: dict[str, object] = {
    "key": "DEMO-42",
    "fields": {
        "summary": "Wiki card",
        "status": {"name": "In Progress"},
        "issuetype": {"name": "Bug"},
        "priority": {"name": "High"},
        "assignee": {"displayName": "Ada"},
        "description": (
            "h2. Summary\n"
            "\n"
            "A *bold* word, an _italic_ word and {{inline `code`}}.\n"
            "\n"
            "h3. Example\n"
            "\n"
            "{code:java}\n"
            'String s = "```";\n'
            "{code}\n"
            "\n"
            "[Jira|https://jira.example.invalid/browse/DEMO-1]\n"
        ),
        "comment": {
            "total": 2,
            "comments": [
                {
                    "id": 1,
                    "author": {"displayName": "Bob"},
                    "created": "2024-02-03T04:05:06.000+0000",
                    "body": "First *raw* comment\nwith two lines",
                },
                {
                    "id": 2,
                    "author": None,
                    "created": None,
                    "body": "{noformat}\nkeep *this* {{literally}}\n{noformat}",
                },
            ],
        },
    },
    "renderedFields": {
        "description": "<p>rendered must be ignored</p>",
        "comment": {"comments": [{"id": 1, "body": "<p>rendered ignored</p>"}]},
    },
}

WIKI_ISSUE_MARKDOWN = """\
# DEMO-42: Wiki card

**Status:** In Progress · **Type:** Bug · **Priority:** High · **Assignee:** Ada

## Description

## Summary

A **bold** word, an *italic* word and `` inline `code` ``.

### Example

````java
String s = "```";
````

[Jira](<https://jira.example.invalid/browse/DEMO-1>)

## Comments

### Comment 1 · Bob · 2024-02-03

First **raw** comment
with two lines

### Comment 2

```
keep *this* {{literally}}
```
"""


def test_wiki_mode_renders_the_raw_card_and_never_drops_comments() -> None:
    rendered = render_issue_markdown(WIKI_ISSUE, use_wiki=True)

    assert rendered == WIKI_ISSUE_MARKDOWN
    assert rendered.endswith("\n")
    assert not rendered.endswith("\n\n")
    assert "rendered must be ignored" not in rendered
    assert "rendered ignored" not in rendered
    assert "### Comment 1" in rendered
    assert "### Comment 2" in rendered


DEFAULT_ISSUE: dict[str, object] = {
    "key": "DEMO-7",
    "fields": {
        "summary": "Default",
        "description": "raw must not appear",
        "comment": {
            "comments": [
                {
                    "id": "1",
                    "author": {"displayName": "Ada"},
                    "created": "2024-01-02T03:04:05.000+0000",
                    "body": "raw fallback",
                }
            ]
        },
    },
    "renderedFields": {
        "description": "<h2>Rendered</h2><p><strong>Bold</strong></p>",
        "comment": {"comments": [{"id": "1", "body": "<p>rendered body</p>"}]},
    },
}

DEFAULT_ISSUE_MARKDOWN = """\
# DEMO-7: Default

## Description

## Rendered

**Bold**

## Comments

### Comment 1 · Ada · 2024-01-02

rendered body
"""

DEFAULT_ISSUE_WIKI_MARKDOWN = """\
# DEMO-7: Default

## Description

raw must not appear

## Comments

### Comment 1 · Ada · 2024-01-02

raw fallback
"""


def test_default_mode_is_unchanged_and_wiki_mode_prefers_raw_fields() -> None:
    assert render_issue_markdown(DEFAULT_ISSUE) == DEFAULT_ISSUE_MARKDOWN
    assert (
        render_issue_markdown(DEFAULT_ISSUE, use_wiki=False)
        == DEFAULT_ISSUE_MARKDOWN
    )
    wiki = render_issue_markdown(DEFAULT_ISSUE, use_wiki=True)

    assert wiki == DEFAULT_ISSUE_WIKI_MARKDOWN
    assert "rendered body" not in wiki
    assert "raw fallback" in wiki


def test_headings_support_h1_to_h6_and_leave_h7_literal() -> None:
    rendered = wiki_to_markdown(
        "h1. One\nh2. Two\nh3. Three\nh4. Four\nh5. Five\nh6. Six\nh7. Seven"
    )

    assert rendered == (
        "# One\n\n"
        "## Two\n\n"
        "### Three\n\n"
        "#### Four\n\n"
        "##### Five\n\n"
        "###### Six\n\n"
        "h7. Seven\n"
    )


def test_bold_italic_and_inline_code_keep_separating_spaces() -> None:
    rendered = wiki_to_markdown(
        "*bold* and _italic_ and {{a}} {{b}} and foo_bar_baz and 2*3*4"
    )

    assert rendered == (
        "**bold** and *italic* and `a` `b` and foo\\_bar\\_baz and 2\\*3\\*4\n"
    )


def test_inline_code_with_backticks_and_empty_inline_code_are_safe() -> None:
    assert wiki_to_markdown("{{a `b` c}}") == "``a `b` c``\n"
    assert wiki_to_markdown("{{}}") == "`[empty Jira inline code]`\n"


WIKI_LINKS = "\n".join(
    (
        "[Plain|https://example.invalid/a?b=1&c=2]",
        "[Bare|https://example.invalid/a_(b)]",
        "[https://example.invalid/only]",
        "[DEMO-2]",
        "[User|~ada]",
        "[Bad|javascript:alert(1)]",
        "[Vbs|vbscript:msgbox(1)]",
        "[File|file:///etc/passwd]",
        "[Data|data:text/html,<script>alert(1)</script>]",
        "[Relative|/browse/DEMO-1]",
        "[Protocol|//evil.invalid/x]",
        "[Injected](<https://evil.invalid/x>)",
        "[bracketed]",
    )
)

WIKI_LINKS_MARKDOWN = (
    "\n".join(
        (
            "[Plain](<https://example.invalid/a?b=1&c=2>)",
            "[Bare](<https://example.invalid/a_(b)>)",
            "[https://example.invalid/only](<https://example.invalid/only>)",
            "`[unsupported Jira link target]` \\[DEMO-2\\]",
            "`[unsupported Jira link target]` \\[User\\|~ada\\]",
            "`[unsupported Jira link target]` \\[Bad\\|javascript:alert\\(1\\)\\]",
            "`[unsupported Jira link target]` \\[Vbs\\|vbscript:msgbox\\(1\\)\\]",
            "`[unsupported Jira link target]` \\[File\\|file:///etc/passwd\\]",
            "`[unsupported Jira link target]` "
            "\\[Data\\|data:text/html,\\<script\\>alert\\(1\\)\\</script\\>\\]",
            "`[unsupported Jira link target]` \\[Relative\\|/browse/DEMO-1\\]",
            "`[unsupported Jira link target]` \\[Protocol\\|//evil.invalid/x\\]",
            "\\[Injected\\]\\(\\<https://evil.invalid/x\\>\\)",
            "\\[bracketed\\]",
        )
    )
    + "\n"
)


def test_only_http_and_https_destinations_become_active_links() -> None:
    rendered = wiki_to_markdown(WIKI_LINKS)

    assert rendered == WIKI_LINKS_MARKDOWN
    assert "](<https://example.invalid/a?b=1&c=2>)" in rendered
    assert "](javascript" not in rendered
    assert "](<javascript" not in rendered
    assert "](vbscript" not in rendered
    assert "](file:" not in rendered
    assert "](data:" not in rendered
    assert "<script>" not in rendered
    assert "\\<script\\>" in rendered


WIKI_UNSUPPORTED = "\n".join(
    (
        "!screenshot.png!",
        "{panel:title=Notes}",
        "Inside *panel*.",
        "{panel}",
        "{color:#ff0000}red{color}",
    )
)

WIKI_UNSUPPORTED_MARKDOWN = (
    "\n".join(
        (
            "`[unsupported Jira image]` !screenshot.png!",
            "`[unsupported Jira macro panel]` {panel:title=Notes}",
            "Inside **panel**.",
            "`[unsupported Jira macro panel]` {panel}",
            "`[unsupported Jira macro color]` {color:#ff0000}red"
            "`[unsupported Jira macro color]` {color}",
        )
    )
    + "\n"
)


def test_a_literal_exclamation_never_turns_a_wiki_link_into_an_image() -> None:
    rendered = render_issue_markdown(
        {
            "key": "DEMO-10",
            "fields": {
                "description": "![Preview|https://example.invalid/tracker]",
                "comment": {
                    "comments": [
                        {
                            "id": 1,
                            "body": "![Preview|https://example.invalid/tracker]",
                        }
                    ]
                },
            },
            "renderedFields": {},
        },
        use_wiki=True,
    )

    assert rendered == (
        "# DEMO-10\n\n"
        "## Description\n\n"
        "\\![Preview](<https://example.invalid/tracker>)\n\n"
        "## Comments\n\n"
        "### Comment 1\n\n"
        "\\![Preview](<https://example.invalid/tracker>)\n"
    )
    assert re.search(r"(?<!\\)!\[Preview\]\(", rendered) is None
    assert rendered.count("\\![Preview](<https://example.invalid/tracker>)") == 2


def test_an_unsupported_image_literal_cannot_prefix_a_real_image() -> None:
    rendered = wiki_to_markdown(
        "!screenshot.png![Preview|https://example.invalid/tracker]"
    )

    assert rendered == (
        "`[unsupported Jira image]` !screenshot.png\\!"
        "[Preview](<https://example.invalid/tracker>)\n"
    )
    assert re.search(r"(?<!\\)!\[Preview\]\(", rendered) is None
    assert "!screenshot.png" in rendered


def test_unsupported_images_and_macros_are_labelled_and_kept_literal() -> None:
    rendered = wiki_to_markdown(WIKI_UNSUPPORTED)

    assert rendered == WIKI_UNSUPPORTED_MARKDOWN
    assert "**panel**" in rendered
    assert "![screenshot.png]" not in rendered


def test_unsupported_table_is_labelled_and_preserved_in_a_fence() -> None:
    rendered = wiki_to_markdown("||A||B||\n|1|2|\nafter")

    assert rendered == (
        "_Unsupported Jira table; showing it literally._\n\n"
        "```text\n"
        "||A||B||\n"
        "|1|2|\n"
        "```\n\n"
        "after\n"
    )


def test_unterminated_code_block_keeps_the_rest_verbatim() -> None:
    rendered = wiki_to_markdown(
        "Before\n{code:python}\nprint('x')\n*not bold*"
    )

    assert rendered == (
        "Before\n\n"
        "_Unterminated Jira code block; showing the rest literally._\n\n"
        "```python\n"
        "print('x')\n"
        "*not bold*\n"
        "```\n"
    )
    assert "**not bold**" not in rendered


def test_noformat_fence_is_longer_than_embedded_backticks() -> None:
    rendered = wiki_to_markdown("{noformat}\n```\n````\n{noformat}")

    assert rendered == "`````\n```\n````\n`````\n"


def test_code_block_content_is_literal() -> None:
    rendered = wiki_to_markdown(
        "{code}\n{{not code}} *not bold* [not|https://x.invalid]\n{code}"
    )

    assert rendered == (
        "```\n"
        "{{not code}} *not bold* [not|https://x.invalid]\n"
        "```\n"
    )
    assert "](<https" not in rendered


def test_empty_code_block_still_renders_a_fence() -> None:
    assert wiki_to_markdown("{code}{code}") == "```\n\n```\n"
    assert wiki_to_markdown("") == ""


def test_code_blocks_keep_multiple_boundary_blank_lines() -> None:
    assert wiki_to_markdown("{code}\n\n\nline\n\n\n{code}") == (
        "```\n\n\nline\n\n\n```\n"
    )
    assert wiki_to_markdown("{code:python}\n\n\nline\n\n\n{code}") == (
        "```python\n\n\nline\n\n\n```\n"
    )
    assert wiki_to_markdown("{noformat}\n\n\nline\n\n\n{noformat}") == (
        "```\n\n\nline\n\n\n```\n"
    )


def test_unterminated_code_block_keeps_boundary_blank_lines() -> None:
    assert wiki_to_markdown("{code}\n\n\nrest\n\n\n") == (
        "_Unterminated Jira code block; showing the rest literally._\n\n"
        "```\n\n\nrest\n\n\n```\n"
    )


def test_wiki_card_comment_keeps_code_boundary_blank_lines() -> None:
    rendered = render_issue_markdown(
        {
            "key": "DEMO-11",
            "fields": {
                "comment": {
                    "comments": [
                        {"id": 1, "body": "{code}\n\n\nline\n\n\n{code}"}
                    ]
                }
            },
            "renderedFields": {},
        },
        use_wiki=True,
    )

    assert rendered == (
        "# DEMO-11\n\n"
        "## Comments\n\n"
        "### Comment 1\n\n"
        "```\n\n\nline\n\n\n```\n"
    )


def test_prose_controls_are_never_raw_and_bidi_stays_visible() -> None:
    raw = "control \x1b[31m red\r\n\tindented\rnext ✓ \u202e"
    rendered = render_issue_markdown(
        {
            "key": "DEMO-8",
            "fields": {"summary": "Controls", "description": raw},
            "renderedFields": {},
        },
        use_wiki=True,
    )

    assert_no_raw_controls(rendered)
    assert "\x1b" not in rendered
    assert "\\u202e" in rendered
    assert "control \\[31m red\nindented next ✓ \\u202e" in rendered
    assert "✓" in rendered


def test_bidi_and_lone_surrogates_are_visible_in_metadata_and_wiki_text() -> None:
    rendered = render_issue_markdown(
        {
            "key": "DEMO-8",
            "fields": {
                "summary": f"Résumé {BIDI_CONTROLS} ✓",
                "description": f"raw {BIDI_CONTROLS} \udfff",
            },
            "renderedFields": {},
        },
        use_wiki=True,
    )

    assert_no_raw_controls(rendered)
    assert f"# DEMO-8: Résumé {BIDI_ESCAPES} ✓" in rendered
    assert f"raw {BIDI_ESCAPES} \\udfff" in rendered


def test_html_in_wiki_prose_is_escaped_not_rendered() -> None:
    rendered = wiki_to_markdown(
        "<script>alert(1)</script>\n<img src=x onerror=alert(1)>"
    )

    assert rendered == (
        "\\<script\\>alert\\(1\\)\\</script\\>\n"
        "\\<img src=x onerror=alert\\(1\\)\\>\n"
    )
    assert "<script>" not in rendered
    assert "<img" not in rendered


def test_wiki_comments_keep_order_and_mark_empty_bodies_explicitly() -> None:
    rendered = render_issue_markdown(
        {
            "key": "DEMO-9",
            "fields": {
                "comment": {
                    "total": 5,
                    "comments": [
                        {"id": 1, "author": {"displayName": "A"}, "body": "first"},
                        {"id": 2, "body": ""},
                        {"id": 3, "body": "third"},
                    ],
                }
            },
            "renderedFields": {},
        },
        use_wiki=True,
    )

    assert rendered == (
        "# DEMO-9\n\n"
        "## Comments\n\n"
        "_Comments are incomplete: showing 3 of 5._\n\n"
        "### Comment 1 · A\n\n"
        "first\n\n"
        "### Comment 2\n\n"
        "_Empty comment body._\n\n"
        "### Comment 3\n\n"
        "third\n"
    )
    first = rendered.index("### Comment 1")
    second = rendered.index("### Comment 2")
    third = rendered.index("### Comment 3")
    assert first < second < third


def test_wiki_mode_reads_only_raw_fields_and_ignores_rendered_html() -> None:
    rendered = render_issue_markdown(
        {
            "key": "DEMO-1",
            "fields": {},
            "renderedFields": {
                "description": "<p>rendered only</p>",
                "comment": {"comments": [{"id": 1, "body": "<p>rendered only</p>"}]},
            },
        },
        use_wiki=True,
    )

    assert rendered == "# DEMO-1\n"
    assert "rendered only" not in rendered


def test_empty_optional_fields_render_only_the_heading_in_wiki_mode() -> None:
    rendered = render_issue_markdown(
        {"key": "DEMO-1", "fields": {}, "renderedFields": None},
        use_wiki=True,
    )

    assert rendered == "# DEMO-1\n"


def test_a_bbk_style_card_gets_safe_links_and_fenced_code() -> None:
    rendered = wiki_to_markdown(
        "h2. Release notes\n"
        "\n"
        "*Important* change in _parser_. Use {{--flag}} now.\n"
        "\n"
        "[Spec|https://example.invalid/spec]\n"
        "\n"
        "{code:bash}\n"
        "atlawire issue DEMO-1 --wiki\n"
        "{code}"
    )

    assert rendered == (
        "## Release notes\n\n"
        "**Important** change in *parser*. Use `--flag` now.\n\n"
        "[Spec](<https://example.invalid/spec>)\n\n"
        "```bash\n"
        "atlawire issue DEMO-1 --wiki\n"
        "```\n"
    )


def test_wiki_renderer_rejects_non_text_input() -> None:
    with pytest.raises(AtlaWireError, match="wiki text"):
        wiki_to_markdown(1)  # type: ignore[arg-type]


def test_issue_renderer_rejects_a_non_boolean_wiki_flag() -> None:
    with pytest.raises(AtlaWireError, match="wiki option"):
        render_issue_markdown(issue(), use_wiki="yes")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ({"fields": {}}, "issue key"),
        ({"key": "DEMO-1"}, "fields"),
        (issue(fields={"summary": 1}), "summary"),
        (issue(fields={"status": "Open"}), "status"),
        (issue(renderedFields=[]), "renderedFields"),
        (issue(fields={"description": 1}), "description"),
        (issue(fields={"comment": []}), "comment"),
        (issue(fields={"comment": {"comments": "none"}}), "comment"),
        (issue(fields={"comment": {"comments": [None]}}), "comment"),
        (issue(fields={"comment": {"comments": [], "total": True}}), "total"),
        (issue(fields={"comment": {"comments": [], "total": -1}}), "total"),
        (issue(fields={"comment": {"comments": [{"body": 1}]}}), "body"),
        (issue(fields={"comment": {"comments": [{"author": "Ada"}]}}), "author"),
        (issue(fields={"comment": {"comments": [{"created": 1}]}}), "created"),
    ],
)
def test_wiki_mode_rejects_malformed_issue_shapes(
    value: dict[str, object], message: str
) -> None:
    with pytest.raises(AtlaWireError, match=message):
        render_issue_markdown(value, use_wiki=True)
