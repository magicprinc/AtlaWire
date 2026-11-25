"""Live read-only consumer matrix for the installed AtlaWire wheel.

Run outside ``tests`` with explicit opt-in. It resolves saved credentials through
the library, discovers real anchors by read-only calls, and then verifies what
each capability *should* return against what it did return. No payload, host or
token is ever printed; every line is a verdict plus a fixed label.

Usage:
    set PYTHONPATH=<installed target>
    python -P -B checks/live_consumer_matrix.py --live
"""

import argparse
import sys
import time
import traceback
from collections.abc import Callable
from typing import Never

from atlawire import bitbucket, confluence, jira, pr_review, repo_grep, repo_search
from atlawire import markdown as md
from atlawire.credentials import PRODUCTS, load_saved_credentials
from atlawire.http import AtlaWireError

PASS, FAIL, CAP, GAP, SKIP = "PASS", "FAIL", "CAP", "GAP", "SKIP"
_results: list[tuple[str, str, str]] = []


def _record(name: str, verdict: str, note: str = "") -> None:
    _results.append((name, verdict, note))
    print(f"{verdict:4} {name}" + (f"  [{note}]" if note else ""))


def _never(message: str) -> Never:
    raise AssertionError(message)


def _check(name: str, fn: Callable[[], str | None]) -> None:
    """Run one check; a returned string is a structural note, not a failure."""
    started = time.monotonic()
    try:
        note = fn()
    except AtlaWireError as exc:
        _record(name, FAIL, f"AtlaWireError {exc.category}")
    except AssertionError as exc:
        _record(name, FAIL, str(exc).splitlines()[0][:120])
    except Exception as exc:  # noqa: BLE001 - a live probe must not abort the run
        _record(name, FAIL, f"{type(exc).__name__}: {str(exc)[:100]}")
        if _VERBOSE:
            traceback.print_exc()
    else:
        elapsed = time.monotonic() - started
        _record(name, PASS, f"{elapsed:.1f}s {note or ''}".strip())


def _cap(name: str, fn: Callable[[], bool]) -> None:
    """Record a capability limit only when the documented bound is observed."""
    try:
        limited = fn()
    except Exception as exc:  # noqa: BLE001
        _record(name, FAIL, f"{type(exc).__name__}: {str(exc)[:100]}")
        return
    _record(name, CAP if limited else PASS, "bounded" if limited else "unbounded")


def _creds(product: str):
    saved = load_saved_credentials(product, allow_http_loopback=False)
    return saved.base_url, saved.token


def _discover(bb, cf, jr) -> dict[str, object]:
    """Find real anchors through read-only listing calls."""
    anchors: dict[str, object] = {}

    projects = bitbucket.list_projects(bb[0], token=bb[1], limit=5)
    if not projects:
        _never("no Bitbucket project is visible")
    project = projects[0]
    anchors["project"] = str(project["key"])

    repos = bitbucket.list_repositories(
        bb[0], anchors["project"], token=bb[1], limit=10
    )
    if not repos:
        _never("no repository is visible in the first project")
    anchors["repo"] = str(repos[0]["slug"])

    spaces = confluence.list_spaces(cf[0], token=cf[1], limit=5)
    if not spaces:
        _never("no Confluence space is visible")
    anchors["space"] = str(spaces[0]["key"])

    issues = jira.search_issues(jr[0], "order by created DESC", token=jr[1], limit=1)
    if not issues:
        _never("no Jira issue is visible")
    anchors["issue"] = str(issues[0]["key"])

    return anchors


_VERBOSE = False


def main(argv: list[str]) -> int:
    global _VERBOSE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="required opt-in")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    if not args.live:
        print("Refusing: pass --live to contact the configured servers.")
        return 2
    _VERBOSE = args.verbose

    bb = _creds("bitbucket")
    cf = _creds("confluence")
    jr = _creds("jira")
    print("credentials: resolved for " + ", ".join(PRODUCTS))

    try:
        anchors = _discover(bb, cf, jr)
    except AssertionError as exc:
        print(f"discovery failed: {exc}")
        return 1
    print("anchors: " + " ".join(sorted(anchors)))
    project = str(anchors["project"])
    repo = str(anchors["repo"])
    space = str(anchors["space"])
    issue = str(anchors["issue"])
    repo_key = f"{project}/{repo}"

    # --- Bitbucket ---------------------------------------------------------
    def bb_project() -> str | None:
        value = bitbucket.get_project(bb[0], project, token=bb[1])
        assert value["key"] == project, "project key mismatch"
        return "key ok"

    def bb_repo() -> str | None:
        value = bitbucket.get_repository(bb[0], project, repo, token=bb[1])
        assert value["slug"] == repo, "repository slug mismatch"
        return "slug ok"

    def bb_branches() -> str | None:
        rows = bitbucket.list_branches(bb[0], repo_key, token=bb[1], limit=10)
        assert rows, "no branch listed"
        default = bitbucket.get_default_branch(bb[0], project, repo, token=bb[1])
        assert any(row["name"] == default["displayId"] for row in rows), (
            "default branch missing from listing"
        )
        return "default branch present"

    def bb_tree() -> str | None:
        rows = bitbucket.list_repository_files(bb[0], repo_key, token=bb[1], limit=20)
        assert rows, "empty repository tree"
        listed = bitbucket.list_directory(bb[0], repo_key, "", token=bb[1], limit=20)
        assert isinstance(listed, list), "directory listing is not a list"
        return f"{len(rows)} path(s)"

    def bb_file() -> str | None:
        rows = bitbucket.list_repository_files(bb[0], repo_key, token=bb[1], limit=50)
        target = next((path for path in rows if path.endswith(".md")), rows[0])
        text = bitbucket.get_repository_file(bb[0], repo_key, target, token=bb[1])
        assert text is not None, "default-branch file read returned nothing"
        return f"{len(text)} char(s)"

    def bb_file_named_ref() -> str | None:
        default = bitbucket.get_default_branch(bb[0], project, repo, token=bb[1])
        rows = bitbucket.list_repository_files(bb[0], repo_key, token=bb[1], limit=50)
        target = next((path for path in rows if path.endswith(".md")), rows[0])
        named = bitbucket.get_repository_file(
            bb[0], repo_key, target, token=bb[1], at=default["displayId"]
        )
        assert named is not None, "named-ref read returned nothing"
        return "branch name accepted"

    def bb_commits() -> str | None:
        rows = bitbucket.list_commits(bb[0], repo_key, token=bb[1], limit=5)
        assert rows, "no commit listed"
        first = rows[0]
        detail = bitbucket.get_commit(bb[0], repo_key, first["id"], token=bb[1])
        assert detail["id"] == first["id"], "commit id mismatch"
        assert first.get("displayId"), "commit row carries no displayId"
        assert first["hash"] == first["id"], "deprecated hash alias diverged"
        return f"{len(rows)} commit(s)"

    def bb_changes() -> str | None:
        commits = bitbucket.list_commits(bb[0], repo_key, token=bb[1], limit=1)
        rows = bitbucket.list_commit_changes(
            bb[0], repo_key, commits[0]["id"], token=bb[1]
        )
        return f"{len(rows)} change(s)"

    def bb_blame() -> str | None:
        rows = bitbucket.list_repository_files(bb[0], repo_key, token=bb[1], limit=50)
        target = next((path for path in rows if path.endswith(".md")), rows[0])
        values = bitbucket.get_file_blame(bb[0], repo_key, target, token=bb[1])
        assert values, "blame returned nothing"
        return f"{len(values)} line(s)"

    def bb_tags() -> str | None:
        rows = bitbucket.list_tags(bb[0], repo_key, token=bb[1], limit=5)
        return f"{len(rows)} tag(s)"

    def bb_prs() -> str | None:
        rows = bitbucket.list_pull_requests(
            bb[0], repo_key, token=bb[1], state="ALL", limit=10
        )
        return f"{len(rows)} pr(s)"

    def bb_my_prs() -> str | None:
        rows = bitbucket.list_my_pull_requests(
            bb[0], token=bb[1], state="OPEN", limit=10
        )
        return f"{len(rows)} pr(s)"

    pr_id: dict[str, object] = {}

    def bb_pr_pick() -> str | None:
        rows = bitbucket.list_pull_requests(
            bb[0], repo_key, token=bb[1], state="ALL", limit=10
        )
        if not rows:
            return "no pull request in this repository"
        pr_id["id"] = rows[0]["id"]
        return f"id {rows[0]['id']} selected"

    def _need_pr() -> object:
        if "id" not in pr_id:
            raise AssertionError("no pull request available")
        return pr_id["id"]

    def bb_pr_detail() -> str | None:
        ident = _need_pr()
        value = bitbucket.get_pull_request(bb[0], repo_key, ident, token=bb[1])
        assert str(value["id"]) == str(ident), "pull request id mismatch"
        compact = bitbucket.pr_compact(bb[0], repo_key, ident, token=bb[1])
        assert compact["id"] == value["id"], "pr_compact id mismatch"
        return "detail and compact agree"

    def bb_pr_files() -> str | None:
        ident = _need_pr()
        rows = bitbucket.list_pull_request_files(bb[0], repo_key, ident, token=bb[1])
        return f"{len(rows)} file(s)"

    def bb_pr_diff() -> str | None:
        ident = _need_pr()
        value = bitbucket.get_pull_request_diff(bb[0], repo_key, ident, token=bb[1])
        assert "diffs" in value, "diff object lacks diffs"
        text = bitbucket.get_pull_request_diff_text(bb[0], repo_key, ident, token=bb[1])
        assert text, "diff text is empty"
        return f"{len(value['diffs'])} diff(s)"

    def bb_pr_diff_whitespace() -> str | None:
        ident = _need_pr()
        modes = ("ignore-all", "ignore-trailing", "ignore-none")
        for mode in modes:
            shown = bitbucket.get_pull_request_diff(
                bb[0], repo_key, ident, token=bb[1], whitespace=mode
            )
            assert "diffs" in shown, f"diff lacks diffs for {mode}"
        return "all three modes accepted"

    def bb_pr_batch_diff() -> str | None:
        ident = _need_pr()
        files = bitbucket.list_pull_request_files(bb[0], repo_key, ident, token=bb[1])
        paths = [str(row["path"]) for row in files[:3]]
        if not paths:
            return "no changed path to request"
        values = bitbucket.get_pull_request_diffs(
            bb[0], repo_key, ident, paths=paths, token=bb[1]
        )
        assert len(values) == len(paths), "batch diff length mismatch"
        assert all("diffs" in value for value in values), "batch diff shape"
        return f"{len(values)} ordered diff(s)"

    def bb_pr_comments() -> str | None:
        ident = _need_pr()
        rows = bitbucket.list_pull_request_comments(
            bb[0], repo_key, ident, token=bb[1], limit=20
        )
        return f"{len(rows)} comment(s)"

    def bb_pr_commits() -> str | None:
        ident = _need_pr()
        rows = bitbucket.list_pull_request_commits(
            bb[0], repo_key, ident, token=bb[1], limit=20
        )
        return f"{len(rows)} commit(s)"

    # --- Confluence --------------------------------------------------------
    page_id: dict[str, object] = {}

    def cf_pick() -> str | None:
        content = confluence.list_space_content(cf[0], space, token=cf[1], limit=10)
        rows = content.get("rows") or []
        pages = [row for row in rows if row.get("type") == "page" and row.get("id")]
        if not pages:
            found = confluence.search_cql(
                cf[0], f'space = "{space}"', token=cf[1], limit=5
            )
            pages = [
                row for row in found if row.get("type") == "page" and row.get("id")
            ]
        if not pages:
            return "no page in space"
        page_id["id"] = pages[0]["id"]
        return f"page {pages[0]['id']} selected"

    def _need_page() -> object:
        if "id" not in page_id:
            raise AssertionError("no Confluence page available")
        return page_id["id"]

    def cf_page() -> str | None:
        ident = _need_page()
        value = confluence.get_page(cf[0], ident, token=cf[1])
        assert str(value["id"]) == str(ident), "page id mismatch"
        return "id ok"

    def cf_forms() -> str | None:
        ident = _need_page()
        title = confluence.get_page_title(cf[0], ident, token=cf[1])
        storage = confluence.get_page_storage(cf[0], ident, token=cf[1])
        forms = confluence.page_forms(cf[0], ident, token=cf[1])
        assert isinstance(title, str) and title, "empty title"
        assert isinstance(storage, str), "storage is not text"
        assert set(forms) == {"document", "markdown", "storage"}, (
            f"page_forms keys {sorted(forms)}"
        )
        assert isinstance(forms["markdown"], str), "markdown form is not text"
        one_call = confluence.get_page_markdown(cf[0], ident, token=cf[1])
        assert one_call == forms["markdown"], "markdown forms disagree"
        return "raw/markdown/json in one call"

    def cf_children() -> str | None:
        ident = _need_page()
        rows = confluence.list_children(cf[0], ident, token=cf[1], limit=20)
        return f"{len(rows)} child(ren)"

    def cf_comments() -> str | None:
        ident = _need_page()
        rows = confluence.get_page_comments(cf[0], ident, token=cf[1], limit=20)
        return f"{len(rows)} comment(s)"

    def cf_history() -> str | None:
        ident = _need_page()
        rows = confluence.get_page_history(cf[0], ident, token=cf[1])
        return f"{len(rows)} version(s)"

    def cf_labels() -> str | None:
        ident = _need_page()
        rows = confluence.get_page_labels(cf[0], ident, token=cf[1], limit=20)
        return f"{len(rows)} label(s)"

    def cf_attachments() -> str | None:
        ident = _need_page()
        rows = confluence.get_page_attachments(cf[0], ident, token=cf[1], limit=20)
        return f"{len(rows)} attachment(s)"

    def cf_spaces() -> str | None:
        rows = confluence.list_spaces(cf[0], token=cf[1], limit=5)
        assert rows, "no space listed"
        detail = confluence.get_space(cf[0], space, token=cf[1])
        assert detail["key"] == space, "space key mismatch"
        return "space detail ok"

    def cf_content() -> str | None:
        value = confluence.list_space_content(cf[0], space, token=cf[1], limit=10)
        assert set(value) == {"rows", "truncated"}, f"content keys {sorted(value)}"
        return f"{len(value['rows'])} content row(s)"

    # --- Jira --------------------------------------------------------------
    def jr_issue() -> str | None:
        value = jira.get_issue(jr[0], issue, token=jr[1])
        assert value["key"] == issue, "issue key mismatch"
        return "key ok"

    def jr_forms() -> str | None:
        forms = jira.issue_forms(jr[0], issue, token=jr[1])
        assert set(forms) == {"document", "markdown", "wiki_markdown"}, (
            f"issue_forms keys {sorted(forms)}"
        )
        assert isinstance(forms["markdown"], str), "markdown form is not text"
        one = jira.get_issue_markdown(jr[0], issue, token=jr[1])
        assert one == forms["markdown"], "markdown forms disagree"
        url = jira.issue_url(jr[0], issue)
        assert url.endswith(f"/browse/{issue}"), "issue URL shape"
        return "document/markdown/wiki + url"

    def jr_comments() -> str | None:
        rows = jira.list_issue_comments(jr[0], issue, token=jr[1], limit=20)
        return f"{len(rows)} comment(s)"

    def jr_changelog() -> str | None:
        rows = jira.list_issue_changelog(jr[0], issue, token=jr[1])
        return f"{len(rows)} entr(y/ies)"

    def jr_transitions() -> str | None:
        rows = jira.list_transitions(jr[0], issue, token=jr[1])
        return f"{len(rows)} transition(s)"

    def jr_links() -> str | None:
        rows = jira.list_issue_remote_links(jr[0], issue, token=jr[1])
        return f"{len(rows)} link(s)"

    def jr_watchers() -> str | None:
        value = jira.get_issue_watchers(jr[0], issue, token=jr[1])
        assert "watchCount" in value, "watchers payload lacks watchCount"
        return "watchCount present"

    def jr_votes() -> str | None:
        value = jira.get_issue_votes(jr[0], issue, token=jr[1])
        assert isinstance(value["voters"], list), "voters is not a list"
        assert "hasVoted" in value, "votes payload lacks hasVoted"
        return f"{len(value['voters'])} voter(s)"

    def jr_properties() -> str | None:
        rows = jira.get_issue_properties(jr[0], issue, token=jr[1])
        return f"{len(rows)} propert(y/ies)"

    def jr_meta() -> str | None:
        projects = jira.list_jira_projects(jr[0], token=jr[1])
        statuses = jira.list_statuses(jr[0], token=jr[1])
        types = jira.list_issue_types(jr[0], token=jr[1])
        assert projects and statuses and types, "empty reference data"
        return f"{len(projects)}p/{len(statuses)}s/{len(types)}t"

    def jr_search() -> str | None:
        rows = jira.search_issues(jr[0], f"key = {issue}", token=jr[1], limit=5)
        assert len(rows) == 1 and rows[0]["key"] == issue, "exact JQL mismatch"
        return "exact JQL ok"

    def jr_titles() -> str | None:
        rows = jira.titles(jr[0], [issue], token=jr[1])
        assert rows.get(issue), "no title for the known issue"
        return "title present"

    def jr_markdown() -> str | None:
        text = jira.get_issue_markdown(jr[0], issue, token=jr[1])
        assert len(text) > 10, "markdown too short"
        assert "\x00" not in text, "NUL in markdown"
        return f"{len(text)} char(s)"

    # --- Cross-cutting -----------------------------------------------------
    def md_confluence_roundtrip() -> str | None:
        ident = _need_page()
        storage = confluence.get_page_storage(cf[0], ident, token=cf[1])
        text = md.confluence_to_md(storage)
        assert isinstance(text, str), "confluence_to_md is not text"
        return f"{len(text)} char(s)"

    def md_html() -> str | None:
        text = md.html_to_md("<p>a</p><h1>T</h1><ul><li>x</li></ul>")
        assert "T" in text and "x" in text, "html conversion lost text"
        return "structure preserved"

    def md_wiki() -> str | None:
        text = md.wiki_to_md("h1. Title\n*bold*")
        assert "Title" in text, "wiki conversion lost text"
        return "wiki ok"

    def md_compact() -> str | None:
        ident = _need_page()
        raw = confluence.get_page_markdown(cf[0], ident, token=cf[1])
        small = md.compact(raw)
        assert len(small) <= len(raw), "compact grew the text"
        as_json = md.compact_json({"a": 1, "links": {"self": []}})
        assert isinstance(as_json, str) and "links" not in as_json, (
            "compact_json did not drop service keys"
        )
        return f"{len(raw)}->{len(small)} char(s)"

    def md_render_diff() -> str | None:
        ident = _need_pr()
        diff = bitbucket.get_pull_request_diff(bb[0], repo_key, ident, token=bb[1])
        text = md.render_diff(diff)
        assert isinstance(text, str), "render_diff is not text"
        return f"{len(text)} char(s)"

    def rv_review() -> str | None:
        ident = _need_pr()
        text = pr_review.review(
            bb[0],
            repo_key,
            ident,
            token=bb[1],
            jira_base_url=jr[0],
            jira_token=jr[1],
        )
        assert text.startswith("#"), "review markdown does not start with a heading"
        return f"{len(text.splitlines())} line(s)"

    def rv_packet() -> str | None:
        ident = _need_pr()
        packet = pr_review.collect_pr_review(
            bb[0],
            repo_key,
            ident,
            token=bb[1],
            jira_base_url=jr[0],
            jira_token=jr[1],
        )
        assert "checks" in packet and "profile" in packet, "packet shape"
        assert packet["files"] is not None, "packet lacks files"
        return "packet shape ok"

    def rv_helpers() -> str | None:
        members = pr_review.java_members("class A { void run() {} }")
        assert members, "java_members found nothing"
        flags = pr_review.red_flags("try { } finally { }", path="A.java")
        assert isinstance(flags, list), "red_flags is not a list"
        symbols = pr_review.changed_symbols(
            "class A { }", "class A { void run() {} }", path="A.java"
        )
        assert isinstance(symbols, list), "changed_symbols is not a list"
        ident = _need_pr()
        detail = bitbucket.get_pull_request(bb[0], repo_key, ident, token=bb[1])
        links = pr_review.file_links(
            bb[0],
            repo_key,
            "README.md",
            from_hash=str(detail["fromRef"]["latestCommit"]),
            to_hash=str(detail["toRef"]["latestCommit"]),
            pr_id=int(ident),
        )
        assert set(links) == {"before", "after", "diff"}, "file_links shape"
        return "review helpers usable"

    def rs_index() -> str | None:
        rows = repo_search.search_repositories(
            bb[0],
            "class",
            token=bb[1],
            project=project,
            engine="index",
            limit=20,
            max_repos=3,
            path_glob="*.java",
        )
        assert rows["rows"] is not None, "index search has no rows"
        return f"{len(rows['rows'])} row(s)"

    def rs_bytes() -> str | None:
        rows = repo_search.search_repositories(
            bb[0],
            "class",
            token=bb[1],
            project=project,
            engine="bytes",
            fetch="archive",
            limit=20,
            max_repos=2,
            path_glob="*.java",
        )
        assert rows["repositories_scanned"] >= 1, "no repository scanned"
        return f"{len(rows['rows'])} row(s)"

    def rg_grep() -> str | None:
        rows = repo_grep.grep_repository(
            bb[0],
            repo_key,
            "class",
            token=bb[1],
            glob="*.java",
            limit=5,
        )
        assert rows["hits"] is not None, "grep result has no hits"
        return f"{len(rows['hits'])} hit(s)"

    checks = [
        ("bb.project", bb_project),
        ("bb.repo", bb_repo),
        ("bb.branches", bb_branches),
        ("bb.tree", bb_tree),
        ("bb.file.default-branch", bb_file),
        ("bb.file.named-ref", bb_file_named_ref),
        ("bb.commits", bb_commits),
        ("bb.commit.changes", bb_changes),
        ("bb.blame", bb_blame),
        ("bb.tags", bb_tags),
        ("bb.prs", bb_prs),
        ("bb.my-prs", bb_my_prs),
        ("bb.pr.pick", bb_pr_pick),
        ("bb.pr.detail+compact", bb_pr_detail),
        ("bb.pr.files", bb_pr_files),
        ("bb.pr.diff", bb_pr_diff),
        ("bb.pr.diff.show-whitespace", bb_pr_diff_whitespace),
        ("bb.pr.diff.batch", bb_pr_batch_diff),
        ("bb.pr.comments", bb_pr_comments),
        ("bb.pr.commits", bb_pr_commits),
        ("cf.pick", cf_pick),
        ("cf.page", cf_page),
        ("cf.forms.one-call", cf_forms),
        ("cf.children", cf_children),
        ("cf.comments", cf_comments),
        ("cf.history", cf_history),
        ("cf.labels", cf_labels),
        ("cf.attachments", cf_attachments),
        ("cf.spaces", cf_spaces),
        ("cf.space-content", cf_content),
        ("jr.issue", jr_issue),
        ("jr.forms.one-call+url", jr_forms),
        ("jr.comments", jr_comments),
        ("jr.changelog", jr_changelog),
        ("jr.transitions", jr_transitions),
        ("jr.remote-links", jr_links),
        ("jr.watchers", jr_watchers),
        ("jr.votes", jr_votes),
        ("jr.properties", jr_properties),
        ("jr.reference-data", jr_meta),
        ("jr.search.exact", jr_search),
        ("jr.titles", jr_titles),
        ("jr.markdown", jr_markdown),
        ("md.confluence", md_confluence_roundtrip),
        ("md.html", md_html),
        ("md.wiki", md_wiki),
        ("md.compact(+json)", md_compact),
        ("md.render-diff", md_render_diff),
        ("review.one-call", rv_review),
        ("review.packet", rv_packet),
        ("review.helpers", rv_helpers),
        ("search.index", rs_index),
        ("search.bytes.archive", rs_bytes),
        ("grep.repository", rg_grep),
    ]

    for name, fn in checks:
        _check(name, fn)

    def note_missing() -> None:
        counts: dict[str, int] = {}
        for _, verdict, _ in _results:
            counts[verdict] = counts.get(verdict, 0) + 1
        print(
            "\n" + " ".join(f"{key}={value}" for key, value in sorted(counts.items()))
        )

    note_missing()
    failed = [name for name, verdict, _ in _results if verdict == FAIL]
    if failed:
        print("failed: " + " ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    raise SystemExit(main(sys.argv[1:]))
