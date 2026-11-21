<!-- Bitbucket Server 5.10.0 REST API — resource group: projects--diff (2 endpoints) -->

## /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/diff

###### Methods

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/diff?contextLines&since&srcPath&until&whitespace

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Retrieve the diff for a specified file path between two provided revisions.

**Note:** This resource is currently *not paged*. The server will internally apply a hard cap to the streamed lines, and it is not possible to request subsequent pages if that cap is exceeded. In the event that the cap is reached, the diff will be cut short and one or more `truncated` flags will be set to `true` on the segments, hunks and diffs substructures in the returned JSON response.

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
<td>contextLines</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#int">int</a>
Default: <code>-1</code></td>
<td>the number of context lines to include around added/removed lines in the diff</td>
</tr>
<tr>
<td>since</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></td>
<td>the base revision to diff from. If omitted the parent revision of the until revision is used</td>
</tr>
<tr>
<td>srcPath</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></td>
<td>the source path for the file, if it was copied, moved or renamed</td>
</tr>
<tr>
<td>until</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></td>
<td>the target revision to diff to (required)</td>
</tr>
<tr>
<td>whitespace</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></td>
<td>optional whitespace flag which can be set to <code>ignore-all</code></td>
</tr>
</tbody>
</table>

*Example response representations:*

-

  200 - application/json (diff)

  ###### Example

      {"diffs":[{"source":{"components":["path","to","file.txt"],"parent":"path/to","name":"file.txt","extension":"txt","toString":"path/to/file.txt"},"destination":{"components":["path","to","file.txt"],"parent":"path/to","name":"file.txt","extension":"txt","toString":"path/to/file.txt"},"hunks":[{"sourceLine":1,"sourceSpan":1,"destinationLine":1,"destinationSpan":2,"segments":[{"type":"REMOVED","lines":[{"destination":1,"source":1,"line":"import sys","truncated":false}],"truncated":false},{"type":"ADDED","lines":[{"destination":1,"source":2,"line":"import re","truncated":false},{"destination":2,"source":3,"line":"import os","truncated":false}],"truncated":false}],"truncated":false}],"truncated":"true","contextLines":"10","fromHash":"a0f224fd7bd5f28ea5a752d41b9c9f6372fc6d9e","toHash":"dc93f22caadcde35daf5cc2cd65d2738c87e31ca","whiteSpace":"SHOW"}],"truncated":"true","contextLines":"10","fromHash":"a0f224fd7bd5f28ea5a752d41b9c9f6372fc6d9e","toHash":"dc93f22caadcde35daf5cc2cd65d2738c87e31ca","whiteSpace":"SHOW"}

  A diff of a file path.

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

## /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/diff/{path:.\*}

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **path** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the path to the file which should be diffed (required) |

###### Methods

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/diff/{path:.\*}?contextLines&since&srcPath&until&whitespace

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Retrieve the diff for a specified file path between two provided revisions.

**Note:** This resource is currently *not paged*. The server will internally apply a hard cap to the streamed lines, and it is not possible to request subsequent pages if that cap is exceeded. In the event that the cap is reached, the diff will be cut short and one or more `truncated` flags will be set to `true` on the segments, hunks and diffs substructures in the returned JSON response.

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
<td>contextLines</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#int">int</a>
Default: <code>-1</code></td>
<td>the number of context lines to include around added/removed lines in the diff</td>
</tr>
<tr>
<td>since</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></td>
<td>the base revision to diff from. If omitted the parent revision of the until revision is used</td>
</tr>
<tr>
<td>srcPath</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></td>
<td>the source path for the file, if it was copied, moved or renamed</td>
</tr>
<tr>
<td>until</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></td>
<td>the target revision to diff to (required)</td>
</tr>
<tr>
<td>whitespace</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></td>
<td>optional whitespace flag which can be set to <code>ignore-all</code></td>
</tr>
</tbody>
</table>

*Example response representations:*

-

  200 - application/json (diff)

  ###### Example

      {"diffs":[{"source":{"components":["path","to","file.txt"],"parent":"path/to","name":"file.txt","extension":"txt","toString":"path/to/file.txt"},"destination":{"components":["path","to","file.txt"],"parent":"path/to","name":"file.txt","extension":"txt","toString":"path/to/file.txt"},"hunks":[{"sourceLine":1,"sourceSpan":1,"destinationLine":1,"destinationSpan":2,"segments":[{"type":"REMOVED","lines":[{"destination":1,"source":1,"line":"import sys","truncated":false}],"truncated":false},{"type":"ADDED","lines":[{"destination":1,"source":2,"line":"import re","truncated":false},{"destination":2,"source":3,"line":"import os","truncated":false}],"truncated":false}],"truncated":false}],"truncated":"true","contextLines":"10","fromHash":"a0f224fd7bd5f28ea5a752d41b9c9f6372fc6d9e","toHash":"dc93f22caadcde35daf5cc2cd65d2738c87e31ca","whiteSpace":"SHOW"}],"truncated":"true","contextLines":"10","fromHash":"a0f224fd7bd5f28ea5a752d41b9c9f6372fc6d9e","toHash":"dc93f22caadcde35daf5cc2cd65d2738c87e31ca","whiteSpace":"SHOW"}

  A diff of a file path.

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
