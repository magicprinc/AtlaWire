"""Discover live identifiers so registered operations can be called for real.

Every probe is one read-only GET through the public reader. Nothing is printed
except the identifiers themselves, which are names, keys, and numeric ids — never
a token, a base URL host, or a response body.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from atlawire.credentials import load_saved_credentials  # noqa: E402
from atlawire.http import AtlaWireError  # noqa: E402
from atlawire.sdk import get_json  # noqa: E402

PRODUCTS = ("jira", "confluence", "bitbucket")


def pair(product: str):
    return load_saved_credentials(product, allow_http_loopback=False)


def fetch(product: str, path: str, params: dict[str, object] | None = None):
    saved = pair(product)
    try:
        return get_json(
            product,
            saved.base_url,
            path,
            token=saved.token,
            params=params or {},
        )
    except AtlaWireError as exc:
        print(f"  ! {product} {path} -> {exc.category} {exc.http_status}", file=sys.stderr)
        return None


def discover() -> dict[str, object]:
    ids: dict[str, object] = {}

    # --- Jira -------------------------------------------------------------
    me = fetch("jira", "/rest/api/2/myself")
    if isinstance(me, dict):
        ids["jira_user"] = me.get("name") or me.get("key")

    project = fetch("jira", "/rest/api/2/project")
    if isinstance(project, list) and project:
        ids["jira_project_key"] = project[0].get("key")
        versions = fetch("jira", f"/rest/api/2/project/{ids['jira_project_key']}/versions")
        if isinstance(versions, list) and versions:
            ids["jira_version_id"] = versions[0].get("id")
        components = fetch(
            "jira", f"/rest/api/2/project/{ids['jira_project_key']}/components"
        )
        if isinstance(components, list) and components:
            ids["jira_component_id"] = components[0].get("id")

    search = fetch(
        "jira",
        "/rest/api/2/search",
        {"jql": "order by created DESC", "maxResults": 1},
    )
    if isinstance(search, dict):
        issues = search.get("issues") or []
        if issues:
            ids["jira_issue_key"] = issues[0].get("key")
            key = ids["jira_issue_key"]
            comments = fetch("jira", f"/rest/api/2/issue/{key}/comment")
            if isinstance(comments, dict):
                entries = comments.get("comments") or []
                if entries:
                    ids["jira_comment_id"] = entries[0].get("id")
            worklogs = fetch("jira", f"/rest/api/2/issue/{key}/worklog")
            if isinstance(worklogs, dict):
                entries = worklogs.get("worklogs") or []
                if entries:
                    ids["jira_worklog_id"] = entries[0].get("id")

    # An issue with comments is more useful than the newest issue: several
    # operations need a comment id. This deployment rejects
    # `comment is not EMPTY` (the field does not support EMPTY), so probe the
    # comments of a small page of issues instead of relying on a JQL predicate.
    if "jira_comment_id" not in ids:
        recent = fetch(
            "jira",
            "/rest/api/2/search",
            {"jql": "created is not EMPTY order by created DESC", "maxResults": 10},
        )
        if isinstance(recent, dict):
            for issue in recent.get("issues") or []:
                key = issue.get("key")
                if not key:
                    continue
                comments = fetch("jira", f"/rest/api/2/issue/{key}/comment")
                if isinstance(comments, dict):
                    entries = comments.get("comments") or []
                    if entries:
                        ids["jira_issue_with_comments"] = key
                        ids["jira_comment_id"] = entries[0].get("id")
                        break

    fields = fetch("jira", "/rest/api/2/field")
    if isinstance(fields, list) and fields:
        ids["jira_field_id"] = fields[0].get("id")
        priority_field = next(
            (f for f in fields if f.get("id") == "priority"), None
        )
        if priority_field:
            ids["jira_field_id"] = "priority"

    # Several attachment routes take an attachment id. Read one issue's
    # attachment list rather than guessing an id.
    probe_key = ids.get("jira_issue_with_comments") or ids.get("jira_issue_key")
    if probe_key:
        issue = fetch(
            "jira",
            f"/rest/api/2/issue/{probe_key}",
            {"fields": "attachment"},
        )
        if isinstance(issue, dict):
            attachments = ((issue.get("fields") or {}).get("attachment")) or []
            if attachments:
                ids["jira_attachment_id"] = attachments[0].get("id")

    issue_types = fetch("jira", "/rest/api/2/issuetype")
    if isinstance(issue_types, list) and issue_types:
        ids["jira_issue_type_id"] = issue_types[0].get("id")

    statuses = fetch("jira", "/rest/api/2/status")
    if isinstance(statuses, list) and statuses:
        ids["jira_status_id"] = statuses[0].get("id")

    # --- Confluence -------------------------------------------------------
    spaces = fetch("confluence", "/rest/api/space", {"limit": 1})
    if isinstance(spaces, dict):
        results = spaces.get("results") or []
        if results:
            ids["confluence_space_key"] = results[0].get("key")

    if "confluence_space_key" in ids:
        content = fetch(
            "confluence",
            "/rest/api/content",
            {"spaceKey": ids["confluence_space_key"], "limit": 1},
        )
        if isinstance(content, dict):
            results = content.get("results") or []
            if results:
                page = results[0]
                ids["confluence_page_id"] = page.get("id")
                ids["confluence_content_type"] = page.get("type") or "page"
                page_id = ids["confluence_page_id"]
                comments = fetch(
                    "confluence", f"/rest/api/content/{page_id}/child/comment", {"limit": 1}
                )
                if isinstance(comments, dict):
                    entries = comments.get("results") or []
                    if entries:
                        ids["confluence_comment_id"] = entries[0].get("id")
                attachments = fetch(
                    "confluence",
                    f"/rest/api/content/{page_id}/child/attachment",
                    {"limit": 1},
                )
                if isinstance(attachments, dict):
                    entries = attachments.get("results") or []
                    if entries:
                        ids["confluence_attachment_id"] = entries[0].get("id")

    # --- Bitbucket --------------------------------------------------------
    projects = fetch("bitbucket", "/rest/api/1.0/projects", {"limit": 1})
    if isinstance(projects, dict):
        values = projects.get("values") or []
        if values:
            ids["bitbucket_project_key"] = values[0].get("key")

    users = fetch("bitbucket", "/rest/api/1.0/users", {"limit": 1})
    if isinstance(users, dict):
        values = users.get("values") or []
        if values:
            ids["bitbucket_user_slug"] = values[0].get("slug") or values[0].get(
                "name"
            )

    if "bitbucket_project_key" in ids:
        project_key = ids["bitbucket_project_key"]
        repos = fetch(
            "bitbucket", f"/rest/api/1.0/projects/{project_key}/repos", {"limit": 1}
        )
        if isinstance(repos, dict):
            values = repos.get("values") or []
            if values:
                ids["bitbucket_repository_slug"] = values[0].get("slug")

    # A repository without pull requests cannot exercise the PR operations, so
    # prefer one that has them when the first choice has none.
    candidates = []
    all_projects = fetch("bitbucket", "/rest/api/1.0/projects", {"limit": 10})
    if isinstance(all_projects, dict):
        candidates.extend(
            (item.get("key"), None) for item in all_projects.get("values") or []
        )
    if "bitbucket_project_key" in ids:
        candidates.insert(0, (ids["bitbucket_project_key"], None))

    for project_key, _ in candidates[:6]:
        if not project_key:
            continue
        repo_list = fetch(
            "bitbucket", f"/rest/api/1.0/projects/{project_key}/repos", {"limit": 10}
        )
        if not isinstance(repo_list, dict):
            continue
        for repo in repo_list.get("values") or []:
            slug = repo.get("slug")
            if not slug:
                continue
            base = f"/rest/api/1.0/projects/{project_key}/repos/{slug}"
            # The default state is OPEN; a finished repository holds only
            # merged or declined pull requests, so ask for every state.
            pulls = fetch(
                "bitbucket", f"{base}/pull-requests", {"limit": 1, "state": "ALL"}
            )
            if not isinstance(pulls, dict):
                continue
            values = pulls.get("values") or []
            if values:
                ids["bitbucket_project_key"] = project_key
                ids["bitbucket_repository_slug"] = slug
                ids["bitbucket_pull_request_id"] = values[0].get("id")
                ids["bitbucket_pull_request_from"] = (
                    (values[0].get("fromRef") or {}).get("id")
                )
                ids["bitbucket_pull_request_to"] = (
                    (values[0].get("toRef") or {}).get("id")
                )
                break
        if "bitbucket_pull_request_id" in ids:
            break

    if "bitbucket_repository_slug" in ids:
        base = (
            f"/rest/api/1.0/projects/{ids['bitbucket_project_key']}"
            f"/repos/{ids['bitbucket_repository_slug']}"
        )
        pulls = fetch("bitbucket", f"{base}/pull-requests", {"limit": 1})
        if isinstance(pulls, dict):
            values = pulls.get("values") or []
            if values:
                ids["bitbucket_pull_request_id"] = values[0].get("id")
        commits = fetch("bitbucket", f"{base}/commits", {"limit": 1})
        if isinstance(commits, dict):
            values = commits.get("values") or []
            if values:
                ids["bitbucket_commit_id"] = values[0].get("id")
        branches = fetch("bitbucket", f"{base}/branches", {"limit": 1})
        if isinstance(branches, dict):
            values = branches.get("values") or []
            if values:
                ids["bitbucket_branch"] = values[0].get("id")
        tags = fetch("bitbucket", f"{base}/tags", {"limit": 1})
        if isinstance(tags, dict):
            values = tags.get("values") or []
            if values:
                ids["bitbucket_tag"] = values[0].get("id")
        files = fetch("bitbucket", f"{base}/files", {"limit": 1})
        if isinstance(files, dict):
            values = files.get("values") or []
            if values:
                first = values[0]
                ids["bitbucket_file_path"] = (
                    first.get("path") if isinstance(first, dict) else first
                )

    return ids


if __name__ == "__main__":
    discovered = discover()
    print(json.dumps(discovered, indent=2, sort_keys=True))
    print(f"\ndiscovered {len(discovered)} identifiers", file=sys.stderr)
