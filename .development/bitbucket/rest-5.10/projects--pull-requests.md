<!-- Bitbucket Server 5.10.0 REST API — resource group: projects--pull-requests (18 endpoints) -->

## /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests

###### Methods

#### POST

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Create a new pull request between two branches. The branches may be in the same repository, or different ones. When using different repositories, they must still be in the same {@link Repository#getHierarchyId() hierarchy}.

The authenticated user must have **REPO_READ** permission for the "from" and "to"repositories to call this resource.

*Example request representations:*

-

  application/json

  ###### Example

      {"title":"Talking Nerdy","description":"It’s a kludge, but put the tuple from the database in the cache.","state":"OPEN","open":true,"closed":false,"fromRef":{"id":"refs/heads/feature-ABC-123","repository":{"slug":"my-repo","name":null,"project":{"key":"PRJ"}}},"toRef":{"id":"refs/heads/master","repository":{"slug":"my-repo","name":null,"project":{"key":"PRJ"}}},"locked":false,"reviewers":[{"user":{"name":"charlie"}}]}

*Example response representations:*

-

  201 - application/json (pullRequest)

  ###### Example

      {"id":101,"version":1,"title":"Talking Nerdy","description":"It’s a kludge, but put the tuple from the database in the cache.","state":"OPEN","open":true,"closed":false,"createdDate":1359075920,"updatedDate":1359075920,"fromRef":{"id":"refs/heads/feature","displayId":"feature-ABC-123","latestCommit":"babecafebabecafebabecafebabecafebabecafe","repository":{"slug":"my-repo","id":1,"name":"My repo","scmId":"git","state":"AVAILABLE","statusMessage":"Available","forkable":true,"project":{"key":"PRJ","id":1,"name":"My Cool Project","description":"The description for my cool project.","public":true,"type":"NORMAL","links":{"self":[{"href":"http://link/to/project"}]}},"public":true,"links":{"clone":[{"href":"ssh://git@<baseURL>/PRJ/my-repo.git","name":"ssh"},{"href":"https://<baseURL>/scm/PRJ/my-repo.git","name":"http"}],"self":[{"href":"http://link/to/repository"}]}}},"toRef":{"id":"refs/heads/master","displayId":"master","latestCommit":"cafebabecafebabecafebabecafebabecafebabe","repository":{"slug":"my-repo","id":1,"name":"My repo","scmId":"git","state":"AVAILABLE","statusMessage":"Available","forkable":true,"project":{"key":"PRJ","id":1,"name":"My Cool Project","description":"The description for my cool project.","public":true,"type":"NORMAL","links":{"self":[{"href":"http://link/to/project"}]}},"public":true,"links":{"clone":[{"href":"ssh://git@<baseURL>/PRJ/my-repo.git","name":"ssh"},{"href":"https://<baseURL>/scm/PRJ/my-repo.git","name":"http"}],"self":[{"href":"http://link/to/repository"}]}}},"locked":false,"author":{"user":{"name":"alice","emailAddress":"alice@example.com","id":92903040,"displayName":"Alice","active":true,"slug":"alice","type":"NORMAL"},"role":"PARTICIPANT","approved":false,"status":"UNAPPROVED"},"reviewers":[{"user":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"lastReviewedCommit":"7549846524f8aed2bd1c0249993ae1bf9d3c9998","role":"REVIEWER","approved":false,"status":"UNAPPROVED"}],"participants":[],"links":{"self":[{"href":"http://link/to/pullrequest"}]}}

  The newly created pull request.

-

  400 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":"field_a","message":"A detailed validation error message for field_a.","exceptionName":null},{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The pull request entity supplied in the request was malformed.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to create a pull request between the two specified repositories.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  One of the specified repositories or branches does not exist.

-

  409 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  One of the following error cases occurred (check the error message for more details):

  - There was a problem resolving one or more reviewers.
  - The specified branches were the same.
  - The *to* branch is already up-to-date with all the commits on the *from* branch.
  - A pull request between the two branches already exists.

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests?direction&at&state&order&withAttributes&withProperties

*This is a [paged API](#paging-params)*. *This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Retrieve a page of pull requests to or from the specified repository.

The authenticated user must have **REPO_READ** permission for the specified repository to call this resource. Optionally clients can specify PR participant filters. Each filter has a mandatory {@code username.N} parameter, and the optional {@code role.N} and {@code approved.N} parameters.

- {@code username.N} - the "root" of a single participant filter, where "N" is a natural number starting from 1. This allows clients to specify multiple participant filters, by providing consecutive filters as {@code username.1}, {@code username.2} etc. Note that the filters numbering has to start with 1 and be continuous for all filters to be processed. The total allowed number of participant filters is 10 and all filters exceeding that limit will be dropped.
- {@code role.N}(optional) the role associated with {@code username.N}. This must be one of {@code AUTHOR}, {@code REVIEWER}, or{@code PARTICIPANT}
- {@code approved.N}(optional) the approved status associated with {@code username.N}. That is whether {@code username.N} has approved the PR. Either {@code true}, or {@code false}

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
<td>direction</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a>
Default: <code>incoming</code></td>
<td>(optional, defaults to INCOMING) the direction relative to the specified repository. Either INCOMING or OUTGOING.</td>
</tr>
<tr>
<td>at</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></td>
<td>(optional) a fully-qualified branch ID to find pull requests to or from, such as {@code refs/heads/master}</td>
</tr>
<tr>
<td>state</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></td>
<td>(optional, defaults to OPEN). Supply ALL to return pull request in any state. If a state is supplied only pull requests in the specified state will be returned. Either OPEN, DECLINED or MERGED.</td>
</tr>
<tr>
<td>order</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></td>
<td>(optional, defaults to NEWEST) the order to return pull requests in, either OLDEST (as in: "oldest first") or NEWEST.</td>
</tr>
<tr>
<td>withAttributes</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#boolean">boolean</a>
Default: <code>true</code></td>
<td>(optional) defaults to true, whether to return additional pull request attributes</td>
</tr>
<tr>
<td>withProperties</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#boolean">boolean</a>
Default: <code>true</code></td>
<td>(optional) defaults to true, whether to return additional pull request properties</td>
</tr>
</tbody>
</table>

*Example response representations:*

-

  200 - application/json ([page](#paging-params))

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"id":101,"version":1,"title":"Talking Nerdy","description":"It’s a kludge, but put the tuple from the database in the cache.","state":"OPEN","open":true,"closed":false,"createdDate":1359075920,"updatedDate":1359085920,"fromRef":{"id":"refs/heads/feature-ABC-123","repository":{"slug":"my-repo","name":null,"project":{"key":"PRJ"}}},"toRef":{"id":"refs/heads/master","repository":{"slug":"my-repo","name":null,"project":{"key":"PRJ"}}},"locked":false,"author":{"user":{"name":"tom","emailAddress":"tom@example.com","id":115026,"displayName":"Tom","active":true,"slug":"tom","type":"NORMAL"},"role":"AUTHOR","approved":true,"status":"APPROVED"},"reviewers":[{"user":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"lastReviewedCommit":"7549846524f8aed2bd1c0249993ae1bf9d3c9998","role":"REVIEWER","approved":true,"status":"APPROVED"}],"participants":[{"user":{"name":"harry","emailAddress":"harry@example.com","id":99049120,"displayName":"Harry","active":true,"slug":"harry","type":"NORMAL"},"role":"PARTICIPANT","approved":true,"status":"APPROVED"},{"user":{"name":"dick","emailAddress":"dick@example.com","id":3083181,"displayName":"Dick","active":true,"slug":"dick","type":"NORMAL"},"role":"PARTICIPANT","approved":false,"status":"UNAPPROVED"}],"links":{"self":[{"href":"http://link/to/pullrequest"}]}}],"start":0}

  A page of pull requests that match the search criteria.

-

  400 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":"field_a","message":"A detailed validation error message for field_a.","exceptionName":null},{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The request was malformed.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the specified pull request.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository or pull request does not exist.

## /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **pullRequestId** | *[long](http://www.w3.org/TR/xmlschema-2/#long)* | the ID of the pull request within the repository |

###### Methods

#### GET

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Retrieve a pull request.

The authenticated user must have **REPO_READ** permission for the repository that this pull request targets to call this resource.

*Example response representations:*

-

  200 - application/json (pullRequest)

  ###### Example

      {"id":101,"version":1,"title":"Talking Nerdy","description":"It’s a kludge, but put the tuple from the database in the cache.","state":"OPEN","open":true,"closed":false,"createdDate":1359075920,"updatedDate":1359085920,"fromRef":{"id":"refs/heads/feature-ABC-123","repository":{"slug":"my-repo","name":null,"project":{"key":"PRJ"}}},"toRef":{"id":"refs/heads/master","repository":{"slug":"my-repo","name":null,"project":{"key":"PRJ"}}},"locked":false,"author":{"user":{"name":"tom","emailAddress":"tom@example.com","id":115026,"displayName":"Tom","active":true,"slug":"tom","type":"NORMAL"},"role":"AUTHOR","approved":true,"status":"APPROVED"},"reviewers":[{"user":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"lastReviewedCommit":"7549846524f8aed2bd1c0249993ae1bf9d3c9998","role":"REVIEWER","approved":true,"status":"APPROVED"}],"participants":[{"user":{"name":"harry","emailAddress":"harry@example.com","id":99049120,"displayName":"Harry","active":true,"slug":"harry","type":"NORMAL"},"role":"PARTICIPANT","approved":true,"status":"APPROVED"},{"user":{"name":"dick","emailAddress":"dick@example.com","id":3083181,"displayName":"Dick","active":true,"slug":"dick","type":"NORMAL"},"role":"PARTICIPANT","approved":false,"status":"UNAPPROVED"}],"links":{"self":[{"href":"http://link/to/pullrequest"}]}}

  The specified pull request.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the specified pull request.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository or pull request does not exist.

#### PUT

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Update the title, description, reviewers or destination branch of an existing pull request.

**Note:** the *reviewers* list may be updated using this resource. However the *author* and *participants* list may not.

The authenticated user must either:

- be the author of the pull request and have the **REPO_READ** permission for the repository that this pull request targets; or
- have the **REPO_WRITE** permission for the repository that this pull request targets

to call this resource.

*Example request representations:*

-

  application/json

  ###### Example

      {"id":101,"version":2,"title":"Talking Nerdy","description":"It’s a hack, but force AO to eagerly initialize to avoid deadlocks.","reviewers":[{"user":{"name":"charlie"}}]}

*Example response representations:*

-

  200 - application/json (pullRequest)

  ###### Example

      {"id":101,"version":1,"title":"Talking Nerdy","description":"It’s a kludge, but put the tuple from the database in the cache.","state":"OPEN","open":true,"closed":false,"createdDate":1359075920,"updatedDate":1359085920,"fromRef":{"id":"refs/heads/feature-ABC-123","repository":{"slug":"my-repo","name":null,"project":{"key":"PRJ"}}},"toRef":{"id":"refs/heads/master","repository":{"slug":"my-repo","name":null,"project":{"key":"PRJ"}}},"locked":false,"author":{"user":{"name":"tom","emailAddress":"tom@example.com","id":115026,"displayName":"Tom","active":true,"slug":"tom","type":"NORMAL"},"role":"AUTHOR","approved":true,"status":"APPROVED"},"reviewers":[{"user":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"lastReviewedCommit":"7549846524f8aed2bd1c0249993ae1bf9d3c9998","role":"REVIEWER","approved":true,"status":"APPROVED"}],"participants":[{"user":{"name":"harry","emailAddress":"harry@example.com","id":99049120,"displayName":"Harry","active":true,"slug":"harry","type":"NORMAL"},"role":"PARTICIPANT","approved":true,"status":"APPROVED"},{"user":{"name":"dick","emailAddress":"dick@example.com","id":3083181,"displayName":"Dick","active":true,"slug":"dick","type":"NORMAL"},"role":"PARTICIPANT","approved":false,"status":"UNAPPROVED"}],"links":{"self":[{"href":"http://link/to/pullrequest"}]}}

  The updated pull request.

-

  400 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":"field_a","message":"A detailed validation error message for field_a.","exceptionName":null},{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  One of the following error cases occurred (check the error message for more details):

  - The request tried to modify the *author* or *participants*.
  - The pull request's version attribute was not specified.
  - A reviewer's username was not specified.
  - The toRef id value was incorrectly left blank

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to update the specified pull request.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  One of the specified repositories or branches does not exist.

-

  409 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  One of the following error cases occurred (check the error message for more details):

  - The specified version is out of date.
  - One of the reviewers could not be added to the pull request.
  - If updating the destination branch:
    - There is already an open pull request with an identical to branch
    - The from and new to branch *are* the same
    - The new destination branch up-to-date is up-to-date with all of changes from the from branch, resulting in a pull request with nothing to merge

#### DELETE

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Deletes a pull request.

To call this resource, users must be authenticated and have permission to view the pull request. Additionally, they must:

- be the pull request author, if the system is configured to allow authors to delete their own pull requests (this is the default) OR
- have repository administrator permission for the repository the pull request is targeting

A body containing the version of the pull request must be provided with this request.

    { "version": 1 }

*Example request representations:*

-

  application/json

  ###### Example

      {"version":1}

*Example response representations:*

-

  204 - application/json

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the specified pull request.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository or pull request does not exist.

## /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/activities

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **pullRequestId** | *[long](http://www.w3.org/TR/xmlschema-2/#long)* | the id of the pull request within the repository |

###### Methods

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/activities?fromId&fromType

*This is a [paged API](#paging-params)*. *This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Retrieve a page of activity associated with a pull request.

Activity items include comments, approvals, rescopes (i.e. adding and removing of commits), merges and more.

Different types of activity items may be introduced in newer versions of Stash or by user installed plugins, so clients should be flexible enough to handle unexpected entity shapes in the returned page.

The authenticated user must have **REPO_READ** permission for the repository that this pull request targets to call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **fromId** | *[long](http://www.w3.org/TR/xmlschema-2/#long)* | (optional) the id of the activity item to use as the first item in the returned page |
| **fromType** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | (required if **fromId** is present) the type of the activity item specified by **fromId** (either **COMMENT** or **ACTIVITY**) |

*Example response representations:*

-

  200 - application/json ([page](#paging-params))

  ###### Example

      {"size":3,"limit":25,"isLastPage":true,"values":[{"id":101,"createdDate":1359065920,"user":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"action":"COMMENTED","commentAction":"ADDED","comment":{"properties":{"key":"value"},"id":1,"version":1,"text":"A measured reply.","author":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"createdDate":1527228363421,"updatedDate":1527228363421,"comments":[{"properties":{"key":"value"},"id":1,"version":1,"text":"An insightful comment.","author":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"createdDate":1527228363411,"updatedDate":1527228363411,"comments":[],"tasks":[],"permittedOperations":{"editable":true,"deletable":true}}],"tasks":[],"permittedOperations":{"editable":true,"deletable":true}},"commentAnchor":{"line":1,"lineType":"CONTEXT","fileType":"FROM","path":"path/to/file","srcPath":"path/to/file"}},{"id":101,"createdDate":1359065920,"user":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"action":"RESCOPED","fromHash":"abcdeabcdeabcdeabcdeabcdeabcdeabcdeabcde","previousFromHash":"bcdeabcdeabcdeabcdeabcdeabcdeabcdeabcdea","previousToHash":"cdeabcdeabcdeabcdeabcdeabcdeabcdeabcdeab","toHash":"ddeabcdeabcdeabcdeabcdeabcdeabcdeabcdeabc","added":{"commits":[{"id":"abcdef0123abcdef4567abcdef8987abcdef6543","displayId":"abcdef0123a","author":{"name":"charlie","emailAddress":"charlie@example.com"},"authorTimestamp":1527228363490,"committer":{"name":"charlie","emailAddress":"charlie@example.com"},"committerTimestamp":1527228363490,"message":"WIP on feature 1","parents":[{"id":"abcdef0123abcdef4567abcdef8987abcdef6543","displayId":"abcdef0"}]}],"total":1},"removed":{"commits":[{"id":"def0123abcdef4567abcdef8987abcdef6543abc","displayId":"def0123abcd","author":{"name":"charlie","emailAddress":"charlie@example.com"},"authorTimestamp":1527228363490,"committer":{"name":"charlie","emailAddress":"charlie@example.com"},"committerTimestamp":1527228363490,"message":"More work on feature 1","parents":[{"id":"abcdef0123abcdef4567abcdef8987abcdef6543","displayId":"abcdef0"}]}],"total":1}},{"id":101,"createdDate":1359085920,"user":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"action":"MERGED"}],"start":0}

  A page of activity relating to the specified pull request.

-

  400 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":"field_a","message":"A detailed validation error message for field_a.","exceptionName":null},{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The request was malformed.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the specified pull request.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository or pull request does not exist.

## /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/decline

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **pullRequestId** | *[long](http://www.w3.org/TR/xmlschema-2/#long)* |  |

###### Methods

#### POST

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/decline?version

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Decline a pull request.

The authenticated user must have **REPO_READ** permission for the repository that this pull request targets to call this resource.

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
<td>the current version of the pull request. If the server's version isn't the same as the specified version the operation will fail. To determine the current version of the pull request it should be fetched from the server prior to this operation. Look for the 'version' attribute in the returned JSON structure.</td>
</tr>
</tbody>
</table>

*Example response representations:*

-

  200

  The pull request was declined.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the pull request.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository or pull request does not exist.

-

  409 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The pull request is not OPEN or has been updated since the version specified by the request.

## /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/merge

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **pullRequestId** | *[long](http://www.w3.org/TR/xmlschema-2/#long)* | the id of the pull request within the repository |

###### Methods

#### POST

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/merge?version

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Merge the specified pull request.

The authenticated user must have **REPO_WRITE** permission for the repository that this pull request targets to call this resource.

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
<td>the current version of the pull request. If the server's version isn't the same as the specified version the operation will fail. To determine the current version of the pull request it should be fetched from the server prior to this operation. Look for the 'version' attribute in the returned JSON structure.</td>
</tr>
</tbody>
</table>

*Example response representations:*

-

  200 - application/json (pullRequest)

  ###### Example

      {"id":101,"version":1,"title":"Talking Nerdy","description":"It’s a kludge, but put the tuple from the database in the cache.","state":"MERGED","open":false,"closed":true,"createdDate":1359075920,"updatedDate":1359115920,"closedDate":1359115920,"fromRef":{"id":"refs/heads/feature-ABC-123","repository":{"slug":"my-repo","name":null,"project":{"key":"PRJ"}}},"toRef":{"id":"refs/heads/master","repository":{"slug":"my-repo","name":null,"project":{"key":"PRJ"}}},"locked":false,"author":{"user":{"name":"tom","emailAddress":"tom@example.com","id":115026,"displayName":"Tom","active":true,"slug":"tom","type":"NORMAL"},"role":"AUTHOR","approved":true,"status":"APPROVED"},"reviewers":[{"user":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"lastReviewedCommit":"7549846524f8aed2bd1c0249993ae1bf9d3c9998","role":"REVIEWER","approved":true,"status":"APPROVED"}],"participants":[{"user":{"name":"harry","emailAddress":"harry@example.com","id":99049120,"displayName":"Harry","active":true,"slug":"harry","type":"NORMAL"},"role":"PARTICIPANT","approved":true,"status":"APPROVED"},{"user":{"name":"dick","emailAddress":"dick@example.com","id":3083181,"displayName":"Dick","active":true,"slug":"dick","type":"NORMAL"},"role":"PARTICIPANT","approved":true,"status":"APPROVED"}],"properties":{"commentCount":3},"links":{"self":[{"href":"http://link/to/pullrequest"}]}}

  The merged pull request.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to merge the specified pull request.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository or pull request does not exist.

-

  409 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  One of the following error cases occurred (check the error message for more details):

  - The pull request has conflicts.
  - A merge check vetoed the merge.
  - The specified version is out of date.
  - The specified pull request is not open.

#### GET

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Test whether a pull request can be merged.

A pull request may not be merged if:

- there are conflicts that need to be manually resolved before merging; and/or
- one or more merge checks have vetoed the merge.

The authenticated user must have **REPO_READ** permission for the repository that this pull request targets to call this resource.

*Example response representations:*

-

  200 - application/json (pullRequest)

  ###### Example

      {"canMerge":false,"conflicted":true,"outcome":"CONFLICTED","vetoes":[{"summaryMessage":"You may not merge after 6pm on a Friday.","detailedMessage":"It is likely that your Blood Alcohol Content (BAC) exceeds the threshold for making sensible decisions regarding pull requests. Please try again on Monday."}]}

  The mergeability status of the pull request.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the specified pull request.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository or pull request does not exist.

-

  409 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified pull request is not open.

## /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/reopen

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **pullRequestId** | *[long](http://www.w3.org/TR/xmlschema-2/#long)* | the id of the pull request within the repository |

###### Methods

#### POST

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/reopen?version

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Re-open a declined pull request.

The authenticated user must have **REPO_READ** permission for the repository that this pull request targets to call this resource.

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
<td>the current version of the pull request. If the server's version isn't the same as the specified version the operation will fail. To determine the current version of the pull request it should be fetched from the server prior to this operation. Look for the 'version' attribute in the returned JSON structure.</td>
</tr>
</tbody>
</table>

*Example response representations:*

-

  200 - application/json (pullRequest)

  ###### Example

      {"id":101,"version":1,"title":"Talking Nerdy","description":"It’s a kludge, but put the tuple from the database in the cache.","state":"OPEN","open":true,"closed":false,"createdDate":1359075920,"updatedDate":1359085920,"fromRef":{"id":"refs/heads/feature-ABC-123","repository":{"slug":"my-repo","name":null,"project":{"key":"PRJ"}}},"toRef":{"id":"refs/heads/master","repository":{"slug":"my-repo","name":null,"project":{"key":"PRJ"}}},"locked":false,"author":{"user":{"name":"tom","emailAddress":"tom@example.com","id":115026,"displayName":"Tom","active":true,"slug":"tom","type":"NORMAL"},"role":"AUTHOR","approved":true,"status":"APPROVED"},"reviewers":[{"user":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"lastReviewedCommit":"7549846524f8aed2bd1c0249993ae1bf9d3c9998","role":"REVIEWER","approved":true,"status":"APPROVED"}],"participants":[{"user":{"name":"harry","emailAddress":"harry@example.com","id":99049120,"displayName":"Harry","active":true,"slug":"harry","type":"NORMAL"},"role":"PARTICIPANT","approved":true,"status":"APPROVED"},{"user":{"name":"dick","emailAddress":"dick@example.com","id":3083181,"displayName":"Dick","active":true,"slug":"dick","type":"NORMAL"},"role":"PARTICIPANT","approved":false,"status":"UNAPPROVED"}],"links":{"self":[{"href":"http://link/to/pullrequest"}]}}

  The merged pull request.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to reopen the specified pull request.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository or pull request does not exist.

-

  409 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  One of the following error cases occurred (check the error message for more details):

  - The pull request is not in a declined state.
  - The specified version is out of date.

## /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/approve

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **pullRequestId** | *[long](http://www.w3.org/TR/xmlschema-2/#long)* | the id of the pull request within the repository |

###### Methods

#### POST

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Approve a pull request as the current user. Implicitly adds the user as a participant if they are not already.

The authenticated user must have **REPO_READ** permission for the repository that this pull request targets to call this resource.

**Deprecated since 4.2**. Use /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/participants/{userSlug} instead

*Example response representations:*

-

  201 - application/json (participant)

  ###### Example

      {"user":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"lastReviewedCommit":"7549846524f8aed2bd1c0249993ae1bf9d3c9998","role":"REVIEWER","approved":true,"status":"APPROVED"}

  Details of the new participant

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the pull request.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository or pull request does not exist.

-

  409 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The pull request is not open.

#### DELETE

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Remove approval from a pull request as the current user. This does not remove the user as a participant.

The authenticated user must have **REPO_READ** permission for the repository that this pull request targets to call this resource.

**Deprecated since 4.2**. Use /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/participants/{userSlug} instead

*Example response representations:*

-

  201 - application/json (participant)

  ###### Example

      {"user":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"lastReviewedCommit":"7549846524f8aed2bd1c0249993ae1bf9d3c9998","role":"REVIEWER","approved":false,"status":"UNAPPROVED"}

  Details of the updated participant

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the pull request.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository or pull request does not exist or the current user is not a participant on the pull request.

-

  409 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The pull request is not open.

## /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/changes

###### Methods

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/changes?changeScope&sinceId&untilId&withComments

*This is a [paged API](#paging-params)*. *This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Gets changes for the specified PullRequest.

If the {@code changeScope} query parameter is set to {@code unreviewed}, the application will attempt to stream unreviewed changes based on the {@code lastReviewedCommit} of the current user, which are the changes between the {@code lastReviewedCommit} and the latest commit of the source branch. The current user is considered to *not* have any unreviewed changes for the pull request when the {@code lastReviewedCommit} is either {@code null} (everything is unreviewed, so all changes are streamed), equal to the latest commit of the source branch (everything is reviewed), or no longer on the source branch (the source branch has been rebased). In these cases, the application will fall back to streaming all changes (the default), which is the effective diff for the pull request. The type of changes streamed can be determined by the {@code changeScope} parameter included in the properties map of the response.

Note: This resource is currently *not paged*. The server will return at most one page. The server will truncate the number of changes to either the request's page limit or an internal maximum, whichever is smaller. The start parameter of the page request is also ignored.

The authenticated user must have **REPO_READ** permission for the repository that this pull request targets to call this resource.

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
<td>changeScope</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a>
Default: <code>ALL</code></td>
<td>{@code UNREVIEWED} to stream the unreviewed changes for the current user (if they exist); {@code RANGE} to stream changes between two arbitrary commits (requires {@code sinceId} and {@code untilId}); otherwise {@code ALL} to stream all changes (the default)</td>
</tr>
<tr>
<td>sinceId</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></td>
<td>the since commit hash to stream changes for a {@code RANGE} arbitrary change scope</td>
</tr>
<tr>
<td>untilId</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></td>
<td>the until commit hash to stream changes for a {@code RANGE} arbitrary change scope</td>
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

      {"size":1,"limit":25,"isLastPage":true,"values":[{"contentId":"5c279d6c7a3a053a145905aa9682ce02c16449e9","fromContentId":"7b86ad1a05b4259b8fa54497a8be0bd359a405bd","path":{"components":["path","to","unreviewed","file.txt"],"parent":"path/to/unreviewed","name":"file.txt","extension":"txt","toString":"path/to/unreviewed/file.txt"},"executable":false,"percentUnchanged":98,"type":"MOVE","nodeType":"FILE","srcPath":{"components":["path","to","file.txt"],"parent":"path/to","name":"file.txt","extension":"txt","toString":"path/to/file.txt"},"srcExecutable":false,"links":{"self":[null]},"properties":{"unreviewedCommits":1}}],"start":0}

  A page of unreviewed Changes for the current user from the supplied pull request, including the unreviewedCommits in the properties map.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the repository or pull request.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The repository or pull request does not exist.

## /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/comments

###### Methods

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/comments?anchorState&diffType&fromHash&path&toHash

*This is a [paged API](#paging-params)*. *This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Gets comments for the specified PullRequest.

The authenticated user must have **REPO_READ** permission for the repository that this pull request targets to call this resource.

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
<td>anchorState</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a>
Default: <code>ACTIVE</code></td>
<td>{@code ACTIVE} to stream the active comments; {@code ORPHANED} to stream the orphaned comments; {@code ALL} to stream both the active and the orphaned comments;</td>
</tr>
<tr>
<td>diffType</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></td>
<td>{@code EFFECTIVE} to stream the comments related to the effective diff of the pull request; {@code RANGE} to stream comments related to a commit range between two arbitrary commits (requires {@code fromHash} and {@code toHash}); {@code COMMIT} to stream comments related to a commit between two arbitrary commits (requires {@code fromHash} and {@code toHash})</td>
</tr>
<tr>
<td>fromHash</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></td>
<td>the from commit hash to stream comments for a {@code RANGE} or {@code COMMIT} arbitrary change scope</td>
</tr>
<tr>
<td>path</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></td>
<td>the path to stream comments for a given path</td>
</tr>
<tr>
<td>toHash</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></td>
<td>the to commit hash to stream comments for a {@code RANGE} or {@code COMMIT} arbitrary change scope</td>
</tr>
</tbody>
</table>

*Example response representations:*

-

  200 - application/json ([page](#paging-params))

  ###### Example

      {"properties":{"key":"value"},"id":1,"version":1,"text":"A measured reply.","author":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"createdDate":1527228363421,"updatedDate":1527228363421,"comments":[{"properties":{"key":"value"},"id":1,"version":1,"text":"An insightful comment.","author":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"createdDate":1527228363411,"updatedDate":1527228363411,"comments":[],"tasks":[],"permittedOperations":{"editable":true,"deletable":true}}],"tasks":[],"permittedOperations":{"editable":true,"deletable":true}}

  A page of Comments from the supplied pull request.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the repository or pull request.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The repository or pull request does not exist.

#### POST

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Add a new comment.

Comments can be added in a few places by setting different attributes:

General pull request comment:

     {
         "text": "An insightful general comment on a pull request."
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
             "diffType": "RANGE",
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
     

For file and line comments, 'path' refers to the path of the file to which the comment should be applied and 'srcPath' refers to the path the that file used to have (only required for copies and moves). Also, fromHash and toHash refer to the sinceId / untilId (respectively) used to produce the diff on which the comment was added. Finally diffType refers to the type of diff the comment was added on. For backwards compatibility purposes if no diffType is provided and no fromHash/toHash pair is provided the diffType will be resolved to 'EFFECTIVE'. In any other cases the diffType is REQUIRED.

For line comments, 'line' refers to the line in the diff that the comment should apply to. 'lineType' refers to the type of diff hunk, which can be:

- 'ADDED' - for an added line;
- 'REMOVED' - for a removed line; or
- 'CONTEXT' - for a line that was unmodified but is in the vicinity of the diff.

'fileType' refers to the file of the diff to which the anchor should be attached - which is of relevance when displaying the diff in a side-by-side way. Currently the supported values are:

- 'FROM' - the source file of the diff
- 'TO' - the destination file of the diff

If the current user is not a participant the user is added as a watcher of the pull request.

The authenticated user must have **REPO_READ** permission for the repository that this pull request targets to call this resource.

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

  The currently authenticated user has insufficient permissions to view the pull request, create a comment or watch the pull request.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  Unable to find the supplied project, repository, pull request or parent comment

## /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/comments/{commentId}

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **commentId** | *[long](http://www.w3.org/TR/xmlschema-2/#long)* | the id of the comment to retrieve |

###### Methods

#### GET

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Retrieves a pull request comment.

The authenticated user must have **REPO_READ** permission for the repository that this pull request targets to call this resource.

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

  Unable to find the supplied project, repository, pull request or comment

#### DELETE

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/comments/{commentId}?version

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Delete a pull request comment. Anyone can delete their own comment. Only users with **REPO_ADMIN** and above may delete comments created by other users.

The authenticated user must have **REPO_READ** permission for the repository that this pull request targets to call this resource.

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

  Unable to find the supplied project, repository or pull request.

-

  409 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The comment has replies or the version supplied does not match the current version.

#### PUT

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Update the text of a comment. Only the user who created a comment may update it.

**Note:** the supplied supplied JSON object must contain a `version` that must match the server's version of the comment or the update will fail. To determine the current version of the comment, the comment should be fetched from the server prior to the update. Look for the 'version' attribute in the returned JSON structure.

The authenticated user must have **REPO_READ** permission for the repository that this pull request targets to call this resource.

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

  The currently authenticated user has insufficient permissions to view the pull request, update a comment or watch the pull request.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  Unable to find the supplied project, repository, pull request or comment

-

  409 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The comment version supplied does not match the current version.

## /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/commits

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **pullRequestId** | *[long](http://www.w3.org/TR/xmlschema-2/#long)* |  |

###### Methods

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/commits?withCounts

*This is a [paged API](#paging-params)*. *This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Retrieve commits for the specified pull request.

The authenticated user must have **REPO_READ** permission for the repository that this pull request targets to call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **withCounts** | *[boolean](http://www.w3.org/TR/xmlschema-2/#boolean)* | if set to true, the service will add "authorCount" and "totalCount" at the end of the page. "authorCount" is the number of different authors and "totalCount" is the total number of commits. |

*Example response representations:*

-

  200 - application/json ([page](#paging-params))

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"id":"def0123abcdef4567abcdef8987abcdef6543abc","displayId":"def0123abcd","author":{"name":"charlie","emailAddress":"charlie@example.com"},"authorTimestamp":1527228363490,"committer":{"name":"charlie","emailAddress":"charlie@example.com"},"committerTimestamp":1527228363490,"message":"More work on feature 1","parents":[{"id":"abcdef0123abcdef4567abcdef8987abcdef6543","displayId":"abcdef0"}]}],"start":0,"authorCount":1,"totalCount":1}

  a page of commits from the supplied pull request.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the repository or pull request.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The repository or pull request does not exist.

## /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/diff

###### Methods

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/diff?contextLines&diffType&sinceId&srcPath&untilId&whitespace&withComments

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Streams a diff within a pull request.

If the specified file has been copied, moved or renamed, the `srcPath` must also be specified to produce the correct diff.

Note: This RESTful endpoint is currently *not paged*. The server will internally apply a hard cap to the streamed lines, and it is not possible to request subsequent pages if that cap is exceeded.

The authenticated user must have **REPO_READ** permission for the repository that this pull request targets to call this resource.

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
<td>diffType</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a>
Default: <code>EFFECTIVE</code></td>
<td>the type of diff being requested. When {@code withComments} is {@code true} this works as a hint to the system to attach the correct set of comments to the diff</td>
</tr>
<tr>
<td>sinceId</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></td>
<td>the since commit hash to stream a diff between two arbitrary hashes</td>
</tr>
<tr>
<td>srcPath</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></td>
<td>the previous path to the file, if the file has been copied, moved or renamed</td>
</tr>
<tr>
<td>untilId</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></td>
<td>the until commit hash to stream a diff between two arbitrary hashes</td>
</tr>
<tr>
<td>whitespace</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></td>
<td>optional whitespace flag which can be set to <code>ignore-all</code></td>
</tr>
<tr>
<td>withComments</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#boolean">boolean</a>
Default: <code>true</code></td>
<td><code>true</code> to embed comments in the diff (the default); otherwise, <code>false</code> to stream the diff without comments</td>
</tr>
</tbody>
</table>

*Example response representations:*

-

  200 - application/json (diffs)

  ###### Example

      {"diffs":[{"source":{"components":["path","to","file.txt"],"parent":"path/to","name":"file.txt","extension":"txt","toString":"path/to/file.txt"},"destination":{"components":["path","to","file.txt"],"parent":"path/to","name":"file.txt","extension":"txt","toString":"path/to/file.txt"},"hunks":[{"sourceLine":1,"sourceSpan":1,"destinationLine":1,"destinationSpan":2,"segments":[{"type":"REMOVED","lines":[{"destination":1,"source":1,"line":"import sys","truncated":false}],"truncated":false},{"type":"ADDED","lines":[{"destination":1,"source":2,"line":"import re","truncated":false,"conflictMarker":"OURS","commentIds":[1]},{"destination":2,"source":3,"line":"import os","truncated":false}],"truncated":false}],"truncated":false}],"lineComments":[{"properties":{"key":"value"},"id":1,"version":1,"text":"An insightful comment.","author":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"createdDate":1527228363411,"updatedDate":1527228363411,"comments":[],"tasks":[],"permittedOperations":{"editable":true,"deletable":true}}],"truncated":"true","contextLines":"10","fromHash":"a0f224fd7bd5f28ea5a752d41b9c9f6372fc6d9e","toHash":"dc93f22caadcde35daf5cc2cd65d2738c87e31ca","whiteSpace":"SHOW"}],"truncated":"true","contextLines":"10","fromHash":"a0f224fd7bd5f28ea5a752d41b9c9f6372fc6d9e","toHash":"dc93f22caadcde35daf5cc2cd65d2738c87e31ca","whiteSpace":"SHOW"}

  a page of differences from a pull request.

-

  400 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":"field_a","message":"A detailed validation error message for field_a.","exceptionName":null},{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  If the request was malformed.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the repository or pull request.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The repository or pull request does not exist.

## /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/diff/{path:.\*}

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **path** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the path to the file which should be diffed (optional) |

###### Methods

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/diff/{path:.\*}?contextLines&diffType&sinceId&srcPath&untilId&whitespace&withComments

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Streams a diff within a pull request.

If the specified file has been copied, moved or renamed, the `srcPath` must also be specified to produce the correct diff.

Note: This RESTful endpoint is currently *not paged*. The server will internally apply a hard cap to the streamed lines, and it is not possible to request subsequent pages if that cap is exceeded.

The authenticated user must have **REPO_READ** permission for the repository that this pull request targets to call this resource.

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
<td>diffType</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a>
Default: <code>EFFECTIVE</code></td>
<td>the type of diff being requested. When {@code withComments} is {@code true} this works as a hint to the system to attach the correct set of comments to the diff</td>
</tr>
<tr>
<td>sinceId</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></td>
<td>the since commit hash to stream a diff between two arbitrary hashes</td>
</tr>
<tr>
<td>srcPath</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></td>
<td>the previous path to the file, if the file has been copied, moved or renamed</td>
</tr>
<tr>
<td>untilId</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></td>
<td>the until commit hash to stream a diff between two arbitrary hashes</td>
</tr>
<tr>
<td>whitespace</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></td>
<td>optional whitespace flag which can be set to <code>ignore-all</code></td>
</tr>
<tr>
<td>withComments</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#boolean">boolean</a>
Default: <code>true</code></td>
<td><code>true</code> to embed comments in the diff (the default); otherwise, <code>false</code> to stream the diff without comments</td>
</tr>
</tbody>
</table>

*Example response representations:*

-

  200 - application/json (diffs)

  ###### Example

      {"diffs":[{"source":{"components":["path","to","file.txt"],"parent":"path/to","name":"file.txt","extension":"txt","toString":"path/to/file.txt"},"destination":{"components":["path","to","file.txt"],"parent":"path/to","name":"file.txt","extension":"txt","toString":"path/to/file.txt"},"hunks":[{"sourceLine":1,"sourceSpan":1,"destinationLine":1,"destinationSpan":2,"segments":[{"type":"REMOVED","lines":[{"destination":1,"source":1,"line":"import sys","truncated":false}],"truncated":false},{"type":"ADDED","lines":[{"destination":1,"source":2,"line":"import re","truncated":false,"conflictMarker":"OURS","commentIds":[1]},{"destination":2,"source":3,"line":"import os","truncated":false}],"truncated":false}],"truncated":false}],"lineComments":[{"properties":{"key":"value"},"id":1,"version":1,"text":"An insightful comment.","author":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"createdDate":1527228363411,"updatedDate":1527228363411,"comments":[],"tasks":[],"permittedOperations":{"editable":true,"deletable":true}}],"truncated":"true","contextLines":"10","fromHash":"a0f224fd7bd5f28ea5a752d41b9c9f6372fc6d9e","toHash":"dc93f22caadcde35daf5cc2cd65d2738c87e31ca","whiteSpace":"SHOW"}],"truncated":"true","contextLines":"10","fromHash":"a0f224fd7bd5f28ea5a752d41b9c9f6372fc6d9e","toHash":"dc93f22caadcde35daf5cc2cd65d2738c87e31ca","whiteSpace":"SHOW"}

  a page of differences from a pull request.

-

  400 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":"field_a","message":"A detailed validation error message for field_a.","exceptionName":null},{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  If the request was malformed.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the repository or pull request.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The repository or pull request does not exist.

## /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/participants

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **pullRequestId** | *[long](http://www.w3.org/TR/xmlschema-2/#long)* | the id of the pull request within the repository |

###### Methods

#### GET

*This is a [paged API](#paging-params)*. *This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Retrieves a page of the participants for a given pull request.

The authenticated user must have **REPO_READ** permission for the repository that this pull request targets to call this resource.

*Example response representations:*

-

  201 - application/json ([page](#paging-params))

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"user":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"lastReviewedCommit":"7549846524f8aed2bd1c0249993ae1bf9d3c9998","role":"REVIEWER","approved":true,"status":"APPROVED"}],"start":0}

  Details of the participants in this pull request

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the pull request.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository or pull request does not exist.

#### POST

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Assigns a participant to an explicit role in pull request. Currently only the REVIEWER role may be assigned.

If the user is not yet a participant in the pull request, they are made one and assigned the supplied role.

If the user is already a participant in the pull request, their previous role is replaced with the supplied role unless they are already assigned the AUTHOR role which cannot be changed and will result in a Bad Request (400) response code.

The authenticated user must have **REPO_WRITE** permission for the repository that this pull request targets to call this resource.

*Example request representations:*

-

  application/json

  ###### Example

      {"user":{"name":"charlie"},"role":"REVIEWER"}

*Example response representations:*

-

  201 - application/json (participant)

  ###### Example

      {"user":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"lastReviewedCommit":"7549846524f8aed2bd1c0249993ae1bf9d3c9998","role":"REVIEWER","approved":false,"status":"UNAPPROVED"}

  The created or updated participant.

-

  400 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The request does not have the username and role, or is attempting an invalid assignment

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to update the pull request.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository or pull request does not exist.

#### DELETE

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/participants?username

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Unassigns a participant from the REVIEWER role they may have been given in a pull request.

If the participant has no explicit role this method has no effect.

Afterwards, the user will still remain a participant in the pull request but their role will be reduced to PARTICIPANT. This is because once made a participant of a pull request, a user will forever remain a participant. Only their role may be altered.

The authenticated user must have **REPO_WRITE** permission for the repository that this pull request targets to call this resource.

**Deprecated since 4.2**. Use /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/participants/{userSlug} instead.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **username** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the participant's user name |

*Example response representations:*

-

  204

  The update completed.

-

  400 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The request does not have the username

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to update the pull request.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository or pull request does not exist.

## /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/participants/{userSlug}

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **pullRequestId** | *[long](http://www.w3.org/TR/xmlschema-2/#long)* | the id of the pull request within the repository |
| **userSlug** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the slug for the user changing their status |
| **pullRequestId** | *[long](http://www.w3.org/TR/xmlschema-2/#long)* | the id of the pull request within the repository |

###### Methods

#### DELETE

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Unassigns a participant from the REVIEWER role they may have been given in a pull request.

If the participant has no explicit role this method has no effect.

Afterwards, the user will still remain a participant in the pull request but their role will be reduced to PARTICIPANT. This is because once made a participant of a pull request, a user will forever remain a participant. Only their role may be altered.

The authenticated user must have **REPO_WRITE** permission for the repository that this pull request targets to call this resource.

**Deprecated since 4.2**. Use /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/participants/{userSlug} instead.

*Example response representations:*

-

  204

  The update completed.

-

  400 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The request does not have the username

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to update the pull request.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository or pull request does not exist.

#### PUT

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Change the current user's status for a pull request. Implicitly adds the user as a participant if they are not already. If the current user is the author, this method will fail.

The possible values for {@code status} are **UNAPPROVED**, **NEEDS_WORK**, or **APPROVED**.

If the new {@code status} is **NEEDS_WORK** or **APPROVED** then the {@code lastReviewedCommit} for the participant will be updated to the latest commit of the source branch of the pull request.

The authenticated user must have **REPO_READ** permission for the repository that this pull request targets to call this resource.

*Example request representations:*

-

  application/json

  ###### Example

      {"user":{"name":"charlie"},"approved":true,"status":"APPROVED"}

*Example response representations:*

-

  201 - application/json (participant)

  ###### Example

      {"user":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"lastReviewedCommit":"7549846524f8aed2bd1c0249993ae1bf9d3c9998","role":"REVIEWER","approved":true,"status":"APPROVED"}

  Details of the new participant

-

  400 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":"field_a","message":"A detailed validation error message for field_a.","exceptionName":null},{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified status was invalid.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the pull request.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository or pull request does not exist.

-

  409 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The pull request is not open.

## /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/tasks

###### Methods

#### GET

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Retrieve the tasks associated with a pull request.

*Example response representations:*

-

  200 - application/json (task)

  ###### Example

      {"size":2,"limit":25,"isLastPage":true,"values":[{"properties":{"diffAnchorPath":"path/to/file.txt"},"anchor":{"properties":{"key":"value"},"id":1,"version":1,"text":"An insightful comment.","author":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"createdDate":1527228363411,"updatedDate":1527228363411,"comments":[],"tasks":[],"permittedOperations":{"editable":true,"deletable":true}},"author":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"createdDate":1527228364842,"id":98,"permittedOperations":{"deletable":true,"editable":true,"transitionable":true},"text":"Fix typos on the constructor's arguments","state":"OPEN"},{"properties":{"diffAnchorPath":"path/to/file.txt"},"anchor":{"properties":{"key":"value"},"id":5,"version":1,"text":"This class is deprecated.  Can you please use the replacement?","author":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"createdDate":1527228363411,"updatedDate":1527228363411,"comments":[],"tasks":[],"permittedOperations":{"editable":true,"deletable":true}},"author":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"createdDate":1527228364842,"id":99,"permittedOperations":{"deletable":false,"editable":false,"transitionable":true},"text":"Remove usage of deprecated class","state":"RESOLVED"}],"start":0}

  A page of tasks associated with the pull request.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  If the current user cannot access the pull request

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  If the pull request does not exist

## /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/tasks/count

###### Methods

#### GET

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Retrieve the total number of {@link TaskState#OPEN open} and {@link TaskState#RESOLVED resolved} tasks associated with a pull request.

*Example response representations:*

-

  200 - application/json (taskCount)

  ###### Example

      {"open":5,"resolved":2}

  Total number of {@link TaskState#OPEN open} and {@link TaskState#RESOLVED resolved} tasks associated with the pull request.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  If the current user cannot access the pull request

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  If the pull request does not exist

## /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/watch

###### Methods

#### POST

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Add the authenticated user as a watcher for the specified pull request.

The authenticated user must have **REPO_READ** permission for the repository that this pull request targets to call this resource.

*Example response representations:*

-

  204

  The user is now watching the pull request.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the pull request.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository or pull request does not exist.

#### DELETE

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Remove the authenticated user as a watcher for the specified pull request.

The authenticated user must have **REPO_READ** permission for the repository that this pull request targets to call this resource.

*Example response representations:*

-

  204

  The user is no longer watching the pull request.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the pull request.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository or pull request does not exist.
