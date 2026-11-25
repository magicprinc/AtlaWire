<!-- jira 8.22.2 - resource group: terminology -->

# `terminology`

3 method(s) as this deployment serves them. Source: its own `application.wadl`.

## GET /terminology/entries

Returns the list of all defined names for the default words "epic" and "sprint".

No query parameters.

## POST /terminology/entries

Change epic/sprint names from {"originalName"} to {"newName"}. The {"newName"} will be displayed in Jira instead of {"originalName"}. {"originalName"} must be equal to "epic" or "sprint". There can be only one entry per unique {"originalName"}. {"newName"} can only consist of alphanumeric characters and spaces e.g. {"newName": "iteration number 2"}. {"newName"} must be between 1 to 100 characters. It can't use the already defined {"newName"} values or restricted JQL words . To reset {"newName"} to the default value, enter the {"originalName"} value as the value for {"newName"}. For example, if you want to return to {"originalName": "sprint"}, enter {"newName": "sprint"}.

No query parameters.

## GET /terminology/entries/{originalName}

Returns epic or sprint name as specified in the {originalName} path param.

No query parameters.
