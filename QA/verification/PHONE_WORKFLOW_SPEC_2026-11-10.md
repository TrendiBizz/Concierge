# Phone workflow — final agreed design (10 November 2026)

The customer (business owner) uses the star codes on their own smartphone so
unanswered/busy calls forward to a carrier number. Telnyx provides the SIP; the
rest is our system.

## The flow

1. **Forward** — the owner's carrier star codes forward unanswered/busy calls to
   the Telnyx DID.
2. **Terminate** — Telnyx (SIP) hands the call to Asterisk, which routes it to our
   private AudioSocket → Grok voice bridge.
3. **Answer** — the Grok voice receptionist answers, discloses transcription, and
   asks permission to record. No audio is recorded before consent; withdrawing
   consent discards it.
4. **Confirmation** — after recording, it asks whether the caller wants a
   confirmation by **text**, **email**, or a **return call**.
5. **Capture + forward** — the enquiry (lead, transcript, recording) is saved to
   the CRM and forwarded to the owner as a **voicemail** (private recording link),
   **text**, and/or **email**.

## Status against the code

| Element | Status |
| --- | --- |
| Carrier star-code forwarding | owner/carrier action; destination = the Telnyx DID |
| Telnyx DID + SIP trunk → Asterisk | **pending**: buy/port a number and route it; Telnyx connection `Trendi` exists (active, IP connection) |
| Asterisk → AudioSocket → Grok | **built + verified** (Asterisk 20.6 + live Grok, two synthetic legs, 9 Nov) |
| Consent-gated recording | **built** (`set_call_recording`; consent required; WAV stored via `voice_records.store_audio`) |
| Confirmation: text / email | **built** (`request_enquiry_acknowledgement` email\|sms; `request_conversation_copy` text\|recording link) |
| Confirmation: return call | **built** (Grok asks, saves the callback preference into the lead) |
| CRM capture | **built** (lead + full transcript) |
| Owner forwarding: text + email | **built** (`asterisk_bridge.finish` queues owner SMS + email) |
| Owner forwarding: voicemail (recording link) | **fixed 2026-11-10** — `asterisk_bridge.finish` now appends the private 24h recording link + CRM note to the owner notification, matching the website-voice path |

## Not code (remaining activation)

1. Buy/port a Telnyx number on the `Trendi` connection and route it to Asterisk.
2. Per business: create/enable the `phone_numbers` row, set `phone_enabled`, grant
   telephone authorization, and set the owner delivery number/email.
3. Run one real forwarded call end to end and confirm the owner receipt.

Everything above the "activation" line is implemented; the bridge is not yet
deployed because there is no number/trunk to terminate yet.
