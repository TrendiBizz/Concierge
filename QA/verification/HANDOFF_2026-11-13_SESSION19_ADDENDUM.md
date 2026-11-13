# Addendum to the session-19 handoff — 2026-11-13 ~12:55 NZDT

Read after `HANDOFF_2026-11-13_SESSION19.md`. Where they differ, this file wins.

## First real calls (operator test calls, +64 9 243 1347)

* Call 1 (12:31) was the first call ever to complete (`phone_calls.status = completed`, 59 s). Call 2 (12:39) followed the fixes below.
* The Hero firewall rule still shows **0 packets**: calls arrive on the existing registration flow, so that rule is not what lets them in. Unproven for a fresh inbound INVITE from Hero.

## Changed today (all deployed, tests 826 passed, on `origin/main`)

| Change | Detail |
|---|---|
| Read-back | A number or email address is said at most once per call; an interruption is treated as the answer, never restarts a read-back; the assistant never mentions devices, queues or delivery limits (`READBACK_RULES`) |
| Text copy | No SMS text-copy offer while the SMS phone has not checked in for 2 hours (`SMS_OFFLINE_RULE`, `sms_copy_available`) |
| Filler words | `api/app/speech_text.py`: owner alert, lead message, website-voice summary and text copy leave out "um/uh/er/hm" and stutters ("I, I"). The stored transcript stays word-for-word |
| Greeting | Phone opening is now: "Hello, I'm the AI assistant for {business}. Our calls are recorded for quality and training purposes[ and a team member may listen in]." Questions are one short sentence at a time; no extras offered; one-sentence goodbye (`phone_instructions`, `QUICK_QUESTIONS`) |

## Policy change to know about (recording)

Recording used to be **ask permission, start only after an explicit yes**. It is now **notice, then record, stop at once if the caller objects**
(the assistant calls `set_call_recording` right after the greeting). Still gated by the business's `call_recording` authorisation and the
platform switch; if either is off the greeting says "transcribed", never "recorded". The listen-in clause appears only while listen-in is
enabled. This follows the operator's wording; it suits NZ rules (the business is a party to the call and the caller is told) but callers
abroad may be under stricter rules. Revisit before wide rollout. Rollback of the phone prompt: `/opt/trendi/backups/api-20261113k/asterisk_bridge.py`.

## Sender / alert address (decided)

* **`admin@trendibizz.com` stays the standard From address** (operator's decision). `SMTP_FROM` unchanged.
* The staging tenant's alerts go to the same address, which routes back into the platform. **This is now proven safe in live use**: the two
  alerts sent from `admin@` to `admin@` were each dropped by the inbound loop guard (`inbound_loop_guard` x2), created **0 drafts**, and caused
  **no repeat alerts**. This replaces the session-18 loop test, so `loop_test.sh` does not need to be run.
* The staging address block (`email_suppressions`) is gone (0 rows). It was removed between 12:32 and 12:39 NZDT; not by this session's scripts.
* The design flaw remains by choice (an alert address that routes in). The guard is what protects it: keep the `X-Concierge-Mail` marker.

## Still open

Everything in the session-19 handoff §4, minus the loop test. Biggest: Conrad's telephone consent and invite (expires 11:31 NZDT on 14 Nov),
the SMS phone, per-caller cap on the AI path, take-over ordering decision, Hero origin list, go-live secret rotation.
Possible next fix: turn spoken digits and emails in owner alerts into written form ("027 88 17 368", "kiwi18@gmail.com") while keeping the spoken text.


## Support mailbox (13:10 NZDT)

`support@trendibizz.com` was only caught by Cloudflare's catch-all forward (no record, no alert) although the website says "Both reach Trendi".
It now has a Cloudflare rule "Support intake" (id `8db03a2cc01f4c97935ed313f73f048c`) to `concierge-inbound-worker`, and a registered inbound mailbox
for `trendi-oauth-staging`. The worker also forwards the original to the operator inbox. Undo: delete the rule; `delete from inbound_mailboxes where recipient='support@trendibizz.com';`.
Not yet tested with a real inbound email. The full plan is `SUPPORT_STRUCTURE_2026-11-13.md`.


## SMS correction (13 Nov ~13:20 NZDT) — read this, it replaces earlier SMS advice

* The "SMS phone" is **not an app on a phone**. It is `Trendi Phone Connector.app` on **Mac.hub** (LaunchAgent `com.trendi.phone-connector`, config `~/.config/trendi-phone/`),
  sending through the Mac's Messages. Earlier advice to "open the app on the phone" was wrong and would never have helped.
* The connector process is running but has been **stuck since 2026-11-11 00:20 UTC**: it keeps POSTing `/api/v1/device-sms/receipt` and the API answers **409** (48 in 24 h);
  its log says `Phone connector requires attention: HTTPError`. It is retrying receipts for jobs the server has already finalised and does not poll for new work.
* The 9 Nov notes (`PHONE_SMS_CONTINUATION_2026-11-09.md`) say a person must confirm Send natively on the Mac, and no text has ever been confirmed sent.
  Alerts need unattended delivery, so the design is unsuitable for alerts even if unstuck.
* Do **not** edit the connector's `device.sqlite` or re-pair it while jobs are ambiguous (sends are irreversible; never an automatic second send).
* Better solution proposed to the operator: push notifications for owner alerts (plus email), and a real SMS API provider for customer-facing texts. See the decision recorded after this note.
