<!-- confluence version not reported - resource group: audit -->

# `audit`

6 method(s) as this deployment serves them. Source: its own `application.wadl`.

## GET /audit

| query | type | default |
|---|---|---|
| `startDate` | string |  |
| `endDate` | string |  |
| `start` | int |  |
| `limit` | int | `1000` |
| `searchString` | string |  |

## POST /audit

No query parameters.

## GET /audit/export

| query | type | default |
|---|---|---|
| `startDate` | string |  |
| `endDate` | string |  |
| `searchString` | string |  |
| `format` | string | `csv` |

## GET /audit/retention

No query parameters.

## PUT /audit/retention

No query parameters.

## GET /audit/since

| query | type | default |
|---|---|---|
| `number` | long | `3` |
| `units` | string |  |
| `start` | int |  |
| `limit` | int | `1000` |
| `searchString` | string |  |
