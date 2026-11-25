<!-- jira 8.22.2 - resource group: issue--transitions -->

# `issue--transitions`

2 method(s) as this deployment serves them. Source: its own `application.wadl`.

## GET /issue/{issueIdOrKey}/transitions

Get a list of the transitions possible for this issue by the current user, along with fields that are required and their types. Fields will only be returned if expand=transitions.fields . The fields in the metadata correspond to the fields in the transition screen for that transition. Fields not in the screen will not be in the metadata.

| query | type | default |
|---|---|---|
| `transitionId` | string |  |

## POST /issue/{issueIdOrKey}/transitions

Perform a transition on an issue. When performing the transition you can update or set other issue fields. The fields that can be set on transtion, in either the fields parameter or the update parameter can be determined using the /rest/api/2/issue/{issueIdOrKey}/transitions?expand=transitions.fields resource. If a field is not configured to appear on the transition screen, then it will not be in the transition metadata, and a field validation error will occur if it is submitted. The updateHistory param adds the issues retrieved by this method to the current user's issue history, if set to true (by default, the issue history does not include issues retrieved via the REST API). You can view the issue history in the Jira application, via the Issues dropdown or by using the lastViewed JQL field in an issue search.

No query parameters.
