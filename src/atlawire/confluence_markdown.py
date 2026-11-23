"""Render a fetched Confluence page as Markdown without extra effects.

Only the validated ``body.storage.value`` XHTML is converted. A link keeps its
readable label and a destination: ``ri:page`` becomes ``confluence:<title>``
(with ``#<anchor>`` when set), ``ri:attachment`` becomes ``attachment:<name>``
and ``ri:url`` keeps the original URL. An ``ac:image`` becomes a Markdown image.
Macro parameters are shown next to the macro name, so a parameter is never
dropped; a macro without a dedicated rule shows a readable marker. Storage that
is too large or too deeply nested falls back to a literal fenced block.
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
_UNNAMED_IMAGE = "image"
# ``language`` is already visible as the fence info string of a code macro.
_CODE_PARAMETERS = frozenset({"language"})
# Percent-encoding is applied only to characters that would end a Markdown
# destination or leak into neighbouring syntax; readable Unicode stays intact.
_DESTINATION_ESCAPES = {
    "\\": "%5C",
    "(": "%28",
    ")": "%29",
    "<": "%3C",
    ">": "%3E",
    "[": "%5B",
    "]": "%5D",
    "`": "%60",
    "|": "%7C",
    " ": "%20",
}
# ``#`` and ``?`` are literal text in the opaque ``confluence:`` and
# ``attachment:`` schemes, so they are escaped there as well.
_OPAQUE_ESCAPES = {**_DESTINATION_ESCAPES, "#": "%23", "?": "%3F"}


class _ConfluenceMarkdownConverter(SafeMarkdownConverter):
    """Storage-format rules for links, images, code macros and macro records."""

    def convert_ac_structured_macro(
        self, el: Tag, text: str, parent_tags: set[str]
    ) -> str:
        name = el.get("ac:name")
        normalized = name.strip().lower() if isinstance(name, str) else ""
        parameters = _macro_parameters(el)
        if normalized in {"code", "noformat"}:
            body = el.find("ac:plain-text-body")
            if body is not None:
                code = body.get_text()
                if code:
                    extras = _unrepresented_parameters(parameters)
                    details = _parameter_details(extras)
                    marker = (
                        _macro_record(name, details, supported=True) if details else ""
                    )
                    fence = fenced_block(code, _code_info(parameters))
                    return "\n\n" + (marker + "\n\n" if marker else "") + fence + "\n\n"
            return _code_fallback(text)
        return _unsupported_macro(name, parameters, text)

    def convert_ac_parameter(self, el: Tag, text: str, parent_tags: set[str]) -> str:
        # Parameters are rendered next to the macro name; emitting them here too
        # would duplicate every value inside the macro body.
        return ""

    def convert_ac_link(self, el: Tag, text: str, parent_tags: set[str]) -> str:
        label = text.strip()
        page = el.find("ri:page", recursive=False)
        if page is not None:
            title = _text_attribute(page, "ri:content-title")
            if title:
                shown = label or _label(title)
                anchor = _text_attribute(el, "ac:anchor")
                return f"[{shown}]({_page_destination(title, anchor)})"
        attachment = el.find("ri:attachment", recursive=False)
        if attachment is not None:
            filename = _text_attribute(attachment, "ri:filename")
            if filename:
                shown = label or _label(filename)
                return f"[{shown}]({_attachment_destination(filename)})"
        url = el.find("ri:url", recursive=False)
        if url is not None:
            value = _text_attribute(url, "ri:value")
            if value:
                shown = label or _label(value)
                return f"[{shown}]({_escaped_destination(value)})"
        user = el.find("ri:user", recursive=False)
        if user is not None:
            username = _text_attribute(user, "ri:username") or _text_attribute(
                user, "ri:userkey"
            )
            if username:
                return label or _label("@" + username)
        return label

    def convert_ac_image(self, el: Tag, text: str, parent_tags: set[str]) -> str:
        alt = _text_attribute(el, "ac:alt")
        alt_text = _label(alt) if alt else ""
        attachment = el.find("ri:attachment", recursive=False)
        if attachment is not None:
            filename = _text_attribute(attachment, "ri:filename")
            if filename:
                shown = alt_text or _label(filename)
                return f"![{shown}]({_attachment_destination(filename)})"
        url = el.find("ri:url", recursive=False)
        if url is not None:
            value = _text_attribute(url, "ri:value")
            if value:
                shown = alt_text or _UNNAMED_IMAGE
                return f"![{shown}]({_escaped_destination(value)})"
        return alt_text


def _text_attribute(tag: Tag, name: str) -> str:
    """Return one string attribute, treating missing or non-string data as absent."""
    value = tag.get(name)
    return value.strip() if isinstance(value, str) else ""


def _escaped_destination(value: str, *, opaque: bool = False) -> str:
    """Keep a destination readable while it cannot end the Markdown syntax.

    Whitespace, parentheses and the other characters that delimit or escape a
    destination are percent-encoded, so a title with spaces stays one link and
    cannot inject a second one. ``opaque`` additionally protects ``#`` and
    ``?``, which are plain text inside the ``confluence:``/``attachment:``
    schemes rather than a fragment or query.
    """
    escapes = _OPAQUE_ESCAPES if opaque else _DESTINATION_ESCAPES
    return "".join(escapes.get(char, char) for char in one_line(value))


def _page_destination(title: str, anchor: str) -> str:
    destination = "confluence:" + _escaped_destination(title, opaque=True)
    if not anchor:
        return destination
    return destination + "#" + _escaped_destination(anchor)


def _attachment_destination(filename: str) -> str:
    return "attachment:" + _escaped_destination(filename, opaque=True)


def _macro_parameters(el: Tag) -> list[tuple[str, str]]:
    """Return parameters declared directly by this macro, in document order.

    Only direct children are read: a nested macro owns its parameters, and its
    own conversion renders them once instead of repeating them in both records.
    """
    parameters: list[tuple[str, str]] = []
    for parameter in el.find_all("ac:parameter", recursive=False):
        name = parameter.get("ac:name")
        parameters.append((name if isinstance(name, str) else "", parameter.get_text()))
    return parameters


def _parameter_details(parameters: list[tuple[str, str]]) -> str:
    """Escape parameters into one visible ``name=value, ...`` list."""
    details: list[str] = []
    for name, value in parameters:
        shown_name = _label(name)
        shown_value = _label(value)
        if shown_name:
            details.append(f"{shown_name}={shown_value}")
        elif shown_value:
            details.append(shown_value)
    return ", ".join(details)


def _macro_record(name: object, details: str, *, supported: bool) -> str:
    """Build a visible macro record; ``details`` keeps every parameter readable."""
    shown = _label(name) if isinstance(name, str) else ""
    label = shown or _UNNAMED_MACRO
    title = f"{label} | {details}" if details else label
    prefix = "[Macro: " if supported else "[Unsupported macro: "
    return prefix + title + "]"


def _unrepresented_parameters(
    parameters: list[tuple[str, str]],
) -> list[tuple[str, str]]:
    """Keep parameters that are not already visible in the macro rendering."""
    return [
        (name, value)
        for name, value in parameters
        if one_line(name).lower() not in _CODE_PARAMETERS
    ]


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
    return ("# " + text).rstrip()


def _code_fallback(text: str) -> str:
    body = text.strip()
    if body:
        return "\n\n" + _CODE_FALLBACK + "\n\n" + body + "\n\n"
    return "\n\n" + _CODE_FALLBACK + "\n\n"


def _code_info(parameters: list[tuple[str, str]]) -> str:
    for name, value in parameters:
        if one_line(name).lower() != "language":
            continue
        label = one_line(value)
        return label if _LANGUAGE.fullmatch(label) else ""
    return ""


def _unsupported_macro(
    name: object, parameters: list[tuple[str, str]], text: str
) -> str:
    marker = _macro_record(name, _parameter_details(parameters), supported=False)
    body = text.strip()
    if body:
        return "\n\n" + marker + "\n\n" + body + "\n\n"
    return "\n\n" + marker + "\n\n"


def _literal_fallback(heading: str, marker: str, source: str) -> str:
    return heading + "\n\n" + marker + "\n\n" + fenced_block(source, "xml") + "\n"


def render_page_markdown(page: dict[str, object]) -> str:
    """Return a self-contained Markdown representation of a fetched page.

    The function is pure and performs no I/O. ``get_page`` must already have
    validated the page shape, so only the title and storage source are read. A
    missing or non-string title renders as a bare ``#`` heading instead of
    raising, so rendering never depends on optional metadata.
    """
    raw_title = page.get("title")
    title = raw_title if isinstance(raw_title, str) else ""
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
