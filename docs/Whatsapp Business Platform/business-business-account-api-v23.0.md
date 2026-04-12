

## Base URL

| URL | Description |
|-----|-------------|
| https://graph.facebook.com |  |

## APIs

| Method | Endpoint |
|--------|----------|
| GET | [/&#123;Version&#125;/&#123;Business-ID&#125;](#get-version-business-id) |

&lt;jumplink id=&quot;get-version-business-id&quot;&gt;&lt;/jumplink&gt;
## GET /&#123;Version&#125;/&#123;Business-ID&#125;

Get Business Portfolio (Specific Fields)

Endpoint reference: [Business](https://developers.facebook.com/docs/marketing-api/reference/business/)

### Header Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| User-Agent | string |  | The user agent string identifying the client software making the request. |
| Authorization | string | ✓ | Bearer token for API authentication. This should be a valid access token obtained through the appropriate OAuth flow or system user token. |

### Query Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| fields | string |  |  |

### Responses

**200**

Example response

**Content Type**: `application/json`

**Schema**: object

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| id | string |  |  |
| name | string |  |  |
| timezone_id | number |  |  |


## Authentication

| Scheme | Type | Location |
|--------|------|----------|
| bearerAuth | HTTP Bearer | Header: `Authorization` |

### Usage Examples

- **bearerAuth**: Include `Authorization: Bearer your-token-here` in request headers

### Global Authentication Requirements

All endpoints require: bearerAuth
