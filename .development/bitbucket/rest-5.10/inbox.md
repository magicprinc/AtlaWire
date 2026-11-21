<!-- Bitbucket Server 5.10.0 REST API — resource group: inbox (2 endpoints) -->

## /rest/api/1.0/inbox/pull-requests/count

###### Methods

#### GET

*Example response representations:*

-

  application/json; charset=UTF-8

## /rest/api/1.0/inbox/pull-requests

###### Methods

#### GET

###### /rest/api/1.0/inbox/pull-requests?start&limit&role

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
<td>start</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#int">int</a>
Default: <code>0</code></td>
<td></td>
</tr>
<tr>
<td>limit</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#int">int</a>
Default: <code>25</code></td>
<td></td>
</tr>
<tr>
<td>role</td>
<td><a href="http://www.w3.org/TR/xmlschema-2/#string">string</a>
Default: <code>reviewer</code></td>
<td></td>
</tr>
</tbody>
</table>

*Example response representations:*

-

  application/json; charset=UTF-8
