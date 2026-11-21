<!-- Bitbucket Server 5.10.0 REST API — resource group: projects--settings (10 endpoints) -->

## /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/settings/pull-requests

###### Methods

#### POST

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Update the pull request settings for the context repository.

The authenticated user must have **REPO_ADMIN** permission for the context repository to call this resource.

This resource will call all RestFragments that are registered with the key **bitbucket.repository.settings.pullRequests**. If any fragment fails validations by returning a non-empty Map of errors, then no fragments will execute.

Only the settings that should be updated need to be included in the request.

The property keys for the settings that are bundled with the application are

- mergeConfig - the merge strategy configuration for pull requests
- requiredApprovers - (Deprecated, please use com.atlassian.bitbucket.server.bundled-hooks.requiredApproversMergeHook instead) the number of approvals required on a pull request for it to be mergeable, or 0 to disable the merge check
- com.atlassian.bitbucket.server.bundled-hooks.requiredApproversMergeHook - a json map containing the keys 'enabled' (a boolean to enable or disable this merge check) and 'count' (an integer to set the number of required approvals)
- requiredAllApprovers - whether or not all approvers must approve a pull request for it to be mergeable
- requiredAllTasksComplete - whether or not all tasks on a pull request need to be completed for it to be mergeable
- requiredSuccessfulBuilds - (Deprecated, please use com.atlassian.bitbucket.server.bitbucket-build.requiredBuildsMergeCheck instead) the number of successful builds on a pull request for it to be mergeable, or 0 to disable the merge check
- com.atlassian.bitbucket.server.bitbucket-build.requiredBuildsMergeCheck - a json map containing the keys 'enabled' (a boolean to enable or disable this merge check) and 'count' (an integer to set the number of required builds)

**Merge strategy configuration deletion:**

An explicitly set pull request merge strategy configuration can be deleted by POSTing a document with an empty "mergeConfig" attribute. i.e:

 {
     "mergeConfig": {
     }
 }
 

Upon completion of this request, the effective configuration will be:

- The configuration set for this repository's SCM type as set at the project level, if present, otherwise
- the configuration set for this repository's SCM type as set at the instance level, if present, otherwise
- the default configuration for this repository's SCM type

*Example request representations:*

-

  application/json

  ###### Example

      {"mergeConfig":{"defaultStrategy":{"id":"no-ff"},"strategies":[{"id":"no-ff"}]},"requiredAllApprovers":false,"requiredAllTasksComplete":false,"com.atlassian.bitbucket.server.bundled-hooks.requiredApproversMergeHook":{"enabled":true,"count":2},"requiredApprovers":2,"com.atlassian.bitbucket.server.bitbucket-build.requiredBuildsMergeCheck":{"enabled":true,"count":3},"requiredSuccessfulBuilds":2}

*Example response representations:*

-

  200 - application/json (settings)

  ###### Example

      {"mergeConfig":{"defaultStrategy":{"description":"Always create a merge commit","enabled":true,"flag":"--no-ff","id":"no-ff","name":"Merge commit"},"strategies":[{"description":"Always create a merge commit","enabled":true,"flag":"--no-ff","id":"no-ff","name":"Merge commit"}],"type":"repository"},"requiredAllApprovers":false,"requiredAllTasksComplete":false,"com.atlassian.bitbucket.server.bundled-hooks.requiredApproversMergeHook":{"enabled":true,"count":2},"requiredApprovers":2,"com.atlassian.bitbucket.server.bitbucket-build.requiredBuildsMergeCheck":{"enabled":true,"count":3},"requiredSuccessfulBuilds":2}

  The repository pull request settings for the context repository.

-

  400 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The repository pull request settings were not updated due to a validation error.

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

#### GET

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Retrieve the pull request settings for the context repository.

The authenticated user must have **REPO_READ** permission for the context repository to call this resource.

This resource will call all RestFragments that are registered with the key **bitbucket.repository.settings.pullRequests**. If any fragment fails validations by returning a non-empty Map of errors, then no fragments will execute.

The property keys for the settings that are bundled with the application are

- mergeConfig - the merge strategy configuration for pull requests
- requiredApprovers - (Deprecated, please use com.atlassian.bitbucket.server.bundled-hooks.requiredApproversMergeHook instead) the number of approvals required on a pull request for it to be mergeable, or 0 if the merge check is disabled
- com.atlassian.bitbucket.server.bundled-hooks.requiredApproversMergeHook - the merge check configuration for required approvers
- requiredAllApprovers - whether or not all approvers must approve a pull request for it to be mergeable
- requiredAllTasksComplete - whether or not all tasks on a pull request need to be completed for it to be mergeable
- requiredSuccessfulBuilds - (Deprecated, please use com.atlassian.bitbucket.server.bitbucket-build.requiredBuildsMergeCheck instead) the number of successful builds on a pull request for it to be mergeable, or 0 if the merge check is disabled
- com.atlassian.bitbucket.server.bitbucket-build.requiredBuildsMergeCheck - the merge check configuration for required builds

*Example response representations:*

-

  200 - application/json

  ###### Example

      {"mergeConfig":{"defaultStrategy":{"description":"Always create a merge commit","enabled":true,"flag":"--no-ff","id":"no-ff","name":"Merge commit"},"strategies":[{"description":"Always create a merge commit","enabled":true,"flag":"--no-ff","id":"no-ff","name":"Merge commit"}],"type":"repository"},"requiredAllApprovers":false,"requiredAllTasksComplete":false,"com.atlassian.bitbucket.server.bundled-hooks.requiredApproversMergeHook":{"enabled":true,"count":2},"requiredApprovers":2,"com.atlassian.bitbucket.server.bitbucket-build.requiredBuildsMergeCheck":{"enabled":true,"count":3},"requiredSuccessfulBuilds":2}

  The repository pull request settings for the context repository.

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

## /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/settings/hooks

###### Methods

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/settings/hooks?type

*This is a [paged API](#paging-params)*. *This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Retrieve a page of repository hooks for this repository.

The authenticated user must have **REPO_READ** permission for the specified repository to call this resource.

###### request query parameters

<table>
<colgroup>
<col style="width: 33%" />
<col style="width: 33%" />
<col style="width: 33%" />
</colgroup>
<thead>
<tr>
<th>parameter</th>
<th>value</th>
<th>description</th>
</tr>
</thead>
<tbody>
<tr>
<td>type</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a>
Default:</td>
<td>the optional type to filter by. Valid values are <code>PRE_RECEIVE</code> or <code>POST_RECEIVE</code></td>
</tr>
</tbody>
</table>

*Example response representations:*

-

  200 - application/json ([page](#paging-params))

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"details":{"key":"com.atlassian.stash.plugin.example:example-repository-hook","name":"Example repository hook","type":"PRE_RECEIVE","description":"An example description for an example hook.","version":"1.2.4","configFormKey":null,"scopeTypes":["PROJECT","REPOSITORY"]},"enabled":true,"configured":true,"scope":{"resourceId":2,"type":"REPOSITORY"}}],"start":0}

  returns a page of repository hooks with their associated enabled state.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to retrieve the hooks.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository does not exist.

## /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/settings/hooks/{hookKey}

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **hookKey** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* |  |

###### Methods

#### GET

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Retrieve a repository hook for this repository.

The authenticated user must have **REPO_READ** permission for the specified repository to call this resource.

*Example response representations:*

-

  200 - application/json

  ###### Example

      {"details":{"key":"com.atlassian.stash.plugin.example:example-repository-hook","name":"Example repository hook","type":"PRE_RECEIVE","description":"An example description for an example hook.","version":"1.2.4","configFormKey":null,"scopeTypes":["PROJECT","REPOSITORY"]},"enabled":true,"configured":true,"scope":{"resourceId":2,"type":"REPOSITORY"}}

  returns the repository hooks with their associated enabled state for the supplied hookKey.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to retrieve the hook.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository hook does not exist for the given repository, or the repository does not exist.

#### DELETE

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Delete repository hook configuration for the supplied **hookKey** and **repositorySlug**

The authenticated user must have **REPO_ADMIN** permission for the specified repository to call this resource.

*Example response representations:*

-

  204

  The hook configuration matching the supplied **hookKey** and **repositorySlug** was deleted

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to delete the hook.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository or hook does not exist.

## /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/settings/hooks/{hookKey}/enabled

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **hookKey** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* |  |

###### Methods

#### PUT

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Enable a repository hook for this repository and optionally apply new configuration.

The authenticated user must have **REPO_ADMIN** permission for the specified repository to call this resource.

A JSON document may be provided to use as the settings for the hook. These structure and validity of the document is decided by the plugin providing the hook.

###### request header parameters

<table>
<colgroup>
<col style="width: 33%" />
<col style="width: 33%" />
<col style="width: 33%" />
</colgroup>
<thead>
<tr>
<th>parameter</th>
<th>value</th>
<th>description</th>
</tr>
</thead>
<tbody>
<tr>
<td>Content-Length</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#int">int</a>
Default: <code>0</code></td>
<td></td>
</tr>
</tbody>
</table>

*Example response representations:*

-

  200 - application/json

  ###### Example

      {"details":{"key":"com.atlassian.stash.plugin.example:example-repository-hook","name":"Example repository hook","type":"PRE_RECEIVE","description":"An example description for an example hook.","version":"1.2.4","configFormKey":null,"scopeTypes":["PROJECT","REPOSITORY"]},"enabled":true,"configured":true,"scope":{"resourceId":2,"type":"REPOSITORY"}}

  returns the repository hooks with their associated enabled state for the supplied hookKey.

-

  400 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The settings specified are invalid.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to enable the hook.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository or hook does not exist.

#### DELETE

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Disable a repository hook for this repository.

The authenticated user must have **REPO_ADMIN** permission for the specified repository to call this resource.

*Example response representations:*

-

  200 - application/json

  ###### Example

      {"details":{"key":"com.atlassian.stash.plugin.example:example-repository-hook","name":"Example repository hook","type":"PRE_RECEIVE","description":"An example description for an example hook.","version":"1.2.4","configFormKey":null,"scopeTypes":["PROJECT","REPOSITORY"]},"enabled":true,"configured":true,"scope":{"resourceId":2,"type":"REPOSITORY"}}

  returns the repository hooks with their associated enabled state for the supplied hookKey.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to disable the hook.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository or hook does not exist.

## /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/settings/hooks/{hookKey}/settings

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **hookKey** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* |  |

###### Methods

#### GET

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Retrieve the settings for a repository hook for this repository.

The authenticated user must have **REPO_READ** permission for the specified repository to call this resource.

*Example response representations:*

-

  200 - application/json

  ###### Example

      {"string-value":"this is an arbitrary string","integer-value":1,"long-value":2147483648,"boolean-value":true,"double-value":1.1}

  The settings for the hook.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to retrieve the hook settings.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository or hook does not exist.

#### PUT

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Modify the settings for a repository hook for this repository.

The service will reject any settings which are too large, the current limit is 32KB once serialized.

The authenticated user must have **REPO_ADMIN** permission for the specified repository to call this resource.

A JSON document can be provided to use as the settings for the hook. These structure and validity of the document is decided by the plugin providing the hook.

*Example request representations:*

-

  application/json

  ###### Example

      {"string-value":"this is an arbitrary string","integer-value":1,"long-value":2147483648,"boolean-value":true,"double-value":1.1}

*Example response representations:*

-

  200 - application/json

  ###### Example

      {"string-value":"this is an arbitrary string","integer-value":1,"long-value":2147483648,"boolean-value":true,"double-value":1.1}

  The settings for the hook.

-

  400 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The settings specified are invalid.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to modify the hook settings.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository or hook does not exist.

## /rest/api/1.0/projects/{projectKey}/settings/pull-requests/{scmId}

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **scmId** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the SCM to get strategies for |

###### Methods

#### POST

Update the pull request merge strategy configuration for this project and SCM.

The authenticated user must have **PROJECT_ADMIN** permission for the context repository to call this resource.

Only the strategies provided will be enabled, the default must be set and included in the set of strategies.

An explicitly set pull request merge strategy configuration can be deleted by POSTing a document with an empty "mergeConfig" attribute. i.e:

 {
     "mergeConfig": {
     }
 }
 

Upon completion of this request, the effective configuration will be the configuration explicitly set for the SCM, or if no such explicit configuration is set then the default configuration will be used.

*Example request representations:*

-

  application/json

  ###### Example

      {"mergeConfig":{"defaultStrategy":{"id":"no-ff"},"strategies":[{"id":"no-ff"}]}}

*Example response representations:*

-

  200 - application/json (strategies)

  ###### Example

      {"mergeConfig":{"defaultStrategy":{"description":"Always create a merge commit","enabled":true,"flag":"--no-ff","id":"no-ff","name":"Merge commit"},"strategies":[{"description":"Always create a merge commit","enabled":true,"flag":"--no-ff","id":"no-ff","name":"Merge commit"}],"type":"repository"}}

  The repository pull request merge strategies for the context repository.

-

  400 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The repository pull request merge strategies were not updated due to a validation error.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to administrate the specified repository.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository does not exist.

#### GET

*This is a [paged API](#paging-params)*.

Retrieve the merge strategy configuration for this project and SCM.

The authenticated user must have **PROJECT_READ** permission for the context repository to call this resource.

*Example response representations:*

-

  200 - application/json ([page](#paging-params))

  ###### Example

      {"mergeConfig":{"defaultStrategy":{"description":"Always create a merge commit","enabled":true,"flag":"--no-ff","id":"no-ff","name":"Merge commit"},"strategies":[{"description":"Always create a merge commit","enabled":true,"flag":"--no-ff","id":"no-ff","name":"Merge commit"}],"type":"repository"}}

  The merge configuration of the request project.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to see the request repository.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The request repository does not exist.

## /rest/api/1.0/projects/{projectKey}/settings/hooks

###### Methods

#### GET

###### /rest/api/1.0/projects/{projectKey}/settings/hooks?type

*This is a [paged API](#paging-params)*.

Retrieve a page of repository hooks for this project.

The authenticated user must have **PROJECT_READ** permission for the specified project to call this resource.

###### request query parameters

<table>
<colgroup>
<col style="width: 33%" />
<col style="width: 33%" />
<col style="width: 33%" />
</colgroup>
<thead>
<tr>
<th>parameter</th>
<th>value</th>
<th>description</th>
</tr>
</thead>
<tbody>
<tr>
<td>type</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a>
Default:</td>
<td>the optional type to filter by. Valid values are <code>PRE_RECEIVE</code> or <code>POST_RECEIVE</code></td>
</tr>
</tbody>
</table>

*Example response representations:*

-

  200 - application/json ([page](#paging-params))

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"details":{"key":"com.atlassian.stash.plugin.example:example-repository-hook","name":"Example repository hook","type":"PRE_RECEIVE","description":"An example description for an example hook.","version":"1.2.4","configFormKey":null,"scopeTypes":["PROJECT","REPOSITORY"]},"enabled":true,"configured":true,"scope":{"resourceId":2,"type":"REPOSITORY"}}],"start":0}

  returns a page of repository hooks with their associated enabled state.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to retrieve the hooks.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified project does not exist.

## /rest/api/1.0/projects/{projectKey}/settings/hooks/{hookKey}

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **hookKey** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* |  |

###### Methods

#### GET

Retrieve a repository hook for this project.

The authenticated user must have **PROJECT_READ** permission for the specified project to call this resource.

*Example response representations:*

-

  200 - application/json

  ###### Example

      {"details":{"key":"com.atlassian.stash.plugin.example:example-repository-hook","name":"Example repository hook","type":"PRE_RECEIVE","description":"An example description for an example hook.","version":"1.2.4","configFormKey":null,"scopeTypes":["PROJECT","REPOSITORY"]},"enabled":true,"configured":true,"scope":{"resourceId":2,"type":"REPOSITORY"}}

  returns the repository hooks with their associated enabled state for the supplied hookKey.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to retrieve the hook.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository hook does not exist for the given project, or the project does not exist.

## /rest/api/1.0/projects/{projectKey}/settings/hooks/{hookKey}/enabled

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **hookKey** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* |  |

###### Methods

#### PUT

Enable a repository hook for this project and optionally apply new configuration.

The authenticated user must have **PROJECT_ADMIN** permission for the specified project to call this resource.

A JSON document may be provided to use as the settings for the hook. These structure and validity of the document is decided by the plugin providing the hook.

###### request header parameters

<table>
<colgroup>
<col style="width: 33%" />
<col style="width: 33%" />
<col style="width: 33%" />
</colgroup>
<thead>
<tr>
<th>parameter</th>
<th>value</th>
<th>description</th>
</tr>
</thead>
<tbody>
<tr>
<td>Content-Length</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#int">int</a>
Default: <code>0</code></td>
<td></td>
</tr>
</tbody>
</table>

*Example response representations:*

-

  200 - application/json

  ###### Example

      {"details":{"key":"com.atlassian.stash.plugin.example:example-repository-hook","name":"Example repository hook","type":"PRE_RECEIVE","description":"An example description for an example hook.","version":"1.2.4","configFormKey":null,"scopeTypes":["PROJECT","REPOSITORY"]},"enabled":true,"configured":true,"scope":{"resourceId":2,"type":"REPOSITORY"}}

  returns the repository hooks with their associated enabled state for the supplied hookKey.

-

  400 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The settings specified are invalid.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to enable the hook.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified project or hook does not exist.

#### DELETE

Disable a repository hook for this project.

The authenticated user must have **PROJECT_ADMIN** permission for the specified project to call this resource.

*Example response representations:*

-

  200 - application/json

  ###### Example

      {"details":{"key":"com.atlassian.stash.plugin.example:example-repository-hook","name":"Example repository hook","type":"PRE_RECEIVE","description":"An example description for an example hook.","version":"1.2.4","configFormKey":null,"scopeTypes":["PROJECT","REPOSITORY"]},"enabled":true,"configured":true,"scope":{"resourceId":2,"type":"REPOSITORY"}}

  returns the repository hooks with their associated enabled state for the supplied hookKey.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to disable the hook.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified project or hook does not exist.

## /rest/api/1.0/projects/{projectKey}/settings/hooks/{hookKey}/settings

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **hookKey** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* |  |

###### Methods

#### GET

Retrieve the settings for a repository hook for this project.

The authenticated user must have **PROJECT_READ** permission for the specified project to call this resource.

*Example response representations:*

-

  200 - application/json

  ###### Example

      {"string-value":"this is an arbitrary string","integer-value":1,"long-value":2147483648,"boolean-value":true,"double-value":1.1}

  The settings for the hook.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to retrieve the hook settings.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified project or hook does not exist.

#### PUT

Modify the settings for a repository hook for this project.

The service will reject any settings which are too large, the current limit is 32KB once serialized.

The authenticated user must have **PROJECT_ADMIN** permission for the specified project to call this resource.

A JSON document can be provided to use as the settings for the hook. These structure and validity of the document is decided by the plugin providing the hook.

*Example request representations:*

-

  application/json

  ###### Example

      {"string-value":"this is an arbitrary string","integer-value":1,"long-value":2147483648,"boolean-value":true,"double-value":1.1}

*Example response representations:*

-

  200 - application/json

  ###### Example

      {"string-value":"this is an arbitrary string","integer-value":1,"long-value":2147483648,"boolean-value":true,"double-value":1.1}

  The settings for the hook.

-

  400 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The settings specified are invalid.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to modify the hook settings.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified project or hook does not exist.
