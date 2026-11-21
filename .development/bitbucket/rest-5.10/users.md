<!-- Bitbucket Server 5.10.0 REST API — resource group: users (5 endpoints) -->

## /rest/api/1.0/users

###### Methods

#### GET

*This is a [paged API](#paging-params)*.

Retrieve a page of users, optionally run through provided filters.

Only authenticated users may call this resource.

## /rest/api/1.0/users/credentials

###### Methods

#### PUT

Update the currently authenticated user's password.

*Example request representations:*

-

  application/json

  ###### Example

      {"password":"secret","passwordConfirm":"secret","oldPassword":"faithless"}

*Example response representations:*

-

  204

  The user's password was successfully updated.

-

  400 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":"field_a","message":"A detailed validation error message for field_a.","exceptionName":null},{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The request was malformed or the old password was incorrect.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  Authentication failed or was not attempted.

## /rest/api/1.0/users/{userSlug}

###### Methods

#### GET

Retrieve the user matching the supplied **userSlug**.

*Example response representations:*

-

  200 - application/json (userSlug)

  ###### Example

      {"name":"jcitizen","emailAddress":"jane@example.com","id":101,"displayName":"Jane Citizen","active":true,"slug":"jcitizen","type":"NORMAL"}

  The user matching the supplied **userSlug**. Note, this may *not* be the user's username, always use the **user.slug** property.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the user.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified user does not exist.

## /rest/api/1.0/users/{userSlug}/avatar.png

###### Methods

#### DELETE

Delete the avatar associated to a user.

Users are always allowed to delete their own avatar. To delete someone else's avatar the authenticated user must have global **ADMIN** permission, or global **SYS_ADMIN** permission to update a **SYS_ADMIN** user's avatar.

*Example response representations:*

-

  200 - application/json (href)

  ###### Example

      {"href":"http://www.gravatar.com/avatar/aa99b351245441b8ca95d54a52d2998c"}

  The new avatar URL if the local avatar was successfully deleted or did not exist

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The authenticated user has insufficient permissions to delete the specified avatar.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified user does not exist.

#### POST

Update the avatar for the user with the supplied **slug**.

This resource accepts POST multipart form data, containing a single image in a form-field named 'avatar'.

There are configurable server limits on both the dimensions (1024x1024 pixels by default) and uploaded file size (1MB by default). Several different image formats are supported, but **PNG** and **JPEG** are preferred due to the file size limit.

This resource has Cross-Site Request Forgery (XSRF) protection. To allow the request to pass the XSRF check the caller needs to send an `X-Atlassian-Token` HTTP header with the value `no-check`.

An example [curl](http://curl.haxx.se/) request to upload an image name 'avatar.png' would be:

 curl -X POST -u username:password -H "X-Atlassian-Token: no-check" http://example.com/rest/api/latest/users/jdoe/avatar.png -F avatar=@avatar.png
 

Users are always allowed to update their own avatar. To update someone else's avatar the authenticated user must have global **ADMIN** permission, or global **SYS_ADMIN** permission to update a **SYS_ADMIN** user's avatar.

*Example response representations:*

-

  201

  The avatar was uploaded successfully.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to update the avatar.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The specified user does not exist.

## /rest/api/1.0/users/{userSlug}/settings

Rest resource for retrieving, and updating user settings key/values

###### Methods

#### GET

Retrieve a map of user setting key values for a specific user identified by the user slug.

*Example response representations:*

-

  200 - application/json (settings)

  ###### Example

      {"string key":"string value","boolean key":true,"long key":10}

  The user settings for the specified user slug.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user is not a project administrator.

#### POST

Update the entries of a map of user setting key/values for a specific user identified by the user slug.

*Example request representations:*

-

  application/json

  ###### Example

      {"string key":"string value","boolean key":true,"long key":10}

*Example response representations:*

-

  200

  The {@link UserSettings were updated successfully}

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user is not a project administrator.
