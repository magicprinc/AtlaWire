<!-- jira 8.22.2 - resource group: projects -->

# `projects`

1 method(s) as this deployment serves them. Source: its own `application.wadl`.

## GET /projects/picker

Returns a list of projects visible to the user where project name and/or key is matching the given query. Passing an empty (or whitespace only) query will match no projects. The project matches will contain a field with the query highlighted.

| query | type | default |
|---|---|---|
| `query` | string | `` |
