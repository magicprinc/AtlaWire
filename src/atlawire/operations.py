"""Static, audited registry of fixed read-only Atlassian GET operations.

This module is the deliberately small alternative to a generic REST
passthrough. An operation is registered in code with one stable ID, one product,
one exact GET path template, its documented API version, its expected JSON
shape, and the path arguments and typed query fields the server route accepts.
A caller can select only a registered ID, its declared path arguments, and its
declared query fields; it cannot supply a URL, method, headers, body, or
arbitrary query parameters.

Each [read_operation][atlawire.operations.read_operation] call performs exactly
one GET against the configured instance and returns the decoded JSON unchanged.
No pagination is attempted and no completeness is claimed: an array, or a paged
object carrying ``isLastPage``/``nextPageStart``, is the one response the server
sent, not proof that no further page exists. Query parameters are also declared
in the registry, not passed through: unknown names and malformed values are
rejected before a request, and only the validated mapping is handed to Requests
for its single encoding step. Response ``_links`` are data only and are never
followed, including the ``content`` URL of Jira attachment metadata; binary
downloads are intentionally out of scope until a same-origin/redirect contract
exists.

Bitbucket documents a 204 response when a repository is empty and has no default
branch. Only ``bitbucket.repository.default-branch`` treats that documented
empty result as JSON ``null``; a 200 response containing JSON ``null``, empty
JSON, or malformed JSON is still an error, and no other operation accepts 204.

Documented routes:

* Jira Server 8.22.0 REST API 2:
  https://docs.atlassian.com/software/jira/docs/api/REST/8.22.0/
* Bitbucket Server 5.10.0 REST API 1.0:
  https://docs.atlassian.com/bitbucket-server/rest/5.10.0/bitbucket-rest.html
* Confluence Server 6.6.0 REST API:
  https://docs.atlassian.com/atlassian-confluence/REST/6.6.0/
"""

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast
from urllib.parse import quote

from atlawire.http import (
    AtlaWireError,
    bearer_session,
    get_json_any,
    get_json_array,
    get_json_object,
    get_json_object_allow_no_content,
    normalize_base_url,
)
from atlawire.sdk import download_to_file as sdk_download_to_file
from atlawire.sdk import request_json_with_status as sdk_request_json_with_status

__all__ = [
    "BINARY_MAX_BYTES",
    "CANONICAL_IDS",
    "OperationShapeError",
    "canonical_operations",
    "describe_operation",
    "list_operations",
    "read_binary",
    "read_operation",
]


class OperationShapeError(AtlaWireError):
    """The server response does not match the registered operation shape.

    It is an execution failure, not a caller-input error, so the CLI maps it to
    exit 1 with ``invalid_response`` rather than to a usage error. ``status`` is
    the received HTTP status when it is known.
    """

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


type ResponseKind = Literal["object", "array", "json", "binary"]
type FieldKind = Literal["string", "integer", "boolean", "object"]
type QueryKind = Literal["string", "integer"]
type BodyKind = Literal["string", "integer", "integer_array"]

_UNKNOWN_ID = "Unknown operation ID."
_INVALID_ARGUMENTS = "Expected a mapping of registered path arguments."
_INVALID_QUERY = "The query parameters are invalid."
_INVALID_VALUE = "The {name} path argument is invalid."
_BAD_SHAPE = "Unexpected JSON response shape for operation {operation_id}."
_INVALID_TOKEN = "Missing or invalid bearer token."
# A path segment is restricted to unreserved ASCII by the per-operation
# patterns. Reject separators, query/fragment markers, pre-encoded bytes, and
# controls first, so a value can never change the fixed route or be decoded
# twice by an intermediary.
_UNSAFE_SEGMENT = re.compile(r"[%/\\?#\x00-\x20\x7f]")
_UNSAFE_QUERY_TEXT = re.compile(r"[\x00-\x20\x7f-\x9f]")
_UNSAFE_QUERY_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")
_MAX_ARGUMENT_LENGTH = 255
_MAX_WORKLOG_IDS = 1000
BINARY_MAX_BYTES = 32 * 1024 * 1024
_BINARY_TARGET = "This operation writes a file; pass an explicit destination."
_NOT_BINARY = "This operation is not a binary read."
_INVALID_BODY = "The request body is invalid."
_MAX_QUERY_INTEGER = 2**31 - 1

_JIRA_PROJECT_ID_OR_KEY = re.compile(r"(?:[A-Z][A-Z0-9_]*|[1-9][0-9]*)")
_JIRA_ISSUE_ID_OR_KEY = re.compile(r"(?:[A-Z][A-Z0-9_]*-[1-9][0-9]*|[1-9][0-9]*)")
_JIRA_ATTACHMENT_ID = re.compile(r"[1-9][0-9]*")
_BITBUCKET_PROJECT_KEY = re.compile(r"~?[A-Za-z0-9_][A-Za-z0-9_.-]*")
_BITBUCKET_REPOSITORY_SLUG = re.compile(r"[A-Za-z0-9_.-]+")
_CONFLUENCE_SPACE_KEY = re.compile(r"~?[A-Za-z0-9_][A-Za-z0-9_.-]*")
_FROM_REPO_ID = re.compile(r"[1-9][0-9]*")
_FROM_REPO_PROJECT = re.compile(r"~?[A-Za-z0-9_][A-Za-z0-9_.-]*")
_FROM_REPO_SLUG = re.compile(r"[A-Za-z0-9_.-]+")
_PULL_REQUEST_ID = re.compile(r"[1-9][0-9]*")
_FULL_COMMIT_ID = re.compile(r"[0-9A-Fa-f]{40}")
_TASK_ID = re.compile(r"[1-9][0-9]*")
_USER_SLUG = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*")
_JIRA_COMMENT_ID = re.compile(r"[1-9][0-9]*")
_JIRA_WORKLOG_ID = re.compile(r"[1-9][0-9]*")
_JIRA_ISSUE_LINK_ID = re.compile(r"[1-9][0-9]*")
_CONFLUENCE_CONTENT_ID = re.compile(r"[1-9][0-9]*")
_CONFLUENCE_CONVERSION_TARGET = re.compile(
    r"(?:storage|view|export_view|styled_view|editor2)"
)

# The initial agent-facing surface. These remain ordinary registry entries:
# the legacy read path and its tests are unchanged.
CANONICAL_IDS = frozenset(
    {
        "bitbucket.repository.get",
        "confluence.space.get",
        "jira.project.get",
    }
)

_MANIFEST_PATH = Path(__file__).with_name("manifest.json")

# Safe example values for the canonical read examples. A missing entry means
# the description returns no example rather than inventing an identifier.
_EXAMPLE_ARGUMENTS: dict[str, dict[str, str]] = {
    "bitbucket.repository.get": {
        "projectKey": "DEMO",
        "repositorySlug": "example-repository",
    },
    "confluence.space.get": {"spaceKey": "DEMO"},
    "jira.project.get": {"projectIdOrKey": "DEMO"},
}


@dataclass(frozen=True, slots=True)
class _Field:
    """One required JSON field and the JSON type it must have."""

    name: str
    kind: FieldKind


@dataclass(frozen=True, slots=True)
class _Argument:
    """One accepted path parameter and its local syntax."""

    name: str
    pattern: re.Pattern[str]
    description: str
    # When true the value is a repository-relative path: each segment must
    # match ``pattern``, and segments are encoded individually.
    allow_slash: bool = False


@dataclass(frozen=True, slots=True)
class _QueryField:
    """One explicitly registered query parameter and its local type."""

    name: str
    kind: QueryKind
    required: bool
    description: str
    max_length: int | None = None
    minimum: int | None = None
    maximum: int | None = None
    from_repo: bool = False
    allowed: tuple[str, ...] = ()
    allow_spaces: bool = False
    # Other query fields that must also be present when this one is used.
    depends_on: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _BodyField:
    """One declared JSON body field for a semantic-read POST."""

    name: str
    kind: BodyKind
    required: bool
    description: str
    allowed: tuple[str, ...] = ()
    maximum: int | None = None


@dataclass(frozen=True, slots=True)
class _Operation:
    """One audited fixed read route."""

    id: str
    product: str
    path: str
    description: str
    documented_version: str
    kind: ResponseKind
    required: tuple[_Field, ...]
    item_required: tuple[_Field, ...] = ()
    object_arrays: tuple[str, ...] = ()
    arguments: tuple[_Argument, ...] = ()
    query: tuple[_QueryField, ...] = ()
    query_at_most_one: tuple[str, ...] = ()
    query_at_least_one: tuple[str, ...] = ()
    query_exactly_one: tuple[str, ...] = ()
    null_on_204: bool = False
    method: str = "GET"
    body: tuple[_BodyField, ...] = ()


_JIRA_VERSION = "Jira Server 8.22.0 REST API 2"
_BITBUCKET_VERSION = "Bitbucket Server 5.10.0 REST API 1.0"
_CONFLUENCE_VERSION = "Confluence Server 6.6.0 REST API"

_COMPARE_QUERY = (
    _QueryField(
        "from",
        "string",
        False,
        "Source commit ID or ref name; Bitbucket uses the default branch when omitted.",
        max_length=_MAX_ARGUMENT_LENGTH,
    ),
    _QueryField(
        "to",
        "string",
        False,
        "Target commit ID or ref name; Bitbucket uses the default branch when omitted.",
        max_length=_MAX_ARGUMENT_LENGTH,
    ),
    _QueryField(
        "fromRepo",
        "string",
        False,
        (
            "Source repository as a positive numeric repository ID or "
            "projectKey/repositorySlug when the source commit is elsewhere."
        ),
        from_repo=True,
    ),
    _QueryField(
        "start",
        "integer",
        False,
        "Zero-based paging start; use the response's nextPageStart for a later page.",
        minimum=0,
        maximum=_MAX_QUERY_INTEGER,
    ),
    _QueryField(
        "limit",
        "integer",
        False,
        "Requested page size; the server may apply a lower hard limit.",
        minimum=1,
        maximum=_MAX_QUERY_INTEGER,
    ),
)

_PAGING_QUERY = (
    _QueryField(
        "start",
        "integer",
        False,
        "Zero-based paging start; use the response's nextPageStart for a later page.",
        minimum=0,
        maximum=_MAX_QUERY_INTEGER,
    ),
    _QueryField(
        "limit",
        "integer",
        False,
        "Requested page size; the server may apply a lower hard limit.",
        minimum=1,
        maximum=_MAX_QUERY_INTEGER,
    ),
)

_PARTICIPANTS_QUERY = (
    _QueryField(
        "direction",
        "string",
        False,
        "Direction relative to the repository: INCOMING or OUTGOING.",
        allowed=("INCOMING", "OUTGOING"),
    ),
    _QueryField(
        "filter",
        "string",
        False,
        "Only users whose username, name, or email contains this value.",
        allow_spaces=True,
    ),
    _QueryField(
        "role",
        "string",
        False,
        "Pull-request role: AUTHOR, REVIEWER, or PARTICIPANT.",
        allowed=("AUTHOR", "REVIEWER", "PARTICIPANT"),
    ),
    *_PAGING_QUERY,
)

_COMMIT_COMMENTS_QUERY = (
    _QueryField(
        "path",
        "string",
        False,
        "Only comments on this repository file path.",
        allow_spaces=True,
    ),
    _QueryField(
        "since",
        "string",
        False,
        "Parent commit or sinceId that anchors the comment range.",
    ),
    *_PAGING_QUERY,
)

_QUERY_EXPAND = _QueryField(
    "expand",
    "string",
    False,
    "Comma-separated expansion names.",
)
_JIRA_PAGING_QUERY = (
    _QueryField(
        "startAt",
        "integer",
        False,
        "Zero-based index of the first result.",
        minimum=0,
        maximum=_MAX_QUERY_INTEGER,
    ),
    _QueryField(
        "maxResults",
        "integer",
        False,
        "Requested page size; the server may apply a lower limit.",
        minimum=1,
        maximum=_MAX_QUERY_INTEGER,
    ),
)
_CONTENT_PAGING_QUERY = (
    _QueryField(
        "start",
        "integer",
        False,
        "Zero-based index of the first result.",
        minimum=0,
        maximum=_MAX_QUERY_INTEGER,
    ),
    _QueryField(
        "limit",
        "integer",
        False,
        "Requested page size; the server may apply a lower limit.",
        minimum=1,
        maximum=_MAX_QUERY_INTEGER,
    ),
)

_OPERATIONS: dict[str, _Operation] = {
    operation.id: operation
    for operation in (
        _Operation(
            id="jira.attachment.content",
            product="jira",
            path="/rest/api/2/attachment/{id}/content",
            description=(
                "Download one Jira attachment's content to an explicit destination."
            ),
            documented_version=_JIRA_VERSION,
            kind="binary",
            required=(),
            arguments=(
                _Argument(
                    "id",
                    _JIRA_ATTACHMENT_ID,
                    "Positive decimal Jira attachment ID.",
                ),
            ),
        ),
        _Operation(
            id="jira.attachment.expand.raw",
            product="jira",
            path="/rest/api/2/attachment/{id}/expand/raw",
            description=(
                "Read the raw expanded content of one Jira attachment; writes "
                "bytes to an explicit destination."
            ),
            documented_version=_JIRA_VERSION,
            kind="binary",
            required=(),
            arguments=(
                _Argument(
                    "id",
                    _JIRA_ATTACHMENT_ID,
                    "Positive decimal Jira attachment ID.",
                ),
            ),
        ),
        _Operation(
            id="jira.avatar.system",
            product="jira",
            path="/rest/api/2/avatar/{type}/system",
            description="Read one system avatar image as bytes.",
            documented_version=_JIRA_VERSION,
            kind="binary",
            required=(),
            arguments=(
                _Argument(
                    "type",
                    re.compile(r"(?:project|user)"),
                    "Avatar type: project or user.",
                ),
            ),
        ),
        _Operation(
            id="bitbucket.hooks.avatar",
            product="bitbucket",
            path="/rest/api/1.0/hooks/{hookKey}/avatar",
            description="Read one Bitbucket hook avatar image as bytes.",
            documented_version=_BITBUCKET_VERSION,
            kind="binary",
            required=(),
            arguments=(
                _Argument(
                    "hookKey",
                    re.compile(r"[A-Za-z0-9._-]+"),
                    "Bitbucket hook key.",
                ),
            ),
        ),
        _Operation(
            id="bitbucket.project.avatar",
            product="bitbucket",
            path="/rest/api/1.0/projects/{projectKey}/avatar.png",
            description="Read one Bitbucket project avatar image as bytes.",
            documented_version=_BITBUCKET_VERSION,
            kind="binary",
            required=(),
            arguments=(
                _Argument(
                    "projectKey",
                    _BITBUCKET_PROJECT_KEY,
                    (
                        "Bitbucket project key, optionally prefixed with ~ "
                        "for a personal project."
                    ),
                ),
            ),
        ),
        _Operation(
            id="bitbucket.repository.archive",
            product="bitbucket",
            path=("/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/archive"),
            description=("Download a repository archive to an explicit destination."),
            documented_version=_BITBUCKET_VERSION,
            kind="binary",
            required=(),
            arguments=(
                _Argument(
                    "projectKey",
                    _BITBUCKET_PROJECT_KEY,
                    "Bitbucket project key.",
                ),
                _Argument(
                    "repositorySlug",
                    _BITBUCKET_REPOSITORY_SLUG,
                    "Bitbucket repository slug.",
                ),
            ),
        ),
        _Operation(
            id="bitbucket.repository.raw",
            product="bitbucket",
            path=("/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/raw"),
            description="Download the repository root as raw bytes.",
            documented_version=_BITBUCKET_VERSION,
            kind="binary",
            required=(),
            arguments=(
                _Argument(
                    "projectKey",
                    _BITBUCKET_PROJECT_KEY,
                    "Bitbucket project key.",
                ),
                _Argument(
                    "repositorySlug",
                    _BITBUCKET_REPOSITORY_SLUG,
                    "Bitbucket repository slug.",
                ),
            ),
        ),
        _Operation(
            id="jira.search.post",
            product="jira",
            path="/rest/api/2/search",
            description=(
                "Search Jira issues with JQL through the documented read-only "
                "POST; does not change any issue."
            ),
            documented_version=_JIRA_VERSION,
            kind="object",
            required=(),
            method="POST",
            body=(
                _BodyField(
                    "jql",
                    "string",
                    True,
                    "JQL query text; the server evaluates it as a search.",
                ),
                _BodyField(
                    "startAt",
                    "integer",
                    False,
                    "Zero-based index of the first result.",
                    maximum=_MAX_QUERY_INTEGER,
                ),
                _BodyField(
                    "maxResults",
                    "integer",
                    False,
                    "Requested page size; the server may apply a lower limit.",
                    maximum=_MAX_QUERY_INTEGER,
                ),
            ),
        ),
        _Operation(
            id="jira.worklog.list",
            product="jira",
            path="/rest/api/2/worklog/list",
            description="List worklogs for up to 1000 issue IDs in one read.",
            documented_version=_JIRA_VERSION,
            kind="array",
            required=(),
            method="POST",
            body=(
                _BodyField(
                    "issueIds",
                    "integer_array",
                    True,
                    "Issue IDs whose worklogs are returned (at most 1000).",
                ),
            ),
        ),
        _Operation(
            id="confluence.content.convert",
            product="confluence",
            path="/rest/api/contentbody/convert/{to}",
            description=(
                "Convert stored content to another representation; returns "
                "the converted text and does not modify the content."
            ),
            documented_version=_CONFLUENCE_VERSION,
            kind="object",
            required=(),
            method="POST",
            arguments=(
                _Argument(
                    "to",
                    _CONFLUENCE_CONVERSION_TARGET,
                    "Target representation.",
                ),
            ),
            body=(
                _BodyField(
                    "value",
                    "string",
                    True,
                    "Content to convert.",
                ),
                _BodyField(
                    "representation",
                    "string",
                    True,
                    "Representation of value.",
                    allowed=(
                        "storage",
                        "view",
                        "export_view",
                        "styled_view",
                        "editor2",
                    ),
                ),
            ),
        ),
        _Operation(
            id="bitbucket.project.get",
            product="bitbucket",
            path="/rest/api/1.0/projects/{projectKey}",
            description="Get one Bitbucket project by key.",
            documented_version=_BITBUCKET_VERSION,
            kind="object",
            required=(),
            arguments=(
                _Argument(
                    "projectKey",
                    _BITBUCKET_PROJECT_KEY,
                    (
                        "Bitbucket project key, optionally prefixed with ~ "
                        "for a personal project."
                    ),
                ),
            ),
        ),
        _Operation(
            id="bitbucket.repository.compare-changes",
            product="bitbucket",
            path=(
                "/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}"
                "/compare/changes"
            ),
            description=(
                "Get one page of file changes available from one Bitbucket "
                "commit but not another."
            ),
            documented_version=_BITBUCKET_VERSION,
            kind="object",
            required=(),
            arguments=(
                _Argument(
                    "projectKey",
                    _BITBUCKET_PROJECT_KEY,
                    (
                        "Bitbucket project key, optionally prefixed with ~ "
                        "for a personal project."
                    ),
                ),
                _Argument(
                    "repositorySlug",
                    _BITBUCKET_REPOSITORY_SLUG,
                    "Bitbucket repository slug.",
                ),
            ),
            query=_COMPARE_QUERY,
        ),
        _Operation(
            id="bitbucket.repository.compare-commits",
            product="bitbucket",
            path=(
                "/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}"
                "/compare/commits"
            ),
            description=(
                "Get one page of commits accessible from one Bitbucket commit "
                "but not another."
            ),
            documented_version=_BITBUCKET_VERSION,
            kind="object",
            required=(),
            arguments=(
                _Argument(
                    "projectKey",
                    _BITBUCKET_PROJECT_KEY,
                    (
                        "Bitbucket project key, optionally prefixed with ~ "
                        "for a personal project."
                    ),
                ),
                _Argument(
                    "repositorySlug",
                    _BITBUCKET_REPOSITORY_SLUG,
                    "Bitbucket repository slug.",
                ),
            ),
            query=_COMPARE_QUERY,
        ),
        _Operation(
            id="bitbucket.repository.commit-comments",
            product="bitbucket",
            path=(
                "/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}"
                "/commits/{commitId}/comments"
            ),
            description="Get one page of comments on a Bitbucket commit.",
            documented_version=_BITBUCKET_VERSION,
            kind="object",
            required=(),
            arguments=(
                _Argument(
                    "projectKey",
                    _BITBUCKET_PROJECT_KEY,
                    (
                        "Bitbucket project key, optionally prefixed with ~ "
                        "for a personal project."
                    ),
                ),
                _Argument(
                    "repositorySlug",
                    _BITBUCKET_REPOSITORY_SLUG,
                    "Bitbucket repository slug.",
                ),
                _Argument(
                    "commitId",
                    _FULL_COMMIT_ID,
                    "Full 40-character Bitbucket commit ID.",
                ),
            ),
            query=_COMMIT_COMMENTS_QUERY,
        ),
        _Operation(
            id="bitbucket.repository.forks",
            product="bitbucket",
            path=("/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/forks"),
            description="Get one page of direct forks of a Bitbucket repository.",
            documented_version=_BITBUCKET_VERSION,
            kind="object",
            required=(),
            arguments=(
                _Argument(
                    "projectKey",
                    _BITBUCKET_PROJECT_KEY,
                    (
                        "Bitbucket project key, optionally prefixed with ~ "
                        "for a personal project."
                    ),
                ),
                _Argument(
                    "repositorySlug",
                    _BITBUCKET_REPOSITORY_SLUG,
                    "Bitbucket repository slug.",
                ),
            ),
            query=_PAGING_QUERY,
        ),
        _Operation(
            id="bitbucket.repository.participants",
            product="bitbucket",
            path=(
                "/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}"
                "/participants"
            ),
            description=(
                "Get one page of pull-request participants for a Bitbucket repository."
            ),
            documented_version=_BITBUCKET_VERSION,
            kind="object",
            required=(),
            arguments=(
                _Argument(
                    "projectKey",
                    _BITBUCKET_PROJECT_KEY,
                    (
                        "Bitbucket project key, optionally prefixed with ~ "
                        "for a personal project."
                    ),
                ),
                _Argument(
                    "repositorySlug",
                    _BITBUCKET_REPOSITORY_SLUG,
                    "Bitbucket repository slug.",
                ),
            ),
            query=_PARTICIPANTS_QUERY,
        ),
        _Operation(
            id="bitbucket.repository.pull-request-activity",
            product="bitbucket",
            path=(
                "/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}"
                "/pull-requests/{pullRequestId}/activities"
            ),
            description="Get one page of activity for a Bitbucket pull request.",
            documented_version=_BITBUCKET_VERSION,
            kind="object",
            required=(),
            arguments=(
                _Argument(
                    "projectKey",
                    _BITBUCKET_PROJECT_KEY,
                    (
                        "Bitbucket project key, optionally prefixed with ~ "
                        "for a personal project."
                    ),
                ),
                _Argument(
                    "repositorySlug",
                    _BITBUCKET_REPOSITORY_SLUG,
                    "Bitbucket repository slug.",
                ),
                _Argument(
                    "pullRequestId",
                    _PULL_REQUEST_ID,
                    "Positive numeric Bitbucket pull-request ID.",
                ),
            ),
            query=_PAGING_QUERY,
        ),
        _Operation(
            id="bitbucket.repository.related",
            product="bitbucket",
            path=("/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/related"),
            description=(
                "Get one page of repositories related to a Bitbucket repository."
            ),
            documented_version=_BITBUCKET_VERSION,
            kind="object",
            required=(),
            arguments=(
                _Argument(
                    "projectKey",
                    _BITBUCKET_PROJECT_KEY,
                    (
                        "Bitbucket project key, optionally prefixed with ~ "
                        "for a personal project."
                    ),
                ),
                _Argument(
                    "repositorySlug",
                    _BITBUCKET_REPOSITORY_SLUG,
                    "Bitbucket repository slug.",
                ),
            ),
            query=_PAGING_QUERY,
        ),
        _Operation(
            id="bitbucket.profile.recent-repositories",
            product="bitbucket",
            path="/rest/api/1.0/profile/recent/repos",
            description=(
                "List one page of repositories recently accessed by the "
                "authenticated Bitbucket user."
            ),
            documented_version=_BITBUCKET_VERSION,
            kind="object",
            required=(),
            query=_PAGING_QUERY,
        ),
        _Operation(
            id="bitbucket.task.get",
            product="bitbucket",
            path="/rest/api/1.0/tasks/{taskId}",
            description=("Get one Bitbucket task visible to the authenticated user."),
            documented_version=_BITBUCKET_VERSION,
            kind="object",
            required=(),
            arguments=(
                _Argument(
                    "taskId",
                    _TASK_ID,
                    "Positive numeric Bitbucket task ID.",
                ),
            ),
        ),
        _Operation(
            id="bitbucket.user.get",
            product="bitbucket",
            path="/rest/api/1.0/users/{userSlug}",
            description="Get one Bitbucket user by slug.",
            documented_version=_BITBUCKET_VERSION,
            kind="object",
            required=(),
            arguments=(
                _Argument(
                    "userSlug",
                    _USER_SLUG,
                    "Bitbucket user slug.",
                ),
            ),
        ),
        _Operation(
            id="bitbucket.users.list",
            product="bitbucket",
            path="/rest/api/1.0/users",
            description=(
                "List one page of Bitbucket users visible to the authenticated user."
            ),
            documented_version=_BITBUCKET_VERSION,
            kind="object",
            required=(),
            query=_PAGING_QUERY,
        ),
        _Operation(
            id="bitbucket.repository.default-branch",
            product="bitbucket",
            path=(
                "/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}"
                "/branches/default"
            ),
            description="Get a Bitbucket repository's configured default branch.",
            documented_version=_BITBUCKET_VERSION,
            kind="object",
            required=(),
            null_on_204=True,
            arguments=(
                _Argument(
                    "projectKey",
                    _BITBUCKET_PROJECT_KEY,
                    (
                        "Bitbucket project key, optionally prefixed with ~ "
                        "for a personal project."
                    ),
                ),
                _Argument(
                    "repositorySlug",
                    _BITBUCKET_REPOSITORY_SLUG,
                    "Bitbucket repository slug.",
                ),
            ),
        ),
        _Operation(
            id="bitbucket.repository.get",
            product="bitbucket",
            path="/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}",
            description=(
                "Get one Bitbucket repository by project key and repository slug."
            ),
            documented_version=_BITBUCKET_VERSION,
            kind="object",
            required=(),
            arguments=(
                _Argument(
                    "projectKey",
                    _BITBUCKET_PROJECT_KEY,
                    (
                        "Bitbucket project key, optionally prefixed with ~ "
                        "for a personal project."
                    ),
                ),
                _Argument(
                    "repositorySlug",
                    _BITBUCKET_REPOSITORY_SLUG,
                    "Bitbucket repository slug.",
                ),
            ),
        ),
        _Operation(
            id="confluence.space.get",
            product="confluence",
            path="/rest/api/space/{spaceKey}",
            description="Get one Confluence space by key.",
            documented_version=_CONFLUENCE_VERSION,
            kind="object",
            required=(),
            arguments=(
                _Argument(
                    "spaceKey",
                    _CONFLUENCE_SPACE_KEY,
                    (
                        "Confluence space key, optionally prefixed with ~ "
                        "for a personal space."
                    ),
                ),
            ),
        ),
        _Operation(
            id="jira.attachment.get",
            product="jira",
            path="/rest/api/2/attachment/{id}",
            description=(
                "Get Jira attachment metadata without downloading its content."
            ),
            documented_version=_JIRA_VERSION,
            kind="object",
            required=(_Field("size", "integer"),),
            arguments=(
                _Argument(
                    "id",
                    _JIRA_ATTACHMENT_ID,
                    "Positive decimal Jira attachment ID.",
                ),
            ),
        ),
        _Operation(
            id="jira.issue.votes",
            product="jira",
            path="/rest/api/2/issue/{issueIdOrKey}/votes",
            description="Get the votes on one Jira issue.",
            documented_version=_JIRA_VERSION,
            kind="object",
            required=(_Field("votes", "integer"), _Field("hasVoted", "boolean")),
            object_arrays=("voters",),
            arguments=(
                _Argument(
                    "issueIdOrKey",
                    _JIRA_ISSUE_ID_OR_KEY,
                    "Jira issue key or positive numeric issue ID.",
                ),
            ),
        ),
        _Operation(
            id="jira.issue.watchers",
            product="jira",
            path="/rest/api/2/issue/{issueIdOrKey}/watchers",
            description="Get the watchers of one Jira issue.",
            documented_version=_JIRA_VERSION,
            kind="object",
            required=(_Field("watchCount", "integer"),),
            object_arrays=("watchers",),
            arguments=(
                _Argument(
                    "issueIdOrKey",
                    _JIRA_ISSUE_ID_OR_KEY,
                    "Jira issue key or positive numeric issue ID.",
                ),
            ),
        ),
        _Operation(
            id="jira.project.components",
            product="jira",
            path="/rest/api/2/project/{projectIdOrKey}/components",
            description="List a Jira project's components.",
            documented_version=_JIRA_VERSION,
            kind="array",
            required=(),
            item_required=(_Field("isAssigneeTypeValid", "boolean"),),
            arguments=(
                _Argument(
                    "projectIdOrKey",
                    _JIRA_PROJECT_ID_OR_KEY,
                    "Jira project key or positive numeric project ID.",
                ),
            ),
        ),
        _Operation(
            id="jira.project.get",
            product="jira",
            path="/rest/api/2/project/{projectIdOrKey}",
            description="Get one Jira project by key or numeric ID.",
            documented_version=_JIRA_VERSION,
            kind="object",
            required=(),
            arguments=(
                _Argument(
                    "projectIdOrKey",
                    _JIRA_PROJECT_ID_OR_KEY,
                    "Jira project key or positive numeric project ID.",
                ),
            ),
        ),
        _Operation(
            id="jira.project.versions",
            product="jira",
            path="/rest/api/2/project/{projectIdOrKey}/versions",
            description="List a Jira project's versions.",
            documented_version=_JIRA_VERSION,
            kind="array",
            required=(),
            item_required=(),
            arguments=(
                _Argument(
                    "projectIdOrKey",
                    _JIRA_PROJECT_ID_OR_KEY,
                    "Jira project key or positive numeric project ID.",
                ),
            ),
        ),
        _Operation(
            id="jira.mypermissions.get",
            product="jira",
            path="/rest/api/2/mypermissions",
            description="Get the authenticated Jira user's permissions, optionally scoped to one project or issue.",
            documented_version=_JIRA_VERSION,
            kind="object",
            required=(),
            query=(
                _QueryField("projectKey", "string", False, "Project key scope."),
                _QueryField(
                    "projectId",
                    "integer",
                    False,
                    "Project ID scope.",
                    minimum=1,
                    maximum=_MAX_QUERY_INTEGER,
                ),
                _QueryField("issueKey", "string", False, "Issue key scope."),
                _QueryField(
                    "issueId",
                    "integer",
                    False,
                    "Issue ID scope.",
                    minimum=1,
                    maximum=_MAX_QUERY_INTEGER,
                ),
            ),
            query_at_most_one=("projectKey", "projectId", "issueKey", "issueId"),
        ),
        _Operation(
            id="jira.user.get",
            product="jira",
            path="/rest/api/2/user",
            description="Get one Jira user by username or user key.",
            documented_version=_JIRA_VERSION,
            kind="object",
            required=(_Field("active", "boolean"),),
            query=(
                _QueryField("username", "string", False, "Jira username."),
                _QueryField("key", "string", False, "Jira user key."),
            ),
            query_at_least_one=("username", "key"),
        ),
        _Operation(
            id="jira.user.assignable-search",
            product="jira",
            path="/rest/api/2/user/assignable/search",
            description="List one page of users assignable to a Jira project or issue.",
            documented_version=_JIRA_VERSION,
            kind="array",
            required=(),
            item_required=(_Field("active", "boolean"),),
            query=(
                _QueryField("username", "string", False, "Username search text."),
                _QueryField(
                    "project",
                    "string",
                    False,
                    "Jira project key for create-mode assignment.",
                ),
                _QueryField(
                    "issueKey",
                    "string",
                    False,
                    "Jira issue key for edit-mode assignment.",
                ),
                _QueryField(
                    "startAt",
                    "integer",
                    False,
                    "Zero-based index of the first result.",
                    minimum=0,
                    maximum=_MAX_QUERY_INTEGER,
                ),
                _QueryField(
                    "maxResults",
                    "integer",
                    False,
                    "Requested page size; the server may apply a lower limit.",
                    minimum=1,
                    maximum=_MAX_QUERY_INTEGER,
                ),
                _QueryField(
                    "actionDescriptorId",
                    "integer",
                    False,
                    "Jira action descriptor ID.",
                    depends_on=("issueKey",),
                ),
            ),
            query_at_least_one=("project", "issueKey"),
        ),
        _Operation(
            id="jira.field.list",
            product="jira",
            path="/rest/api/2/field",
            description="List all Jira fields visible to the authenticated user.",
            documented_version=_JIRA_VERSION,
            kind="array",
            required=(),
        ),
        _Operation(
            id="jira.project.statuses",
            product="jira",
            path="/rest/api/2/project/{projectIdOrKey}/statuses",
            description="List Jira issue types and their valid statuses for a project.",
            documented_version=_JIRA_VERSION,
            kind="array",
            required=(),
            item_required=(_Field("subtask", "boolean"),),
            arguments=(
                _Argument(
                    "projectIdOrKey",
                    _JIRA_PROJECT_ID_OR_KEY,
                    "Jira project key or positive numeric project ID.",
                ),
            ),
        ),
        _Operation(
            id="jira.project.roles",
            product="jira",
            path="/rest/api/2/project/{projectIdOrKey}/role",
            description="List Jira project role names and detail URLs.",
            documented_version=_JIRA_VERSION,
            kind="object",
            required=(),
            arguments=(
                _Argument(
                    "projectIdOrKey",
                    _JIRA_PROJECT_ID_OR_KEY,
                    "Jira project key or positive numeric project ID.",
                ),
            ),
        ),
        _Operation(
            id="jira.issue.comment.get",
            product="jira",
            path="/rest/api/2/issue/{issueIdOrKey}/comment/{id}",
            description="Get one comment on a Jira issue.",
            documented_version=_JIRA_VERSION,
            kind="object",
            required=(),
            arguments=(
                _Argument(
                    "issueIdOrKey",
                    _JIRA_ISSUE_ID_OR_KEY,
                    "Jira issue key or positive numeric issue ID.",
                ),
                _Argument(
                    "id",
                    _JIRA_COMMENT_ID,
                    "Positive numeric Jira comment ID.",
                ),
            ),
            query=(
                _QueryField(
                    "expand", "string", False, "Comma-separated expansion names."
                ),
            ),
        ),
        _Operation(
            id="jira.issue.worklog.get",
            product="jira",
            path="/rest/api/2/issue/{issueIdOrKey}/worklog/{id}",
            description="Get one worklog entry for a Jira issue.",
            documented_version=_JIRA_VERSION,
            kind="object",
            required=(),
            arguments=(
                _Argument(
                    "issueIdOrKey",
                    _JIRA_ISSUE_ID_OR_KEY,
                    "Jira issue key or positive numeric issue ID.",
                ),
                _Argument(
                    "id",
                    _JIRA_WORKLOG_ID,
                    "Positive numeric Jira worklog ID.",
                ),
            ),
        ),
        _Operation(
            id="jira.issue-link.get",
            product="jira",
            path="/rest/api/2/issueLink/{linkId}",
            description="Get one Jira issue link by ID.",
            documented_version=_JIRA_VERSION,
            kind="object",
            required=(),
            arguments=(
                _Argument(
                    "linkId",
                    _JIRA_ISSUE_LINK_ID,
                    "Positive numeric Jira issue link ID.",
                ),
            ),
        ),
        _Operation(
            id="jira.filter.favourites",
            product="jira",
            path="/rest/api/2/filter/favourite",
            description="List the authenticated Jira user's favourite filters.",
            documented_version=_JIRA_VERSION,
            kind="array",
            required=(),
            query=(
                _QueryField(
                    "expand", "string", False, "Comma-separated expansion names."
                ),
            ),
        ),
        _Operation(
            id="jira.jql.autocomplete",
            product="jira",
            path="/rest/api/2/jql/autocompletedata",
            description="Get Jira JQL autocomplete field, function, and word data.",
            documented_version=_JIRA_VERSION,
            kind="object",
            required=(),
        ),
        _Operation(
            id="jira.dashboard.list",
            product="jira",
            path="/rest/api/2/dashboard",
            description="List one page of Jira dashboards visible to the user.",
            documented_version=_JIRA_VERSION,
            kind="object",
            required=(),
            query=(
                _QueryField(
                    "filter", "string", False, "Known filter values: favourite or my."
                ),
                _QueryField(
                    "startAt",
                    "integer",
                    False,
                    "Zero-based index of the first result.",
                    minimum=0,
                    maximum=_MAX_QUERY_INTEGER,
                ),
                _QueryField(
                    "maxResults",
                    "integer",
                    False,
                    "Requested page size; the server may apply a lower limit.",
                    minimum=1,
                    maximum=_MAX_QUERY_INTEGER,
                ),
            ),
        ),
        _Operation(
            id="confluence.content.by-title",
            product="confluence",
            path="/rest/api/content",
            description="Find Confluence pages by exact title, optionally in a space.",
            documented_version=_CONFLUENCE_VERSION,
            kind="object",
            required=(),
            query=(
                _QueryField(
                    "title",
                    "string",
                    True,
                    "Exact Confluence page title.",
                    allow_spaces=True,
                ),
                _QueryField("spaceKey", "string", False, "Confluence space key."),
                _QueryField(
                    "expand", "string", False, "Comma-separated expansion names."
                ),
                _QueryField(
                    "start",
                    "integer",
                    False,
                    "Zero-based index of the first result.",
                    minimum=0,
                    maximum=_MAX_QUERY_INTEGER,
                ),
                _QueryField(
                    "limit",
                    "integer",
                    False,
                    "Requested page size; the server may apply a lower limit.",
                    minimum=1,
                    maximum=_MAX_QUERY_INTEGER,
                ),
            ),
        ),
        _Operation(
            id="confluence.content.search",
            product="confluence",
            path="/rest/api/content/search",
            description="Search Confluence content with one CQL expression.",
            documented_version=_CONFLUENCE_VERSION,
            kind="object",
            required=(),
            query=(
                _QueryField(
                    "cql", "string", True, "Confluence CQL query.", allow_spaces=True
                ),
                _QueryField(
                    "expand", "string", False, "Comma-separated expansion names."
                ),
                _QueryField(
                    "start",
                    "integer",
                    False,
                    "Zero-based index of the first result.",
                    minimum=0,
                    maximum=_MAX_QUERY_INTEGER,
                ),
                _QueryField(
                    "limit",
                    "integer",
                    False,
                    "Requested page size; the server may apply a lower limit.",
                    minimum=1,
                    maximum=_MAX_QUERY_INTEGER,
                ),
            ),
        ),
        _Operation(
            id="confluence.space.content",
            product="confluence",
            path="/rest/api/space/{spaceKey}/content",
            description="List one page of content in a Confluence space.",
            documented_version=_CONFLUENCE_VERSION,
            kind="object",
            required=(),
            arguments=(
                _Argument(
                    "spaceKey",
                    _CONFLUENCE_SPACE_KEY,
                    "Confluence space key, optionally prefixed with ~ for a personal space.",
                ),
            ),
            query=(
                _QueryField(
                    "depth",
                    "string",
                    False,
                    "Content depth: all or root.",
                    allowed=("all", "root"),
                ),
                _QueryField(
                    "expand", "string", False, "Comma-separated expansion names."
                ),
                _QueryField(
                    "start",
                    "integer",
                    False,
                    "Zero-based index of the first result.",
                    minimum=0,
                    maximum=_MAX_QUERY_INTEGER,
                ),
                _QueryField(
                    "limit",
                    "integer",
                    False,
                    "Requested page size; the server may apply a lower limit.",
                    minimum=1,
                    maximum=_MAX_QUERY_INTEGER,
                ),
            ),
        ),
        _Operation(
            id="confluence.content.properties",
            product="confluence",
            path="/rest/api/content/{id}/property",
            description="List one page of Confluence content property entries.",
            documented_version=_CONFLUENCE_VERSION,
            kind="object",
            required=(),
            arguments=(
                _Argument(
                    "id",
                    _CONFLUENCE_CONTENT_ID,
                    "Positive numeric Confluence content ID.",
                ),
            ),
            query=(
                _QueryField(
                    "expand", "string", False, "Comma-separated expansion names."
                ),
                _QueryField(
                    "start",
                    "integer",
                    False,
                    "Zero-based index of the first result.",
                    minimum=0,
                    maximum=_MAX_QUERY_INTEGER,
                ),
                _QueryField(
                    "limit",
                    "integer",
                    False,
                    "Requested page size; the server may apply a lower limit.",
                    minimum=1,
                    maximum=_MAX_QUERY_INTEGER,
                ),
            ),
        ),
        _Operation(
            id="confluence.content.attachments",
            product="confluence",
            path="/rest/api/content/{id}/child/attachment",
            description="List one page of Confluence attachments on content.",
            documented_version=_CONFLUENCE_VERSION,
            kind="object",
            required=(),
            arguments=(
                _Argument(
                    "id",
                    _CONFLUENCE_CONTENT_ID,
                    "Positive numeric Confluence content ID.",
                ),
            ),
            query=(
                _QueryField(
                    "expand", "string", False, "Comma-separated expansion names."
                ),
                _QueryField(
                    "start",
                    "integer",
                    False,
                    "Zero-based index of the first result.",
                    minimum=0,
                    maximum=_MAX_QUERY_INTEGER,
                ),
                _QueryField(
                    "limit",
                    "integer",
                    False,
                    "Requested page size; the server may apply a lower limit.",
                    minimum=1,
                    maximum=_MAX_QUERY_INTEGER,
                ),
                _QueryField(
                    "filename",
                    "string",
                    False,
                    "Only attachments with this exact filename.",
                    allow_spaces=True,
                ),
                _QueryField(
                    "mediaType",
                    "string",
                    False,
                    "Only attachments with this media type.",
                ),
            ),
        ),
        _Operation(
            id="confluence.content.children",
            product="confluence",
            path="/rest/api/content/{id}/child",
            description="Get one page of direct Confluence content children.",
            documented_version=_CONFLUENCE_VERSION,
            kind="object",
            required=(),
            arguments=(
                _Argument(
                    "id",
                    _CONFLUENCE_CONTENT_ID,
                    "Positive numeric Confluence content ID.",
                ),
            ),
            query=(
                _QueryField(
                    "expand", "string", False, "Comma-separated expansion names."
                ),
                _QueryField(
                    "parentVersion",
                    "integer",
                    False,
                    "Content version whose children are requested.",
                    minimum=0,
                    maximum=_MAX_QUERY_INTEGER,
                ),
                _QueryField(
                    "start",
                    "integer",
                    False,
                    "Zero-based index of the first result.",
                    minimum=0,
                    maximum=_MAX_QUERY_INTEGER,
                ),
                _QueryField(
                    "limit",
                    "integer",
                    False,
                    "Requested page size; the server may apply a lower limit.",
                    minimum=1,
                    maximum=_MAX_QUERY_INTEGER,
                ),
            ),
        ),
        _Operation(
            id="confluence.user.get",
            product="confluence",
            path="/rest/api/user",
            description="Get one Confluence user by key or username.",
            documented_version=_CONFLUENCE_VERSION,
            kind="object",
            required=(),
            query=(
                _QueryField("key", "string", False, "Confluence user key."),
                _QueryField("username", "string", False, "Confluence username."),
                _QueryField(
                    "expand", "string", False, "Comma-separated expansion names."
                ),
            ),
            query_exactly_one=("key", "username"),
        ),
    )
}


def _manifest_entries() -> list[dict[str, object]]:
    """Load the generated read manifest, or nothing if it is unusable."""
    try:
        document = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    except OSError, ValueError:
        return []
    entries = document.get("operations")
    return entries if isinstance(entries, list) else []


def _manifest_operation(entry: dict[str, object]) -> _Operation | None:
    """Convert one manifest row into a registry operation, or skip it."""
    operation_id = entry.get("id")
    product = entry.get("product")
    method = entry.get("method")
    path = entry.get("path")
    if (
        not isinstance(operation_id, str)
        or product not in {"jira", "confluence", "bitbucket"}
        or method not in {"GET", "POST"}
        or not isinstance(path, str)
        or not path.startswith("/rest/")
    ):
        return None
    raw_arguments = entry.get("arguments")
    if not isinstance(raw_arguments, list):
        return None
    arguments: list[_Argument] = []
    for raw in raw_arguments:
        if not isinstance(raw, dict):
            return None
        name = raw.get("name")
        pattern = raw.get("pattern")
        description = raw.get("description", "")
        if not isinstance(name, str) or not isinstance(pattern, str):
            return None
        try:
            compiled = re.compile(pattern)
        except re.error:
            return None
        arguments.append(
            _Argument(
                name,
                compiled,
                str(description),
                allow_slash=bool(raw.get("allow_slash")),
            )
        )
    kind = entry.get("kind", "json")
    if kind not in {"json", "object", "array"}:
        return None
    return _Operation(
        id=operation_id,
        product=str(product),
        path=path,
        description=str(entry.get("description", "Read one endpoint.")),
        documented_version=str(entry.get("documented_version", "")),
        kind=cast(ResponseKind, kind),
        required=(),
        arguments=tuple(arguments),
        method=str(method),
    )


def _install_manifest_operations() -> int:
    """Merge generated routes that are not already hand-written."""
    routes = {(op.product, op.method, op.path) for op in _OPERATIONS.values()}
    added = 0
    for entry in _manifest_entries():
        operation = _manifest_operation(entry)
        if operation is None or operation.id in _OPERATIONS:
            continue
        key = (operation.product, operation.method, operation.path)
        if key in routes:
            continue
        _OPERATIONS[operation.id] = operation
        routes.add(key)
        added += 1
    return added


_install_manifest_operations()


def list_operations() -> list[dict[str, object]]:
    """Describe every registered operation without reading any credential.

    The result is a fresh, JSON-serializable list sorted by stable operation ID.
    Each entry exposes the product, fixed GET path, one-line description,
    documented version, expected JSON shape, accepted path arguments, and
    declared typed query fields.
    """
    return [_describe(_OPERATIONS[key]) for key in sorted(_OPERATIONS)]


def _describe(operation: _Operation) -> dict[str, object]:
    return {
        "id": operation.id,
        "product": operation.product,
        "method": operation.method,
        "path": operation.path,
        "description": operation.description,
        "documented_version": operation.documented_version,
        "response": {
            "kind": operation.kind,
            "required": [_field(field) for field in operation.required],
            "items_required": [_field(field) for field in operation.item_required],
            "optional_object_arrays": list(operation.object_arrays),
            "null_on_204": operation.null_on_204,
        },
        "arguments": [
            {
                "name": argument.name,
                "type": "string",
                "pattern": argument.pattern.pattern,
                "max_length": _MAX_ARGUMENT_LENGTH,
                "allow_slash": argument.allow_slash,
                "description": argument.description,
            }
            for argument in operation.arguments
        ],
        "query_rules": {
            "at_most_one": list(operation.query_at_most_one),
            "at_least_one": list(operation.query_at_least_one),
            "exactly_one": list(operation.query_exactly_one),
        },
        "body": [
            {
                "name": field.name,
                "type": field.kind,
                "required": field.required,
                "description": field.description,
                "enum": list(field.allowed),
                "maximum": field.maximum,
            }
            for field in operation.body
        ],
        "query": [
            {
                "name": field.name,
                "type": field.kind,
                "required": field.required,
                "description": field.description,
                "max_length": field.max_length,
                "minimum": field.minimum,
                "maximum": field.maximum,
                "format": (
                    "repository-id-or-project-key/repository-slug"
                    if field.from_repo
                    else None
                ),
                "enum": list(field.allowed),
            }
            for field in operation.query
        ],
    }


def _field(field: _Field) -> dict[str, str]:
    return {"name": field.name, "type": field.kind}


def _command(operation: _Operation) -> list[str]:
    """Return the canonical CLI words for one registered operation."""
    return ["atlawire", "read", operation.id]


def _example(operation: _Operation) -> dict[str, object]:
    """Describe an offline invocation; never invent an unsafe identifier."""
    values = _EXAMPLE_ARGUMENTS.get(operation.id)
    names = {argument.name for argument in operation.arguments}
    if values is None or set(values) != names:
        return {
            "note": (
                "No safe placeholder is registered; pass the documented "
                "arguments as a JSON object with --params."
            )
        }
    return {
        "argv": [
            *_command(operation),
            "--params",
            json.dumps(values, separators=(",", ":")),
        ]
    }


def describe_operation(operation_id: object) -> dict[str, object]:
    """Return one operation's full offline description.

    Raises [AtlaWireError][atlawire.http.AtlaWireError] for an unknown ID so a
    caller can map it without echoing the submitted value.
    """
    operation = _operation(operation_id)
    described = _describe(operation)
    described["command"] = _command(operation)
    described["example"] = _example(operation)
    return described


def canonical_operations() -> list[dict[str, object]]:
    """Return compact descriptions of the canonical agent-facing reads."""
    return [
        {
            "id": operation_id,
            "product": _OPERATIONS[operation_id].product,
            "description": _OPERATIONS[operation_id].description,
            "command": _command(_OPERATIONS[operation_id]),
            "example": _example(_OPERATIONS[operation_id]),
        }
        for operation_id in sorted(CANONICAL_IDS)
    ]


def _validated_body(
    operation: _Operation, body: Mapping[str, object] | None
) -> dict[str, object] | None:
    """Accept only declared body fields with their documented types."""
    if operation.method == "GET":
        if body is not None:
            raise AtlaWireError(_INVALID_BODY)
        return None
    if not isinstance(body, Mapping) or not operation.body:
        raise AtlaWireError(_INVALID_BODY)
    declared = {field.name: field for field in operation.body}
    if any(not isinstance(name, str) or name not in declared for name in body):
        raise AtlaWireError(_INVALID_BODY)
    validated: dict[str, object] = {}
    for field in operation.body:
        if field.name not in body:
            if field.required:
                raise AtlaWireError(_INVALID_BODY)
            continue
        value = body[field.name]
        if field.kind == "integer":
            if (
                not isinstance(value, int)
                or isinstance(value, bool)
                or (field.maximum is not None and value > field.maximum)
                or value < 0
            ):
                raise AtlaWireError(_INVALID_BODY)
        elif field.kind == "integer_array":
            if (
                not isinstance(value, list)
                or not value
                or len(value) > _MAX_WORKLOG_IDS
                or any(
                    not isinstance(item, int) or isinstance(item, bool) or item < 1
                    for item in value
                )
            ):
                raise AtlaWireError(_INVALID_BODY)
        elif (
            not isinstance(value, str)
            or not value
            or (field.allowed and value not in field.allowed)
            or any(ord(char) < 0x20 and ord(char) not in (9, 10, 13) for char in value)
        ):
            raise AtlaWireError(_INVALID_BODY)
        validated[field.name] = value
    return validated


def read_binary(
    operation_id: str,
    base_url: str,
    *,
    token: str,
    arguments: Mapping[str, object],
    destination: str,
    max_bytes: int = BINARY_MAX_BYTES,
    allow_http_loopback: bool = False,
) -> dict[str, object]:
    """Stream one registered binary read into ``destination``.

    The destination must not exist. Nothing is published on failure, and the
    returned receipt describes the complete file that was written.
    """
    operation = _operation(operation_id)
    if operation.kind != "binary":
        raise AtlaWireError(_NOT_BINARY)
    if not isinstance(destination, str) or not destination:
        raise AtlaWireError(_BINARY_TARGET)
    path = _render_path(operation, arguments)
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    if not isinstance(token, str):
        raise AtlaWireError(_INVALID_TOKEN)
    content_type, written, digest = sdk_download_to_file(
        operation.product,
        base,
        path,
        token=token,
        destination=destination,
        max_bytes=max_bytes,
        allow_http_loopback=allow_http_loopback,
    )
    return {
        "path": destination,
        "bytes": written,
        "sha256": digest,
        "content_type": content_type,
    }


def read_operation(
    operation_id: str,
    base_url: str,
    *,
    token: str,
    arguments: Mapping[str, object],
    query: Mapping[str, object] | None = None,
    body: Mapping[str, object] | None = None,
    allow_http_loopback: bool = False,
    use_library: bool = False,
) -> dict[str, object] | list[object] | None:
    """Execute exactly one registered fixed GET and return its raw JSON.

    Only ``operation_id``, the registered path arguments, and declared typed
    query fields are accepted. The destination is the supplied base URL joined
    with the operation's fixed path; the bearer token is sent only in the
    ``Authorization`` header. Unknown query names and malformed query values are
    rejected before any request. There is no arbitrary query string, body,
    caller-selected header, or link following. Exactly one request is made; no
    pagination or completeness is claimed.

    A response of the wrong top-level JSON kind, or an array with a non-object
    entry or an entry missing a documented required field, raises
    [AtlaWireError][atlawire.http.AtlaWireError] instead of returning a partial
    or silently reduced document. Only the Bitbucket default-branch operation
    maps its documented 204 to ``None``; a 200 JSON ``null`` remains an error.
    Unknown and administrative/mutating IDs are rejected before any request.
    """
    operation = _operation(operation_id)
    path = _render_path(operation, arguments)
    params = _validated_query(operation, query)
    payload_body = _validated_body(operation, body)
    base = normalize_base_url(base_url, allow_http_loopback=allow_http_loopback)
    if not isinstance(token, str):
        raise AtlaWireError(_INVALID_TOKEN)
    url = f"{base}{path}"
    if use_library:
        status, payload = sdk_request_json_with_status(
            operation.product,
            base,
            path,
            method=operation.method,
            token=token,
            params=params,
            body=payload_body,
            allow_http_loopback=allow_http_loopback,
        )
        no_content = status == 204 and payload is None
    elif operation.method != "GET":
        raise AtlaWireError("This operation requires the library transport.")
    else:
        status = None
        with bearer_session(token) as session:
            if operation.kind == "json":
                payload = get_json_any(session, url, params=params)
            elif operation.kind == "array":
                payload = get_json_array(session, url, params=params)
            elif operation.null_on_204:
                payload = get_json_object_allow_no_content(session, url, params=params)
            else:
                payload = get_json_object(session, url, params=params)
        # The strict helper returns None only for its documented 204.
        no_content = operation.null_on_204 and payload is None
    if payload is None:
        if no_content and operation.null_on_204:
            return None
        # A 200 whose body is JSON null is a shape error; the status, not the
        # value, decides whether the route may return null.
        raise _shape_error(operation, status)
    _validate_response(operation, payload, status)
    return cast(dict[str, object] | list[object], payload)


def _operation(operation_id: object) -> _Operation:
    if not isinstance(operation_id, str):
        raise AtlaWireError(_UNKNOWN_ID)
    operation = _OPERATIONS.get(operation_id)
    if operation is None:
        raise AtlaWireError(_UNKNOWN_ID)
    return operation


def _render_path(operation: _Operation, arguments: Mapping[str, object]) -> str:
    if not isinstance(arguments, Mapping):
        raise AtlaWireError(_INVALID_ARGUMENTS)
    expected = tuple(argument.name for argument in operation.arguments)
    try:
        provided = set(arguments)
    except TypeError:
        raise AtlaWireError(_INVALID_ARGUMENTS) from None
    if provided != set(expected):
        names = ", ".join(expected)
        raise AtlaWireError(f"Expected exactly the registered path arguments: {names}.")
    rendered = {
        argument.name: _segment(argument, arguments[argument.name])
        for argument in operation.arguments
    }
    # Replace explicitly: a repository-relative placeholder is written as
    # ``{path:.*}``, which is not a Python format field.
    path = operation.path
    for name, value in rendered.items():
        path = path.replace("{" + name + "}", value)
        path = path.replace("{" + name + ":.*}", value)
    if "{" in path:
        raise AtlaWireError("The registered route has an unresolved placeholder.")
    return path


def _segment(argument: _Argument, value: object) -> str:
    if not isinstance(value, str) or not value or len(value) > _MAX_ARGUMENT_LENGTH:
        raise AtlaWireError(_INVALID_VALUE.format(name=argument.name))
    parts = value.split("/") if argument.allow_slash else [value]
    if any(
        not part
        or part in {".", ".."}
        or _UNSAFE_SEGMENT.search(part)
        or argument.pattern.fullmatch(part) is None
        for part in parts
    ):
        raise AtlaWireError(_INVALID_VALUE.format(name=argument.name))
    # The accepted patterns already contain only unreserved ASCII, so this is
    # a single, idempotent encoding step rather than a second escape of an
    # already-encoded or escaped value.
    return "/".join(quote(part, safe="") for part in parts)


def _validated_query(
    operation: _Operation, query: Mapping[str, object] | None
) -> dict[str, str | int]:
    """Return only declared, typed query fields or raise one generic error."""
    if query is None:
        supplied: dict[str, object] = {}
    elif isinstance(query, Mapping):
        try:
            supplied = dict(query)
        except TypeError:
            raise AtlaWireError(_INVALID_QUERY) from None
    else:
        raise AtlaWireError(_INVALID_QUERY)
    fields = {field.name: field for field in operation.query}
    if any(not isinstance(name, str) or name not in fields for name in supplied):
        raise AtlaWireError(_INVALID_QUERY)
    present = set(supplied)
    if sum(name in present for name in operation.query_at_most_one) > 1:
        raise AtlaWireError(_INVALID_QUERY)
    if (
        operation.query_at_least_one
        and sum(name in present for name in operation.query_at_least_one) < 1
    ):
        raise AtlaWireError(_INVALID_QUERY)
    if (
        operation.query_exactly_one
        and sum(name in present for name in operation.query_exactly_one) != 1
    ):
        raise AtlaWireError(_INVALID_QUERY)
    validated: dict[str, str | int] = {}
    for field in operation.query:
        if field.name not in supplied:
            if field.required:
                raise AtlaWireError(_INVALID_QUERY)
            continue
        if any(name not in present for name in field.depends_on):
            raise AtlaWireError(_INVALID_QUERY)
        validated[field.name] = _query_value(field, supplied[field.name])
    return validated


def _query_value(field: _QueryField, value: object) -> str | int:
    if field.kind == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            raise AtlaWireError(_INVALID_QUERY)
        if field.minimum is not None and value < field.minimum:
            raise AtlaWireError(_INVALID_QUERY)
        if field.maximum is not None and value > field.maximum:
            raise AtlaWireError(_INVALID_QUERY)
        return value
    if not isinstance(value, str):
        raise AtlaWireError(_INVALID_QUERY)
    unsafe = _UNSAFE_QUERY_CONTROL if field.allow_spaces else _UNSAFE_QUERY_TEXT
    if (
        not value
        or (field.max_length is not None and len(value) > field.max_length)
        or unsafe.search(value)
        or any(0xD800 <= ord(char) <= 0xDFFF for char in value)
        or (field.allowed and value not in field.allowed)
    ):
        raise AtlaWireError(_INVALID_QUERY)
    if field.from_repo and not _valid_from_repo(value):
        raise AtlaWireError(_INVALID_QUERY)
    return value


def _valid_from_repo(value: str) -> bool:
    """Accept a positive repository ID or one projectKey/repositorySlug pair."""
    if _FROM_REPO_ID.fullmatch(value):
        return True
    project, separator, slug = value.partition("/")
    if (
        not separator
        or not project
        or not slug
        or "/" in slug
        or _FROM_REPO_PROJECT.fullmatch(project) is None
        or _FROM_REPO_SLUG.fullmatch(slug) is None
        or slug in {".", ".."}
    ):
        return False
    return True


def _validate_response(
    operation: _Operation, value: object, status: int | None = None
) -> None:
    if operation.kind == "json":
        return
    if operation.kind == "array":
        if not isinstance(value, list):
            raise _shape_error(operation, status)
        for entry in value:
            if not isinstance(entry, dict):
                raise _shape_error(operation, status)
            _require_fields(entry, operation.item_required, operation, status)
        return
    if not isinstance(value, dict):
        raise _shape_error(operation, status)
    _require_fields(value, operation.required, operation, status)
    for name in operation.object_arrays:
        nested = value.get(name)
        if nested is None:
            continue
        if not isinstance(nested, list) or any(
            not isinstance(entry, dict) for entry in nested
        ):
            raise _shape_error(operation, status)


def _require_fields(
    value: dict[str, object],
    fields: tuple[_Field, ...],
    operation: _Operation,
    status: int | None = None,
) -> None:
    for field in fields:
        if not _matches(value.get(field.name), field.kind):
            raise _shape_error(operation, status)


def _matches(value: object, kind: FieldKind) -> bool:
    if kind == "string":
        return isinstance(value, str)
    if kind == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "boolean":
        return isinstance(value, bool)
    return isinstance(value, dict)


def _shape_error(operation: _Operation, status: int | None = None) -> AtlaWireError:
    return OperationShapeError(
        _BAD_SHAPE.format(operation_id=operation.id), status=status
    )
