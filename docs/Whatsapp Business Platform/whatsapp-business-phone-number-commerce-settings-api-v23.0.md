

## Base URL

| URL | Description |
|-----|-------------|
| https://graph.facebook.com |  |

## APIs

| Method | Endpoint |
|--------|----------|
| GET | [/&#123;Version&#125;/&#123;Phone-Number-ID&#125;/whatsapp_commerce_settings](#get-version-phone-number-id-whatsapp-commerce-settings) |
| POST | [/&#123;Version&#125;/&#123;Phone-Number-ID&#125;/whatsapp_commerce_settings](#post-version-phone-number-id-whatsapp-commerce-settings) |

&lt;jumplink id=&quot;get-version-phone-number-id-whatsapp-commerce-settings&quot;&gt;&lt;/jumplink&gt;
## GET /&#123;Version&#125;/&#123;Phone-Number-ID&#125;/whatsapp_commerce_settings

Get commerce settings

- Guide: [Sell Products &amp; Services](https://developers.facebook.com/docs/business-messaging/whatsapp/catalogs/sell-products-and-services) (Cloud API)
- Guide: [Sell Products &amp; Services](https://developers.facebook.com/docs/whatsapp/on-premises/guides/commerce-guides) (On-Premises API)
- Endpoint reference: [WhatsApp Business Phone Number &amp;gt; WhatsApp Commerce Settings](https://developers.facebook.com/docs/graph-api/reference/whats-app-business-account-to-number-current-status/whatsapp_commerce_settings)

### Responses

**200**

Example response

**Content Type**: `application/json`

**Schema**: object

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| data | array of [Data](#object-data-1) |  |  |


&lt;jumplink id=&quot;post-version-phone-number-id-whatsapp-commerce-settings&quot;&gt;&lt;/jumplink&gt;
## POST /&#123;Version&#125;/&#123;Phone-Number-ID&#125;/whatsapp_commerce_settings

Set or update commerce settings

- Guide: [Sell Products &amp; Services](https://developers.facebook.com/docs/business-messaging/whatsapp/catalogs/sell-products-and-services) (Cloud API)
- Guide: [Sell Products &amp; Services](https://developers.facebook.com/docs/whatsapp/on-premises/guides/commerce-guides) (On-Premises API)
- Endpoint reference: [WhatsApp Business Phone Number &amp;gt; WhatsApp Commerce Settings](https://developers.facebook.com/docs/graph-api/reference/whats-app-business-account-to-number-current-status/whatsapp_commerce_settings)

### Header Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| User-Agent | string |  | The user agent string identifying the client software making the request. |
| Authorization | string | ✓ | Bearer token for API authentication. This should be a valid access token obtained through the appropriate OAuth flow or system user token. |

### Query Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| is_cart_enabled | string |  |  |
| is_catalog_visible | string |  |  |

### Responses

**200**

Example response

**Content Type**: `application/json`

**Schema**: object

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| success | boolean |  |  |


# Components

## Inline Object Definitions

&lt;jumplink id=&quot;object-data-1&quot;&gt;&lt;/jumplink&gt;
### Data

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| id | string |  |  |
| is_cart_enabled | boolean |  |  |
| is_catalog_visible | boolean |  |  |

## Authentication

| Scheme | Type | Location |
|--------|------|----------|
| bearerAuth | HTTP Bearer | Header: `Authorization` |

### Usage Examples

- **bearerAuth**: Include `Authorization: Bearer your-token-here` in request headers

### Global Authentication Requirements

All endpoints require: bearerAuth
