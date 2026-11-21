<!-- Bitbucket Server 5.10.0 REST API — resource group: projects--branches (2 endpoints) -->

## /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/branches

###### Methods

#### POST

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Creates a branch using the information provided in the {@link RestCreateBranchRequest request}

The authenticated user must have **REPO_WRITE** permission for the context repository to call this resource.

*Example request representations:*

-

  application/json

  ###### Example

      {"name":"my-branch","startPoint":"8d351a10fb428c0c1239530256e21cf24f136e73","message":"This is my branch"}

*Example response representations:*

-

  200 - application/json (branch)

  ###### Example

      {"id":"refs/heads/master","displayId":"master","type":"BRANCH","latestCommit":"8d51122def5632836d1cb1026e879069e10a1e13","latestChangeset":"8d51122def5632836d1cb1026e879069e10a1e13","isDefault":true}

  The created branch

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to write to the repository.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository does not exist.

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/branches?base&details&filterText&orderBy

*This is a [paged API](#paging-params)*. *This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Retrieve the branches matching the supplied **filterText** param.

The authenticated user must have **REPO_READ** permission for the specified repository to call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **base** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | base branch or tag to compare each branch to (for the metadata providers that uses that information) |
| **details** | *[boolean](http://www.w3.org/TR/xmlschema-2/#boolean)* | whether to retrieve plugin-provided metadata about each branch |
| **filterText** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the text to match on |
| **orderBy** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | ordering of refs either ALPHABETICAL (by name) or MODIFICATION (last updated) |

*Example response representations:*

-

  200 - application/json ([page](#paging-params))

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"id":"refs/heads/master","displayId":"master","type":"BRANCH","latestCommit":"8d51122def5632836d1cb1026e879069e10a1e13","latestChangeset":"8d51122def5632836d1cb1026e879069e10a1e13","isDefault":true}],"start":0}

  The branches matching the supplied **filterText**.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to read the repository.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository does not exist.

## /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/branches/default

###### Methods

#### GET

*This is a [paged API](#paging-params)*. *This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Get the default branch of the repository.

The authenticated user must have **REPO_READ** permission for the specified repository to call this resource.

*Example response representations:*

-

  200 - application/json ([page](#paging-params))

  ###### Example

      {"id":"refs/heads/master","displayId":"master","type":"BRANCH","latestCommit":"8d51122def5632836d1cb1026e879069e10a1e13","latestChangeset":"8d51122def5632836d1cb1026e879069e10a1e13","isDefault":true}

  The configured default branch for the repository.

-

  204

  The repository is empty, and has no default branch.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to read the repository.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository does not exist, or its configured default branch does not exist.

#### PUT

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Update the default branch of a repository.

The authenticated user must have **REPO_ADMIN** permission for the specified repository to call this resource.

*Example request representations:*

-

  application/json

  ###### Example

      {"id":"refs/heads/master"}

*Example response representations:*

-

  204

  The operation was successful

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to update the repository

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository does not exist.
