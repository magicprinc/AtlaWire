<!-- jira 8.22.2 - resource group: issue--remotelink -->

# `issue--remotelink`

6 method(s) as this deployment serves them. Source: its own `application.wadl`.

## DELETE /issue/{issueIdOrKey}/remotelink

Delete the remote issue link with the given global id on the issue.

| query | type | default |
|---|---|---|
| `globalId` | string |  |

## GET /issue/{issueIdOrKey}/remotelink

A REST sub-resource representing the remote issue links on the issue.

| query | type | default |
|---|---|---|
| `globalId` | string |  |

## POST /issue/{issueIdOrKey}/remotelink

Creates or updates a remote issue link from a JSON representation. If a globalId is provided and a remote issue link exists with that globalId, the remote issue link is updated. Otherwise, the remote issue link is created.

No query parameters.

## DELETE /issue/{issueIdOrKey}/remotelink/{linkId}

Delete the remote issue link with the given id on the issue.

No query parameters.

## GET /issue/{issueIdOrKey}/remotelink/{linkId}

Get the remote issue link with the given id on the issue.

No query parameters.

## PUT /issue/{issueIdOrKey}/remotelink/{linkId}

Updates a remote issue link from a JSON representation. Any fields not provided are set to null.

No query parameters.
