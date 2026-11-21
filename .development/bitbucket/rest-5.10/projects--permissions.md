<!-- Bitbucket Server 5.10.0 REST API — resource group: projects--permissions (9 endpoints) -->

## /rest/api/1.0/projects/{projectKey}/permissions/users

###### Methods

#### PUT

###### /rest/api/1.0/projects/{projectKey}/permissions/users?name&permission

Promote or demote a user's permission level for the specified project.

The authenticated user must have **PROJECT_ADMIN** permission for the specified project or a higher global permission to call this resource. In addition, a user may not reduce their own permission level unless they have a global permission that already implies that permission.

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
<td>the names of the users</td>
</tr>
<tr>
<td>permission</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></td>
<td>the permission to grant. See the [permissions documentation](https://confluence.atlassian.com/display/BitbucketServer/Using+project+permissions) for a detailed explanation of what each permission entails. Available project permissions are:
<ul>
<li>PROJECT_READ</li>
<li>PROJECT_WRITE</li>
<li>PROJECT_ADMIN</li>
</ul></td>
</tr>
</tbody>
</table>

*Example response representations:*

-

  204

  The requested permission was granted.

-

  400

  ###### Example

      {"errors":[{"context":"field_a","message":"A detailed validation error message for field_a.","exceptionName":null},{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The request was malformed or the specified permission does not exist.

-

  401

  The currently authenticated user is not an administrator for the specified project.

-

  403

  The action was disallowed as it would reduce the currently authenticated user's permission level.

-

  404

  The specified project or user does not exist.

#### GET

###### /rest/api/1.0/projects/{projectKey}/permissions/users?filter

*This is a [paged API](#paging-params)*.

Retrieve a page of users that have been granted at least one permission for the specified project.

The authenticated user must have **PROJECT_ADMIN** permission for the specified project or a higher global permission to call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **filter** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | if specified only group names containing the supplied string will be returned |

*Example response representations:*

-

  200 - application/json ([page](#paging-params))

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"user":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"permission":"ADMIN"}],"start":0}

  A page of users and their highest permissions for the specified project.

-

  401

  The currently authenticated user is not a project administrator for the specified project.

-

  404

  The specified project does not exist.

#### DELETE

###### /rest/api/1.0/projects/{projectKey}/permissions/users?name

Revoke all permissions for the specified project for a user.

The authenticated user must have **PROJECT_ADMIN** permission for the specified project or a higher global permission to call this resource.

In addition, a user may not revoke their own project permissions if they do not have a higher global permission.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **name** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the name of the user |

*Example response representations:*

-

  204

  All project permissions were revoked from the user for the specified project.

-

  401

  The currently authenticated user is not an administrator of the specified project.

-

  404

  The specified project or group does not exist.

-

  409

  The action was disallowed as it would reduce the currently authenticated user's permission level.

## /rest/api/1.0/projects/{projectKey}/permissions/{permission}/all

###### resource-wide template parameters

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
<td>permission</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></td>
<td>the permission to grant Available project permissions are:
<ul>
<li>PROJECT_READ</li>
<li>PROJECT_WRITE</li>
<li>PROJECT_ADMIN</li>
</ul></td>
</tr>
</tbody>
</table>

###### Methods

#### POST

###### /rest/api/1.0/projects/{projectKey}/permissions/{permission}/all?allow

Grant or revoke a project permission to all users, i.e. set the default permission.

The authenticated user must have **PROJECT_ADMIN** permission for the specified project or a higher global permission to call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **allow** | *[boolean](http://www.w3.org/TR/xmlschema-2/#boolean)* | *true* to grant the specified permission to all users, or *false* to revoke it |

*Example response representations:*

-

  204

  The requested permission was successfully granted or revoked.

-

  400

  ###### Example

      {"errors":[{"context":"field_a","message":"A detailed validation error message for field_a.","exceptionName":null},{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The request was malformed or the specified permission does not exist.

-

  401

  The currently authenticated user is not an administrator of the specified project.

-

  404

  The specified project does not exist.

#### GET

Check whether the specified permission is the default permission (granted to all users) for a project.

The authenticated user must have **PROJECT_ADMIN** permission for the specified project or a higher global permission to call this resource.

*Example response representations:*

-

  200 - application/json (permitted)

  ###### Example

      {"permitted":true}

  A simple entity indicating whether the specified permission is the default permission for this project.

-

  400

  The request was malformed or the specified permission does not exist.

-

  401

  The currently authenticated user is not an administrator of the specified project.

-

  404

  The specified project does not exist.

## /rest/api/1.0/projects/{projectKey}/permissions/groups

###### Methods

#### PUT

###### /rest/api/1.0/projects/{projectKey}/permissions/groups?permission&name

Promote or demote a group's permission level for the specified project.

The authenticated user must have **PROJECT_ADMIN** permission for the specified project or a higher global permission to call this resource. In addition, a user may not demote a group's permission level if their own permission level would be reduced as a result.

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
<td>permission</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></td>
<td>The permission to grant. See the [permissions documentation](https://confluence.atlassian.com/display/BitbucketServer/Using+project+permissions) for a detailed explanation of what each permission entails. Available project permissions are:
<ul>
<li>PROJECT_READ</li>
<li>PROJECT_WRITE</li>
<li>PROJECT_ADMIN</li>
</ul></td>
</tr>
<tr>
<td>name</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></td>
<td>the names of the groups</td>
</tr>
</tbody>
</table>

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

  401

  The currently authenticated user is not an administrator for the specified project.

-

  403

  The action was disallowed as it would reduce the currently authenticated user's permission level.

-

  404

  The specified project or group does not exist.

#### GET

###### /rest/api/1.0/projects/{projectKey}/permissions/groups?filter

*This is a [paged API](#paging-params)*.

Retrieve a page of groups that have been granted at least one permission for the specified project.

The authenticated user must have **PROJECT_ADMIN** permission for the specified project or a higher global permission to call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **filter** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | if specified only group names containing the supplied string will be returned |

*Example response representations:*

-

  200 - application/json ([page](#paging-params))

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"group":{"name":"group_a"},"permission":"ADMIN"}],"start":0}

  A page of groups and their highest permissions for the specified project.

-

  401

  The currently authenticated user is not a project administrator for the specified project.

-

  404

  The specified project does not exist.

#### DELETE

###### /rest/api/1.0/projects/{projectKey}/permissions/groups?name

Revoke all permissions for the specified project for a group.

The authenticated user must have **PROJECT_ADMIN** permission for the specified project or a higher global permission to call this resource.

In addition, a user may not revoke a group's permissions if it will reduce their own permission level.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **name** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the name of the group |

*Example response representations:*

-

  204

  All project permissions were revoked from the group for the specified project.

-

  401

  The currently authenticated user is not an administrator of the specified project.

-

  404

  The specified project or group does not exist.

-

  409

  The action was disallowed as it would reduce the currently authenticated user's permission level.

## /rest/api/1.0/projects/{projectKey}/permissions/groups/none

###### Methods

#### GET

###### /rest/api/1.0/projects/{projectKey}/permissions/groups/none?filter

*This is a [paged API](#paging-params)*.

Retrieve a page of groups that have no granted permissions for the specified project.

The authenticated user must have **PROJECT_ADMIN** permission for the specified project or a higher global permission to call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **filter** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | if specified only group names containing the supplied string will be returned |

*Example response representations:*

-

  200 - application/json ([page](#paging-params))

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"name":"group-a","deletable":true}],"start":0}

  A page of groups that have not been granted any permissions for the specified project.

-

  401

  The currently authenticated user is not a project administrator for the specified project.

-

  404

  The specified project does not exist.

## /rest/api/1.0/projects/{projectKey}/permissions/users/none

###### Methods

#### GET

###### /rest/api/1.0/projects/{projectKey}/permissions/users/none?filter

*This is a [paged API](#paging-params)*.

Retrieve a page of *licensed* users that have no granted permissions for the specified project.

The authenticated user must have **PROJECT_ADMIN** permission for the specified project or a higher global permission to call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **filter** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | if specified only group names containing the supplied string will be returned |

*Example response representations:*

-

  200 - application/json ([page](#paging-params))

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"name":"group-a","deletable":true}],"start":0}

  A page of users that have not been granted any permissions for the specified project.

-

  401

  The currently authenticated user is not a project administrator for the specified project.

-

  404

  The specified project does not exist.

## /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/permissions/groups

###### Methods

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/permissions/groups?filter

*This is a [paged API](#paging-params)*. *This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Retrieve a page of groups that have been granted at least one permission for the specified repository.

The authenticated user must have **REPO_ADMIN** permission for the specified repository or a higher project or global permission to call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **filter** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | if specified only group names containing the supplied string will be returned |

*Example response representations:*

-

  200 - application/json ([page](#paging-params))

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"group":{"name":"group_a"},"permission":"ADMIN"}],"start":0}

  A page of groups and their highest permissions for the specified repository.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user is not a repository administrator for the specified repository.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository does not exist.

#### PUT

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/permissions/groups?permission&name

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Promote or demote a group's permission level for the specified repository. Available repository permissions are:

- REPO_READ
- REPO_WRITE
- REPO_ADMIN

See the [Bitbucket Server documentation](https://confluence.atlassian.com/display/BitbucketServer/Using+repository+permissions) for a detailed explanation of what each permission entails.

The authenticated user must have **REPO_ADMIN** permission for the specified repository or a higher project or global permission to call this resource. In addition, a user may not demote a group's permission level if their own permission level would be reduced as a result.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **permission** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the permission to grant |
| **name** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the names of the groups |

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

  The currently authenticated user is not an administrator for the specified repository.

-

  403 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The action was disallowed as it would reduce the currently authenticated user's permission level.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository or group does not exist.

#### DELETE

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/permissions/groups?name

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Revoke all permissions for the specified repository for a group.

The authenticated user must have **REPO_ADMIN** permission for the specified repository or a higher project or global permission to call this resource.

In addition, a user may not revoke a group's permissions if it will reduce their own permission level.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **name** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the name of the group |

*Example response representations:*

-

  204

  All repository permissions were revoked from the group for the specified repository.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user is not an administrator of the specified repository.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository or group does not exist.

-

  409 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The action was disallowed as it would reduce the currently authenticated user's permission level.

## /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/permissions/groups/none

###### Methods

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/permissions/groups/none?filter

*This is a [paged API](#paging-params)*. *This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Retrieve a page of groups that have no granted permissions for the specified repository.

The authenticated user must have **REPO_ADMIN** permission for the specified repository or a higher project or global permission to call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **filter** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | if specified only group names containing the supplied string will be returned |

*Example response representations:*

-

  200 - application/json ([page](#paging-params))

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"name":"group-a","deletable":true}],"start":0}

  A page of groups that have not been granted any permissions for the specified repository.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user is not a repository administrator for the specified repository.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository does not exist.

## /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/permissions/users

###### Methods

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/permissions/users?filter

*This is a [paged API](#paging-params)*. *This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Retrieve a page of users that have been granted at least one permission for the specified repository.

The authenticated user must have **REPO_ADMIN** permission for the specified repository or a higher project or global permission to call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **filter** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | if specified only group names containing the supplied string will be returned |

*Example response representations:*

-

  200 - application/json ([page](#paging-params))

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"user":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"permission":"ADMIN"}],"start":0}

  A page of users and their highest permissions for the specified repository.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user is not a repository administrator for the specified repository.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository does not exist.

#### PUT

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/permissions/users?name&permission

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Promote or demote a user's permission level for the specified repository. Available repository permissions are:

- REPO_READ
- REPO_WRITE
- REPO_ADMIN

See the [Bitbucket Server documentation](https://confluence.atlassian.com/display/BitbucketServer/Using+repository+permissions) for a detailed explanation of what each permission entails.

The authenticated user must have **REPO_ADMIN** permission for the specified repository or a higher project or global permission to call this resource. In addition, a user may not reduce their own permission level unless they have a project or global permission that already implies that permission.

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

  The currently authenticated user is not an administrator for the specified repository.

-

  403 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The action was disallowed as it would reduce the currently authenticated user's permission level.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository or user does not exist.

#### DELETE

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/permissions/users?name

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Revoke all permissions for the specified repository for a user.

The authenticated user must have **REPO_ADMIN** permission for the specified repository or a higher project or global permission to call this resource.

In addition, a user may not revoke their own repository permissions if they do not have a higher project or global permission.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **name** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the name of the user |

*Example response representations:*

-

  204

  All repository permissions were revoked from the user for the specified repository.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user is not an administrator of the specified repository.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository or group does not exist.

-

  409 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The action was disallowed as it would reduce the currently authenticated user's permission level.

## /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/permissions/users/none

###### Methods

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/permissions/users/none?filter

*This is a [paged API](#paging-params)*. *This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Retrieve a page of *licensed* users that have no granted permissions for the specified repository.

The authenticated user must have **REPO_ADMIN** permission for the specified repository or a higher project or global permission to call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **filter** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | if specified only group names containing the supplied string will be returned |

*Example response representations:*

-

  200 - application/json ([page](#paging-params))

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"name":"group-a","deletable":true}],"start":0}

  A page of users that have not been granted any permissions for the specified repository.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user is not a repository administrator for the specified repository.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository does not exist.
