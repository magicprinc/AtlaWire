<!-- jira 8.22.2 - resource group: issue--worklog -->

# `issue--worklog`

5 method(s) as this deployment serves them. Source: its own `application.wadl`.

## GET /issue/{issueIdOrKey}/worklog

Returns all work logs for an issue. Note: Work logs won't be returned if the Log work field is hidden for the project.

No query parameters.

## POST /issue/{issueIdOrKey}/worklog

Adds a new worklog entry to an issue.

| query | type | default |
|---|---|---|
| `adjustEstimate` | string |  |
| `newEstimate` | string |  |
| `reduceBy` | string |  |

## DELETE /issue/{issueIdOrKey}/worklog/{id}

Deletes an existing worklog entry.

| query | type | default |
|---|---|---|
| `adjustEstimate` | string |  |
| `newEstimate` | string |  |
| `increaseBy` | string |  |

## GET /issue/{issueIdOrKey}/worklog/{id}

Returns a specific worklog. Note: The work log won't be returned if the Log work field is hidden for the project.

No query parameters.

## PUT /issue/{issueIdOrKey}/worklog/{id}

Updates an existing worklog entry. Note that: Fields possible for editing are: comment, visibility, started, timeSpent and timeSpentSeconds. Either timeSpent or timeSpentSeconds can be set. Fields which are not set will not be updated. For a request to be valid, it has to have at least one field change.

| query | type | default |
|---|---|---|
| `adjustEstimate` | string |  |
| `newEstimate` | string |  |
