<!-- Bitbucket Server 5.10.0 REST API — resource group: admin--mail-server (2 endpoints) -->

## /rest/api/1.0/admin/mail-server

###### Methods

#### DELETE

Deletes the current mail configuration.

The authenticated user must have the **SYS_ADMIN** permission to call this resource.

*Example response representations:*

-

  204 - application/json

  The mail configuration was successfully deleted.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to delete the mail server configuration.

#### GET

Retrieves the current mail configuration. The authenticated user must have the **SYS_ADMIN** permission to call this resource.

*Example response representations:*

-

  200 - application/json (mailHostConfiguration)

  ###### Example

      {"hostname":"smtp.example.com","port":465,"protocol":"SMTP","use-start-tls":true,"require-start-tls":false,"username":"user","sender-address":"stash-no-reply@company.com"}

  The mail configuration.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to retrieve the mail configuration.

-

  404 - application/json

  The mail server hasn't been configured

#### PUT

Updates the mail configuration The authenticated user must have the **SYS_ADMIN** permission to call this resource.

*Example request representations:*

-

  application/json

  ###### Example

      {"hostname":"smtp.example.com","port":465,"protocol":"SMTP","use-start-tls":true,"require-start-tls":false,"username":"user","sender-address":"stash-no-reply@company.com"}

*Example response representations:*

-

  200 - application/json (mailConfiguration)

  ###### Example

      {"hostname":"smtp.example.com","port":465,"protocol":"SMTP","use-start-tls":true,"require-start-tls":false,"username":"user","sender-address":"stash-no-reply@company.com"}

  The updated mail configuration.

-

  400 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":"field_a","message":"A detailed validation error message for field_a.","exceptionName":null},{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The mail configuration was not updated due to a validation error.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to update the mail configuration.

## /rest/api/1.0/admin/mail-server/sender-address

###### Methods

#### DELETE

Clears the server email address.

The authenticated user must have the **ADMIN** permission to call this resource.

*Example response representations:*

-

  204 - application/json

  The server email address was successfully cleared.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to clear the server email address.

#### GET

Retrieves the server email address

*Example response representations:*

-

  200 - application/json (server email address)

  ###### Example

      "stash-no-reply@company.com"

  The server email address

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to retrieve the server email address.

-

  404 - application/json

  The server email address is not set

#### PUT

Updates the server email address The authenticated user must have the **ADMIN** permission to call this resource.

*Example request representations:*

-

  application/json

  ###### Example

      "stash-no-reply@company.com"

*Example response representations:*

-

  200 - application/json (senderAddress)

  ###### Example

      "stash-no-reply@company.com"

  The updated server email address.

-

  400 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":"field_a","message":"A detailed validation error message for field_a.","exceptionName":null},{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The server email address was not updated due to a validation error.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to update the server email address.
