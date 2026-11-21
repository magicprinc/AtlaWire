# Research coverage and evidence limits

AtlaWire replaces common reads across three Atlassian services. It does not
replace every BBK research workflow. Keep BBK available to the owner until
the missing capabilities used by real tasks are covered or deliberately
retired. Do not give agent sessions its write-capable entry points.

| Research task | AtlaWire support | Remaining limit |
| --- | --- | --- |
| Browse a repository and read source at a fixed ref | Projects, repositories, branches, files, directories, blame, commits, commit changes and diff | Repository-wide regex and extension scans over arbitrary refs are not implemented. Indexed search is not equivalent. |
| Examine a PR | Lists, current user's dashboard, card, files, diff, file, comments and commits | No automated cross-source review packet. Declared diff truncation is an error, not an automatic per-file recovery. |
| Trace Jira intent | JQL, current-user tasks, issue, per-issue comments, statuses, available transitions and current identity | No arbitrary-user resolver, author-wide comment discovery, or history/changelog command. A JQL match is not proof of authorship. |
| Find Confluence knowledge | CQL, spaces, child pages, and current page bodies | No historical page-revision inspection, attachment reads, or complete contributor timeline. `contributor` plus a page date describes candidate pages, not who made a particular edit. |
| Find evidence across products | Compose explicit searches and reads | No one-shot federated query, cross-product identity binding, or global author-to-commit/PR index. |
| Inspect database, environment or collaboration knowledge | Read linked Jira, Confluence and Bitbucket evidence | BBK's local schema and environment catalogs, repository mapping, and non-Atlassian integrations have no AtlaWire equivalent. |

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
existing Basemind document corpus where ingestion for richer formats has
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
