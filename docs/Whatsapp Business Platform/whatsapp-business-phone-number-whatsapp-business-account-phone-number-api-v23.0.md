

## Base URL

| URL | Description |
|-----|-------------|
| https://graph.facebook.com |  |

## APIs

| Method | Endpoint |
|--------|----------|
| GET | [/&#123;Version&#125;/&#123;Phone-Number-ID&#125;](#get-version-phone-number-id) |
| POST | [/&#123;Version&#125;/&#123;Phone-Number-ID&#125;](#post-version-phone-number-id) |

&lt;jumplink id=&quot;get-version-phone-number-id&quot;&gt;&lt;/jumplink&gt;
## GET /&#123;Version&#125;/&#123;Phone-Number-ID&#125;

Retrieve WhatsApp Business Phone Number Information

Retrieve comprehensive information about a WhatsApp Business phone number using its unique ID (CSID).
This endpoint provides phone number status, verification details, quality metrics, and configuration information.

**Core Information Returned:**
- Phone number ID and display format
- Verification status and verified business name
- Quality rating based on message delivery performance
- Code verification status for two-step verification
- Display name certification status (when requested)

**Quality Rating System:**
The quality rating reflects how recipients have been receiving messages from this phone number:
- **GREEN**: High quality - messages are being delivered and engaged with well
- **YELLOW**: Medium quality - some delivery or engagement issues detected
- **RED**: Low quality - significant delivery or engagement problems
- **NA**: Quality rating not yet determined (new phone numbers)

**Display Name Status:**
When requesting the `name_status` field, you&#039;ll receive the current certification status:
- **APPROVED**: Business name verified and certificate available for download
- **AVAILABLE_WITHOUT_REVIEW**: Certificate ready without additional review required
- **DECLINED**: Business name verification rejected
- **EXPIRED**: Existing certificate has expired and needs renewal
- **PENDING_REVIEW**: Name verification request is under review
- **NONE**: No certificate or verification request exists

**Code Verification Status:**
Indicates the two-step verification status:
- **VERIFIED**: Phone number has completed two-step verification
- **UNVERIFIED**: Two-step verification is pending or incomplete

**Use Cases:**
- Monitor phone number quality and delivery performance
- Check verification and certification status
- Validate phone number configuration before sending messages
- Retrieve display information for business profiles
- Audit phone number compliance and status

For more information on quality ratings, see [WhatsApp Business Account Message Quality Rating](https://www.facebook.com/business/help/896873687365001).


### Header Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| User-Agent | string |  | The user agent string identifying the client software making the request. |
| Authorization | string | ✓ | Bearer token for API authentication. This should be a valid access token obtained through the appropriate OAuth flow or system user token. |

### Path Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| Version | string | ✓ | Graph API version to use for this request. Determines the API behavior and available features. Use the latest stable version for optimal performance and feature support. |
| Phone-Number-ID | string | ✓ | Your WhatsApp Business Account phone number ID (CSID). This unique identifier is assigned when you register the phone number with WhatsApp Business API and can be found in your WhatsApp Business Manager. |

### Query Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| fields | string |  | Comma-separated list of additional fields to include in the response. If not specified, only default fields (id, display_phone_number, verified_name, quality_rating) are returned. **Available Fields:** - `name_status`: Display name certification status for business verification - `code_verification_status`: Two-step verification status for the phone number **Field Values:** **name_status** values: - `APPROVED`: Business name approved, certificate available for download - `AVAILABLE_WITHOUT_REVIEW`: Certificate ready without additional review - `DECLINED`: Business name verification rejected - `EXPIRED`: Certificate expired and needs renewal - `PENDING_REVIEW`: Name verification under review - `NONE`: No certificate or verification request exists **code_verification_status** values: - `VERIFIED`: Phone number has completed two-step verification - `UNVERIFIED`: Two-step verification pending or incomplete |

### Responses

**200**

Successfully retrieved phone number information. The response includes core phone number details
and any additional fields requested via the `fields` parameter.


**Content Type**: `application/json`

**Schema**: [PhoneNumberInfo](#phonenumberinfo)

**400**

Bad Request - Invalid parameters or malformed request

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**401**

Unauthorized - Invalid or missing access token

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**403**

Forbidden - Insufficient permissions or access denied

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**404**

Not Found - Phone number ID does not exist or is not accessible

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**422**

Unprocessable Entity - Request parameters are valid but cannot be processed

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**429**

Too Many Requests - Rate limit exceeded

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**500**

Internal Server Error - Unexpected server error

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)


&lt;jumplink id=&quot;post-version-phone-number-id&quot;&gt;&lt;/jumplink&gt;
## POST /&#123;Version&#125;/&#123;Phone-Number-ID&#125;

Update WhatsApp Business Account Phone Number Status and Configuration

Update the status and configuration of a WhatsApp Business Account phone number.
This endpoint supports comprehensive phone number management including status updates,
webhook configuration, security settings, and business profile management.

**Supported Operations:**
- Update connection status between WhatsApp Business Account and phone number
- Configure webhook endpoints for message delivery notifications
- Set up two-step verification and security notifications
- Update display names for name verification
- Configure search visibility and privacy settings
- Set username for the WhatsApp Business Account
- Override webhook callback URIs for message notifications

**Business Logic Requirements:**
- App must be linked to the WhatsApp Business Account
- Webhook subscription must exist before configuring callback URI overrides
- Callback URI verification is performed for external URLs
- Internal URLs are allowed for development environments

**Rate Limiting:**
WhatsApp use case throttling applies. Use appropriate retry logic with exponential backoff.

**Security Validations:**
- App-to-WABA linking validation enforced
- Webhook callback URI verification required for external URLs
- Business integration system user checks for AI bot onboarding
- Capability checks for first-party app access


### Header Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| User-Agent | string |  | The user agent string identifying the client software making the request. |
| Authorization | string | ✓ | Bearer token for API authentication. This should be a valid access token obtained through the appropriate OAuth flow or system user token. |

### Path Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| Version | string | ✓ | Graph API version to use for this request. Determines the API behavior and available features. |
| Phone-Number-ID | string | ✓ | Your WhatsApp Business Account phone number ID (CSID). This ID is provided when you register the phone number and can be found in your WhatsApp Business Manager. |

### Request Body (Optional)

Configuration parameters for updating phone number status and settings.
All parameters are optional and can be combined in a single request.


**Content Type**: `application/json`

**Schema**: [PhoneNumberStatusUpdateRequest](#phonenumberstatusupdaterequest)

### Responses

**200**

Operation completed successfully

**Content Type**: `application/json`

**Schema**: Must be one of: [MessageResponse](#messageresponse), [SuccessResponse](#successresponse)

**400**

Bad Request - Invalid parameters or malformed request

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;Invalid parameter: recipient phone number format is incorrect&quot;,
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
        &quot;message&quot;: &quot;Your app doesn&#039;t have permission to access this phone number&quot;,
        &quot;type&quot;: &quot;OAuthException&quot;,
        &quot;code&quot;: 200,
        &quot;error_subcode&quot;: 1349174,
        &quot;fbtrace_id&quot;: &quot;AXsgnV2Cm3ZMGF3dF_cfYIn&quot;
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

Unprocessable Entity - Request parameters are valid but cannot be processed

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;The phone number is not registered&quot;,
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

&lt;jumplink id=&quot;phonenumberinfo&quot;&gt;&lt;/jumplink&gt;
### PhoneNumberInfo

Phone number information and status

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| id | string |  | The ID associated with the phone number |
| display_phone_number | string |  | The string representation of the phone number |
| verified_name | string |  | The verified name associated with the phone number |
| quality_rating | One of &quot;GREEN&quot;, &quot;YELLOW&quot;, &quot;RED&quot;, &quot;NA&quot; |  | The quality rating of the phone number based on how messages have been received by recipients in recent days. - GREEN: High Quality - YELLOW: Medium Quality - RED: Low Quality - NA: Quality has not been determined |
| code_verification_status | One of &quot;VERIFIED&quot;, &quot;UNVERIFIED&quot; |  | The two-step verification status for the phone number indicating whether the number has completed two-step verification. - VERIFIED: Phone number has completed two-step verification - UNVERIFIED: Two-step verification is pending or incomplete |
| name_status | One of &quot;APPROVED&quot;, &quot;AVAILABLE_WITHOUT_REVIEW&quot;, &quot;DECLINED&quot;, &quot;EXPIRED&quot;, &quot;PENDING_REVIEW&quot;, &quot;NONE&quot; |  | The status of a display name associated with a specific phone number. - APPROVED: The name has been approved. You can download your certificate now. - AVAILABLE_WITHOUT_REVIEW: The certificate for the phone is available and display name is ready to use without review. - DECLINED: The name has not been approved. You cannot download your certificate. - EXPIRED: Your certificate has expired and can no longer be downloaded. - PENDING_REVIEW: Your name request is under review. You cannot download your certificate. - NONE: No certificate is available. |

&lt;jumplink id=&quot;messagerequest&quot;&gt;&lt;/jumplink&gt;
### MessageRequest

Request to send a message via WhatsApp Business API

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| messaging_product | &quot;whatsapp&quot; | ✓ | Messaging service used for the request |
| recipient_type | One of &quot;individual&quot;, &quot;group&quot; |  | Type of recipient |
| to | string | ✓ | Recipient&#039;s phone number (with country code) or group ID |
| type | One of &quot;text&quot;, &quot;image&quot;, &quot;audio&quot;, &quot;video&quot;, &quot;document&quot;, &quot;location&quot;, &quot;contacts&quot;, &quot;template&quot;, &quot;interactive&quot;, &quot;reaction&quot;, &quot;sticker&quot; | ✓ | Type of message being sent |
| text | [TextMessage](#textmessage) |  |  |
| context | [MessageContext](#messagecontext) |  |  |

&lt;jumplink id=&quot;textmessage&quot;&gt;&lt;/jumplink&gt;
### TextMessage

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| body | string | ✓ | Text content of the message |
| preview_url | boolean |  | Whether to show URL preview |

&lt;jumplink id=&quot;messagecontext&quot;&gt;&lt;/jumplink&gt;
### MessageContext

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| message_id | string |  | ID of message being replied to |

&lt;jumplink id=&quot;settingsrequest&quot;&gt;&lt;/jumplink&gt;
### SettingsRequest

Request to update phone number settings

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| calling | [CallingSettings](#callingsettings) |  |  |

&lt;jumplink id=&quot;callingsettings&quot;&gt;&lt;/jumplink&gt;
### CallingSettings

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| status | One of &quot;enabled&quot;, &quot;disabled&quot; | ✓ | Enable or disable calling feature |
| call_icon_visibility | One of &quot;visible&quot;, &quot;hidden&quot; |  | Control visibility of the call icon |

&lt;jumplink id=&quot;registerrequest&quot;&gt;&lt;/jumplink&gt;
### RegisterRequest

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| messaging_product | &quot;whatsapp&quot; | ✓ | Messaging service used for the request |
| pin | string | ✓ | 6-digit PIN for two-step verification |

&lt;jumplink id=&quot;verifycoderequest&quot;&gt;&lt;/jumplink&gt;
### VerifyCodeRequest

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| code | string | ✓ | 6-digit verification code received via SMS or voice |

&lt;jumplink id=&quot;twostepverificationrequest&quot;&gt;&lt;/jumplink&gt;
### TwoStepVerificationRequest

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| pin | string | ✓ | 6-digit PIN for two-step verification |

&lt;jumplink id=&quot;phonenumberstatusupdaterequest&quot;&gt;&lt;/jumplink&gt;
### PhoneNumberStatusUpdateRequest

Request to update phone number status and configuration

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| connection_status | [WhatsAppBusinessAccountToNumberStatus](#whatsappbusinessaccounttonumberstatus) |  |  |
| webhook_url | string (uri) |  | Webhook URL for receiving message notifications |
| whatsapp_business_api_data | [WhatsAppBusinessApiData](#whatsappbusinessapidata) |  |  |
| pin | string |  | Two-step verification PIN (can be empty string) |
| search_visibility | [WAAPIBusinessGlobalSearchStateStatus](#waapibusinessglobalsearchstatestatus) |  |  |
| webhook_configuration | [WebhookConfiguration](#webhookconfiguration) |  |  |
| new_display_name | string |  | New display name for name verification request |
| username | string |  | Username for the WhatsApp Business Account |

&lt;jumplink id=&quot;whatsappbusinessapidata&quot;&gt;&lt;/jumplink&gt;
### WhatsAppBusinessApiData

WhatsApp Business API configuration data

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| pin | string |  | Two-step verification PIN (can be empty string) |
| show_security_notifications | boolean |  | Whether to show security notifications |
| notify_user_change_number | boolean |  | Whether to notify users when changing number |

&lt;jumplink id=&quot;webhookconfiguration&quot;&gt;&lt;/jumplink&gt;
### WebhookConfiguration

Webhook configuration settings

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| override_callback_uri | string (uri) | ✓ | Override callback URI for webhook notifications (can be empty string) |
| verify_token | string |  | Token used to verify webhook requests |

&lt;jumplink id=&quot;whatsappbusinessaccounttonumberstatus&quot;&gt;&lt;/jumplink&gt;
### WhatsAppBusinessAccountToNumberStatus

Connection status between WhatsApp Business Account and phone number

**Type**: string

**Enum Values**: &quot;CONNECTED&quot;, &quot;DISCONNECTED&quot;, &quot;PENDING&quot;, &quot;FLAGGED&quot;, &quot;RESTRICTED&quot;, &quot;RATE_LIMITED&quot;, &quot;MESSAGING_LIMIT_TIER_0&quot;, &quot;MESSAGING_LIMIT_TIER_1&quot;, &quot;MESSAGING_LIMIT_TIER_2&quot;, &quot;MESSAGING_LIMIT_TIER_3&quot;, &quot;MESSAGING_LIMIT_TIER_4&quot;

&lt;jumplink id=&quot;waapibusinessglobalsearchstatestatus&quot;&gt;&lt;/jumplink&gt;
### WAAPIBusinessGlobalSearchStateStatus

Search visibility status for the WhatsApp Business Account

**Type**: string

**Enum Values**: &quot;VISIBLE&quot;, &quot;HIDDEN&quot;

&lt;jumplink id=&quot;messageresponse&quot;&gt;&lt;/jumplink&gt;
### MessageResponse

Response from sending a message

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| messaging_product | &quot;whatsapp&quot; | ✓ | Messaging service |
| contacts | array of [ContactResponse](#contactresponse) | ✓ | Contact information |
| messages | array of [MessageResponseItem](#messageresponseitem) | ✓ | Message information |

&lt;jumplink id=&quot;contactresponse&quot;&gt;&lt;/jumplink&gt;
### ContactResponse

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| input | string | ✓ | Input phone number |
| wa_id | string |  | WhatsApp ID |

&lt;jumplink id=&quot;messageresponseitem&quot;&gt;&lt;/jumplink&gt;
### MessageResponseItem

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| id | string | ✓ | Message ID |

&lt;jumplink id=&quot;successresponse&quot;&gt;&lt;/jumplink&gt;
### SuccessResponse

Generic success response

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| success | boolean | ✓ | Operation success status |

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

## Authentication

| Scheme | Type | Location |
|--------|------|----------|
| bearerAuth | HTTP Bearer | Header: `Authorization` |

### Usage Examples

- **bearerAuth**: Include `Authorization: Bearer your-token-here` in request headers

### Global Authentication Requirements

All endpoints require: bearerAuth
