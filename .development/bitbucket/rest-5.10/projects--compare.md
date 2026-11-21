<!-- Bitbucket Server 5.10.0 REST API — resource group: projects--compare (3 endpoints) -->

## /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/compare/diff{path:.\*}

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **path** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the path to the file to diff (optional) |

###### Methods

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/compare/diff{path:.\*}?from&to&fromRepo&srcPath&contextLines&whitespace

*This is a [paged API](#paging-params)*. *This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Gets a diff of the changes available in the {@code from} commit but not in the {@code to} commit.

If either the {@code from} or {@code to} commit are not specified, they will be replaced by the default branch of their containing repository.

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
<td>from</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></td>
<td>the source commit (can be a partial/full commit ID or qualified/unqualified ref name)</td>
</tr>
<tr>
<td>to</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></td>
<td>the target commit (can be a partial/full commit ID or qualified/unqualified ref name)</td>
</tr>
<tr>
<td>fromRepo</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a>
Default:</td>
<td>an optional parameter specifying the source repository containing the source commit if that commit is not present in the current repository; the repository can be specified by either its ID fromRepo=42 or by its project key plus its repo slug separated by a slash: fromRepo=projectKey/repoSlug</td>
</tr>
<tr>
<td>srcPath</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></td>
<td></td>
</tr>
<tr>
<td>contextLines</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#int">int</a>
Default: <code>-1</code></td>
<td>an optional number of context lines to include around each added or removed lines in the diff</td>
</tr>
<tr>
<td>whitespace</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></td>
<td>an optional whitespace flag which can be set to <code>ignore-all</code></td>
</tr>
</tbody>
</table>

*Example response representations:*

-

  200 - application/json ([page](#paging-params))

  ###### Example

      {"diffs":[{"source":{"components":["path","to","file.txt"],"parent":"path/to","name":"file.txt","extension":"txt","toString":"path/to/file.txt"},"destination":{"components":["path","to","file.txt"],"parent":"path/to","name":"file.txt","extension":"txt","toString":"path/to/file.txt"},"hunks":[{"sourceLine":1,"sourceSpan":1,"destinationLine":1,"destinationSpan":2,"segments":[{"type":"REMOVED","lines":[{"destination":1,"source":1,"line":"import sys","truncated":false}],"truncated":false},{"type":"ADDED","lines":[{"destination":1,"source":2,"line":"import re","truncated":false},{"destination":2,"source":3,"line":"import os","truncated":false}],"truncated":false}],"truncated":false}],"truncated":"true","contextLines":"10","fromHash":"a0f224fd7bd5f28ea5a752d41b9c9f6372fc6d9e","toHash":"dc93f22caadcde35daf5cc2cd65d2738c87e31ca","whiteSpace":"SHOW"}],"truncated":"true","contextLines":"10","fromHash":"a0f224fd7bd5f28ea5a752d41b9c9f6372fc6d9e","toHash":"dc93f22caadcde35daf5cc2cd65d2738c87e31ca","whiteSpace":"SHOW"}

  The diff of the changes.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The source or target commit does not exist.

## /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/compare/commits

###### Methods

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/compare/commits?from&to&fromRepo

*This is a [paged API](#paging-params)*. *This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Gets the commits accessible from the {@code from} commit but not in the {@code to} commit.

If either the {@code from} or {@code to} commit are not specified, they will be replaced by the default branch of their containing repository.

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
<td>from</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></td>
<td>the source commit (can be a partial/full commit ID or qualified/unqualified ref name)</td>
</tr>
<tr>
<td>to</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></td>
<td>the target commit (can be a partial/full commit ID or qualified/unqualified ref name)</td>
</tr>
<tr>
<td>fromRepo</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a>
Default:</td>
<td>an optional parameter specifying the source repository containing the source commit if that commit is not present in the current repository; the repository can be specified by either its ID fromRepo=42 or by its project key plus its repo slug separated by a slash: fromRepo=projectKey/repoSlug</td>
</tr>
</tbody>
</table>

*Example response representations:*

-

  200 - application/json ([page](#paging-params))

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"id":"def0123abcdef4567abcdef8987abcdef6543abc","displayId":"def0123abcd","author":{"name":"charlie","emailAddress":"charlie@example.com"},"authorTimestamp":1527228363490,"committer":{"name":"charlie","emailAddress":"charlie@example.com"},"committerTimestamp":1527228363490,"message":"More work on feature 1","parents":[{"id":"abcdef0123abcdef4567abcdef8987abcdef6543","displayId":"abcdef0"}]}],"start":0,"authorCount":1,"totalCount":1}

  A page of commits.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The source or target commit does not exist.

## /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/compare/changes

###### Methods

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/compare/changes?from&to&fromRepo

*This is a [paged API](#paging-params)*. *This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Gets the file changes available in the {@code from} commit but not in the {@code to} commit.

If either the {@code from} or {@code to} commit are not specified, they will be replaced by the default branch of their containing repository.

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
<td>from</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></td>
<td>the source commit (can be a partial/full commit ID or qualified/unqualified ref name)</td>
</tr>
<tr>
<td>to</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></td>
<td>the target commit (can be a partial/full commit ID or qualified/unqualified ref name)</td>
</tr>
<tr>
<td>fromRepo</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a>
Default:</td>
<td>an optional parameter specifying the source repository containing the source commit if that commit is not present in the current repository; the repository can be specified by either its ID fromRepo=42 or by its project key plus its repo slug separated by a slash: fromRepo=projectKey/repoSlug</td>
</tr>
</tbody>
</table>

*Example response representations:*

-

  200 - application/json ([page](#paging-params))

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"contentId":"abcdef0123abcdef4567abcdef8987abcdef6543","fromContentId":"bcdef0123abcdef4567abcdef8987abcdef6543a","path":{"components":["new","path","to","file.txt"],"parent":"new/path/to","name":"file.txt","extension":"txt","toString":"new/path/to/file.txt"},"executable":false,"percentUnchanged":98,"type":"MOVE","nodeType":"FILE","srcPath":{"components":["path","to","file.txt"],"parent":"path/to","name":"file.txt","extension":"txt","toString":"path/to/file.txt"},"srcExecutable":false,"links":{"self":[{"href":"http://link/to/restchange"}]}}],"start":0}

  A page of changes.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The source or target commit does not exist.
