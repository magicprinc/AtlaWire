<!-- Bitbucket Server 5.10.0 REST API — resource group: projects--webhooks (6 endpoints) -->

## /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/webhooks

###### Methods

#### POST

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Create a webhook for the repository specified via the URL.

The authenticated user must have **REPO_ADMIN** permission for the specified repository to call this resource.

*Example request representations:*

-

  application/json

*Example response representations:*

-

  200 - application/json (webhook)

  ###### Example

      {"id":10,"name":"Webhook Name","createdDate":1513106011000,"updatedDate":1513106011000,"events":["repo:refs_updated","repo:modified"],"configuration":{"secret":"password"},"url":"http://example.com","active":true}

  A created webhook.

-

  400 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The webhook parameters were invalid or not supplied.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to create webhooks in the repository.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The repository does not exist.

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/webhooks?event&statistics

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Find webhooks in this repository.

The authenticated user must have **REPO_ADMIN** permission for the specified repository to call this resource.

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
<td>event</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></td>
<td>list of {@link com.atlassian.webhooks.WebhookEvent} ids to filter for</td>
</tr>
<tr>
<td>statistics</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#boolean">boolean</a>
Default: <code>false</code></td>
<td>{@code true} if statistics should be provided for all found webhooks</td>
</tr>
</tbody>
</table>

*Example response representations:*

-

  200 - application/json (webhook)

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"id":10,"name":"Webhook Name","createdDate":1513106011000,"updatedDate":1513106011000,"events":["repo:refs_updated","repo:modified"],"configuration":{"secret":"password"},"url":"http://example.com","active":true}],"start":0}

  A list of webhooks.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to find webhooks in the repository.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The repository does not exist.

## /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/webhooks/test

###### Methods

#### POST

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/webhooks/test?url

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Test connectivity to a specific endpoint.

The authenticated user must have **REPO_ADMIN** permission for the specified repository to call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **url** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the url in which to connect to |

*Example response representations:*

-

  200 - application/json (webhook)

  ###### Example

      {"request":{"url":"http://example.com/callback","body":null,"method":"POST","headers":{"Accept":"*/*"}},"response":{"status":200,"headers":{"Content-Type":"application/json"},"body":"{\n  \"accepted\": true\n}"}}

  a webhook.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to test a connection.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The repository does not exist.

## /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/webhooks/{webhookId}

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **webhookId** | *[int](http://www.w3.org/TR/xmlschema-2/#int)* | the existing webhook id |

###### Methods

#### DELETE

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Delete a webhook for the repository specified via the URL.

The authenticated user must have **REPO_ADMIN** permission for the specified repository to call this resource.

*Example response representations:*

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to delete webhooks in the repository.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The repository does not exist, or webhook does not exist in this repository.

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/webhooks/{webhookId}?statistics

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Get a webhook by id.

The authenticated user must have **REPO_ADMIN** permission for the specified repository to call this resource.

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
<td>statistics</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#boolean">boolean</a>
Default: <code>false</code></td>
<td></td>
</tr>
</tbody>
</table>

*Example response representations:*

-

  200 - application/json (webhook)

  ###### Example

      {"id":10,"name":"Webhook Name","createdDate":1513106011000,"updatedDate":1513106011000,"events":["repo:refs_updated","repo:modified"],"configuration":{"secret":"password"},"url":"http://example.com","active":true}

  a webhook.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to get a webhook in the repository.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The repository does not exist, or the webhook does not exist in the repository.

#### PUT

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Update an existing webhook.

The authenticated user must have **REPO_ADMIN** permission for the specified repository to call this resource.

*Example request representations:*

-

  application/json

*Example response representations:*

-

  200 - application/json (webhook)

  ###### Example

      {"id":10,"name":"Webhook Name","createdDate":1513106011000,"updatedDate":1513106011000,"events":["repo:refs_updated","repo:modified"],"configuration":{"secret":"password"},"url":"http://example.com","active":true}

  a webhook.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to update a webhook in this repository.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The repository does not exist, or the webhook does not exist in the repository.

## /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/webhooks/{webhookId}/latest

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **webhookId** | *[int](http://www.w3.org/TR/xmlschema-2/#int)* | id of the webhook |

###### Methods

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/webhooks/{webhookId}/latest?event&outcome

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Get the latest invocations for a specific webhook.

The authenticated user must have **REPO_ADMIN** permission for the specified repository to call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **event** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the string id of a specific event to retrieve the last invocation for. |
| **outcome** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the outcome to filter for. Can be SUCCESS, FAILURE, ERROR. None specified means that the all will be considered |

*Example response representations:*

-

  200 - application/json (webhookInvocation)

  ###### Example

      {"id":10,"event":"repo:created","duration":155,"start":1513106011,"finish":1513106166,"request":{"method":"POST","url":"http://example.com/callback"},"result":{"description":"200","outcome":"SUCCESS"}}

  a webhook invocation dataset.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to get webhook invocations in the repository.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The repository does not exist, or the webhook does not exist in the repository.

## /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/webhooks/{webhookId}/statistics

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **webhookId** | *[int](http://www.w3.org/TR/xmlschema-2/#int)* | id of the webhook |

###### Methods

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/webhooks/{webhookId}/statistics?event

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Get the statistics for a specific webhook.

The authenticated user must have **REPO_ADMIN** permission for the specified repository to call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **event** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the string id of a specific event to retrieve the last invocation for. May be empty, in which case all events are considered |

*Example response representations:*

-

  200 - application/json (webhookInvocation)

  ###### Example

      {"lastSuccess":{"id":10,"event":"repo:created","duration":155,"start":1513106011,"finish":1513106166,"request":{"method":"POST","url":"http://example.com/callback"},"result":{"description":"200","outcome":"SUCCESS"}},"lastFailure":{"id":11,"event":"repo:refs_updated","duration":100,"start":1513106011,"finish":1513106111,"request":{"method":"POST","url":"http://example.com/callback"},"result":{"description":"404","outcome":"FAILURE"}},"lastError":{"id":12,"event":"repo:modified","duration":100,"start":1513106011,"finish":1513106111,"request":{"method":"POST","url":"http://example.com/callback"},"result":{"description":"Detailed error message","outcome":"ERROR"}},"counts":100}

  a webhook invocation dataset.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to get webhook statistics in the repository.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The repository does not exist, or the webhook does not exist in the repository.

## /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/webhooks/{webhookId}/statistics/summary

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **webhookId** | *[int](http://www.w3.org/TR/xmlschema-2/#int)* | id of the webhook |

###### Methods

#### GET

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Get the statistics summary for a specific webhook.

The authenticated user must have **REPO_ADMIN** permission for the specified repository to call this resource.

*Example response representations:*

-

  200 - application/json (webhookInvocation)

  ###### Example

      {"lastSuccess":{"id":10,"event":"repo:created","duration":155,"start":1513106011,"finish":1513106166,"request":{"method":"POST","url":"http://example.com/callback"},"result":{"description":"200","outcome":"SUCCESS"}},"lastFailure":{"id":11,"event":"repo:refs_updated","duration":100,"start":1513106011,"finish":1513106111,"request":{"method":"POST","url":"http://example.com/callback"},"result":{"description":"404","outcome":"FAILURE"}},"lastError":{"id":12,"event":"repo:modified","duration":100,"start":1513106011,"finish":1513106111,"request":{"method":"POST","url":"http://example.com/callback"},"result":{"description":"Detailed error message","outcome":"ERROR"}},"counts":100}

  a webhook invocation dataset.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to get webhook statistics summary in the repository.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The repository does not exist, or the webhook does not exist in the repository.
