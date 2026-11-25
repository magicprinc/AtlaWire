<!-- jira 8.22.2 - resource group: issueLink -->

# `issueLink`

3 method(s) as this deployment serves them. Source: its own `application.wadl`.

## POST /issueLink

Creates an issue link between two issues. The user requires the link issue permission for the issue which will be linked to another issue. The specified link type in the request is used to create the link and will create a link from the first issue to the second issue using the outward description. It also create a link from the second issue to the first issue using the inward description of the issue link type. It will add the supplied comment to the first issue. The comment can have a restriction who can view it. If group is specified, only users of this group can view this comment, if roleLevel is specified only users who have the specified role can view this comment. The user who creates the issue link needs to belong to the specified group or have the specified role.

No query parameters.

## DELETE /issueLink/{linkId}

Deletes an issue link with the specified id. To be able to delete an issue link you must be able to view both issues and must have the link issue permission for at least one of the issues.

No query parameters.

## GET /issueLink/{linkId}

Returns an issue link with the specified id.

No query parameters.
