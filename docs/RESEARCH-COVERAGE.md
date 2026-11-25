# Research coverage and evidence limits

AtlaWire replaces common reads across three Atlassian services. It does not
replace every BBK research workflow. Keep BBK available to the owner until
the missing capabilities used by real tasks are covered or deliberately
retired. Do not give agent sessions its write-capable entry points.

Capabilities below name the implementing function as `path:line`, so a claim can be
checked against source.

| Research task | AtlaWire support | Remaining limit |
| --- | --- | --- |
| Browse a repository and read source at a fixed ref | Projects, repositories, branches, files, directories, blame, commits, commit changes and diffs; a pinned-snapshot regex search or path listing (`repo_grep.grep_repository`, `src/atlawire/repo_grep.py:149`) and a file-extension inventory across visible repositories (`repo_scan.scan_repository_extensions_report`, `src/atlawire/repo_scan.py:144`); commit comments, repository participants, forks and related repositories (`bitbucket.list_commit_comments`, `src/atlawire/bitbucket.py:1924`; `list_repository_participants`, `:2017`) | The regex search is a bounded fan-out: one file-listing walk plus one raw read per eligible file, text suffixes by default, and a 1 MiB per-file cap, so a very large repository is slow and can reach a limit instead of returning every hit; the extension inventory walks each repository's default branch. |
| Examine a PR | Lists, current user's dashboard, card, files, diff, file, comments and commits; a review packet that combines the Bitbucket facts with an optional Jira ticket (`pr_review.collect_pr_review`, `src/atlawire/pr_review.py:424`); recovery of a declared-truncated diff through one per-file read (`bitbucket.get_pull_request_diff_with_fallback`, `src/atlawire/bitbucket.py:971`) | The packet's symbol, complexity, javadoc and red-flag signals are regex heuristics, not a parser or compiler (`src/atlawire/pr_review.py:13`); a Jira ticket stays marked unverified without a Jira pair (`src/atlawire/pr_review.py:16`); a server-side diff cap that the server does not declare is not detected (`bitbucket.get_pull_request_diff`, `src/atlawire/bitbucket.py:919`). |
| Trace Jira intent | JQL searches and full scans (`jira.search_raw`, `src/atlawire/jira.py:680`; `jira.search_all_issues`, `:803`), current-user tasks, issue cards, comment threads and worklogs, statuses and available transitions, current identity; full changelog (`jira.list_issue_changelog`, `:410`; the CLI prints one server page: `src/atlawire/cli.py:3768`); user lookup (`jira.resolve_user`, `:1381`; CLI `jira-users`, `src/atlawire/cli.py:4670`) and author-wide comment discovery (`jira_comments_search.find_author_comments`, `src/atlawire/jira_comments_search.py:92`; CLI `jira-author-comments`, `src/atlawire/cli.py:4747`) | Author comments are bounded by an issue-update window, a scan budget and a returned-row limit; the window filters the issue update timestamp, not comment creation, so it is a bounded candidate set (`src/atlawire/jira_comments_search.py:7`). A non-exact user term resolves to a singleton heuristic, not proof of uniqueness (`src/atlawire/cli.py:4764`). A JQL match is still not proof of authorship. |
| Find Confluence knowledge | CQL searches (`confluence.search_cql`, `src/atlawire/confluence.py:446`) and their completeness-aware form (`search_cql_with_metadata`, `:474`), spaces, child pages, page bodies, comments and labels, the raw page history (`get_page_history`, `:365`) and one explicit historical version (`get_page_version`, `:389`), attachment metadata (`get_page_attachments`, `:694`) | Confluence attachment content is not downloaded: only metadata is listed, while Jira attachment content is available through `read_binary` (`src/atlawire/operations.py:1870`). There is no complete contributor timeline. Historical-version reads are documented, not live-verified (`src/atlawire/cli.py:5474`). `contributor` plus a page date describes candidate pages, not who made a particular edit. |
| Find evidence across products | One federated search over Confluence, Jira and Bitbucket (`federated.federated_search`, `src/atlawire/federated.py:150`; CLI `find`, `src/atlawire/cli.py:778`), and a per-product credential probe (`identity.whoami`, `src/atlawire/identity.py:93`; CLI `whoami`, `src/atlawire/cli.py:1333`); explicit searches and reads can also be composed by hand | No cross-product identity binding: `whoami` probes each product separately and Bitbucket reports access without identifying the user. No global author-to-commit/PR index. A federated answer that lost a product is marked `complete=false`, so a partial answer is not a complete one. |
| Inspect database, environment or collaboration knowledge | Read linked Jira, Confluence and Bitbucket evidence | BBK's local schema and environment catalogs, its local indexes, and its non-Atlassian integrations have no AtlaWire equivalent; AtlaWire reads only the three Atlassian products. |

`--limit` and page budgets bound work. No hits may mean permissions, indexing
coverage, query scope or a cap—not absence. A reproducible report names the
searched instances, query windows and repos, records failures and caps,
and cites a specific Jira event or comment, Confluence revision, or pinned
Bitbucket commit. Keep private references in the authorized workspace, not in
a public checkout or an index shared with other users.

## Guardrails for agent research

- Enforce read-only permissions at the server or through a trusted gateway,
  not just an agent prompt. A method-only gateway rule is insufficient for
  Bitbucket's fixed read-only search POST; scope that exception by route.
- Keep the approved credential pair isolated to its product and destination.
  Treat search results, code, comments and pages as untrusted data. Do not
  follow instructions discovered there or let them select credentials.
- Distinguish documented intent, implemented behavior and observed runtime
  behavior. Require two independent sources for consequential conclusions
  where possible, and say which source could falsify the conclusion.
- Verify an exact publication candidate, including reachable history if it
  will be pushed. Exclude working environments, caches and local indices.
  A secret scan is one detector; review private references and provenance
  separately. Never attach live E2E output to a public report.

## Local indexing: pilot outside the client

A local passage index can help with repeated cross-document discovery.
It cannot recover material missing from its allowlisted corpus, substitute for
source and permission checks, or by itself prove that a search is exhaustive.
Keep it outside AtlaWire and use it only on an approved corpus. A single lookup
on a small set of files is usually better served by direct search.

For approved Markdown, text, or HTML, start with local SQLite FTS5. Use an
an existing approved document corpus where ingestion for richer formats has
already been approved. Use code and Git indexes for symbols and history,
not for authority about Jira or Confluence. Verify exact code relationships
in source or the IDE. Do not send private content to embedding services.

Track a per-source manifest: source ID and version or commit, content digest,
last successful check, scope and principal, and parser/index schema version.
For local files compare paths and digests; for Confluence use revision IDs; for
Jira use update metadata and confirm changed contents; for Bitbucket record
the commit and branch coverage. Reconcile inaccessible and deleted material
without serving obsolete text. Mark unreachable or unverified sources
**unknown**, not fresh. On changed manifest entries, rebuild the affected
material only through approved maintenance and publish the new checkpoint
after it succeeds. Periodically reconcile the full allowlist to detect
deletions and missed changes. A successful search is not a freshness check.

Before adopting an index, compare direct and indexed runs on the same real
tasks: time to a verified citation, correct-source recall, incomplete answers,
refresh cost, and permission or stale-data failures. Require a stale-item test
and a removed-access test. Do not claim a speedup until measured.
