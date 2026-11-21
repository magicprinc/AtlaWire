<!-- Bitbucket Server 5.10.0 REST API — resource group: projects--watch (1 endpoints) -->

## /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/watch

###### Methods

#### POST

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Add the authenticated user as a watcher for the specified repository.

The authenticated user must have **REPO_READ** permission for the repository to call this resource.

*Example response representations:*

-

  204

  The user is now watching the repository.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the repository.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository does not exist.

#### DELETE

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Remove the authenticated user as a watcher for the specified repository.

The authenticated user must have **REPO_READ** permission for the repository to call this resource.

*Example response representations:*

-

  204

  The user is no longer watching the repository.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the repository.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository does not exist.
