# Finish Concierge — authoritative handoff, 9 November 2026

Updated after deployment and recovery verification, 12:24 NZDT. This replaces earlier prepared/not-deployed recording statements. The complete incoming-telephone workflow is still unfinished.

## Objective and constraints

User requested a handoff followed by completion: incoming call → business-specific Grok conversation → actual audio and full transcript attached to the correct CRM enquiry → requested recording link or text delivered to the consenting recipient. Finish the existing product, preserve working integrations, and avoid repeated account questions.

Existing service: Spark mobile +64 27 881 7368, iPhone linked to this Mac, existing xAI team. No SIP/PBX/Twilio/Telnyx account. No new paid carrier, subscription, number purchase, credit purchase or forwarding activation authorized. Preserve native per-SMS Send confirmation. Prior finite test-call/SMS/social approvals are exhausted. Browser/synthetic audio tests are not cellular-call verification.

Product: /Users/jo/work-staging/concierge-integration, branch integration/concierge-v1. Website: /Users/jo/work-staging/trendi-site-web, branch concierge-site. Current active pinned chat: 01a1bd52-4874-70a1-a709-50c21ff28d89, “Finish Concierge calls, recording and CRM”. Continue this objective after compaction using /Users/jo/.codex/CONTINUITY.md. Cross-repo checkpoint: /Users/jo/.codex/task-state/01a1bd52-4874-70a1-a709-50c21ff28d89.md.

## Deployed and verified

- Website Grok voice uses the existing xAI account. Previous real API/audio probe passed; this is separate from telephone answering.
- Actual website voice recording is implemented: optional unchecked visitor choice; MediaRecorder mixes microphone and played Grok audio; private existing PostgreSQL storage; tenant/session capability enforcement; 12MB/session, 100MB/business, ten-minute session limit; 30-day audio retention.
- CRM enquiry links the saved transcript and actual audio. Contact enrichment reuses one voice enquiry. Completion queues one owner notice and one Twenty event atomically. Owner portal supports authenticated playback/download and explicit 24-hour recording links.
- New website-only request_conversation_copy tool remembers the caller’s chosen format/channel only after contact capture, contact permission and recipient readback/confirmation. It requires a verified same-tenant/same-conversation voice capability. Finish queues delivery after audio/transcript storage, with stable deduplication. Queue status never claims receipt. Native SMS Send confirmation remains.
- Fixed final caller transcript loss, repeated tool/transcript events and microphone/socket stop races. Added tenant-scoped owner transcript endpoint.
- Website headers previously blocked the microphone and xAI WebSocket. Deployed microphone=(self) and connect-src wss://api.x.ai; the browser’s ordinary microphone permission prompt remains. Other policy directives unchanged. Live homepage returns the corrected headers.
- Public homepage, widget and owner UI return200. Private audio without owner authentication returns401; upload/finish without session capability403; unknown recording share404. API and CRM healthy; all 11 production services running.

### Correct tenant and existing authorization

The LIVE widget and owner workspace is **trendi-oauth-staging**, public key pk_8y_wsHO4StqCzd0yc2QNEKp0. It already had telephone/call_recording/sms_read/sms_send/social declarations from 7 November plus email grants. These were preserved. Global VOICE_RECORDING_ENABLED is now true, so its optional recording checkbox is available and unchecked. A telephone declaration is not an active route.

**concierge is the archived prototype**, whose only grants are email_read/email_send. Earlier continuation checks confused it with the live widget tenant; do not repeat that mistake. No business authorization was newly granted in this continuation.

The pending async question offered recording/SMS enablement plus one new recording-link SMS test to Jo. The enablement part is unnecessary for the canonical tenant because the grants already exist. No answer was received and no new test SMS/job was created. Only perform that finite test if Jo explicitly approves it; keep the native Send dialog and exact approved text. Do not send based on historical approvals.

### Evidence and tests

- Full Python API suite: **114 passed**, latest 4.27 seconds. Node final-caller-transcript regression and widget syntax passed.
- Actual browser MediaRecorder fixture recorded 30,652 bytes of valid WebM, mixing a genuine Grok Ara test sentence with synthetic microphone input. It is explicitly not a carrier call.
- Owner browser fixture verified private playback, sharing, recipient/role restrictions and logout cleanup, with no JS errors.
- Disposable database test passed actual browser audio storage/read/share; transcript CRM linkage; one enquiry across two captures; one completion notice; deferred caller-requested delivery; retry deduplication; expiry and purge. Disposable DB removed; no customer data or messages changed.
- Reusable QA: voice_recording_db_check.py, voice_recording_browser.cjs, owner_recording_browser.cjs, voice_transcript_events_test.cjs under QA/verification.
- Live UI proof: QA/verification/voice-widget-deployed-20261109.png. Recording checkbox visible, unchecked. No microphone capture or real telephone call was initiated during this UI check.
- Post-deploy encrypted backup passed 8 November 23:23 UTC. Disposable recovery passed:29 Concierge tables, 121 CRM tables, social vault, uploads and settings; temporary restore container removed. Production volumes unchanged.

## Actual telephone blocker

Discovered xAI’s native Voice Agent Builder in the existing account. Official docs: https://x.ai/news/grok-voice-agent-builder and https://docs.x.ai/developers/rest-api-reference/inference/voice . Although xAI advertises an included number, this account’s console explicitly says:

> Your area does not support provisioning phone numbers. Use Twilio or Direct SIP instead.

Proof: QA/verification/xai-number-region-unavailable-20261109.png. This is account-level availability evidence, not a general claim about every country.

Existing xAI team Concierge fc021a82-2b63-40cf-b1fd-36e84f723a13 has saved agent agent_lQMmpdrJeJDBB7JO:
https://console.x.ai/team/fc021a82-2b63-40cf-b1fd-36e84f723a13/voice/agents/agent_lQMmpdrJeJDBB7JO

Only public business knowledge, web_search and end_call configured. No phone number assigned, no CRM/email connector, no credential granted and no forwarding activated. Initial onboarding auto-published; subsequent safeguard revision saved. Native call recording appears automatic, without a verified disable control; instructions now end immediately if recording is declined and never falsely claim recording was stopped/deleted. Verify actual platform recording controls before activating a telephone route. Native post-call UI offered only email conversation links; webhook/export integration is unverified. Balance observed $4.35, auto-topup untouched. No xAI telephone call made.

The ordinary Spark mobile service currently has no connected audio route to Grok. Phone CUA times out; owner-authorized AppleScript inspection was denied by macOS. The Mac connector’s synthetic Core Audio tap probe passed, but Phone input selection, real caller capture, two-way Grok audio and answer/hangup remain unproven. Do not present the Mac prototype as a seamless worldwide product. No supported ordinary-mobile-only answer API has been established by the evidence.

### Remaining acceptance

A genuine controlled incoming call must prove answering, business knowledge, two-way audio, caller recording choice, actual recording and full transcript in the correct enquiry, requested output delivery, safe hangup/human fallback and tenant isolation. This cannot be replaced by the passing browser/database fixtures. Investigate an existing-account/device route within the stated constraints; do not purchase a service or re-ask which paid provider to use.

SMS: outbound self-test was genuinely received, verified_at 2026-11-08T22:06:04.956013Z. Inbound SMS/Grok reply remains unverified because Jo has no second phone. Installed companion /Users/jo/Applications/Trendi Phone Connector.app, private /Users/jo/.config/trendi-phone/config.json and launch agent com.trendi.phone-connector. Preserve app identity/FDA and durable send journal. Existing /Users/jo/imessage-bridge-grok untouched.

## Production and rollback

VPS 152.42.239.240, root SSH with repo key Concierge and BatchMode/IdentitiesOnly/StrictHostKeyChecking. Secrets /opt/trendi/shared, credential files 600. Source /opt/trendi/releases/20261108-vps/product; compose --env-file /opt/trendi/shared/compose.env -f scripts/vps/compose.yml.

Current API image: **trendi-concierge-api:voice-recordings-delivery-20261109**, also :vps, SHA256 **acd62510b3530a01f212920f1fa9a7e0e4ecffd9ccca3099ff77d9cde41596d8**. Candidate /opt/trendi/candidates/voice-recordings-20261109 contains the exact selectively patched sources/Dockerfile/QA. Production source matches these deployed recording changes. Caddy recording routes validated and loaded; shared links available on chat and owner hosts.

Rollback image **trendi-concierge-api:before-voice-recordings-20261109** preserves prior transcript SHA 0fcce7458a82. Source/env/Caddy/website-header backup: /opt/trendi/candidates/before-voice-recordings-20261109. Restore old image/env/source if needed; recreate API/social together because social shares API network namespace. Restore/restart gateway only if reverting its routes. Website reads mounted site/_headers at startup: restore saved website-headers into the mounted website source then restart website if reverting those headers. Added recording schema is additive and can remain during rollback; preserve recorded customer data.

Local main.py/owner.html/schema.sql and Caddyfile also contain **unshipped managed_phone** preparation. Never bulk-deploy the dirty checkout. managed_phone.py/test and managed-phone routes/schema are not deployed and do not solve ordinary-mobile answering. Select from the clean remote candidate. Preserve unrelated untracked office-shots/tiktok-review. No commits in this continuation.

## Other outstanding work

Meta SocialSync 676274422041376 submission 1132925159709631 successfully submitted: all 6 permissions in review. Cloudflare disclosure corrected 18→131 countries/territories, reopened and verified. Restricted reviewer login/worker retained; global social publishing remains off. All finite approved posts published; no replay authorization remains. Preserve genuine original Desktop recordings privately.

Last verified provider gates: Google Business Profile case 7-0643000042292 pending allowlist/zero quota; LinkedIn Pages 266706827 application pending approval and organization grant; profile 266722540 publishing grant/test unproven; TikTok 7705532547380250645 Login Kit review pending, posting audit not approved; X 33619967 account OAuth/live test unproven and $0 credits. No purchase authorized. support@trendibizz.com mailbox remains uncreated; kiwi18@gmail.com remains the explicitly approved temporary Google consent support address. Do not recreate applications or change MX without evidence/authorization. Detailed provider IDs/history: SESSION_HANDOFF_2026-11-09_PROVIDER_ACTIVATION_VOICE_X.md.

## Continuity and browser cleanup

Automatic compaction settings saved previously; exact remaining-context telemetry is unavailable. Do not invent a meter or ask Jo to create sessions solely because the chat is long. Same objective stays in the same active pinned chat. Completed xAI and live-widget task tabs were closed; personal tabs preserved. Remaining old personal/provider tabs were not indiscriminately closed. No task form currently needs a browser handoff.

Next runnable work: read this file, verify pending user test approval, and continue only the unresolved telephone route/inbound-SMS/provider gates. The deployed recording/CRM work is finished and must not be rebuilt or described as merely prepared.
