

## Base URL

| URL | Description |
|-----|-------------|
| https://graph.facebook.com |  |

## APIs

| Method | Endpoint |
|--------|----------|
| GET | [/&#123;Version&#125;/&#123;Business-ID&#125;/extendedcredits](#get-version-business-id-extendedcredits) |

&lt;jumplink id=&quot;get-version-business-id-extendedcredits&quot;&gt;&lt;/jumplink&gt;
## GET /&#123;Version&#125;/&#123;Business-ID&#125;/extendedcredits

Get credit lines

- Endpoint reference: [Business &amp;gt; Extendedcredits](https://developers.facebook.com/docs/marketing-api/reference/extended-credit/)

### Responses

**200**

Example response

**Content Type**: `application/json`

**Schema**: object

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| data | array of [Data](#object-data-1) |  |  |


# Components

## Inline Object Definitions

&lt;jumplink id=&quot;object-data-1&quot;&gt;&lt;/jumplink&gt;
### Data

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| id | string |  |  |
| legal_entity_name | string |  |  |

## Authentication

| Scheme | Type | Location |
|--------|------|----------|
| bearerAuth | HTTP Bearer | Header: `Authorization` |

### Usage Examples

- **bearerAuth**: Include `Authorization: Bearer your-token-here` in request headers

### Global Authentication Requirements

All endpoints require: bearerAuth
