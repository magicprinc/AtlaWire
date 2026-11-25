<!-- bitbucket 5.10.0 - resource group: projects--settings -->

# `projects--settings`

8 method(s) as this deployment serves them. Source: its own `application.wadl`.

## GET /projects/{projectKey}/settings/hooks

Retrieve a page of repository hooks for this project. The authenticated user must have PROJECT_READ permission for the specified project to call this resource.

| query | type | default |
|---|---|---|
| `type` | string | `` |

## GET /projects/{projectKey}/settings/hooks/{hookKey}

Retrieve a repository hook for this project. The authenticated user must have PROJECT_READ permission for the specified project to call this resource.

No query parameters.

## DELETE /projects/{projectKey}/settings/hooks/{hookKey}/enabled

Disable a repository hook for this project. The authenticated user must have PROJECT_ADMIN permission for the specified project to call this resource.

No query parameters.

## PUT /projects/{projectKey}/settings/hooks/{hookKey}/enabled

Enable a repository hook for this project and optionally apply new configuration. The authenticated user must have PROJECT_ADMIN permission for the specified project to call this resource. A JSON document may be provided to use as the settings for the hook. These structure and validity of the document is decided by the plugin providing the hook.

No query parameters.

## GET /projects/{projectKey}/settings/hooks/{hookKey}/settings

Retrieve the settings for a repository hook for this project. The authenticated user must have PROJECT_READ permission for the specified project to call this resource.

No query parameters.

## PUT /projects/{projectKey}/settings/hooks/{hookKey}/settings

Modify the settings for a repository hook for this project. The service will reject any settings which are too large, the current limit is 32KB once serialized. The authenticated user must have PROJECT_ADMIN permission for the specified project to call this resource. A JSON document can be provided to use as the settings for the hook. These structure and validity of the document is decided by the plugin providing the hook.

No query parameters.

## GET /projects/{projectKey}/settings/pull-requests/{scmId}

Retrieve the merge strategy configuration for this project and SCM. The authenticated user must have PROJECT_READ permission for the context repository to call this resource.

No query parameters.

## POST /projects/{projectKey}/settings/pull-requests/{scmId}

Update the pull request merge strategy configuration for this project and SCM. The authenticated user must have PROJECT_ADMIN permission for the context repository to call this resource. Only the strategies provided will be enabled, the default must be set and included in the set of strategies. An explicitly set pull request merge strategy configuration can be deleted by POSTing a document with an empty "mergeConfig" attribute. i.e: { "mergeConfig": { } } Upon completion of this request, the effective configuration will be the configuration explicitly set for the SCM, or if no such explicit configuration is set then the default configuration will be used.

No query parameters.
