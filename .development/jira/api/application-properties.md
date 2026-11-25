<!-- jira 8.22.2 - resource group: application-properties -->

# `application-properties`

3 method(s) as this deployment serves them. Source: its own `application.wadl`.

## GET /application-properties

Returns an application property.

| query | type | default |
|---|---|---|
| `key` | string |  |
| `permissionLevel` | string |  |
| `keyFilter` | string |  |

## GET /application-properties/advanced-settings

Returns the properties that are displayed on the "General Configuration > Advanced Settings" page.

No query parameters.

## PUT /application-properties/{id}

Modify an application property via PUT. The "value" field present in the PUT will override the existing value.

No query parameters.
