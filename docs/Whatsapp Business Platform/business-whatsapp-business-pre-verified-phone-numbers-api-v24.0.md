

## Base URL

| URL | Description |
|-----|-------------|
| https://graph.facebook.com | Production Graph API server |

## APIs

| Method | Endpoint |
|--------|----------|
| GET | [/&#123;Version&#125;/&#123;Business-ID&#125;/preverified_numbers](#get-version-business-id-preverified-numbers) |

&lt;jumplink id=&quot;get-version-business-id-preverified-numbers&quot;&gt;&lt;/jumplink&gt;
## GET /&#123;Version&#125;/&#123;Business-ID&#125;/preverified_numbers

Get Pre-Verified Phone Numbers

Retrieve pre-verified phone numbers available for use with the specified business.
This endpoint provides information about phone numbers that have been pre-verified
and are ready for immediate use with WhatsApp Business messaging operations.

**Use Cases:**
- Retrieve available pre-verified phone numbers for business messaging setup
- Check verification status and availability of phone numbers
- Monitor pre-verified phone number inventory
- Validate phone number options before WhatsApp Business Account configuration
- Facilitate quick business messaging setup with pre-verified numbers

**Filtering and Pagination:**
- Results can be filtered by verification status, availability, and country
- Cursor-based pagination is supported for large result sets
- Default page size is 25 items, maximum is 100 items per page

**Rate Limiting:**
Standard Graph API rate limits apply. Use appropriate retry logic with exponential backoff.

**Caching:**
Phone number information can be cached for short periods, but availability status
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
| Business-ID | string | ✓ | Your Business ID for which to retrieve pre-verified phone numbers. This ID can be found in your Meta Business Manager or through business management APIs. |

### Query Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| fields | string |  | Comma-separated list of fields to include in the response. If not specified, default fields will be returned (id, display_phone_number, verification_status). Available fields: id, display_phone_number, country_prefix, verification_status, availability_status, created_time, last_updated, supported_features, country_code, region |
| limit | integer [min: 1, max: 100] |  | Maximum number of phone numbers to return per page. Default is 25, maximum is 100. |
| after | string |  | Cursor for pagination. Use this to retrieve the next page of results. This value is provided in the &#039;paging&#039; object of previous responses. |
| before | string |  | Cursor for pagination. Use this to retrieve the previous page of results. This value is provided in the &#039;paging&#039; object of previous responses. |
| verification_status | [PhoneNumberVerificationStatus](#phonenumberverificationstatus) |  | Filter results by verification status. Only phone numbers with the specified verification status will be returned. |
| availability_status | [PhoneNumberAvailabilityStatus](#phonenumberavailabilitystatus) |  | Filter results by availability status. Only phone numbers with the specified availability status will be returned. |
| country_code | string |  | Filter results by country code. Only phone numbers from the specified country will be returned. Use ISO 3166-1 alpha-2 country codes. |

### Responses

**200**

Successfully retrieved pre-verified phone numbers

**Content Type**: `application/json`

**Schema**: [PreVerifiedPhoneNumbersResponse](#preverifiedphonenumbersresponse)

**400**

Bad Request - Invalid parameters or malformed request

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

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

**404**

Not Found - Business does not exist or is not accessible

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

&lt;jumplink id=&quot;preverifiedphonenumber&quot;&gt;&lt;/jumplink&gt;
### PreVerifiedPhoneNumber

Pre-verified phone number details and status information

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| id | string | ✓ | Unique identifier for the pre-verified phone number |
| display_phone_number | string | ✓ | Formatted display version of the phone number |
| country_prefix | integer [min: 1, max: 999] |  | Country code prefix for the phone number |
| verification_status | [PhoneNumberVerificationStatus](#phonenumberverificationstatus) | ✓ |  |
| availability_status | [PhoneNumberAvailabilityStatus](#phonenumberavailabilitystatus) |  |  |
| created_time | string (date-time) |  | Timestamp when the phone number was pre-verified |
| last_updated | string (date-time) |  | Timestamp when the phone number information was last updated |
| supported_features | array of [WhatsAppBusinessFeature](#whatsappbusinessfeature) |  | List of WhatsApp Business features supported by this phone number |
| country_code | string |  | ISO 3166-1 alpha-2 country code for the phone number |
| region | string |  | Geographic region or area for the phone number |

&lt;jumplink id=&quot;phonenumberverificationstatus&quot;&gt;&lt;/jumplink&gt;
### PhoneNumberVerificationStatus

Current verification status of the pre-verified phone number

**Type**: string

**Enum Values**: &quot;VERIFIED&quot;, &quot;PENDING&quot;, &quot;FAILED&quot;, &quot;EXPIRED&quot;

&lt;jumplink id=&quot;phonenumberavailabilitystatus&quot;&gt;&lt;/jumplink&gt;
### PhoneNumberAvailabilityStatus

Current availability status of the pre-verified phone number

**Type**: string

**Enum Values**: &quot;AVAILABLE&quot;, &quot;IN_USE&quot;, &quot;RESERVED&quot;, &quot;UNAVAILABLE&quot;

&lt;jumplink id=&quot;whatsappbusinessfeature&quot;&gt;&lt;/jumplink&gt;
### WhatsAppBusinessFeature

WhatsApp Business features supported by the phone number

**Type**: string

**Enum Values**: &quot;MESSAGING&quot;, &quot;BUSINESS_PROFILE&quot;, &quot;WEBHOOKS&quot;, &quot;TEMPLATES&quot;, &quot;ANALYTICS&quot;, &quot;COMMERCE&quot;, &quot;FLOWS&quot;

&lt;jumplink id=&quot;preverifiedphonenumbersresponse&quot;&gt;&lt;/jumplink&gt;
### PreVerifiedPhoneNumbersResponse

Response containing list of pre-verified phone numbers

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| data | array of [PreVerifiedPhoneNumber](#preverifiedphonenumber) | ✓ | List of pre-verified phone numbers |
| paging | [CursorPaging](#cursorpaging) |  |  |

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
