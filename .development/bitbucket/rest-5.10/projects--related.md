<!-- Bitbucket Server 5.10.0 REST API — resource group: projects--related (1 endpoints) -->

## /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/related

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **projectKey** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the parent project key |

###### Methods

#### GET

*This is a [paged API](#paging-params)*. *This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Retrieve repositories which are related to this one. Related repositories are from the same {@link Repository#getHierarchyId() hierarchy} as this repository.

Only repositories to which the authenticated user has **REPO_READ** permission will be included, even if more repositories are part of this repository's hierarchy.

*Example response representations:*

-

  200 - application/json ([page](#paging-params))

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"slug":"my-repo","id":2,"name":"My repo","scmId":"git","state":"AVAILABLE","statusMessage":"Available","forkable":true,"origin":{"slug":"my-repo","id":1,"name":"My repo","scmId":"git","state":"AVAILABLE","statusMessage":"Available","forkable":true,"project":{"key":"PRJ","id":1,"name":"My Cool Project","description":"The description for my cool project.","public":true,"type":"NORMAL","links":{"self":[{"href":"http://link/to/project"}]}},"public":true,"links":{"clone":[{"href":"ssh://git@<baseURL>/PRJ/my-repo.git","name":"ssh"},{"href":"https://<baseURL>/scm/PRJ/my-repo.git","name":"http"}],"self":[{"href":"http://link/to/repository"}]}},"project":{"key":"~JDOE","id":2,"name":"John Doe","type":"PERSONAL","links":{"self":[{"href":"http://link/to/project"}]}},"links":{"clone":[{"href":"https://<baseURL>/scm/JDOE/my-repo.git","name":"http"},{"href":"ssh://git@<baseURL>/JDOE/my-repo.git","name":"ssh"}],"self":[{"href":"http://link/to/repository"}]}}],"start":0}

  A page of repositories related to the request repository.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to see the request repository.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The request repository does not exist.
