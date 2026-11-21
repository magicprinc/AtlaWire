<!-- Bitbucket Server 5.10.0 REST API — section: 01-authentication -->

## Authentication

Any authentication that works against Bitbucket will work against the REST API. **The preferred authentication methods are HTTP Basic (when using SSL) and OAuth**. Other supported methods include: HTTP Cookies and Trusted Applications.

You can find OAuth code samples in several programming languages at [bitbucket.org/atlassian_tutorial/atlassian-oauth-examples](https://bitbucket.org/atlassian_tutorial/atlassian-oauth-examples).

The log-in page uses cookie-based authentication, so if you are using Bitbucket in a browser you can call REST from JavaScript on the page and rely on the authentication that the browser has established.

## Errors & Validation

If a request fails due to client error, the resource will return an HTTP response code in the 40x range. These can be broadly categorised into:

<table>
<colgroup>
<col style="width: 50%" />
<col style="width: 50%" />
</colgroup>
<thead>
<tr>
<th>HTTP Code</th>
<th>Description</th>
</tr>
</thead>
<tbody>
<tr>
<td>400 (Bad Request)</td>
<td>One or more of the required parameters or attributes:
<ul>
<li>were missing from the request;</li>
<li>incorrectly formatted; or</li>
<li>inappropriate in the given context.</li>
</ul></td>
</tr>
<tr>
<td>401 (Unauthorized)</td>
<td>Either:
<ul>
<li>Authentication is required but was not attempted.</li>
<li>Authentication was attempted but failed.</li>
<li>Authentication was successful but the authenticated user does not have the requisite permission for the resource.</li>
</ul>
See the individual resource documentation for details of required permissions.</td>
</tr>
<tr>
<td>403 (Forbidden)</td>
<td>Actions are usually "forbidden" if they involve breaching the licensed user limit of the server, or degrading the authenticated user's permission level. See the individual resource documentation for more details.</td>
</tr>
<tr>
<td>404 (Not Found)</td>
<td>The entity you are attempting to access, or the project or repository containing it, does not exist.</td>
</tr>
<tr>
<td>405 (Method Not Allowed)</td>
<td>The request HTTP method is not appropriate for the targeted resource. For example an HTTP GET to a resource that only accepts an HTTP POST will result in a 405.</td>
</tr>
<tr>
<td>409 (Conflict)</td>
<td>The attempted update failed due to some conflict with an existing resource. For example:
<ul>
<li>Creating a project with a key that already exists</li>
<li>Merging an out-of-date pull request</li>
<li>Deleting a comment that has replies</li>
<li>etc.</li>
</ul>
See the individual resource documentation for more details.</td>
</tr>
<tr>
<td>415 (Unsupported Media Type)</td>
<td>The request entity has a <code>Content-Type</code> that the server does not support. Almost all of the Bitbucket REST API accepts <code>application/json</code> format, but check the individual resource documentation for more details. Additionally, double-check that you are setting the <code>Content-Type</code> header correctly on your request (e.g. using <code>-H "Content-Type: application/json"</code> in cURL).</td>
</tr>
</tbody>
</table>

For **400** HTTP codes the response will typically contain one or more validation error messages, for example:

    {
        "errors": \[
            {
                "context": "name",
                "message": "The name should be between 1 and 255 characters.",
                "exceptionName": null
            },
            {
                "context": "email",
                "message": "The email should be a valid email address.",
                "exceptionName": null
            }
        \]
    }
    

The `context` attribute indicates which parameter or request entity attribute failed validation. Note that the `context` may be null.

For **401**, **403**, **404** and **409** HTTP codes, the response will contain one or more descriptive error messages:

    {
        "errors": \[
            {
                "context": null,
                "message": "A detailed error message.",
                "exceptionName": null
            }
        \]
    }
    

A **500** (Server Error) HTTP code indicates an incorrect resource url or an unexpected server error. Double-check the URL you are trying to access, then report the issue to your server administrator or [Atlassian Support](https://support.atlassian.com/) if problems persist.
