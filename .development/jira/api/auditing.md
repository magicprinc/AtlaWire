<!-- jira 8.22.2 - resource group: auditing -->

# `auditing`

2 method(s) as this deployment serves them. Source: its own `application.wadl`.

## GET /auditing/record

Returns auditing records filtered using provided parameters

| query | type | default |
|---|---|---|
| `offset` | int |  |
| `limit` | int |  |
| `filter` | string |  |
| `from` | string |  |
| `to` | string |  |
| `projectIds` | string |  |
| `userIds` | string |  |

## POST /auditing/record

Store a record in audit log

No query parameters.
