<!-- bitbucket 5.10.0 - resource group: admin -->

# `admin`

39 method(s) as this deployment serves them. Source: its own `application.wadl`.

## GET /admin/cluster

Gets information about the nodes that currently make up the stash cluster. The authenticated user must have the SYS_ADMIN permission to call this resource.

No query parameters.

## DELETE /admin/groups

Deletes the specified group, removing them from the system. This also removes any permissions that may have been granted to the group. A user may not delete the last group that is granting them administrative permissions, or a group with greater permissions than themselves. The authenticated user must have the ADMIN permission to call this resource.

| query | type | default |
|---|---|---|
| `name` | string |  |

## GET /admin/groups

Retrieve a page of groups. The authenticated user must have LICENSED_USER permission or higher to call this resource.

| query | type | default |
|---|---|---|
| `filter` | string |  |

## POST /admin/groups

Create a new group. The authenticated user must have ADMIN permission or higher to call this resource.

| query | type | default |
|---|---|---|
| `name` | string |  |

## POST /admin/groups/add-user

Deprecated since 2.10 . Use /rest/users/add-groups instead. Add a user to a group. In the request entity, the context attribute is the group and the itemName is the user. The authenticated user must have the ADMIN permission to call this resource.

No query parameters.

## POST /admin/groups/add-users

Add multiple users to a group. The authenticated user must have the ADMIN permission to call this resource.

No query parameters.

## GET /admin/groups/more-members

Retrieves a list of users that are members of a specified group. The authenticated user must have the LICENSED_USER permission to call this resource.

| query | type | default |
|---|---|---|
| `context` | string |  |
| `filter` | string | `` |

## GET /admin/groups/more-non-members

Retrieves a list of users that are not members of a specified group. The authenticated user must have the LICENSED_USER permission to call this resource.

| query | type | default |
|---|---|---|
| `context` | string |  |
| `filter` | string | `` |

## POST /admin/groups/remove-user

Deprecated since 2.10 . Use /rest/users/remove-groups instead. Remove a user from a group. The authenticated user must have the ADMIN permission to call this resource. In the request entity, the context attribute is the group and the itemName is the user.

No query parameters.

## GET /admin/license

Retrieves details about the current license, as well as the current status of the system with regards to the installed license. The status includes the current number of users applied toward the license limit, as well as any status messages about the license (warnings about expiry or user counts exceeding license limits). The authenticated user must have ADMIN permission. Unauthenticated users, and non-administrators, are not permitted to access license details.

No query parameters.

## POST /admin/license

Decodes the provided encoded license and sets it as the active license. If no license was provided, a 400 is returned. If the license cannot be decoded, or cannot be applied, a 409 is returned. Some possible reasons a license may not be applied include: It is for a different product It is already expired Otherwise, if the license is updated successfully, details for the new license are returned with a 200 response. Warning : It is possible to downgrade the license during update, applying a license with a lower number of permitted users. If the number of currently-licensed users exceeds the limits of the new license, pushing will be disabled until the licensed user count is brought into compliance with the new license. The authenticated user must have SYS_ADMIN permission. ADMIN users may view the current license details, but they may not update the license.

No query parameters.

## DELETE /admin/mail-server

Deletes the current mail configuration. The authenticated user must have the SYS_ADMIN permission to call this resource.

No query parameters.

## GET /admin/mail-server

Retrieves the current mail configuration. The authenticated user must have the SYS_ADMIN permission to call this resource.

No query parameters.

## PUT /admin/mail-server

Updates the mail configuration The authenticated user must have the SYS_ADMIN permission to call this resource.

No query parameters.

## DELETE /admin/mail-server/sender-address

Clears the server email address. The authenticated user must have the ADMIN permission to call this resource.

No query parameters.

## GET /admin/mail-server/sender-address

Retrieves the server email address

No query parameters.

## PUT /admin/mail-server/sender-address

Updates the server email address The authenticated user must have the ADMIN permission to call this resource.

No query parameters.

## DELETE /admin/permissions/groups

Revoke all global permissions for a group. The authenticated user must have: ADMIN permission or higher; and greater or equal permissions than the current permission level of the group (a user may not demote the permission level of a group with higher permissions than them) to call this resource. In addition, a user may not revoke a group's permissions if their own permission level would be reduced as a result.

| query | type | default |
|---|---|---|
| `name` | string |  |

## GET /admin/permissions/groups

Retrieve a page of groups that have been granted at least one global permission. The authenticated user must have ADMIN permission or higher to call this resource.

| query | type | default |
|---|---|---|
| `filter` | string | `` |

## PUT /admin/permissions/groups

Promote or demote a user's global permission level. Available global permissions are: LICENSED_USER PROJECT_CREATE ADMIN SYS_ADMIN See the Bitbucket Server documentation for a detailed explanation of what each permission entails. The authenticated user must have: ADMIN permission or higher; and the permission they are attempting to grant or higher; and greater or equal permissions than the current permission level of the group (a user may not demote the permission level of a group with higher permissions than them) to call this resource. In addition, a user may not demote a group's permission level if their own permission level would be reduced as a result.

| query | type | default |
|---|---|---|
| `permission` | string |  |
| `name` | string |  |

## GET /admin/permissions/groups/none

Retrieve a page of groups that have no granted global permissions. The authenticated user must have ADMIN permission or higher to call this resource.

| query | type | default |
|---|---|---|
| `filter` | string | `` |

## DELETE /admin/permissions/users

Revoke all global permissions for a user. The authenticated user must have: ADMIN permission or higher; and greater or equal permissions than the current permission level of the user (a user may not demote the permission level of a user with higher permissions than them) to call this resource. In addition, a user may not demote their own permission level.

| query | type | default |
|---|---|---|
| `name` | string |  |

## GET /admin/permissions/users

Retrieve a page of users that have been granted at least one global permission. The authenticated user must have ADMIN permission or higher to call this resource.

| query | type | default |
|---|---|---|
| `filter` | string | `` |

## PUT /admin/permissions/users

Promote or demote the global permission level of a user. Available global permissions are: LICENSED_USER PROJECT_CREATE ADMIN SYS_ADMIN See the Bitbucket Server documentation for a detailed explanation of what each permission entails. The authenticated user must have: ADMIN permission or higher; and the permission they are attempting to grant; and greater or equal permissions than the current permission level of the user (a user may not demote the permission level of a user with higher permissions than them) to call this resource. In addition, a user may not demote their own permission level.

| query | type | default |
|---|---|---|
| `name` | string |  |
| `permission` | string |  |

## GET /admin/permissions/users/none

Retrieve a page of users that have no granted global permissions. The authenticated user must have ADMIN permission or higher to call this resource.

| query | type | default |
|---|---|---|
| `filter` | string | `` |

## GET /admin/pull-requests/{scmId}

Retrieve the merge strategies available for this instance. The user must be authenticated to call this resource.

No query parameters.

## POST /admin/pull-requests/{scmId}

Update the pull request merge strategies for the context repository. The authenticated user must have ADMIN permission for the context repository to call this resource. Only the strategies provided will be enabled, only one may be set to default An explicitly set pull request merge strategy configuration can be deleted by POSTing a document with an empty "mergeConfig" attribute. i.e: { "mergeConfig": { } } Upon completion of this request, the effective configuration will be the default configuration.

No query parameters.

## DELETE /admin/users

Deletes the specified user, removing them from the system. This also removes any permissions that may have been granted to the user. A user may not delete themselves, and a user with ADMIN permissions may not delete a user with SYS_ADMIN permissions. The authenticated user must have the ADMIN permission to call this resource.

| query | type | default |
|---|---|---|
| `name` | string |  |

## GET /admin/users

Retrieve a page of users. The authenticated user must have the LICENSED_USER permission to call this resource.

| query | type | default |
|---|---|---|
| `filter` | string |  |

## POST /admin/users

Creates a new user from the assembled query parameters. The default group can be used to control initial permissions for new users, such as granting users the ability to login or providing read access to certain projects or repositories. If the user is not added to the default group, they may not be able to login after their account is created until explicit permissions are configured. The authenticated user must have the ADMIN permission to call this resource.

| query | type | default |
|---|---|---|
| `name` | string |  |
| `password` | string |  |
| `displayName` | string |  |
| `emailAddress` | string |  |
| `addToDefaultGroup` | boolean | `true` |
| `notify` | string |  |

## PUT /admin/users

Update a user's details. The authenticated user must have the ADMIN permission to call this resource.

No query parameters.

## POST /admin/users/add-group

Deprecated since 2.10 . Use /rest/users/add-groups instead. Add a user to a group. This is very similar to groups/add-user , but with the context and itemName attributes of the supplied request entity reversed. On the face of it this may appear redundant, but it facilitates a specific UI component in Stash. In the request entity, the context attribute is the user and the itemName is the group. The authenticated user must have the ADMIN permission to call this resource.

No query parameters.

## POST /admin/users/add-groups

Add a user to one or more groups. The authenticated user must have the ADMIN permission to call this resource.

No query parameters.

## DELETE /admin/users/captcha

Clears any CAPTCHA challenge that may constrain the user with the supplied username when they authenticate. Additionally any counter or metric that contributed towards the user being issued the CAPTCHA challenge (for instance too many consecutive failed logins) will also be reset. The authenticated user must have the ADMIN permission to call this resource, and may not clear the CAPTCHA of a user with greater permissions than themselves.

| query | type | default |
|---|---|---|
| `name` | string |  |

## PUT /admin/users/credentials

Update a user's password. The authenticated user must have the ADMIN permission to call this resource, and may not update the password of a user with greater permissions than themselves.

No query parameters.

## GET /admin/users/more-members

Retrieves a list of groups the specified user is a member of. The authenticated user must have the LICENSED_USER permission to call this resource.

| query | type | default |
|---|---|---|
| `context` | string |  |
| `filter` | string | `` |

## GET /admin/users/more-non-members

Retrieves a list of groups the specified user is not a member of. The authenticated user must have the LICENSED_USER permission to call this resource.

| query | type | default |
|---|---|---|
| `context` | string |  |
| `filter` | string | `` |

## POST /admin/users/remove-group

Remove a user from a group. This is very similar to groups/remove-user , but with the context and itemName attributes of the supplied request entity reversed. On the face of it this may appear redundant, but it facilitates a specific UI component in Stash. In the request entity, the context attribute is the user and the itemName is the group. The authenticated user must have the ADMIN permission to call this resource.

No query parameters.

## POST /admin/users/rename

Rename a user. The authenticated user must have the ADMIN permission to call this resource.

No query parameters.
