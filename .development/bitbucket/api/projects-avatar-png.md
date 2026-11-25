<!-- bitbucket 5.10.0 - resource group: projects--avatar-png -->

# `projects--avatar-png`

2 method(s) as this deployment serves them. Source: its own `application.wadl`.

## GET /projects/{projectKey}/avatar.png

Retrieve the avatar for the project matching the supplied projectKey . The authenticated user must have PROJECT_VIEW permission for the specified project to call this resource.

| query | type | default |
|---|---|---|
| `s` | int | `0` |

## POST /projects/{projectKey}/avatar.png

Update the avatar for the project matching the supplied projectKey . This resource accepts POST multipart form data, containing a single image in a form-field named 'avatar'. There are configurable server limits on both the dimensions (1024x1024 pixels by default) and uploaded file size (1MB by default). Several different image formats are supported, but PNG and JPEG are preferred due to the file size limit. This resource has Cross-Site Request Forgery (XSRF) protection. To allow the request to pass the XSRF check the caller needs to send an X-Atlassian-Token HTTP header with the value no-check . An example curl request to upload an image name 'avatar.png' would be: curl -X POST -u username:password -H "X-Atlassian-Token: no-check" http://example.com/rest/api/1.0/projects/STASH/avatar.png -F avatar=@avatar.png The authenticated user must have PROJECT_ADMIN permission for the specified project to call this resource.

No query parameters.
