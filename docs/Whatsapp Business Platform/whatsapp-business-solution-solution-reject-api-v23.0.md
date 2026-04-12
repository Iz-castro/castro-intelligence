

## Base URL

| URL | Description |
|-----|-------------|
| https://graph.facebook.com | Production Graph API server |

## APIs

| Method | Endpoint |
|--------|----------|
| POST | [/&#123;Version&#125;/&#123;Solution-ID&#125;/reject](#post-version-solution-id-reject) |

&lt;jumplink id=&quot;post-version-solution-id-reject&quot;&gt;&lt;/jumplink&gt;
## POST /&#123;Version&#125;/&#123;Solution-ID&#125;/reject

Reject Multi-Partner Solution Request

Reject a pending partnership request or deactivation request for a Multi-Partner Solution.
This endpoint allows solution owners to decline incoming requests and maintain control
over their solution partnerships and lifecycle.


**Use Cases:**
- Reject partnership requests from unauthorized or incompatible applications
- Decline deactivation requests to keep solutions active
- Maintain solution security and partnership quality
- Control solution access and collaboration boundaries


**Request Types:**
- `PARTNERSHIP_REQUEST`: Reject an incoming partnership request from another app
- `DEACTIVATION_REQUEST`: Reject a request to deactivate the solution


**Rate Limiting:**
Standard Graph API rate limits apply. Use appropriate retry logic with exponential backoff.


**Business Logic:**
- Only solution owners can reject requests for their solutions
- Partnership rejections require the partner_app_id parameter
- Rejection actions are permanent and cannot be undone through this API
- Rejected requests may need to be resubmitted through proper channels


### Header Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| User-Agent | string |  | The user agent string identifying the client software making the request. |
| Authorization | string | ✓ | Bearer token for API authentication. This should be a valid access token obtained through the appropriate OAuth flow or system user token. |

### Path Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| Version | string | ✓ | Graph API version to use for this request. Determines the API behavior and available features. |
| Solution-ID | string | ✓ | Your Multi-Partner Solution ID. This ID is provided when you create the solution and can be found in your Partner Dashboard or through solution management APIs. |

### Request Body (Required)

**Content Type**: `application/json`

**Schema**: [SolutionRejectRequest](#solutionrejectrequest)

### Responses

**200**

Successfully rejected the Multi-Partner Solution request

**Content Type**: `application/json`

**Schema**: [SolutionRejectResponse](#solutionrejectresponse)

**400**

Bad Request - Invalid parameters or malformed request

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**401**

Unauthorized - Invalid or missing access token

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;Invalid OAuth access token&quot;,
        &quot;type&quot;: &quot;OAuthException&quot;,
        &quot;code&quot;: 190,
        &quot;error_subcode&quot;: 463,
        &quot;fbtrace_id&quot;: &quot;AXsgnV2Cm3ZMGF3dF_cfYIn&quot;
    &#125;
&#125;\n```

**403**

Forbidden - Insufficient permissions or not solution owner

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**404**

Not Found - Solution ID does not exist or request not found

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**422**

Unprocessable Entity - Request cannot be processed due to business logic constraints

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**429**

Too Many Requests - Rate limit exceeded

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;Application request limit reached&quot;,
        &quot;type&quot;: &quot;OAuthException&quot;,
        &quot;code&quot;: 4,
        &quot;error_subcode&quot;: 2446079,
        &quot;fbtrace_id&quot;: &quot;AXsgnV2Cm3ZMGF3dF_cfYIn&quot;,
        &quot;is_transient&quot;: true
    &#125;
&#125;\n```

**500**

Internal Server Error - Unexpected server error

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;An unexpected error occurred. Please retry your request&quot;,
        &quot;type&quot;: &quot;GraphMethodException&quot;,
        &quot;code&quot;: 2,
        &quot;fbtrace_id&quot;: &quot;AXsgnV2Cm3ZMGF3dF_cfYIn&quot;,
        &quot;is_transient&quot;: true
    &#125;
&#125;\n```


# Components

## Schemas

&lt;jumplink id=&quot;solutionrejectrequest&quot;&gt;&lt;/jumplink&gt;
### SolutionRejectRequest

Request payload for rejecting a Multi-Partner Solution request

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| request_type | One of &quot;PARTNERSHIP_REQUEST&quot;, &quot;DEACTIVATION_REQUEST&quot; | ✓ | Type of request being rejected |
| rejection_reason | string |  | Optional reason for rejecting the request |
| partner_app_id | string |  | The app ID of the requesting partner. Required when request_type is PARTNERSHIP_REQUEST, not used for DEACTIVATION_REQUEST |

&lt;jumplink id=&quot;solutionrejectresponse&quot;&gt;&lt;/jumplink&gt;
### SolutionRejectResponse

Successful response for solution rejection operation

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| success | boolean | ✓ | Indicates whether the rejection was successful |
| solution_id | string | ✓ | The ID of the Multi-Partner Solution |
| rejected_request_type | One of &quot;PARTNERSHIP_REQUEST&quot;, &quot;DEACTIVATION_REQUEST&quot; | ✓ | Type of request that was rejected |
| rejection_timestamp | string (date-time) |  | ISO 8601 timestamp when the rejection was processed |
| partner_app_id | string |  | App ID of the partner whose request was rejected (for partnership rejections) |

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
| type | string | ✓ | Error category type |
| code | integer | ✓ | Numeric error code |
| error_subcode | integer |  | More specific error subcode when available |
| fbtrace_id | string |  | Unique identifier for debugging and support requests with Meta |
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
