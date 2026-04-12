

## Base URL

| URL | Description |
|-----|-------------|
| https://graph.facebook.com | Meta Graph API production server |

## APIs

| Method | Endpoint |
|--------|----------|
| POST | [/&#123;Version&#125;/&#123;Solution-ID&#125;/accept_deactivation_request](#post-version-solution-id-accept-deactivation-request) |

&lt;jumplink id=&quot;post-version-solution-id-accept-deactivation-request&quot;&gt;&lt;/jumplink&gt;
## POST /&#123;Version&#125;/&#123;Solution-ID&#125;/accept_deactivation_request

Accept WhatsApp Business Solution Deactivation Request

Accepts a pending deactivation request for a WhatsApp Business Multi-Partner Solution.


This endpoint completes the partner approval workflow by accepting a deactivation request
that was previously initiated by another solution partner. Upon successful acceptance,
the solution status transitions from ACTIVE to DEACTIVATED, and the pending request
status changes from PENDING_DEACTIVATION to NONE.


**Important Business Logic:**

- Solution must be in ACTIVE status with PENDING_DEACTIVATION pending status

- All outstanding payments and invoices must be settled before acceptance

- Active marketing campaigns must be concluded or transferred

- Webhook notifications will be sent to all solution partners upon completion

- Solution resources and permissions will be cleaned up according to policy


### Header Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| User-Agent | string |  | The user agent string identifying the client software making the request. |
| Authorization | string | ✓ | Bearer token for API authentication. This should be a valid access token obtained through the appropriate OAuth flow or system user token. |

### Path Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| Version | string | ✓ | Graph API version |
| Solution-ID | string | ✓ | Unique identifier for the WhatsApp Business Solution |

### Query Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| fields | string |  | Comma-separated list of fields to return in the response. **Available Fields:** id, name, status, status_for_pending_request, owner_permissions **Default Fields:** name, status, status_for_pending_request |

### Request Body (Optional)

Empty request body - no parameters required for this endpoint

**Content Type**: `application/json`

**Schema**: object

### Responses

**200**

Deactivation request accepted successfully. Solution status updated to DEACTIVATED.


**Content Type**: `application/json`

**Schema**: [WhatsAppBusinessSolution](#whatsappbusinesssolution)

**Example**:\n```json\n&#123;
    &quot;id&quot;: &quot;12345678901234567&quot;,
    &quot;name&quot;: &quot;Sample Business Solution Partnership&quot;,
    &quot;status&quot;: &quot;DEACTIVATED&quot;,
    &quot;status_for_pending_request&quot;: &quot;NONE&quot;,
    &quot;owner_permissions&quot;: [
        &quot;MANAGE&quot;,
        &quot;DEVELOP&quot;
    ]
&#125;\n```

**400**

Bad Request - Invalid request parameters or malformed solution ID format.


**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;Invalid solution ID format provided&quot;,
        &quot;type&quot;: &quot;GraphAPIException&quot;,
        &quot;code&quot;: 100,
        &quot;error_subcode&quot;: 33,
        &quot;fbtrace_id&quot;: &quot;FAKE_TRACE_ID_12345&quot;,
        &quot;is_transient&quot;: false,
        &quot;error_user_title&quot;: &quot;Invalid Request&quot;,
        &quot;error_user_msg&quot;: &quot;The solution ID format is not valid. Please check your request parameters.&quot;
    &#125;
&#125;\n```

**401**

Unauthorized - Invalid, missing, or expired access token.


**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;Invalid OAuth access token&quot;,
        &quot;type&quot;: &quot;OAuthException&quot;,
        &quot;code&quot;: 190,
        &quot;error_subcode&quot;: 463,
        &quot;fbtrace_id&quot;: &quot;FAKE_TRACE_ID_67890&quot;,
        &quot;is_transient&quot;: false,
        &quot;error_user_title&quot;: &quot;Authentication Required&quot;,
        &quot;error_user_msg&quot;: &quot;Please provide a valid access token to access this resource.&quot;
    &#125;
&#125;\n```

**403**

Forbidden - Insufficient permissions or app not authorized for this solution.


**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;App does not have permission to access this solution&quot;,
        &quot;type&quot;: &quot;GraphMethodException&quot;,
        &quot;code&quot;: 10,
        &quot;error_subcode&quot;: 2018218,
        &quot;fbtrace_id&quot;: &quot;FAKE_TRACE_ID_11111&quot;,
        &quot;is_transient&quot;: false,
        &quot;error_user_title&quot;: &quot;Permission Denied&quot;,
        &quot;error_user_msg&quot;: &quot;Your app does not have the required permissions to perform this action on the solution.&quot;
    &#125;
&#125;\n```

**404**

Not Found - Solution ID does not exist or is not accessible to the requesting app.


**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;Solution not found or not accessible&quot;,
        &quot;type&quot;: &quot;GraphMethodException&quot;,
        &quot;code&quot;: 803,
        &quot;error_subcode&quot;: 1675030,
        &quot;fbtrace_id&quot;: &quot;FAKE_TRACE_ID_22222&quot;,
        &quot;is_transient&quot;: false,
        &quot;error_user_title&quot;: &quot;Resource Not Found&quot;,
        &quot;error_user_msg&quot;: &quot;The requested solution could not be found or you do not have access to it.&quot;
    &#125;
&#125;\n```

**422**

Unprocessable Entity - Valid parameters but business logic prevents processing (e.g., wrong solution state, outstanding payments).


**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;Solution is not in a valid state to accept deactivation requests&quot;,
        &quot;type&quot;: &quot;GraphMethodException&quot;,
        &quot;code&quot;: 100,
        &quot;error_subcode&quot;: 2207013,
        &quot;fbtrace_id&quot;: &quot;FAKE_TRACE_ID_33333&quot;,
        &quot;is_transient&quot;: false,
        &quot;error_user_title&quot;: &quot;Request Cannot Be Processed&quot;,
        &quot;error_user_msg&quot;: &quot;The solution must be in ACTIVE status with a pending deactivation request to accept deactivation.&quot;
    &#125;
&#125;\n```

**429**

Too Many Requests - Rate limit exceeded. Use exponential backoff for retries.


**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;Application request limit reached&quot;,
        &quot;type&quot;: &quot;OAuthException&quot;,
        &quot;code&quot;: 4,
        &quot;error_subcode&quot;: 2446079,
        &quot;fbtrace_id&quot;: &quot;FAKE_TRACE_ID_44444&quot;,
        &quot;is_transient&quot;: true,
        &quot;error_user_title&quot;: &quot;Rate Limit Exceeded&quot;,
        &quot;error_user_msg&quot;: &quot;Too many requests have been made. Please wait and try again later.&quot;
    &#125;
&#125;\n```

**500**

Internal Server Error - Unexpected server error. Retry with exponential backoff if is_transient is true.


**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;An unexpected error occurred while processing your request&quot;,
        &quot;type&quot;: &quot;GraphAPIException&quot;,
        &quot;code&quot;: 2,
        &quot;error_subcode&quot;: 1349174,
        &quot;fbtrace_id&quot;: &quot;FAKE_TRACE_ID_55555&quot;,
        &quot;is_transient&quot;: true,
        &quot;error_user_title&quot;: &quot;Service Temporarily Unavailable&quot;,
        &quot;error_user_msg&quot;: &quot;We&#039;re experiencing technical difficulties. Please try again in a few moments.&quot;
    &#125;
&#125;\n```


# Components

## Schemas

&lt;jumplink id=&quot;whatsappbusinesssolution&quot;&gt;&lt;/jumplink&gt;
### WhatsAppBusinessSolution

WhatsApp Business Multi-Partner Solution object with core node fields only

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| id | string | ✓ | Unique identifier for the WhatsApp Business Solution |
| name | string | ✓ | Human-readable name for the solution (UGC text, 2-75 characters) |
| status | [WhatsAppBusinessSolutionStatus](#whatsappbusinesssolutionstatus) | ✓ |  |
| status_for_pending_request | [WhatsAppBusinessSolutionPendingStatus](#whatsappbusinesssolutionpendingstatus) | ✓ |  |
| owner_permissions | array of [WhatsAppBusinessAccountPermissionTask](#whatsappbusinessaccountpermissiontask) |  | Array of permissions granted to the solution owner |

&lt;jumplink id=&quot;whatsappbusinesssolutionstatus&quot;&gt;&lt;/jumplink&gt;
### WhatsAppBusinessSolutionStatus

Current status of the WhatsApp Business Solution

**Type**: string

**Enum Values**: &quot;DRAFT&quot;, &quot;INITIATED&quot;, &quot;ACTIVE&quot;, &quot;REJECTED&quot;, &quot;DEACTIVATED&quot;, &quot;PENDING_DEACTIVATION&quot;

&lt;jumplink id=&quot;whatsappbusinesssolutionpendingstatus&quot;&gt;&lt;/jumplink&gt;
### WhatsAppBusinessSolutionPendingStatus

Status of any pending requests for the solution

**Type**: string

**Enum Values**: &quot;PENDING_ACTIVATION&quot;, &quot;PENDING_DEACTIVATION&quot;, &quot;NONE&quot;

&lt;jumplink id=&quot;whatsappbusinessaccountpermissiontask&quot;&gt;&lt;/jumplink&gt;
### WhatsAppBusinessAccountPermissionTask

Granular permission tasks for WhatsApp Business Account access

**Type**: string

**Enum Values**: &quot;MANAGE&quot;, &quot;DEVELOP&quot;, &quot;MANAGE_TEMPLATES&quot;, &quot;MANAGE_PHONE&quot;, &quot;VIEW_COST&quot;, &quot;MANAGE_EXTENSIONS&quot;, &quot;VIEW_PHONE_ASSETS&quot;, &quot;MANAGE_PHONE_ASSETS&quot;, &quot;VIEW_TEMPLATES&quot;, &quot;VIEW_INSIGHTS&quot;, &quot;RECEIVE_INCOMING_MESSAGES&quot;, &quot;MANAGE_BILLING&quot;, &quot;MANAGE_USERS&quot;, &quot;MESSAGING&quot;, &quot;FULL_CONTROL&quot;

&lt;jumplink id=&quot;graphapierror&quot;&gt;&lt;/jumplink&gt;
### GraphAPIError

Standard Graph API error response

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| error | [Error](#object-error-1) | ✓ |  |

## Inline Object Definitions

&lt;jumplink id=&quot;object-error-1&quot;&gt;&lt;/jumplink&gt;
### Error

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| message | string | ✓ | Human-readable error message |
| type | One of &quot;OAuthException&quot;, &quot;GraphMethodException&quot;, &quot;GraphAPIException&quot; | ✓ | Error type classification |
| code | integer | ✓ | Numeric error code |
| error_subcode | integer |  | More specific error subcode |
| fbtrace_id | string |  | Internal trace ID for debugging |
| is_transient | boolean |  | Whether this error might be resolved by retrying |
| error_user_title | string |  | User-friendly error title |
| error_user_msg | string |  | User-friendly error message |

## Authentication

| Scheme | Type | Location |
|--------|------|----------|
| bearerAuth | HTTP Bearer | Header: `Authorization` |

### Usage Examples

- **bearerAuth**: Include `Authorization: Bearer your-token-here` in request headers

### Global Authentication Requirements

All endpoints require: bearerAuth
