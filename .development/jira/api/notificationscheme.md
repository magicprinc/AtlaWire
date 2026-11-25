<!-- jira 8.22.2 - resource group: notificationscheme -->

# `notificationscheme`

2 method(s) as this deployment serves them. Source: its own `application.wadl`.

## GET /notificationscheme

Returns a paginated list of notification schemes. In order to access notification scheme, the calling user is required to have permissions to administer at least one project associated with the requested notification scheme. Each scheme contains a list of events and recipient configured to receive notifications for these events. Consumer should allow events without recipients to appear in response. The list is ordered by the scheme's name. Follow the documentation of /notificationscheme/{id} resource for all details about returned value.

| query | type | default |
|---|---|---|
| `startAt` | long |  |
| `maxResults` | int |  |
| `expand` | string |  |

## GET /notificationscheme/{id}

Returns a full representation of the notification scheme for the given id. This resource will return a notification scheme containing a list of events and recipient configured to receive notifications for these events. Consumer should allow events without recipients to appear in response. User accessing the data is required to have permissions to administer at least one project associated with the requested notification scheme. Notification recipients can be: current assignee - the value of the notificationType is CurrentAssignee issue reporter - the value of the notificationType is Reporter current user - the value of the notificationType is CurrentUser project lead - the value of the notificationType is ProjectLead component lead - the value of the notificationType is ComponentLead all watchers - the value of the notification type is AllWatchers configured user - the value of the notification type is User. Parameter will contain key of the user. Information about the user will be provided if user expand parameter is used. configured group - the value of the notification type is Group. Parameter will contain name of the group. Information about the group will be provided if group expand parameter is used. configured email address - the value of the notification type is EmailAddress, additionally information about the email will be provided. users or users in groups in the configured custom fields - the value of the notification type is UserCustomField or GroupCustomField. Parameter will contain id of the custom field. Information about the field will be provided if field expand parameter is used. configured project role - the value of the notification type is ProjectRole. Parameter will contain project role id. Information about the project role will be provided if projectRole expand parameter is used. Please see the example for reference. The events can be Jira system events or events configured by administrator. In case of the system events, data about theirs ids, names and descriptions is provided. In case of custom events, the template event is included as well.

| query | type | default |
|---|---|---|
| `expand` | string |  |
