

## Base URL

| URL | Description |
|-----|-------------|
| https://graph.facebook.com | Production Graph API server |

## APIs

| Method | Endpoint |
|--------|----------|
| GET | [/&#123;Version&#125;/&#123;User-ID&#125;/assigned_whatsapp_business_accounts](#get-version-user-id-assigned-whatsapp-business-accounts) |

&lt;jumplink id=&quot;get-version-user-id-assigned-whatsapp-business-accounts&quot;&gt;&lt;/jumplink&gt;
## GET /&#123;Version&#125;/&#123;User-ID&#125;/assigned_whatsapp_business_accounts

Get Assigned WhatsApp Business Accounts

Retrieve WhatsApp Business Accounts that have been assigned to a specific user.
This endpoint provides information about account assignments, permissions, and
current status corresponding to the GraphAssignedWhatsAppBusinessAccountsEdge node.


**Use Cases:**
- Retrieve all WhatsApp Business Accounts assigned to a user
- Check user permissions for specific accounts
- Monitor account assignment status and changes
- Validate user access before performing business operations


**Rate Limiting:**
Standard Graph API rate limits apply. Use appropriate retry logic with exponential backoff.


**Caching:**
Assignment information can be cached for short periods, but permissions and status
may change frequently. Implement appropriate cache invalidation strategies.


### Header Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| User-Agent | string |  | The user agent string identifying the client software making the request. |
| Authorization | string | ✓ | Bearer token for API authentication. This should be a valid access token obtained through the appropriate OAuth flow or system user token. |

### Path Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| Version | string | ✓ | Graph API version to use for this request. Determines the API behavior and available features. |
| User-ID | string | ✓ | The user ID for whom to retrieve assigned WhatsApp Business Accounts. This must be a valid user ID within your solution or partnership. |

### Query Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| fields | string |  | Comma-separated list of fields to include in the response. If not specified, default fields will be returned (id, name, status). Available fields: id, name, status, assignment_date, permissions, business_id, phone_numbers |
| limit | integer [min: 1, max: 100] |  | Maximum number of accounts to return per page. Default is 25, maximum is 100. |
| after | string |  | Cursor for pagination. Use this to get the next page of results. |
| before | string |  | Cursor for pagination. Use this to get the previous page of results. |

### Responses

**200**

Successfully retrieved assigned WhatsApp Business Accounts

**Content Type**: `application/json`

**Schema**: [AssignedAccountsResponse](#assignedaccountsresponse)

**400**

Bad Request - Invalid parameters or malformed request

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;Invalid parameter: user_id must be a valid numeric string&quot;,
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
        &quot;message&quot;: &quot;Your app doesn&#039;t have permission to access assigned WhatsApp Business Accounts for this user&quot;,
        &quot;type&quot;: &quot;OAuthException&quot;,
        &quot;code&quot;: 200,
        &quot;error_subcode&quot;: 1349174,
        &quot;fbtrace_id&quot;: &quot;AXsgnV2Cm3ZMGF3dF_cfYIn&quot;,
        &quot;error_user_title&quot;: &quot;Permission Denied&quot;,
        &quot;error_user_msg&quot;: &quot;Your app doesn&#039;t have permission to access this resource&quot;
    &#125;
&#125;\n```

**404**

Not Found - User ID does not exist or is not accessible

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;User not found&quot;,
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
        &quot;message&quot;: &quot;The requested fields are not available for this user&quot;,
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

&lt;jumplink id=&quot;assignedwhatsappbusinessaccount&quot;&gt;&lt;/jumplink&gt;
### AssignedWhatsAppBusinessAccount

WhatsApp Business Account assigned to a user

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| id | string | ✓ | Unique identifier for the WhatsApp Business Account |
| name | string | ✓ | Display name of the WhatsApp Business Account |
| status | [WhatsAppBusinessAccountStatus](#whatsappbusinessaccountstatus) | ✓ |  |
| assignment_date | string (date-time) |  | Date and time when the account was assigned to the user |
| permissions | array of [WhatsAppBusinessAccountPermission](#whatsappbusinessaccountpermission) |  | List of permissions granted to the user for this account |
| business_id | string |  | Business ID that owns this WhatsApp Business Account |
| phone_numbers | array of [PhoneNumberInfo](#phonenumberinfo) |  | Phone numbers associated with this WhatsApp Business Account |

&lt;jumplink id=&quot;whatsappbusinessaccountstatus&quot;&gt;&lt;/jumplink&gt;
### WhatsAppBusinessAccountStatus

Current status of the WhatsApp Business Account

**Type**: string

**Enum Values**: &quot;ACTIVE&quot;, &quot;PENDING&quot;, &quot;RESTRICTED&quot;, &quot;DISABLED&quot;

&lt;jumplink id=&quot;whatsappbusinessaccountpermission&quot;&gt;&lt;/jumplink&gt;
### WhatsAppBusinessAccountPermission

Permission level for WhatsApp Business Account access

**Type**: string

**Enum Values**: &quot;MANAGE&quot;, &quot;DEVELOP&quot;, &quot;MANAGE_TEMPLATES&quot;, &quot;MANAGE_PHONE&quot;, &quot;VIEW_COST&quot;, &quot;MANAGE_EXTENSIONS&quot;, &quot;VIEW_PHONE_ASSETS&quot;, &quot;MANAGE_PHONE_ASSETS&quot;, &quot;VIEW_TEMPLATES&quot;, &quot;VIEW_INSIGHTS&quot;, &quot;RECEIVE_INCOMING_MESSAGES&quot;, &quot;MANAGE_BILLING&quot;, &quot;MANAGE_USERS&quot;, &quot;MESSAGING&quot;, &quot;FULL_CONTROL&quot;

&lt;jumplink id=&quot;phonenumberinfo&quot;&gt;&lt;/jumplink&gt;
### PhoneNumberInfo

Phone number information for WhatsApp Business Account

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| id | string |  | Phone number ID |
| display_phone_number | string |  | Formatted phone number for display |
| verified_name | string |  | Verified business name for this phone number |
| status | One of &quot;CONNECTED&quot;, &quot;DISCONNECTED&quot;, &quot;MIGRATED&quot;, &quot;PENDING&quot;, &quot;DELETED&quot; |  | Status of the phone number |

&lt;jumplink id=&quot;assignedaccountsresponse&quot;&gt;&lt;/jumplink&gt;
### AssignedAccountsResponse

Response containing assigned WhatsApp Business Accounts

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| data | array of [AssignedWhatsAppBusinessAccount](#assignedwhatsappbusinessaccount) | ✓ | List of assigned WhatsApp Business Accounts |
| paging | [PagingInfo](#paginginfo) |  |  |

&lt;jumplink id=&quot;paginginfo&quot;&gt;&lt;/jumplink&gt;
### PagingInfo

Pagination information for the response

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| cursors | [Cursors](#object-cursors-1) |  |  |
| next | string |  | URL for the next page of results |
| previous | string |  | URL for the previous page of results |

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
| before | string |  | Cursor for the previous page |
| after | string |  | Cursor for the next page |

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
