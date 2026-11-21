<!-- Bitbucket Server 5.10.0 REST API — resource group: projects--changes (1 endpoints) -->

## /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/changes

###### Methods

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/changes?since&until

*This is a [paged API](#paging-params)*. *This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Retrieve a page of changes made in a specified commit.

**Note:** The implementation will apply a hard cap ({@code page.max.changes}) and it is not possible to request subsequent content when that cap is exceeded.

The authenticated user must have **REPO_READ** permission for the specified repository to call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **since** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the commit to which `until` should be compared to produce a page of changes. If not specified the commit's first parent is assumed (if one exists) |
| **until** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the commit to retrieve changes for |

*Example response representations:*

-

  200 - application/json ([page](#paging-params))

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"contentId":"abcdef0123abcdef4567abcdef8987abcdef6543","fromContentId":"bcdef0123abcdef4567abcdef8987abcdef6543a","path":{"components":["new","path","to","file.txt"],"parent":"new/path/to","name":"file.txt","extension":"txt","toString":"new/path/to/file.txt"},"executable":false,"percentUnchanged":98,"type":"MOVE","nodeType":"FILE","srcPath":{"components":["path","to","file.txt"],"parent":"path/to","name":"file.txt","extension":"txt","toString":"path/to/file.txt"},"srcExecutable":false,"links":{"self":[{"href":"http://link/to/restchange"}]}}],"start":0}

  A page of changes

-

  400 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The until parameter was not supplied

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the repository.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The repository or the since or until parameters supplied does not exist.
