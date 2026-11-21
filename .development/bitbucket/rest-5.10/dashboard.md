<!-- Bitbucket Server 5.10.0 REST API — resource group: dashboard (2 endpoints) -->

## /rest/api/1.0/dashboard/pull-request-suggestions

###### Methods

#### GET

###### /rest/api/1.0/dashboard/pull-request-suggestions?changesSince&limit

*This is a [paged API](#paging-params)*.

Retrieves a page of suggestions for pull requests that the currently authenticated user may wish to raise. Such suggestions are based on ref changes occurring and so contain the ref change that prompted the suggestion plus the time the change event occurred. Changes will be returned in descending order based on the time the change that prompted the suggestion occurred.

Note that although the response is a page object, the interface does not support paging, however a limit can be applied to the size of the returned page.

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
<td>changesSince</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a>
Default: <code>172800</code></td>
<td>restrict pull request suggestions to be based on events that occurred since some time in the past. This is expressed in seconds since "now". So to return suggestions based only on activity within the past 48 hours, pass a value of 172800.</td>
</tr>
<tr>
<td>limit</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#int">int</a>
Default: <code>3</code></td>
<td>restricts the result set to return at most this many suggestions.</td>
</tr>
</tbody>
</table>

*Example response representations:*

-

  200 - application/json ([page](#paging-params))

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

  The current user is not authenticated

## /rest/api/1.0/dashboard/pull-requests

###### Methods

#### GET

###### /rest/api/1.0/dashboard/pull-requests?state&role&participantStatus&order&closedSince

*This is a [paged API](#paging-params)*.

Retrieve a page of pull requests where the current authenticated user is involved as either a reviewer, author or a participant. The request may be filtered by pull request state, role or participant status.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **state** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | (optional, defaults to returning pull requests in any state). If a state is supplied only pull requests in the specified state will be returned. Either **OPEN**, **DECLINED** or **MERGED**. Omit this parameter to return pull request in any state. |
| **role** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | (optional, defaults to returning pull requests for any role). If a role is supplied only pull requests where the authenticated user is a participant in the given role will be returned. Either **REVIEWER**, **AUTHOR** or **PARTICIPANT**. |
| **participantStatus** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | (optional, defaults to returning pull requests with any participant status). A comma separated list of participant status. That is, one or more of **UNAPPROVED**, **NEEDS_WORK**, or **APPROVED**. |
| **order** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | (optional, defaults to **NEWEST**) the order to return pull requests in, either **OLDEST** (as in: "oldest first"), **NEWEST**, **PARTICIPANT_STATUS**, or **CLOSED_DATE**. Where **CLOSED_DATE** is specified and the result set includes pull requests that are not in the closed state, these pull requests will appear first in the result set, followed by most recently closed pull requests. |
| **closedSince** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | (optional, defaults to returning pull requests regardless of closed since date). Permits returning only pull requests with a closed timestamp set more recently that (now - closedSince). Units are in seconds. So for example if closed since 86400 is set only pull requests closed in the previous 24 hours will be returned. |

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

  The current user is not authenticated
