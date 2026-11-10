# Concierge — current status, 10 November 2026 (19:30 NZDT)

Read this first. It supersedes the "next session" lists in the older handoffs.
The product is the **Python API on `main`**. Everything else is history.

## Decision: the Rust port is abandoned

**Do not continue the Rust port.** Owner decision 2026-11-10. Do not run
`scripts/rust-gate.sh` as a continuation requirement, do not add to
`concierge-stack/`, and do not treat the draft Rust PR as pending work. The
crates and the `rust/core-port` branch are reference material only; the running
product has always been the Python service. The auto-end tool no longer gates on
Rust (its Rust gate was removed and its test deleted); `pytest api/tests` is the
only gate.

## Repository and deployment state

| | |
| --- | --- |
| Workspace | `/Users/jo/work-staging/concierge-integration` |
| Branch | `main`, synced with `origin/main` (`git@github.com:TrendiBizz/Concierge.git`) |
| GitHub | **public** (made public 2026-11-10) — never commit secrets; `.gitignore` plus the checkpoint tool guard this |
| Tests | `PYTHONPATH=api pytest api/tests -q` — **506 passed**, 9.13s, run 2026-11-10 19:31 |
| Deployed image | `trendi-concierge-api:vps` → `51731df49bd3`; `healthz` 200 |
| Source vs deployment | running `/srv/app/main.py` and `booking.py` **byte-identical** to HEAD (verified 19:12) |
| Auto-commit safety net | launchd `com.trendibizz.concierge-checkpoint` runs `scripts/commit-checkpoint.py` every 5 minutes; log at `~/Library/Logs/concierge-commit-checkpoint.log`. `scripts/auto-end-session.py` now stages the workspace (`git add -A`) before its gates/commit/push (that step was missing from the first build). |
| Live businesses | `trendi-oauth-staging` (real: 28 chunks, calendar, hours 08:00–23:00 Mon–Fri) |
| Test-only tenant | `trendi-meta-review` — **fake review emails created during testing; not a customer, not outstanding work** |

## The seven-step customer workflow — status

| # | Step | Status | Evidence |
|---|---|---|---|
| 1 | Receive voice, text or email | **live** | Text re-verified 19:27 via `https://chat.trendibizz.com/api/v1/chat`: HTTP 200, answer drawn from the business's own manual (USD $400/month, 3-month minimum, NZ GST). Voice token re-verified 19:28: HTTP 200, xAI realtime WSS plus ephemeral token and the full tool set. Email ingress verified earlier with signature checking. |
| 2 | Identify the channel | **live** | Per-channel ingress rows; tenant marker and attendee verified on the real Google event. |
| 3 | Answer from the business's own information | **live** | 28 tenant-scoped chunks; text answer above quoted only that content; cross-tenant retrieval isolation proven in the throwaway database. |
| 4 | Forward the original enquiry to the owner | **live** | `enquiry-original:*` owner alerts delivered to `admin@trendibizz.com`; outbox shows `sent`. Owner SMS goes through the self-hosted device. The owner-alert throttle was re-found broken (see below) and fixed + redeployed 2026-11-10 19:37. |
| 5 | Optional enquirer acknowledgement, separate from owner alerts | **live (DB-verified)** | Offer queues nothing, confirm queues exactly one, decline queues nothing, kind stays `enquirer_ack`. No real person has received one yet — needs their consent. |
| 6 | Retain CRM dialogue, isolate businesses, dedupe retries, calendar + invitation | **live** | Two-business isolation and webhook replay dedupe proven in the throwaway database; live tenant messages persisted; bookings re-proven 19:25 (see below). |
| 7 | CRM Quotations create and retrieve | **live** | Create/retrieve verified per business with 0 cross-tenant leakage (2026-11-10 15:01 report). Not re-run today because it writes to production. |
| — | Cloudflare 403 on an automated probe | **characterised** | Only the case-sensitive literal `Python-urllib` user agent is refused; browser user agent, curl, Go and Googlebot get 200. Browser experience is normal (the 19:27 chat used a browser UA through the public edge). |
| — | Optional cellular telephone | **in progress** | Asterisk adapter (`api/app/asterisk_bridge.py`, `scripts/asterisk/`) verified with synthetic legs against Asterisk 20.6 and live Grok on 9 Nov. A Telnyx SIP connection `Trendi` now exists (active, IP connection). No real number, no real call, no delivered receipt yet. |

## Owner-alert throttle — re-found broken and fixed, 2026-11-10 19:37

The "54 owner SMS in one conversation" fix had a false friend: its SQL matched
`status IN ('queued','sending')`, but `outbox` rows are created with the schema
default `'pending'`, so the guard never fired in production. A rolled-back live
probe with the real schema queued **60 rows** for 30 turns (30 email + 30 SMS).

Fixed in `api/app/owner_notifications.py` to treat every undelivered state
(`pending`/`sending`/`awaiting_receipt`) as in-flight, with a regression test that
pins the status list to `schema.sql` (commit `a27f5ec`). Re-verified against the
real schema and, after deployment, with the deployed module: **30 turns → 2 owner
alerts** (one per channel). Rollback image
`trendi-concierge-api:before-owner-alert-throttle-fix-20261110`; source backup
`/opt/trendi/backups/sms-throttle-fix-20261110/`.

## Live booking re-check — 2026-11-10 19:25

Driven exactly as the assistant's tool drives it, against production and the real
Google Calendar, with owner/enquirer notification deliberately suppressed for the
probe so no external message was sent:

| Step | Result |
| --- | --- |
| readiness | `ready: True`, 5 open days, 30-minute slots, no reason |
| availability | 3 real slots returned for 2026-11-10 (21:30, 22:00, 22:30) |
| `book()` without `confirmed` | refused, `needs_confirmation: True`, read-back returned |
| `book()` with `confirmed=true` | `ok: True`, `calendar_state: synced`, `invitation_state: provider_requested` |
| Google event | present with attendee `recheck-20261110@example.com` and the correct tenant marker |
| cancellation | `calendar_state: cancelled`; live event count for the day = **0** (Google returns the cancelled event as a tombstone on GET-by-id, which is why a 404 assertion is the wrong check) |
| cleanup | 0 test conversations, 0 leads, 0 appointments, 0 new outbox rows |

## What actually remains

1. **Real inbound SMS** — no provider configured; routes return 503 by design. The
   paired device is online but `inbound_verified_at` is NULL. Needs a provider and
   a real inbound test. Optional for the website workflow.
2. **Real telephone call** — a genuine number on the Telnyx trunk routed to the
   Asterisk AudioSocket adapter, then a real forwarded call and owner receipt.
   Optional and separate from website voice.
3. **A real enquirer acknowledgement** — needs a real person's consent.
4. **Quotations live re-run** — done 2026-11-10 20:00: create/retrieve math and
   tenant scoping re-verified in a rolled-back transaction (2 × $100.00 + 15% tax
   → subtotal 20000¢ / tax 3000¢ / total 23000¢; cross-tenant count 0).
5. **Rust housekeeping** — close the draft Rust PR if desired. Not engineering work.

Nothing else is code-blocking for the live business. The earlier "second business
OAuth" blocker is void because `trendi-meta-review` is test data.
