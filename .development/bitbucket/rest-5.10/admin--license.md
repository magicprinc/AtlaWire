<!-- Bitbucket Server 5.10.0 REST API — resource group: admin--license (1 endpoints) -->

## /rest/api/1.0/admin/license

A REST endpoint for retrieving or updating the license.

###### Methods

#### GET

Retrieves details about the current license, as well as the current status of the system with regards to the installed license. The status includes the current number of users applied toward the license limit, as well as any status messages about the license (warnings about expiry or user counts exceeding license limits).

The authenticated user must have **ADMIN** permission. Unauthenticated users, and non-administrators, are not permitted to access license details.

*Example response representations:*

-

  200 - application/json (license)

  ###### Example

      {"creationDate":1331038800000,"purchaseDate":1331038800000,"expiryDate":1372493732817,"numberOfDaysBeforeExpiry":0,"maintenanceExpiryDate":1372493732817,"numberOfDaysBeforeMaintenanceExpiry":0,"gracePeriodEndDate":1372493732817,"numberOfDaysBeforeGracePeriodExpiry":0,"maximumNumberOfUsers":12,"unlimitedNumberOfUsers":false,"serverId":"<server ID embedded in license>","supportEntitlementNumber":"<support entitlement number embedded in license>","license":"<encoded license text>","status":{"serverId":"<actual server ID>","currentNumberOfUsers":2}}

  The currently-installed license.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to view the license, or the request is anonymous.

-

  404 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  No license has been installed.

#### POST

Decodes the provided encoded license and sets it as the active license. If no license was provided, a 400 is returned. If the license cannot be decoded, or cannot be applied, a 409 is returned. Some possible reasons a license may not be applied include:

- It is for a different product
- It is already expired

Otherwise, if the license is updated successfully, details for the new license are returned with a 200 response.

**Warning**: It is possible to downgrade the license during update, applying a license with a lower number of permitted users. If the number of currently-licensed users exceeds the limits of the new license, pushing will be disabled until the licensed user count is brought into compliance with the new license.

The authenticated user must have **SYS_ADMIN** permission. **ADMIN** users may *view* the current license details, but they may not *update* the license.

*Example request representations:*

-

  application/json

  ###### Example

      {"license":"<encoded license text>"}

*Example response representations:*

-

  200 - application/json (license)

  ###### Example

      {"creationDate":1331038800000,"purchaseDate":1331038800000,"expiryDate":1372493732817,"numberOfDaysBeforeExpiry":0,"maintenanceExpiryDate":1372493732817,"numberOfDaysBeforeMaintenanceExpiry":0,"gracePeriodEndDate":1372493732817,"numberOfDaysBeforeGracePeriodExpiry":0,"maximumNumberOfUsers":12,"unlimitedNumberOfUsers":false,"serverId":"<server ID embedded in license>","supportEntitlementNumber":"<support entitlement number embedded in license>","license":"<encoded license text>","status":{"serverId":"<actual server ID>","currentNumberOfUsers":2}}

  The newly-installed license.

-

  400 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":"field_a","message":"A detailed validation error message for field_a.","exceptionName":null},{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  No encoded license was provided in the JSON body for the POST.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions to update the license.

-

  409 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The encoded license could not be decoded, or it is not valid for use on this server. For example, it may be for a different product, or it may have already expired.
