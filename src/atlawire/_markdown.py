"""Neutral Markdown presentation helpers shared by product renderers.

The helpers only shape content that was already fetched: they never add links,
image destinations, or other references, and they keep user text from becoming
active Markdown or HTML. Product-specific element rules stay with each product.
"""

import re

from markdownify import MarkdownConverter

# Only layout-only controls are folded into a space before text enters one
# line. Bidi controls are visually escaped instead, and zero-width joiners are
# ordinary text shaping (emoji sequences, Indic/Persian text), so they stay.
_CONTROLS = re.compile(r"[\x00-\x1f\x7f-\x9f\u2028\u2029\ufeff]")
# Bidi controls and lone surrogates are invisible or unpresentable. They are
# replaced with an ASCII escape sequence wherever they would reach human
# output; ordinary Unicode is left untouched.
_VISIBLE_ESCAPES = r"\u061c\u200e\u200f\u202a-\u202e\u2066-\u2069\ud800-\udfff"
_UNSAFE_VISIBLE = re.compile(rf"[{_VISIBLE_ESCAPES}]")
_ESCAPED_CONTROLS = re.compile(
    rf"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\u2028\u2029{_VISIBLE_ESCAPES}]"
)
_MARKDOWN_SPECIALS = re.compile(r"([\\`*_\[\]<>~&|()])")
_ORDERED_MARKER = re.compile(r"([0-9]{1,9})([.)])(?=\s|$)")
_BACKTICKS = re.compile(r"`+")


class SafeMarkdownConverter(MarkdownConverter):
    """Markdownify variant that never emits active links or image URLs."""

    def convert_a(self, el: object, text: str, parent_tags: set[str]) -> str:
        return text

    def convert_img(self, el: object, text: str, parent_tags: set[str]) -> str:
        alt = getattr(el, "attrs", {}).get("alt")
        if not isinstance(alt, str):
            return ""
        return inline(alt)

    def convert_video(self, el: object, text: str, parent_tags: set[str]) -> str:
        return text

    def convert_pre(self, el: object, text: str, parent_tags: set[str]) -> str:
        if not text:
            return ""
        return "\n\n" + fenced_block(text.strip("\n")) + "\n\n"


def _visible_escape(match: re.Match[str]) -> str:
    """Render one unsafe code point as visible ASCII (``\\u202e``)."""
    code = ord(match[0])
    return f"\\x{code:02x}" if code <= 0xFF else f"\\u{code:04x}"


def one_line(value: str) -> str:
    """Collapse data to one line, removing layout-only controls.

    Bidi controls and lone surrogates are preserved here so [inline] can show
    them as escape sequences after Markdown punctuation is escaped. Callers
    that do not use [inline] must escape the result before human output.
    """
    return " ".join(_CONTROLS.sub(" ", value).split())


def escape_controls(value: str) -> str:
    """Normalize line endings and make unsafe controls visible in Markdown.

    C0/C1, bidi, line-separator and surrogate code points become ``\\xNN`` or
    ``\\uNNNN`` text; ordinary Unicode and layout whitespace are preserved.
    """
    text = value.replace("\r\n", "\n").replace("\r", "\n")
    return _ESCAPED_CONTROLS.sub(_visible_escape, text)


def inline(value: str) -> str:
    """Escape data so Markdown renderers show it literally."""
    text = _MARKDOWN_SPECIALS.sub(r"\\\1", one_line(value))
    if text[:1] in "#-+=":
        text = "\\" + text
    else:
        marker = _ORDERED_MARKER.match(text)
        if marker:
            text = marker[1] + "\\" + text[len(marker[1]) :]
    return _UNSAFE_VISIBLE.sub(_visible_escape, text)


def fenced_block(content: str, info: str = "") -> str:
    """Fence literal text with a delimiter longer than any backtick run in it."""
    content = escape_controls(content)
    longest = max((len(match) for match in _BACKTICKS.findall(content)), default=0)
    fence = "`" * max(3, longest + 1)
    body = content if content.endswith("\n") else content + "\n"
    return f"{fence}{info}\n{body}{fence}"


def convert_html(html: str, converter: MarkdownConverter) -> str | None:
    """Convert HTML to control-free Markdown, or None on converter recursion."""
    try:
        converted = converter.convert(html)
    except RecursionError:
        return None
    return escape_controls(converted.strip())
