<!-- Bitbucket Server 5.10.0 REST API — resource group: projects--commits (8 endpoints) -->

## /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/commits

###### Methods

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/commits?followRenames&ignoreMissing&merges&path&since&until&withCounts

*This is a [paged API](#paging-params)*. *This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Retrieve a page of commits from a given starting commit or "between" two commits. If no explicit commit is specified, the tip of the repository's default branch is assumed. commits may be identified by branch or tag name or by ID. A path may be supplied to restrict the returned commits to only those which affect that path.

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
<td>followRenames</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#boolean">boolean</a>
Default: <code>false</code></td>
<td>if <code>true</code>, the commit history of the specified file will be followed past renames. Only valid for a path to a single file.</td>
</tr>
<tr>
<td>ignoreMissing</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#boolean">boolean</a>
Default: <code>false</code></td>
<td><code>true</code> to ignore missing commits, <code>false</code> otherwise</td>
</tr>
<tr>
<td>merges</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></td>
<td>if present, controls how merge commits should be filtered. Can be either <code>exclude</code>, to exclude merge commits, <code>include</code>, to include both merge commits and non-merge commits or <code>only</code>, to only return merge commits.</td>
</tr>
<tr>
<td>path</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></td>
<td>an optional path to filter commits by</td>
</tr>
<tr>
<td>since</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></td>
<td>the commit ID or ref (exclusively) to retrieve commits after</td>
</tr>
<tr>
<td>until</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></td>
<td>the commit ID (SHA1) or ref (inclusively) to retrieve commits before</td>
</tr>
<tr>
<td>withCounts</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#boolean">boolean</a>
Default: <code>false</code></td>
<td>optionally include the total number of commits and total number of unique authors</td>
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

  400 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  One of the supplied commit IDs or refs was invalid.

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

## /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/commits/{commitId}

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **commitId** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the commit ID to retrieve |

###### Methods

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/commits/{commitId}?path

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Retrieve a single commit *identified by its ID*\>. In general, that ID is a SHA1. <u>From 2.11, ref names like "refs/heads/master" are no longer accepted by this resource.</u>

The authenticated user must have **REPO_READ** permission for the specified repository to call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **path** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | an optional path to filter the commit by. If supplied the details returned *may not* be for the specified commit. Instead, starting from the specified commit, they will be the details for the first commit affecting the specified path. |

*Example response representations:*

-

  200 - application/json (commit)

  ###### Example

      {"id":"abcdef0123abcdef4567abcdef8987abcdef6543","displayId":"abcdef0123a","author":{"name":"charlie","emailAddress":"charlie@example.com"},"authorTimestamp":1527228363490,"committer":{"name":"charlie","emailAddress":"charlie@example.com"},"committerTimestamp":1527228363490,"message":"WIP on feature 1","parents":[{"id":"abcdef0123abcdef4567abcdef8987abcdef6543","displayId":"abcdef0"}]}

  A commit.

-

  400 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The supplied commit ID was invalid.

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

## /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/commits/{commitId}/changes

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **commitId** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the commit to retrieve changes for |

###### Methods

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/commits/{commitId}/changes?since&withComments

*This is a [paged API](#paging-params)*. *This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Retrieve a page of changes made in a specified commit.

**Note:** The implementation will apply a hard cap ({@code page.max.changes}) and it is not possible to request subsequent content when that cap is exceeded.

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
<td>since</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></td>
<td>the commit to which <code>until</code> should be compared to produce a page of changes. If not specified the commit's first parent is assumed (if one exists)</td>
</tr>
<tr>
<td>withComments</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#boolean">boolean</a>
Default: <code>true</code></td>
<td>{@code true} to apply comment counts in the changes (the default); otherwise, {@code false} to stream changes without comment counts</td>
</tr>
</tbody>
</table>

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

## /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/commits/{commitId}/comments

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **commitId** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the *full {@link Commit#getId() ID}* of the commit within the repository |

###### Methods

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/commits/{commitId}/comments?path&since

*This is a [paged API](#paging-params)*. *This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Retrieves the commit discussion comments that match the specified search criteria.

It is possible to retrieve commit discussion comments that are anchored to a range of commits by providing the {@code sinceId} that the comments anchored from.

The authenticated user must have **REPO_READ** permission for the repository that the commit is in to call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **path** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the path to the file on which comments were made |
| **since** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | For a merge commit, a parent can be provided to specify which diff the comments are on. For a commit range, a {@code sinceId} can be provided to specify where the comments are anchored from. |

*Example response representations:*

-

  200 - application/json ([page](#paging-params))

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"id":101,"version":1,"title":"Talking Nerdy","description":"It’s a kludge, but put the tuple from the database in the cache.","state":"OPEN","open":true,"closed":false,"createdDate":1359075920,"updatedDate":1359085920,"fromRef":{"id":"refs/heads/feature-ABC-123","repository":{"slug":"my-repo","name":null,"project":{"key":"PRJ"}}},"toRef":{"id":"refs/heads/master","repository":{"slug":"my-repo","name":null,"project":{"key":"PRJ"}}},"locked":false,"author":{"user":{"name":"tom","emailAddress":"tom@example.com","id":115026,"displayName":"Tom","active":true,"slug":"tom","type":"NORMAL"},"role":"AUTHOR","approved":true,"status":"APPROVED"},"reviewers":[{"user":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"lastReviewedCommit":"7549846524f8aed2bd1c0249993ae1bf9d3c9998","role":"REVIEWER","approved":true,"status":"APPROVED"}],"participants":[{"user":{"name":"harry","emailAddress":"harry@example.com","id":99049120,"displayName":"Harry","active":true,"slug":"harry","type":"NORMAL"},"role":"PARTICIPANT","approved":true,"status":"APPROVED"},{"user":{"name":"dick","emailAddress":"dick@example.com","id":3083181,"displayName":"Dick","active":true,"slug":"dick","type":"NORMAL"},"role":"PARTICIPANT","approved":false,"status":"UNAPPROVED"}],"links":{"self":[{"href":"http://link/to/pullrequest"}]}}],"start":0}

  A page of comments that match the search criteria

-

  400 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":"field_a","message":"A detailed validation error message for field_a.","exceptionName":null},{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The request was malformed.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the comment

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  Unable to find the supplied project, repository, or commit. The missing entity will be specified in the error details.

#### POST

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/commits/{commitId}/comments?since

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Add a new comment.

Comments can be added in a few places by setting different attributes:

General commit comment:

     {
         "text": "An insightful general comment on a commit."
     }
     

Reply to a comment:

     {
         "text": "A measured reply.",
         "parent": {
             "id": 1
         }
     }
     

General file comment:

     {
         "text": "An insightful general comment on a file.",
         "anchor": {
             "diffType": "COMMIT",
             "fromHash": "6df3858eeb9a53a911cd17e66a9174d44ffb02cd",
             "path": "path/to/file",
             "srcPath": "path/to/file",
             "toHash": "04c7c5c931b9418ca7b66f51fe934d0bd9b2ba4b"
         }
     }
     

File line comment:

     {
         "text": "A pithy comment on a particular line within a file.",
         "anchor": {
             "diffType": "COMMIT",
             "line": 1,
             "lineType": "CONTEXT",
             "fileType": "FROM",
             "fromHash": "6df3858eeb9a53a911cd17e66a9174d44ffb02cd",
             "path": "path/to/file",
             "srcPath": "path/to/file",
             "toHash": "04c7c5c931b9418ca7b66f51fe934d0bd9b2ba4b"
     }
     }
     

**Note: general file comments are an experimental feature and may change in the near future!**

For file and line comments, 'path' refers to the path of the file to which the comment should be applied and 'srcPath' refers to the path the that file used to have (only required for copies and moves). Also, fromHash and toHash refer to the sinceId / untilId (respectively) used to produce the diff on which the comment was added. Finally diffType refers to the type of diff the comment was added on.

For line comments, 'line' refers to the line in the diff that the comment should apply to. 'lineType' refers to the type of diff hunk, which can be:

- 'ADDED' - for an added line;
- 'REMOVED' - for a removed line; or
- 'CONTEXT' - for a line that was unmodified but is in the vicinity of the diff.

'fileType' refers to the file of the diff to which the anchor should be attached - which is of relevance when displaying the diff in a side-by-side way. Currently the supported values are:

- 'FROM' - the source file of the diff
- 'TO' - the destination file of the diff

If the current user is not a participant the user is added as one and updated to watch the commit.

The authenticated user must have **REPO_READ** permission for the repository that the commit is in to call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **since** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | For a merge commit, a parent can be provided to specify which diff the comments should be on. For a commit range, a {@code sinceId} can be provided to specify where the comments should be anchored from. |

*Example request representations:*

-

  application/json

  ###### Example

      {"text":"An insightful comment.","parent":{"id":1},"anchor":{"line":1,"lineType":"CONTEXT","fileType":"FROM","path":"path/to/file","srcPath":"path/to/file"}}

*Example response representations:*

-

  201 - application/json (comment)

  ###### Example

      {"properties":{"key":"value"},"id":1,"version":1,"text":"A measured reply.","author":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"createdDate":1527228363421,"updatedDate":1527228363421,"comments":[{"properties":{"key":"value"},"id":1,"version":1,"text":"An insightful comment.","author":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"createdDate":1527228363411,"updatedDate":1527228363411,"comments":[],"tasks":[],"permittedOperations":{"editable":true,"deletable":true}}],"tasks":[],"permittedOperations":{"editable":true,"deletable":true}}

  The newly created comment.

-

  400 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The comment was not created due to a validation error.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the commit, create a comment or watch the commit.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  Unable to find the supplied project, repository, commit or parent comment. The missing entity will be specified in the error details.

## /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/commits/{commitId}/comments/{commentId}

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **commitId** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the *full {@link Commit#getId() ID}* of the commit within the repository |
| **commentId** | *[long](http://www.w3.org/TR/xmlschema-2/#long)* | the ID of the comment to retrieve |
| **commitId** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the *full {@link Commit#getId() ID}* of the commit within the repository |

###### Methods

#### GET

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Retrieves a commit discussion comment.

The authenticated user must have **REPO_READ** permission for the repository that the commit is in to call this resource.

*Example response representations:*

-

  200 - application/json (comment)

  ###### Example

      {"properties":{"key":"value"},"id":1,"version":1,"text":"A measured reply.","author":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"createdDate":1527228363421,"updatedDate":1527228363421,"comments":[{"properties":{"key":"value"},"id":1,"version":1,"text":"An insightful comment.","author":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"createdDate":1527228363411,"updatedDate":1527228363411,"comments":[],"tasks":[],"permittedOperations":{"editable":true,"deletable":true}}],"tasks":[],"permittedOperations":{"editable":true,"deletable":true}}

  The requested comment.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the comment

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  Unable to find the supplied project, repository, commit or comment. The missing entity will be specified in the error details.

#### DELETE

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/commits/{commitId}/comments/{commentId}?version

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Delete a commit comment. Anyone can delete their own comment. Only users with **REPO_ADMIN** and above may delete comments created by other users. Comments which have replies *may not be deleted*, regardless of the user's granted permissions.

The authenticated user must have **REPO_READ** permission for the repository that the commit is in to call this resource.

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
<td>version</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#int">int</a>
Default: <code>-1</code></td>
<td>The expected version of the comment. This must match the server's version of the comment or the delete will fail. To determine the current version of the comment, the comment should be fetched from the server prior to the delete. Look for the 'version' attribute in the returned JSON structure.</td>
</tr>
</tbody>
</table>

*Example response representations:*

-

  204

  The operation was successful

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to delete the comment.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  Unable to find the supplied project, repository or commit. The missing entity will be specified in the error details.

-

  409 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The comment has replies or the version supplied does not match the comment's current version.

#### PUT

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Update the text of a comment. Only the user who created a comment may update it.

**Note:** the supplied supplied JSON object must contain a `version` that must match the server's version of the comment or the update will fail. To determine the current version of the comment, the comment should be fetched from the server prior to the update. Look for the 'version' attribute in the returned JSON structure.

The authenticated user must have **REPO_READ** permission for the repository that the commit is in to call this resource.

*Example request representations:*

-

  application/json

  ###### Example

      {"version":0,"text":"A pithy comment."}

*Example response representations:*

-

  201 - application/json (comment)

  ###### Example

      {"properties":{"key":"value"},"id":1,"version":1,"text":"A measured reply.","author":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"createdDate":1527228363421,"updatedDate":1527228363421,"comments":[{"properties":{"key":"value"},"id":1,"version":1,"text":"An insightful comment.","author":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"createdDate":1527228363411,"updatedDate":1527228363411,"comments":[],"tasks":[],"permittedOperations":{"editable":true,"deletable":true}}],"tasks":[],"permittedOperations":{"editable":true,"deletable":true}}

  The newly updated comment.

-

  400 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The comment was not updated due to a validation error.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the commit, update the comment or watch the commit.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  Unable to find the supplied project, repository, commit or comment. The missing entity will be specified in the error details.

-

  409 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The comment version supplied does not match the current version.

## /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/commits/{commitId}/diff

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **commitId** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* |  |

###### Methods

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/commits/{commitId}/diff?autoSrcPath&contextLines&since&srcPath&whitespace&withComments

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Retrieve the diff between two provided revisions.

**Note:** This resource is currently *not paged*. The server will internally apply a hard cap to the streamed lines, and it is not possible to request subsequent pages if that cap is exceeded. In the event that the cap is reached, the diff will be cut short and one or more {@code truncated} flags will be set to {@code true} on the {@code "segments"}, {@code "hunks"} and {@code "diffs"} properties, as well as the top-level object, in the returned JSON response.

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
<td>autoSrcPath</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#boolean">boolean</a>
Default: <code>false</code></td>
<td>{@code true} to automatically try to find the source path when it's not provided, {@code false} otherwise. Requires the {@code path} to be provided.</td>
</tr>
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
<td>whitespace</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></td>
<td>optional whitespace flag which can be set to {@code ignore-all}</td>
</tr>
<tr>
<td>withComments</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#boolean">boolean</a>
Default: <code>true</code></td>
<td>{@code true} to embed comments in the diff (the default); otherwise {@code false} to stream the diff without comments</td>
</tr>
</tbody>
</table>

*Example response representations:*

-

  200 - application/json (diff)

  ###### Example

      {"diffs":[{"source":{"components":["path","to","file.txt"],"parent":"path/to","name":"file.txt","extension":"txt","toString":"path/to/file.txt"},"destination":{"components":["path","to","file.txt"],"parent":"path/to","name":"file.txt","extension":"txt","toString":"path/to/file.txt"},"hunks":[{"sourceLine":1,"sourceSpan":1,"destinationLine":1,"destinationSpan":2,"segments":[{"type":"REMOVED","lines":[{"destination":1,"source":1,"line":"import sys","truncated":false}],"truncated":false},{"type":"ADDED","lines":[{"destination":1,"source":2,"line":"import re","truncated":false},{"destination":2,"source":3,"line":"import os","truncated":false}],"truncated":false}],"truncated":false}],"truncated":"true","contextLines":"10","fromHash":"a0f224fd7bd5f28ea5a752d41b9c9f6372fc6d9e","toHash":"dc93f22caadcde35daf5cc2cd65d2738c87e31ca","whiteSpace":"SHOW"}],"truncated":"true","contextLines":"10","fromHash":"a0f224fd7bd5f28ea5a752d41b9c9f6372fc6d9e","toHash":"dc93f22caadcde35daf5cc2cd65d2738c87e31ca","whiteSpace":"SHOW"}

  A diff between two revisions.

-

  400 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The until parameter was not supplied.

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

## /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/commits/{commitId}/diff/{path:.\*}

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **commitId** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* |  |
| **path** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the path to the file which should be diffed (optional) |
| **commitId** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* |  |

###### Methods

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/commits/{commitId}/diff/{path:.\*}?autoSrcPath&contextLines&since&srcPath&whitespace&withComments

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Retrieve the diff between two provided revisions.

**Note:** This resource is currently *not paged*. The server will internally apply a hard cap to the streamed lines, and it is not possible to request subsequent pages if that cap is exceeded. In the event that the cap is reached, the diff will be cut short and one or more {@code truncated} flags will be set to {@code true} on the {@code "segments"}, {@code "hunks"} and {@code "diffs"} properties, as well as the top-level object, in the returned JSON response.

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
<td>autoSrcPath</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#boolean">boolean</a>
Default: <code>false</code></td>
<td>{@code true} to automatically try to find the source path when it's not provided, {@code false} otherwise. Requires the {@code path} to be provided.</td>
</tr>
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
<td>whitespace</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></td>
<td>optional whitespace flag which can be set to {@code ignore-all}</td>
</tr>
<tr>
<td>withComments</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#boolean">boolean</a>
Default: <code>true</code></td>
<td>{@code true} to embed comments in the diff (the default); otherwise {@code false} to stream the diff without comments</td>
</tr>
</tbody>
</table>

*Example response representations:*

-

  200 - application/json (diff)

  ###### Example

      {"diffs":[{"source":{"components":["path","to","file.txt"],"parent":"path/to","name":"file.txt","extension":"txt","toString":"path/to/file.txt"},"destination":{"components":["path","to","file.txt"],"parent":"path/to","name":"file.txt","extension":"txt","toString":"path/to/file.txt"},"hunks":[{"sourceLine":1,"sourceSpan":1,"destinationLine":1,"destinationSpan":2,"segments":[{"type":"REMOVED","lines":[{"destination":1,"source":1,"line":"import sys","truncated":false}],"truncated":false},{"type":"ADDED","lines":[{"destination":1,"source":2,"line":"import re","truncated":false},{"destination":2,"source":3,"line":"import os","truncated":false}],"truncated":false}],"truncated":false}],"truncated":"true","contextLines":"10","fromHash":"a0f224fd7bd5f28ea5a752d41b9c9f6372fc6d9e","toHash":"dc93f22caadcde35daf5cc2cd65d2738c87e31ca","whiteSpace":"SHOW"}],"truncated":"true","contextLines":"10","fromHash":"a0f224fd7bd5f28ea5a752d41b9c9f6372fc6d9e","toHash":"dc93f22caadcde35daf5cc2cd65d2738c87e31ca","whiteSpace":"SHOW"}

  A diff between two revisions.

-

  400 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The until parameter was not supplied.

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

## /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/commits/{commitId}/watch

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **commitId** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the *full {@link Commit#getId() ID}* of the commit within the repository |

###### Methods

#### POST

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Add the authenticated user as a watcher for the specified commit.

The authenticated user must have **REPO_READ** permission for the repository containing the commit to call this resource.

*Example response representations:*

-

  204

  The user is now watching the commit.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the pull request.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified project, repository or commit does not exist.

#### DELETE

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Remove the authenticated user as a watcher for the specified commit.

The authenticated user must have **REPO_READ** permission for the repository containing the commit to call this resource.

*Example response representations:*

-

  204

  The user is no longer watching the commit.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the pull request.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified project, repository or commit does not exist.

Compare two commits or refs. \ Each commit can be specified using either a commit ID, a qualified ref name or a unqualified ref name (the latter should be non-ambiguous).
