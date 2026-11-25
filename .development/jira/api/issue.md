<!-- jira 8.22.2 - resource group: issue -->

# `issue`

4 method(s) as this deployment serves them. Source: its own `application.wadl`.

## POST /issue

Creates an issue or a sub-task from a JSON representation. The fields that can be set on create, in either the fields parameter or the update parameter can be determined using the /rest/api/2/issue/createmeta resource. If a field is not configured to appear on the create screen, then it will not be in the createmeta, and a field validation error will occur if it is submitted. Creating a sub-task is similar to creating a regular issue, with two important differences: the issueType field must correspond to a sub-task issue type (you can use /issue/createmeta to discover sub-task issue types), and you must provide a parent field in the issue create request containing the id or key of the parent issue. The updateHistory param adds the project that this issue is created in, to the current user's project history, if set to true (by default, the project history is not updated). You can view the project history in the Jira application, via the Projects dropdown.

| query | type | default |
|---|---|---|
| `updateHistory` | boolean | `false` |

## DELETE /issue/{issueIdOrKey}

Delete an issue. If the issue has subtasks you must set the parameter deleteSubtasks=true to delete the issue. You cannot delete an issue without its subtasks also being deleted.

| query | type | default |
|---|---|---|
| `deleteSubtasks` | string |  |

## GET /issue/{issueIdOrKey}

Returns a full representation of the issue for the given issue key. An issue JSON consists of the issue key, a collection of fields, a link to the workflow transition sub-resource, and (optionally) the HTML rendered values of any fields that support it (e.g. if wiki syntax is enabled for the description or comments). The fields param (which can be specified multiple times) gives a comma-separated list of fields to include in the response. This can be used to retrieve a subset of fields. A particular field can be excluded by prefixing it with a minus. By default, all ( *all ) fields are returned in this get-issue resource. Note: the default is different when doing a jql search -- the default there is just navigable fields ( *navigable ). *all - include all fields *navigable - include just navigable fields summary,comment - include just the summary and comments -comment - include everything except comments (the default is *all for get-issue) *all,-comment - include everything except comments The {@code properties} param is similar to {@code fields} and specifies a comma-separated list of issue properties to include. Unlike {@code fields}, properties are not included by default. To include them all send {@code ?properties=*all}. You can also include only specified properties or exclude some properties with a minus (-) sign. {@code *all} - include all properties {@code *all, -prop1} - include all properties except {@code prop1} {@code prop1, prop1} - include {@code prop1} and {@code prop2} properties Jira will attempt to identify the issue by the issueIdOrKey path parameter. This can be an issue id, or an issue key. If the issue cannot be found via an exact match, Jira will also look for the issue in a case-insensitive way, or by looking to see if the issue was moved. In either of these cases, the request will proceed as normal (a 302 or other redirect will not be returned). The issue key contained in the response will indicate the current value of issue's key. The expand param is used to include, hidden by default, parts of response. This can be used to include: renderedFields - field values in HTML format names - display name of each field schema - schema for each field which describes a type of the field transitions - all possible transitions for the given issue operations - all possibles operations which may be applied on issue editmeta - information about how each field may be edited. It contains field's schema as well. changelog - history of all changes of the given issue versionedRepresentations - REST representations of all fields. Some field may contain more recent versions. RESET representations are numbered. The greatest number always represents the most recent version. It is recommended that the most recent version is used. version for these fields which provide a more recent REST representation. After including versionedRepresentations "fields" field become hidden.

| query | type | default |
|---|---|---|
| `fields` | string |  |
| `expand` | string |  |
| `properties` | string |  |
| `updateHistory` | boolean |  |

## PUT /issue/{issueIdOrKey}

Edits an issue from a JSON representation. The issue can either be updated by setting explicit the field value(s) or by using an operation to change the field value. The fields that can be updated, in either the fields parameter or the update parameter, can be determined using the /rest/api/2/issue/{issueIdOrKey}/editmeta resource. If a field is not configured to appear on the edit screen, then it will not be in the editmeta, and a field validation error will occur if it is submitted. Specifying a "field_id": field_value in the "fields" is a shorthand for a "set" operation in the "update" section. Field should appear either in "fields" or "update", not in both.

| query | type | default |
|---|---|---|
| `notifyUsers` | boolean | `true` |
