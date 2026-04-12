

## Base URL

| URL | Description |
|-----|-------------|
| https://graph.facebook.com | Production Graph API server |

## APIs

| Method | Endpoint |
|--------|----------|
| GET | [/&#123;Version&#125;/&#123;WhatsApp-Business-Profile-ID&#125;](#get-version-whatsapp-business-profile-id) |
| POST | [/&#123;Version&#125;/&#123;WhatsApp-Business-Profile-ID&#125;](#post-version-whatsapp-business-profile-id) |

&lt;jumplink id=&quot;get-version-whatsapp-business-profile-id&quot;&gt;&lt;/jumplink&gt;
## GET /&#123;Version&#125;/&#123;WhatsApp-Business-Profile-ID&#125;

Get WhatsApp Business Profile Details

Retrieve comprehensive details about a WhatsApp Business Profile, including business information,
contact details, and profile configuration.


**Use Cases:**
- Retrieve business profile information and metadata
- Verify profile configuration and contact details
- Check profile status and business information
- Validate profile state before business operations


**Rate Limiting:**
Standard Graph API rate limits apply. Use appropriate retry logic with exponential backoff.


**Caching:**
Profile details can be cached for moderate periods, but business information may change
occasionally. Implement appropriate cache invalidation strategies.


### Header Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| User-Agent | string |  | The user agent string identifying the client software making the request. |
| Authorization | string | ✓ | Bearer token for API authentication. This should be a valid access token obtained through the appropriate OAuth flow or system user token. |

### Path Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| Version | string | ✓ | Graph API version to use for this request. Determines the API behavior and available features. |
| WhatsApp-Business-Profile-ID | string | ✓ | Your WhatsApp Business Profile ID. This ID is provided when the profile is created and can be found in your WhatsApp Business Manager or through business management APIs. |

### Query Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| fields | string |  | Comma-separated list of fields to include in the response. If not specified, default fields will be returned (id and any available profile fields). Available fields: id, account_name, description, email, about, address, vertical, websites, profile_picture_url, messaging_product |

### Responses

**200**

Successfully retrieved WhatsApp Business Profile details

**Content Type**: `application/json`

**Schema**: [WhatsAppBusinessProfileNode](#whatsappbusinessprofilenode)

**400**

Bad Request - Invalid parameters or malformed request

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;Invalid parameter: whatsapp_business_profile_id must be a valid numeric string&quot;,
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

Not Found - WhatsApp Business Profile ID does not exist or is not accessible

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


&lt;jumplink id=&quot;post-version-whatsapp-business-profile-id&quot;&gt;&lt;/jumplink&gt;
## POST /&#123;Version&#125;/&#123;WhatsApp-Business-Profile-ID&#125;

Update WhatsApp Business Profile

Update the WhatsApp Business Profile information such as business description, email, address,
and other profile details. This operation corresponds to the GraphWhatsAppBusinessProfilePost functionality.


**Use Cases:**
- Update business profile information and metadata
- Modify contact details and business description
- Change business vertical classification
- Update website URLs and profile picture
- Maintain current business profile information


**Profile Picture Upload:**
It is recommended to use the Resumable Upload API to obtain an upload ID, then use this
upload ID to obtain the picture handle for the `profile_picture_handle` field.


**Rate Limiting:**
Standard Graph API rate limits apply. Use appropriate retry logic with exponential backoff.


### Header Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| User-Agent | string |  | The user agent string identifying the client software making the request. |
| Authorization | string | ✓ | Bearer token for API authentication. This should be a valid access token obtained through the appropriate OAuth flow or system user token. |

### Path Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| Version | string | ✓ | Graph API version to use for this request. Determines the API behavior and available features. |
| WhatsApp-Business-Profile-ID | string | ✓ | Your WhatsApp Business Profile ID. This ID is provided when the profile is created and can be found in your WhatsApp Business Manager or through business management APIs. |

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
        &quot;message&quot;: &quot;Invalid parameter: messaging_product is required&quot;,
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
        &quot;message&quot;: &quot;Your app doesn&#039;t have permission to update this WhatsApp Business Profile&quot;,
        &quot;type&quot;: &quot;OAuthException&quot;,
        &quot;code&quot;: 200,
        &quot;error_subcode&quot;: 1349174,
        &quot;fbtrace_id&quot;: &quot;AXsgnV2Cm3ZMGF3dF_cfYIn&quot;,
        &quot;error_user_title&quot;: &quot;Permission Denied&quot;,
        &quot;error_user_msg&quot;: &quot;Your app doesn&#039;t have permission to modify this resource&quot;
    &#125;
&#125;\n```

**404**

Not Found - WhatsApp Business Profile ID does not exist or is not accessible

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
        &quot;message&quot;: &quot;The provided profile picture handle is invalid or expired&quot;,
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

&lt;jumplink id=&quot;whatsappbusinessprofilenode&quot;&gt;&lt;/jumplink&gt;
### WhatsAppBusinessProfileNode

WhatsApp Business Profile node details and configuration

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| id | string | ✓ | Unique identifier for the WhatsApp Business Profile |
| account_name | string |  | Name of the business account |
| description | string |  | Business description text |
| email | string (email) |  | Contact email address of the business |
| about | string |  | About section text for the business profile |
| address | string |  | Physical address of the business |
| vertical | [WhatsAppBusinessVertical](#whatsappbusinessvertical) |  |  |
| websites | array of string (uri) |  | List of website URLs associated with the business |
| profile_picture_url | string (uri) |  | URL of the business profile picture |
| profile_picture_handle | string |  | Handle of the profile picture for upload operations |
| messaging_product | &quot;whatsapp&quot; |  | The messaging service used |

&lt;jumplink id=&quot;whatsappbusinessprofileupdaterequest&quot;&gt;&lt;/jumplink&gt;
### WhatsAppBusinessProfileUpdateRequest

Request payload for updating WhatsApp Business Profile information

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| messaging_product | &quot;whatsapp&quot; | ✓ | The messaging service used for the request |
| account_name | string |  | Name of the business account |
| description | string |  | Business description text |
| email | string (email) |  | Contact email address of the business |
| about | string |  | About section text for the business profile |
| address | string |  | Physical address of the business |
| vertical | [WhatsAppBusinessVertical](#whatsappbusinessvertical) |  |  |
| websites | array of string (uri) |  | List of website URLs associated with the business |
| profile_picture_handle | string |  | Handle of the profile picture generated from Resumable Upload API |

&lt;jumplink id=&quot;whatsappbusinessprofileupdateresponse&quot;&gt;&lt;/jumplink&gt;
### WhatsAppBusinessProfileUpdateResponse

Response from updating WhatsApp Business Profile

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| id | string |  | WhatsApp Business Profile ID that was updated |
| success | boolean |  | Indicates if the update was successful |

&lt;jumplink id=&quot;whatsappbusinessvertical&quot;&gt;&lt;/jumplink&gt;
### WhatsAppBusinessVertical

Industry vertical classification for the business

**Type**: string

**Enum Values**: &quot;UNDEFINED&quot;, &quot;OTHER&quot;, &quot;AUTO&quot;, &quot;BEAUTY&quot;, &quot;APPAREL&quot;, &quot;EDU&quot;, &quot;ENTERTAIN&quot;, &quot;EVENT_PLAN&quot;, &quot;FINANCE&quot;, &quot;GROCERY&quot;, &quot;GOVT&quot;, &quot;HOTEL&quot;, &quot;HEALTH&quot;, &quot;NONPROFIT&quot;, &quot;PROF_SERVICES&quot;, &quot;RETAIL&quot;, &quot;TRAVEL&quot;, &quot;RESTAURANT&quot;, &quot;NOT_A_BIZ&quot;

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
