

## Base URL

| URL | Description |
|-----|-------------|
| https://graph.facebook.com | Production Graph API server |

## APIs

| Method | Endpoint |
|--------|----------|
| GET | [/&#123;Version&#125;/&#123;WABA-ID&#125;/phone_numbers](#get-version-waba-id-phone-numbers) |
| POST | [/&#123;Version&#125;/&#123;WABA-ID&#125;/phone_numbers](#post-version-waba-id-phone-numbers) |

&lt;jumplink id=&quot;get-version-waba-id-phone-numbers&quot;&gt;&lt;/jumplink&gt;
## GET /&#123;Version&#125;/&#123;WABA-ID&#125;/phone_numbers

Get WhatsApp Business Account Phone Numbers

Retrieve all phone numbers associated with a WhatsApp Business Account, including their
status, verification details, and configuration information.

**Use Cases:**
- List all phone numbers in a WhatsApp Business Account
- Monitor phone number status and verification progress
- Check phone number quality ratings and messaging limits
- Retrieve phone number configuration details

**Filtering:**
You can filter results using the `filtering` parameter with JSON-encoded filter conditions.
Supported filters include account_mode, messaging_limit_tier, and is_official_business_account.

**Sorting:**
Results can be sorted by creation_time or last_onboarded_time in ascending or descending order.

**Rate Limiting:**
Standard Graph API rate limits apply. Use appropriate retry logic with exponential backoff.

**Caching:**
Phone number data can be cached for short periods, but status information may change
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
| WABA-ID | string | ✓ | WhatsApp Business Account ID. This ID can be found in your WhatsApp Manager or through the business management APIs. |

### Query Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| fields | string |  | Comma-separated list of fields to include in the response. If not specified, default fields will be returned. Available fields include: id, display_phone_number, verified_name, status, quality_rating, country_code, country_dial_code, code_verification_status, unified_cert_status, account_mode, host_platform, messaging_limit_tier, is_official_business_account, username |
| filtering | string |  | JSON-encoded array of filter conditions. Each filter should specify field, operator, and value. Supported fields: account_mode, messaging_limit_tier, is_official_business_account |
| sort | One of &quot;creation_time.asc&quot;, &quot;creation_time.desc&quot;, &quot;last_onboarded_time.asc&quot;, &quot;last_onboarded_time.desc&quot; |  | Sort field and direction. Format: field_name.asc or field_name.desc Supported fields: creation_time, last_onboarded_time |
| limit | integer [min: 1, max: 100] |  | Maximum number of phone numbers to return per page |
| after | string |  | Cursor for pagination - retrieve records after this cursor |
| before | string |  | Cursor for pagination - retrieve records before this cursor |

### Responses

**200**

Successfully retrieved WhatsApp Business Account phone numbers

**Content Type**: `application/json`

**Schema**: [WhatsAppBusinessAccountPhoneNumbersConnection](#whatsappbusinessaccountphonenumbersconnection)

**400**

Bad Request - Invalid parameters or malformed request

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;Invalid parameter: filtering must be valid JSON&quot;,
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
        &quot;message&quot;: &quot;Your app doesn&#039;t have permission to access this WhatsApp Business Account&quot;,
        &quot;type&quot;: &quot;OAuthException&quot;,
        &quot;code&quot;: 200,
        &quot;error_subcode&quot;: 1349174,
        &quot;fbtrace_id&quot;: &quot;AXsgnV2Cm3ZMGF3dF_cfYIn&quot;,
        &quot;error_user_title&quot;: &quot;Permission Denied&quot;,
        &quot;error_user_msg&quot;: &quot;Your app doesn&#039;t have permission to access this resource&quot;
    &#125;
&#125;\n```

**404**

Not Found - WhatsApp Business Account ID does not exist or is not accessible

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;WhatsApp Business Account not found&quot;,
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
        &quot;message&quot;: &quot;The requested fields are not available for this account&quot;,
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


&lt;jumplink id=&quot;post-version-waba-id-phone-numbers&quot;&gt;&lt;/jumplink&gt;
## POST /&#123;Version&#125;/&#123;WABA-ID&#125;/phone_numbers

Create WhatsApp Business Account Phone Number

Create a new phone number registration within a WhatsApp Business Account. This endpoint
initiates the phone number onboarding process, including verification and business name approval.

**Use Cases:**
- Add new phone numbers to a WhatsApp Business Account
- Migrate phone numbers from on-premises to Cloud API
- Register pre-verified phone numbers for BSP scenarios
- Initiate phone number verification and business name approval process

**Prerequisites:**
- WhatsApp Business Account must have available phone number slots
- Phone number must not be already registered with WhatsApp Business
- Business must meet WhatsApp Business API requirements
- Appropriate permissions and app review completion

**Process Flow:**
1. Submit phone number and business name for registration
2. Phone number verification code will be sent (if not pre-verified)
3. Business name will be submitted for review
4. Monitor status through GET endpoint until approval

**Rate Limiting:**
Phone number creation is subject to strict rate limits to prevent abuse.
Standard Graph API rate limits also apply.

**Migration Support:**
Set migrate_phone_number=true when migrating from on-premises API to Cloud API.
Additional validation and migration-specific logic will be applied.


### Header Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| User-Agent | string |  | The user agent string identifying the client software making the request. |
| Authorization | string | ✓ | Bearer token for API authentication. This should be a valid access token obtained through the appropriate OAuth flow or system user token. |

### Path Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| Version | string | ✓ | Graph API version to use for this request. Determines the API behavior and available features. |
| WABA-ID | string | ✓ | WhatsApp Business Account ID where the phone number will be added. This ID can be found in your WhatsApp Manager or through business management APIs. |

### Request Body (Required)

**Content Type**: `application/json`

**Schema**: [PhoneNumberCreateRequest](#phonenumbercreaterequest)

### Responses

**200**

Successfully created phone number registration

**Content Type**: `application/json`

**Schema**: [PhoneNumberCreateResponse](#phonenumbercreateresponse)

**400**

Bad Request - Invalid parameters or malformed request

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;Invalid parameter: phone_number must be in E.164 format&quot;,
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

Forbidden - Insufficient permissions or phone number limit exceeded

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;Phone number limit exceeded for this WhatsApp Business Account&quot;,
        &quot;type&quot;: &quot;OAuthException&quot;,
        &quot;code&quot;: 200,
        &quot;error_subcode&quot;: 1349175,
        &quot;fbtrace_id&quot;: &quot;AXsgnV2Cm3ZMGF3dF_cfYIn&quot;,
        &quot;error_user_title&quot;: &quot;Limit Exceeded&quot;,
        &quot;error_user_msg&quot;: &quot;You have reached the maximum number of phone numbers for this account&quot;
    &#125;
&#125;\n```

**404**

Not Found - WhatsApp Business Account ID does not exist or is not accessible

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;WhatsApp Business Account not found&quot;,
        &quot;type&quot;: &quot;GraphMethodException&quot;,
        &quot;code&quot;: 803,
        &quot;fbtrace_id&quot;: &quot;AXsgnV2Cm3ZMGF3dF_cfYIn&quot;
    &#125;
&#125;\n```

**409**

Conflict - Phone number already exists or is in use

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;Phone number is already registered with WhatsApp Business&quot;,
        &quot;type&quot;: &quot;GraphMethodException&quot;,
        &quot;code&quot;: 100,
        &quot;fbtrace_id&quot;: &quot;AXsgnV2Cm3ZMGF3dF_cfYIn&quot;
    &#125;
&#125;\n```

**422**

Unprocessable Entity - Request parameters are valid but cannot be processed

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;Phone number validation failed: invalid format&quot;,
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
        &quot;message&quot;: &quot;Phone number creation rate limit exceeded&quot;,
        &quot;type&quot;: &quot;OAuthException&quot;,
        &quot;code&quot;: 4,
        &quot;error_subcode&quot;: 2446080,
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

&lt;jumplink id=&quot;whatsappbusinessaccountphonenumber&quot;&gt;&lt;/jumplink&gt;
### WhatsAppBusinessAccountPhoneNumber

WhatsApp Business Account phone number details and status information

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| id | string | ✓ | Unique identifier for the phone number status record |
| display_phone_number | string | ✓ | Phone number in international format for display purposes |
| verified_name | string |  | Business name verified for this phone number |
| status | [WhatsAppPhoneNumberStatus](#whatsappphonenumberstatus) | ✓ |  |
| quality_rating | [WhatsAppPhoneNumberQualityRating](#whatsappphonenumberqualityrating) |  |  |
| country_code | string |  | ISO 3166-1 alpha-2 country code |
| country_dial_code | string |  | Country dialing code |
| code_verification_status | [WhatsAppCodeVerificationStatus](#whatsappcodeverificationstatus) |  |  |
| unified_cert_status | [WhatsAppBusinessUnifiedCertStatus](#whatsappbusinessunifiedcertstatus) |  |  |
| account_mode | [WhatsAppBusinessSandboxEligibility](#whatsappbusinesssandboxeligibility) |  |  |
| host_platform | [WhatsAppBusinessAccountHostPlatform](#whatsappbusinessaccounthostplatform) |  |  |
| messaging_limit_tier | One of &quot;TIER_50&quot;, &quot;TIER_250&quot;, &quot;TIER_1K&quot;, &quot;TIER_10K&quot;, &quot;TIER_100K&quot;, &quot;TIER_UNLIMITED&quot; |  | Current messaging limit tier for the phone number |
| is_official_business_account | boolean |  | Whether this is an official business account |
| username | string |  | WhatsApp username for the business account (if available) |

&lt;jumplink id=&quot;whatsappphonenumberstatus&quot;&gt;&lt;/jumplink&gt;
### WhatsAppPhoneNumberStatus

Current status of the phone number in the WhatsApp Business Account

**Type**: string

**Enum Values**: &quot;PENDING&quot;, &quot;LINKED&quot;, &quot;UNLINKED&quot;, &quot;DELETED&quot;, &quot;MIGRATED&quot;, &quot;BANNED&quot;, &quot;RESTRICTED&quot;

&lt;jumplink id=&quot;whatsappphonenumberqualityrating&quot;&gt;&lt;/jumplink&gt;
### WhatsAppPhoneNumberQualityRating

Quality rating for the phone number based on messaging patterns

**Type**: string

**Enum Values**: &quot;GREEN&quot;, &quot;YELLOW&quot;, &quot;RED&quot;, &quot;UNKNOWN&quot;

&lt;jumplink id=&quot;whatsappcodeverificationstatus&quot;&gt;&lt;/jumplink&gt;
### WhatsAppCodeVerificationStatus

Status of phone number verification code

**Type**: string

**Enum Values**: &quot;VERIFIED&quot;, &quot;NOT_VERIFIED&quot;

&lt;jumplink id=&quot;whatsappbusinessunifiedcertstatus&quot;&gt;&lt;/jumplink&gt;
### WhatsAppBusinessUnifiedCertStatus

Unified certification status combining business and name verification

**Type**: string

**Enum Values**: &quot;APPROVED&quot;, &quot;NAME_PENDING_REVIEW&quot;, &quot;NAME_NOT_APPROVED&quot;, &quot;ACCOUNT_REVIEW_NOT_STARTED&quot;, &quot;LIMITED_ACCESS&quot;

&lt;jumplink id=&quot;whatsappbusinesssandboxeligibility&quot;&gt;&lt;/jumplink&gt;
### WhatsAppBusinessSandboxEligibility

Account mode indicating sandbox or live environment eligibility

**Type**: string

**Enum Values**: &quot;LIVE&quot;, &quot;SANDBOX&quot;

&lt;jumplink id=&quot;whatsappbusinessaccounthostplatform&quot;&gt;&lt;/jumplink&gt;
### WhatsAppBusinessAccountHostPlatform

Platform hosting the WhatsApp Business Account

**Type**: string

**Enum Values**: &quot;CLOUD_API&quot;, &quot;ON_PREMISE&quot;, &quot;NOT_APPLICABLE&quot;

&lt;jumplink id=&quot;whatsappbusinessaccountphonenumbersconnection&quot;&gt;&lt;/jumplink&gt;
### WhatsAppBusinessAccountPhoneNumbersConnection

Paginated collection of WhatsApp Business Account phone numbers

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| data | array of [WhatsAppBusinessAccountPhoneNumber](#whatsappbusinessaccountphonenumber) | ✓ | Array of phone number records |
| paging | [CursorPaging](#cursorpaging) |  |  |

&lt;jumplink id=&quot;cursorpaging&quot;&gt;&lt;/jumplink&gt;
### CursorPaging

Cursor-based pagination information

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| cursors | [Cursors](#object-cursors-1) |  |  |
| previous | string |  | URL for the previous page of results |
| next | string |  | URL for the next page of results |

&lt;jumplink id=&quot;phonenumbercreaterequest&quot;&gt;&lt;/jumplink&gt;
### PhoneNumberCreateRequest

Request payload for creating a new phone number registration

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| phone_number | string | ✓ | Phone number in E.164 format without the + prefix |
| verified_name | string | ✓ | Business name to be verified for this phone number |
| cc | string |  | Country code for the phone number |
| migrate_phone_number | boolean |  | Whether this is a phone number migration from on-premises |
| preverified_id | string |  | Pre-verified phone number ID for BSP scenarios |

&lt;jumplink id=&quot;phonenumbercreateresponse&quot;&gt;&lt;/jumplink&gt;
### PhoneNumberCreateResponse

Response after successfully creating a phone number registration

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| id | string | ✓ | Unique identifier for the created phone number status record |

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
| before | string |  | Cursor pointing to the start of the page |
| after | string |  | Cursor pointing to the end of the page |

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
