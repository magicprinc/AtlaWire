<!-- jira 8.22.2 - resource group: applicationrole -->

# `applicationrole`

4 method(s) as this deployment serves them. Source: its own `application.wadl`.

## GET /applicationrole

Returns all ApplicationRoles in the system. Will also return an ETag header containing a version hash of the collection of ApplicationRoles.

No query parameters.

## PUT /applicationrole

Updates the ApplicationRoles with the passed data if the version hash is the same as the server. Only the groups and default groups setting of the role may be updated. Requests to change the key or the name of the role will be silently ignored. It is acceptable to pass only the roles that are updated as roles that are present in the server but not in data to update with, will not be deleted.

No query parameters.

## GET /applicationrole/{key}

Returns the ApplicationRole with passed key if it exists.

No query parameters.

## PUT /applicationrole/{key}

Updates the ApplicationRole with the passed data. Only the groups and default groups setting of the role may be updated. Requests to change the key or the name of the role will be silently ignored. Optional: If versionHash is passed through the If-Match header the request will be rejected if not the same as server

No query parameters.
