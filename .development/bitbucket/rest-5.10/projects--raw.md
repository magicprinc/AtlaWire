<!-- Bitbucket Server 5.10.0 REST API — resource group: projects--raw (2 endpoints) -->

## /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/raw

###### Methods

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/raw?at&markup&hardwrap&htmlEscape

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Retrieve the raw content for a file path at a specified revision.

The authenticated user must have **REPO_READ** permission for the specified repository to call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **at** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the commit ID or ref to retrieve the content for. |
| **markup** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | if present or `"true"`, triggers the raw content to be markup-rendered and returned as HTML; otherwise, if not specified, or any value other than `"true"`, the content is streamed without markup |
| **hardwrap** | *[boolean](http://www.w3.org/TR/xmlschema-2/#boolean)* | (Optional) Whether the markup implementation should convert newlines to breaks. If not specified, {@link MarkupService} will use the value of the `markup.render.hardwrap` property, which is `true` by default |
| **htmlEscape** | *[boolean](http://www.w3.org/TR/xmlschema-2/#boolean)* | (Optional) true if HTML should be escaped in the input markup, false otherwise. If not specified, {@link MarkupService} will use the value of the `markup.render.html.escape` property, which is `true` by default |

*Example response representations:*

-

  \*/\*

## /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/raw/{path:.\*}

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **path** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the file path to retrieve content from |

###### Methods

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/raw/{path:.\*}?at&markup&hardwrap&htmlEscape

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.

Retrieve the raw content for a file path at a specified revision.

The authenticated user must have **REPO_READ** permission for the specified repository to call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **at** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the commit ID or ref to retrieve the content for. |
| **markup** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | if present or `"true"`, triggers the raw content to be markup-rendered and returned as HTML; otherwise, if not specified, or any value other than `"true"`, the content is streamed without markup |
| **hardwrap** | *[boolean](http://www.w3.org/TR/xmlschema-2/#boolean)* | (Optional) Whether the markup implementation should convert newlines to breaks. If not specified, {@link MarkupService} will use the value of the `markup.render.hardwrap` property, which is `true` by default |
| **htmlEscape** | *[boolean](http://www.w3.org/TR/xmlschema-2/#boolean)* | (Optional) true if HTML should be escaped in the input markup, false otherwise. If not specified, {@link MarkupService} will use the value of the `markup.render.html.escape` property, which is `true` by default |

*Example response representations:*

-

  \*/\*
