<!-- jira 8.22.2 - resource group: component -->

# `component`

5 method(s) as this deployment serves them. Source: its own `application.wadl`.

## POST /component

Create a component via POST.

No query parameters.

## DELETE /component/{id}

Delete a project component.

| query | type | default |
|---|---|---|
| `moveIssuesTo` | string |  |

## GET /component/{id}

Returns a project component.

No query parameters.

## PUT /component/{id}

Modify a component via PUT. Any fields present in the PUT will override existing values. As a convenience, if a field is not present, it is silently ignored. If leadUserName is an empty string ("") the component lead will be removed.

No query parameters.

## GET /component/{id}/relatedIssueCounts

Returns counts of issues related to this component.

No query parameters.
