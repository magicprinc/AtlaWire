# Bitbucket Server 5.10.0 — REST API knowledge base

Source `bitbucket-5.10-rest.html` (794,012 bytes, sha256 `74219748de00f68d`) →
`pandoc -f html -t gfm --wrap=none` → cleaned (JS toggles, div/span noise, hard breaks) → split by section.

**125 paths** in **41 resource files**. The original split had 45 files and 424,215 bytes
(raw Markdown was 625,366 bytes).

This is the documented 5.10.0 core `/rest/api/1.0/` reference. It does not establish whether
an installation exposes code search or other endpoints through a plugin or extension.

## Orientation

| file | lines | bytes |
|---|---|---|
| [Getting started](00-getting-started.md) | 80 | 5,054 |
| [Authentication](01-authentication.md) | 110 | 4,404 |
| [Path index](02-index.md) | 543 | 25,753 |

## Endpoints by resource

| resource | file | paths | bytes |
|---|---|---|---|
| `admin--cluster` | [Reference](admin--cluster.md) | 1 | 1,091 |
| `admin--groups` | [Reference](admin--groups.md) | 6 | 11,686 |
| `admin--license` | [Reference](admin--license.md) | 1 | 4,542 |
| `admin--mail-server` | [Reference](admin--mail-server.md) | 2 | 5,021 |
| `admin--permissions` | [Reference](admin--permissions.md) | 4 | 14,127 |
| `admin--pull-requests` | [Reference](admin--pull-requests.md) | 1 | 3,399 |
| `admin--users` | [Reference](admin--users.md) | 9 | 20,357 |
| `application-properties` | [Reference](application-properties.md) | 1 | 590 |
| `dashboard` | [Reference](dashboard.md) | 2 | 6,739 |
| `groups` | [Reference](groups.md) | 1 | 1,045 |
| `hooks` | [Reference](hooks.md) | 1 | 1,433 |
| `inbox` | [Reference](inbox.md) | 2 | 1,066 |
| `logs` | [Reference](logs.md) | 4 | 3,716 |
| `markup` | [Reference](markup.md) | 1 | 1,732 |
| `profile` | [Reference](profile.md) | 1 | 2,082 |
| `projects--archive` | [Reference](projects--archive.md) | 1 | 4,198 |
| `projects--avatar.png` | [Reference](projects--avatar.png.md) | 1 | 3,071 |
| `projects--branches` | [Reference](projects--branches.md) | 2 | 5,952 |
| `projects--browse` | [Reference](projects--browse.md) | 2 | 8,144 |
| `projects--changes` | [Reference](projects--changes.md) | 1 | 2,671 |
| `projects--commits` | [Reference](projects--commits.md) | 8 | 37,895 |
| `projects--compare` | [Reference](projects--compare.md) | 3 | 9,066 |
| `projects--diff` | [Reference](projects--diff.md) | 2 | 8,214 |
| `projects--files` | [Reference](projects--files.md) | 2 | 4,285 |
| `projects--forks` | [Reference](projects--forks.md) | 1 | 2,722 |
| `projects--last-modified` | [Reference](projects--last-modified.md) | 2 | 6,708 |
| `projects--participants` | [Reference](projects--participants.md) | 1 | 2,625 |
| `projects--permissions` | [Reference](projects--permissions.md) | 9 | 27,858 |
| `projects--projects` | [Reference](projects--projects.md) | 2 | 7,592 |
| `projects--pull-requests` | [Reference](projects--pull-requests.md) | 18 | 87,746 |
| `projects--raw` | [Reference](projects--raw.md) | 2 | 3,511 |
| `projects--recreate` | [Reference](projects--recreate.md) | 1 | 2,179 |
| `projects--related` | [Reference](projects--related.md) | 1 | 2,572 |
| `projects--repos` | [Reference](projects--repos.md) | 2 | 12,448 |
| `projects--settings` | [Reference](projects--settings.md) | 10 | 32,519 |
| `projects--tags` | [Reference](projects--tags.md) | 2 | 4,756 |
| `projects--watch` | [Reference](projects--watch.md) | 1 | 1,976 |
| `projects--webhooks` | [Reference](projects--webhooks.md) | 6 | 15,403 |
| `repos` | [Reference](repos.md) | 1 | 3,591 |
| `tasks` | [Reference](tasks.md) | 2 | 6,439 |
| `users` | [Reference](users.md) | 5 | 6,237 |

## 5.10 conventions worth checking before a call

- Paging: `start` / `limit` (default 25), continue while `isLastPage` is false, next offset is `nextPageStart`.
- PR and comment mutations/deletions need the current `version` integer, otherwise `409 Conflict`.
- `/diff` endpoints are unpaged and may answer `truncated: true`; re-query `/diff/<path>` for the rest.
- Core API fallback without a search extension: enumerate projects → repos → `/files`, `/browse`, `/raw`.
