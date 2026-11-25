<!-- jira 8.22.2 - resource group: filter -->

# `filter`

14 method(s) as this deployment serves them. Source: its own `application.wadl`.

## POST /filter

Creates a new filter, and returns newly created filter. Currently sets permissions just using the users default sharing permissions

| query | type | default |
|---|---|---|
| `expand` | string |  |

## GET /filter/defaultShareScope

Returns the default share scope of the logged-in user.

No query parameters.

## PUT /filter/defaultShareScope

Sets the default share scope of the logged-in user. Available values are: AUTHENTICATED (for sharing with all logged-in users) and PRIVATE (for no shares).

No query parameters.

## GET /filter/favourite

Returns the favourite filters of the logged-in user.

| query | type | default |
|---|---|---|
| `expand` | string |  |

## DELETE /filter/{id}

Delete a filter.

No query parameters.

## GET /filter/{id}

Returns a filter given an id

| query | type | default |
|---|---|---|
| `expand` | string |  |

## PUT /filter/{id}

Updates an existing filter, and returns its new value.

| query | type | default |
|---|---|---|
| `expand` | string |  |

## DELETE /filter/{id}/columns

Resets the columns for the given filter such that the filter no longer has its own column config.

No query parameters.

## GET /filter/{id}/columns

Returns the default columns for the given filter. Currently logged in user will be used as the user making such request.

No query parameters.

## PUT /filter/{id}/columns

Sets the default columns for the given filter.

No query parameters.

## GET /filter/{id}/permission

Returns all share permissions of the given filter.

No query parameters.

## POST /filter/{id}/permission

Adds a share permissions to the given filter. Adding a global permission removes all previous permissions from the filter.

No query parameters.

## DELETE /filter/{id}/permission/{permission-id}

Removes a share permissions from the given filter.

No query parameters.

## GET /filter/{id}/permission/{permissionId}

Returns a single share permission of the given filter.

No query parameters.
