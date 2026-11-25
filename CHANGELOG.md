# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
intends to use [Semantic Versioning](https://semver.org/spec/v2.0.0.html) once releases begin.
No version has been released yet.

Changes below cover the unreleased read-only surface: the initial command batch and the
subsequent agent-facing batch (the latter spans commits `2960a43..a4efee1`).

## [Unreleased]

### Added

- `whitespace` on every diff reader (`get_pull_request_diff`,
  `get_pull_request_diffs`, `get_pull_request_diff_text`, `get_commit_diff`,
  `get_commit_diff_text`) and `--whitespace` on `pr ... diff` and
  `commit-diff`. BBK exposed this parameter; AtlaWire now supports the same
  `ignore-all` / `ignore-trailing` / `ignore-none` values and rejects others
  before any request. All three were confirmed accepted by the live server.
- `atlawire.markdown` as a public module (`compact`, `compact_json`,
  `confluence_to_md`, `html_to_md`, `wiki_to_md`, `jira_issue_to_md`,
  `render_diff`, `page_to_md`) and the review helpers `file_links`,
  `java_members`, `red_flags`, `changed_symbols`, plus the one-call
  `pr_review.review(...)`.
- `checks/live_consumer_matrix.py`: a live read-only consumer matrix that
  discovers anchors, verifies 54 capabilities semantically, and reports
  PASS/FAIL without printing payloads or identifiers.
- `atlawire repo-search` and `repo_search.search_repositories`: cross-repository
  search with an `index` engine (one plugin call), a `bytes` engine (regex over
  default branches), and `fetch="archive"` (one zip per repository, with
  zip-slip rejection and per-entry/total caps). `engine="auto"` picks a
  predictable default. One live run returned rows from multiple repositories;
  archive mode was 2.8x faster than per-file reads.
- `--json` on every command that prints JSON. It is a no-op where JSON is the
  only output; `file --json` and `page-url --json` add real projections, and
  `issue`/`page` refuse to combine it with another format.
- `confluence.page_forms` and `jira.issue_forms`: JSON, raw source, and Markdown
  from a single read.
- `confluence.get_page_storage`, `get_page_title`, `get_page_markdown`;
  `jira.issue_url` and `get_issue_markdown`.
- `bitbucket.pr_compact` and `bitbucket.get_pull_request_diffs` (batch diffs in
  request order).
- Markdown: a plain link now keeps its destination as inert `label (url)` text,
  and runs of blank lines collapse outside fenced code. Measured on 55 live Jira
  descriptions and 21 Confluence pages: more URLs kept, zero active HTML, fewer
  blank lines than before.
- `repo_grep` reads every file of a repository through one session instead of
  opening a new connection per file.

**Initial read-only surface**

- Flat, read-only CLI and Python library for Jira, Confluence, and Bitbucket: Bitbucket
  projects, repositories, files, directories, blame, branches, commits, commit changes/diffs,
  pull requests/files/comments/commits/diffs and indexed code search; Jira JQL search, current
  user issues, issue cards, comments, statuses, and transitions; Confluence page reads, CQL
  search, spaces, and child pages; plus `whoami`, `find`, and the offline `operations` catalog.
- `atlawire --catalog` and `--describe <operation-id>` describe commands and registered reads
  without credentials or network; `atlawire read <id>` runs one registered operation and prints
  a JSON envelope.
- Standard REST reads through `atlassian-python-api==5.0.5`: `api-get`, `api-request`,
  `client_for`, `get_json`, `get_json_with_status`, `request_json`, `request_json_with_status`,
  and `download_to_file`. Only standard non-administrative GETs and four documented read-only
  POSTs are accepted; mutating and administrative routes are rejected before any request.
- Public `atlawire.http.new_session` factory with explicit redirect, environment, timeout, and
  token policy; `bearer_session` remains the strict read transport.

**Agent-facing batch**

- Structured `AtlaWireError` metadata (`product`, `operation`, `category`, `http_status`,
  `method`, `path`) with bounded, credential-free messages.
- Raw JQL and raw projections: `jira.search_raw`, `atlawire jql --fields/--expand`, and
  `atlawire issue --expand`; `atlawire cql --expand` and `atlawire page --expand` print one
  unprojected server document.
- `jira.titles` maps issue keys to summaries in batches of 50 (`key in (...)`) to keep request
  URLs bounded; `jira.resolve_user` resolves a login/display name to one identity and fails on
  ambiguity instead of guessing.
- Full-walk readers: `list_issue_worklogs`, `list_issue_changelog`, `search_all_issues`,
  `list_all_repositories`, and `get_repository_archive` (zip/tar/tar.gz/tgz, 64 MiB
  default byte bound). A budget or metadata inconsistency raises instead of returning a
  partial list.
- Jira issue subresource readers with flat projections: votes, watchers, subtasks, one comment,
  one worklog, issue properties/property, and issue link; exposed as `issue-votes`,
  `issue-watchers`, `issue-subtasks`, `issue-comment`, `issue-worklog`, `issue-properties`,
  `issue-property`, `issue-link` with `--json` (projection, default) or `--raw`.
- Bitbucket repository/PR readers: `get_project`, `get_repository`, `get_default_branch`,
  `get_repository_changes`, `list_commit_comments`, `get_commit_comment`,
  `list_repository_participants`, `list_repository_forks`, `get_related_repositories`; CLI
  commands `project`, `repository`, `default-branch`, `repo-changes`, `commit-comments`,
  `commit-comment`, `repo-participants`, `repo-forks`, `related-repos` with `--json`/`--raw`.
- Confluence space readers: `get_space` (five stable fields), `list_space_content`
  (`rows` + `truncated`), and the `space` / `space-content` commands with `--raw`.
- Truncation and completeness metadata instead of a bare list where a cap can hide rows:
  `list_issue_comments_with_metadata` (`rows`/`truncated`/`total`), `search_issues_with_metadata`,
  `search_all_issues_with_metadata`, `list_children_with_metadata`,
  `get_page_comments_with_metadata`, `get_page_attachments_with_metadata`,
  `list_tags_with_metadata` (`tags`/`limit`/`complete`), `list_commits_with_metadata`
  (`commits`/`limit`/`complete`), and `scan_repository_extensions_report`
  (`rows`/`complete`/`repositories_scanned`/`repositories_total`/`reason`).
- Agent-facing CLI aliases: `grep` (`grep-repo`), `scan` (`scan-extension`), `pr-files`,
  `pr-comments`, and `selftest` (`whoami` probe under the BBK name).
- Author filters on Bitbucket reads: `list_pull_requests(author=..., direction=...)`
  (server participant filter) and `list_commits(author=...)` (exact git author name,
  matched client-side while paging).
- `issue-comments --limit` now narrows the server request (`maxResults`) and reports a truncated
  thread as `{rows, truncated, total}` with a stderr note instead of silently trimming rows.
- Live read-only E2E and parameter-matrix checks under `checks/` (`e2e_bbk_*`, `e2e_param_matrix*`,
  `e2e_semantic_live.py`) with a short report in `checks/e2e_param_matrix_report.md`.

### Fixed

- A truncated or trailer-less gzip member is now one transport error on every
  read path: the SDK JSON reader, the SDK file download, and the text reader.
  Previously the SDK published a partial file with a normal receipt.
- The documented read-only client no longer exposes mutating library methods:
  `open_pull_request`, `reopen_pull_request`, `attach_file`, `attach_content`,
  the permission grants, `user_deactivate`, `tempo_timesheets_write_worklog`
  and `trigger_pipeline` are refused alongside the raw transport verbs.
- `read-operation` prints the same JSON `validation_error` envelope and exit
  code as the canonical `read` command instead of a legacy text error.
- `pr-review` names every shortened check list in `checks.truncated` and sets
  `profile.partial`; `checks.commits` and `checks.files_total` report the packet
  totals, and `diff.counts_complete` compares the changed list with the diff in
  both directions.
- `pr-review` rejects an oversized pull request id in a URL as a usage error
  instead of raising an uncaught `ValueError`.
- Repository grep no longer reports `truncated` when a file holds exactly the
  remaining hit budget on the last eligible file.
- A missing or malformed packaged `manifest.json` is now a fatal error instead
  of silently shrinking the advertised registry.
- Confluence and Jira Markdown conversion no longer drops link destinations, images, user
  mentions, or macro parameters; plain XHTML links and attachment macro parameters are preserved.
- Confluence paged CQL sends the correct space key.
- Repository grep handles its cooperative timeout budget and reports truthful
  `status`/`truncated`/`complete` instead of an incomplete list that looks complete.
- Jira search uses one field set for short rows and reports truncation when a known `total`
  exceeds the rows or the limit was reached without a `total`; a later page that omits `total`
  is accepted.
- `last-modified` resolves the requested ref correctly before the request.
- Bitbucket file reads accept the media type the server derives from the stored file
  (for example `text/markdown`) and reject only a JSON error document.
- Credential echo and percent-encoded administrative paths are rejected on every SDK path.
- Jira reads accept responses without `total` without claiming completeness, and a moved issue's
  canonical key is allowed after the move.
- Jira comment limits now drive the server request instead of trimming a fully read page.
- The previous read batch keeps its safety fixes: HTTP 206 partial responses are rejected, JSON is
  capped at 8 MiB after decompression, cursor-paged Bitbucket reads validate echoed `start`/`size`,
  and duplicate identities or contradictory totals fail instead of publishing partial rows.

### Changed

- `tools/build_read_manifest.py` reads the live `.development/<product>/mapping-*.json`
  inputs again and supports `--check`/`--output`; the committed manifest matches a
  fresh regeneration byte for byte.
- Ruff configuration is now committed in `pyproject.toml`: the S rule set is
  enabled, with per-file ignores only for tests and live checks.
- Jira, Confluence, and Bitbucket reads go through `atlassian-python-api==5.0.5` with guarded
  responses; the shared HTTP transport remains for functions that pin their own `requests` calls.
- The test suite was rewritten specification-first; the legacy suite was archived before the
  rewrite.
- Bitbucket file content-type handling was relaxed while keeping the 1 MiB text bound and unsafe
  control rejection.

### Removed

- `atlawire.facade.AtlaWire` and `atlawire.facade`: the second registry is gone.
  The package root still exports `AtlaWireError`; the two supported surfaces are
  the CLI and the typed product modules.
- Unused direct runtime dependencies on `keyring` and `platformdirs`.
- Marketing-style README claims, non-executable quickstart commands, duplicated quality gates,
  and a "License TBD" statement that contradicted the Apache-2.0 `LICENSE` file present in the
  repository.
