

## Base URL

| URL | Description |
|-----|-------------|
| https://graph.facebook.com |  |

## APIs

| Method | Endpoint |
|--------|----------|
| DELETE | [/&#123;Version&#125;/&#123;Phone-Number-ID&#125;/block_users](#delete-version-phone-number-id-block-users) |
| GET | [/&#123;Version&#125;/&#123;Phone-Number-ID&#125;/block_users](#get-version-phone-number-id-block-users) |
| POST | [/&#123;Version&#125;/&#123;Phone-Number-ID&#125;/block_users](#post-version-phone-number-id-block-users) |

&lt;jumplink id=&quot;delete-version-phone-number-id-block-users&quot;&gt;&lt;/jumplink&gt;
## DELETE /&#123;Version&#125;/&#123;Phone-Number-ID&#125;/block_users

Unblock user(s)

- Guide: [Block Users](https://developers.facebook.com/docs/business-messaging/whatsapp/block-users)\n    \n- Endpoint reference: [DELETE WhatsApp Buiness Phone Number &amp;gt; block_users](https://developers.facebook.com/docs/graph-api/reference/whats-app-business-account-to-number-current-status/block_users/#Deleting)

### Header Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| User-Agent | string |  | The user agent string identifying the client software making the request. |
| Authorization | string | ✓ | Bearer token for API authentication. This should be a valid access token obtained through the appropriate OAuth flow or system user token. |
| Content-Type | One of &quot;application/json&quot;, &quot;application/x-www-form-urlencoded&quot;, &quot;multipart/form-data&quot; | ✓ | Media type of the request body |

### Request Body (Optional)

**Content Type**: `application/json`

**Schema**: object

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| block_users | array of [Block_users](#object-block_users-1) |  |  |
| messaging_product | string |  |  |

### Responses

**200**

Unblock user(s)

**Content Type**: `application/json`

**Schema**: [UnblockUsersData](#unblockusersdata)


&lt;jumplink id=&quot;get-version-phone-number-id-block-users&quot;&gt;&lt;/jumplink&gt;
## GET /&#123;Version&#125;/&#123;Phone-Number-ID&#125;/block_users

Get blocked users

- Guide: [Block Users](https://developers.facebook.com/docs/business-messaging/whatsapp/block-users)\n    \n- Endpoint reference: [GET WhatsApp Buiness Phone Number &amp;gt; block_users](https://developers.facebook.com/docs/graph-api/reference/whats-app-business-account-to-number-current-status/block_users/#Reading)

### Header Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| User-Agent | string |  | The user agent string identifying the client software making the request. |
| Authorization | string | ✓ | Bearer token for API authentication. This should be a valid access token obtained through the appropriate OAuth flow or system user token. |
| Content-Type | One of &quot;application/json&quot;, &quot;application/x-www-form-urlencoded&quot;, &quot;multipart/form-data&quot; | ✓ | Media type of the request body |

### Responses

**200**

Get blocked users

**Content Type**: `application/json`

**Schema**: [GetBlockedUsersData](#getblockedusersdata)


&lt;jumplink id=&quot;post-version-phone-number-id-block-users&quot;&gt;&lt;/jumplink&gt;
## POST /&#123;Version&#125;/&#123;Phone-Number-ID&#125;/block_users

Block user(s)

- Guide: [Block Users](https://developers.facebook.com/docs/business-messaging/whatsapp/block-users)\n    \n- Endpoint reference: [POST WhatsApp Buiness Phone Number &amp;gt; block_users](https://developers.facebook.com/docs/graph-api/reference/whats-app-business-account-to-number-current-status/block_users/#Creating)

### Header Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| User-Agent | string |  | The user agent string identifying the client software making the request. |
| Authorization | string | ✓ | Bearer token for API authentication. This should be a valid access token obtained through the appropriate OAuth flow or system user token. |
| Content-Type | One of &quot;application/json&quot;, &quot;application/x-www-form-urlencoded&quot;, &quot;multipart/form-data&quot; | ✓ | Media type of the request body |

### Request Body (Optional)

**Content Type**: `application/json`

**Schema**: object

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| block_users | array of [Block_users](#object-block_users-1) |  |  |
| messaging_product | string |  |  |

### Responses

**200**

Block user(s)

**Content Type**: `application/json`

**Schema**: [BlockUsersData](#blockusersdata)


# Components

## Schemas

&lt;jumplink id=&quot;blockeduser&quot;&gt;&lt;/jumplink&gt;
### BlockedUser

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| messaging_product | string |  |  |
| wa_id | string |  |  |

&lt;jumplink id=&quot;paginationcursors&quot;&gt;&lt;/jumplink&gt;
### PaginationCursors

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| after | string |  |  |
| before | string |  |  |

&lt;jumplink id=&quot;paging&quot;&gt;&lt;/jumplink&gt;
### Paging

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| cursors | [PaginationCursors](#paginationcursors) |  |  |

&lt;jumplink id=&quot;getblockedusersdata&quot;&gt;&lt;/jumplink&gt;
### GetBlockedUsersData

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| data | array of [BlockedUser](#blockeduser) |  |  |
| paging | [Paging](#paging) |  |  |

&lt;jumplink id=&quot;blockeduseroperation&quot;&gt;&lt;/jumplink&gt;
### BlockedUserOperation

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| input | string |  |  |
| wa_id | string |  |  |

&lt;jumplink id=&quot;blockusersresult&quot;&gt;&lt;/jumplink&gt;
### BlockUsersResult

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| added_users | array of [BlockedUserOperation](#blockeduseroperation) |  |  |

&lt;jumplink id=&quot;unblockusersresult&quot;&gt;&lt;/jumplink&gt;
### UnblockUsersResult

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| removed_users | array of [BlockedUserOperation](#blockeduseroperation) |  |  |

&lt;jumplink id=&quot;blockusersdata&quot;&gt;&lt;/jumplink&gt;
### BlockUsersData

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| block_users | [BlockUsersResult](#blockusersresult) |  |  |
| messaging_product | string |  |  |

&lt;jumplink id=&quot;unblockusersdata&quot;&gt;&lt;/jumplink&gt;
### UnblockUsersData

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| block_users | [UnblockUsersResult](#unblockusersresult) |  |  |
| messaging_product | string |  |  |

## Inline Object Definitions

&lt;jumplink id=&quot;object-block_users-1&quot;&gt;&lt;/jumplink&gt;
### Block_users

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| user | string |  |  |

## Authentication

| Scheme | Type | Location |
|--------|------|----------|
| bearerAuth | HTTP Bearer | Header: `Authorization` |

### Usage Examples

- **bearerAuth**: Include `Authorization: Bearer your-token-here` in request headers

### Global Authentication Requirements

All endpoints require: bearerAuth
