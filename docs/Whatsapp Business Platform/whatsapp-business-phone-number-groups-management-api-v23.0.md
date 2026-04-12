

## Base URL

| URL | Description |
|-----|-------------|
| https://graph.facebook.com | WhatsApp Business Cloud API |

## APIs

| Method | Endpoint |
|--------|----------|
| GET | [/&#123;Version&#125;/&#123;Phone-Number-ID&#125;/groups](#get-version-phone-number-id-groups) |
| POST | [/&#123;Version&#125;/&#123;Phone-Number-ID&#125;/groups](#post-version-phone-number-id-groups) |

&lt;jumplink id=&quot;get-version-phone-number-id-groups&quot;&gt;&lt;/jumplink&gt;
## GET /&#123;Version&#125;/&#123;Phone-Number-ID&#125;/groups

Get Active Groups

Retrieve a list of active groups for a given business phone number

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
| Phone-Number-ID | string | ✓ | Business phone number ID |

### Query Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| limit | integer [min: 1, max: 1024] |  | Number of groups to fetch in the request |
| after | string |  | Cursor that points to the end of a page of data |
| before | string |  | Cursor that points to the beginning of a page of data |

### Responses

**200**

List of active groups

**Content Type**: `application/json`

**Schema**: object

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| data | [Data](#object-data-2) |  |  |
| paging | [PagingInfo](#paginginfo) |  |  |


&lt;jumplink id=&quot;post-version-phone-number-id-groups&quot;&gt;&lt;/jumplink&gt;
## POST /&#123;Version&#125;/&#123;Phone-Number-ID&#125;/groups

Create Group

Create a new group and get an invite link

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
| Phone-Number-ID | string | ✓ | Business phone number ID |

### Request Body (Required)

**Content Type**: `application/json`

**Schema**: object

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| messaging_product | &quot;whatsapp&quot; | ✓ | Messaging product |
| subject | string | ✓ | Group subject. Maximum 128 characters. Whitespace is trimmed. |
| description | string |  | Group description. Maximum 2048 characters. |
| join_approval_mode | One of &quot;approval_required&quot;, &quot;auto_approve&quot; |  | Indicates if WhatsApp users who click the invitation link can join the group with or without being approved first. - approval_required: WhatsApp users must be approved via join request before they can access the group - auto_approve: WhatsApp users can join the group without approval |

### Responses

**200**

Group creation request submitted successfully

**Content Type**: `application/json`

**Schema**: object

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| messaging_product | string |  |  |
| request_id | string |  | Group creation request ID |

**400**

Bad Request - Invalid request parameters

**Content Type**: `application/json`

**Schema**: [ErrorResponse](#errorresponse)

**401**

Unauthorized - Invalid or missing access token

**Content Type**: `application/json`

**Schema**: [ErrorResponse](#errorresponse)

**500**

Internal Server Error - An unexpected error occurred

**Content Type**: `application/json`

**Schema**: [ErrorResponse](#errorresponse)


# Components

## Schemas

&lt;jumplink id=&quot;errorobject&quot;&gt;&lt;/jumplink&gt;
### ErrorObject

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| message | string | ✓ | Human-readable description of the error |
| type | string | ✓ | Error type classification |
| code | integer | ✓ | Numeric error code |

&lt;jumplink id=&quot;errorresponse&quot;&gt;&lt;/jumplink&gt;
### ErrorResponse

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| error | [ErrorObject](#errorobject) | ✓ |  |

&lt;jumplink id=&quot;paginginfo&quot;&gt;&lt;/jumplink&gt;
### PagingInfo

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| cursors | [Cursors](#object-cursors-3) |  |  |
| previous | string |  | Previous page URL |
| next | string |  | Next page URL |

## Inline Object Definitions

&lt;jumplink id=&quot;object-groups-1&quot;&gt;&lt;/jumplink&gt;
### Groups

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| id | string |  | Group ID |
| subject | string |  | Group subject |
| created_at | string |  | Group creation timestamp |

&lt;jumplink id=&quot;object-data-2&quot;&gt;&lt;/jumplink&gt;
### Data

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| groups | array of [Groups](#object-groups-1) |  |  |

&lt;jumplink id=&quot;object-cursors-3&quot;&gt;&lt;/jumplink&gt;
### Cursors

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| before | string |  | Before cursor |
| after | string |  | After cursor |

## Authentication

| Scheme | Type | Location |
|--------|------|----------|
| bearerAuth | HTTP Bearer | Header: `Authorization` |

### Usage Examples

- **bearerAuth**: Include `Authorization: Bearer your-token-here` in request headers

### Global Authentication Requirements

All endpoints require: bearerAuth
