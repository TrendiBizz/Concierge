> Implementation update: the integrated AudioSocket bridge is now built and verified with actual Asterisk and live Grok. See [verification](ASTERISK_GROK_VERIFICATION_2026-11-09.md). This supersedes earlier proposed WebSocket/ARI implementation details below. Carrier activation remains separate.

# Independent business systems inside Concierge — phone integration

9 November 2026. Design from source inspection and primary-source research; not an implemented or carrier-tested phone connection.

## Binding product requirement

Concierge provisions and operates a completely separate business system for every customer. Each system has its own website ingestion and knowledge, helpbot, Grok receptionist configuration and sessions, public phone number and ingress route, CRM, conversations, recordings, messaging destinations and credentials, owner access, settings, consent, limits and lifecycle. No business can read another business's information or operate its tools. Shared hosting or software must not merge these systems. This requirement does not by itself prescribe one physical server per business.

Provisioning must create the business identity first, bind the customer's verified website and channels to it, ingest only that website's approved content, and expose that business's owner portal and helpbot. Phone answering resolves the business through a trusted provisioned route before loading knowledge or creating a Grok session. The model and caller cannot select or change the business identity. Missing or contradictory routing fails closed.

## Selected free software

[Asterisk](https://github.com/asterisk/asterisk) with the [official WebSocket examples](https://github.com/asterisk/asterisk-websocket-examples) is the recommended telephony base. See [research](GITHUB_TWILIO_REPLACEMENT_RESEARCH_2026-11-09.md) for license checks, alternatives and primary sources. It removes Twilio software dependence. Hosting, existing Grok API usage and telephone network access remain separate. No reviewed GitHub software establishes free global cellular ingress from an ordinary mobile subscription alone.

Per-business flow:

`business's existing number → verified business-specific carrier/PBX route → Asterisk → business-bound Concierge call → business's Grok receptionist and website knowledge → business's CRM/transcript/consented recording → business's saved notification destination`.

Use a unique authenticated SIP route or forwarding destination for each business. The public number stays with its owner. A single shared forwarding number is only eligible where actual provider testing establishes trusted original-destination metadata. Caller ID identifies the caller, not the business. Never transfer back to an unconditionally forwarded number and create a loop.

## Existing code and precise changes

| Area | Existing source | Required integration |
| --- | --- | --- |
| Independent records and knowledge | `api/app/schema.sql`, `rag.py:22`, `convo.py:29`, `tools.py:234` | Existing tenant IDs scope chunks, conversations and tools. Preserve and audit that boundary through ingestion, calls, recordings, notifications and owner access. This inspection is not proof of complete isolation. |
| Business phone setup | `managed_phone.py:19`, `api/static/owner.html` | Owner number and forwarding choice already saved. Add a tenant-bound ingress identity, provider credentials reference, country/carrier capability, verification and recovery state. Saving a request must not activate answering. |
| Grok configuration | `voice.py:24`, `phone_sip.py:93` | Reuse per-business prompt, tools, transcript persistence and limits. Add Asterisk media transport: existing SIP code attaches to an xAI-owned call ID and cannot simply accept raw Asterisk audio. |
| Call identity | `phone_sip.py:197`, phone_numbers/phone_calls tables | Introduce trusted Asterisk ingress configuration and call/channel identity binding. Persist business ID with every call and enforce it through every tool and media event. Reject duplicate/ambiguous routes. |
| Audio bridge | New separate service/module | ARI controls channels; incoming media WebSocket connects using ARI-established channel identity. Negotiate/convert PCM rate and endianness explicitly to Grok's supported format; implement barge-in cancellation and playback queue flushing, disconnect cleanup and time limits. No public ARI exposure. |
| Recording and CRM | `voice_records.py:54`, `:79`, `:180` | Reuse business-scoped storage/finalization through a trusted server interface. Explicitly start recording after recording choice. MixMonitor WAV needs validated format support or conversion to current accepted webm/ogg/mp4. Persist complete transcript and recording before notification; do not use browser bearer tokens as server authority. |
| Business-owner notification | `voice_records.py:113`, `:184`, `managed_phone.py:19` | Current recording flow emails notify_email; owner-recipient delivery only recognizes email. Add a separate operational owner SMS notification to that business's verified owner_number, with durable deduplication and delivery status. Caller follow-up remains a separate consented action. |
| SMS credentials | `sms.py:31`, `:98`, `device_sms.py`, `outbox.py` | Preserve scoped native-device queues. SMS Gateway credentials are currently global: introduce per-business credential/device bindings before using customers' own SIM senders. Never silently send one business's texts using another business's sender. |

Native carrier voicemail injection is not universally available. Provide each business with its own voicemail recordings inside Concierge and a private expiring link in its notification; integrate a carrier voicemail inbox only when that carrier exposes a verified interface.

## Onboarding for each independent business

1. Create its own system and owner access; verify its website, ingest its content and preview its helpbot/receptionist.
2. Enter and verify its existing public phone number and owner delivery destination; select country/carrier and busy/no-answer/all-call handling.
3. Provision its own route. Connect an existing compatible SIP/PBX service, or display tested carrier-specific forwarding instructions to its assigned destination. Do not invent universal carrier codes or promise silent carrier configuration.
4. Run an actual inbound verification call, bind it to this business, exercise Grok conversation, save its enquiry and deliver its owner notification. Verify actual receipt.
5. Show Connected only after the route and delivery pass; retain restore-forwarding instructions and a working fallback. Unsupported routes stay explicitly unconnected.

Customers should never operate Asterisk or supply developer tokens. An optional Android SIM gateway or Mac connector is a transport for compatible installations, not a prerequisite imposed on every business. An owner receiving a notification does not need to send it from their own SIM; receiving and sender identity are separate configuration requirements.

## Acceptance and current limits

Two businesses must call concurrently with distinct website facts and receive only their own greeting, answers, CRM entry, transcript, recording and notification. Cross-business IDs, tools, media frames, delivery destinations and owner access must be rejected. Test caller barge-in, abrupt hangup, retries, exactly-once finalization, actual SMS receipt, recording refusal, failed trunks and restored forwarding.

[Asterisk issue2194](https://github.com/asterisk/asterisk/issues/2194) reports outbound WebSocket v() parameter leakage between calls. Do not use those URI parameters as business identity. Use application-initiated incoming media plus independent ARI channel binding, and prove concurrent isolation before production.

No new carrier account, number purchase, call, message, app-code change or deployment was performed for this research. The separately running implementation chat owns the current recording/CRM deployment; this plan does not certify its live telephone ingress. Next implementation milestone is an isolated Asterisk-to-Grok adapter and two-business SIP acceptance harness, followed by a real existing-provider mobile route test. A software SIP test cannot certify the customer's cellular forwarding path.
