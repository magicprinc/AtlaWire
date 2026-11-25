# Live read-only consumer matrix — 2026-11-24

One self-hosted Jira 8.22 / Confluence / Bitbucket 5.10 deployment, read-only,
run as a demanding library consumer against the **installed artifact**, not the
source tree:

```
python -m pip install --target <target> dist/atlawire-0.9.0-py3-none-any.whl
set PYTHONPATH=<target>
python -P -B checks/live_consumer_matrix.py --live
```

The runner asserts `atlawire.__file__` under the target and resolves saved BBK
credentials through `atlawire.credentials`; it never prints a payload, host, or
token. Anchors (project, repository, space, issue, pull request) are discovered
by read-only listing calls, so the same script runs on any deployment.

## Result

| Group | Checks | Result |
| --- | ---: | --- |
| Bitbucket | 20 | all PASS |
| Confluence | 10 | all PASS |
| Jira | 13 | all PASS |
| Markdown and review | 8 | all PASS |
| Cross-repository search and grep | 3 | all PASS |
| **Total** | **54** | **PASS=54 FAIL=0** |

Timing: the whole run completes in well under a minute of server time; the two
slowest checks are cross-repository byte search over an archive (about 10 s) and
the one-call review packet (about 4 s).

## What each check verified

- **Bitbucket** — project and repository identity; default branch present in the
  branch listing; tree and directory listing; file read on the default branch and
  on a named branch; commit listing and commit detail share the same hash; commit
  changes; blame; tags; repository and dashboard pull requests; `pr_compact`
  agrees with the detail call; files, whole diff, per-path batch diff, comments,
  commits; all three whitespace modes accepted.
- **Confluence** — page identity; `document`/`markdown`/`storage` forms from one
  read with the single-form helper returning the same Markdown; children,
  comments, history, labels, attachments; space listing and space detail; space
  content rows with a `rows`/`truncated` envelope.
- **Jira** — issue identity; `document`/`markdown`/`wiki_markdown` forms plus a
  request-free `issue_url`; comments, changelog, transitions, remote links,
  watchers, votes, properties; reference data (projects, statuses, issue types);
  exact-key JQL; title batch; Markdown length and absence of NUL.
- **Markdown and review** — Confluence storage to Markdown, HTML and wiki
  conversion, `compact` and `compact_json` service-key removal, diff rendering;
  one-call review Markdown and the packet shape; `java_members`, `red_flags`,
  `changed_symbols`, and `file_links` returning `before`/`after`/`diff`.
- **Search** — index engine and bytes+archive engine both return rows across
  repositories; single-repository grep returns hits.

## Differential BBK comparison (same day)

`checks/test_bbk_live_parity.py` was run with fixtures discovered from the same
deployment, comparing real CLI subprocesses:

| Comparison | Result |
| --- | --- |
| Jira JQL ordered keys | match |
| Bitbucket indexed search triples | match |
| One-file repository grep hits | match |
| Confluence CQL ordered ids | inconclusive — the server's CQL index returns zero rows for every query, including a known page id |
| Jira author comments | inconclusive — no recent comment authored by the current user |

## Complaints raised by the consumer and resolved in this pass

1. **Diff whitespace was hard-coded.** BBK let the caller pass `whitespace`;
   AtlaWire always sent `ignore-all`. All three values (`ignore-all`,
   `ignore-trailing`, `ignore-none`) were confirmed live, and the parameter is
   now supported and validated in the typed calls and on the CLI. BBK's values
   were accepted by the server but never validated.
2. **Stale installed artifact.** The environment still had `atlawire 0.1.0.dev0`
   from an editable install. It was replaced with the built `0.9.0` wheel, so an
   agent invoking `atlawire` now runs the current code.

## Limits of this evidence

One deployment, one account, one project/space per product, default branch and
one pull request. It does not prove other versions, permissions, large scopes,
writes, or error paths; error paths are covered by the offline suite.
