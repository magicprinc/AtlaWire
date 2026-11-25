<!-- jira 8.22.2 - resource group: issue--watchers -->

# `issue--watchers`

3 method(s) as this deployment serves them. Source: its own `application.wadl`.

## DELETE /issue/{issueIdOrKey}/watchers

Removes a user from an issue's watcher list.

| query | type | default |
|---|---|---|
| `username` | string |  |

## GET /issue/{issueIdOrKey}/watchers

Returns the list of watchers for the issue with the given key.

No query parameters.

## POST /issue/{issueIdOrKey}/watchers

Adds a user to an issue's watcher list.

No query parameters.
