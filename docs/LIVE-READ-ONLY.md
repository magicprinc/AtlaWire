# Read-only end-to-end checks

Use this runbook to verify the installed CLI on a target deployment. It does not
authorize writes, load tests, discovery outside the selected scopes, or credential
migration. The default offline test suite never runs these live checks.

## Run the nine-check gate

Run [checks/live_read_only.py](../checks/live_read_only.py) from the repository root
using the approved Python 3.15 installation. Supply the same three product URL/token
pairs used by the [quickstart](AGENT-QUICKSTART.md), plus the fixture variables below.
Inject credentials locally, not in command arguments or reports. Prefer tokens scoped
to the fixture project, space, and repository. Never test writes on real servers.

```shell
C:/Python315/python.exe -B checks/live_read_only.py --live
```

The runner refuses to start without `--live` and valid settings for all three products.
It uses at most nine CLI processes and 27 HTTP requests; `--timeout SECONDS` bounds
each process (5–300 seconds; default 30). Each child sees only its own product's
credentials and an allowlist of ordinary OS variables. The runner emits fixed labels
and categories, never captured output, settings, queries, IDs, or exception text.

| Check | Expected evidence |
| --- | --- |
| `jira.discovery` | Scoped JQL returns the known issue key within ten results |
| `jira.issue` | Returned issue has the expected key and readable fields |
| `jira.comments` | Expected comment ID and a nonblank body on a complete single page |
| `confluence.search_page` | Scoped CQL returns the known page ID within ten results |
| `confluence.page` | Expected page ID and nonblank storage body |
| `bitbucket.indexed_search` | Repository-scoped search highlights the expected Java path |
| `bitbucket.pull_request` | Expected PR ID, title, and state are readable |
| `bitbucket.pull_request_files` | Expected changed path is present |
| `bitbucket.java_file` | Exact bytes at the pinned commit match the independent SHA-256 |

| Fixture environment variable | Value |
| --- | --- |
| `ATLAWIRE_LIVE_JIRA_JQL` | Approved, narrow discovery query |
| `ATLAWIRE_LIVE_JIRA_ISSUE` | Independently checked issue key |
| `ATLAWIRE_LIVE_JIRA_COMMENT_ID` | Independently checked comment with a nonblank body; choose an issue whose visible thread fits one page |
| `ATLAWIRE_LIVE_CONFLUENCE_CQL` | Approved, narrow discovery query |
| `ATLAWIRE_LIVE_CONFLUENCE_PAGE_ID` | Independently checked page ID |
| `ATLAWIRE_LIVE_CONFLUENCE_MARKER` | Optional independently checked storage text |
| `ATLAWIRE_LIVE_BITBUCKET_REPO` | `PROJECT/slug` with indexed, read-only access |
| `ATLAWIRE_LIVE_BITBUCKET_SEARCH_QUERY` | Exact indexed term |
| `ATLAWIRE_LIVE_BITBUCKET_SEARCH_PATH` | Known indexed default-branch Java path |
| `ATLAWIRE_LIVE_BITBUCKET_PR_ID` | Independently checked PR ID |
| `ATLAWIRE_LIVE_BITBUCKET_PR_PATH` | Expected changed path |
| `ATLAWIRE_LIVE_BITBUCKET_FILE_PATH` | Java path at the pinned commit |
| `ATLAWIRE_LIVE_BITBUCKET_FILE_REF` | Full 40-hex commit ID |
| `ATLAWIRE_LIVE_BITBUCKET_FILE_SHA256` | SHA-256 of those bytes, obtained independently of AtlaWire |

Exit `0` means all nine checks passed. Exit `1` means a check failed or timed out.
Exit `2` means configuration or arguments are absent or invalid. No skipped check
counts as a pass.

## Verify pagination and failures separately

The bounded gate does not prove pagination. Pick a scoped fixture that crosses a real
server page boundary. Independently read the expected IDs in server order, including
the next page, and compare them with the CLI result. Use offline fixtures for induced
later-page failure and cap exhaustion; those paths must fail without partial stdout.

Record only the tested revision, sanitized command scope, fixed result labels, and
counts. A single valid page is not evidence for all pagers. Use the
[feedback template](FEEDBACK.md) for failures; do not attach payloads or raw logs.
