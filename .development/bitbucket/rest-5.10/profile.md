<!-- Bitbucket Server 5.10.0 REST API — resource group: profile (1 endpoints) -->

## /rest/api/1.0/profile/recent/repos

###### Methods

#### GET

###### /rest/api/1.0/profile/recent/repos?permission

*This is a [paged API](#paging-params)*.

Retrieve a page of recently accessed repositories for the currently authenticated user.

Repositories are ordered from most recently to least recently accessed.

Only authenticated users may call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **permission** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | (optional) if specified, it must be a valid repository permission level name and will limit the resulting repository list to ones that the requesting user has the specified permission level to. If not specified, the default `REPO_READ` permission level will be assumed. |

*Example response representations:*

-

  200 - application/json ([page](#paging-params))

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"slug":"my-repo","id":1,"name":"My repo","scmId":"git","state":"AVAILABLE","statusMessage":"Available","forkable":true,"project":{"key":"PRJ","id":1,"name":"My Cool Project","description":"The description for my cool project.","public":true,"type":"NORMAL","links":{"self":[{"href":"http://link/to/project"}]}},"public":true,"links":{"clone":[{"href":"ssh://git@<baseURL>/PRJ/my-repo.git","name":"ssh"},{"href":"https://<baseURL>/scm/PRJ/my-repo.git","name":"http"}],"self":[{"href":"http://link/to/repository"}]}}],"start":0}

  A page of recently accessed repositories.

-

  400 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The permission level is unknown or not related to repository.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The request is unauthenticated.
