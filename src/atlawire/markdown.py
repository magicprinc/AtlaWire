"""Public Markdown and compaction helpers.

These are the conversion layer without a product client: callers pass text or an
already fetched document and receive Markdown or a compact JSON projection. No
function here performs I/O, fetches a link, or executes a macro.

The converters are the same ones the product commands use, so an agent gets one
consistent rendering whether it calls the CLI or the library.
"""

import json
from collections.abc import Mapping
from typing import Any

from atlawire._markdown import SafeMarkdownConverter, convert_html
from atlawire.confluence_markdown import render_page_markdown, render_storage_markdown
from atlawire.issue_markdown import render_issue_markdown, wiki_to_markdown

__all__ = [
    "compact",
    "compact_json",
    "confluence_to_md",
    "html_to_md",
    "jira_issue_to_md",
    "page_to_md",
    "render_diff",
    "wiki_to_md",
]

# Service metadata that carries no review value but dominates payload size.
_DROP = frozenset(
    {
        "links",
        "self",
        "clone",
        "avatarUrl",
        "properties",
        "permittedOperations",
        "mutableDetails",
        "mutableGroups",
        "directoryName",
        "lastAuthenticationTimestamp",
        "type",
    }
)


def confluence_to_md(storage_xhtml: str) -> str:
    """Convert Confluence storage-format XHTML to Markdown.

    Macros, links, attachments and images follow the same rules as
    ``atlawire page --markdown``: labels and destinations are kept as inert
    Markdown, unsupported macros are labelled instead of dropped, and nothing is
    fetched.
    """
    if not isinstance(storage_xhtml, str):
        raise TypeError("Expected Confluence storage XHTML as text.")
    return render_storage_markdown(storage_xhtml)


def page_to_md(page: Mapping[str, Any]) -> str:
    """Render one already fetched page document as Markdown.

    Equivalent to ``render_page_markdown``; kept here so every Markdown entry
    point lives in one module.
    """
    return render_page_markdown(dict(page))


def html_to_md(html: str) -> str:
    """Convert HTML to inert Markdown without active links or image sources."""
    if not isinstance(html, str):
        raise TypeError("Expected HTML as text.")
    converted = convert_html(
        html, SafeMarkdownConverter(escape_misc=True, heading_style="atx", bullets="-")
    )
    return converted or ""


def wiki_to_md(text: str) -> str:
    """Convert Jira wiki markup to Markdown.

    The supported subset is the documented one: headings, bold, italic, inline
    code, ``{code}``/``{noformat}`` blocks, http(s) links. Other macros and
    tables are shown literally with an explicit label.
    """
    return wiki_to_markdown(text)


def jira_issue_to_md(issue: Mapping[str, Any], *, wiki: bool = False) -> str:
    """Render one already fetched Jira issue as Markdown.

    ``wiki=True`` renders the raw description and comments instead of
    ``renderedFields``.
    """
    return render_issue_markdown(dict(issue), use_wiki=wiki)


def render_diff(payload: Mapping[str, Any], *, context: int = 3) -> str:
    """Render an already fetched Bitbucket diff JSON as a review view.

    This is not an applyable patch: it ignores whitespace-only changes and marks
    files where the server sent no textual hunks. Declared truncation is
    reported at the top instead of being silently rendered.
    """
    from atlawire.bitbucket import _render_pull_request_diff_text

    return _render_pull_request_diff_text(dict(payload), context=context)


def compact(obj: object, *, drop_empty: bool = True) -> object:
    """Return a compact projection of a server document.

    Service keys (links, avatars, permitted operations, …) are removed, and two
    well-known wrappers are collapsed to short strings: a user becomes
    ``"name (display name)"`` and a branch ref becomes ``"PROJECT/slug:branch"``.
    ``drop_empty`` also removes nulls and empty containers; pass ``False`` to keep
    them. The input is never mutated.
    """
    if isinstance(obj, list):
        return [compact(item, drop_empty=drop_empty) for item in obj]
    if isinstance(obj, Mapping):
        return _compact_mapping(obj, drop_empty=drop_empty)
    if isinstance(obj, tuple):
        return [compact(item, drop_empty=drop_empty) for item in obj]
    return obj


def _compact_mapping(obj: Mapping[object, object], *, drop_empty: bool) -> object:
    name = obj.get("name")
    if isinstance(name, str) and ("emailAddress" in obj or "displayName" in obj):
        display = obj.get("displayName")
        return f"{name} ({display})".strip() if isinstance(display, str) else name
    identifier = obj.get("id")
    repository = obj.get("repository")
    display_id = obj.get("displayId")
    if (
        identifier is not None
        and isinstance(repository, Mapping)
        and isinstance(display_id, str)
        and display_id
    ):
        project = repository.get("project")
        key = project.get("key") if isinstance(project, Mapping) else None
        slug = repository.get("slug")
        if isinstance(key, str) and isinstance(slug, str):
            return f"{key}/{slug}:{display_id}"
    result: dict[object, object] = {}
    for key, value in obj.items():
        if isinstance(key, str) and key in _DROP:
            continue
        if drop_empty and (value is None or value == [] or value == {}):
            continue
        result[key] = compact(value, drop_empty=drop_empty)
    return result


def compact_json(obj: object, *, drop_empty: bool = True) -> str:
    """Return compact JSON in one line, suitable for logs and agent context."""
    return json.dumps(
        compact(obj, drop_empty=drop_empty),
        ensure_ascii=False,
        separators=(",", ":"),
    )
