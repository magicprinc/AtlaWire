<!-- Bitbucket Server 5.10.0 REST API — resource group: projects--projects (2 endpoints) -->

## /rest/api/1.0/projects

###### Methods

#### GET

###### /rest/api/1.0/projects?name&permission

*This is a [paged API](#paging-params)*.

Retrieve a page of projects.

Only projects for which the authenticated user has the **PROJECT_VIEW** permission will be returned.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **name** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* |  |
| **permission** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* |  |

*Example response representations:*

-

  200 - application/json ([page](#paging-params))

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"key":"PRJ","id":1,"name":"My Cool Project","description":"The description for my cool project.","public":true,"type":"NORMAL","links":{"self":[{"href":"http://link/to/project"}]}}],"start":0}

  A page of projects.

-

  400 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The permission level is unknown or not related to projects.

#### POST

Create a new project.

To include a custom avatar for the project, the project definition should contain an additional attribute with the key `avatar` and the value a data URI containing Base64-encoded image data. The URI should be in the following format:

     data:(content type, e.g. image/png);base64,(data)
 

If the data is not Base64-encoded, or if a character set is defined in the URI, or the URI is otherwise invalid, *project creation will fail*.

The authenticated user must have **PROJECT_CREATE** permission to call this resource.

*Example request representations:*

-

  application/json

  ###### Example

      {"key":"PRJ","name":"My Cool Project","description":"The description for my cool project.","avatar":"data:image/png;base64,<base64-encoded-image-data>"}

*Example response representations:*

-

  201 - application/json (project)

  ###### Example

      {"key":"PRJ","id":1,"name":"My Cool Project","description":"The description for my cool project.","public":true,"type":"NORMAL","links":{"self":[{"href":"http://link/to/project"}]}}

  The newly created project.

-

  400 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":"field_a","message":"A detailed validation error message for field_a.","exceptionName":null},{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The project was not created due to a validation error.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to create a project.

-

  409 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The project key or name is already in use.

## /rest/api/1.0/projects/{projectKey}

###### Methods

#### GET

Retrieve the project matching the supplied **projectKey**.

The authenticated user must have **PROJECT_VIEW** permission for the specified project to call this resource.

*Example response representations:*

-

  200 - application/json (project)

  ###### Example

      {"key":"PRJ","id":1,"name":"My Cool Project","description":"The description for my cool project.","public":true,"type":"NORMAL","links":{"self":[{"href":"http://link/to/project"}]}}

  The project matching the supplied **projectKey**.

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

#### DELETE

Delete the project matching the supplied **projectKey**.

The authenticated user must have **PROJECT_ADMIN** permission for the specified project to call this resource.

*Example response representations:*

-

  204

  The project matching the supplied **projectKey** was deleted.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to delete the project.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified project does not exist.

-

  409 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The project can not be deleted as it contains repositories.

#### PUT

Update the project matching the **projectKey** supplied in the resource path.

To include a custom avatar for the updated project, the project definition should contain an additional attribute with the key `avatar` and the value a data URI containing Base64-encoded image data. The URI should be in the following format: ` data:(content type, e.g. image/png);base64,(data) ` If the data is not Base64-encoded, or if a character set is defined in the URI, or the URI is otherwise invalid, *project creation will fail*.

The authenticated user must have **PROJECT_ADMIN** permission for the specified project to call this resource.

*Example request representations:*

-

  application/json

  ###### Example

      {"key":"PRJ","name":"My Cool Project","description":"The description for my cool project.","avatar":"data:image/png;base64,<base64-encoded-image-data>"}

*Example response representations:*

-

  200 - application/json (project)

  ###### Example

      {"key":"PRJ","id":1,"name":"My Cool Project","description":"The description for my cool project.","public":true,"type":"NORMAL","links":{"self":[{"href":"http://link/to/project"}]}}

  The updated project. The project's key **was not** updated.

-

  201 - application/json (project)

  ###### Example

      {"key":"PRJ","id":1,"name":"My Cool Project","description":"The description for my cool project.","public":true,"type":"NORMAL","links":{"self":[{"href":"http://link/to/project"}]}}

  The updated project. The project's key **was** updated.

-

  400 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":"field_a","message":"A detailed validation error message for field_a.","exceptionName":null},{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The project was not updated due to a validation error.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to update the project.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified project does not exist.
