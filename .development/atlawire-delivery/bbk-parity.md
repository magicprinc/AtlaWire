# AtlaWire vs BBK: read-only Atlassian parity

Scope: read-only Atlassian workflows that agents use. BBK's non-Atlassian
integrations (Kafka, NATS, Grafana, Gmail, Calendar, chats, local indexes,
Maven catalog, MSSQL) are out of scope by the owner's decision and are not
listed as gaps here.

Statuses: **covered** = an AtlaWire command exists with offline tests;
**partial** = command exists but the noted dimension differs; **gap** = no
AtlaWire equivalent.

| BBK workflow | AtlaWire | Status | Note |
| --- | --- | --- | --- |
| `search` (indexed code search) | `search` | covered | Plugin-backed index; same coverage limits as BBK |
| `grep` (regex at a ref) | `grep-repo` | covered | Bounded pages, timeout, regex helper |
| `blame` | `blame` | covered | |
| `ls` | `ls` | covered | |
| `file` | `file` | covered | |
| `commits` | `commits` | covered | Page-first |
| `commit-changes` | `commit-changes` | covered | |
| `commit-diff` | `commit-diff` | covered | |
| `branches`, branch | `branches`, `branch` | covered | |
| `tags`, tag | `tags`, `tag` | covered | |
| `repos`, `projects`, `find-repos` | same names | covered | |
| `last_modified` | `last-modified` | covered | |
| `scan extension` | `scan-extension` | covered | |
| `my_prs` | `my-prs` | covered | |
| `pr files/diff/comments` | `pr`, `pr-diff-complete` | covered | Unified diff rendered locally |
| `review` (PR packet) | `pr-review` | covered | Markdown/JSON |
| merged/declined/dashboard PRs | `prs`, `pr-merge-status` | covered | |
| `jql` | `jql` | covered | |
| `mine` | `mine` | covered | |
| `statuses` | `statuses` | covered | |
| `comments` (author-wide) | `jira-author-comments` | covered | Heuristic author resolution is documented |
| `issue` | `issue`, `issue-changelog`, `issue-comments`, `issue-worklogs`, `issue-remote-links` | covered | |
| transitions/metadata | `transitions`, `jira-create-meta`, `jira-edit-meta`, `jira-transition-fields` | covered | |
| `page` | `page`, `page-history`, `page-comments`, `page-labels`, `page-attachments`, `page-version`, `page-url` | covered | |
| `spaces`, `children` | `spaces`, `children` | covered | |
| `cql` | `cql` | covered | |
| `find` (federated) | `find` | covered | Partial results: surviving products, per-product `errors`, `complete:false`; exit 1 only when all three fail |
| `whoami` | `whoami` | covered | Per-product identity and partial failures |
| `selftest` | `selftest` | covered | Same probe as `whoami`, registered under the BBK name |
| repository attachment download | `attachment-get` | partial | Returns base64 JSON, not a file; `read ... --out` covers archive/raw |
| Jira attachment download | `read jira.attachment.content --out` | covered | Streamed, bounded, no overwrite |
| `convert-body` | `convert-body`, `read confluence.content.convert` | covered | |
| page/issue Markdown rendering | `issue --markdown`, `page` | covered | |

## Remaining functional gaps

1. `attachment-get` emits base64 JSON. A file destination exists for the
   registered binary reads but not for that plugin route.
2. Live differential evidence covers five workflows; the rest are offline
   only.
3. Within one product, a paging failure discards that product's rows for the
   term; it is reported in `errors`, never silently shown as empty.

## Evidence

- Offline: 1073 focused tests across CLI, transport, registry and manifest.
- Live: five BBK comparisons previously recorded in
  `checks/test_bbk_live_parity.py` (JQL, CQL, code search, author comments,
  repository grep).
- Operation coverage: 201 required non-admin operations registered
  (192 JSON GET, 3 semantic POST, 6 binary); 9 administrative/system routes
  and 1 inconsistently documented route are excluded with reasons.
