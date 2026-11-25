<!-- bitbucket 5.10.0 - resource group: projects--repos -->

# `projects--repos`

103 method(s) as this deployment serves them. Source: its own `application.wadl`.

## GET /projects/{projectKey}/repos

Retrieve repositories from the project corresponding to the supplied projectKey . The authenticated user must have REPO_READ permission for the specified project to call this resource.

No query parameters.

## POST /projects/{projectKey}/repos

Create a new repository. Requires an existing project in which this repository will be created. The only parameters which will be used are name and scmId. The authenticated user must have PROJECT_ADMIN permission for the context project to call this resource.

No query parameters.

## DELETE /projects/{projectKey}/repos/{repositorySlug}

Schedule the repository matching the supplied projectKey and repositorySlug to be deleted. If the request repository is not present The authenticated user must have REPO_ADMIN permission for the specified repository to call this resource.

No query parameters.

## GET /projects/{projectKey}/repos/{repositorySlug}

Retrieve the repository matching the supplied projectKey and repositorySlug . The authenticated user must have REPO_READ permission for the specified repository to call this resource.

No query parameters.

## POST /projects/{projectKey}/repos/{repositorySlug}

Create a new repository forked from an existing repository. The JSON body for this {@code POST} is not required to contain any properties. Even the name may be omitted. The following properties will be used, if provided: {@code "name":"Fork name"} - Specifies the forked repository's name Defaults to the name of the origin repository if not specified {@code "project":{"key":"TARGET_KEY"}} - Specifies the forked repository's target project by key Defaults to the current user's personal project if not specified The authenticated user must have REPO_READ permission for the specified repository and PROJECT_ADMIN on the target project to call this resource. Note that users always have PROJECT_ADMIN permission on their personal projects.

No query parameters.

## PUT /projects/{projectKey}/repos/{repositorySlug}

Update the repository matching the repositorySlug supplied in the resource path. The repository's slug is derived from its name. If the name changes the slug may also change. This API can be used to move the repository to a different project by setting the new project in the request, example: {@code {"project":{"key":"NEW_KEY"}}} . The authenticated user must have REPO_ADMIN permission for the specified repository to call this resource.

No query parameters.

## GET /projects/{projectKey}/repos/{repositorySlug}/archive

Streams an archive of the repository's contents at the requested commit. If no at= commit is requested, an archive of the default branch is streamed. The filename= query parameter may be used to specify the exact filename to include in the "Content-Disposition" header. If an explicit filename is not provided, one will be automatically generated based on what is being archived. Its format depends on the at= value: No at= commit: &lt;slug&gt;-&lt;default-branch-name&gt;@&lt;commit&gt;.&lt;format&gt; ; e.g. example-master@43c2f8a0fe8.zip at=sha : &lt;slug&gt;-&lt;at&gt;.&lt;format&gt; ; e.g. example-09bcbb00100cfbb5310fb6834a1d5ce6cac253e9.tar.gz at=branchOrTag : &lt;slug&gt;-&lt;branchOrTag&gt;@&lt;commit&gt;.&lt;format&gt; ; e.g. example-feature@bbb225f16e1.tar If the branch or tag is qualified (e.g. refs/heads/master , the short name ( master ) will be included in the filename If the branch or tag's short name includes slashes (e.g. release/4.6 ), they will be converted to hyphens in the filename ( release-4.5 ) Archives may be requested in the following formats by adding the format= query parameter: zip : A zip file using standard compression (Default) tar : An uncompressed tarball tar.gz or tgz : A GZip-compressed tarball The contents of the archive may be filtered by using the path= query parameter to specify paths to include. path= may be specified multiple times to include multiple paths. The prefix= query parameter may be used to define a directory (or multiple directories) where the archive's contents should be placed. If the prefix does not end with / , one will be added automatically. The prefix is always treated as a directory; it is not possible to use it to prepend characters to the entries in the archive. Archives of public repositories may be streamed by any authenticated or anonymous user. Streaming archives for non-public repositories requires an authenticated user with at least REPO_READ permission.

| query | type | default |
|---|---|---|
| `at` | string |  |
| `filename` | string |  |
| `format` | string |  |
| `path` | string |  |
| `prefix` | string |  |

## GET /projects/{projectKey}/repos/{repositorySlug}/branches

Retrieve the branches matching the supplied filterText param. The authenticated user must have REPO_READ permission for the specified repository to call this resource.

| query | type | default |
|---|---|---|
| `base` | string |  |
| `details` | boolean |  |
| `filterText` | string |  |
| `orderBy` | string |  |

## POST /projects/{projectKey}/repos/{repositorySlug}/branches

Creates a branch using the information provided in the {@link RestCreateBranchRequest request} The authenticated user must have REPO_WRITE permission for the context repository to call this resource.

No query parameters.

## GET /projects/{projectKey}/repos/{repositorySlug}/branches/default

Get the default branch of the repository. The authenticated user must have REPO_READ permission for the specified repository to call this resource.

No query parameters.

## PUT /projects/{projectKey}/repos/{repositorySlug}/branches/default

Update the default branch of a repository. The authenticated user must have REPO_ADMIN permission for the specified repository to call this resource.

No query parameters.

## GET /projects/{projectKey}/repos/{repositorySlug}/browse

Retrieve a page of content for a file path at a specified revision. The authenticated user must have REPO_READ permission for the specified repository to call this resource.

| query | type | default |
|---|---|---|
| `at` | string | `` |
| `type` | boolean | `false` |
| `blame` | string |  |
| `noContent` | string |  |

## GET /projects/{projectKey}/repos/{repositorySlug}/browse/{path}

Retrieve a page of content for a file path at a specified revision. The authenticated user must have REPO_READ permission for the specified repository to call this resource.

| query | type | default |
|---|---|---|
| `at` | string | `` |
| `type` | boolean | `false` |
| `blame` | string |  |
| `noContent` | string |  |

## PUT /projects/{projectKey}/repos/{repositorySlug}/browse/{path}

Update the content of path , on the given repository and branch . This resource accepts PUT multipart form data, containing the file in a form-field named content . An example curl request to update 'README.md' would be: curl -X PUT -u username:password -F content=@README.md -F 'message=Updated using file-edit REST API' -F branch=master -F sourceCommitId=5636641a50b http://example.com/rest/api/latest/projects/PROJECT_1/repos/repo_1/browse/README.md branch: the branch on which the path should be modified or created content: the full content of the file at path message: the message associated with this change, to be used as the commit message. Or null if the default message should be used. sourceCommitId: the commit ID of the file before it was edited, used to identify if content has changed. Or null if this is a new file The file can be updated or created on a new branch. In this case, the sourceBranch parameter should be provided to identify the starting point for the new branch and the branch parameter identifies the branch to create the new commit on.

No query parameters.

## GET /projects/{projectKey}/repos/{repositorySlug}/changes

Retrieve a page of changes made in a specified commit. Note: The implementation will apply a hard cap ({@code page.max.changes}) and it is not possible to request subsequent content when that cap is exceeded. The authenticated user must have REPO_READ permission for the specified repository to call this resource.

| query | type | default |
|---|---|---|
| `since` | string |  |
| `until` | string |  |

## GET /projects/{projectKey}/repos/{repositorySlug}/commits

Retrieve a page of commits from a given starting commit or "between" two commits. If no explicit commit is specified, the tip of the repository's default branch is assumed. commits may be identified by branch or tag name or by ID. A path may be supplied to restrict the returned commits to only those which affect that path. The authenticated user must have REPO_READ permission for the specified repository to call this resource.

| query | type | default |
|---|---|---|
| `followRenames` | boolean | `false` |
| `ignoreMissing` | boolean | `false` |
| `merges` | string |  |
| `path` | string |  |
| `since` | string |  |
| `until` | string |  |
| `withCounts` | boolean | `false` |

## GET /projects/{projectKey}/repos/{repositorySlug}/commits/{commitId}

Retrieve a single commit identified by its ID >. In general, that ID is a SHA1. From 2.11, ref names like "refs/heads/master" are no longer accepted by this resource. The authenticated user must have REPO_READ permission for the specified repository to call this resource.

| query | type | default |
|---|---|---|
| `path` | string |  |

## GET /projects/{projectKey}/repos/{repositorySlug}/commits/{commitId}/changes

Retrieve a page of changes made in a specified commit. Note: The implementation will apply a hard cap ({@code page.max.changes}) and it is not possible to request subsequent content when that cap is exceeded. The authenticated user must have REPO_READ permission for the specified repository to call this resource.

| query | type | default |
|---|---|---|
| `since` | string |  |
| `withComments` | boolean | `true` |

## GET /projects/{projectKey}/repos/{repositorySlug}/commits/{commitId}/comments

Retrieves the commit discussion comments that match the specified search criteria. It is possible to retrieve commit discussion comments that are anchored to a range of commits by providing the {@code sinceId} that the comments anchored from. The authenticated user must have REPO_READ permission for the repository that the commit is in to call this resource.

| query | type | default |
|---|---|---|
| `path` | string |  |
| `since` | string |  |

## POST /projects/{projectKey}/repos/{repositorySlug}/commits/{commitId}/comments

Add a new comment. Comments can be added in a few places by setting different attributes: General commit comment: { "text": "An insightful general comment on a commit." } Reply to a comment: { "text": "A measured reply.", "parent": { "id": 1 } } General file comment: { "text": "An insightful general comment on a file.", "anchor": { "diffType": "COMMIT", "fromHash": "6df3858eeb9a53a911cd17e66a9174d44ffb02cd", "path": "path/to/file", "srcPath": "path/to/file", "toHash": "04c7c5c931b9418ca7b66f51fe934d0bd9b2ba4b" } } File line comment: { "text": "A pithy comment on a particular line within a file.", "anchor": { "diffType": "COMMIT", "line": 1, "lineType": "CONTEXT", "fileType": "FROM", "fromHash": "6df3858eeb9a53a911cd17e66a9174d44ffb02cd", "path": "path/to/file", "srcPath": "path/to/file", "toHash": "04c7c5c931b9418ca7b66f51fe934d0bd9b2ba4b" } } Note: general file comments are an experimental feature and may change in the near future! For file and line comments, 'path' refers to the path of the file to which the comment should be applied and 'srcPath' refers to the path the that file used to have (only required for copies and moves). Also, fromHash and toHash refer to the sinceId / untilId (respectively) used to produce the diff on which the comment was added. Finally diffType refers to the type of diff the comment was added on. For line comments, 'line' refers to the line in the diff that the comment should apply to. 'lineType' refers to the type of diff hunk, which can be: 'ADDED' - for an added line; 'REMOVED' - for a removed line; or 'CONTEXT' - for a line that was unmodified but is in the vicinity of the diff. 'fileType' refers to the file of the diff to which the anchor should be attached - which is of relevance when displaying the diff in a side-by-side way. Currently the supported values are: 'FROM' - the source file of the diff 'TO' - the destination file of the diff If the current user is not a participant the user is added as one and updated to watch the commit. The authenticated user must have REPO_READ permission for the repository that the commit is in to call this resource.

| query | type | default |
|---|---|---|
| `since` | string |  |

## DELETE /projects/{projectKey}/repos/{repositorySlug}/commits/{commitId}/comments/{commentId}

Delete a commit comment. Anyone can delete their own comment. Only users with REPO_ADMIN and above may delete comments created by other users. Comments which have replies may not be deleted , regardless of the user's granted permissions. The authenticated user must have REPO_READ permission for the repository that the commit is in to call this resource.

| query | type | default |
|---|---|---|
| `version` | int | `-1` |

## GET /projects/{projectKey}/repos/{repositorySlug}/commits/{commitId}/comments/{commentId}

Retrieves a commit discussion comment. The authenticated user must have REPO_READ permission for the repository that the commit is in to call this resource.

No query parameters.

## PUT /projects/{projectKey}/repos/{repositorySlug}/commits/{commitId}/comments/{commentId}

Update the text of a comment. Only the user who created a comment may update it. Note: the supplied supplied JSON object must contain a version that must match the server's version of the comment or the update will fail. To determine the current version of the comment, the comment should be fetched from the server prior to the update. Look for the 'version' attribute in the returned JSON structure. The authenticated user must have REPO_READ permission for the repository that the commit is in to call this resource.

No query parameters.

## GET /projects/{projectKey}/repos/{repositorySlug}/commits/{commitId}/diff

Retrieve the diff between two provided revisions. Note: This resource is currently not paged . The server will internally apply a hard cap to the streamed lines, and it is not possible to request subsequent pages if that cap is exceeded. In the event that the cap is reached, the diff will be cut short and one or more {@code truncated} flags will be set to {@code true} on the {@code "segments"}, {@code "hunks"} and {@code "diffs"} properties, as well as the top-level object, in the returned JSON response. The authenticated user must have REPO_READ permission for the specified repository to call this resource.

| query | type | default |
|---|---|---|
| `autoSrcPath` | boolean | `false` |
| `contextLines` | int | `-1` |
| `since` | string |  |
| `srcPath` | string |  |
| `whitespace` | string |  |
| `withComments` | boolean | `true` |

## GET /projects/{projectKey}/repos/{repositorySlug}/commits/{commitId}/diff/{path}

Retrieve the diff between two provided revisions. Note: This resource is currently not paged . The server will internally apply a hard cap to the streamed lines, and it is not possible to request subsequent pages if that cap is exceeded. In the event that the cap is reached, the diff will be cut short and one or more {@code truncated} flags will be set to {@code true} on the {@code "segments"}, {@code "hunks"} and {@code "diffs"} properties, as well as the top-level object, in the returned JSON response. The authenticated user must have REPO_READ permission for the specified repository to call this resource.

| query | type | default |
|---|---|---|
| `autoSrcPath` | boolean | `false` |
| `contextLines` | int | `-1` |
| `since` | string |  |
| `srcPath` | string |  |
| `whitespace` | string |  |
| `withComments` | boolean | `true` |

## DELETE /projects/{projectKey}/repos/{repositorySlug}/commits/{commitId}/watch

Remove the authenticated user as a watcher for the specified commit. The authenticated user must have REPO_READ permission for the repository containing the commit to call this resource.

No query parameters.

## POST /projects/{projectKey}/repos/{repositorySlug}/commits/{commitId}/watch

Add the authenticated user as a watcher for the specified commit. The authenticated user must have REPO_READ permission for the repository containing the commit to call this resource.

No query parameters.

## GET /projects/{projectKey}/repos/{repositorySlug}/compare/changes

Gets the file changes available in the {@code from} commit but not in the {@code to} commit. If either the {@code from} or {@code to} commit are not specified, they will be replaced by the default branch of their containing repository.

| query | type | default |
|---|---|---|
| `from` | string |  |
| `to` | string |  |
| `fromRepo` | string | `` |

## GET /projects/{projectKey}/repos/{repositorySlug}/compare/commits

Gets the commits accessible from the {@code from} commit but not in the {@code to} commit. If either the {@code from} or {@code to} commit are not specified, they will be replaced by the default branch of their containing repository.

| query | type | default |
|---|---|---|
| `from` | string |  |
| `to` | string |  |
| `fromRepo` | string | `` |

## GET /projects/{projectKey}/repos/{repositorySlug}/compare/diff{path}

Gets a diff of the changes available in the {@code from} commit but not in the {@code to} commit. If either the {@code from} or {@code to} commit are not specified, they will be replaced by the default branch of their containing repository.

| query | type | default |
|---|---|---|
| `from` | string |  |
| `to` | string |  |
| `fromRepo` | string | `` |
| `srcPath` | string |  |
| `contextLines` | int | `-1` |
| `whitespace` | string |  |

## GET /projects/{projectKey}/repos/{repositorySlug}/diff

Retrieve the diff for a specified file path between two provided revisions. Note: This resource is currently not paged . The server will internally apply a hard cap to the streamed lines, and it is not possible to request subsequent pages if that cap is exceeded. In the event that the cap is reached, the diff will be cut short and one or more truncated flags will be set to true on the segments, hunks and diffs substructures in the returned JSON response. The authenticated user must have REPO_READ permission for the specified repository to call this resource.

| query | type | default |
|---|---|---|
| `contextLines` | int | `-1` |
| `since` | string |  |
| `srcPath` | string |  |
| `until` | string |  |
| `whitespace` | string |  |

## GET /projects/{projectKey}/repos/{repositorySlug}/diff/{path}

Retrieve the diff for a specified file path between two provided revisions. Note: This resource is currently not paged . The server will internally apply a hard cap to the streamed lines, and it is not possible to request subsequent pages if that cap is exceeded. In the event that the cap is reached, the diff will be cut short and one or more truncated flags will be set to true on the segments, hunks and diffs substructures in the returned JSON response. The authenticated user must have REPO_READ permission for the specified repository to call this resource.

| query | type | default |
|---|---|---|
| `contextLines` | int | `-1` |
| `since` | string |  |
| `srcPath` | string |  |
| `until` | string |  |
| `whitespace` | string |  |

## GET /projects/{projectKey}/repos/{repositorySlug}/files

Retrieve a page of files from particular directory of a repository. The search is done recursively, so all files from any sub-directory of the specified directory will be returned. The authenticated user must have REPO_READ permission for the specified repository to call this resource.

| query | type | default |
|---|---|---|
| `at` | string |  |

## GET /projects/{projectKey}/repos/{repositorySlug}/files/{path}

Retrieve a page of files from particular directory of a repository. The search is done recursively, so all files from any sub-directory of the specified directory will be returned. The authenticated user must have REPO_READ permission for the specified repository to call this resource.

| query | type | default |
|---|---|---|
| `at` | string |  |

## GET /projects/{projectKey}/repos/{repositorySlug}/forks

Retrieve repositories which have been forked from this one. Unlike {@link #getRelatedRepositories(Repository, PageRequest) related repositories}, this only looks at a given repository's direct forks. If those forks have themselves been the origin of more forks, such "grandchildren" repositories will not be retrieved. Only repositories to which the authenticated user has REPO_READ permission will be included, even if other repositories have been forked from this one.

No query parameters.

## GET /projects/{projectKey}/repos/{repositorySlug}/last-modified

Streams files in the requested path with the last commit to modify each file. Commit modifications are traversed starting from the at commit or, if not specified, from the tip of the default branch. Unless the repository is public, the authenticated user must have REPO_READ access to call this resource.

| query | type | default |
|---|---|---|
| `at` | string |  |

## GET /projects/{projectKey}/repos/{repositorySlug}/last-modified/{path}

Streams files in the requested path with the last commit to modify each file. Commit modifications are traversed starting from the at commit or, if not specified, from the tip of the default branch. Unless the repository is public, the authenticated user must have REPO_READ access to call this resource.

| query | type | default |
|---|---|---|
| `at` | string |  |

## GET /projects/{projectKey}/repos/{repositorySlug}/participants

Retrieve a page of participant users for all the pull requests to or from the specified repository. Optionally clients can specify following filters.

| query | type | default |
|---|---|---|
| `direction` | string | `incoming` |
| `filter` | string |  |
| `role` | string |  |

## DELETE /projects/{projectKey}/repos/{repositorySlug}/permissions/groups

Revoke all permissions for the specified repository for a group. The authenticated user must have REPO_ADMIN permission for the specified repository or a higher project or global permission to call this resource. In addition, a user may not revoke a group's permissions if it will reduce their own permission level.

| query | type | default |
|---|---|---|
| `name` | string |  |

## GET /projects/{projectKey}/repos/{repositorySlug}/permissions/groups

Retrieve a page of groups that have been granted at least one permission for the specified repository. The authenticated user must have REPO_ADMIN permission for the specified repository or a higher project or global permission to call this resource.

| query | type | default |
|---|---|---|
| `filter` | string |  |

## PUT /projects/{projectKey}/repos/{repositorySlug}/permissions/groups

Promote or demote a group's permission level for the specified repository. Available repository permissions are: REPO_READ REPO_WRITE REPO_ADMIN See the Bitbucket Server documentation for a detailed explanation of what each permission entails. The authenticated user must have REPO_ADMIN permission for the specified repository or a higher project or global permission to call this resource. In addition, a user may not demote a group's permission level if their own permission level would be reduced as a result.

| query | type | default |
|---|---|---|
| `permission` | string |  |
| `name` | string |  |

## GET /projects/{projectKey}/repos/{repositorySlug}/permissions/groups/none

Retrieve a page of groups that have no granted permissions for the specified repository. The authenticated user must have REPO_ADMIN permission for the specified repository or a higher project or global permission to call this resource.

| query | type | default |
|---|---|---|
| `filter` | string |  |

## DELETE /projects/{projectKey}/repos/{repositorySlug}/permissions/users

Revoke all permissions for the specified repository for a user. The authenticated user must have REPO_ADMIN permission for the specified repository or a higher project or global permission to call this resource. In addition, a user may not revoke their own repository permissions if they do not have a higher project or global permission.

| query | type | default |
|---|---|---|
| `name` | string |  |

## GET /projects/{projectKey}/repos/{repositorySlug}/permissions/users

Retrieve a page of users that have been granted at least one permission for the specified repository. The authenticated user must have REPO_ADMIN permission for the specified repository or a higher project or global permission to call this resource.

| query | type | default |
|---|---|---|
| `filter` | string |  |

## PUT /projects/{projectKey}/repos/{repositorySlug}/permissions/users

Promote or demote a user's permission level for the specified repository. Available repository permissions are: REPO_READ REPO_WRITE REPO_ADMIN See the Bitbucket Server documentation for a detailed explanation of what each permission entails. The authenticated user must have REPO_ADMIN permission for the specified repository or a higher project or global permission to call this resource. In addition, a user may not reduce their own permission level unless they have a project or global permission that already implies that permission.

| query | type | default |
|---|---|---|
| `name` | string |  |
| `permission` | string |  |

## GET /projects/{projectKey}/repos/{repositorySlug}/permissions/users/none

Retrieve a page of licensed users that have no granted permissions for the specified repository. The authenticated user must have REPO_ADMIN permission for the specified repository or a higher project or global permission to call this resource.

| query | type | default |
|---|---|---|
| `filter` | string |  |

## GET /projects/{projectKey}/repos/{repositorySlug}/pull-requests

Retrieve a page of pull requests to or from the specified repository. The authenticated user must have REPO_READ permission for the specified repository to call this resource. Optionally clients can specify PR participant filters. Each filter has a mandatory {@code username.N} parameter, and the optional {@code role.N} and {@code approved.N} parameters. {@code username.N} - the "root" of a single participant filter, where "N" is a natural number starting from 1. This allows clients to specify multiple participant filters, by providing consecutive filters as {@code username.1}, {@code username.2} etc. Note that the filters numbering has to start with 1 and be continuous for all filters to be processed. The total allowed number of participant filters is 10 and all filters exceeding that limit will be dropped. {@code role.N}(optional) the role associated with {@code username.N}. This must be one of {@code AUTHOR}, {@code REVIEWER}, or{@code PARTICIPANT} {@code approved.N}(optional) the approved status associated with {@code username.N}. That is whether {@code username.N} has approved the PR. Either {@code true}, or {@code false}

| query | type | default |
|---|---|---|
| `direction` | string | `incoming` |
| `at` | string |  |
| `state` | string |  |
| `order` | string |  |
| `withAttributes` | boolean | `true` |
| `withProperties` | boolean | `true` |

## POST /projects/{projectKey}/repos/{repositorySlug}/pull-requests

Create a new pull request between two branches. The branches may be in the same repository, or different ones. When using different repositories, they must still be in the same {@link Repository#getHierarchyId() hierarchy}. The authenticated user must have REPO_READ permission for the "from" and "to"repositories to call this resource.

No query parameters.

## DELETE /projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}

Deletes a pull request. To call this resource, users must be authenticated and have permission to view the pull request. Additionally, they must: be the pull request author, if the system is configured to allow authors to delete their own pull requests (this is the default) OR have repository administrator permission for the repository the pull request is targeting A body containing the version of the pull request must be provided with this request. { "version": 1 }

No query parameters.

## GET /projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}

Retrieve a pull request. The authenticated user must have REPO_READ permission for the repository that this pull request targets to call this resource.

No query parameters.

## PUT /projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}

Update the title, description, reviewers or destination branch of an existing pull request. Note: the reviewers list may be updated using this resource. However the author and participants list may not. The authenticated user must either: be the author of the pull request and have the REPO_READ permission for the repository that this pull request targets; or have the REPO_WRITE permission for the repository that this pull request targets to call this resource.

No query parameters.

## GET /projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/activities

Retrieve a page of activity associated with a pull request. Activity items include comments, approvals, rescopes (i.e. adding and removing of commits), merges and more. Different types of activity items may be introduced in newer versions of Stash or by user installed plugins, so clients should be flexible enough to handle unexpected entity shapes in the returned page. The authenticated user must have REPO_READ permission for the repository that this pull request targets to call this resource.

| query | type | default |
|---|---|---|
| `fromId` | long |  |
| `fromType` | string |  |

## DELETE /projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/approve

Remove approval from a pull request as the current user. This does not remove the user as a participant. The authenticated user must have REPO_READ permission for the repository that this pull request targets to call this resource. Deprecated since 4.2 . Use /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/participants/{userSlug} instead

No query parameters.

## POST /projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/approve

Approve a pull request as the current user. Implicitly adds the user as a participant if they are not already. The authenticated user must have REPO_READ permission for the repository that this pull request targets to call this resource. Deprecated since 4.2 . Use /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/participants/{userSlug} instead

No query parameters.

## GET /projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/changes

Gets changes for the specified PullRequest. If the {@code changeScope} query parameter is set to {@code unreviewed}, the application will attempt to stream unreviewed changes based on the {@code lastReviewedCommit} of the current user, which are the changes between the {@code lastReviewedCommit} and the latest commit of the source branch. The current user is considered to not have any unreviewed changes for the pull request when the {@code lastReviewedCommit} is either {@code null} (everything is unreviewed, so all changes are streamed), equal to the latest commit of the source branch (everything is reviewed), or no longer on the source branch (the source branch has been rebased). In these cases, the application will fall back to streaming all changes (the default), which is the effective diff for the pull request. The type of changes streamed can be determined by the {@code changeScope} parameter included in the properties map of the response. Note: This resource is currently not paged . The server will return at most one page. The server will truncate the number of changes to either the request's page limit or an internal maximum, whichever is smaller. The start parameter of the page request is also ignored. The authenticated user must have REPO_READ permission for the repository that this pull request targets to call this resource.

| query | type | default |
|---|---|---|
| `changeScope` | string | `ALL` |
| `sinceId` | string |  |
| `untilId` | string |  |
| `withComments` | boolean | `true` |

## GET /projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/comments

Gets comments for the specified PullRequest. The authenticated user must have REPO_READ permission for the repository that this pull request targets to call this resource.

| query | type | default |
|---|---|---|
| `anchorState` | string | `ACTIVE` |
| `diffType` | string |  |
| `fromHash` | string |  |
| `path` | string |  |
| `toHash` | string |  |

## POST /projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/comments

Add a new comment. Comments can be added in a few places by setting different attributes: General pull request comment: { "text": "An insightful general comment on a pull request." } Reply to a comment: { "text": "A measured reply.", "parent": { "id": 1 } } General file comment: { "text": "An insightful general comment on a file.", "anchor": { "diffType": "RANGE", "fromHash": "6df3858eeb9a53a911cd17e66a9174d44ffb02cd", "path": "path/to/file", "srcPath": "path/to/file", "toHash": "04c7c5c931b9418ca7b66f51fe934d0bd9b2ba4b" } } File line comment: { "text": "A pithy comment on a particular line within a file.", "anchor": { "diffType": "COMMIT", "line": 1, "lineType": "CONTEXT", "fileType": "FROM", "fromHash": "6df3858eeb9a53a911cd17e66a9174d44ffb02cd", "path": "path/to/file", "srcPath": "path/to/file", "toHash": "04c7c5c931b9418ca7b66f51fe934d0bd9b2ba4b" } } For file and line comments, 'path' refers to the path of the file to which the comment should be applied and 'srcPath' refers to the path the that file used to have (only required for copies and moves). Also, fromHash and toHash refer to the sinceId / untilId (respectively) used to produce the diff on which the comment was added. Finally diffType refers to the type of diff the comment was added on. For backwards compatibility purposes if no diffType is provided and no fromHash/toHash pair is provided the diffType will be resolved to 'EFFECTIVE'. In any other cases the diffType is REQUIRED. For line comments, 'line' refers to the line in the diff that the comment should apply to. 'lineType' refers to the type of diff hunk, which can be: 'ADDED' - for an added line; 'REMOVED' - for a removed line; or 'CONTEXT' - for a line that was unmodified but is in the vicinity of the diff. 'fileType' refers to the file of the diff to which the anchor should be attached - which is of relevance when displaying the diff in a side-by-side way. Currently the supported values are: 'FROM' - the source file of the diff 'TO' - the destination file of the diff If the current user is not a participant the user is added as a watcher of the pull request. The authenticated user must have REPO_READ permission for the repository that this pull request targets to call this resource.

No query parameters.

## DELETE /projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/comments/{commentId}

Delete a pull request comment. Anyone can delete their own comment. Only users with REPO_ADMIN and above may delete comments created by other users. The authenticated user must have REPO_READ permission for the repository that this pull request targets to call this resource.

| query | type | default |
|---|---|---|
| `version` | int | `-1` |

## GET /projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/comments/{commentId}

Retrieves a pull request comment. The authenticated user must have REPO_READ permission for the repository that this pull request targets to call this resource.

No query parameters.

## PUT /projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/comments/{commentId}

Update the text of a comment. Only the user who created a comment may update it. Note: the supplied supplied JSON object must contain a version that must match the server's version of the comment or the update will fail. To determine the current version of the comment, the comment should be fetched from the server prior to the update. Look for the 'version' attribute in the returned JSON structure. The authenticated user must have REPO_READ permission for the repository that this pull request targets to call this resource.

No query parameters.

## GET /projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/commits

Retrieve commits for the specified pull request. The authenticated user must have REPO_READ permission for the repository that this pull request targets to call this resource.

| query | type | default |
|---|---|---|
| `withCounts` | boolean |  |

## POST /projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/decline

Decline a pull request. The authenticated user must have REPO_READ permission for the repository that this pull request targets to call this resource.

| query | type | default |
|---|---|---|
| `version` | int | `-1` |

## GET /projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/diff

Streams a diff within a pull request. If the specified file has been copied, moved or renamed, the srcPath must also be specified to produce the correct diff. Note: This RESTful endpoint is currently not paged . The server will internally apply a hard cap to the streamed lines, and it is not possible to request subsequent pages if that cap is exceeded. The authenticated user must have REPO_READ permission for the repository that this pull request targets to call this resource.

| query | type | default |
|---|---|---|
| `contextLines` | int | `-1` |
| `diffType` | string | `EFFECTIVE` |
| `sinceId` | string |  |
| `srcPath` | string |  |
| `untilId` | string |  |
| `whitespace` | string |  |
| `withComments` | boolean | `true` |

## GET /projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/diff/{path}

Streams a diff within a pull request. If the specified file has been copied, moved or renamed, the srcPath must also be specified to produce the correct diff. Note: This RESTful endpoint is currently not paged . The server will internally apply a hard cap to the streamed lines, and it is not possible to request subsequent pages if that cap is exceeded. The authenticated user must have REPO_READ permission for the repository that this pull request targets to call this resource.

| query | type | default |
|---|---|---|
| `contextLines` | int | `-1` |
| `diffType` | string | `EFFECTIVE` |
| `sinceId` | string |  |
| `srcPath` | string |  |
| `untilId` | string |  |
| `whitespace` | string |  |
| `withComments` | boolean | `true` |

## GET /projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/merge

Test whether a pull request can be merged. A pull request may not be merged if: there are conflicts that need to be manually resolved before merging; and/or one or more merge checks have vetoed the merge. The authenticated user must have REPO_READ permission for the repository that this pull request targets to call this resource.

No query parameters.

## POST /projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/merge

Merge the specified pull request. The authenticated user must have REPO_WRITE permission for the repository that this pull request targets to call this resource.

| query | type | default |
|---|---|---|
| `version` | int | `-1` |

## DELETE /projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/participants

Unassigns a participant from the REVIEWER role they may have been given in a pull request. If the participant has no explicit role this method has no effect. Afterwards, the user will still remain a participant in the pull request but their role will be reduced to PARTICIPANT. This is because once made a participant of a pull request, a user will forever remain a participant. Only their role may be altered. The authenticated user must have REPO_WRITE permission for the repository that this pull request targets to call this resource. Deprecated since 4.2 . Use /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/participants/{userSlug} instead.

| query | type | default |
|---|---|---|
| `username` | string |  |

## GET /projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/participants

Retrieves a page of the participants for a given pull request. The authenticated user must have REPO_READ permission for the repository that this pull request targets to call this resource.

No query parameters.

## POST /projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/participants

Assigns a participant to an explicit role in pull request. Currently only the REVIEWER role may be assigned. If the user is not yet a participant in the pull request, they are made one and assigned the supplied role. If the user is already a participant in the pull request, their previous role is replaced with the supplied role unless they are already assigned the AUTHOR role which cannot be changed and will result in a Bad Request (400) response code. The authenticated user must have REPO_WRITE permission for the repository that this pull request targets to call this resource.

No query parameters.

## DELETE /projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/participants/{userSlug}

Unassigns a participant from the REVIEWER role they may have been given in a pull request. If the participant has no explicit role this method has no effect. Afterwards, the user will still remain a participant in the pull request but their role will be reduced to PARTICIPANT. This is because once made a participant of a pull request, a user will forever remain a participant. Only their role may be altered. The authenticated user must have REPO_WRITE permission for the repository that this pull request targets to call this resource. Deprecated since 4.2 . Use /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/participants/{userSlug} instead.

No query parameters.

## PUT /projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/participants/{userSlug}

Change the current user's status for a pull request. Implicitly adds the user as a participant if they are not already. If the current user is the author, this method will fail. The possible values for {@code status} are UNAPPROVED , NEEDS_WORK , or APPROVED . If the new {@code status} is NEEDS_WORK or APPROVED then the {@code lastReviewedCommit} for the participant will be updated to the latest commit of the source branch of the pull request. The authenticated user must have REPO_READ permission for the repository that this pull request targets to call this resource.

No query parameters.

## POST /projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/reopen

Re-open a declined pull request. The authenticated user must have REPO_READ permission for the repository that this pull request targets to call this resource.

| query | type | default |
|---|---|---|
| `version` | int | `-1` |

## GET /projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/tasks

Retrieve the tasks associated with a pull request.

No query parameters.

## GET /projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/tasks/count

Retrieve the total number of {@link TaskState#OPEN open} and {@link TaskState#RESOLVED resolved} tasks associated with a pull request.

No query parameters.

## DELETE /projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/watch

Remove the authenticated user as a watcher for the specified pull request. The authenticated user must have REPO_READ permission for the repository that this pull request targets to call this resource.

No query parameters.

## POST /projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/watch

Add the authenticated user as a watcher for the specified pull request. The authenticated user must have REPO_READ permission for the repository that this pull request targets to call this resource.

No query parameters.

## GET /projects/{projectKey}/repos/{repositorySlug}/raw

Retrieve the raw content for a file path at a specified revision. The authenticated user must have REPO_READ permission for the specified repository to call this resource.

| query | type | default |
|---|---|---|
| `at` | string |  |
| `markup` | string |  |
| `hardwrap` | boolean |  |
| `htmlEscape` | boolean |  |

## GET /projects/{projectKey}/repos/{repositorySlug}/raw/{path}

Retrieve the raw content for a file path at a specified revision. The authenticated user must have REPO_READ permission for the specified repository to call this resource.

| query | type | default |
|---|---|---|
| `at` | string |  |
| `markup` | string |  |
| `hardwrap` | boolean |  |
| `htmlEscape` | boolean |  |

## POST /projects/{projectKey}/repos/{repositorySlug}/recreate

If a create or fork operation fails, calling this method will clean up the broken repository and try again. The repository must be in an INITIALISATION_FAILED state. The authenticated user must have PROJECT_ADMIN permission for the specified project to call this resource.

No query parameters.

## GET /projects/{projectKey}/repos/{repositorySlug}/related

Retrieve repositories which are related to this one. Related repositories are from the same {@link Repository#getHierarchyId() hierarchy} as this repository. Only repositories to which the authenticated user has REPO_READ permission will be included, even if more repositories are part of this repository's hierarchy.

No query parameters.

## GET /projects/{projectKey}/repos/{repositorySlug}/settings/hooks

Retrieve a page of repository hooks for this repository. The authenticated user must have REPO_READ permission for the specified repository to call this resource.

| query | type | default |
|---|---|---|
| `type` | string | `` |

## DELETE /projects/{projectKey}/repos/{repositorySlug}/settings/hooks/{hookKey}

Delete repository hook configuration for the supplied hookKey and repositorySlug The authenticated user must have REPO_ADMIN permission for the specified repository to call this resource.

No query parameters.

## GET /projects/{projectKey}/repos/{repositorySlug}/settings/hooks/{hookKey}

Retrieve a repository hook for this repository. The authenticated user must have REPO_READ permission for the specified repository to call this resource.

No query parameters.

## DELETE /projects/{projectKey}/repos/{repositorySlug}/settings/hooks/{hookKey}/enabled

Disable a repository hook for this repository. The authenticated user must have REPO_ADMIN permission for the specified repository to call this resource.

No query parameters.

## PUT /projects/{projectKey}/repos/{repositorySlug}/settings/hooks/{hookKey}/enabled

Enable a repository hook for this repository and optionally apply new configuration. The authenticated user must have REPO_ADMIN permission for the specified repository to call this resource. A JSON document may be provided to use as the settings for the hook. These structure and validity of the document is decided by the plugin providing the hook.

No query parameters.

## GET /projects/{projectKey}/repos/{repositorySlug}/settings/hooks/{hookKey}/settings

Retrieve the settings for a repository hook for this repository. The authenticated user must have REPO_READ permission for the specified repository to call this resource.

No query parameters.

## PUT /projects/{projectKey}/repos/{repositorySlug}/settings/hooks/{hookKey}/settings

Modify the settings for a repository hook for this repository. The service will reject any settings which are too large, the current limit is 32KB once serialized. The authenticated user must have REPO_ADMIN permission for the specified repository to call this resource. A JSON document can be provided to use as the settings for the hook. These structure and validity of the document is decided by the plugin providing the hook.

No query parameters.

## GET /projects/{projectKey}/repos/{repositorySlug}/settings/pull-requests

Retrieve the pull request settings for the context repository. The authenticated user must have REPO_READ permission for the context repository to call this resource. This resource will call all RestFragments that are registered with the key bitbucket.repository.settings.pullRequests . If any fragment fails validations by returning a non-empty Map of errors, then no fragments will execute. The property keys for the settings that are bundled with the application are mergeConfig - the merge strategy configuration for pull requests requiredApprovers - (Deprecated, please use com.atlassian.bitbucket.server.bundled-hooks.requiredApproversMergeHook instead) the number of approvals required on a pull request for it to be mergeable, or 0 if the merge check is disabled com.atlassian.bitbucket.server.bundled-hooks.requiredApproversMergeHook - the merge check configuration for required approvers requiredAllApprovers - whether or not all approvers must approve a pull request for it to be mergeable requiredAllTasksComplete - whether or not all tasks on a pull request need to be completed for it to be mergeable requiredSuccessfulBuilds - (Deprecated, please use com.atlassian.bitbucket.server.bitbucket-build.requiredBuildsMergeCheck instead) the number of successful builds on a pull request for it to be mergeable, or 0 if the merge check is disabled com.atlassian.bitbucket.server.bitbucket-build.requiredBuildsMergeCheck - the merge check configuration for required builds

No query parameters.

## POST /projects/{projectKey}/repos/{repositorySlug}/settings/pull-requests

Update the pull request settings for the context repository. The authenticated user must have REPO_ADMIN permission for the context repository to call this resource. This resource will call all RestFragments that are registered with the key bitbucket.repository.settings.pullRequests . If any fragment fails validations by returning a non-empty Map of errors, then no fragments will execute. Only the settings that should be updated need to be included in the request. The property keys for the settings that are bundled with the application are mergeConfig - the merge strategy configuration for pull requests requiredApprovers - (Deprecated, please use com.atlassian.bitbucket.server.bundled-hooks.requiredApproversMergeHook instead) the number of approvals required on a pull request for it to be mergeable, or 0 to disable the merge check com.atlassian.bitbucket.server.bundled-hooks.requiredApproversMergeHook - a json map containing the keys 'enabled' (a boolean to enable or disable this merge check) and 'count' (an integer to set the number of required approvals) requiredAllApprovers - whether or not all approvers must approve a pull request for it to be mergeable requiredAllTasksComplete - whether or not all tasks on a pull request need to be completed for it to be mergeable requiredSuccessfulBuilds - (Deprecated, please use com.atlassian.bitbucket.server.bitbucket-build.requiredBuildsMergeCheck instead) the number of successful builds on a pull request for it to be mergeable, or 0 to disable the merge check com.atlassian.bitbucket.server.bitbucket-build.requiredBuildsMergeCheck - a json map containing the keys 'enabled' (a boolean to enable or disable this merge check) and 'count' (an integer to set the number of required builds) Merge strategy configuration deletion: An explicitly set pull request merge strategy configuration can be deleted by POSTing a document with an empty "mergeConfig" attribute. i.e: { "mergeConfig": { } } Upon completion of this request, the effective configuration will be: The configuration set for this repository's SCM type as set at the project level, if present, otherwise the configuration set for this repository's SCM type as set at the instance level, if present, otherwise the default configuration for this repository's SCM type

No query parameters.

## GET /projects/{projectKey}/repos/{repositorySlug}/tags

Retrieve the tags matching the supplied filterText param. The authenticated user must have REPO_READ permission for the context repository to call this resource.

| query | type | default |
|---|---|---|
| `filterText` | string |  |
| `orderBy` | string |  |

## POST /projects/{projectKey}/repos/{repositorySlug}/tags

Creates a tag using the information provided in the {@link RestCreateTagRequest request} The authenticated user must have REPO_WRITE permission for the context repository to call this resource.

No query parameters.

## GET /projects/{projectKey}/repos/{repositorySlug}/tags/{name}

Retrieve a tag in the specified repository. The authenticated user must have REPO_READ permission for the context repository to call this resource.

No query parameters.

## DELETE /projects/{projectKey}/repos/{repositorySlug}/watch

Remove the authenticated user as a watcher for the specified repository. The authenticated user must have REPO_READ permission for the repository to call this resource.

No query parameters.

## POST /projects/{projectKey}/repos/{repositorySlug}/watch

Add the authenticated user as a watcher for the specified repository. The authenticated user must have REPO_READ permission for the repository to call this resource.

No query parameters.

## GET /projects/{projectKey}/repos/{repositorySlug}/webhooks

Find webhooks in this repository. The authenticated user must have REPO_ADMIN permission for the specified repository to call this resource.

| query | type | default |
|---|---|---|
| `event` | string |  |
| `statistics` | boolean | `false` |

## POST /projects/{projectKey}/repos/{repositorySlug}/webhooks

Create a webhook for the repository specified via the URL. The authenticated user must have REPO_ADMIN permission for the specified repository to call this resource.

No query parameters.

## POST /projects/{projectKey}/repos/{repositorySlug}/webhooks/test

Test connectivity to a specific endpoint. The authenticated user must have REPO_ADMIN permission for the specified repository to call this resource.

| query | type | default |
|---|---|---|
| `url` | string |  |

## DELETE /projects/{projectKey}/repos/{repositorySlug}/webhooks/{webhookId}

Delete a webhook for the repository specified via the URL. The authenticated user must have REPO_ADMIN permission for the specified repository to call this resource.

No query parameters.

## GET /projects/{projectKey}/repos/{repositorySlug}/webhooks/{webhookId}

Get a webhook by id. The authenticated user must have REPO_ADMIN permission for the specified repository to call this resource.

| query | type | default |
|---|---|---|
| `statistics` | boolean | `false` |

## PUT /projects/{projectKey}/repos/{repositorySlug}/webhooks/{webhookId}

Update an existing webhook. The authenticated user must have REPO_ADMIN permission for the specified repository to call this resource.

No query parameters.

## GET /projects/{projectKey}/repos/{repositorySlug}/webhooks/{webhookId}/latest

Get the latest invocations for a specific webhook. The authenticated user must have REPO_ADMIN permission for the specified repository to call this resource.

| query | type | default |
|---|---|---|
| `event` | string |  |
| `outcome` | string |  |

## GET /projects/{projectKey}/repos/{repositorySlug}/webhooks/{webhookId}/statistics

Get the statistics for a specific webhook. The authenticated user must have REPO_ADMIN permission for the specified repository to call this resource.

| query | type | default |
|---|---|---|
| `event` | string |  |

## GET /projects/{projectKey}/repos/{repositorySlug}/webhooks/{webhookId}/statistics/summary

Get the statistics summary for a specific webhook. The authenticated user must have REPO_ADMIN permission for the specified repository to call this resource.

No query parameters.
