<!-- jira 8.22.2 - resource group: avatar -->

# `avatar`

3 method(s) as this deployment serves them. Source: its own `application.wadl`.

## GET /avatar/{type}/system

Returns all system avatars of the given type.

No query parameters.

## POST /avatar/{type}/temporary

Creates temporary avatar

| query | type | default |
|---|---|---|
| `filename` | string |  |
| `size` | long |  |

## POST /avatar/{type}/temporaryCrop

Updates the cropping instructions of the temporary avatar.

No query parameters.
