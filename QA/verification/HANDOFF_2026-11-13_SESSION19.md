# Handoff — session nineteen — 2026-11-13 ~12:40 NZDT

Adds to `HANDOFF_2026-11-13_FINAL_SESSION18.md` (read that for procedures, access and the full open list; where the
two disagree, **this file wins**). Nothing here changes how to deploy, test or roll back.

---------------------------------------------------------------------------------------------------

## 1. Done this session (all verified)

| What | Detail |
|---|---|
| Text-first wording | Take-over alert, failed-transfer note and callback task say "reply by text or email" / "Reply to: …" when `owner_text_only`; other owners unchanged |
| Dedicated call number | `tenants.owner_call_phone` (settable like `notify_phone`). Take-over and listen-in ring it first, then fall back to `notify_phone` |
| Automated senders | Inbound mail with `Auto-Submitted` (not `no`), `Precedence: bulk/junk/list/auto_reply`, `List-Id` or `X-Auto-Response-Suppress` keeps its draft, gets **no auto-reply** (flag `automated_sender`) |
| Call failure reason | `phone_calls.failure_reason` filled for failed/disconnected Asterisk calls |
| Tests | **806 passed** (798 + 8 in `api/tests/test_session19_fixes.py`) |
| Deploy | API rebuilt, bridge restarted (plain `docker restart asterisk-bridge-1`; its code is bind-mounted from `$REL/api/app`). Rollback: image `trendi-concierge-api:before-20261113-s19`, files `/opt/trendi/backups/api-20261113h/` |
| Housekeeping | Tables `loopfix_backup_*_20261113` dropped after a verified dump (180 rows) to `/opt/trendi/backups/loopfix-20261113/loopfix_tables.sql`; secret-bearing scratch outputs `call_audit2.txt`, `verify2_out.txt` removed from `~/audit-20261113/` |
| Loop test | `~/audit-20261113/loop_test.sh` (standalone, **not run**). It sends ONE real alert and un-suppresses the staging address; run only when fewer than 8 emails were delivered to it in the last hour |

**Loop test result from session 18: SKIPPED** (68 delivered in the hour, guard correctly holding). Still unproven end to end.

---------------------------------------------------------------------------------------------------

## 2. Safety audit (13 Nov ~12:35 NZDT, read-only)

### Email
* OK: flood guard live and holding (limits 8/10 min and 25/h per recipient; kill switch off; nothing blocked). Loop guard deployed. 0 alerts in the last 10 minutes. One operator suppression row.
* OK: SPF present, DKIM for Brevo (`brevo1/brevo2._domainkey`) present, DMARC `p=quarantine`. SPF has no Brevo include, so DMARC passes on DKIM alone; fine, note for the `p=reject` step.
* Watch: **34 delivered to `admin@` in the last hour** (tail of the incident). The 25/h limit will block that address until it ages out (about 13:30 NZDT). `admin@trendibizz.com` still routes into the platform (design flaw open).
* 8 quarantined and 3 draft inbound emails await the owner. 3 failed sends in 24 h (reason not inspected).

### SMS
* **Broken:** the phone device has been silent since 2026-11-11 00:20 UTC, never inbound-verified. 38 SMS failed "Phone never confirmed send", 39 cancelled (storm cleanup), 46 `uncertain`. The staging tenant still has `sms_enabled` true, so **every staging alert still tries a text that cannot succeed (18 attempts in the last hour)**.
* Fix is the operator's: open the app on the phone, or set staging `sms_enabled` to false until it is back.

### Calls
* OK: 19 containers up, Hero registered, no active channels, host exposes only SSH publicly (plus SIP/RTP UDP by design), fail2ban running, swap exists (2 GB, unused; **the session-18 note "no swap" is wrong**), disk 37%, memory 3.9 GB free.
* **Unproven:** the SIP firewall rule for Hero's /24 has matched **0 packets** since it was installed, while 5,925 others were dropped. Hero registration works because it is outbound; **no inbound Hero call has crossed the firewall yet**. The real test call is the first proof.
* The DID `+64 9 243 1347` and the catch-all currently reach `trendi-oauth-staging` (telephone consented there); a real caller today gets the internal staging assistant.
* Ring-first caps are only rendered into the dialplan when a route sets `ring_owner`, so the live (staging) dialplan has no cap lines. They are proven on the scratch PBX only.
* Per-tenant daily call limit 30 exists; there is no per-caller limit on the AI-answer path.

### Onboarding (Pukeko, from the database)
* `phone_enabled` false, `sms_enabled` false, `owner_text_only` true, alerts to his email; authorisations: **`email_read` only** (no `telephone`, no `email_send`, no `sms_*`). Whether owner alerts need `email_send` was not checked; confirm before go-live.
* Current invite: created 2026-11-12 22:31 UTC, **unused**, expires 2026-11-13 22:31 UTC (**11:31 NZDT on 14 Nov**). Earlier invites were consumed within one second of creation (tests or link scanners); a mail scanner could do the same to this one.
* 0 plan uploads. 43 open tasks, 27 leads, 11 pending drafts.

---------------------------------------------------------------------------------------------------

## 3. Advice: how to answer calls (recommended order)

1. **Prove the line on staging first.** Make the real test call while watching `iptables -L TRENDI-SIP -v -n` (the RETURN counter must rise), `docker logs -f asterisk-bridge-1`, and `pjsip set logger on`. If it never rings, widen `HERO_NETS` or get Hero's full INVITE source list. Success = `phone_calls.status = completed`, lead saved, owner alert sent, no dead air.
2. **For Pukeko, answer with the assistant at once; do not use ring-first.** Conrad is Deaf: ringing his phone first adds about 15 seconds of silence for every caller and risks carrier voicemail swallowing the call. Send him the lead and transcript by email immediately and let him take over in writing. Cutover with ring-first stays available for owners who can answer.
3. **Prefer carrier forwarding over a new number per customer.** The customer keeps their published number and forwards it (always, or on busy/no answer) to their dedicated DID. A hearing owner answers first and the assistant is the fallback, which replaces ring-first and fixes the one-number-per-business bottleneck without new routing code. Still needs one DID per customer on the Hero account until the routing model is generalised.
4. **Gate the cutover on:** test call passed; Conrad's own telephone consent (never write it for him); the alert path confirmed (email now, SMS only when the device is back); `cutover_to_tenant.sh` rehearsed with its `--rollback` command ready.
5. **Add before real traffic:** a per-caller cap on the AI-answer path, and a persisted record of bridge logs (restarts lose them).

---------------------------------------------------------------------------------------------------

## 4. Open list (delta; everything else in the session-18 handoff stands)

**Only the operator can do:** read the loop test (after ~13:30 NZDT) and run `loop_test.sh` if wanted; real test call; message Conrad (telephone consent, invite expires 11:31 NZDT 14 Nov, voicemail off if ring-first is ever used); wake the SMS phone or disable staging SMS; give the replacement staging alert address; decide the take-over ordering (below); confirm `HEALTH_ALERT_TO`; ChatGPT Hub steps; crawler policy; Hero origin list; rotate go-live secrets; delete `~/audit-20261113/` once the venv is moved.

**Needs a decision:**
* Take-over still pauses the case before the transfer rings. You earlier said the owner must be able to answer, so I left it. Options: (a) keep, (b) transfer first and pause only if it connected.
* Per-caller cap on the AI path, and a consent gate on the owner-ring path.

**Not done this session (and why):** replacing the staging alert address (needs your address); deleting scratch tenants (`concierge`, `trendi-meta-review` look like candidates, not confirmed); deleting the audit folder (venv and handoff references still needed); the flood guard counting stuck `sending` rows (judged acceptable).

---------------------------------------------------------------------------------------------------

## 5. Rules (unchanged, plus)

* A mutating test needs the kill switch and rollback ready first, and your say-so.
* Run read-only audits before changing anything; mask addresses; never print secrets.
* The audit scripts in `~/audit-20261113/` (`audit19.sh`, `audit19.sql`) are read-only and safe to re-run.
