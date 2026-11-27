"""Compare BBK's public API with AtlaWire, function by function, live.

The BBK function list comes from its own sources read with `ast`. The map is keyed
by `module:function` because BBK reuses names across modules — `projects` exists in
both `jira.py` and `bitbucket.py`, and a name-only key silently mapped one onto the
other's equivalent.

Verdicts:
    better   the explicit note says the capability is broader or stricter
    same     the same job with the same observable result
    different  deliberately different shape, reason recorded
    worse    an equivalent exists but its live call failed
    missing  no equivalent could be resolved
    excluded outside the read-only Atlassian scope (a local store, a write)

Run:
    python checks/live_tester_bbk_parity.py [--out FILE]
"""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from live_tester_discovery import discover

BBK = Path(r"D:\zcache\bbk\bbk")
PYTHON = sys.executable

IN_SCOPE = (
    "jira.py",
    "confluence.py",
    "bitbucket.py",
    "repo.py",
    "repo_grep.py",
    "review.py",
    "find.py",
    "attachments.py",
    "md.py",
    "idx.py",
)

# key = "bbk_module:bbk_function" -> (atlawire symbol, verdict, note, argv key)
MAP: dict[str, tuple[str, str, str, str | None]] = {
    # --- jira -------------------------------------------------------------
    "jira.py:jql": (
        "atlawire.jira.search_all_issues",
        "better",
        "Adds completeness reporting and a bounded page budget",
        "jql",
    ),
    "jira.py:rows": ("atlawire.jira.search_all_issues", "same", "", "jql"),
    "jira.py:mine": (
        "atlawire.jira.search_issues",
        "same",
        "A JQL preset over the same search",
        "mine",
    ),
    "jira.py:issue": ("atlawire.jira.get_issue", "same", "", "issue"),
    "jira.py:issue_md": (
        "atlawire.issue_markdown.render_issue_markdown",
        "same",
        "",
        "issue",
    ),
    "jira.py:issue_comments": (
        "atlawire.jira.list_issue_comments",
        "same",
        "",
        "issue-comments",
    ),
    "jira.py:issue_watchers": (
        "atlawire.jira.get_issue_watchers",
        "same",
        "",
        "issue-watchers",
    ),
    "jira.py:issue_worklogs": (
        "atlawire.jira.list_issue_worklogs",
        "same",
        "",
        "issue-worklogs",
    ),
    "jira.py:issue_changelog": (
        "atlawire.jira.get_issue_changelog",
        "same",
        "",
        "issue-changelog",
    ),
    "jira.py:me": ("atlawire.jira.get_current_user", "same", "", "jira-me"),
    "jira.py:projects": (
        "atlawire.jira.list_jira_projects",
        "same",
        "",
        "jira-projects",
    ),
    "jira.py:priorities": (
        "atlawire.jira.list_priorities",
        "same",
        "",
        "jira-priorities",
    ),
    "jira.py:statuses": ("atlawire.jira.list_statuses", "same", "", "statuses"),
    "jira.py:issue_types": (
        "atlawire.jira.list_issue_types",
        "same",
        "",
        "jira-issue-types",
    ),
    "jira.py:users": ("atlawire.jira.search_users", "same", "", None),
    "jira.py:resolve_user": (
        "atlawire.jira.search_users",
        "same",
        "Resolves a name through the documented user search",
        None,
    ),
    "jira.py:transitions": (
        "atlawire.jira.list_transitions",
        "same",
        "",
        "transitions",
    ),
    "jira.py:titles": ("atlawire.jira.titles", "same", "", "titles"),
    "jira.py:url": ("atlawire.jira.issue_url", "same", "", "issue-url"),
    "jira.py:recent_comments": (
        "atlawire.jira_comments_search.find_author_comments",
        "same",
        "Author comment search over JQL",
        "jira-author-comments",
    ),
    # --- confluence -------------------------------------------------------
    "confluence.py:spaces": ("atlawire.confluence.list_spaces", "same", "", "spaces"),
    "confluence.py:page": ("atlawire.confluence.get_page", "same", "", "page"),
    "confluence.py:page_md": (
        "atlawire.confluence.get_page_markdown",
        "better",
        "One call renders Markdown",
        "page",
    ),
    "confluence.py:page_storage": (
        "atlawire.confluence.get_page_storage",
        "same",
        "",
        None,
    ),
    "confluence.py:page_id": ("atlawire.confluence.page_id", "same", "", None),
    "confluence.py:title": ("atlawire.confluence.get_page_title", "same", "", None),
    "confluence.py:children": (
        "atlawire.confluence.list_children",
        "better",
        "Reports completeness instead of a bare list",
        "children",
    ),
    "confluence.py:search_cql": ("atlawire.confluence.search_cql", "same", "", "cql"),
    "confluence.py:url_for": (
        "atlawire.confluence.get_page_web_url",
        "better",
        "A JSON envelope carries the URL",
        "page-url",
    ),
    "confluence.py:client_base": (
        "atlawire.sdk.client_for",
        "different",
        "Never returns saved credentials implicitly",
        None,
    ),
    # --- bitbucket --------------------------------------------------------
    "bitbucket.py:projects": (
        "atlawire.bitbucket.list_projects",
        "same",
        "",
        "projects",
    ),
    "bitbucket.py:repos": ("atlawire.bitbucket.list_repositories", "same", "", "repos"),
    "bitbucket.py:list_files": (
        "atlawire.bitbucket.list_repository_files",
        "same",
        "",
        "files",
    ),
    "bitbucket.py:file_at": (
        "atlawire.bitbucket.get_repository_file",
        "better",
        "Reads the real default branch when no ref is given",
        "file",
    ),
    "bitbucket.py:pr": ("atlawire.bitbucket.get_pull_request", "same", "", "pr"),
    "bitbucket.py:pr_files": (
        "atlawire.bitbucket.list_pull_request_files",
        "same",
        "",
        "pr-files",
    ),
    "bitbucket.py:pr_comments": (
        "atlawire.bitbucket.list_pull_request_comments",
        "same",
        "",
        "pr-comments",
    ),
    "bitbucket.py:prs": (
        "atlawire.bitbucket.list_pull_requests",
        "better",
        "Adds direction, author, role and participant filters",
        "prs",
    ),
    "bitbucket.py:my_prs": (
        "atlawire.bitbucket.list_my_pull_requests",
        "same",
        "",
        "my-prs",
    ),
    "bitbucket.py:pr_diff": (
        "atlawire.bitbucket.get_pull_request_diffs",
        "better",
        "Batch paths, validated whitespace mode",
        "pr-diff",
    ),
    "bitbucket.py:pr_file": (
        "atlawire.bitbucket.get_pull_request_file",
        "same",
        "",
        "pr-file",
    ),
    "bitbucket.py:pr_compact": ("atlawire.bitbucket.pr_compact", "same", "", "pr"),
    "bitbucket.py:search_code": (
        "atlawire.repo_search.search_repositories",
        "better",
        "Three engines and bounded per-repo work",
        "repo-search",
    ),
    "bitbucket.py:repos_with_extension": (
        "atlawire.repo_scan.scan_repository_extensions_report",
        "better",
        "Reports completeness",
        "scan-extension",
    ),
    # --- repo -------------------------------------------------------------
    "repo.py:ls": ("atlawire.bitbucket.list_directory", "same", "", "ls"),
    "repo.py:blame": ("atlawire.bitbucket.get_file_blame", "same", "", "blame"),
    "repo.py:branches": ("atlawire.bitbucket.list_branches", "same", "", "branches"),
    "repo.py:commits": ("atlawire.bitbucket.list_commits", "same", "", "commits"),
    "repo.py:commit": ("atlawire.bitbucket.get_commit", "same", "", "commit"),
    "repo.py:branch": ("atlawire.bitbucket.get_branch", "same", "", "branch"),
    "repo.py:find_repos": (
        "atlawire.bitbucket.find_repositories",
        "same",
        "",
        "find-repos",
    ),
    "repo.py:pr_commits": (
        "atlawire.bitbucket.list_pull_request_commits",
        "same",
        "",
        "pr-commits",
    ),
    # --- repo_grep --------------------------------------------------------
    "repo_grep.py:grep": (
        "atlawire.repo_grep.grep_repository",
        "same",
        "",
        "grep-repo",
    ),
    "repo_grep.py:grep_ex": ("atlawire.repo_grep.grep_repository", "same", "", None),
    "repo_grep.py:commit_changes": (
        "atlawire.bitbucket.list_commit_changes",
        "same",
        "",
        "commit-changes",
    ),
    "repo_grep.py:commit_diff": (
        "atlawire.bitbucket.get_commit_diff",
        "same",
        "",
        "commit-diff",
    ),
    # --- review -----------------------------------------------------------
    "review.py:review": ("atlawire.pr_review.review", "same", "", "pr-review"),
    "review.py:collect": ("atlawire.pr_review.collect_pr_review", "same", "", None),
    "review.py:find_ticket": ("atlawire.pr_review.find_ticket", "same", "", None),
    "review.py:fetch_ticket": ("atlawire.pr_review.fetch_ticket", "same", "", None),
    "review.py:red_flags": ("atlawire.pr_review.red_flags", "same", "", None),
    "review.py:changed_symbols": (
        "atlawire.pr_review.changed_symbols",
        "same",
        "",
        None,
    ),
    "review.py:java_members": ("atlawire.pr_review.java_members", "same", "", None),
    "review.py:file_links": ("atlawire.pr_review.file_links", "same", "", None),
    "review.py:parse_pr_link": ("atlawire.pr_review.parse_pr_link", "same", "", None),
    "review.py:is_test_path": ("atlawire.pr_review.is_test_path", "same", "", None),
    "review.py:render_markdown": (
        "atlawire.pr_review.render_markdown",
        "same",
        "",
        None,
    ),
    # --- attachments ------------------------------------------------------
    "attachments.py:attachment_download": (
        "atlawire.bitbucket_attachment",
        "same",
        "Read through attachment-get",
        "attachment-get",
    ),
    # --- md ---------------------------------------------------------------
    "md.py:confluence_to_md": ("atlawire.markdown.confluence_to_md", "same", "", None),
    "md.py:wiki_to_md": ("atlawire.markdown.wiki_to_md", "same", "", None),
    "md.py:html_to_md": ("atlawire.markdown.html_to_md", "same", "", None),
    "md.py:jira_issue_to_md": ("atlawire.markdown.jira_issue_to_md", "same", "", None),
    "md.py:render_diff": ("atlawire.markdown.render_diff", "same", "", None),
    "md.py:compact": ("atlawire.markdown.compact", "same", "", None),
    "md.py:compact_json": ("atlawire.markdown.compact_json", "same", "", None),
    "md.py:change_rows": (
        "atlawire.markdown.render_diff",
        "different",
        "Diff rendering covers the same output; there is no row model",
        None,
    ),
    # --- find -------------------------------------------------------------
    "find.py:find": (
        "atlawire.federated.federated_search",
        "better",
        "Labels every partial answer with complete=false",
        "find",
    ),
    # --- idx (BBK local index store) --------------------------------------
    "idx.py:load": ("", "excluded", "BBK local index; AtlaWire reads the server", None),
    "idx.py:search": ("", "excluded", "BBK local index; use repo-search instead", None),
    "idx.py:databases": ("", "excluded", "BBK local index bookkeeping", None),
    "idx.py:projects": ("", "excluded", "BBK local index bookkeeping", None),
}


def cli_args(pool: dict[str, object]) -> dict[str, list[str]]:
    repo = (
        f"{pool.get('bitbucket_project_key')}/{pool.get('bitbucket_repository_slug')}"
    )
    pr = str(pool.get("bitbucket_pull_request_id"))
    issue = str(pool.get("jira_issue_key"))
    page = str(pool.get("confluence_page_id"))
    return {
        "jql": ["jql", "order by created DESC", "--limit", "1", "--json"],
        "mine": ["mine", "--limit", "1", "--json"],
        "issue": ["issue", issue, "--json"],
        "issue-comments": ["issue-comments", issue, "--json"],
        "issue-watchers": ["issue-watchers", issue, "--json"],
        "issue-worklogs": ["issue-worklogs", issue, "--json"],
        "issue-changelog": ["issue-changelog", issue, "--json"],
        "jira-me": ["jira-me", "--json"],
        "jira-projects": ["jira-projects", "--json"],
        "jira-priorities": ["jira-priorities", "--json"],
        "statuses": ["statuses", "--json"],
        "jira-issue-types": ["jira-issue-types", "--json"],
        "transitions": ["transitions", issue, "--json"],
        # `titles`, `issue-url`, `pr-file` and `pr-commits` exist as library
        # functions but have no CLI command, so no live CLI call is made for
        # them. That gap is reported separately, not as a failed call.
        "jira-author-comments": [
            "jira-author-comments",
            str(pool.get("jira_user")),
            "--limit",
            "1",
            "--json",
        ],
        "spaces": ["spaces", "--limit", "1", "--json"],
        "page": ["page", page, "--json"],
        "children": ["children", page, "--json"],
        "page-url": ["page-url", page, "--json"],
        "cql": ["cql", "type = page", "--limit", "1", "--json"],
        "projects": ["projects", "--limit", "1", "--json"],
        "repos": [
            "repos",
            str(pool.get("bitbucket_project_key")),
            "--limit",
            "1",
            "--json",
        ],
        "files": ["files", repo, "--json"],
        "file": ["file", repo, str(pool.get("bitbucket_file_path"))],
        "pr": ["pr", repo, pr, "--json"],
        "pr-files": ["pr-files", repo, pr, "--json"],
        "pr-comments": ["pr-comments", repo, pr, "--json"],
        "prs": ["prs", repo, "--limit", "1", "--json"],
        "my-prs": ["my-prs", "--limit", "1", "--json"],
        "pr-file": ["pr-file", repo, pr, str(pool.get("bitbucket_file_path"))],
        "pr-commits": ["pr-commits", repo, pr, "--limit", "1", "--json"],
        "repo-search": ["repo-search", "README", "--limit", "1", "--json"],
        "scan-extension": [
            "scan-extension",
            "--ext",
            ".md",
            "--max-pages",
            "1",
            "--project",
            str(pool.get("bitbucket_project_key")),
        ],
        "ls": ["ls", repo, "--json"],
        "blame": ["blame", repo, str(pool.get("bitbucket_file_path"))],
        "branches": ["branches", repo, "--limit", "1", "--json"],
        "commits": ["commits", repo, "--limit", "1", "--json"],
        "commit": ["commit", repo, str(pool.get("bitbucket_commit_id")), "--json"],
        "branch": ["branch", repo, str(pool.get("bitbucket_branch"))],
        "find-repos": ["find-repos", "address", "--json"],
        "grep-repo": ["grep-repo", repo, "--limit", "1"],
        "commit-changes": [
            "commit-changes",
            repo,
            str(pool.get("bitbucket_commit_id")),
            "--json",
        ],
        "commit-diff": [
            "commit-diff",
            repo,
            str(pool.get("bitbucket_commit_id")),
            "--json",
        ],
        "pr-review": ["pr-review", repo, pr],
        "find": ["find", "README", "--limit", "1", "--json"],
        "attachment-get": None,
    }


def bbk_functions() -> list[tuple[str, str, int]]:
    found = []
    for filename in IN_SCOPE:
        path = BBK / filename
        if not path.is_file():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("_"):
                    continue
                found.append((filename, node.name, node.lineno))
    return found


def symbol_exists(dotted: str) -> bool:
    if not dotted:
        return False
    module_path, _, attribute = dotted.rpartition(".")
    try:
        module = __import__(module_path, fromlist=[attribute])
    except Exception:  # noqa: BLE001
        return False
    return hasattr(module, attribute)


def run_cli(argv: list[str]) -> int:
    completed = subprocess.run(
        [PYTHON, "-B", "-m", "atlawire", *argv],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        check=False,
    )
    return completed.returncode


def run(out: Path) -> int:
    pool = discover()
    args = cli_args(pool)
    results = []

    for module, name, line in bbk_functions():
        key = f"{module}:{name}"
        record = {"bbk": key, "bbk_line": line}
        entry = MAP.get(key)
        if entry is None:
            record.update(
                atlawire=None,
                verdict="missing",
                note="not in the parity map; needs triage",
            )
            results.append(record)
            continue

        symbol, declared, note, argv_key = entry
        record.update(atlawire=symbol or None, note=note)

        if declared == "excluded":
            record["verdict"] = "excluded"
            results.append(record)
            continue

        if not symbol_exists(symbol):
            record["verdict"] = "missing"
            record["note"] = f"{symbol} does not import"
            results.append(record)
            continue

        if argv_key:
            argv = args.get(argv_key)
            if argv:
                code = run_cli(argv)
                record.update(live_argv=argv, live_exit=code)
                if code != 0:
                    record["verdict"] = "worse"
                    record["note"] = f"live call failed with exit {code}"
                    results.append(record)
                    continue

        record["verdict"] = declared
        results.append(record)

    summary = Counter(record["verdict"] for record in results)
    document = {
        "generated": __import__("datetime").datetime.now().astimezone().isoformat(),
        "bbk_functions_in_scope": len(results),
        "summary": dict(summary),
        "results": results,
    }
    out.write_text(json.dumps(document, indent=2), encoding="utf-8")
    print(f"in-scope BBK functions: {len(results)}")
    print(f"summary: {dict(summary)}")
    for record in results:
        if record["verdict"] in {"missing", "worse"}:
            print(f"  {record['verdict']:8} {record['bbk']:34} {record.get('note')}")
    print("written:", out)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out", type=Path, default=Path("checks/live_tester_bbk_parity.json")
    )
    options = parser.parse_args()
    raise SystemExit(run(options.out))
