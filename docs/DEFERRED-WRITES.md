# Historical BBK write API reference

AtlaWire supports discovery, reading, and analysis. It deliberately does not
include Atlassian writes, a generic REST escape hatch, or an apply mode. An
agent prepares a local proposal with the target, current state and revision,
exact change, expected result, and verification steps. The owner reviews the
proposal and applies it through an authorized workflow. Do not give the
research agent a write-capable fallback for this step.

This inventory describes what the legacy BBK source attempted against
Bitbucket Server 5.10, Jira Server 8.22, and Confluence Data Center. It is a
reference for a future, separately authorized library, **not** a claim that
every operation works or that every server version uses these routes. Write
operations were not exercised for AtlaWire.

## Bitbucket

Paths are relative to `/rest/api/1.0/projects/{project}/repos/{repo}`.
`{pr}` is the pull-request ID and `{comment}` is the comment ID.

| Legacy function | Method and relative path | Request and result |
| --- | --- | --- |
| `pr_comment` | `POST /pull-requests/{pr}/comments` | `text`; returns comment ID and version. |
| `pr_comment_reply` | Same `POST` | `text`, `parent.id`; returns comment ID and version. |
| `pr_comment_anchored` | Same `POST` | `text`; optional `anchor` with `diffType=COMMIT`, `path`, `srcPath`, `line`, `lineType`, `fileType`, `fromHash`, and `toHash`; optional `severity=BLOCKER` for a task. Inspect the returned anchor: a successful creation can still be unanchored. |
| `pr_comment_update` | `PUT /pull-requests/{pr}/comments/{comment}` | BBK passed the current comment `version` in the query and `text` in JSON; verify version placement on the intended release. BBK returned the status. |
| `pr_comment_delete` | `DELETE /pull-requests/{pr}/comments/{comment}` | Query `version` must match the current comment; returns status. |
| `pr_create` | `POST /pull-requests` | `title`, optional `description`, `fromRef`, `toRef`, optional `reviewers[].user.name`. BBK used `refs/heads/{branch}` and same-repository `repository.slug` and `repository.project.key` on both refs. Returns PR ID and version. |
| `pr_update` | `PUT /pull-requests/{pr}` | Body includes `id`, current `version`, and requested `title`, `description`, or `reviewers`. Omitted reviewers and an explicit empty array represent different intents; confirm server semantics. |
| `pr_merge` | `POST /pull-requests/{pr}/merge` | Query `version`; body `strategyId`, optional `message`. BBK used `merge-commit`, `squash`, or `fast-forward`; validate what the server permits. Returns PR state. |
| `pr_decline` | `POST /pull-requests/{pr}/decline` | Query `version`; optional `message`; returns PR state. |
| `pr_approve` / `pr_unapprove` | `POST` / `DELETE /pull-requests/{pr}/approve` | Applies to the authenticated actor, not an arbitrary reviewer. BBK sent an empty JSON object for approval. |
| `branch_create` | `POST /branches` | `name`, `startPoint`, and `message`. Resolve the intended start commit explicitly. |
| `branch_delete` | `DELETE /branches` | BBK sent `name` and `dryRun=false` in the query. Verify the intended release and compare the current tip against the approved tip before applying. |
| `attachment_delete` | `DELETE /attachments/{attachment}` | Attachment ID scoped to the repository; returns status. |

`attachment_download` lived in the same BBK module but was a read:
`GET /attachments/{attachment}` returned bytes. It is a research gap, not a
write. The rest of the public vendor API is not implied by this inventory.

## Jira

Paths are relative to `/rest/api/2/issue/{issue}`. Use the canonical issue key
confirmed by a read, and the specific comment ID for comment changes.

| Legacy function | Method and relative path | Request and result |
| --- | --- | --- |
| `jira_comment` | `POST /comment` | `body` string in the instance's comment format; returns comment ID. |
| `jira_update_comment` | `PUT /comment/{comment}` | `body` string; BBK returned status. Check visibility and permissions before preserving or changing a restricted comment. |
| `jira_delete_comment` | `DELETE /comment/{comment}` | No body; returns status. |
| `jira_transition` | `POST /transitions` | Read available transitions first. Body `transition.id`; optional `update.comment[].add.body`. Resolve to a unique transition ID and check available fields and current state; a status name alone can be ambiguous. |

## Confluence

Paths are relative to `/rest/api/content`. The storage representation is
Confluence storage XHTML, not Markdown or rendered HTML.

| Legacy function | Method and relative path | Request and result |
| --- | --- | --- |
| `confluence_comment` | `POST` to the collection | `type=comment`, `container.id`, `container.type=page`, `body.storage.value`, `body.storage.representation=storage`. Returns comment ID. The historical child-comment path was not the create route. |
| `confluence_delete_comment` | `DELETE /{comment}` | Verify the ID points to the intended comment, not a page; returns status. |
| `confluence_update_page` | `PUT /{page}` | `id`, `type=page`, current `title`, `version.number` set to current plus one, optional `version.message`, and new `body.storage`. Re-read and reconcile on conflict, rather than silently replacing a newer edit. |

## If a write library is ever approved

- Isolate it from the research CLI and credentials. Validate one exact
  service, target, actor, revision, and payload per approval.
- Separate a local, side-effect-free preview from execution. BBK's dry runs
  could still write local audit records and some fetched current metadata;
  do not carry that ambiguity forward.
- Record intent and outcome separately, without credentials or private body
  text. Treat a timed-out write as an unknown outcome. Reconcile by read;
  do not blindly retry a possibly committed write.
- Test route, payload, stale state, permission denial, unexpected responses and
  uncertain outcomes against local fixtures. Live write validation requires
  separate authorization and a designated disposable environment.
