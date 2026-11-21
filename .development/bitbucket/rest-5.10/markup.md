<!-- Bitbucket Server 5.10.0 REST API — resource group: markup (1 endpoints) -->

## /rest/api/1.0/markup/preview

###### Methods

#### POST

###### /rest/api/1.0/markup/preview?urlMode&hardwrap&htmlEscape

Preview the generated html for given markdown contents.

Only authenticated users may call this resource.

###### request query parameters

| parameter | value | description |
|----|----|----|
| **urlMode** | *[string](http://www.w3.org/TR/xmlschema-2/#string)* | (Optional) The UrlMode used when building the url. One of: ABSOLUTE, RELATIVE and CONFIGURED By default this is RELATIVE. |
| **hardwrap** | *[boolean](http://www.w3.org/TR/xmlschema-2/#boolean)* | (Optional) Whether the markup implementation should convert newlines to breaks. By default this is false which reflects the standard markdown specification. |
| **htmlEscape** | *[boolean](http://www.w3.org/TR/xmlschema-2/#boolean)* | (Optional) true if HTML should be escaped in the input markup, false otherwise. |

*Example request representations:*

-

  \*/\*

  ###### Example

      # Hello World!

*Example response representations:*

-

  200 - application/json (markup)

  ###### Example

      {
           "html" : "<h1>Hello World!</h1>"
       }

  The rendered markdown.

-

  400 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The markdown was invalid.

-

  401 - application/json ([errors](#errors-and-validation))

  ###### Example

      {"errors":[{"context":null,"message":"A detailed error message.","exceptionName":null}]}

  The currently authenticated user has insufficient permissions preview rendered markdown.
