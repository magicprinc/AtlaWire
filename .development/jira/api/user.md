<!-- jira 8.22.2 - resource group: user -->

# `user`

35 method(s) as this deployment serves them. Source: its own `application.wadl`.

## DELETE /user

Removes user and its references (like project roles associations, watches, history). Note: user references will not be removed if multiple User Directories are used and there is a user with the same name existing in another directory (shadowing user).

| query | type | default |
|---|---|---|
| `username` | string |  |
| `key` | string |  |

## GET /user

Returns a user. This resource cannot be accessed anonymously.

| query | type | default |
|---|---|---|
| `username` | string |  |
| `key` | string |  |
| `includeDeleted` | boolean | `false` |

## POST /user

Create user. By default created user will not be notified with email. If password field is not set then password will be randomly generated.

No query parameters.

## PUT /user

Modify user. The "value" fields present will override the existing value. Fields skipped in request will not be changed.

| query | type | default |
|---|---|---|
| `username` | string |  |
| `key` | string |  |

## GET /user/a11y/personal-settings

Returns available accessibility personal settings along with `enabled` property that indicates the currently logged-in user preference.

No query parameters.

## GET /user/anonymization

Validates user anonymization process.

| query | type | default |
|---|---|---|
| `userKey` | string |  |
| `expand` | string |  |

## POST /user/anonymization

Schedules a user anonymization process. Requires system admin permission.

No query parameters.

## GET /user/anonymization/progress

Returns information about a user anonymization operation progress.

| query | type | default |
|---|---|---|
| `taskId` | long |  |

## GET /user/anonymization/rerun

Validates user anonymization re-run process.

| query | type | default |
|---|---|---|
| `userKey` | string |  |
| `oldUserKey` | string |  |
| `oldUserName` | string |  |
| `expand` | string |  |

## POST /user/anonymization/rerun

Schedules a user anonymization process. Requires system admin permission.

No query parameters.

## DELETE /user/anonymization/unlock

Removes stale user anonymization task, for scenarios when the node that was executing it is no longer alive. Use it only after making sure that the parent node of the task is actually down, and not just having connectivity issues.

No query parameters.

## DELETE /user/application

Remove user from given application. Admin permission will be required to perform this operation.

| query | type | default |
|---|---|---|
| `username` | string |  |
| `applicationKey` | string |  |

## POST /user/application

Add user to given application. Admin permission will be required to perform this operation.

| query | type | default |
|---|---|---|
| `username` | string |  |
| `applicationKey` | string |  |

## GET /user/assignable/multiProjectSearch

Returns a list of users that match the search string and can be assigned issues for all the given projects.

| query | type | default |
|---|---|---|
| `username` | string |  |
| `projectKeys` | string |  |
| `maxResults` | int | `50` |

## GET /user/assignable/search

Returns a list of users that match the search string. This resource cannot be accessed anonymously. Please note that this resource should be called with an issue key when a list of assignable users is retrieved for editing. For create only a project key should be supplied. The list of assignable users may be incorrect if it's called with the project key for editing.

| query | type | default |
|---|---|---|
| `username` | string |  |
| `project` | string |  |
| `issueKey` | string |  |
| `maxResults` | int | `50` |
| `actionDescriptorId` | int |  |

## POST /user/avatar

Converts temporary avatar into a real avatar

| query | type | default |
|---|---|---|
| `username` | string |  |

## PUT /user/avatar

| query | type | default |
|---|---|---|
| `username` | string |  |

## POST /user/avatar/temporary

Creates temporary avatar using multipart. The response is sent back as JSON stored in a textarea. This is because the client uses remote iframing to submit avatars using multipart. So we must send them a valid HTML page back from which the client parses the JSON from. Creating a temporary avatar is part of a 3-step process in uploading a new avatar for a user: upload, crop, confirm. This endpoint allows you to use a multipart upload instead of sending the image directly as the request body. You *must* use "avatar" as the name of the upload parameter: curl -c cookiejar.txt -X POST -u admin:admin -H "X-Atlassian-Token: no-check" \ -F "avatar=@mynewavatar.png;type=image/png" \ 'http://localhost:8090/jira/rest/api/2/user/avatar/temporary?username=admin'

| query | type | default |
|---|---|---|
| `username` | string |  |

## POST /user/avatar/temporary

Creates temporary avatar. Creating a temporary avatar is part of a 3-step process in uploading a new avatar for a user: upload, crop, confirm. The following examples shows these three steps using curl. The cookies (session) need to be preserved between requests, hence the use of -b and -c. The id created in step 2 needs to be passed to step 3 (you can simply pass the whole response of step 2 as the request of step 3). curl -c cookiejar.txt -X POST -u admin:admin -H "X-Atlassian-Token: no-check" \ -H "Content-Type: image/png" --data-binary @mynewavatar.png \ 'http://localhost:8090/jira/rest/api/2/user/avatar/temporary?username=admin&amp;filename=mynewavatar.png' curl -b cookiejar.txt -X POST -u admin:admin -H "X-Atlassian-Token: no-check" \ -H "Content-Type: application/json" --data '{"cropperWidth": "65","cropperOffsetX": "10","cropperOffsetY": "16"}' \ -o tmpid.json \ http://localhost:8090/jira/rest/api/2/user/avatar?username=admin curl -b cookiejar.txt -X PUT -u admin:admin -H "X-Atlassian-Token: no-check" \ -H "Content-Type: application/json" --data-binary @tmpid.json \ http://localhost:8090/jira/rest/api/2/user/avatar?username=admin

| query | type | default |
|---|---|---|
| `username` | string |  |
| `filename` | string |  |
| `size` | long |  |

## DELETE /user/avatar/{id}

Deletes avatar

| query | type | default |
|---|---|---|
| `username` | string |  |

## GET /user/avatars

Returns all avatars which are visible for the currently logged in user.

| query | type | default |
|---|---|---|
| `username` | string |  |

## DELETE /user/columns

Reset the default columns for the given user to the system default. Admin permission will be required to get columns for a user other than the currently logged in user.

| query | type | default |
|---|---|---|
| `username` | string |  |

## GET /user/columns

Returns the default columns for the given user. Admin permission will be required to get columns for a user other than the currently logged in user.

| query | type | default |
|---|---|---|
| `username` | string |  |

## PUT /user/columns

Sets the default columns for the given user. Admin permission will be required to get columns for a user other than the currently logged in user.

No query parameters.

## GET /user/duplicated/count

Returns the number of users whose accounts are duplicated. Duplicated means that the user has an account in more than one directory and either more than one account is active or the only active account does not belong to the directory with the highest priority. The data returned by this endpoint is cached for 10 minutes and the cache is flushed when any User Directory is added, removed, enabled, disabled, or synchronized. A System Administrator can also flush the cache manually. Related JAC ticket: https://jira.atlassian.com/browse/JRASERVER-68797

| query | type | default |
|---|---|---|
| `flush` | boolean |  |

## GET /user/duplicated/list

Returns duplicated users mapped to their directories with an indication if their accounts are active or not. Duplicated means that the user has an account in more than one directory and either more than one account is active or the only active account does not belong to the directory with the highest priority. The data returned by this endpoint is cached for 10 minutes and the cache is flushed when any User Directory is added, removed, enabled, disabled, or synchronized. A System Administrator can also flush the cache manually. Related JAC ticket: https://jira.atlassian.com/browse/JRASERVER-68797

| query | type | default |
|---|---|---|
| `flush` | boolean |  |

## PUT /user/password

Modify user password.

| query | type | default |
|---|---|---|
| `username` | string |  |
| `key` | string |  |

## GET /user/permission/search

Returns a list of active users that match the search string and have all specified permissions for the project or issue. This resource can be accessed by users with ADMINISTER_PROJECT permission for the project or global ADMIN or SYSADMIN rights. This endpoint can cause serious performance issues and will be removed in Jira 9.0.

| query | type | default |
|---|---|---|
| `username` | string |  |
| `permissions` | string |  |
| `issueKey` | string |  |
| `projectKey` | string |  |
| `startAt` | int |  |
| `maxResults` | int |  |

## GET /user/picker

Returns a list of users matching query with highlighting.

| query | type | default |
|---|---|---|
| `query` | string |  |
| `maxResults` | int |  |
| `showAvatar` | boolean |  |
| `exclude` | string |  |

## GET /user/properties

Returns the keys of all properties for the user identified by the key or by the id.

| query | type | default |
|---|---|---|
| `userKey` | string |  |
| `username` | string |  |

## DELETE /user/properties/{propertyKey}

Removes the property from the user identified by the key or by the id. Ths user removing the property is required to have permissions to administer the user.

| query | type | default |
|---|---|---|
| `userKey` | string |  |
| `username` | string |  |

## GET /user/properties/{propertyKey}

Returns the value of the property with a given key from the user identified by the key or by the id. The user who retrieves the property is required to have permissions to read the user.

| query | type | default |
|---|---|---|
| `userKey` | string |  |
| `username` | string |  |

## PUT /user/properties/{propertyKey}

Sets the value of the specified user's property. You can use this resource to store a custom data against the user identified by the key or by the id. The user who stores the data is required to have permissions to administer the user.

| query | type | default |
|---|---|---|
| `userKey` | string |  |
| `username` | string |  |

## GET /user/search

Returns a list of users that match the search string. This resource cannot be accessed anonymously.

| query | type | default |
|---|---|---|
| `username` | string |  |
| `startAt` | int |  |
| `maxResults` | int |  |
| `includeActive` | boolean |  |
| `includeInactive` | boolean |  |

## GET /user/viewissue/search

Returns a list of active users that match the search string. This resource cannot be accessed anonymously and requires the Browse Users global permission. Given an issue key this resource will provide a list of users that match the search string and have the browse issue permission for the issue provided.

| query | type | default |
|---|---|---|
| `username` | string |  |
| `issueKey` | string |  |
| `projectKey` | string |  |
| `maxResults` | int |  |
