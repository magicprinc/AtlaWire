<!-- jira 8.22.2 - resource group: version -->

# `version`

16 method(s) as this deployment serves them. Source: its own `application.wadl`.

## POST /version

Create a version via POST.

No query parameters.

## GET /version/remotelink

Returns the remote version links for a given global ID.

| query | type | default |
|---|---|---|
| `globalId` | string |  |

## DELETE /version/{id}

Delete a project version.

| query | type | default |
|---|---|---|
| `moveFixIssuesTo` | string |  |
| `moveAffectedIssuesTo` | string |  |

## GET /version/{id}

Returns a project version.

| query | type | default |
|---|---|---|
| `expand` | string |  |

## PUT /version/{id}

Modify a version via PUT. Any fields present in the PUT will override existing values. As a convenience, if a field is not present, it is silently ignored.

No query parameters.

## PUT /version/{id}/mergeto/{moveIssuesTo}

Merge versions

No query parameters.

## POST /version/{id}/move

Modify a version's sequence within a project. The move version bean has 2 alternative field value pairs: position An absolute position, which may have a value of 'First', 'Last', 'Earlier' or 'Later' after A version to place this version after. The value should be the self link of another version

No query parameters.

## GET /version/{id}/relatedIssueCounts

Returns a bean containing the number of fixed in and affected issues for the given version.

No query parameters.

## POST /version/{id}/removeAndSwap

Delete a project version.

No query parameters.

## GET /version/{id}/unresolvedIssueCount

Returns the number of unresolved issues for the given version

No query parameters.

## DELETE /version/{versionId}/remotelink

Delete all remote version links for a given version ID.

No query parameters.

## GET /version/{versionId}/remotelink

Returns the remote version links associated with the given version ID.

No query parameters.

## POST /version/{versionId}/remotelink

Create a remote version link via POST. The link's global ID will be taken from the JSON payload if provided; otherwise, it will be generated.

No query parameters.

## DELETE /version/{versionId}/remotelink/{globalId}

Delete a specific remote version link with the given version ID and global ID.

No query parameters.

## GET /version/{versionId}/remotelink/{globalId}

A REST sub-resource representing a remote version link

No query parameters.

## POST /version/{versionId}/remotelink/{globalId}

Create a remote version link via POST. The link's global ID will be taken from the JSON payload if provided; otherwise, it will be generated.

No query parameters.
