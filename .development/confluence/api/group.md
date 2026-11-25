<!-- confluence version not reported - resource group: group -->

# `group`

3 method(s) as this deployment serves them. Source: its own `application.wadl`.

## GET /group

| query | type | default |
|---|---|---|
| `expand` | string | `` |
| `start` | int |  |
| `limit` | int | `200` |

## GET /group/{groupName}

| query | type | default |
|---|---|---|
| `expand` | string |  |

## GET /group/{groupName}/member

| query | type | default |
|---|---|---|
| `expand` | string |  |
| `start` | int |  |
| `limit` | int | `200` |
