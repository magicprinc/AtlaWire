<!-- jira 8.22.2 - resource group: worklog -->

# `worklog`

3 method(s) as this deployment serves them. Source: its own `application.wadl`.

## GET /worklog/deleted

Returns worklogs id and delete time of worklogs that was deleted since given time. The returns set of worklogs is limited to 1000 elements. This API will not return worklogs deleted during last minute.

| query | type | default |
|---|---|---|
| `since` | long | `0` |

## POST /worklog/list

Returns worklogs for given worklog ids. Only worklogs to which the calling user has permissions, will be included in the result. The returns set of worklogs is limited to 1000 elements.

No query parameters.

## GET /worklog/updated

Returns worklogs id and update time of worklogs that was updated since given time. The returns set of worklogs is limited to 1000 elements. This API will not return worklogs updated during last minute.

| query | type | default |
|---|---|---|
| `since` | long | `0` |
