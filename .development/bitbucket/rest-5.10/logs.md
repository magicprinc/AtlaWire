<!-- Bitbucket Server 5.10.0 REST API — resource group: logs (4 endpoints) -->

## /rest/api/1.0/logs/logger/{loggerName}

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **loggerName** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the name of the logger. |

###### Methods

#### GET

Retrieve the current log level for a given logger.

The authenticated user must have **ADMIN** permission or higher to call this resource.

*Example response representations:*

-

  200 - application/json (logLevel)

  ###### Example

      {"logLevel":"DEBUG"}

  The log level of the logger.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to retrieve the log level.

## /rest/api/1.0/logs/logger/{loggerName}/{levelName}

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **levelName** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the level to set the logger to. Either TRACE, DEBUG, INFO, WARN or ERROR |
| **loggerName** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the name of the logger. |

###### Methods

#### PUT

Set the current log level for a given logger.

The authenticated user must have **ADMIN** permission or higher to call this resource.

*Example response representations:*

-

  204 - application/json

  The log level was successfully changed.

-

  400 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The log level was invalid.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to set the log level.

## /rest/api/1.0/logs/rootLogger

###### Methods

#### GET

Retrieve the current log level for the root logger.

The authenticated user must have **ADMIN** permission or higher to call this resource.

*Example response representations:*

-

  200 - application/json (logLevel)

  ###### Example

      {"logLevel":"DEBUG"}

  The log level of the logger.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to retrieve the log level.

## /rest/api/1.0/logs/rootLogger/{levelName}

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **levelName** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the level to set the logger to. Either TRACE, DEBUG, INFO, WARN or ERROR |

###### Methods

#### PUT

Set the current log level for the root logger.

The authenticated user must have **ADMIN** permission or higher to call this resource.

*Example response representations:*

-

  204 - application/json

  The log level was successfully changed.

-

  400 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The log level was invalid.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to retrieve the log level.
