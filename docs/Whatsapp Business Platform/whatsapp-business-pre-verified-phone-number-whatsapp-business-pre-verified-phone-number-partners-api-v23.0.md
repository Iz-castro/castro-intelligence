

## Base URL

| URL | Description |
|-----|-------------|
| https://graph.facebook.com | Production Graph API server |

## APIs

| Method | Endpoint |
|--------|----------|
| GET | [/&#123;Version&#125;/&#123;Pre-Verified-Phone-Number-ID&#125;/partners](#get-version-pre-verified-phone-number-id-partners) |

&lt;jumplink id=&quot;get-version-pre-verified-phone-number-id-partners&quot;&gt;&lt;/jumplink&gt;
## GET /&#123;Version&#125;/&#123;Pre-Verified-Phone-Number-ID&#125;/partners

Get Pre-Verified Phone Number Partners

Retrieve the list of partner businesses that have been granted access to a specific
WhatsApp Business Pre-Verified Phone Number.


**Use Cases:**
- Monitor partner business relationships and access permissions
- Verify which businesses have access to shared pre-verified phone numbers
- Retrieve partner business information for operational purposes
- Validate partnership configurations before business operations


**Rate Limiting:**
Standard Graph API rate limits apply. Use appropriate retry logic with exponential backoff.


**Caching:**
Partner information can be cached for moderate periods, but partnership relationships
may change. Implement appropriate cache invalidation strategies.


### Header Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| User-Agent | string |  | The user agent string identifying the client software making the request. |
| Authorization | string | ✓ | Bearer token for API authentication. This should be a valid access token obtained through the appropriate OAuth flow or system user token. |

### Path Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| Version | string | ✓ | Graph API version to use for this request. Determines the API behavior and available features. |
| Pre-Verified-Phone-Number-ID | string | ✓ | Your Pre-Verified Phone Number ID. This ID is provided when the pre-verified phone number is created and can be found in your WhatsApp Business Account management interface. |

### Query Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| fields | string |  | Comma-separated list of fields to include in the response. If not specified, default fields will be returned (id, name). Available fields: id, name, created_time, updated_time, verification_status, primary_page, timezone_id, two_factor_type |
| limit | integer [min: 1, max: 100] |  | Maximum number of partner businesses to return per page. Default is 25, maximum is 100. |
| after | string |  | Cursor for pagination. Use the &#039;after&#039; cursor from a previous response to get the next page. |
| before | string |  | Cursor for pagination. Use the &#039;before&#039; cursor from a previous response to get the previous page. |

### Responses

**200**

Successfully retrieved partner businesses for the pre-verified phone number

**Content Type**: `application/json`

**Schema**: [WhatsAppBusinessPreVerifiedPhoneNumberPartnersResponse](#whatsappbusinesspreverifiedphonenumberpartnersresponse)

**400**

Bad Request - Invalid parameters or malformed request

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;Invalid parameter: pre_verified_phone_number_id must be a valid numeric string&quot;,
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
        &quot;message&quot;: &quot;Your app doesn&#039;t have permission to access this Pre-Verified Phone Number&quot;,
        &quot;type&quot;: &quot;OAuthException&quot;,
        &quot;code&quot;: 200,
        &quot;error_subcode&quot;: 1349174,
        &quot;fbtrace_id&quot;: &quot;AXsgnV2Cm3ZMGF3dF_cfYIn&quot;,
        &quot;error_user_title&quot;: &quot;Permission Denied&quot;,
        &quot;error_user_msg&quot;: &quot;Your app doesn&#039;t have permission to access this resource&quot;
    &#125;
&#125;\n```

**404**

Not Found - Pre-Verified Phone Number ID does not exist or is not accessible

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;Pre-Verified Phone Number not found&quot;,
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
        &quot;message&quot;: &quot;The requested fields are not available for this pre-verified phone number&quot;,
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

&lt;jumplink id=&quot;whatsappbusinesspreverifiedphonenumberpartnersresponse&quot;&gt;&lt;/jumplink&gt;
### WhatsAppBusinessPreVerifiedPhoneNumberPartnersResponse

Response containing partner businesses for a pre-verified phone number

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| data | array of [BusinessPartner](#businesspartner) | ✓ | List of partner businesses with access to the pre-verified phone number |
| paging | [CursorPaging](#cursorpaging) |  |  |

&lt;jumplink id=&quot;businesspartner&quot;&gt;&lt;/jumplink&gt;
### BusinessPartner

Business entity that has partner access to the pre-verified phone number

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| id | string | ✓ | Unique identifier for the partner business |
| name | string | ✓ | Name of the partner business |
| created_time | string (date-time) |  | ISO 8601 timestamp when the business was created |
| updated_time | string (date-time) |  | ISO 8601 timestamp when the business was last updated |
| verification_status | One of &quot;not_verified&quot;, &quot;pending&quot;, &quot;verified&quot; |  | Business verification status |
| primary_page | string |  | Primary Facebook Page ID associated with the business |
| timezone_id | integer |  | Timezone identifier for the business location |
| two_factor_type | One of &quot;none&quot;, &quot;admin_required&quot; |  | Two-factor authentication method configured for the business |

&lt;jumplink id=&quot;cursorpaging&quot;&gt;&lt;/jumplink&gt;
### CursorPaging

Cursor-based pagination information

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| cursors | [Cursors](#object-cursors-1) |  |  |
| next | string |  | Graph API endpoint URL for the next page of results |
| previous | string |  | Graph API endpoint URL for the previous page of results |

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
