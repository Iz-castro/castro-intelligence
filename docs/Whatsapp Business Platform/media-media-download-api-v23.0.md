

## Base URL

| URL | Description |
|-----|-------------|
| https://graph.facebook.com |  |

## APIs

| Method | Endpoint |
|--------|----------|
| GET | [/&#123;Version&#125;/&#123;Media-URL&#125;](#get-version-media-url) |

&lt;jumplink id=&quot;get-version-media-url&quot;&gt;&lt;/jumplink&gt;
## GET /&#123;Version&#125;/&#123;Media-URL&#125;

Download Media

Download media files using URLs obtained from media retrieval endpoints.
Requires User Access Token with whatsapp_business_messaging permission.
Media URLs expire after 5 minutes and must be re-retrieved if expired.
Returns binary content with appropriate MIME type headers.


### Responses

**200**

Download Media

**Content Type**: `text/plain`


## Authentication

| Scheme | Type | Location |
|--------|------|----------|
| bearerAuth | HTTP Bearer | Header: `Authorization` |

### Usage Examples

- **bearerAuth**: Include `Authorization: Bearer your-token-here` in request headers

### Global Authentication Requirements

All endpoints require: bearerAuth
