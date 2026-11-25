<!-- jira 8.22.2 - resource group: groups -->

# `groups`

1 method(s) as this deployment serves them. Source: its own `application.wadl`.

## GET /groups/picker

Returns groups with substrings matching a given query. This is mainly for use with the group picker, so the returned groups contain html to be used as picker suggestions. The groups are also wrapped in a single response object that also contains a header for use in the picker, specifically Showing X of Y matching groups . The number of groups returned is limited by the system property "jira.ajax.autocomplete.limit" The groups will be unique and sorted.

| query | type | default |
|---|---|---|
| `query` | string |  |
| `exclude` | string |  |
| `maxResults` | int |  |
| `userName` | string |  |
