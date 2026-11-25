<!-- bitbucket 5.10.0 - resource group: tasks -->

# `tasks`

4 method(s) as this deployment serves them. Source: its own `application.wadl`.

## POST /tasks

Create a new task.

No query parameters.

## DELETE /tasks/{taskId}

Delete a task. Note that only the task's creator, the context's author or an admin of the context's repository can delete a task. (For a pull request task, those are the task's creator, the pull request's author or an admin on the repository containing the pull request). Additionally a task cannot be deleted if it has already been resolved.

No query parameters.

## GET /tasks/{taskId}

Retrieve a existing task.

No query parameters.

## PUT /tasks/{taskId}

Update a existing task. As of Stash 3.3, only the state and text of a task can be updated. Updating the state of a task is allowed for any user having READ access to the repository. However only the task's creator, the context's author or an admin of the context's repository can update the task's text. (For a pull request task, those are the task's creator, the pull request's author or an admin on the repository containing the pull request). Additionally the task's text cannot be updated if it has been resolved.

No query parameters.
