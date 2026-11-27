"""Call every public Python reader with discovered identifiers, as a library user would.

Records successes, failures, and functions that cannot be called without a value
this deployment does not have. This is the Python API surface, tested separately
from the CLI.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(r"D:\REPO\github\AtlaWire\src")))
sys.path.insert(0, str(Path(r"D:\REPO\github\AtlaWire\checks")))

from live_tester_discovery import discover

from atlawire import (
    bitbucket,
    confluence,
    jira,
)
from atlawire.credentials import load_saved_credentials
from atlawire.http import AtlaWireError

pool = discover()
saved = {
    product: load_saved_credentials(product, allow_http_loopback=False)
    for product in ("jira", "confluence", "bitbucket")
}

REPO = f"{pool.get('bitbucket_project_key')}/{pool.get('bitbucket_repository_slug')}"

# Explicit calls: one representative, working invocation per function.
CASES: list[tuple[str, str, object]] = [
    # jira
    ("jira", "get_current_user", lambda u, t: jira.get_current_user(u, token=t)),
    (
        "jira",
        "get_issue",
        lambda u, t: jira.get_issue(u, str(pool.get("jira_issue_key")), token=t),
    ),
    (
        "jira",
        "list_issue_comments",
        lambda u, t: jira.list_issue_comments(
            u, str(pool.get("jira_issue_key")), token=t
        ),
    ),
    (
        "jira",
        "get_issue_watchers",
        lambda u, t: jira.get_issue_watchers(
            u, str(pool.get("jira_issue_key")), token=t
        ),
    ),
    (
        "jira",
        "list_issue_worklogs",
        lambda u, t: jira.list_issue_worklogs(
            u, str(pool.get("jira_issue_key")), token=t
        ),
    ),
    (
        "jira",
        "get_issue_changelog",
        lambda u, t: jira.get_issue_changelog(
            u, str(pool.get("jira_issue_key")), token=t
        ),
    ),
    ("jira", "list_jira_projects", lambda u, t: jira.list_jira_projects(u, token=t)),
    ("jira", "list_priorities", lambda u, t: jira.list_priorities(u, token=t)),
    ("jira", "list_statuses", lambda u, t: jira.list_statuses(u, token=t)),
    ("jira", "list_issue_types", lambda u, t: jira.list_issue_types(u, token=t)),
    ("jira", "search_users", lambda u, t: jira.search_users(u, "a", token=t)),
    (
        "jira",
        "list_transitions",
        lambda u, t: jira.list_transitions(u, str(pool.get("jira_issue_key")), token=t),
    ),
    (
        "jira",
        "titles",
        lambda u, t: jira.titles(u, [str(pool.get("jira_issue_key"))], token=t),
    ),
    (
        "jira",
        "issue_url",
        lambda u, t: jira.issue_url(u, str(pool.get("jira_issue_key"))),
    ),
    (
        "jira",
        "search_all_issues",
        lambda u, t: jira.search_all_issues(
            u, "order by created DESC", token=t, limit=1
        ),
    ),
    (
        "jira",
        "search_issues",
        lambda u, t: jira.search_issues(u, "order by created DESC", token=t, limit=1),
    ),
    # confluence
    (
        "confluence",
        "list_spaces",
        lambda u, t: confluence.list_spaces(u, token=t, limit=1),
    ),
    (
        "confluence",
        "get_page",
        lambda u, t: confluence.get_page(
            u, str(pool.get("confluence_page_id")), token=t
        ),
    ),
    (
        "confluence",
        "get_page_markdown",
        lambda u, t: confluence.get_page_markdown(
            u, str(pool.get("confluence_page_id")), token=t
        ),
    ),
    (
        "confluence",
        "get_page_storage",
        lambda u, t: confluence.get_page_storage(
            u, str(pool.get("confluence_page_id")), token=t
        ),
    ),
    (
        "confluence",
        "get_page_title",
        lambda u, t: confluence.get_page_title(
            u, str(pool.get("confluence_page_id")), token=t
        ),
    ),
    (
        "confluence",
        "get_page_web_url",
        lambda u, t: confluence.get_page_web_url(
            u, str(pool.get("confluence_page_id")), token=t
        ),
    ),
    (
        "confluence",
        "list_children",
        lambda u, t: confluence.list_children(
            u, str(pool.get("confluence_page_id")), token=t
        ),
    ),
    (
        "confluence",
        "page_id",
        lambda u, t: confluence.page_id(
            u, str(pool.get("confluence_page_id")), token=t
        ),
    ),
    # bitbucket
    (
        "bitbucket",
        "list_projects",
        lambda u, t: bitbucket.list_projects(u, token=t, limit=1),
    ),
    (
        "bitbucket",
        "list_repositories",
        lambda u, t: bitbucket.list_repositories(
            u, str(pool.get("bitbucket_project_key")), token=t, limit=1
        ),
    ),
    (
        "bitbucket",
        "get_repository",
        lambda u, t: bitbucket.get_repository(u, REPO, token=t),
    ),
    (
        "bitbucket",
        "get_pull_request",
        lambda u, t: bitbucket.get_pull_request(
            u, REPO, pool.get("bitbucket_pull_request_id"), token=t
        ),
    ),
    (
        "bitbucket",
        "list_pull_request_files",
        lambda u, t: bitbucket.list_pull_request_files(
            u, REPO, pool.get("bitbucket_pull_request_id"), token=t
        ),
    ),
    (
        "bitbucket",
        "list_pull_request_comments",
        lambda u, t: bitbucket.list_pull_request_comments(
            u, REPO, pool.get("bitbucket_pull_request_id"), token=t
        ),
    ),
    (
        "bitbucket",
        "list_pull_request_commits",
        lambda u, t: bitbucket.list_pull_request_commits(
            u, REPO, pool.get("bitbucket_pull_request_id"), token=t
        ),
    ),
    (
        "bitbucket",
        "get_pull_request_merge_status",
        lambda u, t: bitbucket.get_pull_request_merge_status(
            u, "BCHAT/business-chat-api", 1231, token=t
        ),
    ),
    (
        "bitbucket",
        "get_repository_file",
        lambda u, t: bitbucket.get_repository_file(
            u, REPO, str(pool.get("bitbucket_file_path")), token=t
        ),
    ),
    (
        "bitbucket",
        "list_repository_files",
        lambda u, t: bitbucket.list_repository_files(u, REPO, token=t),
    ),
    (
        "bitbucket",
        "list_branches",
        lambda u, t: bitbucket.list_branches(u, REPO, token=t, limit=1),
    ),
    (
        "bitbucket",
        "list_commits",
        lambda u, t: bitbucket.list_commits(u, REPO, token=t, limit=1),
    ),
    (
        "bitbucket",
        "get_commit",
        lambda u, t: bitbucket.get_commit(
            u, REPO, str(pool.get("bitbucket_commit_id")), token=t
        ),
    ),
    (
        "bitbucket",
        "list_tags",
        lambda u, t: bitbucket.list_tags(u, REPO, token=t, limit=1),
    ),
    (
        "bitbucket",
        "get_default_branch",
        lambda u, t: bitbucket.get_default_branch(
            u,
            str(pool.get("bitbucket_project_key")),
            str(pool.get("bitbucket_repository_slug")),
            token=t,
        ),
    ),
    (
        "bitbucket",
        "list_directory",
        lambda u, t: bitbucket.list_directory(u, REPO, token=t),
    ),
    (
        "bitbucket",
        "find_repositories",
        lambda u, t: bitbucket.find_repositories(u, "address", token=t),
    ),
]

results = []
for product, name, call in CASES:
    base = saved[product].base_url
    token = saved[product].token
    module = {"jira": jira, "confluence": confluence, "bitbucket": bitbucket}[product]
    if not hasattr(module, name):
        results.append({"product": product, "function": name, "outcome": "absent"})
        continue
    try:
        value = call(base, token)
        size = len(value) if hasattr(value, "__len__") else "?"
        results.append(
            {"product": product, "function": name, "outcome": "ok", "size": size}
        )
    except AtlaWireError as exc:
        results.append(
            {
                "product": product,
                "function": name,
                "outcome": "failed",
                "category": exc.category,
                "status": exc.http_status,
                "detail": (exc.detail or "")[:150],
            }
        )
    except TypeError as exc:
        results.append(
            {
                "product": product,
                "function": name,
                "outcome": "signature-mismatch",
                "detail": str(exc)[:150],
            }
        )

summary = Counter(record["outcome"] for record in results)
print("summary:", dict(summary))
for record in results:
    if record["outcome"] != "ok":
        print(
            f"  {record['outcome']:18} {record['product']:11} {record['function']:30} "
            f"{record.get('detail') or ''}"
        )

out = Path(r"D:\REPO\github\AtlaWire\checks\live_tester_python_api.json")
out.write_text(json.dumps(results, indent=2), encoding="utf-8")
print("\nwritten:", out)
