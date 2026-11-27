# 2026-11-27: "ACTION NEEDED: no reply yet to Ruben" for a thread Jo was already answering

## Symptom
Jo got `ACTION NEEDED: no reply yet to Ruben` (tenant trendi-oauth-staging, 27 Nov 15:46 NZDT, and the
same notice on 25 Nov). Ruben's messages were replies to Jo's own link-swap outreach email; the 27 Nov one
was "thanks Jo, appreciate you adding the link ... our link is live". Body also read "A email enquiry".

## Cause
Concierge only sees mail coming in. Jo answers from Gmail, so nothing tells Concierge he replied: both
Ruben leads (848da280…, d2220071…) stayed `status='new'`, and `owner_issues.sweep_unanswered` chased each
after 120 min (`sla_alerted_at` 2026-11-25 21:27 UTC and 2026-11-27 02:46 UTC). Wording: `"A " + label`.

## Fix
- `api/app/owner_threads.py` (new): an inbound email that replies (In-Reply-To / last References) to a
  message that is not one of the sender's own earlier emails, from someone Concierge has emailed nothing in
  30 days, is a thread the owner runs from their own mailbox. Earlier `new` email enquiries from that
  address become `contacted`; this enquiry gets `leads.owner_thread = true`. The enquiry alert still goes.
- `api/app/sla.py` `overdue()`: `AND NOT owner_thread` (so no "no reply yet" chase, no SLA list entry).
- `api/app/inbound_email.py`: calls `owner_threads.note` after capture (failure is logged, mail kept);
  audit detail gets `owner_thread: true`.
- `api/app/schema.sql`: `leads.owner_thread boolean NOT NULL DEFAULT false` (applied at API start).
- `api/app/owner_issues.py`: "An email enquiry" / "A text message".
- Not inferred when Concierge did email the customer (the parent could be ours): chase stays on.

## Proof
- `api/tests/test_owner_alert_postgres.py`: `test_reply_to_the_owners_own_email_is_not_chased`
  (Ruben replay: first lead -> contacted, second flagged, sweep raises 0), `test_owner_thread_needs_evidence`
  (no reply header / reply to own mail / Concierge emailed them -> not flagged), article check.
- That file had been skipping all 25 tests in the full suite (hard-coded port 55432); `_dsn` now uses
  `TEST_DATABASE_URL`, and all 28 run and pass.
- Mutation: dropping `AND NOT owner_thread` -> 1 failed; ignoring the own-mail parent check -> 1 failed.
- Full suite: 1964 passed, 19 skipped.
- The two existing Ruben leads already had their one notice each (deduped per enquiry); they are not re-sent.
