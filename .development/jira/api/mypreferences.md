<!-- jira 8.22.2 - resource group: mypreferences -->

# `mypreferences`

3 method(s) as this deployment serves them. Source: its own `application.wadl`.

## DELETE /mypreferences

Removes preference of the currently logged in user. Preference key must be provided as input parameters (key). If key parameter is not provided or wrong - status code 404. If preference is unset - status code 204.

| query | type | default |
|---|---|---|
| `key` | string |  |

## GET /mypreferences

Returns preference of the currently logged in user. Preference key must be provided as input parameter (key). The value is returned exactly as it is. If key parameter is not provided or wrong - status code 404. If value is found - status code 200.

| query | type | default |
|---|---|---|
| `key` | string |  |

## PUT /mypreferences

Sets preference of the currently logged in user. Preference key must be provided as input parameters (key). Value must be provided as post body. If key or value parameter is not provided - status code 404. If preference is set - status code 204.

| query | type | default |
|---|---|---|
| `key` | string |  |
