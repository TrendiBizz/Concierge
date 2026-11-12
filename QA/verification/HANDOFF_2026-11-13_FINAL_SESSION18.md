# Handoff — end of session eighteen — 2026-11-13 ~12:10 NZDT

This is the **complete, current** handoff. It supersedes `HANDOFF_2026-11-13_SESSION18.md` (earlier in the
same session) and carries every open item from `HANDOFF_CURRENT_2026-11-11.md` forward. Where this file and
an older doc disagree, **this file wins** (it records corrections). Evidence docs written this session:
`FLOOD_PROTECTION_2026-11-13.md`, `CHATGPT_BUSINESS_HUB_KIT.md`, `GO_LIVE_HARDENING.md` (older).

---------------------------------------------------------------------------------------------------

## 0. Read this first (60 seconds)

* The platform is **healthy** (19 containers, Hero registered, API suite **798 passed**, healthcheck green).
* **Two real test calls completed on 13 Nov** (operator, 12:31 NZDT 59 s and 12:39 NZDT 82 s, both
  `phone_calls.status = completed`, each produced a phone lead, a call insight and an owner email alert). The
  cause of the 3 failures on 12 Nov is **still unknown**. What is still unproven on a live call: supervision /
  take-over, SMS alerts (device offline), the no-answer fallback, and any call to Pukeko.
* **Pukeko (Conrad) is not live on the phone.** Blocked by one thing only he can do: authorise *telephone
  answering* in his owner portal (a consent record; never write it for him). Everything else for the cutover
  is built, tested and waiting (`scripts/asterisk/cutover_to_tenant.sh`).
* **A live loop test is still running in the background** (see section 4). Read its result before anything else.
* Two incidents happened this session and were both caused by me: a mutating "test" flipped Pukeko's
  `phone_enabled` (reverted within minutes) and unblocking an alert address started a 76-email loop
  (stopped, cleaned, and now guarded). Lessons are in section 9. Read them.

---------------------------------------------------------------------------------------------------

## 1. Access, procedures, tooling (updated — use these)

* Repo: `/Users/jo/work-staging/concierge-integration`, branch `main`. The checkpoint agent commits every 5
  minutes and **pushes only when it commits**; at the last check `main` == `origin/main`.
* VPS `152.42.239.240`; release dir `/opt/trendi/releases/20261108-vps/product` (**not** a git checkout).
  SSH key is repo-local: `ssh -o BatchMode=yes -o IdentitiesOnly=yes -i /Users/jo/work-staging/concierge-integration/Concierge root@152.42.239.240`
* **API deploy (proven 6 times this session):** `scp` the changed files into `$REL/api/app/`, `chmod 644`,
  verify hashes, then
  `cd $REL/scripts/vps && docker compose -f compose.yml --env-file /opt/trendi/shared/compose.env --profile crm --profile public up -d --build --no-deps api`
  and wait for `healthy` (~60-90 s). `schema.sql` is applied at API start. **Never** `--remove-orphans`
  (clamav, rspamd, shell are orphans). **Never recreate the PBX without `compose.public.yml`.**
* **Website deploy:** the served root is **`/opt/trendi/releases/20261108-vps/website/site/`** (not the folder
  above it; repo `website/` == that `site/`). `chmod -R a+rX`. Cloudflare **caches `/robots.txt`**.
* **Tests:** a throwaway venv lives at `~/audit-20261113/venv` (python3.13). Run from `api/`:
  `cd api && ~/audit-20261113/venv/bin/python -m pytest tests -q -p no:cacheprovider` -> expect **798 passed**.
  **Move that venv out of `~/audit-20261113/` before deleting the folder** (it holds secrets, see section 8), or
  recreate: `python3.13 -m venv V && V/bin/pip install -r api/requirements.txt -r api/requirements-dev.txt pillow`.
* **Rollback points:** images `trendi-concierge-api:before-2026111{2,3}-*` (`-gate`, `-textonly`, `-loopguard`,
  `-sweepcap`, `-floodguard`, `-caps`); file backups `/opt/trendi/backups/api-20261113{,b,c,d,e,f,g}/`;
  host hardening `/opt/trendi/backups/harden-20261112-211444/`; website `/opt/trendi/backups/website-20261113/`.
* **Desktop Commander quirks (Mac.hub, device `94c529fd-3d2c-4396-a68d-cc86d0d2fb74`):** every call returns after
  **3 seconds** (long work must run in the background and write to a file, then be read); `sleep N` in a call
  does **not** wait; `read_process_output` returns as soon as any output exists; a harmless `getcwd` error prints
  on every call; each call is a separate approval prompt (the operator set Auto, but the *connector* still asks
  per tool: set its tools to "Always allow" in the Claude app connector settings). Batch work into one script.
* **Quoting traps that cost time:** `\x27` is not a quote in psql; nested heredocs need distinct delimiters;
  `eval "$P" <<SQL` hung; use `psql ... < file.sql` or `docker exec -i ... <<'SQL'` inside `bash -s`.
* **Never print secrets.** `docker inspect` and `grep -A` on `/etc/asterisk/*.conf` both leak (see section 8).

---------------------------------------------------------------------------------------------------

## 2. What was done this session (all verified, all on `origin/main`)

| Area | What | Key commit / evidence |
|---|---|---|
| Host security | UDP 5060 restricted to Hero's /24 via `DOCKER-USER` + systemd unit (RTP deliberately open); container log rotation (PBX log was 2.6 GB); sshd hardening; fail2ban (1 h ban, recidive); 4 package updates | `scripts/vps/harden_host.sh`; 2,900 scanner packets dropped in the first minute; Hero re-registered |
| Owner-alert resilience | A failed alert is re-sent once on the other channel (capped); `channel_report` for email/SMS/voice | `5c95f63`, `34368e4` |
| Onboarding (API side) | Opt-in invitation email (`send_email`), go-live gate (409 `alerts_not_proven`, `?force=true`), `GET /owner/channel-health`, `POST /owner/alerts/test`, `POST /admin/tenants/{slug}/test-alert`, `notify_phone` settable | `78f7541` |
| Phone cutover | `scripts/asterisk/cutover_to_tenant.sh` (refuses without telephone consent; backups; `--rollback`); staged render proven byte-identical | `94c9dc7` |
| Text-first owner | `tenants.owner_text_only`: assistant never offers a transfer/call-back and never explains why; owner may still answer or take over | `b9ab2c6` |
| Ring-first | `ring_owner` per route: the owner's phone rings first, decline/busy/no-answer -> assistant at once; **hard limits** 12 rings/h, 3 per caller/h, 2 concurrent, proven on a scratch Asterisk | `b9ab2c6` + caps commit (via checkpoint) |
| Loop incident | Own-mail guard (marker headers, inbound drop); 60 junk drafts/leads/tasks deleted (backups kept) | `8c5f49f` |
| Flood protection | Central delivery guard, kill switch + admin endpoints, in-memory last-resort caps, no replies to robots, tighter SMS AI limit, healthcheck alarm | `35ac44a`, `ce0d1ea`, FLOOD doc |
| ChatGPT Business Hub kit | Hosted feed `https://trendibizz.com/chatgpt-products.csv` (3 products, 15/15 links OK, PNGs), robots.txt user-fetcher allows, `llms.txt` price bug fixed, pre-filled prompts | `CHATGPT_BUSINESS_HUB_KIT.md`, `scripts/build_chatgpt_product_feed.py` |
| Data | Conrad's mobile saved as Pukeko `notify_phone`; Pukeko `owner_text_only = true`; stale staging SMS cancelled; Brevo-sourced suppression removed then re-added | see section 3 |
| Invite | Portal invite emailed to Conrad (single-use, 24 h; sent ~11:30 NZDT 13 Nov, **expires ~11:30 NZDT 14 Nov**) | `emailed: True` |

**Corrections to older statements:** offsite backup **works** (encrypted restic, daily 14:15 UTC); the pricing
card "USD 400" is deliberate styling (not a bug); the `llms.txt` "USD 00/month" **was** a bug (fixed).

---------------------------------------------------------------------------------------------------

## 3. Production state snapshot (verify before relying on it)

* **Tenants:** `trendi-oauth-staging` (internal; *the DID currently reaches it*): `phone_enabled` t,
  `notify_phone` the operator's mobile, `notify_email` `admin@trendibizz.com`, `owner_text_only` f.
  `pukeko-construction` (customer): `phone_enabled` **f**, `sms_enabled` f, `owner_text_only` **t**,
  `notify_phone` Conrad's mobile, `notify_email` his address, channel authorisations: **`email_read` only —
  NO `telephone`**.
* **Phone:** Hero `concierge-reg` Registered. `/etc/asterisk/extensions.conf` routes `+6492431347` **and a
  catch-all `_.`** to `business-trendi-oauth-staging`; bridge listener `trendi-oauth-staging` on :9510.
  Routes file `/opt/trendi/shared/asterisk-routes.json` (0600, holds the line password) has exactly one route.
  `phone_numbers` has one enabled row for the DID (staging).
* **SMS phone device:** silent since **2026-11-11 00:20 UTC**, `inbound_verified_at` empty. All SMS alerts
  fail/`uncertain` until a human opens the app on that phone. 46 `uncertain`, 39 cancelled device jobs.
* **Email:** Brevo block on the staging address removed by the operator. Our own `email_suppressions` row for it
  **does not exist**: removed 2026-11-13 23:39 UTC for the loop test, which passed (section 4). Test email id 496 was `sent`.
* **Flood guard:** limits per recipient 8/10 min and 25/h; identical 6/10 min (email) and 3/10 min (SMS); per
  business 100/h and 120/day email (40/150 SMS); global 150/h and 270/day email (60/400 SMS). Kill switch is
  **off** (`system_flags.outbound_paused` = 0). `GET /admin/outbound/status` shows volumes and blocks.
* **Database leftovers to drop later:** tables `loopfix_backup_leads_20261113`, `loopfix_backup_drafts_20261113`,
  `loopfix_backup_tasks_20261113`.
* **Healthcheck:** cron every 5 min (`scripts/vps/healthcheck.sh`) now includes `outbound:*` checks and emails
  `HEALTH_ALERT_TO` (default is the operator's personal address) once per condition.

---------------------------------------------------------------------------------------------------

## 4. In flight right now

* **Live loop test** (`~/audit-20261113/all.sh`, step 6): waiting up to 12 minutes for the flood guard's
  one-hour recipient window on the staging address to clear, then sends **one** alert and watches for repeats
  (automatic kill switch: more than 4 alert rows -> pause + re-suppress). **Read `~/audit-20261113/all_out.txt`
  from line 48.** Outcomes:
  * `RESULT: no repeat` -> the guard is proven end to end; the address is **left unsuppressed** (alerts work).
  * `RESULT: LOOP TEST FAILED` -> outbound is **PAUSED** and the address re-suppressed. Investigate, then
    `POST /admin/outbound/resume`.
  * `SKIPPED` -> window had not cleared; re-run later (the guard was correctly holding the address).
  * If it says *no drafts and no loop-guard drops*, the test email never re-entered: inconclusive.
* A scheduled check-in (`trig_01KnPALGjJ7e6gh1mbPDKusQ`, ~12:13 NZDT) will report the result into this session.
  Step 7 of that script (commit/push) finds nothing to commit because the checkpoint agent already did.
* **RESULT (13 Nov, 23:39-23:42 UTC): LOOP TEST PASSED.** The first run was skipped (guard still holding the
  address). The re-run found the window clear, removed the suppression, sent one test alert and watched 150 s:
  alert rows rose to 3 and then stayed at 3; **0 junk drafts**; **2 loop-guard drops recorded** (our own mail
  coming back was dropped); no pause needed. Of the 3 rows, 1 was the test; the other 2 were **not a loop** but the
  alerts for the operator's real phone call at 12:39 NZDT (`Phone message...` + the caller's text copy). The staging
  address is **left unsuppressed** (staging email alerts work again) and the kill switch is **off**.
* **What the two test calls showed (12:31 and 12:39 NZDT):** callback number heard correctly (027 881 7368) and
  email heard correctly; summaries accurate (`quote_requested`); lead saved with consent; owner email alert and the
  caller's email copy sent. **Gaps seen:** *no caller name was captured on either call* (consider prompting for
  it); the caller asked for a **text copy** and the insight says "the text was queued", but SMS is stuck
  `awaiting_receipt` because the phone device is offline, so that promise is not kept until the device is back
  (3 SMS rows pending on the staging tenant; they will go `uncertain` after 15 min, then the capped escalation
  may re-send them by email). Quality of the voice (dead air, read-back) was not assessed from logs.

---------------------------------------------------------------------------------------------------

## 5. The to-do list — everything open

### 5A. Only the operator can do these (do first)
1. **Read the loop-test result** (section 4).
2. **Conrad must authorise telephone answering** in his owner portal (he has the invite; **the email does not
   mention this step — message him**). Without it the bridge rejects every call to Pukeko.
3. **Wake the SMS phone** (open the app) and confirm `sms_devices.last_seen` advances and `inbound_verified_at` is set.
4. *(Two test calls already completed on 13 Nov: see section 4. Still do these.)* **Make the real test call** to **+64 9 243 1347** (full enquiry, callback number and email read aloud). Expect
   no dead air, details read back, lead saved, owner alert fired, `phone_calls.status = completed`. Read the
   logs during it: `docker logs -f asterisk-bridge-1`, and `pjsip set logger on` on the PBX (turn it off after).
   If it never rings: `iptables -L TRENDI-SIP -v -n` on the VPS (a rising DROP count with Hero traffic means widen
   `HERO_NETS` in `harden_host.sh` or get Hero's full origin list). Rollback of the firewall is in `harden_host.sh`.
5. **Tell Conrad before the cutover:** his phone will ring first; he may answer or decline (declining is fine, the
   assistant takes the call at once). **He should disable voicemail on that mobile** (carrier voicemail would be
   treated as an answer and swallow the call).
6. Set Desktop Commander's connector tools to **Always allow** (stops the per-call approval prompts).
7. Delete the ~77 junk "Email enquiry for Trendi Concierge" emails in Gmail (label Trendibizz/Enquiries).
8. **Send Conrad the plan-upload link** (`/upload/{token}`, created 2026-11-11, 0 uploads; sending never confirmed).
9. Read/decide the **11 email drafts** (8 quarantined, 3 draft) — plus any new ones.
10. Ask Hero for their **full call-origin (INVITE source) address list** (DNS gives one host, `103.212.52.17`; the
    firewall allows its /24 as a hedge) and whether they offer an SMS/voice status API.
11. **ChatGPT Business Hub** (only the signed-in owner can): claim the profile as **Trendi**, paste the 262-char
    description, upload square photos incl. the logo, add the feed (prefer the hosted URL), confirm only at 0 errors,
    re-check Insights after a week. Steps and pre-filled prompts: `CHATGPT_BUSINESS_HUB_KIT.md`.
12. **Decide the crawler policy:** the site blocks GPTBot and ClaudeBot (training) while allowing search and
    user-fetchers; the kit's audit will mark GPTBot down. Left as is; one-line change if you want it.
13. **Confirm `HEALTH_ALERT_TO`** (where flood/health alarms are emailed).
14. Decide the staging tenant's alert address. **`admin@trendibizz.com` routes back into the platform**
    (Cloudflare Email Routing) — it is what made the loop. Safer: a non-routed address for staging alerts, and
    decide the final owner of `admin@` (also in `GO_LIVE_HARDENING.md`).
15. Rotate-at-go-live secrets that appeared in transcripts (section 8) and delete `~/audit-20261113/` after moving the venv.

### 5B. Pukeko phone cutover (when Conrad has consented)
1. Confirm consent: `select channel, authorized from tenant_channel_authorizations a join tenants t on t.id=a.tenant_id where t.slug='pukeko-construction'` shows `telephone | t`.
2. Go-live gate passes (Pukeko has delivered alerts; the script runs it through the admin API).
3. On the VPS: `RING_OWNER=+6421824305 bash $REL/scripts/asterisk/cutover_to_tenant.sh pukeko-construction`
   (it refuses without consent, backs up, moves the `phone_numbers` row, swaps routes, re-renders only
   `extensions.conf`, reloads the dialplan, recreates **only** the bridge, verifies). It prints the backup dir.
   **Undo:** `bash cutover_to_tenant.sh --rollback <backup-dir>`.
4. Then test: owner answers; owner declines; owner ignores (15 s); a caller hangs up while it rings. Check
   `phone_calls`, the alert emails, and that **calls Conrad answers himself leave no CRM record** (known gap).
5. **Unverified:** the outbound ring number format (`6421...` without `+`) has never been tried on Hero; a failure
   falls safely to the assistant, so watch the first calls.
6. **The script asserts exactly one route** (`len(routes)==1`). Adding a second customer needs the script and the
   routing model generalised (see 5D-1).

### 5C. Phone / voice backlog
* `phone_calls` rows have empty `from_number`/`session_id` and no **failure reason**; add them. **Persist bridge
  logs across restarts** (the 12 Nov failure evidence was lost to a restart).
* The 3 failed calls: unexplained. Hypotheses: Hero sending from an address outside the pinned identify match
  (`103.212.52.17/32`; widen to the /24 or the verified list); outbound/inbound number-format mismatch.
* Supervision on a real call (listen/whisper/join), media modes, 30 s no-answer fallback: still unproven live.
* For a Deaf owner these are mostly moot, but the **portal take-over alert and after-call tasks still say "ring
  them back"** — change wording to "reply by text or email" when `owner_text_only` is set.
* Missed-call text-back is inert for Pukeko (`sms_enabled` false) pending the SMS device; `payment_instructions`
  unset for Pukeko ("Get paid on an accepted quotation" reads unconfigured).
* AudioSocket carries no caller ID (the agent asks for a callback number); transferred calls show the business CLI.
* RTP 10000-10099/udp is open by design; revisit once Hero's media ranges are known.
* Not built on purpose: multi-call supervision/queue/roster; browser listen-in (WSS/DTLS/ICE).
* Review the live-listen **disclosure copy** (customer-facing).

### 5D. Onboarding — what is left (the operator wants it as seamless as possible)
Done (API only): opt-in invite email, go-live gate, channel-health endpoint, alert test endpoints, `notify_phone`
via API, `owner_text_only` via API. **Open:**
1. **Number model.** One Hero registration = one number = one business (renderer: exact-DID routes only with
   >1 route). Each new customer needs their own DID on the account (or a forward to a DID) plus a routes entry;
   the cutover script is single-route. Design and automate this (it is the real install bottleneck).
2. Portal UI for everything above: channel-health panel, "send test alert" button, `owner_text_only` and
   ring-first toggles, invite-email checkbox in the admin UI, "call me to test" button (AMI originate).
3. Website prefill (owner approves; no silent crawl), widget snippet "verify installed" check, go-live checklist
   screen showing per-channel health, SMS-device pairing with a clear "keep the app open" indicator.
4. Real-browser and accessibility QA (never run), a controlled real-customer consent test.
5. External: Meta app review, TikTok sandbox, LinkedIn Page management; Pukeko social OAuth; live social publishing.

### 5E. Flood / safety backlog (`FLOOD_PROTECTION_2026-11-13.md` §5, §7)
* In-memory caps (Twenty, Brevo webhook, social writes, mailer/SMS last-resort) **reset on restart** and were only
  unit-tested; the DB guard is the primary control. Consider persisting them.
* Read inbound `Auto-Submitted`/`Precedence` headers from other systems and hold auto-replies (today: address and
  subject heuristics only). Add a check that does not rely on a human noticing a flood: a **Brevo daily-quota alert**
  (free plan 300/day) and an operator alert channel that cannot loop.
* Limits are heuristics: tune from real traffic.
* Not audited: the Rust social service internals, Twenty bridge volume beyond the cap, Brevo webhook beyond the cap,
  rate limits on the take-over/listen-in admin endpoints.
* Owner-alert throttle (`owner_notifications`) still only applies when a `lead_id` is passed (the central guard covers it now).

### 5F. Go-live security (`GO_LIVE_HARDENING.md` plus new)
Rotate `BREVO_WEBHOOK_SECRET` (+ its Brevo webhook URL) and `ADMIN_TOKEN`; Brevo paid plan/dedicated IP, rotate
the SMTP key, narrow authorised IPs to `152.42.239.240`; DMARC `p=quarantine` -> watch ~a week -> check
`include:spf.web-hosting.com` alignment -> `p=reject`; delete scratch tenants and decide `admin@trendibizz.com`;
split the Cloudflare token; rotate the xAI key (visible in `docker inspect`); Worker secret plain-text -> Secret.
**New:** the AMI secret and the Hero SIP password were printed into this session's transcript and sit in plain
text in the mounted `manager.conf`/`pjsip.conf`; Pukeko's `report_token` and `calendar_token` were printed.
The operator says the first two are test credentials to be changed; treat all four as go-live rotations.

### 5G. Operations / housekeeping
* Merge this file into `HANDOFF_CURRENT_2026-11-11.md`'s consolidated list.
* Restore test runs monthly (next 30 Nov). Disk 36%, ~7.9 GB RAM, **no swap** (ClamAV + Rspamd + the bridge; one
  spike could take the line down). Single VPS = single point of failure.
* Docker `daemon.json` log caps apply to containers only after they are recreated.
* Drop the `loopfix_backup_*_20261113` tables when the cleanup is accepted.
* Astryx Native (Mondays 09:00 NZ, still a placeholder), `.github/workflows/uptime.yml` red runs (not read; GitHub
  was not connected), richer admin console, remove the old test phone route, daily GEO check 07:00 NZ.
* The DSH harness patch note from the old handoff is unrelated to Concierge.

---------------------------------------------------------------------------------------------------

## 6. Things we missed or only found late (so they are not lost)

1. **`admin@trendibizz.com` is both an alert target and an inbound route** — the root of the loop. Any address
   that routes into a tenant mailbox must never be an alert recipient (the guard now contains it, the design flaw remains).
2. **Alerts and transfers share one phone number** (`notify_phone`): SMS target *and* the number a take-over rings.
   A text-first owner needs them separable (today `owner_text_only` only changes what the assistant says).
3. **Ring-first and consent:** the AI path checks consent/limits; the owner-ring path did not (now capped, but
   not consent-gated). A call the owner answers himself bypasses the CRM entirely.
4. **The cutover script and renderer assume one business per number.**
5. **No staging environment.** Everything is tested against fake pools or production; two production
   mistakes this session came from that. A scratch Asterisk (no network) proved itself as a pattern worth reusing.
6. **Existing tests hit a real DB without schema** in places (`outbox._deliver`); the guard had to fail open
   because of it. Worth a proper test database fixture.
7. **The flood guard counts only delivered rows** (`sent`/`awaiting_receipt`); a stuck `sending` row is not
   counted. Acceptable, but know it.
8. **Take-over still pauses the assistant before trying to ring** (the transfer-fails-after-pausing hazard I
   found when I first read it) — `take_over` was restored to the original behaviour when the operator said the
   owner must be allowed to answer; the hazard is therefore still present and worth fixing.
9. Healthcheck's operator email defaults to a **personal address**: confirm it is intended.
10. Cloudflare caches robots.txt/other static files; the token cannot purge. Plan around it when changing them.
11. Conrad is Deaf: the whole product exists for that. Keep alerts text-first (email now, SMS when the device is
    back), keep the portal accessible, and never disclose it to callers (the prompt rule is explicit).
12. `broken`/unreliable: SMS device (a physical phone). The operator chose to keep it ("use our own system"); it
    needs a health indicator, an owner-facing "phone offline" notice (channel-health exists, UI does not) and ideally a backup path.

---------------------------------------------------------------------------------------------------

## 7. Command cheat-sheet (run on the VPS unless noted; never paste tokens into chat)

```
# flood guard / kill switch (token read on the box, never printed)
T=$(grep '^ADMIN_TOKEN=' /opt/trendi/shared/api.env | cut -d= -f2-)
curl -s -H "X-Admin-Token: $T" http://127.0.0.1:8000/admin/outbound/status
curl -s -X POST -H "X-Admin-Token: $T" http://127.0.0.1:8000/admin/outbound/pause     # stop ALL email+SMS now
curl -s -X POST -H "X-Admin-Token: $T" http://127.0.0.1:8000/admin/outbound/resume
# suppress / unsuppress an alert address (staging)
psql: insert into email_suppressions(tenant_id,address,reason,source,detail) ...   /   delete from email_suppressions ...
# health
bash /opt/trendi/releases/20261108-vps/product/scripts/vps/healthcheck.sh
docker exec asterisk-pbx-1 asterisk -rx "pjsip show registrations"
iptables -L TRENDI-SIP -v -n
# phone cutover / undo
RING_OWNER=+6421824305 bash $REL/scripts/asterisk/cutover_to_tenant.sh pukeko-construction
bash $REL/scripts/asterisk/cutover_to_tenant.sh --rollback /opt/trendi/backups/phone-cutover-<timestamp>
# regenerate the ChatGPT feed (Mac): python3 scripts/build_chatgpt_product_feed.py   (then deploy to website/site/)
```

---------------------------------------------------------------------------------------------------

## 8. Secrets and sensitive material to clean up

* `~/audit-20261113/` on the Mac contains output files holding the **AMI secret and the Hero SIP password**
  (`call_audit2.txt`) and the test venv. Move the venv, then delete the folder.
* `/tmp/pbx-scratch` on the VPS is removed by the test script; confirm it is gone.
* This session's transcript contains: the AMI secret, the Hero SIP password, Pukeko's `report_token` and
  `calendar_token`, and the (public) widget key. Rotate at go-live.

---------------------------------------------------------------------------------------------------

## 9. Rules for the next session (learned the hard way)

1. **Never use a mutating production call as a "safe test".** Prove gates with unit tests or read-only queries;
   verify the *data* before predicting an outcome.
2. **Consent records belong to the business owner** (`tenant_channel_authorizations`, audited by trigger). Never write them.
3. **Before unblocking or enabling any alert address, check it does not route back into the platform.**
4. Keep a kill switch and the rollback command ready *before* any test that sends real messages.
5. Print only what you need; mask addresses and tokens; remember `grep -A` can dump secrets.
6. Batch work into one script per step (the operator is charged a prompt per tool call); write outputs to files.
7. Full-file edits when handing code to the operator; this session used in-place edits on the 3,100-line `main.py`.
8. Warn at 70% context with a summary (the operator asked); the operator hates repeated approval prompts and noise.
