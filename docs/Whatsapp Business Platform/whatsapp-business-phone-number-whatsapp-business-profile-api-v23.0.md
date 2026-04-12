

## Base URL

| URL | Description |
|-----|-------------|
| https://graph.facebook.com | Production Graph API server |

## APIs

| Method | Endpoint |
|--------|----------|
| GET | [/&#123;Version&#125;/&#123;Phone-Number-ID&#125;/whatsapp_business_profile](#get-version-phone-number-id-whatsapp-business-profile) |
| POST | [/&#123;Version&#125;/&#123;Phone-Number-ID&#125;/whatsapp_business_profile](#post-version-phone-number-id-whatsapp-business-profile) |

&lt;jumplink id=&quot;get-version-phone-number-id-whatsapp-business-profile&quot;&gt;&lt;/jumplink&gt;
## GET /&#123;Version&#125;/&#123;Phone-Number-ID&#125;/whatsapp_business_profile

Get WhatsApp Business Profile

Retrieve comprehensive information about a WhatsApp Business Profile, including
business details, contact information, and profile settings.


**Use Cases:**
- Retrieve current business profile information
- Check business contact details and settings
- Verify business vertical and website information
- Get profile picture URL and about section


**Rate Limiting:**
Standard Graph API rate limits apply. Use appropriate retry logic with exponential backoff.


**Caching:**
Business profile information can be cached for moderate periods, but should be
refreshed periodically to ensure accuracy.


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
| Phone-Number-ID | string | ✓ | Your WhatsApp Business phone number ID. This ID represents the phone number status entity and can be obtained from your WhatsApp Business Account phone numbers list. |

### Query Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| fields | string |  | Comma-separated list of fields to include in the response. If not specified, default fields will be returned (messaging_product, about, address, description, email, profile_picture_url, websites, vertical). Available fields: messaging_product, about, address, description, email, profile_picture_url, websites, vertical |

### Responses

**200**

Successfully retrieved WhatsApp Business Profile information

**Content Type**: `application/json`

**Schema**: [WhatsAppBusinessProfileResponse](#whatsappbusinessprofileresponse)

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
        &quot;message&quot;: &quot;Your app doesn&#039;t have permission to access this WhatsApp Business Profile&quot;,
        &quot;type&quot;: &quot;OAuthException&quot;,
        &quot;code&quot;: 200,
        &quot;error_subcode&quot;: 1349174,
        &quot;fbtrace_id&quot;: &quot;AXsgnV2Cm3ZMGF3dF_cfYIn&quot;,
        &quot;error_user_title&quot;: &quot;Permission Denied&quot;,
        &quot;error_user_msg&quot;: &quot;Your app doesn&#039;t have permission to access this resource&quot;
    &#125;
&#125;\n```

**404**

Not Found - Phone Number ID does not exist or is not accessible

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;WhatsApp Business Profile not found&quot;,
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
        &quot;message&quot;: &quot;The requested fields are not available for this profile&quot;,
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


&lt;jumplink id=&quot;post-version-phone-number-id-whatsapp-business-profile&quot;&gt;&lt;/jumplink&gt;
## POST /&#123;Version&#125;/&#123;Phone-Number-ID&#125;/whatsapp_business_profile

Update WhatsApp Business Profile

Update WhatsApp Business Profile information including business details,
contact information, and profile settings.


**Use Cases:**
- Update business description and contact information
- Modify business address and website information
- Change business vertical classification
- Update profile picture using Resumable Upload API
- Update profile picture and about section


**Rate Limiting:**
Standard Graph API rate limits apply. Use appropriate retry logic with exponential backoff.


**Profile Picture Updates:**
To update the profile picture, first use the Resumable Upload API to obtain a
profile_picture_handle, then include it in the request.


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
| Phone-Number-ID | string | ✓ | Your WhatsApp Business phone number ID. This ID represents the phone number status entity and can be obtained from your WhatsApp Business Account phone numbers list. |

### Request Body (Required)

**Content Type**: `application/json`

**Schema**: [WhatsAppBusinessProfileUpdateRequest](#whatsappbusinessprofileupdaterequest)

### Responses

**200**

Successfully updated WhatsApp Business Profile

**Content Type**: `application/json`

**Schema**: [WhatsAppBusinessProfileUpdateResponse](#whatsappbusinessprofileupdateresponse)

**400**

Bad Request - Invalid parameters or malformed request

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;Invalid parameter: email must be a valid email address&quot;,
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
        &quot;message&quot;: &quot;Your app doesn&#039;t have permission to modify this WhatsApp Business Profile&quot;,
        &quot;type&quot;: &quot;OAuthException&quot;,
        &quot;code&quot;: 200,
        &quot;error_subcode&quot;: 1349174,
        &quot;fbtrace_id&quot;: &quot;AXsgnV2Cm3ZMGF3dF_cfYIn&quot;,
        &quot;error_user_title&quot;: &quot;Permission Denied&quot;,
        &quot;error_user_msg&quot;: &quot;Your app doesn&#039;t have permission to access this resource&quot;
    &#125;
&#125;\n```

**404**

Not Found - Phone Number ID does not exist or is not accessible

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;WhatsApp Business Profile not found&quot;,
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
        &quot;message&quot;: &quot;The profile picture handle is invalid or expired&quot;,
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

&lt;jumplink id=&quot;whatsappbusinessprofile&quot;&gt;&lt;/jumplink&gt;
### WhatsAppBusinessProfile

WhatsApp Business Profile information and settings

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| messaging_product | &quot;whatsapp&quot; | ✓ | The messaging service used for the request |
| about | string |  | The text to display in business profile&#039;s About section |
| address | string |  | The address of the business |
| description | string |  | Description of the business |
| email | string (email) |  | The contact email address of the business |
| profile_picture_url | string (uri) |  | URL of the business profile picture |
| websites | array of string (uri) |  | URLs associated with the business |
| vertical | [WhatsAppBusinessVertical](#whatsappbusinessvertical) |  |  |

&lt;jumplink id=&quot;whatsappbusinessprofileupdaterequest&quot;&gt;&lt;/jumplink&gt;
### WhatsAppBusinessProfileUpdateRequest

Request payload for updating WhatsApp Business Profile

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| messaging_product | &quot;whatsapp&quot; | ✓ | The messaging service used for the request |
| about | string |  | The text to display in business profile&#039;s About section |
| address | string |  | The address of the business |
| description | string |  | Description of the business |
| email | string (email) |  | The contact email address of the business |
| profile_picture_handle | string |  | The handle of the profile picture generated from Resumable Upload API |
| websites | array of string (uri) |  | URLs associated with the business |
| vertical | [WhatsAppBusinessVertical](#whatsappbusinessvertical) |  |  |

&lt;jumplink id=&quot;whatsappbusinessvertical&quot;&gt;&lt;/jumplink&gt;
### WhatsAppBusinessVertical

The industry type of the business

**Type**: string

**Enum Values**: &quot;OTHER&quot;, &quot;AUTO&quot;, &quot;BEAUTY&quot;, &quot;APPAREL&quot;, &quot;EDU&quot;, &quot;ENTERTAIN&quot;, &quot;EVENT_PLAN&quot;, &quot;FINANCE&quot;, &quot;GROCERY&quot;, &quot;GOVT&quot;, &quot;HOTEL&quot;, &quot;HEALTH&quot;, &quot;NONPROFIT&quot;, &quot;PROF_SERVICES&quot;, &quot;RETAIL&quot;, &quot;TRAVEL&quot;, &quot;RESTAURANT&quot;, &quot;ALCOHOL&quot;, &quot;ONLINE_GAMBLING&quot;, &quot;PHYSICAL_GAMBLING&quot;, &quot;OTC_DRUGS&quot;

&lt;jumplink id=&quot;whatsappbusinessprofileresponse&quot;&gt;&lt;/jumplink&gt;
### WhatsAppBusinessProfileResponse

Response containing business profile information

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| data | array of [Data](#object-data-1) |  |  |

&lt;jumplink id=&quot;whatsappbusinessprofileupdateresponse&quot;&gt;&lt;/jumplink&gt;
### WhatsAppBusinessProfileUpdateResponse

Response after updating business profile

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| success | boolean |  | Indicates whether the update was successful |

&lt;jumplink id=&quot;graphapierror&quot;&gt;&lt;/jumplink&gt;
### GraphAPIError

Standard Graph API error response

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| error | [Error](#object-error-2) | ✓ |  |

## Inline Object Definitions

&lt;jumplink id=&quot;object-data-1&quot;&gt;&lt;/jumplink&gt;
### Data

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| business_profile | [WhatsAppBusinessProfile](#whatsappbusinessprofile) |  |  |

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
