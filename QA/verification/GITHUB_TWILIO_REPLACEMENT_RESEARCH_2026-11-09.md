> Implementation update: the integrated AudioSocket bridge is now built and verified with actual Asterisk and live Grok. See [verification](ASTERISK_GROK_VERIFICATION_2026-11-09.md). This supersedes earlier proposed WebSocket/ARI implementation details below. Carrier activation remains separate.

# GitHub Twilio replacement for Concierge — 9 November 2026

## Recommendation

Use **Asterisk + its official WebSocket examples + a small Concierge/Grok bridge** as the free software telephony base. This replaces Twilio's programmable voice software dependency. It does not create a free connection from every mobile network to the internet. A working existing SIP/PBX route or a carrier forwarding destination is still needed. No purchases, routing changes, calls, texts or production deployments were performed in this research.

Customer experience: customer keeps their phone and public number; Concierge connects a supported existing business phone system or gives carrier-specific forwarding instructions; a verification call proves correct routing, two-way Grok audio and message delivery before showing Connected. Customer does not operate Asterisk or enter developer credentials. This is an architecture recommendation, not a tested end-to-end cellular implementation.

## Candidates verified against primary sources

| Project | License / current state | Suitability |
| --- | --- | --- |
| [Asterisk](https://github.com/asterisk/asterisk) | [GPLv2; LICENSE explicitly discusses separate ARI/AMI/AGI applications](https://github.com/asterisk/asterisk/blob/master/LICENSE) | Recommended free base. SIP/PBX routing, recording and external media; a separate Grok bridge is needed. |
| [Official Asterisk WebSocket examples](https://github.com/asterisk/asterisk-websocket-examples) | Apache-2.0; Python asyncio/websockets | First-party reusable transport examples; not a complete Grok receptionist or PSTN carrier. |
| [Fonoster](https://github.com/fonoster/fonoster) | MIT; actively changing platform; README warns of major upgrades and breaking changes | Genuine open-source alternative, multitenancy and raw audio support; larger new stack than integrating an Asterisk bridge. No native Grok realtime implementation was located during this review. |
| [jambonz](https://github.com/jambonz/jambonz-feature-server) | Feature-server source MIT, but current complete self-host deployment requires production licensing | Official docs describe native Grok realtime, tool/event hooks and recording, but **not an indefinitely free production recommendation**. |
| [FreeSWITCH](https://github.com/signalwire/freeswitch) | [Core MPL-1.1; tree contains other component licenses](https://github.com/signalwire/freeswitch/blob/master/LICENSE) | Viable free PBX/media base; more custom transport/integration investigation needed for this repository. No reviewed first-party native Grok end-to-end implementation established. |

Asterisk `chan_websocket` carries binary call audio and handles framing/timing, TLS, silence and incoming/outgoing connections. It is available from 20.16/21.11/22.6/23.0. JSON control messages arrive with 20.18/22.8/23.2; select and pin a supported patched release rather than copying latest-doc features onto an older image. See [channel documentation](https://docs.asterisk.org/Configuration/Channel-Drivers/WebSocket/) and [official introduction](https://www.asterisk.org/asterisk-media-over-websockets/). Use ARI ExternalMedia (`transport=websocket`, `encapsulation=none`) or Dial WebSocket; bridge PCM to Grok's realtime WebSocket. [ARI channel API](https://docs.asterisk.org/Latest_API/API_Documentation/Asterisk_REST_Interface/Channels_REST_API/).

Asterisk can record the call via [MixMonitor](https://docs.asterisk.org/Asterisk_22_Documentation/API_Documentation/Dialplan_Applications/MixMonitor/). Recording must be explicitly started after the appropriate caller choice; stop/finalize it before attaching the finished file. Capture transcripts from Grok events separately. Do not assume the Voice Agent API records audio automatically.

Fonoster's current [README](https://github.com/fonoster/fonoster) exposes raw bidirectional audio in Voice Applications and signed per-call sessions. Its [SIP trunk guide](https://github.com/fonoster/fonoster/blob/main/docs-site/telephony/trunks.mdx) still requires carrier authentication, addressing and number formatting. Its [Compose entrypoint](https://github.com/fonoster/fonoster/blob/main/compose.yaml) describes NATS, Postgres, Routr, RTPEngine, Roomr, AppBridge, MinIO, API and dashboard. This is not a phone-only universal gateway.

## jambonz findings that change the recommendation

Current [licensing documentation](https://docs.jambonz.org/self-hosting/overview/licensing) requires a domain-bound self-host license: free evaluation is 30 days, normally ten concurrent sessions; commercial production requires purchase. MIT feature-server code does not establish that the complete current packaged service is free.

[Official llm documentation](https://docs.jambonz.org/verbs/verbs/llm) advertises `vendor: 'xai'`, `grok-voice-latest`, required `session_update`, fixed 24kHz PCM and tool/event hooks. However inspected GitHub `main` [llm/index.js at fa932596](https://github.com/jambonz/jambonz-feature-server/blob/fa932596836ea5c9706fb4e2e78b08424a77c1ef/lib/tasks/llm/index.js) has no `xai` switch case, and [openai_s2s.js](https://github.com/jambonz/jambonz-feature-server/blob/main/lib/tasks/llm/llms/openai_s2s.js) rejects vendors other than OpenAI/Microsoft. The repository API had no latest release entry. Native xAI is therefore documented, but not verified in the inspected public source or a deployable pinned release. Do not promise that cloning this repo provides that capability today.

## Reliable routing for each customer's own phone

A caller's **From** number identifies the caller, not the customer business. Forwarded call **To/Request-URI** can identify the shared answering destination. One central number therefore cannot safely identify every customer solely by To. SIP [History-Info (RFC7044)](https://www.rfc-editor.org/rfc/rfc7044.html) and [Diversion (RFC5806, historic)](https://www.rfc-editor.org/rfc/rfc5806.html) can carry redirection information, but their existence does not guarantee that each carrier preserves it.

Use a unique authenticated SIP route or a dedicated forwarding destination mapped to each tenant as the default. Shared destination optimization is allowed only after verifying the provider's forwarding metadata on actual calls. Trust metadata only from the authenticated/allowlisted trunk; reject unknown, duplicate, contradictory or ambiguous mappings. Do not let the caller/model choose a tenant. Asterisk [PJSIP configuration examples](https://docs.asterisk.org/Configuration/Channel-Drivers/SIP/Configuring-res_pjsip/res_pjsip-Configuration-Examples/) show provider endpoint/registration configuration; jambonz's [routing documentation](https://docs.jambonz.org/guides/using-the-jambonz-portal/advanced-concepts/inbound-call-routing) likewise combines carrier origin and called number.

**Important current Asterisk isolation issue:** [open issue2194](https://github.com/asterisk/asterisk/issues/2194) reports outbound WebSocket `v()` URI parameters being inherited or swapped across calls (versions20.20.1/22.9/23.4.1). Do not route by these parameters. Correlate media using ARI-created channel IDs and the connection's MEDIA_START identity, preferably application-initiated incoming media mode, with a concurrent isolation test. Pin a verified fix before relying on outbound URI metadata.

## Concierge integration boundaries

Recommended flow:

`customer existing public number → verified carrier/PBX route → Asterisk → authenticated per-call Concierge session → existing Grok realtime + tenant knowledge/tools → CRM enquiry + transcript + private recording → configured customer notification destination`.

Persist tenant-bound ingress ID, call ID, conversation ID, enquiry ID, recording ID and idempotent delivery state together. Owner notification destination and caller acknowledgement destination are separate. Confirm each recipient and requested content; a summary SMS can carry an expiring recording link. Reuse the existing consent/outbox/receipt machinery rather than adding direct sends from the model. Never transfer a call back to an unconditionally forwarded public number: it can loop.

A generic carrier voicemail inbox is not a universal write API. Store/play the voicemail in Concierge and deliver a link or use a specifically verified provider integration. Do not describe an audio file in Concierge as deposited into the customer's carrier voicemail.

## What can actually be free

Asterisk/Fonoster/FreeSWITCH software can be self-hosted without a Twilio platform subscription. Hosting, Grok API usage, public telephone numbers, PSTN call legs/forwarding and mobile SMS are distinct services. Existing plans may include some of these; no reviewed project supplies universally free global PSTN access or SMS. SIP-only tests between software endpoints can avoid a new carrier bill, but do not prove incoming cellular service.

For compatible Android customers, [SMS Gateway for Android](https://github.com/capcom6/android-sms-gateway) is Apache-2.0 software that sends/receives through an Android device and API; it still uses a SIM/plan, Android permissions and a device that remains available. It is an optional transport, not a solution for all iPhones or incoming cellular audio. Keep the existing Mac/SMS connector as another optional transport, not a mandatory customer requirement.

## Acceptance before customer activation

Two customers calling concurrently must receive different tenant prompts/knowledge and only their own records; missing or spoofed route metadata must fail closed. Test real forwarded and direct calls, caller ID, recording choice, barge-in, disconnect/fallback, two-way audio, complete transcript/audio, exactly-once recipient delivery, actual receipt, and restoring prior forwarding. Coverage is verified per country/carrier route; do not label unsupported combinations connected.
