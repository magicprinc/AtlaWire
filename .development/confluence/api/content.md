<!-- confluence version not reported - resource group: content -->

# `content`

32 method(s) as this deployment serves them. Source: its own `application.wadl`.

## GET /content

| query | type | default |
|---|---|---|
| `type` | string | `page` |
| `spaceKey` | string |  |
| `title` | string |  |
| `status` | string |  |
| `postingDay` | string |  |
| `expand` | string | `` |
| `start` | int |  |
| `limit` | int | `25` |

## POST /content

| query | type | default |
|---|---|---|
| `status` | string | `current` |
| `expand` | string | `body.storage,history,space,container.history,container.version,version,ancestors` |

## POST /content/blueprint/instance/{draftId}

| query | type | default |
|---|---|---|
| `status` | string | `draft` |
| `expand` | string | `body.storage,history,space,version,ancestors` |

## PUT /content/blueprint/instance/{draftId}

| query | type | default |
|---|---|---|
| `status` | string | `draft` |
| `expand` | string | `body.storage,history,space,version,ancestors` |

## GET /content/search

| query | type | default |
|---|---|---|
| `cql` | string |  |
| `cqlcontext` | string |  |
| `expand` | string | `` |
| `start` | int |  |
| `limit` | int | `25` |

## PUT /content/{contentId}

| query | type | default |
|---|---|---|
| `status` | string |  |
| `conflictPolicy` | string | `abort` |

## DELETE /content/{id}

| query | type | default |
|---|---|---|
| `status` | string |  |

## GET /content/{id}

| query | type | default |
|---|---|---|
| `status` | string |  |
| `version` | int |  |
| `expand` | string | `history,space,version` |

## GET /content/{id}/child

| query | type | default |
|---|---|---|
| `expand` | string | `` |
| `parentVersion` | int | `0` |
| `start` | int |  |
| `limit` | int | `25` |

## GET /content/{id}/child/attachment

| query | type | default |
|---|---|---|
| `expand` | string | `` |
| `start` | int |  |
| `limit` | int | `50` |
| `filename` | string |  |
| `mediaType` | string |  |

## POST /content/{id}/child/attachment

| query | type | default |
|---|---|---|
| `status` | string | `current` |
| `allowDuplicated` | boolean | `false` |
| `expand` | string | `` |

## PUT /content/{id}/child/attachment/{attachmentId}

No query parameters.

## POST /content/{id}/child/attachment/{attachmentId}/data

No query parameters.

## GET /content/{id}/child/comment

| query | type | default |
|---|---|---|
| `expand` | string | `` |
| `parentVersion` | int | `0` |
| `start` | int |  |
| `limit` | int | `25` |
| `location` | string |  |
| `depth` | string | `` |

## GET /content/{id}/child/{type}

| query | type | default |
|---|---|---|
| `expand` | string | `` |
| `parentVersion` | int | `0` |
| `start` | int |  |
| `limit` | int | `25` |

## GET /content/{id}/descendant

| query | type | default |
|---|---|---|
| `expand` | string | `` |

## GET /content/{id}/descendant/{type}

| query | type | default |
|---|---|---|
| `expand` | string | `` |
| `start` | int |  |
| `limit` | int | `25` |

## GET /content/{id}/history

| query | type | default |
|---|---|---|
| `expand` | string | `previousVersion,nextVersion,lastUpdated` |

## GET /content/{id}/history/{version}/macro/hash/{hash}

No query parameters.

## GET /content/{id}/history/{version}/macro/id/{macroId}

No query parameters.

## DELETE /content/{id}/label

| query | type | default |
|---|---|---|
| `name` | string |  |

## GET /content/{id}/label

| query | type | default |
|---|---|---|
| `prefix` | string |  |
| `start` | int |  |
| `limit` | int | `200` |

## POST /content/{id}/label

No query parameters.

## DELETE /content/{id}/label/{label}

No query parameters.

## GET /content/{id}/property

| query | type | default |
|---|---|---|
| `expand` | string |  |
| `start` | int |  |
| `limit` | int | `10` |

## POST /content/{id}/property

No query parameters.

## DELETE /content/{id}/property/{key}

No query parameters.

## GET /content/{id}/property/{key}

| query | type | default |
|---|---|---|
| `expand` | string |  |

## POST /content/{id}/property/{key}

No query parameters.

## PUT /content/{id}/property/{key}

No query parameters.

## GET /content/{id}/restriction/byOperation

| query | type | default |
|---|---|---|
| `expand` | string | `update.restrictions.user,read.restrictions.group,read.restrictions.user,update.restrictions.group` |

## GET /content/{id}/restriction/byOperation/{operationKey}

| query | type | default |
|---|---|---|
| `expand` | string | `restrictions.user,restrictions.group` |
| `start` | int |  |
| `limit` | int | `100` |
