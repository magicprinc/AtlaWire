<div id="header" class="header" role="banner">

<div class="aui-header-inner">

<div class="aui-header-primary">

# <span class="aui-header-logo-device" style="background-image: url(../../../assets/images/atlassian-developers-logo.svg);"></span>

</div>

</div>

</div>

<div class="container">

# REST Resources Provided By: Bitbucket Server - REST

This is the reference document for the Atlassian Bitbucket REST API. The REST API is for developers who want to:

- integrate Bitbucket with other applications;
- create scripts that interact with Bitbucket; or
- develop plugins that enhance the Bitbucket UI, using REST to interact with the backend.

You can read more about developing Bitbucket plugins in the [Bitbucket Developer Documentation](https://developer.atlassian.com/server/bitbucket/).

## Getting started

Because the REST API is based on open standards, you can use any web development language or command line tool capable of generating an HTTP request to access the API. See the [developer documentation](https://developer.atlassian.com/server/bitbucket/reference/rest-api/) for a basic usage example.

If you're already working with the [Atlassian SDK](https://developer.atlassian.com/server/framework/atlassian-sdk/), the [REST API Browser](https://developer.atlassian.com/server/framework/atlassian-sdk/using-the-rest-api-browser/) is a great tool for exploring and experimenting with the Bitbucket REST API.

## <span id="StructureoftheRESTURIs"></span>Structure of the REST URIs

Bitbucket's REST APIs provide access to resources (data entities) via URI paths. To use a REST API, your application will make an HTTP request and parse the response. The Bitbucket REST API uses JSON as its communication format, and the standard HTTP methods like GET, PUT, POST and DELETE. URIs for Bitbucket's REST API resource have the following structure:

\
    http://host:port/context/rest/api-name/api-version/path/to/resource\

For example, the following URI would retrieve a page of the latest commits to the **jira** repository in the **Jira** project on <https://stash.atlassian.com>.

\
    https://stash.atlassian.com/rest/api/1.0/projects/JIRA/repos/jira/commits\

See the API descriptions below for a full list of available resources.

Alternatively we also publish a list of resources in [WADL](http://en.wikipedia.org/wiki/Web_Application_Description_Language) format. It is available [here](bitbucket-rest.wadl).

## Paged APIs

Bitbucket uses paging to conserve server resources and limit response size for resources that return potentially large collections of items. A request to a paged API will result in a `values` array wrapped in a JSON object with some paging metadata, like this:

\
    {\
        "size": 3,\
        "limit": 3,\
        "isLastPage": false,\
        "values": \[\
            { /\* result 0 \*/ },\
            { /\* result 1 \*/ },\
            { /\* result 2 \*/ }\
        \],\
        "start": 0,\
        "filter": null,\
        "nextPageStart": 3\
    }\

Clients can use the `limit` and `start` query parameters to retrieve the desired number of results.

The `limit` parameter indicates how many results to return per page. Most APIs default to returning `25` if the limit is left unspecified. This number can be increased, but note that a resource-specific hard limit will apply. These hard limits can be configured by server administrators, so it's always best practice to check the `limit` attribute on the response to see what limit has been applied. The request to get a larger page should look like this:

\
    http://host:port/context/rest/api-name/api-version/path/to/resource?limit={desired size of page}\

For example:

\
    https://stash.atlassian.com/rest/api/1.0/projects/JIRA/repos/jira/commits?limit=1000\

The `start` parameter indicates which item should be used as the first item in the page of results. All paged responses contain an `isLastPage` attribute indicating whether another page of items exists.

**Important:** If more than one page exists (i.e. the response contains `"isLastPage": false`), the response object will also contain a `nextPageStart` attribute which ***must*** be used by the client as the `start` parameter on the next request. Identifiers of adjacent objects in a page may not be contiguous, so the start of the next page is *not* necessarily the start of the last page plus the last page's size. A client should always use `nextPageStart` to avoid unexpected results from a paged API. The request to get a subsequent page should look like this:

\
    http://host:port/context/rest/api-name/api-version/path/to/resource?start={nextPageStart from previous response}\

For example:

\
    https://stash.atlassian.com/rest/api/1.0/projects/JIRA/repos/jira/commits?start=25\

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

\
    {\
        "errors": \[\
            {\
                "context": "name",\
                "message": "The name should be between 1 and 255 characters.",\
                "exceptionName": null\
            },\
            {\
                "context": "email",\
                "message": "The email should be a valid email address.",\
                "exceptionName": null\
            }\
        \]\
    }\
    

The `context` attribute indicates which parameter or request entity attribute failed validation. Note that the `context` may be null.

For **401**, **403**, **404** and **409** HTTP codes, the response will contain one or more descriptive error messages:

\
    {\
        "errors": \[\
            {\
                "context": null,\
                "message": "A detailed error message.",\
                "exceptionName": null\
            }\
        \]\
    }\
    

A **500** (Server Error) HTTP code indicates an incorrect resource url or an unexpected server error. Double-check the URL you are trying to access, then report the issue to your server administrator or [Atlassian Support](https://support.atlassian.com/) if problems persist.

## Personal Repositories

Bitbucket allows users to manage their own repositories, called personal repositories. These are repositories associated with the user and to which they always have REPO_ADMIN permission.

Accessing personal repositories via REST is achieved through the normal project-centric REST URLs using the user's slug prefixed by tilde as the project key. E.g. to list personal repositories for a user with slug "johnsmith" you would make a GET to:

http://example.com/rest/api/1.0/projects/~johnsmith/repos

In addition to this, Bitbucket allows access to these repositories through an alternate set of user-centric REST URLs beginning with:

http://example.com/rest/api/1.0/users/~{userSlug}/repos

E.g. to list the forks of the repository with slug "nodejs" in the personal project of user with slug "johnsmith" using the regular REST URL you would make a GET to:

http://example.com/rest/api/1.0/projects/~johnsmith/repos/nodejs/forks

Using the alternate URL, you would make a GET to:

http://example.com/rest/api/1.0/users/johnsmith/repos/nodejs/forks

## Index

Provides REST resources

- [Resources](#resources)
  - <div id="api/1.0/admin">

    </div>

     

  - [http://example.com/rest/api/1.0/admin](#idm532026142528)
    - <div id="api/1.0/admin/groups">

      </div>

    - [http://example.com/rest/api/1.0/admin/groups](#idm532026140912) \[[GET](#idm532026140272), [POST](#idm532026132944), [DELETE](#idm532026122064)\]
      <div id="api/1.0/admin/groups/add-user">

      </div>

    - [http://example.com/rest/api/1.0/admin/groups/add-user](#idm532064578848) \[[POST](#idm532064576992)\]
      <div id="api/1.0/admin/groups/add-users">

      </div>

    - [http://example.com/rest/api/1.0/admin/groups/add-users](#idm532027401936) \[[POST](#idm532027401440)\]
      <div id="api/1.0/admin/groups/more-members">

      </div>

    - [http://example.com/rest/api/1.0/admin/groups/more-members](#idm532027388832) \[[GET](#idm532027388464)\]
      <div id="api/1.0/admin/groups/more-non-members">

      </div>

    - [http://example.com/rest/api/1.0/admin/groups/more-non-members](#idm532027380496) \[[GET](#idm532027378592)\]
      <div id="api/1.0/admin/groups/remove-user">

      </div>

    - [http://example.com/rest/api/1.0/admin/groups/remove-user](#idm532061981920) \[[POST](#idm532061972672)\]
      <div id="api/1.0/admin/users">

      </div>

    - [http://example.com/rest/api/1.0/admin/users](#idm532026105008) \[[GET](#idm532026104352), [PUT](#idm532026097696), [POST](#idm532026084976), [DELETE](#idm532026064704)\]
      <div id="api/1.0/admin/users/add-group">

      </div>

    - [http://example.com/rest/api/1.0/admin/users/add-group](#idm532063441504) \[[POST](#idm532063441248)\]
      <div id="api/1.0/admin/users/add-groups">

      </div>

    - [http://example.com/rest/api/1.0/admin/users/add-groups](#idm532061983296) \[[POST](#idm532061983008)\]
      <div id="api/1.0/admin/users/captcha">

      </div>

    - [http://example.com/rest/api/1.0/admin/users/captcha](#idm532064589152) \[[DELETE](#idm532064588656)\]
      <div id="api/1.0/admin/users/credentials">

      </div>

    - [http://example.com/rest/api/1.0/admin/users/credentials](#idm532025490784) \[[PUT](#idm532025489664)\]
      <div id="api/1.0/admin/users/more-members">

      </div>

    - [http://example.com/rest/api/1.0/admin/users/more-members](#idm532027370176) \[[GET](#idm532027369184)\]
      <div id="api/1.0/admin/users/more-non-members">

      </div>

    - [http://example.com/rest/api/1.0/admin/users/more-non-members](#idm532027361472) \[[GET](#idm532027360800)\]
      <div id="api/1.0/admin/users/remove-group">

      </div>

    - [http://example.com/rest/api/1.0/admin/users/remove-group](#idm532063436400) \[[POST](#idm532063436144)\]
      <div id="api/1.0/admin/users/rename">

      </div>

    - [http://example.com/rest/api/1.0/admin/users/rename](#idm532027412768) \[[POST](#idm532027413936)\]

    <div id="api/1.0/admin/cluster">

    </div>

     

  - [http://example.com/rest/api/1.0/admin/cluster](#idm532026187008) \[[GET](#idm532026185216)\]
    <div id="api/1.0/admin/license">

    </div>

     

  - [http://example.com/rest/api/1.0/admin/license](#idm532025970944) \[[GET](#idm532025970192), [POST](#idm532025961888)\]
    <div id="api/1.0/admin/mail-server">

    </div>

     

  - [http://example.com/rest/api/1.0/admin/mail-server](#idm532023689168) \[[DELETE](#idm532023687232), [GET](#idm532023683088), [PUT](#idm532023675872)\]
    - <div id="api/1.0/admin/mail-server/sender-address">

      </div>

    - [http://example.com/rest/api/1.0/admin/mail-server/sender-address](#idm532023665808) \[[DELETE](#idm532023665552), [GET](#idm532023661088), [PUT](#idm532023654720)\]

    <div id="api/1.0/admin/permissions">

    </div>

     

  - [http://example.com/rest/api/1.0/admin/permissions](#idm532026348384)
    - <div id="api/1.0/admin/permissions/groups">

      </div>

    - [http://example.com/rest/api/1.0/admin/permissions/groups](#idm532026311408) \[[PUT](#idm532026310912), [GET](#idm532026294496), [DELETE](#idm532026287728)\]
      <div id="api/1.0/admin/permissions/groups/none">

      </div>

    - [http://example.com/rest/api/1.0/admin/permissions/groups/none](#idm532026269120) \[[GET](#idm532026267168)\]
      <div id="api/1.0/admin/permissions/users">

      </div>

    - [http://example.com/rest/api/1.0/admin/permissions/users](#idm532026347376) \[[PUT](#idm532026346992), [GET](#idm532026330240), [DELETE](#idm532026323344)\]
      <div id="api/1.0/admin/permissions/users/none">

      </div>

    - [http://example.com/rest/api/1.0/admin/permissions/users/none](#idm532026275728) \[[GET](#idm532026275232)\]

    <div id="api/1.0/admin/pull-requests/{scmId}">

    </div>

     

  - [http://example.com/rest/api/1.0/admin/pull-requests/{scmId}](#idm532025993376) \[[POST](#idm532025991824), [GET](#idm532025979888)\]
    <div id="api/1.0/application-properties">

    </div>

     

  - [http://example.com/rest/api/1.0/application-properties](#idm532026378624) \[[GET](#idm532026377424)\]
    <div id="api/1.0/dashboard">

    </div>

     

  - [http://example.com/rest/api/1.0/dashboard](#idm532061756624)
    - <div id="api/1.0/dashboard/pull-request-suggestions">

      </div>

    - [http://example.com/rest/api/1.0/dashboard/pull-request-suggestions](#idm532061755120) \[[GET](#idm532061754864)\]
      <div id="api/1.0/dashboard/pull-requests">

      </div>

    - [http://example.com/rest/api/1.0/dashboard/pull-requests](#idm532061745200) \[[GET](#idm532061743296)\]

    <div id="api/1.0/groups">

    </div>

     

  - [http://example.com/rest/api/1.0/groups](#idm532025402208) \[[GET](#idm532025403200)\]
    <div id="api/1.0/hooks">

    </div>

     

  - [http://example.com/rest/api/1.0/hooks](#idm532025356240)
    - <div id="api/1.0/hooks/{hookKey}/avatar">

      </div>

    - [http://example.com/rest/api/1.0/hooks/{hookKey}/avatar](#idm532025356112) \[[GET](#idm532025353744)\]

    <div id="api/1.0/inbox">

    </div>

     

  - [http://example.com/rest/api/1.0/inbox](#idm532026148208)
    - <div id="api/1.0/inbox/pull-requests">

      </div>

    - [http://example.com/rest/api/1.0/inbox/pull-requests](#idm532026146592) \[[GET](#idm532026146912)\]
      <div id="api/1.0/inbox/pull-requests/count">

      </div>

    - [http://example.com/rest/api/1.0/inbox/pull-requests/count](#idm532026149280) \[[GET](#idm532026147840)\]

    <div id="api/1.0/logs">

    </div>

     

  - [http://example.com/rest/api/1.0/logs](#idm532027255840)
    - <div id="api/1.0/logs/logger/{loggerName}">

      </div>

    - [http://example.com/rest/api/1.0/logs/logger/{loggerName}](#idm532027256864) \[[GET](#idm532027254144)\]
      <div id="api/1.0/logs/logger/{loggerName}/{levelName}">

      </div>

    - [http://example.com/rest/api/1.0/logs/logger/{loggerName}/{levelName}](#idm532025472384) \[[PUT](#idm532063422448)\]
      <div id="api/1.0/logs/rootLogger">

      </div>

    - [http://example.com/rest/api/1.0/logs/rootLogger](#idm532063415184) \[[GET](#idm532063415056)\]
      <div id="api/1.0/logs/rootLogger/{levelName}">

      </div>

    - [http://example.com/rest/api/1.0/logs/rootLogger/{levelName}](#idm532063408880) \[[PUT](#idm532027247872)\]

    <div id="api/1.0/markup">

    </div>

     

  - [http://example.com/rest/api/1.0/markup](#idm532063356496)
    - <div id="api/1.0/markup/preview">

      </div>

    - [http://example.com/rest/api/1.0/markup/preview](#idm532063357696) \[[POST](#idm532063356096)\]

    <div id="api/1.0/profile/recent/repos">

    </div>

     

  - [http://example.com/rest/api/1.0/profile/recent/repos](#idm532023761296) \[[GET](#idm532023760096)\]
    <div id="api/1.0/projects">

    </div>

     

  - [http://example.com/rest/api/1.0/projects](#idm532026446992) \[[GET](#idm532026448016), [POST](#idm532026440192)\]
    - <div id="api/1.0/projects/{projectKey}">

      </div>

    - [http://example.com/rest/api/1.0/projects/{projectKey}](#idm532026426032) \[[GET](#idm532026426656), [DELETE](#idm532026418784), [PUT](#idm532026408272)\]
      <div id="api/1.0/projects/{projectKey}/avatar.png">

      </div>

    - [http://example.com/rest/api/1.0/projects/{projectKey}/avatar.png](#idm532026393088) \[[GET](#idm532026392592), [POST](#idm532026384208)\]

    <div id="api/1.0/projects/{projectKey}/permissions">

    </div>

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/permissions](#idm532027240944)
    - <div id="api/1.0/projects/{projectKey}/permissions/groups">

      </div>

    - [http://example.com/rest/api/1.0/projects/{projectKey}/permissions/groups](#idm532027222704) \[[PUT](#idm532063398752), [GET](#idm532025460784), [DELETE](#idm532025454368)\]
      <div id="api/1.0/projects/{projectKey}/permissions/groups/none">

      </div>

    - [http://example.com/rest/api/1.0/projects/{projectKey}/permissions/groups/none](#idm532027217712) \[[GET](#idm532027217120)\]
      <div id="api/1.0/projects/{projectKey}/permissions/users">

      </div>

    - [http://example.com/rest/api/1.0/projects/{projectKey}/permissions/users](#idm532027240592) \[[PUT](#idm532027240336), [GET](#idm532063408256), [DELETE](#idm532063401824)\]
      <div id="api/1.0/projects/{projectKey}/permissions/users/none">

      </div>

    - [http://example.com/rest/api/1.0/projects/{projectKey}/permissions/users/none](#idm532025453984) \[[GET](#idm532025453408)\]
      <div id="api/1.0/projects/{projectKey}/permissions/{permission}/all">

      </div>

    - [http://example.com/rest/api/1.0/projects/{projectKey}/permissions/{permission}/all](#idm532027230128) \[[POST](#idm532025470032), [GET](#idm532025463088)\]

    <div id="api/1.0/projects/{projectKey}/repos">

    </div>

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/repos](#idm532026524400) \[[POST](#idm532026523120), [GET](#idm532026511200)\]
    - <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}">

      </div>

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}](#idm532025663472) \[[GET](#idm532025661856), [PUT](#idm532025659792), [DELETE](#idm532025636784), [POST](#idm532025629360)\]
      <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/forks">

      </div>

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/forks](#idm532025616608) \[[GET](#idm532025615120)\]
      <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/recreate">

      </div>

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/recreate](#idm532025599632) \[[POST](#idm532025599376)\]
      <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/related">

      </div>

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/related](#idm532025606624) \[[GET](#idm532025607664)\]

    <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/archive">

    </div>

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/archive](#idm532025516960) \[[GET](#idm532025515040)\]
    <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/branches">

    </div>

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/branches](#idm532065002640) \[[POST](#idm532065001520), [GET](#idm532061935136)\]
    - <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/branches/default">

      </div>

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/branches/default](#idm532023779664) \[[GET](#idm532023778192), [PUT](#idm532023769856)\]

    <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/browse">

    </div>

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/browse](#idm532027352368) \[[GET](#idm532027351696)\]
    - <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/browse/{path:.*}">

      </div>

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/browse/{path:.\*}](#idm532027334656) \[[GET](#idm532027333712), [PUT](#idm532027316624)\]

    <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/changes">

    </div>

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/changes](#idm532025564880) \[[GET](#idm532025563888)\]
    <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/commits">

    </div>

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/commits](#idm532027292144) \[[GET](#idm532027291648)\]
    - <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/commits/{commitId}">

      </div>

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/commits/{commitId}](#idm532027270128) \[[GET](#idm532027268832)\]

    <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/commits/{commitId}/changes">

    </div>

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/commits/{commitId}/changes](#idm532061686512) \[[GET](#idm532061685168)\]
    <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/commits/{commitId}/comments">

    </div>

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/commits/{commitId}/comments](#idm532025948608) \[[GET](#idm532025946144), [POST](#idm532025933648)\]
    - <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/commits/{commitId}/comments/{commentId}">

      </div>

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/commits/{commitId}/comments/{commentId}](#idm532023804640) \[[GET](#idm532023802176), [DELETE](#idm532023793904), [PUT](#idm532065336464)\]

    <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/commits/{commitId}/diff">

    </div>

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/commits/{commitId}/diff](#idm532025426128) \[[GET](#idm532025423488)\]
    - <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/commits/{commitId}/diff/{path:.*}">

      </div>

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/commits/{commitId}/diff/{path:.\*}](#idm532027211472) \[[GET](#idm532025422208)\]

    <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/commits/{commitId}/watch">

    </div>

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/commits/{commitId}/watch](#idm532025446832) \[[POST](#idm532025445344), [DELETE](#idm532063383360)\]
    <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/compare">

    </div>

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/compare](#idm532025395568)
    - <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/compare/changes">

      </div>

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/compare/changes](#idm532025366384) \[[GET](#idm532025367952)\]
      <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/compare/commits">

      </div>

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/compare/commits](#idm532025378224) \[[GET](#idm532025377232)\]
      <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/compare/diff{path:.*}">

      </div>

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/compare/diff{path:.\*}](#idm532025393744) \[[GET](#idm532025392560)\]

    <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/diff">

    </div>

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/diff](#idm532061671952) \[[GET](#idm532061670480)\]
    - <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/diff/{path:.*}">

      </div>

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/diff/{path:.\*}](#idm532061652656) \[[GET](#idm532061651328)\]

    <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/files">

    </div>

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/files](#idm532026552512) \[[GET](#idm532026552256)\]
    - <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/files/{path:.*}">

      </div>

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/files/{path:.\*}](#idm532026540192) \[[GET](#idm532026536976)\]

    <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/last-modified">

    </div>

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/last-modified](#idm532026375296) \[[GET](#idm532026373776)\]
    - <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/last-modified/{path:.*}">

      </div>

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/last-modified/{path:.\*}](#idm532026362224) \[[GET](#idm532026360144)\]

    <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/participants">

    </div>

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/participants](#idm532025440688) \[[GET](#idm532025440064)\]
    <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/permissions">

    </div>

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/permissions](#idm532063342624)
    - <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/permissions/groups">

      </div>

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/permissions/groups](#idm532063341600) \[[GET](#idm532063341344), [PUT](#idm532064564656), [DELETE](#idm532064549280)\]
      <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/permissions/groups/none">

      </div>

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/permissions/groups/none](#idm532064540000) \[[GET](#idm532064538528)\]
      <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/permissions/users">

      </div>

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/permissions/users](#idm532064529856) \[[GET](#idm532064528016), [PUT](#idm532064518176), [DELETE](#idm532064504416)\]
      <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/permissions/users/none">

      </div>

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/permissions/users/none](#idm532064494400) \[[GET](#idm532064492928)\]

    <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests">

    </div>

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests](#idm532061891456) \[[POST](#idm532061892512), [GET](#idm532061876064)\]
    - <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}">

      </div>

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}](#idm532061857808) \[[GET](#idm532061855088), [PUT](#idm532061854112), [DELETE](#idm532061832352)\]
      <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/activities">

      </div>

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/activities](#idm532061786272) \[[GET](#idm532061783952)\]
      <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/decline">

      </div>

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/decline](#idm532061798880) \[[POST](#idm532061796368)\]
      <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/merge">

      </div>

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/merge](#idm532061823200) \[[POST](#idm532061821248), [GET](#idm532061809648)\]
      <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/reopen">

      </div>

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/reopen](#idm532061770544) \[[POST](#idm532061768496)\]

    <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/approve">

    </div>

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/approve](#idm532025588176) \[[POST](#idm532025586624), [DELETE](#idm532025575328)\]
    <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/changes">

    </div>

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/changes](#idm532026613024) \[[GET](#idm532064704784)\]
    <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/comments">

    </div>

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/comments](#idm532026059760) \[[GET](#idm532026059312), [POST](#idm532026042848)\]
    - <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/comments/{commentId}">

      </div>

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/comments/{commentId}](#idm532026031408) \[[GET](#idm532026028800), [DELETE](#idm532026019568), [PUT](#idm532026009472)\]

    <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/commits">

    </div>

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/commits](#idm532026197296) \[[GET](#idm532026196144)\]
    <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/diff">

    </div>

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/diff](#idm532026613424) \[[GET](#idm532026596192)\]
    - <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/diff/{path:.*}">

      </div>

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/diff/{path:.\*}](#idm532026575552) \[[GET](#idm532026572640)\]

    <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/participants">

    </div>

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/participants](#idm532061633216) \[[GET](#idm532061631888), [POST](#idm532061623920), [DELETE](#idm532023725632)\]
    - <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/participants/{userSlug}">

      </div>

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/participants/{userSlug}](#idm532023715744) \[[DELETE](#idm532023712864), [PUT](#idm532023710608)\]

    <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/tasks">

    </div>

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/tasks](#idm532026179296) \[[GET](#idm532026178704)\]
    - <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/tasks/count">

      </div>

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/tasks/count](#idm532026170752) \[[GET](#idm532026171504)\]

    <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/watch">

    </div>

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/watch](#idm532026246416) \[[POST](#idm532026245824), [DELETE](#idm532026239952)\]
    <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/raw">

    </div>

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/raw](#idm532027165280) \[[GET](#idm532027163792)\]
    - <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/raw/{path:.*}">

      </div>

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/raw/{path:.\*}](#idm532024748720) \[[GET](#idm532024747920)\]

    <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/settings">

    </div>

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/settings](#idm532025537536)
    - <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/settings/pull-requests">

      </div>

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/settings/pull-requests](#idm532025538608) \[[POST](#idm532025537024), [GET](#idm532025525312)\]

    <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/settings/hooks">

    </div>

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/settings/hooks](#idm532023749840) \[[GET](#idm532023749344)\]
    - <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/settings/hooks/{hookKey}">

      </div>

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/settings/hooks/{hookKey}](#idm532061908496) \[[GET](#idm532061906896), [DELETE](#idm532061899904)\]
      <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/settings/hooks/{hookKey}/enabled">

      </div>

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/settings/hooks/{hookKey}/enabled](#idm532061929904) \[[PUT](#idm532061928944), [DELETE](#idm532061916048)\]
      <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/settings/hooks/{hookKey}/settings">

      </div>

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/settings/hooks/{hookKey}/settings](#idm532023739856) \[[GET](#idm532023738048), [PUT](#idm532023730240)\]

    <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/tags">

    </div>

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/tags](#idm532023645760) \[[GET](#idm532023644240), [POST](#idm532063377104)\]
    - <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/tags/{name:.*}">

      </div>

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/tags/{name:.\*}](#idm532063370592) \[[GET](#idm532063365616)\]

    <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/watch">

    </div>

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/watch](#idm532026260384) \[[POST](#idm532026259184), [DELETE](#idm532026252912)\]
    <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/webhooks">

    </div>

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/webhooks](#idm532063490592) \[[POST](#idm532063481456), [GET](#idm532063470320)\]
    - <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/webhooks/test">

      </div>

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/webhooks/test](#idm532026458112) \[[POST](#idm532026456640)\]
      <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/webhooks/{webhookId}">

      </div>

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/webhooks/{webhookId}](#idm532063458736) \[[DELETE](#idm532063456720), [GET](#idm532063451424), [PUT](#idm532026501696)\]
      <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/webhooks/{webhookId}/latest">

      </div>

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/webhooks/{webhookId}/latest](#idm532026493680) \[[GET](#idm532026490672)\]
      <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/webhooks/{webhookId}/statistics">

      </div>

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/webhooks/{webhookId}/statistics](#idm532026480752) \[[GET](#idm532026477744)\]
      <div id="api/1.0/projects/{projectKey}/repos/{repositorySlug}/webhooks/{webhookId}/statistics/summary">

      </div>

    - [http://example.com/rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/webhooks/{webhookId}/statistics/summary](#idm532026468928) \[[GET](#idm532026465920)\]

    <div id="api/1.0/projects/{projectKey}/settings">

    </div>

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/settings](#idm532027304992)
    - <div id="api/1.0/projects/{projectKey}/settings/pull-requests/{scmId}">

      </div>

    - [http://example.com/rest/api/1.0/projects/{projectKey}/settings/pull-requests/{scmId}](#idm532027303696) \[[POST](#idm532027302512), [GET](#idm532063430336)\]

    <div id="api/1.0/projects/{projectKey}/settings/hooks">

    </div>

     

  - [http://example.com/rest/api/1.0/projects/{projectKey}/settings/hooks](#idm532023631920) \[[GET](#idm532023631520)\]
    - <div id="api/1.0/projects/{projectKey}/settings/hooks/{hookKey}">

      </div>

    - [http://example.com/rest/api/1.0/projects/{projectKey}/settings/hooks/{hookKey}](#idm532027174304) \[[GET](#idm532027172704)\]
      <div id="api/1.0/projects/{projectKey}/settings/hooks/{hookKey}/enabled">

      </div>

    - [http://example.com/rest/api/1.0/projects/{projectKey}/settings/hooks/{hookKey}/enabled](#idm532027196656) \[[PUT](#idm532027194784), [DELETE](#idm532027192720)\]
      <div id="api/1.0/projects/{projectKey}/settings/hooks/{hookKey}/settings">

      </div>

    - [http://example.com/rest/api/1.0/projects/{projectKey}/settings/hooks/{hookKey}/settings](#idm532023621120) \[[GET](#idm532023619520), [PUT](#idm532023618720)\]

    <div id="api/1.0/repos">

    </div>

     

  - [http://example.com/rest/api/1.0/repos](#idm532026162096) \[[GET](#idm532026161600)\]
    <div id="api/1.0/tasks">

    </div>

     

  - [http://example.com/rest/api/1.0/tasks](#idm532061728560) \[[POST](#idm532061726752)\]
    - <div id="api/1.0/tasks/{taskId}">

      </div>

    - [http://example.com/rest/api/1.0/tasks/{taskId}](#idm532061716704) \[[GET](#idm532061715168), [DELETE](#idm532061708640), [PUT](#idm532061700144)\]

    <div id="api/1.0/users">

    </div>

     

  - [http://example.com/rest/api/1.0/users](#idm532026233456) \[[GET](#idm532026232256), [PUT](#idm532026224512)\]
    - <div id="api/1.0/users/credentials">

      </div>

    - [http://example.com/rest/api/1.0/users/credentials](#idm532025501440) \[[PUT](#idm532025496368)\]
      <div id="api/1.0/users/{userSlug}">

      </div>

    - [http://example.com/rest/api/1.0/users/{userSlug}](#idm532026214112) \[[GET](#idm532026213616)\]
      <div id="api/1.0/users/{userSlug}/avatar.png">

      </div>

    - [http://example.com/rest/api/1.0/users/{userSlug}/avatar.png](#idm532026205984) \[[DELETE](#idm532026204992), [POST](#idm532025502816)\]

    <div id="api/1.0/users/{userSlug}/settings">

    </div>

     

  - [http://example.com/rest/api/1.0/users/{userSlug}/settings](#idm532025550848) \[[GET](#idm532025549392), [POST](#idm532025548688)\]

## Resources

Rest resource for retrieving, creating and deleting users or groups

<div class="resource">

### /rest/api/1.0/admin/groups

###### Methods

<div class="methods">

<div class="method">

#### GET

###### /rest/api/1.0/admin/groups<span class="optional">?filter</span>

*This is a [paged API](#paging-params)*.\
\
Retrieve a page of groups.

The authenticated user must have **LICENSED_USER** permission or higher to call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **filter** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | if specified only group names containing the supplied string will be returned |

*Example response representations:*

- <div>

  200 - application/json ([page](#paging-params)) \[<a href="#" onclick="toggle(&#39;idm532026138528&#39;); return false;"><em><span id="link-idm532026138528">expand</span></em></a>\]

  </div>

  <div id="idm532026138528" class="toggle">

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"name":"group-a","deletable":true}],"start":0}

  A page of groups.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026137040&#39;); return false;"><em><span id="link-idm532026137040">expand</span></em></a>\]

  </div>

  <div id="idm532026137040" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user is not a licensed user.

  <div class="representation">

  </div>

  </div>

</div>

<div class="method">

#### POST

###### /rest/api/1.0/admin/groups<span class="optional">?name</span>

Create a new group.

The authenticated user must have **ADMIN** permission or higher to call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **name** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | Name of the group. |

*Example response representations:*

- <div>

  200 - application/json (restDetailedGroup) \[<a href="#" onclick="toggle(&#39;idm532026130240&#39;); return false;"><em><span id="link-idm532026130240">expand</span></em></a>\]

  </div>

  <div id="idm532026130240" class="toggle">

  ###### Example

      {"name":"group-a","deletable":true}

  The newly created group.

  <div class="representation">

  </div>

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026128080&#39;); return false;"><em><span id="link-idm532026128080">expand</span></em></a>\]

  </div>

  <div id="idm532026128080" class="toggle">

  ###### Example

      {"errors":[{"context":"field_a","message":"A detailed validation error message for field_a.","exceptionName":null},{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The request was malformed.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026125328&#39;); return false;"><em><span id="link-idm532026125328">expand</span></em></a>\]

  </div>

  <div id="idm532026125328" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user is not an administrator.

  <div class="representation">

  </div>

  </div>

- <div>

  409 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026124480&#39;); return false;"><em><span id="link-idm532026124480">expand</span></em></a>\]

  </div>

  <div id="idm532026124480" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  A group with this name already exists.

  <div class="representation">

  </div>

  </div>

</div>

<div class="method">

#### DELETE

###### /rest/api/1.0/admin/groups<span class="optional">?name</span>

Deletes the specified group, removing them from the system. This also removes any permissions that may have been granted to the group.

A user may not delete the last group that is granting them administrative permissions, or a group with greater permissions than themselves.

The authenticated user must have the **ADMIN** permission to call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **name** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the name identifying the group to delete |

*Example response representations:*

- <div>

  200 - application/json (detailedGroup) \[<a href="#" onclick="toggle(&#39;idm532026118288&#39;); return false;"><em><span id="link-idm532026118288">expand</span></em></a>\]

  </div>

  <div id="idm532026118288" class="toggle">

  ###### Example

      {"name":"group-a","deletable":true}

  The deleted group.

  <div class="representation">

  </div>

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026115552&#39;); return false;"><em><span id="link-idm532026115552">expand</span></em></a>\]

  </div>

  <div id="idm532026115552" class="toggle">

  ###### Example

      {"errors":[{"context":"field_a","message":"A detailed validation error message for field_a.","exceptionName":null},{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The request was malformed.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026114352&#39;); return false;"><em><span id="link-idm532026114352">expand</span></em></a>\]

  </div>

  <div id="idm532026114352" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The authenticated user does not have the **ADMIN** permission.

  <div class="representation">

  </div>

  </div>

- <div>

  403 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026110864&#39;); return false;"><em><span id="link-idm532026110864">expand</span></em></a>\]

  </div>

  <div id="idm532026110864" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The action was disallowed as the authenticated user has a lower permission level than the group being deleted.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026109664&#39;); return false;"><em><span id="link-idm532026109664">expand</span></em></a>\]

  </div>

  <div id="idm532026109664" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified group does not exist.

  <div class="representation">

  </div>

  </div>

- <div>

  409 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026106288&#39;); return false;"><em><span id="link-idm532026106288">expand</span></em></a>\]

  </div>

  <div id="idm532026106288" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The action was disallowed as it would lower the authenticated user's permission level.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/admin/users

###### Methods

<div class="methods">

<div class="method">

#### GET

###### /rest/api/1.0/admin/users<span class="optional">?filter</span>

*This is a [paged API](#paging-params)*.\
\
Retrieve a page of users.

The authenticated user must have the **LICENSED_USER** permission to call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **filter** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | if specified only users with usernames, display name or email addresses containing the supplied string will be returned |

*Example response representations:*

- <div>

  200 - application/json ([page](#paging-params)) \[<a href="#" onclick="toggle(&#39;idm532026102400&#39;); return false;"><em><span id="link-idm532026102400">expand</span></em></a>\]

  </div>

  <div id="idm532026102400" class="toggle">

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL","directoryName":"Bitbucket Internal Directory","deletable":true,"lastAuthenticationTimestamp":1368145580548,"mutableDetails":true,"mutableGroups":true}],"start":0}

  A page of users.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026101424&#39;); return false;"><em><span id="link-idm532026101424">expand</span></em></a>\]

  </div>

  <div id="idm532026101424" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user is not a licensed user.

  <div class="representation">

  </div>

  </div>

</div>

<div class="method">

#### PUT

Update a user's details.

The authenticated user must have the **ADMIN** permission to call this resource.

*Example request representations:*

- <div>

  application/json \[<a href="#" onclick="toggle(&#39;idm532026095072&#39;); return false;"><em><span id="link-idm532026095072">expand</span></em></a>\]

  </div>

  <div id="idm532026095072" class="toggle">

  ###### Example

      {"name":"jcitizen","displayName":"Jane Citizen","email":"jane@example.com"}

  </div>

*Example response representations:*

- <div>

  200 - application/json (detailedUser) \[<a href="#" onclick="toggle(&#39;idm532026093488&#39;); return false;"><em><span id="link-idm532026093488">expand</span></em></a>\]

  </div>

  <div id="idm532026093488" class="toggle">

  ###### Example

      {"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL","directoryName":"Bitbucket Internal Directory","deletable":true,"lastAuthenticationTimestamp":1368145580548,"mutableDetails":true,"mutableGroups":true}

  The updated user.

  <div class="representation">

  </div>

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026091424&#39;); return false;"><em><span id="link-idm532026091424">expand</span></em></a>\]

  </div>

  <div id="idm532026091424" class="toggle">

  ###### Example

      {"errors":[{"context":"field_a","message":"A detailed validation error message for field_a.","exceptionName":null},{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The request was malformed.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026088928&#39;); return false;"><em><span id="link-idm532026088928">expand</span></em></a>\]

  </div>

  <div id="idm532026088928" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The authenticated user does not have the **ADMIN** permission or has a lower permission level than the user being deleted.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026086960&#39;); return false;"><em><span id="link-idm532026086960">expand</span></em></a>\]

  </div>

  <div id="idm532026086960" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified user does not exist.

  <div class="representation">

  </div>

  </div>

</div>

<div class="method">

#### POST

###### /rest/api/1.0/admin/users<span class="optional">?name</span><span class="optional">&password</span><span class="optional">&displayName</span><span class="optional">&emailAddress</span><span class="optional">&addToDefaultGroup</span><span class="optional">&notify</span>

Creates a new user from the assembled query parameters.

The default group can be used to control initial permissions for new users, such as granting users the ability to login or providing read access to certain projects or repositories. If the user is not added to the default group, they may not be able to login after their account is created until explicit permissions are configured.

The authenticated user must have the **ADMIN** permission to call this resource.

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
<td><p><strong>name</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p></td>
<td><p>the username for the new user</p></td>
</tr>
<tr>
<td><p><strong>password</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p></td>
<td><p>the password for the new user</p></td>
</tr>
<tr>
<td><p><strong>displayName</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p></td>
<td><p>the display name for the new user</p></td>
</tr>
<tr>
<td><p><strong>emailAddress</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p></td>
<td><p>the e-mail address for the new user</p></td>
</tr>
<tr>
<td><p><strong>addToDefaultGroup</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#boolean">boolean</a></em></p>
<p>Default: <code>true</code></p></td>
<td><p><code>true</code> to add the user to the default group, which can be used to grant them a set of initial permissions; otherwise, <code>false</code> to not add them to a group</p></td>
</tr>
<tr>
<td><p><strong>notify</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p></td>
<td><p>if present and not <code>false</code> instead of requiring a password, the create user will be notified via email their account has been created and requires a password to be reset. This option can only be used if a mail server has been configured</p></td>
</tr>
</tbody>
</table>

*Example response representations:*

- <div>

  204 \[<a href="#" onclick="toggle(&#39;idm532026069952&#39;); return false;"><em><span id="link-idm532026069952">expand</span></em></a>\]

  </div>

  <div id="idm532026069952" class="toggle">

  The user was successfully created.

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026074912&#39;); return false;"><em><span id="link-idm532026074912">expand</span></em></a>\]

  </div>

  <div id="idm532026074912" class="toggle">

  ###### Example

      {"errors":[{"context":"field_a","message":"A detailed validation error message for field_a.","exceptionName":null},{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The request was malformed.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026074784&#39;); return false;"><em><span id="link-idm532026074784">expand</span></em></a>\]

  </div>

  <div id="idm532026074784" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The authenticated user is not an administrator.

  <div class="representation">

  </div>

  </div>

- <div>

  403 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026068624&#39;); return false;"><em><span id="link-idm532026068624">expand</span></em></a>\]

  </div>

  <div id="idm532026068624" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  Adding the user to the default group would exceed the server's license limit.

  <div class="representation">

  </div>

  </div>

- <div>

  409 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026066304&#39;); return false;"><em><span id="link-idm532026066304">expand</span></em></a>\]

  </div>

  <div id="idm532026066304" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  Another user with the same name already exists.

  <div class="representation">

  </div>

  </div>

</div>

<div class="method">

#### DELETE

###### /rest/api/1.0/admin/users<span class="optional">?name</span>

Deletes the specified user, removing them from the system. This also removes any permissions that may have been granted to the user.

A user may not delete themselves, and a user with **ADMIN** permissions may not delete a user with **SYS_ADMIN**permissions.

The authenticated user must have the **ADMIN** permission to call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **name** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the username identifying the user to delete |

*Example response representations:*

- <div>

  200 - application/json (detailedUser) \[<a href="#" onclick="toggle(&#39;idm532064703600&#39;); return false;"><em><span id="link-idm532064703600">expand</span></em></a>\]

  </div>

  <div id="idm532064703600" class="toggle">

  ###### Example

      {"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL","directoryName":"Bitbucket Internal Directory","deletable":true,"lastAuthenticationTimestamp":1368145580548,"mutableDetails":true,"mutableGroups":true}

  The deleted user.

  <div class="representation">

  </div>

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532064597728&#39;); return false;"><em><span id="link-idm532064597728">expand</span></em></a>\]

  </div>

  <div id="idm532064597728" class="toggle">

  ###### Example

      {"errors":[{"context":"field_a","message":"A detailed validation error message for field_a.","exceptionName":null},{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The request was malformed.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532064595344&#39;); return false;"><em><span id="link-idm532064595344">expand</span></em></a>\]

  </div>

  <div id="idm532064595344" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The authenticated user does not have the **ADMIN** permission.

  <div class="representation">

  </div>

  </div>

- <div>

  403 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532064594640&#39;); return false;"><em><span id="link-idm532064594640">expand</span></em></a>\]

  </div>

  <div id="idm532064594640" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The action was disallowed as the authenticated user has a lower permission level than the user being deleted.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532027422912&#39;); return false;"><em><span id="link-idm532027422912">expand</span></em></a>\]

  </div>

  <div id="idm532027422912" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified user does not exist.

  <div class="representation">

  </div>

  </div>

- <div>

  409 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025493312&#39;); return false;"><em><span id="link-idm532025493312">expand</span></em></a>\]

  </div>

  <div id="idm532025493312" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The action was disallowed as a user can not delete themselves.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/admin/users/credentials

###### Methods

<div class="methods">

<div class="method">

#### PUT

Update a user's password.

The authenticated user must have the **ADMIN** permission to call this resource, and may not update the password of a user with greater permissions than themselves.

*Example request representations:*

- <div>

  application/json \[<a href="#" onclick="toggle(&#39;idm532025488112&#39;); return false;"><em><span id="link-idm532025488112">expand</span></em></a>\]

  </div>

  <div id="idm532025488112" class="toggle">

  ###### Example

      {"password":"secret","passwordConfirm":"secret","name":"jcitizen"}

  </div>

*Example response representations:*

- <div>

  204 \[<a href="#" onclick="toggle(&#39;idm532027415888&#39;); return false;"><em><span id="link-idm532027415888">expand</span></em></a>\]

  </div>

  <div id="idm532027415888" class="toggle">

  The user's password was successfully updated.

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532027422000&#39;); return false;"><em><span id="link-idm532027422000">expand</span></em></a>\]

  </div>

  <div id="idm532027422000" class="toggle">

  ###### Example

      {"errors":[{"context":"field_a","message":"A detailed validation error message for field_a.","exceptionName":null},{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The request was malformed.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532027418864&#39;); return false;"><em><span id="link-idm532027418864">expand</span></em></a>\]

  </div>

  <div id="idm532027418864" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The authenticated user does not have the **ADMIN** permission or has a lower permission level than the user being deleted.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532027415024&#39;); return false;"><em><span id="link-idm532027415024">expand</span></em></a>\]

  </div>

  <div id="idm532027415024" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified user does not exist.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/admin/users/rename

###### Methods

<div class="methods">

<div class="method">

#### POST

Rename a user.

The authenticated user must have the **ADMIN** permission to call this resource.

*Example request representations:*

- <div>

  application/json \[<a href="#" onclick="toggle(&#39;idm532025485872&#39;); return false;"><em><span id="link-idm532025485872">expand</span></em></a>\]

  </div>

  <div id="idm532025485872" class="toggle">

  ###### Example

      {"name":"jcitizen","newName":"jcitizen-new"}

  </div>

*Example response representations:*

- <div>

  200 - application/json (detailedUser) \[<a href="#" onclick="toggle(&#39;idm532025484608&#39;); return false;"><em><span id="link-idm532025484608">expand</span></em></a>\]

  </div>

  <div id="idm532025484608" class="toggle">

  ###### Example

      {"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL","directoryName":"Bitbucket Internal Directory","deletable":true,"lastAuthenticationTimestamp":1368145580548,"mutableDetails":true,"mutableGroups":true}

  The renamed user.

  <div class="representation">

  </div>

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025482592&#39;); return false;"><em><span id="link-idm532025482592">expand</span></em></a>\]

  </div>

  <div id="idm532025482592" class="toggle">

  ###### Example

      {"errors":[{"context":"field_a","message":"A detailed validation error message for field_a.","exceptionName":null},{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The request was malformed.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025480240&#39;); return false;"><em><span id="link-idm532025480240">expand</span></em></a>\]

  </div>

  <div id="idm532025480240" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The authenticated user does not have the **ADMIN** permission or has a lower permission level than the user being deleted.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532064591312&#39;); return false;"><em><span id="link-idm532064591312">expand</span></em></a>\]

  </div>

  <div id="idm532064591312" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified user does not exist.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/admin/users/captcha

###### Methods

<div class="methods">

<div class="method">

#### DELETE

###### /rest/api/1.0/admin/users/captcha<span class="optional">?name</span>

Clears any CAPTCHA challenge that may constrain the user with the supplied username when they authenticate. Additionally any counter or metric that contributed towards the user being issued the CAPTCHA challenge (for instance too many consecutive failed logins) will also be reset.

The authenticated user must have the **ADMIN** permission to call this resource, and may not clear the CAPTCHA of a user with greater permissions than themselves.

###### request query parameters

| parameter | value                                                | description |
|-----------|------------------------------------------------------|-------------|
| **name**  | *[string](http://www.w3.org/TR/xmlschema-2/#string)* |             |

*Example response representations:*

- <div>

  204 - application/json \[<a href="#" onclick="toggle(&#39;idm532025478656&#39;); return false;"><em><span id="link-idm532025478656">expand</span></em></a>\]

  </div>

  <div id="idm532025478656" class="toggle">

  The CAPTCHA was successfully cleared.

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532064585888&#39;); return false;"><em><span id="link-idm532064585888">expand</span></em></a>\]

  </div>

  <div id="idm532064585888" class="toggle">

  ###### Example

      {"errors":[{"context":"field_a","message":"A detailed validation error message for field_a.","exceptionName":null},{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The request was malformed.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532064585760&#39;); return false;"><em><span id="link-idm532064585760">expand</span></em></a>\]

  </div>

  <div id="idm532064585760" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The authenticated user does not have the **ADMIN** permission.

  <div class="representation">

  </div>

  </div>

- <div>

  403 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025477920&#39;); return false;"><em><span id="link-idm532025477920">expand</span></em></a>\]

  </div>

  <div id="idm532025477920" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The action was disallowed as the authenticated user has a lower permission level than the group being deleted.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532064579488&#39;); return false;"><em><span id="link-idm532064579488">expand</span></em></a>\]

  </div>

  <div id="idm532064579488" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified user does not exist.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/admin/groups/add-user

###### Methods

<div class="methods">

<div class="method">

#### POST

**Deprecated since 2.10**. Use /rest/users/add-groups instead.

Add a user to a group.

In the request entity, the *context* attribute is the group and the *itemName* is the user.

The authenticated user must have the **ADMIN** permission to call this resource.

*Example request representations:*

- <div>

  application/json \[<a href="#" onclick="toggle(&#39;idm532064575456&#39;); return false;"><em><span id="link-idm532064575456">expand</span></em></a>\]

  </div>

  <div id="idm532064575456" class="toggle">

  ###### Example

      {"context":"group_a","itemName":"user_a"}

  </div>

*Example response representations:*

- <div>

  200 \[<a href="#" onclick="toggle(&#39;idm532064575072&#39;); return false;"><em><span id="link-idm532064575072">expand</span></em></a>\]

  </div>

  <div id="idm532064575072" class="toggle">

  The user was added to the group

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532063448176&#39;); return false;"><em><span id="link-idm532063448176">expand</span></em></a>\]

  </div>

  <div id="idm532063448176" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The authenticated user does not have the **ADMIN** permission.

  <div class="representation">

  </div>

  </div>

- <div>

  403 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532063445952&#39;); return false;"><em><span id="link-idm532063445952">expand</span></em></a>\]

  </div>

  <div id="idm532063445952" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The action was disallowed as it would exceed the server's licensing limit, or the groups permissions exceed the authenticated user's permission level.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532063443600&#39;); return false;"><em><span id="link-idm532063443600">expand</span></em></a>\]

  </div>

  <div id="idm532063443600" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified user or group does not exist.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/admin/users/add-group

###### Methods

<div class="methods">

<div class="method">

#### POST

**Deprecated since 2.10**. Use /rest/users/add-groups instead.

Add a user to a group. This is very similar to `groups/add-user`, but with the *context* and *itemName* attributes of the supplied request entity reversed. On the face of it this may appear redundant, but it facilitates a specific UI component in Stash.

In the request entity, the *context* attribute is the user and the *itemName* is the group.

The authenticated user must have the **ADMIN** permission to call this resource.

*Example request representations:*

- <div>

  application/json \[<a href="#" onclick="toggle(&#39;idm532027411440&#39;); return false;"><em><span id="link-idm532027411440">expand</span></em></a>\]

  </div>

  <div id="idm532027411440" class="toggle">

  ###### Example

      {"context":"user_a","itemName":"group_a"}

  </div>

*Example response representations:*

- <div>

  200 \[<a href="#" onclick="toggle(&#39;idm532027410016&#39;); return false;"><em><span id="link-idm532027410016">expand</span></em></a>\]

  </div>

  <div id="idm532027410016" class="toggle">

  The user was added to the group

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532027408784&#39;); return false;"><em><span id="link-idm532027408784">expand</span></em></a>\]

  </div>

  <div id="idm532027408784" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The authenticated user does not have the **ADMIN** permission.

  <div class="representation">

  </div>

  </div>

- <div>

  403 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532027406576&#39;); return false;"><em><span id="link-idm532027406576">expand</span></em></a>\]

  </div>

  <div id="idm532027406576" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The action was disallowed as it would exceed the server's licensing limit, or the groups permissions exceed the authenticated user's permission level.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532027405504&#39;); return false;"><em><span id="link-idm532027405504">expand</span></em></a>\]

  </div>

  <div id="idm532027405504" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified user or group does not exist.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/admin/groups/add-users

###### Methods

<div class="methods">

<div class="method">

#### POST

Add multiple users to a group.

The authenticated user must have the **ADMIN** permission to call this resource.

*Example request representations:*

- <div>

  application/json \[<a href="#" onclick="toggle(&#39;idm532027400320&#39;); return false;"><em><span id="link-idm532027400320">expand</span></em></a>\]

  </div>

  <div id="idm532027400320" class="toggle">

  ###### Example

      {"group":"group","users":["user1","user2"]}

  </div>

*Example response representations:*

- <div>

  200 \[<a href="#" onclick="toggle(&#39;idm532063439200&#39;); return false;"><em><span id="link-idm532063439200">expand</span></em></a>\]

  </div>

  <div id="idm532063439200" class="toggle">

  *\>All*

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532063438592&#39;); return false;"><em><span id="link-idm532063438592">expand</span></em></a>\]

  </div>

  <div id="idm532063438592" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The authenticated user does not have the **ADMIN** permission.

  <div class="representation">

  </div>

  </div>

- <div>

  403 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061987760&#39;); return false;"><em><span id="link-idm532061987760">expand</span></em></a>\]

  </div>

  <div id="idm532061987760" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The action was disallowed as it would exceed the server's licensing limit, or the group's permissions exceed the authenticated user's permission level.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061985712&#39;); return false;"><em><span id="link-idm532061985712">expand</span></em></a>\]

  </div>

  <div id="idm532061985712" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified group or users do not exist.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/admin/users/add-groups

###### Methods

<div class="methods">

<div class="method">

#### POST

Add a user to one or more groups.

The authenticated user must have the **ADMIN** permission to call this resource.

*Example request representations:*

- <div>

  application/json \[<a href="#" onclick="toggle(&#39;idm532061980912&#39;); return false;"><em><span id="link-idm532061980912">expand</span></em></a>\]

  </div>

  <div id="idm532061980912" class="toggle">

  ###### Example

      {"user":"user","groups":["group_a","group_b"]}

  </div>

*Example response representations:*

- <div>

  200 \[<a href="#" onclick="toggle(&#39;idm532061980784&#39;); return false;"><em><span id="link-idm532061980784">expand</span></em></a>\]

  </div>

  <div id="idm532061980784" class="toggle">

  The user was added to *all* the groups

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061978432&#39;); return false;"><em><span id="link-idm532061978432">expand</span></em></a>\]

  </div>

  <div id="idm532061978432" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The authenticated user does not have the **ADMIN** permission.

  <div class="representation">

  </div>

  </div>

- <div>

  403 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061980208&#39;); return false;"><em><span id="link-idm532061980208">expand</span></em></a>\]

  </div>

  <div id="idm532061980208" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The action was disallowed as it would exceed the server's licensing limit, or the groups permissions exceed the authenticated user's permission level.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061974880&#39;); return false;"><em><span id="link-idm532061974880">expand</span></em></a>\]

  </div>

  <div id="idm532061974880" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified user or groups do not exist.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/admin/groups/remove-user

###### Methods

<div class="methods">

<div class="method">

#### POST

**Deprecated since 2.10**. Use /rest/users/remove-groups instead.

Remove a user from a group.

The authenticated user must have the **ADMIN** permission to call this resource.

In the request entity, the *context* attribute is the group and the *itemName* is the user.

*Example request representations:*

- <div>

  application/json \[<a href="#" onclick="toggle(&#39;idm532061969584&#39;); return false;"><em><span id="link-idm532061969584">expand</span></em></a>\]

  </div>

  <div id="idm532061969584" class="toggle">

  ###### Example

      {"context":"group_a","itemName":"user_a"}

  </div>

*Example response representations:*

- <div>

  200 \[<a href="#" onclick="toggle(&#39;idm532061967488&#39;); return false;"><em><span id="link-idm532061967488">expand</span></em></a>\]

  </div>

  <div id="idm532061967488" class="toggle">

  The user was removed from the group.

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061966992&#39;); return false;"><em><span id="link-idm532061966992">expand</span></em></a>\]

  </div>

  <div id="idm532061966992" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The authenticated user does not have the **ADMIN** permission.

  <div class="representation">

  </div>

  </div>

- <div>

  403 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025476960&#39;); return false;"><em><span id="link-idm532025476960">expand</span></em></a>\]

  </div>

  <div id="idm532025476960" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The action was disallowed as the group has a higher permission level than the context user.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025475744&#39;); return false;"><em><span id="link-idm532025475744">expand</span></em></a>\]

  </div>

  <div id="idm532025475744" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified user or group does not exist.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/admin/users/remove-group

###### Methods

<div class="methods">

<div class="method">

#### POST

Remove a user from a group. This is very similar to `groups/remove-user`, but with the *context* and *itemName* attributes of the supplied request entity reversed. On the face of it this may appear redundant, but it facilitates a specific UI component in Stash.

In the request entity, the *context* attribute is the user and the *itemName* is the group.

The authenticated user must have the **ADMIN** permission to call this resource.

*Example request representations:*

- <div>

  application/json \[<a href="#" onclick="toggle(&#39;idm532027397952&#39;); return false;"><em><span id="link-idm532027397952">expand</span></em></a>\]

  </div>

  <div id="idm532027397952" class="toggle">

  ###### Example

      {"context":"user_a","itemName":"group_a"}

  </div>

*Example response representations:*

- <div>

  200 \[<a href="#" onclick="toggle(&#39;idm532027396832&#39;); return false;"><em><span id="link-idm532027396832">expand</span></em></a>\]

  </div>

  <div id="idm532027396832" class="toggle">

  The user was removed from the group.

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532027395632&#39;); return false;"><em><span id="link-idm532027395632">expand</span></em></a>\]

  </div>

  <div id="idm532027395632" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The authenticated user does not have the **ADMIN** permission.

  <div class="representation">

  </div>

  </div>

- <div>

  403 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532027394208&#39;); return false;"><em><span id="link-idm532027394208">expand</span></em></a>\]

  </div>

  <div id="idm532027394208" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The action was disallowed as the group has a higher permission level than the context user.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532027392208&#39;); return false;"><em><span id="link-idm532027392208">expand</span></em></a>\]

  </div>

  <div id="idm532027392208" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified user or group does not exist.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/admin/groups/more-members

###### Methods

<div class="methods">

<div class="method">

#### GET

###### /rest/api/1.0/admin/groups/more-members<span class="optional">?context</span><span class="optional">&filter</span>

*This is a [paged API](#paging-params)*.\
\
Retrieves a list of users that are members of a specified group.

The authenticated user must have the **LICENSED_USER** permission to call this resource.

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
<td><p><strong>context</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p></td>
<td><p>the group which should be used to locate members</p></td>
</tr>
<tr>
<td><p><strong>filter</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p>
<p>Default:</p></td>
<td><p>if specified only users with usernames, display names or email addresses containing the supplied string will be returned</p></td>
</tr>
</tbody>
</table>

*Example response representations:*

- <div>

  200 - application/json ([page](#paging-params)) \[<a href="#" onclick="toggle(&#39;idm532027384512&#39;); return false;"><em><span id="link-idm532027384512">expand</span></em></a>\]

  </div>

  <div id="idm532027384512" class="toggle">

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL","directoryName":"Bitbucket Internal Directory","deletable":true,"lastAuthenticationTimestamp":1368145580548,"mutableDetails":true,"mutableGroups":true}],"start":0}

  A page of users.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532027382080&#39;); return false;"><em><span id="link-idm532027382080">expand</span></em></a>\]

  </div>

  <div id="idm532027382080" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user is not a licensed user.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/admin/groups/more-non-members

###### Methods

<div class="methods">

<div class="method">

#### GET

###### /rest/api/1.0/admin/groups/more-non-members<span class="optional">?context</span><span class="optional">&filter</span>

*This is a [paged API](#paging-params)*.\
\
Retrieves a list of users that are *not* members of a specified group.

The authenticated user must have the **LICENSED_USER** permission to call this resource.

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
<td><p><strong>context</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p></td>
<td><p>the group which should be used to locate non-members</p></td>
</tr>
<tr>
<td><p><strong>filter</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p>
<p>Default:</p></td>
<td><p>if specified only users with usernames, display names or email addresses containing the supplied string will be returned</p></td>
</tr>
</tbody>
</table>

*Example response representations:*

- <div>

  200 - application/json ([page](#paging-params)) \[<a href="#" onclick="toggle(&#39;idm532027374896&#39;); return false;"><em><span id="link-idm532027374896">expand</span></em></a>\]

  </div>

  <div id="idm532027374896" class="toggle">

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL","directoryName":"Bitbucket Internal Directory","deletable":true,"lastAuthenticationTimestamp":1368145580548,"mutableDetails":true,"mutableGroups":true}],"start":0}

  A page of users.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532027372064&#39;); return false;"><em><span id="link-idm532027372064">expand</span></em></a>\]

  </div>

  <div id="idm532027372064" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user is not a licensed user.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/admin/users/more-members

###### Methods

<div class="methods">

<div class="method">

#### GET

###### /rest/api/1.0/admin/users/more-members<span class="optional">?context</span><span class="optional">&filter</span>

*This is a [paged API](#paging-params)*.\
\
Retrieves a list of groups the specified user is a member of.

The authenticated user must have the **LICENSED_USER** permission to call this resource.

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
<td><p><strong>context</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p></td>
<td><p>the user which should be used to locate groups</p></td>
</tr>
<tr>
<td><p><strong>filter</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p>
<p>Default:</p></td>
<td><p>if specified only groups with names containing the supplied string will be returned</p></td>
</tr>
</tbody>
</table>

*Example response representations:*

- <div>

  200 - application/json ([page](#paging-params)) \[<a href="#" onclick="toggle(&#39;idm532027365568&#39;); return false;"><em><span id="link-idm532027365568">expand</span></em></a>\]

  </div>

  <div id="idm532027365568" class="toggle">

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"name":"group-a","deletable":true}],"start":0}

  A page of groups.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532027362784&#39;); return false;"><em><span id="link-idm532027362784">expand</span></em></a>\]

  </div>

  <div id="idm532027362784" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user is not a licensed user.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/admin/users/more-non-members

###### Methods

<div class="methods">

<div class="method">

#### GET

###### /rest/api/1.0/admin/users/more-non-members<span class="optional">?context</span><span class="optional">&filter</span>

*This is a [paged API](#paging-params)*.\
\
Retrieves a list of groups the specified user is *not* a member of.

The authenticated user must have the **LICENSED_USER** permission to call this resource.

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
<td><p><strong>context</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p></td>
<td><p>the user which should be used to locate groups</p></td>
</tr>
<tr>
<td><p><strong>filter</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p>
<p>Default:</p></td>
<td><p>if specified only groups with names containing the supplied string will be returned</p></td>
</tr>
</tbody>
</table>

*Example response representations:*

- <div>

  200 - application/json ([page](#paging-params)) \[<a href="#" onclick="toggle(&#39;idm532027356464&#39;); return false;"><em><span id="link-idm532027356464">expand</span></em></a>\]

  </div>

  <div id="idm532027356464" class="toggle">

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"name":"group-a","deletable":true}],"start":0}

  A page of groups.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532027353680&#39;); return false;"><em><span id="link-idm532027353680">expand</span></em></a>\]

  </div>

  <div id="idm532027353680" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user is not a licensed user.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/admin/cluster

###### Methods

<div class="methods">

<div class="method">

#### GET

Gets information about the nodes that currently make up the stash cluster.

The authenticated user must have the **SYS_ADMIN** permission to call this resource.

*Example response representations:*

- <div>

  200 - application/json \[<a href="#" onclick="toggle(&#39;idm532026184000&#39;); return false;"><em><span id="link-idm532026184000">expand</span></em></a>\]

  </div>

  <div id="idm532026184000" class="toggle">

  ###### Example

      {"localNode":{"id":"d4fde8b1-2504-4998-a0ba-14fbe98edd4d","name":"foo","address":{"hostName":"foo","port":5000},"local":true},"nodes":[{"id":"d4fde8b1-2504-4998-a0ba-14fbe98edd4d","name":"foo","address":{"hostName":"foo","port":5000},"local":true},{"id":"73518909-8e86-445b-8345-fcbf2e0934b6","name":"bar","address":{"hostName":"bar","port":5001},"local":true}],"running":true}

  Information about the cluster

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026181840&#39;); return false;"><em><span id="link-idm532026181840">expand</span></em></a>\]

  </div>

  <div id="idm532026181840" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to retrieve the cluster information.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/admin/license

A REST endpoint for retrieving or updating the license.

###### Methods

<div class="methods">

<div class="method">

#### GET

Retrieves details about the current license, as well as the current status of the system with regards to the installed license. The status includes the current number of users applied toward the license limit, as well as any status messages about the license (warnings about expiry or user counts exceeding license limits).

The authenticated user must have **ADMIN** permission. Unauthenticated users, and non-administrators, are not permitted to access license details.

*Example response representations:*

- <div>

  200 - application/json (license) \[<a href="#" onclick="toggle(&#39;idm532025969232&#39;); return false;"><em><span id="link-idm532025969232">expand</span></em></a>\]

  </div>

  <div id="idm532025969232" class="toggle">

  ###### Example

      {"creationDate":1331038800000,"purchaseDate":1331038800000,"expiryDate":1372493732817,"numberOfDaysBeforeExpiry":0,"maintenanceExpiryDate":1372493732817,"numberOfDaysBeforeMaintenanceExpiry":0,"gracePeriodEndDate":1372493732817,"numberOfDaysBeforeGracePeriodExpiry":0,"maximumNumberOfUsers":12,"unlimitedNumberOfUsers":false,"serverId":"<server ID embedded in license>","supportEntitlementNumber":"<support entitlement number embedded in license>","license":"<encoded license text>","status":{"serverId":"<actual server ID>","currentNumberOfUsers":2}}

  The currently-installed license.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025966320&#39;); return false;"><em><span id="link-idm532025966320">expand</span></em></a>\]

  </div>

  <div id="idm532025966320" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the license, or the request is anonymous.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025963616&#39;); return false;"><em><span id="link-idm532025963616">expand</span></em></a>\]

  </div>

  <div id="idm532025963616" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  No license has been installed.

  <div class="representation">

  </div>

  </div>

</div>

<div class="method">

#### POST

Decodes the provided encoded license and sets it as the active license. If no license was provided, a 400 is returned. If the license cannot be decoded, or cannot be applied, a 409 is returned. Some possible reasons a license may not be applied include:

- It is for a different product
- It is already expired

Otherwise, if the license is updated successfully, details for the new license are returned with a 200 response.

**Warning**: It is possible to downgrade the license during update, applying a license with a lower number of permitted users. If the number of currently-licensed users exceeds the limits of the new license, pushing will be disabled until the licensed user count is brought into compliance with the new license.

The authenticated user must have **SYS_ADMIN** permission. **ADMIN** users may *view* the current license details, but they may not *update* the license.

*Example request representations:*

- <div>

  application/json \[<a href="#" onclick="toggle(&#39;idm532025959328&#39;); return false;"><em><span id="link-idm532025959328">expand</span></em></a>\]

  </div>

  <div id="idm532025959328" class="toggle">

  ###### Example

      {"license":"<encoded license text>"}

  </div>

*Example response representations:*

- <div>

  200 - application/json (license) \[<a href="#" onclick="toggle(&#39;idm532025957456&#39;); return false;"><em><span id="link-idm532025957456">expand</span></em></a>\]

  </div>

  <div id="idm532025957456" class="toggle">

  ###### Example

      {"creationDate":1331038800000,"purchaseDate":1331038800000,"expiryDate":1372493732817,"numberOfDaysBeforeExpiry":0,"maintenanceExpiryDate":1372493732817,"numberOfDaysBeforeMaintenanceExpiry":0,"gracePeriodEndDate":1372493732817,"numberOfDaysBeforeGracePeriodExpiry":0,"maximumNumberOfUsers":12,"unlimitedNumberOfUsers":false,"serverId":"<server ID embedded in license>","supportEntitlementNumber":"<support entitlement number embedded in license>","license":"<encoded license text>","status":{"serverId":"<actual server ID>","currentNumberOfUsers":2}}

  The newly-installed license.

  <div class="representation">

  </div>

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025956160&#39;); return false;"><em><span id="link-idm532025956160">expand</span></em></a>\]

  </div>

  <div id="idm532025956160" class="toggle">

  ###### Example

      {"errors":[{"context":"field_a","message":"A detailed validation error message for field_a.","exceptionName":null},{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  No encoded license was provided in the JSON body for the POST.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025953024&#39;); return false;"><em><span id="link-idm532025953024">expand</span></em></a>\]

  </div>

  <div id="idm532025953024" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to update the license.

  <div class="representation">

  </div>

  </div>

- <div>

  409 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025950960&#39;); return false;"><em><span id="link-idm532025950960">expand</span></em></a>\]

  </div>

  <div id="idm532025950960" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The encoded license could not be decoded, or it is not valid for use on this server. For example, it may be for a different product, or it may have already expired.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/admin/mail-server

###### Methods

<div class="methods">

<div class="method">

#### DELETE

Deletes the current mail configuration.

The authenticated user must have the **SYS_ADMIN** permission to call this resource.

*Example response representations:*

- <div>

  204 - application/json \[<a href="#" onclick="toggle(&#39;idm532023684672&#39;); return false;"><em><span id="link-idm532023684672">expand</span></em></a>\]

  </div>

  <div id="idm532023684672" class="toggle">

  The mail configuration was successfully deleted.

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532023686016&#39;); return false;"><em><span id="link-idm532023686016">expand</span></em></a>\]

  </div>

  <div id="idm532023686016" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to delete the mail server configuration.

  <div class="representation">

  </div>

  </div>

</div>

<div class="method">

#### GET

Retrieves the current mail configuration. The authenticated user must have the **SYS_ADMIN** permission to call this resource.

*Example response representations:*

- <div>

  200 - application/json (mailHostConfiguration) \[<a href="#" onclick="toggle(&#39;idm532023681744&#39;); return false;"><em><span id="link-idm532023681744">expand</span></em></a>\]

  </div>

  <div id="idm532023681744" class="toggle">

  ###### Example

      {"hostname":"smtp.example.com","port":465,"protocol":"SMTP","use-start-tls":true,"require-start-tls":false,"username":"user","sender-address":"stash-no-reply@company.com"}

  The mail configuration.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532023679920&#39;); return false;"><em><span id="link-idm532023679920">expand</span></em></a>\]

  </div>

  <div id="idm532023679920" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to retrieve the mail configuration.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json \[<a href="#" onclick="toggle(&#39;idm532023676848&#39;); return false;"><em><span id="link-idm532023676848">expand</span></em></a>\]

  </div>

  <div id="idm532023676848" class="toggle">

  The mail server hasn't been configured

  </div>

</div>

<div class="method">

#### PUT

Updates the mail configuration The authenticated user must have the **SYS_ADMIN** permission to call this resource.

*Example request representations:*

- <div>

  application/json \[<a href="#" onclick="toggle(&#39;idm532023674656&#39;); return false;"><em><span id="link-idm532023674656">expand</span></em></a>\]

  </div>

  <div id="idm532023674656" class="toggle">

  ###### Example

      {"hostname":"smtp.example.com","port":465,"protocol":"SMTP","use-start-tls":true,"require-start-tls":false,"username":"user","sender-address":"stash-no-reply@company.com"}

  </div>

*Example response representations:*

- <div>

  200 - application/json (mailConfiguration) \[<a href="#" onclick="toggle(&#39;idm532023672912&#39;); return false;"><em><span id="link-idm532023672912">expand</span></em></a>\]

  </div>

  <div id="idm532023672912" class="toggle">

  ###### Example

      {"hostname":"smtp.example.com","port":465,"protocol":"SMTP","use-start-tls":true,"require-start-tls":false,"username":"user","sender-address":"stash-no-reply@company.com"}

  The updated mail configuration.

  <div class="representation">

  </div>

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532023670672&#39;); return false;"><em><span id="link-idm532023670672">expand</span></em></a>\]

  </div>

  <div id="idm532023670672" class="toggle">

  ###### Example

      {"errors":[{"context":"field_a","message":"A detailed validation error message for field_a.","exceptionName":null},{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The mail configuration was not updated due to a validation error.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532023668320&#39;); return false;"><em><span id="link-idm532023668320">expand</span></em></a>\]

  </div>

  <div id="idm532023668320" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to update the mail configuration.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/admin/mail-server/sender-address

###### Methods

<div class="methods">

<div class="method">

#### DELETE

Clears the server email address.

The authenticated user must have the **ADMIN** permission to call this resource.

*Example response representations:*

- <div>

  204 - application/json \[<a href="#" onclick="toggle(&#39;idm532023661728&#39;); return false;"><em><span id="link-idm532023661728">expand</span></em></a>\]

  </div>

  <div id="idm532023661728" class="toggle">

  The server email address was successfully cleared.

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532023664336&#39;); return false;"><em><span id="link-idm532023664336">expand</span></em></a>\]

  </div>

  <div id="idm532023664336" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to clear the server email address.

  <div class="representation">

  </div>

  </div>

</div>

<div class="method">

#### GET

Retrieves the server email address

*Example response representations:*

- <div>

  200 - application/json (server email address) \[<a href="#" onclick="toggle(&#39;idm532023659792&#39;); return false;"><em><span id="link-idm532023659792">expand</span></em></a>\]

  </div>

  <div id="idm532023659792" class="toggle">

  ###### Example

      "stash-no-reply@company.com"

  The server email address

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532023657376&#39;); return false;"><em><span id="link-idm532023657376">expand</span></em></a>\]

  </div>

  <div id="idm532023657376" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to retrieve the server email address.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json \[<a href="#" onclick="toggle(&#39;idm532023655216&#39;); return false;"><em><span id="link-idm532023655216">expand</span></em></a>\]

  </div>

  <div id="idm532023655216" class="toggle">

  The server email address is not set

  </div>

</div>

<div class="method">

#### PUT

Updates the server email address The authenticated user must have the **ADMIN** permission to call this resource.

*Example request representations:*

- <div>

  application/json \[<a href="#" onclick="toggle(&#39;idm532023653376&#39;); return false;"><em><span id="link-idm532023653376">expand</span></em></a>\]

  </div>

  <div id="idm532023653376" class="toggle">

  ###### Example

      "stash-no-reply@company.com"

  </div>

*Example response representations:*

- <div>

  200 - application/json (senderAddress) \[<a href="#" onclick="toggle(&#39;idm532023652272&#39;); return false;"><em><span id="link-idm532023652272">expand</span></em></a>\]

  </div>

  <div id="idm532023652272" class="toggle">

  ###### Example

      "stash-no-reply@company.com"

  The updated server email address.

  <div class="representation">

  </div>

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532023650800&#39;); return false;"><em><span id="link-idm532023650800">expand</span></em></a>\]

  </div>

  <div id="idm532023650800" class="toggle">

  ###### Example

      {"errors":[{"context":"field_a","message":"A detailed validation error message for field_a.","exceptionName":null},{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The server email address was not updated due to a validation error.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532023647760&#39;); return false;"><em><span id="link-idm532023647760">expand</span></em></a>\]

  </div>

  <div id="idm532023647760" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to update the server email address.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/admin/permissions/users

###### Methods

<div class="methods">

<div class="method">

#### PUT

###### /rest/api/1.0/admin/permissions/users<span class="optional">?name</span><span class="optional">&permission</span>

Promote or demote the global permission level of a user. Available global permissions are:

- LICENSED_USER
- PROJECT_CREATE
- ADMIN
- SYS_ADMIN

See the [Bitbucket Server documentation](https://confluence.atlassian.com/display/BitbucketServer/Global+permissions) for a detailed explanation of what each permission entails.

The authenticated user must have:

- **ADMIN** permission or higher; and
- the permission they are attempting to grant; and
- greater or equal permissions than the current permission level of the user (a user may not demote the permission level of a user with higher permissions than them)

to call this resource. In addition, a user may not demote their own permission level.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **name** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the names of the users |
| **permission** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the permission to grant |

*Example response representations:*

- <div>

  204 \[<a href="#" onclick="toggle(&#39;idm532026338416&#39;); return false;"><em><span id="link-idm532026338416">expand</span></em></a>\]

  </div>

  <div id="idm532026338416" class="toggle">

  The requested permission was granted.

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026344640&#39;); return false;"><em><span id="link-idm532026344640">expand</span></em></a>\]

  </div>

  <div id="idm532026344640" class="toggle">

  ###### Example

      {"errors":[{"context":"field_a","message":"A detailed validation error message for field_a.","exceptionName":null},{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The request was malformed or the specified permission does not exist.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026340848&#39;); return false;"><em><span id="link-idm532026340848">expand</span></em></a>\]

  </div>

  <div id="idm532026340848" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user is not an administrator or doesn't have the specified permission they are attempting to grant.

  <div class="representation">

  </div>

  </div>

- <div>

  403 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026336416&#39;); return false;"><em><span id="link-idm532026336416">expand</span></em></a>\]

  </div>

  <div id="idm532026336416" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The action was disallowed as it would exceed the server's license limits.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026334816&#39;); return false;"><em><span id="link-idm532026334816">expand</span></em></a>\]

  </div>

  <div id="idm532026334816" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified user does not exist.

  <div class="representation">

  </div>

  </div>

- <div>

  409 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026332592&#39;); return false;"><em><span id="link-idm532026332592">expand</span></em></a>\]

  </div>

  <div id="idm532026332592" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The action was disallowed as it would reduce the currently authenticated user's permission level or the currently authenticated user has a lower permission level than the user they are attempting to modify.

  <div class="representation">

  </div>

  </div>

</div>

<div class="method">

#### GET

###### /rest/api/1.0/admin/permissions/users<span class="optional">?filter</span>

*This is a [paged API](#paging-params)*.\
\
Retrieve a page of users that have been granted at least one global permission.

The authenticated user must have **ADMIN** permission or higher to call this resource.

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
<td><p><strong>filter</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p>
<p>Default:</p></td>
<td><p>if specified only user names containing the supplied string will be returned</p></td>
</tr>
</tbody>
</table>

*Example response representations:*

- <div>

  200 - application/json ([page](#paging-params)) \[<a href="#" onclick="toggle(&#39;idm532026326960&#39;); return false;"><em><span id="link-idm532026326960">expand</span></em></a>\]

  </div>

  <div id="idm532026326960" class="toggle">

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"user":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"permission":"ADMIN"}],"start":0}

  A page of users and their highest global permissions.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026324800&#39;); return false;"><em><span id="link-idm532026324800">expand</span></em></a>\]

  </div>

  <div id="idm532026324800" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user is not an administrator.

  <div class="representation">

  </div>

  </div>

</div>

<div class="method">

#### DELETE

###### /rest/api/1.0/admin/permissions/users<span class="optional">?name</span>

Revoke all global permissions for a user.

The authenticated user must have:

- **ADMIN** permission or higher; and
- greater or equal permissions than the current permission level of the user (a user may not demote the permission level of a user with higher permissions than them)

to call this resource. In addition, a user may not demote their own permission level.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **name** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the name of the user |

*Example response representations:*

- <div>

  204 \[<a href="#" onclick="toggle(&#39;idm532026316640&#39;); return false;"><em><span id="link-idm532026316640">expand</span></em></a>\]

  </div>

  <div id="idm532026316640" class="toggle">

  All global permissions were revoked from the user.

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026319456&#39;); return false;"><em><span id="link-idm532026319456">expand</span></em></a>\]

  </div>

  <div id="idm532026319456" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user is not an administrator.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026315904&#39;); return false;"><em><span id="link-idm532026315904">expand</span></em></a>\]

  </div>

  <div id="idm532026315904" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified user does not exist.

  <div class="representation">

  </div>

  </div>

- <div>

  409 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026315056&#39;); return false;"><em><span id="link-idm532026315056">expand</span></em></a>\]

  </div>

  <div id="idm532026315056" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The action was disallowed as it would reduce the currently authenticated user's permission level or the currently authenticated user has a lower permission level than the user they are attempting to modify.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/admin/permissions/groups

###### Methods

<div class="methods">

<div class="method">

#### PUT

###### /rest/api/1.0/admin/permissions/groups<span class="optional">?permission</span><span class="optional">&name</span>

Promote or demote a user's global permission level. Available global permissions are:

- LICENSED_USER
- PROJECT_CREATE
- ADMIN
- SYS_ADMIN

See the [Bitbucket Server documentation](https://confluence.atlassian.com/display/BitbucketServer/Global+permissions) for a detailed explanation of what each permission entails.

The authenticated user must have:

- **ADMIN** permission or higher; and
- the permission they are attempting to grant or higher; and
- greater or equal permissions than the current permission level of the group (a user may not demote the permission level of a group with higher permissions than them)

to call this resource. In addition, a user may not demote a group's permission level if their own permission level would be reduced as a result.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **permission** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the permission to grant |
| **name** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the names of the groups |

*Example response representations:*

- <div>

  204 \[<a href="#" onclick="toggle(&#39;idm532026302944&#39;); return false;"><em><span id="link-idm532026302944">expand</span></em></a>\]

  </div>

  <div id="idm532026302944" class="toggle">

  The specified permission was granted to the specified user.

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026307808&#39;); return false;"><em><span id="link-idm532026307808">expand</span></em></a>\]

  </div>

  <div id="idm532026307808" class="toggle">

  ###### Example

      {"errors":[{"context":"field_a","message":"A detailed validation error message for field_a.","exceptionName":null},{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The request was malformed or the specified permission does not exist.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026304544&#39;); return false;"><em><span id="link-idm532026304544">expand</span></em></a>\]

  </div>

  <div id="idm532026304544" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user is not an administrator or doesn't have the specified permission they are attempting to grant.

  <div class="representation">

  </div>

  </div>

- <div>

  403 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026300752&#39;); return false;"><em><span id="link-idm532026300752">expand</span></em></a>\]

  </div>

  <div id="idm532026300752" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The action was disallowed as it would exceed the server's license limits.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026299616&#39;); return false;"><em><span id="link-idm532026299616">expand</span></em></a>\]

  </div>

  <div id="idm532026299616" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified group does not exist.

  <div class="representation">

  </div>

  </div>

- <div>

  409 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026296848&#39;); return false;"><em><span id="link-idm532026296848">expand</span></em></a>\]

  </div>

  <div id="idm532026296848" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The action was disallowed as it would reduce the currently authenticated user's permission level or the currently authenticated user has a lower permission level than the group they are attempting to modify.

  <div class="representation">

  </div>

  </div>

</div>

<div class="method">

#### GET

###### /rest/api/1.0/admin/permissions/groups<span class="optional">?filter</span>

*This is a [paged API](#paging-params)*.\
\
Retrieve a page of groups that have been granted at least one global permission.

The authenticated user must have **ADMIN** permission or higher to call this resource.

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
<td><p><strong>filter</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p>
<p>Default:</p></td>
<td><p>if specified only group names containing the supplied string will be returned</p></td>
</tr>
</tbody>
</table>

*Example response representations:*

- <div>

  200 - application/json ([page](#paging-params)) \[<a href="#" onclick="toggle(&#39;idm532026291216&#39;); return false;"><em><span id="link-idm532026291216">expand</span></em></a>\]

  </div>

  <div id="idm532026291216" class="toggle">

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"group":{"name":"group_a"},"permission":"ADMIN"}],"start":0}

  A page of groups and their highest global permissions.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026289056&#39;); return false;"><em><span id="link-idm532026289056">expand</span></em></a>\]

  </div>

  <div id="idm532026289056" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user is not an administrator.

  <div class="representation">

  </div>

  </div>

</div>

<div class="method">

#### DELETE

###### /rest/api/1.0/admin/permissions/groups<span class="optional">?name</span>

Revoke all global permissions for a group.

The authenticated user must have:

- **ADMIN** permission or higher; and
- greater or equal permissions than the current permission level of the group (a user may not demote the permission level of a group with higher permissions than them)

to call this resource. In addition, a user may not revoke a group's permissions if their own permission level would be reduced as a result.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **name** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the name of the group |

*Example response representations:*

- <div>

  204 \[<a href="#" onclick="toggle(&#39;idm532026280960&#39;); return false;"><em><span id="link-idm532026280960">expand</span></em></a>\]

  </div>

  <div id="idm532026280960" class="toggle">

  All global permissions were revoked from the group.

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026283776&#39;); return false;"><em><span id="link-idm532026283776">expand</span></em></a>\]

  </div>

  <div id="idm532026283776" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user is not an administrator.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026280224&#39;); return false;"><em><span id="link-idm532026280224">expand</span></em></a>\]

  </div>

  <div id="idm532026280224" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified group does not exist.

  <div class="representation">

  </div>

  </div>

- <div>

  409 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026279376&#39;); return false;"><em><span id="link-idm532026279376">expand</span></em></a>\]

  </div>

  <div id="idm532026279376" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The action was disallowed as it would reduce the currently authenticated user's permission level or the currently authenticated user has a lower permission level than the group they are attempting to modify.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/admin/permissions/users/none

###### Methods

<div class="methods">

<div class="method">

#### GET

###### /rest/api/1.0/admin/permissions/users/none<span class="optional">?filter</span>

*This is a [paged API](#paging-params)*.\
\
Retrieve a page of users that have no granted global permissions.

The authenticated user must have **ADMIN** permission or higher to call this resource.

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
<td><p><strong>filter</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p>
<p>Default:</p></td>
<td><p>if specified only user names containing the supplied string will be returned</p></td>
</tr>
</tbody>
</table>

*Example response representations:*

- <div>

  200 - application/json ([page](#paging-params)) \[<a href="#" onclick="toggle(&#39;idm532026272752&#39;); return false;"><em><span id="link-idm532026272752">expand</span></em></a>\]

  </div>

  <div id="idm532026272752" class="toggle">

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"}],"start":0}

  A page of users that have not been granted any global permissions.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026271152&#39;); return false;"><em><span id="link-idm532026271152">expand</span></em></a>\]

  </div>

  <div id="idm532026271152" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user is not an administrator.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/admin/permissions/groups/none

###### Methods

<div class="methods">

<div class="method">

#### GET

###### /rest/api/1.0/admin/permissions/groups/none<span class="optional">?filter</span>

*This is a [paged API](#paging-params)*.\
\
Retrieve a page of groups that have no granted global permissions.

The authenticated user must have **ADMIN** permission or higher to call this resource.

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
<td><p><strong>filter</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p>
<p>Default:</p></td>
<td><p>if specified only group names containing the supplied string will be returned</p></td>
</tr>
</tbody>
</table>

*Example response representations:*

- <div>

  200 - application/json ([page](#paging-params)) \[<a href="#" onclick="toggle(&#39;idm532026264864&#39;); return false;"><em><span id="link-idm532026264864">expand</span></em></a>\]

  </div>

  <div id="idm532026264864" class="toggle">

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"name":"group-a","deletable":true}],"start":0}

  A page of groups that have not been granted any global permissions.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026263184&#39;); return false;"><em><span id="link-idm532026263184">expand</span></em></a>\]

  </div>

  <div id="idm532026263184" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user is not an administrator.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/admin/pull-requests/{scmId}

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **scmId** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the id of the scm to get strategies for |

###### Methods

<div class="methods">

<div class="method">

#### POST

Update the pull request merge strategies for the context repository.

The authenticated user must have **ADMIN** permission for the context repository to call this resource.

Only the strategies provided will be enabled, only one may be set to default

An explicitly set pull request merge strategy configuration can be deleted by POSTing a document with an empty "mergeConfig" attribute. i.e:

\
 {\
     "mergeConfig": {\
     }\
 }\
 

Upon completion of this request, the effective configuration will be the default configuration.

*Example request representations:*

- <div>

  application/json \[<a href="#" onclick="toggle(&#39;idm532025990864&#39;); return false;"><em><span id="link-idm532025990864">expand</span></em></a>\]

  </div>

  <div id="idm532025990864" class="toggle">

  ###### Example

      {"defaultStrategy":{"id":"no-ff"},"strategies":[{"id":"no-ff"}]}

  </div>

*Example response representations:*

- <div>

  200 - application/json (strategies) \[<a href="#" onclick="toggle(&#39;idm532025989344&#39;); return false;"><em><span id="link-idm532025989344">expand</span></em></a>\]

  </div>

  <div id="idm532025989344" class="toggle">

  ###### Example

      {"defaultStrategy":{"description":"Always create a merge commit","enabled":true,"flag":"--no-ff","id":"no-ff","name":"Merge commit"},"strategies":[{"description":"Always create a merge commit","enabled":true,"flag":"--no-ff","id":"no-ff","name":"Merge commit"}],"type":"repository"}

  The repository pull request merge strategies for the context repository.

  <div class="representation">

  </div>

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025987376&#39;); return false;"><em><span id="link-idm532025987376">expand</span></em></a>\]

  </div>

  <div id="idm532025987376" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The repository pull request merge strategies were not updated due to a validation error.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025983840&#39;); return false;"><em><span id="link-idm532025983840">expand</span></em></a>\]

  </div>

  <div id="idm532025983840" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to administrate the specified repository.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025982688&#39;); return false;"><em><span id="link-idm532025982688">expand</span></em></a>\]

  </div>

  <div id="idm532025982688" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository does not exist.

  <div class="representation">

  </div>

  </div>

</div>

<div class="method">

#### GET

*This is a [paged API](#paging-params)*.\
\
Retrieve the merge strategies available for this instance.

The user must be authenticated to call this resource.

*Example response representations:*

- <div>

  200 - application/json ([page](#paging-params)) \[<a href="#" onclick="toggle(&#39;idm532025978000&#39;); return false;"><em><span id="link-idm532025978000">expand</span></em></a>\]

  </div>

  <div id="idm532025978000" class="toggle">

  ###### Example

      {"defaultStrategy":{"description":"Always create a merge commit","enabled":true,"flag":"--no-ff","id":"no-ff","name":"Merge commit"},"strategies":[{"description":"Always create a merge commit","enabled":true,"flag":"--no-ff","id":"no-ff","name":"Merge commit"}],"type":"repository"}

  The merge configuration of this instance.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025977168&#39;); return false;"><em><span id="link-idm532025977168">expand</span></em></a>\]

  </div>

  <div id="idm532025977168" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to see the request repository.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025972928&#39;); return false;"><em><span id="link-idm532025972928">expand</span></em></a>\]

  </div>

  <div id="idm532025972928" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The request repository does not exist.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/application-properties

###### Methods

<div class="methods">

<div class="method">

#### GET

Retrieve version information and other application properties.

No authentication is required to call this resource.

*Example response representations:*

- <div>

  200 - application/json (applicationProperties) \[<a href="#" onclick="toggle(&#39;idm532026376432&#39;); return false;"><em><span id="link-idm532026376432">expand</span></em></a>\]

  </div>

  <div id="idm532026376432" class="toggle">

  ###### Example

      {"version":"2.1.0","buildNumber":"20130123103656677","buildDate":"1358897885952000","displayName":"Example.com Bitbucket"}

  The application properties.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

REST Resource for personal dashboards

<div class="resource">

### /rest/api/1.0/dashboard/pull-request-suggestions

###### Methods

<div class="methods">

<div class="method">

#### GET

###### /rest/api/1.0/dashboard/pull-request-suggestions<span class="optional">?changesSince</span><span class="optional">&limit</span>

*This is a [paged API](#paging-params)*.\
\
Retrieves a page of suggestions for pull requests that the currently authenticated user may wish to raise. Such suggestions are based on ref changes occurring and so contain the ref change that prompted the suggestion plus the time the change event occurred. Changes will be returned in descending order based on the time the change that prompted the suggestion occurred.

Note that although the response is a page object, the interface does not support paging, however a limit can be applied to the size of the returned page.

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
<td><p><strong>changesSince</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p>
<p>Default: <code>172800</code></p></td>
<td><p>restrict pull request suggestions to be based on events that occurred since some time in the past. This is expressed in seconds since "now". So to return suggestions based only on activity within the past 48 hours, pass a value of 172800.</p></td>
</tr>
<tr>
<td><p><strong>limit</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#int">int</a></em></p>
<p>Default: <code>3</code></p></td>
<td><p>restricts the result set to return at most this many suggestions.</p></td>
</tr>
</tbody>
</table>

*Example response representations:*

- <div>

  200 - application/json ([page](#paging-params)) \[<a href="#" onclick="toggle(&#39;idm532061750160&#39;); return false;"><em><span id="link-idm532061750160">expand</span></em></a>\]

  </div>

  <div id="idm532061750160" class="toggle">

  A page of pull requests that match the search criteria.

  <div class="representation">

  </div>

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061749696&#39;); return false;"><em><span id="link-idm532061749696">expand</span></em></a>\]

  </div>

  <div id="idm532061749696" class="toggle">

  ###### Example

      {"errors":[{"context":"field_a","message":"A detailed validation error message for field_a.","exceptionName":null},{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The request was malformed.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061746624&#39;); return false;"><em><span id="link-idm532061746624">expand</span></em></a>\]

  </div>

  <div id="idm532061746624" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The current user is not authenticated

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/dashboard/pull-requests

###### Methods

<div class="methods">

<div class="method">

#### GET

###### /rest/api/1.0/dashboard/pull-requests<span class="optional">?state</span><span class="optional">&role</span><span class="optional">&participantStatus</span><span class="optional">&order</span><span class="optional">&closedSince</span>

*This is a [paged API](#paging-params)*.\
\
Retrieve a page of pull requests where the current authenticated user is involved as either a reviewer, author or a participant. The request may be filtered by pull request state, role or participant status.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **state** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | (optional, defaults to returning pull requests in any state). If a state is supplied only pull requests in the specified state will be returned. Either **OPEN**, **DECLINED** or **MERGED**. Omit this parameter to return pull request in any state. |
| **role** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | (optional, defaults to returning pull requests for any role). If a role is supplied only pull requests where the authenticated user is a participant in the given role will be returned. Either **REVIEWER**, **AUTHOR** or **PARTICIPANT**. |
| **participantStatus** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | (optional, defaults to returning pull requests with any participant status). A comma separated list of participant status. That is, one or more of **UNAPPROVED**, **NEEDS_WORK**, or **APPROVED**. |
| **order** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | (optional, defaults to **NEWEST**) the order to return pull requests in, either **OLDEST** (as in: "oldest first"), **NEWEST**, **PARTICIPANT_STATUS**, or **CLOSED_DATE**. Where **CLOSED_DATE** is specified and the result set includes pull requests that are not in the closed state, these pull requests will appear first in the result set, followed by most recently closed pull requests. |
| **closedSince** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | (optional, defaults to returning pull requests regardless of closed since date). Permits returning only pull requests with a closed timestamp set more recently that (now - closedSince). Units are in seconds. So for example if closed since 86400 is set only pull requests closed in the previous 24 hours will be returned. |

*Example response representations:*

- <div>

  200 - application/json ([page](#paging-params)) \[<a href="#" onclick="toggle(&#39;idm532061734864&#39;); return false;"><em><span id="link-idm532061734864">expand</span></em></a>\]

  </div>

  <div id="idm532061734864" class="toggle">

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"id":101,"version":1,"title":"Talking Nerdy","description":"It’s a kludge, but put the tuple from the database in the cache.","state":"OPEN","open":true,"closed":false,"createdDate":1359075920,"updatedDate":1359085920,"fromRef":{"id":"refs/heads/feature-ABC-123","repository":{"slug":"my-repo","name":null,"project":{"key":"PRJ"}}},"toRef":{"id":"refs/heads/master","repository":{"slug":"my-repo","name":null,"project":{"key":"PRJ"}}},"locked":false,"author":{"user":{"name":"tom","emailAddress":"tom@example.com","id":115026,"displayName":"Tom","active":true,"slug":"tom","type":"NORMAL"},"role":"AUTHOR","approved":true,"status":"APPROVED"},"reviewers":[{"user":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"lastReviewedCommit":"7549846524f8aed2bd1c0249993ae1bf9d3c9998","role":"REVIEWER","approved":true,"status":"APPROVED"}],"participants":[{"user":{"name":"harry","emailAddress":"harry@example.com","id":99049120,"displayName":"Harry","active":true,"slug":"harry","type":"NORMAL"},"role":"PARTICIPANT","approved":true,"status":"APPROVED"},{"user":{"name":"dick","emailAddress":"dick@example.com","id":3083181,"displayName":"Dick","active":true,"slug":"dick","type":"NORMAL"},"role":"PARTICIPANT","approved":false,"status":"UNAPPROVED"}],"links":{"self":[{"href":"http://link/to/pullrequest"}]}}],"start":0}

  A page of pull requests that match the search criteria.

  <div class="representation">

  </div>

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061732656&#39;); return false;"><em><span id="link-idm532061732656">expand</span></em></a>\]

  </div>

  <div id="idm532061732656" class="toggle">

  ###### Example

      {"errors":[{"context":"field_a","message":"A detailed validation error message for field_a.","exceptionName":null},{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The request was malformed.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061730224&#39;); return false;"><em><span id="link-idm532061730224">expand</span></em></a>\]

  </div>

  <div id="idm532061730224" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The current user is not authenticated

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/groups

###### Methods

<div class="methods">

<div class="method">

#### GET

###### /rest/api/1.0/groups<span class="optional">?filter</span>

*This is a [paged API](#paging-params)*.\
\
Retrieve a page of group names.

The authenticated user must have **PROJECT_ADMIN** permission or higher to call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **filter** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | if specified only group names containing the supplied string will be returned |

*Example response representations:*

- <div>

  200 - application/json ([page](#paging-params)) \[<a href="#" onclick="toggle(&#39;idm532025399600&#39;); return false;"><em><span id="link-idm532025399600">expand</span></em></a>\]

  </div>

  <div id="idm532025399600" class="toggle">

  ###### Example

      {"size":2,"limit":25,"isLastPage":true,"values":["group_a","group_b"],"start":0}

  A page of group names.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025396832&#39;); return false;"><em><span id="link-idm532025396832">expand</span></em></a>\]

  </div>

  <div id="idm532025396832" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user is not a project administrator.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/hooks/{hookKey}/avatar

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **hookKey** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the complete module key of the hook module |

###### Methods

<div class="methods">

<div class="method">

#### GET

###### /rest/api/1.0/hooks/{hookKey}/avatar<span class="optional">?version</span>

Retrieve the avatar for the project matching the supplied **moduleKey**.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **version** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | optional version used for HTTP caching only - any non-blank version will result in a large max-age Cache-Control header. Note that this does not affect the Last-Modified header. |

*Example response representations:*

- <div>

  200 - image/png \[<a href="#" onclick="toggle(&#39;idm532025350896&#39;); return false;"><em><span id="link-idm532025350896">expand</span></em></a>\]

  </div>

  <div id="idm532025350896" class="toggle">

  The avatar of the project matching the supplied **projectKey**.

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025349792&#39;); return false;"><em><span id="link-idm532025349792">expand</span></em></a>\]

  </div>

  <div id="idm532025349792" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the project.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025347216&#39;); return false;"><em><span id="link-idm532025347216">expand</span></em></a>\]

  </div>

  <div id="idm532025347216" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified project does not exist.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/inbox/pull-requests/count

###### Methods

<div class="methods">

<div class="method">

#### GET

*Example response representations:*

- <div>

  application/json; charset=UTF-8 \[<a href="#" onclick="toggle(&#39;idm532026146720&#39;); return false;"><em><span id="link-idm532026146720">expand</span></em></a>\]

  </div>

  <div id="idm532026146720" class="toggle">

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/inbox/pull-requests

###### Methods

<div class="methods">

<div class="method">

#### GET

###### /rest/api/1.0/inbox/pull-requests<span class="optional">?start</span><span class="optional">&limit</span><span class="optional">&role</span>

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
<td><p><strong>start</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#int">int</a></em></p>
<p>Default: <code>0</code></p></td>
<td></td>
</tr>
<tr>
<td><p><strong>limit</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#int">int</a></em></p>
<p>Default: <code>25</code></p></td>
<td></td>
</tr>
<tr>
<td><p><strong>role</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p>
<p>Default: <code>reviewer</code></p></td>
<td></td>
</tr>
</tbody>
</table>

*Example response representations:*

- <div>

  application/json; charset=UTF-8 \[<a href="#" onclick="toggle(&#39;idm532026141536&#39;); return false;"><em><span id="link-idm532026141536">expand</span></em></a>\]

  </div>

  <div id="idm532026141536" class="toggle">

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/logs/logger/{loggerName}

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **loggerName** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the name of the logger. |

###### Methods

<div class="methods">

<div class="method">

#### GET

Retrieve the current log level for a given logger.

The authenticated user must have **ADMIN** permission or higher to call this resource.

*Example response representations:*

- <div>

  200 - application/json (logLevel) \[<a href="#" onclick="toggle(&#39;idm532027252928&#39;); return false;"><em><span id="link-idm532027252928">expand</span></em></a>\]

  </div>

  <div id="idm532027252928" class="toggle">

  ###### Example

      {"logLevel":"DEBUG"}

  The log level of the logger.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532027250304&#39;); return false;"><em><span id="link-idm532027250304">expand</span></em></a>\]

  </div>

  <div id="idm532027250304" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to retrieve the log level.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/logs/logger/{loggerName}/{levelName}

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **levelName** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the level to set the logger to. Either TRACE, DEBUG, INFO, WARN or ERROR |
| **loggerName** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the name of the logger. |

###### Methods

<div class="methods">

<div class="method">

#### PUT

Set the current log level for a given logger.

The authenticated user must have **ADMIN** permission or higher to call this resource.

*Example response representations:*

- <div>

  204 - application/json \[<a href="#" onclick="toggle(&#39;idm532063418432&#39;); return false;"><em><span id="link-idm532063418432">expand</span></em></a>\]

  </div>

  <div id="idm532063418432" class="toggle">

  The log level was successfully changed.

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532063421232&#39;); return false;"><em><span id="link-idm532063421232">expand</span></em></a>\]

  </div>

  <div id="idm532063421232" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The log level was invalid.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532063421104&#39;); return false;"><em><span id="link-idm532063421104">expand</span></em></a>\]

  </div>

  <div id="idm532063421104" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to set the log level.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/logs/rootLogger

###### Methods

<div class="methods">

<div class="method">

#### GET

Retrieve the current log level for the root logger.

The authenticated user must have **ADMIN** permission or higher to call this resource.

*Example response representations:*

- <div>

  200 - application/json (logLevel) \[<a href="#" onclick="toggle(&#39;idm532063413840&#39;); return false;"><em><span id="link-idm532063413840">expand</span></em></a>\]

  </div>

  <div id="idm532063413840" class="toggle">

  ###### Example

      {"logLevel":"DEBUG"}

  The log level of the logger.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532063413712&#39;); return false;"><em><span id="link-idm532063413712">expand</span></em></a>\]

  </div>

  <div id="idm532063413712" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to retrieve the log level.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/logs/rootLogger/{levelName}

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **levelName** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the level to set the logger to. Either TRACE, DEBUG, INFO, WARN or ERROR |

###### Methods

<div class="methods">

<div class="method">

#### PUT

Set the current log level for the root logger.

The authenticated user must have **ADMIN** permission or higher to call this resource.

*Example response representations:*

- <div>

  204 - application/json \[<a href="#" onclick="toggle(&#39;idm532027242608&#39;); return false;"><em><span id="link-idm532027242608">expand</span></em></a>\]

  </div>

  <div id="idm532027242608" class="toggle">

  The log level was successfully changed.

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532027246656&#39;); return false;"><em><span id="link-idm532027246656">expand</span></em></a>\]

  </div>

  <div id="idm532027246656" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The log level was invalid.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532027244784&#39;); return false;"><em><span id="link-idm532027244784">expand</span></em></a>\]

  </div>

  <div id="idm532027244784" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to retrieve the log level.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/markup/preview

###### Methods

<div class="methods">

<div class="method">

#### POST

###### /rest/api/1.0/markup/preview<span class="optional">?urlMode</span><span class="optional">&hardwrap</span><span class="optional">&htmlEscape</span>

Preview the generated html for given markdown contents.

Only authenticated users may call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **urlMode** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | (Optional) The UrlMode used when building the url. One of: ABSOLUTE, RELATIVE and CONFIGURED By default this is RELATIVE. |
| **hardwrap** | *[boolean](http://www.w3.org/TR/xmlschema-2/#boolean)* | (Optional) Whether the markup implementation should convert newlines to breaks. By default this is false which reflects the standard markdown specification. |
| **htmlEscape** | *[boolean](http://www.w3.org/TR/xmlschema-2/#boolean)* | (Optional) true if HTML should be escaped in the input markup, false otherwise. |

*Example request representations:*

- <div>

  \*/\* \[<a href="#" onclick="toggle(&#39;idm532063351984&#39;); return false;"><em><span id="link-idm532063351984">expand</span></em></a>\]

  </div>

  <div id="idm532063351984" class="toggle">

  ###### Example

      # Hello World!

  </div>

*Example response representations:*

- <div>

  200 - application/json (markup) \[<a href="#" onclick="toggle(&#39;idm532063349664&#39;); return false;"><em><span id="link-idm532063349664">expand</span></em></a>\]

  </div>

  <div id="idm532063349664" class="toggle">

  ###### Example

      {
           "html" : "<h1>Hello World!</h1>"
       }

  The rendered markdown.

  <div class="representation">

  </div>

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532063347856&#39;); return false;"><em><span id="link-idm532063347856">expand</span></em></a>\]

  </div>

  <div id="idm532063347856" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The markdown was invalid.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532063345264&#39;); return false;"><em><span id="link-idm532063345264">expand</span></em></a>\]

  </div>

  <div id="idm532063345264" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions preview rendered markdown.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/profile/recent/repos

###### Methods

<div class="methods">

<div class="method">

#### GET

###### /rest/api/1.0/profile/recent/repos<span class="optional">?permission</span>

*This is a [paged API](#paging-params)*.\
\
Retrieve a page of recently accessed repositories for the currently authenticated user.

Repositories are ordered from most recently to least recently accessed.

Only authenticated users may call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **permission** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | (optional) if specified, it must be a valid repository permission level name and will limit the resulting repository list to ones that the requesting user has the specified permission level to. If not specified, the default `REPO_READ` permission level will be assumed. |

*Example response representations:*

- <div>

  200 - application/json ([page](#paging-params)) \[<a href="#" onclick="toggle(&#39;idm532023757808&#39;); return false;"><em><span id="link-idm532023757808">expand</span></em></a>\]

  </div>

  <div id="idm532023757808" class="toggle">

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"slug":"my-repo","id":1,"name":"My repo","scmId":"git","state":"AVAILABLE","statusMessage":"Available","forkable":true,"project":{"key":"PRJ","id":1,"name":"My Cool Project","description":"The description for my cool project.","public":true,"type":"NORMAL","links":{"self":[{"href":"http://link/to/project"}]}},"public":true,"links":{"clone":[{"href":"ssh://git@<baseURL>/PRJ/my-repo.git","name":"ssh"},{"href":"https://<baseURL>/scm/PRJ/my-repo.git","name":"http"}],"self":[{"href":"http://link/to/repository"}]}}],"start":0}

  A page of recently accessed repositories.

  <div class="representation">

  </div>

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532023756416&#39;); return false;"><em><span id="link-idm532023756416">expand</span></em></a>\]

  </div>

  <div id="idm532023756416" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The permission level is unknown or not related to repository.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532023753232&#39;); return false;"><em><span id="link-idm532023753232">expand</span></em></a>\]

  </div>

  <div id="idm532023753232" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The request is unauthenticated.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects

###### Methods

<div class="methods">

<div class="method">

#### GET

###### /rest/api/1.0/projects<span class="optional">?name</span><span class="optional">&permission</span>

*This is a [paged API](#paging-params)*.\
\
Retrieve a page of projects.

Only projects for which the authenticated user has the **PROJECT_VIEW** permission will be returned.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **name** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* |  |
| **permission** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* |  |

*Example response representations:*

- <div>

  200 - application/json ([page](#paging-params)) \[<a href="#" onclick="toggle(&#39;idm532026444416&#39;); return false;"><em><span id="link-idm532026444416">expand</span></em></a>\]

  </div>

  <div id="idm532026444416" class="toggle">

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"key":"PRJ","id":1,"name":"My Cool Project","description":"The description for my cool project.","public":true,"type":"NORMAL","links":{"self":[{"href":"http://link/to/project"}]}}],"start":0}

  A page of projects.

  <div class="representation">

  </div>

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026443552&#39;); return false;"><em><span id="link-idm532026443552">expand</span></em></a>\]

  </div>

  <div id="idm532026443552" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The permission level is unknown or not related to projects.

  <div class="representation">

  </div>

  </div>

</div>

<div class="method">

#### POST

Create a new project.

To include a custom avatar for the project, the project definition should contain an additional attribute with the key `avatar` and the value a data URI containing Base64-encoded image data. The URI should be in the following format:

\
     data:(content type, e.g. image/png);base64,(data)\
 

If the data is not Base64-encoded, or if a character set is defined in the URI, or the URI is otherwise invalid, *project creation will fail*.

The authenticated user must have **PROJECT_CREATE** permission to call this resource.

*Example request representations:*

- <div>

  application/json \[<a href="#" onclick="toggle(&#39;idm532026437136&#39;); return false;"><em><span id="link-idm532026437136">expand</span></em></a>\]

  </div>

  <div id="idm532026437136" class="toggle">

  ###### Example

      {"key":"PRJ","name":"My Cool Project","description":"The description for my cool project.","avatar":"data:image/png;base64,<base64-encoded-image-data>"}

  </div>

*Example response representations:*

- <div>

  201 - application/json (project) \[<a href="#" onclick="toggle(&#39;idm532026435216&#39;); return false;"><em><span id="link-idm532026435216">expand</span></em></a>\]

  </div>

  <div id="idm532026435216" class="toggle">

  ###### Example

      {"key":"PRJ","id":1,"name":"My Cool Project","description":"The description for my cool project.","public":true,"type":"NORMAL","links":{"self":[{"href":"http://link/to/project"}]}}

  The newly created project.

  <div class="representation">

  </div>

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026433360&#39;); return false;"><em><span id="link-idm532026433360">expand</span></em></a>\]

  </div>

  <div id="idm532026433360" class="toggle">

  ###### Example

      {"errors":[{"context":"field_a","message":"A detailed validation error message for field_a.","exceptionName":null},{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The project was not created due to a validation error.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026431680&#39;); return false;"><em><span id="link-idm532026431680">expand</span></em></a>\]

  </div>

  <div id="idm532026431680" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to create a project.

  <div class="representation">

  </div>

  </div>

- <div>

  409 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026428240&#39;); return false;"><em><span id="link-idm532026428240">expand</span></em></a>\]

  </div>

  <div id="idm532026428240" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The project key or name is already in use.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}

###### Methods

<div class="methods">

<div class="method">

#### GET

Retrieve the project matching the supplied **projectKey**.

The authenticated user must have **PROJECT_VIEW** permission for the specified project to call this resource.

*Example response representations:*

- <div>

  200 - application/json (project) \[<a href="#" onclick="toggle(&#39;idm532026424608&#39;); return false;"><em><span id="link-idm532026424608">expand</span></em></a>\]

  </div>

  <div id="idm532026424608" class="toggle">

  ###### Example

      {"key":"PRJ","id":1,"name":"My Cool Project","description":"The description for my cool project.","public":true,"type":"NORMAL","links":{"self":[{"href":"http://link/to/project"}]}}

  The project matching the supplied **projectKey**.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026424480&#39;); return false;"><em><span id="link-idm532026424480">expand</span></em></a>\]

  </div>

  <div id="idm532026424480" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the project.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026420064&#39;); return false;"><em><span id="link-idm532026420064">expand</span></em></a>\]

  </div>

  <div id="idm532026420064" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified project does not exist.

  <div class="representation">

  </div>

  </div>

</div>

<div class="method">

#### DELETE

Delete the project matching the supplied **projectKey**.

The authenticated user must have **PROJECT_ADMIN** permission for the specified project to call this resource.

*Example response representations:*

- <div>

  204 \[<a href="#" onclick="toggle(&#39;idm532026413616&#39;); return false;"><em><span id="link-idm532026413616">expand</span></em></a>\]

  </div>

  <div id="idm532026413616" class="toggle">

  The project matching the supplied **projectKey** was deleted.

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026416064&#39;); return false;"><em><span id="link-idm532026416064">expand</span></em></a>\]

  </div>

  <div id="idm532026416064" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to delete the project.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026412832&#39;); return false;"><em><span id="link-idm532026412832">expand</span></em></a>\]

  </div>

  <div id="idm532026412832" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified project does not exist.

  <div class="representation">

  </div>

  </div>

- <div>

  409 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026410480&#39;); return false;"><em><span id="link-idm532026410480">expand</span></em></a>\]

  </div>

  <div id="idm532026410480" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The project can not be deleted as it contains repositories.

  <div class="representation">

  </div>

  </div>

</div>

<div class="method">

#### PUT

Update the project matching the **projectKey** supplied in the resource path.

To include a custom avatar for the updated project, the project definition should contain an additional attribute with the key `avatar` and the value a data URI containing Base64-encoded image data. The URI should be in the following format: ` data:(content type, e.g. image/png);base64,(data) ` If the data is not Base64-encoded, or if a character set is defined in the URI, or the URI is otherwise invalid, *project creation will fail*.

The authenticated user must have **PROJECT_ADMIN** permission for the specified project to call this resource.

*Example request representations:*

- <div>

  application/json \[<a href="#" onclick="toggle(&#39;idm532026406688&#39;); return false;"><em><span id="link-idm532026406688">expand</span></em></a>\]

  </div>

  <div id="idm532026406688" class="toggle">

  ###### Example

      {"key":"PRJ","name":"My Cool Project","description":"The description for my cool project.","avatar":"data:image/png;base64,<base64-encoded-image-data>"}

  </div>

*Example response representations:*

- <div>

  200 - application/json (project) \[<a href="#" onclick="toggle(&#39;idm532026405920&#39;); return false;"><em><span id="link-idm532026405920">expand</span></em></a>\]

  </div>

  <div id="idm532026405920" class="toggle">

  ###### Example

      {"key":"PRJ","id":1,"name":"My Cool Project","description":"The description for my cool project.","public":true,"type":"NORMAL","links":{"self":[{"href":"http://link/to/project"}]}}

  The updated project. The project's key **was not** updated.

  <div class="representation">

  </div>

  </div>

- <div>

  201 - application/json (project) \[<a href="#" onclick="toggle(&#39;idm532026403264&#39;); return false;"><em><span id="link-idm532026403264">expand</span></em></a>\]

  </div>

  <div id="idm532026403264" class="toggle">

  ###### Example

      {"key":"PRJ","id":1,"name":"My Cool Project","description":"The description for my cool project.","public":true,"type":"NORMAL","links":{"self":[{"href":"http://link/to/project"}]}}

  The updated project. The project's key **was** updated.

  <div class="representation">

  </div>

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026401392&#39;); return false;"><em><span id="link-idm532026401392">expand</span></em></a>\]

  </div>

  <div id="idm532026401392" class="toggle">

  ###### Example

      {"errors":[{"context":"field_a","message":"A detailed validation error message for field_a.","exceptionName":null},{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The project was not updated due to a validation error.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026398800&#39;); return false;"><em><span id="link-idm532026398800">expand</span></em></a>\]

  </div>

  <div id="idm532026398800" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to update the project.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026395408&#39;); return false;"><em><span id="link-idm532026395408">expand</span></em></a>\]

  </div>

  <div id="idm532026395408" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified project does not exist.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/avatar.png

###### Methods

<div class="methods">

<div class="method">

#### GET

###### /rest/api/1.0/projects/{projectKey}/avatar.png<span class="optional">?s</span>

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
<td><p><strong>s</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#int">int</a></em></p>
<p>Default: <code>0</code></p></td>
<td><p>The desired size of the image. The server will return an image as close as possible to the specified size.</p></td>
</tr>
</tbody>
</table>

*Example response representations:*

- <div>

  200 - image/png \[<a href="#" onclick="toggle(&#39;idm532026390224&#39;); return false;"><em><span id="link-idm532026390224">expand</span></em></a>\]

  </div>

  <div id="idm532026390224" class="toggle">

  The avatar of the project matching the supplied **projectKey**.

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026388816&#39;); return false;"><em><span id="link-idm532026388816">expand</span></em></a>\]

  </div>

  <div id="idm532026388816" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the project.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026387232&#39;); return false;"><em><span id="link-idm532026387232">expand</span></em></a>\]

  </div>

  <div id="idm532026387232" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified project does not exist.

  <div class="representation">

  </div>

  </div>

</div>

<div class="method">

#### POST

Update the avatar for the project matching the supplied **projectKey**.

This resource accepts POST multipart form data, containing a single image in a form-field named 'avatar'.

There are configurable server limits on both the dimensions (1024x1024 pixels by default) and uploaded file size (1MB by default). Several different image formats are supported, but **PNG** and **JPEG** are preferred due to the file size limit.

This resource has Cross-Site Request Forgery (XSRF) protection. To allow the request to pass the XSRF check the caller needs to send an `X-Atlassian-Token` HTTP header with the value `no-check`.

An example [curl](http://curl.haxx.se/) request to upload an image name 'avatar.png' would be:

\
 curl -X POST -u username:password -H "X-Atlassian-Token: no-check" http://example.com/rest/api/1.0/projects/STASH/avatar.png -F avatar=@avatar.png\
 

The authenticated user must have **PROJECT_ADMIN** permission for the specified project to call this resource.

*Example response representations:*

- <div>

  201 \[<a href="#" onclick="toggle(&#39;idm532026383152&#39;); return false;"><em><span id="link-idm532026383152">expand</span></em></a>\]

  </div>

  <div id="idm532026383152" class="toggle">

  The avatar was uploaded successfully.

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026382768&#39;); return false;"><em><span id="link-idm532026382768">expand</span></em></a>\]

  </div>

  <div id="idm532026382768" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to update the project.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026381664&#39;); return false;"><em><span id="link-idm532026381664">expand</span></em></a>\]

  </div>

  <div id="idm532026381664" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified project does not exist.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/permissions/users

###### Methods

<div class="methods">

<div class="method">

#### PUT

###### /rest/api/1.0/projects/{projectKey}/permissions/users<span class="optional">?name</span><span class="optional">&permission</span>

Promote or demote a user's permission level for the specified project.

The authenticated user must have **PROJECT_ADMIN** permission for the specified project or a higher global permission to call this resource. In addition, a user may not reduce their own permission level unless they have a global permission that already implies that permission.

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
<td><p><strong>name</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p></td>
<td><p>the names of the users</p></td>
</tr>
<tr>
<td><p><strong>permission</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p></td>
<td><p>the permission to grant. See the [permissions documentation](https://confluence.atlassian.com/display/BitbucketServer/Using+project+permissions) for a detailed explanation of what each permission entails. Available project permissions are:</p>
<ul>
<li>PROJECT_READ</li>
<li>PROJECT_WRITE</li>
<li>PROJECT_ADMIN</li>
</ul></td>
</tr>
</tbody>
</table>

*Example response representations:*

- <div>

  204 \[<a href="#" onclick="toggle(&#39;idm532027235488&#39;); return false;"><em><span id="link-idm532027235488">expand</span></em></a>\]

  </div>

  <div id="idm532027235488" class="toggle">

  The requested permission was granted.

  </div>

- <div>

  400 \[<a href="#" onclick="toggle(&#39;idm532027236320&#39;); return false;"><em><span id="link-idm532027236320">expand</span></em></a>\]

  </div>

  <div id="idm532027236320" class="toggle">

  ###### Example

      {"errors":[{"context":"field_a","message":"A detailed validation error message for field_a.","exceptionName":null},{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The request was malformed or the specified permission does not exist.

  </div>

- <div>

  401 \[<a href="#" onclick="toggle(&#39;idm532027236192&#39;); return false;"><em><span id="link-idm532027236192">expand</span></em></a>\]

  </div>

  <div id="idm532027236192" class="toggle">

  The currently authenticated user is not an administrator for the specified project.

  </div>

- <div>

  403 \[<a href="#" onclick="toggle(&#39;idm532027232896&#39;); return false;"><em><span id="link-idm532027232896">expand</span></em></a>\]

  </div>

  <div id="idm532027232896" class="toggle">

  The action was disallowed as it would reduce the currently authenticated user's permission level.

  </div>

- <div>

  404 \[<a href="#" onclick="toggle(&#39;idm532027232256&#39;); return false;"><em><span id="link-idm532027232256">expand</span></em></a>\]

  </div>

  <div id="idm532027232256" class="toggle">

  The specified project or user does not exist.

  </div>

</div>

<div class="method">

#### GET

###### /rest/api/1.0/projects/{projectKey}/permissions/users<span class="optional">?filter</span>

*This is a [paged API](#paging-params)*.\
\
Retrieve a page of users that have been granted at least one permission for the specified project.

The authenticated user must have **PROJECT_ADMIN** permission for the specified project or a higher global permission to call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **filter** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | if specified only group names containing the supplied string will be returned |

*Example response representations:*

- <div>

  200 - application/json ([page](#paging-params)) \[<a href="#" onclick="toggle(&#39;idm532063406144&#39;); return false;"><em><span id="link-idm532063406144">expand</span></em></a>\]

  </div>

  <div id="idm532063406144" class="toggle">

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"user":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"permission":"ADMIN"}],"start":0}

  A page of users and their highest permissions for the specified project.

  <div class="representation">

  </div>

  </div>

- <div>

  401 \[<a href="#" onclick="toggle(&#39;idm532063404544&#39;); return false;"><em><span id="link-idm532063404544">expand</span></em></a>\]

  </div>

  <div id="idm532063404544" class="toggle">

  The currently authenticated user is not a project administrator for the specified project.

  </div>

- <div>

  404 \[<a href="#" onclick="toggle(&#39;idm532063402432&#39;); return false;"><em><span id="link-idm532063402432">expand</span></em></a>\]

  </div>

  <div id="idm532063402432" class="toggle">

  The specified project does not exist.

  </div>

</div>

<div class="method">

#### DELETE

###### /rest/api/1.0/projects/{projectKey}/permissions/users<span class="optional">?name</span>

Revoke all permissions for the specified project for a user.

The authenticated user must have **PROJECT_ADMIN** permission for the specified project or a higher global permission to call this resource.

In addition, a user may not revoke their own project permissions if they do not have a higher global permission.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **name** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the name of the user |

*Example response representations:*

- <div>

  204 \[<a href="#" onclick="toggle(&#39;idm532025470960&#39;); return false;"><em><span id="link-idm532025470960">expand</span></em></a>\]

  </div>

  <div id="idm532025470960" class="toggle">

  All project permissions were revoked from the user for the specified project.

  </div>

- <div>

  401 \[<a href="#" onclick="toggle(&#39;idm532063399440&#39;); return false;"><em><span id="link-idm532063399440">expand</span></em></a>\]

  </div>

  <div id="idm532063399440" class="toggle">

  The currently authenticated user is not an administrator of the specified project.

  </div>

- <div>

  404 \[<a href="#" onclick="toggle(&#39;idm532063398880&#39;); return false;"><em><span id="link-idm532063398880">expand</span></em></a>\]

  </div>

  <div id="idm532063398880" class="toggle">

  The specified project or group does not exist.

  </div>

- <div>

  409 \[<a href="#" onclick="toggle(&#39;idm532027230880&#39;); return false;"><em><span id="link-idm532027230880">expand</span></em></a>\]

  </div>

  <div id="idm532027230880" class="toggle">

  The action was disallowed as it would reduce the currently authenticated user's permission level.

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/permissions/{permission}/all

###### resource-wide template parameters

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
<td><p><strong>permission</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p></td>
<td><p>the permission to grant Available project permissions are:</p>
<ul>
<li>PROJECT_READ</li>
<li>PROJECT_WRITE</li>
<li>PROJECT_ADMIN</li>
</ul></td>
</tr>
</tbody>
</table>

###### Methods

<div class="methods">

<div class="method">

#### POST

###### /rest/api/1.0/projects/{projectKey}/permissions/{permission}/all<span class="optional">?allow</span>

Grant or revoke a project permission to all users, i.e. set the default permission.

The authenticated user must have **PROJECT_ADMIN** permission for the specified project or a higher global permission to call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **allow** | *[boolean](http://www.w3.org/TR/xmlschema-2/#boolean)* | *true* to grant the specified permission to all users, or *false* to revoke it |

*Example response representations:*

- <div>

  204 \[<a href="#" onclick="toggle(&#39;idm532025464064&#39;); return false;"><em><span id="link-idm532025464064">expand</span></em></a>\]

  </div>

  <div id="idm532025464064" class="toggle">

  The requested permission was successfully granted or revoked.

  </div>

- <div>

  400 \[<a href="#" onclick="toggle(&#39;idm532025467360&#39;); return false;"><em><span id="link-idm532025467360">expand</span></em></a>\]

  </div>

  <div id="idm532025467360" class="toggle">

  ###### Example

      {"errors":[{"context":"field_a","message":"A detailed validation error message for field_a.","exceptionName":null},{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The request was malformed or the specified permission does not exist.

  </div>

- <div>

  401 \[<a href="#" onclick="toggle(&#39;idm532025466576&#39;); return false;"><em><span id="link-idm532025466576">expand</span></em></a>\]

  </div>

  <div id="idm532025466576" class="toggle">

  The currently authenticated user is not an administrator of the specified project.

  </div>

- <div>

  404 \[<a href="#" onclick="toggle(&#39;idm532025463472&#39;); return false;"><em><span id="link-idm532025463472">expand</span></em></a>\]

  </div>

  <div id="idm532025463472" class="toggle">

  The specified project does not exist.

  </div>

</div>

<div class="method">

#### GET

Check whether the specified permission is the default permission (granted to all users) for a project.

The authenticated user must have **PROJECT_ADMIN** permission for the specified project or a higher global permission to call this resource.

*Example response representations:*

- <div>

  200 - application/json (permitted) \[<a href="#" onclick="toggle(&#39;idm532027227616&#39;); return false;"><em><span id="link-idm532027227616">expand</span></em></a>\]

  </div>

  <div id="idm532027227616" class="toggle">

  ###### Example

      {"permitted":true}

  A simple entity indicating whether the specified permission is the default permission for this project.

  <div class="representation">

  </div>

  </div>

- <div>

  400 \[<a href="#" onclick="toggle(&#39;idm532027227488&#39;); return false;"><em><span id="link-idm532027227488">expand</span></em></a>\]

  </div>

  <div id="idm532027227488" class="toggle">

  The request was malformed or the specified permission does not exist.

  </div>

- <div>

  401 \[<a href="#" onclick="toggle(&#39;idm532027224160&#39;); return false;"><em><span id="link-idm532027224160">expand</span></em></a>\]

  </div>

  <div id="idm532027224160" class="toggle">

  The currently authenticated user is not an administrator of the specified project.

  </div>

- <div>

  404 \[<a href="#" onclick="toggle(&#39;idm532027224448&#39;); return false;"><em><span id="link-idm532027224448">expand</span></em></a>\]

  </div>

  <div id="idm532027224448" class="toggle">

  The specified project does not exist.

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/permissions/groups

###### Methods

<div class="methods">

<div class="method">

#### PUT

###### /rest/api/1.0/projects/{projectKey}/permissions/groups<span class="optional">?permission</span><span class="optional">&name</span>

Promote or demote a group's permission level for the specified project.

The authenticated user must have **PROJECT_ADMIN** permission for the specified project or a higher global permission to call this resource. In addition, a user may not demote a group's permission level if their own permission level would be reduced as a result.

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
<td><p><strong>permission</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p></td>
<td><p>The permission to grant. See the [permissions documentation](https://confluence.atlassian.com/display/BitbucketServer/Using+project+permissions) for a detailed explanation of what each permission entails. Available project permissions are:</p>
<ul>
<li>PROJECT_READ</li>
<li>PROJECT_WRITE</li>
<li>PROJECT_ADMIN</li>
</ul></td>
</tr>
<tr>
<td><p><strong>name</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p></td>
<td><p>the names of the groups</p></td>
</tr>
</tbody>
</table>

*Example response representations:*

- <div>

  204 \[<a href="#" onclick="toggle(&#39;idm532025462800&#39;); return false;"><em><span id="link-idm532025462800">expand</span></em></a>\]

  </div>

  <div id="idm532025462800" class="toggle">

  The requested permission was granted.

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532063396176&#39;); return false;"><em><span id="link-idm532063396176">expand</span></em></a>\]

  </div>

  <div id="idm532063396176" class="toggle">

  ###### Example

      {"errors":[{"context":"field_a","message":"A detailed validation error message for field_a.","exceptionName":null},{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The request was malformed or the specified permission does not exist.

  <div class="representation">

  </div>

  </div>

- <div>

  401 \[<a href="#" onclick="toggle(&#39;idm532063394464&#39;); return false;"><em><span id="link-idm532063394464">expand</span></em></a>\]

  </div>

  <div id="idm532063394464" class="toggle">

  The currently authenticated user is not an administrator for the specified project.

  </div>

- <div>

  403 \[<a href="#" onclick="toggle(&#39;idm532025462144&#39;); return false;"><em><span id="link-idm532025462144">expand</span></em></a>\]

  </div>

  <div id="idm532025462144" class="toggle">

  The action was disallowed as it would reduce the currently authenticated user's permission level.

  </div>

- <div>

  404 \[<a href="#" onclick="toggle(&#39;idm532025461392&#39;); return false;"><em><span id="link-idm532025461392">expand</span></em></a>\]

  </div>

  <div id="idm532025461392" class="toggle">

  The specified project or group does not exist.

  </div>

</div>

<div class="method">

#### GET

###### /rest/api/1.0/projects/{projectKey}/permissions/groups<span class="optional">?filter</span>

*This is a [paged API](#paging-params)*.\
\
Retrieve a page of groups that have been granted at least one permission for the specified project.

The authenticated user must have **PROJECT_ADMIN** permission for the specified project or a higher global permission to call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **filter** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | if specified only group names containing the supplied string will be returned |

*Example response representations:*

- <div>

  200 - application/json ([page](#paging-params)) \[<a href="#" onclick="toggle(&#39;idm532025458368&#39;); return false;"><em><span id="link-idm532025458368">expand</span></em></a>\]

  </div>

  <div id="idm532025458368" class="toggle">

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"group":{"name":"group_a"},"permission":"ADMIN"}],"start":0}

  A page of groups and their highest permissions for the specified project.

  <div class="representation">

  </div>

  </div>

- <div>

  401 \[<a href="#" onclick="toggle(&#39;idm532025457904&#39;); return false;"><em><span id="link-idm532025457904">expand</span></em></a>\]

  </div>

  <div id="idm532025457904" class="toggle">

  The currently authenticated user is not a project administrator for the specified project.

  </div>

- <div>

  404 \[<a href="#" onclick="toggle(&#39;idm532025456912&#39;); return false;"><em><span id="link-idm532025456912">expand</span></em></a>\]

  </div>

  <div id="idm532025456912" class="toggle">

  The specified project does not exist.

  </div>

</div>

<div class="method">

#### DELETE

###### /rest/api/1.0/projects/{projectKey}/permissions/groups<span class="optional">?name</span>

Revoke all permissions for the specified project for a group.

The authenticated user must have **PROJECT_ADMIN** permission for the specified project or a higher global permission to call this resource.

In addition, a user may not revoke a group's permissions if it will reduce their own permission level.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **name** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the name of the group |

*Example response representations:*

- <div>

  204 \[<a href="#" onclick="toggle(&#39;idm532027219840&#39;); return false;"><em><span id="link-idm532027219840">expand</span></em></a>\]

  </div>

  <div id="idm532027219840" class="toggle">

  All project permissions were revoked from the group for the specified project.

  </div>

- <div>

  401 \[<a href="#" onclick="toggle(&#39;idm532027221488&#39;); return false;"><em><span id="link-idm532027221488">expand</span></em></a>\]

  </div>

  <div id="idm532027221488" class="toggle">

  The currently authenticated user is not an administrator of the specified project.

  </div>

- <div>

  404 \[<a href="#" onclick="toggle(&#39;idm532027219120&#39;); return false;"><em><span id="link-idm532027219120">expand</span></em></a>\]

  </div>

  <div id="idm532027219120" class="toggle">

  The specified project or group does not exist.

  </div>

- <div>

  409 \[<a href="#" onclick="toggle(&#39;idm532027218416&#39;); return false;"><em><span id="link-idm532027218416">expand</span></em></a>\]

  </div>

  <div id="idm532027218416" class="toggle">

  The action was disallowed as it would reduce the currently authenticated user's permission level.

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/permissions/groups/none

###### Methods

<div class="methods">

<div class="method">

#### GET

###### /rest/api/1.0/projects/{projectKey}/permissions/groups/none<span class="optional">?filter</span>

*This is a [paged API](#paging-params)*.\
\
Retrieve a page of groups that have no granted permissions for the specified project.

The authenticated user must have **PROJECT_ADMIN** permission for the specified project or a higher global permission to call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **filter** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | if specified only group names containing the supplied string will be returned |

*Example response representations:*

- <div>

  200 - application/json ([page](#paging-params)) \[<a href="#" onclick="toggle(&#39;idm532063389120&#39;); return false;"><em><span id="link-idm532063389120">expand</span></em></a>\]

  </div>

  <div id="idm532063389120" class="toggle">

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"name":"group-a","deletable":true}],"start":0}

  A page of groups that have not been granted any permissions for the specified project.

  <div class="representation">

  </div>

  </div>

- <div>

  401 \[<a href="#" onclick="toggle(&#39;idm532063387984&#39;); return false;"><em><span id="link-idm532063387984">expand</span></em></a>\]

  </div>

  <div id="idm532063387984" class="toggle">

  The currently authenticated user is not a project administrator for the specified project.

  </div>

- <div>

  404 \[<a href="#" onclick="toggle(&#39;idm532063386336&#39;); return false;"><em><span id="link-idm532063386336">expand</span></em></a>\]

  </div>

  <div id="idm532063386336" class="toggle">

  The specified project does not exist.

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/permissions/users/none

###### Methods

<div class="methods">

<div class="method">

#### GET

###### /rest/api/1.0/projects/{projectKey}/permissions/users/none<span class="optional">?filter</span>

*This is a [paged API](#paging-params)*.\
\
Retrieve a page of *licensed* users that have no granted permissions for the specified project.

The authenticated user must have **PROJECT_ADMIN** permission for the specified project or a higher global permission to call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **filter** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | if specified only group names containing the supplied string will be returned |

*Example response representations:*

- <div>

  200 - application/json ([page](#paging-params)) \[<a href="#" onclick="toggle(&#39;idm532025450608&#39;); return false;"><em><span id="link-idm532025450608">expand</span></em></a>\]

  </div>

  <div id="idm532025450608" class="toggle">

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"name":"group-a","deletable":true}],"start":0}

  A page of users that have not been granted any permissions for the specified project.

  <div class="representation">

  </div>

  </div>

- <div>

  401 \[<a href="#" onclick="toggle(&#39;idm532025450272&#39;); return false;"><em><span id="link-idm532025450272">expand</span></em></a>\]

  </div>

  <div id="idm532025450272" class="toggle">

  The currently authenticated user is not a project administrator for the specified project.

  </div>

- <div>

  404 \[<a href="#" onclick="toggle(&#39;idm532025447824&#39;); return false;"><em><span id="link-idm532025447824">expand</span></em></a>\]

  </div>

  <div id="idm532025447824" class="toggle">

  The specified project does not exist.

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **projectKey** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the parent project key |

###### Methods

<div class="methods">

<div class="method">

#### POST

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Create a new repository. Requires an existing project in which this repository will be created. The only parameters which will be used are name and scmId.

The authenticated user must have **PROJECT_ADMIN** permission for the context project to call this resource.

*Example request representations:*

- <div>

  application/json \[<a href="#" onclick="toggle(&#39;idm532026521776&#39;); return false;"><em><span id="link-idm532026521776">expand</span></em></a>\]

  </div>

  <div id="idm532026521776" class="toggle">

  ###### Example

      {"name":"My repo","scmId":"git","forkable":true}

  </div>

*Example response representations:*

- <div>

  201 - application/json (repository) \[<a href="#" onclick="toggle(&#39;idm532026520832&#39;); return false;"><em><span id="link-idm532026520832">expand</span></em></a>\]

  </div>

  <div id="idm532026520832" class="toggle">

  ###### Example

      {"slug":"my-repo","id":1,"name":"My repo","scmId":"git","state":"AVAILABLE","statusMessage":"Available","forkable":true,"project":{"key":"PRJ","id":1,"name":"My Cool Project","description":"The description for my cool project.","public":true,"type":"NORMAL","links":{"self":[{"href":"http://link/to/project"}]}},"public":true,"links":{"clone":[{"href":"ssh://git@<baseURL>/PRJ/my-repo.git","name":"ssh"},{"href":"https://<baseURL>/scm/PRJ/my-repo.git","name":"http"}],"self":[{"href":"http://link/to/repository"}]}}

  The newly created repository.

  <div class="representation">

  </div>

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026517744&#39;); return false;"><em><span id="link-idm532026517744">expand</span></em></a>\]

  </div>

  <div id="idm532026517744" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The repository was not created due to a validation error.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026516688&#39;); return false;"><em><span id="link-idm532026516688">expand</span></em></a>\]

  </div>

  <div id="idm532026516688" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to create a repository.

  <div class="representation">

  </div>

  </div>

- <div>

  409 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026512784&#39;); return false;"><em><span id="link-idm532026512784">expand</span></em></a>\]

  </div>

  <div id="idm532026512784" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  A repository with same name already exists.

  <div class="representation">

  </div>

  </div>

</div>

<div class="method">

#### GET

*This is a [paged API](#paging-params)*. *This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Retrieve repositories from the project corresponding to the supplied **projectKey**.

The authenticated user must have **REPO_READ** permission for the specified project to call this resource.

*Example response representations:*

- <div>

  200 - application/json ([page](#paging-params)) \[<a href="#" onclick="toggle(&#39;idm532026509488&#39;); return false;"><em><span id="link-idm532026509488">expand</span></em></a>\]

  </div>

  <div id="idm532026509488" class="toggle">

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"slug":"my-repo","id":1,"name":"My repo","scmId":"git","state":"AVAILABLE","statusMessage":"Available","forkable":true,"project":{"key":"PRJ","id":1,"name":"My Cool Project","description":"The description for my cool project.","public":true,"type":"NORMAL","links":{"self":[{"href":"http://link/to/project"}]}},"public":true,"links":{"clone":[{"href":"ssh://git@<baseURL>/PRJ/my-repo.git","name":"ssh"},{"href":"https://<baseURL>/scm/PRJ/my-repo.git","name":"http"}],"self":[{"href":"http://link/to/repository"}]}}],"start":0}

  The repositories matching the supplied **projectKey**.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025669856&#39;); return false;"><em><span id="link-idm532025669856">expand</span></em></a>\]

  </div>

  <div id="idm532025669856" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to see the specified project.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025668480&#39;); return false;"><em><span id="link-idm532025668480">expand</span></em></a>\]

  </div>

  <div id="idm532025668480" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified project does not exist.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **projectKey** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the parent project key |
| **projectKey** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the parent project key |
| **repositorySlug** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the repository slug |

###### Methods

<div class="methods">

<div class="method">

#### GET

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Retrieve the repository matching the supplied **projectKey** and **repositorySlug**.

The authenticated user must have **REPO_READ** permission for the specified repository to call this resource.

*Example response representations:*

- <div>

  200 - application/json (repository) \[<a href="#" onclick="toggle(&#39;idm532025659088&#39;); return false;"><em><span id="link-idm532025659088">expand</span></em></a>\]

  </div>

  <div id="idm532025659088" class="toggle">

  ###### Example

      {"slug":"my-repo","id":1,"name":"My repo","scmId":"git","state":"AVAILABLE","statusMessage":"Available","forkable":true,"project":{"key":"PRJ","id":1,"name":"My Cool Project","description":"The description for my cool project.","public":true,"type":"NORMAL","links":{"self":[{"href":"http://link/to/project"}]}},"public":true,"links":{"clone":[{"href":"ssh://git@<baseURL>/PRJ/my-repo.git","name":"ssh"},{"href":"https://<baseURL>/scm/PRJ/my-repo.git","name":"http"}],"self":[{"href":"http://link/to/repository"}]}}

  The repository which matches the supplied **projectKey** and **repositorySlug**.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025658960&#39;); return false;"><em><span id="link-idm532025658960">expand</span></em></a>\]

  </div>

  <div id="idm532025658960" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to see the specified repository.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025654064&#39;); return false;"><em><span id="link-idm532025654064">expand</span></em></a>\]

  </div>

  <div id="idm532025654064" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository does not exist.

  <div class="representation">

  </div>

  </div>

</div>

<div class="method">

#### PUT

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Update the repository matching the **repositorySlug** supplied in the resource path.

The repository's slug is derived from its name. If the name changes the slug may also change.

This API can be used to move the repository to a different project by setting the new project in the request, example: {@code {"project":{"key":"NEW_KEY"}}} .

The authenticated user must have **REPO_ADMIN** permission for the specified repository to call this resource.

*Example request representations:*

- <div>

  application/json \[<a href="#" onclick="toggle(&#39;idm532025650448&#39;); return false;"><em><span id="link-idm532025650448">expand</span></em></a>\]

  </div>

  <div id="idm532025650448" class="toggle">

  ###### Example

      {"name":"My repo","forkable":false,"project":{"key":"PRJ"},"public":true}

  </div>

*Example response representations:*

- <div>

  201 - application/json (repository) \[<a href="#" onclick="toggle(&#39;idm532025647776&#39;); return false;"><em><span id="link-idm532025647776">expand</span></em></a>\]

  </div>

  <div id="idm532025647776" class="toggle">

  ###### Example

      {"slug":"my-repo","id":1,"name":"My repo","scmId":"git","state":"AVAILABLE","statusMessage":"Available","forkable":true,"project":{"key":"PRJ","id":1,"name":"My Cool Project","description":"The description for my cool project.","public":true,"type":"NORMAL","links":{"self":[{"href":"http://link/to/project"}]}},"public":true,"links":{"clone":[{"href":"ssh://git@<baseURL>/PRJ/my-repo.git","name":"ssh"},{"href":"https://<baseURL>/scm/PRJ/my-repo.git","name":"http"}],"self":[{"href":"http://link/to/repository"}]}}

  The updated repository.

  <div class="representation">

  </div>

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025645632&#39;); return false;"><em><span id="link-idm532025645632">expand</span></em></a>\]

  </div>

  <div id="idm532025645632" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The repository was not updated due to a validation error.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025644560&#39;); return false;"><em><span id="link-idm532025644560">expand</span></em></a>\]

  </div>

  <div id="idm532025644560" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to update a repository

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025641840&#39;); return false;"><em><span id="link-idm532025641840">expand</span></em></a>\]

  </div>

  <div id="idm532025641840" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository does not exist.

  <div class="representation">

  </div>

  </div>

- <div>

  409 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025639488&#39;); return false;"><em><span id="link-idm532025639488">expand</span></em></a>\]

  </div>

  <div id="idm532025639488" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  A repository with same name as the target already exists

  <div class="representation">

  </div>

  </div>

</div>

<div class="method">

#### DELETE

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Schedule the repository matching the supplied **projectKey** and **repositorySlug** to be deleted. If the request repository is not present

The authenticated user must have **REPO_ADMIN** permission for the specified repository to call this resource.

*Example response representations:*

- <div>

  202 - application/json (message) \[<a href="#" onclick="toggle(&#39;idm532025634720&#39;); return false;"><em><span id="link-idm532025634720">expand</span></em></a>\]

  </div>

  <div id="idm532025634720" class="toggle">

  ###### Example

      {"context":null,"message":"Repository scheduled for deletion.","exceptionName":null}

  The repository has been scheduled for deletion.

  <div class="representation">

  </div>

  </div>

- <div>

  204 \[<a href="#" onclick="toggle(&#39;idm532025631616&#39;); return false;"><em><span id="link-idm532025631616">expand</span></em></a>\]

  </div>

  <div id="idm532025631616" class="toggle">

  No repository matching the supplied **projectKey** and **repositorySlug** was found.

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025633888&#39;); return false;"><em><span id="link-idm532025633888">expand</span></em></a>\]

  </div>

  <div id="idm532025633888" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to delete the repository.

  <div class="representation">

  </div>

  </div>

</div>

<div class="method">

#### POST

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Create a new repository forked from an existing repository.

The JSON body for this {@code POST} is not required to contain *any* properties. Even the name may be omitted. The following properties will be used, if provided:

- {@code "name":"Fork name"} - Specifies the forked repository's name
  - Defaults to the name of the origin repository if not specified
- {@code "project":{"key":"TARGET_KEY"}} - Specifies the forked repository's target project by key
  - Defaults to the current user's personal project if not specified

The authenticated user must have **REPO_READ** permission for the specified repository and **PROJECT_ADMIN** on the target project to call this resource. Note that users *always* have **PROJECT_ADMIN** permission on their personal projects.

*Example request representations:*

- <div>

  application/json \[<a href="#" onclick="toggle(&#39;idm532025628400&#39;); return false;"><em><span id="link-idm532025628400">expand</span></em></a>\]

  </div>

  <div id="idm532025628400" class="toggle">

  ###### Example

      {"slug":"my-repo","name":null,"project":{"key":"PRJ"}}

  </div>

*Example response representations:*

- <div>

  201 - application/json (repository) \[<a href="#" onclick="toggle(&#39;idm532025625648&#39;); return false;"><em><span id="link-idm532025625648">expand</span></em></a>\]

  </div>

  <div id="idm532025625648" class="toggle">

  ###### Example

      {"slug":"my-repo","id":2,"name":"My repo","scmId":"git","state":"AVAILABLE","statusMessage":"Available","forkable":true,"origin":{"slug":"my-repo","id":1,"name":"My repo","scmId":"git","state":"AVAILABLE","statusMessage":"Available","forkable":true,"project":{"key":"PRJ","id":1,"name":"My Cool Project","description":"The description for my cool project.","public":true,"type":"NORMAL","links":{"self":[{"href":"http://link/to/project"}]}},"public":true,"links":{"clone":[{"href":"ssh://git@<baseURL>/PRJ/my-repo.git","name":"ssh"},{"href":"https://<baseURL>/scm/PRJ/my-repo.git","name":"http"}],"self":[{"href":"http://link/to/repository"}]}},"project":{"key":"~JDOE","id":2,"name":"John Doe","type":"PERSONAL","links":{"self":[{"href":"http://link/to/project"}]}},"links":{"clone":[{"href":"https://<baseURL>/scm/JDOE/my-repo.git","name":"http"},{"href":"ssh://git@<baseURL>/JDOE/my-repo.git","name":"ssh"}],"self":[{"href":"http://link/to/repository"}]}}

  The newly created fork.

  <div class="representation">

  </div>

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025623648&#39;); return false;"><em><span id="link-idm532025623648">expand</span></em></a>\]

  </div>

  <div id="idm532025623648" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  A validation error prevented the fork from being created. Possible validation errors include: The name or slug for the fork collides with another repository in the target project; an SCM type was specified in the JSON body; a project was specified in the JSON body without a "key" property.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025620416&#39;); return false;"><em><span id="link-idm532025620416">expand</span></em></a>\]

  </div>

  <div id="idm532025620416" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to create a fork.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025618960&#39;); return false;"><em><span id="link-idm532025618960">expand</span></em></a>\]

  </div>

  <div id="idm532025618960" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository does not exist, or, if a target project was specified, the target project does not exist.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/forks

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **projectKey** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the parent project key |

###### Methods

<div class="methods">

<div class="method">

#### GET

*This is a [paged API](#paging-params)*. *This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Retrieve repositories which have been forked from this one. Unlike {@link \#getRelatedRepositories(Repository, PageRequest) related repositories}, this only looks at a given repository's direct forks. If those forks have themselves been the origin of more forks, such "grandchildren" repositories will not be retrieved.

Only repositories to which the authenticated user has **REPO_READ** permission will be included, even if other repositories have been forked from this one.

*Example response representations:*

- <div>

  200 - application/json ([page](#paging-params)) \[<a href="#" onclick="toggle(&#39;idm532025614064&#39;); return false;"><em><span id="link-idm532025614064">expand</span></em></a>\]

  </div>

  <div id="idm532025614064" class="toggle">

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"slug":"my-repo","id":2,"name":"My repo","scmId":"git","state":"AVAILABLE","statusMessage":"Available","forkable":true,"origin":{"slug":"my-repo","id":1,"name":"My repo","scmId":"git","state":"AVAILABLE","statusMessage":"Available","forkable":true,"project":{"key":"PRJ","id":1,"name":"My Cool Project","description":"The description for my cool project.","public":true,"type":"NORMAL","links":{"self":[{"href":"http://link/to/project"}]}},"public":true,"links":{"clone":[{"href":"ssh://git@<baseURL>/PRJ/my-repo.git","name":"ssh"},{"href":"https://<baseURL>/scm/PRJ/my-repo.git","name":"http"}],"self":[{"href":"http://link/to/repository"}]}},"project":{"key":"~JDOE","id":2,"name":"John Doe","type":"PERSONAL","links":{"self":[{"href":"http://link/to/project"}]}},"links":{"clone":[{"href":"https://<baseURL>/scm/JDOE/my-repo.git","name":"http"},{"href":"ssh://git@<baseURL>/JDOE/my-repo.git","name":"ssh"}],"self":[{"href":"http://link/to/repository"}]}}],"start":0}

  A page of repositories related to the request repository.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025612176&#39;); return false;"><em><span id="link-idm532025612176">expand</span></em></a>\]

  </div>

  <div id="idm532025612176" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to see the request repository.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025610144&#39;); return false;"><em><span id="link-idm532025610144">expand</span></em></a>\]

  </div>

  <div id="idm532025610144" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The request repository does not exist.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/recreate

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **projectKey** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the parent project key |

###### Methods

<div class="methods">

<div class="method">

#### POST

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
If a create or fork operation fails, calling this method will clean up the broken repository and try again. The repository must be in an INITIALISATION_FAILED state.

The authenticated user must have **PROJECT_ADMIN** permission for the specified project to call this resource.

*Example response representations:*

- <div>

  201 - application/json (repository) \[<a href="#" onclick="toggle(&#39;idm532025598032&#39;); return false;"><em><span id="link-idm532025598032">expand</span></em></a>\]

  </div>

  <div id="idm532025598032" class="toggle">

  ###### Example

      {"slug":"my-repo","id":1,"name":"My repo","scmId":"git","state":"AVAILABLE","statusMessage":"Available","forkable":true,"project":{"key":"PRJ","id":1,"name":"My Cool Project","description":"The description for my cool project.","public":true,"type":"NORMAL","links":{"self":[{"href":"http://link/to/project"}]}},"public":true,"links":{"clone":[{"href":"ssh://git@<baseURL>/PRJ/my-repo.git","name":"ssh"},{"href":"https://<baseURL>/scm/PRJ/my-repo.git","name":"http"}],"self":[{"href":"http://link/to/repository"}]}}

  The newly created repository.

  <div class="representation">

  </div>

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025595392&#39;); return false;"><em><span id="link-idm532025595392">expand</span></em></a>\]

  </div>

  <div id="idm532025595392" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The repository was not created due to a validation error.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025592736&#39;); return false;"><em><span id="link-idm532025592736">expand</span></em></a>\]

  </div>

  <div id="idm532025592736" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to create a repository.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025591200&#39;); return false;"><em><span id="link-idm532025591200">expand</span></em></a>\]

  </div>

  <div id="idm532025591200" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository does not exist.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/related

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **projectKey** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the parent project key |

###### Methods

<div class="methods">

<div class="method">

#### GET

*This is a [paged API](#paging-params)*. *This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Retrieve repositories which are related to this one. Related repositories are from the same {@link Repository#getHierarchyId() hierarchy} as this repository.

Only repositories to which the authenticated user has **REPO_READ** permission will be included, even if more repositories are part of this repository's hierarchy.

*Example response representations:*

- <div>

  200 - application/json ([page](#paging-params)) \[<a href="#" onclick="toggle(&#39;idm532065645680&#39;); return false;"><em><span id="link-idm532065645680">expand</span></em></a>\]

  </div>

  <div id="idm532065645680" class="toggle">

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"slug":"my-repo","id":2,"name":"My repo","scmId":"git","state":"AVAILABLE","statusMessage":"Available","forkable":true,"origin":{"slug":"my-repo","id":1,"name":"My repo","scmId":"git","state":"AVAILABLE","statusMessage":"Available","forkable":true,"project":{"key":"PRJ","id":1,"name":"My Cool Project","description":"The description for my cool project.","public":true,"type":"NORMAL","links":{"self":[{"href":"http://link/to/project"}]}},"public":true,"links":{"clone":[{"href":"ssh://git@<baseURL>/PRJ/my-repo.git","name":"ssh"},{"href":"https://<baseURL>/scm/PRJ/my-repo.git","name":"http"}],"self":[{"href":"http://link/to/repository"}]}},"project":{"key":"~JDOE","id":2,"name":"John Doe","type":"PERSONAL","links":{"self":[{"href":"http://link/to/project"}]}},"links":{"clone":[{"href":"https://<baseURL>/scm/JDOE/my-repo.git","name":"http"},{"href":"ssh://git@<baseURL>/JDOE/my-repo.git","name":"ssh"}],"self":[{"href":"http://link/to/repository"}]}}],"start":0}

  A page of repositories related to the request repository.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025604176&#39;); return false;"><em><span id="link-idm532025604176">expand</span></em></a>\]

  </div>

  <div id="idm532025604176" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to see the request repository.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025601888&#39;); return false;"><em><span id="link-idm532025601888">expand</span></em></a>\]

  </div>

  <div id="idm532025601888" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The request repository does not exist.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/archive

###### Methods

<div class="methods">

<div class="method">

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/archive<span class="optional">?at</span><span class="optional">&filename</span><span class="optional">&format</span><span class="optional">&path</span><span class="optional">&prefix</span>

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
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

- <div>

  200 - application/octet-stream; application/x-tar (archive) \[<a href="#" onclick="toggle(&#39;idm532063490432&#39;); return false;"><em><span id="link-idm532063490432">expand</span></em></a>\]

  </div>

  <div id="idm532063490432" class="toggle">

  An archive or the requested commit, in zip, tar or gzipped-tar format.

  <div class="representation">

  </div>

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532063490160&#39;); return false;"><em><span id="link-idm532063490160">expand</span></em></a>\]

  </div>

  <div id="idm532063490160" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The requested `format` is not supported.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532063488832&#39;); return false;"><em><span id="link-idm532063488832">expand</span></em></a>\]

  </div>

  <div id="idm532063488832" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the repository.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532063484496&#39;); return false;"><em><span id="link-idm532063484496">expand</span></em></a>\]

  </div>

  <div id="idm532063484496" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The repository does not exist or does not contain the `at` commit.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/branches

###### Methods

<div class="methods">

<div class="method">

#### POST

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Creates a branch using the information provided in the {@link RestCreateBranchRequest request}

The authenticated user must have **REPO_WRITE** permission for the context repository to call this resource.

*Example request representations:*

- <div>

  application/json \[<a href="#" onclick="toggle(&#39;idm532065000272&#39;); return false;"><em><span id="link-idm532065000272">expand</span></em></a>\]

  </div>

  <div id="idm532065000272" class="toggle">

  ###### Example

      {"name":"my-branch","startPoint":"8d351a10fb428c0c1239530256e21cf24f136e73","message":"This is my branch"}

  </div>

*Example response representations:*

- <div>

  200 - application/json (branch) \[<a href="#" onclick="toggle(&#39;idm532061941104&#39;); return false;"><em><span id="link-idm532061941104">expand</span></em></a>\]

  </div>

  <div id="idm532061941104" class="toggle">

  ###### Example

      {"id":"refs/heads/master","displayId":"master","type":"BRANCH","latestCommit":"8d51122def5632836d1cb1026e879069e10a1e13","latestChangeset":"8d51122def5632836d1cb1026e879069e10a1e13","isDefault":true}

  The created branch

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061939456&#39;); return false;"><em><span id="link-idm532061939456">expand</span></em></a>\]

  </div>

  <div id="idm532061939456" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to write to the repository.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061936512&#39;); return false;"><em><span id="link-idm532061936512">expand</span></em></a>\]

  </div>

  <div id="idm532061936512" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository does not exist.

  <div class="representation">

  </div>

  </div>

</div>

<div class="method">

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/branches<span class="optional">?base</span><span class="optional">&details</span><span class="optional">&filterText</span><span class="optional">&orderBy</span>

*This is a [paged API](#paging-params)*. *This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Retrieve the branches matching the supplied **filterText** param.

The authenticated user must have **REPO_READ** permission for the specified repository to call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **base** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | base branch or tag to compare each branch to (for the metadata providers that uses that information) |
| **details** | *[boolean](http://www.w3.org/TR/xmlschema-2/#boolean)* | whether to retrieve plugin-provided metadata about each branch |
| **filterText** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the text to match on |
| **orderBy** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | ordering of refs either ALPHABETICAL (by name) or MODIFICATION (last updated) |

*Example response representations:*

- <div>

  200 - application/json ([page](#paging-params)) \[<a href="#" onclick="toggle(&#39;idm532023786032&#39;); return false;"><em><span id="link-idm532023786032">expand</span></em></a>\]

  </div>

  <div id="idm532023786032" class="toggle">

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"id":"refs/heads/master","displayId":"master","type":"BRANCH","latestCommit":"8d51122def5632836d1cb1026e879069e10a1e13","latestChangeset":"8d51122def5632836d1cb1026e879069e10a1e13","isDefault":true}],"start":0}

  The branches matching the supplied **filterText**.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532023783296&#39;); return false;"><em><span id="link-idm532023783296">expand</span></em></a>\]

  </div>

  <div id="idm532023783296" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to read the repository.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532023780816&#39;); return false;"><em><span id="link-idm532023780816">expand</span></em></a>\]

  </div>

  <div id="idm532023780816" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository does not exist.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/branches/default

###### Methods

<div class="methods">

<div class="method">

#### GET

*This is a [paged API](#paging-params)*. *This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Get the default branch of the repository.

The authenticated user must have **REPO_READ** permission for the specified repository to call this resource.

*Example response representations:*

- <div>

  200 - application/json ([page](#paging-params)) \[<a href="#" onclick="toggle(&#39;idm532023776976&#39;); return false;"><em><span id="link-idm532023776976">expand</span></em></a>\]

  </div>

  <div id="idm532023776976" class="toggle">

  ###### Example

      {"id":"refs/heads/master","displayId":"master","type":"BRANCH","latestCommit":"8d51122def5632836d1cb1026e879069e10a1e13","latestChangeset":"8d51122def5632836d1cb1026e879069e10a1e13","isDefault":true}

  The configured default branch for the repository.

  <div class="representation">

  </div>

  </div>

- <div>

  204 \[<a href="#" onclick="toggle(&#39;idm532023772368&#39;); return false;"><em><span id="link-idm532023772368">expand</span></em></a>\]

  </div>

  <div id="idm532023772368" class="toggle">

  The repository is empty, and has no default branch.

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532023776848&#39;); return false;"><em><span id="link-idm532023776848">expand</span></em></a>\]

  </div>

  <div id="idm532023776848" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to read the repository.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532023770992&#39;); return false;"><em><span id="link-idm532023770992">expand</span></em></a>\]

  </div>

  <div id="idm532023770992" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository does not exist, or its configured default branch does not exist.

  <div class="representation">

  </div>

  </div>

</div>

<div class="method">

#### PUT

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Update the default branch of a repository.

The authenticated user must have **REPO_ADMIN** permission for the specified repository to call this resource.

*Example request representations:*

- <div>

  application/json \[<a href="#" onclick="toggle(&#39;idm532023767392&#39;); return false;"><em><span id="link-idm532023767392">expand</span></em></a>\]

  </div>

  <div id="idm532023767392" class="toggle">

  ###### Example

      {"id":"refs/heads/master"}

  </div>

*Example response representations:*

- <div>

  204 \[<a href="#" onclick="toggle(&#39;idm532023763536&#39;); return false;"><em><span id="link-idm532023763536">expand</span></em></a>\]

  </div>

  <div id="idm532023763536" class="toggle">

  The operation was successful

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532023765632&#39;); return false;"><em><span id="link-idm532023765632">expand</span></em></a>\]

  </div>

  <div id="idm532023765632" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to update the repository

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532023762880&#39;); return false;"><em><span id="link-idm532023762880">expand</span></em></a>\]

  </div>

  <div id="idm532023762880" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository does not exist.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/browse

###### Methods

<div class="methods">

<div class="method">

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/browse<span class="optional">?at</span><span class="optional">&type</span><span class="optional">&blame</span><span class="optional">&noContent</span>

*This is a [paged API](#paging-params)*. *This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Retrieve a page of content for a file path at a specified revision.

The authenticated user must have **REPO_READ** permission for the specified repository to call this resource.

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
<td><p><strong>at</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p>
<p>Default:</p></td>
<td><p>the commit ID or ref to retrieve the content for.</p></td>
</tr>
<tr>
<td><p><strong>type</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#boolean">boolean</a></em></p>
<p>Default: <code>false</code></p></td>
<td><p>if true only the type will be returned for the file path instead of the contents.</p></td>
</tr>
<tr>
<td><p><strong>blame</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p></td>
<td><p>if present the blame will be returned for the file as well.</p></td>
</tr>
<tr>
<td><p><strong>noContent</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p></td>
<td><p>if present and used with blame only the blame is retrieved instead of the contents.</p></td>
</tr>
</tbody>
</table>

*Example response representations:*

- <div>

  200 - application/json ([page](#paging-params)) \[<a href="#" onclick="toggle(&#39;idm532027344160&#39;); return false;"><em><span id="link-idm532027344160">expand</span></em></a>\]

  </div>

  <div id="idm532027344160" class="toggle">

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"start":0,"lines":[{"text":"print('hello world')"}]}

  A page of contents from a file.

  <div class="representation">

  </div>

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532027345488&#39;); return false;"><em><span id="link-idm532027345488">expand</span></em></a>\]

  </div>

  <div id="idm532027345488" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The path or until parameters were not supplied.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532027340304&#39;); return false;"><em><span id="link-idm532027340304">expand</span></em></a>\]

  </div>

  <div id="idm532027340304" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the repository.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532027340752&#39;); return false;"><em><span id="link-idm532027340752">expand</span></em></a>\]

  </div>

  <div id="idm532027340752" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The repository does not exist.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/browse/{path:.\*}

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **path** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the path of the file that is to be modified or created |

###### Methods

<div class="methods">

<div class="method">

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/browse/{path:.\*}<span class="optional">?at</span><span class="optional">&type</span><span class="optional">&blame</span><span class="optional">&noContent</span>

*This is a [paged API](#paging-params)*. *This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Retrieve a page of content for a file path at a specified revision.

The authenticated user must have **REPO_READ** permission for the specified repository to call this resource.

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
<td><p><strong>at</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p>
<p>Default:</p></td>
<td><p>the commit ID or ref to retrieve the content for.</p></td>
</tr>
<tr>
<td><p><strong>type</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#boolean">boolean</a></em></p>
<p>Default: <code>false</code></p></td>
<td><p>if true only the type will be returned for the file path instead of the contents.</p></td>
</tr>
<tr>
<td><p><strong>blame</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p></td>
<td><p>if present the blame will be returned for the file as well.</p></td>
</tr>
<tr>
<td><p><strong>noContent</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p></td>
<td><p>if present and used with blame only the blame is retrieved instead of the contents.</p></td>
</tr>
</tbody>
</table>

*Example response representations:*

- <div>

  200 - application/json ([page](#paging-params)) \[<a href="#" onclick="toggle(&#39;idm532027326240&#39;); return false;"><em><span id="link-idm532027326240">expand</span></em></a>\]

  </div>

  <div id="idm532027326240" class="toggle">

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"start":0,"lines":[{"text":"print('hello world')"}]}

  A page of contents from a file.

  <div class="representation">

  </div>

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532027327568&#39;); return false;"><em><span id="link-idm532027327568">expand</span></em></a>\]

  </div>

  <div id="idm532027327568" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The path or until parameters were not supplied.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532027321184&#39;); return false;"><em><span id="link-idm532027321184">expand</span></em></a>\]

  </div>

  <div id="idm532027321184" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the repository.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532027319904&#39;); return false;"><em><span id="link-idm532027319904">expand</span></em></a>\]

  </div>

  <div id="idm532027319904" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The repository does not exist.

  <div class="representation">

  </div>

  </div>

</div>

<div class="method">

#### PUT

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Update the content of `path`, on the given `repository` and `branch`.

This resource accepts PUT multipart form data, containing the file in a form-field named `content`.

An example [curl](http://curl.haxx.se/) request to update 'README.md' would be:

\
 curl -X PUT -u username:password -F content=@README.md  -F 'message=Updated using file-edit REST API'\
 -F branch=master -F  sourceCommitId=5636641a50b\
  http://example.com/rest/api/latest/projects/PROJECT_1/repos/repo_1/browse/README.md\
 

branch: the branch on which the `path` should be modified or created

content: the full content of the file at `path`

message: the message associated with this change, to be used as the commit message. Or null if the default message should be used.

sourceCommitId: the commit ID of the file before it was edited, used to identify if content has changed. Or null if this is a new file

The file can be updated or created on a new branch. In this case, the `sourceBranch` parameter should be provided to identify the starting point for the new branch and the `branch` parameter identifies the branch to create the new commit on.

*Example response representations:*

- <div>

  200 - application/json \[<a href="#" onclick="toggle(&#39;idm532027315840&#39;); return false;"><em><span id="link-idm532027315840">expand</span></em></a>\]

  </div>

  <div id="idm532027315840" class="toggle">

  ###### Example

      {"id":"abcdef0123abcdef4567abcdef8987abcdef6543","displayId":"abcdef0123a","author":{"name":"charlie","emailAddress":"charlie@example.com"},"authorTimestamp":1527228363490,"committer":{"name":"charlie","emailAddress":"charlie@example.com"},"committerTimestamp":1527228363490,"message":"WIP on feature 1","parents":[{"id":"abcdef0123abcdef4567abcdef8987abcdef6543","displayId":"abcdef0"}]}

  The newly created commit

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532027314720&#39;); return false;"><em><span id="link-idm532027314720">expand</span></em></a>\]

  </div>

  <div id="idm532027314720" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The branch or content parameters were not supplied.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532027311936&#39;); return false;"><em><span id="link-idm532027311936">expand</span></em></a>\]

  </div>

  <div id="idm532027311936" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user does not have write permission for the given repository

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532027309680&#39;); return false;"><em><span id="link-idm532027309680">expand</span></em></a>\]

  </div>

  <div id="idm532027309680" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The repository does not exist.

  <div class="representation">

  </div>

  </div>

- <div>

  409 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532027307312&#39;); return false;"><em><span id="link-idm532027307312">expand</span></em></a>\]

  </div>

  <div id="idm532027307312" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The file already exists when trying to create a file, or the given content does not modify the file, or the file has changed since the given sourceCommitId

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/changes

###### Methods

<div class="methods">

<div class="method">

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/changes<span class="optional">?since</span><span class="optional">&until</span>

*This is a [paged API](#paging-params)*. *This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Retrieve a page of changes made in a specified commit.

**Note:** The implementation will apply a hard cap ({@code page.max.changes}) and it is not possible to request subsequent content when that cap is exceeded.

The authenticated user must have **REPO_READ** permission for the specified repository to call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **since** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the commit to which `until` should be compared to produce a page of changes. If not specified the commit's first parent is assumed (if one exists) |
| **until** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the commit to retrieve changes for |

*Example response representations:*

- <div>

  200 - application/json ([page](#paging-params)) \[<a href="#" onclick="toggle(&#39;idm532025561264&#39;); return false;"><em><span id="link-idm532025561264">expand</span></em></a>\]

  </div>

  <div id="idm532025561264" class="toggle">

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"contentId":"abcdef0123abcdef4567abcdef8987abcdef6543","fromContentId":"bcdef0123abcdef4567abcdef8987abcdef6543a","path":{"components":["new","path","to","file.txt"],"parent":"new/path/to","name":"file.txt","extension":"txt","toString":"new/path/to/file.txt"},"executable":false,"percentUnchanged":98,"type":"MOVE","nodeType":"FILE","srcPath":{"components":["path","to","file.txt"],"parent":"path/to","name":"file.txt","extension":"txt","toString":"path/to/file.txt"},"srcExecutable":false,"links":{"self":[{"href":"http://link/to/restchange"}]}}],"start":0}

  A page of changes

  <div class="representation">

  </div>

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025559888&#39;); return false;"><em><span id="link-idm532025559888">expand</span></em></a>\]

  </div>

  <div id="idm532025559888" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The until parameter was not supplied

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025555536&#39;); return false;"><em><span id="link-idm532025555536">expand</span></em></a>\]

  </div>

  <div id="idm532025555536" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the repository.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025555984&#39;); return false;"><em><span id="link-idm532025555984">expand</span></em></a>\]

  </div>

  <div id="idm532025555984" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The repository or the since or until parameters supplied does not exist.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/commits

###### Methods

<div class="methods">

<div class="method">

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/commits<span class="optional">?followRenames</span><span class="optional">&ignoreMissing</span><span class="optional">&merges</span><span class="optional">&path</span><span class="optional">&since</span><span class="optional">&until</span><span class="optional">&withCounts</span>

*This is a [paged API](#paging-params)*. *This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Retrieve a page of commits from a given starting commit or "between" two commits. If no explicit commit is specified, the tip of the repository's default branch is assumed. commits may be identified by branch or tag name or by ID. A path may be supplied to restrict the returned commits to only those which affect that path.

The authenticated user must have **REPO_READ** permission for the specified repository to call this resource.

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
<td><p><strong>followRenames</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#boolean">boolean</a></em></p>
<p>Default: <code>false</code></p></td>
<td><p>if <code>true</code>, the commit history of the specified file will be followed past renames. Only valid for a path to a single file.</p></td>
</tr>
<tr>
<td><p><strong>ignoreMissing</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#boolean">boolean</a></em></p>
<p>Default: <code>false</code></p></td>
<td><p><code>true</code> to ignore missing commits, <code>false</code> otherwise</p></td>
</tr>
<tr>
<td><p><strong>merges</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p></td>
<td><p>if present, controls how merge commits should be filtered. Can be either <code>exclude</code>, to exclude merge commits, <code>include</code>, to include both merge commits and non-merge commits or <code>only</code>, to only return merge commits.</p></td>
</tr>
<tr>
<td><p><strong>path</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p></td>
<td><p>an optional path to filter commits by</p></td>
</tr>
<tr>
<td><p><strong>since</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p></td>
<td><p>the commit ID or ref (exclusively) to retrieve commits after</p></td>
</tr>
<tr>
<td><p><strong>until</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p></td>
<td><p>the commit ID (SHA1) or ref (inclusively) to retrieve commits before</p></td>
</tr>
<tr>
<td><p><strong>withCounts</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#boolean">boolean</a></em></p>
<p>Default: <code>false</code></p></td>
<td><p>optionally include the total number of commits and total number of unique authors</p></td>
</tr>
</tbody>
</table>

*Example response representations:*

- <div>

  200 - application/json ([page](#paging-params)) \[<a href="#" onclick="toggle(&#39;idm532027281760&#39;); return false;"><em><span id="link-idm532027281760">expand</span></em></a>\]

  </div>

  <div id="idm532027281760" class="toggle">

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"id":"def0123abcdef4567abcdef8987abcdef6543abc","displayId":"def0123abcd","author":{"name":"charlie","emailAddress":"charlie@example.com"},"authorTimestamp":1527228363490,"committer":{"name":"charlie","emailAddress":"charlie@example.com"},"committerTimestamp":1527228363490,"message":"More work on feature 1","parents":[{"id":"abcdef0123abcdef4567abcdef8987abcdef6543","displayId":"abcdef0"}]}],"start":0,"authorCount":1,"totalCount":1}

  A page of commits.

  <div class="representation">

  </div>

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532027280224&#39;); return false;"><em><span id="link-idm532027280224">expand</span></em></a>\]

  </div>

  <div id="idm532027280224" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  One of the supplied commit IDs or refs was invalid.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532027275888&#39;); return false;"><em><span id="link-idm532027275888">expand</span></em></a>\]

  </div>

  <div id="idm532027275888" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the repository.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532027272480&#39;); return false;"><em><span id="link-idm532027272480">expand</span></em></a>\]

  </div>

  <div id="idm532027272480" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The repository does not exist.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/commits/{commitId}

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **commitId** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the commit ID to retrieve |

###### Methods

<div class="methods">

<div class="method">

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/commits/{commitId}<span class="optional">?path</span>

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Retrieve a single commit *identified by its ID*\>. In general, that ID is a SHA1. <u>From 2.11, ref names like "refs/heads/master" are no longer accepted by this resource.</u>

The authenticated user must have **REPO_READ** permission for the specified repository to call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **path** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | an optional path to filter the commit by. If supplied the details returned *may not* be for the specified commit. Instead, starting from the specified commit, they will be the details for the first commit affecting the specified path. |

*Example response representations:*

- <div>

  200 - application/json (commit) \[<a href="#" onclick="toggle(&#39;idm532027267296&#39;); return false;"><em><span id="link-idm532027267296">expand</span></em></a>\]

  </div>

  <div id="idm532027267296" class="toggle">

  ###### Example

      {"id":"abcdef0123abcdef4567abcdef8987abcdef6543","displayId":"abcdef0123a","author":{"name":"charlie","emailAddress":"charlie@example.com"},"authorTimestamp":1527228363490,"committer":{"name":"charlie","emailAddress":"charlie@example.com"},"committerTimestamp":1527228363490,"message":"WIP on feature 1","parents":[{"id":"abcdef0123abcdef4567abcdef8987abcdef6543","displayId":"abcdef0"}]}

  A commit.

  <div class="representation">

  </div>

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532027263632&#39;); return false;"><em><span id="link-idm532027263632">expand</span></em></a>\]

  </div>

  <div id="idm532027263632" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The supplied commit ID was invalid.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532027260480&#39;); return false;"><em><span id="link-idm532027260480">expand</span></em></a>\]

  </div>

  <div id="idm532027260480" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the repository.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532027259200&#39;); return false;"><em><span id="link-idm532027259200">expand</span></em></a>\]

  </div>

  <div id="idm532027259200" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The repository does not exist.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/commits/{commitId}/changes

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **commitId** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the commit to retrieve changes for |

###### Methods

<div class="methods">

<div class="method">

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/commits/{commitId}/changes<span class="optional">?since</span><span class="optional">&withComments</span>

*This is a [paged API](#paging-params)*. *This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Retrieve a page of changes made in a specified commit.

**Note:** The implementation will apply a hard cap ({@code page.max.changes}) and it is not possible to request subsequent content when that cap is exceeded.

The authenticated user must have **REPO_READ** permission for the specified repository to call this resource.

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
<td><p><strong>since</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p></td>
<td><p>the commit to which <code>until</code> should be compared to produce a page of changes. If not specified the commit's first parent is assumed (if one exists)</p></td>
</tr>
<tr>
<td><p><strong>withComments</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#boolean">boolean</a></em></p>
<p>Default: <code>true</code></p></td>
<td><p>{@code true} to apply comment counts in the changes (the default); otherwise, {@code false} to stream changes without comment counts</p></td>
</tr>
</tbody>
</table>

*Example response representations:*

- <div>

  200 - application/json ([page](#paging-params)) \[<a href="#" onclick="toggle(&#39;idm532061681088&#39;); return false;"><em><span id="link-idm532061681088">expand</span></em></a>\]

  </div>

  <div id="idm532061681088" class="toggle">

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"contentId":"abcdef0123abcdef4567abcdef8987abcdef6543","fromContentId":"bcdef0123abcdef4567abcdef8987abcdef6543a","path":{"components":["new","path","to","file.txt"],"parent":"new/path/to","name":"file.txt","extension":"txt","toString":"new/path/to/file.txt"},"executable":false,"percentUnchanged":98,"type":"MOVE","nodeType":"FILE","srcPath":{"components":["path","to","file.txt"],"parent":"path/to","name":"file.txt","extension":"txt","toString":"path/to/file.txt"},"srcExecutable":false,"links":{"self":[{"href":"http://link/to/restchange"}]}}],"start":0}

  A page of changes

  <div class="representation">

  </div>

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061678480&#39;); return false;"><em><span id="link-idm532061678480">expand</span></em></a>\]

  </div>

  <div id="idm532061678480" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The until parameter was not supplied

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061682576&#39;); return false;"><em><span id="link-idm532061682576">expand</span></em></a>\]

  </div>

  <div id="idm532061682576" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the repository.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061673168&#39;); return false;"><em><span id="link-idm532061673168">expand</span></em></a>\]

  </div>

  <div id="idm532061673168" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The repository or the since or until parameters supplied does not exist.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/commits/{commitId}/comments

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **commitId** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the *full {@link Commit#getId() ID}* of the commit within the repository |

###### Methods

<div class="methods">

<div class="method">

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/commits/{commitId}/comments<span class="optional">?path</span><span class="optional">&since</span>

*This is a [paged API](#paging-params)*. *This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Retrieves the commit discussion comments that match the specified search criteria.

It is possible to retrieve commit discussion comments that are anchored to a range of commits by providing the {@code sinceId} that the comments anchored from.

The authenticated user must have **REPO_READ** permission for the repository that the commit is in to call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **path** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the path to the file on which comments were made |
| **since** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | For a merge commit, a parent can be provided to specify which diff the comments are on. For a commit range, a {@code sinceId} can be provided to specify where the comments are anchored from. |

*Example response representations:*

- <div>

  200 - application/json ([page](#paging-params)) \[<a href="#" onclick="toggle(&#39;idm532025943472&#39;); return false;"><em><span id="link-idm532025943472">expand</span></em></a>\]

  </div>

  <div id="idm532025943472" class="toggle">

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"id":101,"version":1,"title":"Talking Nerdy","description":"It’s a kludge, but put the tuple from the database in the cache.","state":"OPEN","open":true,"closed":false,"createdDate":1359075920,"updatedDate":1359085920,"fromRef":{"id":"refs/heads/feature-ABC-123","repository":{"slug":"my-repo","name":null,"project":{"key":"PRJ"}}},"toRef":{"id":"refs/heads/master","repository":{"slug":"my-repo","name":null,"project":{"key":"PRJ"}}},"locked":false,"author":{"user":{"name":"tom","emailAddress":"tom@example.com","id":115026,"displayName":"Tom","active":true,"slug":"tom","type":"NORMAL"},"role":"AUTHOR","approved":true,"status":"APPROVED"},"reviewers":[{"user":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"lastReviewedCommit":"7549846524f8aed2bd1c0249993ae1bf9d3c9998","role":"REVIEWER","approved":true,"status":"APPROVED"}],"participants":[{"user":{"name":"harry","emailAddress":"harry@example.com","id":99049120,"displayName":"Harry","active":true,"slug":"harry","type":"NORMAL"},"role":"PARTICIPANT","approved":true,"status":"APPROVED"},{"user":{"name":"dick","emailAddress":"dick@example.com","id":3083181,"displayName":"Dick","active":true,"slug":"dick","type":"NORMAL"},"role":"PARTICIPANT","approved":false,"status":"UNAPPROVED"}],"links":{"self":[{"href":"http://link/to/pullrequest"}]}}],"start":0}

  A page of comments that match the search criteria

  <div class="representation">

  </div>

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025942288&#39;); return false;"><em><span id="link-idm532025942288">expand</span></em></a>\]

  </div>

  <div id="idm532025942288" class="toggle">

  ###### Example

      {"errors":[{"context":"field_a","message":"A detailed validation error message for field_a.","exceptionName":null},{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The request was malformed.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025937184&#39;); return false;"><em><span id="link-idm532025937184">expand</span></em></a>\]

  </div>

  <div id="idm532025937184" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the comment

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025936256&#39;); return false;"><em><span id="link-idm532025936256">expand</span></em></a>\]

  </div>

  <div id="idm532025936256" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  Unable to find the supplied project, repository, or commit. The missing entity will be specified in the error details.

  <div class="representation">

  </div>

  </div>

</div>

<div class="method">

#### POST

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/commits/{commitId}/comments<span class="optional">?since</span>

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Add a new comment.

Comments can be added in a few places by setting different attributes:

General commit comment:

\
     {\
         "text": "An insightful general comment on a commit."\
     }\
     

Reply to a comment:

\
     {\
         "text": "A measured reply.",\
         "parent": {\
             "id": 1\
         }\
     }\
     

General file comment:

\
     {\
         "text": "An insightful general comment on a file.",\
         "anchor": {\
             "diffType": "COMMIT",\
             "fromHash": "6df3858eeb9a53a911cd17e66a9174d44ffb02cd",\
             "path": "path/to/file",\
             "srcPath": "path/to/file",\
             "toHash": "04c7c5c931b9418ca7b66f51fe934d0bd9b2ba4b"\
         }\
     }\
     

File line comment:

\
     {\
         "text": "A pithy comment on a particular line within a file.",\
         "anchor": {\
             "diffType": "COMMIT",\
             "line": 1,\
             "lineType": "CONTEXT",\
             "fileType": "FROM",\
             "fromHash": "6df3858eeb9a53a911cd17e66a9174d44ffb02cd",\
             "path": "path/to/file",\
             "srcPath": "path/to/file",\
             "toHash": "04c7c5c931b9418ca7b66f51fe934d0bd9b2ba4b"\
     }\
     }\
     

**Note: general file comments are an experimental feature and may change in the near future!**

For file and line comments, 'path' refers to the path of the file to which the comment should be applied and 'srcPath' refers to the path the that file used to have (only required for copies and moves). Also, fromHash and toHash refer to the sinceId / untilId (respectively) used to produce the diff on which the comment was added. Finally diffType refers to the type of diff the comment was added on.

For line comments, 'line' refers to the line in the diff that the comment should apply to. 'lineType' refers to the type of diff hunk, which can be:

- 'ADDED' - for an added line;
- 'REMOVED' - for a removed line; or
- 'CONTEXT' - for a line that was unmodified but is in the vicinity of the diff.

'fileType' refers to the file of the diff to which the anchor should be attached - which is of relevance when displaying the diff in a side-by-side way. Currently the supported values are:

- 'FROM' - the source file of the diff
- 'TO' - the destination file of the diff

If the current user is not a participant the user is added as one and updated to watch the commit.

The authenticated user must have **REPO_READ** permission for the repository that the commit is in to call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **since** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | For a merge commit, a parent can be provided to specify which diff the comments should be on. For a commit range, a {@code sinceId} can be provided to specify where the comments should be anchored from. |

*Example request representations:*

- <div>

  application/json \[<a href="#" onclick="toggle(&#39;idm532025929808&#39;); return false;"><em><span id="link-idm532025929808">expand</span></em></a>\]

  </div>

  <div id="idm532025929808" class="toggle">

  ###### Example

      {"text":"An insightful comment.","parent":{"id":1},"anchor":{"line":1,"lineType":"CONTEXT","fileType":"FROM","path":"path/to/file","srcPath":"path/to/file"}}

  </div>

*Example response representations:*

- <div>

  201 - application/json (comment) \[<a href="#" onclick="toggle(&#39;idm532025928128&#39;); return false;"><em><span id="link-idm532025928128">expand</span></em></a>\]

  </div>

  <div id="idm532025928128" class="toggle">

  ###### Example

      {"properties":{"key":"value"},"id":1,"version":1,"text":"A measured reply.","author":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"createdDate":1527228363421,"updatedDate":1527228363421,"comments":[{"properties":{"key":"value"},"id":1,"version":1,"text":"An insightful comment.","author":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"createdDate":1527228363411,"updatedDate":1527228363411,"comments":[],"tasks":[],"permittedOperations":{"editable":true,"deletable":true}}],"tasks":[],"permittedOperations":{"editable":true,"deletable":true}}

  The newly created comment.

  <div class="representation">

  </div>

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025927344&#39;); return false;"><em><span id="link-idm532025927344">expand</span></em></a>\]

  </div>

  <div id="idm532025927344" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The comment was not created due to a validation error.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532023809312&#39;); return false;"><em><span id="link-idm532023809312">expand</span></em></a>\]

  </div>

  <div id="idm532023809312" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the commit, create a comment or watch the commit.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532023806992&#39;); return false;"><em><span id="link-idm532023806992">expand</span></em></a>\]

  </div>

  <div id="idm532023806992" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  Unable to find the supplied project, repository, commit or parent comment. The missing entity will be specified in the error details.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/commits/{commitId}/comments/{commentId}

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **commitId** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the *full {@link Commit#getId() ID}* of the commit within the repository |
| **commentId** | *[long](http://www.w3.org/TR/xmlschema-2/#long)* | the ID of the comment to retrieve |
| **commitId** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the *full {@link Commit#getId() ID}* of the commit within the repository |

###### Methods

<div class="methods">

<div class="method">

#### GET

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Retrieves a commit discussion comment.

The authenticated user must have **REPO_READ** permission for the repository that the commit is in to call this resource.

*Example response representations:*

- <div>

  200 - application/json (comment) \[<a href="#" onclick="toggle(&#39;idm532023800832&#39;); return false;"><em><span id="link-idm532023800832">expand</span></em></a>\]

  </div>

  <div id="idm532023800832" class="toggle">

  ###### Example

      {"properties":{"key":"value"},"id":1,"version":1,"text":"A measured reply.","author":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"createdDate":1527228363421,"updatedDate":1527228363421,"comments":[{"properties":{"key":"value"},"id":1,"version":1,"text":"An insightful comment.","author":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"createdDate":1527228363411,"updatedDate":1527228363411,"comments":[],"tasks":[],"permittedOperations":{"editable":true,"deletable":true}}],"tasks":[],"permittedOperations":{"editable":true,"deletable":true}}

  The requested comment.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532023798160&#39;); return false;"><em><span id="link-idm532023798160">expand</span></em></a>\]

  </div>

  <div id="idm532023798160" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the comment

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532023795264&#39;); return false;"><em><span id="link-idm532023795264">expand</span></em></a>\]

  </div>

  <div id="idm532023795264" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  Unable to find the supplied project, repository, commit or comment. The missing entity will be specified in the error details.

  <div class="representation">

  </div>

  </div>

</div>

<div class="method">

#### DELETE

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/commits/{commitId}/comments/{commentId}<span class="optional">?version</span>

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Delete a commit comment. Anyone can delete their own comment. Only users with **REPO_ADMIN** and above may delete comments created by other users. Comments which have replies *may not be deleted*, regardless of the user's granted permissions.

The authenticated user must have **REPO_READ** permission for the repository that the commit is in to call this resource.

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
<td><p><strong>version</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#int">int</a></em></p>
<p>Default: <code>-1</code></p></td>
<td><p>The expected version of the comment. This must match the server's version of the comment or the delete will fail. To determine the current version of the comment, the comment should be fetched from the server prior to the delete. Look for the 'version' attribute in the returned JSON structure.</p></td>
</tr>
</tbody>
</table>

*Example response representations:*

- <div>

  204 \[<a href="#" onclick="toggle(&#39;idm532061946880&#39;); return false;"><em><span id="link-idm532061946880">expand</span></em></a>\]

  </div>

  <div id="idm532061946880" class="toggle">

  The operation was successful

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061949216&#39;); return false;"><em><span id="link-idm532061949216">expand</span></em></a>\]

  </div>

  <div id="idm532061949216" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to delete the comment.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061945504&#39;); return false;"><em><span id="link-idm532061945504">expand</span></em></a>\]

  </div>

  <div id="idm532061945504" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  Unable to find the supplied project, repository or commit. The missing entity will be specified in the error details.

  <div class="representation">

  </div>

  </div>

- <div>

  409 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061944208&#39;); return false;"><em><span id="link-idm532061944208">expand</span></em></a>\]

  </div>

  <div id="idm532061944208" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The comment has replies or the version supplied does not match the comment's current version.

  <div class="representation">

  </div>

  </div>

</div>

<div class="method">

#### PUT

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Update the text of a comment. Only the user who created a comment may update it.

**Note:** the supplied supplied JSON object must contain a `version` that must match the server's version of the comment or the update will fail. To determine the current version of the comment, the comment should be fetched from the server prior to the update. Look for the 'version' attribute in the returned JSON structure.

The authenticated user must have **REPO_READ** permission for the repository that the commit is in to call this resource.

*Example request representations:*

- <div>

  application/json \[<a href="#" onclick="toggle(&#39;idm532065502096&#39;); return false;"><em><span id="link-idm532065502096">expand</span></em></a>\]

  </div>

  <div id="idm532065502096" class="toggle">

  ###### Example

      {"version":0,"text":"A pithy comment."}

  </div>

*Example response representations:*

- <div>

  201 - application/json (comment) \[<a href="#" onclick="toggle(&#39;idm532065280912&#39;); return false;"><em><span id="link-idm532065280912">expand</span></em></a>\]

  </div>

  <div id="idm532065280912" class="toggle">

  ###### Example

      {"properties":{"key":"value"},"id":1,"version":1,"text":"A measured reply.","author":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"createdDate":1527228363421,"updatedDate":1527228363421,"comments":[{"properties":{"key":"value"},"id":1,"version":1,"text":"An insightful comment.","author":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"createdDate":1527228363411,"updatedDate":1527228363411,"comments":[],"tasks":[],"permittedOperations":{"editable":true,"deletable":true}}],"tasks":[],"permittedOperations":{"editable":true,"deletable":true}}

  The newly updated comment.

  <div class="representation">

  </div>

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532065011616&#39;); return false;"><em><span id="link-idm532065011616">expand</span></em></a>\]

  </div>

  <div id="idm532065011616" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The comment was not updated due to a validation error.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532065008816&#39;); return false;"><em><span id="link-idm532065008816">expand</span></em></a>\]

  </div>

  <div id="idm532065008816" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the commit, update the comment or watch the commit.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532065006576&#39;); return false;"><em><span id="link-idm532065006576">expand</span></em></a>\]

  </div>

  <div id="idm532065006576" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  Unable to find the supplied project, repository, commit or comment. The missing entity will be specified in the error details.

  <div class="representation">

  </div>

  </div>

- <div>

  409 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532065004960&#39;); return false;"><em><span id="link-idm532065004960">expand</span></em></a>\]

  </div>

  <div id="idm532065004960" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The comment version supplied does not match the current version.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/commits/{commitId}/diff

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **commitId** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* |  |

###### Methods

<div class="methods">

<div class="method">

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/commits/{commitId}/diff<span class="optional">?autoSrcPath</span><span class="optional">&contextLines</span><span class="optional">&since</span><span class="optional">&srcPath</span><span class="optional">&whitespace</span><span class="optional">&withComments</span>

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Retrieve the diff between two provided revisions.

**Note:** This resource is currently *not paged*. The server will internally apply a hard cap to the streamed lines, and it is not possible to request subsequent pages if that cap is exceeded. In the event that the cap is reached, the diff will be cut short and one or more {@code truncated} flags will be set to {@code true} on the {@code "segments"}, {@code "hunks"} and {@code "diffs"} properties, as well as the top-level object, in the returned JSON response.

The authenticated user must have **REPO_READ** permission for the specified repository to call this resource.

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
<td><p><strong>autoSrcPath</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#boolean">boolean</a></em></p>
<p>Default: <code>false</code></p></td>
<td><p>{@code true} to automatically try to find the source path when it's not provided, {@code false} otherwise. Requires the {@code path} to be provided.</p></td>
</tr>
<tr>
<td><p><strong>contextLines</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#int">int</a></em></p>
<p>Default: <code>-1</code></p></td>
<td><p>the number of context lines to include around added/removed lines in the diff</p></td>
</tr>
<tr>
<td><p><strong>since</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p></td>
<td><p>the base revision to diff from. If omitted the parent revision of the until revision is used</p></td>
</tr>
<tr>
<td><p><strong>srcPath</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p></td>
<td><p>the source path for the file, if it was copied, moved or renamed</p></td>
</tr>
<tr>
<td><p><strong>whitespace</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p></td>
<td><p>optional whitespace flag which can be set to {@code ignore-all}</p></td>
</tr>
<tr>
<td><p><strong>withComments</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#boolean">boolean</a></em></p>
<p>Default: <code>true</code></p></td>
<td><p>{@code true} to embed comments in the diff (the default); otherwise {@code false} to stream the diff without comments</p></td>
</tr>
</tbody>
</table>

*Example response representations:*

- <div>

  200 - application/json (diff) \[<a href="#" onclick="toggle(&#39;idm532061955648&#39;); return false;"><em><span id="link-idm532061955648">expand</span></em></a>\]

  </div>

  <div id="idm532061955648" class="toggle">

  ###### Example

      {"diffs":[{"source":{"components":["path","to","file.txt"],"parent":"path/to","name":"file.txt","extension":"txt","toString":"path/to/file.txt"},"destination":{"components":["path","to","file.txt"],"parent":"path/to","name":"file.txt","extension":"txt","toString":"path/to/file.txt"},"hunks":[{"sourceLine":1,"sourceSpan":1,"destinationLine":1,"destinationSpan":2,"segments":[{"type":"REMOVED","lines":[{"destination":1,"source":1,"line":"import sys","truncated":false}],"truncated":false},{"type":"ADDED","lines":[{"destination":1,"source":2,"line":"import re","truncated":false},{"destination":2,"source":3,"line":"import os","truncated":false}],"truncated":false}],"truncated":false}],"truncated":"true","contextLines":"10","fromHash":"a0f224fd7bd5f28ea5a752d41b9c9f6372fc6d9e","toHash":"dc93f22caadcde35daf5cc2cd65d2738c87e31ca","whiteSpace":"SHOW"}],"truncated":"true","contextLines":"10","fromHash":"a0f224fd7bd5f28ea5a752d41b9c9f6372fc6d9e","toHash":"dc93f22caadcde35daf5cc2cd65d2738c87e31ca","whiteSpace":"SHOW"}

  A diff between two revisions.

  <div class="representation">

  </div>

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061952976&#39;); return false;"><em><span id="link-idm532061952976">expand</span></em></a>\]

  </div>

  <div id="idm532061952976" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The until parameter was not supplied.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061952352&#39;); return false;"><em><span id="link-idm532061952352">expand</span></em></a>\]

  </div>

  <div id="idm532061952352" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the repository.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025422560&#39;); return false;"><em><span id="link-idm532025422560">expand</span></em></a>\]

  </div>

  <div id="idm532025422560" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The repository does not exist.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/commits/{commitId}/diff/{path:.\*}

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **commitId** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* |  |
| **path** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the path to the file which should be diffed (optional) |
| **commitId** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* |  |

###### Methods

<div class="methods">

<div class="method">

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/commits/{commitId}/diff/{path:.\*}<span class="optional">?autoSrcPath</span><span class="optional">&contextLines</span><span class="optional">&since</span><span class="optional">&srcPath</span><span class="optional">&whitespace</span><span class="optional">&withComments</span>

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Retrieve the diff between two provided revisions.

**Note:** This resource is currently *not paged*. The server will internally apply a hard cap to the streamed lines, and it is not possible to request subsequent pages if that cap is exceeded. In the event that the cap is reached, the diff will be cut short and one or more {@code truncated} flags will be set to {@code true} on the {@code "segments"}, {@code "hunks"} and {@code "diffs"} properties, as well as the top-level object, in the returned JSON response.

The authenticated user must have **REPO_READ** permission for the specified repository to call this resource.

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
<td><p><strong>autoSrcPath</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#boolean">boolean</a></em></p>
<p>Default: <code>false</code></p></td>
<td><p>{@code true} to automatically try to find the source path when it's not provided, {@code false} otherwise. Requires the {@code path} to be provided.</p></td>
</tr>
<tr>
<td><p><strong>contextLines</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#int">int</a></em></p>
<p>Default: <code>-1</code></p></td>
<td><p>the number of context lines to include around added/removed lines in the diff</p></td>
</tr>
<tr>
<td><p><strong>since</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p></td>
<td><p>the base revision to diff from. If omitted the parent revision of the until revision is used</p></td>
</tr>
<tr>
<td><p><strong>srcPath</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p></td>
<td><p>the source path for the file, if it was copied, moved or renamed</p></td>
</tr>
<tr>
<td><p><strong>whitespace</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p></td>
<td><p>optional whitespace flag which can be set to {@code ignore-all}</p></td>
</tr>
<tr>
<td><p><strong>withComments</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#boolean">boolean</a></em></p>
<p>Default: <code>true</code></p></td>
<td><p>{@code true} to embed comments in the diff (the default); otherwise {@code false} to stream the diff without comments</p></td>
</tr>
</tbody>
</table>

*Example response representations:*

- <div>

  200 - application/json (diff) \[<a href="#" onclick="toggle(&#39;idm532025411984&#39;); return false;"><em><span id="link-idm532025411984">expand</span></em></a>\]

  </div>

  <div id="idm532025411984" class="toggle">

  ###### Example

      {"diffs":[{"source":{"components":["path","to","file.txt"],"parent":"path/to","name":"file.txt","extension":"txt","toString":"path/to/file.txt"},"destination":{"components":["path","to","file.txt"],"parent":"path/to","name":"file.txt","extension":"txt","toString":"path/to/file.txt"},"hunks":[{"sourceLine":1,"sourceSpan":1,"destinationLine":1,"destinationSpan":2,"segments":[{"type":"REMOVED","lines":[{"destination":1,"source":1,"line":"import sys","truncated":false}],"truncated":false},{"type":"ADDED","lines":[{"destination":1,"source":2,"line":"import re","truncated":false},{"destination":2,"source":3,"line":"import os","truncated":false}],"truncated":false}],"truncated":false}],"truncated":"true","contextLines":"10","fromHash":"a0f224fd7bd5f28ea5a752d41b9c9f6372fc6d9e","toHash":"dc93f22caadcde35daf5cc2cd65d2738c87e31ca","whiteSpace":"SHOW"}],"truncated":"true","contextLines":"10","fromHash":"a0f224fd7bd5f28ea5a752d41b9c9f6372fc6d9e","toHash":"dc93f22caadcde35daf5cc2cd65d2738c87e31ca","whiteSpace":"SHOW"}

  A diff between two revisions.

  <div class="representation">

  </div>

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025411376&#39;); return false;"><em><span id="link-idm532025411376">expand</span></em></a>\]

  </div>

  <div id="idm532025411376" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The until parameter was not supplied.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025407440&#39;); return false;"><em><span id="link-idm532025407440">expand</span></em></a>\]

  </div>

  <div id="idm532025407440" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the repository.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025405680&#39;); return false;"><em><span id="link-idm532025405680">expand</span></em></a>\]

  </div>

  <div id="idm532025405680" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The repository does not exist.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/commits/{commitId}/watch

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **commitId** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the *full {@link Commit#getId() ID}* of the commit within the repository |

###### Methods

<div class="methods">

<div class="method">

#### POST

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Add the authenticated user as a watcher for the specified commit.

The authenticated user must have **REPO_READ** permission for the repository containing the commit to call this resource.

*Example response representations:*

- <div>

  204 \[<a href="#" onclick="toggle(&#39;idm532025441680&#39;); return false;"><em><span id="link-idm532025441680">expand</span></em></a>\]

  </div>

  <div id="idm532025441680" class="toggle">

  The user is now watching the commit.

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025443696&#39;); return false;"><em><span id="link-idm532025443696">expand</span></em></a>\]

  </div>

  <div id="idm532025443696" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the pull request.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025440320&#39;); return false;"><em><span id="link-idm532025440320">expand</span></em></a>\]

  </div>

  <div id="idm532025440320" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified project, repository or commit does not exist.

  <div class="representation">

  </div>

  </div>

</div>

<div class="method">

#### DELETE

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Remove the authenticated user as a watcher for the specified commit.

The authenticated user must have **REPO_READ** permission for the repository containing the commit to call this resource.

*Example response representations:*

- <div>

  204 \[<a href="#" onclick="toggle(&#39;idm532027215776&#39;); return false;"><em><span id="link-idm532027215776">expand</span></em></a>\]

  </div>

  <div id="idm532027215776" class="toggle">

  The user is no longer watching the commit.

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532063381968&#39;); return false;"><em><span id="link-idm532063381968">expand</span></em></a>\]

  </div>

  <div id="idm532063381968" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the pull request.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532027215168&#39;); return false;"><em><span id="link-idm532027215168">expand</span></em></a>\]

  </div>

  <div id="idm532027215168" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified project, repository or commit does not exist.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

Compare two commits or refs. \<p\> Each commit can be specified using either a commit ID, a qualified ref name or a unqualified ref name (the latter should be non-ambiguous).

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/compare/diff{path:.\*}

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **path** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the path to the file to diff (optional) |

###### Methods

<div class="methods">

<div class="method">

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/compare/diff{path:.\*}<span class="optional">?from</span><span class="optional">&to</span><span class="optional">&fromRepo</span><span class="optional">&srcPath</span><span class="optional">&contextLines</span><span class="optional">&whitespace</span>

*This is a [paged API](#paging-params)*. *This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Gets a diff of the changes available in the {@code from} commit but not in the {@code to} commit.

If either the {@code from} or {@code to} commit are not specified, they will be replaced by the default branch of their containing repository.

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
<td><p><strong>from</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p></td>
<td><p>the source commit (can be a partial/full commit ID or qualified/unqualified ref name)</p></td>
</tr>
<tr>
<td><p><strong>to</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p></td>
<td><p>the target commit (can be a partial/full commit ID or qualified/unqualified ref name)</p></td>
</tr>
<tr>
<td><p><strong>fromRepo</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p>
<p>Default:</p></td>
<td><p>an optional parameter specifying the source repository containing the source commit if that commit is not present in the current repository; the repository can be specified by either its ID <em>fromRepo=42</em> or by its project key plus its repo slug separated by a slash: <em>fromRepo=projectKey/repoSlug</em></p></td>
</tr>
<tr>
<td><p><strong>srcPath</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p></td>
<td></td>
</tr>
<tr>
<td><p><strong>contextLines</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#int">int</a></em></p>
<p>Default: <code>-1</code></p></td>
<td><p>an optional number of context lines to include around each added or removed lines in the diff</p></td>
</tr>
<tr>
<td><p><strong>whitespace</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p></td>
<td><p>an optional whitespace flag which can be set to <code>ignore-all</code></p></td>
</tr>
</tbody>
</table>

*Example response representations:*

- <div>

  200 - application/json ([page](#paging-params)) \[<a href="#" onclick="toggle(&#39;idm532025382656&#39;); return false;"><em><span id="link-idm532025382656">expand</span></em></a>\]

  </div>

  <div id="idm532025382656" class="toggle">

  ###### Example

      {"diffs":[{"source":{"components":["path","to","file.txt"],"parent":"path/to","name":"file.txt","extension":"txt","toString":"path/to/file.txt"},"destination":{"components":["path","to","file.txt"],"parent":"path/to","name":"file.txt","extension":"txt","toString":"path/to/file.txt"},"hunks":[{"sourceLine":1,"sourceSpan":1,"destinationLine":1,"destinationSpan":2,"segments":[{"type":"REMOVED","lines":[{"destination":1,"source":1,"line":"import sys","truncated":false}],"truncated":false},{"type":"ADDED","lines":[{"destination":1,"source":2,"line":"import re","truncated":false},{"destination":2,"source":3,"line":"import os","truncated":false}],"truncated":false}],"truncated":false}],"truncated":"true","contextLines":"10","fromHash":"a0f224fd7bd5f28ea5a752d41b9c9f6372fc6d9e","toHash":"dc93f22caadcde35daf5cc2cd65d2738c87e31ca","whiteSpace":"SHOW"}],"truncated":"true","contextLines":"10","fromHash":"a0f224fd7bd5f28ea5a752d41b9c9f6372fc6d9e","toHash":"dc93f22caadcde35daf5cc2cd65d2738c87e31ca","whiteSpace":"SHOW"}

  The diff of the changes.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025382528&#39;); return false;"><em><span id="link-idm532025382528">expand</span></em></a>\]

  </div>

  <div id="idm532025382528" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The source or target commit does not exist.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/compare/commits

###### Methods

<div class="methods">

<div class="method">

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/compare/commits<span class="optional">?from</span><span class="optional">&to</span><span class="optional">&fromRepo</span>

*This is a [paged API](#paging-params)*. *This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Gets the commits accessible from the {@code from} commit but not in the {@code to} commit.

If either the {@code from} or {@code to} commit are not specified, they will be replaced by the default branch of their containing repository.

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
<td><p><strong>from</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p></td>
<td><p>the source commit (can be a partial/full commit ID or qualified/unqualified ref name)</p></td>
</tr>
<tr>
<td><p><strong>to</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p></td>
<td><p>the target commit (can be a partial/full commit ID or qualified/unqualified ref name)</p></td>
</tr>
<tr>
<td><p><strong>fromRepo</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p>
<p>Default:</p></td>
<td><p>an optional parameter specifying the source repository containing the source commit if that commit is not present in the current repository; the repository can be specified by either its ID <em>fromRepo=42</em> or by its project key plus its repo slug separated by a slash: <em>fromRepo=projectKey/repoSlug</em></p></td>
</tr>
</tbody>
</table>

*Example response representations:*

- <div>

  200 - application/json ([page](#paging-params)) \[<a href="#" onclick="toggle(&#39;idm532025372224&#39;); return false;"><em><span id="link-idm532025372224">expand</span></em></a>\]

  </div>

  <div id="idm532025372224" class="toggle">

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"id":"def0123abcdef4567abcdef8987abcdef6543abc","displayId":"def0123abcd","author":{"name":"charlie","emailAddress":"charlie@example.com"},"authorTimestamp":1527228363490,"committer":{"name":"charlie","emailAddress":"charlie@example.com"},"committerTimestamp":1527228363490,"message":"More work on feature 1","parents":[{"id":"abcdef0123abcdef4567abcdef8987abcdef6543","displayId":"abcdef0"}]}],"start":0,"authorCount":1,"totalCount":1}

  A page of commits.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025372096&#39;); return false;"><em><span id="link-idm532025372096">expand</span></em></a>\]

  </div>

  <div id="idm532025372096" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The source or target commit does not exist.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/compare/changes

###### Methods

<div class="methods">

<div class="method">

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/compare/changes<span class="optional">?from</span><span class="optional">&to</span><span class="optional">&fromRepo</span>

*This is a [paged API](#paging-params)*. *This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Gets the file changes available in the {@code from} commit but not in the {@code to} commit.

If either the {@code from} or {@code to} commit are not specified, they will be replaced by the default branch of their containing repository.

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
<td><p><strong>from</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p></td>
<td><p>the source commit (can be a partial/full commit ID or qualified/unqualified ref name)</p></td>
</tr>
<tr>
<td><p><strong>to</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p></td>
<td><p>the target commit (can be a partial/full commit ID or qualified/unqualified ref name)</p></td>
</tr>
<tr>
<td><p><strong>fromRepo</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p>
<p>Default:</p></td>
<td><p>an optional parameter specifying the source repository containing the source commit if that commit is not present in the current repository; the repository can be specified by either its ID <em>fromRepo=42</em> or by its project key plus its repo slug separated by a slash: <em>fromRepo=projectKey/repoSlug</em></p></td>
</tr>
</tbody>
</table>

*Example response representations:*

- <div>

  200 - application/json ([page](#paging-params)) \[<a href="#" onclick="toggle(&#39;idm532025360832&#39;); return false;"><em><span id="link-idm532025360832">expand</span></em></a>\]

  </div>

  <div id="idm532025360832" class="toggle">

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"contentId":"abcdef0123abcdef4567abcdef8987abcdef6543","fromContentId":"bcdef0123abcdef4567abcdef8987abcdef6543a","path":{"components":["new","path","to","file.txt"],"parent":"new/path/to","name":"file.txt","extension":"txt","toString":"new/path/to/file.txt"},"executable":false,"percentUnchanged":98,"type":"MOVE","nodeType":"FILE","srcPath":{"components":["path","to","file.txt"],"parent":"path/to","name":"file.txt","extension":"txt","toString":"path/to/file.txt"},"srcExecutable":false,"links":{"self":[{"href":"http://link/to/restchange"}]}}],"start":0}

  A page of changes.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025357936&#39;); return false;"><em><span id="link-idm532025357936">expand</span></em></a>\]

  </div>

  <div id="idm532025357936" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The source or target commit does not exist.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/diff

###### Methods

<div class="methods">

<div class="method">

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/diff<span class="optional">?contextLines</span><span class="optional">&since</span><span class="optional">&srcPath</span><span class="optional">&until</span><span class="optional">&whitespace</span>

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Retrieve the diff for a specified file path between two provided revisions.

**Note:** This resource is currently *not paged*. The server will internally apply a hard cap to the streamed lines, and it is not possible to request subsequent pages if that cap is exceeded. In the event that the cap is reached, the diff will be cut short and one or more `truncated` flags will be set to `true` on the segments, hunks and diffs substructures in the returned JSON response.

The authenticated user must have **REPO_READ** permission for the specified repository to call this resource.

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
<td><p><strong>contextLines</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#int">int</a></em></p>
<p>Default: <code>-1</code></p></td>
<td><p>the number of context lines to include around added/removed lines in the diff</p></td>
</tr>
<tr>
<td><p><strong>since</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p></td>
<td><p>the base revision to diff from. If omitted the parent revision of the until revision is used</p></td>
</tr>
<tr>
<td><p><strong>srcPath</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p></td>
<td><p>the source path for the file, if it was copied, moved or renamed</p></td>
</tr>
<tr>
<td><p><strong>until</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p></td>
<td><p>the target revision to diff to (required)</p></td>
</tr>
<tr>
<td><p><strong>whitespace</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p></td>
<td><p>optional whitespace flag which can be set to <code>ignore-all</code></p></td>
</tr>
</tbody>
</table>

*Example response representations:*

- <div>

  200 - application/json (diff) \[<a href="#" onclick="toggle(&#39;idm532061662288&#39;); return false;"><em><span id="link-idm532061662288">expand</span></em></a>\]

  </div>

  <div id="idm532061662288" class="toggle">

  ###### Example

      {"diffs":[{"source":{"components":["path","to","file.txt"],"parent":"path/to","name":"file.txt","extension":"txt","toString":"path/to/file.txt"},"destination":{"components":["path","to","file.txt"],"parent":"path/to","name":"file.txt","extension":"txt","toString":"path/to/file.txt"},"hunks":[{"sourceLine":1,"sourceSpan":1,"destinationLine":1,"destinationSpan":2,"segments":[{"type":"REMOVED","lines":[{"destination":1,"source":1,"line":"import sys","truncated":false}],"truncated":false},{"type":"ADDED","lines":[{"destination":1,"source":2,"line":"import re","truncated":false},{"destination":2,"source":3,"line":"import os","truncated":false}],"truncated":false}],"truncated":false}],"truncated":"true","contextLines":"10","fromHash":"a0f224fd7bd5f28ea5a752d41b9c9f6372fc6d9e","toHash":"dc93f22caadcde35daf5cc2cd65d2738c87e31ca","whiteSpace":"SHOW"}],"truncated":"true","contextLines":"10","fromHash":"a0f224fd7bd5f28ea5a752d41b9c9f6372fc6d9e","toHash":"dc93f22caadcde35daf5cc2cd65d2738c87e31ca","whiteSpace":"SHOW"}

  A diff of a file path.

  <div class="representation">

  </div>

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061661824&#39;); return false;"><em><span id="link-idm532061661824">expand</span></em></a>\]

  </div>

  <div id="idm532061661824" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The path or until parameters were not supplied.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061663360&#39;); return false;"><em><span id="link-idm532061663360">expand</span></em></a>\]

  </div>

  <div id="idm532061663360" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the repository.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061654944&#39;); return false;"><em><span id="link-idm532061654944">expand</span></em></a>\]

  </div>

  <div id="idm532061654944" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The repository does not exist.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/diff/{path:.\*}

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **path** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the path to the file which should be diffed (required) |

###### Methods

<div class="methods">

<div class="method">

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/diff/{path:.\*}<span class="optional">?contextLines</span><span class="optional">&since</span><span class="optional">&srcPath</span><span class="optional">&until</span><span class="optional">&whitespace</span>

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Retrieve the diff for a specified file path between two provided revisions.

**Note:** This resource is currently *not paged*. The server will internally apply a hard cap to the streamed lines, and it is not possible to request subsequent pages if that cap is exceeded. In the event that the cap is reached, the diff will be cut short and one or more `truncated` flags will be set to `true` on the segments, hunks and diffs substructures in the returned JSON response.

The authenticated user must have **REPO_READ** permission for the specified repository to call this resource.

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
<td><p><strong>contextLines</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#int">int</a></em></p>
<p>Default: <code>-1</code></p></td>
<td><p>the number of context lines to include around added/removed lines in the diff</p></td>
</tr>
<tr>
<td><p><strong>since</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p></td>
<td><p>the base revision to diff from. If omitted the parent revision of the until revision is used</p></td>
</tr>
<tr>
<td><p><strong>srcPath</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p></td>
<td><p>the source path for the file, if it was copied, moved or renamed</p></td>
</tr>
<tr>
<td><p><strong>until</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p></td>
<td><p>the target revision to diff to (required)</p></td>
</tr>
<tr>
<td><p><strong>whitespace</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p></td>
<td><p>optional whitespace flag which can be set to <code>ignore-all</code></p></td>
</tr>
</tbody>
</table>

*Example response representations:*

- <div>

  200 - application/json (diff) \[<a href="#" onclick="toggle(&#39;idm532061644064&#39;); return false;"><em><span id="link-idm532061644064">expand</span></em></a>\]

  </div>

  <div id="idm532061644064" class="toggle">

  ###### Example

      {"diffs":[{"source":{"components":["path","to","file.txt"],"parent":"path/to","name":"file.txt","extension":"txt","toString":"path/to/file.txt"},"destination":{"components":["path","to","file.txt"],"parent":"path/to","name":"file.txt","extension":"txt","toString":"path/to/file.txt"},"hunks":[{"sourceLine":1,"sourceSpan":1,"destinationLine":1,"destinationSpan":2,"segments":[{"type":"REMOVED","lines":[{"destination":1,"source":1,"line":"import sys","truncated":false}],"truncated":false},{"type":"ADDED","lines":[{"destination":1,"source":2,"line":"import re","truncated":false},{"destination":2,"source":3,"line":"import os","truncated":false}],"truncated":false}],"truncated":false}],"truncated":"true","contextLines":"10","fromHash":"a0f224fd7bd5f28ea5a752d41b9c9f6372fc6d9e","toHash":"dc93f22caadcde35daf5cc2cd65d2738c87e31ca","whiteSpace":"SHOW"}],"truncated":"true","contextLines":"10","fromHash":"a0f224fd7bd5f28ea5a752d41b9c9f6372fc6d9e","toHash":"dc93f22caadcde35daf5cc2cd65d2738c87e31ca","whiteSpace":"SHOW"}

  A diff of a file path.

  <div class="representation">

  </div>

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061640608&#39;); return false;"><em><span id="link-idm532061640608">expand</span></em></a>\]

  </div>

  <div id="idm532061640608" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The path or until parameters were not supplied.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061642880&#39;); return false;"><em><span id="link-idm532061642880">expand</span></em></a>\]

  </div>

  <div id="idm532061642880" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the repository.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061636192&#39;); return false;"><em><span id="link-idm532061636192">expand</span></em></a>\]

  </div>

  <div id="idm532061636192" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The repository does not exist.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/files

###### Methods

<div class="methods">

<div class="method">

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/files<span class="optional">?at</span>

*This is a [paged API](#paging-params)*. *This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Retrieve a page of files from particular directory of a repository. The search is done recursively, so all files from any sub-directory of the specified directory will be returned.

The authenticated user must have **REPO_READ** permission for the specified repository to call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **at** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the commit ID or ref (e.g. a branch or tag) to list the files at. If not specified the default branch will be used instead. |

*Example response representations:*

- <div>

  200 - application/json ([page](#paging-params)) \[<a href="#" onclick="toggle(&#39;idm532026548208&#39;); return false;"><em><span id="link-idm532026548208">expand</span></em></a>\]

  </div>

  <div id="idm532026548208" class="toggle">

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":["path/to/file.txt"],"start":0}

  A page of files.

  <div class="representation">

  </div>

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026545408&#39;); return false;"><em><span id="link-idm532026545408">expand</span></em></a>\]

  </div>

  <div id="idm532026545408" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The path requested is not a directory at the supplied commit.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026543168&#39;); return false;"><em><span id="link-idm532026543168">expand</span></em></a>\]

  </div>

  <div id="idm532026543168" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the repository.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026541600&#39;); return false;"><em><span id="link-idm532026541600">expand</span></em></a>\]

  </div>

  <div id="idm532026541600" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The path requested does not exist at the supplied commit.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/files/{path:.\*}

###### resource-wide template parameters

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
<td><p><strong>path</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p>
<p>Default:</p></td>
<td><p>the directory to list files for.</p></td>
</tr>
</tbody>
</table>

###### Methods

<div class="methods">

<div class="method">

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/files/{path:.\*}<span class="optional">?at</span>

*This is a [paged API](#paging-params)*. *This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Retrieve a page of files from particular directory of a repository. The search is done recursively, so all files from any sub-directory of the specified directory will be returned.

The authenticated user must have **REPO_READ** permission for the specified repository to call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **at** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the commit ID or ref (e.g. a branch or tag) to list the files at. If not specified the default branch will be used instead. |

*Example response representations:*

- <div>

  200 - application/json ([page](#paging-params)) \[<a href="#" onclick="toggle(&#39;idm532026534288&#39;); return false;"><em><span id="link-idm532026534288">expand</span></em></a>\]

  </div>

  <div id="idm532026534288" class="toggle">

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":["path/to/file.txt"],"start":0}

  A page of files.

  <div class="representation">

  </div>

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026535344&#39;); return false;"><em><span id="link-idm532026535344">expand</span></em></a>\]

  </div>

  <div id="idm532026535344" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The path requested is not a directory at the supplied commit.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026529120&#39;); return false;"><em><span id="link-idm532026529120">expand</span></em></a>\]

  </div>

  <div id="idm532026529120" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the repository.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026526832&#39;); return false;"><em><span id="link-idm532026526832">expand</span></em></a>\]

  </div>

  <div id="idm532026526832" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The path requested does not exist at the supplied commit.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/last-modified

###### Methods

<div class="methods">

<div class="method">

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/last-modified<span class="optional">?at</span>

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Streams files in the requested `path` with the last commit to modify each file. Commit modifications are traversed starting from the `at` commit or, if not specified, from the tip of the default branch.

Unless the repository is public, the authenticated user must have **REPO_READ** access to call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **at** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the commit to use as the starting point when listing files and calculating modifications |

*Example response representations:*

- <div>

  200 - application/json (modifications) \[<a href="#" onclick="toggle(&#39;idm532026371440&#39;); return false;"><em><span id="link-idm532026371440">expand</span></em></a>\]

  </div>

  <div id="idm532026371440" class="toggle">

  ###### Example

      {"files":{"pom.xml":{"id":"def0123abcdef4567abcdef8987abcdef6543abc","displayId":"def0123abcd","author":{"name":"charlie","emailAddress":"charlie@example.com"},"authorTimestamp":1527228363490,"committer":{"name":"charlie","emailAddress":"charlie@example.com"},"committerTimestamp":1527228363490,"message":"More work on feature 1","parents":[{"id":"abcdef0123abcdef4567abcdef8987abcdef6543","displayId":"abcdef0"}]},"README.md":{"id":"abcdef0123abcdef4567abcdef8987abcdef6543","displayId":"abcdef0123a","author":{"name":"charlie","emailAddress":"charlie@example.com"},"authorTimestamp":1527228363490,"committer":{"name":"charlie","emailAddress":"charlie@example.com"},"committerTimestamp":1527228363490,"message":"WIP on feature 1","parents":[{"id":"abcdef0123abcdef4567abcdef8987abcdef6543","displayId":"abcdef0"}]}},"latestCommit":{"id":"def0123abcdef4567abcdef8987abcdef6543abc","displayId":"def0123abcd","author":{"name":"charlie","emailAddress":"charlie@example.com"},"authorTimestamp":1527228363490,"committer":{"name":"charlie","emailAddress":"charlie@example.com"},"committerTimestamp":1527228363490,"message":"More work on feature 1","parents":[{"id":"abcdef0123abcdef4567abcdef8987abcdef6543","displayId":"abcdef0"}]}}

  A map of files to the last commit that modified them, and the latest commit to update the requested path.

  <div class="representation">

  </div>

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026370048&#39;); return false;"><em><span id="link-idm532026370048">expand</span></em></a>\]

  </div>

  <div id="idm532026370048" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  No `at` commit was specified. When streaming modifications, an explicit starting commit must be supplied.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026367312&#39;); return false;"><em><span id="link-idm532026367312">expand</span></em></a>\]

  </div>

  <div id="idm532026367312" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the repository.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026363952&#39;); return false;"><em><span id="link-idm532026363952">expand</span></em></a>\]

  </div>

  <div id="idm532026363952" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The repository does not exist or does not contain the `at` commit, or the `at` commit does not contain the requested path.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/last-modified/{path:.\*}

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **path** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the path within the repository whose files should be streamed |

###### Methods

<div class="methods">

<div class="method">

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/last-modified/{path:.\*}<span class="optional">?at</span>

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Streams files in the requested `path` with the last commit to modify each file. Commit modifications are traversed starting from the `at` commit or, if not specified, from the tip of the default branch.

Unless the repository is public, the authenticated user must have **REPO_READ** access to call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **at** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the commit to use as the starting point when listing files and calculating modifications |

*Example response representations:*

- <div>

  200 - application/json (modifications) \[<a href="#" onclick="toggle(&#39;idm532026358480&#39;); return false;"><em><span id="link-idm532026358480">expand</span></em></a>\]

  </div>

  <div id="idm532026358480" class="toggle">

  ###### Example

      {"files":{"pom.xml":{"id":"def0123abcdef4567abcdef8987abcdef6543abc","displayId":"def0123abcd","author":{"name":"charlie","emailAddress":"charlie@example.com"},"authorTimestamp":1527228363490,"committer":{"name":"charlie","emailAddress":"charlie@example.com"},"committerTimestamp":1527228363490,"message":"More work on feature 1","parents":[{"id":"abcdef0123abcdef4567abcdef8987abcdef6543","displayId":"abcdef0"}]},"README.md":{"id":"abcdef0123abcdef4567abcdef8987abcdef6543","displayId":"abcdef0123a","author":{"name":"charlie","emailAddress":"charlie@example.com"},"authorTimestamp":1527228363490,"committer":{"name":"charlie","emailAddress":"charlie@example.com"},"committerTimestamp":1527228363490,"message":"WIP on feature 1","parents":[{"id":"abcdef0123abcdef4567abcdef8987abcdef6543","displayId":"abcdef0"}]}},"latestCommit":{"id":"def0123abcdef4567abcdef8987abcdef6543abc","displayId":"def0123abcd","author":{"name":"charlie","emailAddress":"charlie@example.com"},"authorTimestamp":1527228363490,"committer":{"name":"charlie","emailAddress":"charlie@example.com"},"committerTimestamp":1527228363490,"message":"More work on feature 1","parents":[{"id":"abcdef0123abcdef4567abcdef8987abcdef6543","displayId":"abcdef0"}]}}

  A map of files to the last commit that modified them, and the latest commit to update the requested path.

  <div class="representation">

  </div>

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026357008&#39;); return false;"><em><span id="link-idm532026357008">expand</span></em></a>\]

  </div>

  <div id="idm532026357008" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  No `at` commit was specified. When streaming modifications, an explicit starting commit must be supplied.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026354384&#39;); return false;"><em><span id="link-idm532026354384">expand</span></em></a>\]

  </div>

  <div id="idm532026354384" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the repository.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026350784&#39;); return false;"><em><span id="link-idm532026350784">expand</span></em></a>\]

  </div>

  <div id="idm532026350784" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The repository does not exist or does not contain the `at` commit, or the `at` commit does not contain the requested path.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/participants

###### Methods

<div class="methods">

<div class="method">

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/participants<span class="optional">?direction</span><span class="optional">&filter</span><span class="optional">&role</span>

*This is a [paged API](#paging-params)*. *This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Retrieve a page of participant users for all the pull requests to or from the specified repository.

Optionally clients can specify following filters.

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
<td><p><strong>direction</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p>
<p>Default: <code>incoming</code></p></td>
<td><p>(optional, defaults to <strong>INCOMING</strong>) the direction relative to the specified repository. Either <strong>INCOMING</strong> or <strong>OUTGOING</strong>.</p></td>
</tr>
<tr>
<td><p><strong>filter</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p></td>
<td><p>(optional) return only users, whose username, name or email address <em>contain</em> the {@code filter} value</p></td>
</tr>
<tr>
<td><p><strong>role</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p></td>
<td><p>(optional) The role associated with the pull request participant. This must be one of {@code AUTHOR}, {@code REVIEWER}, or{@code PARTICIPANT}</p></td>
</tr>
</tbody>
</table>

*Example response representations:*

- <div>

  200 - application/json ([page](#paging-params)) \[<a href="#" onclick="toggle(&#39;idm532025435680&#39;); return false;"><em><span id="link-idm532025435680">expand</span></em></a>\]

  </div>

  <div id="idm532025435680" class="toggle">

  ###### Example

      {"name":"charlie","emailAddress":"charlie@example.com"}

  A page of users that match the search criteria.

  <div class="representation">

  </div>

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025432416&#39;); return false;"><em><span id="link-idm532025432416">expand</span></em></a>\]

  </div>

  <div id="idm532025432416" class="toggle">

  ###### Example

      {"errors":[{"context":"field_a","message":"A detailed validation error message for field_a.","exceptionName":null},{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The request was malformed.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025434368&#39;); return false;"><em><span id="link-idm532025434368">expand</span></em></a>\]

  </div>

  <div id="idm532025434368" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the specified repository.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025426880&#39;); return false;"><em><span id="link-idm532025426880">expand</span></em></a>\]

  </div>

  <div id="idm532025426880" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository does not exist.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/permissions/groups

###### Methods

<div class="methods">

<div class="method">

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/permissions/groups<span class="optional">?filter</span>

*This is a [paged API](#paging-params)*. *This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Retrieve a page of groups that have been granted at least one permission for the specified repository.

The authenticated user must have **REPO_ADMIN** permission for the specified repository or a higher project or global permission to call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **filter** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | if specified only group names containing the supplied string will be returned |

*Example response representations:*

- <div>

  200 - application/json ([page](#paging-params)) \[<a href="#" onclick="toggle(&#39;idm532064570608&#39;); return false;"><em><span id="link-idm532064570608">expand</span></em></a>\]

  </div>

  <div id="idm532064570608" class="toggle">

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"group":{"name":"group_a"},"permission":"ADMIN"}],"start":0}

  A page of groups and their highest permissions for the specified repository.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532064568224&#39;); return false;"><em><span id="link-idm532064568224">expand</span></em></a>\]

  </div>

  <div id="idm532064568224" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user is not a repository administrator for the specified repository.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532064565984&#39;); return false;"><em><span id="link-idm532064565984">expand</span></em></a>\]

  </div>

  <div id="idm532064565984" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository does not exist.

  <div class="representation">

  </div>

  </div>

</div>

<div class="method">

#### PUT

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/permissions/groups<span class="optional">?permission</span><span class="optional">&name</span>

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Promote or demote a group's permission level for the specified repository. Available repository permissions are:

- REPO_READ
- REPO_WRITE
- REPO_ADMIN

See the [Bitbucket Server documentation](https://confluence.atlassian.com/display/BitbucketServer/Using+repository+permissions) for a detailed explanation of what each permission entails.

The authenticated user must have **REPO_ADMIN** permission for the specified repository or a higher project or global permission to call this resource. In addition, a user may not demote a group's permission level if their own permission level would be reduced as a result.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **permission** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the permission to grant |
| **name** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the names of the groups |

*Example response representations:*

- <div>

  204 \[<a href="#" onclick="toggle(&#39;idm532064554672&#39;); return false;"><em><span id="link-idm532064554672">expand</span></em></a>\]

  </div>

  <div id="idm532064554672" class="toggle">

  The requested permission was granted.

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532064561072&#39;); return false;"><em><span id="link-idm532064561072">expand</span></em></a>\]

  </div>

  <div id="idm532064561072" class="toggle">

  ###### Example

      {"errors":[{"context":"field_a","message":"A detailed validation error message for field_a.","exceptionName":null},{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The request was malformed or the specified permission does not exist.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532064557696&#39;); return false;"><em><span id="link-idm532064557696">expand</span></em></a>\]

  </div>

  <div id="idm532064557696" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user is not an administrator for the specified repository.

  <div class="representation">

  </div>

  </div>

- <div>

  403 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532064553888&#39;); return false;"><em><span id="link-idm532064553888">expand</span></em></a>\]

  </div>

  <div id="idm532064553888" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The action was disallowed as it would reduce the currently authenticated user's permission level.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532064552656&#39;); return false;"><em><span id="link-idm532064552656">expand</span></em></a>\]

  </div>

  <div id="idm532064552656" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository or group does not exist.

  <div class="representation">

  </div>

  </div>

</div>

<div class="method">

#### DELETE

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/permissions/groups<span class="optional">?name</span>

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Revoke all permissions for the specified repository for a group.

The authenticated user must have **REPO_ADMIN** permission for the specified repository or a higher project or global permission to call this resource.

In addition, a user may not revoke a group's permissions if it will reduce their own permission level.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **name** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the name of the group |

*Example response representations:*

- <div>

  204 \[<a href="#" onclick="toggle(&#39;idm532064545824&#39;); return false;"><em><span id="link-idm532064545824">expand</span></em></a>\]

  </div>

  <div id="idm532064545824" class="toggle">

  All repository permissions were revoked from the group for the specified repository.

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532064546960&#39;); return false;"><em><span id="link-idm532064546960">expand</span></em></a>\]

  </div>

  <div id="idm532064546960" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user is not an administrator of the specified repository.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532064543520&#39;); return false;"><em><span id="link-idm532064543520">expand</span></em></a>\]

  </div>

  <div id="idm532064543520" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository or group does not exist.

  <div class="representation">

  </div>

  </div>

- <div>

  409 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532064542592&#39;); return false;"><em><span id="link-idm532064542592">expand</span></em></a>\]

  </div>

  <div id="idm532064542592" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The action was disallowed as it would reduce the currently authenticated user's permission level.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/permissions/groups/none

###### Methods

<div class="methods">

<div class="method">

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/permissions/groups/none<span class="optional">?filter</span>

*This is a [paged API](#paging-params)*. *This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Retrieve a page of groups that have no granted permissions for the specified repository.

The authenticated user must have **REPO_ADMIN** permission for the specified repository or a higher project or global permission to call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **filter** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | if specified only group names containing the supplied string will be returned |

*Example response representations:*

- <div>

  200 - application/json ([page](#paging-params)) \[<a href="#" onclick="toggle(&#39;idm532064535968&#39;); return false;"><em><span id="link-idm532064535968">expand</span></em></a>\]

  </div>

  <div id="idm532064535968" class="toggle">

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"name":"group-a","deletable":true}],"start":0}

  A page of groups that have not been granted any permissions for the specified repository.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532064533040&#39;); return false;"><em><span id="link-idm532064533040">expand</span></em></a>\]

  </div>

  <div id="idm532064533040" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user is not a repository administrator for the specified repository.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532064531408&#39;); return false;"><em><span id="link-idm532064531408">expand</span></em></a>\]

  </div>

  <div id="idm532064531408" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository does not exist.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/permissions/users

###### Methods

<div class="methods">

<div class="method">

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/permissions/users<span class="optional">?filter</span>

*This is a [paged API](#paging-params)*. *This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Retrieve a page of users that have been granted at least one permission for the specified repository.

The authenticated user must have **REPO_ADMIN** permission for the specified repository or a higher project or global permission to call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **filter** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | if specified only group names containing the supplied string will be returned |

*Example response representations:*

- <div>

  200 - application/json ([page](#paging-params)) \[<a href="#" onclick="toggle(&#39;idm532064525808&#39;); return false;"><em><span id="link-idm532064525808">expand</span></em></a>\]

  </div>

  <div id="idm532064525808" class="toggle">

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"user":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"permission":"ADMIN"}],"start":0}

  A page of users and their highest permissions for the specified repository.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532064524480&#39;); return false;"><em><span id="link-idm532064524480">expand</span></em></a>\]

  </div>

  <div id="idm532064524480" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user is not a repository administrator for the specified repository.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532064520176&#39;); return false;"><em><span id="link-idm532064520176">expand</span></em></a>\]

  </div>

  <div id="idm532064520176" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository does not exist.

  <div class="representation">

  </div>

  </div>

</div>

<div class="method">

#### PUT

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/permissions/users<span class="optional">?name</span><span class="optional">&permission</span>

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Promote or demote a user's permission level for the specified repository. Available repository permissions are:

- REPO_READ
- REPO_WRITE
- REPO_ADMIN

See the [Bitbucket Server documentation](https://confluence.atlassian.com/display/BitbucketServer/Using+repository+permissions) for a detailed explanation of what each permission entails.

The authenticated user must have **REPO_ADMIN** permission for the specified repository or a higher project or global permission to call this resource. In addition, a user may not reduce their own permission level unless they have a project or global permission that already implies that permission.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **name** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the names of the users |
| **permission** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the permission to grant |

*Example response representations:*

- <div>

  204 \[<a href="#" onclick="toggle(&#39;idm532064510256&#39;); return false;"><em><span id="link-idm532064510256">expand</span></em></a>\]

  </div>

  <div id="idm532064510256" class="toggle">

  The requested permission was granted.

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532064514240&#39;); return false;"><em><span id="link-idm532064514240">expand</span></em></a>\]

  </div>

  <div id="idm532064514240" class="toggle">

  ###### Example

      {"errors":[{"context":"field_a","message":"A detailed validation error message for field_a.","exceptionName":null},{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The request was malformed or the specified permission does not exist.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532064512128&#39;); return false;"><em><span id="link-idm532064512128">expand</span></em></a>\]

  </div>

  <div id="idm532064512128" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user is not an administrator for the specified repository.

  <div class="representation">

  </div>

  </div>

- <div>

  403 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532064508352&#39;); return false;"><em><span id="link-idm532064508352">expand</span></em></a>\]

  </div>

  <div id="idm532064508352" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The action was disallowed as it would reduce the currently authenticated user's permission level.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532064507216&#39;); return false;"><em><span id="link-idm532064507216">expand</span></em></a>\]

  </div>

  <div id="idm532064507216" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository or user does not exist.

  <div class="representation">

  </div>

  </div>

</div>

<div class="method">

#### DELETE

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/permissions/users<span class="optional">?name</span>

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Revoke all permissions for the specified repository for a user.

The authenticated user must have **REPO_ADMIN** permission for the specified repository or a higher project or global permission to call this resource.

In addition, a user may not revoke their own repository permissions if they do not have a higher project or global permission.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **name** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the name of the user |

*Example response representations:*

- <div>

  204 \[<a href="#" onclick="toggle(&#39;idm532064500224&#39;); return false;"><em><span id="link-idm532064500224">expand</span></em></a>\]

  </div>

  <div id="idm532064500224" class="toggle">

  All repository permissions were revoked from the user for the specified repository.

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532064501344&#39;); return false;"><em><span id="link-idm532064501344">expand</span></em></a>\]

  </div>

  <div id="idm532064501344" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user is not an administrator of the specified repository.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532064497920&#39;); return false;"><em><span id="link-idm532064497920">expand</span></em></a>\]

  </div>

  <div id="idm532064497920" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository or group does not exist.

  <div class="representation">

  </div>

  </div>

- <div>

  409 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532064496992&#39;); return false;"><em><span id="link-idm532064496992">expand</span></em></a>\]

  </div>

  <div id="idm532064496992" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The action was disallowed as it would reduce the currently authenticated user's permission level.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/permissions/users/none

###### Methods

<div class="methods">

<div class="method">

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/permissions/users/none<span class="optional">?filter</span>

*This is a [paged API](#paging-params)*. *This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Retrieve a page of *licensed* users that have no granted permissions for the specified repository.

The authenticated user must have **REPO_ADMIN** permission for the specified repository or a higher project or global permission to call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **filter** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | if specified only group names containing the supplied string will be returned |

*Example response representations:*

- <div>

  200 - application/json ([page](#paging-params)) \[<a href="#" onclick="toggle(&#39;idm532064490624&#39;); return false;"><em><span id="link-idm532064490624">expand</span></em></a>\]

  </div>

  <div id="idm532064490624" class="toggle">

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"name":"group-a","deletable":true}],"start":0}

  A page of users that have not been granted any permissions for the specified repository.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532023636096&#39;); return false;"><em><span id="link-idm532023636096">expand</span></em></a>\]

  </div>

  <div id="idm532023636096" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user is not a repository administrator for the specified repository.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532023633760&#39;); return false;"><em><span id="link-idm532023633760">expand</span></em></a>\]

  </div>

  <div id="idm532023633760" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository does not exist.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests

###### Methods

<div class="methods">

<div class="method">

#### POST

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Create a new pull request between two branches. The branches may be in the same repository, or different ones. When using different repositories, they must still be in the same {@link Repository#getHierarchyId() hierarchy}.

The authenticated user must have **REPO_READ** permission for the "from" and "to"repositories to call this resource.

*Example request representations:*

- <div>

  application/json \[<a href="#" onclick="toggle(&#39;idm532061890224&#39;); return false;"><em><span id="link-idm532061890224">expand</span></em></a>\]

  </div>

  <div id="idm532061890224" class="toggle">

  ###### Example

      {"title":"Talking Nerdy","description":"It’s a kludge, but put the tuple from the database in the cache.","state":"OPEN","open":true,"closed":false,"fromRef":{"id":"refs/heads/feature-ABC-123","repository":{"slug":"my-repo","name":null,"project":{"key":"PRJ"}}},"toRef":{"id":"refs/heads/master","repository":{"slug":"my-repo","name":null,"project":{"key":"PRJ"}}},"locked":false,"reviewers":[{"user":{"name":"charlie"}}]}

  </div>

*Example response representations:*

- <div>

  201 - application/json (pullRequest) \[<a href="#" onclick="toggle(&#39;idm532061888496&#39;); return false;"><em><span id="link-idm532061888496">expand</span></em></a>\]

  </div>

  <div id="idm532061888496" class="toggle">

  ###### Example

      {"id":101,"version":1,"title":"Talking Nerdy","description":"It’s a kludge, but put the tuple from the database in the cache.","state":"OPEN","open":true,"closed":false,"createdDate":1359075920,"updatedDate":1359075920,"fromRef":{"id":"refs/heads/feature","displayId":"feature-ABC-123","latestCommit":"babecafebabecafebabecafebabecafebabecafe","repository":{"slug":"my-repo","id":1,"name":"My repo","scmId":"git","state":"AVAILABLE","statusMessage":"Available","forkable":true,"project":{"key":"PRJ","id":1,"name":"My Cool Project","description":"The description for my cool project.","public":true,"type":"NORMAL","links":{"self":[{"href":"http://link/to/project"}]}},"public":true,"links":{"clone":[{"href":"ssh://git@<baseURL>/PRJ/my-repo.git","name":"ssh"},{"href":"https://<baseURL>/scm/PRJ/my-repo.git","name":"http"}],"self":[{"href":"http://link/to/repository"}]}}},"toRef":{"id":"refs/heads/master","displayId":"master","latestCommit":"cafebabecafebabecafebabecafebabecafebabe","repository":{"slug":"my-repo","id":1,"name":"My repo","scmId":"git","state":"AVAILABLE","statusMessage":"Available","forkable":true,"project":{"key":"PRJ","id":1,"name":"My Cool Project","description":"The description for my cool project.","public":true,"type":"NORMAL","links":{"self":[{"href":"http://link/to/project"}]}},"public":true,"links":{"clone":[{"href":"ssh://git@<baseURL>/PRJ/my-repo.git","name":"ssh"},{"href":"https://<baseURL>/scm/PRJ/my-repo.git","name":"http"}],"self":[{"href":"http://link/to/repository"}]}}},"locked":false,"author":{"user":{"name":"alice","emailAddress":"alice@example.com","id":92903040,"displayName":"Alice","active":true,"slug":"alice","type":"NORMAL"},"role":"PARTICIPANT","approved":false,"status":"UNAPPROVED"},"reviewers":[{"user":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"lastReviewedCommit":"7549846524f8aed2bd1c0249993ae1bf9d3c9998","role":"REVIEWER","approved":false,"status":"UNAPPROVED"}],"participants":[],"links":{"self":[{"href":"http://link/to/pullrequest"}]}}

  The newly created pull request.

  <div class="representation">

  </div>

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061886096&#39;); return false;"><em><span id="link-idm532061886096">expand</span></em></a>\]

  </div>

  <div id="idm532061886096" class="toggle">

  ###### Example

      {"errors":[{"context":"field_a","message":"A detailed validation error message for field_a.","exceptionName":null},{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The pull request entity supplied in the request was malformed.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061884192&#39;); return false;"><em><span id="link-idm532061884192">expand</span></em></a>\]

  </div>

  <div id="idm532061884192" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to create a pull request between the two specified repositories.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061881776&#39;); return false;"><em><span id="link-idm532061881776">expand</span></em></a>\]

  </div>

  <div id="idm532061881776" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  One of the specified repositories or branches does not exist.

  <div class="representation">

  </div>

  </div>

- <div>

  409 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061879984&#39;); return false;"><em><span id="link-idm532061879984">expand</span></em></a>\]

  </div>

  <div id="idm532061879984" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  One of the following error cases occurred (check the error message for more details):

  - There was a problem resolving one or more reviewers.
  - The specified branches were the same.
  - The *to* branch is already up-to-date with all the commits on the *from* branch.
  - A pull request between the two branches already exists.

  <div class="representation">

  </div>

  </div>

</div>

<div class="method">

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests<span class="optional">?direction</span><span class="optional">&at</span><span class="optional">&state</span><span class="optional">&order</span><span class="optional">&withAttributes</span><span class="optional">&withProperties</span>

*This is a [paged API](#paging-params)*. *This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Retrieve a page of pull requests to or from the specified repository.

The authenticated user must have **REPO_READ** permission for the specified repository to call this resource. Optionally clients can specify PR participant filters. Each filter has a mandatory {@code username.N} parameter, and the optional {@code role.N} and {@code approved.N} parameters.

- {@code username.N} - the "root" of a single participant filter, where "N" is a natural number starting from 1. This allows clients to specify multiple participant filters, by providing consecutive filters as {@code username.1}, {@code username.2} etc. Note that the filters numbering has to start with 1 and be continuous for all filters to be processed. The total allowed number of participant filters is 10 and all filters exceeding that limit will be dropped.
- {@code role.N}(optional) the role associated with {@code username.N}. This must be one of {@code AUTHOR}, {@code REVIEWER}, or{@code PARTICIPANT}
- {@code approved.N}(optional) the approved status associated with {@code username.N}. That is whether {@code username.N} has approved the PR. Either {@code true}, or {@code false}

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
<td><p><strong>direction</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p>
<p>Default: <code>incoming</code></p></td>
<td><p>(optional, defaults to <strong>INCOMING</strong>) the direction relative to the specified repository. Either <strong>INCOMING</strong> or <strong>OUTGOING</strong>.</p></td>
</tr>
<tr>
<td><p><strong>at</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p></td>
<td><p>(optional) a <em>fully-qualified</em> branch ID to find pull requests to or from, such as {@code refs/heads/master}</p></td>
</tr>
<tr>
<td><p><strong>state</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p></td>
<td><p>(optional, defaults to <strong>OPEN</strong>). Supply <strong>ALL</strong> to return pull request in any state. If a state is supplied only pull requests in the specified state will be returned. Either <strong>OPEN</strong>, <strong>DECLINED</strong> or <strong>MERGED</strong>.</p></td>
</tr>
<tr>
<td><p><strong>order</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p></td>
<td><p>(optional, defaults to <strong>NEWEST</strong>) the order to return pull requests in, either <strong>OLDEST</strong> (as in: "oldest first") or <strong>NEWEST</strong>.</p></td>
</tr>
<tr>
<td><p><strong>withAttributes</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#boolean">boolean</a></em></p>
<p>Default: <code>true</code></p></td>
<td><p>(optional) defaults to true, whether to return additional pull request attributes</p></td>
</tr>
<tr>
<td><p><strong>withProperties</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#boolean">boolean</a></em></p>
<p>Default: <code>true</code></p></td>
<td><p>(optional) defaults to true, whether to return additional pull request properties</p></td>
</tr>
</tbody>
</table>

*Example response representations:*

- <div>

  200 - application/json ([page](#paging-params)) \[<a href="#" onclick="toggle(&#39;idm532061865952&#39;); return false;"><em><span id="link-idm532061865952">expand</span></em></a>\]

  </div>

  <div id="idm532061865952" class="toggle">

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"id":101,"version":1,"title":"Talking Nerdy","description":"It’s a kludge, but put the tuple from the database in the cache.","state":"OPEN","open":true,"closed":false,"createdDate":1359075920,"updatedDate":1359085920,"fromRef":{"id":"refs/heads/feature-ABC-123","repository":{"slug":"my-repo","name":null,"project":{"key":"PRJ"}}},"toRef":{"id":"refs/heads/master","repository":{"slug":"my-repo","name":null,"project":{"key":"PRJ"}}},"locked":false,"author":{"user":{"name":"tom","emailAddress":"tom@example.com","id":115026,"displayName":"Tom","active":true,"slug":"tom","type":"NORMAL"},"role":"AUTHOR","approved":true,"status":"APPROVED"},"reviewers":[{"user":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"lastReviewedCommit":"7549846524f8aed2bd1c0249993ae1bf9d3c9998","role":"REVIEWER","approved":true,"status":"APPROVED"}],"participants":[{"user":{"name":"harry","emailAddress":"harry@example.com","id":99049120,"displayName":"Harry","active":true,"slug":"harry","type":"NORMAL"},"role":"PARTICIPANT","approved":true,"status":"APPROVED"},{"user":{"name":"dick","emailAddress":"dick@example.com","id":3083181,"displayName":"Dick","active":true,"slug":"dick","type":"NORMAL"},"role":"PARTICIPANT","approved":false,"status":"UNAPPROVED"}],"links":{"self":[{"href":"http://link/to/pullrequest"}]}}],"start":0}

  A page of pull requests that match the search criteria.

  <div class="representation">

  </div>

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061864080&#39;); return false;"><em><span id="link-idm532061864080">expand</span></em></a>\]

  </div>

  <div id="idm532061864080" class="toggle">

  ###### Example

      {"errors":[{"context":"field_a","message":"A detailed validation error message for field_a.","exceptionName":null},{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The request was malformed.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061861504&#39;); return false;"><em><span id="link-idm532061861504">expand</span></em></a>\]

  </div>

  <div id="idm532061861504" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the specified pull request.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061858528&#39;); return false;"><em><span id="link-idm532061858528">expand</span></em></a>\]

  </div>

  <div id="idm532061858528" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository or pull request does not exist.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **pullRequestId** | *[long](http://www.w3.org/TR/xmlschema-2/#long)* | the ID of the pull request within the repository |

###### Methods

<div class="methods">

<div class="method">

#### GET

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Retrieve a pull request.

The authenticated user must have **REPO_READ** permission for the repository that this pull request targets to call this resource.

*Example response representations:*

- <div>

  200 - application/json (pullRequest) \[<a href="#" onclick="toggle(&#39;idm532061853440&#39;); return false;"><em><span id="link-idm532061853440">expand</span></em></a>\]

  </div>

  <div id="idm532061853440" class="toggle">

  ###### Example

      {"id":101,"version":1,"title":"Talking Nerdy","description":"It’s a kludge, but put the tuple from the database in the cache.","state":"OPEN","open":true,"closed":false,"createdDate":1359075920,"updatedDate":1359085920,"fromRef":{"id":"refs/heads/feature-ABC-123","repository":{"slug":"my-repo","name":null,"project":{"key":"PRJ"}}},"toRef":{"id":"refs/heads/master","repository":{"slug":"my-repo","name":null,"project":{"key":"PRJ"}}},"locked":false,"author":{"user":{"name":"tom","emailAddress":"tom@example.com","id":115026,"displayName":"Tom","active":true,"slug":"tom","type":"NORMAL"},"role":"AUTHOR","approved":true,"status":"APPROVED"},"reviewers":[{"user":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"lastReviewedCommit":"7549846524f8aed2bd1c0249993ae1bf9d3c9998","role":"REVIEWER","approved":true,"status":"APPROVED"}],"participants":[{"user":{"name":"harry","emailAddress":"harry@example.com","id":99049120,"displayName":"Harry","active":true,"slug":"harry","type":"NORMAL"},"role":"PARTICIPANT","approved":true,"status":"APPROVED"},{"user":{"name":"dick","emailAddress":"dick@example.com","id":3083181,"displayName":"Dick","active":true,"slug":"dick","type":"NORMAL"},"role":"PARTICIPANT","approved":false,"status":"UNAPPROVED"}],"links":{"self":[{"href":"http://link/to/pullrequest"}]}}

  The specified pull request.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061851376&#39;); return false;"><em><span id="link-idm532061851376">expand</span></em></a>\]

  </div>

  <div id="idm532061851376" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the specified pull request.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061848608&#39;); return false;"><em><span id="link-idm532061848608">expand</span></em></a>\]

  </div>

  <div id="idm532061848608" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository or pull request does not exist.

  <div class="representation">

  </div>

  </div>

</div>

<div class="method">

#### PUT

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Update the title, description, reviewers or destination branch of an existing pull request.

**Note:** the *reviewers* list may be updated using this resource. However the *author* and *participants* list may not.

The authenticated user must either:

- be the author of the pull request and have the **REPO_READ** permission for the repository that this pull request targets; or
- have the **REPO_WRITE** permission for the repository that this pull request targets

to call this resource.

*Example request representations:*

- <div>

  application/json \[<a href="#" onclick="toggle(&#39;idm532061845520&#39;); return false;"><em><span id="link-idm532061845520">expand</span></em></a>\]

  </div>

  <div id="idm532061845520" class="toggle">

  ###### Example

      {"id":101,"version":2,"title":"Talking Nerdy","description":"It’s a hack, but force AO to eagerly initialize to avoid deadlocks.","reviewers":[{"user":{"name":"charlie"}}]}

  </div>

*Example response representations:*

- <div>

  200 - application/json (pullRequest) \[<a href="#" onclick="toggle(&#39;idm532061843440&#39;); return false;"><em><span id="link-idm532061843440">expand</span></em></a>\]

  </div>

  <div id="idm532061843440" class="toggle">

  ###### Example

      {"id":101,"version":1,"title":"Talking Nerdy","description":"It’s a kludge, but put the tuple from the database in the cache.","state":"OPEN","open":true,"closed":false,"createdDate":1359075920,"updatedDate":1359085920,"fromRef":{"id":"refs/heads/feature-ABC-123","repository":{"slug":"my-repo","name":null,"project":{"key":"PRJ"}}},"toRef":{"id":"refs/heads/master","repository":{"slug":"my-repo","name":null,"project":{"key":"PRJ"}}},"locked":false,"author":{"user":{"name":"tom","emailAddress":"tom@example.com","id":115026,"displayName":"Tom","active":true,"slug":"tom","type":"NORMAL"},"role":"AUTHOR","approved":true,"status":"APPROVED"},"reviewers":[{"user":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"lastReviewedCommit":"7549846524f8aed2bd1c0249993ae1bf9d3c9998","role":"REVIEWER","approved":true,"status":"APPROVED"}],"participants":[{"user":{"name":"harry","emailAddress":"harry@example.com","id":99049120,"displayName":"Harry","active":true,"slug":"harry","type":"NORMAL"},"role":"PARTICIPANT","approved":true,"status":"APPROVED"},{"user":{"name":"dick","emailAddress":"dick@example.com","id":3083181,"displayName":"Dick","active":true,"slug":"dick","type":"NORMAL"},"role":"PARTICIPANT","approved":false,"status":"UNAPPROVED"}],"links":{"self":[{"href":"http://link/to/pullrequest"}]}}

  The updated pull request.

  <div class="representation">

  </div>

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061840944&#39;); return false;"><em><span id="link-idm532061840944">expand</span></em></a>\]

  </div>

  <div id="idm532061840944" class="toggle">

  ###### Example

      {"errors":[{"context":"field_a","message":"A detailed validation error message for field_a.","exceptionName":null},{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  One of the following error cases occurred (check the error message for more details):

  - The request tried to modify the *author* or *participants*.
  - The pull request's version attribute was not specified.
  - A reviewer's username was not specified.
  - The toRef id value was incorrectly left blank

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061839456&#39;); return false;"><em><span id="link-idm532061839456">expand</span></em></a>\]

  </div>

  <div id="idm532061839456" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to update the specified pull request.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061836544&#39;); return false;"><em><span id="link-idm532061836544">expand</span></em></a>\]

  </div>

  <div id="idm532061836544" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  One of the specified repositories or branches does not exist.

  <div class="representation">

  </div>

  </div>

- <div>

  409 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061834752&#39;); return false;"><em><span id="link-idm532061834752">expand</span></em></a>\]

  </div>

  <div id="idm532061834752" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  One of the following error cases occurred (check the error message for more details):

  - The specified version is out of date.
  - One of the reviewers could not be added to the pull request.
  - If updating the destination branch:
    - There is already an open pull request with an identical to branch
    - The from and new to branch *are* the same
    - The new destination branch up-to-date is up-to-date with all of changes from the from branch, resulting in a pull request with nothing to merge

  <div class="representation">

  </div>

  </div>

</div>

<div class="method">

#### DELETE

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Deletes a pull request.

To call this resource, users must be authenticated and have permission to view the pull request. Additionally, they must:

- be the pull request author, if the system is configured to allow authors to delete their own pull requests (this is the default) OR
- have repository administrator permission for the repository the pull request is targeting

A body containing the version of the pull request must be provided with this request.

    { "version": 1 }

*Example request representations:*

- <div>

  application/json \[<a href="#" onclick="toggle(&#39;idm532061829312&#39;); return false;"><em><span id="link-idm532061829312">expand</span></em></a>\]

  </div>

  <div id="idm532061829312" class="toggle">

  ###### Example

      {"version":1}

  </div>

*Example response representations:*

- <div>

  204 - application/json \[<a href="#" onclick="toggle(&#39;idm532061826560&#39;); return false;"><em><span id="link-idm532061826560">expand</span></em></a>\]

  </div>

  <div id="idm532061826560" class="toggle">

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061827632&#39;); return false;"><em><span id="link-idm532061827632">expand</span></em></a>\]

  </div>

  <div id="idm532061827632" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the specified pull request.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061825008&#39;); return false;"><em><span id="link-idm532061825008">expand</span></em></a>\]

  </div>

  <div id="idm532061825008" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository or pull request does not exist.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/activities

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **pullRequestId** | *[long](http://www.w3.org/TR/xmlschema-2/#long)* | the id of the pull request within the repository |

###### Methods

<div class="methods">

<div class="method">

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/activities<span class="optional">?fromId</span><span class="optional">&fromType</span>

*This is a [paged API](#paging-params)*. *This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Retrieve a page of activity associated with a pull request.

Activity items include comments, approvals, rescopes (i.e. adding and removing of commits), merges and more.

Different types of activity items may be introduced in newer versions of Stash or by user installed plugins, so clients should be flexible enough to handle unexpected entity shapes in the returned page.

The authenticated user must have **REPO_READ** permission for the repository that this pull request targets to call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **fromId** | *[long](http://www.w3.org/TR/xmlschema-2/#long)* | (optional) the id of the activity item to use as the first item in the returned page |
| **fromType** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | (required if **fromId** is present) the type of the activity item specified by **fromId** (either **COMMENT** or **ACTIVITY**) |

*Example response representations:*

- <div>

  200 - application/json ([page](#paging-params)) \[<a href="#" onclick="toggle(&#39;idm532061779936&#39;); return false;"><em><span id="link-idm532061779936">expand</span></em></a>\]

  </div>

  <div id="idm532061779936" class="toggle">

  ###### Example

      {"size":3,"limit":25,"isLastPage":true,"values":[{"id":101,"createdDate":1359065920,"user":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"action":"COMMENTED","commentAction":"ADDED","comment":{"properties":{"key":"value"},"id":1,"version":1,"text":"A measured reply.","author":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"createdDate":1527228363421,"updatedDate":1527228363421,"comments":[{"properties":{"key":"value"},"id":1,"version":1,"text":"An insightful comment.","author":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"createdDate":1527228363411,"updatedDate":1527228363411,"comments":[],"tasks":[],"permittedOperations":{"editable":true,"deletable":true}}],"tasks":[],"permittedOperations":{"editable":true,"deletable":true}},"commentAnchor":{"line":1,"lineType":"CONTEXT","fileType":"FROM","path":"path/to/file","srcPath":"path/to/file"}},{"id":101,"createdDate":1359065920,"user":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"action":"RESCOPED","fromHash":"abcdeabcdeabcdeabcdeabcdeabcdeabcdeabcde","previousFromHash":"bcdeabcdeabcdeabcdeabcdeabcdeabcdeabcdea","previousToHash":"cdeabcdeabcdeabcdeabcdeabcdeabcdeabcdeab","toHash":"ddeabcdeabcdeabcdeabcdeabcdeabcdeabcdeabc","added":{"commits":[{"id":"abcdef0123abcdef4567abcdef8987abcdef6543","displayId":"abcdef0123a","author":{"name":"charlie","emailAddress":"charlie@example.com"},"authorTimestamp":1527228363490,"committer":{"name":"charlie","emailAddress":"charlie@example.com"},"committerTimestamp":1527228363490,"message":"WIP on feature 1","parents":[{"id":"abcdef0123abcdef4567abcdef8987abcdef6543","displayId":"abcdef0"}]}],"total":1},"removed":{"commits":[{"id":"def0123abcdef4567abcdef8987abcdef6543abc","displayId":"def0123abcd","author":{"name":"charlie","emailAddress":"charlie@example.com"},"authorTimestamp":1527228363490,"committer":{"name":"charlie","emailAddress":"charlie@example.com"},"committerTimestamp":1527228363490,"message":"More work on feature 1","parents":[{"id":"abcdef0123abcdef4567abcdef8987abcdef6543","displayId":"abcdef0"}]}],"total":1}},{"id":101,"createdDate":1359085920,"user":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"action":"MERGED"}],"start":0}

  A page of activity relating to the specified pull request.

  <div class="representation">

  </div>

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061776784&#39;); return false;"><em><span id="link-idm532061776784">expand</span></em></a>\]

  </div>

  <div id="idm532061776784" class="toggle">

  ###### Example

      {"errors":[{"context":"field_a","message":"A detailed validation error message for field_a.","exceptionName":null},{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The request was malformed.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061774656&#39;); return false;"><em><span id="link-idm532061774656">expand</span></em></a>\]

  </div>

  <div id="idm532061774656" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the specified pull request.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061772288&#39;); return false;"><em><span id="link-idm532061772288">expand</span></em></a>\]

  </div>

  <div id="idm532061772288" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository or pull request does not exist.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/decline

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **pullRequestId** | *[long](http://www.w3.org/TR/xmlschema-2/#long)* |  |

###### Methods

<div class="methods">

<div class="method">

#### POST

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/decline<span class="optional">?version</span>

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Decline a pull request.

The authenticated user must have **REPO_READ** permission for the repository that this pull request targets to call this resource.

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
<td><p><strong>version</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#int">int</a></em></p>
<p>Default: <code>-1</code></p></td>
<td><p>the current version of the pull request. If the server's version isn't the same as the specified version the operation will fail. To determine the current version of the pull request it should be fetched from the server prior to this operation. Look for the 'version' attribute in the returned JSON structure.</p></td>
</tr>
</tbody>
</table>

*Example response representations:*

- <div>

  200 \[<a href="#" onclick="toggle(&#39;idm532061793664&#39;); return false;"><em><span id="link-idm532061793664">expand</span></em></a>\]

  </div>

  <div id="idm532061793664" class="toggle">

  The pull request was declined.

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061792672&#39;); return false;"><em><span id="link-idm532061792672">expand</span></em></a>\]

  </div>

  <div id="idm532061792672" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the pull request.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061791536&#39;); return false;"><em><span id="link-idm532061791536">expand</span></em></a>\]

  </div>

  <div id="idm532061791536" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository or pull request does not exist.

  <div class="representation">

  </div>

  </div>

- <div>

  409 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061788208&#39;); return false;"><em><span id="link-idm532061788208">expand</span></em></a>\]

  </div>

  <div id="idm532061788208" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The pull request is not OPEN or has been updated since the version specified by the request.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/merge

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **pullRequestId** | *[long](http://www.w3.org/TR/xmlschema-2/#long)* | the id of the pull request within the repository |

###### Methods

<div class="methods">

<div class="method">

#### POST

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/merge<span class="optional">?version</span>

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Merge the specified pull request.

The authenticated user must have **REPO_WRITE** permission for the repository that this pull request targets to call this resource.

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
<td><p><strong>version</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#int">int</a></em></p>
<p>Default: <code>-1</code></p></td>
<td><p>the current version of the pull request. If the server's version isn't the same as the specified version the operation will fail. To determine the current version of the pull request it should be fetched from the server prior to this operation. Look for the 'version' attribute in the returned JSON structure.</p></td>
</tr>
</tbody>
</table>

*Example response representations:*

- <div>

  200 - application/json (pullRequest) \[<a href="#" onclick="toggle(&#39;idm532061819808&#39;); return false;"><em><span id="link-idm532061819808">expand</span></em></a>\]

  </div>

  <div id="idm532061819808" class="toggle">

  ###### Example

      {"id":101,"version":1,"title":"Talking Nerdy","description":"It’s a kludge, but put the tuple from the database in the cache.","state":"MERGED","open":false,"closed":true,"createdDate":1359075920,"updatedDate":1359115920,"closedDate":1359115920,"fromRef":{"id":"refs/heads/feature-ABC-123","repository":{"slug":"my-repo","name":null,"project":{"key":"PRJ"}}},"toRef":{"id":"refs/heads/master","repository":{"slug":"my-repo","name":null,"project":{"key":"PRJ"}}},"locked":false,"author":{"user":{"name":"tom","emailAddress":"tom@example.com","id":115026,"displayName":"Tom","active":true,"slug":"tom","type":"NORMAL"},"role":"AUTHOR","approved":true,"status":"APPROVED"},"reviewers":[{"user":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"lastReviewedCommit":"7549846524f8aed2bd1c0249993ae1bf9d3c9998","role":"REVIEWER","approved":true,"status":"APPROVED"}],"participants":[{"user":{"name":"harry","emailAddress":"harry@example.com","id":99049120,"displayName":"Harry","active":true,"slug":"harry","type":"NORMAL"},"role":"PARTICIPANT","approved":true,"status":"APPROVED"},{"user":{"name":"dick","emailAddress":"dick@example.com","id":3083181,"displayName":"Dick","active":true,"slug":"dick","type":"NORMAL"},"role":"PARTICIPANT","approved":true,"status":"APPROVED"}],"properties":{"commentCount":3},"links":{"self":[{"href":"http://link/to/pullrequest"}]}}

  The merged pull request.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061816080&#39;); return false;"><em><span id="link-idm532061816080">expand</span></em></a>\]

  </div>

  <div id="idm532061816080" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to merge the specified pull request.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061814848&#39;); return false;"><em><span id="link-idm532061814848">expand</span></em></a>\]

  </div>

  <div id="idm532061814848" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository or pull request does not exist.

  <div class="representation">

  </div>

  </div>

- <div>

  409 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061810896&#39;); return false;"><em><span id="link-idm532061810896">expand</span></em></a>\]

  </div>

  <div id="idm532061810896" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  One of the following error cases occurred (check the error message for more details):

  - The pull request has conflicts.
  - A merge check vetoed the merge.
  - The specified version is out of date.
  - The specified pull request is not open.

  <div class="representation">

  </div>

  </div>

</div>

<div class="method">

#### GET

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Test whether a pull request can be merged.

A pull request may not be merged if:

- there are conflicts that need to be manually resolved before merging; and/or
- one or more merge checks have vetoed the merge.

The authenticated user must have **REPO_READ** permission for the repository that this pull request targets to call this resource.

*Example response representations:*

- <div>

  200 - application/json (pullRequest) \[<a href="#" onclick="toggle(&#39;idm532061807376&#39;); return false;"><em><span id="link-idm532061807376">expand</span></em></a>\]

  </div>

  <div id="idm532061807376" class="toggle">

  ###### Example

      {"canMerge":false,"conflicted":true,"outcome":"CONFLICTED","vetoes":[{"summaryMessage":"You may not merge after 6pm on a Friday.","detailedMessage":"It is likely that your Blood Alcohol Content (BAC) exceeds the threshold for making sensible decisions regarding pull requests. Please try again on Monday."}]}

  The mergeability status of the pull request.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061805184&#39;); return false;"><em><span id="link-idm532061805184">expand</span></em></a>\]

  </div>

  <div id="idm532061805184" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the specified pull request.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061802992&#39;); return false;"><em><span id="link-idm532061802992">expand</span></em></a>\]

  </div>

  <div id="idm532061802992" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository or pull request does not exist.

  <div class="representation">

  </div>

  </div>

- <div>

  409 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061799632&#39;); return false;"><em><span id="link-idm532061799632">expand</span></em></a>\]

  </div>

  <div id="idm532061799632" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified pull request is not open.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/reopen

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **pullRequestId** | *[long](http://www.w3.org/TR/xmlschema-2/#long)* | the id of the pull request within the repository |

###### Methods

<div class="methods">

<div class="method">

#### POST

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/reopen<span class="optional">?version</span>

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Re-open a declined pull request.

The authenticated user must have **REPO_READ** permission for the repository that this pull request targets to call this resource.

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
<td><p><strong>version</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#int">int</a></em></p>
<p>Default: <code>-1</code></p></td>
<td><p>the current version of the pull request. If the server's version isn't the same as the specified version the operation will fail. To determine the current version of the pull request it should be fetched from the server prior to this operation. Look for the 'version' attribute in the returned JSON structure.</p></td>
</tr>
</tbody>
</table>

*Example response representations:*

- <div>

  200 - application/json (pullRequest) \[<a href="#" onclick="toggle(&#39;idm532061765888&#39;); return false;"><em><span id="link-idm532061765888">expand</span></em></a>\]

  </div>

  <div id="idm532061765888" class="toggle">

  ###### Example

      {"id":101,"version":1,"title":"Talking Nerdy","description":"It’s a kludge, but put the tuple from the database in the cache.","state":"OPEN","open":true,"closed":false,"createdDate":1359075920,"updatedDate":1359085920,"fromRef":{"id":"refs/heads/feature-ABC-123","repository":{"slug":"my-repo","name":null,"project":{"key":"PRJ"}}},"toRef":{"id":"refs/heads/master","repository":{"slug":"my-repo","name":null,"project":{"key":"PRJ"}}},"locked":false,"author":{"user":{"name":"tom","emailAddress":"tom@example.com","id":115026,"displayName":"Tom","active":true,"slug":"tom","type":"NORMAL"},"role":"AUTHOR","approved":true,"status":"APPROVED"},"reviewers":[{"user":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"lastReviewedCommit":"7549846524f8aed2bd1c0249993ae1bf9d3c9998","role":"REVIEWER","approved":true,"status":"APPROVED"}],"participants":[{"user":{"name":"harry","emailAddress":"harry@example.com","id":99049120,"displayName":"Harry","active":true,"slug":"harry","type":"NORMAL"},"role":"PARTICIPANT","approved":true,"status":"APPROVED"},{"user":{"name":"dick","emailAddress":"dick@example.com","id":3083181,"displayName":"Dick","active":true,"slug":"dick","type":"NORMAL"},"role":"PARTICIPANT","approved":false,"status":"UNAPPROVED"}],"links":{"self":[{"href":"http://link/to/pullrequest"}]}}

  The merged pull request.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061763408&#39;); return false;"><em><span id="link-idm532061763408">expand</span></em></a>\]

  </div>

  <div id="idm532061763408" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to reopen the specified pull request.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061760656&#39;); return false;"><em><span id="link-idm532061760656">expand</span></em></a>\]

  </div>

  <div id="idm532061760656" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository or pull request does not exist.

  <div class="representation">

  </div>

  </div>

- <div>

  409 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061758288&#39;); return false;"><em><span id="link-idm532061758288">expand</span></em></a>\]

  </div>

  <div id="idm532061758288" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  One of the following error cases occurred (check the error message for more details):

  - The pull request is not in a declined state.
  - The specified version is out of date.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/approve

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **pullRequestId** | *[long](http://www.w3.org/TR/xmlschema-2/#long)* | the id of the pull request within the repository |

###### Methods

<div class="methods">

<div class="method">

#### POST

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Approve a pull request as the current user. Implicitly adds the user as a participant if they are not already.

The authenticated user must have **REPO_READ** permission for the repository that this pull request targets to call this resource.

**Deprecated since 4.2**. Use /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/participants/{userSlug} instead

*Example response representations:*

- <div>

  201 - application/json (participant) \[<a href="#" onclick="toggle(&#39;idm532025584960&#39;); return false;"><em><span id="link-idm532025584960">expand</span></em></a>\]

  </div>

  <div id="idm532025584960" class="toggle">

  ###### Example

      {"user":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"lastReviewedCommit":"7549846524f8aed2bd1c0249993ae1bf9d3c9998","role":"REVIEWER","approved":true,"status":"APPROVED"}

  Details of the new participant

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025582352&#39;); return false;"><em><span id="link-idm532025582352">expand</span></em></a>\]

  </div>

  <div id="idm532025582352" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the pull request.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025581408&#39;); return false;"><em><span id="link-idm532025581408">expand</span></em></a>\]

  </div>

  <div id="idm532025581408" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository or pull request does not exist.

  <div class="representation">

  </div>

  </div>

- <div>

  409 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025577616&#39;); return false;"><em><span id="link-idm532025577616">expand</span></em></a>\]

  </div>

  <div id="idm532025577616" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The pull request is not open.

  <div class="representation">

  </div>

  </div>

</div>

<div class="method">

#### DELETE

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Remove approval from a pull request as the current user. This does not remove the user as a participant.

The authenticated user must have **REPO_READ** permission for the repository that this pull request targets to call this resource.

**Deprecated since 4.2**. Use /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/participants/{userSlug} instead

*Example response representations:*

- <div>

  201 - application/json (participant) \[<a href="#" onclick="toggle(&#39;idm532025573488&#39;); return false;"><em><span id="link-idm532025573488">expand</span></em></a>\]

  </div>

  <div id="idm532025573488" class="toggle">

  ###### Example

      {"user":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"lastReviewedCommit":"7549846524f8aed2bd1c0249993ae1bf9d3c9998","role":"REVIEWER","approved":false,"status":"UNAPPROVED"}

  Details of the updated participant

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025571440&#39;); return false;"><em><span id="link-idm532025571440">expand</span></em></a>\]

  </div>

  <div id="idm532025571440" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the pull request.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025569632&#39;); return false;"><em><span id="link-idm532025569632">expand</span></em></a>\]

  </div>

  <div id="idm532025569632" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository or pull request does not exist or the current user is not a participant on the pull request.

  <div class="representation">

  </div>

  </div>

- <div>

  409 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025567600&#39;); return false;"><em><span id="link-idm532025567600">expand</span></em></a>\]

  </div>

  <div id="idm532025567600" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The pull request is not open.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/changes

###### Methods

<div class="methods">

<div class="method">

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/changes<span class="optional">?changeScope</span><span class="optional">&sinceId</span><span class="optional">&untilId</span><span class="optional">&withComments</span>

*This is a [paged API](#paging-params)*. *This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Gets changes for the specified PullRequest.

If the {@code changeScope} query parameter is set to {@code unreviewed}, the application will attempt to stream unreviewed changes based on the {@code lastReviewedCommit} of the current user, which are the changes between the {@code lastReviewedCommit} and the latest commit of the source branch. The current user is considered to *not* have any unreviewed changes for the pull request when the {@code lastReviewedCommit} is either {@code null} (everything is unreviewed, so all changes are streamed), equal to the latest commit of the source branch (everything is reviewed), or no longer on the source branch (the source branch has been rebased). In these cases, the application will fall back to streaming all changes (the default), which is the effective diff for the pull request. The type of changes streamed can be determined by the {@code changeScope} parameter included in the properties map of the response.

Note: This resource is currently *not paged*. The server will return at most one page. The server will truncate the number of changes to either the request's page limit or an internal maximum, whichever is smaller. The start parameter of the page request is also ignored.

The authenticated user must have **REPO_READ** permission for the repository that this pull request targets to call this resource.

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
<td><p><strong>changeScope</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p>
<p>Default: <code>ALL</code></p></td>
<td><p>{@code UNREVIEWED} to stream the unreviewed changes for the current user (if they exist); {@code RANGE} to stream changes between two arbitrary commits (requires {@code sinceId} and {@code untilId}); otherwise {@code ALL} to stream all changes (the default)</p></td>
</tr>
<tr>
<td><p><strong>sinceId</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p></td>
<td><p>the since commit hash to stream changes for a {@code RANGE} arbitrary change scope</p></td>
</tr>
<tr>
<td><p><strong>untilId</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p></td>
<td><p>the until commit hash to stream changes for a {@code RANGE} arbitrary change scope</p></td>
</tr>
<tr>
<td><p><strong>withComments</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#boolean">boolean</a></em></p>
<p>Default: <code>true</code></p></td>
<td><p>{@code true} to apply comment counts in the changes (the default); otherwise, {@code false} to stream changes without comment counts</p></td>
</tr>
</tbody>
</table>

*Example response representations:*

- <div>

  200 - application/json ([page](#paging-params)) \[<a href="#" onclick="toggle(&#39;idm532026609936&#39;); return false;"><em><span id="link-idm532026609936">expand</span></em></a>\]

  </div>

  <div id="idm532026609936" class="toggle">

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"contentId":"5c279d6c7a3a053a145905aa9682ce02c16449e9","fromContentId":"7b86ad1a05b4259b8fa54497a8be0bd359a405bd","path":{"components":["path","to","unreviewed","file.txt"],"parent":"path/to/unreviewed","name":"file.txt","extension":"txt","toString":"path/to/unreviewed/file.txt"},"executable":false,"percentUnchanged":98,"type":"MOVE","nodeType":"FILE","srcPath":{"components":["path","to","file.txt"],"parent":"path/to","name":"file.txt","extension":"txt","toString":"path/to/file.txt"},"srcExecutable":false,"links":{"self":[null]},"properties":{"unreviewedCommits":1}}],"start":0}

  A page of unreviewed Changes for the current user from the supplied pull request, including the unreviewedCommits in the properties map.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026602496&#39;); return false;"><em><span id="link-idm532026602496">expand</span></em></a>\]

  </div>

  <div id="idm532026602496" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the repository or pull request.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026600864&#39;); return false;"><em><span id="link-idm532026600864">expand</span></em></a>\]

  </div>

  <div id="idm532026600864" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The repository or pull request does not exist.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/comments

###### Methods

<div class="methods">

<div class="method">

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/comments<span class="optional">?anchorState</span><span class="optional">&diffType</span><span class="optional">&fromHash</span><span class="optional">&path</span><span class="optional">&toHash</span>

*This is a [paged API](#paging-params)*. *This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Gets comments for the specified PullRequest.

The authenticated user must have **REPO_READ** permission for the repository that this pull request targets to call this resource.

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
<td><p><strong>anchorState</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p>
<p>Default: <code>ACTIVE</code></p></td>
<td><p>{@code ACTIVE} to stream the active comments; {@code ORPHANED} to stream the orphaned comments; {@code ALL} to stream both the active and the orphaned comments;</p></td>
</tr>
<tr>
<td><p><strong>diffType</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p></td>
<td><p>{@code EFFECTIVE} to stream the comments related to the effective diff of the pull request; {@code RANGE} to stream comments related to a commit range between two arbitrary commits (requires {@code fromHash} and {@code toHash}); {@code COMMIT} to stream comments related to a commit between two arbitrary commits (requires {@code fromHash} and {@code toHash})</p></td>
</tr>
<tr>
<td><p><strong>fromHash</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p></td>
<td><p>the from commit hash to stream comments for a {@code RANGE} or {@code COMMIT} arbitrary change scope</p></td>
</tr>
<tr>
<td><p><strong>path</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p></td>
<td><p>the path to stream comments for a given path</p></td>
</tr>
<tr>
<td><p><strong>toHash</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p></td>
<td><p>the to commit hash to stream comments for a {@code RANGE} or {@code COMMIT} arbitrary change scope</p></td>
</tr>
</tbody>
</table>

*Example response representations:*

- <div>

  200 - application/json ([page](#paging-params)) \[<a href="#" onclick="toggle(&#39;idm532026051856&#39;); return false;"><em><span id="link-idm532026051856">expand</span></em></a>\]

  </div>

  <div id="idm532026051856" class="toggle">

  ###### Example

      {"properties":{"key":"value"},"id":1,"version":1,"text":"A measured reply.","author":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"createdDate":1527228363421,"updatedDate":1527228363421,"comments":[{"properties":{"key":"value"},"id":1,"version":1,"text":"An insightful comment.","author":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"createdDate":1527228363411,"updatedDate":1527228363411,"comments":[],"tasks":[],"permittedOperations":{"editable":true,"deletable":true}}],"tasks":[],"permittedOperations":{"editable":true,"deletable":true}}

  A page of Comments from the supplied pull request.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026050992&#39;); return false;"><em><span id="link-idm532026050992">expand</span></em></a>\]

  </div>

  <div id="idm532026050992" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the repository or pull request.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026052144&#39;); return false;"><em><span id="link-idm532026052144">expand</span></em></a>\]

  </div>

  <div id="idm532026052144" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The repository or pull request does not exist.

  <div class="representation">

  </div>

  </div>

</div>

<div class="method">

#### POST

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Add a new comment.

Comments can be added in a few places by setting different attributes:

General pull request comment:

\
     {\
         "text": "An insightful general comment on a pull request."\
     }\
     

Reply to a comment:

\
     {\
         "text": "A measured reply.",\
         "parent": {\
             "id": 1\
         }\
     }\
     

General file comment:

\
     {\
         "text": "An insightful general comment on a file.",\
         "anchor": {\
             "diffType": "RANGE",\
             "fromHash": "6df3858eeb9a53a911cd17e66a9174d44ffb02cd",\
             "path": "path/to/file",\
             "srcPath": "path/to/file",\
             "toHash": "04c7c5c931b9418ca7b66f51fe934d0bd9b2ba4b"\
         }\
     }\
     

File line comment:

\
     {\
         "text": "A pithy comment on a particular line within a file.",\
         "anchor": {\
             "diffType": "COMMIT",\
             "line": 1,\
             "lineType": "CONTEXT",\
             "fileType": "FROM",\
             "fromHash": "6df3858eeb9a53a911cd17e66a9174d44ffb02cd",\
             "path": "path/to/file",\
             "srcPath": "path/to/file",\
             "toHash": "04c7c5c931b9418ca7b66f51fe934d0bd9b2ba4b"\
         }\
     }\
     

For file and line comments, 'path' refers to the path of the file to which the comment should be applied and 'srcPath' refers to the path the that file used to have (only required for copies and moves). Also, fromHash and toHash refer to the sinceId / untilId (respectively) used to produce the diff on which the comment was added. Finally diffType refers to the type of diff the comment was added on. For backwards compatibility purposes if no diffType is provided and no fromHash/toHash pair is provided the diffType will be resolved to 'EFFECTIVE'. In any other cases the diffType is REQUIRED.

For line comments, 'line' refers to the line in the diff that the comment should apply to. 'lineType' refers to the type of diff hunk, which can be:

- 'ADDED' - for an added line;
- 'REMOVED' - for a removed line; or
- 'CONTEXT' - for a line that was unmodified but is in the vicinity of the diff.

'fileType' refers to the file of the diff to which the anchor should be attached - which is of relevance when displaying the diff in a side-by-side way. Currently the supported values are:

- 'FROM' - the source file of the diff
- 'TO' - the destination file of the diff

If the current user is not a participant the user is added as a watcher of the pull request.

The authenticated user must have **REPO_READ** permission for the repository that this pull request targets to call this resource.

*Example request representations:*

- <div>

  application/json \[<a href="#" onclick="toggle(&#39;idm532026041920&#39;); return false;"><em><span id="link-idm532026041920">expand</span></em></a>\]

  </div>

  <div id="idm532026041920" class="toggle">

  ###### Example

      {"text":"An insightful comment.","parent":{"id":1},"anchor":{"line":1,"lineType":"CONTEXT","fileType":"FROM","path":"path/to/file","srcPath":"path/to/file"}}

  </div>

*Example response representations:*

- <div>

  201 - application/json (comment) \[<a href="#" onclick="toggle(&#39;idm532026040720&#39;); return false;"><em><span id="link-idm532026040720">expand</span></em></a>\]

  </div>

  <div id="idm532026040720" class="toggle">

  ###### Example

      {"properties":{"key":"value"},"id":1,"version":1,"text":"A measured reply.","author":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"createdDate":1527228363421,"updatedDate":1527228363421,"comments":[{"properties":{"key":"value"},"id":1,"version":1,"text":"An insightful comment.","author":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"createdDate":1527228363411,"updatedDate":1527228363411,"comments":[],"tasks":[],"permittedOperations":{"editable":true,"deletable":true}}],"tasks":[],"permittedOperations":{"editable":true,"deletable":true}}

  The newly created comment.

  <div class="representation">

  </div>

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026038592&#39;); return false;"><em><span id="link-idm532026038592">expand</span></em></a>\]

  </div>

  <div id="idm532026038592" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The comment was not created due to a validation error.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026035952&#39;); return false;"><em><span id="link-idm532026035952">expand</span></em></a>\]

  </div>

  <div id="idm532026035952" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the pull request, create a comment or watch the pull request.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026033696&#39;); return false;"><em><span id="link-idm532026033696">expand</span></em></a>\]

  </div>

  <div id="idm532026033696" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  Unable to find the supplied project, repository, pull request or parent comment

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/comments/{commentId}

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **commentId** | *[long](http://www.w3.org/TR/xmlschema-2/#long)* | the id of the comment to retrieve |

###### Methods

<div class="methods">

<div class="method">

#### GET

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Retrieves a pull request comment.

The authenticated user must have **REPO_READ** permission for the repository that this pull request targets to call this resource.

*Example response representations:*

- <div>

  200 - application/json (comment) \[<a href="#" onclick="toggle(&#39;idm532026027456&#39;); return false;"><em><span id="link-idm532026027456">expand</span></em></a>\]

  </div>

  <div id="idm532026027456" class="toggle">

  ###### Example

      {"properties":{"key":"value"},"id":1,"version":1,"text":"A measured reply.","author":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"createdDate":1527228363421,"updatedDate":1527228363421,"comments":[{"properties":{"key":"value"},"id":1,"version":1,"text":"An insightful comment.","author":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"createdDate":1527228363411,"updatedDate":1527228363411,"comments":[],"tasks":[],"permittedOperations":{"editable":true,"deletable":true}}],"tasks":[],"permittedOperations":{"editable":true,"deletable":true}}

  The requested comment.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026024848&#39;); return false;"><em><span id="link-idm532026024848">expand</span></em></a>\]

  </div>

  <div id="idm532026024848" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the comment

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026021936&#39;); return false;"><em><span id="link-idm532026021936">expand</span></em></a>\]

  </div>

  <div id="idm532026021936" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  Unable to find the supplied project, repository, pull request or comment

  <div class="representation">

  </div>

  </div>

</div>

<div class="method">

#### DELETE

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/comments/{commentId}<span class="optional">?version</span>

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Delete a pull request comment. Anyone can delete their own comment. Only users with **REPO_ADMIN** and above may delete comments created by other users.

The authenticated user must have **REPO_READ** permission for the repository that this pull request targets to call this resource.

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
<td><p><strong>version</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#int">int</a></em></p>
<p>Default: <code>-1</code></p></td>
<td><p>The expected version of the comment. This must match the server's version of the comment or the delete will fail. To determine the current version of the comment, the comment should be fetched from the server prior to the delete. Look for the 'version' attribute in the returned JSON structure.</p></td>
</tr>
</tbody>
</table>

*Example response representations:*

- <div>

  204 \[<a href="#" onclick="toggle(&#39;idm532026014048&#39;); return false;"><em><span id="link-idm532026014048">expand</span></em></a>\]

  </div>

  <div id="idm532026014048" class="toggle">

  The operation was successful

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026017152&#39;); return false;"><em><span id="link-idm532026017152">expand</span></em></a>\]

  </div>

  <div id="idm532026017152" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to delete the comment.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026013264&#39;); return false;"><em><span id="link-idm532026013264">expand</span></em></a>\]

  </div>

  <div id="idm532026013264" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  Unable to find the supplied project, repository or pull request.

  <div class="representation">

  </div>

  </div>

- <div>

  409 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026011696&#39;); return false;"><em><span id="link-idm532026011696">expand</span></em></a>\]

  </div>

  <div id="idm532026011696" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The comment has replies or the version supplied does not match the current version.

  <div class="representation">

  </div>

  </div>

</div>

<div class="method">

#### PUT

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Update the text of a comment. Only the user who created a comment may update it.

**Note:** the supplied supplied JSON object must contain a `version` that must match the server's version of the comment or the update will fail. To determine the current version of the comment, the comment should be fetched from the server prior to the update. Look for the 'version' attribute in the returned JSON structure.

The authenticated user must have **REPO_READ** permission for the repository that this pull request targets to call this resource.

*Example request representations:*

- <div>

  application/json \[<a href="#" onclick="toggle(&#39;idm532026006992&#39;); return false;"><em><span id="link-idm532026006992">expand</span></em></a>\]

  </div>

  <div id="idm532026006992" class="toggle">

  ###### Example

      {"version":0,"text":"A pithy comment."}

  </div>

*Example response representations:*

- <div>

  201 - application/json (comment) \[<a href="#" onclick="toggle(&#39;idm532026005968&#39;); return false;"><em><span id="link-idm532026005968">expand</span></em></a>\]

  </div>

  <div id="idm532026005968" class="toggle">

  ###### Example

      {"properties":{"key":"value"},"id":1,"version":1,"text":"A measured reply.","author":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"createdDate":1527228363421,"updatedDate":1527228363421,"comments":[{"properties":{"key":"value"},"id":1,"version":1,"text":"An insightful comment.","author":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"createdDate":1527228363411,"updatedDate":1527228363411,"comments":[],"tasks":[],"permittedOperations":{"editable":true,"deletable":true}}],"tasks":[],"permittedOperations":{"editable":true,"deletable":true}}

  The newly updated comment.

  <div class="representation">

  </div>

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026003328&#39;); return false;"><em><span id="link-idm532026003328">expand</span></em></a>\]

  </div>

  <div id="idm532026003328" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The comment was not updated due to a validation error.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026000368&#39;); return false;"><em><span id="link-idm532026000368">expand</span></em></a>\]

  </div>

  <div id="idm532026000368" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the pull request, update a comment or watch the pull request.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025998704&#39;); return false;"><em><span id="link-idm532025998704">expand</span></em></a>\]

  </div>

  <div id="idm532025998704" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  Unable to find the supplied project, repository, pull request or comment

  <div class="representation">

  </div>

  </div>

- <div>

  409 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025995680&#39;); return false;"><em><span id="link-idm532025995680">expand</span></em></a>\]

  </div>

  <div id="idm532025995680" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The comment version supplied does not match the current version.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/commits

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **pullRequestId** | *[long](http://www.w3.org/TR/xmlschema-2/#long)* |  |

###### Methods

<div class="methods">

<div class="method">

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/commits<span class="optional">?withCounts</span>

*This is a [paged API](#paging-params)*. *This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Retrieve commits for the specified pull request.

The authenticated user must have **REPO_READ** permission for the repository that this pull request targets to call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **withCounts** | *[boolean](http://www.w3.org/TR/xmlschema-2/#boolean)* | if set to true, the service will add "authorCount" and "totalCount" at the end of the page. "authorCount" is the number of different authors and "totalCount" is the total number of commits. |

*Example response representations:*

- <div>

  200 - application/json ([page](#paging-params)) \[<a href="#" onclick="toggle(&#39;idm532026193552&#39;); return false;"><em><span id="link-idm532026193552">expand</span></em></a>\]

  </div>

  <div id="idm532026193552" class="toggle">

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"id":"def0123abcdef4567abcdef8987abcdef6543abc","displayId":"def0123abcd","author":{"name":"charlie","emailAddress":"charlie@example.com"},"authorTimestamp":1527228363490,"committer":{"name":"charlie","emailAddress":"charlie@example.com"},"committerTimestamp":1527228363490,"message":"More work on feature 1","parents":[{"id":"abcdef0123abcdef4567abcdef8987abcdef6543","displayId":"abcdef0"}]}],"start":0,"authorCount":1,"totalCount":1}

  a page of commits from the supplied pull request.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026194608&#39;); return false;"><em><span id="link-idm532026194608">expand</span></em></a>\]

  </div>

  <div id="idm532026194608" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the repository or pull request.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026188576&#39;); return false;"><em><span id="link-idm532026188576">expand</span></em></a>\]

  </div>

  <div id="idm532026188576" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The repository or pull request does not exist.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/diff

###### Methods

<div class="methods">

<div class="method">

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/diff<span class="optional">?contextLines</span><span class="optional">&diffType</span><span class="optional">&sinceId</span><span class="optional">&srcPath</span><span class="optional">&untilId</span><span class="optional">&whitespace</span><span class="optional">&withComments</span>

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Streams a diff within a pull request.

If the specified file has been copied, moved or renamed, the `srcPath` must also be specified to produce the correct diff.

Note: This RESTful endpoint is currently *not paged*. The server will internally apply a hard cap to the streamed lines, and it is not possible to request subsequent pages if that cap is exceeded.

The authenticated user must have **REPO_READ** permission for the repository that this pull request targets to call this resource.

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
<td><p><strong>contextLines</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#int">int</a></em></p>
<p>Default: <code>-1</code></p></td>
<td><p>the number of context lines to include around added/removed lines in the diff</p></td>
</tr>
<tr>
<td><p><strong>diffType</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p>
<p>Default: <code>EFFECTIVE</code></p></td>
<td><p>the type of diff being requested. When {@code withComments} is {@code true} this works as a hint to the system to attach the correct set of comments to the diff</p></td>
</tr>
<tr>
<td><p><strong>sinceId</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p></td>
<td><p>the since commit hash to stream a diff between two arbitrary hashes</p></td>
</tr>
<tr>
<td><p><strong>srcPath</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p></td>
<td><p>the previous path to the file, if the file has been copied, moved or renamed</p></td>
</tr>
<tr>
<td><p><strong>untilId</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p></td>
<td><p>the until commit hash to stream a diff between two arbitrary hashes</p></td>
</tr>
<tr>
<td><p><strong>whitespace</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p></td>
<td><p>optional whitespace flag which can be set to <code>ignore-all</code></p></td>
</tr>
<tr>
<td><p><strong>withComments</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#boolean">boolean</a></em></p>
<p>Default: <code>true</code></p></td>
<td><p><code>true</code> to embed comments in the diff (the default); otherwise, <code>false</code> to stream the diff without comments</p></td>
</tr>
</tbody>
</table>

*Example response representations:*

- <div>

  200 - application/json (diffs) \[<a href="#" onclick="toggle(&#39;idm532026583712&#39;); return false;"><em><span id="link-idm532026583712">expand</span></em></a>\]

  </div>

  <div id="idm532026583712" class="toggle">

  ###### Example

      {"diffs":[{"source":{"components":["path","to","file.txt"],"parent":"path/to","name":"file.txt","extension":"txt","toString":"path/to/file.txt"},"destination":{"components":["path","to","file.txt"],"parent":"path/to","name":"file.txt","extension":"txt","toString":"path/to/file.txt"},"hunks":[{"sourceLine":1,"sourceSpan":1,"destinationLine":1,"destinationSpan":2,"segments":[{"type":"REMOVED","lines":[{"destination":1,"source":1,"line":"import sys","truncated":false}],"truncated":false},{"type":"ADDED","lines":[{"destination":1,"source":2,"line":"import re","truncated":false,"conflictMarker":"OURS","commentIds":[1]},{"destination":2,"source":3,"line":"import os","truncated":false}],"truncated":false}],"truncated":false}],"lineComments":[{"properties":{"key":"value"},"id":1,"version":1,"text":"An insightful comment.","author":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"createdDate":1527228363411,"updatedDate":1527228363411,"comments":[],"tasks":[],"permittedOperations":{"editable":true,"deletable":true}}],"truncated":"true","contextLines":"10","fromHash":"a0f224fd7bd5f28ea5a752d41b9c9f6372fc6d9e","toHash":"dc93f22caadcde35daf5cc2cd65d2738c87e31ca","whiteSpace":"SHOW"}],"truncated":"true","contextLines":"10","fromHash":"a0f224fd7bd5f28ea5a752d41b9c9f6372fc6d9e","toHash":"dc93f22caadcde35daf5cc2cd65d2738c87e31ca","whiteSpace":"SHOW"}

  a page of differences from a pull request.

  <div class="representation">

  </div>

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026585440&#39;); return false;"><em><span id="link-idm532026585440">expand</span></em></a>\]

  </div>

  <div id="idm532026585440" class="toggle">

  ###### Example

      {"errors":[{"context":"field_a","message":"A detailed validation error message for field_a.","exceptionName":null},{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  If the request was malformed.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026578784&#39;); return false;"><em><span id="link-idm532026578784">expand</span></em></a>\]

  </div>

  <div id="idm532026578784" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the repository or pull request.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026577424&#39;); return false;"><em><span id="link-idm532026577424">expand</span></em></a>\]

  </div>

  <div id="idm532026577424" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The repository or pull request does not exist.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/diff/{path:.\*}

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **path** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the path to the file which should be diffed (optional) |

###### Methods

<div class="methods">

<div class="method">

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/diff/{path:.\*}<span class="optional">?contextLines</span><span class="optional">&diffType</span><span class="optional">&sinceId</span><span class="optional">&srcPath</span><span class="optional">&untilId</span><span class="optional">&whitespace</span><span class="optional">&withComments</span>

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Streams a diff within a pull request.

If the specified file has been copied, moved or renamed, the `srcPath` must also be specified to produce the correct diff.

Note: This RESTful endpoint is currently *not paged*. The server will internally apply a hard cap to the streamed lines, and it is not possible to request subsequent pages if that cap is exceeded.

The authenticated user must have **REPO_READ** permission for the repository that this pull request targets to call this resource.

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
<td><p><strong>contextLines</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#int">int</a></em></p>
<p>Default: <code>-1</code></p></td>
<td><p>the number of context lines to include around added/removed lines in the diff</p></td>
</tr>
<tr>
<td><p><strong>diffType</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p>
<p>Default: <code>EFFECTIVE</code></p></td>
<td><p>the type of diff being requested. When {@code withComments} is {@code true} this works as a hint to the system to attach the correct set of comments to the diff</p></td>
</tr>
<tr>
<td><p><strong>sinceId</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p></td>
<td><p>the since commit hash to stream a diff between two arbitrary hashes</p></td>
</tr>
<tr>
<td><p><strong>srcPath</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p></td>
<td><p>the previous path to the file, if the file has been copied, moved or renamed</p></td>
</tr>
<tr>
<td><p><strong>untilId</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p></td>
<td><p>the until commit hash to stream a diff between two arbitrary hashes</p></td>
</tr>
<tr>
<td><p><strong>whitespace</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p></td>
<td><p>optional whitespace flag which can be set to <code>ignore-all</code></p></td>
</tr>
<tr>
<td><p><strong>withComments</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#boolean">boolean</a></em></p>
<p>Default: <code>true</code></p></td>
<td><p><code>true</code> to embed comments in the diff (the default); otherwise, <code>false</code> to stream the diff without comments</p></td>
</tr>
</tbody>
</table>

*Example response representations:*

- <div>

  200 - application/json (diffs) \[<a href="#" onclick="toggle(&#39;idm532026561008&#39;); return false;"><em><span id="link-idm532026561008">expand</span></em></a>\]

  </div>

  <div id="idm532026561008" class="toggle">

  ###### Example

      {"diffs":[{"source":{"components":["path","to","file.txt"],"parent":"path/to","name":"file.txt","extension":"txt","toString":"path/to/file.txt"},"destination":{"components":["path","to","file.txt"],"parent":"path/to","name":"file.txt","extension":"txt","toString":"path/to/file.txt"},"hunks":[{"sourceLine":1,"sourceSpan":1,"destinationLine":1,"destinationSpan":2,"segments":[{"type":"REMOVED","lines":[{"destination":1,"source":1,"line":"import sys","truncated":false}],"truncated":false},{"type":"ADDED","lines":[{"destination":1,"source":2,"line":"import re","truncated":false,"conflictMarker":"OURS","commentIds":[1]},{"destination":2,"source":3,"line":"import os","truncated":false}],"truncated":false}],"truncated":false}],"lineComments":[{"properties":{"key":"value"},"id":1,"version":1,"text":"An insightful comment.","author":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"createdDate":1527228363411,"updatedDate":1527228363411,"comments":[],"tasks":[],"permittedOperations":{"editable":true,"deletable":true}}],"truncated":"true","contextLines":"10","fromHash":"a0f224fd7bd5f28ea5a752d41b9c9f6372fc6d9e","toHash":"dc93f22caadcde35daf5cc2cd65d2738c87e31ca","whiteSpace":"SHOW"}],"truncated":"true","contextLines":"10","fromHash":"a0f224fd7bd5f28ea5a752d41b9c9f6372fc6d9e","toHash":"dc93f22caadcde35daf5cc2cd65d2738c87e31ca","whiteSpace":"SHOW"}

  a page of differences from a pull request.

  <div class="representation">

  </div>

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026558064&#39;); return false;"><em><span id="link-idm532026558064">expand</span></em></a>\]

  </div>

  <div id="idm532026558064" class="toggle">

  ###### Example

      {"errors":[{"context":"field_a","message":"A detailed validation error message for field_a.","exceptionName":null},{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  If the request was malformed.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026555600&#39;); return false;"><em><span id="link-idm532026555600">expand</span></em></a>\]

  </div>

  <div id="idm532026555600" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the repository or pull request.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026553232&#39;); return false;"><em><span id="link-idm532026553232">expand</span></em></a>\]

  </div>

  <div id="idm532026553232" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The repository or pull request does not exist.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/participants

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **pullRequestId** | *[long](http://www.w3.org/TR/xmlschema-2/#long)* | the id of the pull request within the repository |

###### Methods

<div class="methods">

<div class="method">

#### GET

*This is a [paged API](#paging-params)*. *This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Retrieves a page of the participants for a given pull request.

The authenticated user must have **REPO_READ** permission for the repository that this pull request targets to call this resource.

*Example response representations:*

- <div>

  201 - application/json ([page](#paging-params)) \[<a href="#" onclick="toggle(&#39;idm532061630672&#39;); return false;"><em><span id="link-idm532061630672">expand</span></em></a>\]

  </div>

  <div id="idm532061630672" class="toggle">

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"user":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"lastReviewedCommit":"7549846524f8aed2bd1c0249993ae1bf9d3c9998","role":"REVIEWER","approved":true,"status":"APPROVED"}],"start":0}

  Details of the participants in this pull request

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061629680&#39;); return false;"><em><span id="link-idm532061629680">expand</span></em></a>\]

  </div>

  <div id="idm532061629680" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the pull request.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061625552&#39;); return false;"><em><span id="link-idm532061625552">expand</span></em></a>\]

  </div>

  <div id="idm532061625552" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository or pull request does not exist.

  <div class="representation">

  </div>

  </div>

</div>

<div class="method">

#### POST

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Assigns a participant to an explicit role in pull request. Currently only the REVIEWER role may be assigned.

If the user is not yet a participant in the pull request, they are made one and assigned the supplied role.

If the user is already a participant in the pull request, their previous role is replaced with the supplied role unless they are already assigned the AUTHOR role which cannot be changed and will result in a Bad Request (400) response code.

The authenticated user must have **REPO_WRITE** permission for the repository that this pull request targets to call this resource.

*Example request representations:*

- <div>

  application/json \[<a href="#" onclick="toggle(&#39;idm532061621712&#39;); return false;"><em><span id="link-idm532061621712">expand</span></em></a>\]

  </div>

  <div id="idm532061621712" class="toggle">

  ###### Example

      {"user":{"name":"charlie"},"role":"REVIEWER"}

  </div>

*Example response representations:*

- <div>

  201 - application/json (participant) \[<a href="#" onclick="toggle(&#39;idm532061619808&#39;); return false;"><em><span id="link-idm532061619808">expand</span></em></a>\]

  </div>

  <div id="idm532061619808" class="toggle">

  ###### Example

      {"user":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"lastReviewedCommit":"7549846524f8aed2bd1c0249993ae1bf9d3c9998","role":"REVIEWER","approved":false,"status":"UNAPPROVED"}

  The created or updated participant.

  <div class="representation">

  </div>

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061618112&#39;); return false;"><em><span id="link-idm532061618112">expand</span></em></a>\]

  </div>

  <div id="idm532061618112" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The request does not have the username and role, or is attempting an invalid assignment

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532027205392&#39;); return false;"><em><span id="link-idm532027205392">expand</span></em></a>\]

  </div>

  <div id="idm532027205392" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to update the pull request.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532027203808&#39;); return false;"><em><span id="link-idm532027203808">expand</span></em></a>\]

  </div>

  <div id="idm532027203808" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository or pull request does not exist.

  <div class="representation">

  </div>

  </div>

</div>

<div class="method">

#### DELETE

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/participants<span class="optional">?username</span>

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Unassigns a participant from the REVIEWER role they may have been given in a pull request.

If the participant has no explicit role this method has no effect.

Afterwards, the user will still remain a participant in the pull request but their role will be reduced to PARTICIPANT. This is because once made a participant of a pull request, a user will forever remain a participant. Only their role may be altered.

The authenticated user must have **REPO_WRITE** permission for the repository that this pull request targets to call this resource.

**Deprecated since 4.2**. Use /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/participants/{userSlug} instead.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **username** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the participant's user name |

*Example response representations:*

- <div>

  204 \[<a href="#" onclick="toggle(&#39;idm532023718800&#39;); return false;"><em><span id="link-idm532023718800">expand</span></em></a>\]

  </div>

  <div id="idm532023718800" class="toggle">

  The update completed.

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532023722480&#39;); return false;"><em><span id="link-idm532023722480">expand</span></em></a>\]

  </div>

  <div id="idm532023722480" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The request does not have the username

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532023720432&#39;); return false;"><em><span id="link-idm532023720432">expand</span></em></a>\]

  </div>

  <div id="idm532023720432" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to update the pull request.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532023717344&#39;); return false;"><em><span id="link-idm532023717344">expand</span></em></a>\]

  </div>

  <div id="idm532023717344" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository or pull request does not exist.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/participants/{userSlug}

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **pullRequestId** | *[long](http://www.w3.org/TR/xmlschema-2/#long)* | the id of the pull request within the repository |
| **userSlug** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the slug for the user changing their status |
| **pullRequestId** | *[long](http://www.w3.org/TR/xmlschema-2/#long)* | the id of the pull request within the repository |

###### Methods

<div class="methods">

<div class="method">

#### DELETE

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Unassigns a participant from the REVIEWER role they may have been given in a pull request.

If the participant has no explicit role this method has no effect.

Afterwards, the user will still remain a participant in the pull request but their role will be reduced to PARTICIPANT. This is because once made a participant of a pull request, a user will forever remain a participant. Only their role may be altered.

The authenticated user must have **REPO_WRITE** permission for the repository that this pull request targets to call this resource.

**Deprecated since 4.2**. Use /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/participants/{userSlug} instead.

*Example response representations:*

- <div>

  204 \[<a href="#" onclick="toggle(&#39;idm532023705520&#39;); return false;"><em><span id="link-idm532023705520">expand</span></em></a>\]

  </div>

  <div id="idm532023705520" class="toggle">

  The update completed.

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532023711712&#39;); return false;"><em><span id="link-idm532023711712">expand</span></em></a>\]

  </div>

  <div id="idm532023711712" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The request does not have the username

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532023710448&#39;); return false;"><em><span id="link-idm532023710448">expand</span></em></a>\]

  </div>

  <div id="idm532023710448" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to update the pull request.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532023704816&#39;); return false;"><em><span id="link-idm532023704816">expand</span></em></a>\]

  </div>

  <div id="idm532023704816" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository or pull request does not exist.

  <div class="representation">

  </div>

  </div>

</div>

<div class="method">

#### PUT

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Change the current user's status for a pull request. Implicitly adds the user as a participant if they are not already. If the current user is the author, this method will fail.

The possible values for {@code status} are **UNAPPROVED**, **NEEDS_WORK**, or **APPROVED**.

If the new {@code status} is **NEEDS_WORK** or **APPROVED** then the {@code lastReviewedCommit} for the participant will be updated to the latest commit of the source branch of the pull request.

The authenticated user must have **REPO_READ** permission for the repository that this pull request targets to call this resource.

*Example request representations:*

- <div>

  application/json \[<a href="#" onclick="toggle(&#39;idm532023701872&#39;); return false;"><em><span id="link-idm532023701872">expand</span></em></a>\]

  </div>

  <div id="idm532023701872" class="toggle">

  ###### Example

      {"user":{"name":"charlie"},"approved":true,"status":"APPROVED"}

  </div>

*Example response representations:*

- <div>

  201 - application/json (participant) \[<a href="#" onclick="toggle(&#39;idm532023700496&#39;); return false;"><em><span id="link-idm532023700496">expand</span></em></a>\]

  </div>

  <div id="idm532023700496" class="toggle">

  ###### Example

      {"user":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"lastReviewedCommit":"7549846524f8aed2bd1c0249993ae1bf9d3c9998","role":"REVIEWER","approved":true,"status":"APPROVED"}

  Details of the new participant

  <div class="representation">

  </div>

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532023697024&#39;); return false;"><em><span id="link-idm532023697024">expand</span></em></a>\]

  </div>

  <div id="idm532023697024" class="toggle">

  ###### Example

      {"errors":[{"context":"field_a","message":"A detailed validation error message for field_a.","exceptionName":null},{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified status was invalid.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532023694656&#39;); return false;"><em><span id="link-idm532023694656">expand</span></em></a>\]

  </div>

  <div id="idm532023694656" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the pull request.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532023692160&#39;); return false;"><em><span id="link-idm532023692160">expand</span></em></a>\]

  </div>

  <div id="idm532023692160" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository or pull request does not exist.

  <div class="representation">

  </div>

  </div>

- <div>

  409 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532023689808&#39;); return false;"><em><span id="link-idm532023689808">expand</span></em></a>\]

  </div>

  <div id="idm532023689808" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The pull request is not open.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/tasks

###### Methods

<div class="methods">

<div class="method">

#### GET

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Retrieve the tasks associated with a pull request.

*Example response representations:*

- <div>

  200 - application/json (task) \[<a href="#" onclick="toggle(&#39;idm532026177744&#39;); return false;"><em><span id="link-idm532026177744">expand</span></em></a>\]

  </div>

  <div id="idm532026177744" class="toggle">

  ###### Example

      {"size":2,"limit":25,"isLastPage":true,"values":[{"properties":{"diffAnchorPath":"path/to/file.txt"},"anchor":{"properties":{"key":"value"},"id":1,"version":1,"text":"An insightful comment.","author":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"createdDate":1527228363411,"updatedDate":1527228363411,"comments":[],"tasks":[],"permittedOperations":{"editable":true,"deletable":true}},"author":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"createdDate":1527228364842,"id":98,"permittedOperations":{"deletable":true,"editable":true,"transitionable":true},"text":"Fix typos on the constructor's arguments","state":"OPEN"},{"properties":{"diffAnchorPath":"path/to/file.txt"},"anchor":{"properties":{"key":"value"},"id":5,"version":1,"text":"This class is deprecated.  Can you please use the replacement?","author":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"createdDate":1527228363411,"updatedDate":1527228363411,"comments":[],"tasks":[],"permittedOperations":{"editable":true,"deletable":true}},"author":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"createdDate":1527228364842,"id":99,"permittedOperations":{"deletable":false,"editable":false,"transitionable":true},"text":"Remove usage of deprecated class","state":"RESOLVED"}],"start":0}

  A page of tasks associated with the pull request.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026176784&#39;); return false;"><em><span id="link-idm532026176784">expand</span></em></a>\]

  </div>

  <div id="idm532026176784" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  If the current user cannot access the pull request

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026174272&#39;); return false;"><em><span id="link-idm532026174272">expand</span></em></a>\]

  </div>

  <div id="idm532026174272" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  If the pull request does not exist

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/tasks/count

###### Methods

<div class="methods">

<div class="method">

#### GET

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Retrieve the total number of {@link TaskState#OPEN open} and {@link TaskState#RESOLVED resolved} tasks associated with a pull request.

*Example response representations:*

- <div>

  200 - application/json (taskCount) \[<a href="#" onclick="toggle(&#39;idm532026169424&#39;); return false;"><em><span id="link-idm532026169424">expand</span></em></a>\]

  </div>

  <div id="idm532026169424" class="toggle">

  ###### Example

      {"open":5,"resolved":2}

  Total number of {@link TaskState#OPEN open} and {@link TaskState#RESOLVED resolved} tasks associated with the pull request.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026169296&#39;); return false;"><em><span id="link-idm532026169296">expand</span></em></a>\]

  </div>

  <div id="idm532026169296" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  If the current user cannot access the pull request

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026164352&#39;); return false;"><em><span id="link-idm532026164352">expand</span></em></a>\]

  </div>

  <div id="idm532026164352" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  If the pull request does not exist

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{pullRequestId}/watch

###### Methods

<div class="methods">

<div class="method">

#### POST

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Add the authenticated user as a watcher for the specified pull request.

The authenticated user must have **REPO_READ** permission for the repository that this pull request targets to call this resource.

*Example response representations:*

- <div>

  204 \[<a href="#" onclick="toggle(&#39;idm532026243344&#39;); return false;"><em><span id="link-idm532026243344">expand</span></em></a>\]

  </div>

  <div id="idm532026243344" class="toggle">

  The user is now watching the pull request.

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026244608&#39;); return false;"><em><span id="link-idm532026244608">expand</span></em></a>\]

  </div>

  <div id="idm532026244608" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the pull request.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026241552&#39;); return false;"><em><span id="link-idm532026241552">expand</span></em></a>\]

  </div>

  <div id="idm532026241552" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository or pull request does not exist.

  <div class="representation">

  </div>

  </div>

</div>

<div class="method">

#### DELETE

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Remove the authenticated user as a watcher for the specified pull request.

The authenticated user must have **REPO_READ** permission for the repository that this pull request targets to call this resource.

*Example response representations:*

- <div>

  204 \[<a href="#" onclick="toggle(&#39;idm532026235792&#39;); return false;"><em><span id="link-idm532026235792">expand</span></em></a>\]

  </div>

  <div id="idm532026235792" class="toggle">

  The user is no longer watching the pull request.

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026238064&#39;); return false;"><em><span id="link-idm532026238064">expand</span></em></a>\]

  </div>

  <div id="idm532026238064" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the pull request.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026235040&#39;); return false;"><em><span id="link-idm532026235040">expand</span></em></a>\]

  </div>

  <div id="idm532026235040" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository or pull request does not exist.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/raw

###### Methods

<div class="methods">

<div class="method">

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/raw<span class="optional">?at</span><span class="optional">&markup</span><span class="optional">&hardwrap</span><span class="optional">&htmlEscape</span>

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
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

- <div>

  \*/\* \[<a href="#" onclick="toggle(&#39;idm532024749328&#39;); return false;"><em><span id="link-idm532024749328">expand</span></em></a>\]

  </div>

  <div id="idm532024749328" class="toggle">

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/raw/{path:.\*}

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **path** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the file path to retrieve content from |

###### Methods

<div class="methods">

<div class="method">

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/raw/{path:.\*}<span class="optional">?at</span><span class="optional">&markup</span><span class="optional">&hardwrap</span><span class="optional">&htmlEscape</span>

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
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

- <div>

  \*/\* \[<a href="#" onclick="toggle(&#39;idm532024740880&#39;); return false;"><em><span id="link-idm532024740880">expand</span></em></a>\]

  </div>

  <div id="idm532024740880" class="toggle">

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/settings/pull-requests

###### Methods

<div class="methods">

<div class="method">

#### POST

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Update the pull request settings for the context repository.

The authenticated user must have **REPO_ADMIN** permission for the context repository to call this resource.

This resource will call all RestFragments that are registered with the key **bitbucket.repository.settings.pullRequests**. If any fragment fails validations by returning a non-empty Map of errors, then no fragments will execute.

Only the settings that should be updated need to be included in the request.

The property keys for the settings that are bundled with the application are

- mergeConfig - the merge strategy configuration for pull requests
- requiredApprovers - (Deprecated, please use com.atlassian.bitbucket.server.bundled-hooks.requiredApproversMergeHook instead) the number of approvals required on a pull request for it to be mergeable, or 0 to disable the merge check
- com.atlassian.bitbucket.server.bundled-hooks.requiredApproversMergeHook - a json map containing the keys 'enabled' (a boolean to enable or disable this merge check) and 'count' (an integer to set the number of required approvals)
- requiredAllApprovers - whether or not all approvers must approve a pull request for it to be mergeable
- requiredAllTasksComplete - whether or not all tasks on a pull request need to be completed for it to be mergeable
- requiredSuccessfulBuilds - (Deprecated, please use com.atlassian.bitbucket.server.bitbucket-build.requiredBuildsMergeCheck instead) the number of successful builds on a pull request for it to be mergeable, or 0 to disable the merge check
- com.atlassian.bitbucket.server.bitbucket-build.requiredBuildsMergeCheck - a json map containing the keys 'enabled' (a boolean to enable or disable this merge check) and 'count' (an integer to set the number of required builds)

**Merge strategy configuration deletion:**

An explicitly set pull request merge strategy configuration can be deleted by POSTing a document with an empty "mergeConfig" attribute. i.e:

\
 {\
     "mergeConfig": {\
     }\
 }\
 

Upon completion of this request, the effective configuration will be:

- The configuration set for this repository's SCM type as set at the project level, if present, otherwise
- the configuration set for this repository's SCM type as set at the instance level, if present, otherwise
- the default configuration for this repository's SCM type

*Example request representations:*

- <div>

  application/json \[<a href="#" onclick="toggle(&#39;idm532025535712&#39;); return false;"><em><span id="link-idm532025535712">expand</span></em></a>\]

  </div>

  <div id="idm532025535712" class="toggle">

  ###### Example

      {"mergeConfig":{"defaultStrategy":{"id":"no-ff"},"strategies":[{"id":"no-ff"}]},"requiredAllApprovers":false,"requiredAllTasksComplete":false,"com.atlassian.bitbucket.server.bundled-hooks.requiredApproversMergeHook":{"enabled":true,"count":2},"requiredApprovers":2,"com.atlassian.bitbucket.server.bitbucket-build.requiredBuildsMergeCheck":{"enabled":true,"count":3},"requiredSuccessfulBuilds":2}

  </div>

*Example response representations:*

- <div>

  200 - application/json (settings) \[<a href="#" onclick="toggle(&#39;idm532025534256&#39;); return false;"><em><span id="link-idm532025534256">expand</span></em></a>\]

  </div>

  <div id="idm532025534256" class="toggle">

  ###### Example

      {"mergeConfig":{"defaultStrategy":{"description":"Always create a merge commit","enabled":true,"flag":"--no-ff","id":"no-ff","name":"Merge commit"},"strategies":[{"description":"Always create a merge commit","enabled":true,"flag":"--no-ff","id":"no-ff","name":"Merge commit"}],"type":"repository"},"requiredAllApprovers":false,"requiredAllTasksComplete":false,"com.atlassian.bitbucket.server.bundled-hooks.requiredApproversMergeHook":{"enabled":true,"count":2},"requiredApprovers":2,"com.atlassian.bitbucket.server.bitbucket-build.requiredBuildsMergeCheck":{"enabled":true,"count":3},"requiredSuccessfulBuilds":2}

  The repository pull request settings for the context repository.

  <div class="representation">

  </div>

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025532160&#39;); return false;"><em><span id="link-idm532025532160">expand</span></em></a>\]

  </div>

  <div id="idm532025532160" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The repository pull request settings were not updated due to a validation error.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025528304&#39;); return false;"><em><span id="link-idm532025528304">expand</span></em></a>\]

  </div>

  <div id="idm532025528304" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to see the specified repository.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025526096&#39;); return false;"><em><span id="link-idm532025526096">expand</span></em></a>\]

  </div>

  <div id="idm532025526096" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository does not exist.

  <div class="representation">

  </div>

  </div>

</div>

<div class="method">

#### GET

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Retrieve the pull request settings for the context repository.

The authenticated user must have **REPO_READ** permission for the context repository to call this resource.

This resource will call all RestFragments that are registered with the key **bitbucket.repository.settings.pullRequests**. If any fragment fails validations by returning a non-empty Map of errors, then no fragments will execute.

The property keys for the settings that are bundled with the application are

- mergeConfig - the merge strategy configuration for pull requests
- requiredApprovers - (Deprecated, please use com.atlassian.bitbucket.server.bundled-hooks.requiredApproversMergeHook instead) the number of approvals required on a pull request for it to be mergeable, or 0 if the merge check is disabled
- com.atlassian.bitbucket.server.bundled-hooks.requiredApproversMergeHook - the merge check configuration for required approvers
- requiredAllApprovers - whether or not all approvers must approve a pull request for it to be mergeable
- requiredAllTasksComplete - whether or not all tasks on a pull request need to be completed for it to be mergeable
- requiredSuccessfulBuilds - (Deprecated, please use com.atlassian.bitbucket.server.bitbucket-build.requiredBuildsMergeCheck instead) the number of successful builds on a pull request for it to be mergeable, or 0 if the merge check is disabled
- com.atlassian.bitbucket.server.bitbucket-build.requiredBuildsMergeCheck - the merge check configuration for required builds

*Example response representations:*

- <div>

  200 - application/json \[<a href="#" onclick="toggle(&#39;idm532025522736&#39;); return false;"><em><span id="link-idm532025522736">expand</span></em></a>\]

  </div>

  <div id="idm532025522736" class="toggle">

  ###### Example

      {"mergeConfig":{"defaultStrategy":{"description":"Always create a merge commit","enabled":true,"flag":"--no-ff","id":"no-ff","name":"Merge commit"},"strategies":[{"description":"Always create a merge commit","enabled":true,"flag":"--no-ff","id":"no-ff","name":"Merge commit"}],"type":"repository"},"requiredAllApprovers":false,"requiredAllTasksComplete":false,"com.atlassian.bitbucket.server.bundled-hooks.requiredApproversMergeHook":{"enabled":true,"count":2},"requiredApprovers":2,"com.atlassian.bitbucket.server.bitbucket-build.requiredBuildsMergeCheck":{"enabled":true,"count":3},"requiredSuccessfulBuilds":2}

  The repository pull request settings for the context repository.

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025521216&#39;); return false;"><em><span id="link-idm532025521216">expand</span></em></a>\]

  </div>

  <div id="idm532025521216" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to see the specified repository.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025518768&#39;); return false;"><em><span id="link-idm532025518768">expand</span></em></a>\]

  </div>

  <div id="idm532025518768" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository does not exist.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/settings/hooks

###### Methods

<div class="methods">

<div class="method">

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/settings/hooks<span class="optional">?type</span>

*This is a [paged API](#paging-params)*. *This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Retrieve a page of repository hooks for this repository.

The authenticated user must have **REPO_READ** permission for the specified repository to call this resource.

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
<td><p><strong>type</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p>
<p>Default:</p></td>
<td><p>the optional type to filter by. Valid values are <code>PRE_RECEIVE</code> or <code>POST_RECEIVE</code></p></td>
</tr>
</tbody>
</table>

*Example response representations:*

- <div>

  200 - application/json ([page](#paging-params)) \[<a href="#" onclick="toggle(&#39;idm532023746944&#39;); return false;"><em><span id="link-idm532023746944">expand</span></em></a>\]

  </div>

  <div id="idm532023746944" class="toggle">

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"details":{"key":"com.atlassian.stash.plugin.example:example-repository-hook","name":"Example repository hook","type":"PRE_RECEIVE","description":"An example description for an example hook.","version":"1.2.4","configFormKey":null,"scopeTypes":["PROJECT","REPOSITORY"]},"enabled":true,"configured":true,"scope":{"resourceId":2,"type":"REPOSITORY"}}],"start":0}

  returns a page of repository hooks with their associated enabled state.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532023745136&#39;); return false;"><em><span id="link-idm532023745136">expand</span></em></a>\]

  </div>

  <div id="idm532023745136" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to retrieve the hooks.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532023742656&#39;); return false;"><em><span id="link-idm532023742656">expand</span></em></a>\]

  </div>

  <div id="idm532023742656" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository does not exist.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/settings/hooks/{hookKey}

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **hookKey** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* |  |

###### Methods

<div class="methods">

<div class="method">

#### GET

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Retrieve a repository hook for this repository.

The authenticated user must have **REPO_READ** permission for the specified repository to call this resource.

*Example response representations:*

- <div>

  200 - application/json \[<a href="#" onclick="toggle(&#39;idm532061905584&#39;); return false;"><em><span id="link-idm532061905584">expand</span></em></a>\]

  </div>

  <div id="idm532061905584" class="toggle">

  ###### Example

      {"details":{"key":"com.atlassian.stash.plugin.example:example-repository-hook","name":"Example repository hook","type":"PRE_RECEIVE","description":"An example description for an example hook.","version":"1.2.4","configFormKey":null,"scopeTypes":["PROJECT","REPOSITORY"]},"enabled":true,"configured":true,"scope":{"resourceId":2,"type":"REPOSITORY"}}

  returns the repository hooks with their associated enabled state for the supplied hookKey.

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061903280&#39;); return false;"><em><span id="link-idm532061903280">expand</span></em></a>\]

  </div>

  <div id="idm532061903280" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to retrieve the hook.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061901648&#39;); return false;"><em><span id="link-idm532061901648">expand</span></em></a>\]

  </div>

  <div id="idm532061901648" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository hook does not exist for the given repository, or the repository does not exist.

  <div class="representation">

  </div>

  </div>

</div>

<div class="method">

#### DELETE

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Delete repository hook configuration for the supplied **hookKey** and **repositorySlug**

The authenticated user must have **REPO_ADMIN** permission for the specified repository to call this resource.

*Example response representations:*

- <div>

  204 \[<a href="#" onclick="toggle(&#39;idm532061895648&#39;); return false;"><em><span id="link-idm532061895648">expand</span></em></a>\]

  </div>

  <div id="idm532061895648" class="toggle">

  The hook configuration matching the supplied **hookKey** and **repositorySlug** was deleted

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061897040&#39;); return false;"><em><span id="link-idm532061897040">expand</span></em></a>\]

  </div>

  <div id="idm532061897040" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to delete the hook.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061893728&#39;); return false;"><em><span id="link-idm532061893728">expand</span></em></a>\]

  </div>

  <div id="idm532061893728" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository or hook does not exist.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/settings/hooks/{hookKey}/enabled

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **hookKey** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* |  |

###### Methods

<div class="methods">

<div class="method">

#### PUT

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Enable a repository hook for this repository and optionally apply new configuration.

The authenticated user must have **REPO_ADMIN** permission for the specified repository to call this resource.

A JSON document may be provided to use as the settings for the hook. These structure and validity of the document is decided by the plugin providing the hook.

###### request header parameters

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
<td><p><strong>Content-Length</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#int">int</a></em></p>
<p>Default: <code>0</code></p></td>
<td></td>
</tr>
</tbody>
</table>

*Example response representations:*

- <div>

  200 - application/json \[<a href="#" onclick="toggle(&#39;idm532061925872&#39;); return false;"><em><span id="link-idm532061925872">expand</span></em></a>\]

  </div>

  <div id="idm532061925872" class="toggle">

  ###### Example

      {"details":{"key":"com.atlassian.stash.plugin.example:example-repository-hook","name":"Example repository hook","type":"PRE_RECEIVE","description":"An example description for an example hook.","version":"1.2.4","configFormKey":null,"scopeTypes":["PROJECT","REPOSITORY"]},"enabled":true,"configured":true,"scope":{"resourceId":2,"type":"REPOSITORY"}}

  returns the repository hooks with their associated enabled state for the supplied hookKey.

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061925744&#39;); return false;"><em><span id="link-idm532061925744">expand</span></em></a>\]

  </div>

  <div id="idm532061925744" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The settings specified are invalid.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061920704&#39;); return false;"><em><span id="link-idm532061920704">expand</span></em></a>\]

  </div>

  <div id="idm532061920704" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to enable the hook.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061918432&#39;); return false;"><em><span id="link-idm532061918432">expand</span></em></a>\]

  </div>

  <div id="idm532061918432" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository or hook does not exist.

  <div class="representation">

  </div>

  </div>

</div>

<div class="method">

#### DELETE

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Disable a repository hook for this repository.

The authenticated user must have **REPO_ADMIN** permission for the specified repository to call this resource.

*Example response representations:*

- <div>

  200 - application/json \[<a href="#" onclick="toggle(&#39;idm532061914992&#39;); return false;"><em><span id="link-idm532061914992">expand</span></em></a>\]

  </div>

  <div id="idm532061914992" class="toggle">

  ###### Example

      {"details":{"key":"com.atlassian.stash.plugin.example:example-repository-hook","name":"Example repository hook","type":"PRE_RECEIVE","description":"An example description for an example hook.","version":"1.2.4","configFormKey":null,"scopeTypes":["PROJECT","REPOSITORY"]},"enabled":true,"configured":true,"scope":{"resourceId":2,"type":"REPOSITORY"}}

  returns the repository hooks with their associated enabled state for the supplied hookKey.

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061913824&#39;); return false;"><em><span id="link-idm532061913824">expand</span></em></a>\]

  </div>

  <div id="idm532061913824" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to disable the hook.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061911824&#39;); return false;"><em><span id="link-idm532061911824">expand</span></em></a>\]

  </div>

  <div id="idm532061911824" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository or hook does not exist.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/settings/hooks/{hookKey}/settings

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **hookKey** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* |  |

###### Methods

<div class="methods">

<div class="method">

#### GET

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Retrieve the settings for a repository hook for this repository.

The authenticated user must have **REPO_READ** permission for the specified repository to call this resource.

*Example response representations:*

- <div>

  200 - application/json \[<a href="#" onclick="toggle(&#39;idm532023736736&#39;); return false;"><em><span id="link-idm532023736736">expand</span></em></a>\]

  </div>

  <div id="idm532023736736" class="toggle">

  ###### Example

      {"string-value":"this is an arbitrary string","integer-value":1,"long-value":2147483648,"boolean-value":true,"double-value":1.1}

  The settings for the hook.

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532023736608&#39;); return false;"><em><span id="link-idm532023736608">expand</span></em></a>\]

  </div>

  <div id="idm532023736608" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to retrieve the hook settings.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532023733504&#39;); return false;"><em><span id="link-idm532023733504">expand</span></em></a>\]

  </div>

  <div id="idm532023733504" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository or hook does not exist.

  <div class="representation">

  </div>

  </div>

</div>

<div class="method">

#### PUT

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Modify the settings for a repository hook for this repository.

The service will reject any settings which are too large, the current limit is 32KB once serialized.

The authenticated user must have **REPO_ADMIN** permission for the specified repository to call this resource.

A JSON document can be provided to use as the settings for the hook. These structure and validity of the document is decided by the plugin providing the hook.

*Example request representations:*

- <div>

  application/json \[<a href="#" onclick="toggle(&#39;idm532023728176&#39;); return false;"><em><span id="link-idm532023728176">expand</span></em></a>\]

  </div>

  <div id="idm532023728176" class="toggle">

  ###### Example

      {"string-value":"this is an arbitrary string","integer-value":1,"long-value":2147483648,"boolean-value":true,"double-value":1.1}

  </div>

*Example response representations:*

- <div>

  200 - application/json \[<a href="#" onclick="toggle(&#39;idm532064573168&#39;); return false;"><em><span id="link-idm532064573168">expand</span></em></a>\]

  </div>

  <div id="idm532064573168" class="toggle">

  ###### Example

      {"string-value":"this is an arbitrary string","integer-value":1,"long-value":2147483648,"boolean-value":true,"double-value":1.1}

  The settings for the hook.

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532027209136&#39;); return false;"><em><span id="link-idm532027209136">expand</span></em></a>\]

  </div>

  <div id="idm532027209136" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The settings specified are invalid.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532027207632&#39;); return false;"><em><span id="link-idm532027207632">expand</span></em></a>\]

  </div>

  <div id="idm532027207632" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to modify the hook settings.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061932240&#39;); return false;"><em><span id="link-idm532061932240">expand</span></em></a>\]

  </div>

  <div id="idm532061932240" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository or hook does not exist.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/tags

###### Methods

<div class="methods">

<div class="method">

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/tags<span class="optional">?filterText</span><span class="optional">&orderBy</span>

*This is a [paged API](#paging-params)*. *This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Retrieve the tags matching the supplied **filterText** param.

The authenticated user must have **REPO_READ** permission for the context repository to call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **filterText** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the text to match on |
| **orderBy** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | ordering of refs either ALPHABETICAL (by name) or MODIFICATION (last updated) |

*Example response representations:*

- <div>

  200 - application/json ([page](#paging-params)) \[<a href="#" onclick="toggle(&#39;idm532023640896&#39;); return false;"><em><span id="link-idm532023640896">expand</span></em></a>\]

  </div>

  <div id="idm532023640896" class="toggle">

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"id":"release-2.0.0","displayId":"refs/tags/release-2.0.0","type":"TAG","latestCommit":"8d351a10fb428c0c1239530256e21cf24f136e73","latestChangeset":"8d351a10fb428c0c1239530256e21cf24f136e73","hash":"8d51122def5632836d1cb1026e879069e10a1e13"}],"start":0}

  The tags matching the supplied **filterText**.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532023638736&#39;); return false;"><em><span id="link-idm532023638736">expand</span></em></a>\]

  </div>

  <div id="idm532023638736" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to read the repository.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532063379264&#39;); return false;"><em><span id="link-idm532063379264">expand</span></em></a>\]

  </div>

  <div id="idm532063379264" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository does not exist.

  <div class="representation">

  </div>

  </div>

</div>

<div class="method">

#### POST

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Creates a tag using the information provided in the {@link RestCreateTagRequest request}

The authenticated user must have **REPO_WRITE** permission for the context repository to call this resource.

*Example request representations:*

- <div>

  application/json \[<a href="#" onclick="toggle(&#39;idm532063375696&#39;); return false;"><em><span id="link-idm532063375696">expand</span></em></a>\]

  </div>

  <div id="idm532063375696" class="toggle">

  ###### Example

      {"name":"my-tag","startPoint":"8d351a10fb428c0c1239530256e21cf24f136e73","message":"This is my tag"}

  </div>

*Example response representations:*

- <div>

  200 - application/json (tag) \[<a href="#" onclick="toggle(&#39;idm532063373520&#39;); return false;"><em><span id="link-idm532063373520">expand</span></em></a>\]

  </div>

  <div id="idm532063373520" class="toggle">

  ###### Example

      {"id":"release-2.0.0","displayId":"refs/tags/release-2.0.0","type":"TAG","latestCommit":"8d351a10fb428c0c1239530256e21cf24f136e73","latestChangeset":"8d351a10fb428c0c1239530256e21cf24f136e73","hash":"8d51122def5632836d1cb1026e879069e10a1e13"}

  The created tag

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532063371472&#39;); return false;"><em><span id="link-idm532063371472">expand</span></em></a>\]

  </div>

  <div id="idm532063371472" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to write to the repository.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532063369072&#39;); return false;"><em><span id="link-idm532063369072">expand</span></em></a>\]

  </div>

  <div id="idm532063369072" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository does not exist.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/tags/{name:.\*}

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **name** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the name of the tag to be retrieved |

###### Methods

<div class="methods">

<div class="method">

#### GET

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Retrieve a tag in the specified repository.

The authenticated user must have **REPO_READ** permission for the context repository to call this resource.

*Example response representations:*

- <div>

  200 - application/json (tag) \[<a href="#" onclick="toggle(&#39;idm532063363968&#39;); return false;"><em><span id="link-idm532063363968">expand</span></em></a>\]

  </div>

  <div id="idm532063363968" class="toggle">

  ###### Example

      {"id":"release-2.0.0","displayId":"refs/tags/release-2.0.0","type":"TAG","latestCommit":"8d351a10fb428c0c1239530256e21cf24f136e73","latestChangeset":"8d351a10fb428c0c1239530256e21cf24f136e73","hash":"8d51122def5632836d1cb1026e879069e10a1e13"}

  The tag which matches the supplied **name**.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532063361936&#39;); return false;"><em><span id="link-idm532063361936">expand</span></em></a>\]

  </div>

  <div id="idm532063361936" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to read the repository.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532063358880&#39;); return false;"><em><span id="link-idm532063358880">expand</span></em></a>\]

  </div>

  <div id="idm532063358880" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified tag does not exist.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/watch

###### Methods

<div class="methods">

<div class="method">

#### POST

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Add the authenticated user as a watcher for the specified repository.

The authenticated user must have **REPO_READ** permission for the repository to call this resource.

*Example response representations:*

- <div>

  204 \[<a href="#" onclick="toggle(&#39;idm532026255568&#39;); return false;"><em><span id="link-idm532026255568">expand</span></em></a>\]

  </div>

  <div id="idm532026255568" class="toggle">

  The user is now watching the repository.

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026258064&#39;); return false;"><em><span id="link-idm532026258064">expand</span></em></a>\]

  </div>

  <div id="idm532026258064" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the repository.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026255056&#39;); return false;"><em><span id="link-idm532026255056">expand</span></em></a>\]

  </div>

  <div id="idm532026255056" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository does not exist.

  <div class="representation">

  </div>

  </div>

</div>

<div class="method">

#### DELETE

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Remove the authenticated user as a watcher for the specified repository.

The authenticated user must have **REPO_READ** permission for the repository to call this resource.

*Example response representations:*

- <div>

  204 \[<a href="#" onclick="toggle(&#39;idm532026249072&#39;); return false;"><em><span id="link-idm532026249072">expand</span></em></a>\]

  </div>

  <div id="idm532026249072" class="toggle">

  The user is no longer watching the repository.

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026251600&#39;); return false;"><em><span id="link-idm532026251600">expand</span></em></a>\]

  </div>

  <div id="idm532026251600" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the repository.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026248560&#39;); return false;"><em><span id="link-idm532026248560">expand</span></em></a>\]

  </div>

  <div id="idm532026248560" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository does not exist.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/webhooks

###### Methods

<div class="methods">

<div class="method">

#### POST

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Create a webhook for the repository specified via the URL.

The authenticated user must have **REPO_ADMIN** permission for the specified repository to call this resource.

*Example request representations:*

- <div>

  application/json \[<a href="#" onclick="toggle(&#39;idm532063479504&#39;); return false;"><em><span id="link-idm532063479504">expand</span></em></a>\]

  </div>

  <div id="idm532063479504" class="toggle">

  </div>

*Example response representations:*

- <div>

  200 - application/json (webhook) \[<a href="#" onclick="toggle(&#39;idm532063479008&#39;); return false;"><em><span id="link-idm532063479008">expand</span></em></a>\]

  </div>

  <div id="idm532063479008" class="toggle">

  ###### Example

      {"id":10,"name":"Webhook Name","createdDate":1513106011000,"updatedDate":1513106011000,"events":["repo:refs_updated","repo:modified"],"configuration":{"secret":"password"},"url":"http://example.com","active":true}

  A created webhook.

  <div class="representation">

  </div>

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532063478880&#39;); return false;"><em><span id="link-idm532063478880">expand</span></em></a>\]

  </div>

  <div id="idm532063478880" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The webhook parameters were invalid or not supplied.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532063479296&#39;); return false;"><em><span id="link-idm532063479296">expand</span></em></a>\]

  </div>

  <div id="idm532063479296" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to create webhooks in the repository.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532063473216&#39;); return false;"><em><span id="link-idm532063473216">expand</span></em></a>\]

  </div>

  <div id="idm532063473216" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The repository does not exist.

  <div class="representation">

  </div>

  </div>

</div>

<div class="method">

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/webhooks<span class="optional">?event</span><span class="optional">&statistics</span>

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Find webhooks in this repository.

The authenticated user must have **REPO_ADMIN** permission for the specified repository to call this resource.

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
<td><p><strong>event</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p></td>
<td><p>list of {@link com.atlassian.webhooks.WebhookEvent} ids to filter for</p></td>
</tr>
<tr>
<td><p><strong>statistics</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#boolean">boolean</a></em></p>
<p>Default: <code>false</code></p></td>
<td><p>{@code true} if statistics should be provided for all found webhooks</p></td>
</tr>
</tbody>
</table>

*Example response representations:*

- <div>

  200 - application/json (webhook) \[<a href="#" onclick="toggle(&#39;idm532063465696&#39;); return false;"><em><span id="link-idm532063465696">expand</span></em></a>\]

  </div>

  <div id="idm532063465696" class="toggle">

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"id":10,"name":"Webhook Name","createdDate":1513106011000,"updatedDate":1513106011000,"events":["repo:refs_updated","repo:modified"],"configuration":{"secret":"password"},"url":"http://example.com","active":true}],"start":0}

  A list of webhooks.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532063463504&#39;); return false;"><em><span id="link-idm532063463504">expand</span></em></a>\]

  </div>

  <div id="idm532063463504" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to find webhooks in the repository.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532063460448&#39;); return false;"><em><span id="link-idm532063460448">expand</span></em></a>\]

  </div>

  <div id="idm532063460448" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The repository does not exist.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/webhooks/test

###### Methods

<div class="methods">

<div class="method">

#### POST

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/webhooks/test<span class="optional">?url</span>

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Test connectivity to a specific endpoint.

The authenticated user must have **REPO_ADMIN** permission for the specified repository to call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **url** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the url in which to connect to |

*Example response representations:*

- <div>

  200 - application/json (webhook) \[<a href="#" onclick="toggle(&#39;idm532026454464&#39;); return false;"><em><span id="link-idm532026454464">expand</span></em></a>\]

  </div>

  <div id="idm532026454464" class="toggle">

  ###### Example

      {"request":{"url":"http://example.com/callback","body":null,"method":"POST","headers":{"Accept":"*/*"}},"response":{"status":200,"headers":{"Content-Type":"application/json"},"body":"{\n  \"accepted\": true\n}"}}

  a webhook.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026452464&#39;); return false;"><em><span id="link-idm532026452464">expand</span></em></a>\]

  </div>

  <div id="idm532026452464" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to test a connection.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026449360&#39;); return false;"><em><span id="link-idm532026449360">expand</span></em></a>\]

  </div>

  <div id="idm532026449360" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The repository does not exist.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/webhooks/{webhookId}

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **webhookId** | *[int](http://www.w3.org/TR/xmlschema-2/#int)* | the existing webhook id |

###### Methods

<div class="methods">

<div class="method">

#### DELETE

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Delete a webhook for the repository specified via the URL.

The authenticated user must have **REPO_ADMIN** permission for the specified repository to call this resource.

*Example response representations:*

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532063455504&#39;); return false;"><em><span id="link-idm532063455504">expand</span></em></a>\]

  </div>

  <div id="idm532063455504" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to delete webhooks in the repository.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532063455376&#39;); return false;"><em><span id="link-idm532063455376">expand</span></em></a>\]

  </div>

  <div id="idm532063455376" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The repository does not exist, or webhook does not exist in this repository.

  <div class="representation">

  </div>

  </div>

</div>

<div class="method">

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/webhooks/{webhookId}<span class="optional">?statistics</span>

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Get a webhook by id.

The authenticated user must have **REPO_ADMIN** permission for the specified repository to call this resource.

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
<td><p><strong>statistics</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#boolean">boolean</a></em></p>
<p>Default: <code>false</code></p></td>
<td></td>
</tr>
</tbody>
</table>

*Example response representations:*

- <div>

  200 - application/json (webhook) \[<a href="#" onclick="toggle(&#39;idm532026508112&#39;); return false;"><em><span id="link-idm532026508112">expand</span></em></a>\]

  </div>

  <div id="idm532026508112" class="toggle">

  ###### Example

      {"id":10,"name":"Webhook Name","createdDate":1513106011000,"updatedDate":1513106011000,"events":["repo:refs_updated","repo:modified"],"configuration":{"secret":"password"},"url":"http://example.com","active":true}

  a webhook.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026506400&#39;); return false;"><em><span id="link-idm532026506400">expand</span></em></a>\]

  </div>

  <div id="idm532026506400" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to get a webhook in the repository.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026504080&#39;); return false;"><em><span id="link-idm532026504080">expand</span></em></a>\]

  </div>

  <div id="idm532026504080" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The repository does not exist, or the webhook does not exist in the repository.

  <div class="representation">

  </div>

  </div>

</div>

<div class="method">

#### PUT

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Update an existing webhook.

The authenticated user must have **REPO_ADMIN** permission for the specified repository to call this resource.

*Example request representations:*

- <div>

  application/json \[<a href="#" onclick="toggle(&#39;idm532026499920&#39;); return false;"><em><span id="link-idm532026499920">expand</span></em></a>\]

  </div>

  <div id="idm532026499920" class="toggle">

  </div>

*Example response representations:*

- <div>

  200 - application/json (webhook) \[<a href="#" onclick="toggle(&#39;idm532026499792&#39;); return false;"><em><span id="link-idm532026499792">expand</span></em></a>\]

  </div>

  <div id="idm532026499792" class="toggle">

  ###### Example

      {"id":10,"name":"Webhook Name","createdDate":1513106011000,"updatedDate":1513106011000,"events":["repo:refs_updated","repo:modified"],"configuration":{"secret":"password"},"url":"http://example.com","active":true}

  a webhook.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026496800&#39;); return false;"><em><span id="link-idm532026496800">expand</span></em></a>\]

  </div>

  <div id="idm532026496800" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to update a webhook in this repository.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026494432&#39;); return false;"><em><span id="link-idm532026494432">expand</span></em></a>\]

  </div>

  <div id="idm532026494432" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The repository does not exist, or the webhook does not exist in the repository.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/webhooks/{webhookId}/latest

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **webhookId** | *[int](http://www.w3.org/TR/xmlschema-2/#int)* | id of the webhook |

###### Methods

<div class="methods">

<div class="method">

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/webhooks/{webhookId}/latest<span class="optional">?event</span><span class="optional">&outcome</span>

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Get the latest invocations for a specific webhook.

The authenticated user must have **REPO_ADMIN** permission for the specified repository to call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **event** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the string id of a specific event to retrieve the last invocation for. |
| **outcome** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the outcome to filter for. Can be SUCCESS, FAILURE, ERROR. None specified means that the all will be considered |

*Example response representations:*

- <div>

  200 - application/json (webhookInvocation) \[<a href="#" onclick="toggle(&#39;idm532026486928&#39;); return false;"><em><span id="link-idm532026486928">expand</span></em></a>\]

  </div>

  <div id="idm532026486928" class="toggle">

  ###### Example

      {"id":10,"event":"repo:created","duration":155,"start":1513106011,"finish":1513106166,"request":{"method":"POST","url":"http://example.com/callback"},"result":{"description":"200","outcome":"SUCCESS"}}

  a webhook invocation dataset.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026488000&#39;); return false;"><em><span id="link-idm532026488000">expand</span></em></a>\]

  </div>

  <div id="idm532026488000" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to get webhook invocations in the repository.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026481504&#39;); return false;"><em><span id="link-idm532026481504">expand</span></em></a>\]

  </div>

  <div id="idm532026481504" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The repository does not exist, or the webhook does not exist in the repository.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/webhooks/{webhookId}/statistics

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **webhookId** | *[int](http://www.w3.org/TR/xmlschema-2/#int)* | id of the webhook |

###### Methods

<div class="methods">

<div class="method">

#### GET

###### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/webhooks/{webhookId}/statistics<span class="optional">?event</span>

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Get the statistics for a specific webhook.

The authenticated user must have **REPO_ADMIN** permission for the specified repository to call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **event** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the string id of a specific event to retrieve the last invocation for. May be empty, in which case all events are considered |

*Example response representations:*

- <div>

  200 - application/json (webhookInvocation) \[<a href="#" onclick="toggle(&#39;idm532026475360&#39;); return false;"><em><span id="link-idm532026475360">expand</span></em></a>\]

  </div>

  <div id="idm532026475360" class="toggle">

  ###### Example

      {"lastSuccess":{"id":10,"event":"repo:created","duration":155,"start":1513106011,"finish":1513106166,"request":{"method":"POST","url":"http://example.com/callback"},"result":{"description":"200","outcome":"SUCCESS"}},"lastFailure":{"id":11,"event":"repo:refs_updated","duration":100,"start":1513106011,"finish":1513106111,"request":{"method":"POST","url":"http://example.com/callback"},"result":{"description":"404","outcome":"FAILURE"}},"lastError":{"id":12,"event":"repo:modified","duration":100,"start":1513106011,"finish":1513106111,"request":{"method":"POST","url":"http://example.com/callback"},"result":{"description":"Detailed error message","outcome":"ERROR"}},"counts":100}

  a webhook invocation dataset.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026472528&#39;); return false;"><em><span id="link-idm532026472528">expand</span></em></a>\]

  </div>

  <div id="idm532026472528" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to get webhook statistics in the repository.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026469680&#39;); return false;"><em><span id="link-idm532026469680">expand</span></em></a>\]

  </div>

  <div id="idm532026469680" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The repository does not exist, or the webhook does not exist in the repository.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/repos/{repositorySlug}/webhooks/{webhookId}/statistics/summary

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **webhookId** | *[int](http://www.w3.org/TR/xmlschema-2/#int)* | id of the webhook |

###### Methods

<div class="methods">

<div class="method">

#### GET

*This API can also be invoked via a [user-centric URL](#personal-repositories) when addressing repositories in personal projects*.\
\
Get the statistics summary for a specific webhook.

The authenticated user must have **REPO_ADMIN** permission for the specified repository to call this resource.

*Example response representations:*

- <div>

  200 - application/json (webhookInvocation) \[<a href="#" onclick="toggle(&#39;idm532026464704&#39;); return false;"><em><span id="link-idm532026464704">expand</span></em></a>\]

  </div>

  <div id="idm532026464704" class="toggle">

  ###### Example

      {"lastSuccess":{"id":10,"event":"repo:created","duration":155,"start":1513106011,"finish":1513106166,"request":{"method":"POST","url":"http://example.com/callback"},"result":{"description":"200","outcome":"SUCCESS"}},"lastFailure":{"id":11,"event":"repo:refs_updated","duration":100,"start":1513106011,"finish":1513106111,"request":{"method":"POST","url":"http://example.com/callback"},"result":{"description":"404","outcome":"FAILURE"}},"lastError":{"id":12,"event":"repo:modified","duration":100,"start":1513106011,"finish":1513106111,"request":{"method":"POST","url":"http://example.com/callback"},"result":{"description":"Detailed error message","outcome":"ERROR"}},"counts":100}

  a webhook invocation dataset.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026462176&#39;); return false;"><em><span id="link-idm532026462176">expand</span></em></a>\]

  </div>

  <div id="idm532026462176" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to get webhook statistics summary in the repository.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026459328&#39;); return false;"><em><span id="link-idm532026459328">expand</span></em></a>\]

  </div>

  <div id="idm532026459328" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The repository does not exist, or the webhook does not exist in the repository.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/settings/pull-requests/{scmId}

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **scmId** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | the SCM to get strategies for |

###### Methods

<div class="methods">

<div class="method">

#### POST

Update the pull request merge strategy configuration for this project and SCM.

The authenticated user must have **PROJECT_ADMIN** permission for the context repository to call this resource.

Only the strategies provided will be enabled, the default must be set and included in the set of strategies.

An explicitly set pull request merge strategy configuration can be deleted by POSTing a document with an empty "mergeConfig" attribute. i.e:

\
 {\
     "mergeConfig": {\
     }\
 }\
 

Upon completion of this request, the effective configuration will be the configuration explicitly set for the SCM, or if no such explicit configuration is set then the default configuration will be used.

*Example request representations:*

- <div>

  application/json \[<a href="#" onclick="toggle(&#39;idm532027301120&#39;); return false;"><em><span id="link-idm532027301120">expand</span></em></a>\]

  </div>

  <div id="idm532027301120" class="toggle">

  ###### Example

      {"mergeConfig":{"defaultStrategy":{"id":"no-ff"},"strategies":[{"id":"no-ff"}]}}

  </div>

*Example response representations:*

- <div>

  200 - application/json (strategies) \[<a href="#" onclick="toggle(&#39;idm532027298832&#39;); return false;"><em><span id="link-idm532027298832">expand</span></em></a>\]

  </div>

  <div id="idm532027298832" class="toggle">

  ###### Example

      {"mergeConfig":{"defaultStrategy":{"description":"Always create a merge commit","enabled":true,"flag":"--no-ff","id":"no-ff","name":"Merge commit"},"strategies":[{"description":"Always create a merge commit","enabled":true,"flag":"--no-ff","id":"no-ff","name":"Merge commit"}],"type":"repository"}}

  The repository pull request merge strategies for the context repository.

  <div class="representation">

  </div>

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532027298208&#39;); return false;"><em><span id="link-idm532027298208">expand</span></em></a>\]

  </div>

  <div id="idm532027298208" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The repository pull request merge strategies were not updated due to a validation error.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532063434288&#39;); return false;"><em><span id="link-idm532063434288">expand</span></em></a>\]

  </div>

  <div id="idm532063434288" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to administrate the specified repository.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532063431664&#39;); return false;"><em><span id="link-idm532063431664">expand</span></em></a>\]

  </div>

  <div id="idm532063431664" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository does not exist.

  <div class="representation">

  </div>

  </div>

</div>

<div class="method">

#### GET

*This is a [paged API](#paging-params)*.\
\
Retrieve the merge strategy configuration for this project and SCM.

The authenticated user must have **PROJECT_READ** permission for the context repository to call this resource.

*Example response representations:*

- <div>

  200 - application/json ([page](#paging-params)) \[<a href="#" onclick="toggle(&#39;idm532063428304&#39;); return false;"><em><span id="link-idm532063428304">expand</span></em></a>\]

  </div>

  <div id="idm532063428304" class="toggle">

  ###### Example

      {"mergeConfig":{"defaultStrategy":{"description":"Always create a merge commit","enabled":true,"flag":"--no-ff","id":"no-ff","name":"Merge commit"},"strategies":[{"description":"Always create a merge commit","enabled":true,"flag":"--no-ff","id":"no-ff","name":"Merge commit"}],"type":"repository"}}

  The merge configuration of the request project.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532063425536&#39;); return false;"><em><span id="link-idm532063425536">expand</span></em></a>\]

  </div>

  <div id="idm532063425536" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to see the request repository.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532027294192&#39;); return false;"><em><span id="link-idm532027294192">expand</span></em></a>\]

  </div>

  <div id="idm532027294192" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The request repository does not exist.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/settings/hooks

###### Methods

<div class="methods">

<div class="method">

#### GET

###### /rest/api/1.0/projects/{projectKey}/settings/hooks<span class="optional">?type</span>

*This is a [paged API](#paging-params)*.\
\
Retrieve a page of repository hooks for this project.

The authenticated user must have **PROJECT_READ** permission for the specified project to call this resource.

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
<td><p><strong>type</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a></em></p>
<p>Default:</p></td>
<td><p>the optional type to filter by. Valid values are <code>PRE_RECEIVE</code> or <code>POST_RECEIVE</code></p></td>
</tr>
</tbody>
</table>

*Example response representations:*

- <div>

  200 - application/json ([page](#paging-params)) \[<a href="#" onclick="toggle(&#39;idm532023629680&#39;); return false;"><em><span id="link-idm532023629680">expand</span></em></a>\]

  </div>

  <div id="idm532023629680" class="toggle">

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"details":{"key":"com.atlassian.stash.plugin.example:example-repository-hook","name":"Example repository hook","type":"PRE_RECEIVE","description":"An example description for an example hook.","version":"1.2.4","configFormKey":null,"scopeTypes":["PROJECT","REPOSITORY"]},"enabled":true,"configured":true,"scope":{"resourceId":2,"type":"REPOSITORY"}}],"start":0}

  returns a page of repository hooks with their associated enabled state.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532023628400&#39;); return false;"><em><span id="link-idm532023628400">expand</span></em></a>\]

  </div>

  <div id="idm532023628400" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to retrieve the hooks.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532023624432&#39;); return false;"><em><span id="link-idm532023624432">expand</span></em></a>\]

  </div>

  <div id="idm532023624432" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified project does not exist.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/settings/hooks/{hookKey}

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **hookKey** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* |  |

###### Methods

<div class="methods">

<div class="method">

#### GET

Retrieve a repository hook for this project.

The authenticated user must have **PROJECT_READ** permission for the specified project to call this resource.

*Example response representations:*

- <div>

  200 - application/json \[<a href="#" onclick="toggle(&#39;idm532027171392&#39;); return false;"><em><span id="link-idm532027171392">expand</span></em></a>\]

  </div>

  <div id="idm532027171392" class="toggle">

  ###### Example

      {"details":{"key":"com.atlassian.stash.plugin.example:example-repository-hook","name":"Example repository hook","type":"PRE_RECEIVE","description":"An example description for an example hook.","version":"1.2.4","configFormKey":null,"scopeTypes":["PROJECT","REPOSITORY"]},"enabled":true,"configured":true,"scope":{"resourceId":2,"type":"REPOSITORY"}}

  returns the repository hooks with their associated enabled state for the supplied hookKey.

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532027169728&#39;); return false;"><em><span id="link-idm532027169728">expand</span></em></a>\]

  </div>

  <div id="idm532027169728" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to retrieve the hook.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532027167136&#39;); return false;"><em><span id="link-idm532027167136">expand</span></em></a>\]

  </div>

  <div id="idm532027167136" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified repository hook does not exist for the given project, or the project does not exist.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/settings/hooks/{hookKey}/enabled

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **hookKey** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* |  |

###### Methods

<div class="methods">

<div class="method">

#### PUT

Enable a repository hook for this project and optionally apply new configuration.

The authenticated user must have **PROJECT_ADMIN** permission for the specified project to call this resource.

A JSON document may be provided to use as the settings for the hook. These structure and validity of the document is decided by the plugin providing the hook.

###### request header parameters

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
<td><p><strong>Content-Length</strong></p></td>
<td><p><em><a href="http://www.w3.org/TR/xmlschema-2/#int">int</a></em></p>
<p>Default: <code>0</code></p></td>
<td></td>
</tr>
</tbody>
</table>

*Example response representations:*

- <div>

  200 - application/json \[<a href="#" onclick="toggle(&#39;idm532027191680&#39;); return false;"><em><span id="link-idm532027191680">expand</span></em></a>\]

  </div>

  <div id="idm532027191680" class="toggle">

  ###### Example

      {"details":{"key":"com.atlassian.stash.plugin.example:example-repository-hook","name":"Example repository hook","type":"PRE_RECEIVE","description":"An example description for an example hook.","version":"1.2.4","configFormKey":null,"scopeTypes":["PROJECT","REPOSITORY"]},"enabled":true,"configured":true,"scope":{"resourceId":2,"type":"REPOSITORY"}}

  returns the repository hooks with their associated enabled state for the supplied hookKey.

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532027191552&#39;); return false;"><em><span id="link-idm532027191552">expand</span></em></a>\]

  </div>

  <div id="idm532027191552" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The settings specified are invalid.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532027186480&#39;); return false;"><em><span id="link-idm532027186480">expand</span></em></a>\]

  </div>

  <div id="idm532027186480" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to enable the hook.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532027184208&#39;); return false;"><em><span id="link-idm532027184208">expand</span></em></a>\]

  </div>

  <div id="idm532027184208" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified project or hook does not exist.

  <div class="representation">

  </div>

  </div>

</div>

<div class="method">

#### DELETE

Disable a repository hook for this project.

The authenticated user must have **PROJECT_ADMIN** permission for the specified project to call this resource.

*Example response representations:*

- <div>

  200 - application/json \[<a href="#" onclick="toggle(&#39;idm532027180960&#39;); return false;"><em><span id="link-idm532027180960">expand</span></em></a>\]

  </div>

  <div id="idm532027180960" class="toggle">

  ###### Example

      {"details":{"key":"com.atlassian.stash.plugin.example:example-repository-hook","name":"Example repository hook","type":"PRE_RECEIVE","description":"An example description for an example hook.","version":"1.2.4","configFormKey":null,"scopeTypes":["PROJECT","REPOSITORY"]},"enabled":true,"configured":true,"scope":{"resourceId":2,"type":"REPOSITORY"}}

  returns the repository hooks with their associated enabled state for the supplied hookKey.

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532027178640&#39;); return false;"><em><span id="link-idm532027178640">expand</span></em></a>\]

  </div>

  <div id="idm532027178640" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to disable the hook.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532027176032&#39;); return false;"><em><span id="link-idm532027176032">expand</span></em></a>\]

  </div>

  <div id="idm532027176032" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified project or hook does not exist.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/projects/{projectKey}/settings/hooks/{hookKey}/settings

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **hookKey** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* |  |

###### Methods

<div class="methods">

<div class="method">

#### GET

Retrieve the settings for a repository hook for this project.

The authenticated user must have **PROJECT_READ** permission for the specified project to call this resource.

*Example response representations:*

- <div>

  200 - application/json \[<a href="#" onclick="toggle(&#39;idm532023618080&#39;); return false;"><em><span id="link-idm532023618080">expand</span></em></a>\]

  </div>

  <div id="idm532023618080" class="toggle">

  ###### Example

      {"string-value":"this is an arbitrary string","integer-value":1,"long-value":2147483648,"boolean-value":true,"double-value":1.1}

  The settings for the hook.

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532023617952&#39;); return false;"><em><span id="link-idm532023617952">expand</span></em></a>\]

  </div>

  <div id="idm532023617952" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to retrieve the hook settings.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532023613248&#39;); return false;"><em><span id="link-idm532023613248">expand</span></em></a>\]

  </div>

  <div id="idm532023613248" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified project or hook does not exist.

  <div class="representation">

  </div>

  </div>

</div>

<div class="method">

#### PUT

Modify the settings for a repository hook for this project.

The service will reject any settings which are too large, the current limit is 32KB once serialized.

The authenticated user must have **PROJECT_ADMIN** permission for the specified project to call this resource.

A JSON document can be provided to use as the settings for the hook. These structure and validity of the document is decided by the plugin providing the hook.

*Example request representations:*

- <div>

  application/json \[<a href="#" onclick="toggle(&#39;idm532023610224&#39;); return false;"><em><span id="link-idm532023610224">expand</span></em></a>\]

  </div>

  <div id="idm532023610224" class="toggle">

  ###### Example

      {"string-value":"this is an arbitrary string","integer-value":1,"long-value":2147483648,"boolean-value":true,"double-value":1.1}

  </div>

*Example response representations:*

- <div>

  200 - application/json \[<a href="#" onclick="toggle(&#39;idm532064999040&#39;); return false;"><em><span id="link-idm532064999040">expand</span></em></a>\]

  </div>

  <div id="idm532064999040" class="toggle">

  ###### Example

      {"string-value":"this is an arbitrary string","integer-value":1,"long-value":2147483648,"boolean-value":true,"double-value":1.1}

  The settings for the hook.

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025343024&#39;); return false;"><em><span id="link-idm532025343024">expand</span></em></a>\]

  </div>

  <div id="idm532025343024" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The settings specified are invalid.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532027200704&#39;); return false;"><em><span id="link-idm532027200704">expand</span></em></a>\]

  </div>

  <div id="idm532027200704" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to modify the hook settings.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532027199568&#39;); return false;"><em><span id="link-idm532027199568">expand</span></em></a>\]

  </div>

  <div id="idm532027199568" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified project or hook does not exist.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/repos

REST resource for searching through repositories

###### Methods

<div class="methods">

<div class="method">

#### GET

###### /rest/api/1.0/repos<span class="optional">?name</span><span class="optional">&projectname</span><span class="optional">&permission</span><span class="optional">&visibility</span>

*This is a [paged API](#paging-params)*.\
\
Retrieve a page of repositories based on query parameters that control the search. See the documentation of the parameters for more details.

This resource is anonymously accessible.

**Note on permissions.** In absence of the {@code permission} query parameter the implicit 'read' permission is assumed. Please note that this permission is lower than the REPO_READ permission rather than being equal to it. The implicit 'read' permission for a given repository is assigned to any user that has any of the higher permissions, such as `REPO_READ`, as well as to anonymous users if the repository is marked as public. The important implication of the above is that an anonymous request to this resource with a permission level `REPO_READ` is guaranteed to receive an empty list of repositories as a result. For anonymous requests it is therefore recommended to not specify the `permission` parameter at all.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **name** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | (optional) if specified, this will limit the resulting repository list to ones whose name matches this parameter's value. The match will be done case-insensitive and any leading and/or trailing whitespace characters on the `name` parameter will be stripped. |
| **projectname** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | (optional) if specified, this will limit the resulting repository list to ones whose project's name matches this parameter's value. The match will be done case-insensitive and any leading and/or trailing whitespace characters on the `projectname` parameter will be stripped. |
| **permission** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | (optional) if specified, it must be a valid repository permission level name and will limit the resulting repository list to ones that the requesting user has the specified permission level to. If not specified, the default implicit 'read' permission level will be assumed. The currently supported explicit permission values are `REPO_READ`, `REPO_WRITE` and `REPO_ADMIN`. |
| **visibility** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | (optional) if specified, this will limit the resulting repository list based on the repositories visibility. Valid values are *public* or *private*. |

*Example response representations:*

- <div>

  200 - application/json ([page](#paging-params)) \[<a href="#" onclick="toggle(&#39;idm532026155376&#39;); return false;"><em><span id="link-idm532026155376">expand</span></em></a>\]

  </div>

  <div id="idm532026155376" class="toggle">

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"slug":"my-repo","id":1,"name":"My repo","scmId":"git","state":"AVAILABLE","statusMessage":"Available","forkable":true,"project":{"key":"PRJ","id":1,"name":"My Cool Project","description":"The description for my cool project.","public":true,"type":"NORMAL","links":{"self":[{"href":"http://link/to/project"}]}},"public":true,"links":{"clone":[{"href":"ssh://git@<baseURL>/PRJ/my-repo.git","name":"ssh"},{"href":"https://<baseURL>/scm/PRJ/my-repo.git","name":"http"}],"self":[{"href":"http://link/to/repository"}]}}],"start":0}

  A page of repositories.

  <div class="representation">

  </div>

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026153712&#39;); return false;"><em><span id="link-idm532026153712">expand</span></em></a>\]

  </div>

  <div id="idm532026153712" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The `visibility` parameter contains an invalid value

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/tasks

###### Methods

<div class="methods">

<div class="method">

#### POST

Create a new task.

*Example request representations:*

- <div>

  application/json \[<a href="#" onclick="toggle(&#39;idm532061725792&#39;); return false;"><em><span id="link-idm532061725792">expand</span></em></a>\]

  </div>

  <div id="idm532061725792" class="toggle">

  ###### Example

      {"anchor":{"id":1,"type":"COMMENT"},"text":"Fix the missing imports"}

  </div>

*Example response representations:*

- <div>

  201 - application/json (task) \[<a href="#" onclick="toggle(&#39;idm532061724016&#39;); return false;"><em><span id="link-idm532061724016">expand</span></em></a>\]

  </div>

  <div id="idm532061724016" class="toggle">

  ###### Example

      {"anchor":{"properties":{"key":"value"},"id":1,"version":1,"text":"An insightful comment.","author":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"createdDate":1527228363411,"updatedDate":1527228363411,"comments":[],"tasks":[],"permittedOperations":{"editable":true,"deletable":true}},"author":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"createdDate":1527228364841,"id":99,"permittedOperations":{"deletable":true,"editable":true,"transitionable":true},"text":"Fix the missing imports"}

  A copy of the created task.

  <div class="representation">

  </div>

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061723376&#39;); return false;"><em><span id="link-idm532061723376">expand</span></em></a>\]

  </div>

  <div id="idm532061723376" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  If the task data is invalid (for example, if the task's text is missing or blank)

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061719136&#39;); return false;"><em><span id="link-idm532061719136">expand</span></em></a>\]

  </div>

  <div id="idm532061719136" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  If the anchor of the task (such as a pull request comment) does not exist or is not visible to the current user

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/tasks/{taskId}

###### resource-wide template parameters

| parameter | value | description |
|----|----|----|
| **taskId** | *[long](http://www.w3.org/TR/xmlschema-2/#long)* | the id identifying the task to delete |

###### Methods

<div class="methods">

<div class="method">

#### GET

Retrieve a existing task.

*Example response representations:*

- <div>

  200 - application/json (task) \[<a href="#" onclick="toggle(&#39;idm532061714208&#39;); return false;"><em><span id="link-idm532061714208">expand</span></em></a>\]

  </div>

  <div id="idm532061714208" class="toggle">

  ###### Example

      {"properties":{"diffAnchorPath":"path/to/file.txt"},"anchor":{"properties":{"key":"value"},"id":1,"version":1,"text":"An insightful comment.","author":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"createdDate":1527228363411,"updatedDate":1527228363411,"comments":[],"tasks":[],"permittedOperations":{"editable":true,"deletable":true}},"author":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"createdDate":1527228364842,"id":99,"permittedOperations":{"deletable":false,"editable":false,"transitionable":true},"text":"Resolve the merge conflicts","state":"OPEN"}

  A copy of the task.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061711456&#39;); return false;"><em><span id="link-idm532061711456">expand</span></em></a>\]

  </div>

  <div id="idm532061711456" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  If the task does not exist

  <div class="representation">

  </div>

  </div>

</div>

<div class="method">

#### DELETE

Delete a task.

Note that only the task's creator, the context's author or an admin of the context's repository can delete a task. (For a pull request task, those are the task's creator, the pull request's author or an admin on the repository containing the pull request). Additionally a task cannot be deleted if it has already been resolved.

*Example response representations:*

- <div>

  204 (task) \[<a href="#" onclick="toggle(&#39;idm532061705968&#39;); return false;"><em><span id="link-idm532061705968">expand</span></em></a>\]

  </div>

  <div id="idm532061705968" class="toggle">

  if the task was successfully deleted.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061707360&#39;); return false;"><em><span id="link-idm532061707360">expand</span></em></a>\]

  </div>

  <div id="idm532061707360" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  If the current user does not have the permission to delete the task

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061704320&#39;); return false;"><em><span id="link-idm532061704320">expand</span></em></a>\]

  </div>

  <div id="idm532061704320" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  If the task does not exist

  <div class="representation">

  </div>

  </div>

- <div>

  409 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061703216&#39;); return false;"><em><span id="link-idm532061703216">expand</span></em></a>\]

  </div>

  <div id="idm532061703216" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  If the task to delete is in the resolved state

  <div class="representation">

  </div>

  </div>

</div>

<div class="method">

#### PUT

Update a existing task.

As of Stash 3.3, only the state and text of a task can be updated.

Updating the state of a task is allowed for any user having *READ* access to the repository. However only the task's creator, the context's author or an admin of the context's repository can update the task's text. (For a pull request task, those are the task's creator, the pull request's author or an admin on the repository containing the pull request). Additionally the task's text cannot be updated if it has been resolved.

*Example request representations:*

- <div>

  application/json \[<a href="#" onclick="toggle(&#39;idm532061697824&#39;); return false;"><em><span id="link-idm532061697824">expand</span></em></a>\]

  </div>

  <div id="idm532061697824" class="toggle">

  ###### Example

      {"id":99,"text":"Fix the missing and obsolete imports"}

  </div>

*Example response representations:*

- <div>

  200 - application/json (task) \[<a href="#" onclick="toggle(&#39;idm532061697216&#39;); return false;"><em><span id="link-idm532061697216">expand</span></em></a>\]

  </div>

  <div id="idm532061697216" class="toggle">

  ###### Example

      {"properties":{"diffAnchorPath":"path/to/file.txt"},"anchor":{"properties":{"key":"value"},"id":1,"version":1,"text":"An insightful comment.","author":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"createdDate":1527228363411,"updatedDate":1527228363411,"comments":[],"tasks":[],"permittedOperations":{"editable":true,"deletable":true}},"author":{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"},"createdDate":1527228364841,"id":99,"permittedOperations":{"deletable":true,"editable":true,"transitionable":true},"text":"Fix the missing and deprecated imports","state":"OPEN"}

  A copy of the task if it was successfully updated.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061695472&#39;); return false;"><em><span id="link-idm532061695472">expand</span></em></a>\]

  </div>

  <div id="idm532061695472" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  If the current user does not have the permission to update the task

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061691808&#39;); return false;"><em><span id="link-idm532061691808">expand</span></em></a>\]

  </div>

  <div id="idm532061691808" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  If the task does not exist

  <div class="representation">

  </div>

  </div>

- <div>

  409 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532061689808&#39;); return false;"><em><span id="link-idm532061689808">expand</span></em></a>\]

  </div>

  <div id="idm532061689808" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  If the task to update is in the resolved state

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/users

###### Methods

<div class="methods">

<div class="method">

#### GET

*This is a [paged API](#paging-params)*.\
\
Retrieve a page of users, optionally run through provided filters.

Only authenticated users may call this resource.

### Supported Filters

Filters are provided in query parameters in a standard `name=value` fashion. The following filters are currently supported:

- {@code filter} - return only users, whose username, name or email address *contain* the {@code filter} value
- {@code group} - return only users who are members of the given group
- {@code permission} - the "root" of a permission filter, whose value must be a valid global, project, or repository permission. Additional filter parameters referring to this filter that specify the resource (project or repository) to apply the filter to must be prefixed with `permission.`. See the section "Permission Filters" below for more details.
- {@code permission.N} - the "root" of a single permission filter, similar to the {@code permission} parameter, where "N" is a natural number starting from 1. This allows clients to specify multiple permission filters, by providing consecutive filters as {@code permission.1}, {@code permission.2} etc. Note that the filters numbering has to start with 1 and be continuous for all filters to be processed. The total allowed number of permission filters is 50 and all filters exceeding that limit will be dropped. See the section "Permission Filters" below for more details on how the permission filters are processed.

### Permission Filters

The following three sub-sections list parameters supported for permission filters (where `[root]` is the root permission filter name, e.g. {@code permission}, {@code permission.1} etc.) depending on the permission resource. The system determines which filter to apply (Global, Project or Repository permission) based on the `[root]` permission value. E.g. {@code ADMIN} is a global permission, {@code PROJECT_ADMIN} is a project permission and {@code REPO_ADMIN} is a repository permission. Note that the parameters for a given resource will be looked up in the order as they are listed below, that is e.g. for a project resource, if both {@code projectId} and {@code projectKey} are provided, the system will use {@code projectId} for the lookup.

#### Global permissions

The permission value under `[root]` is the only required and recognized parameter, as global permissions do not apply to a specific resource.

Example valid filter: `permission=ADMIN`.

#### Project permissions

- `[root]`- specifies the project permission
- `[root].projectId` - specifies the project ID to lookup the project by
- `[root].projectKey` - specifies the project key to lookup the project by

Example valid filter: `permission.1=PROJECT_ADMIN&permission.1.projectKey=TEST_PROJECT`.

#### Repository permissions

- `[root]`- specifies the repository permission
- `[root].projectId` - specifies the repository ID to lookup the repository by
- `[root].projectKey` and `[root].repositorySlug`- specifies the project key and repository slug to lookup the repository by; both values *need to* be provided for this look up to be triggered

Example valid filter: `permission.2=REPO_ADMIN&permission.2.projectKey=TEST_PROJECT&permission.2.repositorySlug=test_repo`.

*Example response representations:*

- <div>

  200 - application/json ([page](#paging-params)) \[<a href="#" onclick="toggle(&#39;idm532026231392&#39;); return false;"><em><span id="link-idm532026231392">expand</span></em></a>\]

  </div>

  <div id="idm532026231392" class="toggle">

  ###### Example

      {"size":1,"limit":25,"isLastPage":true,"values":[{"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"}],"start":0}

  A page of users.

  <div class="representation">

  </div>

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026228944&#39;); return false;"><em><span id="link-idm532026228944">expand</span></em></a>\]

  </div>

  <div id="idm532026228944" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The search request was invalid, which may happen for multiple reasons, among others:

  - permission filter for project/repository permission with no parameters specifying the project or repository to apply the filter to
  - invalid permission name
  - permission filter for a project/repository permission pointing to a non-existent project or repository

  The exact reason for the error and - in most cases - the request parameter name that had invalid value - will be provided in the error message.
  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026227760&#39;); return false;"><em><span id="link-idm532026227760">expand</span></em></a>\]

  </div>

  <div id="idm532026227760" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  Authentication failed or was not attempted.

  <div class="representation">

  </div>

  </div>

</div>

<div class="method">

#### PUT

Update the currently authenticated user's details. The update will always be applied to the currently authenticated user.

*Example request representations:*

- <div>

  application/json \[<a href="#" onclick="toggle(&#39;idm532026222624&#39;); return false;"><em><span id="link-idm532026222624">expand</span></em></a>\]

  </div>

  <div id="idm532026222624" class="toggle">

  ###### Example

      {"name":null,"displayName":"Jane Citizen","email":"jane@example.com"}

  </div>

*Example response representations:*

- <div>

  200 - application/json (detailedUser) \[<a href="#" onclick="toggle(&#39;idm532026222240&#39;); return false;"><em><span id="link-idm532026222240">expand</span></em></a>\]

  </div>

  <div id="idm532026222240" class="toggle">

  ###### Example

      {"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"}

  The updated user.

  <div class="representation">

  </div>

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026219504&#39;); return false;"><em><span id="link-idm532026219504">expand</span></em></a>\]

  </div>

  <div id="idm532026219504" class="toggle">

  ###### Example

      {"errors":[{"context":"field_a","message":"A detailed validation error message for field_a.","exceptionName":null},{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The request was malformed.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026217200&#39;); return false;"><em><span id="link-idm532026217200">expand</span></em></a>\]

  </div>

  <div id="idm532026217200" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  Authentication failed or was not attempted.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/users/credentials

###### Methods

<div class="methods">

<div class="method">

#### PUT

Update the currently authenticated user's password.

*Example request representations:*

- <div>

  application/json \[<a href="#" onclick="toggle(&#39;idm532025493936&#39;); return false;"><em><span id="link-idm532025493936">expand</span></em></a>\]

  </div>

  <div id="idm532025493936" class="toggle">

  ###### Example

      {"password":"secret","passwordConfirm":"secret","oldPassword":"faithless"}

  </div>

*Example response representations:*

- <div>

  204 \[<a href="#" onclick="toggle(&#39;idm532026197808&#39;); return false;"><em><span id="link-idm532026197808">expand</span></em></a>\]

  </div>

  <div id="idm532026197808" class="toggle">

  The user's password was successfully updated.

  </div>

- <div>

  400 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026202368&#39;); return false;"><em><span id="link-idm532026202368">expand</span></em></a>\]

  </div>

  <div id="idm532026202368" class="toggle">

  ###### Example

      {"errors":[{"context":"field_a","message":"A detailed validation error message for field_a.","exceptionName":null},{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The request was malformed or the old password was incorrect.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026200512&#39;); return false;"><em><span id="link-idm532026200512">expand</span></em></a>\]

  </div>

  <div id="idm532026200512" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  Authentication failed or was not attempted.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/users/{userSlug}

###### Methods

<div class="methods">

<div class="method">

#### GET

Retrieve the user matching the supplied **userSlug**.

*Example response representations:*

- <div>

  200 - application/json (userSlug) \[<a href="#" onclick="toggle(&#39;idm532026212656&#39;); return false;"><em><span id="link-idm532026212656">expand</span></em></a>\]

  </div>

  <div id="idm532026212656" class="toggle">

  ###### Example

      {"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"}

  The user matching the supplied **userSlug**. Note, this may *not* be the user's username, always use the **user.slug** property.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026210032&#39;); return false;"><em><span id="link-idm532026210032">expand</span></em></a>\]

  </div>

  <div id="idm532026210032" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the user.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532026208640&#39;); return false;"><em><span id="link-idm532026208640">expand</span></em></a>\]

  </div>

  <div id="idm532026208640" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified user does not exist.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/users/{userSlug}/avatar.png

###### Methods

<div class="methods">

<div class="method">

#### DELETE

Delete the avatar associated to a user.

Users are always allowed to delete their own avatar. To delete someone else's avatar the authenticated user must have global **ADMIN** permission, or global **SYS_ADMIN** permission to update a **SYS_ADMIN** user's avatar.

*Example response representations:*

- <div>

  200 - application/json (href) \[<a href="#" onclick="toggle(&#39;idm532026203552&#39;); return false;"><em><span id="link-idm532026203552">expand</span></em></a>\]

  </div>

  <div id="idm532026203552" class="toggle">

  ###### Example

      {"href":"http://www.gravatar.com/avatar/aa99b351245441b8ca95d54a52d2998c"}

  The new avatar URL if the local avatar was successfully deleted or did not exist

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025506640&#39;); return false;"><em><span id="link-idm532025506640">expand</span></em></a>\]

  </div>

  <div id="idm532025506640" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The authenticated user has insufficient permissions to delete the specified avatar.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025505504&#39;); return false;"><em><span id="link-idm532025505504">expand</span></em></a>\]

  </div>

  <div id="idm532025505504" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified user does not exist.

  <div class="representation">

  </div>

  </div>

</div>

<div class="method">

#### POST

Update the avatar for the user with the supplied **slug**.

This resource accepts POST multipart form data, containing a single image in a form-field named 'avatar'.

There are configurable server limits on both the dimensions (1024x1024 pixels by default) and uploaded file size (1MB by default). Several different image formats are supported, but **PNG** and **JPEG** are preferred due to the file size limit.

This resource has Cross-Site Request Forgery (XSRF) protection. To allow the request to pass the XSRF check the caller needs to send an `X-Atlassian-Token` HTTP header with the value `no-check`.

An example [curl](http://curl.haxx.se/) request to upload an image name 'avatar.png' would be:

\
 curl -X POST -u username:password -H "X-Atlassian-Token: no-check" http://example.com/rest/api/latest/users/jdoe/avatar.png -F avatar=@avatar.png\
 

Users are always allowed to update their own avatar. To update someone else's avatar the authenticated user must have global **ADMIN** permission, or global **SYS_ADMIN** permission to update a **SYS_ADMIN** user's avatar.

*Example response representations:*

- <div>

  201 \[<a href="#" onclick="toggle(&#39;idm532025501008&#39;); return false;"><em><span id="link-idm532025501008">expand</span></em></a>\]

  </div>

  <div id="idm532025501008" class="toggle">

  The avatar was uploaded successfully.

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025500880&#39;); return false;"><em><span id="link-idm532025500880">expand</span></em></a>\]

  </div>

  <div id="idm532025500880" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to update the avatar.

  <div class="representation">

  </div>

  </div>

- <div>

  404 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025497600&#39;); return false;"><em><span id="link-idm532025497600">expand</span></em></a>\]

  </div>

  <div id="idm532025497600" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified user does not exist.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

<div class="resource">

### /rest/api/1.0/users/{userSlug}/settings

Rest resource for retrieving, and updating user settings key/values

###### Methods

<div class="methods">

<div class="method">

#### GET

Retrieve a map of user setting key values for a specific user identified by the user slug.

*Example response representations:*

- <div>

  200 - application/json (settings) \[<a href="#" onclick="toggle(&#39;idm532025548176&#39;); return false;"><em><span id="link-idm532025548176">expand</span></em></a>\]

  </div>

  <div id="idm532025548176" class="toggle">

  ###### Example

      {"string key":"string value","boolean key":true,"long key":10}

  The user settings for the specified user slug.

  <div class="representation">

  </div>

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025548048&#39;); return false;"><em><span id="link-idm532025548048">expand</span></em></a>\]

  </div>

  <div id="idm532025548048" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user is not a project administrator.

  <div class="representation">

  </div>

  </div>

</div>

<div class="method">

#### POST

Update the entries of a map of user setting key/values for a specific user identified by the user slug.

*Example request representations:*

- <div>

  application/json \[<a href="#" onclick="toggle(&#39;idm532025542432&#39;); return false;"><em><span id="link-idm532025542432">expand</span></em></a>\]

  </div>

  <div id="idm532025542432" class="toggle">

  ###### Example

      {"string key":"string value","boolean key":true,"long key":10}

  </div>

*Example response representations:*

- <div>

  200 \[<a href="#" onclick="toggle(&#39;idm532025540320&#39;); return false;"><em><span id="link-idm532025540320">expand</span></em></a>\]

  </div>

  <div id="idm532025540320" class="toggle">

  The {@link UserSettings were updated successfully}

  </div>

- <div>

  401 - application/json ([errors](#errors-and-validation)) \[<a href="#" onclick="toggle(&#39;idm532025539824&#39;); return false;"><em><span id="link-idm532025539824">expand</span></em></a>\]

  </div>

  <div id="idm532025539824" class="toggle">

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user is not a project administrator.

  <div class="representation">

  </div>

  </div>

</div>

</div>

</div>

</div>
