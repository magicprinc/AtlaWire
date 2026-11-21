<!-- Bitbucket Server 5.10.0 REST API — section: 00-getting-started -->

## Getting started

Because the REST API is based on open standards, you can use any web development language or command line tool capable of generating an HTTP request to access the API. See the [developer documentation](https://developer.atlassian.com/server/bitbucket/reference/rest-api/) for a basic usage example.

If you're already working with the [Atlassian SDK](https://developer.atlassian.com/server/framework/atlassian-sdk/), the [REST API Browser](https://developer.atlassian.com/server/framework/atlassian-sdk/using-the-rest-api-browser/) is a great tool for exploring and experimenting with the Bitbucket REST API.

## Structure of the REST URIs

Bitbucket's REST APIs provide access to resources (data entities) via URI paths. To use a REST API, your application will make an HTTP request and parse the response. The Bitbucket REST API uses JSON as its communication format, and the standard HTTP methods like GET, PUT, POST and DELETE. URIs for Bitbucket's REST API resource have the following structure:

    http://host:port/context/rest/api-name/api-version/path/to/resource

For example, the following URI would retrieve a page of the latest commits to the **jira** repository in the **Jira** project on <https://stash.atlassian.com>.

    https://stash.atlassian.com/rest/api/1.0/projects/JIRA/repos/jira/commits

See the API descriptions below for a full list of available resources.

Alternatively we also publish a list of resources in [WADL](http://en.wikipedia.org/wiki/Web_Application_Description_Language) format. It is available [here](bitbucket-rest.wadl).

## Paged APIs

Bitbucket uses paging to conserve server resources and limit response size for resources that return potentially large collections of items. A request to a paged API will result in a `values` array wrapped in a JSON object with some paging metadata, like this:

    {
        "size": 3,
        "limit": 3,
        "isLastPage": false,
        "values": \[
            { /\* result 0 \*/ },
            { /\* result 1 \*/ },
            { /\* result 2 \*/ }
        \],
        "start": 0,
        "filter": null,
        "nextPageStart": 3
    }

Clients can use the `limit` and `start` query parameters to retrieve the desired number of results.

The `limit` parameter indicates how many results to return per page. Most APIs default to returning `25` if the limit is left unspecified. This number can be increased, but note that a resource-specific hard limit will apply. These hard limits can be configured by server administrators, so it's always best practice to check the `limit` attribute on the response to see what limit has been applied. The request to get a larger page should look like this:

    http://host:port/context/rest/api-name/api-version/path/to/resource?limit={desired size of page}

For example:

    https://stash.atlassian.com/rest/api/1.0/projects/JIRA/repos/jira/commits?limit=1000

The `start` parameter indicates which item should be used as the first item in the page of results. All paged responses contain an `isLastPage` attribute indicating whether another page of items exists.

**Important:** If more than one page exists (i.e. the response contains `"isLastPage": false`), the response object will also contain a `nextPageStart` attribute which ***must*** be used by the client as the `start` parameter on the next request. Identifiers of adjacent objects in a page may not be contiguous, so the start of the next page is *not* necessarily the start of the last page plus the last page's size. A client should always use `nextPageStart` to avoid unexpected results from a paged API. The request to get a subsequent page should look like this:

    http://host:port/context/rest/api-name/api-version/path/to/resource?start={nextPageStart from previous response}

For example:

    https://stash.atlassian.com/rest/api/1.0/projects/JIRA/repos/jira/commits?start=25

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
