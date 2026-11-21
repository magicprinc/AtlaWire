<!-- Bitbucket Server 5.10.0 REST API — resource group: projects--browse (2 endpoints) -->

## /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/browse

###### Methods

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/browse?at&type&blame&noContent

*This is a [paged API](#paging-params)*. *This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Retrieve a page of content for a file path at a specified revision.

The authenticated user must have **REPO_READ** permission for the specified repository to call this resource.

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
<td>at</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a>
Default:</td>
<td>the commit ID or ref to retrieve the content for.</td>
</tr>
<tr>
<td>type</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#boolean">boolean</a>
Default: <code>false</code></td>
<td>if true only the type will be returned for the file path instead of the contents.</td>
</tr>
<tr>
<td>blame</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></td>
<td>if present the blame will be returned for the file as well.</td>
</tr>
<tr>
<td>noContent</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></td>
<td>if present and used with blame only the blame is retrieved instead of the contents.</td>
</tr>
</tbody>
</table>

*Example response representations:*

-

  200 - application/json ([page](#paging-params))

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"start":0,"lines":[{"text":"print('hello world')"}]}

  A page of contents from a file.

-

  400 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The path or until parameters were not supplied.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the repository.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The repository does not exist.

## /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/browse/{path:.\*}

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **path** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the path of the file that is to be modified or created |

###### Methods

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/browse/{path:.\*}?at&type&blame&noContent

*This is a [paged API](#paging-params)*. *This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Retrieve a page of content for a file path at a specified revision.

The authenticated user must have **REPO_READ** permission for the specified repository to call this resource.

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
<td>at</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a>
Default:</td>
<td>the commit ID or ref to retrieve the content for.</td>
</tr>
<tr>
<td>type</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#boolean">boolean</a>
Default: <code>false</code></td>
<td>if true only the type will be returned for the file path instead of the contents.</td>
</tr>
<tr>
<td>blame</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></td>
<td>if present the blame will be returned for the file as well.</td>
</tr>
<tr>
<td>noContent</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></td>
<td>if present and used with blame only the blame is retrieved instead of the contents.</td>
</tr>
</tbody>
</table>

*Example response representations:*

-

  200 - application/json ([page](#paging-params))

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"start":0,"lines":[{"text":"print('hello world')"}]}

  A page of contents from a file.

-

  400 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The path or until parameters were not supplied.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the repository.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The repository does not exist.

#### PUT

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Update the content of `path`, on the given `repository` and `branch`.

This resource accepts PUT multipart form data, containing the file in a form-field named `content`.

An example [curl](http://curl.haxx.se/) request to update 'README.md' would be:

 curl -X PUT -u username:password -F content=@README.md  -F 'message=Updated using file-edit REST API'
 -F branch=master -F  sourceCommitId=5636641a50b
  http://example.com/rest/api/latest/projects/PROJECT_1/repos/repo_1/browse/README.md
 

branch: the branch on which the `path` should be modified or created

content: the full content of the file at `path`

message: the message associated with this change, to be used as the commit message. Or null if the default message should be used.

sourceCommitId: the commit ID of the file before it was edited, used to identify if content has changed. Or null if this is a new file

The file can be updated or created on a new branch. In this case, the `sourceBranch` parameter should be provided to identify the starting point for the new branch and the `branch` parameter identifies the branch to create the new commit on.

*Example response representations:*

-

  200 - application/json

  ###### Example

      {"id":"abcdef0123abcdef4567abcdef8987abcdef6543","displayId":"abcdef0123a","author":{"name":"charlie","emailAddress":"charlie@example.com"},"authorTimestamp":1527228363490,"committer":{"name":"charlie","emailAddress":"charlie@example.com"},"committerTimestamp":1527228363490,"message":"WIP on feature 1","parents":[{"id":"abcdef0123abcdef4567abcdef8987abcdef6543","displayId":"abcdef0"}]}

  The newly created commit

-

  400 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The branch or content parameters were not supplied.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user does not have write permission for the given repository

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The repository does not exist.

-

  409 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The file already exists when trying to create a file, or the given content does not modify the file, or the file has changed since the given sourceCommitId
