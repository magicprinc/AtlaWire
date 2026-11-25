"""Command-line interface and library for self-hosted Atlassian products."""

from atlawire.http import AtlaWireError
from atlawire.markdown import (
    compact,
    compact_json,
    confluence_to_md,
    html_to_md,
    jira_issue_to_md,
    render_diff,
    wiki_to_md,
)
from atlawire.operations import describe_operation, list_operations, read_operation
from atlawire.pr_review import (
    changed_symbols,
    fetch_ticket,
    file_links,
    find_ticket,
    java_members,
    red_flags,
    review,
)
from atlawire.sdk import SdkRequestError, client_for, get_json, request_json

__version__ = "0.9.7"

__all__ = [
    "AtlaWireError",
    "SdkRequestError",
    "__version__",
    "changed_symbols",
    "client_for",
    "compact",
    "compact_json",
    "confluence_to_md",
    "describe_operation",
    "fetch_ticket",
    "file_links",
    "find_ticket",
    "get_json",
    "html_to_md",
    "java_members",
    "jira_issue_to_md",
    "list_operations",
    "read_operation",
    "red_flags",
    "render_diff",
    "request_json",
    "review",
    "wiki_to_md",
]
