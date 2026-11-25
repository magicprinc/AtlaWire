<!-- jira 8.22.2 - resource group: comment -->

# `comment`

4 method(s) as this deployment serves them. Source: its own `application.wadl`.

## GET /comment/{commentId}/properties

Returns the keys of all properties for the comment identified by the key or by the id.

No query parameters.

## DELETE /comment/{commentId}/properties/{propertyKey}

Removes the property from the comment identified by the key or by the id. Ths user removing the property is required to have permissions to administer the comment.

No query parameters.

## GET /comment/{commentId}/properties/{propertyKey}

Returns the value of the property with a given key from the comment identified by the key or by the id. The user who retrieves the property is required to have permissions to read the comment.

No query parameters.

## PUT /comment/{commentId}/properties/{propertyKey}

Sets the value of the specified comment's property. You can use this resource to store a custom data against the comment identified by the key or by the id. The user who stores the data is required to have permissions to administer the comment.

No query parameters.
