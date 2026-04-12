

## Base URL

| URL | Description |
|-----|-------------|
| https://graph.facebook.com |  |

## APIs

| Method | Endpoint |
|--------|----------|
| DELETE | [/&#123;Version&#125;/&#123;Media-ID&#125;](#delete-version-media-id) |
| GET | [/&#123;Version&#125;/&#123;Media-ID&#125;](#get-version-media-id) |

&lt;jumplink id=&quot;delete-version-media-id&quot;&gt;&lt;/jumplink&gt;
## DELETE /&#123;Version&#125;/&#123;Media-ID&#125;

Delete Media

To delete media, make a **DELETE** call to the ID of the media you want to delete.

## Prerequisites
- [User Access Token](https://developers.facebook.com/docs/facebook-login/access-tokens#usertokens) with **`whatsapp_business_messaging`** permission
- Media object ID from either uploading media endpoint or media message Webhooks

### Header Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| User-Agent | string |  | The user agent string identifying the client software making the request. |
| Authorization | string | ✓ | Bearer token for API authentication. This should be a valid access token obtained through the appropriate OAuth flow or system user token. |
| Content-Type | One of &quot;application/json&quot;, &quot;application/x-www-form-urlencoded&quot;, &quot;multipart/form-data&quot; | ✓ | Media type of the request body |

### Query Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| phone_number_id | string |  | Specifies that deletion of the media only be performed if the media belongs to the provided phone number. |

### Responses

**200**

Delete Media

**Content Type**: `application/json`

**Schema**: object

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| success | boolean |  |  |


&lt;jumplink id=&quot;get-version-media-id&quot;&gt;&lt;/jumplink&gt;
## GET /&#123;Version&#125;/&#123;Media-ID&#125;

Retrieve Media URL

To retrieve your media’s URL, make a **GET** call to **`/&#123;&#123;Media-ID&#125;&#125;`**. Use the returned URL to download the media file. Note that clicking this URL (i.e. performing a generic GET) will not return the media; you must include an access token. For more information, see [Download Media](https://developers.facebook.com/docs/business-messaging/whatsapp/business-phone-numbers/media#download-media).

You can also use the optional query **`?phone_number_id`** for **`Retrieve Media URL`** and **`Delete Media`**. This parameter checks to make sure the media belongs to the phone number before retrieval or deletion.

#### Response

A successful response includes an object with a media URL. The URL is only valid for 5 minutes. To use this URL, see [Download Media](https://developers.facebook.com/docs/business-messaging/whatsapp/business-phone-numbers/media#download-media).

### Header Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| User-Agent | string |  | The user agent string identifying the client software making the request. |
| Authorization | string | ✓ | Bearer token for API authentication. This should be a valid access token obtained through the appropriate OAuth flow or system user token. |

### Query Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| phone_number_id | string |  | Specifies that this action only be performed if the media belongs to the provided phone number. |

### Responses

**200**

Retrieve Media URL

**Content Type**: `application/json`

**Schema**: object

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| file_size | string |  |  |
| id | string |  |  |
| messaging_product | string |  |  |
| mime_type | string |  |  |
| sha256 | string |  |  |
| url | string |  |  |


## Authentication

| Scheme | Type | Location |
|--------|------|----------|
| bearerAuth | HTTP Bearer | Header: `Authorization` |

### Usage Examples

- **bearerAuth**: Include `Authorization: Bearer your-token-here` in request headers

### Global Authentication Requirements

All endpoints require: bearerAuth
