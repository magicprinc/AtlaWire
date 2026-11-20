# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
intends to use [Semantic Versioning](https://semver.org/spec/v2.0.0.html) once releases begin.
No version has been released yet.

## [Unreleased]

### Added

- Initial repository design documentation: a pre-implementation `README.md` describing goals,
  non-goals, security boundaries, and the quality/testing plan, plus a dependency-ordered
  `TODO.md`.
- `atlawire repos PROJECT` lists a Bitbucket project's repositories with `bbk`-compatible TSV
  or JSON output. It follows server-provided pagination and fails without printing partial rows.
- `atlawire projects` lists visible Bitbucket projects with `bbk`-compatible TSV or JSON
  including optional descriptions and server-provided links.
- `atlawire pr PROJECT/SLUG PR_ID [show]` retrieves a pull request as raw Bitbucket JSON.
- `atlawire pr PROJECT/SLUG PR_ID files` lists changed paths and rejects responses that
  reach the server's reported cap.
- `atlawire pr PROJECT/SLUG PR_ID comments` reads paginated comment activity as TSV or JSON.
- `atlawire pr PROJECT/SLUG PR_ID diff --json` retrieves Bitbucket diff JSON and rejects
  declared truncation.
- `atlawire pr PROJECT/SLUG PR_ID diff` shows a terminal-safe review, not a patch to apply.
- `atlawire file` and `pr … file` read bounded UTF-8 source, preserving bytes and selecting
  the correct repository and commit for forked pull requests.
- `atlawire branches` and `commits` list repository history with fixed filters across
  cursor requests and legacy-compatible TSV or JSON.
- `atlawire issue KEY_OR_URL` retrieves Jira issue JSON, including rendered fields when returned.
- `atlawire issue KEY_OR_URL --markdown` renders issue details and comments while keeping JSON
  as the default. Missing or ambiguous rendered comments fall back to raw text.
- `atlawire jql QUERY` searches Jira with bounded pagination and `bbk`-compatible TSV and JSON rows.
- `atlawire mine` lists the current user's issues; `atlawire statuses` lists visible status names.
- `atlawire page ID_OR_URL` retrieves Confluence page JSON, including the storage body.
- `atlawire page ID_OR_URL --markdown` converts stored Confluence content without extra
  requests, preserving basic document structure and code macros.
- `atlawire cql QUERY` searches Confluence with bounded pagination and TSV or JSON output.
- `atlawire spaces` lists Confluence spaces with `bbk`-compatible TSV columns or JSON output.
- `atlawire children ID_OR_URL` lists direct child pages with their version numbers.

### Fixed

- Repository TSV escapes data that would otherwise split a row or change terminal output.

### Changed

- Replaced the inherited Java-era `.editorconfig` and `.gitignore` with Python-oriented
  versions (4-space indent, line length 88, Python caches, virtual environments, coverage and
  local database artifacts).
- Added the initial Python package, Click entry point, and smoke tests for the module and
  console-script entry points.

### Removed

- Marketing-style README claims, non-executable quickstart commands, duplicated quality gates,
  and a "License TBD" statement that contradicted the Apache-2.0 `LICENSE` file present in the
  repository.
