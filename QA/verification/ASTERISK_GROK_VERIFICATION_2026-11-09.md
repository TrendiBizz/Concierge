# Asterisk → Grok → independent Concierge businesses — verified 9 November 2026

## Implemented

`api/app/asterisk_bridge.py` is a separate private AudioSocket service using the existing Grok realtime API, knowledge/tools, conversations, enquiries and outbox. No Twilio or new voice platform dependency. Each business has an explicit, unique ingress destination and listener, mapped before creating its Grok session. Customer and model input cannot select another business. Verified carrier identity plus exact DID routes shared SIP ingress; missing/unknown destinations are rejected. Existing public mobile numbers can remain with their carrier and forward to these destinations once supplied by a telephone provider.

Controls include trusted private PBX peers, initial UUID validation, global replay rejection, per-business enablement/telephone authorization/daily limits, live authorization rechecks, ten-minute call cap, bounded audio and tool output, paced playback and barge-in. Business context and CRM/tool calls stay fixed throughout the call. Caller ID is not available in AudioSocket's UUID protocol; Grok asks for callback details.

On completion, full caller turns stay in the business conversation and enquiry. One owner SMS is queued to that business's configured owner number, optional email goes to its notify address, and the supported Twenty voice.completed integration event is queued. Existing workers/credentials perform delivery; no new transport is invented. This adapter transcribes messages and explicitly discloses that telephone audio is not recorded. It does not implement a carrier voicemail deposit or attach telephone audio to browser recordings.

## Verification actually performed

- Full API suite: **119 passed in 4.13 seconds**.
- Five bridge regressions cover concurrent isolated business audio/transcript/tool contexts and barge-in; cumulative transcript corrections; unique ingress/listeners; shared-source exact DID routes and unknown rejection; oversized/truncated frames; silence injection without losing partial packet reads.
- Disposable PostgreSQL integration: two separate businesses, actual TCP bridge and mock Grok; correct independent CRM/outbox records and cross-business replay rejection passed. No external messages.
- **Actual Asterisk 20.6.0 + live Grok realtime API**, two concurrent synthetic telephone legs: Alpha Workshop and Beta Florist each spoke their own greeting, received an approximately ten-second synthetic caller message including reference seven-four-two, returned spoken goodbye and ended through the bridge. Both full messages persisted to the correct business CRM; each owner SMS was queued once. Returned speech audio and captured synthetic test-leg WAV files were checked. Both calls completed. Actual xAI session negotiation confirmed PCM16 mono 8kHz input/output.
- Live harness: `QA/verification/asterisk_live_grok_integration.py`; database harness: `QA/verification/asterisk_db_integration.py`. The live harness requires the disposable fixture database populated by the database harness, Docker, macOS say and ffmpeg, and uses the existing Grok credential without exposing it to Docker or logs. Real API usage occurred. **Carrier calls: zero; external SMS/email: zero.**
- Generated dialplan loaded in actual Asterisk; a synthetic Local channel executed the generated timeout and kernel UUID expression, producing a valid UUID before reaching AudioSocket. This isolated probe had no bridge DNS/service; media success is established by the separate live harness above.
- Compose configuration validation and git whitespace validation passed. Config generator produces private Asterisk dialplan and source-matched PJSIP routes.

## Bugs caught by live testing and fixed

1. Grok emits successive cumulative input_audio_transcription.completed events using the same item ID. Ignoring repeated IDs truncated messages after their first words. The bridge updates that same scoped message row when cumulative text changes, and ignores exact duplicates.
2. Silent Asterisk endpoints can stop emitting media during Wait. Grok needs silence samples to detect the end of a caller turn. The bridge supplies real-time PCM silence while preserving an outstanding partial frame read; the live calls now produce a response after the message and terminate cleanly.
3. The installed Asterisk has no UUID() dialplan function. Generated dialplans use the Linux kernel random UUID source with a fixed trusted command and filtering instead.

## Phone activation boundary

This implementation is local and tested; it has not changed the production deployment, Spark forwarding or carrier accounts. It does not by itself provide a publicly dialable number. The forwarded-mobile acceptance test and an actual owner delivery receipt remain unperformed. Software success above must not be represented as a live Spark call or delivered text.

For each business, activation requires its own verified destination (or a carrier-guaranteed preserved original destination), provider connection, business authorization and owner delivery transport. A single shared forwarding number cannot safely identify arbitrary businesses when carriers strip the original destination; never infer the business from caller ID or default to the first business. Carrier coverage, forwarding and messaging rules differ by country; the adapter has no country-specific voice dependency, but no universal free PSTN/SMS guarantee follows.

## Concrete NZ provider research

[2talk pricing](https://www.2talk.co.nz/pricing) currently lists GO FREE at $0 ex GST, one NZ 028 number and one trunk. However, [2talk terms section 3](https://www.2talk.co.nz/terms) requires a credit balance to use services; a zero-cost activation cannot be guaranteed. No account, number, payment or purchase was created. Its [official PJSIP guide](https://support.2talk.co.nz/asterisk-co) supports Asterisk using lyra.2talk.co.nz and the line number/password. [Register trunk documentation](https://support.2talk.co.nz/register-trunks-outbound-trunking) describes explicit preserved DDI configuration; validate real received destination before activating a shared trunk. [Media guidance](https://support.2talk.co.nz/lyra-media-ranges-firewalls) documents separate RTP sources; do not assume the SIP proxy IP also carries media. [Spark call features](https://www.spark.co.nz/help/mobile/manage/mobile-call-features) documents forwarding to another telephone number. No Spark setting was changed.

Deployment instructions: `scripts/asterisk/README.md`. The default stack exposes no public SIP, RTP or AudioSocket ports. A real provider needs its verified authentication, destination format, media/NAT/firewall configuration and a real forwarded call test before activation. Registration secrets belong only in private deployment files, never source control.

Temporary fixture database and probe PBX containers were removed after verification. Cached Asterisk image and synthetic audio/logs remain local for inspection.
