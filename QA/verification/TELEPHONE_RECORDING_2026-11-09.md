# Telephone recording and caller copies — 9 November 2026

Implemented consent-gated AudioSocket recording in api/app/telephone_recording.py
and connected it in asterisk_bridge.py to existing voice session storage and
request_conversation_copy delivery. The server creates a phone-channel voice
session for the same conversation, using no browser-provided tenant context.

Grok asks recording permission. set_call_recording requires explicit confirmed
true and enabled true, global recording enabled and business authorization.
Capture begins only afterwards, using incoming and actually played PCM frames.
Withdrawal discards the in-memory recording. Revoked authorization blocks save.
Mono 8kHz PCM WAV is bounded to ten minutes (under12MiB); validated WAV format
is supported by existing private CRM playback/download/share endpoints.

On hangup recording saves before existing call finalization and requested-copy
queueing. Caller copies require saved contact permission and readback confirmation;
existing outbox/native Send confirmation remains. Queue does not imply receipt.
No automatic outbound callback, carrier voicemail deposit, or public ingress
activation is claimed.

Verification:
- Full suite126passed before adding final format-validation test; final focused
  recording suite3passed. py_compile and git diff whitespace passed.
- QA/verification/asterisk_recording_integration.py passed against real disposable
  pgvector/PostgreSQL and actual bridge protocol with mocked Grok: concurrent
  Alpha/Beta calls, unconfirmed request rejected, Alpha WAV saved in own CRM,
  Beta consent withdrawal removed audio, cross-business recording access404,
  correct confirmed caller recording-link SMS queued once, correct owner SMS
  queues, replay rejected. No real calls or messages. Fixture containers removed.
- Production modules and WAV schema verified; internal healthok. Production has
  zero enabled phone numbers, phone_receptionist_enabled=false. Thus no actual
  smartphone ingress exists. Bridge source included in API image but no bridge
  listener/PBX service or public SIP/RTP ports were activated.

Deployment: existing release /opt/trendi/releases/20261108-vps/product.
Changed voice_records.py/schema.sql and added asterisk_bridge.py and
telephone_recording.py. Backup source:
/opt/trendi/backups/telephone-recording-20261109/source-before.tgz
Rollback image: trendi-concierge-api:before-telephone-recording-20261109
Build log: /opt/trendi/backups/telephone-recording-20261109/build.log
Rollback image does not remove WAV recordings; preserve data if rolling back.

Real remaining dependency: a public carrier forwarding destination per business,
trusted SIP connection, followed by real forwarded-mobile and delivery acceptance.
The destination is platform infrastructure; customer phone/carrier stays theirs.
No service purchased, account created or carrier forwarding changed.
