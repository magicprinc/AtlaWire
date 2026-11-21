<!-- Bitbucket Server 5.10.0 REST API — resource group: admin--users (9 endpoints) -->

## /rest/api/1.0/admin/users

###### Methods

#### GET

###### /rest/api/1.0/admin/users?filter

*This is a [paged API](#paging-params)*.

Retrieve a page of users.

The authenticated user must have the **LICENSED_USER** permission to call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **filter** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | if specified only users with usernames, display name or email addresses containing the supplied string will be returned |

*Example response representations:*

-

  200 - application/json ([page](#paging-params))

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL","directoryName":"Bitbucket Internal Directory","deletable":true,"lastAuthenticationTimestamp":1368145580548,"mutableDetails":true,"mutableGroups":true}],"start":0}

  A page of users.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user is not a licensed user.

#### PUT

Update a user's details.

The authenticated user must have the **ADMIN** permission to call this resource.

*Example request representations:*

-

  application/json

  ###### Example

      {"name":"jcitizen","displayName":"Jane Citizen","email":"jane@example.com"}

*Example response representations:*

-

  200 - application/json (detailedUser)

  ###### Example

      {"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL","directoryName":"Bitbucket Internal Directory","deletable":true,"lastAuthenticationTimestamp":1368145580548,"mutableDetails":true,"mutableGroups":true}

  The updated user.

-

  400 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":"field_a","message":"A detailed validation error message for field_a.","exceptionName":null},{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The request was malformed.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The authenticated user does not have the **ADMIN** permission or has a lower permission level than the user being deleted.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified user does not exist.

#### POST

###### /rest/api/1.0/admin/users?name&password&displayName&emailAddress&addToDefaultGroup&notify

Creates a new user from the assembled query parameters.

The default group can be used to control initial permissions for new users, such as granting users the ability to login or providing read access to certain projects or repositories. If the user is not added to the default group, they may not be able to login after their account is created until explicit permissions are configured.

The authenticated user must have the **ADMIN** permission to call this resource.

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
<td>name</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></td>
<td>the username for the new user</td>
</tr>
<tr>
<td>password</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></td>
<td>the password for the new user</td>
</tr>
<tr>
<td>displayName</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></td>
<td>the display name for the new user</td>
</tr>
<tr>
<td>emailAddress</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></td>
<td>the e-mail address for the new user</td>
</tr>
<tr>
<td>addToDefaultGroup</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#boolean">boolean</a>
Default: <code>true</code></td>
<td><code>true</code> to add the user to the default group, which can be used to grant them a set of initial permissions; otherwise, <code>false</code> to not add them to a group</td>
</tr>
<tr>
<td>notify</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></td>
<td>if present and not <code>false</code> instead of requiring a password, the create user will be notified via email their account has been created and requires a password to be reset. This option can only be used if a mail server has been configured</td>
</tr>
</tbody>
</table>

*Example response representations:*

-

  204

  The user was successfully created.

-

  400 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":"field_a","message":"A detailed validation error message for field_a.","exceptionName":null},{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The request was malformed.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The authenticated user is not an administrator.

-

  403 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  Adding the user to the default group would exceed the server's license limit.

-

  409 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  Another user with the same name already exists.

#### DELETE

###### /rest/api/1.0/admin/users?name

Deletes the specified user, removing them from the system. This also removes any permissions that may have been granted to the user.

A user may not delete themselves, and a user with **ADMIN** permissions may not delete a user with **SYS_ADMIN**permissions.

The authenticated user must have the **ADMIN** permission to call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **name** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the username identifying the user to delete |

*Example response representations:*

-

  200 - application/json (detailedUser)

  ###### Example

      {"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL","directoryName":"Bitbucket Internal Directory","deletable":true,"lastAuthenticationTimestamp":1368145580548,"mutableDetails":true,"mutableGroups":true}

  The deleted user.

-

  400 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":"field_a","message":"A detailed validation error message for field_a.","exceptionName":null},{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The request was malformed.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The authenticated user does not have the **ADMIN** permission.

-

  403 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The action was disallowed as the authenticated user has a lower permission level than the user being deleted.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified user does not exist.

-

  409 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The action was disallowed as a user can not delete themselves.

## /rest/api/1.0/admin/users/credentials

###### Methods

#### PUT

Update a user's password.

The authenticated user must have the **ADMIN** permission to call this resource, and may not update the password of a user with greater permissions than themselves.

*Example request representations:*

-

  application/json

  ###### Example

      {"password":"secret","passwordConfirm":"secret","name":"jcitizen"}

*Example response representations:*

-

  204

  The user's password was successfully updated.

-

  400 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":"field_a","message":"A detailed validation error message for field_a.","exceptionName":null},{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The request was malformed.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The authenticated user does not have the **ADMIN** permission or has a lower permission level than the user being deleted.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified user does not exist.

## /rest/api/1.0/admin/users/rename

###### Methods

#### POST

Rename a user.

The authenticated user must have the **ADMIN** permission to call this resource.

*Example request representations:*

-

  application/json

  ###### Example

      {"name":"jcitizen","newName":"jcitizen-new"}

*Example response representations:*

-

  200 - application/json (detailedUser)

  ###### Example

      {"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL","directoryName":"Bitbucket Internal Directory","deletable":true,"lastAuthenticationTimestamp":1368145580548,"mutableDetails":true,"mutableGroups":true}

  The renamed user.

-

  400 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":"field_a","message":"A detailed validation error message for field_a.","exceptionName":null},{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The request was malformed.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The authenticated user does not have the **ADMIN** permission or has a lower permission level than the user being deleted.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified user does not exist.

## /rest/api/1.0/admin/users/captcha

###### Methods

#### DELETE

###### /rest/api/1.0/admin/users/captcha?name

Clears any CAPTCHA challenge that may constrain the user with the supplied username when they authenticate. Additionally any counter or metric that contributed towards the user being issued the CAPTCHA challenge (for instance too many consecutive failed logins) will also be reset.

The authenticated user must have the **ADMIN** permission to call this resource, and may not clear the CAPTCHA of a user with greater permissions than themselves.

###### request query parameters

| parameter | value                                                | description |
|-----------|------------------------------------------------------|-------------|
| **name**  | *[string](http://www.w3.org/TR/xmlschema-2/#string)* |             |

*Example response representations:*

-

  204 - application/json

  The CAPTCHA was successfully cleared.

-

  400 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":"field_a","message":"A detailed validation error message for field_a.","exceptionName":null},{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The request was malformed.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The authenticated user does not have the **ADMIN** permission.

-

  403 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The action was disallowed as the authenticated user has a lower permission level than the group being deleted.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified user does not exist.

## /rest/api/1.0/admin/users/add-group

###### Methods

#### POST

**Deprecated since 2.10**. Use /rest/users/add-groups instead.

Add a user to a group. This is very similar to `groups/add-user`, but with the *context* and *itemName* attributes of the supplied request entity reversed. On the face of it this may appear redundant, but it facilitates a specific UI component in Stash.

In the request entity, the *context* attribute is the user and the *itemName* is the group.

The authenticated user must have the **ADMIN** permission to call this resource.

*Example request representations:*

-

  application/json

  ###### Example

      {"context":"user_a","itemName":"group_a"}

*Example response representations:*

-

  200

  The user was added to the group

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The authenticated user does not have the **ADMIN** permission.

-

  403 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The action was disallowed as it would exceed the server's licensing limit, or the groups permissions exceed the authenticated user's permission level.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified user or group does not exist.

## /rest/api/1.0/admin/users/add-groups

###### Methods

#### POST

Add a user to one or more groups.

The authenticated user must have the **ADMIN** permission to call this resource.

*Example request representations:*

-

  application/json

  ###### Example

      {"user":"user","groups":["group_a","group_b"]}

*Example response representations:*

-

  200

  The user was added to *all* the groups

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The authenticated user does not have the **ADMIN** permission.

-

  403 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The action was disallowed as it would exceed the server's licensing limit, or the groups permissions exceed the authenticated user's permission level.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified user or groups do not exist.

## /rest/api/1.0/admin/users/remove-group

###### Methods

#### POST

Remove a user from a group. This is very similar to `groups/remove-user`, but with the *context* and *itemName* attributes of the supplied request entity reversed. On the face of it this may appear redundant, but it facilitates a specific UI component in Stash.

In the request entity, the *context* attribute is the user and the *itemName* is the group.

The authenticated user must have the **ADMIN** permission to call this resource.

*Example request representations:*

-

  application/json

  ###### Example

      {"context":"user_a","itemName":"group_a"}

*Example response representations:*

-

  200

  The user was removed from the group.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The authenticated user does not have the **ADMIN** permission.

-

  403 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The action was disallowed as the group has a higher permission level than the context user.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified user or group does not exist.

## /rest/api/1.0/admin/users/more-members

###### Methods

#### GET

###### /rest/api/1.0/admin/users/more-members?context&filter

*This is a [paged API](#paging-params)*.

Retrieves a list of groups the specified user is a member of.

The authenticated user must have the **LICENSED_USER** permission to call this resource.

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
<td>context</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></td>
<td>the user which should be used to locate groups</td>
</tr>
<tr>
<td>filter</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a>
Default:</td>
<td>if specified only groups with names containing the supplied string will be returned</td>
</tr>
</tbody>
</table>

*Example response representations:*

-

  200 - application/json ([page](#paging-params))

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"name":"group-a","deletable":true}],"start":0}

  A page of groups.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user is not a licensed user.

## /rest/api/1.0/admin/users/more-non-members

###### Methods

#### GET

###### /rest/api/1.0/admin/users/more-non-members?context&filter

*This is a [paged API](#paging-params)*.

Retrieves a list of groups the specified user is *not* a member of.

The authenticated user must have the **LICENSED_USER** permission to call this resource.

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
<td>context</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></td>
<td>the user which should be used to locate groups</td>
</tr>
<tr>
<td>filter</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a>
Default:</td>
<td>if specified only groups with names containing the supplied string will be returned</td>
</tr>
</tbody>
</table>

*Example response representations:*

-

  200 - application/json ([page](#paging-params))

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"name":"group-a","deletable":true}],"start":0}

  A page of groups.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user is not a licensed user.
