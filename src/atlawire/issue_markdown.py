"""Render a fetched Jira issue as Markdown without extra network or file effects.

The default renderer converts only the HTML that Jira already returned in
``renderedFields``. It keeps link labels and image alt text but drops link and
image destinations, and escapes text that could otherwise become active
Markdown or HTML. An image without alt text has no visible text at all, so its
source is kept as inert, labelled literal text instead of vanishing, and a
rendered user mention keeps its account name next to the display name. Neither
becomes an active link or image. This is a readability measure, not a general
HTML sanitizer. Rendered comment bodies are used only for unambiguous ids; raw
descriptions or comments use a literal fenced text block. C0/C1 controls are
shown as visible escape sequences instead of raw bytes.
Wiki mode (``use_wiki=True``) instead reads the raw Jira wiki markup in
``fields.description`` and in every ``fields.comment`` body; ``renderedFields``
is then ignored. [wiki_to_markdown] supports a deliberately small subset:
headings, ``*bold*``, ``_italic_``, inline code, ``{code}``/``{noformat}``
blocks and http(s) links. Any other macro, image or table is shown literally
with an explicit label; list, quote and other inline styles stay escaped
literal text. Links are never followed, non-http(s) destinations never become
active Markdown, and all remaining prose is inline-escaped: layout C0 controls
are dropped, while bidi controls and lone surrogates become visible escapes.
"""

import re
from typing import NamedTuple
from urllib.parse import unquote

from atlawire._markdown import (
    SafeMarkdownConverter,
    convert_html,
    escape_controls,
    fenced_block,
    inline,
    one_line,
)
from atlawire.http import AtlaWireError

_ISO_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_CONVERSION_UNAVAILABLE = (
    "_Rendered Markdown conversion was unavailable; no raw fallback was available._"
)

# A rendered image without alt text and a user mention both lose data under the
# shared rules: the image has no visible text, and the mention keeps only the
# display name. These patterns recover the account name and keep the image
# source as labelled literal text, never as an active destination.
_PROFILE_LINK = re.compile(r"[?&]name=([^&#\s]{1,256})")
_USERNAME_LIMIT = 128
_IMAGE_REFERENCE = "`[Jira image]`"
_IMAGE_REFERENCE_PREFIX = _IMAGE_REFERENCE + " "

# Jira wiki rules kept intentionally narrow. Each pattern owns one syntax and
# there is no recursive parse: unsupported nesting stays literal text.
_WIKI_HEADING = re.compile(r"^ {0,3}h([1-6])\.\s*(.*)$")
# ``{code}``/``{noformat}`` open a block macro only when they are not the
# inner part of an inline ``{{code}}`` span: the lookbehind keeps the block
# scan from consuming the braces that belong to inline code.
_WIKI_CODE = re.compile(r"(?<!\{)\{code(?::(?P<params>[^}\n]{0,256}))?\}")
_WIKI_CODE_CLOSE = re.compile(r"\{code\}")
_WIKI_NOFORMAT = re.compile(r"(?<!\{)\{noformat\}")
_WIKI_NOFORMAT_CLOSE = re.compile(r"\{noformat\}")
_WIKI_LANGUAGE = re.compile(r"[A-Za-z0-9_+.#-]{1,32}")
_WIKI_SAFE_LINK = re.compile(
    r"https?://[A-Za-z0-9\-._~:/?#\[\]@!$&'()*+,;=%]+", re.IGNORECASE
)
_WIKI_ISSUE_LINK = re.compile(r"[A-Z][A-Z0-9_]*-[0-9]+")
_WIKI_INLINE = re.compile(
    r"\{\{(?P<code>[^{}\n]{0,4096}?)\}\}"
    r"|!(?P<image>[^!\s\n]{1,512})!"
    r"|\[(?P<link>[^\[\]\n]{0,2048})\]"
    r"|\{(?P<macro>[A-Za-z][A-Za-z0-9_-]{0,63})"
    r"(?::(?P<params>[^}\n]{0,256}))?\}"
    r"|(?<![\w])\*(?P<bold>[^*\n]{1,1000})\*(?![\w])"
    r"|(?<![\w])_(?P<italic>[^_\n]{1,1000})_(?![\w])"
)
_BACKTICKS = re.compile(r"`+")
_WIKI_EMPTY_COMMENT = "_Empty comment body._"


class _RenderedComments(NamedTuple):
    """Rendered comment bodies plus ids that cannot be safely attached."""

    bodies: dict[str, str]
    unavailable: set[str]
    ambiguous: set[str]


def _image_reference(source: str, label: str = "") -> str:
    """Show an image source as inert, labelled literal text.

    Markdown cannot show an image without loading its destination, which this
    renderer never does, and an image without alt text has no other visible
    text. Keeping the escaped source preserves the only data the image had.
    """
    reference = _IMAGE_REFERENCE
    if label:
        reference += " " + inline(label)
    return reference + " " + inline(source)


def _linked_image(text: str, attrs: dict[str, object]) -> str:
    """Keep the file name and address of an image that is a link child.

    A Jira attachment preview is ``<a title=... href=...><img .../></a>``: the
    anchor names the attachment while the inner image only shows a thumbnail.
    """
    title = attrs.get("title")
    if not isinstance(title, str) or not title.strip():
        return text
    remainder = text[len(_IMAGE_REFERENCE_PREFIX) :]
    if _IMAGE_REFERENCE in remainder:
        return text
    href = attrs.get("href")
    source = href.strip() if isinstance(href, str) and href.strip() else remainder
    return _image_reference(source, title.strip())


def _attr_text(value: object) -> str:
    """Read one HTML attribute, which a parser may split into a word list."""
    if isinstance(value, str):
        return value
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return " ".join(value)
    return ""


def _checked_username(name: str) -> str | None:
    """Accept one account name only when it is short, single-line and visible."""
    value = name.strip()
    if not value or len(value) > _USERNAME_LIMIT:
        return None
    if any(char.isspace() or not char.isprintable() for char in value):
        return None
    return value


def _user_name(attrs: dict[str, object]) -> str | None:
    """Return the account name of a rendered Jira profile link, if it is one."""
    href = _attr_text(attrs.get("href"))
    profile_class = "user-hover" in _attr_text(attrs.get("class")).split()
    if not profile_class and "ViewProfile.jspa" not in href:
        return None
    name = _checked_username(_attr_text(attrs.get("rel")))
    if name is not None:
        return name
    match = _PROFILE_LINK.search(href)
    if match is not None:
        return _checked_username(unquote(match[1]))
    return None


def _user_mention(text: str, username: str) -> str:
    """Keep the account name next to a rendered mention display name."""
    visible = text.strip()
    quoted = inline(username)
    if not visible:
        return f"~{quoted}"
    if username in visible or quoted in visible:
        return text
    return f"{text} ({quoted})"


class _IssueMarkdownConverter(SafeMarkdownConverter):
    """Keep image sources and user identities that the shared rules drop.

    [SafeMarkdownConverter] drops link and image destinations by design. That
    leaves an image without alt text with no text at all and a user mention
    with only the display name, so both are restored here as inert literal
    text: no link and no image destination is ever emitted.
    """

    def convert_img(self, el: object, text: str, parent_tags: set[str]) -> str:
        attrs = getattr(el, "attrs", {})
        alt = attrs.get("alt")
        if isinstance(alt, str) and alt.strip():
            return inline(alt)
        title = attrs.get("title")
        if isinstance(title, str) and title.strip():
            return inline(title)
        source = attrs.get("src")
        if isinstance(source, str) and source.strip():
            return _image_reference(source.strip())
        return ""

    def convert_a(self, el: object, text: str, parent_tags: set[str]) -> str:
        attrs = getattr(el, "attrs", {})
        username = _user_name(attrs)
        if username is not None:
            return _user_mention(text, username)
        if text.startswith(_IMAGE_REFERENCE_PREFIX):
            return _linked_image(text, attrs)
        return text


def _render_html(html: str) -> str | None:
    return convert_html(
        html,
        _IssueMarkdownConverter(escape_misc=True, heading_style="atx", bullets="-"),
    )


def _field_name(fields: dict[str, object], field: str, label: str) -> str | None:
    value = fields.get(field)
    if value is None:
        return None
    if not isinstance(value, dict):
        raise AtlaWireError(f"Invalid Jira {label} in the issue.")
    name = value.get("displayName" if field == "assignee" else "name")
    if name is None:
        return None
    if not isinstance(name, str):
        raise AtlaWireError(f"Invalid Jira {label} in the issue.")
    return one_line(name)


def _comment_id(value: object) -> str | None:
    """Return a comparable id for strings and integers, but never for booleans."""
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        return value or None
    if isinstance(value, int):
        return str(value)
    return None


def _rendered_comments(rendered_fields: dict[str, object]) -> _RenderedComments:
    result = _RenderedComments({}, set(), set())
    container = rendered_fields.get("comment")
    if container is None:
        return result
    if not isinstance(container, dict):
        raise AtlaWireError("Invalid Jira rendered comment in the issue.")
    entries = container.get("comments")
    if entries is None:
        return result
    if not isinstance(entries, list):
        raise AtlaWireError("Invalid Jira rendered comment in the issue.")
    by_id: dict[str, list[str | None]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise AtlaWireError("Invalid Jira rendered comment in the issue.")
        body = entry.get("body")
        if body is not None and not isinstance(body, str):
            raise AtlaWireError("Invalid Jira rendered comment body in the issue.")
        key = _comment_id(entry.get("id"))
        if key is None:
            continue
        by_id.setdefault(key, []).append(body)
    for key, bodies in by_id.items():
        if len(bodies) > 1:
            result.ambiguous.add(key)
            continue
        body = bodies[0]
        if body is None:
            continue
        rendered = _render_html(body)
        if rendered is None:
            result.unavailable.add(key)
        elif rendered:
            result.bodies[key] = rendered
    return result


def _comments(
    fields: dict[str, object],
) -> tuple[list[dict[str, object]], int | None]:
    container = fields.get("comment")
    if container is None:
        return [], None
    if not isinstance(container, dict):
        raise AtlaWireError("Invalid Jira comment field in the issue.")
    entries = container.get("comments")
    if entries is None:
        entries = []
    if not isinstance(entries, list):
        raise AtlaWireError("Invalid Jira comment field in the issue.")
    comments: list[dict[str, object]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise AtlaWireError("Invalid Jira comment in the issue.")
        comments.append(entry)
    total = container.get("total")
    if total is None:
        return comments, None
    if not isinstance(total, int) or isinstance(total, bool) or total < 0:
        raise AtlaWireError("Invalid Jira comment total in the issue.")
    if total < len(comments):
        raise AtlaWireError("Inconsistent Jira comment total in the issue.")
    return comments, total


def _description(
    fields: dict[str, object], rendered_fields: dict[str, object]
) -> str | None:
    raw_value = fields.get("description")
    if raw_value is not None and not isinstance(raw_value, str):
        raise AtlaWireError("Invalid Jira description in the issue.")
    conversion_failed = False
    rendered_value = rendered_fields.get("description")
    if rendered_value is not None:
        if not isinstance(rendered_value, str):
            raise AtlaWireError("Invalid Jira rendered description in the issue.")
        rendered = _render_html(rendered_value)
        if rendered:
            return rendered
        conversion_failed = rendered is None
    if raw_value is not None and raw_value.strip():
        return fenced_block(raw_value, "text")
    if conversion_failed:
        return _CONVERSION_UNAVAILABLE
    return None


def _author(entry: dict[str, object]) -> str | None:
    value = entry.get("author")
    if value is None:
        return None
    if not isinstance(value, dict):
        raise AtlaWireError("Invalid Jira comment author in the issue.")
    name = value.get("displayName")
    if name is None:
        return None
    if not isinstance(name, str):
        raise AtlaWireError("Invalid Jira comment author in the issue.")
    return one_line(name)


def _created(entry: dict[str, object]) -> str | None:
    value = entry.get("created")
    if value is None:
        return None
    if not isinstance(value, str):
        raise AtlaWireError("Invalid Jira comment created date in the issue.")
    text = one_line(value)
    return text[:10] if _ISO_DATE.match(text) else text


def _ambiguous_raw_ids(comments: list[dict[str, object]]) -> set[str]:
    seen: set[str] = set()
    ambiguous: set[str] = set()
    for entry in comments:
        key = _comment_id(entry.get("id"))
        if key is None:
            continue
        if key in seen:
            ambiguous.add(key)
        else:
            seen.add(key)
    return ambiguous


def _comment_title(index: int, entry: dict[str, object]) -> str:
    title = [f"Comment {index}"]
    author = _author(entry)
    if author:
        title.append(inline(author))
    created = _created(entry)
    if created:
        title.append(inline(created))
    return "### " + " · ".join(title)


def _comment(
    index: int,
    entry: dict[str, object],
    rendered: _RenderedComments,
    ambiguous_raw: set[str],
) -> str:
    body = entry.get("body")
    if body is None:
        body = ""
    if not isinstance(body, str):
        raise AtlaWireError("Invalid Jira comment body in the issue.")
    key = _comment_id(entry.get("id"))
    ambiguous = key is not None and (key in ambiguous_raw or key in rendered.ambiguous)
    rendered_text = None if key is None or ambiguous else rendered.bodies.get(key)
    unavailable = key is not None and not ambiguous and key in rendered.unavailable
    if rendered_text:
        content = rendered_text
    elif unavailable and not body.strip():
        content = _CONVERSION_UNAVAILABLE
    else:
        content = fenced_block(body, "text")
    return _comment_title(index, entry) + "\n\n" + content


class _WikiPart(NamedTuple):
    """One plain text run or one code-like macro from Jira wiki markup."""

    value: str
    macro: str | None = None
    info: str = ""
    terminated: bool = True


def _wiki_language(params: str | None) -> str:
    """Return a safe info string for a ``{code}`` language parameter."""
    if not params:
        return ""
    parts = [part.strip() for part in params.split("|")]
    language = ""
    for part in parts:
        if part.lower().startswith("language="):
            language = part.split("=", 1)[1].strip()
            break
    else:
        language = parts[0] if parts else ""
    return language if _WIKI_LANGUAGE.fullmatch(language) else ""


def _wiki_parts(text: str) -> list[_WikiPart]:
    """Split text around ``{code}`` and ``{noformat}`` blocks.

    An opener without a closing macro consumes the rest of the input and keeps
    its ``terminated`` flag false, so no code is silently dropped.
    """
    parts: list[_WikiPart] = []
    position = 0
    while position < len(text):
        code = _WIKI_CODE.search(text, position)
        plain = _WIKI_NOFORMAT.search(text, position)
        if plain is not None and (code is None or plain.start() < code.start()):
            match = plain
            macro = "noformat"
            closer = _WIKI_NOFORMAT_CLOSE
            info = ""
        elif code is not None:
            match = code
            macro = "code"
            closer = _WIKI_CODE_CLOSE
            info = _wiki_language(match["params"])
        else:
            parts.append(_WikiPart(text[position:]))
            break
        if match.start() > position:
            parts.append(_WikiPart(text[position : match.start()]))
        closing = closer.search(text, match.end())
        if closing is None:
            parts.append(_WikiPart(text[match.end() :], macro, info, terminated=False))
            break
        parts.append(_WikiPart(text[match.end() : closing.start()], macro, info))
        position = closing.end()
    return parts


def _code_content(value: str) -> str:
    """Drop only the line break that ends the opener line, keeping blank lines.

    Jira writes ``{code}`` on its own line, so the first newline is structural.
    Every later newline, including trailing ones, is code content and is kept.
    """
    content = escape_controls(value)
    return content.removeprefix("\n")


def _code_span(content: str) -> str:
    """Format one inline code span without losing embedded backticks."""
    content = escape_controls(content).replace("\n", " ")
    if not content:
        return "`[empty Jira inline code]`"
    longest = max((len(run) for run in _BACKTICKS.findall(content)), default=0)
    fence = "`" * (longest + 1)
    pad = " " if content[:1] in "` " or content[-1:] in "` " else ""
    return f"{fence}{pad}{content}{pad}{fence}"


def _wiki_unsupported(kind: str, literal: str) -> str:
    """Keep an unsupported construct visible, inert and explicitly labelled."""
    return f"`[unsupported Jira {kind}]` {inline(literal)}"


def _wiki_unsupported_block(kind: str, literal: str) -> str:
    label = f"_Unsupported Jira {kind}; showing it literally._"
    return label + "\n\n" + fenced_block(literal, "text")


def _wiki_link(body: str) -> str:
    """Render one bracketed Jira link, or label its unsupported destination."""
    label, separator, target = body.partition("|")
    if separator:
        target = target.strip()
        if _WIKI_SAFE_LINK.fullmatch(target):
            text = inline(label.strip() or target)
            return f"[{text}](<{target}>)"
        return _wiki_unsupported("link target", f"[{body}]")
    target = body.strip()
    if _WIKI_SAFE_LINK.fullmatch(target):
        return f"[{inline(target)}](<{target}>)"
    if body.startswith(("~", "^")) or _WIKI_ISSUE_LINK.fullmatch(target):
        return _wiki_unsupported("link target", f"[{body}]")
    return inline(f"[{body}]")


def _wiki_gap(text: str) -> str:
    """Escape text between two inline tokens, keeping the separating spaces."""
    escaped = inline(text)
    if not escaped:
        return " " if text else ""
    if text[:1].isspace():
        escaped = " " + escaped
    if text[-1:].isspace():
        escaped += " "
    return escaped


def _escape_image_opener(pieces: list[str]) -> None:
    """Keep a literal ``!`` before a link from forming a Markdown image.

    The visible exclamation stays, but it becomes ``\\!`` so the following
    ``[label](<url>)`` is parsed as a link rather than an image.
    """
    if pieces and pieces[-1].endswith("!"):
        pieces[-1] = pieces[-1][:-1] + "\\!"


def _wiki_inline(text: str) -> str:
    """Escape one line of wiki text, converting only the supported inline forms."""
    pieces: list[str] = []
    position = 0
    for match in _WIKI_INLINE.finditer(text):
        if match.start() > position:
            pieces.append(_wiki_gap(text[position : match.start()]))
        if match["code"] is not None:
            pieces.append(_code_span(match["code"]))
        elif match["image"] is not None:
            pieces.append(_wiki_unsupported("image", match[0]))
        elif match["link"] is not None:
            _escape_image_opener(pieces)
            pieces.append(_wiki_link(match["link"]))
        elif match["macro"] is not None:
            name = match["macro"]
            pieces.append(_wiki_unsupported(f"macro {name}", match[0]))
        elif match["bold"] is not None:
            pieces.append(f"**{inline(match['bold'])}**")
        else:
            pieces.append(f"*{inline(match['italic'])}*")
        position = match.end()
    if position < len(text):
        tail = text[position:]
        escaped = inline(tail)
        if escaped and tail[:1].isspace():
            escaped = " " + escaped
        pieces.append(escaped)
    return "".join(pieces)


def _flush_paragraph(paragraph: list[str], blocks: list[str]) -> None:
    if paragraph:
        blocks.append("\n".join(paragraph))
        paragraph.clear()


def _wiki_text_blocks(text: str) -> list[str]:
    """Render headings, tables and paragraph lines from a plain wiki run."""
    blocks: list[str] = []
    paragraph: list[str] = []
    lines = text.split("\n")
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            _flush_paragraph(paragraph, blocks)
            index += 1
            continue
        heading = _WIKI_HEADING.match(line)
        if heading is not None:
            _flush_paragraph(paragraph, blocks)
            body = _wiki_inline(heading[2].strip())
            blocks.append("#" * int(heading[1]) + (f" {body}" if body else ""))
            index += 1
            continue
        if line.lstrip().startswith("|"):
            _flush_paragraph(paragraph, blocks)
            start = index
            while index < len(lines) and lines[index].lstrip().startswith("|"):
                index += 1
            blocks.append(
                _wiki_unsupported_block("table", "\n".join(lines[start:index]))
            )
            continue
        rendered_line = _wiki_inline(line)
        if rendered_line:
            paragraph.append(rendered_line)
        index += 1
    _flush_paragraph(paragraph, blocks)
    return blocks


def wiki_to_markdown(text: str) -> str:
    """Render Jira wiki markup read-only, without fetching or executing anything.

    Supported syntax is intentionally small: ``h1.``-``h6.`` headings,
    ``*bold*``, ``_italic_``, ``{{inline code}}``, ``{code}``/``{code:lang}``
    and ``{noformat}`` blocks, and ``[label|http(s) URL]`` or bare ``[URL]``
    links. A ``[label|target]`` whose target is not http(s) is shown literally
    with a label; the same applies to images, other macros and tables. Nested
    or other inline styles stay literal text. Code blocks drop only the line
    break ending the opener line, so blank content lines are preserved. An
    unterminated code block keeps the remaining input in a labelled fence. The
    result ends with one newline unless the input has no renderable content.
    """
    if not isinstance(text, str):
        raise AtlaWireError("Expected Jira wiki text.")
    blocks: list[str] = []
    for part in _wiki_parts(text):
        if part.macro is None:
            blocks.extend(_wiki_text_blocks(part.value))
            continue
        content = _code_content(part.value)
        if part.terminated:
            blocks.append(fenced_block(content, part.info))
            continue
        label = f"_Unterminated Jira {part.macro} block; showing the rest literally._"
        blocks.append(label + "\n\n" + fenced_block(content, part.info))
    rendered = "\n\n".join(blocks)
    if not rendered:
        return ""
    return escape_controls(rendered.strip()) + "\n"


def _wiki_description(fields: dict[str, object]) -> str | None:
    value = fields.get("description")
    if value is None:
        return None
    if not isinstance(value, str):
        raise AtlaWireError("Invalid Jira description in the issue.")
    if not value.strip():
        return None
    return wiki_to_markdown(value).rstrip("\n")


def _wiki_comment(index: int, entry: dict[str, object]) -> str:
    body = entry.get("body")
    if body is None:
        body = ""
    if not isinstance(body, str):
        raise AtlaWireError("Invalid Jira comment body in the issue.")
    if body.strip():
        content = wiki_to_markdown(body).rstrip("\n")
    else:
        content = _WIKI_EMPTY_COMMENT
    return _comment_title(index, entry) + "\n\n" + content


def _comment_blocks(
    fields: dict[str, object],
    rendered_fields: dict[str, object],
    use_wiki: bool,
) -> list[str]:
    """Render the comment section; wiki mode reads raw bodies only."""
    rendered_comments: _RenderedComments | None = (
        None if use_wiki else _rendered_comments(rendered_fields)
    )
    comments, total = _comments(fields)
    ambiguous_raw: set[str] = set() if use_wiki else _ambiguous_raw_ids(comments)
    if not (comments or (total is not None and total > 0)):
        return []
    blocks = ["## Comments"]
    if total is not None and total > len(comments):
        blocks.append(f"_Comments are incomplete: showing {len(comments)} of {total}._")
    if use_wiki:
        blocks.extend(
            _wiki_comment(index, entry) for index, entry in enumerate(comments, 1)
        )
    elif rendered_comments is not None:
        blocks.extend(
            _comment(index, entry, rendered_comments, ambiguous_raw)
            for index, entry in enumerate(comments, 1)
        )
    return blocks


def _metadata(fields: dict[str, object]) -> str:
    return " · ".join(
        f"**{label}:** {inline(value)}"
        for label, value in (
            ("Status", _field_name(fields, "status", "status")),
            ("Type", _field_name(fields, "issuetype", "type")),
            ("Priority", _field_name(fields, "priority", "priority")),
            ("Assignee", _field_name(fields, "assignee", "assignee")),
        )
        if value
    )


def render_issue_markdown(issue: dict[str, object], *, use_wiki: bool = False) -> str:
    """Return a self-contained Markdown representation of a fetched issue.

    The function is pure: it reads the issue mapping and performs no I/O. A
    rendered body is matched to a raw comment by id, not by list position.
    Missing or empty rendered bodies fall back to literal fenced raw text.

    With ``use_wiki`` the raw description and every raw comment body are
    rendered as Jira wiki markup instead of the HTML in ``renderedFields``;
    that field is still shape-checked but supplies no content. Comments keep
    their original order and are never dropped.
    """
    if not isinstance(use_wiki, bool):
        raise AtlaWireError("Expected a boolean wiki option.")
    if not isinstance(issue, dict):
        raise AtlaWireError("Expected a Jira issue object.")
    key = issue.get("key")
    if not isinstance(key, str) or not key:
        raise AtlaWireError("Expected a non-empty Jira issue key.")
    fields = issue.get("fields")
    if not isinstance(fields, dict):
        raise AtlaWireError("Expected Jira issue fields.")
    rendered_fields = issue.get("renderedFields")
    if rendered_fields is None:
        rendered_fields = {}
    if not isinstance(rendered_fields, dict):
        raise AtlaWireError("Invalid Jira renderedFields in the issue.")

    summary_value = fields.get("summary")
    if summary_value is None:
        summary = ""
    elif isinstance(summary_value, str):
        summary = one_line(summary_value)
    else:
        raise AtlaWireError("Invalid Jira summary in the issue.")

    heading = "# " + inline(key)
    if summary:
        heading += ": " + inline(summary)
    blocks = [heading]

    metadata = _metadata(fields)
    if metadata:
        blocks.append(metadata)

    description = (
        _wiki_description(fields) if use_wiki else _description(fields, rendered_fields)
    )
    if description:
        blocks.extend(("## Description", description))

    blocks.extend(_comment_blocks(fields, rendered_fields, use_wiki))
    return escape_controls("\n\n".join(blocks) + "\n")
