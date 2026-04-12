

## Base URL

| URL | Description |
|-----|-------------|
| https://graph.facebook.com |  |

## APIs

| Method | Endpoint |
|--------|----------|
| GET | [/&#123;Version&#125;/&#123;Phone-Number-ID&#125;/settings](#get-version-phone-number-id-settings) |
| POST | [/&#123;Version&#125;/&#123;Phone-Number-ID&#125;/settings](#post-version-phone-number-id-settings) |

&lt;jumplink id=&quot;get-version-phone-number-id-settings&quot;&gt;&lt;/jumplink&gt;
## GET /&#123;Version&#125;/&#123;Phone-Number-ID&#125;/settings

Get phone number settings

Retrieve current settings for a WhatsApp Business phone number.
Returns calling settings, payload encryption settings, and data
storage configurations.


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
| Phone-Number-ID | string | ✓ |  |

### Query Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| include_sip_credentials | boolean |  | Include SIP credentials in the response (requires additional permissions) |

### Responses

**200**

Current phone number settings retrieved successfully

**Content Type**: `application/json`

**Schema**: [PhoneNumberSettingsResponse](#phonenumbersettingsresponse)

**400**

Bad Request - Invalid request parameters

**Content Type**: `application/json`

**Schema**: [ErrorResponse](#errorresponse)

**403**

Forbidden - Template not approved or insufficient permissions

**Content Type**: `application/json`

**Schema**: [ErrorResponse](#errorresponse)


&lt;jumplink id=&quot;post-version-phone-number-id-settings&quot;&gt;&lt;/jumplink&gt;
## POST /&#123;Version&#125;/&#123;Phone-Number-ID&#125;/settings

Update phone number settings

Update various settings for a WhatsApp Business phone number.
You can configure calling settings, user identity change settings,
payload encryption, and data storage configurations.
Only one feature setting can be specified per request.


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
| Phone-Number-ID | string | ✓ |  |

### Request Body (Optional)

**Content Type**: `application/json`

**Schema**: Must be one of: [CallingSettingsRequest](#callingsettingsrequest), [UserIdentityChangeSettingsRequest](#useridentitychangesettingsrequest), [PayloadEncryptionSettingsRequest](#payloadencryptionsettingsrequest), [StorageConfigurationSettingsRequest](#storageconfigurationsettingsrequest)

### Responses

**200**

Settings updated successfully

**Content Type**: `application/json`

**Schema**: object

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| success | boolean |  |  |

**400**

Bad Request - Invalid request parameters

**Content Type**: `application/json`

**Schema**: [ErrorResponse](#errorresponse)

**403**

Forbidden - Template not approved or insufficient permissions

**Content Type**: `application/json`

**Schema**: [ErrorResponse](#errorresponse)


# Components

## Schemas

&lt;jumplink id=&quot;callingsettingsrequest&quot;&gt;&lt;/jumplink&gt;
### CallingSettingsRequest

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| calling | [CallingSettings](#callingsettings) | ✓ |  |

&lt;jumplink id=&quot;callingsettings&quot;&gt;&lt;/jumplink&gt;
### CallingSettings

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| status | One of &quot;enabled&quot;, &quot;disabled&quot; | ✓ | Enable or disable calling feature |
| call_icon_visibility | One of &quot;visible&quot;, &quot;hidden&quot; |  | Control visibility of the call icon |
| video | [VideoSettings](#videosettings) |  |  |
| sip | [SipSettings](#sipsettings) |  |  |
| srtp_key_exchange_protocol | One of &quot;DTLS-SRTP&quot;, &quot;SDES-SRTP&quot; |  | SRTP key exchange protocol |

&lt;jumplink id=&quot;videosettings&quot;&gt;&lt;/jumplink&gt;
### VideoSettings

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| status | One of &quot;enabled&quot;, &quot;disabled&quot; | ✓ | Enable or disable video calling |

&lt;jumplink id=&quot;sipsettings&quot;&gt;&lt;/jumplink&gt;
### SipSettings

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| status | One of &quot;enabled&quot;, &quot;disabled&quot; | ✓ | Enable or disable SIP calling |

&lt;jumplink id=&quot;useridentitychangesettingsrequest&quot;&gt;&lt;/jumplink&gt;
### UserIdentityChangeSettingsRequest

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| user_identity_change | [UserIdentityChangeSettings](#useridentitychangesettings) | ✓ |  |

&lt;jumplink id=&quot;useridentitychangesettings&quot;&gt;&lt;/jumplink&gt;
### UserIdentityChangeSettings

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| enabled | boolean | ✓ | Enable or disable user identity change notifications |

&lt;jumplink id=&quot;payloadencryptionsettingsrequest&quot;&gt;&lt;/jumplink&gt;
### PayloadEncryptionSettingsRequest

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| payload_encryption | [PayloadEncryptionSettings](#payloadencryptionsettings) | ✓ |  |

&lt;jumplink id=&quot;payloadencryptionsettings&quot;&gt;&lt;/jumplink&gt;
### PayloadEncryptionSettings

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| status | One of &quot;enabled&quot;, &quot;disabled&quot; | ✓ | Enable or disable payload encryption |
| client_encryption_key | string |  | Base64-encoded public key for payload encryption (required when enabling encryption) |

&lt;jumplink id=&quot;storageconfigurationsettingsrequest&quot;&gt;&lt;/jumplink&gt;
### StorageConfigurationSettingsRequest

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| storage_configuration | [StorageConfigurationSettings](#storageconfigurationsettings) | ✓ |  |

&lt;jumplink id=&quot;storageconfigurationsettings&quot;&gt;&lt;/jumplink&gt;
### StorageConfigurationSettings

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| enabled | boolean | ✓ | Enable or disable custom storage configuration |
| region | string |  | Data storage region |

&lt;jumplink id=&quot;phonenumbersettingsresponse&quot;&gt;&lt;/jumplink&gt;
### PhoneNumberSettingsResponse

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| calling | [CallingSettingsResponse](#callingsettingsresponse) | ✓ |  |
| payload_encryption | [PayloadEncryptionSettingsResponse](#payloadencryptionsettingsresponse) |  |  |
| storage_configuration | [StorageConfigurationSettingsResponse](#storageconfigurationsettingsresponse) | ✓ |  |

&lt;jumplink id=&quot;callingsettingsresponse&quot;&gt;&lt;/jumplink&gt;
### CallingSettingsResponse

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| status | One of &quot;enabled&quot;, &quot;disabled&quot; | ✓ | Current calling feature status |
| call_icon_visibility | One of &quot;visible&quot;, &quot;hidden&quot; | ✓ | Current call icon visibility setting |
| ip_addresses | [Ip_addresses](#object-ip_addresses-1) | ✓ |  |
| callback_permission_status | One of &quot;enabled&quot;, &quot;disabled&quot; | ✓ | Callback permission status |
| srtp_key_exchange_protocol | One of &quot;DTLS-SRTP&quot;, &quot;SDES-SRTP&quot; |  | SRTP key exchange protocol (optional) |
| call_hours | [CallHoursSettings](#callhourssettings) |  |  |
| call_icons | [CallIconsSettings](#calliconssettings) |  |  |
| sip | [SipSettingsResponse](#sipsettingsresponse) |  |  |
| video | [VideoSettingsResponse](#videosettingsresponse) |  |  |
| audio | [AudioSettingsResponse](#audiosettingsresponse) |  |  |
| restrictions | [CallingRestrictionsResponse](#callingrestrictionsresponse) |  |  |

&lt;jumplink id=&quot;callhourssettings&quot;&gt;&lt;/jumplink&gt;
### CallHoursSettings

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| status | One of &quot;enabled&quot;, &quot;disabled&quot; | ✓ | Call hours feature status |
| timezone | string |  | Timezone for call hours |
| day_of_week_start | string |  | Start day of the week |

&lt;jumplink id=&quot;calliconssettings&quot;&gt;&lt;/jumplink&gt;
### CallIconsSettings

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| restrict_to_user_countries | array of string |  | List of countries where call icons are restricted |

&lt;jumplink id=&quot;sipsettingsresponse&quot;&gt;&lt;/jumplink&gt;
### SipSettingsResponse

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| status | One of &quot;enabled&quot;, &quot;disabled&quot; | ✓ | SIP calling status |
| servers | array of [SipServerInfo](#sipserverinfo) |  | SIP server configuration |

&lt;jumplink id=&quot;sipserverinfo&quot;&gt;&lt;/jumplink&gt;
### SipServerInfo

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| app_id | string | ✓ | Application ID for SIP server |
| hostname | string | ✓ | SIP server hostname |
| port | integer |  | SIP server port (optional) |
| password | string |  | SIP password (only included when include_sip_credentials=true) |

&lt;jumplink id=&quot;videosettingsresponse&quot;&gt;&lt;/jumplink&gt;
### VideoSettingsResponse

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| status | One of &quot;enabled&quot;, &quot;disabled&quot; | ✓ | Video calling status |

&lt;jumplink id=&quot;audiosettingsresponse&quot;&gt;&lt;/jumplink&gt;
### AudioSettingsResponse

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| status | One of &quot;enabled&quot;, &quot;disabled&quot; |  | Audio calling status |

&lt;jumplink id=&quot;callingrestrictionsresponse&quot;&gt;&lt;/jumplink&gt;
### CallingRestrictionsResponse

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| restrictions | array of [Restrictions](#object-restrictions-2) |  |  |

&lt;jumplink id=&quot;payloadencryptionsettingsresponse&quot;&gt;&lt;/jumplink&gt;
### PayloadEncryptionSettingsResponse

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| status | One of &quot;enabled&quot;, &quot;disabled&quot; | ✓ | Payload encryption status |
| client_encryption_key_fingerprint | string |  | Client encryption key fingerprint (when encryption is enabled) |
| cloud_encryption_key | string |  | Cloud encryption key (when encryption is enabled) |

&lt;jumplink id=&quot;storageconfigurationsettingsresponse&quot;&gt;&lt;/jumplink&gt;
### StorageConfigurationSettingsResponse

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| status | One of &quot;default&quot;, &quot;in_country_storage_enabled&quot; | ✓ | Data storage configuration status |
| data_localization_region | string |  | Data localization region (when in-country storage is enabled) |

## Inline Object Definitions

&lt;jumplink id=&quot;object-ip_addresses-1&quot;&gt;&lt;/jumplink&gt;
### Ip_addresses

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| default | array of string | ✓ | Default IP addresses for calling |

&lt;jumplink id=&quot;object-restrictions-2&quot;&gt;&lt;/jumplink&gt;
### Restrictions

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| type | string |  | Type of restriction |
| expiration | integer (int64) |  | Expiration timestamp for the restriction |

## Authentication

| Scheme | Type | Location |
|--------|------|----------|
| bearerAuth | HTTP Bearer | Header: `Authorization` |

### Usage Examples

- **bearerAuth**: Include `Authorization: Bearer your-token-here` in request headers

### Global Authentication Requirements

All endpoints require: bearerAuth
