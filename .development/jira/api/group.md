<!-- jira 8.22.2 - resource group: group -->

# `group`

6 method(s) as this deployment serves them. Source: its own `application.wadl`.

## DELETE /group

Deletes a group by given group parameter. Returns no content

| query | type | default |
|---|---|---|
| `groupname` | string |  |
| `swapGroup` | string |  |

## GET /group

Returns REST representation for the requested group. Allows to get list of active users belonging to the specified group and its subgroups if "users" expand option is provided. You can page through users list by using indexes in expand param. For example to get users from index 10 to index 15 use "users[10:15]" expand value. This will return 6 users (if there are at least 16 users in this group). Indexes are 0-based and inclusive. This resource is deprecated, please use group/member API instead.

| query | type | default |
|---|---|---|
| `groupname` | string |  |
| `expand` | string |  |

## POST /group

Creates a group by given group parameter Returns REST representation for the requested group.

No query parameters.

## GET /group/member

This resource returns a paginated list of users who are members of the specified group and its subgroups. Users in the page are ordered by user names. User of this resource is required to have sysadmin or admin permissions.

| query | type | default |
|---|---|---|
| `groupname` | string |  |
| `includeInactiveUsers` | boolean | `false` |
| `startAt` | long | `0` |
| `maxResults` | int | `50` |

## DELETE /group/user

Removes given user from a group. Returns no content

| query | type | default |
|---|---|---|
| `groupname` | string |  |
| `username` | string |  |

## POST /group/user

Adds given user to a group. Returns the current state of the group.

| query | type | default |
|---|---|---|
| `groupname` | string |  |
