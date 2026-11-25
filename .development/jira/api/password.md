<!-- jira 8.22.2 - resource group: password -->

# `password`

3 method(s) as this deployment serves them. Source: its own `application.wadl`.

## GET /password/policy

Returns the list of requirements for the current password policy. For example, "The password must have at least 10 characters.", "The password must not be similar to the user's name or email address.", etc.

| query | type | default |
|---|---|---|
| `hasOldPassword` | boolean | `false` |

## POST /password/policy/createUser

Returns a list of statements explaining why the password policy would disallow a proposed password for a new user. You can use this method to test the password policy validation. This could be done prior to an action where a new user and related password are created, using methods like the ones in UserService . For example, you could use this to validate a password in a create user form in the user interface, as the user enters it. The username and new password must be not empty to perform the validation. Note, this method will help you validate against the policy only. It won't check any other validations that might be performed when creating a new user, e.g. checking whether a user with the same name already exists.

No query parameters.

## POST /password/policy/updateUser

Returns a list of statements explaining why the password policy would disallow a proposed new password for a user with an existing password. You can use this method to test the password policy validation. This could be done prior to an action where the password is actually updated, using methods like ChangePassword or ResetPassword . For example, you could use this to validate a password in a change password form in the user interface, as the user enters it. The user must exist and the username and new password must be not empty, to perform the validation. Note, this method will help you validate against the policy only. It won't check any other validations that might be performed when submitting a password change/reset request, e.g. verifying whether the old password is valid.

No query parameters.
