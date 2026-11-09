# Finish each business's Concierge secretary — authoritative handoff

9 November 2026. This scope supersedes earlier handoffs that made cellular call
forwarding, Asterisk, a receiving DID or Spark a prerequisite for Concierge.

## User's complete requirements

Each subscribing business sets up its own private portal/workspace, business
information, website and owner contact number/email. Every business has its own
knowledge, Grok receptionist/help bot, enquiries, CRM, calendar and quotations.
Use the existing paid Grok Voice account for website voice.

1. A call, text or email comes into that business's customer portal on Concierge.
2. Identify its channel: answer a voice call, reply to text, understand email.
3. Answer the enquiry using that business's information and context.
4. Forward the enquiry to that business owner in its original form: voice
   dialogue/recording, text conversation or email, with useful context. Use the
   owner's configured phone/email destination; attach the same enquiry to CRM.
5. Ask the caller/texter/email enquirer whether they want an acknowledgement.
   Confirm the recipient/channel and send it if requested. Keep this separate
   from notifying the owner; an owner alert is not an enquirer acknowledgement.
6. Save the complete dialogue/text/email in CRM and apply the appropriate contact,
   enquiry, task and appointment changes. When an appointment is agreed, check
   availability, create it in the owner's connected calendar, send the enquirer
   an invitation and retain the booking data in CRM. Handle timezone, retries,
   duplicate events and booking conflicts. A CRM-only appointment is not proof
   the calendar and invitation succeeded.
7. Add a Quotations section in CRM. Connect quotes to the business/contact/enquiry.
   Determine a sensible minimal workflow from existing CRM conventions and build
   it; exact quote statuses, pricing/tax rules and automatic sending were not
   specified by the user. Preserve draft/review control and accurate pricing.

Meaning of call: website/portal browser voice using the visitor's microphone and
internet/data. The owner's existing smartphone receives the resulting message,
recording link or email. Entering the owner's number sets a notification target;
it does not grant access to cellular calls or SMS APIs. Actual carrier SMS and
external email still use configured transports; verify those delivery paths.
Owner notifications and optional enquirer acknowledgements are distinct.

Spark belongs only to Jo's business. No customer's configuration inherits it.
Customer isolation applies to backend queries, tools, recordings, notification
recipients, calendars, queues and UI, not merely separate agent prompts.

## Execution command requested by the user

Paste this to resume:

> Continue implementing /Users/jo/work-staging/concierge-integration/QA/verification/HANDOFF_CONCIERGE_PORTAL_WORKFLOW_2026-11-09.md. Implement and verify all seven requirements as one business-specific portal workflow. Start doing the next incomplete step immediately. Continue through routine failures by diagnosing, fixing and retesting. Give concise progress updates while working; keep working when answering status questions. Complete every independently actionable item before requesting a genuinely missing input. For an unavoidable dependency, prepare the concrete integration and ask only for the smallest required action, with the recommended solution, while continuing other work. Finish with evidence of the working flow, committed and pushed code, and the verified deployment status. Preserve consent and existing permissions; never invent delivery, calendar success or test results. Stop promptly if I explicitly say STOP.

This is a continuation instruction, not an executable shell command or a claim
that a prompt can override tool limits or grant new purchases/messages.

## Workspace and Git

Repo /Users/jo/work-staging/concierge-integration, integration/concierge-v1.
Origin git@github.com:TrendiBizz/Concierge.git. Before this handoff commit local and
remote HEAD matched e36e527b2ae642ff2387c4dc496fd0c3d455030f. User explicitly asked
all Concierge code to be committed and pushed. Preserve unrelated office-shots,
tiktok-review assets and private keys/env files; do not stage those wholesale.
Read /Users/jo/.codex/RTK.md and CONTINUITY.md; checkpoint below. Do not spawn
agents without authorization. Continue this objective in the same chat unless
user explicitly asks a new chat. Handoff request does not authorize new thread.

## Existing implementation and real limits

- Website Grok voice/session, transcript CRM and browser audio-recording capture,
  tenant-scoped playback/download, expiring recording shares, confirmed caller
  text/recording-copy request and completion paths exist and were deployed.
  Existing browser recording and caller-copy evidence is in the verification
  scripts below. Queue insertion is not actual message receipt.
- Important gaps found on last read: OwnerBusinessProfile exposes notify_email
  but no owner notification phone. Generic automation._owner_alert sends email
  only. Website voice _finish_enquiry emails the owner but does not automatically
  queue owner SMS or include the recording itself/link. request_conversation_copy
  handles consenting ENQUIRER delivery, not the owner's website notification.
  Owner contact phone lives in managed_phone_setups only, an inappropriate
  dependency for website-only businesses. Build a clean business notification
  setting/path; retain existing transport permissions and device confirmation.
- Owner UI currently exposes mobile/SIP/Twilio setup prominently from the prior
  misunderstood scope. Make website secretary onboarding clear and standalone;
  preserve optional cellular features without making them prerequisites.
- Saving a website currently does not crawl/import knowledge automatically.
  Business-private knowledge upload exists. Verify and complete onboarding/site
  import safely rather than claiming website knowledge was loaded from a URL.
- Email ingress/review and SMS/device/outbox modules exist; inspect and test actual
  connection to the unified enquiry/owner/acknowledgement workflow. Native SMS
  Send confirmation was previously required and verified once by the user; old
  finite approvals are not permission to send more test messages. Incoming SMS
  end-to-end receipt remains unverified. No new paid service was approved.
- Booking/tools/calendar modules exist but the full cross-channel calendar+invite
  requirement has not been proven. Search existing implementation before adding
  duplicate machinery. Quotation keyword scoring exists; a CRM Quotations
  section was not found in the last search and remains to implement.
- Previous Asterisk work is optional retained code, not the core solution: private
  per-business AudioSocket/Grok bridge with consent-gated bounded WAV recording
  and requested copies. Its source is in API image; no PBX/bridge service or
  carrier routes activated. Production had zero enabled phone numbers and
  phone_receptionist_enabled=false. These do not block website voice.

## Deployment and verification evidence

VPS152.42.239.240, SSH root using repo-local private key Concierge with BatchMode,
IdentitiesOnly and StrictHostKeyChecking. Never print/commit key or env secrets.
Release /opt/trendi/releases/20261108-vps/product, Compose scripts/vps/compose.yml,
--env-file /opt/trendi/shared/compose.env. Secrets /opt/trendi/shared.

Latest deployed API image sha256:41f931b7f1e334119a5a3bbbcc3f8b8b45942f28a04119afca28155431d8a1c7;
container trendi-api-1 was healthy. Private /healthz returned ok; public /healthz
is intentionally404 at gateway. Owner UI https://concierge.trendibizz.com/owner-ui.
Backup /opt/trendi/backups/telephone-recording-20261109/source-before.tgz;
rollback image trendi-concierge-api:before-telephone-recording-20261109.
Earlier mobile setup backup /opt/trendi/backups/mobile-setup-20261109.
Latest deployed addition included voice_records.py/schema.sql and new bridge/
telephone_recording.py. Many current edits were deployed across earlier turns;
compare live/source deliberately before deploying a new batch.

Handoff preparation reran the full current suite: **127passed in4.42seconds**.
Python:
PYTHONPATH=api /tmp/concierge-venv/bin/python -m pytest api/tests -q
No physical handset test or complete seven-step acceptance has passed.

Evidence/scripts in QA/verification:
- voice_recording_browser.cjs, owner_recording_browser.cjs (mocked browser checks)
- voice_recording_db_check.py, voice_transcript_events_test.cjs
- TELEPHONE_RECORDING_2026-11-09.md and asterisk_recording_integration.py
- ASTERISK_GROK_VERIFICATION_2026-11-09.md (actual Asterisk+live Grok synthetic calls)
- MOBILE_CONNECTION_SETUP_2026-11-09.md (optional older cellular setup)
Disposable fixture containers removed; task browser tabs closed. Personal tabs
preserved. Nothing newly sent or purchased during handoff preparation.

## Resume sequence and completion criteria

1. Trace one website voice, portal text and email enquiry through existing code.
   Make an acceptance matrix for the seven requirements with actual evidence;
   start fixing gaps, not another research-only architecture proposal.
2. Complete business owner contact/preferences in onboarding, channel-specific
   owner delivery with recordings/transcript/email, optional enquirer ack,
   correct CRM linkage and stable retry deduplication across all three channels.
3. Complete calendar availability/booking/invite and CRM Quotations using existing
   modules. Keep business identity fixed server-side on every tool action.
4. Test two independent businesses concurrently, plus declined acknowledgement,
   recording consent, delivery failure/retry, foreign-record access, booking
   conflict and duplicate webhook/tool actions. Verify actual configured channel
   receipts/calendar effects where authorized; label mocks and queue checks.
5. Review diff and secrets, commit/push relevant code and evidence, deploy tested
   work with rollback, check health/UI and complete workflow. Update checkpoint
   with commit, deployed image and exact verified vs unresolved acceptance items.

A missing external permission is not a reason to abandon independent work.
Completion means all seven behaviors implemented and verified to their actual
integration boundaries; report only the exact remaining human action if real
receipt/calendar verification requires one. Never label the full service working
from passing unit tests alone.
