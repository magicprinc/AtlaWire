"""Render a fetched Confluence page as Markdown without extra effects.

Only the validated ``body.storage.value`` XHTML is converted. A link keeps its
readable label and a destination: ``ri:page`` becomes ``confluence:<title>``
(with ``#<anchor>`` when set), ``ri:attachment`` becomes ``attachment:<name>``
and ``ri:url`` keeps the original URL; a plain XHTML ``<a href>`` keeps its
destination (``http(s)``, a relative path or ``mailto:``) in an ordinary link.
An ``ac:image`` becomes a Markdown image. Macro parameters are shown next to
the macro name, so a parameter is never dropped; a parameter whose value is a
nested ``ri:attachment`` shows the attachment filename instead of an empty
value. An ``info``/``note``/``warning``/``tip``/``panel`` macro keeps its whole
body in a blockquote labelled with the panel type, and a ``status`` macro
becomes visible inline-code text. A macro without a dedicated rule shows a
readable marker. Storage that is too large or too deeply nested falls back to a
literal fenced block.
"""

import re
from dataclasses import dataclass
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
# Panel macros keep their whole body, so the type is visible as a label.
_PANEL_MACROS = frozenset({"info", "note", "warning", "tip", "panel"})
# A panel title that stays on the label line may not look like a Markdown block.
_BLOCK_LINE = re.compile(r"(?:[-*+] |[0-9]{1,9}[.)] |#{1,6} |```|\||> )")
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


@dataclass(frozen=True, slots=True)
class _Parameter:
    """One macro parameter: its name, readable value and whether it is a target."""

    name: str
    value: str
    reference: bool = False


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
        if normalized in _PANEL_MACROS:
            return _panel_macro(name, parameters, text)
        if normalized == "status":
            return _status_macro(name, parameters, text)
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

    def convert_a(self, el: object, text: str, parent_tags: set[str]) -> str:
        """Keep the destination of a plain XHTML anchor as a Markdown link.

        The shared helper drops every ``<a href>`` so fetched HTML cannot add
        active references; storage-format pages still use ordinary anchors for
        pasted links, relative paths and ``mailto:`` addresses, so this product
        rule keeps the label together with its destination.
        """
        label = text.strip()
        if not isinstance(el, Tag):
            return text
        href = _text_attribute(el, "href")
        if not href:
            return text
        shown = label or _label(href)
        return f"[{shown}]({_escaped_destination(href)})"


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


def _macro_parameters(el: Tag) -> list[_Parameter]:
    """Return parameters declared directly by this macro, in document order.

    A parameter that holds a nested reference element (``ri:attachment``) has no
    text of its own, so its filename is kept as the readable value and marked
    as a reference; without that its record would show a bare ``name=``.

    Only direct children are read: a nested macro owns its parameters, and its
    own conversion renders them once instead of repeating them in both records.
    """
    parameters: list[_Parameter] = []
    for parameter in el.find_all("ac:parameter", recursive=False):
        name = parameter.get("ac:name")
        shown_name = name if isinstance(name, str) else ""
        attachment = parameter.find("ri:attachment")
        if attachment is not None:
            filename = _text_attribute(attachment, "ri:filename")
            if filename:
                parameters.append(_Parameter(shown_name, filename, reference=True))
                continue
        parameters.append(_Parameter(shown_name, parameter.get_text()))
    return parameters


def _parameter_details(parameters: list[_Parameter]) -> str:
    """Render parameters into one visible ``name=value`` list."""
    details: list[str] = []
    for parameter in parameters:
        shown_name = _label(parameter.name)
        shown_value = (
            _escaped_destination(parameter.value, opaque=True)
            if parameter.reference
            else _label(parameter.value)
        )
        if shown_name:
            details.append(f"{shown_name}={shown_value}")
        elif shown_value:
            details.append(shown_value)
    return ", ".join(details)


def _macro_record(name: object, details: str, *, supported: bool) -> str:
    """Build a visible macro record; ``details`` keeps every parameter readable."""
    label = _shown_macro_name(name)
    title = f"{label} | {details}" if details else label
    prefix = "[Macro: " if supported else "[Unsupported macro: "
    return prefix + title + "]"


def _unrepresented_parameters(
    parameters: list[_Parameter],
) -> list[_Parameter]:
    """Keep parameters that are not already visible in the macro rendering."""
    return [
        parameter
        for parameter in parameters
        if one_line(parameter.name).lower() not in _CODE_PARAMETERS
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


def _code_info(parameters: list[_Parameter]) -> str:
    for parameter in parameters:
        if one_line(parameter.name).lower() != "language":
            continue
        label = one_line(parameter.value)
        return label if _LANGUAGE.fullmatch(label) else ""
    return ""


def _unsupported_macro(name: object, parameters: list[_Parameter], text: str) -> str:
    marker = _macro_record(name, _parameter_details(parameters), supported=False)
    body = text.strip()
    if body:
        return "\n\n" + marker + "\n\n" + body + "\n\n"
    return "\n\n" + marker + "\n\n"


def _shown_macro_name(name: object) -> str:
    """Return the escaped macro name, or the unnamed placeholder."""
    shown = _label(name) if isinstance(name, str) else ""
    return shown or _UNNAMED_MACRO


def _labelled_parameters(
    parameters: list[_Parameter], wanted: str
) -> tuple[str, list[_Parameter]]:
    """Split off the one parameter a macro shows as its visible label.

    Only the first matching parameter becomes the label; every other parameter
    stays in the record, so a panel or status macro never drops data it cannot
    show in the label itself.
    """
    label = ""
    rest: list[_Parameter] = []
    for parameter in parameters:
        if not label and one_line(parameter.name).lower() == wanted:
            label = one_line(parameter.value)
            continue
        rest.append(parameter)
    return label, rest


def _quote_line(line: str) -> str:
    """Prefix one line of a panel body with a blockquote marker."""
    return "> " + line if line.strip() else ">"


def _panel_macro(name: object, parameters: list[_Parameter], text: str) -> str:
    """Keep a panel body in a blockquote labelled with the panel type.

    A title parameter replaces the type name as the label, and every other
    parameter stays visible in a macro record before the quote.
    """
    title, extras = _labelled_parameters(parameters, "title")
    type_name = one_line(name).capitalize() if isinstance(name, str) else ""
    shown = _label(title) if title else _label(type_name) or _UNNAMED_MACRO
    details = _parameter_details(extras)
    marker = _macro_record(name, details, supported=True) + "\n\n" if details else ""
    head = f"> **{shown}:**"
    body = text.strip()
    if not body:
        return "\n\n" + marker + head + "\n\n"
    lines = body.splitlines()
    if _BLOCK_LINE.match(lines[0]):
        quoted = head + "\n" + _quote_line(lines[0])
    else:
        quoted = head + " " + lines[0]
    for line in lines[1:]:
        quoted += "\n" + _quote_line(line)
    return "\n\n" + marker + quoted + "\n\n"


def _inline_code(value: str) -> str:
    """Format literal text as one inline span, keeping embedded backticks."""
    content = one_line(value)
    longest = max((len(run) for run in re.findall(r"`+", content)), default=0)
    fence = "`" * (longest + 1)
    pad = " " if content[:1] in "` " or content[-1:] in "` " else ""
    return f"{fence}{pad}{content}{pad}{fence}"


def _status_macro(name: object, parameters: list[_Parameter], text: str) -> str:
    """Render a status macro as visible inline text next to its type.

    The title is the visible status value, so it stays inside the inline span
    without Markdown escaping; a parameter that is not the title is shown in a
    macro record, because the span has no room to present it readably.
    """
    title, extras = _labelled_parameters(parameters, "title")
    span = _inline_code(f"[STATUS] {title}" if title else "[STATUS]")
    details = _parameter_details(extras)
    pieces = [_macro_record(name, details, supported=True)] if details else []
    pieces.append(span)
    body = text.strip()
    if body:
        pieces.append(body)
    return " ".join(pieces)

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
