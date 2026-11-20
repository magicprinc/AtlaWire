"""Render a fetched Jira issue as Markdown without extra network or file effects.

The renderer converts only the HTML that Jira already returned in
``renderedFields``. It keeps link labels and image alt text but drops link and
image destinations, and escapes text that could otherwise become active
Markdown or HTML. This is a readability measure, not a general HTML sanitizer.
Rendered comment bodies are used only for unambiguous ids; raw descriptions or
comments use a literal fenced text block. C0/C1 controls are shown as visible
escape sequences instead of raw bytes.
"""

import re
from typing import NamedTuple

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


class _RenderedComments(NamedTuple):
    """Rendered comment bodies plus ids that cannot be safely attached."""

    bodies: dict[str, str]
    unavailable: set[str]
    ambiguous: set[str]


def _render_html(html: str) -> str | None:
    return convert_html(
        html,
        SafeMarkdownConverter(escape_misc=True, heading_style="atx", bullets="-"),
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
    title = [f"Comment {index}"]
    author = _author(entry)
    if author:
        title.append(inline(author))
    created = _created(entry)
    if created:
        title.append(inline(created))
    return "### " + " · ".join(title) + "\n\n" + content


def render_issue_markdown(issue: dict[str, object]) -> str:
    """Return a self-contained Markdown representation of a fetched issue.

    The function is pure: it reads the issue mapping and performs no I/O. A
    rendered body is matched to a raw comment by id, not by list position.
    Missing or empty rendered bodies fall back to literal fenced raw text.
    """
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

    metadata = [
        f"**{label}:** {inline(value)}"
        for label, value in (
            ("Status", _field_name(fields, "status", "status")),
            ("Type", _field_name(fields, "issuetype", "type")),
            ("Priority", _field_name(fields, "priority", "priority")),
            ("Assignee", _field_name(fields, "assignee", "assignee")),
        )
        if value
    ]
    if metadata:
        blocks.append(" · ".join(metadata))

    description = _description(fields, rendered_fields)
    if description:
        blocks.extend(("## Description", description))

    rendered_comments = _rendered_comments(rendered_fields)
    comments, total = _comments(fields)
    ambiguous_raw = _ambiguous_raw_ids(comments)
    if comments or (total is not None and total > 0):
        blocks.append("## Comments")
        if total is not None and total > len(comments):
            blocks.append(
                f"_Comments are incomplete: showing {len(comments)} of {total}._"
            )
        blocks.extend(
            _comment(index, entry, rendered_comments, ambiguous_raw)
            for index, entry in enumerate(comments, 1)
        )

    return escape_controls("\n\n".join(blocks) + "\n")
