

## Base URL

| URL | Description |
|-----|-------------|
| https://graph.facebook.com | Production Graph API server |

## APIs

| Method | Endpoint |
|--------|----------|
| GET | [/&#123;Version&#125;/&#123;Solution-ID&#125;](#get-version-solution-id) |

&lt;jumplink id=&quot;get-version-solution-id&quot;&gt;&lt;/jumplink&gt;
## GET /&#123;Version&#125;/&#123;Solution-ID&#125;

Get Multi-Partner Solution Details

Retrieve comprehensive details about a Multi-Partner Solution, including its current status,
pending status transitions, ownership information, and granted permissions.


**Use Cases:**
- Monitor solution lifecycle and status changes
- Verify solution configuration before business onboarding
- Check pending approval requests and status transitions
- Retrieve solution ownership and permission details


**Rate Limiting:**
Standard Graph API rate limits apply. Use appropriate retry logic with exponential backoff.


**Caching:**
Solution details can be cached for short periods, but status information may change
frequently during transitions. Implement appropriate cache invalidation strategies.


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

### Query Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| fields | string |  | Comma-separated list of fields to include in the response. If not specified, default fields will be returned (name, status, status_for_pending_request). Available fields: id, name, status, status_for_pending_request, owner_app, owner_permissions |

### Responses

**200**

Successfully retrieved Multi-Partner Solution details

**Content Type**: `application/json`

**Schema**: [WhatsAppBusinessSolution](#whatsappbusinesssolution)

**400**

Bad Request - Invalid parameters or malformed request

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;Invalid parameter: solution_id must be a valid numeric string&quot;,
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

Forbidden - Insufficient permissions or access denied

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;Your app doesn&#039;t have permission to access this Multi-Partner Solution&quot;,
        &quot;type&quot;: &quot;OAuthException&quot;,
        &quot;code&quot;: 200,
        &quot;error_subcode&quot;: 1349174,
        &quot;fbtrace_id&quot;: &quot;AXsgnV2Cm3ZMGF3dF_cfYIn&quot;,
        &quot;error_user_title&quot;: &quot;Permission Denied&quot;,
        &quot;error_user_msg&quot;: &quot;Your app doesn&#039;t have permission to access this resource&quot;
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

Unprocessable Entity - Request parameters are valid but cannot be processed

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;The requested fields are not available for this solution&quot;,
        &quot;type&quot;: &quot;GraphMethodException&quot;,
        &quot;code&quot;: 100,
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

&lt;jumplink id=&quot;whatsappbusinesssolution&quot;&gt;&lt;/jumplink&gt;
### WhatsAppBusinessSolution

Multi-Partner Solution details and configuration

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| id | string | ✓ | Unique identifier for the Multi-Partner Solution |
| name | string | ✓ | Human-readable name of the Multi-Partner Solution |
| status | [WhatsAppBusinessSolutionStatus](#whatsappbusinesssolutionstatus) | ✓ |  |
| status_for_pending_request | [WhatsAppBusinessSolutionPendingStatus](#whatsappbusinesssolutionpendingstatus) | ✓ |  |
| owner_app | [ApplicationNode](#applicationnode) |  |  |
| owner_permissions | array of [WhatsAppBusinessAccountPermissionTask](#whatsappbusinessaccountpermissiontask) |  | List of WhatsApp Business Account permissions granted to the solution owner |

&lt;jumplink id=&quot;whatsappbusinesssolutionstatus&quot;&gt;&lt;/jumplink&gt;
### WhatsAppBusinessSolutionStatus

Current effective status of the Multi-Partner Solution

**Type**: string

**Enum Values**: &quot;DRAFT&quot;, &quot;INITIATED&quot;, &quot;ACTIVE&quot;, &quot;REJECTED&quot;, &quot;DEACTIVATED&quot;

&lt;jumplink id=&quot;whatsappbusinesssolutionpendingstatus&quot;&gt;&lt;/jumplink&gt;
### WhatsAppBusinessSolutionPendingStatus

Status of any pending solution status transition requests

**Type**: string

**Enum Values**: &quot;PENDING_ACTIVATION&quot;, &quot;PENDING_DEACTIVATION&quot;, &quot;NONE&quot;

&lt;jumplink id=&quot;whatsappbusinessaccountpermissiontask&quot;&gt;&lt;/jumplink&gt;
### WhatsAppBusinessAccountPermissionTask

Granular permission tasks for WhatsApp Business Account access

**Type**: string

**Enum Values**: &quot;MANAGE&quot;, &quot;DEVELOP&quot;, &quot;MANAGE_TEMPLATES&quot;, &quot;MANAGE_PHONE&quot;, &quot;VIEW_COST&quot;, &quot;MANAGE_EXTENSIONS&quot;, &quot;VIEW_PHONE_ASSETS&quot;, &quot;MANAGE_PHONE_ASSETS&quot;, &quot;VIEW_TEMPLATES&quot;, &quot;VIEW_INSIGHTS&quot;, &quot;RECEIVE_INCOMING_MESSAGES&quot;, &quot;MANAGE_BILLING&quot;, &quot;MANAGE_USERS&quot;, &quot;MESSAGING&quot;, &quot;FULL_CONTROL&quot;

&lt;jumplink id=&quot;applicationnode&quot;&gt;&lt;/jumplink&gt;
### ApplicationNode

Meta application that owns the Multi-Partner Solution

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| id | string |  | Unique identifier for the Meta application |
| name | string |  | Name of the Meta application |

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
