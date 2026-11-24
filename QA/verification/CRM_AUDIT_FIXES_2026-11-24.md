# CRM Deep Audit & End-to-End Remediation (24 November 2026)

## Scope
Full forensic audit and remediation across all inbound channels (phone, browser voice, voicemail, website chat, SMS, inbound email, Meta WhatsApp/Messenger/Instagram DMs, website enquiry forms), outbound customer/owner notifications, bookings & two-way calendars (Google Calendar, Microsoft 365, ICS), Studio CRM UI, integrations, and site copy.

Per owner instruction (Jo, 2026-11-24), **Tradify and Fergus** were removed from code, Studio, website copy, and tests (only Xero, Microsoft 365 Calendar, ServiceM8, Google Calendar, and signed Webhooks remain).

---

## Root Causes & Fixes

### 1. Customer & Owner Replies / Alerting (P0)
- **Email Secretary crash (`api/app/email_secretary.py`):** `process_once()` queried nonexistent column `in_reply_to` from `email_drafts`, causing `UndefinedColumnError` on every auto-reply job and leaving `outbox.lead_id` NULL.
  - *Fix:* Selected only existing columns (`message_id_hdr, references_hdr`), populated `outbox.lead_id` by looking up the email lead, and added structured exception logging.
- **Silent customer reply failures (`api/app/owner_issues.py`):** `sweep_reply_failed()` used `INNER JOIN leads` and omitted `approved_reply` & `enquirer_ack` from `CUSTOMER_REPLY_KINDS`, silently dropping failed customer email replies when `lead_id IS NULL`.
  - *Fix:* Added `"approved_reply"` and `"enquirer_ack"` to `CUSTOMER_REPLY_KINDS`, switched to `LEFT JOIN leads` with `to_addr` fallback and `lead_id or f"outbox-{id}"` anchor, and swept `site-enquiry:%` alerts in `sweep_undelivered()`.
- **Broken SMS circuit breaker (`api/app/owner_notifications.py`):** Checked only `"did not confirm"` while the Android SMS gateway writes `"never confirmed"`.
  - *Fix:* Matched `"did not confirm"`, `"never confirmed"`, and `"receipt missing"` (case-insensitive).
- **Stale `/owner-ui` links (`api/app/owner_notifications.py`, `api/app/owner_issues.py`, `api/app/webpush.py`, `api/app/enquiry_alerts.py`):** SMS, issue emails, and web-push alerts pointed owners to `/owner-ui` instead of `/studio/`.
  - *Fix:* Updated portal URLs to `/studio/` and appended `Open in Studio:` link to enquiry alerts.
- **National NZ/AU phone normalization (`api/app/casetimeline.py`, `api/app/acknowledgements.py`, `api/app/enquiries.py`):** `tenant_country_code()` ignored tenant timezone and `acknowledgements.py` omitted country code, breaking national numbers like `021...`.
  - *Fix:* Inferred default country code from `tenant["timezone"]` (`Pacific/Auckland` → `64`, `Australia/*` → `61`, `Europe/London` → `44`, `America/*` → `1`), passed it in `acknowledgements.py`, and normalized phones in `enquiries.capture()`.

### 2. Phone, Voicemail, Browser Voice, Chat, Email, Meta & Site Forms (P0/P1)
- **Rust shell tool call ID bug (`concierge-stack/core-rs/src/shell.rs`):** `Action::Tool { call_id, ... }` shadowed `state.call_id` with Gemini's function-call ID when posting to `/internal/voice/tool`, breaking phone caller context.
  - *Fix:* Renamed binding to `fc_call_id` so `/internal/voice/tool` receives `state.call_id` while `Bridge::tool_response` replies with `fc_call_id`.
- **Phone bridge & pause enforcement (`api/app/asterisk_bridge.py`, `api/app/routers/telephony.py`):** Enforced `tenant_pause.is_paused(tenant)` on inbound phone registration, voice tokens, and phone tool calls; passed `from_number` as `sender_phone` into phone tool calls; preserved structured `leads.message` on `finish()`, included both Caller & Concierge turns in owner alerts, recorded transcript on `casetimeline`, and emitted `call.completed` webhook; captured rate-limited inbound SMS in CRM before returning empty.
- **Voicemail (`api/app/voicemail_fallback.py`, `api/app/voice_records.py`, `api/app/missed_calls.py`):** Normalized voicemail caller IDs cleanly instead of prepending `+` to `021...`; allowed voicemail recording storage under `recording_consent=True` (`is_voicemail=True`); extracted contact details, reconciled `casetimeline`, emitted `customer.enquiry`, and triggered automation on voicemail finish; skipped voicemail calls in `missed_calls.decide()` to prevent duplicate missed-call SMS.
- **Browser voice (`api/static/widget.js`):** Added `pagehide` keepalive flush so closing a tab mid-call still persists transcript and triggers `/finish`.
- **Chat & attribution (`api/app/chat.py`, `api/app/enquiries.py`, `api/app/tools.py`):** Persisted `page_url` & `utm` on lead capture; backfilled `name`/`email`/`phone`/`consent_contact`/`page_url` and re-scored on subsequent turns; looked up lead phone/email in `run_turn_stream()` so `casetimeline.mark_replied()` marks chat events answered; extended phone alert hold to 630s.
- **Inbound email & manual replies (`api/app/inbound_email.py`, `api/app/email_drafts.py`, `api/app/chat_inbox.py`, `api/app/sms_inbox.py`):** Saved inbound email user turns in `messages`; linked `outbox.lead_id` on approved drafts; advanced `'new'` leads to `'contacted'` and called `casetimeline.mark_replied()` on manual email, chat, and SMS replies.
- **Meta & website enquiry forms (`api/app/meta_inbound.py`, `api/app/site_enquiry.py`):** Captured inbound WhatsApp/Messenger/Instagram DMs into CRM (`convo` + `enquiries.capture`); captured `/api/enquiry` submissions into `trendi-support` tenant CRM with linked `lead_id` on operator alert.

### 3. Bookings, Calendars & Self-Serve Manage Links (P0/P1)
- **Public `/booking/{token}` blocked by gateway (`scripts/vps/Caddyfile`):** `/booking/*` was missing from `@owner` route allowlist on `concierge.trendibizz.com` (returning 404).
  - *Fix:* Added `/booking/*` to `@owner` in `scripts/vps/Caddyfile`.
- **Self-serve & owner booking lifecycle (`api/app/booking_links.py`, `api/app/booking.py`, `api/app/automation.py`, `api/app/outbox.py`, `api/app/portability.py`):**
  - Added `POST /owner/appointments` (conflict check, case reconciliation, calendar sync, confirmation/reminders) and `PATCH /owner/appointments/{id}` (owner complete/no-show/cancel/reschedule with outbox cancel, calendar sync, webhooks).
  - Enhanced `GET /booking/{token}` with local business time and interactive Reschedule form; hardened `/cancel` and `/reschedule` with advisory-lock conflict checks, outbox reminder cancellation, owner alerts, calendar sync, and webhook events (`appointment.rescheduled`, `appointment.cancelled`, `appointment.no_show`, `appointment.completed`).
  - Included `booking_links.manage_url()` in `appt_confirm` & `appt_rem24`; enforced `consent_contact` on review-request emails; prevented SMS quiet-hours deferral from pushing `appt_rem2` past `starts_at`; raised daily slot cap from 12 to 48 and merged M365 busy intervals.
- **Two-way Google Calendar & ICS (`api/app/calendar_connection.py`, `api/app/ical.py`):** `sync_one()` now `PATCH`es existing Google Calendar events on reschedule instead of entering an infinite retry loop; ICS feed now includes `X-WR-TIMEZONE`, `LAST-MODIFIED`, `SEQUENCE`, and `STATUS:CANCELLED` for both `cancelled` and `no_show`.

### 4. Integrations, Social & CRM API / Studio UI (P1)
- **Integrations (`api/app/integrations.py`, `api/app/config.py`, `api/app/quotations.py`):** Removed `tradify` and `fergus` completely (`PROVIDERS = ("xero", "m365", "servicem8")`); added `m365_busy()`, M365 attendees + cancel/reschedule sync; added `mobile` phone to ServiceM8 and skipped blank turn-1 chat greetings; added 1 transient retry in `dispatch()`; emitted `quote.accepted` on manual acceptance too.
- **Social video publishing (`api/app/social/publishers.py`):** Routed Facebook videos to `/{page_id}/videos` (`file_url`) and Instagram videos to `media_type=REELS` (`video_url`) with container `status_code` polling.
- **CRM API (`api/app/routers/crm.py`):** Added `limit` (default 200, max 500) and inferred `currency` to `GET /owner/crm`; added `POST /owner/calendar/rotate-token`, `GET /owner/crm/leads/{lead_id}/events`, `GET /owner/webhooks/events`, and `POST /owner/webhooks/test`; enriched `POST /owner/crm/leads` with phone normalization, `casetimeline.reconcile()`, scoring, and webhook emission; fixed `GET /owner/contacts/{case_key}/timeline` to return `primary_phone`, `primary_email`, `assigned_to`, `company_id`, `notes`, `score`, `score_label`, and appointment `id`/`ends_at`.
- **Studio UI (`web/portal/src/CrmQuotes.tsx`, `App.tsx`, `Engage.tsx`, `Integrations.tsx`):**
  - Fixed blank appointment timestamps (`starts_at || start_at`) on Enquiries and Bookings.
  - Added lead score badges, click-to-call/email links, inline notes, stage/channel filters, stage history view, local-timezone `next_action_at` saved on blur, and dynamic tenant currency.
  - Added manual **Book appointment** form, **Complete / No-show / Cancel** actions, **Private calendar feed (ICS)** card with copy & rotate, and split opening-hours preservation in Bookings.
  - Wired `/owner/analytics/summary` into Reports; fixed `Engage` compose/calendar/posts segmented view; added Webhook Deliveries log & test ping in Integrations; handled `?integration=&result=` OAuth callback toast.
- **Website (`website/concierge.html`, `pricing.html`, `ai-office.html`, `ai-office-nz.html`, `seo.html`, `concierge.js`):** Removed Tradify and Fergus from all pages; updated SEO deposit button label to `Pay deposit, USD $499`; added `/contact` fallback navigation in `concierge.js` when widget fails to load on pages without a status banner.

---

## Proof
1. **Regression Tests (`api/tests/test_crm_audit_fixes_20261124.py`):** 10/10 passed; mutation-checked once (temporarily disabling the voicemail skip in `missed_calls.py` killed the test as expected, then restored).
2. **Full Python API Suite:** Verified against live test Postgres (`TEST_DATABASE_URL=postgresql://postgres:pw@127.0.0.1:55433/postgres pytest -q`).
3. **Rust Core & Parity Suite:** `cd concierge-stack/core-rs && cargo test` — all unit, 29 parity suites, and end-to-end shell test passed.
4. **Studio Build:** `cd web/portal && npm run build` (`tsc -b && vite build`) — passed cleanly.
5. **SEO Gate & Deploy Parity:** `python3 scripts/seo/site_seo.py check`, `./scripts/seo-gate.sh https://trendibizz.com` (`GATE RESULT: PASS`), and `KEY=./Concierge ./scripts/vps/verify-deploy.sh` (exit 0).
