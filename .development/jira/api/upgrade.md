<!-- jira 8.22.2 - resource group: upgrade -->

# `upgrade`

2 method(s) as this deployment serves them. Source: its own `application.wadl`.

## GET /upgrade

Returns the result of the last upgrade task. Returns {@link javax.ws.rs.core.Response#seeOther(java.net.URI)} if still running.

No query parameters.

## POST /upgrade

Runs any pending delayed upgrade tasks. Need Admin permissions to do this.

No query parameters.
