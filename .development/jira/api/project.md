<!-- jira 8.22.2 - resource group: project -->

# `project`

39 method(s) as this deployment serves them. Source: its own `application.wadl`.

## GET /project

Returns all projects which are visible for the currently logged in user. If no user is logged in, it returns the list of projects that are visible when using anonymous access.

| query | type | default |
|---|---|---|
| `expand` | string |  |
| `recent` | int |  |
| `includeArchived` | boolean |  |
| `browseArchive` | boolean |  |

## POST /project

Creates a new project.

No query parameters.

## GET /project/type

Returns all the project types defined on the Jira instance, not taking into account whether the license to use those project types is valid or not.

No query parameters.

## GET /project/type/{projectTypeKey}

Returns the project type with the given key.

No query parameters.

## GET /project/type/{projectTypeKey}/accessible

Returns the project type with the given key, if it is accessible to the logged in user. This takes into account whether the user is licensed on the Application that defines the project type.

No query parameters.

## DELETE /project/{projectIdOrKey}

Deletes a project.

No query parameters.

## GET /project/{projectIdOrKey}

Contains a full representation of a project in JSON format. All project keys associated with the project will only be returned if expand=projectKeys .

| query | type | default |
|---|---|---|
| `expand` | string |  |

## PUT /project/{projectIdOrKey}

Updates a project. Only non null values sent in JSON will be updated in the project. Values available for the assigneeType field are: "PROJECT_LEAD" and "UNASSIGNED".

| query | type | default |
|---|---|---|
| `expand` | string |  |

## PUT /project/{projectIdOrKey}/archive

Archives a project.

No query parameters.

## POST /project/{projectIdOrKey}/avatar

Converts the temporary avatar into the final one. This is step 2/3 of changing an avatar for a project: Upload (store temporary avatar) Crop (create avatar from temporary) Update (update project avatar)

No query parameters.

## PUT /project/{projectIdOrKey}/avatar

Updates an avatar for a project. This is step 3/3 of changing an avatar for a project: Upload (store temporary avatar) Crop (create avatar from temporary) Update (update project avatar)

No query parameters.

## POST /project/{projectIdOrKey}/avatar/temporary

Creates temporary avatar using multipart. The response is sent back as JSON stored in a textarea. This is because the client uses remote iframing to submit avatars using multipart. So we must send them a valid HTML page back from which the client parses the JSON.

No query parameters.

## POST /project/{projectIdOrKey}/avatar/temporary

Uploads an image and creates a temporary avatar. This is step 1/3 of changing an avatar for a project: Upload (store temporary avatar) Crop (create avatar from temporary) Update (update project avatar) Supported image formats: BMP GIF JPEG PNG WBMP curl \ -X POST \ -u admin:admin \ -H "X-Atlassian-Token: no-check" \ -H "Content-Type: image/png" \ --data-binary @mynewavatar.png \ 'http://localhost:8090/jira/rest/api/2/user/avatar/temporary?username=admin&amp;filename=mynewavatar.png'

| query | type | default |
|---|---|---|
| `filename` | string |  |
| `size` | long |  |

## DELETE /project/{projectIdOrKey}/avatar/{id}

Deletes avatar

No query parameters.

## GET /project/{projectIdOrKey}/avatars

Returns all avatars which are visible for the currently logged in user. The avatars are grouped into system and custom.

No query parameters.

## GET /project/{projectIdOrKey}/components

Contains a full representation of a the specified project's components.

No query parameters.

## GET /project/{projectIdOrKey}/properties

Returns the keys of all properties for the project identified by the key or by the id.

No query parameters.

## DELETE /project/{projectIdOrKey}/properties/{propertyKey}

Removes the property from the project identified by the key or by the id. Ths user removing the property is required to have permissions to administer the project.

No query parameters.

## GET /project/{projectIdOrKey}/properties/{propertyKey}

Returns the value of the property with a given key from the project identified by the key or by the id. The user who retrieves the property is required to have permissions to read the project.

No query parameters.

## PUT /project/{projectIdOrKey}/properties/{propertyKey}

Sets the value of the specified project's property. You can use this resource to store a custom data against the project identified by the key or by the id. The user who stores the data is required to have permissions to administer the project.

No query parameters.

## PUT /project/{projectIdOrKey}/restore

Restore an archived project. In case of success restored project should be re-indexed.

No query parameters.

## GET /project/{projectIdOrKey}/role

Returns all roles in the given project Id or key, with links to full details on each role.

No query parameters.

## DELETE /project/{projectIdOrKey}/role/{id}

Deletes actors (users or groups) from a project role. Delete a user from the role: /rest/api/2/project/{projectIdOrKey}/role/{roleId}?user={username} Delete a group from the role: /rest/api/2/project/{projectIdOrKey}/role/{roleId}?group={groupname}

| query | type | default |
|---|---|---|
| `user` | string |  |
| `group` | string |  |

## GET /project/{projectIdOrKey}/role/{id}

Returns the details for a given project role in a project.

No query parameters.

## POST /project/{projectIdOrKey}/role/{id}

Adds an actor (user or group) to a project role. For user actors, their usernames should be used.

No query parameters.

## PUT /project/{projectIdOrKey}/role/{id}

Updates a project role to include the specified actors (users or groups). Can be also used to clear roles to not include any users or groups. For user actors, their usernames should be used.

No query parameters.

## GET /project/{projectIdOrKey}/statuses

Get all issue types with valid status values for a project

No query parameters.

## PUT /project/{projectIdOrKey}/type/{newProjectTypeKey}

Updates the type of a project.

No query parameters.

## GET /project/{projectIdOrKey}/version

Returns all versions for the specified project. Results are paginated . Results can be ordered by the following fields: sequence name startDate releaseDate

| query | type | default |
|---|---|---|
| `startAt` | long |  |
| `maxResults` | int |  |
| `orderBy` | string |  |
| `expand` | string |  |

## GET /project/{projectIdOrKey}/versions

Contains a full representation of a the specified project's versions.

| query | type | default |
|---|---|---|
| `expand` | string |  |

## GET /project/{projectKeyOrId}/issuesecuritylevelscheme

Returns the issue security scheme for project.

No query parameters.

## GET /project/{projectKeyOrId}/notificationscheme

Gets a notification scheme associated with the project. Follow the documentation of /notificationscheme/{id} resource for all details about returned value.

| query | type | default |
|---|---|---|
| `expand` | string |  |

## GET /project/{projectKeyOrId}/permissionscheme

Gets a permission scheme assigned with a project.

| query | type | default |
|---|---|---|
| `expand` | string |  |

## PUT /project/{projectKeyOrId}/permissionscheme

Assigns a permission scheme with a project.

| query | type | default |
|---|---|---|
| `expand` | string |  |

## GET /project/{projectKeyOrId}/priorityscheme

Gets a full representation of a priority scheme in JSON format used by specified project. User must be global administrator or project administrator. All project keys associated with the priority scheme will only be returned if additional query parameter is provided expand=projectKeys .

No query parameters.

## PUT /project/{projectKeyOrId}/priorityscheme

Assigns project with priority scheme. Priority scheme assign with migration is possible from the UI. Operation will fail if migration is needed as a result of operation eg. there are issues with priorities invalid in the destination scheme. All project keys associated with the priority scheme will only be returned if additional query parameter is provided expand=projectKeys .

No query parameters.

## DELETE /project/{projectKeyOrId}/priorityscheme/{schemeId}

Unassigns project from priority scheme. Operation will fail for defualt priority scheme, project is not found or project is not associated with provided priority scheme. All project keys associated with the priority scheme will only be returned if additional query parameter is provided expand=projectKeys .

No query parameters.

## GET /project/{projectKeyOrId}/securitylevel

Returns all security levels for the project that the current logged in user has access to. If the user does not have the Set Issue Security permission, the list will be empty.

No query parameters.

## GET /project/{projectKeyOrId}/workflowscheme

Returns the workflow scheme that is associated with requested project.

No query parameters.
