<!-- jira 8.22.2 - resource group: priorityschemes -->

# `priorityschemes`

5 method(s) as this deployment serves them. Source: its own `application.wadl`.

## GET /priorityschemes

Returns all priority schemes. All project keys associated with the priority scheme will only be returned if additional query parameter is provided expand=schemes.projectKeys .

| query | type | default |
|---|---|---|
| `startAt` | long |  |
| `maxResults` | int |  |

## POST /priorityschemes

Creates new priority scheme.

No query parameters.

## DELETE /priorityschemes/{schemeId}

Deletes a priority scheme. All projects using deleted scheme will use default priority scheme afterwards. Default priority scheme can't be deleted.

No query parameters.

## GET /priorityschemes/{schemeId}

Gets a full representation of a priority scheme in JSON format. All project keys associated with the priority scheme will only be returned if additional query parameter is provided expand=projectKeys .

No query parameters.

## PUT /priorityschemes/{schemeId}

Updates a priority scheme. Update will be rejected if issue migration would be needed as a result of scheme update. Priority scheme update with migration is possible from the UI. All project keys associated with the priority scheme will only be returned if additional query parameter is provided expand=projectKeys .

No query parameters.
