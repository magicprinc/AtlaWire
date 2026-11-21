<!-- Bitbucket Server 5.10.0 REST API — resource group: tasks (2 endpoints) -->

## /rest/api/1.0/tasks

###### Methods

#### POST

Create a new task.

*Example request representations:*

-

  application/json

  ###### Example

      {"anchor":{"id":1,"type":"COMMENT"},"text":"Fix the missing imports"}

*Example response representations:*

-

  201 - application/json (task)

  ###### Example

      {"anchor":{"properties":{"key":"value"},"id":1,"version":1,"text":"An insightful comment.","author":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"createdDate":1527228363411,"updatedDate":1527228363411,"comments":[],"tasks":[],"permittedOperations":{"editable":true,"deletable":true}},"author":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"createdDate":1527228364841,"id":99,"permittedOperations":{"deletable":true,"editable":true,"transitionable":true},"text":"Fix the missing imports"}

  A copy of the created task.

-

  400 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  If the task data is invalid (for example, if the task's text is missing or blank)

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  If the anchor of the task (such as a pull request comment) does not exist or is not visible to the current user

## /rest/api/1.0/tasks/{taskId}

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **taskId** | *[long](http://www.w3.org/TR/xmlschema-2/#long)* | the id identifying the task to delete |

###### Methods

#### GET

Retrieve a existing task.

*Example response representations:*

-

  200 - application/json (task)

  ###### Example

      {"properties":{"diffAnchorPath":"path/to/file.txt"},"anchor":{"properties":{"key":"value"},"id":1,"version":1,"text":"An insightful comment.","author":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"createdDate":1527228363411,"updatedDate":1527228363411,"comments":[],"tasks":[],"permittedOperations":{"editable":true,"deletable":true}},"author":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"createdDate":1527228364842,"id":99,"permittedOperations":{"deletable":false,"editable":false,"transitionable":true},"text":"Resolve the merge conflicts","state":"OPEN"}

  A copy of the task.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  If the task does not exist

#### DELETE

Delete a task.

Note that only the task's creator, the context's author or an admin of the context's repository can delete a task. (For a pull request task, those are the task's creator, the pull request's author or an admin on the repository containing the pull request). Additionally a task cannot be deleted if it has already been resolved.

*Example response representations:*

-

  204 (task)

  if the task was successfully deleted.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  If the current user does not have the permission to delete the task

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  If the task does not exist

-

  409 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  If the task to delete is in the resolved state

#### PUT

Update a existing task.

As of Stash 3.3, only the state and text of a task can be updated.

Updating the state of a task is allowed for any user having *READ* access to the repository. However only the task's creator, the context's author or an admin of the context's repository can update the task's text. (For a pull request task, those are the task's creator, the pull request's author or an admin on the repository containing the pull request). Additionally the task's text cannot be updated if it has been resolved.

*Example request representations:*

-

  application/json

  ###### Example

      {"id":99,"text":"Fix the missing and obsolete imports"}

*Example response representations:*

-

  200 - application/json (task)

  ###### Example

      {"properties":{"diffAnchorPath":"path/to/file.txt"},"anchor":{"properties":{"key":"value"},"id":1,"version":1,"text":"An insightful comment.","author":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"createdDate":1527228363411,"updatedDate":1527228363411,"comments":[],"tasks":[],"permittedOperations":{"editable":true,"deletable":true}},"author":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"createdDate":1527228364841,"id":99,"permittedOperations":{"deletable":true,"editable":true,"transitionable":true},"text":"Fix the missing and deprecated imports","state":"OPEN"}

  A copy of the task if it was successfully updated.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  If the current user does not have the permission to update the task

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  If the task does not exist

-

  409 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  If the task to update is in the resolved state
