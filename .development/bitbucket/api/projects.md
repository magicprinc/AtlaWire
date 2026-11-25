<!-- bitbucket 5.10.0 - resource group: projects -->

# `projects`

5 method(s) as this deployment serves them. Source: its own `application.wadl`.

## GET /projects

Retrieve a page of projects. Only projects for which the authenticated user has the PROJECT_VIEW permission will be returned.

| query | type | default |
|---|---|---|
| `name` | string |  |
| `permission` | string |  |

## POST /projects

Create a new project. To include a custom avatar for the project, the project definition should contain an additional attribute with the key avatar and the value a data URI containing Base64-encoded image data. The URI should be in the following format: data:(content type, e.g. image/png);base64,(data) If the data is not Base64-encoded, or if a character set is defined in the URI, or the URI is otherwise invalid, project creation will fail . The authenticated user must have PROJECT_CREATE permission to call this resource.

No query parameters.

## DELETE /projects/{projectKey}

Delete the project matching the supplied projectKey . The authenticated user must have PROJECT_ADMIN permission for the specified project to call this resource.

No query parameters.

## GET /projects/{projectKey}

Retrieve the project matching the supplied projectKey . The authenticated user must have PROJECT_VIEW permission for the specified project to call this resource.

No query parameters.

## PUT /projects/{projectKey}

Update the project matching the projectKey supplied in the resource path. To include a custom avatar for the updated project, the project definition should contain an additional attribute with the key avatar and the value a data URI containing Base64-encoded image data. The URI should be in the following format: data:(content type, e.g. image/png);base64,(data) If the data is not Base64-encoded, or if a character set is defined in the URI, or the URI is otherwise invalid, project creation will fail . The authenticated user must have PROJECT_ADMIN permission for the specified project to call this resource.

No query parameters.
