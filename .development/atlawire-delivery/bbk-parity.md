# AtlaWire vs BBK: read-only Atlassian parity

Scope: read-only Atlassian workflows that agents use. BBK's non-Atlassian
integrations (Kafka, NATS, Grafana, Gmail, Calendar, chats, local indexes,
Maven catalog, MSSQL) are out of scope by the owner's decision and are not
listed as gaps here.

This is a **provisional mapping**, not a parity verdict. **Covered** means a
candidate command and offline tests were identified, not that all BBK flags,
public helpers or live behavior were verified. **Partial** means a known gap
or failure remains; **gap** means no equivalent has been identified. Use the
[delivery checklist](delivery-plan.md#execution-order) and [functional test
matrix](test-plan.md#6-full-functional-matrix) to replace labels with exact
fixture, artifact and outcome evidence.

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
| `find` (federated) | `find` | partial | Returns some partial results; missing pairs, mixed-term all-failed detection and total-read budget are open |
| `whoami` | `whoami` | covered | Per-product identity and partial failures |
| `selftest` | `selftest` | covered | Same probe as `whoami`, registered under the BBK name |
| repository attachment download | `attachment-get` | partial | Supports base64 and `--out`; no-overwrite and complete gzip validation are open |
| Jira attachment download | `read jira.attachment.content --out` | partial | Streamed and bounded; complete response and no-overwrite need regression proof |
| `convert-body` | `convert-body`, `read confluence.content.convert` | covered | |
| page/issue Markdown rendering | `issue --markdown`, `page` | covered | |

## Remaining functional gaps

1. Both file-output paths violate the no-overwrite guarantee at publication
   time. See [audit follow-up](audit-follow-up.md). The repository attachment
   route is BBK-observed; live plugin/version support is not established here.
2. Five historical live comparisons are not verification of the current wheel
   or of the rest of the matrix.
3. The `find` boundary intentionally discards a failed product/term's page
   sequence. Keep other successful terms and products. Current code can still
   abort because one product is unconfigured or because every product had
   *some* failed term.

## Evidence

- Offline: historical focused selections cover parts of the CLI, transport,
  registry and manifest. No reconciled workflow-by-workflow pass on one
  artifact yet.
- Live: five BBK comparisons previously recorded in
  `checks/test_bbk_live_parity.py` (JQL, CQL, code search, author comments,
  repository grep).
- REST registry: 202 registered entries at `16b739a` (199 GET, 3 semantic
  POST; 7 binary entries), of which three are in `--catalog.operations`.
  These are local counts, not the required REST scope or a parity percentage.
  Verify route/metadata dispositions and permission exclusions separately.
