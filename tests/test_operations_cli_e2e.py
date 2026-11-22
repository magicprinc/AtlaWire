"""Installed-CLI loopback contracts for the static operation registry.

Expected CLI contract, wired by a separate change:

    atlawire operations
    atlawire read-operation ID --params '{"name":"value"}' \
        [--base-url URL] [--token-from-env] [--allow-http-loopback]

``operations`` prints the JSON array returned by
[list_operations][atlawire.operations.list_operations] and needs no credential.
``read-operation`` resolves the operation's product through the standard product
URL/token mechanism, calls
[read_operation][atlawire.operations.read_operation] once, and prints its raw
JSON result. ``--query`` is optional JSON object text; it must be parsed as an
object, reject duplicate object keys and non-object text, and pass only the
resulting mapping. The operation ID and path arguments are rejected before any
HTTP request, so an unknown, mutating, or administratively named ID never
reaches a server even when credentials exist. Errors exit nonzero with no
stdout.

Every response comes from a synthetic loopback server, every credential is a
fixture, and ``BBK_CREDENTIALS`` points at a path that must not exist. No test
contacts a real instance, reads a real credential store, or mutates server state.
"""

import json
import subprocess
from collections.abc import Mapping
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import cast
from urllib.parse import urlsplit

import pytest

from atlawire.operations import list_operations
from tests._loopback import (
    Request,
    request_record,
    run_installed,
    send_bytes,
    send_json,
    serving,
)

JIRA_CONTEXT = "/jira"
BITBUCKET_CONTEXT = "/bitbucket"
CONFLUENCE_CONTEXT = "/confluence"
JIRA_TOKEN = "synthetic-operations-jira-8a1"
BITBUCKET_TOKEN = "synthetic-operations-bitbucket-8a2"
CONFLUENCE_TOKEN = "synthetic-operations-confluence-8a3"
SENTINEL = "OPERATIONS-E2E-SENTINEL"
PARAM_SECRET = "SYNTHETIC-PARAMS-SECRET-4z9"
COMPARE_QUERY_NAMES = ("from", "to", "fromRepo", "start", "limit")
PAGING_QUERY_NAMES = ("start", "limit")
BITBUCKET_COMMIT_ID = "abcdef0123abcdef4567abcdef8987abcdef6543"
EXPECTED_QUERY_NAMES: dict[str, tuple[str, ...]] = {
    "bitbucket.repository.commit-comments": (
        "path",
        "since",
        "start",
        "limit",
    ),
    "bitbucket.repository.compare-changes": COMPARE_QUERY_NAMES,
    "bitbucket.repository.compare-commits": COMPARE_QUERY_NAMES,
    "bitbucket.repository.forks": PAGING_QUERY_NAMES,
    "bitbucket.repository.participants": (
        "direction",
        "filter",
        "role",
        "start",
        "limit",
    ),
    "bitbucket.repository.pull-request-activity": PAGING_QUERY_NAMES,
    "bitbucket.repository.related": PAGING_QUERY_NAMES,
    "bitbucket.profile.recent-repositories": PAGING_QUERY_NAMES,
    "bitbucket.users.list": PAGING_QUERY_NAMES,
    "jira.mypermissions.get": ("projectKey", "projectId", "issueKey", "issueId"),
    "jira.user.get": ("username", "key"),
    "jira.user.assignable-search": (
        "username",
        "project",
        "issueKey",
        "startAt",
        "maxResults",
        "actionDescriptorId",
    ),
    "jira.field.list": (),
    "jira.project.statuses": (),
    "jira.project.roles": (),
    "jira.issue.comment.get": ("expand",),
    "jira.issue.worklog.get": (),
    "jira.issue-link.get": (),
    "jira.filter.favourites": ("expand",),
    "jira.jql.autocomplete": (),
    "jira.dashboard.list": ("filter", "startAt", "maxResults"),
    "confluence.content.by-title": ("title", "spaceKey", "expand", "start", "limit"),
    "confluence.content.search": ("cql", "expand", "start", "limit"),
    "confluence.space.content": ("depth", "expand", "start", "limit"),
    "confluence.content.properties": ("expand", "start", "limit"),
    "confluence.content.attachments": (
        "expand",
        "start",
        "limit",
        "filename",
        "mediaType",
    ),
    "confluence.content.children": ("expand", "parentVersion", "start", "limit"),
    "confluence.user.get": ("key", "username", "expand"),
}
# Documented per-operation required query fields: only these two operations
# mandate a value, every other declared query field is optional. Kept separate
# from EXPECTED_QUERY_NAMES so a name can be declared without turning it required.
EXPECTED_REQUIRED_QUERY_NAMES: dict[str, tuple[str, ...]] = {
    "confluence.content.by-title": ("title",),
    "confluence.content.search": ("cql",),
}
MISSING_CREDENTIALS = Path(__file__).with_name(
    "bbk-credentials-missing-operations.json"
)

JIRA_PROJECT_PATH = f"{JIRA_CONTEXT}/rest/api/2/project/EX"
JIRA_VERSIONS_PATH = f"{JIRA_CONTEXT}/rest/api/2/project/EX/versions"
JIRA_COMPONENTS_PATH = f"{JIRA_CONTEXT}/rest/api/2/project/EX/components"
JIRA_WATCHERS_PATH = f"{JIRA_CONTEXT}/rest/api/2/issue/EX-1/watchers"
JIRA_VOTES_PATH = f"{JIRA_CONTEXT}/rest/api/2/issue/EX-1/votes"
JIRA_ATTACHMENT_PATH = f"{JIRA_CONTEXT}/rest/api/2/attachment/10001"
JIRA_ATTACHMENT_CONTENT_PATH = f"{JIRA_CONTEXT}/attachment/content/10001"
HONEYPOT_PATH = "/capture"
ADMIN_PATH = "/admin/rest/api/2/serverInfo"
BITBUCKET_PROJECT_PATH = f"{BITBUCKET_CONTEXT}/rest/api/1.0/projects/PRJ"
BITBUCKET_REPOSITORY_PATH = (
    f"{BITBUCKET_CONTEXT}/rest/api/1.0/projects/PRJ/repos/widgets"
)
BITBUCKET_COMMIT_COMMENTS_PATH = (
    f"{BITBUCKET_REPOSITORY_PATH}/commits/{BITBUCKET_COMMIT_ID}/comments"
)
BITBUCKET_FORKS_PATH = f"{BITBUCKET_REPOSITORY_PATH}/forks"
BITBUCKET_PARTICIPANTS_PATH = f"{BITBUCKET_REPOSITORY_PATH}/participants"
BITBUCKET_ACTIVITY_PATH = f"{BITBUCKET_REPOSITORY_PATH}/pull-requests/7/activities"
BITBUCKET_RELATED_PATH = f"{BITBUCKET_REPOSITORY_PATH}/related"
BITBUCKET_PROFILE_RECENT_PATH = f"{BITBUCKET_CONTEXT}/rest/api/1.0/profile/recent/repos"
BITBUCKET_TASK_PATH = f"{BITBUCKET_CONTEXT}/rest/api/1.0/tasks/99"
BITBUCKET_USER_PATH = f"{BITBUCKET_CONTEXT}/rest/api/1.0/users/jcitizen"
BITBUCKET_USERS_PATH = f"{BITBUCKET_CONTEXT}/rest/api/1.0/users"
BITBUCKET_COMPARE_CHANGES_PATH = f"{BITBUCKET_REPOSITORY_PATH}/compare/changes"
BITBUCKET_COMPARE_COMMITS_PATH = f"{BITBUCKET_REPOSITORY_PATH}/compare/commits"
BITBUCKET_DEFAULT_BRANCH_PATH = f"{BITBUCKET_REPOSITORY_PATH}/branches/default"
CONFLUENCE_SPACE_PATH = f"{CONFLUENCE_CONTEXT}/rest/api/space/TST"
JIRA_MYPERMISSIONS_GET_PATH = f"{JIRA_CONTEXT}/rest/api/2/mypermissions"
JIRA_USER_GET_PATH = f"{JIRA_CONTEXT}/rest/api/2/user"
JIRA_USER_ASSIGNABLE_SEARCH_PATH = f"{JIRA_CONTEXT}/rest/api/2/user/assignable/search"
JIRA_FIELD_LIST_PATH = f"{JIRA_CONTEXT}/rest/api/2/field"
JIRA_PROJECT_STATUSES_PATH = f"{JIRA_CONTEXT}/rest/api/2/project/EX/statuses"
JIRA_PROJECT_ROLES_PATH = f"{JIRA_CONTEXT}/rest/api/2/project/EX/role"
JIRA_ISSUE_COMMENT_GET_PATH = f"{JIRA_CONTEXT}/rest/api/2/issue/EX-1/comment/10000"
JIRA_ISSUE_WORKLOG_GET_PATH = f"{JIRA_CONTEXT}/rest/api/2/issue/EX-1/worklog/10001"
JIRA_ISSUE_LINK_GET_PATH = f"{JIRA_CONTEXT}/rest/api/2/issueLink/10002"
JIRA_FILTER_FAVOURITES_PATH = f"{JIRA_CONTEXT}/rest/api/2/filter/favourite"
JIRA_JQL_AUTOCOMPLETE_PATH = f"{JIRA_CONTEXT}/rest/api/2/jql/autocompletedata"
JIRA_DASHBOARD_LIST_PATH = f"{JIRA_CONTEXT}/rest/api/2/dashboard"
CONFLUENCE_CONTENT_BY_TITLE_PATH = f"{CONFLUENCE_CONTEXT}/rest/api/content"
CONFLUENCE_CONTENT_SEARCH_PATH = f"{CONFLUENCE_CONTEXT}/rest/api/content/search"
CONFLUENCE_SPACE_CONTENT_PATH = f"{CONFLUENCE_CONTEXT}/rest/api/space/TST/content"
CONFLUENCE_CONTENT_PROPERTIES_PATH = (
    f"{CONFLUENCE_CONTEXT}/rest/api/content/1234/property"
)
CONFLUENCE_CONTENT_ATTACHMENTS_PATH = (
    f"{CONFLUENCE_CONTEXT}/rest/api/content/1234/child/attachment"
)
CONFLUENCE_CONTENT_CHILDREN_PATH = f"{CONFLUENCE_CONTEXT}/rest/api/content/1234/child"
CONFLUENCE_USER_GET_PATH = f"{CONFLUENCE_CONTEXT}/rest/api/user"

EXPECTED_CATALOG: dict[str, tuple[str, str]] = {
    "bitbucket.project.get": (
        "bitbucket",
        "/rest/api/1.0/projects/{projectKey}",
    ),
    "bitbucket.repository.compare-changes": (
        "bitbucket",
        ("/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/compare/changes"),
    ),
    "bitbucket.repository.compare-commits": (
        "bitbucket",
        ("/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/compare/commits"),
    ),
    "bitbucket.profile.recent-repositories": (
        "bitbucket",
        "/rest/api/1.0/profile/recent/repos",
    ),
    "bitbucket.repository.commit-comments": (
        "bitbucket",
        (
            "/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}"
            "/commits/{commitId}/comments"
        ),
    ),
    "bitbucket.repository.forks": (
        "bitbucket",
        ("/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/forks"),
    ),
    "bitbucket.repository.participants": (
        "bitbucket",
        ("/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/participants"),
    ),
    "bitbucket.repository.pull-request-activity": (
        "bitbucket",
        (
            "/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}"
            "/pull-requests/{pullRequestId}/activities"
        ),
    ),
    "bitbucket.repository.related": (
        "bitbucket",
        ("/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/related"),
    ),
    "bitbucket.task.get": ("bitbucket", "/rest/api/1.0/tasks/{taskId}"),
    "bitbucket.user.get": ("bitbucket", "/rest/api/1.0/users/{userSlug}"),
    "bitbucket.users.list": ("bitbucket", "/rest/api/1.0/users"),
    "jira.mypermissions.get": ("jira", "/rest/api/2/mypermissions"),
    "jira.user.get": ("jira", "/rest/api/2/user"),
    "jira.user.assignable-search": ("jira", "/rest/api/2/user/assignable/search"),
    "jira.field.list": ("jira", "/rest/api/2/field"),
    "jira.project.statuses": (
        "jira",
        "/rest/api/2/project/{projectIdOrKey}/statuses",
    ),
    "jira.project.roles": (
        "jira",
        "/rest/api/2/project/{projectIdOrKey}/role",
    ),
    "jira.issue.comment.get": (
        "jira",
        "/rest/api/2/issue/{issueIdOrKey}/comment/{id}",
    ),
    "jira.issue.worklog.get": (
        "jira",
        "/rest/api/2/issue/{issueIdOrKey}/worklog/{id}",
    ),
    "jira.issue-link.get": (
        "jira",
        "/rest/api/2/issueLink/{linkId}",
    ),
    "jira.filter.favourites": ("jira", "/rest/api/2/filter/favourite"),
    "jira.jql.autocomplete": ("jira", "/rest/api/2/jql/autocompletedata"),
    "jira.dashboard.list": ("jira", "/rest/api/2/dashboard"),
    "confluence.content.by-title": ("confluence", "/rest/api/content"),
    "confluence.content.search": ("confluence", "/rest/api/content/search"),
    "confluence.space.content": (
        "confluence",
        "/rest/api/space/{spaceKey}/content",
    ),
    "confluence.content.properties": (
        "confluence",
        "/rest/api/content/{id}/property",
    ),
    "confluence.content.attachments": (
        "confluence",
        "/rest/api/content/{id}/child/attachment",
    ),
    "confluence.content.children": (
        "confluence",
        "/rest/api/content/{id}/child",
    ),
    "confluence.user.get": ("confluence", "/rest/api/user"),
    "bitbucket.repository.default-branch": (
        "bitbucket",
        ("/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/branches/default"),
    ),
    "bitbucket.repository.get": (
        "bitbucket",
        "/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}",
    ),
    "confluence.space.get": ("confluence", "/rest/api/space/{spaceKey}"),
    "jira.attachment.get": ("jira", "/rest/api/2/attachment/{id}"),
    "jira.issue.votes": ("jira", "/rest/api/2/issue/{issueIdOrKey}/votes"),
    "jira.issue.watchers": ("jira", "/rest/api/2/issue/{issueIdOrKey}/watchers"),
    "jira.project.components": (
        "jira",
        "/rest/api/2/project/{projectIdOrKey}/components",
    ),
    "jira.project.get": ("jira", "/rest/api/2/project/{projectIdOrKey}"),
    "jira.project.versions": (
        "jira",
        "/rest/api/2/project/{projectIdOrKey}/versions",
    ),
}

JIRA_PROJECT_BODY: dict[str, object] = {
    "id": "10000",
    "key": "EX",
    "name": "Example",
    "unknownField": {"kept": True},
    "_links": {"self": "https://other.example/rest/api/2/project/EX"},
}
JIRA_VERSIONS_BODY: list[dict[str, object]] = [
    {"id": "10000", "name": "1.0", "released": True},
    {"id": "10010", "name": "2.0", "extra": "kept"},
]
JIRA_COMPONENTS_BODY: list[dict[str, object]] = [
    {"id": "10000", "name": "Component 1", "isAssigneeTypeValid": False},
    {"id": "10050", "name": "PXA", "isAssigneeTypeValid": True},
]
JIRA_WATCHERS_BODY: dict[str, object] = {
    "isWatching": False,
    "watchCount": 1,
    "watchers": [{"name": "fred"}],
}
JIRA_VOTES_BODY: dict[str, object] = {
    "votes": 2,
    "hasVoted": True,
    "voters": [{"name": "fred"}, {"name": "anna"}],
}
JIRA_ATTACHMENT_BODY: dict[str, object] = {
    "self": f"https://other.example{JIRA_ATTACHMENT_PATH}",
    "filename": "report.txt",
    "size": 1234,
    "mimeType": "text/plain",
    "content": f"https://other.example{JIRA_ATTACHMENT_CONTENT_PATH}",
    "_links": {"download": "https://other.example/attachment/content/10001"},
}
BITBUCKET_PROJECT_BODY: dict[str, object] = {
    "key": "PRJ",
    "id": 1,
    "name": "My Cool Project",
    "public": False,
}
BITBUCKET_REPOSITORY_BODY: dict[str, object] = {
    "slug": "widgets",
    "id": 2,
    "name": "Widgets",
    "state": "AVAILABLE",
    "project": {"key": "PRJ"},
}
BITBUCKET_COMPARE_CHANGES_BODY: dict[str, object] = {
    "size": 1,
    "limit": 25,
    "isLastPage": True,
    "values": [
        {
            "contentId": "abcdef0123abcdef4567abcdef8987abcdef6543",
            "type": "MODIFY",
            "path": {"toString": "src/a.py"},
        }
    ],
    "start": 0,
}
BITBUCKET_COMPARE_COMMITS_BODY: dict[str, object] = {
    "size": 1,
    "limit": 25,
    "isLastPage": False,
    "nextPageStart": 1,
    "values": [
        {
            "id": "def0123abcdef4567abcdef8987abcdef6543abc",
            "displayId": "def0123abcd",
            "message": "More work",
        }
    ],
    "start": 0,
    "authorCount": 1,
    "totalCount": 2,
}
BITBUCKET_COMMIT_COMMENTS_BODY: dict[str, object] = {
    "size": 1,
    "limit": 25,
    "isLastPage": True,
    "values": [{"id": 101, "text": "A comment", "state": "OPEN"}],
    "start": 0,
}
BITBUCKET_FORKS_BODY: dict[str, object] = {
    "size": 1,
    "limit": 25,
    "isLastPage": True,
    "values": [{"slug": "widgets-fork"}],
    "start": 0,
}
BITBUCKET_PARTICIPANTS_BODY: dict[str, object] = {
    "size": 1,
    "limit": 25,
    "isLastPage": True,
    "values": [{"name": "charlie", "role": "REVIEWER"}],
    "start": 0,
}
BITBUCKET_ACTIVITY_BODY: dict[str, object] = {
    "size": 1,
    "limit": 25,
    "isLastPage": True,
    "values": [{"id": 101, "action": "COMMENTED"}],
    "start": 0,
}
BITBUCKET_RELATED_BODY: dict[str, object] = {
    "size": 1,
    "limit": 25,
    "isLastPage": True,
    "values": [{"slug": "widgets-related"}],
    "start": 0,
}
BITBUCKET_PROFILE_RECENT_BODY: dict[str, object] = {
    "size": 1,
    "limit": 25,
    "isLastPage": True,
    "values": [{"slug": "recent"}],
    "start": 0,
}
BITBUCKET_TASK_BODY: dict[str, object] = {
    "id": 99,
    "text": "Resolve the merge conflicts",
    "state": "OPEN",
}
BITBUCKET_USER_BODY: dict[str, object] = {
    "slug": "jcitizen",
    "name": "jcitizen",
    "displayName": "Jane Citizen",
}
BITBUCKET_USERS_BODY: dict[str, object] = {
    "size": 1,
    "limit": 25,
    "isLastPage": True,
    "values": [{"slug": "jcitizen", "name": "jcitizen"}],
    "start": 0,
}
BITBUCKET_DEFAULT_BRANCH_BODY: dict[str, object] = {
    "id": "refs/heads/master",
    "displayId": "master",
    "type": "BRANCH",
    "isDefault": True,
}
CONFLUENCE_SPACE_BODY: dict[str, object] = {
    "id": 11,
    "key": "TST",
    "name": "Example space",
    "type": "global",
}

JIRA_MYPERMISSIONS_GET_BODY = {"permissions": {"EDIT_ISSUE": {"havePermission": True}}}
JIRA_USER_GET_BODY = {"active": True, "name": "fred", "displayName": "Fred"}
JIRA_USER_ASSIGNABLE_SEARCH_BODY = [{"active": True, "name": "fred"}]
JIRA_FIELD_LIST_BODY = [{"id": "summary", "name": "Summary", "custom": False}]
JIRA_PROJECT_STATUSES_BODY = [
    {"id": "1", "name": "Task", "subtask": False, "statuses": []}
]
JIRA_PROJECT_ROLES_BODY = {
    "Developers": "https://atlassian.example/rest/api/2/project/EX/role/10000"
}
JIRA_ISSUE_COMMENT_GET_BODY = {"id": "10000", "body": "A comment"}
JIRA_ISSUE_WORKLOG_GET_BODY = {"id": "10001", "timeSpent": "3h"}
JIRA_ISSUE_LINK_GET_BODY = {"id": "10002", "type": {"name": "Duplicate"}}
JIRA_FILTER_FAVOURITES_BODY = [{"id": "10000", "name": "All Open Bugs"}]
JIRA_JQL_AUTOCOMPLETE_BODY = {
    "visibleFieldNames": [],
    "visibleFunctionNames": [],
    "jqlReservedWords": [],
}
JIRA_DASHBOARD_LIST_BODY = {
    "startAt": 0,
    "maxResults": 10,
    "total": 1,
    "dashboards": [{"id": "10000", "name": "System Dashboard"}],
}
CONFLUENCE_CONTENT_BY_TITLE_BODY = {
    "results": [{"id": "1234", "type": "page", "title": "Example"}],
    "size": 1,
}
CONFLUENCE_CONTENT_SEARCH_BODY = {
    "results": [{"id": "1234", "title": "Example"}],
    "size": 1,
}
CONFLUENCE_SPACE_CONTENT_BODY = {
    "results": [{"id": "1234", "title": "Example"}],
    "size": 1,
}
CONFLUENCE_CONTENT_PROPERTIES_BODY = {
    "results": [{"key": "example-property-key"}],
    "size": 1,
}
CONFLUENCE_CONTENT_ATTACHMENTS_BODY = {
    "results": [{"id": "att1", "title": "file.txt"}],
    "size": 1,
}
CONFLUENCE_CONTENT_CHILDREN_BODY = {"page": {"results": [{"id": "1234"}], "size": 1}}
CONFLUENCE_USER_GET_BODY = {"type": "known", "username": "jcitizen"}

BODIES: dict[str, object] = {
    JIRA_PROJECT_PATH: JIRA_PROJECT_BODY,
    JIRA_VERSIONS_PATH: JIRA_VERSIONS_BODY,
    JIRA_COMPONENTS_PATH: JIRA_COMPONENTS_BODY,
    JIRA_WATCHERS_PATH: JIRA_WATCHERS_BODY,
    JIRA_VOTES_PATH: JIRA_VOTES_BODY,
    JIRA_ATTACHMENT_PATH: JIRA_ATTACHMENT_BODY,
    BITBUCKET_PROJECT_PATH: BITBUCKET_PROJECT_BODY,
    BITBUCKET_REPOSITORY_PATH: BITBUCKET_REPOSITORY_BODY,
    BITBUCKET_COMMIT_COMMENTS_PATH: BITBUCKET_COMMIT_COMMENTS_BODY,
    BITBUCKET_FORKS_PATH: BITBUCKET_FORKS_BODY,
    BITBUCKET_PARTICIPANTS_PATH: BITBUCKET_PARTICIPANTS_BODY,
    BITBUCKET_ACTIVITY_PATH: BITBUCKET_ACTIVITY_BODY,
    BITBUCKET_RELATED_PATH: BITBUCKET_RELATED_BODY,
    BITBUCKET_PROFILE_RECENT_PATH: BITBUCKET_PROFILE_RECENT_BODY,
    BITBUCKET_TASK_PATH: BITBUCKET_TASK_BODY,
    BITBUCKET_USER_PATH: BITBUCKET_USER_BODY,
    BITBUCKET_USERS_PATH: BITBUCKET_USERS_BODY,
    BITBUCKET_COMPARE_CHANGES_PATH: BITBUCKET_COMPARE_CHANGES_BODY,
    BITBUCKET_COMPARE_COMMITS_PATH: BITBUCKET_COMPARE_COMMITS_BODY,
    BITBUCKET_DEFAULT_BRANCH_PATH: BITBUCKET_DEFAULT_BRANCH_BODY,
    CONFLUENCE_SPACE_PATH: CONFLUENCE_SPACE_BODY,
    JIRA_MYPERMISSIONS_GET_PATH: JIRA_MYPERMISSIONS_GET_BODY,
    JIRA_USER_GET_PATH: JIRA_USER_GET_BODY,
    JIRA_USER_ASSIGNABLE_SEARCH_PATH: JIRA_USER_ASSIGNABLE_SEARCH_BODY,
    JIRA_FIELD_LIST_PATH: JIRA_FIELD_LIST_BODY,
    JIRA_PROJECT_STATUSES_PATH: JIRA_PROJECT_STATUSES_BODY,
    JIRA_PROJECT_ROLES_PATH: JIRA_PROJECT_ROLES_BODY,
    JIRA_ISSUE_COMMENT_GET_PATH: JIRA_ISSUE_COMMENT_GET_BODY,
    JIRA_ISSUE_WORKLOG_GET_PATH: JIRA_ISSUE_WORKLOG_GET_BODY,
    JIRA_ISSUE_LINK_GET_PATH: JIRA_ISSUE_LINK_GET_BODY,
    JIRA_FILTER_FAVOURITES_PATH: JIRA_FILTER_FAVOURITES_BODY,
    JIRA_JQL_AUTOCOMPLETE_PATH: JIRA_JQL_AUTOCOMPLETE_BODY,
    JIRA_DASHBOARD_LIST_PATH: JIRA_DASHBOARD_LIST_BODY,
    CONFLUENCE_CONTENT_BY_TITLE_PATH: CONFLUENCE_CONTENT_BY_TITLE_BODY,
    CONFLUENCE_CONTENT_SEARCH_PATH: CONFLUENCE_CONTENT_SEARCH_BODY,
    CONFLUENCE_SPACE_CONTENT_PATH: CONFLUENCE_SPACE_CONTENT_BODY,
    CONFLUENCE_CONTENT_PROPERTIES_PATH: CONFLUENCE_CONTENT_PROPERTIES_BODY,
    CONFLUENCE_CONTENT_ATTACHMENTS_PATH: CONFLUENCE_CONTENT_ATTACHMENTS_BODY,
    CONFLUENCE_CONTENT_CHILDREN_PATH: CONFLUENCE_CONTENT_CHILDREN_BODY,
    CONFLUENCE_USER_GET_PATH: CONFLUENCE_USER_GET_BODY,
}

CASES = [
    (
        "jira.project.get",
        {"projectIdOrKey": "EX"},
        JIRA_CONTEXT,
        JIRA_PROJECT_PATH,
        JIRA_TOKEN,
        JIRA_PROJECT_BODY,
    ),
    (
        "jira.project.versions",
        {"projectIdOrKey": "EX"},
        JIRA_CONTEXT,
        JIRA_VERSIONS_PATH,
        JIRA_TOKEN,
        JIRA_VERSIONS_BODY,
    ),
    (
        "jira.project.components",
        {"projectIdOrKey": "EX"},
        JIRA_CONTEXT,
        JIRA_COMPONENTS_PATH,
        JIRA_TOKEN,
        JIRA_COMPONENTS_BODY,
    ),
    (
        "jira.issue.watchers",
        {"issueIdOrKey": "EX-1"},
        JIRA_CONTEXT,
        JIRA_WATCHERS_PATH,
        JIRA_TOKEN,
        JIRA_WATCHERS_BODY,
    ),
    (
        "jira.issue.votes",
        {"issueIdOrKey": "EX-1"},
        JIRA_CONTEXT,
        JIRA_VOTES_PATH,
        JIRA_TOKEN,
        JIRA_VOTES_BODY,
    ),
    (
        "jira.attachment.get",
        {"id": "10001"},
        JIRA_CONTEXT,
        JIRA_ATTACHMENT_PATH,
        JIRA_TOKEN,
        JIRA_ATTACHMENT_BODY,
    ),
    (
        "bitbucket.project.get",
        {"projectKey": "PRJ"},
        BITBUCKET_CONTEXT,
        BITBUCKET_PROJECT_PATH,
        BITBUCKET_TOKEN,
        BITBUCKET_PROJECT_BODY,
    ),
    (
        "bitbucket.repository.get",
        {"projectKey": "PRJ", "repositorySlug": "widgets"},
        BITBUCKET_CONTEXT,
        BITBUCKET_REPOSITORY_PATH,
        BITBUCKET_TOKEN,
        BITBUCKET_REPOSITORY_BODY,
    ),
    (
        "bitbucket.repository.compare-changes",
        {"projectKey": "PRJ", "repositorySlug": "widgets"},
        BITBUCKET_CONTEXT,
        BITBUCKET_COMPARE_CHANGES_PATH,
        BITBUCKET_TOKEN,
        BITBUCKET_COMPARE_CHANGES_BODY,
    ),
    (
        "bitbucket.repository.compare-commits",
        {"projectKey": "PRJ", "repositorySlug": "widgets"},
        BITBUCKET_CONTEXT,
        BITBUCKET_COMPARE_COMMITS_PATH,
        BITBUCKET_TOKEN,
        BITBUCKET_COMPARE_COMMITS_BODY,
    ),
    (
        "bitbucket.repository.commit-comments",
        {
            "projectKey": "PRJ",
            "repositorySlug": "widgets",
            "commitId": BITBUCKET_COMMIT_ID,
        },
        BITBUCKET_CONTEXT,
        BITBUCKET_COMMIT_COMMENTS_PATH,
        BITBUCKET_TOKEN,
        BITBUCKET_COMMIT_COMMENTS_BODY,
    ),
    (
        "bitbucket.repository.forks",
        {"projectKey": "PRJ", "repositorySlug": "widgets"},
        BITBUCKET_CONTEXT,
        BITBUCKET_FORKS_PATH,
        BITBUCKET_TOKEN,
        BITBUCKET_FORKS_BODY,
    ),
    (
        "bitbucket.repository.participants",
        {"projectKey": "PRJ", "repositorySlug": "widgets"},
        BITBUCKET_CONTEXT,
        BITBUCKET_PARTICIPANTS_PATH,
        BITBUCKET_TOKEN,
        BITBUCKET_PARTICIPANTS_BODY,
    ),
    (
        "bitbucket.repository.pull-request-activity",
        {
            "projectKey": "PRJ",
            "repositorySlug": "widgets",
            "pullRequestId": "7",
        },
        BITBUCKET_CONTEXT,
        BITBUCKET_ACTIVITY_PATH,
        BITBUCKET_TOKEN,
        BITBUCKET_ACTIVITY_BODY,
    ),
    (
        "bitbucket.repository.related",
        {"projectKey": "PRJ", "repositorySlug": "widgets"},
        BITBUCKET_CONTEXT,
        BITBUCKET_RELATED_PATH,
        BITBUCKET_TOKEN,
        BITBUCKET_RELATED_BODY,
    ),
    (
        "bitbucket.profile.recent-repositories",
        {},
        BITBUCKET_CONTEXT,
        BITBUCKET_PROFILE_RECENT_PATH,
        BITBUCKET_TOKEN,
        BITBUCKET_PROFILE_RECENT_BODY,
    ),
    (
        "bitbucket.task.get",
        {"taskId": "99"},
        BITBUCKET_CONTEXT,
        BITBUCKET_TASK_PATH,
        BITBUCKET_TOKEN,
        BITBUCKET_TASK_BODY,
    ),
    (
        "bitbucket.user.get",
        {"userSlug": "jcitizen"},
        BITBUCKET_CONTEXT,
        BITBUCKET_USER_PATH,
        BITBUCKET_TOKEN,
        BITBUCKET_USER_BODY,
    ),
    (
        "bitbucket.users.list",
        {},
        BITBUCKET_CONTEXT,
        BITBUCKET_USERS_PATH,
        BITBUCKET_TOKEN,
        BITBUCKET_USERS_BODY,
    ),
    (
        "bitbucket.repository.default-branch",
        {"projectKey": "PRJ", "repositorySlug": "widgets"},
        BITBUCKET_CONTEXT,
        BITBUCKET_DEFAULT_BRANCH_PATH,
        BITBUCKET_TOKEN,
        BITBUCKET_DEFAULT_BRANCH_BODY,
    ),
    (
        "confluence.space.get",
        {"spaceKey": "TST"},
        CONFLUENCE_CONTEXT,
        CONFLUENCE_SPACE_PATH,
        CONFLUENCE_TOKEN,
        CONFLUENCE_SPACE_BODY,
    ),
    (
        "jira.mypermissions.get",
        {},
        JIRA_CONTEXT,
        JIRA_MYPERMISSIONS_GET_PATH,
        JIRA_TOKEN,
        JIRA_MYPERMISSIONS_GET_BODY,
    ),
    (
        "jira.field.list",
        {},
        JIRA_CONTEXT,
        JIRA_FIELD_LIST_PATH,
        JIRA_TOKEN,
        JIRA_FIELD_LIST_BODY,
    ),
    (
        "jira.project.statuses",
        {"projectIdOrKey": "EX"},
        JIRA_CONTEXT,
        JIRA_PROJECT_STATUSES_PATH,
        JIRA_TOKEN,
        JIRA_PROJECT_STATUSES_BODY,
    ),
    (
        "jira.project.roles",
        {"projectIdOrKey": "EX"},
        JIRA_CONTEXT,
        JIRA_PROJECT_ROLES_PATH,
        JIRA_TOKEN,
        JIRA_PROJECT_ROLES_BODY,
    ),
    (
        "jira.issue.comment.get",
        {"issueIdOrKey": "EX-1", "id": "10000"},
        JIRA_CONTEXT,
        JIRA_ISSUE_COMMENT_GET_PATH,
        JIRA_TOKEN,
        JIRA_ISSUE_COMMENT_GET_BODY,
    ),
    (
        "jira.issue.worklog.get",
        {"issueIdOrKey": "EX-1", "id": "10001"},
        JIRA_CONTEXT,
        JIRA_ISSUE_WORKLOG_GET_PATH,
        JIRA_TOKEN,
        JIRA_ISSUE_WORKLOG_GET_BODY,
    ),
    (
        "jira.issue-link.get",
        {"linkId": "10002"},
        JIRA_CONTEXT,
        JIRA_ISSUE_LINK_GET_PATH,
        JIRA_TOKEN,
        JIRA_ISSUE_LINK_GET_BODY,
    ),
    (
        "jira.filter.favourites",
        {},
        JIRA_CONTEXT,
        JIRA_FILTER_FAVOURITES_PATH,
        JIRA_TOKEN,
        JIRA_FILTER_FAVOURITES_BODY,
    ),
    (
        "jira.jql.autocomplete",
        {},
        JIRA_CONTEXT,
        JIRA_JQL_AUTOCOMPLETE_PATH,
        JIRA_TOKEN,
        JIRA_JQL_AUTOCOMPLETE_BODY,
    ),
    (
        "jira.dashboard.list",
        {},
        JIRA_CONTEXT,
        JIRA_DASHBOARD_LIST_PATH,
        JIRA_TOKEN,
        JIRA_DASHBOARD_LIST_BODY,
    ),
    (
        "confluence.space.content",
        {"spaceKey": "TST"},
        CONFLUENCE_CONTEXT,
        CONFLUENCE_SPACE_CONTENT_PATH,
        CONFLUENCE_TOKEN,
        CONFLUENCE_SPACE_CONTENT_BODY,
    ),
    (
        "confluence.content.properties",
        {"id": "1234"},
        CONFLUENCE_CONTEXT,
        CONFLUENCE_CONTENT_PROPERTIES_PATH,
        CONFLUENCE_TOKEN,
        CONFLUENCE_CONTENT_PROPERTIES_BODY,
    ),
    (
        "confluence.content.attachments",
        {"id": "1234"},
        CONFLUENCE_CONTEXT,
        CONFLUENCE_CONTENT_ATTACHMENTS_PATH,
        CONFLUENCE_TOKEN,
        CONFLUENCE_CONTENT_ATTACHMENTS_BODY,
    ),
    (
        "confluence.content.children",
        {"id": "1234"},
        CONFLUENCE_CONTEXT,
        CONFLUENCE_CONTENT_CHILDREN_PATH,
        CONFLUENCE_TOKEN,
        CONFLUENCE_CONTENT_CHILDREN_BODY,
    ),
]

QUERY_CASES = [
    (
        "jira.user.get",
        {},
        {"username": "fred"},
        JIRA_CONTEXT,
        JIRA_USER_GET_PATH,
        JIRA_TOKEN,
        JIRA_USER_GET_BODY,
    ),
    (
        "jira.user.assignable-search",
        {},
        {"project": "EX"},
        JIRA_CONTEXT,
        JIRA_USER_ASSIGNABLE_SEARCH_PATH,
        JIRA_TOKEN,
        JIRA_USER_ASSIGNABLE_SEARCH_BODY,
    ),
    (
        "confluence.content.by-title",
        {},
        {"title": "Example Page"},
        CONFLUENCE_CONTEXT,
        CONFLUENCE_CONTENT_BY_TITLE_PATH,
        CONFLUENCE_TOKEN,
        CONFLUENCE_CONTENT_BY_TITLE_BODY,
    ),
    (
        "confluence.content.search",
        {},
        {"cql": "space = TST"},
        CONFLUENCE_CONTEXT,
        CONFLUENCE_CONTENT_SEARCH_PATH,
        CONFLUENCE_TOKEN,
        CONFLUENCE_CONTENT_SEARCH_BODY,
    ),
    (
        "confluence.user.get",
        {},
        {"username": "jcitizen"},
        CONFLUENCE_CONTEXT,
        CONFLUENCE_USER_GET_PATH,
        CONFLUENCE_TOKEN,
        CONFLUENCE_USER_GET_BODY,
    ),
]


def honeypot_project_body(origin: str) -> dict[str, object]:
    """A successful Jira project whose URLs point only at the honeypot."""
    return {
        "id": "10000",
        "key": "EX",
        "name": "Example",
        "self": f"{origin}/rest/api/2/project/EX",
        "url": f"{origin}/browse/EX",
        "_links": {
            "self": [{"href": f"{origin}/rest/api/2/project/EX"}],
            "next": f"{origin}/next",
        },
        "components": [{"self": f"{origin}/rest/api/2/component/1"}],
    }


def answer(
    scenario: str, path: str, *, honeypot_origin: str | None = None
) -> tuple[int, object]:
    if scenario == "server-error":
        return 500, {
            "message": SENTINEL,
            "token": JIRA_TOKEN,
            "path": path,
        }
    if scenario == "shape" and path == JIRA_PROJECT_PATH:
        return 200, []
    if scenario == "default-branch-204" and path == BITBUCKET_DEFAULT_BRANCH_PATH:
        return 204, None
    if scenario == "default-branch-json-null" and path == BITBUCKET_DEFAULT_BRANCH_PATH:
        return 200, None
    if scenario == "no-content-other" and path == JIRA_PROJECT_PATH:
        return 204, None
    if scenario == "attachment-minimal" and path == JIRA_ATTACHMENT_PATH:
        return 200, {"size": 1234}
    if scenario == "honeypot-links" and path == JIRA_PROJECT_PATH:
        assert honeypot_origin is not None
        return 200, honeypot_project_body(honeypot_origin)
    body = BODIES.get(path)
    if body is not None:
        return 200, body
    return 404, {"unexpected": SENTINEL, "path": path}


def redirect_location(
    scenario: str,
    path: str,
    *,
    primary_port: int,
    honeypot_origin: str | None,
) -> str | None:
    if path != JIRA_PROJECT_PATH:
        return None
    primary = f"http://127.0.0.1:{primary_port}"
    if scenario == "redirect-honeypot":
        assert honeypot_origin is not None
        return f"{honeypot_origin}{HONEYPOT_PATH}"
    if scenario == "redirect-other-product":
        return f"{primary}{BITBUCKET_CONTEXT}/rest/api/1.0/projects/PRJ"
    if scenario == "redirect-admin":
        return f"{primary}{ADMIN_PATH}"
    return None


def make_handler(
    scenario: str,
    seen: list[Request],
    *,
    honeypot_origin: str | None = None,
) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            pass

        def _serve(self) -> None:
            seen.append(request_record(self))
            path = urlsplit(self.path).path
            location = redirect_location(
                scenario,
                path,
                primary_port=self.server.server_port,
                honeypot_origin=honeypot_origin,
            )
            if location is not None:
                self.send_response(302)
                self.send_header("Location", location)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            status, body = answer(scenario, path, honeypot_origin=honeypot_origin)
            if status == 204:
                send_bytes(self, 204, b"", content_type=None)
            else:
                send_json(self, status, body)

        def do_GET(self) -> None:
            self._serve()

        def do_POST(self) -> None:
            self._serve()

        def do_PUT(self) -> None:
            self._serve()

        def do_PATCH(self) -> None:
            self._serve()

        def do_DELETE(self) -> None:
            self._serve()

    return Handler


def environment(origin: str) -> dict[str, str]:
    return {
        "ATLAWIRE_JIRA_URL": f"{origin}{JIRA_CONTEXT}",
        "ATLAWIRE_JIRA_TOKEN": JIRA_TOKEN,
        "ATLAWIRE_BITBUCKET_URL": f"{origin}{BITBUCKET_CONTEXT}",
        "ATLAWIRE_BITBUCKET_TOKEN": BITBUCKET_TOKEN,
        "ATLAWIRE_CONFLUENCE_URL": f"{origin}{CONFLUENCE_CONTEXT}",
        "ATLAWIRE_CONFLUENCE_TOKEN": CONFLUENCE_TOKEN,
        "BBK_CREDENTIALS": str(MISSING_CREDENTIALS),
    }


def read_via_cli(
    operation_id: str,
    params: object,
    *,
    context: str,
    scenario: str = "happy",
    raw_params: str | None = None,
    query: object | None = None,
    raw_query: str | None = None,
) -> tuple[subprocess.CompletedProcess[str], list[Request]]:
    seen: list[Request] = []
    with serving(make_handler(scenario, seen)) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        arguments = json.dumps(params) if raw_params is None else raw_params
        cli_arguments = [
            "read-operation",
            operation_id,
            "--params",
            arguments,
        ]
        if raw_query is not None:
            cli_arguments.extend(["--query", raw_query])
        elif query is not None:
            cli_arguments.extend(["--query", json.dumps(query)])
        cli_arguments.extend(
            [
                "--base-url",
                f"{origin}{context}",
                "--token-from-env",
                "--allow-http-loopback",
            ]
        )
        result = run_installed(cli_arguments, environment(origin))
    return result, seen


def read_via_cli_with_honeypot(
    operation_id: str,
    params: object,
    *,
    context: str,
    scenario: str,
) -> tuple[subprocess.CompletedProcess[str], list[Request], list[Request], str]:
    """Run one read while a second loopback server records forbidden hits."""
    primary_seen: list[Request] = []
    honeypot_seen: list[Request] = []
    with serving(make_handler("honeypot", honeypot_seen)) as honeypot:
        honeypot_origin = f"http://127.0.0.1:{honeypot.server_port}"
        with serving(
            make_handler(
                scenario,
                primary_seen,
                honeypot_origin=honeypot_origin,
            )
        ) as server:
            origin = f"http://127.0.0.1:{server.server_port}"
            result = run_installed(
                [
                    "read-operation",
                    operation_id,
                    "--params",
                    json.dumps(params),
                    "--base-url",
                    f"{origin}{context}",
                    "--token-from-env",
                    "--allow-http-loopback",
                ],
                environment(origin),
            )
    return result, primary_seen, honeypot_seen, honeypot_origin


def assert_no_secret_details(text: str) -> None:
    for detail in (
        JIRA_TOKEN,
        BITBUCKET_TOKEN,
        CONFLUENCE_TOKEN,
        SENTINEL,
        PARAM_SECRET,
        "Traceback",
    ):
        assert detail not in text


def test_operations_prints_the_static_catalog_without_credentials() -> None:
    result = run_installed(
        ["operations"], {"BBK_CREDENTIALS": str(MISSING_CREDENTIALS)}
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    payload = json.loads(result.stdout)
    assert payload == list_operations()
    entries = cast(list[dict[str, object]], payload)
    by_id = {cast(str, entry["id"]): entry for entry in entries}
    by_route = {
        (entry["product"], entry["method"], entry["path"]): entry for entry in entries
    }
    manifest = json.loads(
        (Path(__file__).parents[1] / "src/atlawire/manifest.json").read_text(
            encoding="utf-8"
        )
    )
    for row in manifest["operations"]:
        entry = by_route[(row["product"], row["method"], row["path"])]
        assert entry["product"] == row["product"]
        assert entry["method"] == row["method"]
        assert entry["path"] == row["path"]
    for operation_id, (product, path) in EXPECTED_CATALOG.items():
        entry = by_id[operation_id]
        assert entry["product"] == product
        assert entry["method"] == "GET"
        assert entry["path"] == path
        assert entry["documented_version"]
        assert entry["description"]
        arguments = cast(list[dict[str, object]], entry["arguments"])
        assert all(argument["name"] for argument in arguments)
        response = cast(dict[str, object], entry["response"])
        assert response["null_on_204"] is (
            operation_id == "bitbucket.repository.default-branch"
        )
        query = cast(list[dict[str, object]], entry["query"])
        assert [field["name"] for field in query] == list(
            EXPECTED_QUERY_NAMES.get(operation_id, ())
        )
        assert all(type(field["required"]) is bool for field in query)
        required_names = tuple(
            cast(str, field["name"]) for field in query if field["required"] is True
        )
        assert required_names == EXPECTED_REQUIRED_QUERY_NAMES.get(operation_id, ())
    assert set(EXPECTED_REQUIRED_QUERY_NAMES) <= set(EXPECTED_CATALOG)
    assert not MISSING_CREDENTIALS.exists()


@pytest.mark.parametrize(
    ("operation_id", "params", "context", "path", "token", "body"),
    CASES,
)
def test_read_operation_sends_one_fixed_get_and_prints_raw_json(
    operation_id: str,
    params: Mapping[str, object],
    context: str,
    path: str,
    token: str,
    body: object,
) -> None:
    result, seen = read_via_cli(operation_id, params, context=context)

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == body
    assert seen == [("GET", path, {}, f"Bearer {token}")]


def test_compare_commits_forwards_query_and_returns_raw_page() -> None:
    query = {
        "from": "feature&next=1",
        "to": "ветка",
        "fromRepo": "PRJ/widgets",
        "start": 0,
        "limit": 25,
    }

    result, seen = read_via_cli(
        "bitbucket.repository.compare-commits",
        {"projectKey": "PRJ", "repositorySlug": "widgets"},
        context=BITBUCKET_CONTEXT,
        query=query,
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == BITBUCKET_COMPARE_COMMITS_BODY
    assert seen == [
        (
            "GET",
            BITBUCKET_COMPARE_COMMITS_PATH,
            {
                "from": ["feature&next=1"],
                "to": ["ветка"],
                "fromRepo": ["PRJ/widgets"],
                "start": ["0"],
                "limit": ["25"],
            },
            f"Bearer {BITBUCKET_TOKEN}",
        )
    ]
    assert {record[0] for record in seen} == {"GET"}


def test_compare_changes_accepts_reserved_unicode_paging_values() -> None:
    query = {
        "from": "ветка&x=1",
        "to": "main?x#y",
        "start": 25,
        "limit": 100,
    }

    result, seen = read_via_cli(
        "bitbucket.repository.compare-changes",
        {"projectKey": "PRJ", "repositorySlug": "widgets"},
        context=BITBUCKET_CONTEXT,
        query=query,
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == BITBUCKET_COMPARE_CHANGES_BODY
    assert seen == [
        (
            "GET",
            BITBUCKET_COMPARE_CHANGES_PATH,
            {
                "from": ["ветка&x=1"],
                "to": ["main?x#y"],
                "start": ["25"],
                "limit": ["100"],
            },
            f"Bearer {BITBUCKET_TOKEN}",
        )
    ]
    assert set(seen[0][2]) == {"from", "to", "start", "limit"}
    assert {record[0] for record in seen} == {"GET"}


def test_compare_rejects_unknown_query_without_request() -> None:
    result, seen = read_via_cli(
        "bitbucket.repository.compare-commits",
        {"projectKey": "PRJ", "repositorySlug": "widgets"},
        context=BITBUCKET_CONTEXT,
        query={"from": "a", "extra": PARAM_SECRET},
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert seen == []
    assert "The query parameters are invalid." in result.stderr
    assert_no_secret_details(result.stderr)


@pytest.mark.parametrize(
    "query",
    [
        {"from": 1},
        {"start": "0"},
        {"limit": 0},
        {"fromRepo": "PRJ/.."},
    ],
)
def test_compare_rejects_wrong_query_types_without_request(
    query: Mapping[str, object],
) -> None:
    result, seen = read_via_cli(
        "bitbucket.repository.compare-commits",
        {"projectKey": "PRJ", "repositorySlug": "widgets"},
        context=BITBUCKET_CONTEXT,
        query=query,
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert seen == []
    assert "The query parameters are invalid." in result.stderr
    assert_no_secret_details(result.stderr)


def test_compare_rejects_duplicate_raw_query_keys_without_request() -> None:
    raw_query = '{"from":"first","from":"' + PARAM_SECRET + '"}'

    result, seen = read_via_cli(
        "bitbucket.repository.compare-commits",
        {"projectKey": "PRJ", "repositorySlug": "widgets"},
        context=BITBUCKET_CONTEXT,
        raw_query=raw_query,
    )

    assert result.returncode in {1, 2}
    assert result.stdout == ""
    assert seen == []
    assert PARAM_SECRET not in result.stdout
    assert PARAM_SECRET not in result.stderr
    assert_no_secret_details(result.stderr)


def test_compare_server_error_does_not_echo_query_token_or_target() -> None:
    query = {"from": PARAM_SECRET, "to": "main", "start": 0, "limit": 25}

    result, seen = read_via_cli(
        "bitbucket.repository.compare-commits",
        {"projectKey": "PRJ", "repositorySlug": "widgets"},
        context=BITBUCKET_CONTEXT,
        scenario="server-error",
        query=query,
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert len(seen) == 1
    assert seen[0][0] == "GET"
    assert seen[0][1] == BITBUCKET_COMPARE_COMMITS_PATH
    assert "HTTP 500" in result.stderr
    assert BITBUCKET_COMPARE_COMMITS_PATH not in result.stderr
    assert_no_secret_details(result.stderr)


def query_record(query: Mapping[str, object]) -> dict[str, list[str]]:
    return {name: [str(value)] for name, value in query.items()}


@pytest.mark.parametrize(
    ("operation_id", "params", "query", "context", "path", "token", "body"),
    QUERY_CASES,
)
def test_required_query_operations_send_one_get(
    operation_id: str,
    params: Mapping[str, object],
    query: Mapping[str, object],
    context: str,
    path: str,
    token: str,
    body: object,
) -> None:
    result, seen = read_via_cli(
        operation_id,
        params,
        context=context,
        query=query,
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == body
    assert seen == [("GET", path, query_record(query), f"Bearer {token}")]
    assert {record[0] for record in seen} == {"GET"}


def test_long_cql_is_sent_as_one_encoded_query_value() -> None:
    cql = 'space = TST AND text ~ "' + "x" * 300 + '"'

    result, seen = read_via_cli(
        "confluence.content.search",
        {},
        context=CONFLUENCE_CONTEXT,
        query={"cql": cql},
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == CONFLUENCE_CONTENT_SEARCH_BODY
    assert seen == [
        (
            "GET",
            CONFLUENCE_CONTENT_SEARCH_PATH,
            {"cql": [cql]},
            f"Bearer {CONFLUENCE_TOKEN}",
        )
    ]
    assert set(seen[0][2]) == {"cql"}


def test_jira_user_queries_accept_both_documented_identifiers() -> None:
    user_result, user_seen = read_via_cli(
        "jira.user.get",
        {},
        context=JIRA_CONTEXT,
        query={"username": "fred", "key": "JIRAUSER1"},
    )
    assignable_result, assignable_seen = read_via_cli(
        "jira.user.assignable-search",
        {},
        context=JIRA_CONTEXT,
        query={
            "project": "EX",
            "issueKey": "EX-1",
            "actionDescriptorId": 7,
        },
    )

    assert user_result.returncode == 0, user_result.stderr
    assert json.loads(user_result.stdout) == JIRA_USER_GET_BODY
    assert user_seen == [
        (
            "GET",
            JIRA_USER_GET_PATH,
            {"username": ["fred"], "key": ["JIRAUSER1"]},
            f"Bearer {JIRA_TOKEN}",
        )
    ]
    assert assignable_result.returncode == 0, assignable_result.stderr
    assert json.loads(assignable_result.stdout) == JIRA_USER_ASSIGNABLE_SEARCH_BODY
    assert assignable_seen == [
        (
            "GET",
            JIRA_USER_ASSIGNABLE_SEARCH_PATH,
            {
                "project": ["EX"],
                "issueKey": ["EX-1"],
                "actionDescriptorId": ["7"],
            },
            f"Bearer {JIRA_TOKEN}",
        )
    ]


@pytest.mark.parametrize(
    ("operation_id", "params", "query", "context"),
    [
        (
            "jira.mypermissions.get",
            {},
            {"projectKey": "EX", "issueKey": "EX-1"},
            JIRA_CONTEXT,
        ),
        (
            "jira.user.get",
            {},
            {},
            JIRA_CONTEXT,
        ),
        (
            "jira.user.assignable-search",
            {},
            {},
            JIRA_CONTEXT,
        ),
        (
            "jira.dashboard.list",
            {},
            {"startAt": -1},
            JIRA_CONTEXT,
        ),
        (
            "confluence.content.by-title",
            {},
            {},
            CONFLUENCE_CONTEXT,
        ),
        (
            "confluence.content.search",
            {},
            {},
            CONFLUENCE_CONTEXT,
        ),
        (
            "confluence.space.content",
            {"spaceKey": "TST"},
            {"depth": "other"},
            CONFLUENCE_CONTEXT,
        ),
        (
            "confluence.content.by-title",
            {},
            {"title": "Example", "type": "page"},
            CONFLUENCE_CONTEXT,
        ),
    ],
)
def test_new_query_rules_and_required_values_fail_without_request(
    operation_id: str,
    params: Mapping[str, object],
    query: Mapping[str, object],
    context: str,
) -> None:
    result, seen = read_via_cli(
        operation_id,
        params,
        context=context,
        query=query,
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert seen == []
    assert "The query parameters are invalid." in result.stderr
    assert_no_secret_details(result.stderr)


@pytest.mark.parametrize(
    ("operation_id", "params", "context"),
    [
        (
            "jira.project.statuses",
            {"projectIdOrKey": "../EX"},
            JIRA_CONTEXT,
        ),
        (
            "jira.issue.comment.get",
            {"issueIdOrKey": "EX-1", "id": "0"},
            JIRA_CONTEXT,
        ),
        (
            "jira.issue.worklog.get",
            {"issueIdOrKey": "EX-1", "id": "0"},
            JIRA_CONTEXT,
        ),
        ("jira.issue-link.get", {"linkId": "0"}, JIRA_CONTEXT),
        (
            "confluence.content.properties",
            {"id": "0"},
            CONFLUENCE_CONTEXT,
        ),
        (
            "confluence.content.attachments",
            {"id": "0"},
            CONFLUENCE_CONTEXT,
        ),
        (
            "confluence.content.children",
            {"id": "0"},
            CONFLUENCE_CONTEXT,
        ),
        (
            "confluence.space.content",
            {"spaceKey": "../TST"},
            CONFLUENCE_CONTEXT,
        ),
    ],
)
def test_new_route_values_fail_without_request(
    operation_id: str,
    params: Mapping[str, object],
    context: str,
) -> None:
    result, seen = read_via_cli(operation_id, params, context=context)

    assert result.returncode == 1
    assert result.stdout == ""
    assert seen == []
    assert "path argument" in result.stderr
    assert_no_secret_details(result.stderr)


def test_participants_forwards_filters_and_paging() -> None:
    query = {
        "direction": "INCOMING",
        "filter": "Jane Doe",
        "role": "REVIEWER",
        "start": 0,
        "limit": 25,
    }

    result, seen = read_via_cli(
        "bitbucket.repository.participants",
        {"projectKey": "PRJ", "repositorySlug": "widgets"},
        context=BITBUCKET_CONTEXT,
        query=query,
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == BITBUCKET_PARTICIPANTS_BODY
    assert seen == [
        (
            "GET",
            BITBUCKET_PARTICIPANTS_PATH,
            {
                "direction": ["INCOMING"],
                "filter": ["Jane Doe"],
                "role": ["REVIEWER"],
                "start": ["0"],
                "limit": ["25"],
            },
            f"Bearer {BITBUCKET_TOKEN}",
        )
    ]
    assert {record[0] for record in seen} == {"GET"}


def test_commit_comments_forwards_path_and_since() -> None:
    query = {
        "path": "src/a file.py",
        "since": BITBUCKET_COMMIT_ID,
        "start": 0,
        "limit": 25,
    }

    result, seen = read_via_cli(
        "bitbucket.repository.commit-comments",
        {
            "projectKey": "PRJ",
            "repositorySlug": "widgets",
            "commitId": BITBUCKET_COMMIT_ID,
        },
        context=BITBUCKET_CONTEXT,
        query=query,
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == BITBUCKET_COMMIT_COMMENTS_BODY
    assert seen == [
        (
            "GET",
            BITBUCKET_COMMIT_COMMENTS_PATH,
            {
                "path": ["src/a file.py"],
                "since": [BITBUCKET_COMMIT_ID],
                "start": ["0"],
                "limit": ["25"],
            },
            f"Bearer {BITBUCKET_TOKEN}",
        )
    ]
    assert {record[0] for record in seen} == {"GET"}


def test_forks_forwards_start_and_limit() -> None:
    result, seen = read_via_cli(
        "bitbucket.repository.forks",
        {"projectKey": "PRJ", "repositorySlug": "widgets"},
        context=BITBUCKET_CONTEXT,
        query={"start": 25, "limit": 100},
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == BITBUCKET_FORKS_BODY
    assert seen == [
        (
            "GET",
            BITBUCKET_FORKS_PATH,
            {"start": ["25"], "limit": ["100"]},
            f"Bearer {BITBUCKET_TOKEN}",
        )
    ]
    assert {record[0] for record in seen} == {"GET"}


@pytest.mark.parametrize(
    ("operation_id", "params", "query"),
    [
        (
            "bitbucket.repository.participants",
            {"projectKey": "PRJ", "repositorySlug": "widgets"},
            {"direction": "SIDEWAYS"},
        ),
        (
            "bitbucket.repository.participants",
            {"projectKey": "PRJ", "repositorySlug": "widgets"},
            {"role": "OWNER"},
        ),
        (
            "bitbucket.repository.pull-request-activity",
            {
                "projectKey": "PRJ",
                "repositorySlug": "widgets",
                "pullRequestId": "7",
            },
            {"fromId": 1},
        ),
        (
            "bitbucket.profile.recent-repositories",
            {},
            {"permission": "REPO_READ"},
        ),
        ("bitbucket.users.list", {}, {"filter": "jdoe"}),
        ("bitbucket.task.get", {"taskId": "99"}, {"start": 0}),
    ],
)
def test_new_operations_reject_undeclared_or_enum_query_without_request(
    operation_id: str,
    params: Mapping[str, object],
    query: Mapping[str, object],
) -> None:
    result, seen = read_via_cli(
        operation_id,
        params,
        context=BITBUCKET_CONTEXT,
        query=query,
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert seen == []
    assert "The query parameters are invalid." in result.stderr
    assert_no_secret_details(result.stderr)


@pytest.mark.parametrize(
    ("operation_id", "params"),
    [
        (
            "bitbucket.repository.commit-comments",
            {
                "projectKey": "PRJ",
                "repositorySlug": "widgets",
                "commitId": "abc",
            },
        ),
        (
            "bitbucket.repository.pull-request-activity",
            {
                "projectKey": "PRJ",
                "repositorySlug": "widgets",
                "pullRequestId": "0",
            },
        ),
        ("bitbucket.task.get", {"taskId": "0"}),
        ("bitbucket.user.get", {"userSlug": "../jdoe"}),
    ],
)
def test_new_operations_reject_invalid_route_values_without_request(
    operation_id: str,
    params: Mapping[str, object],
) -> None:
    result, seen = read_via_cli(
        operation_id,
        params,
        context=BITBUCKET_CONTEXT,
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert seen == []
    assert "path argument" in result.stderr
    assert_no_secret_details(result.stderr)


def test_attachment_read_never_requests_the_content_url() -> None:
    result, seen = read_via_cli(
        "jira.attachment.get",
        {"id": "10001"},
        context=JIRA_CONTEXT,
    )

    assert result.returncode == 0, result.stderr
    assert seen == [("GET", JIRA_ATTACHMENT_PATH, {}, f"Bearer {JIRA_TOKEN}")]
    assert JIRA_ATTACHMENT_CONTENT_PATH not in {record[1] for record in seen}
    assert JIRA_ATTACHMENT_CONTENT_PATH in result.stdout
    assert SENTINEL not in result.stdout


def test_default_branch_204_prints_json_null() -> None:
    result, seen = read_via_cli(
        "bitbucket.repository.default-branch",
        {"projectKey": "PRJ", "repositorySlug": "widgets"},
        context=BITBUCKET_CONTEXT,
        scenario="default-branch-204",
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert result.stdout.strip() == "null"
    assert json.loads(result.stdout) is None
    assert seen == [
        (
            "GET",
            BITBUCKET_DEFAULT_BRANCH_PATH,
            {},
            f"Bearer {BITBUCKET_TOKEN}",
        )
    ]


def test_default_branch_200_json_null_is_an_error() -> None:
    result, seen = read_via_cli(
        "bitbucket.repository.default-branch",
        {"projectKey": "PRJ", "repositorySlug": "widgets"},
        context=BITBUCKET_CONTEXT,
        scenario="default-branch-json-null",
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert seen == [
        (
            "GET",
            BITBUCKET_DEFAULT_BRANCH_PATH,
            {},
            f"Bearer {BITBUCKET_TOKEN}",
        )
    ]
    assert "Expected a JSON object." in result.stderr
    assert_no_secret_details(result.stderr)


def test_204_is_an_error_for_operations_that_do_not_document_it() -> None:
    result, seen = read_via_cli(
        "jira.project.get",
        {"projectIdOrKey": "EX"},
        context=JIRA_CONTEXT,
        scenario="no-content-other",
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert seen == [("GET", JIRA_PROJECT_PATH, {}, f"Bearer {JIRA_TOKEN}")]
    assert "Expected a valid JSON response." in result.stderr
    assert_no_secret_details(result.stderr)


def test_attachment_metadata_without_filename_is_returned_raw() -> None:
    result, seen = read_via_cli(
        "jira.attachment.get",
        {"id": "10001"},
        context=JIRA_CONTEXT,
        scenario="attachment-minimal",
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == {"size": 1234}
    assert "filename" not in json.loads(result.stdout)
    assert seen == [("GET", JIRA_ATTACHMENT_PATH, {}, f"Bearer {JIRA_TOKEN}")]


def test_successful_object_urls_never_reach_the_honeypot() -> None:
    result, primary_seen, honeypot_seen, honeypot_origin = read_via_cli_with_honeypot(
        "jira.project.get",
        {"projectIdOrKey": "EX"},
        context=JIRA_CONTEXT,
        scenario="honeypot-links",
    )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == honeypot_project_body(honeypot_origin)
    assert primary_seen == [("GET", JIRA_PROJECT_PATH, {}, f"Bearer {JIRA_TOKEN}")]
    assert honeypot_seen == []
    assert honeypot_origin in result.stdout


@pytest.mark.parametrize(
    ("scenario", "forbidden_path"),
    [
        ("redirect-honeypot", None),
        (
            "redirect-other-product",
            f"{BITBUCKET_CONTEXT}/rest/api/1.0/projects/PRJ",
        ),
        ("redirect-admin", ADMIN_PATH),
    ],
)
def test_redirects_are_refused_without_touching_forbidden_destinations(
    scenario: str, forbidden_path: str | None
) -> None:
    result, primary_seen, honeypot_seen, honeypot_origin = read_via_cli_with_honeypot(
        "jira.project.get",
        {"projectIdOrKey": "EX"},
        context=JIRA_CONTEXT,
        scenario=scenario,
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert "redirect refused" in result.stderr
    assert primary_seen == [("GET", JIRA_PROJECT_PATH, {}, f"Bearer {JIRA_TOKEN}")]
    assert honeypot_seen == []
    assert honeypot_origin not in result.stderr
    if forbidden_path is not None:
        assert not any(record[1].startswith(forbidden_path) for record in primary_seen)


def test_read_operation_uses_the_saved_product_credential_pair(
    tmp_path: Path,
) -> None:
    seen: list[Request] = []
    with serving(make_handler("happy", seen)) as server:
        origin = f"http://127.0.0.1:{server.server_port}"
        credentials = tmp_path / "fixture-bbk-credentials.json"
        credentials.write_text(
            json.dumps(
                {
                    "jira_url": f"{origin}{JIRA_CONTEXT}",
                    "jira_token": JIRA_TOKEN,
                    "bitbucket_url": f"{origin}{BITBUCKET_CONTEXT}",
                    "bitbucket_token": BITBUCKET_TOKEN,
                    "confluence_url": f"{origin}{CONFLUENCE_CONTEXT}",
                    "confluence_token": CONFLUENCE_TOKEN,
                }
            ),
            encoding="utf-8",
        )
        result = run_installed(
            [
                "read-operation",
                "jira.project.get",
                "--params",
                json.dumps({"projectIdOrKey": "EX"}),
                "--base-url",
                f"{origin}{JIRA_CONTEXT}",
                "--allow-http-loopback",
            ],
            {"BBK_CREDENTIALS": str(credentials)},
        )

    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    assert json.loads(result.stdout) == JIRA_PROJECT_BODY
    assert seen == [("GET", JIRA_PROJECT_PATH, {}, f"Bearer {JIRA_TOKEN}")]


@pytest.mark.parametrize(
    "operation_id",
    [
        "jira.issue.delete",
        "jira.issue.create",
        "bitbucket.project.create",
        "bitbucket.repository.delete",
        "confluence.space.delete",
        "admin.user.get",
        "/rest/api/2/project/EX",
    ],
)
def test_unknown_mutating_and_administrative_ids_fail_without_a_request(
    operation_id: str,
) -> None:
    result, seen = read_via_cli(
        operation_id,
        {"projectIdOrKey": PARAM_SECRET},
        context=JIRA_CONTEXT,
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert seen == []
    assert "Unknown operation ID." in result.stderr
    assert operation_id not in result.stderr
    assert_no_secret_details(result.stderr)


@pytest.mark.parametrize(
    ("operation_id", "params", "context"),
    [
        ("jira.project.get", {}, JIRA_CONTEXT),
        ("jira.project.get", {"projectIdOrKey": "EX", "extra": "x"}, JIRA_CONTEXT),
        ("jira.project.get", {"projectIdOrKey": 10000}, JIRA_CONTEXT),
        ("jira.project.get", {"projectIdOrKey": True}, JIRA_CONTEXT),
        ("jira.project.get", {"projectIdOrKey": "../EX"}, JIRA_CONTEXT),
        ("jira.project.get", {"projectIdOrKey": "EX/OTHER"}, JIRA_CONTEXT),
        ("jira.project.get", {"projectIdOrKey": "EX%2FOTHER"}, JIRA_CONTEXT),
        ("jira.attachment.get", {"id": "0"}, JIRA_CONTEXT),
        ("jira.attachment.get", {"id": "1/2"}, JIRA_CONTEXT),
        (
            "bitbucket.repository.get",
            {"projectKey": "PRJ", "repositorySlug": ".."},
            BITBUCKET_CONTEXT,
        ),
        (
            "bitbucket.repository.get",
            {"projectKey": "PRJ", "repositorySlug": "widgets/other"},
            BITBUCKET_CONTEXT,
        ),
        ("confluence.space.get", {"spaceKey": ".."}, CONFLUENCE_CONTEXT),
    ],
)
def test_invalid_path_parameters_fail_without_a_request(
    operation_id: str,
    params: Mapping[str, object],
    context: str,
) -> None:
    result, seen = read_via_cli(operation_id, params, context=context)

    assert result.returncode == 1
    assert result.stdout == ""
    assert seen == []
    assert "path argument" in result.stderr
    assert "../EX" not in result.stderr
    assert "EX/OTHER" not in result.stderr
    assert "EX%2FOTHER" not in result.stderr
    assert "widgets/other" not in result.stderr
    assert_no_secret_details(result.stderr)


def test_missing_params_option_is_a_usage_error() -> None:
    result = run_installed(
        ["read-operation", "jira.project.get"],
        {"BBK_CREDENTIALS": str(MISSING_CREDENTIALS)},
    )

    assert result.returncode == 2
    assert result.stdout == ""
    assert "Missing option" in result.stderr
    assert "--params" in result.stderr
    assert_no_secret_details(result.stderr)


def test_malformed_params_json_fails_without_a_request() -> None:
    raw_params = '{"projectIdOrKey":"' + PARAM_SECRET + '",'

    result, seen = read_via_cli(
        "jira.project.get",
        {},
        context=JIRA_CONTEXT,
        raw_params=raw_params,
    )

    assert result.returncode in {1, 2}
    assert result.stdout == ""
    assert seen == []
    assert PARAM_SECRET not in result.stdout
    assert PARAM_SECRET not in result.stderr
    assert_no_secret_details(result.stderr)


def test_invalid_path_value_with_secret_is_not_echoed() -> None:
    result, seen = read_via_cli(
        "jira.project.get",
        {"projectIdOrKey": PARAM_SECRET},
        context=JIRA_CONTEXT,
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert seen == []
    assert "path argument" in result.stderr
    assert PARAM_SECRET not in result.stdout
    assert PARAM_SECRET not in result.stderr
    assert_no_secret_details(result.stderr)


def test_wrong_response_shape_prints_no_partial_result() -> None:
    result, seen = read_via_cli(
        "jira.project.get",
        {"projectIdOrKey": "EX"},
        context=JIRA_CONTEXT,
        scenario="shape",
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert seen == [("GET", JIRA_PROJECT_PATH, {}, f"Bearer {JIRA_TOKEN}")]
    assert "Expected a JSON object." in result.stderr
    assert_no_secret_details(result.stderr)


def test_transport_failure_does_not_echo_request_details() -> None:
    result, seen = read_via_cli(
        "jira.project.get",
        {"projectIdOrKey": "EX"},
        context=JIRA_CONTEXT,
        scenario="server-error",
    )

    assert result.returncode == 1
    assert result.stdout == ""
    assert seen == [("GET", JIRA_PROJECT_PATH, {}, f"Bearer {JIRA_TOKEN}")]
    assert "HTTP 500" in result.stderr
    for detail in (
        JIRA_TOKEN,
        BITBUCKET_TOKEN,
        CONFLUENCE_TOKEN,
        SENTINEL,
        JIRA_PROJECT_PATH,
        "Traceback",
    ):
        assert detail not in result.stderr
