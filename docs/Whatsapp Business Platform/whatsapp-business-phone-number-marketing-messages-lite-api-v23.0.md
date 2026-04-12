

## Base URL

| URL | Description |
|-----|-------------|
| https://graph.facebook.com |  |

## APIs

| Method | Endpoint |
|--------|----------|
| POST | [/&#123;Version&#125;/&#123;Phone-Number-ID&#125;/marketing_messages](#post-version-phone-number-id-marketing-messages) |

&lt;jumplink id=&quot;post-version-phone-number-id-marketing-messages&quot;&gt;&lt;/jumplink&gt;
## POST /&#123;Version&#125;/&#123;Phone-Number-ID&#125;/marketing_messages

Send Marketing Template Message

Send marketing template messages using pre-approved templates. Supports optional product policy controls and message activity sharing settings.

### Header Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| User-Agent | string |  | The user agent string identifying the client software making the request. |
| Authorization | string | ✓ | Bearer token for API authentication. This should be a valid access token obtained through the appropriate OAuth flow or system user token. |
| Content-Type | One of &quot;application/json&quot;, &quot;application/x-www-form-urlencoded&quot;, &quot;multipart/form-data&quot; | ✓ | Media type of the request body |

### Path Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| Version | string | ✓ | WhatsApp API version (e.g., v20.0) |
| Phone-Number-ID | string | ✓ | WhatsApp Business Phone Number ID |

### Request Body (Required)

**Content Type**: `application/json`

**Schema**: [MarketingMessageRequestPayload](#marketingmessagerequestpayload)

### Responses

**200**

Marketing message sent successfully

**Content Type**: `application/json`

**Schema**: [MarketingMessageResponsePayload](#marketingmessageresponsepayload)

**400**

Bad Request - Invalid request parameters

**Content Type**: `application/json`

**Schema**: [ErrorResponse](#errorresponse)

**401**

Unauthorized - Invalid or missing access token

**Content Type**: `application/json`

**Schema**: [ErrorResponse](#errorresponse)

**403**

Forbidden - Template not approved or insufficient permissions

**Content Type**: `application/json`

**Schema**: [ErrorResponse](#errorresponse)


# Components

## Schemas

&lt;jumplink id=&quot;marketingmessagerequestpayload&quot;&gt;&lt;/jumplink&gt;
### MarketingMessageRequestPayload

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| messaging_product | &quot;whatsapp&quot; | ✓ | Messaging service used. Must be &quot;whatsapp&quot; |
| recipient_type | &quot;individual&quot; | ✓ | Type of recipient. Must be &quot;individual&quot; |
| to | string | ✓ | WhatsApp ID or phone number of the message recipient |
| type | &quot;template&quot; | ✓ | Type of message. Must be &quot;template&quot; for marketing messages |
| template | [Template](#object-template-1) | ✓ |  |
| product_policy | One of &quot;CLOUD_API_FALLBACK&quot;, &quot;STRICT&quot; |  | Optional product policy setting |
| message_activity_sharing | boolean |  | Optional flag to control message activity sharing |

**Additional Properties**: Not allowed

&lt;jumplink id=&quot;marketingmessageresponsepayload&quot;&gt;&lt;/jumplink&gt;
### MarketingMessageResponsePayload

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| contacts | array of [Contacts](#object-contacts-2) |  |  |
| messages | array of [Messages](#object-messages-3) |  |  |
| messaging_product | string |  |  |

## Inline Object Definitions

&lt;jumplink id=&quot;object-template-1&quot;&gt;&lt;/jumplink&gt;
### Template

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| name | string | ✓ | Name of the template. |
| language | [LanguageObject](#languageobject) | ✓ | Contains a `language` object. Specifies the language the template may be rendered in |
| components | array of [TemplateComponent](#templatecomponent) |  | Array of `components` objects containing the parameters of the message. |

&lt;jumplink id=&quot;object-contacts-2&quot;&gt;&lt;/jumplink&gt;
### Contacts

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| input | string |  |  |
| wa_id | string |  |  |

&lt;jumplink id=&quot;object-messages-3&quot;&gt;&lt;/jumplink&gt;
### Messages

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| id | string |  |  |
| message_status | One of &quot;accepted&quot;, &quot;held_for_quality_assessment&quot;, &quot;paused&quot; |  | The status of a WhatsApp message: - `accepted`: The message has been accepted by WhatsApp and is being processed - `held_for_quality_assessment`: The message is being held for quality assessment before delivery - `paused`: The message delivery has been paused |

## Authentication

| Scheme | Type | Location |
|--------|------|----------|
| bearerAuth | HTTP Bearer | Header: `Authorization` |

### Usage Examples

- **bearerAuth**: Include `Authorization: Bearer your-token-here` in request headers

### Global Authentication Requirements

All endpoints require: bearerAuth
