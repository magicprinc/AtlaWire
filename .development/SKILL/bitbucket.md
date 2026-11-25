# Bitbucket MCP: install and use (DSH / Command Code)

Audience: a coding agent running in **DSH** or **Command Code** on this Windows machine.
Goal: use the same **local stdio** Bitbucket MCP server as OpenCode, with the same credentials, without changing another agent’s config.

> **Execution boundary.** This file is an instruction for the target agent. The agent that wrote it only **read** the OpenCode, DSH and Command Code configs to document them; it did not modify them and must not modify them. The target agent owns its own config edit after user approval. Config observations are a read-only snapshot from 2026-11-16; re-read the live file before editing.

---

## 0. What “installed locally” means here

**Locally = the server package is already on this PC and is started from an absolute on-disk path. It is not fetched from the web on each invocation.**

Every client runs `node <absolute path>\build\index.js`. There is no `npx`, no `npm exec`, no `@latest`, and no package download at MCP startup. The only network traffic is the Bitbucket API calls to `https://bitbucket.example.com`.

Verified state:

| Item | Value |
|---|---|
| Package | `@nexus2520/bitbucket-mcp-server@4.0.0` |
| Package location | `C:\Users\magic\AppData\Roaming\npm\node_modules\@nexus2520\bitbucket-mcp-server` |
| Entry point | `...\build\index.js` |
| Transport | local **stdio** process, not HTTP and not a remote MCP |
| Node requirement | Node.js **22 or newer** |
| Bitbucket base URL | `https://bitbucket.example.com` |
| Username | `a.fink` |
| OpenCode | configured as `"type": "local"`, command `node .../build/index.js` |
| DSH | configured as `transport: stdio`, `node.exe .../build/index.js` |
| Command Code | **not configured** (read-only snapshot; re-check live) |

The package is in the **global npm prefix** (`C:\Users\magic\AppData\Roaming\npm\node_modules`), not in a project’s `node_modules`. That is still “on this PC” and is intentional: the config pins the exact `build/index.js` path instead of `npx -y`, so no registry lookup or download happens when the MCP server starts, and a new npm release cannot silently change the server between sessions.

Do not replace the command with `npx`, `npm exec`, `@latest`, or any package name that Node would resolve remotely. If an update is wanted, install the exact version explicitly with `npm install -g ...@<version>`, verify it, and restart the client.

Verification commands:

```powershell
node --version
npm ls -g @nexus2520/bitbucket-mcp-server --depth=0
Test-Path "$env:APPDATA\npm\node_modules\@nexus2520\bitbucket-mcp-server\build\index.js"
```

Expected:

- Node `v22.x` or newer.
- `@nexus2520/bitbucket-mcp-server@4.0.0`.
- `True`.

Confirm the active OpenCode command is local (this prints no token):

```powershell
$b = (Get-Content "$env:USERPROFILE\.config\opencode\opencode.json" -Raw | ConvertFrom-Json).mcp.servers.bitbucket
$b.type
$b.command
```

Expected: `local` and `[ "node", "C:/Users/magic/AppData/Roaming/npm/node_modules/@nexus2520/bitbucket-mcp-server/build/index.js" ]`. No `npx`, no `@latest`.

For DSH, inspect only the `command`/`args` lines of the `mcp-bitbucket` block; they must point to `C:/Program Files/nodejs/node.exe` plus the absolute `build/index.js` path.

If the package is missing, install it only after user approval:

```powershell
npm install -g @nexus2520/bitbucket-mcp-server@4.0.0
```

Do not use `npx -y @nexus2520/bitbucket-mcp-server` in the MCP config.

---

## 1. Credential: use the existing token, do not duplicate it

The user explicitly authorized the target agent to use the same Bitbucket token as OpenCode.

**Do not print the token, paste it into chat, commit it, put it in a URL, or write it into this document.** Read it at install time from the owner-approved OpenCode config:

```powershell
$opencode = Get-Content "$env:USERPROFILE\.config\opencode\opencode.json" -Raw | ConvertFrom-Json
$token = $opencode.mcp.servers.bitbucket.environment.BITBUCKET_TOKEN
if (-not $token) { throw "BITBUCKET_TOKEN not found in the OpenCode config" }
```

The token is not reproduced here by design. If the read is blocked by a sandbox or policy, ask the user to provide it through the approved secret channel; do not guess and do not fall back to a public token.

Server environment:

```text
BITBUCKET_BASE_URL=https://bitbucket.example.com
BITBUCKET_USERNAME=a.fink
BITBUCKET_TOKEN=<read from the existing config>
BITBUCKET_READ_ONLY=false
```

`BITBUCKET_READ_ONLY=false` matches the existing OpenCode/DSH setup and allows comments, approvals and merges. For an agent that only needs to review, set `true`; it removes every mutating tool from `tools/list` and dispatch.

---

## 2. Configure Command Code (only if you are Command Code)

Check first; do not duplicate:

```powershell
command-code mcp list | Select-String bitbucket
```

If `bitbucket` is absent, build the JSON and add it at **user** scope:

```powershell
$opencode = Get-Content "$env:USERPROFILE\.config\opencode\opencode.json" -Raw | ConvertFrom-Json
$token = $opencode.mcp.servers.bitbucket.environment.BITBUCKET_TOKEN
if (-not $token) { throw "BITBUCKET_TOKEN not found" }

$config = @{
  transport = "stdio"
  command   = "node"
  args      = @("C:/Users/magic/AppData/Roaming/npm/node_modules/@nexus2520/bitbucket-mcp-server/build/index.js")
  env       = @{
    BITBUCKET_BASE_URL  = "https://bitbucket.example.com"
    BITBUCKET_USERNAME  = "a.fink"
    BITBUCKET_TOKEN     = $token
    BITBUCKET_READ_ONLY = "false"
  }
} | ConvertTo-Json -Compress -Depth 5

command-code mcp add-json bitbucket $config --scope user
```

Use `command-code` or `cmdc`, **not** `cmd`: in PowerShell `cmd` resolves to `cmd.exe`, not the Command Code CLI.

Verify:

```powershell
command-code mcp list | Select-String bitbucket
$m = (Get-Content "$env:USERPROFILE\.commandcode\mcp.json" -Raw | ConvertFrom-Json).mcpServers.bitbucket
$m.transport
$m.command
$m.args
```

Expected: `bitbucket`, `stdio`, `user`, enabled; `node`; the absolute local `build/index.js` path. Do not print `$m.env`; it contains the token.

`add-json` places the JSON (including the token) in the process command line. If that exposure is unacceptable, edit `mcp.json` directly instead; never echo the token.

Fallback if `add-json` is unavailable: add this key inside `mcpServers` in `C:\Users\magic\.commandcode\mcp.json`, preserving valid JSON and existing entries:

```json
"bitbucket": {
  "transport": "stdio",
  "enabled": true,
  "command": "node",
  "args": [
    "C:/Users/magic/AppData/Roaming/npm/node_modules/@nexus2520/bitbucket-mcp-server/build/index.js"
  ],
  "env": {
    "BITBUCKET_BASE_URL": "https://bitbucket.example.com",
    "BITBUCKET_USERNAME": "a.fink",
    "BITBUCKET_TOKEN": "<read from the existing OpenCode config; do not paste into this file>",
    "BITBUCKET_READ_ONLY": "false"
  }
}
```

Then validate:

```powershell
Get-Content "$env:USERPROFILE\.commandcode\mcp.json" -Raw | ConvertFrom-Json | Out-Null
```

Restart Command Code after the edit.

---

## 3. DSH: verify, do not duplicate

The DSH web profile already contains the server in:

`C:\Users\magic\.dsh\profiles\web\cordis.patch.yml`

Expected block:

```yaml
- insert:
    - id: mcp-bitbucket
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: bitbucket
        transport: stdio
        command: 'C:/Program Files/nodejs/node.exe'
        args:
          - 'C:/Users/magic/AppData/Roaming/npm/node_modules/@nexus2520/bitbucket-mcp-server/build/index.js'
        env:
          BITBUCKET_BASE_URL: 'https://bitbucket.example.com'
          BITBUCKET_USERNAME: 'a.fink'
          BITBUCKET_TOKEN: '<existing value>'
          BITBUCKET_READ_ONLY: 'false'
```

If it is present, change nothing. If it is missing, add exactly one `insert:` block; the DSH patch layer requires `insert:` for a new plugin (a bare `id:` only overrides an existing plugin). Do not paste the token into chat or logs. The headless DSH profile currently has an empty patch file; add the block there only if the user actually uses that profile.

---

## 4. OpenCode

Already configured as the reference. Do not edit another agent’s config; this section is informational only.

---

## 5. Tool surface

The server exposes 25 tools. The ones used most for PR work:

| Task | Tool |
|---|---|
| List PRs | `list_pull_requests` |
| PR metadata, comments, file list | `get_pull_request` |
| **PR diff** | `get_pull_request_diff` |
| PR commits | `list_pr_commits` |
| Commit diff | `get_commit_detail` |
| Inline/general comment | `add_comment` / `manage_comment` |
| Approve / request changes | `set_review_status` |
| Merge / decline | `merge_pull_request` / `decline_pull_request` |
| Read file / search repo | `get_file_content` / `grep` / `search_code` |

Tool names carry a client prefix. Match by the suffix: `get_pull_request_diff`, `list_pull_requests`, etc.

Typical PR flow:

1. `list_pull_requests` with `workspace` (project key), `repository` (repo slug), `state: "OPEN"`.
2. `get_pull_request` with `pull_request_id` for metadata, comments and the changed-file list.
3. `get_pull_request_diff` for the actual patch.
4. `add_comment` for findings; use `get_pull_request_diff` line numbers if inline comments are needed.
5. `set_review_status` only when the user asks to approve or request changes.

Do not mutate a PR (`add_comment`, `set_review_status`, `merge_pull_request`, `decline_pull_request`) without explicit user approval, even when `BITBUCKET_READ_ONLY=false`.

---

## 6. PR diff: plain text in 4.0.0, JSON only on old servers

Quick answer:

- Want the patch? Call `get_pull_request_diff` → **plain unified diff text**.
- Want the changed-file list? Call `get_pull_request` → **JSON** `file_changes` (no patch bodies).
- Got JSON with `files[].hunks[].lines[]` from `get_pull_request_diff`? That is an **old 2.x server**, not this install.

**Verified: the claim “PR diff comes as JSON and must be converted” is not true for the installed 4.0.0 server.** It was true for the old 2.x server.

Evidence:

- `build/handlers/review-handlers.js` (`handleGetPullRequestDiff`) sends `Accept: text/plain` and `responseType: 'text'`, then returns the raw diff through `textContent(...)`.
- `build/formatting/respond.js` defines `textContent` as `{ content: [{ type: 'text', text }] }`.
- `README.md` says: `get_pull_request_diff` — raw unified diff text.
- `CHANGELOG.md` v3.0.0: “Diffs are raw unified diff text (`Accept: text/plain`) … Applies to `get_pull_request_diff` and `get_commit_detail`.”

So on this machine:

- `get_pull_request_diff` returns a text block beginning with `PR #<id> diff (<n> files)` followed by `diff --git ...` sections.
- Do **not** parse it as JSON and do **not** convert it.
- The MCP **envelope** is still JSON-RPC: the tool result is `{ content: [{ type: "text", text: "<unified diff>" }] }`. The diff is the `text` field. Do not `JSON.parse` that text.

### 6.1 Which call returned JSON?

| Call | Response | Contains the patch? |
|---|---|---|
| `get_pull_request` (default `include_file_changes: true`) | JSON metadata + `file_changes` list of `{ path, status, old_path }` | **No** — changed-file list only |
| `get_pull_request_diff` | Plain unified diff text | Yes |
| `get_commit_detail` | Plain unified diff text; `detail: "files"` returns a JSON file list | Yes / no |
| Old `get_pull_request_diff` (< 3.0.0) | JSON `files[].hunks[].lines[]` | Yes, but needs conversion |
| Raw REST API without `Accept: text/plain` | JSON | Yes, request `text/plain` or convert |

Diagnose by shape:

- JSON with `file_changes` / `path` / `status` / `old_path` and **no** `hunks` → `get_pull_request`. This is **PR files / PR changes**, not a diff. Call `get_pull_request_diff` for the patch.
- JSON with `files[].hunks[].lines[]` → an old 2.x server’s diff response. Convert or upgrade (section 6.2).
- JSON wrapper with `content[0].text` containing `diff --git ...` → the normal MCP envelope around plain text. Use `content[0].text` unchanged.

`get_pull_request` never embeds diff bodies in 4.0.0. `include_file_changes` only toggles the changed-file list. If you need one file’s patch, call `get_pull_request_diff` with `file_path=<path>`.

If you use the raw Bitbucket REST API instead of the MCP tool, the API may return JSON unless you send `Accept: text/plain`. Prefer `get_pull_request_diff`; if you must call the API, request `text/plain` rather than converting JSON.

### 6.2 If you actually have an old 2.x server

Check the version:

```powershell
node -p "require('C:/Users/magic/AppData/Roaming/npm/node_modules/@nexus2520/bitbucket-mcp-server/package.json').version"
```

If it is below `3.0.0`, either upgrade to 4.0.0 (with user approval) or convert the structured JSON. The 2.x schema is:

```json
{
  "files": [
    {
      "file_path": "src/Button.res",
      "old_path": null,
      "status": "modified",
      "hunks": [
        {
          "source_start": 27,
          "source_span": 6,
          "destination_start": 27,
          "destination_span": 7,
          "lines": [
            { "type": "CONTEXT", "content": "  old context" },
            { "type": "REMOVED", "content": "  oldFunction()" },
            { "type": "ADDED", "content": "  newFunction()" }
          ]
        }
      ]
    }
  ]
}
```

Converter (Node.js; only for the old JSON shape):

```js
function jsonDiffToUnified(payload) {
  const files = payload?.files ?? [];
  const out = [];
  for (const file of files) {
    const status = String(file.status ?? "").toLowerCase();
    const isAdded = status === "added";
    const isDeleted = status === "deleted" || status === "removed";
    const oldPath = isAdded ? file.file_path : (file.old_path ?? file.file_path);
    const newPath = file.file_path;

    out.push(`diff --git a/${oldPath} b/${newPath}`);
    out.push(isAdded ? "--- /dev/null" : `--- a/${oldPath}`);
    out.push(isDeleted ? "+++ /dev/null" : `+++ b/${newPath}`);

    if (!file.hunks?.length) {
      out.push(`Binary files a/${oldPath} and b/${newPath} differ`);
      continue;
    }

    for (const hunk of file.hunks) {
      out.push(
        `@@ -${hunk.source_start ?? 0},${hunk.source_span ?? 0} ` +
          `+${hunk.destination_start ?? 0},${hunk.destination_span ?? 0} @@`,
      );
      for (const line of hunk.lines ?? []) {
        const prefix =
          line.type === "ADDED" ? "+" : line.type === "REMOVED" ? "-" : " ";
        out.push(prefix + line.content);
      }
    }
  }
  return out.join("\n") + "\n";
}
```

Wrapper that handles the v4 text, the MCP envelope, and the old JSON:

```js
function toUnifiedDiff(result) {
  // v4: already plain text
  if (typeof result === "string") return result;

  // MCP envelope
  const text = result?.content?.[0]?.text;
  if (typeof text === "string") {
    try {
      const parsed = JSON.parse(text);
      if (parsed?.files) return jsonDiffToUnified(parsed);
    } catch {
      // not JSON: the text itself is the unified diff
    }
    return text;
  }

  // old JSON payload
  if (result?.files) return jsonDiffToUnified(result);

  throw new Error("Unrecognized diff payload");
}
```

Do not apply this on 4.0.0. The first branch returns the text unchanged.

---

## 7. Verification checklist

| Check | Command or action | Pass condition |
|---|---|---|
| Node version | `node --version` | `v22` or newer |
| Package version | `npm ls -g @nexus2520/bitbucket-mcp-server --depth=0` | `4.0.0` |
| Entry point | `Test-Path ...\build\index.js` | `True` |
| Local transport | config read | `type: local` / `transport: stdio`; no URL |
| Command Code config | `command-code mcp list` | `bitbucket` stdio user enabled |
| Auth | `get_pull_request` on a known PR | JSON metadata, no 401/403 |
| PR file list | `get_pull_request` | JSON `file_changes`; no `hunks` |
| Diff shape | `get_pull_request_diff` | text starting `PR #... diff` and `diff --git` |
| No JSON diff | inspect `get_pull_request_diff` | no `"files": [...]` / `"hunks": [...]` on 4.0.0 |

If `get_pull_request_diff` returns JSON with `files`/`hunks`, the server is older than 3.0.0 or a different server is running. Check the version and fix the server before adding conversion code. If `get_pull_request` returns JSON `file_changes`, that is the PR file list — call `get_pull_request_diff` for the patch.

---

## 8. Security and limits

- The token has write access because `BITBUCKET_READ_ONLY=false`. Prefer `true` for review-only agents; use `false` only when the user wants comments/approvals/merges.
- Never print the token, include it in a URL, commit it, or send it to an external service.
- The server talks to the internal Bitbucket host only. Do not proxy it through a public endpoint.
- Diffs and source code are internal data. Do not paste them into public issues, external chats, or third-party services.
- PR metadata and diffs can be large; use `file_path`, `include_patterns`/`exclude_patterns`, and `context_lines` to scope, and read truncation markers.
- The graph/tool result is evidence, not proof: verify surprising findings against the source.

---

## 9. Rollback

- **Command Code:** `command-code mcp remove bitbucket --scope user`, then restart. Or remove the key from `~/.commandcode/mcp.json` and validate.
- **DSH:** remove the `mcp-bitbucket` `insert:` block from the profile patch and restart.
- Do not run `npm uninstall -g @nexus2520/bitbucket-mcp-server` while OpenCode or DSH is using it; stop those clients first and confirm with the user.

---

## 10. Short agent checklist

1. Confirm the package is on disk at `4.0.0` and Node is 22+.
2. Confirm the client command is `node` plus the absolute local `build/index.js` path; no `npx`, `npm exec`, or `@latest`.
3. Read the token from the existing owner-approved config; never print it.
4. Configure **only your own** client: Command Code if absent; DSH only if the block is missing.
5. Restart the client and verify `mcp list` / tool visibility.
6. Call `get_pull_request` on a known PR to confirm auth.
7. Call `get_pull_request_diff`; expect plain unified diff text on 4.0.0. Do not convert it.
8. If you see JSON `files`/`hunks`, the server is old; check the version before writing a converter.
9. Report what changed, the version, the verification result, and any check you skipped.
