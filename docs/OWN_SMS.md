# Trendi SMS transports

Trendi uses its own smsgate and paired-phone transports as primary SMS systems for new and existing tenants. Hero is the landline for voicemail only; no Hero SMS credentials are needed. Existing voice/voicemail, email and chatbot configuration is unchanged.

The default `SMS_PROVIDER=smsgate` requires the existing gateway URL, username and password settings. Explicit `SMS_PROVIDER=none` still disables the global gateway. Tenant `sms_transport=device` selects the paired phone independently of that global switch. Existing Twilio support remains optional compatibility, with signed, account-bound delivery callbacks.

Outbox smsgate submissions commit a submission marker before contacting the gateway. Queue acceptance records the gateway identifier and leaves the row awaiting confirmation, rather than claiming delivery. Timeouts or malformed acknowledgements are held for reconciliation and never automatically resent. Missing confirmation is held after 24 hours. This change does not invent a gateway delivery webhook contract; its existing inbound HMAC implementation still needs validation against an actual device before claiming live verification. Paired-phone jobs retain their stable request keys, authenticated receipts and duplicate protection.

Do not clear submission markers or force resend without reconciling the existing gateway/phone result. Historical Hero submission markers remain eligible for stale reconciliation only; Hero sending code and configuration have been removed.

No real SMS, calls, purchases or new provider accounts were used to verify this correction.
