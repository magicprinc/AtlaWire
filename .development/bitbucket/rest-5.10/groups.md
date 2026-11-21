<!-- Bitbucket Server 5.10.0 REST API — resource group: groups (1 endpoints) -->

## /rest/api/1.0/groups

###### Methods

#### GET

###### /rest/api/1.0/groups?filter

*This is a [paged API](#paging-params)*.

Retrieve a page of group names.

The authenticated user must have **PROJECT_ADMIN** permission or higher to call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **filter** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | if specified only group names containing the supplied string will be returned |

*Example response representations:*

-

  200 - application/json ([page](#paging-params))

  ###### Example

      {"size":2,"limit":25,"isLastPage":true,"values":["group_a","group_b"],"start":0}

  A page of group names.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user is not a project administrator.
