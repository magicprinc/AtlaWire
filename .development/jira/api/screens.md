<!-- jira 8.22.2 - resource group: screens -->

# `screens`

12 method(s) as this deployment serves them. Source: its own `application.wadl`.

## GET /screens

Gets available field screens

| query | type | default |
|---|---|---|
| `startAt` | string |  |
| `maxResults` | string |  |
| `expand` | string |  |
| `search` | string |  |

## POST /screens/addToDefault/{fieldId}

Adds field or custom field to the default tab

No query parameters.

## GET /screens/{screenId}/availableFields

Gets available fields for screen. i.e ones that haven't already been added.

No query parameters.

## GET /screens/{screenId}/tabs

Returns a list of all tabs for the given screen

| query | type | default |
|---|---|---|
| `projectKey` | string |  |

## POST /screens/{screenId}/tabs

Creates tab for given screen

No query parameters.

## DELETE /screens/{screenId}/tabs/{tabId}

Deletes tab to give screen

No query parameters.

## PUT /screens/{screenId}/tabs/{tabId}

Renames tab on given screen

No query parameters.

## GET /screens/{screenId}/tabs/{tabId}/fields

Gets all fields for a given tab

| query | type | default |
|---|---|---|
| `projectKey` | string |  |

## POST /screens/{screenId}/tabs/{tabId}/fields

Adds field to the given tab.

No query parameters.

## DELETE /screens/{screenId}/tabs/{tabId}/fields/{id}

Removes field from given tab

No query parameters.

## POST /screens/{screenId}/tabs/{tabId}/fields/{id}/move

Moves field on the given tab

No query parameters.

## POST /screens/{screenId}/tabs/{tabId}/move/{pos}

Moves tab position

No query parameters.
