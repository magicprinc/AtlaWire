<!-- jira 8.22.2 - resource group: workflowscheme -->

# `workflowscheme`

26 method(s) as this deployment serves them. Source: its own `application.wadl`.

## POST /workflowscheme

Create a new workflow scheme. The body contains a representation of the new scheme. Values not passed are assumed to be set to their defaults.

No query parameters.

## DELETE /workflowscheme/{id}

Delete the passed workflow scheme.

No query parameters.

## GET /workflowscheme/{id}

Returns the requested workflow scheme to the caller.

| query | type | default |
|---|---|---|
| `returnDraftIfExists` | boolean | `false` |

## PUT /workflowscheme/{id}

Update the passed workflow scheme. The body of the request is a representation of the workflow scheme. Values not passed are assumed to indicate no change for that field. The passed representation can have its updateDraftIfNeeded flag set to true to indicate that the draft should be created and/or updated when the actual scheme cannot be edited (e.g. when the scheme is being used by a project). Values not appearing the body will not be touched.

No query parameters.

## POST /workflowscheme/{id}/createdraft

Create a draft for the passed scheme. The draft will be a copy of the state of the parent.

No query parameters.

## DELETE /workflowscheme/{id}/default

Remove the default workflow from the passed workflow scheme.

| query | type | default |
|---|---|---|
| `updateDraftIfNeeded` | boolean |  |

## GET /workflowscheme/{id}/default

Return the default workflow from the passed workflow scheme.

| query | type | default |
|---|---|---|
| `returnDraftIfExists` | boolean | `false` |

## PUT /workflowscheme/{id}/default

Set the default workflow for the passed workflow scheme. The passed representation can have its updateDraftIfNeeded flag set to true to indicate that the draft should be created/updated when the actual scheme cannot be edited.

No query parameters.

## DELETE /workflowscheme/{id}/draft

Delete the passed draft workflow scheme.

No query parameters.

## GET /workflowscheme/{id}/draft

Returns the requested draft workflow scheme to the caller.

No query parameters.

## PUT /workflowscheme/{id}/draft

Update a draft workflow scheme. The draft will created if necessary. The body is a representation of the workflow scheme. Values not passed are assumed to indicate no change for that field.

No query parameters.

## DELETE /workflowscheme/{id}/draft/default

Remove the default workflow from the passed draft workflow scheme.

No query parameters.

## GET /workflowscheme/{id}/draft/default

Return the default workflow from the passed draft workflow scheme to the caller.

No query parameters.

## PUT /workflowscheme/{id}/draft/default

Set the default workflow for the passed draft workflow scheme.

No query parameters.

## DELETE /workflowscheme/{id}/draft/issuetype/{issueType}

Remove the specified issue type mapping from the draft scheme.

No query parameters.

## GET /workflowscheme/{id}/draft/issuetype/{issueType}

Returns the issue type mapping for the passed draft workflow scheme.

No query parameters.

## PUT /workflowscheme/{id}/draft/issuetype/{issueType}

Set the issue type mapping for the passed draft scheme. The passed representation can have its updateDraftIfNeeded flag set to true to indicate that the draft should be created/updated when the actual scheme cannot be edited.

No query parameters.

## DELETE /workflowscheme/{id}/draft/workflow

Delete the passed workflow from the draft workflow scheme.

| query | type | default |
|---|---|---|
| `workflowName` | string |  |

## GET /workflowscheme/{id}/draft/workflow

Returns the draft workflow mappings or requested mapping to the caller.

| query | type | default |
|---|---|---|
| `workflowName` | string |  |

## PUT /workflowscheme/{id}/draft/workflow

Update the draft scheme to include the passed mapping. The body is a representation of the workflow mapping. Values not passed are assumed to indicate no change for that field.

| query | type | default |
|---|---|---|
| `workflowName` | string |  |

## DELETE /workflowscheme/{id}/issuetype/{issueType}

Remove the specified issue type mapping from the scheme.

| query | type | default |
|---|---|---|
| `updateDraftIfNeeded` | boolean |  |

## GET /workflowscheme/{id}/issuetype/{issueType}

Returns the issue type mapping for the passed workflow scheme.

| query | type | default |
|---|---|---|
| `returnDraftIfExists` | boolean | `false` |

## PUT /workflowscheme/{id}/issuetype/{issueType}

Set the issue type mapping for the passed scheme. The passed representation can have its updateDraftIfNeeded flag set to true to indicate that the draft should be created/updated when the actual scheme cannot be edited.

No query parameters.

## DELETE /workflowscheme/{id}/workflow

Delete the passed workflow from the workflow scheme.

| query | type | default |
|---|---|---|
| `workflowName` | string |  |
| `updateDraftIfNeeded` | boolean |  |

## GET /workflowscheme/{id}/workflow

Returns the workflow mappings or requested mapping to the caller for the passed scheme.

| query | type | default |
|---|---|---|
| `workflowName` | string |  |
| `returnDraftIfExists` | boolean | `false` |

## PUT /workflowscheme/{id}/workflow

Update the scheme to include the passed mapping. The body is a representation of the workflow mapping. Values not passed are assumed to indicate no change for that field. The passed representation can have its updateDraftIfNeeded flag set to true to indicate that the draft should be created/updated when the actual scheme cannot be edited.

| query | type | default |
|---|---|---|
| `workflowName` | string |  |
