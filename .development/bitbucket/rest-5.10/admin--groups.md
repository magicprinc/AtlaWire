<!-- Bitbucket Server 5.10.0 REST API — resource group: admin--groups (6 endpoints) -->

## /rest/api/1.0/admin/groups

###### Methods

#### GET

###### /rest/api/1.0/admin/groups?filter

*This is a [paged API](#paging-params)*.

Retrieve a page of groups.

The authenticated user must have **LICENSED_USER** permission or higher to call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **filter** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | if specified only group names containing the supplied string will be returned |

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

#### POST

###### /rest/api/1.0/admin/groups?name

Create a new group.

The authenticated user must have **ADMIN** permission or higher to call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **name** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | Name of the group. |

*Example response representations:*

-

  200 - application/json (restDetailedGroup)

  ###### Example

      {"name":"group-a","deletable":true}

  The newly created group.

-

  400 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":"field_a","message":"A detailed validation error message for field_a.","exceptionName":null},{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The request was malformed.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user is not an administrator.

-

  409 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  A group with this name already exists.

#### DELETE

###### /rest/api/1.0/admin/groups?name

Deletes the specified group, removing them from the system. This also removes any permissions that may have been granted to the group.

A user may not delete the last group that is granting them administrative permissions, or a group with greater permissions than themselves.

The authenticated user must have the **ADMIN** permission to call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **name** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the name identifying the group to delete |

*Example response representations:*

-

  200 - application/json (detailedGroup)

  ###### Example

      {"name":"group-a","deletable":true}

  The deleted group.

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

  The specified group does not exist.

-

  409 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The action was disallowed as it would lower the authenticated user's permission level.

## /rest/api/1.0/admin/groups/add-user

###### Methods

#### POST

**Deprecated since 2.10**. Use /rest/users/add-groups instead.

Add a user to a group.

In the request entity, the *context* attribute is the group and the *itemName* is the user.

The authenticated user must have the **ADMIN** permission to call this resource.

*Example request representations:*

-

  application/json

  ###### Example

      {"context":"group_a","itemName":"user_a"}

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

## /rest/api/1.0/admin/groups/add-users

###### Methods

#### POST

Add multiple users to a group.

The authenticated user must have the **ADMIN** permission to call this resource.

*Example request representations:*

-

  application/json

  ###### Example

      {"group":"group","users":["user1","user2"]}

*Example response representations:*

-

  200

  *\>All*

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The authenticated user does not have the **ADMIN** permission.

-

  403 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The action was disallowed as it would exceed the server's licensing limit, or the group's permissions exceed the authenticated user's permission level.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified group or users do not exist.

## /rest/api/1.0/admin/groups/remove-user

###### Methods

#### POST

**Deprecated since 2.10**. Use /rest/users/remove-groups instead.

Remove a user from a group.

The authenticated user must have the **ADMIN** permission to call this resource.

In the request entity, the *context* attribute is the group and the *itemName* is the user.

*Example request representations:*

-

  application/json

  ###### Example

      {"context":"group_a","itemName":"user_a"}

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

## /rest/api/1.0/admin/groups/more-members

###### Methods

#### GET

###### /rest/api/1.0/admin/groups/more-members?context&filter

*This is a [paged API](#paging-params)*.

Retrieves a list of users that are members of a specified group.

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
<td>the group which should be used to locate members</td>
</tr>
<tr>
<td>filter</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a>
Default:</td>
<td>if specified only users with usernames, display names or email addresses containing the supplied string will be returned</td>
</tr>
</tbody>
</table>

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

## /rest/api/1.0/admin/groups/more-non-members

###### Methods

#### GET

###### /rest/api/1.0/admin/groups/more-non-members?context&filter

*This is a [paged API](#paging-params)*.

Retrieves a list of users that are *not* members of a specified group.

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
<td>the group which should be used to locate non-members</td>
</tr>
<tr>
<td>filter</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a>
Default:</td>
<td>if specified only users with usernames, display names or email addresses containing the supplied string will be returned</td>
</tr>
</tbody>
</table>

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
