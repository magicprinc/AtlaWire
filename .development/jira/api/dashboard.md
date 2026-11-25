<!-- jira 8.22.2 - resource group: dashboard -->

# `dashboard`

6 method(s) as this deployment serves them. Source: its own `application.wadl`.

## GET /dashboard

Returns a list of all dashboards, optionally filtering them.

| query | type | default |
|---|---|---|
| `filter` | string |  |
| `startAt` | int |  |
| `maxResults` | int |  |

## GET /dashboard/{dashboardId}/items/{itemId}/properties

Returns the keys of all properties for the dashboard item identified by the id.

No query parameters.

## DELETE /dashboard/{dashboardId}/items/{itemId}/properties/{propertyKey}

Removes the property from the dashboard item identified by the key or by the id. Ths user removing the property is required to have permissions to administer the dashboard item.

No query parameters.

## GET /dashboard/{dashboardId}/items/{itemId}/properties/{propertyKey}

Returns the value of the property with a given key from the dashboard item identified by the id. The user who retrieves the property is required to have permissions to read the dashboard item.

No query parameters.

## PUT /dashboard/{dashboardId}/items/{itemId}/properties/{propertyKey}

Sets the value of the specified dashboard item's property. You can use this resource to store a custom data against the dashboard item identified by the id. The user who stores the data is required to have permissions to administer the dashboard item.

No query parameters.

## GET /dashboard/{id}

Returns a single dashboard.

No query parameters.
