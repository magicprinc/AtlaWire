<!-- jira 8.22.2 - resource group: myself -->

# `myself`

3 method(s) as this deployment serves them. Source: its own `application.wadl`.

## GET /myself

Returns currently logged user. This resource cannot be accessed anonymously.

No query parameters.

## PUT /myself

Modify currently logged user. The "value" fields present will override the existing value. Fields skipped in request will not be changed. Only email and display name can be change that way. Requires user password.

No query parameters.

## PUT /myself/password

Modify caller password.

No query parameters.
