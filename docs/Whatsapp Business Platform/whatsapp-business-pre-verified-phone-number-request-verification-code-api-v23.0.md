

## Base URL

| URL | Description |
|-----|-------------|
| https://graph.facebook.com | Production Graph API server |

## APIs

| Method | Endpoint |
|--------|----------|
| POST | [/&#123;Version&#125;/&#123;Pre-Verified-Phone-Number-ID&#125;/request_code](#post-version-pre-verified-phone-number-id-request-code) |

&lt;jumplink id=&quot;post-version-pre-verified-phone-number-id-request-code&quot;&gt;&lt;/jumplink&gt;
## POST /&#123;Version&#125;/&#123;Pre-Verified-Phone-Number-ID&#125;/request_code

Request Verification Code for Pre-Verified Phone Number

Request a verification code for a pre-verified phone number via SMS or voice call.
This is part of the WhatsApp Business Account onboarding process where pre-approved
phone numbers must be verified before they can be used for messaging.


**Process Flow:**
1. Call this endpoint to request a verification code
2. User receives code via SMS or voice call
3. Use the verify_code endpoint to complete verification
4. Phone number becomes active for messaging


**Rate Limiting:**
- Limited number of code requests per phone number per time period
- Exponential backoff recommended for retry attempts
- Voice calls may have additional restrictions


**Language Support:**
Verification messages are sent in the specified language when available.
Falls back to English (en_US) if the requested language is not supported.


**Security Considerations:**
- Codes expire after a short time period
- Limited number of verification attempts allowed
- Phone number must be pre-verified and owned by requesting business


### Header Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| User-Agent | string |  | The user agent string identifying the client software making the request. |
| Authorization | string | ✓ | Bearer token for API authentication. This should be a valid access token obtained through the appropriate OAuth flow or system user token. |

### Path Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| Version | string | ✓ | Graph API version to use for this request. Determines the API behavior and available features. |
| Pre-Verified-Phone-Number-ID | string | ✓ | Your pre-verified phone number ID. This ID is provided when the phone number is pre-verified and can be found in your WhatsApp Business Account settings. |

### Request Body (Required)

Verification code request parameters

**Content Type**: `application/json`

**Schema**: [RequestCodeRequest](#requestcoderequest)

### Responses

**200**

Successfully requested verification code

**Content Type**: `application/json`

**Schema**: [RequestCodeResponse](#requestcoderesponse)

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

Not Found - Pre-verified phone number ID does not exist or is not accessible

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;Pre-verified phone number not found&quot;,
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

&lt;jumplink id=&quot;requestcoderequest&quot;&gt;&lt;/jumplink&gt;
### RequestCodeRequest

Request body for requesting verification code

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| code_method | [PhoneVerificationMethodCode](#phoneverificationmethodcode) | ✓ |  |
| language | string | ✓ | Language/locale code for the verification message. Must be a valid locale identifier. The verification message will be sent in this language if supported. Supports various formats including xx_XX, xx-XX, and extended locale codes. |

&lt;jumplink id=&quot;phoneverificationmethodcode&quot;&gt;&lt;/jumplink&gt;
### PhoneVerificationMethodCode

Method for receiving the verification code

**Type**: string

**Enum Values**: &quot;SMS&quot;, &quot;VOICE&quot;

&lt;jumplink id=&quot;requestcoderesponse&quot;&gt;&lt;/jumplink&gt;
### RequestCodeResponse

Response after successfully requesting verification code

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| success | boolean | ✓ | Indicates whether the verification code request was successful |

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
