# Flood protection — incident, audit of every outbound path, and what is now in place (2026-11-13)

## 1. The incident

An owner-alert email sent to `admin@trendibizz.com` routes back into the platform as an inbound
enquiry (Cloudflare Email Routing -> Worker -> `/api/v1/inbound/cloudflare`). That produced a new
"Email enquiry" alert to the same address, and so on. It was dormant while Brevo blocked the address.
Unblocking it (and clearing our own suppression row for a test email) started it: **76 alert emails in
about 20 minutes**, 60 junk drafts, 60 junk leads and 60 junk tasks. The escalation sweep deployed
earlier the same day made it worse (16 fallback emails sent, 39 jobs queued on the SMS phone device).
All of it was cleaned up by hand (backups in `loopfix_backup_*_20261113`).

## 2. Why we did not have this as a matter of course

1. **Limits were built at the entrances, not the exit.** Per-endpoint request limits exist (chat per IP
   and per session, inbound mailbox 60/hour, phone daily limits). Nothing measured what *left* the
   platform, per recipient or in total.
2. **Six code paths insert straight into the outbox** (`acknowledgements`, `email_secretary`,
   `email_drafts`, `asterisk_bridge` x2, `owner_notifications`), so a protection added to one path
   never covered the others.
3. **We had fixed this same class of bug twice, one path at a time.** A 30-turn chat once produced 54
   texts to an owner; the fix (`owner_notifications` throttle) only applies when a lead id is passed,
   and its first version "never fired in production" because it matched the wrong statuses.
4. **No loop detection on any channel, no global or per-recipient budget, no kill switch, and no alarm.**
5. **No test ever simulated a loop**, so nothing proved that a feedback path was closed.

## 3. What is in place now (all deployed 2026-11-13, tests: 789 passed)

| Protection | Where | Behaviour |
|---|---|---|
| Delivery-time guard | `flood_guard.check`, called from `outbox._deliver` for every email and text | Blocks (stores `skipped`, `flood_guard:<reason>`) when delivered counts reach: same recipient 8 / 10 min and 25 / hour; identical message 6 / 10 min (email subject) or 3 / 10 min (SMS text); one business 100 / hour and 120 / day email (40 / 150 SMS); global 150 / hour and 270 / day email (60 / 400 SMS). The 270 headroom matches the mail provider's 300/day free plan |
| Fails open | same | If the guard's own lookup breaks it logs and lets the message through: a broken safety check must never stop a real alert |
| Kill switch | `system_flags.outbound_paused`; `POST /admin/outbound/pause` and `/resume`; `GET /admin/outbound/status` | Pausing stops all sending at once (everything stays queued); status shows volumes against limits and what was blocked. Round trip proven live |
| Last-resort caps | `mailer.send_email` (10 / 10 min per address, 200 / hour overall), `sms.send_sms` (10 / 10 min per number), `events._post` outbound webhooks (60 / hour per business) | Catch anything that bypasses the outbox. In-memory, per process, reset on restart |
| No replies to robots | `email_secretary` and the outbox | Never auto-reply to `noreply`, `mailer-daemon`, `postmaster`, bounce addresses or out-of-office / undeliverable subjects |
| Own mail never re-enters | `mailer` marker headers (`Auto-Submitted`, `X-Concierge-Mail`) + `cloudflare_inbound.is_own_mail` | Mail we sent that routes back is dropped before it can become a draft, lead or alert |
| Escalation cap | `channel_health.escalate_failed_owner_alerts` | Newest first, 10 per sweep, max 3 fallbacks per business per hour |
| SMS AI replies | `sms_limiter` | 12 replies per contact per hour (was 30): limits bot-to-bot text loops |

## 4. Audit of every outbound or work-creating path

"Verified" means I read the code and, where stated, tested it. "Not audited" means exactly that.

| System | Entrance limit | Exit limit before | Exit limit now | Loop guard | Remaining gap |
|---|---|---|---|---|---|
| Owner alerts (email, SMS) | n/a | Per-lead throttle only when a lead id is passed | Central guard + kill switch | Own-mail guard | None known |
| Follow-ups, SLA, quotations, sales, voice records (`outbox.enqueue`) | n/a | None | Central guard | n/a | None known |
| Campaigns | Paced 60 email / 20 SMS per hour | Pacing only | Pacing + central guard | n/a | None known |
| Email auto-replies (`email_secretary`) | Per-mailbox 60 / hour | None | Central guard + robot refusal | Robot heuristics (address, subject) | Inbound `Auto-Submitted` header of other systems is not read; only address/subject heuristics |
| Inbound email | Mailbox 60 / hour; sender 10 / hour (quarantines, does not reject) | n/a | n/a | Own-mail guard (marker header; sender address when no raw message) | Sender limit only quarantines |
| Inbound SMS (Twilio, gateway, phone device) | 12 AI replies / contact / hour | None | Central guard (3 identical / 10 min) | STOP / HELP words only | No check for short-code or bot senders |
| Missed-call text-back | Per phone per day (existing) | None | Central guard | n/a | None known |
| Phone calls, AI path | `phone_daily_limit`, `voice_daily_limit` per business | n/a | n/a | n/a | None known |
| **Phone calls, ring-first** (built, not yet live) | **None** | n/a | n/a | n/a | **Rings the owner before the AI path, so the daily limits do not apply: a flood of calls to the number would ring the owner's phone without limit. Must add a rings-per-hour cap and a concurrency cap, tested on a scratch Asterisk, BEFORE the Pukeko cutover** |
| Outbound calls (take-over, listen-in) | Owner-initiated only, no autodial | n/a | n/a | n/a | Rate limits on those admin endpoints not audited |
| Outbound webhooks (`lead_webhook_url`) | n/a | None | 60 / hour per business | n/a | None known |
| Twenty CRM bridge (outbound HTTP) | n/a | Own retry queue | Unchanged | n/a | Volume caps not audited |
| Social publishing (Rust service) | n/a | Not audited | Not audited | n/a | **Not audited in this pass** |
| Brevo webhook (bounces) | Signed | n/a | n/a | n/a | Volume limits not audited |
| Chat widget, voice tokens | Per IP per minute, per session per day, daily voice limit | n/a | n/a | n/a | None known |
| Network (SIP, SSH) | SIP restricted to the carrier; fail2ban | n/a | n/a | n/a | Done earlier this session |

## 5. Still to do (in priority order)

1. **Ring-first caps** (above) before the Pukeko cutover.
2. **An alarm, not just a switch:** have `scripts/vps/healthcheck.sh` call `/admin/outbound/status` and warn
   when anything was blocked or hourly volume passes 60% of a limit; tell the operator by a channel
   that cannot loop.
3. **End-to-end loop test on staging** with the kill switch ready: send one alert to an address that routes
   back in, and confirm it is dropped and nothing repeats. (Not done: it needs real email.)
4. Read inbound `Auto-Submitted` / `Precedence` headers from other systems and hold auto-replies.
5. Audit the social publishing service, the Twenty bridge and the Brevo webhook for volume limits.
6. A Brevo daily-quota alert (300 / day on the free plan).
7. Drop the `loopfix_backup_*_20261113` tables once the cleanup is accepted.

## 6. Operating it

```
# status (read-only)
curl -s -H "X-Admin-Token: $ADMIN_TOKEN" http://127.0.0.1:8000/admin/outbound/status
# kill switch
curl -s -X POST -H "X-Admin-Token: $ADMIN_TOKEN" http://127.0.0.1:8000/admin/outbound/pause
curl -s -X POST -H "X-Admin-Token: $ADMIN_TOKEN" http://127.0.0.1:8000/admin/outbound/resume
```
Rollback of this change: image `trendi-concierge-api:before-20261113-floodguard`, files in
`/opt/trendi/backups/api-20261113f/`.

`admin@trendibizz.com` is still suppressed for the staging tenant (re-suppressed during the incident).
Delete that `email_suppressions` row only when you want alerts to it again; the loop guard and the caps
now protect against a repeat.

## 7. Update, later the same day: the gaps in section 5 are closed

Tests: API suite **798 passed** (789 before). Deployed and verified live; rollback image
`trendi-concierge-api:before-20261113-caps`, files in `/opt/trendi/backups/api-20261113g/`.

| Gap | Now | Evidence |
|---|---|---|
| Ring-first had no limit | The dialplan rings the owner only while: fewer than **12** owner rings this hour, fewer than **3** from this caller this hour, fewer than **2** rings in progress. Over any limit the call goes straight to the assistant. Counters are AstDB keys per hour. Tunable per route (`max_per_hour`, `max_per_caller_hour`, `max_concurrent`) | Proven on a **scratch Asterisk with no network and a dummy number**: one caller x6 calls -> counter stopped at 3; 15 different callers -> hourly total stopped at 12; with 3 rings in progress a 4th went straight to the assistant (`rf_skip` -> `Answer`). 9 unit tests |
| Twenty CRM bridge | 600 events / hour / business (in-memory); already limited to one authorised tenant and a retry queue | tests; code read |
| Brevo webhook | 120 calls / minute (in-memory); already needs the shared secret and rejects payloads over 100 KB / 500 events | code read |
| Social publishing | Writes capped at 120 / 10 min (in-memory) at the single `_request` choke point; the service itself is human-approval based | code read |
| No alarm | `healthcheck.py` now has `outbound:guard`, `outbound:paused`, `outbound:blocked`, `outbound:volume:<channel>` checks. The existing 5-minute cron healthcheck emails the operator once per condition (de-duplicated, 6-hourly reminder); details carry no counts so mail is not repeated | Live check returned `ok`; cron path confirmed |

Still open (honest list):
- The caps on Twenty, the Brevo webhook and social writes are **in-memory per process**: they reset on restart
  and were not individually exercised live (they were code-read and unit-tested only).
- Ring-first is still **not live**: the Pukeko cutover waits for the owner to authorise telephone answering.
- The healthcheck's operator email goes to `HEALTH_ALERT_TO`; confirm that address is the one you want.
- Auto-reply handling still reads address and subject heuristics, not the other system's `Auto-Submitted` header.
