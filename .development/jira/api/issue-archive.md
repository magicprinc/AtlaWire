<!-- jira 8.22.2 - resource group: issue--archive -->

# `issue--archive`

2 method(s) as this deployment serves them. Source: its own `application.wadl`.

## POST /issue/archive

Archives a list of issues.

| query | type | default |
|---|---|---|
| `notifyUsers` | boolean | `false` |

## PUT /issue/{issueIdOrKey}/archive

Archives an issue.

| query | type | default |
|---|---|---|
| `notifyUsers` | boolean | `true` |
