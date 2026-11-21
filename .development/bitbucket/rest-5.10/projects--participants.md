<!-- Bitbucket Server 5.10.0 REST API — resource group: projects--participants (1 endpoints) -->

## /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/participants

###### Methods

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/participants?direction&filter&role

*This is a [paged API](#paging-params)*. *This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Retrieve a page of participant users for all the pull requests to or from the specified repository.

Optionally clients can specify following filters.

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
<td>filter</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></td>
<td>(optional) return only users, whose username, name or email address contain the {@code filter} value</td>
</tr>
<tr>
<td>role</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></td>
<td>(optional) The role associated with the pull request participant. This must be one of {@code AUTHOR}, {@code REVIEWER}, or{@code PARTICIPANT}</td>
</tr>
</tbody>
</table>

*Example response representations:*

-

  200 - application/json ([page](#paging-params))

  ###### Example

      {"name":"charlie","emailAddress":"charlie@example.com"}

  A page of users that match the search criteria.

-

  400 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":"field_a","message":"A detailed validation error message for field_a.","exceptionName":null},{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The request was malformed.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the specified repository.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository does not exist.
