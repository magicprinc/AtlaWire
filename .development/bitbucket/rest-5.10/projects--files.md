<!-- Bitbucket Server 5.10.0 REST API — resource group: projects--files (2 endpoints) -->

## /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/files

###### Methods

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/files?at

*This is a [paged API](#paging-params)*. *This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Retrieve a page of files from particular directory of a repository. The search is done recursively, so all files from any sub-directory of the specified directory will be returned.

The authenticated user must have **REPO_READ** permission for the specified repository to call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **at** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the commit ID or ref (e.g. a branch or tag) to list the files at. If not specified the default branch will be used instead. |

*Example response representations:*

-

  200 - application/json ([page](#paging-params))

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":["path/to/file.txt"],"start":0}

  A page of files.

-

  400 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The path requested is not a directory at the supplied commit.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the repository.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The path requested does not exist at the supplied commit.

## /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/files/{path:.\*}

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
<td>path</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a>
Default:</td>
<td>the directory to list files for.</td>
</tr>
</tbody>
</table>

###### Methods

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/files/{path:.\*}?at

*This is a [paged API](#paging-params)*. *This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Retrieve a page of files from particular directory of a repository. The search is done recursively, so all files from any sub-directory of the specified directory will be returned.

The authenticated user must have **REPO_READ** permission for the specified repository to call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **at** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the commit ID or ref (e.g. a branch or tag) to list the files at. If not specified the default branch will be used instead. |

*Example response representations:*

-

  200 - application/json ([page](#paging-params))

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":["path/to/file.txt"],"start":0}

  A page of files.

-

  400 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The path requested is not a directory at the supplied commit.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the repository.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The path requested does not exist at the supplied commit.
