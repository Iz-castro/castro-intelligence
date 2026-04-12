

## Base URL

| URL | Description |
|-----|-------------|
| https://graph.facebook.com | Production Graph API server |

## APIs

| Method | Endpoint |
|--------|----------|
| POST | [/&#123;Version&#125;/&#123;Business-ID&#125;/share_preverified_numbers](#post-version-business-id-share-preverified-numbers) |

&lt;jumplink id=&quot;post-version-business-id-share-preverified-numbers&quot;&gt;&lt;/jumplink&gt;
## POST /&#123;Version&#125;/&#123;Business-ID&#125;/share_preverified_numbers

Share Pre-Verified Phone Number with Another Business

Share a pre-verified phone number with another business entity, granting specified
permissions for collaborative WhatsApp Business messaging operations.


**Use Cases:**
- Enable partner businesses to use your pre-verified phone numbers for messaging
- Share phone number resources between parent and subsidiary businesses
- Facilitate multi-business WhatsApp integrations with shared phone number access
- Establish temporary or permanent phone number sharing relationships


**Business Logic:**
- Only businesses with appropriate ownership or sharing rights can share phone numbers
- Shared phone numbers maintain original ownership while granting usage permissions
- Multiple businesses can have access to the same phone number with different permission levels
- Sharing relationships can be time-limited with automatic expiration


**Rate Limiting:**
Standard Graph API rate limits apply. Use appropriate retry logic with exponential backoff.


**Validation:**
- Pre-verified phone number must exist and be accessible to the requesting business
- Target business must be a valid and accessible business entity
- Requested permissions must be valid and within the scope of allowed sharing permissions
- Sharing operation must comply with business relationship and access control policies


### Header Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| User-Agent | string |  | The user agent string identifying the client software making the request. |
| Authorization | string | ✓ | Bearer token for API authentication. This should be a valid access token obtained through the appropriate OAuth flow or system user token. |

### Path Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| Version | string | ✓ | Graph API version to use for this request. Determines the API behavior and available features. |
| Business-ID | string | ✓ | Your Business ID that owns or has sharing rights to the pre-verified phone number. This ID can be found in your Meta Business Manager or through business management APIs. |

### Request Body (Required)

Phone number sharing configuration and target business details

**Content Type**: `application/json`

**Schema**: [PreVerifiedPhoneNumberShareRequest](#preverifiedphonenumbersharerequest)

### Responses

**200**

Successfully shared pre-verified phone number with target business

**Content Type**: `application/json`

**Schema**: [PreVerifiedPhoneNumberShareResponse](#preverifiedphonenumbershareresponse)

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

Not Found - Resource does not exist or is not accessible

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

&lt;jumplink id=&quot;preverifiedphonenumbersharerequest&quot;&gt;&lt;/jumplink&gt;
### PreVerifiedPhoneNumberShareRequest

Request payload for sharing a pre-verified phone number with another business

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| preverified_id | string | ✓ | Unique identifier of the pre-verified phone number to be shared. Must be a valid phone number ID that the requesting business owns or has sharing rights to. |
| partner_business_id | string | ✓ | Business ID of the partner business that will receive access to the pre-verified phone number. Must be a valid business entity accessible to the requesting app. |

&lt;jumplink id=&quot;preverifiedphonenumberpermission&quot;&gt;&lt;/jumplink&gt;
### PreVerifiedPhoneNumberPermission

Specific permissions that can be granted for shared pre-verified phone numbers

**Type**: string

**Enum Values**: &quot;MESSAGING&quot;, &quot;VIEW_DETAILS&quot;, &quot;MANAGE_SETTINGS&quot;, &quot;VIEW_ANALYTICS&quot;, &quot;MANAGE_WEBHOOKS&quot;

&lt;jumplink id=&quot;preverifiedphonenumbershareresponse&quot;&gt;&lt;/jumplink&gt;
### PreVerifiedPhoneNumberShareResponse

Response containing details of the successful phone number sharing operation

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| success | boolean | ✓ | Indicates whether the sharing operation was successful |

&lt;jumplink id=&quot;sharingstatus&quot;&gt;&lt;/jumplink&gt;
### SharingStatus

Current status of the phone number sharing relationship

**Type**: string

**Enum Values**: &quot;ACTIVE&quot;, &quot;PENDING&quot;, &quot;EXPIRED&quot;, &quot;REVOKED&quot;

&lt;jumplink id=&quot;sharedpreverifiedphonenumber&quot;&gt;&lt;/jumplink&gt;
### SharedPreVerifiedPhoneNumber

Details of the shared pre-verified phone number

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| id | string |  | Unique identifier for the pre-verified phone number |
| display_phone_number | string |  | Formatted display version of the phone number |
| country_prefix | integer [min: 1, max: 999] |  | Country code prefix for the phone number |
| verification_status | One of &quot;VERIFIED&quot;, &quot;PENDING&quot;, &quot;FAILED&quot; |  | Current verification status of the phone number |

&lt;jumplink id=&quot;businesssummary&quot;&gt;&lt;/jumplink&gt;
### BusinessSummary

Summary information about a business entity

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| id | string |  | Unique identifier for the business |
| name | string |  | Name of the business |
| verification_status | One of &quot;VERIFIED&quot;, &quot;UNVERIFIED&quot;, &quot;PENDING&quot; |  | Business verification status |

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
