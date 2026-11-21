<!-- Bitbucket Server 5.10.0 REST API — resource group: admin--cluster (1 endpoints) -->

## /rest/api/1.0/admin/cluster

###### Methods

#### GET

Gets information about the nodes that currently make up the stash cluster.

The authenticated user must have the **SYS_ADMIN** permission to call this resource.

*Example response representations:*

-

  200 - application/json

  ###### Example

      {"localNode":{"id":"d4fde8b1-2504-4998-a0ba-14fbe98edd4d","name":"foo","address":{"hostName":"foo","port":5000},"local":true},"nodes":[{"id":"d4fde8b1-2504-4998-a0ba-14fbe98edd4d","name":"foo","address":{"hostName":"foo","port":5000},"local":true},{"id":"73518909-8e86-445b-8345-fcbf2e0934b6","name":"bar","address":{"hostName":"bar","port":5001},"local":true}],"running":true}

  Information about the cluster

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to retrieve the cluster information.
