<!-- confluence version not reported - resource group: space -->

# `space`

14 method(s) as this deployment serves them. Source: its own `application.wadl`.

## GET /space

| query | type | default |
|---|---|---|
| `spaceKey` | string |  |
| `type` | string |  |
| `status` | string |  |
| `label` | string |  |
| `favourite` | boolean |  |
| `expand` | string | `` |
| `start` | int |  |
| `limit` | int | `25` |

## POST /space

No query parameters.

## POST /space/_private

No query parameters.

## DELETE /space/{spaceKey}

No query parameters.

## GET /space/{spaceKey}

| query | type | default |
|---|---|---|
| `expand` | string | `` |

## PUT /space/{spaceKey}

No query parameters.

## GET /space/{spaceKey}/content

| query | type | default |
|---|---|---|
| `depth` | string | `all` |
| `expand` | string | `` |
| `start` | int |  |
| `limit` | int | `25` |

## GET /space/{spaceKey}/content/{type}

| query | type | default |
|---|---|---|
| `depth` | string | `all` |
| `expand` | string | `` |
| `start` | int |  |
| `limit` | int | `25` |

## GET /space/{spaceKey}/property

| query | type | default |
|---|---|---|
| `expand` | string | `version` |
| `start` | int |  |
| `limit` | int | `10` |

## POST /space/{spaceKey}/property

No query parameters.

## DELETE /space/{spaceKey}/property/{key}

No query parameters.

## GET /space/{spaceKey}/property/{key}

| query | type | default |
|---|---|---|
| `expand` | string | `version` |

## POST /space/{spaceKey}/property/{key}

No query parameters.

## PUT /space/{spaceKey}/property/{key}

No query parameters.
