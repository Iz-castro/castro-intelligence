

## Base URL

| URL | Description |
|-----|-------------|
| https://graph.facebook.com | Production Graph API server |

## APIs

| Method | Endpoint |
|--------|----------|
| POST | [/&#123;Version&#125;/&#123;Solution-ID&#125;/accept](#post-version-solution-id-accept) |

&lt;jumplink id=&quot;post-version-solution-id-accept&quot;&gt;&lt;/jumplink&gt;
## POST /&#123;Version&#125;/&#123;Solution-ID&#125;/accept

Accept Multi-Partner Solution Invitation

Accept an invitation to participate in a Multi-Partner Solution as a partner application.
This endpoint transitions the partner&#039;s status from NOTIFICATION_SENT to ACCEPTED,
enabling the solution to progress toward ACTIVE status once all required partners accept.


**Use Cases:**
- Accept partnership invitations for Multi-Partner Solutions
- Activate partner participation in existing solutions
- Confirm partner app&#039;s commitment to solution terms and conditions
- Enable solution workflow progression from INITIATED to ACTIVE status


**Business Logic:**
- Only invited partner apps can accept solution invitations
- Solution must be in INITIATED status to accept partnerships
- Partner status transitions from NOTIFICATION_SENT to ACCEPTED
- Solution may become ACTIVE once all required partners accept
- Acceptance creates formal partnership agreement between apps


**Rate Limiting:**
Standard Graph API rate limits apply. Use appropriate retry logic with exponential backoff.


**Validation:**
- Partner app must have received a valid solution invitation
- Solution must exist and be accessible to the partner app
- Partner app must have proper permissions and capabilities
- Acceptance request must include valid partner app identification


### Header Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| User-Agent | string |  | The user agent string identifying the client software making the request. |
| Authorization | string | ✓ | Bearer token for API authentication. This should be a valid access token obtained through the appropriate OAuth flow or system user token. |

### Path Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| Version | string | ✓ | Graph API version to use for this request. Determines the API behavior and available features. |
| Solution-ID | string | ✓ | ID of the Multi-Partner Solution to accept. This ID is provided in the original invitation and can be found in partner notifications or solution management interfaces. |

### Request Body (Required)

**Content Type**: `application/json`

**Schema**: [WhatsAppBusinessSolutionAcceptRequest](#whatsappbusinesssolutionacceptrequest)

### Responses

**200**

Multi-Partner Solution invitation accepted successfully. The partner&#039;s status has been
updated to ACCEPTED and the solution may progress toward ACTIVE status.


**Content Type**: `application/json`

**Schema**: [WhatsAppBusinessSolutionAcceptResponse](#whatsappbusinesssolutionacceptresponse)

**400**

Bad Request - Invalid parameters or malformed request

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;Invalid parameter: partner_app_id must be a valid numeric string&quot;,
        &quot;type&quot;: &quot;OAuthException&quot;,
        &quot;code&quot;: 100,
        &quot;fbtrace_id&quot;: &quot;AXsgnV2Cm3ZMGF3dF_cfYIn&quot;
    &#125;
&#125;\n```

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

Forbidden - Insufficient permissions or not invited to solution

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;Your app is not invited to participate in this Multi-Partner Solution&quot;,
        &quot;type&quot;: &quot;OAuthException&quot;,
        &quot;code&quot;: 200,
        &quot;error_subcode&quot;: 1349175,
        &quot;fbtrace_id&quot;: &quot;AXsgnV2Cm3ZMGF3dF_cfYIn&quot;,
        &quot;error_user_title&quot;: &quot;Permission Denied&quot;,
        &quot;error_user_msg&quot;: &quot;Your app doesn&#039;t have permission to accept this solution invitation&quot;
    &#125;
&#125;\n```

**404**

Not Found - Solution ID does not exist or is not accessible

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;Multi-Partner Solution not found&quot;,
        &quot;type&quot;: &quot;GraphMethodException&quot;,
        &quot;code&quot;: 803,
        &quot;fbtrace_id&quot;: &quot;AXsgnV2Cm3ZMGF3dF_cfYIn&quot;
    &#125;
&#125;\n```

**422**

Unprocessable Entity - Solution cannot be accepted in current state

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;Solution cannot be accepted: solution is not in INITIATED status&quot;,
        &quot;type&quot;: &quot;GraphMethodException&quot;,
        &quot;code&quot;: 100,
        &quot;error_subcode&quot;: 2207051,
        &quot;fbtrace_id&quot;: &quot;AXsgnV2Cm3ZMGF3dF_cfYIn&quot;
    &#125;
&#125;\n```

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

&lt;jumplink id=&quot;whatsappbusinesssolutionacceptrequest&quot;&gt;&lt;/jumplink&gt;
### WhatsAppBusinessSolutionAcceptRequest

Request payload for accepting a Multi-Partner Solution invitation

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| partner_app_id | string | ✓ | ID of the partner application accepting the solution invitation. This must match the app ID that received the original invitation. |
| log_session_id | string |  | Optional session identifier for logging and debugging purposes. Used to track the acceptance flow across multiple API calls. |

&lt;jumplink id=&quot;whatsappbusinesssolutionacceptresponse&quot;&gt;&lt;/jumplink&gt;
### WhatsAppBusinessSolutionAcceptResponse

Successful response confirming solution acceptance

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| solution_id | string | ✓ | ID of the Multi-Partner Solution that was accepted |
| partner_status | [WhatsAppBusinessSolutionPartnerStatus](#whatsappbusinesssolutionpartnerstatus) | ✓ |  |
| success | boolean | ✓ | Indicates whether the acceptance was successful |
| message | string |  | Human-readable confirmation message |
| update_time | string (date-time) |  | Timestamp when the acceptance was processed |

&lt;jumplink id=&quot;whatsappbusinesssolutionpartnerstatus&quot;&gt;&lt;/jumplink&gt;
### WhatsAppBusinessSolutionPartnerStatus

Current status of the partner&#039;s participation in the Multi-Partner Solution

**Type**: string

**Enum Values**: &quot;DRAFT&quot;, &quot;INITIATED&quot;, &quot;NOTIFICATION_SENT&quot;, &quot;ACCEPTED&quot;, &quot;REJECTED&quot;, &quot;DEACTIVATED&quot;

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
