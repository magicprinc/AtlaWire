<!-- bitbucket 5.10.0 - resource group: logs -->

# `logs`

4 method(s) as this deployment serves them. Source: its own `application.wadl`.

## GET /logs/logger/{loggerName}

Retrieve the current log level for a given logger. The authenticated user must have ADMIN permission or higher to call this resource.

No query parameters.

## PUT /logs/logger/{loggerName}/{levelName}

Set the current log level for a given logger. The authenticated user must have ADMIN permission or higher to call this resource.

No query parameters.

## GET /logs/rootLogger

Retrieve the current log level for the root logger. The authenticated user must have ADMIN permission or higher to call this resource.

No query parameters.

## PUT /logs/rootLogger/{levelName}

Set the current log level for the root logger. The authenticated user must have ADMIN permission or higher to call this resource.

No query parameters.
