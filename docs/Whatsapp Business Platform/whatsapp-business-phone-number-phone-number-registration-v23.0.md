

## Base URL

| URL | Description |
|-----|-------------|
| https://graph.facebook.com | Production Graph API server |

## APIs

| Method | Endpoint |
|--------|----------|
| POST | [/&#123;Version&#125;/&#123;Phone-Number-ID&#125;/register](#post-version-phone-number-id-register) |

&lt;jumplink id=&quot;post-version-phone-number-id-register&quot;&gt;&lt;/jumplink&gt;
## POST /&#123;Version&#125;/&#123;Phone-Number-ID&#125;/register

Register WhatsApp Business Phone Number

Register a WhatsApp Business phone number for messaging capabilities and enable
two-step verification. This is a required step before sending messages through
the WhatsApp Business Cloud API.


**Registration Process:**
1. Phone number must be in UNVERIFIED status
2. Provide a 6-digit PIN for two-step verification
3. Optionally provide backup data for account migration
4. Registration activates messaging capabilities


**Migration Support:**
For migrating from on-premises WhatsApp Business API, include backup data
with password and encrypted account information.


**Rate Limiting:**
Registration attempts are rate-limited to prevent abuse. Standard Graph API
rate limits apply with additional restrictions for registration endpoints.


**Security Requirements:**
- Two-step verification is mandatory for all registered numbers
- PIN must be securely stored and managed by the business
- Registration enables webhook delivery and message sending capabilities


### Header Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| User-Agent | string |  | The user agent string identifying the client software making the request. |
| Authorization | string | ✓ | Bearer token for API authentication. This should be a valid access token obtained through the appropriate OAuth flow or system user token. |

### Path Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| Version | string | ✓ | Graph API version to use for this request. Determines the API behavior and available features. |
| Phone-Number-ID | string | ✓ | The ID of the phone number to register. This ID is provided when the phone number is added to your WhatsApp Business Account and can be found in WhatsApp Manager. |

### Request Body (Required)

Registration request payload with PIN and optional migration data

**Content Type**: `application/json`

**Schema**: [WhatsAppBusinessPhoneNumberRegistrationRequest](#whatsappbusinessphonenumberregistrationrequest)

### Responses

**200**

Successfully registered WhatsApp Business phone number

**Content Type**: `application/json`

**Schema**: [WhatsAppBusinessPhoneNumberRegistrationResponse](#whatsappbusinessphonenumberregistrationresponse)

**400**

Bad Request - Invalid parameters or malformed request

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;Invalid PIN format. PIN must be exactly 6 digits&quot;,
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
        &quot;message&quot;: &quot;Your app doesn&#039;t have permission to register this phone number&quot;,
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

**422**

Unprocessable Entity - Phone number cannot be registered in current state

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;Phone number is already registered or in invalid state for registration&quot;,
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
        &quot;message&quot;: &quot;Registration rate limit exceeded&quot;,
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
        &quot;message&quot;: &quot;An unexpected error occurred during registration. Please retry your request&quot;,
        &quot;type&quot;: &quot;GraphMethodException&quot;,
        &quot;code&quot;: 2,
        &quot;fbtrace_id&quot;: &quot;AXsgnV2Cm3ZMGF3dF_cfYIn&quot;,
        &quot;is_transient&quot;: true
    &#125;
&#125;\n```


# Components

## Schemas

&lt;jumplink id=&quot;whatsappbusinessphonenumberregistrationrequest&quot;&gt;&lt;/jumplink&gt;
### WhatsAppBusinessPhoneNumberRegistrationRequest

Request payload for registering a WhatsApp Business phone number

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| messaging_product | &quot;whatsapp&quot; | ✓ | Must be &#039;whatsapp&#039; to indicate WhatsApp Business messaging product |
| pin | string | ✓ | 6-digit PIN for two-step verification setup |
| backup | [WhatsAppBusinessAccountBackup](#whatsappbusinessaccountbackup) |  |  |
| data_localization_region | [WhatsAppDataLocalizationRegion](#whatsappdatalocalizationregion) |  |  |
| meta_store_retention_minutes | integer [min: 60, max: 60] |  | Message retention period in minutes (deprecated in v21+) |

&lt;jumplink id=&quot;whatsappbusinessaccountbackup&quot;&gt;&lt;/jumplink&gt;
### WhatsAppBusinessAccountBackup

Backup data for migrating existing WhatsApp Business accounts

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| password | string |  | Backup password for account migration |
| data | string |  | Encrypted backup data for account migration |

&lt;jumplink id=&quot;whatsappdatalocalizationregion&quot;&gt;&lt;/jumplink&gt;
### WhatsAppDataLocalizationRegion

Data localization region for message storage (deprecated in v21+)

**Type**: string

**Enum Values**: &quot;AE&quot;, &quot;AU&quot;, &quot;BH&quot;, &quot;BR&quot;, &quot;CA&quot;, &quot;CH&quot;, &quot;DE&quot;, &quot;GB&quot;, &quot;ID&quot;, &quot;IN&quot;, &quot;JP&quot;, &quot;KR&quot;, &quot;SG&quot;, &quot;ZA&quot;

&lt;jumplink id=&quot;whatsappbusinessphonenumberregistrationresponse&quot;&gt;&lt;/jumplink&gt;
### WhatsAppBusinessPhoneNumberRegistrationResponse

Response from phone number registration request

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| success | boolean | ✓ | Indicates whether the registration was successful |

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
