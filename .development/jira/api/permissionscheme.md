<!-- jira 8.22.2 - resource group: permissionscheme -->

# `permissionscheme`

11 method(s) as this deployment serves them. Source: its own `application.wadl`.

## GET /permissionscheme

Returns a list of all permission schemes. By default only shortened beans are returned. If you want to include permissions of all the schemes, then specify the permissions expand parameter. Permissions will be included also if you specify any other expand parameter.

| query | type | default |
|---|---|---|
| `expand` | string |  |

## POST /permissionscheme

Create a new permission scheme. This method can create schemes with a defined permission set, or without.

| query | type | default |
|---|---|---|
| `expand` | string |  |

## GET /permissionscheme/{permissionSchemeId}/attribute/{attributeKey}

No query parameters.

## PUT /permissionscheme/{permissionSchemeId}/attribute/{key}

Updates or inserts the attribute for a permission scheme specified by permission scheme id. The attribute consists of the key and the value. The value will be converted to Boolean using Boolean#valueOf.

No query parameters.

## DELETE /permissionscheme/{schemeId}

Deletes a permission scheme identified by the given id.

No query parameters.

## GET /permissionscheme/{schemeId}

Returns a permission scheme identified by the given id.

| query | type | default |
|---|---|---|
| `expand` | string |  |

## PUT /permissionscheme/{schemeId}

Updates a permission scheme. If the permissions list is present then it will be set in the permission scheme, which basically means it will overwrite any permission grants that existed in the permission scheme. Sending an empty list will remove all permission grants from the permission scheme. To update just the name and description, do not send permissions list at all. To add or remove a single permission grant instead of updating the whole list at once use the {schemeId}/permission/ resource.

| query | type | default |
|---|---|---|
| `expand` | string |  |

## GET /permissionscheme/{schemeId}/permission

Returns all permission grants of the given permission scheme.

| query | type | default |
|---|---|---|
| `expand` | string |  |

## POST /permissionscheme/{schemeId}/permission

Creates a permission grant in a permission scheme.

| query | type | default |
|---|---|---|
| `expand` | string |  |

## DELETE /permissionscheme/{schemeId}/permission/{permissionId}

Deletes a permission grant from a permission scheme.

No query parameters.

## GET /permissionscheme/{schemeId}/permission/{permissionId}

Returns a permission grant identified by the given id.

| query | type | default |
|---|---|---|
| `expand` | string |  |
