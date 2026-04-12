

## Base URL

| URL | Description |
|-----|-------------|
| https://graph.facebook.com | Production Graph API server |

## APIs

| Method | Endpoint |
|--------|----------|
| GET | [/&#123;Version&#125;/&#123;Phone-Number-ID&#125;/official_business_account](#get-version-phone-number-id-official-business-account) |
| POST | [/&#123;Version&#125;/&#123;Phone-Number-ID&#125;/official_business_account](#post-version-phone-number-id-official-business-account) |

&lt;jumplink id=&quot;get-version-phone-number-id-official-business-account&quot;&gt;&lt;/jumplink&gt;
## GET /&#123;Version&#125;/&#123;Phone-Number-ID&#125;/official_business_account

Get Official Business Account Status

Retrieve the Official Business Account (OBA) status and related information for a WhatsApp Business Account phone number.

**Use Cases:**
- Check current OBA verification status
- Monitor OBA application progress
- Retrieve status messages for business account verification
- Validate business credibility status

**Rate Limiting:**
Standard Graph API rate limits apply. Use appropriate retry logic with exponential backoff.

**Caching:**
OBA status information can be cached for moderate periods, but status may change
during verification processes. Implement appropriate cache invalidation strategies.


### Header Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| User-Agent | string |  | The user agent string identifying the client software making the request. |
| Authorization | string | ✓ | Bearer token for API authentication. This should be a valid access token obtained through the appropriate OAuth flow or system user token. |

### Path Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| Version | string | ✓ | Graph API version to use for this request. Determines the API behavior and available features. |
| Phone-Number-ID | string | ✓ | Your WhatsApp Business phone number ID. This ID represents the phone number status entity and can be obtained from your WhatsApp Business Account phone numbers list. |

### Query Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| fields | string |  | Comma-separated list of fields to include in the response. If not specified, default fields will be returned (oba_status, status_message). Available fields: oba_status, status_message |

### Responses

**200**

Successfully retrieved Official Business Account status

**Content Type**: `application/json`

**Schema**: [OfficialBusinessAccountStatus](#officialbusinessaccountstatus)

**400**

Bad Request - Invalid parameters or malformed request

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;Invalid parameter: phone_number_id must be a valid numeric string&quot;,
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
        &quot;message&quot;: &quot;Your app doesn&#039;t have permission to access this WhatsApp Business Account phone number&quot;,
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
        &quot;message&quot;: &quot;WhatsApp Business Account phone number not found&quot;,
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
        &quot;message&quot;: &quot;The requested fields are not available for this phone number&quot;,
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


&lt;jumplink id=&quot;post-version-phone-number-id-official-business-account&quot;&gt;&lt;/jumplink&gt;
## POST /&#123;Version&#125;/&#123;Phone-Number-ID&#125;/official_business_account

Update Official Business Account Status

Update or modify the Official Business Account (OBA) status for a WhatsApp Business Account phone number.
This endpoint allows businesses to submit new applications, withdraw existing applications, or resubmit
after addressing rejection reasons.

**Use Cases:**
- Submit initial Official Business Account application
- Withdraw pending OBA application
- Resubmit OBA application after addressing rejection feedback
- Update application data for pending applications

**Application Data Requirements:**
When submitting or resubmitting an OBA application, certain business information may be required
depending on the current status and previous submissions.

**Rate Limiting:**
Standard Graph API rate limits apply with additional restrictions on application submissions
to prevent abuse. Use appropriate retry logic with exponential backoff.

**Status Transitions:**
- Applications can only be submitted when no active application exists
- Withdrawals are only allowed for pending applications
- Resubmissions are only allowed after rejection


### Header Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| User-Agent | string |  | The user agent string identifying the client software making the request. |
| Authorization | string | ✓ | Bearer token for API authentication. This should be a valid access token obtained through the appropriate OAuth flow or system user token. |

### Path Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| Version | string | ✓ | Graph API version to use for this request. Determines the API behavior and available features. |
| Phone-Number-ID | string | ✓ | Your WhatsApp Business phone number ID. This ID represents the phone number status entity and can be obtained from your WhatsApp Business Account phone numbers list. |

### Request Body (Required)

Official Business Account status update request

**Content Type**: `application/json`

**Schema**: [OfficialBusinessAccountUpdateRequest](#officialbusinessaccountupdaterequest)

### Responses

**200**

Successfully updated Official Business Account status

**Content Type**: `application/json`

**Schema**: [OfficialBusinessAccountUpdateResponse](#officialbusinessaccountupdateresponse)

**400**

Bad Request - Invalid parameters, malformed request, or invalid state transition

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

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;Your app doesn&#039;t have permission to modify this WhatsApp Business Account phone number&quot;,
        &quot;type&quot;: &quot;OAuthException&quot;,
        &quot;code&quot;: 200,
        &quot;error_subcode&quot;: 1349174,
        &quot;fbtrace_id&quot;: &quot;AXsgnV2Cm3ZMGF3dF_cfYIn&quot;,
        &quot;error_user_title&quot;: &quot;Permission Denied&quot;,
        &quot;error_user_msg&quot;: &quot;Your app doesn&#039;t have permission to modify this resource&quot;
    &#125;
&#125;\n```

**404**

Not Found - Phone number ID does not exist or is not accessible

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;WhatsApp Business Account phone number not found&quot;,
        &quot;type&quot;: &quot;GraphMethodException&quot;,
        &quot;code&quot;: 803,
        &quot;fbtrace_id&quot;: &quot;AXsgnV2Cm3ZMGF3dF_cfYIn&quot;
    &#125;
&#125;\n```

**409**

Conflict - Invalid state transition or conflicting request

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**422**

Unprocessable Entity - Request is valid but cannot be processed due to business rules

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**429**

Too Many Requests - Rate limit exceeded or too many application attempts

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

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

&lt;jumplink id=&quot;officialbusinessaccountstatus&quot;&gt;&lt;/jumplink&gt;
### OfficialBusinessAccountStatus

Official Business Account status information for a WhatsApp Business Account phone number

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| id | string | ✓ | Unique identifier for the WhatsApp Business Account phone number |
| oba_status | [WhatsAppBusinessAppealStatus](#whatsappbusinessappealstatus) | ✓ |  |
| status_message | string | ✓ | Human-readable message describing the current Official Business Account status |

&lt;jumplink id=&quot;officialbusinessaccountupdaterequest&quot;&gt;&lt;/jumplink&gt;
### OfficialBusinessAccountUpdateRequest

Request payload for updating Official Business Account status

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| business_website_url | string (uri) | ✓ | Official business website URL |
| primary_country_of_operation | string | ✓ | Primary country where the business operates |
| primary_language | string |  | Primary language used by the business |
| parent_business_or_brand | string |  | Parent business or brand name |
| supporting_links | array of string (uri) |  | Supporting links that demonstrate business notability (minimum 5, maximum 10) |
| additional_supporting_information | string |  | Additional information to support the Official Business Account application |

&lt;jumplink id=&quot;officialbusinessaccountupdateresponse&quot;&gt;&lt;/jumplink&gt;
### OfficialBusinessAccountUpdateResponse

Response for Official Business Account status update operation

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| success | boolean | ✓ | Indicates if the operation was successful |
| message | string | ✓ | Human-readable message describing the result of the operation |
| updated_status | [OfficialBusinessAccountStatus](#officialbusinessaccountstatus) |  |  |
| tracking_id | string |  | Unique identifier for tracking the application/update request |

&lt;jumplink id=&quot;whatsappbusinessappealstatus&quot;&gt;&lt;/jumplink&gt;
### WhatsAppBusinessAppealStatus

Official Business Account appeal and verification status

**Type**: string

**Enum Values**: &quot;PENDING&quot;, &quot;APPROVED&quot;, &quot;REJECTED&quot;, &quot;UNDER_REVIEW&quot;, &quot;EXPIRED&quot;, &quot;CANCELLED&quot;

&lt;jumplink id=&quot;graphapierror&quot;&gt;&lt;/jumplink&gt;
### GraphAPIError

Standard Graph API error response

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| error | [Error](#object-error-1) | ✓ |  |

## Inline Object Definitions

&lt;jumplink id=&quot;object-error-1&quot;&gt;&lt;/jumplink&gt;
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
