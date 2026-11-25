<!-- bitbucket 5.10.0 - resource group: projects--permissions -->

# `projects--permissions`

10 method(s) as this deployment serves them. Source: its own `application.wadl`.

## DELETE /projects/{projectKey}/permissions/groups

Revoke all permissions for the specified project for a group. The authenticated user must have PROJECT_ADMIN permission for the specified project or a higher global permission to call this resource. In addition, a user may not revoke a group's permissions if it will reduce their own permission level.

| query | type | default |
|---|---|---|
| `name` | string |  |

## GET /projects/{projectKey}/permissions/groups

Retrieve a page of groups that have been granted at least one permission for the specified project. The authenticated user must have PROJECT_ADMIN permission for the specified project or a higher global permission to call this resource.

| query | type | default |
|---|---|---|
| `filter` | string |  |

## PUT /projects/{projectKey}/permissions/groups

Promote or demote a group's permission level for the specified project. The authenticated user must have PROJECT_ADMIN permission for the specified project or a higher global permission to call this resource. In addition, a user may not demote a group's permission level if their own permission level would be reduced as a result.

| query | type | default |
|---|---|---|
| `permission` | string |  |
| `name` | string |  |

## GET /projects/{projectKey}/permissions/groups/none

Retrieve a page of groups that have no granted permissions for the specified project. The authenticated user must have PROJECT_ADMIN permission for the specified project or a higher global permission to call this resource.

| query | type | default |
|---|---|---|
| `filter` | string |  |

## DELETE /projects/{projectKey}/permissions/users

Revoke all permissions for the specified project for a user. The authenticated user must have PROJECT_ADMIN permission for the specified project or a higher global permission to call this resource. In addition, a user may not revoke their own project permissions if they do not have a higher global permission.

| query | type | default |
|---|---|---|
| `name` | string |  |

## GET /projects/{projectKey}/permissions/users

Retrieve a page of users that have been granted at least one permission for the specified project. The authenticated user must have PROJECT_ADMIN permission for the specified project or a higher global permission to call this resource.

| query | type | default |
|---|---|---|
| `filter` | string |  |

## PUT /projects/{projectKey}/permissions/users

Promote or demote a user's permission level for the specified project. The authenticated user must have PROJECT_ADMIN permission for the specified project or a higher global permission to call this resource. In addition, a user may not reduce their own permission level unless they have a global permission that already implies that permission.

| query | type | default |
|---|---|---|
| `name` | string |  |
| `permission` | string |  |

## GET /projects/{projectKey}/permissions/users/none

Retrieve a page of licensed users that have no granted permissions for the specified project. The authenticated user must have PROJECT_ADMIN permission for the specified project or a higher global permission to call this resource.

| query | type | default |
|---|---|---|
| `filter` | string |  |

## GET /projects/{projectKey}/permissions/{permission}/all

Check whether the specified permission is the default permission (granted to all users) for a project. The authenticated user must have PROJECT_ADMIN permission for the specified project or a higher global permission to call this resource.

No query parameters.

## POST /projects/{projectKey}/permissions/{permission}/all

Grant or revoke a project permission to all users, i.e. set the default permission. The authenticated user must have PROJECT_ADMIN permission for the specified project or a higher global permission to call this resource.

| query | type | default |
|---|---|---|
| `allow` | boolean |  |
