<!-- Bitbucket Server 5.10.0 REST API — resource group: projects--last-modified (2 endpoints) -->

## /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/last-modified

###### Methods

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/last-modified?at

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Streams files in the requested `path` with the last commit to modify each file. Commit modifications are traversed starting from the `at` commit or, if not specified, from the tip of the default branch.

Unless the repository is public, the authenticated user must have **REPO_READ** access to call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **at** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the commit to use as the starting point when listing files and calculating modifications |

*Example response representations:*

-

  200 - application/json (modifications)

  ###### Example

      {"files":{"pom.xml":{"id":"def0123abcdef4567abcdef8987abcdef6543abc","displayId":"def0123abcd","author":{"name":"charlie","emailAddress":"charlie@example.com"},"authorTimestamp":1527228363490,"committer":{"name":"charlie","emailAddress":"charlie@example.com"},"committerTimestamp":1527228363490,"message":"More work on feature 1","parents":[{"id":"abcdef0123abcdef4567abcdef8987abcdef6543","displayId":"abcdef0"}]},"README.md":{"id":"abcdef0123abcdef4567abcdef8987abcdef6543","displayId":"abcdef0123a","author":{"name":"charlie","emailAddress":"charlie@example.com"},"authorTimestamp":1527228363490,"committer":{"name":"charlie","emailAddress":"charlie@example.com"},"committerTimestamp":1527228363490,"message":"WIP on feature 1","parents":[{"id":"abcdef0123abcdef4567abcdef8987abcdef6543","displayId":"abcdef0"}]}},"latestCommit":{"id":"def0123abcdef4567abcdef8987abcdef6543abc","displayId":"def0123abcd","author":{"name":"charlie","emailAddress":"charlie@example.com"},"authorTimestamp":1527228363490,"committer":{"name":"charlie","emailAddress":"charlie@example.com"},"committerTimestamp":1527228363490,"message":"More work on feature 1","parents":[{"id":"abcdef0123abcdef4567abcdef8987abcdef6543","displayId":"abcdef0"}]}}

  A map of files to the last commit that modified them, and the latest commit to update the requested path.

-

  400 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  No `at` commit was specified. When streaming modifications, an explicit starting commit must be supplied.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the repository.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The repository does not exist or does not contain the `at` commit, or the `at` commit does not contain the requested path.

## /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/last-modified/{path:.\*}

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **path** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the path within the repository whose files should be streamed |

###### Methods

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/last-modified/{path:.\*}?at

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Streams files in the requested `path` with the last commit to modify each file. Commit modifications are traversed starting from the `at` commit or, if not specified, from the tip of the default branch.

Unless the repository is public, the authenticated user must have **REPO_READ** access to call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **at** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the commit to use as the starting point when listing files and calculating modifications |

*Example response representations:*

-

  200 - application/json (modifications)

  ###### Example

      {"files":{"pom.xml":{"id":"def0123abcdef4567abcdef8987abcdef6543abc","displayId":"def0123abcd","author":{"name":"charlie","emailAddress":"charlie@example.com"},"authorTimestamp":1527228363490,"committer":{"name":"charlie","emailAddress":"charlie@example.com"},"committerTimestamp":1527228363490,"message":"More work on feature 1","parents":[{"id":"abcdef0123abcdef4567abcdef8987abcdef6543","displayId":"abcdef0"}]},"README.md":{"id":"abcdef0123abcdef4567abcdef8987abcdef6543","displayId":"abcdef0123a","author":{"name":"charlie","emailAddress":"charlie@example.com"},"authorTimestamp":1527228363490,"committer":{"name":"charlie","emailAddress":"charlie@example.com"},"committerTimestamp":1527228363490,"message":"WIP on feature 1","parents":[{"id":"abcdef0123abcdef4567abcdef8987abcdef6543","displayId":"abcdef0"}]}},"latestCommit":{"id":"def0123abcdef4567abcdef8987abcdef6543abc","displayId":"def0123abcd","author":{"name":"charlie","emailAddress":"charlie@example.com"},"authorTimestamp":1527228363490,"committer":{"name":"charlie","emailAddress":"charlie@example.com"},"committerTimestamp":1527228363490,"message":"More work on feature 1","parents":[{"id":"abcdef0123abcdef4567abcdef8987abcdef6543","displayId":"abcdef0"}]}}

  A map of files to the last commit that modified them, and the latest commit to update the requested path.

-

  400 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  No `at` commit was specified. When streaming modifications, an explicit starting commit must be supplied.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the repository.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The repository does not exist or does not contain the `at` commit, or the `at` commit does not contain the requested path.
