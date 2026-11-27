# Zoho CRM setup

## Leads custom fields

| API name | Type | Notes |
| --- | --- | --- |
| `LINE_User_ID` | Single line | Turn **"Do not allow duplicate values" ON**. The relay's upsert uses it as `duplicate_check_fields`, so without this the same person can be created twice. |
| `LINE_Status` | Picklist | Values: `Friend`, `Blocked`. Set to `Friend` on registration and `Blocked` on unfollow. |
| `Last_LINE_Inbound` | Date/Time | Updated by the relay when the customer sends a text message. |
| `Last_LINE_Push` | Date/Time | Updated by the Deluge function after a follow-up is sent. |

## Org variables

Created under Setup > Developer Space > Org Variables (read with `zoho.crm.getOrgVariable`).

| API name | Value |
| --- | --- |
| `line_relay_url` | Base URL of the deployed relay, without a trailing slash (for example `https://line-zoho-relay.example.workers.dev`). |
| `line_relay_key` | The same secret as the relay's `RELAY_KEY`. Sent in the `X-Relay-Key` header. |

## Connection

The Deluge function uses a CRM connection named `zoho_crm` with the scopes
`ZohoCRM.modules.leads.READ`, `ZohoCRM.modules.leads.UPDATE` and `ZohoCRM.modules.notes.CREATE`.
