<!-- jira 8.22.2 - resource group: reindex -->

# `reindex`

7 method(s) as this deployment serves them. Source: its own `application.wadl`.

## GET /reindex

Returns information on the system reindexes. If a reindex is currently taking place then information about this reindex is returned. If there is no active index task, then returns information about the latest reindex task run, otherwise returns a 404 indicating that no reindex has taken place.

| query | type | default |
|---|---|---|
| `taskId` | long |  |

## POST /reindex

Kicks off a reindex. Need Admin permissions to perform this reindex.

| query | type | default |
|---|---|---|
| `type` | string |  |
| `indexComments` | boolean | `false` |
| `indexChangeHistory` | boolean | `false` |
| `indexWorklogs` | boolean | `false` |

## POST /reindex/issue

Reindexes one or more individual issues. Indexing is performed synchronously - the call returns when indexing of the issues has completed or a failure occurs. Use either explicitly specified issue IDs or a JQL query to select issues to reindex.

| query | type | default |
|---|---|---|
| `issueId` | string |  |
| `indexComments` | boolean | `false` |
| `indexChangeHistory` | boolean | `false` |
| `indexWorklogs` | boolean | `false` |

## GET /reindex/progress

Returns information on the system reindexes. If a reindex is currently taking place then information about this reindex is returned. If there is no active index task, then returns information about the latest reindex task run, otherwise returns a 404 indicating that no reindex has taken place.

| query | type | default |
|---|---|---|
| `taskId` | long |  |

## POST /reindex/request

Executes any pending reindex requests. Returns a JSON array containing the IDs of the reindex requests that are being processed. Execution is asynchronous - progress of the returned tasks can be monitored through other REST calls.

No query parameters.

## GET /reindex/request/bulk

Retrieves the progress of a multiple reindex requests. Only reindex requests that actually exist will be returned in the results.

| query | type | default |
|---|---|---|
| `requestId` | string |  |

## GET /reindex/request/{requestId}

Retrieves the progress of a single reindex request.

No query parameters.
