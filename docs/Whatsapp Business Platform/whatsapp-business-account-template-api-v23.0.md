

## Base URL

| URL | Description |
|-----|-------------|
| https://graph.facebook.com |  |

## APIs

| Method | Endpoint |
|--------|----------|
| DELETE | [/&#123;Version&#125;/&#123;WABA-ID&#125;/message_templates](#delete-version-waba-id-message-templates) |
| GET | [/&#123;Version&#125;/&#123;TEMPLATE_ID&#125;](#get-version-template-id) |
| GET | [/&#123;Version&#125;/&#123;WABA-ID&#125;/message_templates](#get-version-waba-id-message-templates) |
| POST | [/&#123;Version&#125;/&#123;TEMPLATE_ID&#125;](#post-version-template-id) |
| POST | [/&#123;Version&#125;/&#123;WABA-ID&#125;/message_templates](#post-version-waba-id-message-templates) |

&lt;jumplink id=&quot;delete-version-waba-id-message-templates&quot;&gt;&lt;/jumplink&gt;
## DELETE /&#123;Version&#125;/&#123;WABA-ID&#125;/message_templates

Delete template by name

- Guide: [Message Templates](https://developers.facebook.com/docs/business-messaging/whatsapp/templates/overview)
- Guide: [How To Monitor Quality Signals](https://developers.facebook.com/docs/whatsapp/guides/how-to-monitor-quality-signals)
- Endpoint reference: [WhatsApp Business Account &amp;gt; Message Templates](https://developers.facebook.com/docs/graph-api/reference/whats-app-business-account/message_templates/)

### Header Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| User-Agent | string |  | The user agent string identifying the client software making the request. |
| Authorization | string | ✓ | Bearer token for API authentication. This should be a valid access token obtained through the appropriate OAuth flow or system user token. |

### Query Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| name | string |  |  |
| hsm_id | string |  | Template ID |

### Responses

**200**

Example response / Example response

**Content Type**: `application/json`

**Schema**: object

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| success | boolean |  |  |


&lt;jumplink id=&quot;get-version-template-id&quot;&gt;&lt;/jumplink&gt;
## GET /&#123;Version&#125;/&#123;TEMPLATE_ID&#125;

Get template by ID (default fields)

- Guide: [Message Templates](https://developers.facebook.com/docs/business-messaging/whatsapp/templates/overview)
- Guide: [How To Monitor Quality Signals](https://developers.facebook.com/docs/whatsapp/guides/how-to-monitor-quality-signals)
- Endpoint reference: [WhatsApp Message Template](https://developers.facebook.com/docs/graph-api/reference/whats-app-business-hsm/)

### Responses

**200**

Example response

**Content Type**: `application/json`

**Schema**: object

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| category | string |  |  |
| components | array of [Components](#object-components-3) |  |  |
| id | string |  |  |
| language | string |  |  |
| name | string |  |  |
| status | string |  |  |


&lt;jumplink id=&quot;get-version-waba-id-message-templates&quot;&gt;&lt;/jumplink&gt;
## GET /&#123;Version&#125;/&#123;WABA-ID&#125;/message_templates

Get template by name (default fields)

- Guide: [Message Templates](https://developers.facebook.com/docs/business-messaging/whatsapp/templates/overview)
- Guide: [How To Monitor Quality Signals](https://developers.facebook.com/docs/whatsapp/guides/how-to-monitor-quality-signals)
- Endpoint reference: [WhatsApp Business Account &amp;gt; Message Templates](https://developers.facebook.com/docs/graph-api/reference/whats-app-business-account/message_templates/)

### Header Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| User-Agent | string |  | The user agent string identifying the client software making the request. |
| Authorization | string | ✓ | Bearer token for API authentication. This should be a valid access token obtained through the appropriate OAuth flow or system user token. |

### Query Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| name | string |  |  |

### Responses

**200**

Example response / Example response

**Content Type**: `application/json`

**Schema**: object

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| data | array of [Data](#object-data-4) |  |  |
| paging | [Paging](#object-paging-6) |  |  |


&lt;jumplink id=&quot;post-version-template-id&quot;&gt;&lt;/jumplink&gt;
## POST /&#123;Version&#125;/&#123;TEMPLATE_ID&#125;

Edit template

- Guide: [Message Templates](https://developers.facebook.com/docs/business-messaging/whatsapp/templates/overview)
- Guide: [How To Monitor Quality Signals](https://developers.facebook.com/docs/whatsapp/guides/how-to-monitor-quality-signals)
- Endpoint reference: [WhatsApp Message Template](https://developers.facebook.com/docs/graph-api/reference/whats-app-business-hsm/)

### Request Body (Optional)

**Content Type**: `application/json`

**Schema**: object

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| category | string |  |  |
| components | array of [Components](#object-components-3) |  |  |
| language | string |  |  |
| name | string |  |  |

### Responses

**200**

Example response

**Content Type**: `application/json`

**Schema**: object

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| success | boolean |  |  |


&lt;jumplink id=&quot;post-version-waba-id-message-templates&quot;&gt;&lt;/jumplink&gt;
## POST /&#123;Version&#125;/&#123;WABA-ID&#125;/message_templates

Create authentication template w/ OTP copy code button

- Guide: [Authentication Templates with OTP Buttons](https://developers.facebook.com/docs/business-messaging/whatsapp/templates/authentication-templates/authentication-templates)
- Guide: [Message Templates](https://developers.facebook.com/docs/business-messaging/whatsapp/templates/overview)
- Guide: [How To Monitor Quality Signals](https://developers.facebook.com/docs/whatsapp/guides/how-to-monitor-quality-signals)
- Endpoint reference: [WhatsApp Business Account &amp;gt; Message Templates](https://developers.facebook.com/docs/graph-api/reference/whats-app-business-account/message_templates/)

### Request Body (Optional)

**Content Type**: `application/json`

**Schema**: object

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| category | string |  |  |
| components | array of [Components](#object-components-8) |  |  |
| language | string |  |  |
| name | string |  |  |

### Responses

**200**

Example response / Example response / Example response / Example response / Example response / Example response / Example response / Example response / Create Flow Template Message by Name / Create Flow Template Message by Flow JSON / Create Flow Template Message by ID

**Content Type**: `application/json`

**Schema**: object

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| category | string |  |  |
| id | string |  |  |
| status | string |  |  |


# Components

## Inline Object Definitions

&lt;jumplink id=&quot;object-buttons-1&quot;&gt;&lt;/jumplink&gt;
### Buttons

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| text | string |  |  |
| type | string |  |  |

&lt;jumplink id=&quot;object-example-2&quot;&gt;&lt;/jumplink&gt;
### Example

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| body_text | array of array of string |  |  |

&lt;jumplink id=&quot;object-components-3&quot;&gt;&lt;/jumplink&gt;
### Components

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| buttons | array of [Buttons](#object-buttons-1) |  |  |
| example | [Example](#object-example-2) |  |  |
| format | string |  |  |
| text | string |  |  |
| type | string |  |  |

&lt;jumplink id=&quot;object-data-4&quot;&gt;&lt;/jumplink&gt;
### Data

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| category | string |  |  |
| components | array of [Components](#object-components-3) |  |  |
| id | string |  |  |
| language | string |  |  |
| name | string |  |  |
| status | string |  |  |

&lt;jumplink id=&quot;object-cursors-5&quot;&gt;&lt;/jumplink&gt;
### Cursors

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| after | string |  |  |
| before | string |  |  |

&lt;jumplink id=&quot;object-paging-6&quot;&gt;&lt;/jumplink&gt;
### Paging

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| cursors | [Cursors](#object-cursors-5) |  |  |

&lt;jumplink id=&quot;object-buttons-7&quot;&gt;&lt;/jumplink&gt;
### Buttons

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| flow_action | string |  |  |
| flow_id | string |  |  |
| navigate_screen | string |  |  |
| text | string |  |  |
| type | string |  |  |

&lt;jumplink id=&quot;object-components-8&quot;&gt;&lt;/jumplink&gt;
### Components

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| buttons | array of [Buttons](#object-buttons-7) |  |  |
| text | string |  |  |
| type | string |  |  |

## Authentication

| Scheme | Type | Location |
|--------|------|----------|
| bearerAuth | HTTP Bearer | Header: `Authorization` |

### Usage Examples

- **bearerAuth**: Include `Authorization: Bearer your-token-here` in request headers

### Global Authentication Requirements

All endpoints require: bearerAuth
