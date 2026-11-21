<!-- Bitbucket Server 5.10.0 REST API — resource group: projects--archive (1 endpoints) -->

## /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/archive

###### Methods

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/archive?at&filename&format&path&prefix

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Streams an archive of the repository's contents at the requested commit. If no `at=` commit is requested, an archive of the default branch is streamed.

The `filename=` query parameter may be used to specify the exact filename to include in the `"Content-Disposition"` header. If an explicit filename is not provided, one will be automatically generated based on what is being archived. Its format depends on the `at=` value:

- No `at=` commit: `<slug>-<default-branch-name>@<commit>.<format>`; e.g. example-master@43c2f8a0fe8.zip
- `at=sha`: `<slug>-<at>.<format>`; e.g. example-09bcbb00100cfbb5310fb6834a1d5ce6cac253e9.tar.gz
- `at=branchOrTag`: `<slug>-<branchOrTag>@<commit>.<format>`; e.g. example-feature@bbb225f16e1.tar
  - If the branch or tag is qualified (e.g. `refs/heads/master`, the short name (`master`) will be included in the filename
  - If the branch or tag's *short name* includes slashes (e.g. `release/4.6`), they will be converted to hyphens in the filename (`release-4.5`)

Archives may be requested in the following formats by adding the `format=` query parameter:

- `zip`: A zip file using standard compression (Default)
- `tar`: An uncompressed tarball
- `tar.gz` or `tgz`: A GZip-compressed tarball

The contents of the archive may be filtered by using the `path=` query parameter to specify paths to include. `path=` may be specified multiple times to include multiple paths.

The `prefix=` query parameter may be used to define a directory (or multiple directories) where the archive's contents should be placed. If the prefix does not end with `/`, one will be added automatically. The prefix is *always* treated as a directory; it is not possible to use it to prepend characters to the entries in the archive.

Archives of public repositories may be streamed by any authenticated or anonymous user. Streaming archives for non-public repositories requires an *authenticated user* with at least **REPO_READ** permission.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **at** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the commit to stream an archive of; if not supplied, an archive of the default branch is streamed |
| **filename** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | a filename to include the "Content-Disposition" header |
| **format** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the format to stream the archive in; must be one of: zip, tar, tar.gz or tgz |
| **path** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | paths to include in the streamed archive; may be repeated to include multiple paths |
| **prefix** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | a prefix to apply to all entries in the streamed archive; if the supplied prefix does not end with a trailing `/`, one will be added automatically |

*Example response representations:*

-

  200 - application/octet-stream; application/x-tar (archive)

  An archive or the requested commit, in zip, tar or gzipped-tar format.

-

  400 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The requested `format` is not supported.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the repository.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The repository does not exist or does not contain the `at` commit.
