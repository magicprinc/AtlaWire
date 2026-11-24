# MIGRATION-FROM-BBK — migration notes for agents

Operational notes for an agent moving read workflows from `bbk` to AtlaWire.
Everything below was checked in this repository; the live rows come from one
self-hosted Jira/Confluence/Bitbucket run on 2026-11-24 (AtlaWire `0.1.0.dev0`,
`d40d071` + local audit fixes). Treat live timings and results as a sample from
one deployment, not a guarantee.

## 1. Which layer to call

| Need | Use |
|---|---|
| A known, named workflow (issue card, PR diff, path listing) | the typed function in `atlawire.jira`, `atlawire.confluence`, `atlawire.bitbucket` |
| A registered read that has no typed wrapper | `atlawire read <operation-id>` / `read_operation(...)` (202 operations in `atlawire operations`) |
| A standard non-admin REST GET/POST with no typed wrapper | `atlawire.sdk.get_json` / `request_json` |
| A cross-product lead search | `atlawire find` / `federated.federated_search` |

All three typed modules are the canonical Python surface. `facade.AtlaWire` was
removed; there is no second dispatcher.

## 2. Calling convention change (the main rewrite)

BBK resolves credentials itself and takes no base URL or token:

```python
import bbk
rows = bbk.jira.jql("project = DEMO", limit=20)
page = bbk.confluence.page_md("12345")
data = bbk.bitbucket.projects()
```

AtlaWire takes an explicit pair, because the library never reads your
environment or credential file on its own:

```python
from atlawire.credentials import resolve_saved_credentials
from atlawire import jira, confluence, bitbucket

creds = resolve_saved_credentials("jira", supplied_base_url=None,
                                  allow_http_loopback=False)
rows = jira.search_issues(creds.base_url, "project = DEMO",
                          token=creds.token, limit=20)
```

The saved file is the same BBK file (`~/.config/atlassian/credentials.json`, or
`BBK_CREDENTIALS`). Resolve each product **once per process** and reuse the
`(base_url, token)` pair; do not call `resolve_saved_credentials` per file or
per row. `--token-from-env` / `ATLAWIRE_<PRODUCT>_URL` + `_TOKEN` is the CLI
equivalent.

## 3. Function map

| BBK | AtlaWire | Notes |
|---|---|---|
| `jira.jql` / `jira.rows` | `jira.search_issues` / `jira.search_raw` | short rows vs. the raw search envelope |
| `jira.mine` | `jira.list_my_issues` | |
| `jira.issue` | `jira.get_issue` | raw issue document |
| `jira.issue_md` | `issue_markdown.render_issue_markdown(issue)` | takes the issue document, not a key |
| `jira.statuses` | `jira.list_statuses` | |
| `jira.me` | `jira.get_current_user` | |
| `jira.transitions` | `jira.list_transitions` | |
| `jira.titles` | `jira.titles` | same name, explicit pair |
| `jira.resolve_user` | `jira.resolve_user` | |
| `jira.recent_comments` | `jira_comments_search` module | no same-name function |
| `jira.url` | — | no equivalent; build the browse URL yourself |
| `confluence.page` | `confluence.get_page` | |
| `confluence.page_storage` | `confluence.get_page(...)["body"]["storage"]["value"]` | no one-call helper |
| `confluence.page_md` | `confluence_markdown.render_page_markdown(page)` | takes the page document |
| `confluence.title` | field of `confluence.get_page` | no one-call helper |
| `confluence.url_for` | `confluence.get_page_web_url` | |
| `confluence.children` | `confluence.list_children` | |
| `confluence.spaces` | `confluence.list_spaces` | |
| `confluence.search_cql` | `confluence.search_cql` | |
| `bitbucket.projects` | `bitbucket.list_projects` | |
| `bitbucket.repos` | `bitbucket.list_repositories` | |
| `bitbucket.list_files` | `bitbucket.list_repository_files` | |
| `bitbucket.file_at` | `bitbucket.get_repository_file` | default branch when `at` is omitted |
| `bitbucket.pr` | `bitbucket.get_pull_request` | |
| `bitbucket.pr_files` | `bitbucket.list_pull_request_files` | |
| `bitbucket.pr_diff` | `bitbucket.get_pull_request_diff` | one path per call; no `paths=[...]` batch |
| `bitbucket.pr_file` | `bitbucket.get_pull_request_file` | |
| `bitbucket.pr_comments` | `bitbucket.list_pull_request_comments` | |
| `bitbucket.pr_commits` | `bitbucket.list_pull_request_commits` | |
| `bitbucket.pr_compact` | — | no compact PR projection |
| `bitbucket.my_prs` | `bitbucket.list_my_pull_requests` | |
| `bitbucket.prs` | `bitbucket.list_pull_requests` | |
| `bitbucket.search_code` | `bitbucket_search.search_code` | scope by `project=` **or** `repo=` (slug only) |
| `bitbucket.find_repos` | `bitbucket.find_repositories` | |
| `bitbucket.branches` | `bitbucket.list_branches` | |
| `bitbucket.commits` | `bitbucket.list_commits` | |
| `bitbucket.commit` | `bitbucket.get_commit` | |
| `bitbucket.commit_changes` | `bitbucket.list_commit_changes` | |
| `bitbucket.commit_diff` | `bitbucket.get_commit_diff` | |
| `bitbucket.ls` | `bitbucket.list_directory` | |
| `bitbucket.blame` | `bitbucket.get_file_blame` | |
| `grep` / `grep_ex` | `repo_grep.grep_repository` | one call; `--glob`/`--path` filters |
| `ls` (repo root) | `bitbucket.list_directory(repo, "")` | |
| `find` | `federated.federated_search` | takes three `ProductTarget` pairs |
| `whoami` | `identity.whoami(confluence=..., jira=..., bitbucket=...)` | explicit pairs, one per product |
| `attachments.attachment_download` | `bitbucket_attachment.get_repository_attachment` | bytes, never written implicitly |
| `repos_with_extension` | `repo_scan.scan_repository_extensions` | |
| `md.confluence_to_md` | `confluence_markdown.render_page_markdown` | document in, Markdown out |
| `md.jira_issue_to_md` | `issue_markdown.render_issue_markdown` | |
| `md.render_diff` | `bitbucket.get_pull_request_diff_text` | |
| `md.compact` / `compact_json` | — | no compact formatter |
| `review.*` | `pr_review.collect_pr_review` / `render_markdown` | packet, not BBK's `Packet` |
| `review.java_members`, `red_flags`, `changed_symbols` | private helpers in `pr_review` | not public |

## 4. Behaviour differences to plan for

- **No implicit credential lookup.** Every typed call takes `base_url` and
  `token`; this is the largest mechanical change.
- **No typed-layer retry.** Typed reads make one request per page and fail fast.
  `sdk.get_json` / `request_json` own a bounded retry policy (three attempts,
  five-second wait budget, `429`/`503`, no TLS retry). Do not stack your own
  retry loop on top of the SDK one.
- **Bearer only.** There is no Basic-auth fallback. A server that rejects the
  PAT with `401` fails here; document that as an environment/credential issue.
- **Errors are `AtlaWireError`.** Branch on `category`, `http_status`,
  `product`, `operation`, `method`, `path` instead of parsing text. You do not
  need a translator for consumers that only print errors; add one only where a
  caller must catch `BbkError` specifically.
- **Completeness is explicit.** Lists that a server can cap report
  `truncated` / `complete` (or have a `*_with_metadata` sibling). A short list
  without these fields proves nothing about the full set.
- **File revision.** `get_repository_file` and `file` omit `at` by default,
  matching the listing commands. Pass an explicit ref or a commit id when you
  need one pinned snapshot; a branch name still moves.

## 5. Live evidence (2026-11-24, one self-hosted deployment)

33 paired tasks were run through BBK and AtlaWire against the same fixtures.

- **Matched results:** Jira JQL, issue card, statuses, transitions, titles;
  Confluence page JSON, page storage, spaces, children, CQL, page URL;
  Bitbucket projects, repos, file list, file text, branches, commits, PRs,
  my PRs, PR card, PR files, PR comments, PR commits, find-repos.
- **AtlaWire-only available:** `jira.get_current_user`, `confluence.get_page_web_url`,
  `confluence.search_cql` (typed), `federated_search`, `identity.whoami` (explicit pairs).
- **Deliberate gaps:** `pr_compact`; `jira.url`; one-call `page_storage`/`title`;
  `pr_diff(paths=[...])` batching; public `review` heuristics.
- **Not a product bug:** my first `search_code(repo=...)` call used a slug
  keyword; the correct scope is `repo="KEY/slug"` or `project="KEY"`.
- **Markdown differs in size** for Jira and Confluence. Both are inert and
  preserve facts; exact byte parity is not a contract. Compare facts, not bytes.
- **Latency:** 0.14–0.22 s for most typed reads; the federated search took
  0.74 s (three products); a full repository grep took 17 s. Roughly equal to
  BBK except where AtlaWire deliberately reads more pages.

## 6. CLI equivalent

The CLI is the same API with credential resolution built in, so it is the
fastest migration path for scripts:

```shell
atlawire issue DEMO-42 --token-from-env
atlawire page 12345 --markdown --token-from-env
atlawire pr DEMO/widgets 7 diff --token-from-env
atlawire repos DEMO --json --token-from-env
```

`--json` is not universal; check `atlawire <command> --help`. List commands
that page without a row cap expose `--max-pages`; a few also take `--limit`.

## 7. Verification before switching

1. Resolve all three pairs once and run `atlawire whoami --json`; expect
   `ok: true` for each product.
2. Replay 2–3 real BBK workflows against the same fixtures and compare facts.
3. Check that every list you depend on reports completeness, or that you accept
   its cap.
4. Keep the saved credentials file unchanged; AtlaWire reads the same keys and
   ignores `*_user`/`*_password`.
