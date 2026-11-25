<!-- confluence version not reported - resource group: webhooks -->

# `webhooks`

9 method(s) as this deployment serves them. Source: its own `application.wadl`.

## GET /webhooks

| query | type | default |
|---|---|---|
| `event` | string |  |
| `statistics` | boolean | `false` |
| `start` | int |  |
| `limit` | int | `100` |

## POST /webhooks

No query parameters.

## POST /webhooks/test

| query | type | default |
|---|---|---|
| `url` | string |  |

## DELETE /webhooks/{webhookId}

No query parameters.

## GET /webhooks/{webhookId}

| query | type | default |
|---|---|---|
| `statistics` | boolean | `false` |

## PUT /webhooks/{webhookId}

No query parameters.

## GET /webhooks/{webhookId}/latest

| query | type | default |
|---|---|---|
| `event` | string |  |
| `outcome` | string |  |

## GET /webhooks/{webhookId}/statistics

| query | type | default |
|---|---|---|
| `event` | string |  |

## GET /webhooks/{webhookId}/statistics/summary

No query parameters.
