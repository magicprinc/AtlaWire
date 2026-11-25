<!-- jira 8.22.2 - resource group: issue--createmeta -->

# `issue--createmeta`

3 method(s) as this deployment serves them. Source: its own `application.wadl`.

## GET /issue/createmeta

Returns the meta data for creating issues. This includes the available projects, issue types and fields, including field types and whether or not those fields are required. Projects will not be returned if the user does not have permission to create issues in that project. The fields in the createmeta correspond to the fields in the create screen for the project/issuetype. Fields not in the screen will not be in the createmeta. Fields will only be returned if expand=projects.issuetypes.fields . The results can be filtered by project and/or issue type, given by the query params.

| query | type | default |
|---|---|---|
| `projectIds` | string |  |
| `projectKeys` | string |  |
| `issuetypeIds` | string |  |
| `issuetypeNames` | string |  |

## GET /issue/createmeta/{projectIdOrKey}/issuetypes

Returns the metadata for issue types used for creating issues. Data will not be returned if the user does not have permission to create issues in that project.

| query | type | default |
|---|---|---|
| `startAt` | long | `0` |
| `maxResults` | int | `50` |

## GET /issue/createmeta/{projectIdOrKey}/issuetypes/{issueTypeId}

Returns the metadata for issue types used for creating issues. Data will not be returned if the user does not have permission to create issues in that project.

| query | type | default |
|---|---|---|
| `startAt` | long | `0` |
| `maxResults` | int | `50` |
