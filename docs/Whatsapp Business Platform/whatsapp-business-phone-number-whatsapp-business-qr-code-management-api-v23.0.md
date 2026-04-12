

## Base URL

| URL | Description |
|-----|-------------|
| https://graph.facebook.com | Production Graph API server |

## APIs

| Method | Endpoint |
|--------|----------|
| GET | [/&#123;Version&#125;/&#123;Phone-Number-ID&#125;/message_qrdls](#get-version-phone-number-id-message-qrdls) |
| POST | [/&#123;Version&#125;/&#123;Phone-Number-ID&#125;/message_qrdls](#post-version-phone-number-id-message-qrdls) |

&lt;jumplink id=&quot;get-version-phone-number-id-message-qrdls&quot;&gt;&lt;/jumplink&gt;
## GET /&#123;Version&#125;/&#123;Phone-Number-ID&#125;/message_qrdls

List All Message QR Codes

Retrieve all message QR codes for a phone number, sorted by creation time (newest first).
Supports field selection, filtering by code, cursor-based pagination, and QR image generation.


### Header Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| User-Agent | string |  | The user agent string identifying the client software making the request. |
| Authorization | string | ✓ | Bearer token for API authentication. This should be a valid access token obtained through the appropriate OAuth flow or system user token. |

### Path Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| Version | string | ✓ | Graph API version to use for this request. Determines the API behavior and available features. |
| Phone-Number-ID | string | ✓ | The WhatsApp Business Account phone number ID for which to list QR codes. This ID is provided when you add a phone number to your WhatsApp Business Account. |

### Query Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| fields | string |  | Comma-separated list of fields to include in the response. Available fields: - code: QR code identifier (always included) - prefilled_message: Pre-filled message text (always included) - deep_link_url: WhatsApp deep link URL (always included) - creation_time: Unix timestamp when QR code was created (first-party apps only) - qr_image_url.format(FORMAT): QR code image URL where FORMAT is SVG or PNG Example: &quot;code,prefilled_message,qr_image_url.format(SVG)&quot; |
| code | string |  | Filter results to a specific QR code by its unique identifier. When provided, only the matching QR code will be returned (if it exists). |
| limit | integer [min: 1, max: 25] |  | Maximum number of QR codes to return in a single response. Default and maximum limit is typically 25. |
| after | string |  | Cursor for pagination. Use this to get the next page of results. Obtain this value from the paging.cursors.after field in previous responses. |
| before | string |  | Cursor for pagination. Use this to get the previous page of results. Obtain this value from the paging.cursors.before field in previous responses. |

### Responses

**200**

Successfully retrieved the list of message QR codes

**Content Type**: `application/json`

**Schema**: [QrCodeList](#qrcodelist)

**400**

Bad Request - Invalid parameters or malformed request

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;Invalid fields parameter. Check field names and format specifications&quot;,
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
        &quot;message&quot;: &quot;Your app doesn&#039;t have permission to list QR codes for this phone number&quot;,
        &quot;type&quot;: &quot;OAuthException&quot;,
        &quot;code&quot;: 200,
        &quot;error_subcode&quot;: 1349174,
        &quot;fbtrace_id&quot;: &quot;AXsgnV2Cm3ZMGF3dF_cfYIn&quot;,
        &quot;error_user_title&quot;: &quot;Permission Denied&quot;,
        &quot;error_user_msg&quot;: &quot;Your app doesn&#039;t have permission to access this resource&quot;
    &#125;
&#125;\n```

**404**

Not Found - Phone number ID does not exist or is not accessible

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;Phone number not found&quot;,
        &quot;type&quot;: &quot;GraphMethodException&quot;,
        &quot;code&quot;: 803,
        &quot;fbtrace_id&quot;: &quot;AXsgnV2Cm3ZMGF3dF_cfYIn&quot;
    &#125;
&#125;\n```

**429**

Too Many Requests - Rate limit exceeded

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;Too many API calls. Please try again later&quot;,
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


&lt;jumplink id=&quot;post-version-phone-number-id-message-qrdls&quot;&gt;&lt;/jumplink&gt;
## POST /&#123;Version&#125;/&#123;Phone-Number-ID&#125;/message_qrdls

Create or Update Message QR Code

Create a new QR code (without code parameter) or update existing QR code (with code parameter).
Supports optional QR image generation in PNG or SVG format.


### Header Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| User-Agent | string |  | The user agent string identifying the client software making the request. |
| Authorization | string | ✓ | Bearer token for API authentication. This should be a valid access token obtained through the appropriate OAuth flow or system user token. |
| Content-Type | One of &quot;application/json&quot;, &quot;application/x-www-form-urlencoded&quot;, &quot;multipart/form-data&quot; | ✓ | Media type of the request body |

### Path Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| Version | string | ✓ | Graph API version to use for this request. Determines the API behavior and available features. |
| Phone-Number-ID | string | ✓ | The WhatsApp Business Account phone number ID for which to create or update the QR code. This ID is provided when you add a phone number to your WhatsApp Business Account. |

### Request Body (Required)

**Content Type**: `application/json`

**Schema**: Must be one of: [CreateQrCodeRequest](#createqrcoderequest), [UpdateQrCodeRequest](#updateqrcoderequest)

### Responses

**200**

Successfully created or updated the message QR code

**Content Type**: `application/json`

**Schema**: [QrCodeResponse](#qrcoderesponse)

**400**

Bad Request - Invalid parameters or malformed request

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;Invalid prefilled_message length. Maximum 140 characters allowed&quot;,
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
        &quot;message&quot;: &quot;Your app doesn&#039;t have permission to manage QR codes for this phone number&quot;,
        &quot;type&quot;: &quot;OAuthException&quot;,
        &quot;code&quot;: 200,
        &quot;error_subcode&quot;: 1349174,
        &quot;fbtrace_id&quot;: &quot;AXsgnV2Cm3ZMGF3dF_cfYIn&quot;,
        &quot;error_user_title&quot;: &quot;Permission Denied&quot;,
        &quot;error_user_msg&quot;: &quot;Your app doesn&#039;t have permission to access this resource&quot;
    &#125;
&#125;\n```

**404**

Not Found - Phone number ID does not exist or QR code not found for update

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;Phone number not found&quot;,
        &quot;type&quot;: &quot;GraphMethodException&quot;,
        &quot;code&quot;: 803,
        &quot;fbtrace_id&quot;: &quot;AXsgnV2Cm3ZMGF3dF_cfYIn&quot;
    &#125;
&#125;\n```

**429**

Too Many Requests - Rate limit exceeded

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;Too many QR code operations. Please try again later&quot;,
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

&lt;jumplink id=&quot;qrcodedetails&quot;&gt;&lt;/jumplink&gt;
### QrCodeDetails

Complete details of a message QR code

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| code | string | ✓ | Unique 14-character QR code identifier |
| prefilled_message | string | ✓ | Pre-filled message text that appears in customer chat |
| deep_link_url | string (uri) | ✓ | WhatsApp deep link URL for direct conversation initiation |
| creation_time | integer |  | Unix timestamp when QR code was created (first-party apps only) |
| qr_image_url | string (uri) |  | QR code image download URL (when format specified in fields) |

&lt;jumplink id=&quot;qrcodelist&quot;&gt;&lt;/jumplink&gt;
### QrCodeList

List of message QR codes with pagination information

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| data | array of [QrCodeDetails](#qrcodedetails) | ✓ | Array of QR code objects |
| paging | [Paging](#object-paging-2) |  | Pagination information for navigating through large result sets. Contains cursors for accessing previous and next pages of results. |

&lt;jumplink id=&quot;createqrcoderequest&quot;&gt;&lt;/jumplink&gt;
### CreateQrCodeRequest

Request payload for creating a new message QR code

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| prefilled_message | string | ✓ | Pre-filled message text (max 140 characters) that appears in customer chat |
| generate_qr_image | One of &quot;PNG&quot;, &quot;SVG&quot; |  | QR image format. When specified, response includes qr_image_url |

&lt;jumplink id=&quot;updateqrcoderequest&quot;&gt;&lt;/jumplink&gt;
### UpdateQrCodeRequest

Request payload for updating an existing message QR code

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| code | string | ✓ | 14-character QR code identifier to update |
| prefilled_message | string | ✓ | New pre-filled message text (max 140 characters) |

&lt;jumplink id=&quot;qrcoderesponse&quot;&gt;&lt;/jumplink&gt;
### QrCodeResponse

Response containing QR code details after creation or update

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| code | string | ✓ | Unique 14-character identifier for the QR code. This code is used for future updates or deletions. |
| prefilled_message | string | ✓ | The pre-filled message text associated with this QR code. This text appears when customers use the QR code. |
| deep_link_url | string (uri) | ✓ | WhatsApp deep link URL that can be used directly without QR code scanning. Customers can click this link to start a conversation with the pre-filled message. |
| qr_image_url | string (uri) |  | URL to download the QR code image. Only present if generate_qr_image parameter was specified in the request. Image format matches the requested format. |

&lt;jumplink id=&quot;graphapierror&quot;&gt;&lt;/jumplink&gt;
### GraphAPIError

Standard Graph API error response

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| error | [Error](#object-error-3) | ✓ |  |

## Inline Object Definitions

&lt;jumplink id=&quot;object-cursors-1&quot;&gt;&lt;/jumplink&gt;
### Cursors

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| before | string |  | Cursor for accessing the previous page of results |
| after | string |  | Cursor for accessing the next page of results |

&lt;jumplink id=&quot;object-paging-2&quot;&gt;&lt;/jumplink&gt;
### Paging

Pagination information for navigating through large result sets.
Contains cursors for accessing previous and next pages of results.


| Property | Type | Required | Description |
|----------|------|----------|-------------|
| cursors | [Cursors](#object-cursors-1) |  |  |
| previous | string (uri) |  | URL for the previous page of results |
| next | string (uri) |  | URL for the next page of results |

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
