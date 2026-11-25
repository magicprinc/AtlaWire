<!-- jira 8.22.2 - resource group: role -->

# `role`

9 method(s) as this deployment serves them. Source: its own `application.wadl`.

## GET /role

Get all the ProjectRoles available in Jira. Currently this list is global.

No query parameters.

## POST /role

Creates a new ProjectRole to be available in Jira. The created role does not have any default actors assigned.

No query parameters.

## DELETE /role/{id}

Deletes a role. May return 403 in the future

| query | type | default |
|---|---|---|
| `swap` | long |  |

## GET /role/{id}

Get a specific ProjectRole available in Jira.

No query parameters.

## POST /role/{id}

Partially updates a roles name or description.

No query parameters.

## PUT /role/{id}

Fully updates a roles. Both name and description must be given.

No query parameters.

## DELETE /role/{id}/actors

Removes default actor from the given role.

| query | type | default |
|---|---|---|
| `user` | string |  |
| `group` | string |  |

## GET /role/{id}/actors

Gets default actors for the given role.

No query parameters.

## POST /role/{id}/actors

Adds default actors to the given role. The request data should contain a list of usernames or a list of groups to add.

No query parameters.
