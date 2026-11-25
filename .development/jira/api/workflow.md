<!-- jira 8.22.2 - resource group: workflow -->

# `workflow`

5 method(s) as this deployment serves them. Source: its own `application.wadl`.

## GET /workflow

Returns all workflows.

| query | type | default |
|---|---|---|
| `workflowName` | string |  |

## DELETE /workflow/transitions/{id}/properties

Delete a property from the passed transition on the passed workflow. It is not an error to delete a property that does not exist.

| query | type | default |
|---|---|---|
| `key` | string |  |
| `workflowName` | string |  |
| `workflowMode` | string |  |

## GET /workflow/transitions/{id}/properties

Return the property or properties associated with a transition.

| query | type | default |
|---|---|---|
| `includeReservedKeys` | boolean |  |
| `key` | string |  |
| `workflowName` | string |  |
| `workflowMode` | string |  |

## POST /workflow/transitions/{id}/properties

Add a new property to a transition. Trying to add a property that already exists will fail.

| query | type | default |
|---|---|---|
| `key` | string |  |
| `workflowName` | string |  |
| `workflowMode` | string |  |

## PUT /workflow/transitions/{id}/properties

Update/add new property to a transition. Trying to update a property that does not exist will result in a new property being added.

| query | type | default |
|---|---|---|
| `key` | string |  |
| `workflowName` | string |  |
| `workflowMode` | string |  |
