<!-- Bitbucket Server 5.10.0 REST API — resource group: projects--recreate (1 endpoints) -->

## /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/recreate

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **projectKey** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the parent project key |

###### Methods

#### POST

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

If a create or fork operation fails, calling this method will clean up the broken repository and try again. The repository must be in an INITIALISATION_FAILED state.

The authenticated user must have **PROJECT_ADMIN** permission for the specified project to call this resource.

*Example response representations:*

-

  201 - application/json (repository)

  ###### Example

      {"slug":"my-repo","id":1,"name":"My repo","scmId":"git","state":"AVAILABLE","statusMessage":"Available","forkable":true,"project":{"key":"PRJ","id":1,"name":"My Cool Project","description":"The description for my cool project.","public":true,"type":"NORMAL","links":{"self":[{"href":"http://link/to/project"}]}},"public":true,"links":{"clone":[{"href":"ssh://git@<baseURL>/PRJ/my-repo.git","name":"ssh"},{"href":"https://<baseURL>/scm/PRJ/my-repo.git","name":"http"}],"self":[{"href":"http://link/to/repository"}]}}

  The newly created repository.

-

  400 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The repository was not created due to a validation error.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to create a repository.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository does not exist.
