# AtlaWire vs BBK: read-only Atlassian parity (S3)

Scope: every public Atlassian and Markdown function BBK exposes (44 functions in
`bbk.bitbucket`, `bbk.confluence`, `bbk.jira`, `bbk.md`). BBK's non-Atlassian
integrations (Kafka, NATS, Grafana, Gmail, Calendar, chats, local indexes, Maven
catalog, MSSQL) are out of scope by the owner's decision.

Verdicts:

- **parity** — same capability and same observable result; AtlaWire may validate
  more input.
- **improved** — same capability with a stronger contract: explicit errors
  instead of silent partials, the real default branch instead of a hard-coded
  name, one-call forms, or a parameter BBK lacked.
- **different** — same job, deliberately different shape; the reason is stated.

Evidence abbreviations:

- **L** — `checks/live_consumer_matrix.py`, 2026-11-24, installed wheel
  `atlawire-0.9.0`, read-only, 54/54 checks (report:
  `checks/live_consumer_matrix_report_2026-11-24.md`).
- **D** — `checks/test_bbk_live_parity.py`, same day, live differential against
  the real BBK child: `jql`, indexed `search` and one-file `grep` matched
  exactly; `cql` and author-comments were inconclusive for the reasons below.
- **T** — the offline suite (`tests/`), public surface only.

## Bitbucket (14 functions)

| BBK | AtlaWire | Verdict | Evidence / note |
| --- | --- | --- | --- |
| `projects()` | `bitbucket.list_projects` / `projects` | parity | T, L |
| `repos(project)` | `bitbucket.list_repositories` / `repos` | parity | T, L |
| `repos_with_extension(extension, workers=8)` | `repo_scan.scan_repository_extensions*` / `scan-extension` | improved | Bounded per-repo work and an explicit `complete`/`truncated` report instead of a bare list; T |
| `search_code(query, project, repo, limit, every_page)` | `repo_search.search_repositories` / `repo-search` | improved | Three engines (`index`, `bytes`, `auto`), optional archive fetch, per-entry caps; L, D, T |
| `list_files(repo, at)` | `list_repository_files` / `files` | parity | T, L |
| `file_at(repo, path, at="master")` | `get_repository_file` / `file` | improved | `at=None` reads the repository's real default branch (BBK hard-codes `master` and fails on `main`); L, T |
| `pr(repo, pr_id)` | `get_pull_request` / `pr show` | parity | L |
| `pr_compact(repo, pr_id)` | `bitbucket.pr_compact` | parity | L |
| `pr_files(repo, pr_id)` | `list_pull_request_files` / `pr files` | parity | L |
| `pr_diff(repo, pr_id, paths, context, whitespace)` | `get_pull_request_diff`, `get_pull_request_diffs`, `get_pull_request_diff_text`, `get_pull_request_diff_with_fallback`, `pr diff` | improved | Same `paths`/`context`/`whitespace`. The mode is validated, and all three live-accepted values are supported (`ignore-all`, `ignore-trailing`, `ignore-none`). BBK silently fell back on `truncated`; AtlaWire does that only in the explicitly named `_with_fallback` call. L, T |
| `pr_file(repo, pr_id, path, side)` | `get_pull_request_file` / `pr file` | parity | T |
| `pr_comments(repo, pr_id)` | `list_pull_request_comments` / `pr comments` | parity | L |
| `prs(repo, state, limit, order)` | `list_pull_requests` / `prs` | improved | Adds `direction`, `author`, `role`, `participant`, `max_pages`; L |
| `my_prs(state, role, limit, participant_status)` | `list_my_pull_requests` / `my-prs` | parity | Rejects `state=ALL`, exactly as the dashboard endpoint does (BBK: "ALL сервер не принимает"); L |

## Confluence (10 functions)

| BBK | AtlaWire | Verdict | Evidence / note |
| --- | --- | --- | --- |
| `spaces(limit)` | `list_spaces` / `spaces` | parity | L |
| `page(value)` | `get_page` / `page` | parity | L |
| `page_id(value)` | `confluence.page_id` | parity | T |
| `page_storage(value)` | `get_page_storage` | parity | L |
| `page_md(value)` | `get_page_markdown` | parity | L |
| `title(value)` | `get_page_title` | parity | L |
| `url_for(page)` | `get_page_web_url` / `page-url` | improved | `--json` returns `{url}`; T |
| `children(value, limit)` | `list_children`, `list_children_with_metadata` | improved | Adds the completeness signal; L |
| `search_cql(cql, limit)` | `search_cql`, `search_cql_with_metadata` / `cql` | parity | L, D (this deployment returns an empty CQL index, see limits) |
| `client_base()` | `client_for` (typed layer) | different | AtlaWire never returns saved credentials implicitly; `client_for` returns one product's base URL and token to the caller that asked. T |

Beyond parity: `page_forms` and the `get_page_storage` + `get_page_title` +
`get_page_markdown` trio give JSON, storage XHTML and Markdown from **one** read;
BBK needed up to three calls (L: `cf.forms.one-call`).

## Jira (12 functions)

| BBK | AtlaWire | Verdict | Evidence / note |
| --- | --- | --- | --- |
| `jql(query, limit, fields)` | `search_issues`, `search_all_issues*` / `jql` | parity | `fields` is a string or list; L, D (ordered keys matched BBK exactly) |
| `rows(query, limit)` | `search_issues` / `jql` | parity | Same projection family; T, D |
| `issue(key)` | `get_issue` / `issue` | parity | L |
| `issue_md(key, wiki)` | `get_issue_markdown`, `jira_issue_to_md`, `issue --markdown` | parity | L |
| `me()` | `get_current_user` / `whoami` | parity | L |
| `mine(status, limit)` | `list_my_issues` / `mine` | parity | T |
| `recent_comments(user, days, limit, text, project, max_issues, strict)` | `find_author_comments` / `jira-author-comments` | improved | Always strict: a page-budget cut raises instead of returning partial rows, so BBK's `strict` opt-in is unnecessary. `grep=` replaces `text=`; user resolution tries exact, transliteration, then a short prefix and rejects ambiguity. T, D (inconclusive here: no recent comment by the current user) |
| `resolve_user(term)` | `resolve_user` | parity | `None` reads `/myself`; L |
| `statuses()` | `list_statuses` / `statuses` | parity | Returns names; L |
| `titles(keys, refresh)` | `titles` | improved | Same batching (50 per JQL read) without a SQLite cache: no stale answers, so `refresh` has no meaning; T, L |
| `transitions(issue_key)` | `list_transitions` / `transitions` | parity | L |
| `url(key)` | `jira.issue_url` | parity | L |

Beyond parity: `issue_forms` returns the JSON document, Markdown and
wiki-Markdown from one read; `issue_url` needs no request (L).

## Markdown (8 functions)

| BBK | AtlaWire | Verdict | Evidence / note |
| --- | --- | --- | --- |
| `confluence_to_md(storage)` | `atlawire.markdown.confluence_to_md` | improved | Inert output only: no active HTML; link destinations kept as `label (url)`; mention and macro text preserved; L, T |
| `wiki_to_md(text)` | `markdown.wiki_to_md` | improved | Same inert-output contract; L |
| `html_to_md(html)` | `markdown.html_to_md` | improved | Same; L |
| `jira_issue_to_md(issue, wiki)` | `markdown.jira_issue_to_md` | parity | L |
| `render_diff(payload)` | `markdown.render_diff` | parity | L |
| `compact(obj)` | `markdown.compact` | parity | Drops service keys and collapses user and branch wrappers; L |
| `compact_json(obj)` | `markdown.compact_json` | parity | One-line JSON; L |
| `change_rows(changes)` | `list_pull_request_files` / `list_commit_changes` | different | The projection is built inside the typed list call, so a separate raw-row helper is unnecessary; T |

BBK's `jira2markdown` dependency was not adopted: it is a 0.6 alpha, adds
`pyparsing>=3`, and can emit active HTML. The comparison is recorded in
`docs/MIGRATION-FROM-BBK.md`.

## Live limits observed (not AtlaWire defects)

1. **CQL index empty.** `/rest/api/content/search` returns `size=0`,
   `totalSize=0` for every query tried, including `id = <known page id>`, while
   direct content listing in the same space returns pages. Both BBK and AtlaWire
   therefore get zero rows; the differential check reports `empty_result`, not a
   mismatch.
2. **No recent comment by the current user**, so the author-comments
   differential check reports `fixture:...` instead of a comparison.
3. **Dashboard pull requests reject `state=ALL`** (`400`); both tools reject it
   before the request.

## Evidence summary

| Gate | Result |
| --- | --- |
| Live consumer matrix on the installed wheel | 54/54 PASS |
| Differential BBK comparison | 3 pass, 2 inconclusive (documented above), 0 mismatch |
| Offline suite | recorded in `progress.md` after the final change |
