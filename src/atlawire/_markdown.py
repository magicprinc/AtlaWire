"""Neutral Markdown presentation helpers shared by product renderers.

The helpers only shape content that was already fetched: they never add links,
image destinations, or other references, and they keep user text from becoming
active Markdown or HTML. Product-specific element rules stay with each product.
"""

import re

from markdownify import MarkdownConverter

_CONTROLS = re.compile(
    r"[\x00-\x1f\x7f-\x9f\u200b-\u200f\u202a-\u202e\u2066-\u2069\ufeff\u2028\u2029]"
)
_C0_C1_CONTROLS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
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


def one_line(value: str) -> str:
    """Collapse data to one control-free line before it enters markup."""
    return " ".join(_CONTROLS.sub(" ", value).split())


def escape_controls(value: str) -> str:
    """Normalize line endings and make C0/C1 controls visible in Markdown."""
    text = value.replace("\r\n", "\n").replace("\r", "\n")
    return _C0_C1_CONTROLS.sub(lambda match: f"\\x{ord(match[0]):02x}", text)


def inline(value: str) -> str:
    """Escape data so Markdown renderers show it literally."""
    text = _MARKDOWN_SPECIALS.sub(r"\\\1", one_line(value))
    if text[:1] in "#-+=":
        return "\\" + text
    marker = _ORDERED_MARKER.match(text)
    if marker:
        return marker[1] + "\\" + text[len(marker[1]) :]
    return text


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
