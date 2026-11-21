<!-- Bitbucket Server 5.10.0 REST API — resource group: hooks (1 endpoints) -->

## /rest/api/1.0/hooks/{hookKey}/avatar

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **hookKey** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the complete module key of the hook module |

###### Methods

#### GET

###### /rest/api/1.0/hooks/{hookKey}/avatar?version

Retrieve the avatar for the project matching the supplied **moduleKey**.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **version** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | optional version used for HTTP caching only - any non-blank version will result in a large max-age Cache-Control header. Note that this does not affect the Last-Modified header. |

*Example response representations:*

-

  200 - image/png

  The avatar of the project matching the supplied **projectKey**.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the project.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified project does not exist.
