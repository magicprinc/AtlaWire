"""Unit contracts for the static audited read-only operation registry.

The expected routes, versions, response shapes, and argument names below are
enumerated independently from the registry so a wrong path or a silently
widened shape cannot pass by agreeing with itself.
"""

import json
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import cast

import pytest
import requests

import atlawire.operations as operations
from atlawire.http import AtlaWireError
from atlawire.http import bearer_session as real_bearer_session
from atlawire.operations import list_operations, read_operation

TOKEN = "synthetic-operations-token-7c1"
COMMIT_ID = "abcdef0123abcdef4567abcdef8987abcdef6543"
SENTINEL = "OPERATIONS-UNIT-SENTINEL"
BASE = "https://atlassian.example"

EXPECTED: dict[str, dict[str, object]] = {
    "bitbucket.project.get": {
        "product": "bitbucket",
        "path": "/rest/api/1.0/projects/{projectKey}",
        "version": "Bitbucket Server 5.10.0 REST API 1.0",
        "kind": "object",
        "required": (),
        "items_required": (),
        "object_arrays": (),
        "arguments": ("projectKey",),
    },
    "bitbucket.repository.compare-changes": {
        "product": "bitbucket",
        "path": (
            "/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/compare/changes"
        ),
        "version": "Bitbucket Server 5.10.0 REST API 1.0",
        "kind": "object",
        "required": (),
        "items_required": (),
        "object_arrays": (),
        "arguments": ("projectKey", "repositorySlug"),
    },
    "bitbucket.repository.compare-commits": {
        "product": "bitbucket",
        "path": (
            "/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/compare/commits"
        ),
        "version": "Bitbucket Server 5.10.0 REST API 1.0",
        "kind": "object",
        "required": (),
        "items_required": (),
        "object_arrays": (),
        "arguments": ("projectKey", "repositorySlug"),
    },
    "bitbucket.repository.default-branch": {
        "product": "bitbucket",
        "path": (
            "/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}"
            "/branches/default"
        ),
        "version": "Bitbucket Server 5.10.0 REST API 1.0",
        "kind": "object",
        "required": (),
        "items_required": (),
        "object_arrays": (),
        "arguments": ("projectKey", "repositorySlug"),
    },
    "bitbucket.repository.get": {
        "product": "bitbucket",
        "path": "/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}",
        "version": "Bitbucket Server 5.10.0 REST API 1.0",
        "kind": "object",
        "required": (),
        "items_required": (),
        "object_arrays": (),
        "arguments": ("projectKey", "repositorySlug"),
    },
    "confluence.space.get": {
        "product": "confluence",
        "path": "/rest/api/space/{spaceKey}",
        "version": "Confluence Server 6.6.0 REST API",
        "kind": "object",
        "required": (),
        "items_required": (),
        "object_arrays": (),
        "arguments": ("spaceKey",),
    },
    "jira.attachment.get": {
        "product": "jira",
        "path": "/rest/api/2/attachment/{id}",
        "version": "Jira Server 8.22.0 REST API 2",
        "kind": "object",
        "required": (("size", "integer"),),
        "items_required": (),
        "object_arrays": (),
        "arguments": ("id",),
    },
    "jira.issue.votes": {
        "product": "jira",
        "path": "/rest/api/2/issue/{issueIdOrKey}/votes",
        "version": "Jira Server 8.22.0 REST API 2",
        "kind": "object",
        "required": (("votes", "integer"), ("hasVoted", "boolean")),
        "items_required": (),
        "object_arrays": ("voters",),
        "arguments": ("issueIdOrKey",),
    },
    "jira.issue.watchers": {
        "product": "jira",
        "path": "/rest/api/2/issue/{issueIdOrKey}/watchers",
        "version": "Jira Server 8.22.0 REST API 2",
        "kind": "object",
        "required": (("watchCount", "integer"),),
        "items_required": (),
        "object_arrays": ("watchers",),
        "arguments": ("issueIdOrKey",),
    },
    "jira.project.components": {
        "product": "jira",
        "path": "/rest/api/2/project/{projectIdOrKey}/components",
        "version": "Jira Server 8.22.0 REST API 2",
        "kind": "array",
        "required": (),
        "items_required": (("isAssigneeTypeValid", "boolean"),),
        "object_arrays": (),
        "arguments": ("projectIdOrKey",),
    },
    "jira.project.get": {
        "product": "jira",
        "path": "/rest/api/2/project/{projectIdOrKey}",
        "version": "Jira Server 8.22.0 REST API 2",
        "kind": "object",
        "required": (),
        "items_required": (),
        "object_arrays": (),
        "arguments": ("projectIdOrKey",),
    },
    "jira.project.versions": {
        "product": "jira",
        "path": "/rest/api/2/project/{projectIdOrKey}/versions",
        "version": "Jira Server 8.22.0 REST API 2",
        "kind": "array",
        "required": (),
        "items_required": (),
        "object_arrays": (),
        "arguments": ("projectIdOrKey",),
    },
    "bitbucket.repository.commit-comments": {
        "product": "bitbucket",
        "path": (
            "/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}"
            "/commits/{commitId}/comments"
        ),
        "version": "Bitbucket Server 5.10.0 REST API 1.0",
        "kind": "object",
        "required": (),
        "items_required": (),
        "object_arrays": (),
        "arguments": ("projectKey", "repositorySlug", "commitId"),
    },
    "bitbucket.repository.forks": {
        "product": "bitbucket",
        "path": ("/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/forks"),
        "version": "Bitbucket Server 5.10.0 REST API 1.0",
        "kind": "object",
        "required": (),
        "items_required": (),
        "object_arrays": (),
        "arguments": ("projectKey", "repositorySlug"),
    },
    "bitbucket.repository.participants": {
        "product": "bitbucket",
        "path": (
            "/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/participants"
        ),
        "version": "Bitbucket Server 5.10.0 REST API 1.0",
        "kind": "object",
        "required": (),
        "items_required": (),
        "object_arrays": (),
        "arguments": ("projectKey", "repositorySlug"),
    },
    "bitbucket.repository.pull-request-activity": {
        "product": "bitbucket",
        "path": (
            "/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}"
            "/pull-requests/{pullRequestId}/activities"
        ),
        "version": "Bitbucket Server 5.10.0 REST API 1.0",
        "kind": "object",
        "required": (),
        "items_required": (),
        "object_arrays": (),
        "arguments": ("projectKey", "repositorySlug", "pullRequestId"),
    },
    "bitbucket.repository.related": {
        "product": "bitbucket",
        "path": ("/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/related"),
        "version": "Bitbucket Server 5.10.0 REST API 1.0",
        "kind": "object",
        "required": (),
        "items_required": (),
        "object_arrays": (),
        "arguments": ("projectKey", "repositorySlug"),
    },
    "bitbucket.profile.recent-repositories": {
        "product": "bitbucket",
        "path": "/rest/api/1.0/profile/recent/repos",
        "version": "Bitbucket Server 5.10.0 REST API 1.0",
        "kind": "object",
        "required": (),
        "items_required": (),
        "object_arrays": (),
        "arguments": (),
    },
    "bitbucket.task.get": {
        "product": "bitbucket",
        "path": "/rest/api/1.0/tasks/{taskId}",
        "version": "Bitbucket Server 5.10.0 REST API 1.0",
        "kind": "object",
        "required": (),
        "items_required": (),
        "object_arrays": (),
        "arguments": ("taskId",),
    },
    "bitbucket.user.get": {
        "product": "bitbucket",
        "path": "/rest/api/1.0/users/{userSlug}",
        "version": "Bitbucket Server 5.10.0 REST API 1.0",
        "kind": "object",
        "required": (),
        "items_required": (),
        "object_arrays": (),
        "arguments": ("userSlug",),
    },
    "bitbucket.users.list": {
        "product": "bitbucket",
        "path": "/rest/api/1.0/users",
        "version": "Bitbucket Server 5.10.0 REST API 1.0",
        "kind": "object",
        "required": (),
        "items_required": (),
        "object_arrays": (),
        "arguments": (),
    },
}

_QUERY_INT_MAX = 2**31 - 1
_PAGING_QUERY = (
    ("start", "integer", False, None, 0, _QUERY_INT_MAX, None, ()),
    ("limit", "integer", False, None, 1, _QUERY_INT_MAX, None, ()),
)
_COMPARE_QUERY = (
    ("from", "string", False, 255, None, None, None, ()),
    ("to", "string", False, 255, None, None, None, ()),
    (
        "fromRepo",
        "string",
        False,
        None,
        None,
        None,
        "repository-id-or-project-key/repository-slug",
        (),
    ),
    *_PAGING_QUERY,
)
_PARTICIPANTS_QUERY = (
    (
        "direction",
        "string",
        False,
        None,
        None,
        None,
        None,
        ("INCOMING", "OUTGOING"),
    ),
    ("filter", "string", False, None, None, None, None, ()),
    (
        "role",
        "string",
        False,
        None,
        None,
        None,
        None,
        ("AUTHOR", "REVIEWER", "PARTICIPANT"),
    ),
    *_PAGING_QUERY,
)
_COMMIT_COMMENTS_QUERY = (
    ("path", "string", False, None, None, None, None, ()),
    ("since", "string", False, None, None, None, None, ()),
    *_PAGING_QUERY,
)
EXPECTED_QUERY: dict[str, tuple[tuple[object, ...], ...]] = {
    "bitbucket.repository.commit-comments": _COMMIT_COMMENTS_QUERY,
    "bitbucket.repository.compare-changes": _COMPARE_QUERY,
    "bitbucket.repository.compare-commits": _COMPARE_QUERY,
    "bitbucket.repository.forks": _PAGING_QUERY,
    "bitbucket.repository.participants": _PARTICIPANTS_QUERY,
    "bitbucket.repository.pull-request-activity": _PAGING_QUERY,
    "bitbucket.repository.related": _PAGING_QUERY,
    "bitbucket.profile.recent-repositories": _PAGING_QUERY,
    "bitbucket.users.list": _PAGING_QUERY,
}

SAMPLES: dict[str, dict[str, object]] = {
    "bitbucket.project.get": {"projectKey": "PRJ"},
    "bitbucket.repository.compare-changes": {
        "projectKey": "PRJ",
        "repositorySlug": "widgets",
    },
    "bitbucket.repository.compare-commits": {
        "projectKey": "PRJ",
        "repositorySlug": "widgets",
    },
    "bitbucket.repository.commit-comments": {
        "projectKey": "PRJ",
        "repositorySlug": "widgets",
        "commitId": COMMIT_ID,
    },
    "bitbucket.repository.forks": {
        "projectKey": "PRJ",
        "repositorySlug": "widgets",
    },
    "bitbucket.repository.participants": {
        "projectKey": "PRJ",
        "repositorySlug": "widgets",
    },
    "bitbucket.repository.pull-request-activity": {
        "projectKey": "PRJ",
        "repositorySlug": "widgets",
        "pullRequestId": "7",
    },
    "bitbucket.repository.related": {
        "projectKey": "PRJ",
        "repositorySlug": "widgets",
    },
    "bitbucket.profile.recent-repositories": {},
    "bitbucket.task.get": {"taskId": "99"},
    "bitbucket.user.get": {"userSlug": "jcitizen"},
    "bitbucket.users.list": {},
    "bitbucket.repository.default-branch": {
        "projectKey": "PRJ",
        "repositorySlug": "widgets",
    },
    "bitbucket.repository.get": {
        "projectKey": "PRJ",
        "repositorySlug": "widgets",
    },
    "confluence.space.get": {"spaceKey": "TST"},
    "jira.attachment.get": {"id": "10001"},
    "jira.issue.votes": {"issueIdOrKey": "EX-1"},
    "jira.issue.watchers": {"issueIdOrKey": "EX-1"},
    "jira.project.components": {"projectIdOrKey": "EX"},
    "jira.project.get": {"projectIdOrKey": "EX"},
    "jira.project.versions": {"projectIdOrKey": "EX"},
}

BODIES: dict[str, object] = {
    "bitbucket.project.get": {
        "key": "PRJ",
        "id": 1,
        "name": "My Cool Project",
        "public": False,
        "unknownField": {"kept": True},
        "_links": {
            "self": [{"href": "https://other.example/rest/api/1.0/projects/PRJ"}]
        },
    },
    "bitbucket.repository.compare-changes": {
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
    },
    "bitbucket.repository.compare-commits": {
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
    },
    "bitbucket.repository.commit-comments": {
        "size": 1,
        "limit": 25,
        "isLastPage": True,
        "values": [{"id": 101, "text": "A comment", "state": "OPEN"}],
        "start": 0,
    },
    "bitbucket.repository.forks": {
        "size": 1,
        "limit": 25,
        "isLastPage": True,
        "values": [{"slug": "widgets-fork"}],
        "start": 0,
    },
    "bitbucket.repository.participants": {
        "size": 1,
        "limit": 25,
        "isLastPage": True,
        "values": [{"name": "charlie", "role": "REVIEWER"}],
        "start": 0,
    },
    "bitbucket.repository.pull-request-activity": {
        "size": 1,
        "limit": 25,
        "isLastPage": True,
        "values": [{"id": 101, "action": "COMMENTED"}],
        "start": 0,
    },
    "bitbucket.repository.related": {
        "size": 1,
        "limit": 25,
        "isLastPage": True,
        "values": [{"slug": "widgets-related"}],
        "start": 0,
    },
    "bitbucket.profile.recent-repositories": {
        "size": 1,
        "limit": 25,
        "isLastPage": True,
        "values": [{"slug": "recent"}],
        "start": 0,
    },
    "bitbucket.task.get": {
        "id": 99,
        "text": "Resolve the merge conflicts",
        "state": "OPEN",
    },
    "bitbucket.user.get": {
        "slug": "jcitizen",
        "name": "jcitizen",
        "displayName": "Jane Citizen",
    },
    "bitbucket.users.list": {
        "size": 1,
        "limit": 25,
        "isLastPage": True,
        "values": [{"slug": "jcitizen", "name": "jcitizen"}],
        "start": 0,
    },
    "bitbucket.repository.default-branch": {
        "id": "refs/heads/master",
        "displayId": "master",
        "type": "BRANCH",
        "latestCommit": "8d51122def5632836d1cb1026e879069e10a1e13",
        "isDefault": True,
    },
    "bitbucket.repository.get": {
        "slug": "widgets",
        "id": 2,
        "name": "Widgets",
        "state": "AVAILABLE",
        "project": {"key": "PRJ"},
    },
    "confluence.space.get": {
        "id": 11,
        "key": "TST",
        "name": "Example space",
        "type": "global",
        "unknownField": [1, 2, 3],
    },
    "jira.attachment.get": {
        "self": "https://atlassian.example/rest/api/2/attachment/10001",
        "filename": "report.txt",
        "size": 1234,
        "mimeType": "text/plain",
        "content": "https://other.example/attachment/content/10001",
        "thumbnail": "https://other.example/attachment/thumbnail/10001",
        "_links": {"download": "https://other.example/attachment/content/10001"},
    },
    "jira.issue.votes": {
        "self": "https://atlassian.example/rest/api/2/issue/EX-1/votes",
        "votes": 2,
        "hasVoted": True,
        "voters": [{"name": "fred"}, {"name": "anna", "extra": "kept"}],
    },
    "jira.issue.watchers": {
        "self": "https://atlassian.example/rest/api/2/issue/EX-1/watchers",
        "isWatching": False,
        "watchCount": 1,
        "watchers": [{"name": "fred"}],
    },
    "jira.project.components": [
        {
            "id": "10000",
            "name": "Component 1",
            "isAssigneeTypeValid": False,
            "extra": "kept",
        },
        {
            "id": "10050",
            "name": "PXA",
            "isAssigneeTypeValid": True,
        },
    ],
    "jira.project.get": {
        "id": "10000",
        "key": "EX",
        "name": "Example",
        "unknownField": {"kept": True},
        "_links": {"self": "https://other.example/rest/api/2/project/EX"},
    },
    "jira.project.versions": [
        {"id": "10000", "name": "1.0", "released": True},
        {"id": "10010", "name": "2.0", "extra": "kept"},
    ],
}


class _Response:
    def __init__(self, status: int, body: bytes) -> None:
        self.status_code = status
        self.headers = {"Content-Type": "application/json"}
        self._body = body

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *exc_info: object) -> bool:
        return False

    def iter_content(self, chunk_size: int) -> Iterator[bytes]:
        for start in range(0, len(self._body), chunk_size):
            yield self._body[start : start + chunk_size]


class _Capture:
    """A real bearer session with scripted GET and forbidden other methods."""

    def __init__(self, token: str, status: int, body: bytes) -> None:
        self.session = real_bearer_session(token)
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.mutating: list[str] = []
        self._status = status
        self._body = body
        setattr(self.session, "get", self._get)
        for name in ("post", "put", "patch", "delete", "head"):
            setattr(self.session, name, self._mutator(name))

    def _get(self, url: str, **kwargs: object) -> _Response:
        self.calls.append((url, dict(kwargs)))
        return _Response(self._status, self._body)

    def _mutator(self, name: str) -> object:
        def call(*args: object, **kwargs: object) -> object:
            self.mutating.append(name)
            raise AssertionError(f"{name} must never be called")

        return call


def install_transport(
    monkeypatch: pytest.MonkeyPatch,
    *,
    body: object = b"",
    status: int = 200,
    token: str = TOKEN,
) -> list[_Capture]:
    payload = body if isinstance(body, bytes) else json.dumps(body).encode()
    captures: list[_Capture] = []

    def factory(value: str) -> requests.Session:
        capture = _Capture(value, status, payload)
        captures.append(capture)
        return capture.session

    monkeypatch.setattr(operations, "bearer_session", factory)
    return captures


def forbid_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    def factory(token: str) -> requests.Session:
        raise AssertionError("No session may be created for an invalid request")

    monkeypatch.setattr(operations, "bearer_session", factory)


EXPECTED.update(
    {
        "jira.mypermissions.get": {
            "product": "jira",
            "path": "/rest/api/2/mypermissions",
            "version": "Jira Server 8.22.0 REST API 2",
            "kind": "object",
            "required": (),
            "items_required": (),
            "object_arrays": (),
            "arguments": (),
        },
        "jira.user.get": {
            "product": "jira",
            "path": "/rest/api/2/user",
            "version": "Jira Server 8.22.0 REST API 2",
            "kind": "object",
            "required": (("active", "boolean"),),
            "items_required": (),
            "object_arrays": (),
            "arguments": (),
        },
        "jira.user.assignable-search": {
            "product": "jira",
            "path": "/rest/api/2/user/assignable/search",
            "version": "Jira Server 8.22.0 REST API 2",
            "kind": "array",
            "required": (),
            "items_required": (("active", "boolean"),),
            "object_arrays": (),
            "arguments": (),
        },
        "jira.field.list": {
            "product": "jira",
            "path": "/rest/api/2/field",
            "version": "Jira Server 8.22.0 REST API 2",
            "kind": "array",
            "required": (),
            "items_required": (),
            "object_arrays": (),
            "arguments": (),
        },
        "jira.project.statuses": {
            "product": "jira",
            "path": "/rest/api/2/project/{projectIdOrKey}/statuses",
            "version": "Jira Server 8.22.0 REST API 2",
            "kind": "array",
            "required": (),
            "items_required": (("subtask", "boolean"),),
            "object_arrays": (),
            "arguments": ("projectIdOrKey",),
        },
        "jira.project.roles": {
            "product": "jira",
            "path": "/rest/api/2/project/{projectIdOrKey}/role",
            "version": "Jira Server 8.22.0 REST API 2",
            "kind": "object",
            "required": (),
            "items_required": (),
            "object_arrays": (),
            "arguments": ("projectIdOrKey",),
        },
        "jira.issue.comment.get": {
            "product": "jira",
            "path": "/rest/api/2/issue/{issueIdOrKey}/comment/{id}",
            "version": "Jira Server 8.22.0 REST API 2",
            "kind": "object",
            "required": (),
            "items_required": (),
            "object_arrays": (),
            "arguments": ("issueIdOrKey", "id"),
        },
        "jira.issue.worklog.get": {
            "product": "jira",
            "path": "/rest/api/2/issue/{issueIdOrKey}/worklog/{id}",
            "version": "Jira Server 8.22.0 REST API 2",
            "kind": "object",
            "required": (),
            "items_required": (),
            "object_arrays": (),
            "arguments": ("issueIdOrKey", "id"),
        },
        "jira.issue-link.get": {
            "product": "jira",
            "path": "/rest/api/2/issueLink/{linkId}",
            "version": "Jira Server 8.22.0 REST API 2",
            "kind": "object",
            "required": (),
            "items_required": (),
            "object_arrays": (),
            "arguments": ("linkId",),
        },
        "jira.filter.favourites": {
            "product": "jira",
            "path": "/rest/api/2/filter/favourite",
            "version": "Jira Server 8.22.0 REST API 2",
            "kind": "array",
            "required": (),
            "items_required": (),
            "object_arrays": (),
            "arguments": (),
        },
        "jira.jql.autocomplete": {
            "product": "jira",
            "path": "/rest/api/2/jql/autocompletedata",
            "version": "Jira Server 8.22.0 REST API 2",
            "kind": "object",
            "required": (),
            "items_required": (),
            "object_arrays": (),
            "arguments": (),
        },
        "jira.dashboard.list": {
            "product": "jira",
            "path": "/rest/api/2/dashboard",
            "version": "Jira Server 8.22.0 REST API 2",
            "kind": "object",
            "required": (),
            "items_required": (),
            "object_arrays": (),
            "arguments": (),
        },
        "confluence.content.by-title": {
            "product": "confluence",
            "path": "/rest/api/content",
            "version": "Confluence Server 6.6.0 REST API",
            "kind": "object",
            "required": (),
            "items_required": (),
            "object_arrays": (),
            "arguments": (),
        },
        "confluence.content.search": {
            "product": "confluence",
            "path": "/rest/api/content/search",
            "version": "Confluence Server 6.6.0 REST API",
            "kind": "object",
            "required": (),
            "items_required": (),
            "object_arrays": (),
            "arguments": (),
        },
        "confluence.space.content": {
            "product": "confluence",
            "path": "/rest/api/space/{spaceKey}/content",
            "version": "Confluence Server 6.6.0 REST API",
            "kind": "object",
            "required": (),
            "items_required": (),
            "object_arrays": (),
            "arguments": ("spaceKey",),
        },
        "confluence.content.properties": {
            "product": "confluence",
            "path": "/rest/api/content/{id}/property",
            "version": "Confluence Server 6.6.0 REST API",
            "kind": "object",
            "required": (),
            "items_required": (),
            "object_arrays": (),
            "arguments": ("id",),
        },
        "confluence.content.attachments": {
            "product": "confluence",
            "path": "/rest/api/content/{id}/child/attachment",
            "version": "Confluence Server 6.6.0 REST API",
            "kind": "object",
            "required": (),
            "items_required": (),
            "object_arrays": (),
            "arguments": ("id",),
        },
        "confluence.content.children": {
            "product": "confluence",
            "path": "/rest/api/content/{id}/child",
            "version": "Confluence Server 6.6.0 REST API",
            "kind": "object",
            "required": (),
            "items_required": (),
            "object_arrays": (),
            "arguments": ("id",),
        },
        "confluence.user.get": {
            "product": "confluence",
            "path": "/rest/api/user",
            "version": "Confluence Server 6.6.0 REST API",
            "kind": "object",
            "required": (),
            "items_required": (),
            "object_arrays": (),
            "arguments": (),
        },
    }
)

SAMPLES.update(
    {
        "jira.mypermissions.get": {},
        "jira.user.get": {},
        "jira.user.assignable-search": {},
        "jira.field.list": {},
        "jira.project.statuses": {"projectIdOrKey": "EX"},
        "jira.project.roles": {"projectIdOrKey": "EX"},
        "jira.issue.comment.get": {"issueIdOrKey": "EX-1", "id": "10000"},
        "jira.issue.worklog.get": {"issueIdOrKey": "EX-1", "id": "10001"},
        "jira.issue-link.get": {"linkId": "10002"},
        "jira.filter.favourites": {},
        "jira.jql.autocomplete": {},
        "jira.dashboard.list": {},
        "confluence.content.by-title": {},
        "confluence.content.search": {},
        "confluence.space.content": {"spaceKey": "TST"},
        "confluence.content.properties": {"id": "1234"},
        "confluence.content.attachments": {"id": "1234"},
        "confluence.content.children": {"id": "1234"},
        "confluence.user.get": {},
    }
)

SAMPLE_QUERY: dict[str, dict[str, object] | None] = {
    "jira.mypermissions.get": None,
    "jira.user.get": {"username": "fred"},
    "jira.user.assignable-search": {"project": "EX"},
    "jira.field.list": None,
    "jira.project.statuses": None,
    "jira.project.roles": None,
    "jira.issue.comment.get": None,
    "jira.issue.worklog.get": None,
    "jira.issue-link.get": None,
    "jira.filter.favourites": None,
    "jira.jql.autocomplete": None,
    "jira.dashboard.list": None,
    "confluence.content.by-title": {"title": "Example"},
    "confluence.content.search": {"cql": "space = TST"},
    "confluence.space.content": None,
    "confluence.content.properties": None,
    "confluence.content.attachments": None,
    "confluence.content.children": None,
    "confluence.user.get": {"username": "jcitizen"},
}

BODIES.update(
    {
        "jira.mypermissions.get": {
            "permissions": {"EDIT_ISSUE": {"havePermission": True}}
        },
        "jira.user.get": {"active": True, "name": "fred", "displayName": "Fred"},
        "jira.user.assignable-search": [{"active": True, "name": "fred"}],
        "jira.field.list": [{"id": "summary", "name": "Summary", "custom": False}],
        "jira.project.statuses": [
            {"id": "1", "name": "Task", "subtask": False, "statuses": []}
        ],
        "jira.project.roles": {
            "Developers": "https://atlassian.example/rest/api/2/project/EX/role/10000"
        },
        "jira.issue.comment.get": {"id": "10000", "body": "A comment"},
        "jira.issue.worklog.get": {"id": "10001", "timeSpent": "3h"},
        "jira.issue-link.get": {"id": "10002", "type": {"name": "Duplicate"}},
        "jira.filter.favourites": [{"id": "10000", "name": "All Open Bugs"}],
        "jira.jql.autocomplete": {
            "visibleFieldNames": [],
            "visibleFunctionNames": [],
            "jqlReservedWords": [],
        },
        "jira.dashboard.list": {
            "startAt": 0,
            "maxResults": 10,
            "total": 1,
            "dashboards": [{"id": "10000", "name": "System Dashboard"}],
        },
        "confluence.content.by-title": {
            "results": [{"id": "1234", "type": "page", "title": "Example"}],
            "size": 1,
        },
        "confluence.content.search": {
            "results": [{"id": "1234", "title": "Example"}],
            "size": 1,
        },
        "confluence.space.content": {
            "results": [{"id": "1234", "title": "Example"}],
            "size": 1,
        },
        "confluence.content.properties": {
            "results": [{"key": "example-property-key"}],
            "size": 1,
        },
        "confluence.content.attachments": {
            "results": [{"id": "att1", "title": "file.txt"}],
            "size": 1,
        },
        "confluence.content.children": {
            "page": {"results": [{"id": "1234"}], "size": 1}
        },
        "confluence.user.get": {"type": "known", "username": "jcitizen"},
    }
)

EXPECTED_QUERY.update(
    {
        "jira.mypermissions.get": (
            ("projectKey", "string", False, None, None, None, None, ()),
            ("projectId", "integer", False, None, 1, 2147483647, None, ()),
            ("issueKey", "string", False, None, None, None, None, ()),
            ("issueId", "integer", False, None, 1, 2147483647, None, ()),
        ),
        "jira.user.get": (
            ("username", "string", False, None, None, None, None, ()),
            ("key", "string", False, None, None, None, None, ()),
        ),
        "jira.user.assignable-search": (
            ("username", "string", False, None, None, None, None, ()),
            ("project", "string", False, None, None, None, None, ()),
            ("issueKey", "string", False, None, None, None, None, ()),
            ("startAt", "integer", False, None, 0, 2147483647, None, ()),
            ("maxResults", "integer", False, None, 1, 2147483647, None, ()),
            ("actionDescriptorId", "integer", False, None, None, None, None, ()),
        ),
        "jira.field.list": (),
        "jira.project.statuses": (),
        "jira.project.roles": (),
        "jira.issue.comment.get": (
            ("expand", "string", False, None, None, None, None, ()),
        ),
        "jira.issue.worklog.get": (),
        "jira.issue-link.get": (),
        "jira.filter.favourites": (
            ("expand", "string", False, None, None, None, None, ()),
        ),
        "jira.jql.autocomplete": (),
        "jira.dashboard.list": (
            ("filter", "string", False, None, None, None, None, ()),
            ("startAt", "integer", False, None, 0, 2147483647, None, ()),
            ("maxResults", "integer", False, None, 1, 2147483647, None, ()),
        ),
        "confluence.content.by-title": (
            ("title", "string", True, None, None, None, None, ()),
            ("spaceKey", "string", False, None, None, None, None, ()),
            ("expand", "string", False, None, None, None, None, ()),
            ("start", "integer", False, None, 0, 2147483647, None, ()),
            ("limit", "integer", False, None, 1, 2147483647, None, ()),
        ),
        "confluence.content.search": (
            ("cql", "string", True, None, None, None, None, ()),
            ("expand", "string", False, None, None, None, None, ()),
            ("start", "integer", False, None, 0, 2147483647, None, ()),
            ("limit", "integer", False, None, 1, 2147483647, None, ()),
        ),
        "confluence.space.content": (
            ("depth", "string", False, None, None, None, None, ("all", "root")),
            ("expand", "string", False, None, None, None, None, ()),
            ("start", "integer", False, None, 0, 2147483647, None, ()),
            ("limit", "integer", False, None, 1, 2147483647, None, ()),
        ),
        "confluence.content.properties": (
            ("expand", "string", False, None, None, None, None, ()),
            ("start", "integer", False, None, 0, 2147483647, None, ()),
            ("limit", "integer", False, None, 1, 2147483647, None, ()),
        ),
        "confluence.content.attachments": (
            ("expand", "string", False, None, None, None, None, ()),
            ("start", "integer", False, None, 0, 2147483647, None, ()),
            ("limit", "integer", False, None, 1, 2147483647, None, ()),
            ("filename", "string", False, None, None, None, None, ()),
            ("mediaType", "string", False, None, None, None, None, ()),
        ),
        "confluence.content.children": (
            ("expand", "string", False, None, None, None, None, ()),
            ("parentVersion", "integer", False, None, 0, 2147483647, None, ()),
            ("start", "integer", False, None, 0, 2147483647, None, ()),
            ("limit", "integer", False, None, 1, 2147483647, None, ()),
        ),
        "confluence.user.get": (
            ("key", "string", False, None, None, None, None, ()),
            ("username", "string", False, None, None, None, None, ()),
            ("expand", "string", False, None, None, None, None, ()),
        ),
    }
)


EXPECTED_RULES: dict[str, tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]] = {
    "jira.mypermissions.get": (
        ("projectKey", "projectId", "issueKey", "issueId"),
        (),
        (),
    ),
    "jira.user.get": ((), ("username", "key"), ()),
    "jira.user.assignable-search": ((), ("project", "issueKey"), ()),
    "confluence.user.get": ((), (), ("key", "username")),
}


@pytest.fixture(autouse=True)
def _missing_bbk_credentials(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("BBK_CREDENTIALS", str(tmp_path / "missing.json"))


def test_catalog_describes_every_manifest_route_and_the_hand_written_set() -> None:
    described = list_operations()
    by_id = {cast(str, entry["id"]): entry for entry in described}
    by_route = {
        (entry["product"], entry["method"], entry["path"]): entry for entry in described
    }
    manifest = json.loads(
        (Path(__file__).parents[1] / "src/atlawire/manifest.json").read_text(
            encoding="utf-8"
        )
    )

    # Every generated route is advertised with the manifest's own method and
    # path, so a wrong or dropped route fails without comparing two views of
    # the same registry.
    for row in manifest["operations"]:
        entry = by_route[(row["product"], row["method"], row["path"])]
        assert entry["product"] == row["product"]
        assert entry["method"] == row["method"]
        assert entry["path"] == row["path"]

    # The hand-written operations keep their independently enumerated shape.
    for operation_id, expected in EXPECTED.items():
        entry = by_id[operation_id]
        assert entry["product"] == expected["product"]
        assert entry["method"] == "GET"
        assert entry["path"] == expected["path"]
        assert entry["documented_version"] == expected["version"]
        description = cast(str, entry["description"])
        assert description
        assert "\n" not in description

        response = cast(dict[str, object], entry["response"])
        assert response["kind"] == expected["kind"]
        assert _fields(response["required"]) == list(
            cast(tuple[tuple[str, str], ...], expected["required"])
        )
        assert _fields(response["items_required"]) == list(
            cast(tuple[tuple[str, str], ...], expected["items_required"])
        )
        assert response["optional_object_arrays"] == list(
            cast(tuple[str, ...], expected["object_arrays"])
        )
        assert response["null_on_204"] == (
            operation_id == "bitbucket.repository.default-branch"
        )

        arguments = cast(list[dict[str, object]], entry["arguments"])
        assert [argument["name"] for argument in arguments] == list(
            cast(tuple[str, ...], expected["arguments"])
        )
        for argument in arguments:
            assert set(argument) == {
                "name",
                "type",
                "pattern",
                "max_length",
                "allow_slash",
                "description",
            }
            assert argument["type"] == "string"
            assert isinstance(argument["pattern"], str) and argument["pattern"]
            assert argument["max_length"] == 255
            assert argument["allow_slash"] is False
            assert isinstance(argument["description"], str) and argument["description"]

        rules = cast(dict[str, object], entry["query_rules"])
        assert set(rules) == {
            "at_most_one",
            "at_least_one",
            "exactly_one",
        }
        (
            expected_at_most,
            expected_at_least,
            expected_exactly,
        ) = EXPECTED_RULES.get(operation_id, ((), (), ()))
        assert tuple(rules["at_most_one"]) == expected_at_most
        assert tuple(rules["at_least_one"]) == expected_at_least
        assert tuple(rules["exactly_one"]) == expected_exactly

        query = cast(list[dict[str, object]], entry["query"])
        assert [
            (
                field["name"],
                field["type"],
                field["required"],
                field["max_length"],
                field["minimum"],
                field["maximum"],
                field["format"],
                tuple(field["enum"]),
            )
            for field in query
        ] == list(EXPECTED_QUERY.get(operation_id, ()))
        for field in query:
            assert set(field) == {
                "name",
                "type",
                "required",
                "description",
                "max_length",
                "minimum",
                "maximum",
                "format",
                "enum",
            }
            assert isinstance(field["description"], str) and field["description"]

    # The catalog must be JSON data for an agent-facing CLI response.
    assert json.loads(json.dumps(described)) == described


def _fields(value: object) -> list[tuple[str, str]]:
    return [
        (cast(str, field["name"]), cast(str, field["type"]))
        for field in cast(list[dict[str, object]], value)
    ]


def test_catalog_is_stable_and_does_not_read_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("list_operations must not read credentials")

    monkeypatch.setattr("atlawire.credentials.load_saved_credentials", forbidden)
    first = list_operations()
    first[0]["path"] = "/tampered"
    cast(dict[str, object], first[0]["response"])["kind"] = "array"

    second = list_operations()

    assert second == list_operations()
    assert second[0]["path"] != "/tampered"
    assert cast(dict[str, object], second[0]["response"])["kind"] != "array"


@pytest.mark.parametrize("operation_id", sorted(EXPECTED))
def test_each_operation_sends_exactly_one_fixed_get(
    monkeypatch: pytest.MonkeyPatch, operation_id: str
) -> None:
    body = BODIES[operation_id]
    captures = install_transport(monkeypatch, body=body)
    query = SAMPLE_QUERY.get(operation_id)

    result = read_operation(
        operation_id,
        BASE,
        token=TOKEN,
        arguments=cast(Mapping[str, object], SAMPLES[operation_id]),
        query=query,
    )

    assert result == body
    assert len(captures) == 1
    capture = captures[0]
    assert len(capture.calls) == 1
    url, kwargs = capture.calls[0]
    expected_path = cast(str, EXPECTED[operation_id]["path"]).format(
        **cast(dict[str, str], SAMPLES[operation_id])
    )
    assert url == BASE + expected_path
    assert kwargs["params"] == ({} if query is None else query)
    assert kwargs["allow_redirects"] is False
    assert kwargs["stream"] is True
    assert kwargs["timeout"] == (5, 30)
    assert capture.mutating == []
    assert capture.session.headers["Authorization"] == f"Bearer {TOKEN}"
    assert TOKEN not in url


@pytest.mark.parametrize(
    ("operation_id", "path", "body"),
    [
        (
            "bitbucket.repository.compare-changes",
            (
                "/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}"
                "/compare/changes"
            ),
            BODIES["bitbucket.repository.compare-changes"],
        ),
        (
            "bitbucket.repository.compare-commits",
            (
                "/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}"
                "/compare/commits"
            ),
            BODIES["bitbucket.repository.compare-commits"],
        ),
    ],
)
def test_compare_operations_forward_declared_query_values(
    monkeypatch: pytest.MonkeyPatch,
    operation_id: str,
    path: str,
    body: object,
) -> None:
    captures = install_transport(monkeypatch, body=body)
    query = {
        "from": "feature&next=1",
        "to": "ветка?x#y",
        "fromRepo": "PRJ/widgets",
        "start": 25,
        "limit": 100,
    }

    result = read_operation(
        operation_id,
        BASE,
        token=TOKEN,
        arguments={"projectKey": "PRJ", "repositorySlug": "widgets"},
        query=query,
    )

    assert result == body
    assert len(captures) == 1
    url, kwargs = captures[0].calls[0]
    assert url == BASE + path.format(projectKey="PRJ", repositorySlug="widgets")
    assert kwargs["params"] == query
    assert kwargs["params"] is not query
    assert kwargs["allow_redirects"] is False
    assert kwargs["stream"] is True
    assert captures[0].mutating == []


@pytest.mark.parametrize(
    "from_repo", ["42", "PRJ/widgets", "~user/repo", "PRJ/a.b-c_d"]
)
def test_from_repo_accepts_documented_repository_id_or_project_slug(
    monkeypatch: pytest.MonkeyPatch, from_repo: str
) -> None:
    captures = install_transport(
        monkeypatch, body=BODIES["bitbucket.repository.compare-commits"]
    )

    read_operation(
        "bitbucket.repository.compare-commits",
        BASE,
        token=TOKEN,
        arguments={"projectKey": "PRJ", "repositorySlug": "widgets"},
        query={"fromRepo": from_repo},
    )

    assert captures[0].calls[0][1]["params"] == {"fromRepo": from_repo}


@pytest.mark.parametrize(
    "operation_id",
    [
        "bitbucket.repository.compare-changes",
        "bitbucket.repository.compare-commits",
        "jira.project.get",
    ],
)
def test_absent_or_empty_query_is_backward_compatible(
    monkeypatch: pytest.MonkeyPatch, operation_id: str
) -> None:
    body = BODIES[operation_id]
    arguments = cast(Mapping[str, object], SAMPLES[operation_id])
    for query in (None, {}):
        captures = install_transport(monkeypatch, body=body)
        read_operation(
            operation_id,
            BASE,
            token=TOKEN,
            arguments=arguments,
            query=query,
        )
        assert captures[0].calls[0][1]["params"] == {}


@pytest.mark.parametrize(
    ("operation_id", "query"),
    [
        (
            "bitbucket.repository.compare-commits",
            {"unknown": SENTINEL},
        ),
        (
            "bitbucket.repository.compare-commits",
            {"from": [SENTINEL]},
        ),
        ("bitbucket.repository.compare-commits", {"to": True}),
        ("bitbucket.repository.compare-commits", {"from": None}),
        ("bitbucket.repository.compare-commits", {"from": ""}),
        (
            "bitbucket.repository.compare-commits",
            {"from": "bad\nvalue"},
        ),
        (
            "bitbucket.repository.compare-commits",
            {"from": "x" * 256},
        ),
        (
            "bitbucket.repository.compare-commits",
            {"fromRepo": "PRJ"},
        ),
        (
            "bitbucket.repository.compare-commits",
            {"fromRepo": "PRJ/a/b"},
        ),
        (
            "bitbucket.repository.compare-commits",
            {"fromRepo": "PRJ/.."},
        ),
        ("bitbucket.repository.compare-commits", {"fromRepo": "0"}),
        (
            "bitbucket.repository.compare-commits",
            {"fromRepo": ["PRJ", "widgets"]},
        ),
        ("bitbucket.repository.compare-commits", {"start": "0"}),
        ("bitbucket.repository.compare-commits", {"start": -1}),
        ("bitbucket.repository.compare-commits", {"start": 2**31}),
        ("bitbucket.repository.compare-commits", {"limit": 0}),
        ("bitbucket.repository.compare-commits", {"limit": 2**31}),
        ("jira.project.get", {"from": "a"}),
        (
            "bitbucket.repository.participants",
            {"direction": "SIDEWAYS"},
        ),
        (
            "bitbucket.repository.participants",
            {"role": "OWNER"},
        ),
        (
            "bitbucket.repository.participants",
            {"filter": [SENTINEL]},
        ),
        (
            "bitbucket.repository.commit-comments",
            {"path": 1},
        ),
        (
            "bitbucket.repository.commit-comments",
            {"since": [COMMIT_ID]},
        ),
        (
            "bitbucket.repository.pull-request-activity",
            {"fromId": 1},
        ),
        (
            "bitbucket.profile.recent-repositories",
            {"permission": "REPO_READ"},
        ),
        (
            "bitbucket.users.list",
            {"filter": "jdoe"},
        ),
        ("bitbucket.task.get", {"start": 0}),
        ("bitbucket.user.get", {"start": 0}),
    ],
)
def test_invalid_query_fails_before_transport(
    monkeypatch: pytest.MonkeyPatch,
    operation_id: str,
    query: Mapping[str, object],
) -> None:
    forbid_transport(monkeypatch)

    with pytest.raises(AtlaWireError) as raised:
        read_operation(
            operation_id,
            BASE,
            token=TOKEN,
            arguments=cast(Mapping[str, object], SAMPLES[operation_id]),
            query=query,
        )

    assert str(raised.value) == "The query parameters are invalid."
    assert SENTINEL not in str(raised.value)


@pytest.mark.parametrize("query", [[], "from=a", [("from", "a")], SENTINEL])
def test_non_mapping_query_is_rejected(
    monkeypatch: pytest.MonkeyPatch, query: object
) -> None:
    forbid_transport(monkeypatch)

    with pytest.raises(AtlaWireError) as raised:
        read_operation(
            "bitbucket.repository.compare-commits",
            BASE,
            token=TOKEN,
            arguments={"projectKey": "PRJ", "repositorySlug": "widgets"},
            query=cast(Mapping[str, object], query),
        )

    assert str(raised.value) == "The query parameters are invalid."
    assert SENTINEL not in str(raised.value)


@pytest.mark.parametrize(
    "operation_id",
    [
        "bitbucket.repository.commit-comments",
        "bitbucket.repository.forks",
        "bitbucket.repository.participants",
        "bitbucket.repository.pull-request-activity",
        "bitbucket.repository.related",
        "bitbucket.profile.recent-repositories",
        "bitbucket.users.list",
    ],
)
def test_paged_operations_forward_start_and_limit(
    monkeypatch: pytest.MonkeyPatch, operation_id: str
) -> None:
    captures = install_transport(monkeypatch, body=BODIES[operation_id])

    read_operation(
        operation_id,
        BASE,
        token=TOKEN,
        arguments=cast(Mapping[str, object], SAMPLES[operation_id]),
        query={"start": 25, "limit": 100},
    )

    assert captures[0].calls[0][1]["params"] == {"start": 25, "limit": 100}


def test_participants_query_accepts_documented_filters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captures = install_transport(
        monkeypatch, body=BODIES["bitbucket.repository.participants"]
    )
    query = {
        "direction": "INCOMING",
        "filter": "Джейн Doe",
        "role": "REVIEWER",
        "start": 0,
        "limit": 25,
    }

    read_operation(
        "bitbucket.repository.participants",
        BASE,
        token=TOKEN,
        arguments={"projectKey": "PRJ", "repositorySlug": "widgets"},
        query=query,
    )

    assert captures[0].calls[0][1]["params"] == query


def test_commit_comments_query_accepts_path_and_since(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captures = install_transport(
        monkeypatch, body=BODIES["bitbucket.repository.commit-comments"]
    )
    query = {
        "path": "src/файл a.py",
        "since": COMMIT_ID,
        "start": 0,
        "limit": 25,
    }

    read_operation(
        "bitbucket.repository.commit-comments",
        BASE,
        token=TOKEN,
        arguments={
            "projectKey": "PRJ",
            "repositorySlug": "widgets",
            "commitId": COMMIT_ID,
        },
        query=query,
    )

    assert captures[0].calls[0][1]["params"] == query


@pytest.mark.parametrize(
    ("operation_id", "query"),
    [
        ("jira.mypermissions.get", {"projectKey": "EX"}),
        ("jira.user.get", {"username": "fred"}),
        ("jira.user.get", {"key": "JIRAUSER1"}),
        (
            "jira.user.get",
            {"username": "fred", "key": "JIRAUSER1"},
        ),
        ("jira.user.assignable-search", {"project": "EX"}),
        ("jira.user.assignable-search", {"issueKey": "EX-1"}),
        (
            "jira.user.assignable-search",
            {"project": "EX", "issueKey": "EX-1"},
        ),
        (
            "jira.user.assignable-search",
            {"issueKey": "EX-1", "actionDescriptorId": 7},
        ),
        ("confluence.user.get", {"key": "abc"}),
        ("confluence.user.get", {"username": "jcitizen"}),
    ],
)
def test_query_rule_choices_are_accepted(
    monkeypatch: pytest.MonkeyPatch,
    operation_id: str,
    query: Mapping[str, object],
) -> None:
    captures = install_transport(monkeypatch, body=BODIES[operation_id])

    read_operation(
        operation_id,
        BASE,
        token=TOKEN,
        arguments=cast(Mapping[str, object], SAMPLES[operation_id]),
        query=query,
    )

    assert captures[0].calls[0][1]["params"] == query


@pytest.mark.parametrize(
    ("operation_id", "query"),
    [
        (
            "jira.mypermissions.get",
            {"projectKey": "EX", "issueKey": "EX-1"},
        ),
        ("jira.user.get", {}),
        ("jira.user.assignable-search", {}),
        ("confluence.user.get", {}),
        (
            "confluence.user.get",
            {"key": "abc", "username": "jcitizen"},
        ),
    ],
)
def test_query_rules_reject_empty_or_multiple_choices(
    monkeypatch: pytest.MonkeyPatch,
    operation_id: str,
    query: Mapping[str, object],
) -> None:
    forbid_transport(monkeypatch)

    with pytest.raises(AtlaWireError) as raised:
        read_operation(
            operation_id,
            BASE,
            token=TOKEN,
            arguments=cast(Mapping[str, object], SAMPLES[operation_id]),
            query=query,
        )

    assert str(raised.value) == "The query parameters are invalid."


def test_long_cql_is_not_capped_at_255_characters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cql = 'space = TST AND text ~ "' + "x" * 300 + '"'
    captures = install_transport(monkeypatch, body=BODIES["confluence.content.search"])

    read_operation(
        "confluence.content.search",
        BASE,
        token=TOKEN,
        arguments={},
        query={"cql": cql},
    )

    assert len(cql) > 255
    assert captures[0].calls[0][1]["params"] == {"cql": cql}


@pytest.mark.parametrize(
    ("operation_id", "query"),
    [
        ("confluence.content.by-title", {"title": "Example Page"}),
        ("confluence.content.search", {"cql": 'space = TST AND text ~ "deploy"'}),
    ],
)
def test_required_new_query_fields_accept_declared_values(
    monkeypatch: pytest.MonkeyPatch,
    operation_id: str,
    query: Mapping[str, object],
) -> None:
    captures = install_transport(monkeypatch, body=BODIES[operation_id])

    read_operation(
        operation_id,
        BASE,
        token=TOKEN,
        arguments=cast(Mapping[str, object], SAMPLES[operation_id]),
        query=query,
    )

    assert captures[0].calls[0][1]["params"] == query


@pytest.mark.parametrize(
    "operation_id",
    ["confluence.content.by-title", "confluence.content.search"],
)
def test_required_new_query_fields_reject_missing_values(
    monkeypatch: pytest.MonkeyPatch, operation_id: str
) -> None:
    forbid_transport(monkeypatch)

    with pytest.raises(AtlaWireError) as raised:
        read_operation(
            operation_id,
            BASE,
            token=TOKEN,
            arguments=cast(Mapping[str, object], SAMPLES[operation_id]),
            query={},
        )

    assert str(raised.value) == "The query parameters are invalid."


@pytest.mark.parametrize(
    ("operation_id", "query"),
    [
        (
            "jira.user.assignable-search",
            {"project": "EX", "startAt": 25, "maxResults": 100},
        ),
        (
            "jira.dashboard.list",
            {"startAt": 25, "maxResults": 100},
        ),
        (
            "confluence.content.by-title",
            {"title": "Example", "start": 25, "limit": 100},
        ),
        (
            "confluence.content.search",
            {"cql": "space = TST", "start": 25, "limit": 100},
        ),
        (
            "confluence.space.content",
            {"depth": "all", "start": 25, "limit": 100},
        ),
        (
            "confluence.content.properties",
            {"start": 25, "limit": 100},
        ),
        (
            "confluence.content.attachments",
            {
                "filename": "my file.txt",
                "mediaType": "text/plain",
                "start": 25,
                "limit": 100,
            },
        ),
        (
            "confluence.content.children",
            {"parentVersion": 0, "start": 25, "limit": 100},
        ),
    ],
)
def test_new_paged_queries_forward_declared_values(
    monkeypatch: pytest.MonkeyPatch,
    operation_id: str,
    query: Mapping[str, object],
) -> None:
    captures = install_transport(monkeypatch, body=BODIES[operation_id])

    read_operation(
        operation_id,
        BASE,
        token=TOKEN,
        arguments=cast(Mapping[str, object], SAMPLES[operation_id]),
        query=query,
    )

    assert captures[0].calls[0][1]["params"] == query


@pytest.mark.parametrize(
    ("operation_id", "query"),
    [
        ("jira.dashboard.list", {"startAt": -1}),
        ("confluence.space.content", {"depth": "other"}),
        (
            "confluence.content.by-title",
            {"title": "Example", "type": "page"},
        ),
        (
            "jira.user.get",
            {"username": "fred", "includeDeleted": True},
        ),
        (
            "jira.user.assignable-search",
            {"project": "EX", "actionDescriptorId": 1},
        ),
        ("confluence.space.content", {"status": "current"}),
    ],
)
def test_new_query_rejects_undeclared_or_enum_values(
    monkeypatch: pytest.MonkeyPatch,
    operation_id: str,
    query: Mapping[str, object],
) -> None:
    forbid_transport(monkeypatch)

    with pytest.raises(AtlaWireError) as raised:
        read_operation(
            operation_id,
            BASE,
            token=TOKEN,
            arguments=cast(Mapping[str, object], SAMPLES[operation_id]),
            query=query,
        )

    assert str(raised.value) == "The query parameters are invalid."


def test_attachment_metadata_never_fetches_the_returned_content_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captures = install_transport(monkeypatch, body=BODIES["jira.attachment.get"])

    read_operation(
        "jira.attachment.get",
        BASE,
        token=TOKEN,
        arguments={"id": "10001"},
    )

    assert len(captures) == 1
    assert [call[0] for call in captures[0].calls] == [
        BASE + "/rest/api/2/attachment/10001"
    ]
    assert all("content" not in call[0] for call in captures[0].calls)


@pytest.mark.parametrize(
    "operation_id",
    [
        "",
        "jira.project.get ",
        "JIRA.PROJECT.GET",
        "jira.issue.delete",
        "jira.issue.create",
        "jira.issue.update",
        "bitbucket.project.create",
        "bitbucket.repository.delete",
        "confluence.space.delete",
        "admin.user.get",
        "search",
        "/rest/api/2/project/EX",
        "https://atlassian.example/rest/api/2/project/EX",
        "jira.issue." + SENTINEL,
    ],
)
def test_unknown_mutating_and_administrative_ids_are_rejected(
    monkeypatch: pytest.MonkeyPatch, operation_id: str
) -> None:
    forbid_transport(monkeypatch)

    with pytest.raises(AtlaWireError) as raised:
        read_operation(
            operation_id,
            BASE,
            token=TOKEN,
            arguments={"projectIdOrKey": SENTINEL},
        )

    assert str(raised.value) == "Unknown operation ID."
    assert SENTINEL not in str(raised.value)


@pytest.mark.parametrize("operation_id", [None, 1, True, ["jira.project.get"]])
def test_non_string_operation_ids_are_rejected(
    monkeypatch: pytest.MonkeyPatch, operation_id: object
) -> None:
    forbid_transport(monkeypatch)

    with pytest.raises(AtlaWireError, match="Unknown operation ID"):
        read_operation(
            cast(str, operation_id),
            BASE,
            token=TOKEN,
            arguments={"projectIdOrKey": "EX"},
        )


@pytest.mark.parametrize(
    ("operation_id", "arguments"),
    [
        ("jira.project.get", {}),
        ("jira.project.get", {"projectIdOrKey": "EX", "extra": SENTINEL}),
        ("jira.project.get", {"projectIdOrKey": "EX", SENTINEL: "x"}),
        ("jira.project.get", {"projectIdOrKey": 10000}),
        ("jira.project.get", {"projectIdOrKey": 1.0}),
        ("jira.project.get", {"projectIdOrKey": True}),
        ("jira.project.get", {"projectIdOrKey": None}),
        ("jira.project.get", {"projectIdOrKey": ["EX"]}),
        ("jira.project.get", {"projectIdOrKey": {"key": "EX"}}),
        ("jira.project.get", {"projectIdOrKey": SENTINEL}),
        ("jira.project.get", {"projectIdOrKey": ""}),
        ("jira.project.get", {"projectIdOrKey": "../EX"}),
        ("jira.project.get", {"projectIdOrKey": ".."}),
        ("jira.project.get", {"projectIdOrKey": "EX/OTHER"}),
        ("jira.project.get", {"projectIdOrKey": "EX\\OTHER"}),
        ("jira.project.get", {"projectIdOrKey": "EX%2FOTHER"}),
        ("jira.project.get", {"projectIdOrKey": "EX?x=1"}),
        ("jira.project.get", {"projectIdOrKey": "EX#fragment"}),
        ("jira.project.get", {"projectIdOrKey": "EX\n"}),
        ("jira.project.get", {"projectIdOrKey": "EX OTHER"}),
        ("jira.project.get", {"projectIdOrKey": "x" * 256}),
        ("jira.issue.watchers", {"issueIdOrKey": "../EX-1"}),
        ("jira.issue.watchers", {"issueIdOrKey": "EX-0"}),
        ("jira.issue.votes", {"issueIdOrKey": "EX-1/other"}),
        ("jira.attachment.get", {"id": "0"}),
        ("jira.attachment.get", {"id": "-1"}),
        ("jira.attachment.get", {"id": "1.5"}),
        ("jira.attachment.get", {"id": "1e3"}),
        ("jira.attachment.get", {"id": "1/2"}),
        ("jira.attachment.get", {"id": "%31"}),
        ("jira.attachment.get", {"id": " 1"}),
        ("jira.attachment.get", {"id": "1 "}),
        ("bitbucket.repository.get", {"projectKey": "PRJ"}),
        (
            "bitbucket.repository.get",
            {"projectKey": "PRJ", "repositorySlug": ".."},
        ),
        (
            "bitbucket.repository.get",
            {"projectKey": "PRJ", "repositorySlug": "widgets/other"},
        ),
        ("confluence.space.get", {"spaceKey": ".."}),
        ("confluence.space.get", {"spaceKey": "%54ST"}),
        (
            "bitbucket.repository.commit-comments",
            {"projectKey": "PRJ", "repositorySlug": "widgets"},
        ),
        (
            "bitbucket.repository.commit-comments",
            {
                "projectKey": "PRJ",
                "repositorySlug": "widgets",
                "commitId": "abc",
            },
        ),
        (
            "bitbucket.repository.commit-comments",
            {
                "projectKey": "PRJ",
                "repositorySlug": "widgets",
                "commitId": "g" * 40,
            },
        ),
        (
            "bitbucket.repository.commit-comments",
            {
                "projectKey": "PRJ",
                "repositorySlug": "widgets",
                "commitId": "../" + COMMIT_ID,
            },
        ),
        (
            "bitbucket.repository.participants",
            {"projectKey": "PRJ"},
        ),
        (
            "bitbucket.repository.pull-request-activity",
            {
                "projectKey": "PRJ",
                "repositorySlug": "widgets",
                "pullRequestId": "0",
            },
        ),
        (
            "bitbucket.repository.pull-request-activity",
            {
                "projectKey": "PRJ",
                "repositorySlug": "widgets",
                "pullRequestId": "-1",
            },
        ),
        (
            "bitbucket.repository.pull-request-activity",
            {
                "projectKey": "PRJ",
                "repositorySlug": "widgets",
                "pullRequestId": "1.5",
            },
        ),
        (
            "bitbucket.repository.pull-request-activity",
            {
                "projectKey": "PRJ",
                "repositorySlug": "widgets",
                "pullRequestId": "7/other",
            },
        ),
        ("bitbucket.task.get", {"taskId": "0"}),
        ("bitbucket.task.get", {"taskId": "-1"}),
        ("bitbucket.task.get", {"taskId": "1.5"}),
        ("bitbucket.task.get", {"taskId": "../99"}),
        ("bitbucket.user.get", {"userSlug": "../jdoe"}),
        ("bitbucket.user.get", {"userSlug": ".hidden"}),
        ("bitbucket.user.get", {"userSlug": "jdoe/other"}),
        ("bitbucket.user.get", {"userSlug": "%6a"}),
        ("bitbucket.profile.recent-repositories", {"extra": "x"}),
        ("bitbucket.users.list", {"extra": "x"}),
        ("jira.mypermissions.get", {"extra": "x"}),
        ("jira.user.get", {"extra": "x"}),
        ("jira.user.assignable-search", {"extra": "x"}),
        ("jira.field.list", {"extra": "x"}),
        ("jira.project.statuses", {}),
        ("jira.project.roles", {"projectIdOrKey": "../EX"}),
        (
            "jira.issue.comment.get",
            {"issueIdOrKey": "EX-1", "id": "0"},
        ),
        (
            "jira.issue.worklog.get",
            {"issueIdOrKey": "EX-1", "id": "0"},
        ),
        ("jira.issue-link.get", {"linkId": "0"}),
        ("jira.jql.autocomplete", {"extra": "x"}),
        ("jira.dashboard.list", {"extra": "x"}),
        ("confluence.content.by-title", {"extra": "x"}),
        ("confluence.content.search", {"extra": "x"}),
        ("confluence.space.content", {"spaceKey": "../TST"}),
        ("confluence.content.properties", {"id": "0"}),
        ("confluence.content.attachments", {"id": "0"}),
        ("confluence.content.children", {"id": "0"}),
        ("confluence.user.get", {"extra": "x"}),
    ],
)
def test_missing_extra_wrong_type_and_traversal_arguments_fail_before_transport(
    monkeypatch: pytest.MonkeyPatch,
    operation_id: str,
    arguments: Mapping[str, object],
) -> None:
    forbid_transport(monkeypatch)

    with pytest.raises(AtlaWireError) as raised:
        read_operation(operation_id, BASE, token=TOKEN, arguments=arguments)

    message = str(raised.value)
    assert (
        "registered path arguments" in message or "path argument is invalid" in message
    )
    assert SENTINEL not in message
    assert "../EX" not in message
    assert "widgets/other" not in message
    assert "\n" not in message


@pytest.mark.parametrize(
    "arguments",
    [
        None,
        [],
        "projectIdOrKey=EX",
        "projectIdOrKey=" + SENTINEL,
        [("projectIdOrKey", "EX")],
    ],
)
def test_non_mapping_arguments_are_rejected(
    monkeypatch: pytest.MonkeyPatch, arguments: object
) -> None:
    forbid_transport(monkeypatch)

    with pytest.raises(AtlaWireError, match="mapping") as raised:
        read_operation(
            "jira.project.get",
            BASE,
            token=TOKEN,
            arguments=cast(Mapping[str, object], arguments),
        )

    assert SENTINEL not in str(raised.value)


@pytest.mark.parametrize(
    ("operation_id", "body"),
    [
        ("jira.project.get", []),
        ("jira.issue.watchers", []),
        ("jira.project.versions", {}),
        ("jira.project.components", {"values": []}),
    ],
)
def test_wrong_top_level_json_kind_is_rejected(
    monkeypatch: pytest.MonkeyPatch, operation_id: str, body: object
) -> None:
    captures = install_transport(monkeypatch, body=body)
    sample = cast(Mapping[str, object], SAMPLES[operation_id])
    expected = (
        "Expected a JSON object."
        if EXPECTED[operation_id]["kind"] == "object"
        else "Expected a JSON array."
    )

    with pytest.raises(AtlaWireError) as raised:
        read_operation(operation_id, BASE, token=TOKEN, arguments=sample)

    assert str(raised.value) == expected
    assert SENTINEL not in str(raised.value)
    assert len(captures) == 1
    assert len(captures[0].calls) == 1
    assert captures[0].mutating == []


@pytest.mark.parametrize(
    ("operation_id", "body"),
    [
        ("jira.attachment.get", {}),
        ("jira.attachment.get", {"filename": "a.txt"}),
        ("jira.attachment.get", {"size": True}),
        ("jira.attachment.get", {"size": "1"}),
        ("jira.issue.watchers", {}),
        ("jira.issue.watchers", {"watchCount": "1"}),
        ("jira.issue.watchers", {"watchCount": 1, "watchers": {}}),
        ("jira.issue.watchers", {"watchCount": 1, "watchers": ["fred"]}),
        ("jira.issue.votes", {"votes": 1}),
        ("jira.issue.votes", {"votes": 1, "hasVoted": "yes"}),
        ("jira.issue.votes", {"votes": 1, "hasVoted": True, "voters": "fred"}),
        ("jira.project.versions", ["not an object"]),
        ("jira.project.versions", [{"id": "1"}, "bad"]),
        ("jira.project.components", [{"id": "1", "name": "ok"}, "bad"]),
        ("jira.project.components", [{"id": "1", "name": "ok"}]),
        ("jira.project.components", [{"isAssigneeTypeValid": "yes"}]),
    ],
)
def test_incorrect_response_fields_publish_nothing(
    monkeypatch: pytest.MonkeyPatch, operation_id: str, body: object
) -> None:
    captures = install_transport(monkeypatch, body=body)
    sample = cast(Mapping[str, object], SAMPLES[operation_id])

    with pytest.raises(AtlaWireError) as raised:
        read_operation(operation_id, BASE, token=TOKEN, arguments=sample)

    message = str(raised.value)
    assert operation_id in message
    assert SENTINEL not in message
    assert len(captures) == 1
    assert len(captures[0].calls) == 1
    assert captures[0].mutating == []


@pytest.mark.parametrize(
    ("operation_id", "arguments", "body"),
    [
        ("jira.project.get", {"projectIdOrKey": "EX"}, {}),
        (
            "jira.project.get",
            {"projectIdOrKey": "EX"},
            {"key": "EX", "name": None},
        ),
        ("jira.attachment.get", {"id": "10001"}, {"size": 1}),
        (
            "jira.attachment.get",
            {"id": "10001"},
            {"size": 1, "filename": None},
        ),
        (
            "jira.project.versions",
            {"projectIdOrKey": "EX"},
            [{"id": "1"}, {"name": None}],
        ),
        (
            "jira.project.components",
            {"projectIdOrKey": "EX"},
            [
                {"isAssigneeTypeValid": False},
                {"id": "1", "name": None, "isAssigneeTypeValid": True},
            ],
        ),
        ("bitbucket.project.get", {"projectKey": "PRJ"}, {"name": "P"}),
        (
            "bitbucket.repository.get",
            {"projectKey": "PRJ", "repositorySlug": "widgets"},
            {"slug": "widgets"},
        ),
        (
            "bitbucket.repository.default-branch",
            {"projectKey": "PRJ", "repositorySlug": "widgets"},
            {"displayId": "master"},
        ),
        ("confluence.space.get", {"spaceKey": "TST"}, {"name": "S"}),
        (
            "jira.issue.watchers",
            {"issueIdOrKey": "EX-1"},
            {"watchCount": 0, "isWatching": None},
        ),
        (
            "jira.issue.votes",
            {"issueIdOrKey": "EX-1"},
            {"votes": 0, "hasVoted": False, "voters": None},
        ),
    ],
)
def test_documented_optional_and_nullable_fields_are_preserved_raw(
    monkeypatch: pytest.MonkeyPatch,
    operation_id: str,
    arguments: Mapping[str, object],
    body: object,
) -> None:
    install_transport(monkeypatch, body=body)

    assert read_operation(operation_id, BASE, token=TOKEN, arguments=arguments) == body


def test_default_branch_204_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captures = install_transport(monkeypatch, body=b"", status=204)

    result = read_operation(
        "bitbucket.repository.default-branch",
        BASE,
        token=TOKEN,
        arguments={"projectKey": "PRJ", "repositorySlug": "widgets"},
    )

    assert result is None
    assert len(captures) == 1
    assert len(captures[0].calls) == 1
    assert captures[0].calls[0][1]["params"] == {}
    assert captures[0].session.headers["Authorization"] == f"Bearer {TOKEN}"


@pytest.mark.parametrize(
    ("body", "message"),
    [
        (b"null", "Expected a JSON object."),
        (b"", "Expected a valid JSON response."),
        (b"{", "Expected a valid JSON response."),
    ],
)
def test_default_branch_200_null_empty_or_malformed_json_is_an_error(
    monkeypatch: pytest.MonkeyPatch, body: bytes, message: str
) -> None:
    install_transport(monkeypatch, body=body, status=200)

    with pytest.raises(AtlaWireError) as raised:
        read_operation(
            "bitbucket.repository.default-branch",
            BASE,
            token=TOKEN,
            arguments={"projectKey": "PRJ", "repositorySlug": "widgets"},
        )

    assert str(raised.value) == message


def test_204_is_rejected_for_operations_that_do_not_document_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_transport(monkeypatch, body=b"", status=204)

    with pytest.raises(AtlaWireError, match="valid JSON response"):
        read_operation(
            "jira.project.get",
            BASE,
            token=TOKEN,
            arguments={"projectIdOrKey": "EX"},
        )


@pytest.mark.parametrize(
    "base_url",
    [
        "http://atlassian.example",
        "https://user:password@atlassian.example",
        "https://atlassian.example?query=1",
        "https://atlassian.example#fragment",
        "https://atlassian.example\\evil",
    ],
)
def test_invalid_destinations_fail_before_transport(
    monkeypatch: pytest.MonkeyPatch, base_url: str
) -> None:
    forbid_transport(monkeypatch)

    with pytest.raises(AtlaWireError) as raised:
        read_operation(
            "jira.project.get",
            base_url,
            token=TOKEN,
            arguments={"projectIdOrKey": "EX"},
        )

    assert "HTTPS base URL" in str(raised.value)
    assert TOKEN not in str(raised.value)


def test_loopback_http_requires_explicit_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captures = install_transport(monkeypatch, body=BODIES["jira.project.get"])

    read_operation(
        "jira.project.get",
        "http://127.0.0.1:8080",
        token=TOKEN,
        arguments={"projectIdOrKey": "EX"},
        allow_http_loopback=True,
    )

    assert captures[0].calls[0][0] == ("http://127.0.0.1:8080/rest/api/2/project/EX")


@pytest.mark.parametrize("token", ["", "not a token", "тест"])
def test_invalid_tokens_fail_before_transport(token: str) -> None:
    with pytest.raises(AtlaWireError, match="bearer token"):
        read_operation(
            "jira.project.get",
            BASE,
            token=token,
            arguments={"projectIdOrKey": "EX"},
        )


def test_non_string_token_is_rejected_before_transport() -> None:
    with pytest.raises(AtlaWireError, match="bearer token"):
        read_operation(
            "jira.project.get",
            BASE,
            token=cast(str, 123),
            arguments={"projectIdOrKey": "EX"},
        )


def test_transport_failure_does_not_echo_token_target_arguments_or_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = json.dumps({"message": SENTINEL, "token": TOKEN}).encode()
    install_transport(monkeypatch, body=body, status=500)

    with pytest.raises(AtlaWireError) as raised:
        read_operation(
            "jira.project.get",
            BASE,
            token=TOKEN,
            arguments={"projectIdOrKey": "ARGSENTINEL9D9"},
        )

    message = str(raised.value)
    assert "HTTP 500" in message
    for detail in (
        TOKEN,
        SENTINEL,
        "ARGSENTINEL9D9",
        "atlassian.example",
        "/rest/api/2/project",
    ):
        assert detail not in message
