## Bitbucket Server 5.10.0 Environment Overrides

The target Bitbucket instance is **Bitbucket Server 5.10.0** (on-premise). Adhere to these constraints to prevent `404 Not Found` or `405 Method Not Allowed` errors from newer Data Center APIs.

### 1. Safe Native Subcommands
Compatible with stable `/rest/api/1.0/` and `/rest/branch-utils/1.0/` endpoints in version 5.10.0:
- **Repos & Projects:** `bkt repo list`, `bkt repo view`, `bkt repo create`, `bkt repo clone`
- **Branches & Tags:** `bkt branch list`, `bkt branch create`
- **Pull Requests:** `bkt pr list`, `bkt pr view`, `bkt pr create`, `bkt pr merge`, `bkt pr decline`, `bkt pr reopen`
- **Reviews & Comments:** `bkt pr comments`, `bkt pr approve`, `bkt pr tasks`
- **Admin & Hooks:** `bkt perms`, `bkt webhook`

### 2. Blocked Subcommands (Do Not Use)
Target Data Center 7.x+ or Cloud features absent in 5.10.0:
- `bkt status rate-limit`, `bkt repo default-reviewers`, `bkt pr checks` (Code Insights), and `bkt skill search`.

### 3. Fallback Procedure (`bkt api` + Local Spec)
For unsupported commands or missing endpoints:
1. Grep `references/bitbucket-5.10-rest.md` to confirm the exact `/rest/api/1.0/...` path, method, and parameters (such as `version` for PR updates/deletions).
2. Query via `bkt api` with `--json` and `--jq`:
   ```bash
   # Read a raw file at a branch/commit
   bkt api "/rest/api/1.0/projects/<KEY>/repos/<SLUG>/raw/<PATH>" --param at=master

   # Fetch a PR diff
   bkt api "/rest/api/1.0/projects/<KEY>/repos/<SLUG>/pull-requests/<ID>/diff" --json --jq '{truncated, files: [.diffs[].destination.toString]}'

   # Manual pagination
   bkt api "/rest/api/1.0/projects/<KEY>/repos/<SLUG>/commits" --param limit=100 --param start=0 --json
   ```

### 4. Key 5.10.0 API Behavior
- **Version Locking:** Modifications or deletions to PRs and comments require a `version` integer from a prior `GET` (otherwise returning HTTP `409 Conflict`).
- **Pagination:** Uses `start` and `limit` (default `25`); inspect `nextPageStart` when `isLastPage` is `false`.
- **Diffs:** `/diff` endpoints are unpaged and truncate large files (`"truncated": true`); re-query specific file paths `/diff/<path>` as needed.
