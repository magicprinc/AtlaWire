<!-- Bitbucket Server 5.10.0 REST API — resource group: projects--tags (2 endpoints) -->

## /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/tags

###### Methods

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/tags?filterText&orderBy

*This is a [paged API](#paging-params)*. *This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Retrieve the tags matching the supplied **filterText** param.

The authenticated user must have **REPO_READ** permission for the context repository to call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **filterText** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the text to match on |
| **orderBy** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | ordering of refs either ALPHABETICAL (by name) or MODIFICATION (last updated) |

*Example response representations:*

-

  200 - application/json ([page](#paging-params))

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"id":"release-2.0.0","displayId":"refs/tags/release-2.0.0","type":"TAG","latestCommit":"8d351a10fb428c0c1239530256e21cf24f136e73","latestChangeset":"8d351a10fb428c0c1239530256e21cf24f136e73","hash":"8d51122def5632836d1cb1026e879069e10a1e13"}],"start":0}

  The tags matching the supplied **filterText**.

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

#### POST

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Creates a tag using the information provided in the {@link RestCreateTagRequest request}

The authenticated user must have **REPO_WRITE** permission for the context repository to call this resource.

*Example request representations:*

-

  application/json

  ###### Example

      {"name":"my-tag","startPoint":"8d351a10fb428c0c1239530256e21cf24f136e73","message":"This is my tag"}

*Example response representations:*

-

  200 - application/json (tag)

  ###### Example

      {"id":"release-2.0.0","displayId":"refs/tags/release-2.0.0","type":"TAG","latestCommit":"8d351a10fb428c0c1239530256e21cf24f136e73","latestChangeset":"8d351a10fb428c0c1239530256e21cf24f136e73","hash":"8d51122def5632836d1cb1026e879069e10a1e13"}

  The created tag

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

## /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/tags/{name:.\*}

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **name** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the name of the tag to be retrieved |

###### Methods

#### GET

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Retrieve a tag in the specified repository.

The authenticated user must have **REPO_READ** permission for the context repository to call this resource.

*Example response representations:*

-

  200 - application/json (tag)

  ###### Example

      {"id":"release-2.0.0","displayId":"refs/tags/release-2.0.0","type":"TAG","latestCommit":"8d351a10fb428c0c1239530256e21cf24f136e73","latestChangeset":"8d351a10fb428c0c1239530256e21cf24f136e73","hash":"8d51122def5632836d1cb1026e879069e10a1e13"}

  The tag which matches the supplied **name**.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to read the repository.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified tag does not exist.
