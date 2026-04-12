

## Base URL

| URL | Description |
|-----|-------------|
| https://graph.facebook.com | Production Graph API server |

## APIs

| Method | Endpoint |
|--------|----------|
| GET | [/&#123;Version&#125;/&#123;Phone-Number-ID&#125;/business_compliance_info](#get-version-phone-number-id-business-compliance-info) |
| POST | [/&#123;Version&#125;/&#123;Phone-Number-ID&#125;/business_compliance_info](#post-version-phone-number-id-business-compliance-info) |

&lt;jumplink id=&quot;get-version-phone-number-id-business-compliance-info&quot;&gt;&lt;/jumplink&gt;
## GET /&#123;Version&#125;/&#123;Phone-Number-ID&#125;/business_compliance_info

Get Business Compliance Information

Retrieve comprehensive business compliance information for a WhatsApp Business Account phone number,
including entity details, registration status, and required contact information for regulatory compliance.


**Use Cases:**
- Retrieve business compliance information for regulatory reporting
- Verify business entity registration status and contact details
- Access grievance officer and customer care information
- Support compliance audits and regulatory verification processes


**Rate Limiting:**
Standard Graph API rate limits apply. Use appropriate retry logic with exponential backoff.


**Caching:**
Compliance information can be cached for moderate periods, but should be refreshed regularly
to ensure accuracy for regulatory purposes. Implement appropriate cache invalidation strategies.


### Header Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| User-Agent | string |  | The user agent string identifying the client software making the request. |
| Authorization | string | ✓ | Bearer token for API authentication. This should be a valid access token obtained through the appropriate OAuth flow or system user token. |

### Path Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| Version | string | ✓ | Graph API version to use for this request. Determines the API behavior and available features. |
| Phone-Number-ID | string | ✓ | Your WhatsApp Business Account phone number ID. This ID can be found in your WhatsApp Business Manager or through phone number management APIs. |

### Query Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| fields | string |  | Comma-separated list of fields to include in the response. If not specified, default fields will be returned. Available fields: messaging_product, entity_name, entity_type, entity_type_custom, is_registered, grievance_officer_details, customer_care_details |

### Responses

**200**

Successfully retrieved business compliance information

**Content Type**: `application/json`

**Schema**: object

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| data | array of [BusinessComplianceInfo](#businesscomplianceinfo) |  |  |

**400**

Bad Request - Invalid parameters or malformed request

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;Invalid parameter: phone_number_id must be a valid numeric string&quot;,
        &quot;type&quot;: &quot;OAuthException&quot;,
        &quot;code&quot;: 100,
        &quot;fbtrace_id&quot;: &quot;AXsgnV2Cm3ZMGF3dF_cfYIn&quot;
    &#125;
&#125;\n```

**401**

Unauthorized - Invalid or missing access token

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;Invalid OAuth access token&quot;,
        &quot;type&quot;: &quot;OAuthException&quot;,
        &quot;code&quot;: 190,
        &quot;error_subcode&quot;: 463,
        &quot;fbtrace_id&quot;: &quot;AXsgnV2Cm3ZMGF3dF_cfYIn&quot;
    &#125;
&#125;\n```

**403**

Forbidden - Insufficient permissions or access denied

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;Your app doesn&#039;t have permission to access this WhatsApp Business Account&quot;,
        &quot;type&quot;: &quot;OAuthException&quot;,
        &quot;code&quot;: 200,
        &quot;error_subcode&quot;: 1349174,
        &quot;fbtrace_id&quot;: &quot;AXsgnV2Cm3ZMGF3dF_cfYIn&quot;,
        &quot;error_user_title&quot;: &quot;Permission Denied&quot;,
        &quot;error_user_msg&quot;: &quot;Your app doesn&#039;t have permission to access this resource&quot;
    &#125;
&#125;\n```

**404**

Not Found - Phone number ID does not exist or is not accessible

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;WhatsApp Business Account phone number not found&quot;,
        &quot;type&quot;: &quot;GraphMethodException&quot;,
        &quot;code&quot;: 803,
        &quot;fbtrace_id&quot;: &quot;AXsgnV2Cm3ZMGF3dF_cfYIn&quot;
    &#125;
&#125;\n```

**422**

Unprocessable Entity - Request parameters are valid but cannot be processed

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;The requested fields are not available for this phone number&quot;,
        &quot;type&quot;: &quot;GraphMethodException&quot;,
        &quot;code&quot;: 100,
        &quot;fbtrace_id&quot;: &quot;AXsgnV2Cm3ZMGF3dF_cfYIn&quot;
    &#125;
&#125;\n```

**429**

Too Many Requests - Rate limit exceeded

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;Application request limit reached&quot;,
        &quot;type&quot;: &quot;OAuthException&quot;,
        &quot;code&quot;: 4,
        &quot;error_subcode&quot;: 2446079,
        &quot;fbtrace_id&quot;: &quot;AXsgnV2Cm3ZMGF3dF_cfYIn&quot;,
        &quot;is_transient&quot;: true
    &#125;
&#125;\n```

**500**

Internal Server Error - Unexpected server error

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;An unexpected error occurred. Please retry your request&quot;,
        &quot;type&quot;: &quot;GraphMethodException&quot;,
        &quot;code&quot;: 2,
        &quot;fbtrace_id&quot;: &quot;AXsgnV2Cm3ZMGF3dF_cfYIn&quot;,
        &quot;is_transient&quot;: true
    &#125;
&#125;\n```


&lt;jumplink id=&quot;post-version-phone-number-id-business-compliance-info&quot;&gt;&lt;/jumplink&gt;
## POST /&#123;Version&#125;/&#123;Phone-Number-ID&#125;/business_compliance_info

Update Business Compliance Information

Create or update comprehensive business compliance information for a WhatsApp Business Account phone number,
including entity details, registration status, and required contact information for regulatory compliance.


**Use Cases:**
- Set business compliance information for regulatory reporting
- Update business entity registration status and details
- Configure grievance officer and customer care contact information
- Ensure compliance data accuracy for regulatory purposes
- Support compliance setup for new business operations


**Rate Limiting:**
Standard Graph API rate limits apply. Use appropriate retry logic with exponential backoff.


**Validation Rules:**
- `entity_name` is required and must be between 2 and 128 characters
- `entity_type` is required and must be a valid entity type enum value
- `entity_type_custom` is mandatory when `entity_type` is &quot;Other&quot;
- `entity_type_custom` cannot be used with non-&quot;Other&quot; entity types
- `is_registered` can only be used with &quot;Other&quot; or &quot;Partnership&quot; entity types
- `grievance_officer_details` is required with complete contact information
- `customer_care_details` is required with contact information
- Phone numbers must be valid international format with country code
- Email addresses must be valid format and under 128 characters


### Header Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| User-Agent | string |  | The user agent string identifying the client software making the request. |
| Authorization | string | ✓ | Bearer token for API authentication. This should be a valid access token obtained through the appropriate OAuth flow or system user token. |

### Path Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| Version | string | ✓ | Graph API version to use for this request. Determines the API behavior and available features. |
| Phone-Number-ID | string | ✓ | Your WhatsApp Business Account phone number ID. This ID can be found in your WhatsApp Business Manager or through phone number management APIs. |

### Request Body (Required)

**Content Type**: `application/json`

**Schema**: [BusinessComplianceInfoUpdateRequest](#businesscomplianceinfoupdaterequest)

### Responses

**200**

Successfully updated business compliance information

**Content Type**: `application/json`

**Schema**: object

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| success | boolean | ✓ | Indicates whether the compliance information was successfully updated |

**400**

Bad Request - Invalid parameters or validation errors

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**401**

Unauthorized - Invalid or missing access token

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;Invalid OAuth access token&quot;,
        &quot;type&quot;: &quot;OAuthException&quot;,
        &quot;code&quot;: 190,
        &quot;error_subcode&quot;: 463,
        &quot;fbtrace_id&quot;: &quot;AXsgnV2Cm3ZMGF3dF_cfYIn&quot;
    &#125;
&#125;\n```

**403**

Forbidden - Insufficient permissions or access denied

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;Your app doesn&#039;t have permission to access this WhatsApp Business Account&quot;,
        &quot;type&quot;: &quot;OAuthException&quot;,
        &quot;code&quot;: 200,
        &quot;error_subcode&quot;: 1349174,
        &quot;fbtrace_id&quot;: &quot;AXsgnV2Cm3ZMGF3dF_cfYIn&quot;,
        &quot;error_user_title&quot;: &quot;Permission Denied&quot;,
        &quot;error_user_msg&quot;: &quot;Your app doesn&#039;t have permission to access this resource&quot;
    &#125;
&#125;\n```

**404**

Not Found - Phone number ID does not exist or is not accessible

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;WhatsApp Business Account phone number not found&quot;,
        &quot;type&quot;: &quot;GraphMethodException&quot;,
        &quot;code&quot;: 803,
        &quot;fbtrace_id&quot;: &quot;AXsgnV2Cm3ZMGF3dF_cfYIn&quot;
    &#125;
&#125;\n```

**422**

Unprocessable Entity - Request parameters are valid but cannot be processed

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**429**

Too Many Requests - Rate limit exceeded

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;Application request limit reached&quot;,
        &quot;type&quot;: &quot;OAuthException&quot;,
        &quot;code&quot;: 4,
        &quot;error_subcode&quot;: 2446079,
        &quot;fbtrace_id&quot;: &quot;AXsgnV2Cm3ZMGF3dF_cfYIn&quot;,
        &quot;is_transient&quot;: true
    &#125;
&#125;\n```

**500**

Internal Server Error - Unexpected server error

**Content Type**: `application/json`

**Schema**: [GraphAPIError](#graphapierror)

**Example**:\n```json\n&#123;
    &quot;error&quot;: &#123;
        &quot;message&quot;: &quot;An unexpected error occurred. Please retry your request&quot;,
        &quot;type&quot;: &quot;GraphMethodException&quot;,
        &quot;code&quot;: 2,
        &quot;fbtrace_id&quot;: &quot;AXsgnV2Cm3ZMGF3dF_cfYIn&quot;,
        &quot;is_transient&quot;: true
    &#125;
&#125;\n```


# Components

## Schemas

&lt;jumplink id=&quot;businesscomplianceinfo&quot;&gt;&lt;/jumplink&gt;
### BusinessComplianceInfo

WhatsApp Business Account compliance information and regulatory details

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| whatsapp_business_account_id | string | ✓ | Unique identifier for the WhatsApp Business Account |
| messaging_product | &quot;whatsapp&quot; |  | Messaging product identifier, always &#039;whatsapp&#039; for WhatsApp Business |
| entity_name | string |  | Legal name of the business entity |
| entity_type | string |  | Type of business entity (e.g., Partnership, Private Limited Company, etc.) |
| entity_type_custom | string |  | Custom entity type description when standard types don&#039;t apply |
| is_registered | boolean |  | Whether the business entity is officially registered with regulatory authorities |
| grievance_officer_details | [GrievanceOfficerDetails](#grievanceofficerdetails) |  |  |
| customer_care_details | [CustomerCareDetails](#customercaredetails) |  |  |

&lt;jumplink id=&quot;grievanceofficerdetails&quot;&gt;&lt;/jumplink&gt;
### GrievanceOfficerDetails

Contact information for the designated grievance officer

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| name | string |  | Full name of the grievance officer |
| email | string (email) |  | Email address for grievance officer contact |
| mobile_number | string |  | Mobile phone number for grievance officer (with country code) |
| landline_number | string |  | Landline phone number for grievance officer (with country code) |

&lt;jumplink id=&quot;customercaredetails&quot;&gt;&lt;/jumplink&gt;
### CustomerCareDetails

Contact information for customer care and support

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| email | string (email) |  | Email address for customer care contact |
| mobile_number | string |  | Mobile phone number for customer care (with country code) |
| landline_number | string |  | Landline phone number for customer care (with country code) |

&lt;jumplink id=&quot;graphapierror&quot;&gt;&lt;/jumplink&gt;
### GraphAPIError

Standard Graph API error response

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| error | [Error](#object-error-1) | ✓ |  |

&lt;jumplink id=&quot;businesscomplianceinfoupdaterequest&quot;&gt;&lt;/jumplink&gt;
### BusinessComplianceInfoUpdateRequest

Request object for updating WhatsApp Business Account compliance information

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| messaging_product | &quot;whatsapp&quot; | ✓ | Messaging product identifier, must be &#039;whatsapp&#039; |
| entity_name | string | ✓ | Legal name of the business entity |
| entity_type | [BusinessEntityType](#businessentitytype) | ✓ |  |
| entity_type_custom | string |  | Custom entity type description when entity_type is &quot;OTHER&quot;. Required for OTHER entity type. |
| is_registered | boolean |  | Whether the business entity is officially registered with regulatory authorities. Can only be used with &quot;OTHER&quot; or &quot;PARTNERSHIP&quot; entity types. |
| grievance_officer_details | [GrievanceOfficerUpdateDetails](#grievanceofficerupdatedetails) | ✓ |  |
| customer_care_details | [CustomerCareUpdateDetails](#customercareupdatedetails) | ✓ |  |

&lt;jumplink id=&quot;businessentitytype&quot;&gt;&lt;/jumplink&gt;
### BusinessEntityType

Type of business entity for compliance purposes

**Type**: string

**Enum Values**: &quot;LIMITED_LIABILITY_PARTNERSHIP&quot;, &quot;SOLE_PROPRIETORSHIP&quot;, &quot;PARTNERSHIP&quot;, &quot;PUBLIC_COMPANY&quot;, &quot;PRIVATE_COMPANY&quot;, &quot;OTHER&quot;

&lt;jumplink id=&quot;grievanceofficerupdatedetails&quot;&gt;&lt;/jumplink&gt;
### GrievanceOfficerUpdateDetails

Contact information for the designated grievance officer

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| name | string | ✓ | Full name of the grievance officer |
| email | string (email) | ✓ | Email address for grievance officer contact |
| mobile_number | string |  | Mobile phone number for grievance officer (with country code) |
| landline_number | string |  | Landline phone number for grievance officer (with country code) |

&lt;jumplink id=&quot;customercareupdatedetails&quot;&gt;&lt;/jumplink&gt;
### CustomerCareUpdateDetails

Contact information for customer care and support

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| email | string (email) | ✓ | Email address for customer care contact |
| mobile_number | string |  | Mobile phone number for customer care (with country code) |
| landline_number | string |  | Landline phone number for customer care (with country code) |

## Inline Object Definitions

&lt;jumplink id=&quot;object-error-1&quot;&gt;&lt;/jumplink&gt;
### Error

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| message | string | ✓ | Human-readable error message |
| type | string | ✓ | Error category type |
| code | integer | ✓ | Numeric error code |
| error_subcode | integer |  | More specific error subcode when available |
| fbtrace_id | string |  | Unique identifier for debugging and support requests with Meta |
| is_transient | boolean |  | Indicates whether this error is temporary and the request should be retried |
| error_user_title | string |  | User-friendly error title for display purposes |
| error_user_msg | string |  | User-friendly error message for display purposes |

## Authentication

| Scheme | Type | Location |
|--------|------|----------|
| bearerAuth | HTTP Bearer | Header: `Authorization` |

### Usage Examples

- **bearerAuth**: Include `Authorization: Bearer your-token-here` in request headers

### Global Authentication Requirements

All endpoints require: bearerAuth
