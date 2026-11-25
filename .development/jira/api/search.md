<!-- jira 8.22.2 - resource group: search -->

# `search`

2 method(s) as this deployment serves them. Source: its own `application.wadl`.

## GET /search

Searches for issues using JQL. Sorting the jql parameter is a full JQL expression, and includes an ORDER BY clause. The fields param (which can be specified multiple times) gives a comma-separated list of fields to include in the response. This can be used to retrieve a subset of fields. A particular field can be excluded by prefixing it with a minus. By default, only navigable ( *navigable ) fields are returned in this search resource. Note: the default is different in the get-issue resource -- the default there all fields ( *all ). *all - include all fields *navigable - include just navigable fields summary,comment - include just the summary and comments -description - include navigable fields except the description (the default is *navigable for search) *all,-comment - include everything except comments GET vs POST: If the JQL query is too large to be encoded as a query param you should instead POST to this resource. Expanding Issues in the Search Result: It is possible to expand the issues returned by directly specifying the expansion on the expand parameter passed in to this resources. For instance, to expand the &quot;changelog&quot; for all the issues on the search result, it is neccesary to specify &quot;changelog&quot; as one of the values to expand.

| query | type | default |
|---|---|---|
| `jql` | string |  |
| `startAt` | int |  |
| `maxResults` | int |  |
| `validateQuery` | boolean | `true` |
| `fields` | string |  |
| `expand` | string |  |

## POST /search

Performs a search using JQL.

No query parameters.
