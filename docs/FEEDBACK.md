# Local feedback template

Use this single template for friction found while doing real Java work with
AtlaWire. There is no separate pilot roster and no recruiting step: the real work
that reveals the problem is the pilot. Copy the block into the task's local
project directory; do not commit tokens, raw logs, payloads, or internal URLs.

## Stop rules

- **P0 — stop using the affected path.** Examples: credentials reach the wrong
  destination, a write occurs, a failed or partial read is reported as success,
  one product's data is presented as another product's, or a check claims
  pagination it did not observe. Stop, preserve only sanitized evidence, and
  notify the primary/owner before trying another route.
- **P1 — fix before expansion.** Examples: a cap or failed read is mistaken for
  an empty result, the discovery lane consistently misses the right product, a
  documented recipe cannot complete the task, or an error is indistinguishable
  from a successful empty answer. Do not widen usage or claim readiness until the
  cause is fixed and rechecked.
- **P2 — backlog.** Ergonomics, wording, output shape, or a missing convenience
  with a safe workaround. Continue using the documented bounded path.

A passing smoke check is not a readiness claim. Missing or skipped checks are
evidence gaps; say so explicitly.

## Template

```text
Date:
Type (bug / feature request):
Agent / session:
Task and Java term or symbol:
Products and lanes used (Jira / Confluence / Bitbucket):
Commands (sanitized; no tokens, raw URLs, or payloads):
Observed outcome:
Expected outcome and why:
Failure category (missing config / CLI failure / timeout / invalid output /
wrong oracle / cap or partial read / discovery miss / docs):
Caps hit or reads that failed (exact command and limit, no raw output):
Stable references used (issue key, page ID/version, commit SHA, PR ID, path):
Was the code actually opened at a pinned ref? (yes/no):
What the issue/page claimed vs what the code proved:
Pagination claimed? (yes/no; if yes, link the separate scoped evidence):
Sanitized evidence (counts, hashes, server-side predicate only):
Impact on the task:
Workaround tried:
Class (P0 / P1 / P2):
Owner action requested:
```

## Required evidence

- Keep product output out of the report. A fixed check name and failure category
  are enough to reproduce the lane; raw stdout/stderr stays local.
- Cite stable references: Jira issue key, Confluence page ID and version,
  Bitbucket PR ID, repository path, and the pinned commit/ref that was opened.
- Separate claims from code. A Jira description, Confluence note, PR title, or
  search snippet is a claim; only the opened file/diff is code evidence.
- If a pager is claimed to work, attach a separate scoped read-only run with a
  sanitized server-side oracle (expected count, IDs/order, terminal-page
  behavior). `checks/live_read_only.py` is a single bounded smoke check and is
  not pagination evidence.
- No write tests against real servers are authorized. Report findings from
  read-only work only; never create, copy, store, or print real credentials.
- If Bitbucket indexed search is unavailable, record the lane as failed or
  unverified. Name the working `bbk` search or scoped repository browse used
  instead; do not present a different content search as equivalent.

## Weekly handling (local, no ceremony)

Group open entries by class. Fix P1 causes before adding new workflows or users.
Close a bug with the command, scope, and observed recheck result. For feature
requests, record the decision and what real tasks would justify revisiting it.
