<!-- jira 8.22.2 - resource group: email-templates -->

# `email-templates`

5 method(s) as this deployment serves them. Source: its own `application.wadl`.

## GET /email-templates

Creates a zip file containing email templates at local home and returns the file.

No query parameters.

## POST /email-templates

Extracts given zip file to temporary templates folder. If the folder already exists it will replace it's content

No query parameters.

## POST /email-templates/apply

Replaces the current email templates pack with previously uploaded one, if exists.

No query parameters.

## POST /email-templates/revert

Replaces the current email templates pack with default templates, which are copied over from Jira binaries.

No query parameters.

## GET /email-templates/types

Returns a list of root templates mapped with Event Types. The list can be used to decide which test emails to send.

No query parameters.
