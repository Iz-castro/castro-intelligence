

## Base URL

| URL | Description |
|-----|-------------|
| https://graph.facebook.com | WhatsApp Business Cloud API |

## APIs

| Method | Endpoint |
|--------|----------|
| DELETE | [/&#123;Version&#125;/&#123;group_id&#125;/participants](#delete-version-group-id-participants) |
| POST | [/&#123;Version&#125;/&#123;group_id&#125;/participants](#post-version-group-id-participants) |

&lt;jumplink id=&quot;delete-version-group-id-participants&quot;&gt;&lt;/jumplink&gt;
## DELETE /&#123;Version&#125;/&#123;group_id&#125;/participants

Remove Group Participants

Remove participants from group

### Header Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| User-Agent | string |  | The user agent string identifying the client software making the request. |
| Authorization | string | ✓ | Bearer token for API authentication. This should be a valid access token obtained through the appropriate OAuth flow or system user token. |
| Content-Type | One of &quot;application/json&quot;, &quot;application/x-www-form-urlencoded&quot;, &quot;multipart/form-data&quot; | ✓ | Media type of the request body |

### Path Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| Version | string | ✓ |  |
| group_id | string | ✓ | Group ID |

### Request Body (Required)

**Content Type**: `application/json`

**Schema**: object

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| messaging_product | &quot;whatsapp&quot; | ✓ |  |
| participants | array of [Participants](#object-participants-1) | ✓ | Array of phone numbers or WhatsApp IDs to remove (max 8 participants) |

### Responses

**200**

Participants removal request processed


&lt;jumplink id=&quot;post-version-group-id-participants&quot;&gt;&lt;/jumplink&gt;
## POST /&#123;Version&#125;/&#123;group_id&#125;/participants

Add Group Participants

Add participants to group

### Header Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| User-Agent | string |  | The user agent string identifying the client software making the request. |
| Authorization | string | ✓ | Bearer token for API authentication. This should be a valid access token obtained through the appropriate OAuth flow or system user token. |
| Content-Type | One of &quot;application/json&quot;, &quot;application/x-www-form-urlencoded&quot;, &quot;multipart/form-data&quot; | ✓ | Media type of the request body |

### Path Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| Version | string | ✓ |  |
| group_id | string | ✓ | Group ID |

### Request Body (Required)

**Content Type**: `application/json`

**Schema**: object

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| messaging_product | &quot;whatsapp&quot; | ✓ |  |
| participants | array of [Participants](#object-participants-1) | ✓ | Array of phone numbers or WhatsApp IDs to remove (max 8 participants) |

### Responses

**200**

Participants addition request processed


# Components

## Inline Object Definitions

&lt;jumplink id=&quot;object-participants-1&quot;&gt;&lt;/jumplink&gt;
### Participants

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| user | string | ✓ | WhatsApp user phone number or WhatsApp user ID |

## Authentication

| Scheme | Type | Location |
|--------|------|----------|
| bearerAuth | HTTP Bearer | Header: `Authorization` |

### Usage Examples

- **bearerAuth**: Include `Authorization: Bearer your-token-here` in request headers

### Global Authentication Requirements

All endpoints require: bearerAuth
