

## Base URL

| URL | Description |
|-----|-------------|
| https://graph.facebook.com | Production Graph API server |

## APIs

| Method | Endpoint |
|--------|----------|
| GET | [/&#123;Version&#125;/&#123;Business-ID&#125;/client_whatsapp_business_accounts](#get-version-business-id-client-whatsapp-business-accounts) |

&lt;jumplink id=&quot;get-version-business-id-client-whatsapp-business-accounts&quot;&gt;&lt;/jumplink&gt;
## GET /&#123;Version&#125;/&#123;Business-ID&#125;/client_whatsapp_business_accounts

Get Client WhatsApp Business Accounts

Retrieve a list of WhatsApp Business Accounts that have been shared with the specified business.


**Use Cases:**
- Monitor shared WABA relationships and permissions
- Verify WABA configuration and status information
- Retrieve WABA details for business integrations
- Manage multi-business WhatsApp messaging setups


**Rate Limiting:**
Standard Graph API rate limits apply. Use appropriate retry logic with exponential backoff.


**Caching:**
WABA information can be cached for moderate periods, but status information may change
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
| Business-ID | string | ✓ | Your Business ID. This ID can be found in your Meta Business Suite URL or through business management APIs. |

### Query Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| fields | string |  | Comma-separated list of fields to include in the response. If not specified, default fields will be returned (id, name, currency, timezone_id). Available fields: id, name, account_review_status, purchase_order_number, audiences, ownership_type, subscribed_apps, business_verification_status, country, currency, timezone_id, on_behalf_of_business_info, schedules, is_enabled_for_insights, dcc_config, message_templates, phone_numbers |
| business_type | array of One of &quot;STANDARD&quot;, &quot;PREMIUM&quot;, &quot;ENTERPRISE&quot; |  | Filter results by WhatsApp Business Account type |
| limit | integer [min: 1, max: 100] |  | Maximum number of WhatsApp Business Accounts to return per page. Default is 25, maximum is 100. |
| after | string |  | Cursor for pagination. Use this to get the next page of results. |
| before | string |  | Cursor for pagination. Use this to get the previous page of results. |
| find | string |  | Find a specific WhatsApp Business Account by ID |

### Responses

**200**

Successfully retrieved client WhatsApp Business Accounts

**Content Type**: `application/json`

**Schema**: [ClientWhatsAppBusinessAccountsResponse](#clientwhatsappbusinessaccountsresponse)

**400**

Bad Request - Invalid parameters or malformed request

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;Invalid parameter: business_id must be a valid numeric string&quot;,
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
        &quot;message&quot;: &quot;Your app doesn&#039;t have permission to access client WhatsApp Business Accounts for this business&quot;,
        &quot;type&quot;: &quot;OAuthException&quot;,
        &quot;code&quot;: 200,
        &quot;error_subcode&quot;: 1349174,
        &quot;fbtrace_id&quot;: &quot;AXsgnV2Cm3ZMGF3dF_cfYIn&quot;,
        &quot;error_user_title&quot;: &quot;Permission Denied&quot;,
        &quot;error_user_msg&quot;: &quot;Your app doesn&#039;t have permission to access this resource&quot;
    &#125;
&#125;\n```

**404**

Not Found - Business ID does not exist or is not accessible

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;Business not found&quot;,
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
        &quot;message&quot;: &quot;The requested fields are not available for this business&quot;,
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

&lt;jumplink id=&quot;whatsappbusinessaccount&quot;&gt;&lt;/jumplink&gt;
### WhatsAppBusinessAccount

WhatsApp Business Account details and configuration

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| id | string | ✓ | Unique identifier for the WhatsApp Business Account |
| name | string | ✓ | Human-readable name of the WhatsApp Business Account |
| account_review_status | [AccountReviewStatus](#accountreviewstatus) |  |  |
| purchase_order_number | string |  | Purchase order number associated with the account |
| audiences | array of string |  | List of audience segments associated with the account |
| ownership_type | [OwnershipType](#ownershiptype) |  |  |
| subscribed_apps | array of [SubscribedApp](#subscribedapp) |  | List of applications subscribed to this WABA |
| business_verification_status | [BusinessVerificationStatus](#businessverificationstatus) |  |  |
| country | string |  | Country code where the WABA is registered |
| currency | string |  | Currency code for the WABA |
| timezone_id | string |  | Timezone identifier for the WABA |
| on_behalf_of_business_info | [OnBehalfOfBusinessInfo](#onbehalfofbusinessinfo) |  |  |
| schedules | array of [BusinessSchedule](#businessschedule) |  | Business hours and scheduling information |
| is_enabled_for_insights | boolean |  | Whether insights are enabled for this WABA |
| dcc_config | [DCCConfig](#dccconfig) |  |  |
| message_templates | array of [MessageTemplate](#messagetemplate) |  | Message templates associated with the WABA |
| phone_numbers | array of [PhoneNumber](#phonenumber) |  | Phone numbers associated with the WABA |

&lt;jumplink id=&quot;accountreviewstatus&quot;&gt;&lt;/jumplink&gt;
### AccountReviewStatus

Review status of the WhatsApp Business Account

**Type**: string

**Enum Values**: &quot;APPROVED&quot;, &quot;PENDING&quot;, &quot;REJECTED&quot;, &quot;RESTRICTED&quot;

&lt;jumplink id=&quot;ownershiptype&quot;&gt;&lt;/jumplink&gt;
### OwnershipType

Type of ownership for the WhatsApp Business Account

**Type**: string

**Enum Values**: &quot;SELF_OWNED&quot;, &quot;CLIENT_OWNED&quot;, &quot;AGENCY_OWNED&quot;

&lt;jumplink id=&quot;businessverificationstatus&quot;&gt;&lt;/jumplink&gt;
### BusinessVerificationStatus

Verification status of the business associated with the WABA

**Type**: string

**Enum Values**: &quot;VERIFIED&quot;, &quot;UNVERIFIED&quot;, &quot;PENDING&quot;, &quot;REJECTED&quot;

&lt;jumplink id=&quot;subscribedapp&quot;&gt;&lt;/jumplink&gt;
### SubscribedApp

Application subscribed to the WABA

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| id | string |  | Application ID |
| name | string |  | Application name |

&lt;jumplink id=&quot;onbehalfofbusinessinfo&quot;&gt;&lt;/jumplink&gt;
### OnBehalfOfBusinessInfo

Information about the business on whose behalf the WABA operates

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| id | string |  | Business ID |
| name | string |  | Business name |

&lt;jumplink id=&quot;businessschedule&quot;&gt;&lt;/jumplink&gt;
### BusinessSchedule

Business hours schedule information

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| day_of_week | One of &quot;MONDAY&quot;, &quot;TUESDAY&quot;, &quot;WEDNESDAY&quot;, &quot;THURSDAY&quot;, &quot;FRIDAY&quot;, &quot;SATURDAY&quot;, &quot;SUNDAY&quot; |  |  |
| open_time | string |  | Opening time in HH:MM format |
| close_time | string |  | Closing time in HH:MM format |

&lt;jumplink id=&quot;dccconfig&quot;&gt;&lt;/jumplink&gt;
### DCCConfig

Data and Content Control configuration

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| enabled | boolean |  | Whether DCC is enabled |
| policy_url | string |  | URL to the DCC policy |

&lt;jumplink id=&quot;messagetemplate&quot;&gt;&lt;/jumplink&gt;
### MessageTemplate

Message template information

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| id | string |  | Template ID |
| name | string |  | Template name |
| status | One of &quot;APPROVED&quot;, &quot;PENDING&quot;, &quot;REJECTED&quot;, &quot;DISABLED&quot; |  |  |

&lt;jumplink id=&quot;phonenumber&quot;&gt;&lt;/jumplink&gt;
### PhoneNumber

Phone number associated with the WABA

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| id | string |  | Phone number ID |
| display_phone_number | string |  | Formatted phone number for display |
| verified_name | string |  | Verified business name for the phone number |

&lt;jumplink id=&quot;clientwhatsappbusinessaccountsresponse&quot;&gt;&lt;/jumplink&gt;
### ClientWhatsAppBusinessAccountsResponse

Response containing list of client WhatsApp Business Accounts

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| data | array of [WhatsAppBusinessAccount](#whatsappbusinessaccount) |  | Array of client WhatsApp Business Accounts |
| paging | [CursorPaging](#cursorpaging) |  |  |

&lt;jumplink id=&quot;cursorpaging&quot;&gt;&lt;/jumplink&gt;
### CursorPaging

Cursor-based pagination information

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| cursors | [Cursors](#object-cursors-1) |  |  |
| previous | string |  | URL for the previous page of results |
| next | string |  | URL for the next page of results |

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
| before | string |  | Cursor pointing to the start of the page of data |
| after | string |  | Cursor pointing to the end of the page of data |

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
