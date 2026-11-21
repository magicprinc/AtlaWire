<!-- Bitbucket Server 5.10.0 REST API — resource group: admin--pull-requests (1 endpoints) -->

## /rest/api/1.0/admin/pull-requests/{scmId}

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **scmId** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the id of the scm to get strategies for |

###### Methods

#### POST

Update the pull request merge strategies for the context repository.

The authenticated user must have **ADMIN** permission for the context repository to call this resource.

Only the strategies provided will be enabled, only one may be set to default

An explicitly set pull request merge strategy configuration can be deleted by POSTing a document with an empty "mergeConfig" attribute. i.e:

 {
     "mergeConfig": {
     }
 }
 

Upon completion of this request, the effective configuration will be the default configuration.

*Example request representations:*

-

  application/json

  ###### Example

      {"defaultStrategy":{"id":"no-ff"},"strategies":[{"id":"no-ff"}]}

*Example response representations:*

-

  200 - application/json (strategies)

  ###### Example

      {"defaultStrategy":{"description":"Always create a merge commit","enabled":true,"flag":"--no-ff","id":"no-ff","name":"Merge commit"},"strategies":[{"description":"Always create a merge commit","enabled":true,"flag":"--no-ff","id":"no-ff","name":"Merge commit"}],"type":"repository"}

  The repository pull request merge strategies for the context repository.

-

  400 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The repository pull request merge strategies were not updated due to a validation error.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to administrate the specified repository.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository does not exist.

#### GET

*This is a [paged API](#paging-params)*.

Retrieve the merge strategies available for this instance.

The user must be authenticated to call this resource.

*Example response representations:*

-

  200 - application/json ([page](#paging-params))

  ###### Example

      {"defaultStrategy":{"description":"Always create a merge commit","enabled":true,"flag":"--no-ff","id":"no-ff","name":"Merge commit"},"strategies":[{"description":"Always create a merge commit","enabled":true,"flag":"--no-ff","id":"no-ff","name":"Merge commit"}],"type":"repository"}

  The merge configuration of this instance.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to see the request repository.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The request repository does not exist.
