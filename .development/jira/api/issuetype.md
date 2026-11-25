<!-- jira 8.22.2 - resource group: issuetype -->

# `issuetype`

13 method(s) as this deployment serves them. Source: its own `application.wadl`.

## GET /issuetype

Returns a list of all issue types visible to the user

No query parameters.

## POST /issuetype

Creates an issue type from a JSON representation and adds the issue newly created issue type to the default issue type scheme.

No query parameters.

## DELETE /issuetype/{id}

Deletes the specified issue type. If the issue type has any associated issues, these issues will be migrated to the alternative issue type specified in the parameter. You can determine the alternative issue types by calling the /rest/api/2/issuetype/{id}/alternatives resource.

| query | type | default |
|---|---|---|
| `alternativeIssueTypeId` | string |  |

## GET /issuetype/{id}

Returns a full representation of the issue type that has the given id.

No query parameters.

## PUT /issuetype/{id}

Updates the specified issue type from a JSON representation.

No query parameters.

## GET /issuetype/{id}/alternatives

Returns a list of all alternative issue types for the given issue type id. The list will contain these issues types, to which issues assigned to the given issue type can be migrated. The suitable alternatives are issue types which are assigned to the same workflow, the same field configuration and the same screen scheme.

No query parameters.

## POST /issuetype/{id}/avatar

Converts temporary avatar into a real avatar

No query parameters.

## POST /issuetype/{id}/avatar/temporary

Creates temporary avatar using multipart. The response is sent back as JSON stored in a textarea. This is because the client uses remote iframing to submit avatars using multipart. So we must send them a valid HTML page back from which the client parses the JSON from. Creating a temporary avatar is part of a 3-step process in uploading a new avatar for an issue type: upload, crop, confirm. This endpoint allows you to use a multipart upload instead of sending the image directly as the request body. You *must* use "avatar" as the name of the upload parameter: curl -c cookiejar.txt -X POST -u admin:admin -H "X-Atlassian-Token: no-check" \ -F "avatar=@mynewavatar.png;type=image/png" \ 'http://localhost:8090/jira/rest/api/2/issuetype/1/avatar/temporary'

No query parameters.

## POST /issuetype/{id}/avatar/temporary

Creates temporary avatar. Creating a temporary avatar is part of a 3-step process in uploading a new avatar for an issue type: upload, crop, confirm. The following examples shows these three steps using curl. The cookies (session) need to be preserved between requests, hence the use of -b and -c. The id created in step 2 needs to be passed to step 3 (you can simply pass the whole response of step 2 as the request of step 3). curl -c cookiejar.txt -X POST -u admin:admin -H "X-Atlassian-Token: no-check" \ -H "Content-Type: image/png" --data-binary @mynewavatar.png \ 'http://localhost:8090/jira/rest/api/2/issuetype/1/avatar/temporary?filename=mynewavatar.png' curl -b cookiejar.txt -X POST -u admin:admin -H "X-Atlassian-Token: no-check" \ -H "Content-Type: application/json" --data '{"cropperWidth": "65","cropperOffsetX": "10","cropperOffsetY": "16"}' \ -o tmpid.json \ http://localhost:8090/jira/rest/api/2/issuetype/1/avatar curl -b cookiejar.txt -X PUT -u admin:admin -H "X-Atlassian-Token: no-check" \ -H "Content-Type: application/json" --data-binary @tmpid.json \ http://localhost:8090/jira/rest/api/2/issuetype/1/avatar

| query | type | default |
|---|---|---|
| `filename` | string |  |
| `size` | long |  |

## GET /issuetype/{issueTypeId}/properties

Returns the keys of all properties for the issue type identified by the id.

No query parameters.

## DELETE /issuetype/{issueTypeId}/properties/{propertyKey}

Removes the property from the issue type identified by the id. Ths user removing the property is required to have permissions to edit the issue type.

No query parameters.

## GET /issuetype/{issueTypeId}/properties/{propertyKey}

Returns the value of the property with a given key from the issue type identified by the id. The user who retrieves the property is required to have permissions to view the issue type.

No query parameters.

## PUT /issuetype/{issueTypeId}/properties/{propertyKey}

Sets the value of the specified issue type's property. You can use this resource to store a custom data against an issue type identified by the id. The user who stores the data is required to have permissions to edit an issue type.

No query parameters.
