

## Base URL

No base URL specified.

## APIs

| Method | Endpoint |
|--------|----------|
| POST | [/whatsapp/webhooks](#post-whatsapp-webhooks) |

&lt;jumplink id=&quot;post-whatsapp-webhooks&quot;&gt;&lt;/jumplink&gt;
## POST /whatsapp/webhooks

Receive incoming WhatsApp messages

Endpoint for receiving webhook payloads for diverse incoming WhatsApp message types.

### Request Body (Required)

Webhook payload containing incoming WhatsApp messages.

**Content Type**: `application/json`

**Schema**: [WebhookPayload](#webhookpayload)

### Responses

**200**

Webhook received successfully


# Components

## Schemas

&lt;jumplink id=&quot;webhookpayload&quot;&gt;&lt;/jumplink&gt;
### WebhookPayload

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| object | string | ✓ | Always &#039;whatsapp_business_account&#039; for these webhooks. |
| entry | array of [Entry](#entry) | ✓ |  |

&lt;jumplink id=&quot;entry&quot;&gt;&lt;/jumplink&gt;
### Entry

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| id | string | ✓ | WhatsApp Business Account ID. |
| changes | array of [Change](#change) | ✓ |  |

&lt;jumplink id=&quot;change&quot;&gt;&lt;/jumplink&gt;
### Change

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| value | Must be one of: [IncomingMessageValueGeneral](#incomingmessagevaluegeneral), [IncomingMessageValueSystem](#incomingmessagevaluesystem), [StatusMessageValue](#statusmessagevalue), [GroupValue](#groupvalue) | ✓ |  |
| field | One of &quot;messages&quot;, &quot;group_lifecycle_update&quot;, &quot;group_settings_update&quot;, &quot;group_participant_update&quot; | ✓ | The field indicate to what object is the webhook related: - messages: the webhook is related to messages from consumer or status of message sent by business to consumer. - group_lifecycle_update: the webhook is related to group creation and deletion. - group_settings_update: the webhook is related to group settings update. - group_participant_update: the webhook is related to participants joining and leaving the groups. |

&lt;jumplink id=&quot;metadata&quot;&gt;&lt;/jumplink&gt;
### Metadata

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| display_phone_number | string | ✓ | Business display phone number. |
| phone_number_id | string | ✓ | Business phone number ID. |

&lt;jumplink id=&quot;contactprofile&quot;&gt;&lt;/jumplink&gt;
### ContactProfile

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| profile | [Profile](#object-profile-1) | ✓ |  |
| wa_id | string |  | WhatsApp user ID. Note that a WhatsApp user&#039;s ID and phone number may not always match. |

&lt;jumplink id=&quot;incomingmessagevaluegeneral&quot;&gt;&lt;/jumplink&gt;
### IncomingMessageValueGeneral

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| messaging_product | string | ✓ | Always &#039;whatsapp&#039;. |
| metadata | [Metadata](#metadata) | ✓ |  |
| contacts | array of [ContactProfile](#contactprofile) | ✓ | Array of contact profiles for the sender. Included for all non-system incoming messages. |
| messages | array of [IncomingMessage](#incomingmessage) | ✓ | Array of message objects. The structure varies based on the &#039;type&#039; property. |

&lt;jumplink id=&quot;incomingmessagevaluesystem&quot;&gt;&lt;/jumplink&gt;
### IncomingMessageValueSystem

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| messaging_product | string | ✓ | Always &#039;whatsapp&#039;. |
| metadata | [Metadata](#metadata) | ✓ |  |
| messages | array of [SystemMessage](#systemmessage) | ✓ | Array containing only &#039;system&#039; message objects. |

&lt;jumplink id=&quot;statusmessagevalue&quot;&gt;&lt;/jumplink&gt;
### StatusMessageValue

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| messaging_product | string | ✓ | Always &#039;whatsapp&#039;. |
| metadata | [Metadata](#metadata) | ✓ |  |
| statuses | array of [Statuses](#statuses) | ✓ | Array of status objects. |

&lt;jumplink id=&quot;statuses&quot;&gt;&lt;/jumplink&gt;
### Statuses

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| id | string | ✓ | Unique WhatsApp message ID the status is associated with. |
| status | One of &quot;sent&quot;, &quot;delivered&quot;, &quot;read&quot;, &quot;failed&quot; | ✓ |  |
| timestamp | string | ✓ |  |
| recipient_id | string | ✓ | Recipeint phone number. |
| group_id | string |  | Group ID if the message was sent to a group. |
| conversation | [Conversation](#conversation) |  |  |
| pricing | [Pricing](#pricing) |  |  |
| errors | array of [StatusError](#statuserror) |  |  |

&lt;jumplink id=&quot;conversation&quot;&gt;&lt;/jumplink&gt;
### Conversation

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| id | string |  |  |
| expiration_timestamp | string |  |  |
| origin | [ConversationOrigin](#conversationorigin) |  |  |

&lt;jumplink id=&quot;conversationorigin&quot;&gt;&lt;/jumplink&gt;
### ConversationOrigin

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| type | string |  |  |

&lt;jumplink id=&quot;pricing&quot;&gt;&lt;/jumplink&gt;
### Pricing

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| billable | boolean |  |  |
| pricing_model | One of &quot;CBP&quot;, &quot;PMP&quot; |  |  |
| category | string |  |  |

&lt;jumplink id=&quot;statuserror&quot;&gt;&lt;/jumplink&gt;
### StatusError

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| code | integer |  |  |
| title | string |  |  |
| message | string |  |  |
| error_data | [ErrorData](#errordata) |  |  |
| href | string |  |  |

&lt;jumplink id=&quot;errordata&quot;&gt;&lt;/jumplink&gt;
### ErrorData

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| details | string |  |  |

&lt;jumplink id=&quot;groupvalue&quot;&gt;&lt;/jumplink&gt;
### GroupValue

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| messaging_product | string | ✓ | Always &#039;whatsapp&#039;. |
| metadata | [Metadata](#metadata) | ✓ |  |
| groups | array of [Groups](#groups) | ✓ | Array of group objects. |

&lt;jumplink id=&quot;groups&quot;&gt;&lt;/jumplink&gt;
### Groups

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| timestamp | integer | ✓ | Unix timestamp of the group event |
| group_id | string | ✓ | Unique identifier for the group |
| type | One of &quot;group_create&quot;, &quot;group_delete&quot;, &quot;group_settings_update&quot;, &quot;group_add_participants&quot;, &quot;group_remove_participants&quot; | ✓ | Type of group event |
| request_id | string | ✓ | Unique identifier for the request |
| subject | string |  | Group subject/name |
| description | string |  | Group description |
| added_participants | array of [GroupParticipant](#groupparticipant) |  | List of participants added to the group |
| removed_participants | array of [GroupParticipant](#groupparticipant) |  | List of participants removed from the group |
| profile_picture | [GroupProfilePicture](#groupprofilepicture) |  | Group profile picture information |

&lt;jumplink id=&quot;groupparticipant&quot;&gt;&lt;/jumplink&gt;
### GroupParticipant

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| input | string |  | Input phone number or WhatsApp ID |
| wa_id | string |  | WhatsApp ID of the participant |

&lt;jumplink id=&quot;groupprofilepicture&quot;&gt;&lt;/jumplink&gt;
### GroupProfilePicture

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| mime_type | string |  | MIME type of the profile picture |
| sha256 | string |  | SHA256 hash of the profile picture |

&lt;jumplink id=&quot;basemessageproperties&quot;&gt;&lt;/jumplink&gt;
### BaseMessageProperties

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| from | string | ✓ | WhatsApp user phone number. Note that a WhatsApp user&#039;s phone number and ID may not always match. |
| id | string | ✓ | Unique WhatsApp message ID. |
| timestamp | string | ✓ | Unix timestamp indicating when the webhook was triggered. |

&lt;jumplink id=&quot;incomingmessage&quot;&gt;&lt;/jumplink&gt;
### IncomingMessage

**Type**: object

&lt;jumplink id=&quot;textmessage&quot;&gt;&lt;/jumplink&gt;
### TextMessage

&lt;jumplink id=&quot;contextobject&quot;&gt;&lt;/jumplink&gt;
### ContextObject

Only included if message via a &quot;Message business&quot; button.

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| from | string | ✓ | Business display phone number. |
| id | string | ✓ | WhatsApp message ID of the message the user used to access the &quot;Message business&quot; button. |
| referred_product | [Referred_product](#object-referred_product-2) | ✓ |  |

&lt;jumplink id=&quot;referralobject&quot;&gt;&lt;/jumplink&gt;
### ReferralObject

Only included if message via a Click to WhatsApp ad.

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| source_url | string | ✓ | Ad URL. |
| source_id | string | ✓ | Ad ID. |
| source_type | One of &quot;ad&quot;, &quot;post&quot; | ✓ |  |
| body | string | ✓ | Ad primary text. |
| headline | string | ✓ | Ad headline. |
| media_type | One of &quot;image&quot;, &quot;video&quot; | ✓ |  |
| image_url | string |  | Only included for image media_type. |
| video_url | string |  | Only included for video media_type. |
| thumbnail_url | string |  | Only included for video media_type. |
| ctwa_clid | string | ✓ | Ad click ID. |
| welcome_message | [Welcome_message](#object-welcome_message-3) |  |  |

&lt;jumplink id=&quot;reactionmessage&quot;&gt;&lt;/jumplink&gt;
### ReactionMessage

&lt;jumplink id=&quot;mediamessageproperties&quot;&gt;&lt;/jumplink&gt;
### MediaMessageProperties

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| mime_type | string | ✓ | Media asset MIME type. |
| sha256 | string | ✓ | Media asset SHA-256 hash. |
| id | string | ✓ | Media asset ID. A GET request on this ID can provide the asset URL. |

&lt;jumplink id=&quot;audiomessage&quot;&gt;&lt;/jumplink&gt;
### AudioMessage

&lt;jumplink id=&quot;documentmessage&quot;&gt;&lt;/jumplink&gt;
### DocumentMessage

&lt;jumplink id=&quot;imagemessage&quot;&gt;&lt;/jumplink&gt;
### ImageMessage

&lt;jumplink id=&quot;stickermessage&quot;&gt;&lt;/jumplink&gt;
### StickerMessage

&lt;jumplink id=&quot;videomessage&quot;&gt;&lt;/jumplink&gt;
### VideoMessage

&lt;jumplink id=&quot;locationmessage&quot;&gt;&lt;/jumplink&gt;
### LocationMessage

&lt;jumplink id=&quot;contactsharingmessage&quot;&gt;&lt;/jumplink&gt;
### ContactSharingMessage

&lt;jumplink id=&quot;contactobject&quot;&gt;&lt;/jumplink&gt;
### ContactObject

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| addresses | array of [Addresses](#object-addresses-4) |  |  |
| birthday | string (date) |  | Contact birthday (YYYY-MM-DD). |
| emails | array of [Emails](#object-emails-5) |  |  |
| name | [Name](#object-name-6) |  |  |
| org | [Org](#object-org-7) |  |  |
| phones | array of [Phones](#object-phones-8) |  |  |
| urls | array of [Urls](#object-urls-9) |  |  |

&lt;jumplink id=&quot;unsupportedmessage&quot;&gt;&lt;/jumplink&gt;
### UnsupportedMessage

&lt;jumplink id=&quot;interactivemessagereply&quot;&gt;&lt;/jumplink&gt;
### InteractiveMessageReply

&lt;jumplink id=&quot;interactivelistreplycontent&quot;&gt;&lt;/jumplink&gt;
### InteractiveListReplyContent

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| list_reply | [List_reply](#object-list_reply-10) | ✓ |  |

&lt;jumplink id=&quot;interactivebuttonreplycontent&quot;&gt;&lt;/jumplink&gt;
### InteractiveButtonReplyContent

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| button_reply | [Button_reply](#object-button_reply-11) | ✓ |  |

&lt;jumplink id=&quot;ordermessage&quot;&gt;&lt;/jumplink&gt;
### OrderMessage

&lt;jumplink id=&quot;systemmessage&quot;&gt;&lt;/jumplink&gt;
### SystemMessage

## Inline Object Definitions

&lt;jumplink id=&quot;object-profile-1&quot;&gt;&lt;/jumplink&gt;
### Profile

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| name | string | ✓ | WhatsApp user&#039;s name as it appears in their profile in the WhatsApp client. |

&lt;jumplink id=&quot;object-referred_product-2&quot;&gt;&lt;/jumplink&gt;
### Referred_product

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| catalog_id | string | ✓ | Product catalog ID. |
| product_retailer_id | string | ✓ | Product ID. |

&lt;jumplink id=&quot;object-welcome_message-3&quot;&gt;&lt;/jumplink&gt;
### Welcome_message

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| text | string | ✓ | Ad greeting text. |

&lt;jumplink id=&quot;object-addresses-4&quot;&gt;&lt;/jumplink&gt;
### Addresses

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| city | string |  | City mentioned in the contact address |
| country | string |  | Country mentioned in the contact address |
| country_code | string |  | ISO country code for the contact address |
| state | string |  | State mentioned in the contact address |
| street | string |  | Street mentioned in the contact address |
| type | string |  | Type of address, such as home or work |
| zip | string |  | Zip code in the contact address |

&lt;jumplink id=&quot;object-emails-5&quot;&gt;&lt;/jumplink&gt;
### Emails

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| email | string (email) |  | Email address of the contact |
| type | string |  | Type of email, such as personal or work |

&lt;jumplink id=&quot;object-name-6&quot;&gt;&lt;/jumplink&gt;
### Name

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| formatted_name | string | ✓ | Contact&#039;s formatted name |
| first_name | string |  | Contact’s first name |
| last_name | string |  | Contact’s last name |
| middle_name | string |  | Contact’s middle name |
| suffix | string |  | Contact’s name suffix |
| prefix | string |  | Contact’s name prefix |

&lt;jumplink id=&quot;object-org-7&quot;&gt;&lt;/jumplink&gt;
### Org

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| company | string |  | Name of the company where the contact works |
| department | string |  | Name of the department where the contact works |
| title | string |  | Contact&#039;s job title |

&lt;jumplink id=&quot;object-phones-8&quot;&gt;&lt;/jumplink&gt;
### Phones

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| phone | string |  | Contact’s Phone number |
| wa_id | string |  | Contact&#039;s WhatsApp Number. Note that a WhatsApp user&#039;s ID and phone number may not always match. |
| type | string |  | Type of phone number. For example, cell, mobile, main, iPhone, home, work, etc. |

&lt;jumplink id=&quot;object-urls-9&quot;&gt;&lt;/jumplink&gt;
### Urls

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| url | string (uri) |  | Website URL associated with the contact or their company |
| type | string |  | Type of website. For example, company, work, personal, Facebook Page, Instagram, etc. |

&lt;jumplink id=&quot;object-list_reply-10&quot;&gt;&lt;/jumplink&gt;
### List_reply

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| id | string | ✓ | Row ID. |
| title | string | ✓ | Row title. |
| description | string | ✓ | Row description. |

&lt;jumplink id=&quot;object-button_reply-11&quot;&gt;&lt;/jumplink&gt;
### Button_reply

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| id | string | ✓ | Button ID. |
| title | string | ✓ | Button label text. |

## Authentication

| Scheme | Type | Location |
|--------|------|----------|
| bearerAuth | HTTP Bearer | Header: `Authorization` |

### Usage Examples

- **bearerAuth**: Include `Authorization: Bearer your-token-here` in request headers

### Global Authentication Requirements

All endpoints require: bearerAuth
