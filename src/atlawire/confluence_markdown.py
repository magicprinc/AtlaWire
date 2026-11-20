"""Render a fetched Confluence page as Markdown without extra effects.

Only the validated ``body.storage.value`` XHTML is converted. Link and image
destinations are never emitted, macro parameters are omitted, and a macro
without a dedicated rule shows a readable marker plus its rich body. Storage
that is too large or too deeply nested falls back to a literal fenced block.
"""

import re
from typing import cast

from bs4 import Tag

from atlawire._markdown import (
    SafeMarkdownConverter,
    convert_html,
    fenced_block,
    inline,
    one_line,
)

# Conversion is linear for normal pages; this only bounds pathological input.
_MAX_STORAGE_CHARS = 1_000_000
_LANGUAGE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_+#.-]{0,31}")
_TRAILING_ATX = re.compile(r"(?<=\s)(#+)$")
_SIZE_FALLBACK = (
    "_Page storage is too large to convert; the raw storage source follows._"
)
_RECURSION_FALLBACK = (
    "_Page storage is nested too deeply to convert; the raw storage source follows._"
)
_CODE_FALLBACK = "_Code conversion fallback: no plain-text code payload was available._"
_UNNAMED_MACRO = "unknown"


class _ConfluenceMarkdownConverter(SafeMarkdownConverter):
    """Storage-format rules for code macros and readable macro fallbacks."""

    def convert_ac_structured_macro(
        self, el: Tag, text: str, parent_tags: set[str]
    ) -> str:
        name = el.get("ac:name")
        normalized = name.strip().lower() if isinstance(name, str) else ""
        if normalized in {"code", "noformat"}:
            body = el.find("ac:plain-text-body")
            if body is not None:
                code = body.get_text()
                if code:
                    return "\n\n" + fenced_block(code, _code_info(el)) + "\n\n"
            return _code_fallback(text)
        return _unsupported_macro(name, text)

    def convert_ac_parameter(self, el: Tag, text: str, parent_tags: set[str]) -> str:
        # Parameters are metadata; macro bodies are the only readable content.
        return ""

    def convert_ac_link(self, el: Tag, text: str, parent_tags: set[str]) -> str:
        label = text.strip()
        if label:
            return label
        for tag_name, attribute in (
            ("ri:page", "ri:content-title"),
            ("ri:attachment", "ri:filename"),
        ):
            target = el.find(tag_name)
            value = target.get(attribute) if target is not None else None
            if isinstance(value, str):
                label = _label(value)
                if label:
                    return label
        user = el.find("ri:user")
        if user is not None:
            name = user.get("ri:username") or user.get("ri:userkey")
            if isinstance(name, str) and name.strip():
                return _label("@" + name.strip())
        return ""

    def convert_ac_image(self, el: Tag, text: str, parent_tags: set[str]) -> str:
        alt = el.get("ac:alt")
        return _label(alt) if isinstance(alt, str) else ""


def _label(value: str) -> str:
    """Escape a visible label, treating whitespace-only data as absent."""
    text = one_line(value)
    return inline(text) if text else ""


def _heading(title: str) -> str:
    """Build an ATX heading without losing literal trailing hash characters."""
    text = _label(title)
    trailing = _TRAILING_ATX.search(text)
    if trailing:
        text = text[: trailing.start()] + trailing[1].replace("#", "\\#")
    return "# " + text


def _code_fallback(text: str) -> str:
    body = text.strip()
    if body:
        return "\n\n" + _CODE_FALLBACK + "\n\n" + body + "\n\n"
    return "\n\n" + _CODE_FALLBACK + "\n\n"


def _code_info(el: Tag) -> str:
    parameter = el.find("ac:parameter", {"ac:name": "language"})
    if parameter is None:
        return ""
    label = one_line(parameter.get_text())
    return label if _LANGUAGE.fullmatch(label) else ""


def _unsupported_macro(name: object, text: str) -> str:
    shown = _label(name) if isinstance(name, str) else ""
    marker = f"[Unsupported macro: {shown or _UNNAMED_MACRO}]"
    body = text.strip()
    if body:
        return "\n\n" + marker + "\n\n" + body + "\n\n"
    return "\n\n" + marker + "\n\n"


def _literal_fallback(heading: str, marker: str, source: str) -> str:
    return heading + "\n\n" + marker + "\n\n" + fenced_block(source, "xml") + "\n"


def render_page_markdown(page: dict[str, object]) -> str:
    """Return a self-contained Markdown representation of a fetched page.

    The function is pure and performs no I/O. ``get_page`` must already have
    validated the page shape, so only the title and storage source are read.
    """
    title = cast(str, page["title"])
    body = cast(dict[str, object], page["body"])
    storage = cast(dict[str, object], body["storage"])
    source = cast(str, storage["value"])

    heading = _heading(title)
    if not source.strip():
        return heading + "\n"
    if len(source) > _MAX_STORAGE_CHARS:
        return _literal_fallback(heading, _SIZE_FALLBACK, source)
    rendered = convert_html(
        source,
        _ConfluenceMarkdownConverter(
            escape_misc=True,
            heading_style="atx",
            bullets="-",
        ),
    )
    if rendered is None:
        return _literal_fallback(heading, _RECURSION_FALLBACK, source)
    if not rendered:
        return heading + "\n"
    return heading + "\n\n" + rendered + "\n"
