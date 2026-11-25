<!-- jira 8.22.2 - resource group: jql -->

# `jql`

2 method(s) as this deployment serves them. Source: its own `application.wadl`.

## GET /jql/autocompletedata

Returns the auto complete data required for JQL searches.

No query parameters.

## GET /jql/autocompletedata/suggestions

Returns auto complete suggestions for JQL search.

| query | type | default |
|---|---|---|
| `fieldName` | string |  |
| `fieldValue` | string |  |
| `predicateName` | string |  |
| `predicateValue` | string |  |
