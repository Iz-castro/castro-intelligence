

## Base URL

| URL | Description |
|-----|-------------|
| https://graph.facebook.com | Production Graph API server |

## APIs

| Method | Endpoint |
|--------|----------|
| GET | [/&#123;Version&#125;/&#123;WhatsApp-Account-Number-ID&#125;](#get-version-whatsapp-account-number-id) |

&lt;jumplink id=&quot;get-version-whatsapp-account-number-id&quot;&gt;&lt;/jumplink&gt;
## GET /&#123;Version&#125;/&#123;WhatsApp-Account-Number-ID&#125;

Get WhatsApp Account Number Details

Retrieve comprehensive details about a WhatsApp Account Number, including its current status,
verification information, quality rating, and configuration settings.

**Use Cases:**
- Monitor account number status and quality rating
- Verify account number configuration before messaging operations
- Check verification and approval status
- Retrieve display name and business profile information

**Rate Limiting:**
Standard Graph API rate limits apply. Use appropriate retry logic with exponential backoff.

**Caching:**
Account number details can be cached for short periods, but status information may change
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
| WhatsApp-Account-Number-ID | string | ✓ | Your WhatsApp Account Number ID. This ID represents the account number entity and can be obtained from your WhatsApp Business Account phone numbers list. |

### Query Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| fields | string |  | Comma-separated list of fields to include in the response. If not specified, default fields will be returned (id, display_phone_number, status). Available fields: id, display_phone_number, verified_name, status, quality_rating, country_code, country_dial_code, code_verification_status, name_status, messaging_limit_tier, account_mode, certificate, is_official_business_account |

### Responses

**200**

Successfully retrieved WhatsApp Account Number details

**Content Type**: `application/json`

**Schema**: [WhatsAppAccountNumber](#whatsappaccountnumber)

**400**

Bad Request - Invalid parameters or malformed request

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;Invalid parameter: account_number_id must be a valid numeric string&quot;,
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
        &quot;message&quot;: &quot;Your app doesn&#039;t have permission to access this WhatsApp Account Number&quot;,
        &quot;type&quot;: &quot;OAuthException&quot;,
        &quot;code&quot;: 200,
        &quot;error_subcode&quot;: 1349174,
        &quot;fbtrace_id&quot;: &quot;AXsgnV2Cm3ZMGF3dF_cfYIn&quot;,
        &quot;error_user_title&quot;: &quot;Permission Denied&quot;,
        &quot;error_user_msg&quot;: &quot;Your app doesn&#039;t have permission to access this resource&quot;
    &#125;
&#125;\n```

**404**

Not Found - Account Number ID does not exist or is not accessible

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;WhatsApp Account Number not found&quot;,
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
        &quot;message&quot;: &quot;The requested fields are not available for this account number&quot;,
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

&lt;jumplink id=&quot;whatsappaccountnumber&quot;&gt;&lt;/jumplink&gt;
### WhatsAppAccountNumber

WhatsApp Account Number details and configuration

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| id | string | ✓ | Unique identifier for the WhatsApp Account Number |
| display_phone_number | string | ✓ | Phone number in international format for display purposes |
| verified_name | string |  | Business name verified for this phone number |
| status | [WhatsAppAccountNumberStatus](#whatsappaccountnumberstatus) | ✓ |  |
| quality_rating | [WhatsAppPhoneNumberQualityRating](#whatsappphonenumberqualityrating) |  |  |
| country_code | string |  | ISO 3166-1 alpha-2 country code |
| country_dial_code | string |  | Country dialing code |
| code_verification_status | [WhatsAppCodeVerificationStatus](#whatsappcodeverificationstatus) |  |  |
| name_status | [WhatsAppDisplayNameStatus](#whatsappdisplaynamestatus) |  |  |
| messaging_limit_tier | One of &quot;TIER_50&quot;, &quot;TIER_250&quot;, &quot;TIER_1K&quot;, &quot;TIER_10K&quot;, &quot;TIER_100K&quot;, &quot;TIER_UNLIMITED&quot; |  | Current messaging limit tier for the account number |
| account_mode | [WhatsAppBusinessSandboxEligibility](#whatsappbusinesssandboxeligibility) |  |  |
| certificate | string |  | Business certificate information for the account number |
| is_official_business_account | boolean |  | Whether this is an official business account |

&lt;jumplink id=&quot;whatsappaccountnumberstatus&quot;&gt;&lt;/jumplink&gt;
### WhatsAppAccountNumberStatus

Current status of the WhatsApp Account Number

**Type**: string

**Enum Values**: &quot;CONNECTED&quot;, &quot;DISCONNECTED&quot;, &quot;UNVERIFIED&quot;, &quot;PENDING&quot;, &quot;FLAGGED&quot;, &quot;RESTRICTED&quot;

&lt;jumplink id=&quot;whatsappphonenumberqualityrating&quot;&gt;&lt;/jumplink&gt;
### WhatsAppPhoneNumberQualityRating

Quality rating based on message delivery and user feedback

**Type**: string

**Enum Values**: &quot;GREEN&quot;, &quot;YELLOW&quot;, &quot;RED&quot;, &quot;NA&quot;

&lt;jumplink id=&quot;whatsappcodeverificationstatus&quot;&gt;&lt;/jumplink&gt;
### WhatsAppCodeVerificationStatus

Two-step verification status for the phone number

**Type**: string

**Enum Values**: &quot;VERIFIED&quot;, &quot;UNVERIFIED&quot;

&lt;jumplink id=&quot;whatsappdisplaynamestatus&quot;&gt;&lt;/jumplink&gt;
### WhatsAppDisplayNameStatus

Status of the display name associated with the phone number

**Type**: string

**Enum Values**: &quot;APPROVED&quot;, &quot;AVAILABLE_WITHOUT_REVIEW&quot;, &quot;DECLINED&quot;, &quot;EXPIRED&quot;, &quot;PENDING_REVIEW&quot;, &quot;NONE&quot;

&lt;jumplink id=&quot;whatsappbusinesssandboxeligibility&quot;&gt;&lt;/jumplink&gt;
### WhatsAppBusinessSandboxEligibility

Account mode indicating sandbox or live environment

**Type**: string

**Enum Values**: &quot;LIVE&quot;, &quot;SANDBOX&quot;

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
