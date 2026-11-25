<!-- bitbucket 5.10.0 - resource group: dashboard -->

# `dashboard`

2 method(s) as this deployment serves them. Source: its own `application.wadl`.

## GET /dashboard/pull-request-suggestions

Retrieves a page of suggestions for pull requests that the currently authenticated user may wish to raise. Such suggestions are based on ref changes occurring and so contain the ref change that prompted the suggestion plus the time the change event occurred. Changes will be returned in descending order based on the time the change that prompted the suggestion occurred. Note that although the response is a page object, the interface does not support paging, however a limit can be applied to the size of the returned page.

| query | type | default |
|---|---|---|
| `changesSince` | string | `172800` |
| `limit` | int | `3` |

## GET /dashboard/pull-requests

Retrieve a page of pull requests where the current authenticated user is involved as either a reviewer, author or a participant. The request may be filtered by pull request state, role or participant status.

| query | type | default |
|---|---|---|
| `state` | string |  |
| `role` | string |  |
| `participantStatus` | string |  |
| `order` | string |  |
| `closedSince` | string |  |
