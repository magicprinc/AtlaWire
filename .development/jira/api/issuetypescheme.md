<!-- jira 8.22.2 - resource group: issuetypescheme -->

# `issuetypescheme`

10 method(s) as this deployment serves them. Source: its own `application.wadl`.

## GET /issuetypescheme

Returns a list of all issue type schemes visible to the user (must be admin). All issue types associated with the scheme will only be returned if an additional query parameter is provided: expand=schemes.issueTypes . Similarly, the default issue type associated with the scheme (if one exists) will only be returned if additional an query parameter is provided: expand=schemes.defaultIssueType . Note that both query parameters can be used together: expand=schemes.issueTypes,schemes.defaultIssueType .

No query parameters.

## POST /issuetypescheme

Creates an issue type scheme from a JSON representation. (Admin required)

No query parameters.

## DELETE /issuetypescheme/{schemeId}

Deletes the specified issue type scheme. Any projects associated with this IssueTypeScheme will be automatically associated with the global default IssueTypeScheme. (Admin required)

No query parameters.

## GET /issuetypescheme/{schemeId}

Returns a full representation of the issue type scheme that has the given id (must be admin).

No query parameters.

## PUT /issuetypescheme/{schemeId}

Updates the specified issue type scheme from a JSON representation. (Admin required)

No query parameters.

## DELETE /issuetypescheme/{schemeId}/associations

Removes all project associations for the specified issue type scheme. These projects revert to an association with the default/global issue type scheme.(Admin required)

No query parameters.

## GET /issuetypescheme/{schemeId}/associations

For the specified issue type scheme, returns all of the associated projects. (Admin required)

| query | type | default |
|---|---|---|
| `expand` | string |  |

## POST /issuetypescheme/{schemeId}/associations

Adds additional projects to those already associated with the specified issue type scheme. (Admin required)

No query parameters.

## PUT /issuetypescheme/{schemeId}/associations

Associates the given projects with the specified issue type scheme. Any existing project-associations the issue type scheme has will be overwritten. (Admin required)

No query parameters.

## DELETE /issuetypescheme/{schemeId}/associations/{projIdOrKey}

For the specified issue type scheme, removes the given project association . This project reverts to an association with the default/global issue type scheme.(Admin required)

No query parameters.
