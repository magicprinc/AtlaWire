<!-- Bitbucket Server 5.10.0 REST API — resource group: admin--permissions (4 endpoints) -->

## /rest/api/1.0/admin/permissions/users

###### Methods

#### PUT

###### /rest/api/1.0/admin/permissions/users?name&permission

Promote or demote the global permission level of a user. Available global permissions are:

- LICENSED_USER
- PROJECT_CREATE
- ADMIN
- SYS_ADMIN

See the [Bitbucket Server documentation](https://confluence.atlassian.com/display/BitbucketServer/Global+permissions) for a detailed explanation of what each permission entails.

The authenticated user must have:

- **ADMIN** permission or higher; and
- the permission they are attempting to grant; and
- greater or equal permissions than the current permission level of the user (a user may not demote the permission level of a user with higher permissions than them)

to call this resource. In addition, a user may not demote their own permission level.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **name** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the names of the users |
| **permission** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the permission to grant |

*Example response representations:*

-

  204

  The requested permission was granted.

-

  400 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":"field_a","message":"A detailed validation error message for field_a.","exceptionName":null},{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The request was malformed or the specified permission does not exist.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user is not an administrator or doesn't have the specified permission they are attempting to grant.

-

  403 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The action was disallowed as it would exceed the server's license limits.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified user does not exist.

-

  409 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The action was disallowed as it would reduce the currently authenticated user's permission level or the currently authenticated user has a lower permission level than the user they are attempting to modify.

#### GET

###### /rest/api/1.0/admin/permissions/users?filter

*This is a [paged API](#paging-params)*.

Retrieve a page of users that have been granted at least one global permission.

The authenticated user must have **ADMIN** permission or higher to call this resource.

###### request query parameters

<table>
<colgroup>
<col style="width: 33%" />
<col style="width: 33%" />
<col style="width: 33%" />
</colgroup>
<thead>
<tr>
<th>parameter</th>
<th>value</th>
<th>description</th>
</tr>
</thead>
<tbody>
<tr>
<td>filter</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a>
Default:</td>
<td>if specified only user names containing the supplied string will be returned</td>
</tr>
</tbody>
</table>

*Example response representations:*

-

  200 - application/json ([page](#paging-params))

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"user":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"permission":"ADMIN"}],"start":0}

  A page of users and their highest global permissions.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user is not an administrator.

#### DELETE

###### /rest/api/1.0/admin/permissions/users?name

Revoke all global permissions for a user.

The authenticated user must have:

- **ADMIN** permission or higher; and
- greater or equal permissions than the current permission level of the user (a user may not demote the permission level of a user with higher permissions than them)

to call this resource. In addition, a user may not demote their own permission level.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **name** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the name of the user |

*Example response representations:*

-

  204

  All global permissions were revoked from the user.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user is not an administrator.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified user does not exist.

-

  409 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The action was disallowed as it would reduce the currently authenticated user's permission level or the currently authenticated user has a lower permission level than the user they are attempting to modify.

## /rest/api/1.0/admin/permissions/groups

###### Methods

#### PUT

###### /rest/api/1.0/admin/permissions/groups?permission&name

Promote or demote a user's global permission level. Available global permissions are:

- LICENSED_USER
- PROJECT_CREATE
- ADMIN
- SYS_ADMIN

See the [Bitbucket Server documentation](https://confluence.atlassian.com/display/BitbucketServer/Global+permissions) for a detailed explanation of what each permission entails.

The authenticated user must have:

- **ADMIN** permission or higher; and
- the permission they are attempting to grant or higher; and
- greater or equal permissions than the current permission level of the group (a user may not demote the permission level of a group with higher permissions than them)

to call this resource. In addition, a user may not demote a group's permission level if their own permission level would be reduced as a result.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **permission** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the permission to grant |
| **name** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the names of the groups |

*Example response representations:*

-

  204

  The specified permission was granted to the specified user.

-

  400 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":"field_a","message":"A detailed validation error message for field_a.","exceptionName":null},{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The request was malformed or the specified permission does not exist.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user is not an administrator or doesn't have the specified permission they are attempting to grant.

-

  403 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The action was disallowed as it would exceed the server's license limits.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified group does not exist.

-

  409 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The action was disallowed as it would reduce the currently authenticated user's permission level or the currently authenticated user has a lower permission level than the group they are attempting to modify.

#### GET

###### /rest/api/1.0/admin/permissions/groups?filter

*This is a [paged API](#paging-params)*.

Retrieve a page of groups that have been granted at least one global permission.

The authenticated user must have **ADMIN** permission or higher to call this resource.

###### request query parameters

<table>
<colgroup>
<col style="width: 33%" />
<col style="width: 33%" />
<col style="width: 33%" />
</colgroup>
<thead>
<tr>
<th>parameter</th>
<th>value</th>
<th>description</th>
</tr>
</thead>
<tbody>
<tr>
<td>filter</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a>
Default:</td>
<td>if specified only group names containing the supplied string will be returned</td>
</tr>
</tbody>
</table>

*Example response representations:*

-

  200 - application/json ([page](#paging-params))

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"group":{"name":"group_a"},"permission":"ADMIN"}],"start":0}

  A page of groups and their highest global permissions.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user is not an administrator.

#### DELETE

###### /rest/api/1.0/admin/permissions/groups?name

Revoke all global permissions for a group.

The authenticated user must have:

- **ADMIN** permission or higher; and
- greater or equal permissions than the current permission level of the group (a user may not demote the permission level of a group with higher permissions than them)

to call this resource. In addition, a user may not revoke a group's permissions if their own permission level would be reduced as a result.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **name** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the name of the group |

*Example response representations:*

-

  204

  All global permissions were revoked from the group.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user is not an administrator.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified group does not exist.

-

  409 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The action was disallowed as it would reduce the currently authenticated user's permission level or the currently authenticated user has a lower permission level than the group they are attempting to modify.

## /rest/api/1.0/admin/permissions/users/none

###### Methods

#### GET

###### /rest/api/1.0/admin/permissions/users/none?filter

*This is a [paged API](#paging-params)*.

Retrieve a page of users that have no granted global permissions.

The authenticated user must have **ADMIN** permission or higher to call this resource.

###### request query parameters

<table>
<colgroup>
<col style="width: 33%" />
<col style="width: 33%" />
<col style="width: 33%" />
</colgroup>
<thead>
<tr>
<th>parameter</th>
<th>value</th>
<th>description</th>
</tr>
</thead>
<tbody>
<tr>
<td>filter</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a>
Default:</td>
<td>if specified only user names containing the supplied string will be returned</td>
</tr>
</tbody>
</table>

*Example response representations:*

-

  200 - application/json ([page](#paging-params))

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"}],"start":0}

  A page of users that have not been granted any global permissions.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user is not an administrator.

## /rest/api/1.0/admin/permissions/groups/none

###### Methods

#### GET

###### /rest/api/1.0/admin/permissions/groups/none?filter

*This is a [paged API](#paging-params)*.

Retrieve a page of groups that have no granted global permissions.

The authenticated user must have **ADMIN** permission or higher to call this resource.

###### request query parameters

<table>
<colgroup>
<col style="width: 33%" />
<col style="width: 33%" />
<col style="width: 33%" />
</colgroup>
<thead>
<tr>
<th>parameter</th>
<th>value</th>
<th>description</th>
</tr>
</thead>
<tbody>
<tr>
<td>filter</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a>
Default:</td>
<td>if specified only group names containing the supplied string will be returned</td>
</tr>
</tbody>
</table>

*Example response representations:*

-

  200 - application/json ([page](#paging-params))

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"name":"group-a","deletable":true}],"start":0}

  A page of groups that have not been granted any global permissions.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user is not an administrator.
