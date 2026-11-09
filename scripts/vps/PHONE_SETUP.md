# Optional Grok SIP telephone setup

Website voice and the portal secretary use the existing Grok browser connection.
They do not require PHONE_RECEPTIONIST_ENABLED, XAI_SIP_CONNECTIONS or a DID.
These settings enable ordinary carrier/PBX calls only. A personal owner contact
number is a notification target, not proof of a SIP-capable telephone route.

## Runtime settings

Production loads /opt/trendi/shared/api.env, mode0600, with Compose raw env_file.
Editing .env.example does not update runtime settings. Keep the existing xAI key.

- PHONE_RECEPTIONIST_ENABLED=true: opens the global handler; individual businesses
  and phone numbers still require activation and authorization.
- PHONE_VOICE_PROVIDER=grok.
- XAI_API_KEY: existing team API key, server-side only.
- XAI_SIP_CONNECTIONS: one-line JSON object keyed by a locally chosen connection
  UUID. Each entry has enabled=true, tenant (exact business slug), number (actual
  registered E.164 destination) and signing_secret (real provider whsec_ secret).
  The private mapping must never be committed. Empty {} means no SIP routes.

Webhook: POST https://concierge.trendibizz.com/api/v1/phone/xai/{connection_id}.
The ID in that URL must equal the UUID key in XAI_SIP_CONNECTIONS.

## Connect an existing number

xAI supports registration through its API; console access is not inherently
required. GET https://api.x.ai/v2/phone-numbers lists the existing team's numbers.
POST /v2/phone-numbers with origin=byo_trunk registers an existing carrier/PBX
number, webhook URL and actual SIP IP allowlist or digest credentials. It returns
its webhook signing secret once. Store the actual response privately. Registration
alone does not buy/provision a public number or connect an ordinary mobile SIM.
Route the existing carrier/PBX to sip:<actual-number>@sip.voice.x.ai;transport=tls.

Official API and routing instructions:
https://docs.x.ai/developers/model-capabilities/audio/speech-to-speech/sip

Never create a fictional route from the owner's contact phone or invent a signing
secret. When the existing team has zero registered numbers and no carrier ingress
has been supplied, the exact remaining prerequisite is a genuine compatible
number/trunk. The xAI API does not provision new xAI numbers. Keep phone setup
pending while the website service continues operating independently.

## Bind to the correct business

Use the existing authenticated admin endpoints (private loopback/API access):

1. POST /admin/tenants/{slug}/phone-numbers with actual e164 to create the row.
2. PATCH /admin/tenants/{slug}/phone-numbers/{number} with enabled=true.
3. PATCH /admin/tenants/{slug} with phone_enabled=true.
4. Obtain that owner's telephone authorization through existing onboarding.
5. Add the corresponding signed webhook mapping privately; recreate API/social.

An enabled phone_numbers row belongs to exactly one tenant. The caller/model
never chooses the business. Unknown/unauthorized calls remain rejected. Database
configuration and a healthy image are not evidence a real carrier call succeeded.

## Verify

Check image revision and health, authenticated business readiness and exact number
mapping without printing secrets. Test an unsigned webhook (must reject), then
make one authorized actual incoming call. Verify correct business greeting,
complete transcript/CRM, requested acknowledgement and actual owner receipt.
Only then add its slug to PHONE_VERIFIED_TENANTS. Queue insertion is not receipt.
Native SIP currently transcribes; do not claim it saves telephone audio recording.
Keep website recording consent/storage verification separate.
