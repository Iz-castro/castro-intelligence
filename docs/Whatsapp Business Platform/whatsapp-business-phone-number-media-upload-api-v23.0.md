

## Base URL

| URL | Description |
|-----|-------------|
| https://graph.facebook.com |  |

## APIs

| Method | Endpoint |
|--------|----------|
| POST | [/&#123;Version&#125;/&#123;Phone-Number-ID&#125;/media](#post-version-phone-number-id-media) |

&lt;jumplink id=&quot;post-version-phone-number-id-media&quot;&gt;&lt;/jumplink&gt;
## POST /&#123;Version&#125;/&#123;Phone-Number-ID&#125;/media

Upload Image

This request uploads an image as .jpeg. The parameters are specified as **form-data** in the request **body**.

### Header Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| User-Agent | string |  | The user agent string identifying the client software making the request. |
| Authorization | string | ✓ | Bearer token for API authentication. This should be a valid access token obtained through the appropriate OAuth flow or system user token. |

### Path Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| Version | string | ✓ |  |
| Phone-Number-ID | string | ✓ |  |

### Request Body (Optional)

**Content Type**: `application/json`

**Schema**: object

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| file | string |  |  |
| messaging_product | string |  |  |

**Content Type**: `multipart/form-data`

**Schema**: object

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| file | string (binary) |  |  |
| messaging_product | string |  |  |

### Responses

**200**

Upload Image JSON / Upload Sticker File (form-data) / Upload Sticker File JSON / Upload Audio (form-data) / Upload Audio JSON

**Content Type**: `application/json`

**Schema**: object

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| id | string |  |  |


## Authentication

| Scheme | Type | Location |
|--------|------|----------|
| bearerAuth | HTTP Bearer | Header: `Authorization` |

### Usage Examples

- **bearerAuth**: Include `Authorization: Bearer your-token-here` in request headers

### Global Authentication Requirements

All endpoints require: bearerAuth
