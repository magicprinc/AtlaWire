<!-- bitbucket 5.10.0 - resource group: repos -->

# `repos`

1 method(s) as this deployment serves them. Source: its own `application.wadl`.

## GET /repos

Retrieve a page of repositories based on query parameters that control the search. See the documentation of the parameters for more details. This resource is anonymously accessible. Note on permissions. In absence of the {@code permission} query parameter the implicit 'read' permission is assumed. Please note that this permission is lower than the REPO_READ permission rather than being equal to it. The implicit 'read' permission for a given repository is assigned to any user that has any of the higher permissions, such as REPO_READ , as well as to anonymous users if the repository is marked as public. The important implication of the above is that an anonymous request to this resource with a permission level REPO_READ is guaranteed to receive an empty list of repositories as a result. For anonymous requests it is therefore recommended to not specify the permission parameter at all.

| query | type | default |
|---|---|---|
| `name` | string |  |
| `projectname` | string |  |
| `permission` | string |  |
| `visibility` | string |  |
