<!-- jira 8.22.2 - resource group: issue--comment -->

# `issue--comment`

5 method(s) as this deployment serves them. Source: its own `application.wadl`.

## GET /issue/{issueIdOrKey}/comment

Returns all comments for an issue. Results can be ordered by the "created" field which means the date a comment was added.

| query | type | default |
|---|---|---|
| `startAt` | long |  |
| `maxResults` | int |  |
| `orderBy` | string |  |
| `expand` | string |  |

## POST /issue/{issueIdOrKey}/comment

Adds a new comment to an issue.

| query | type | default |
|---|---|---|
| `expand` | string |  |

## DELETE /issue/{issueIdOrKey}/comment/{id}

Deletes an existing comment .

No query parameters.

## GET /issue/{issueIdOrKey}/comment/{id}

Returns a single comment.

| query | type | default |
|---|---|---|
| `expand` | string |  |

## PUT /issue/{issueIdOrKey}/comment/{id}

Updates an existing comment using its JSON representation.

| query | type | default |
|---|---|---|
| `expand` | string |  |
