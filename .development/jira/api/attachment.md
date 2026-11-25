<!-- jira 8.22.2 - resource group: attachment -->

# `attachment`

5 method(s) as this deployment serves them. Source: its own `application.wadl`.

## GET /attachment/meta

Returns the meta information for an attachments, specifically if they are enabled and the maximum upload size allowed.

No query parameters.

## DELETE /attachment/{id}

Remove an attachment from an issue.

No query parameters.

## GET /attachment/{id}

Returns the meta-data for an attachment, including the URI of the actual attached file.

No query parameters.

## GET /attachment/{id}/expand/human

Tries to expand an attachment. Output is human-readable and subject to change.

No query parameters.

## GET /attachment/{id}/expand/raw

Tries to expand an attachment. Output is raw and should be backwards-compatible through the course of time.

No query parameters.
