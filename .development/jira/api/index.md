<!-- jira 8.22.2 - resource group: index -->

# `index`

1 method(s) as this deployment serves them. Source: its own `application.wadl`.

## GET /index/summary

Summarizes index condition of current node. Returned data consists of: nodeId - Node identifier. reportTime - Time of this report creation. issueIndex - Summary of issue index status. replicationQueues - Map of index replication queues, where keys represent nodes from which replication operations came from. issueIndex can contain: indexReadable - If false the end point failed to read data from issue index (check Jira logs for detailed stack trace), otherwise true . When false other fields of issueIndex can be not visible. countInDatabase - Count of issues found in database. countInIndex - Count of issues found while querying index. lastUpdatedInDatabase - Time of last update of issue found in database. lastUpdatedInIndex - Time of last update of issue found while querying index. replicationQueues 's map values can contain: lastConsumedOperation - Last executed index replication operation by current node from sending node's queue. lastConsumedOperation.id - Identifier of the operation. lastConsumedOperation.replicationTime - Time when the operation was sent to other nodes. lastOperationInQueue - Last index replication operation in sending node's queue. lastOperationInQueue.id - Identifier of the operation. lastOperationInQueue.replicationTime - Time when the operation was sent to other nodes. queueSize - Number of operations in queue from sending node to current node.

No query parameters.
