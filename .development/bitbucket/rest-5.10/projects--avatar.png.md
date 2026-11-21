<!-- Bitbucket Server 5.10.0 REST API — resource group: projects--avatar.png (1 endpoints) -->

## /rest/api/1.0/projects/{projectKey}/avatar.png

###### Methods

#### GET

###### /rest/api/1.0/projects/{projectKey}/avatar.png?s

Retrieve the avatar for the project matching the supplied **projectKey**.

The authenticated user must have **PROJECT_VIEW** permission for the specified project to call this resource.

###### request query parameters

<table>
<colgroup>
<col style="width: 33%" />
<col style="width: 33%" />
<col style="width: 33%" />
</colgroup>
<thead>
<tr>
<th>parameter</th>
<th>value</th>
<th>description</th>
</tr>
</thead>
<tbody>
<tr>
<td>s</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#int">int</a>
Default: <code>0</code></td>
<td>The desired size of the image. The server will return an image as close as possible to the specified size.</td>
</tr>
</tbody>
</table>

*Example response representations:*

-

  200 - image/png

  The avatar of the project matching the supplied **projectKey**.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the project.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified project does not exist.

#### POST

Update the avatar for the project matching the supplied **projectKey**.

This resource accepts POST multipart form data, containing a single image in a form-field named 'avatar'.

There are configurable server limits on both the dimensions (1024x1024 pixels by default) and uploaded file size (1MB by default). Several different image formats are supported, but **PNG** and **JPEG** are preferred due to the file size limit.

This resource has Cross-Site Request Forgery (XSRF) protection. To allow the request to pass the XSRF check the caller needs to send an `X-Atlassian-Token` HTTP header with the value `no-check`.

An example [curl](http://curl.haxx.se/) request to upload an image name 'avatar.png' would be:

 curl -X POST -u username:password -H "X-Atlassian-Token: no-check" http://example.com/rest/api/1.0/projects/STASH/avatar.png -F avatar=@avatar.png
 

The authenticated user must have **PROJECT_ADMIN** permission for the specified project to call this resource.

*Example response representations:*

-

  201

  The avatar was uploaded successfully.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to update the project.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified project does not exist.
