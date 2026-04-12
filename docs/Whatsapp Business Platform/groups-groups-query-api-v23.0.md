

## Base URL

| URL | Description |
|-----|-------------|
| https://graph.facebook.com | WhatsApp Business Cloud API |

## APIs

| Method | Endpoint |
|--------|----------|
| DELETE | [/&#123;Version&#125;/&#123;group_id&#125;](#delete-version-group-id) |
| GET | [/&#123;Version&#125;/&#123;group_id&#125;](#get-version-group-id) |
| POST | [/&#123;Version&#125;/&#123;group_id&#125;](#post-version-group-id) |

&lt;jumplink id=&quot;delete-version-group-id&quot;&gt;&lt;/jumplink&gt;
## DELETE /&#123;Version&#125;/&#123;group_id&#125;

Delete Group

Delete the group and remove all participants, including the business

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

### Responses

**200**

Group deletion successful

**Content Type**: `application/json`

**Schema**: object

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| success | boolean |  |  |


&lt;jumplink id=&quot;get-version-group-id&quot;&gt;&lt;/jumplink&gt;
## GET /&#123;Version&#125;/&#123;group_id&#125;

Get Group Info

Retrieve metadata about a single group

### Header Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| User-Agent | string |  | The user agent string identifying the client software making the request. |
| Authorization | string | ✓ | Bearer token for API authentication. This should be a valid access token obtained through the appropriate OAuth flow or system user token. |

### Path Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| Version | string | ✓ |  |
| group_id | string | ✓ | Group ID |

### Query Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| fields | string |  | Comma-separated list of fields to return |

### Responses

**200**

Group information

**Content Type**: `application/json`

**Schema**: [GroupInfo](#groupinfo)


&lt;jumplink id=&quot;post-version-group-id&quot;&gt;&lt;/jumplink&gt;
## POST /&#123;Version&#125;/&#123;group_id&#125;

Update Group Settings

Update the subject, description, and photo of a group

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
| subject | string |  | The new subject for the group |
| description | string |  | The new description for the group |
| profile_picture_file | string |  | Path to an image file for group profile picture |

**Content Type**: `multipart/form-data`

**Schema**: object

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| messaging_product | &quot;whatsapp&quot; |  |  |
| file | string (binary) |  | Image file for group profile picture (JPEG, max 5MB, square format, min 192x192) |

### Responses

**200**

Group settings updated successfully


# Components

## Schemas

&lt;jumplink id=&quot;groupinfo&quot;&gt;&lt;/jumplink&gt;
### GroupInfo

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| id | string |  | Group ID |
| messaging_product | string |  |  |
| join_approval_mode | One of &quot;approval_required&quot;, &quot;auto_approve&quot; |  | Join approval mode for the group |
| subject | string |  | Group subject |
| description | string |  | Group description |
| suspended | boolean |  | Returns true if the group has been suspended by WhatsApp |
| creation_timestamp | integer |  | UNIX timestamp in seconds at which the group was created |
| participants | array of [Participants](#object-participants-1) |  | List of participants in the group |
| total_participant_count | integer |  | Total number of participants in the group, excluding your business |

## Inline Object Definitions

&lt;jumplink id=&quot;object-participants-1&quot;&gt;&lt;/jumplink&gt;
### Participants

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| wa_id | string |  | WhatsApp user ID |

## Authentication

| Scheme | Type | Location |
|--------|------|----------|
| bearerAuth | HTTP Bearer | Header: `Authorization` |

### Usage Examples

- **bearerAuth**: Include `Authorization: Bearer your-token-here` in request headers

### Global Authentication Requirements

All endpoints require: bearerAuth
