<!-- confluence version not reported - resource group: user -->

# `user`

10 method(s) as this deployment serves them. Source: its own `application.wadl`.

## GET /user

| query | type | default |
|---|---|---|
| `key` | string |  |
| `username` | string |  |
| `expand` | string |  |

## GET /user/anonymous

No query parameters.

## GET /user/current

| query | type | default |
|---|---|---|
| `expand` | string |  |

## GET /user/memberof

| query | type | default |
|---|---|---|
| `key` | string |  |
| `username` | string |  |
| `expand` | string |  |
| `start` | int |  |
| `limit` | int | `200` |

## DELETE /user/watch/content/{contentId}

| query | type | default |
|---|---|---|
| `key` | string |  |
| `username` | string |  |

## GET /user/watch/content/{contentId}

| query | type | default |
|---|---|---|
| `key` | string |  |
| `username` | string |  |

## POST /user/watch/content/{contentId}

| query | type | default |
|---|---|---|
| `key` | string |  |
| `username` | string |  |

## DELETE /user/watch/space/{spaceKey}

| query | type | default |
|---|---|---|
| `key` | string |  |
| `username` | string |  |
| `contentType` | string |  |

## GET /user/watch/space/{spaceKey}

| query | type | default |
|---|---|---|
| `key` | string |  |
| `username` | string |  |
| `contentType` | string |  |

## POST /user/watch/space/{spaceKey}

| query | type | default |
|---|---|---|
| `key` | string |  |
| `username` | string |  |
| `contentType` | string |  |
