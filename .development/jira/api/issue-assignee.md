<!-- jira 8.22.2 - resource group: issue--assignee -->

# `issue--assignee`

1 method(s) as this deployment serves them. Source: its own `application.wadl`.

## PUT /issue/{issueIdOrKey}/assignee

Assigns an issue to a user. You can use this resource to assign issues when the user submitting the request has the assign permission but not the edit issue permission. If the name is "-1" automatic assignee is used. A null name will remove the assignee.

No query parameters.
