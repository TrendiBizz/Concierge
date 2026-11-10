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
| Asterisk → AudioSocket → Grok | **installed on the VPS 2026-11-10**: Asterisk 20.6 with endpoint `concierge-ingress-1`, exact-DID dialplan and `app/chan/res_audiosocket` running; the bridge listens on 9510; a local originate through `s@business-trendi-oauth-staging` created a `phone_calls` row, conversation and lead and reached Grok with no bridge error. Test rows removed. |
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

Everything above the "activation" line is implemented. The pbx + bridge containers
are running on the VPS on the private phone network (no public SIP ports yet);
the placeholder route/DID used for the local test was removed after verification.
Activation is: real Telnyx DID → swap the route + `phone_numbers` row → set
`source_cidr` to Telnyx's SIP signalling range → publish SIP/RTP. The Asterisk
Dockerfile needed `/var/run/asterisk` created at start (the non-root build had no
CLI socket); fixed 2026-11-10.


## 2026-11-10 update — Telnyx cancelled, stack parked

Telnyx was cancelled after a sudden pricing change; the `+1 916 270 1051` number
was never called. Activation was removed from production (`phone_numbers`,
`phone_enabled`, `managed_phone_setups`), the pbx/bridge containers were stopped,
and the public SIP/RTP ports therefore close. The Asterisk stack itself is
installed and verified and is **carrier-agnostic**.

Safety: the base `compose.yml` keeps the phone network internal with no published
ports; `compose.public.yml` is the explicit override that publishes UDP 5060 and
10000-10099 and allows egress to the carrier. Two latent issues were fixed while
parking it: owner SMS now falls back to `tenant.notify_phone` when no managed-phone
row exists (previously only the email sent), and the public ports are no longer
the default.

### What a replacement SIP supplier must provide

- An inbound voice DID (an NZ number keeps forwarding rates local).
- SIP trunk with IP authentication (allowlist `152.42.239.240`) or registration
  credentials — the renderer currently emits IP-auth endpoints; registration is a
  small addition once the supplier is chosen.
- UDP 5060 with G711U/G711A; G722/G729 optional.
- The supplier's SIP signalling range for `source_cidr` and media ranges for the
  firewall.
- Stable per-minute pricing.
