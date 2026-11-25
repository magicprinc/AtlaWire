<!-- jira 8.22.2 - resource group: mypermissions -->

# `mypermissions`

1 method(s) as this deployment serves them. Source: its own `application.wadl`.

## GET /mypermissions

Returns all permissions in the system and whether the currently logged in user has them. You can optionally provide a specific context to get permissions for (projectKey OR projectId OR issueKey OR issueId) When no context supplied the project related permissions will return true if the user has that permission in ANY project If a project context is provided, project related permissions will return true if the user has the permissions in the specified project. For permissions that are determined using issue data (e.g Current Assignee), true will be returned if the user meets the permission criteria in ANY issue in that project If an issue context is provided, it will return whether or not the user has each permission in that specific issue NB: The above means that for issue-level permissions (EDIT_ISSUE for example), hasPermission may be true when no context is provided, or when a project context is provided, but may be false for any given (or all) issues. This would occur (for example) if Reporters were given the EDIT_ISSUE permission. This is because any user could be a reporter, except in the context of a concrete issue, where the reporter is known. Global permissions will still be returned for all scopes. Prior to version 6.4 this service returned project permissions with keys corresponding to com.atlassian.jira.security.Permissions.Permission constants. Since 6.4 those keys are considered deprecated and this service returns system project permission keys corresponding to constants defined in com.atlassian.jira.permission.ProjectPermissions. Permissions with legacy keys are still also returned for backwards compatibility, they are marked with an attribute deprecatedKey=true. The attribute is missing for project permissions with the current keys.

| query | type | default |
|---|---|---|
| `projectKey` | string |  |
| `projectId` | string |  |
| `issueKey` | string |  |
| `issueId` | string |  |
