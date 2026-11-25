<!-- jira 8.22.2 - resource group: cluster -->

# `cluster`

9 method(s) as this deployment serves them. Source: its own `application.wadl`.

## PUT /cluster/index-snapshot/{nodeId}

request current index from node (the request is processed asynchronously)

No query parameters.

## DELETE /cluster/node/{nodeId}

Delete the node from the cluster if state of node is OFFLINE.

No query parameters.

## PUT /cluster/node/{nodeId}/offline

Change the node's state to offline if the node is reporting as active, but is not alive. Don't use this method as an equivalent of running ./stop-jira.sh. This method doesn't shut down a node, but only changes its state, so that other nodes don't communicate with it.

No query parameters.

## GET /cluster/nodes

No query parameters.

## POST /cluster/zdu/approve

No query parameters.

## POST /cluster/zdu/cancel

No query parameters.

## POST /cluster/zdu/retryUpgrade

No query parameters.

## POST /cluster/zdu/start

No query parameters.

## GET /cluster/zdu/state

No query parameters.
