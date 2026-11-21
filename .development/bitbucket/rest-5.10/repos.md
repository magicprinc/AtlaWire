<!-- Bitbucket Server 5.10.0 REST API — resource group: repos (1 endpoints) -->

## /rest/api/1.0/repos

REST resource for searching through repositories

###### Methods

#### GET

###### /rest/api/1.0/repos?name&projectname&permission&visibility

*This is a [paged API](#paging-params)*.

Retrieve a page of repositories based on query parameters that control the search. See the documentation of the parameters for more details.

This resource is anonymously accessible.

**Note on permissions.** In absence of the {@code permission} query parameter the implicit 'read' permission is assumed. Please note that this permission is lower than the REPO_READ permission rather than being equal to it. The implicit 'read' permission for a given repository is assigned to any user that has any of the higher permissions, such as `REPO_READ`, as well as to anonymous users if the repository is marked as public. The important implication of the above is that an anonymous request to this resource with a permission level `REPO_READ` is guaranteed to receive an empty list of repositories as a result. For anonymous requests it is therefore recommended to not specify the `permission` parameter at all.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **name** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | (optional) if specified, this will limit the resulting repository list to ones whose name matches this parameter's value. The match will be done case-insensitive and any leading and/or trailing whitespace characters on the `name` parameter will be stripped. |
| **projectname** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | (optional) if specified, this will limit the resulting repository list to ones whose project's name matches this parameter's value. The match will be done case-insensitive and any leading and/or trailing whitespace characters on the `projectname` parameter will be stripped. |
| **permission** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | (optional) if specified, it must be a valid repository permission level name and will limit the resulting repository list to ones that the requesting user has the specified permission level to. If not specified, the default implicit 'read' permission level will be assumed. The currently supported explicit permission values are `REPO_READ`, `REPO_WRITE` and `REPO_ADMIN`. |
| **visibility** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | (optional) if specified, this will limit the resulting repository list based on the repositories visibility. Valid values are *public* or *private*. |

*Example response representations:*

-

  200 - application/json ([page](#paging-params))

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"slug":"my-repo","id":1,"name":"My repo","scmId":"git","state":"AVAILABLE","statusMessage":"Available","forkable":true,"project":{"key":"PRJ","id":1,"name":"My Cool Project","description":"The description for my cool project.","public":true,"type":"NORMAL","links":{"self":[{"href":"http://link/to/project"}]}},"public":true,"links":{"clone":[{"href":"ssh://git@<baseURL>/PRJ/my-repo.git","name":"ssh"},{"href":"https://<baseURL>/scm/PRJ/my-repo.git","name":"http"}],"self":[{"href":"http://link/to/repository"}]}}],"start":0}

  A page of repositories.

-

  400 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The `visibility` parameter contains an invalid value
