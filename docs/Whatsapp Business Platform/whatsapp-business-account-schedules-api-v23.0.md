

## Base URL

| URL | Description |
|-----|-------------|
| https://graph.facebook.com | Production Graph API server |

## APIs

| Method | Endpoint |
|--------|----------|
| GET | [/&#123;Version&#125;/&#123;WABA-ID&#125;/schedules](#get-version-waba-id-schedules) |
| POST | [/&#123;Version&#125;/&#123;WABA-ID&#125;/schedules](#post-version-waba-id-schedules) |

&lt;jumplink id=&quot;get-version-waba-id-schedules&quot;&gt;&lt;/jumplink&gt;
## GET /&#123;Version&#125;/&#123;WABA-ID&#125;/schedules

Get WhatsApp Business Account Schedules

Retrieve all schedules associated with a WhatsApp Business Account, including their
configuration, status, and execution details.

**Use Cases:**
- List all schedules in a WhatsApp Business Account
- Monitor schedule status and performance
- Check schedule configuration and timing details
- Retrieve schedule execution history and metrics

**Filtering:**
You can filter results using the `filtering` parameter with JSON-encoded filter conditions.
Supported filters include status, schedule_type, and is_active.

**Sorting:**
Results can be sorted by created_time or updated_time in ascending or descending order.

**Rate Limiting:**
Standard Graph API rate limits apply. Use appropriate retry logic with exponential backoff.

**Caching:**
Schedule data can be cached for short periods, but status information may change
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
| WABA-ID | string | ✓ | WhatsApp Business Account ID. This ID can be found in your WhatsApp Manager or through the business management APIs. |

### Query Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| fields | string |  | Comma-separated list of fields to include in the response. If not specified, default fields will be returned. Available fields include: id, name, status, schedule_type, description, start_time, end_time, timezone, days_of_week, created_time, updated_time, is_active, recurrence_pattern |
| filtering | string |  | JSON-encoded array of filter conditions. Each filter should specify field, operator, and value. Supported fields: status, schedule_type, is_active |
| sort | One of &quot;created_time.asc&quot;, &quot;created_time.desc&quot;, &quot;updated_time.asc&quot;, &quot;updated_time.desc&quot; |  | Sort field and direction. Format: field_name.asc or field_name.desc Supported fields: created_time, updated_time |
| limit | integer [min: 1, max: 100] |  | Maximum number of schedules to return per page |
| after | string |  | Cursor for pagination - retrieve records after this cursor |
| before | string |  | Cursor for pagination - retrieve records before this cursor |

### Responses

**200**

Successfully retrieved WhatsApp Business Account schedules

**Content Type**: `application/json`

**Schema**: [WhatsAppBusinessAccountSchedulesConnection](#whatsappbusinessaccountschedulesconnection)

**400**

Bad Request - Invalid parameters or malformed request

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;Invalid parameter: filtering must be valid JSON&quot;,
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
        &quot;message&quot;: &quot;Your app doesn&#039;t have permission to access this WhatsApp Business Account&quot;,
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
        &quot;message&quot;: &quot;The requested fields are not available for this account&quot;,
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


&lt;jumplink id=&quot;post-version-waba-id-schedules&quot;&gt;&lt;/jumplink&gt;
## POST /&#123;Version&#125;/&#123;WABA-ID&#125;/schedules

Create WhatsApp Business Account Schedule

Create a new schedule configuration within a WhatsApp Business Account. This endpoint
allows businesses to set up automated scheduling for various operations such as business hours,
automated responses, and maintenance windows.

**Use Cases:**
- Create business hours schedules for automated responses
- Set up maintenance windows for system operations
- Configure automated message campaigns with timing
- Establish recurring schedule patterns for business operations

**Prerequisites:**
- WhatsApp Business Account must have scheduling feature enabled
- Appropriate permissions for schedule management
- Valid timezone and time format specifications
- Business must meet WhatsApp Business API requirements

**Process Flow:**
1. Submit schedule configuration with timing and recurrence details
2. System validates schedule parameters and conflicts
3. Schedule is created and activated based on is_active flag
4. Monitor schedule status through GET endpoint

**Rate Limiting:**
Schedule creation is subject to rate limits to prevent abuse.
Standard Graph API rate limits also apply.

**Validation:**
- Start time must be before end time
- Timezone must be valid IANA timezone identifier
- Days of week must be valid if specified
- Recurrence pattern must be consistent with schedule type


### Header Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| User-Agent | string |  | The user agent string identifying the client software making the request. |
| Authorization | string | ✓ | Bearer token for API authentication. This should be a valid access token obtained through the appropriate OAuth flow or system user token. |

### Path Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| Version | string | ✓ | Graph API version to use for this request. Determines the API behavior and available features. |
| WABA-ID | string | ✓ | WhatsApp Business Account ID where the schedule will be created. This ID can be found in your WhatsApp Manager or through business management APIs. |

### Request Body (Required)

**Content Type**: `application/json`

**Schema**: [ScheduleCreateRequest](#schedulecreaterequest)

### Responses

**200**

Successfully created schedule

**Content Type**: `application/json`

**Schema**: [ScheduleCreateResponse](#schedulecreateresponse)

**400**

Bad Request - Invalid parameters or malformed request

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;Invalid parameter: start_time must be before end_time&quot;,
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

Forbidden - Insufficient permissions or schedule limit exceeded

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;Schedule limit exceeded for this WhatsApp Business Account&quot;,
        &quot;type&quot;: &quot;OAuthException&quot;,
        &quot;code&quot;: 200,
        &quot;error_subcode&quot;: 1349175,
        &quot;fbtrace_id&quot;: &quot;AXsgnV2Cm3ZMGF3dF_cfYIn&quot;,
        &quot;error_user_title&quot;: &quot;Limit Exceeded&quot;,
        &quot;error_user_msg&quot;: &quot;You have reached the maximum number of schedules for this account&quot;
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

**409**

Conflict - Schedule name already exists or time conflict

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;Schedule name already exists in this WhatsApp Business Account&quot;,
        &quot;type&quot;: &quot;GraphMethodException&quot;,
        &quot;code&quot;: 100,
        &quot;fbtrace_id&quot;: &quot;AXsgnV2Cm3ZMGF3dF_cfYIn&quot;
    &#125;
&#125;\n```

**422**

Unprocessable Entity - Request parameters are valid but cannot be processed

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;Schedule validation failed: invalid timezone identifier&quot;,
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
        &quot;message&quot;: &quot;Schedule creation rate limit exceeded&quot;,
        &quot;type&quot;: &quot;OAuthException&quot;,
        &quot;code&quot;: 4,
        &quot;error_subcode&quot;: 2446080,
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

&lt;jumplink id=&quot;whatsappbusinessaccountschedule&quot;&gt;&lt;/jumplink&gt;
### WhatsAppBusinessAccountSchedule

WhatsApp Business Account schedule configuration and details

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| id | string | ✓ | Unique identifier for the schedule |
| name | string | ✓ | Human-readable name for the schedule |
| status | [WhatsAppScheduleStatus](#whatsappschedulestatus) | ✓ |  |
| schedule_type | [WhatsAppScheduleType](#whatsappscheduletype) | ✓ |  |
| description | string |  | Optional description of the schedule purpose |
| start_time | string (time) |  | Schedule start time in HH:MM format |
| end_time | string (time) |  | Schedule end time in HH:MM format |
| timezone | string |  | Timezone identifier for the schedule |
| days_of_week | array of [DayOfWeek](#dayofweek) |  | Days of the week when the schedule is active |
| created_time | string (date-time) |  | ISO 8601 timestamp when the schedule was created |
| updated_time | string (date-time) |  | ISO 8601 timestamp when the schedule was last updated |
| is_active | boolean |  | Whether the schedule is currently active |
| recurrence_pattern | [RecurrencePattern](#recurrencepattern) |  |  |

&lt;jumplink id=&quot;whatsappschedulestatus&quot;&gt;&lt;/jumplink&gt;
### WhatsAppScheduleStatus

Current status of the schedule

**Type**: string

**Enum Values**: &quot;ACTIVE&quot;, &quot;INACTIVE&quot;, &quot;PAUSED&quot;, &quot;EXPIRED&quot;, &quot;DRAFT&quot;

&lt;jumplink id=&quot;whatsappscheduletype&quot;&gt;&lt;/jumplink&gt;
### WhatsAppScheduleType

Type of schedule configuration

**Type**: string

**Enum Values**: &quot;BUSINESS_HOURS&quot;, &quot;AUTOMATED_RESPONSE&quot;, &quot;MESSAGE_CAMPAIGN&quot;, &quot;MAINTENANCE_WINDOW&quot;, &quot;CUSTOM&quot;

&lt;jumplink id=&quot;dayofweek&quot;&gt;&lt;/jumplink&gt;
### DayOfWeek

Day of the week

**Type**: string

**Enum Values**: &quot;MONDAY&quot;, &quot;TUESDAY&quot;, &quot;WEDNESDAY&quot;, &quot;THURSDAY&quot;, &quot;FRIDAY&quot;, &quot;SATURDAY&quot;, &quot;SUNDAY&quot;

&lt;jumplink id=&quot;recurrencepattern&quot;&gt;&lt;/jumplink&gt;
### RecurrencePattern

Pattern for recurring schedules

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| frequency | One of &quot;DAILY&quot;, &quot;WEEKLY&quot;, &quot;MONTHLY&quot;, &quot;YEARLY&quot; |  |  |
| interval | integer [min: 1] |  | Interval between recurrences |
| end_date | string (date) |  | End date for the recurrence pattern |

&lt;jumplink id=&quot;whatsappbusinessaccountschedulesconnection&quot;&gt;&lt;/jumplink&gt;
### WhatsAppBusinessAccountSchedulesConnection

Paginated collection of WhatsApp Business Account schedules

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| data | array of [WhatsAppBusinessAccountSchedule](#whatsappbusinessaccountschedule) | ✓ | Array of schedule records |
| paging | [CursorPaging](#cursorpaging) |  |  |

&lt;jumplink id=&quot;cursorpaging&quot;&gt;&lt;/jumplink&gt;
### CursorPaging

Cursor-based pagination information

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| cursors | [Cursors](#object-cursors-1) |  |  |
| previous | string |  | URL for the previous page of results |
| next | string |  | URL for the next page of results |

&lt;jumplink id=&quot;schedulecreaterequest&quot;&gt;&lt;/jumplink&gt;
### ScheduleCreateRequest

Request payload for creating a new schedule

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| name | string | ✓ | Human-readable name for the schedule |
| schedule_type | [WhatsAppScheduleType](#whatsappscheduletype) | ✓ |  |
| description | string |  | Optional description of the schedule purpose |
| start_time | string (time) | ✓ | Schedule start time in HH:MM format |
| end_time | string (time) | ✓ | Schedule end time in HH:MM format |
| timezone | string |  | Timezone identifier for the schedule |
| days_of_week | array of [DayOfWeek](#dayofweek) |  | Days of the week when the schedule is active |
| is_active | boolean |  | Whether the schedule should be active upon creation |
| recurrence_pattern | [RecurrencePattern](#recurrencepattern) |  |  |

&lt;jumplink id=&quot;schedulecreateresponse&quot;&gt;&lt;/jumplink&gt;
### ScheduleCreateResponse

Response after successfully creating a schedule

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| id | string | ✓ | Unique identifier for the created schedule |

&lt;jumplink id=&quot;graphapierror&quot;&gt;&lt;/jumplink&gt;
### GraphAPIError

Standard Graph API error response

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| error | [Error](#object-error-2) | ✓ |  |

## Inline Object Definitions

&lt;jumplink id=&quot;object-cursors-1&quot;&gt;&lt;/jumplink&gt;
### Cursors

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| before | string |  | Cursor pointing to the start of the page |
| after | string |  | Cursor pointing to the end of the page |

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
