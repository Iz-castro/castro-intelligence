

## Base URL

| URL | Description |
|-----|-------------|
| https://graph.facebook.com | Production Graph API server |

## APIs

| Method | Endpoint |
|--------|----------|
| GET | [/&#123;Version&#125;/&#123;Message-History-ID&#125;/events](#get-version-message-history-id-events) |

&lt;jumplink id=&quot;get-version-message-history-id-events&quot;&gt;&lt;/jumplink&gt;
## GET /&#123;Version&#125;/&#123;Message-History-ID&#125;/events

Get WhatsApp Message History Events

Retrieve paginated message delivery status events for a specific message history entry,
including delivery status occurrences, timestamps, and application information.


**Use Cases:**
- Track detailed message delivery status events and transitions
- Monitor delivery status occurrence timestamps
- Retrieve application information for delivery events
- Debug message delivery issues and status changes


**Rate Limiting:**
Standard Graph API rate limits apply. Use appropriate retry logic with exponential backoff.


**Caching:**
Message history events can be cached for short periods, but delivery status events
may change frequently. Implement appropriate cache invalidation strategies.


**Pagination:**
This endpoint supports cursor-based pagination. Use the `after` and `before` cursors
from the response to navigate through results.


### Header Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| User-Agent | string |  | The user agent string identifying the client software making the request. |
| Authorization | string | ✓ | Bearer token for API authentication. This should be a valid access token obtained through the appropriate OAuth flow or system user token. |

### Path Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| Version | string | ✓ | Graph API version to use for this request. Determines the API behavior and available features. |
| Message-History-ID | string | ✓ | Your WhatsApp Business Message History ID. This ID is provided when you retrieve message history and can be found through message history APIs. |

### Query Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| status_filter | [WhatsAppMessageDeliveryStatus](#whatsappmessagedeliverystatus) |  | Filter results by specific delivery status. When provided, only events with this delivery status will be returned. |
| fields | string |  | Comma-separated list of fields to include in the response. If not specified, default fields will be returned (cursor, node&#123;id,delivery_status,occurrence_timestamp&#125;). Available fields: cursor, node&#123;id,delivery_status,error_description,occurrence_timestamp,status_timestamp,application&#125; |
| limit | integer [min: 1, max: 100] |  | Maximum number of message history events to return per page. Default is 25, maximum is 100. |
| after | string |  | Cursor for pagination. Use this to get the next page of results. This value comes from the `paging.cursors.after` field in previous responses. |
| before | string |  | Cursor for pagination. Use this to get the previous page of results. This value comes from the `paging.cursors.before` field in previous responses. |

### Responses

**200**

Successfully retrieved WhatsApp message history events

**Content Type**: `application/json`

**Schema**: [MessageHistoryEventsResponse](#messagehistoryeventsresponse)

**400**

Bad Request - Invalid parameters or malformed request

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;Invalid parameter: status_filter must be a valid delivery status&quot;,
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
        &quot;message&quot;: &quot;Your app doesn&#039;t have permission to access message history events for this resource&quot;,
        &quot;type&quot;: &quot;OAuthException&quot;,
        &quot;code&quot;: 200,
        &quot;error_subcode&quot;: 1349174,
        &quot;fbtrace_id&quot;: &quot;AXsgnV2Cm3ZMGF3dF_cfYIn&quot;,
        &quot;error_user_title&quot;: &quot;Permission Denied&quot;,
        &quot;error_user_msg&quot;: &quot;Your app doesn&#039;t have permission to access this resource&quot;
    &#125;
&#125;\n```

**404**

Not Found - Message History ID does not exist or is not accessible

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;WhatsApp Business Message History not found&quot;,
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
        &quot;message&quot;: &quot;The requested fields are not available for this message history&quot;,
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

&lt;jumplink id=&quot;whatsappmessagehistoryeventsedge&quot;&gt;&lt;/jumplink&gt;
### WhatsAppMessageHistoryEventsEdge

Edge containing message delivery status occurrence with pagination cursor

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| cursor | string |  | Pagination cursor for this edge |
| node | [WhatsAppBusinessMessageDeliveryStatusOccurrence](#whatsappbusinessmessagedeliverystatusoccurrence) | ✓ |  |

&lt;jumplink id=&quot;whatsappbusinessmessagedeliverystatusoccurrence&quot;&gt;&lt;/jumplink&gt;
### WhatsAppBusinessMessageDeliveryStatusOccurrence

Message delivery status occurrence with detailed event information

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| id | string | ✓ | Unique identifier for the message delivery status occurrence |
| delivery_status | [WhatsAppMessageDeliveryStatus](#whatsappmessagedeliverystatus) | ✓ |  |
| error_description | string |  | Error description if the delivery encountered an error |
| occurrence_timestamp | integer (int64) | ✓ | Unix timestamp when the delivery status occurrence happened |
| status_timestamp | integer (int64) |  | Unix timestamp when the status was recorded |
| application | [ApplicationNode](#applicationnode) |  |  |

&lt;jumplink id=&quot;whatsappmessagedeliverystatus&quot;&gt;&lt;/jumplink&gt;
### WhatsAppMessageDeliveryStatus

Message delivery status

**Type**: string

**Enum Values**: &quot;ACCEPTED&quot;, &quot;DELIVERED&quot;, &quot;ERROR&quot;, &quot;READ&quot;, &quot;SENT&quot;

&lt;jumplink id=&quot;applicationnode&quot;&gt;&lt;/jumplink&gt;
### ApplicationNode

Meta application that processed the delivery status event

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| id | string |  | Unique identifier for the Meta application |
| name | string |  | Name of the Meta application |

&lt;jumplink id=&quot;messagehistoryeventsresponse&quot;&gt;&lt;/jumplink&gt;
### MessageHistoryEventsResponse

Paginated response containing message history events

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| data | array of [WhatsAppMessageHistoryEventsEdge](#whatsappmessagehistoryeventsedge) |  | Array of message history event edges |
| paging | [PaginationInfo](#paginationinfo) |  |  |

&lt;jumplink id=&quot;paginationinfo&quot;&gt;&lt;/jumplink&gt;
### PaginationInfo

Pagination information for navigating through results

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| cursors | [Cursors](#object-cursors-1) |  | Pagination cursors for navigation |
| previous | string (uri) |  | URL for the previous page of results |
| next | string (uri) |  | URL for the next page of results |

&lt;jumplink id=&quot;graphapierror&quot;&gt;&lt;/jumplink&gt;
### GraphAPIError

Standard Graph API error response

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| error | [Error](#object-error-2) | ✓ |  |

## Inline Object Definitions

&lt;jumplink id=&quot;object-cursors-1&quot;&gt;&lt;/jumplink&gt;
### Cursors

Pagination cursors for navigation

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| before | string |  | Cursor for the previous page of results |
| after | string |  | Cursor for the next page of results |

&lt;jumplink id=&quot;object-error-2&quot;&gt;&lt;/jumplink&gt;
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
