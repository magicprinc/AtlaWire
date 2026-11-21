<!-- Bitbucket Server 5.10.0 REST API — resource group: projects--repos (2 endpoints) -->

## /rest/api/1.0/projects/{projectKey}/repos

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **projectKey** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the parent project key |

###### Methods

#### POST

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Create a new repository. Requires an existing project in which this repository will be created. The only parameters which will be used are name and scmId.

The authenticated user must have **PROJECT_ADMIN** permission for the context project to call this resource.

*Example request representations:*

-

  application/json

  ###### Example

      {"name":"My repo","scmId":"git","forkable":true}

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

  409 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  A repository with same name already exists.

#### GET

*This is a [paged API](#paging-params)*. *This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Retrieve repositories from the project corresponding to the supplied **projectKey**.

The authenticated user must have **REPO_READ** permission for the specified project to call this resource.

*Example response representations:*

-

  200 - application/json ([page](#paging-params))

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"slug":"my-repo","id":1,"name":"My repo","scmId":"git","state":"AVAILABLE","statusMessage":"Available","forkable":true,"project":{"key":"PRJ","id":1,"name":"My Cool Project","description":"The description for my cool project.","public":true,"type":"NORMAL","links":{"self":[{"href":"http://link/to/project"}]}},"public":true,"links":{"clone":[{"href":"ssh://git@<baseURL>/PRJ/my-repo.git","name":"ssh"},{"href":"https://<baseURL>/scm/PRJ/my-repo.git","name":"http"}],"self":[{"href":"http://link/to/repository"}]}}],"start":0}

  The repositories matching the supplied **projectKey**.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to see the specified project.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified project does not exist.

## /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **projectKey** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the parent project key |
| **projectKey** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the parent project key |
| **repositorySlug** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the repository slug |

###### Methods

#### GET

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Retrieve the repository matching the supplied **projectKey** and **repositorySlug**.

The authenticated user must have **REPO_READ** permission for the specified repository to call this resource.

*Example response representations:*

-

  200 - application/json (repository)

  ###### Example

      {"slug":"my-repo","id":1,"name":"My repo","scmId":"git","state":"AVAILABLE","statusMessage":"Available","forkable":true,"project":{"key":"PRJ","id":1,"name":"My Cool Project","description":"The description for my cool project.","public":true,"type":"NORMAL","links":{"self":[{"href":"http://link/to/project"}]}},"public":true,"links":{"clone":[{"href":"ssh://git@<baseURL>/PRJ/my-repo.git","name":"ssh"},{"href":"https://<baseURL>/scm/PRJ/my-repo.git","name":"http"}],"self":[{"href":"http://link/to/repository"}]}}

  The repository which matches the supplied **projectKey** and **repositorySlug**.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to see the specified repository.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository does not exist.

#### PUT

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Update the repository matching the **repositorySlug** supplied in the resource path.

The repository's slug is derived from its name. If the name changes the slug may also change.

This API can be used to move the repository to a different project by setting the new project in the request, example: {@code {"project":{"key":"NEW_KEY"}}} .

The authenticated user must have **REPO_ADMIN** permission for the specified repository to call this resource.

*Example request representations:*

-

  application/json

  ###### Example

      {"name":"My repo","forkable":false,"project":{"key":"PRJ"},"public":true}

*Example response representations:*

-

  201 - application/json (repository)

  ###### Example

      {"slug":"my-repo","id":1,"name":"My repo","scmId":"git","state":"AVAILABLE","statusMessage":"Available","forkable":true,"project":{"key":"PRJ","id":1,"name":"My Cool Project","description":"The description for my cool project.","public":true,"type":"NORMAL","links":{"self":[{"href":"http://link/to/project"}]}},"public":true,"links":{"clone":[{"href":"ssh://git@<baseURL>/PRJ/my-repo.git","name":"ssh"},{"href":"https://<baseURL>/scm/PRJ/my-repo.git","name":"http"}],"self":[{"href":"http://link/to/repository"}]}}

  The updated repository.

-

  400 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The repository was not updated due to a validation error.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to update a repository

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository does not exist.

-

  409 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  A repository with same name as the target already exists

#### DELETE

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Schedule the repository matching the supplied **projectKey** and **repositorySlug** to be deleted. If the request repository is not present

The authenticated user must have **REPO_ADMIN** permission for the specified repository to call this resource.

*Example response representations:*

-

  202 - application/json (message)

  ###### Example

      {"context":null,"message":"Repository scheduled for deletion.","exceptionName":null}

  The repository has been scheduled for deletion.

-

  204

  No repository matching the supplied **projectKey** and **repositorySlug** was found.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to delete the repository.

#### POST

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Create a new repository forked from an existing repository.

The JSON body for this {@code POST} is not required to contain *any* properties. Even the name may be omitted. The following properties will be used, if provided:

- {@code "name":"Fork name"} - Specifies the forked repository's name
  - Defaults to the name of the origin repository if not specified
- {@code "project":{"key":"TARGET_KEY"}} - Specifies the forked repository's target project by key
  - Defaults to the current user's personal project if not specified

The authenticated user must have **REPO_READ** permission for the specified repository and **PROJECT_ADMIN** on the target project to call this resource. Note that users *always* have **PROJECT_ADMIN** permission on their personal projects.

*Example request representations:*

-

  application/json

  ###### Example

      {"slug":"my-repo","name":null,"project":{"key":"PRJ"}}

*Example response representations:*

-

  201 - application/json (repository)

  ###### Example

      {"slug":"my-repo","id":2,"name":"My repo","scmId":"git","state":"AVAILABLE","statusMessage":"Available","forkable":true,"origin":{"slug":"my-repo","id":1,"name":"My repo","scmId":"git","state":"AVAILABLE","statusMessage":"Available","forkable":true,"project":{"key":"PRJ","id":1,"name":"My Cool Project","description":"The description for my cool project.","public":true,"type":"NORMAL","links":{"self":[{"href":"http://link/to/project"}]}},"public":true,"links":{"clone":[{"href":"ssh://git@<baseURL>/PRJ/my-repo.git","name":"ssh"},{"href":"https://<baseURL>/scm/PRJ/my-repo.git","name":"http"}],"self":[{"href":"http://link/to/repository"}]}},"project":{"key":"~JDOE","id":2,"name":"John Doe","type":"PERSONAL","links":{"self":[{"href":"http://link/to/project"}]}},"links":{"clone":[{"href":"https://<baseURL>/scm/JDOE/my-repo.git","name":"http"},{"href":"ssh://git@<baseURL>/JDOE/my-repo.git","name":"ssh"}],"self":[{"href":"http://link/to/repository"}]}}

  The newly created fork.

-

  400 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  A validation error prevented the fork from being created. Possible validation errors include: The name or slug for the fork collides with another repository in the target project; an SCM type was specified in the JSON body; a project was specified in the JSON body without a "key" property.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to create a fork.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository does not exist, or, if a target project was specified, the target project does not exist.
