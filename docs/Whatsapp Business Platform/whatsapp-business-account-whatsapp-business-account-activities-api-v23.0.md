

## Base URL

| URL | Description |
|-----|-------------|
| https://graph.facebook.com | Production Graph API server |

## APIs

| Method | Endpoint |
|--------|----------|
| GET | [/&#123;Version&#125;/&#123;WABA-ID&#125;/activities](#get-version-waba-id-activities) |

&lt;jumplink id=&quot;get-version-waba-id-activities&quot;&gt;&lt;/jumplink&gt;
## GET /&#123;Version&#125;/&#123;WABA-ID&#125;/activities

Get WhatsApp Business Account Activities

Retrieve activity logs and audit trails for a WhatsApp Business Account.
This endpoint returns a chronological list of activities performed on the account,
including administrative actions, configuration changes, and operational events.

**Use Cases:**
- Monitor account configuration changes and administrative actions
- Generate compliance and audit reports for regulatory requirements
- Track user activities and permission modifications
- Investigate security incidents and unauthorized access attempts
- Monitor API usage patterns and operational events

**Rate Limiting:**
Standard Graph API rate limits apply. Use appropriate retry logic with exponential backoff.

**Caching:**
Activity data can be cached for short periods, but recent activities may change
frequently. Implement appropriate cache invalidation strategies.


### Header Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| User-Agent | string |  | The user agent string identifying the client software making the request. |
| Authorization | string | ✓ | Bearer token for API authentication. This should be a valid access token obtained through the appropriate OAuth flow or system user token. |

### Path Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| Version | string | ✓ | Graph API version to use for this request. Determines the API behavior and available features. |
| WABA-ID | string | ✓ | Your WhatsApp Business Account ID. This ID can be found in your WhatsApp Manager or through the business account management APIs. |

### Query Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| fields | string |  | Comma-separated list of fields to include in the response. If not specified, default fields will be returned (id, activity_type, timestamp, actor_type). Available fields: id, activity_type, timestamp, actor_type, actor_id, actor_name, description, details, ip_address, user_agent |
| limit | integer [min: 1, max: 100] |  | Maximum number of activity records to return per page. Default is 25, maximum is 100. |
| after | string |  | Cursor for pagination. Use this to get the next page of results. |
| before | string |  | Cursor for pagination. Use this to get the previous page of results. |
| since | string |  | Unix timestamp or ISO 8601 date string. Only return activities that occurred after this time. |
| until | string |  | Unix timestamp or ISO 8601 date string. Only return activities that occurred before this time. |
| activity_type | string |  | Filter activities by type. Can be a single type or comma-separated list of types. |

### Responses

**200**

Successfully retrieved WhatsApp Business Account activities

**Content Type**: `application/json`

**Schema**: [ActivityList](#activitylist)

**400**

Bad Request - Invalid parameters or malformed request

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;Invalid parameter: limit must be between 1 and 100&quot;,
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
        &quot;message&quot;: &quot;Your app doesn&#039;t have permission to access WhatsApp Business Account activities&quot;,
        &quot;type&quot;: &quot;OAuthException&quot;,
        &quot;code&quot;: 200,
        &quot;error_subcode&quot;: 1349174,
        &quot;fbtrace_id&quot;: &quot;AXsgnV2Cm3ZMGF3dF_cfYIn&quot;,
        &quot;error_user_title&quot;: &quot;Permission Denied&quot;,
        &quot;error_user_msg&quot;: &quot;Your app doesn&#039;t have permission to access this resource&quot;
    &#125;
&#125;\n```

**404**

Not Found - WhatsApp Business Account ID does not exist or is not accessible

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;WhatsApp Business Account not found&quot;,
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
        &quot;message&quot;: &quot;The requested date range is too large. Maximum range is 90 days&quot;,
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

&lt;jumplink id=&quot;whatsappbusinessaccountactivity&quot;&gt;&lt;/jumplink&gt;
### WhatsAppBusinessAccountActivity

WhatsApp Business Account activity record

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| id | string | ✓ | Unique identifier for the activity record |
| activity_type | [ActivityType](#activitytype) | ✓ |  |
| timestamp | string (date-time) | ✓ | ISO 8601 timestamp when the activity occurred |
| actor_type | [ActorType](#actortype) | ✓ |  |
| actor_id | string |  | ID of the user or system that performed the activity |
| actor_name | string |  | Name of the user or system that performed the activity |
| description | string |  | Human-readable description of the activity |
| details | [Details](#object-details-1) |  | Additional structured details about the activity |
| ip_address | string |  | IP address from which the activity was performed (when available) |
| user_agent | string |  | User agent string from the client that performed the activity |

&lt;jumplink id=&quot;activitytype&quot;&gt;&lt;/jumplink&gt;
### ActivityType

Type of activity performed on the WhatsApp Business Account

**Type**: string

**Enum Values**: &quot;ACCOUNT_CREATED&quot;, &quot;ACCOUNT_UPDATED&quot;, &quot;ACCOUNT_DELETED&quot;, &quot;PHONE_NUMBER_ADDED&quot;, &quot;PHONE_NUMBER_REMOVED&quot;, &quot;PHONE_NUMBER_VERIFIED&quot;, &quot;USER_ADDED&quot;, &quot;USER_REMOVED&quot;, &quot;USER_ROLE_CHANGED&quot;, &quot;PERMISSION_GRANTED&quot;, &quot;PERMISSION_REVOKED&quot;, &quot;TEMPLATE_CREATED&quot;, &quot;TEMPLATE_UPDATED&quot;, &quot;TEMPLATE_DELETED&quot;, &quot;WEBHOOK_CONFIGURED&quot;, &quot;API_ACCESS_GRANTED&quot;, &quot;API_ACCESS_REVOKED&quot;, &quot;BILLING_UPDATED&quot;, &quot;COMPLIANCE_ACTION&quot;, &quot;SECURITY_EVENT&quot;

&lt;jumplink id=&quot;actortype&quot;&gt;&lt;/jumplink&gt;
### ActorType

Type of entity that performed the activity

**Type**: string

**Enum Values**: &quot;USER&quot;, &quot;SYSTEM&quot;, &quot;API&quot;, &quot;ADMIN&quot;, &quot;AUTOMATED_PROCESS&quot;

&lt;jumplink id=&quot;activitylist&quot;&gt;&lt;/jumplink&gt;
### ActivityList

Paginated list of WhatsApp Business Account activities

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| data | array of [WhatsAppBusinessAccountActivity](#whatsappbusinessaccountactivity) | ✓ | Array of activity records |
| paging | [Paging](#paging) |  |  |

&lt;jumplink id=&quot;paging&quot;&gt;&lt;/jumplink&gt;
### Paging

Pagination information for activity results

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| cursors | [Cursors](#object-cursors-2) |  |  |
| previous | string |  | Graph API endpoint URL for the previous page of results |
| next | string |  | Graph API endpoint URL for the next page of results |

&lt;jumplink id=&quot;graphapierror&quot;&gt;&lt;/jumplink&gt;
### GraphAPIError

Standard Graph API error response

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| error | [Error](#object-error-3) | ✓ |  |

## Inline Object Definitions

&lt;jumplink id=&quot;object-details-1&quot;&gt;&lt;/jumplink&gt;
### Details

Additional structured details about the activity

**Additional Properties**: Allowed

&lt;jumplink id=&quot;object-cursors-2&quot;&gt;&lt;/jumplink&gt;
### Cursors

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| before | string |  | Cursor pointing to the start of the page of data |
| after | string |  | Cursor pointing to the end of the page of data |

&lt;jumplink id=&quot;object-error-3&quot;&gt;&lt;/jumplink&gt;
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
