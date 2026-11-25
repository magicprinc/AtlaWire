<!-- jira 8.22.2 - resource group: issue--properties -->

# `issue--properties`

4 method(s) as this deployment serves them. Source: its own `application.wadl`.

## GET /issue/{issueIdOrKey}/properties

Returns the keys of all properties for the issue identified by the key or by the id.

No query parameters.

## DELETE /issue/{issueIdOrKey}/properties/{propertyKey}

Removes the property from the issue identified by the key or by the id. Ths user removing the property is required to have permissions to edit the issue.

No query parameters.

## GET /issue/{issueIdOrKey}/properties/{propertyKey}

Returns the value of the property with a given key from the issue identified by the key or by the id. The user who retrieves the property is required to have permissions to read the issue.

No query parameters.

## PUT /issue/{issueIdOrKey}/properties/{propertyKey}

Sets the value of the specified issue's property. You can use this resource to store a custom data against the issue identified by the key or by the id. The user who stores the data is required to have permissions to edit the issue.

No query parameters.
