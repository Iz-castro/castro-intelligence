

## Base URL

| URL | Description |
|-----|-------------|
| https://graph.facebook.com | Production Graph API server |

## APIs

| Method | Endpoint |
|--------|----------|
| GET | [/&#123;Version&#125;/&#123;Business-ID&#125;/whatsapp_business_accounts](#get-version-business-id-whatsapp-business-accounts) |
| POST | [/&#123;Version&#125;/&#123;Business-ID&#125;/whatsapp_business_accounts](#post-version-business-id-whatsapp-business-accounts) |

&lt;jumplink id=&quot;get-version-business-id-whatsapp-business-accounts&quot;&gt;&lt;/jumplink&gt;
## GET /&#123;Version&#125;/&#123;Business-ID&#125;/whatsapp_business_accounts

Get WhatsApp Business Accounts

Retrieve a list of WhatsApp Business Accounts owned by the specified business portfolio.

This endpoint provides information about WhatsApp Business Accounts that are owned
by the business, including their configuration, status, and core properties. This
corresponds to the GraphBusinessWhatsAppBusinessAccountsEdge functionality.

**Use Cases:**
- Retrieve list of owned WhatsApp Business Accounts
- Monitor WABA status and configuration
- Verify WABA details for business integrations
- Manage business WhatsApp messaging setups

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
| Business-ID | string | ✓ | Your business portfolio ID. This ID can be found in the Meta Business Suite or through business management APIs. |

### Query Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| fields | string |  | Comma-separated list of fields to include in the response. If not specified, default fields will be returned (id, name, currency, timezone_id). Available fields: id, name, account_review_status, purchase_order_number, currency, timezone_id, business_verification_status, country, on_behalf_of_business_info, is_enabled_for_insights, message_template_namespace |
| business_type | array of One of &quot;ENTERPRISE&quot;, &quot;SMB&quot; |  | Filter results by WhatsApp Business Account type |
| limit | integer [min: 1, max: 100] |  | Maximum number of WhatsApp Business Accounts to return per page. Default is 25, maximum is 100. |
| after | string |  | Cursor for pagination. Use this to get the next page of results. |
| before | string |  | Cursor for pagination. Use this to get the previous page of results. |
| find | string |  | Find a specific WhatsApp Business Account by ID |

### Responses

**200**

Successfully retrieved WhatsApp Business Accounts

**Content Type**: `application/json`

**Schema**: [WhatsAppBusinessAccountsResponse](#whatsappbusinessaccountsresponse)

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
        &quot;message&quot;: &quot;Your app doesn&#039;t have permission to access WhatsApp Business Accounts for this business&quot;,
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


&lt;jumplink id=&quot;post-version-business-id-whatsapp-business-accounts&quot;&gt;&lt;/jumplink&gt;
## POST /&#123;Version&#125;/&#123;Business-ID&#125;/whatsapp_business_accounts

Create WhatsApp Business Account

Create a new WhatsApp Business Account under the specified business portfolio.

This endpoint creates a new WABA with the provided configuration and associates it
with the business portfolio. The account will be set up with the specified payment
method and business settings.

**Rate Limiting:**
Standard Graph API rate limits apply. Account creation may have additional
rate limits to prevent abuse.

**Business Logic:**
- Account name must be unique within the business portfolio
- Payment method must be valid and active
- Business must have appropriate permissions for WABA creation
- Created account will be in pending state until verification is complete


### Header Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| User-Agent | string |  | The user agent string identifying the client software making the request. |
| Authorization | string | ✓ | Bearer token for API authentication. This should be a valid access token obtained through the appropriate OAuth flow or system user token. |

### Path Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| Version | string | ✓ | Graph API version to use for this request. Determines the API behavior and available features. |
| Business-ID | string | ✓ | Your business portfolio ID. This ID can be found in the Meta Business Suite or through business management APIs. |

### Request Body (Required)

**Content Type**: `application/json`

**Schema**: [WhatsAppBusinessAccountCreationRequest](#whatsappbusinessaccountcreationrequest)

### Responses

**200**

Successfully created WhatsApp Business Account

**Content Type**: `application/json`

**Schema**: [WhatsAppBusinessAccountCreationResponse](#whatsappbusinessaccountcreationresponse)

**400**

Bad Request - Invalid parameters or malformed request

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;Invalid parameter: name is required&quot;,
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
        &quot;message&quot;: &quot;Your app doesn&#039;t have permission to create WhatsApp Business Accounts&quot;,
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
        &quot;message&quot;: &quot;Cannot create WhatsApp Business Account: payment method is invalid&quot;,
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

&lt;jumplink id=&quot;whatsappbusinessaccountcreationrequest&quot;&gt;&lt;/jumplink&gt;
### WhatsAppBusinessAccountCreationRequest

Request payload for creating a WhatsApp Business Account

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| name | string | ✓ | Human-readable name for the WhatsApp Business Account |
| primary_funding_id | string |  | ID of the primary funding source (credit card or extended credit) |
| purchase_order_number | string |  | Purchase order number for billing reference |
| currency | string |  | Currency code for billing (ISO 4217 format) |
| timezone_id | integer |  | Timezone ID for the account |
| business_type | [WhatsAppBusinessType](#whatsappbusinesstype) |  |  |
| on_behalf_of_business_id | string |  | Business ID when creating account on behalf of another business |

&lt;jumplink id=&quot;whatsappbusinesstype&quot;&gt;&lt;/jumplink&gt;
### WhatsAppBusinessType

Type of WhatsApp Business Account

**Type**: string

**Enum Values**: &quot;ENTERPRISE&quot;, &quot;SMB&quot;

&lt;jumplink id=&quot;whatsappbusinessaccount&quot;&gt;&lt;/jumplink&gt;
### WhatsAppBusinessAccount

WhatsApp Business Account details and configuration

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| id | string | ✓ | Unique identifier for the WhatsApp Business Account |
| name | string | ✓ | Human-readable name of the WhatsApp Business Account |
| account_review_status | [AccountReviewStatus](#accountreviewstatus) |  |  |
| purchase_order_number | string |  | Purchase order number associated with the account |
| currency | string |  | Currency code for the WABA (ISO 4217 format) |
| timezone_id | string |  | Timezone identifier for the WABA |
| business_verification_status | [BusinessVerificationStatus](#businessverificationstatus) |  |  |
| country | string |  | Country code where the WABA is registered |
| on_behalf_of_business_info | [OnBehalfOfBusinessInfo](#onbehalfofbusinessinfo) |  |  |
| is_enabled_for_insights | boolean |  | Whether insights are enabled for this WABA |
| message_template_namespace | string |  | Namespace for message templates |

&lt;jumplink id=&quot;accountreviewstatus&quot;&gt;&lt;/jumplink&gt;
### AccountReviewStatus

Review status of the WhatsApp Business Account

**Type**: string

**Enum Values**: &quot;APPROVED&quot;, &quot;PENDING&quot;, &quot;REJECTED&quot;, &quot;RESTRICTED&quot;

&lt;jumplink id=&quot;businessverificationstatus&quot;&gt;&lt;/jumplink&gt;
### BusinessVerificationStatus

Verification status of the business associated with the WABA

**Type**: string

**Enum Values**: &quot;VERIFIED&quot;, &quot;UNVERIFIED&quot;, &quot;PENDING&quot;, &quot;REJECTED&quot;

&lt;jumplink id=&quot;onbehalfofbusinessinfo&quot;&gt;&lt;/jumplink&gt;
### OnBehalfOfBusinessInfo

Information about the business on whose behalf the WABA operates

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| id | string |  | Business ID |
| name | string |  | Business name |

&lt;jumplink id=&quot;whatsappbusinessaccountcreationresponse&quot;&gt;&lt;/jumplink&gt;
### WhatsAppBusinessAccountCreationResponse

Response after successfully creating a WhatsApp Business Account

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| id | string | ✓ | Unique identifier for the created WhatsApp Business Account |
| payment_account_id | string | ✓ | ID of the associated payment account for billing |

&lt;jumplink id=&quot;whatsappbusinessaccountsresponse&quot;&gt;&lt;/jumplink&gt;
### WhatsAppBusinessAccountsResponse

Response containing list of WhatsApp Business Accounts

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| data | array of [WhatsAppBusinessAccount](#whatsappbusinessaccount) |  | Array of WhatsApp Business Accounts |
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
