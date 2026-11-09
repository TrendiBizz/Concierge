# Customer-owned phone requirement — authoritative steering

User explicitly requires a workable product for any customer in any country using their own phones and numbers. Mac/Apple Continuity, Jo's Spark configuration, and a US-only answering number are insufficient as the product solution.

Keep existing customer phones/numbers. Grok supplies voice intelligence; carrier/PBX routing must carry the actual call audio. No universal ordinary-mobile API has been established. Do not label a customer connected until a real inbound call on their designated number proves two-way Grok audio, recording/transcript attachment, and requested recipient delivery. Retain human fallback and restore routing when setup fails. Do not claim global coverage based on one country or carrier.

Read-only xAI inventory check using existing production credential returned HTTP200 and zero phone numbers. Official API docs currently document xAI provisioned area_code as a three-digit US filter; this is not evidence of worldwide local number availability. Built-in xAI number activation/test approval was requested asynchronously but has not been granted. Latest user steering means a US-only route is not sufficient regardless.

Sources: https://docs.x.ai/developers/rest-api-reference/inference/voice ; https://x.ai/news/grok-voice-agent-builder ; https://www.spark.co.nz/help/mobile/manage/mobile-call-features

Next: validate carrier forwarding/BYO SIP coverage and explicit unsupported cases; implement customer setup against existing integrations without requiring a customer Mac, a new carrier account, or new subscription unless specifically authorized. Coordinate with active same-checkout implementation before editing shared source or deploying.

## Builder activation attempt — latest user steering

User supplied xAI Builder instructions and requested finish. Continued existing Trendi agent `agent_lQMmpdrJeJDBB7JO`, team `fc021a82-2b63-40cf-b1fd-36e84f723a13`; do not create duplicate agent. Builder shows Live, last published minutes ago, tools only web_search and end_call, no CRM/SMS API tool or connectors yet.

Read-only GET /v2/phone-numbers?agent_id=agent_lQMmpdrJeJDBB7JO returned empty. One POST /v2/phone-numbers (origin=xai_provisioned,name=Trendi Concierge,agent_id=...) failed403: `agents endpoint is not enabled for this team`. No number or secret created. No automatic retry. Console Add number independently shows `Your area does not support provisioning phone numbers` / `Use Twilio or Direct SIP instead.` This is a concrete account/region restriction, not a Grok voice failure. Do not bypass country eligibility or claim included number active. Existing Spark forwarding unchanged.

UI Direct SIP offers `sip:{number}@sip.voice.x.ai;transport=tls`; existing ordinary mobile number still needs provider routing, no existing SIP account established. API request custom tools are supported with fixed headers and body/query parameters; native Builder SMS tool specifically requires a Twilio number with outbound SMS. Own inspection tab1374601267 closed; other active setup tab1374601264 preserved (owned by continuation chat). No live microphone/call or text sent.
