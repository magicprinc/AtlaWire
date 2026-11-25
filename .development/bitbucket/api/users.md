<!-- bitbucket 5.10.0 - resource group: users -->

# `users`

8 method(s) as this deployment serves them. Source: its own `application.wadl`.

## GET /users

Retrieve a page of users, optionally run through provided filters. Only authenticated users may call this resource. Supported Filters Filters are provided in query parameters in a standard name=value fashion. The following filters are currently supported: {@code filter} - return only users, whose username, name or email address contain the {@code filter} value {@code group} - return only users who are members of the given group {@code permission} - the "root" of a permission filter, whose value must be a valid global, project, or repository permission. Additional filter parameters referring to this filter that specify the resource (project or repository) to apply the filter to must be prefixed with permission. . See the section "Permission Filters" below for more details. {@code permission.N} - the "root" of a single permission filter, similar to the {@code permission} parameter, where "N" is a natural number starting from 1. This allows clients to specify multiple permission filters, by providing consecutive filters as {@code permission.1}, {@code permission.2} etc. Note that the filters numbering has to start with 1 and be continuous for all filters to be processed. The total allowed number of permission filters is 50 and all filters exceeding that limit will be dropped. See the section "Permission Filters" below for more details on how the permission filters are processed. Permission Filters The following three sub-sections list parameters supported for permission filters (where [root] is the root permission filter name, e.g. {@code permission}, {@code permission.1} etc.) depending on the permission resource. The system determines which filter to apply (Global, Project or Repository permission) based on the [root] permission value. E.g. {@code ADMIN} is a global permission, {@code PROJECT_ADMIN} is a project permission and {@code REPO_ADMIN} is a repository permission. Note that the parameters for a given resource will be looked up in the order as they are listed below, that is e.g. for a project resource, if both {@code projectId} and {@code projectKey} are provided, the system will use {@code projectId} for the lookup. Global permissions The permission value under [root] is the only required and recognized parameter, as global permissions do not apply to a specific resource. Example valid filter: permission=ADMIN . Project permissions [root] - specifies the project permission [root].projectId - specifies the project ID to lookup the project by [root].projectKey - specifies the project key to lookup the project by Example valid filter: permission.1=PROJECT_ADMIN&permission.1.projectKey=TEST_PROJECT . Repository permissions [root] - specifies the repository permission [root].projectId - specifies the repository ID to lookup the repository by [root].projectKey and [root].repositorySlug - specifies the project key and repository slug to lookup the repository by; both values need to be provided for this look up to be triggered Example valid filter: permission.2=REPO_ADMIN&permission.2.projectKey=TEST_PROJECT&permission.2.repositorySlug=test_repo .

No query parameters.

## PUT /users

Update the currently authenticated user's details. The update will always be applied to the currently authenticated user.

No query parameters.

## PUT /users/credentials

Update the currently authenticated user's password.

No query parameters.

## GET /users/{userSlug}

Retrieve the user matching the supplied userSlug .

No query parameters.

## DELETE /users/{userSlug}/avatar.png

Delete the avatar associated to a user. Users are always allowed to delete their own avatar. To delete someone else's avatar the authenticated user must have global ADMIN permission, or global SYS_ADMIN permission to update a SYS_ADMIN user's avatar.

No query parameters.

## POST /users/{userSlug}/avatar.png

Update the avatar for the user with the supplied slug . This resource accepts POST multipart form data, containing a single image in a form-field named 'avatar'. There are configurable server limits on both the dimensions (1024x1024 pixels by default) and uploaded file size (1MB by default). Several different image formats are supported, but PNG and JPEG are preferred due to the file size limit. This resource has Cross-Site Request Forgery (XSRF) protection. To allow the request to pass the XSRF check the caller needs to send an X-Atlassian-Token HTTP header with the value no-check . An example curl request to upload an image name 'avatar.png' would be: curl -X POST -u username:password -H "X-Atlassian-Token: no-check" http://example.com/rest/api/latest/users/jdoe/avatar.png -F avatar=@avatar.png Users are always allowed to update their own avatar. To update someone else's avatar the authenticated user must have global ADMIN permission, or global SYS_ADMIN permission to update a SYS_ADMIN user's avatar.

No query parameters.

## GET /users/{userSlug}/settings

Retrieve a map of user setting key values for a specific user identified by the user slug.

No query parameters.

## POST /users/{userSlug}/settings

Update the entries of a map of user setting key/values for a specific user identified by the user slug.

No query parameters.
