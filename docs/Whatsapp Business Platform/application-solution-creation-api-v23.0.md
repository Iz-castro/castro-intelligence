

## Base URL

| URL | Description |
|-----|-------------|
| https://graph.facebook.com | Production Graph API server |

## APIs

| Method | Endpoint |
|--------|----------|
| POST | [/&#123;Version&#125;/&#123;Application-ID&#125;/whatsapp_business_solution](#post-version-application-id-whatsapp-business-solution) |

&lt;jumplink id=&quot;post-version-application-id-whatsapp-business-solution&quot;&gt;&lt;/jumplink&gt;
## POST /&#123;Version&#125;/&#123;Application-ID&#125;/whatsapp_business_solution

Create Multi-Partner Solution

Create a new Multi-Partner Solution that defines permission distribution between
a solution owner app and a partner app for WhatsApp Business messaging collaboration.


**Permission Logic:**
- Only one partner (owner or partner app) can have MESSAGING permission
- At least one partner must have MESSAGING permission
- Both partners automatically receive default solution partner permissions
- Empty permission arrays indicate no configurable permissions for that partner


**Solution Lifecycle:**
- Solutions are created with INITIATED status
- Require subsequent activation workflow through solution management
- Can be managed through Partner Dashboard or solution management APIs


**Rate Limiting:**
Standard Graph API rate limits apply with WhatsApp Business Management throttling.
Use appropriate retry logic with exponential backoff for rate-limited requests.


**Validation:**
- Partner app must be accessible and have proper capabilities
- Permission combinations are validated against business logic rules
- Solution names must meet length and content requirements


### Header Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| User-Agent | string |  | The user agent string identifying the client software making the request. |
| Authorization | string | ✓ | Bearer token for API authentication. This should be a valid access token obtained through the appropriate OAuth flow or system user token. |

### Path Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| Version | string | ✓ | Graph API version to use for this request. Determines API behavior and available features. Use the latest stable version for new integrations. |
| Application-ID | string | ✓ | Your Facebook Application ID that will serve as the solution owner. This application will be the primary owner of the created solution. |

### Request Body (Required)

**Content Type**: `application/json`

**Schema**: [WhatsAppBusinessSolutionCreateRequest](#whatsappbusinesssolutioncreaterequest)

### Responses

**200**

Multi-Partner Solution created successfully. The solution is created with INITIATED status
and can be managed through subsequent API calls or Partner Dashboard.


**Content Type**: `application/json`

**Schema**: [WhatsAppBusinessSolutionCreateResponse](#whatsappbusinesssolutioncreateresponse)

**400**

Bad Request - Invalid parameters provided. This includes validation failures
for permission logic, malformed IDs, or constraint violations.


**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**401**

Unauthorized - Authentication required or invalid access token provided.


**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**403**

Forbidden - Insufficient permissions or missing required capabilities.
App may lack whatsapp_business_management permission or required granular scopes.


**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**404**

Not Found - Application ID not found or not accessible to the requesting entity.


**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**422**

Unprocessable Entity - Request is well-formed but contains business logic violations.
This includes cases where both partners have MESSAGING permission or neither has it.


**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**429**

Too Many Requests - Rate limiting threshold exceeded.
Implement exponential backoff retry logic.


**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**500**

Internal Server Error - Unexpected server-side error occurred.
These errors are typically transient and should be retried.


**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)


# Components

## Schemas

&lt;jumplink id=&quot;whatsappbusinesssolutioncreaterequest&quot;&gt;&lt;/jumplink&gt;
### WhatsAppBusinessSolutionCreateRequest

Request payload for creating a Multi-Partner Solution

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| owner_permissions | array of [WhatsAppBusinessAccountConfigurablePermissionTask](#whatsappbusinessaccountconfigurablepermissiontask) | ✓ | Configurable permissions granted to the solution owner app. Currently supports only MESSAGING permission. Use empty array if owner should not have configurable permissions. |
| partner_app_id | string | ✓ | Facebook Application ID of the partner app that will participate in this solution. Must be a valid application ID accessible to the requesting entity. |
| partner_permissions | array of [WhatsAppBusinessAccountConfigurablePermissionTask](#whatsappbusinessaccountconfigurablepermissiontask) | ✓ | Configurable permissions granted to the partner app. Currently supports only MESSAGING permission. Use empty array if partner should not have configurable permissions. |
| solution_name | string | ✓ | Human-readable name for the Multi-Partner Solution. Used for identification and management purposes in partner dashboards and solution management interfaces. |

&lt;jumplink id=&quot;whatsappbusinesssolutioncreateresponse&quot;&gt;&lt;/jumplink&gt;
### WhatsAppBusinessSolutionCreateResponse

Successful response containing the created solution identifier

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| solution_id | string | ✓ | Unique identifier for the newly created Multi-Partner Solution. Use this ID for subsequent solution management operations. |

&lt;jumplink id=&quot;whatsappbusinessaccountconfigurablepermissiontask&quot;&gt;&lt;/jumplink&gt;
### WhatsAppBusinessAccountConfigurablePermissionTask

Configurable permission tasks for WhatsApp Business Account access in Multi-Partner Solutions.
Currently only MESSAGING permission is configurable through this API.


**Type**: string

**Enum Values**: &quot;MESSAGING&quot;

&lt;jumplink id=&quot;graphapierror&quot;&gt;&lt;/jumplink&gt;
### GraphAPIError

Standard Graph API error response structure

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| error | [Error](#object-error-1) | ✓ |  |

## Inline Object Definitions

&lt;jumplink id=&quot;object-error-1&quot;&gt;&lt;/jumplink&gt;
### Error

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| message | string | ✓ | Human-readable error message describing the issue |
| type | string | ✓ | Error type classification for programmatic handling |
| code | integer | ✓ | Numeric error code for specific error identification |
| error_subcode | integer |  | More specific error subcode when applicable |
| fbtrace_id | string |  | Facebook trace ID for debugging and support purposes |
| is_transient | boolean |  | Indicates whether this error is temporary and the request should be retried |
| error_user_title | string |  | User-friendly error title for display purposes |
| error_user_msg | string |  | User-friendly error message for display purposes |

## Authentication

| Scheme | Type | Location |
|--------|------|----------|
| bearerAuth | HTTP Bearer | Header: `Authorization` |

### Usage Examples

- **bearerAuth**: Include `Authorization: Bearer your-token-here` in request headers

### Global Authentication Requirements

All endpoints require: bearerAuth
