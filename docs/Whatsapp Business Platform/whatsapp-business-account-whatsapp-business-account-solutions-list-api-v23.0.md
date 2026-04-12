

## Base URL

| URL | Description |
|-----|-------------|
| https://graph.facebook.com | Production Graph API server |

## APIs

| Method | Endpoint |
|--------|----------|
| GET | [/&#123;Version&#125;/&#123;WABA-ID&#125;/solutions](#get-version-waba-id-solutions) |

&lt;jumplink id=&quot;get-version-waba-id-solutions&quot;&gt;&lt;/jumplink&gt;
## GET /&#123;Version&#125;/&#123;WABA-ID&#125;/solutions

List Multi-Partner Solutions for WABA

Retrieve a paginated list of Multi-Partner Solutions associated with the specified
WhatsApp Business Account. This endpoint supports field selection and cursor-based
pagination for efficient data retrieval.


**Use Cases:**
- Discover available Multi-Partner Solutions for business onboarding
- Monitor solution status and availability across your WABA
- Retrieve solution ownership and permission details
- Filter solutions by specific fields or status requirements


**Rate Limiting:**
Standard Graph API rate limits apply. Use appropriate retry logic with exponential backoff.


**Caching:**
Solution listings can be cached for short periods, but status information may change
frequently during transitions. Implement appropriate cache invalidation strategies.


**Pagination:**
This endpoint supports cursor-based pagination using `limit`, `after`, and `before`
parameters. Use the `paging` object in responses to navigate through result sets.


### Header Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| User-Agent | string |  | The user agent string identifying the client software making the request. |
| Authorization | string | ✓ | Bearer token for API authentication. This should be a valid access token obtained through the appropriate OAuth flow or system user token. |

### Path Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| Version | string | ✓ | Graph API version to use for this request. Determines the API behavior and available features. |
| WABA-ID | string | ✓ | WhatsApp Business Account ID for which to retrieve associated Multi-Partner Solutions. This ID can be found in your WhatsApp Business Manager or through WABA management APIs. |

### Query Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| fields | string |  | Comma-separated list of fields to include in the response. If not specified, default fields will be returned (name, status, status_for_pending_request). Available fields: id, name, status, status_for_pending_request, owner_app, owner_permissions |
| limit | integer [min: 1, max: 100] |  | Maximum number of solutions to return per page. Default is 25, maximum is 100. |
| after | string |  | Cursor for pagination. Returns solutions after this cursor position. Use the cursor from the previous response&#039;s `paging.cursors.after` field. |
| before | string |  | Cursor for pagination. Returns solutions before this cursor position. Use the cursor from the previous response&#039;s `paging.cursors.before` field. |

### Responses

**200**

Successfully retrieved Multi-Partner Solutions list

**Content Type**: `application/json`

**Schema**: [SolutionsList](#solutionslist)

**400**

Bad Request - Invalid parameters or malformed request

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;Invalid parameter: waba_id must be a valid numeric string&quot;,
        &quot;type&quot;: &quot;OAuthException&quot;,
        &quot;code&quot;: 100,
        &quot;fbtrace_id&quot;: &quot;FAKE_TRACE_ID_123ABC456DEF&quot;
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
        &quot;fbtrace_id&quot;: &quot;FAKE_TRACE_ID_123ABC456DEF&quot;
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
        &quot;fbtrace_id&quot;: &quot;FAKE_TRACE_ID_123ABC456DEF&quot;,
        &quot;error_user_title&quot;: &quot;Permission Denied&quot;,
        &quot;error_user_msg&quot;: &quot;Your app doesn&#039;t have permission to access this resource&quot;
    &#125;
&#125;\n```

**404**

Not Found - WABA ID does not exist or is not accessible

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;WhatsApp Business Account not found&quot;,
        &quot;type&quot;: &quot;GraphMethodException&quot;,
        &quot;code&quot;: 803,
        &quot;fbtrace_id&quot;: &quot;FAKE_TRACE_ID_123ABC456DEF&quot;
    &#125;
&#125;\n```

**422**

Unprocessable Entity - Request parameters are valid but cannot be processed

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;The requested fields are not available for this WABA&quot;,
        &quot;type&quot;: &quot;GraphMethodException&quot;,
        &quot;code&quot;: 100,
        &quot;fbtrace_id&quot;: &quot;FAKE_TRACE_ID_123ABC456DEF&quot;
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
        &quot;fbtrace_id&quot;: &quot;FAKE_TRACE_ID_123ABC456DEF&quot;,
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
        &quot;fbtrace_id&quot;: &quot;FAKE_TRACE_ID_123ABC456DEF&quot;,
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

&lt;jumplink id=&quot;solutionslist&quot;&gt;&lt;/jumplink&gt;
### SolutionsList

Paginated list of Multi-Partner Solutions

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| data | array of [WhatsAppBusinessSolution](#whatsappbusinesssolution) | ✓ | Array of Multi-Partner Solutions associated with the WABA |
| paging | [Paging](#paging) |  |  |

&lt;jumplink id=&quot;paging&quot;&gt;&lt;/jumplink&gt;
### Paging

Pagination information for cursor-based pagination

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| cursors | [Cursors](#object-cursors-1) |  |  |
| previous | string |  | Graph API endpoint URL for the previous page of data |
| next | string |  | Graph API endpoint URL for the next page of data |

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
| before | string |  | Cursor pointing to the start of the page of data that has been returned |
| after | string |  | Cursor pointing to the end of the page of data that has been returned |

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
