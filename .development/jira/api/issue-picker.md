<!-- jira 8.22.2 - resource group: issue--picker -->

# `issue--picker`

1 method(s) as this deployment serves them. Source: its own `application.wadl`.

## GET /issue/picker

Returns suggested issues which match the auto-completion query for the user which executes this request. This REST method will check the user's history and the user's browsing context and select this issues, which match the query.

| query | type | default |
|---|---|---|
| `query` | string |  |
| `currentJQL` | string |  |
| `currentIssueKey` | string |  |
| `currentProjectId` | string |  |
| `showSubTasks` | boolean |  |
| `showSubTaskParent` | boolean |  |
