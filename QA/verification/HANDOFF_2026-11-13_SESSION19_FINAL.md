# Handoff — end of session nineteen — 2026-11-13 ~14:10 NZDT

This is the **current** handoff. It sits on top of `HANDOFF_2026-11-13_FINAL_SESSION18.md` (base access, procedures, open list),
`HANDOFF_2026-11-13_SESSION19.md` + `..._SESSION19_ADDENDUM.md` (earlier same-day changes), `SUPPORT_STRUCTURE_2026-11-13.md` and
`ONBOARDING_REDESIGN_2026-11-13.md`. **Where they disagree, this file wins.**

---------------------------------------------------------------------------------------------------

## 0. Read first (60 seconds)

* Platform healthy: 19 containers, Hero registered, tests all passing at the last deploy (about 900), no tracebacks.
* **Two real test calls completed** (first ever). Owner alerts reach `admin@` by email within seconds. The SMS connector is **fixed** and polling again; one
  test text was sent and verified by the Mac. The operator has **not yet confirmed it arrived on their phone**.
* **Web push is deployed but nobody has tried it on a phone.** Its UI lives in `/owner-ui` (the static owner page), **not** in `/studio` where the operator works.
* **The operator's own Trendi Support workspace exists** (owner account created 00:56 UTC, NZ timezone, country 64). It still has **no consents**.
* **Conrad (Pukeko) invite expires 11:31 NZDT on 14 Nov** (single use, unused at last check) and he has not authorised telephone answering. Message him.
* The operator asked for a **redesign of onboarding so customers only give permission** (see `ONBOARDING_REDESIGN_2026-11-13.md`) and asked for a better method than
  "prefer a PNG icon" for SVG logos (section 6). Nothing of that redesign is built yet.
* Last two operator messages: "find a better tool or method than svg", "do a handoff so we move to new session".

---------------------------------------------------------------------------------------------------

## 1. Procedures — **new lessons from today (read before deploying anything)**

1. **The production image installs from the pinned lockfile `scripts/vps/api-requirements.lock`**, built with `scripts/vps/Dockerfile.api` and context = the product root
   (`compose.yml`: `build: {context: ../.., dockerfile: scripts/vps/Dockerfile.api}`). Adding a library to `api/requirements.txt` does nothing. 14 pins were added for `pywebpush`.
   The line `ifcopenshell>=0.8,<1` is an intentional unpinned range at the end.
2. **After recreating `api` you MUST recreate `social`**: `up -d --no-deps --force-recreate social`. It runs with `network_mode: service:api`; without this the Studio shows
   "Social service unavailable". Every earlier API deploy silently broke it. Verify `docker inspect -f '{{.HostConfig.NetworkMode}}' trendi-social-1` equals the API container id.
   Publishing stays off (`SOCIAL_ENABLE_PUBLISH=false`).
3. **The public proxy has a path allowlist** (server `Caddyfile`, `@owner`): `/owner-ui /onboarding /studio /studio/* /quote/* /upload/* /robots.txt /owner/* ...`; everything else is 404.
   New public paths go under `/owner/` or must be added to the Caddyfile. (`/owner-sw.js` 404'd for this reason; the service worker is now `/owner/sw.js`.)
4. **Portal (React, `web/portal`) deploy**: `npm run build`, `rsync -a dist/ root@VPS:/opt/trendi/shared/studio/` (**no `--delete`**, so already-open pages keep their old chunks), `chmod -R a+rX`.
   It is bind-mounted read-only into the API container: **no restart**. Styles must go in `src/index.css` (**`App.css` is never imported**). Backups: `/opt/trendi/backups/studio-20261113{,b,c,d}`.
5. **Gated deploy pattern** (templates in `~/audit-20261113/run_s19*.sh`, `run_portal*.sh`): patch with exact-match anchors (all-or-nothing) -> compile -> **full test suite** -> no-call precheck ->
   backup files + tag image -> scp + hash check -> **build, check the image really contains the change** -> restart -> wait healthy -> **recreate social** -> verify through the **public** address -> commit own files only.
   A `restore()` puts files, `api.env` and the `:vps` image tag back on any failure.
6. **Desktop Commander quirks** unchanged (3-second calls, run work in background to a file). The Mac's `Edit`/`Write` tools in this harness only see the sandbox: use `write_file` on the Mac.
7. **Healthcheck** (cron 5 min) emails the operator once per condition. Creating a tenant before its owner exists and has consented raises `inbound:chain ... owner_account,consent`. That is why the new tenant's reply mailbox is **disabled** until consent exists.
8. **Defaults that are wrong for New Zealand**: global `DEFAULT_COUNTRY_CODE=1`; new tenants default to timezone `America/Chicago`; no tenant has `default_country_code` set. Phone input now derives the country from the business (own setting, then timezone). `trendi-support` is fixed (Pacific/Auckland, 64). `pukeko-construction` and `trendi-oauth-staging` are NZ timezone but have **no** country code: do not change them without checking case-identity effects (`casetimeline.tenant_country_code`).
9. A **date-dependent test** (`test_missed_calls`) broke at UTC midnight; fixed (it now uses today's date).
10. `help`: operator preference is **no usage percentage claims** unless a real number is on screen (they were rightly angry when one was guessed).

---------------------------------------------------------------------------------------------------

## 2. Changed today — deployed and verified (all on `origin/main`)

| Area | Change |
|---|---|
| Owner wording | take-over alert/note/task say "reply by text or email" when `owner_text_only` |
| Dedicated call number | `tenants.owner_call_phone` (falls back to `notify_phone`) |
| Inbound mail | automated senders (Auto-Submitted, Precedence bulk/list, List-Id, X-Auto-Response-Suppress) keep a draft but get no auto-reply |
| Calls | `phone_calls.failure_reason`; assistant says a number once, never restarts a read-back after an interruption, never offers a text copy while the SMS device is silent; fillers (um/uh) and stutters removed from outgoing alerts/leads/text copies (`speech_text.py`); greeting is two sentences ("Hello, I'm the AI assistant for X. Our calls are recorded for quality and training purposes[ and a team member may listen in].") with quick one-line questions |
| **Policy change** | recording is now **notice then record, stop on objection** (was ask permission). Still gated by the business's `call_recording` authorisation and the platform switch; "transcribed" replaces "recorded" when unavailable |
| Support | `support@trendibizz.com` -> Cloudflare rule "Support intake" (id `8db03a2cc01f4c97935ed313f73f048c`) -> `concierge-inbound-worker` (posts to the API, **also forwards the original to the operator inbox**); mailbox registered to `trendi-oauth-staging`. Verified with a real email |
| Acknowledgement | opt-in `inbound_ack` (+ `inbound_ack_text`): reference "T-n", only for senders whose DKIM aligns/DMARC passes, never robots/lists/high risk, once per sender per day, goes through the outbox (needs `email_send` consent) |
| Support tenant | `trendi-support` created: alerts to `admin@`, SLA alert 1440 min on every enquiry (`sla_min_score` 0), `inbound_ack` on, AI auto-reply **off**, owner account exists, NZ timezone + 64, **reply mailbox disabled until consent** |
| Web push | `webpush.py`, `push_subscriptions`, `/owner/push/{key,subscribe,unsubscribe,test}`, `/owner/sw.js`, "Phone alerts" panel in `/owner-ui`; alerts push in the background (cap 30/h per business, dedupe 10 min, only real push-service hosts allowed). VAPID keys generated on the VPS into `api.env` (never printed) |
| SMS connector | server now accepts a **late device-verified receipt** for an `uncertain` job and acknowledges receipts for already-closed jobs (it was stuck 2 days answering 409). Connector polling again; unacked journal 0 |
| Errors | owner-portal validation errors are one readable sentence, never echo the input (incl. the password); app-written messages are kept |
| Portal (`/studio`) | red flashing `ErrorNote`, big "12" rule box + live meter + instant check, password-manager fields + "Suggest a strong password", Setup shows problems in the red box |
| Phone input | any usual way of writing a number is accepted and stored as `+country...` using the business's country (`0211234567`, `021 123 4567`, `(021) 123-4567`, `+64 21 123 4567` -> `+64211234567`); `+0...`, letters and newlines still refused |
| Housekeeping | `loopfix_backup_*` tables dropped after a verified dump (`/opt/trendi/backups/loopfix-20261113/loopfix_tables.sql`); two secret-bearing scratch files deleted |

---------------------------------------------------------------------------------------------------

## 3. Production snapshot (verify before relying on it)

* **Tenants**: `concierge` (archived prototype), `pukeko-construction` (customer; email_read only; phone/SMS off; text-only owner), `trendi-meta-review`, `trendi-oauth-staging` (the internal tenant: the DID `+64 9 243 1347` and the catch-all route here, `phone_enabled`, `sms_enabled` true, owns the `support@` mailbox), `trendi-support` (above).
* **Cloudflare email routing**: `admin@` and the `reply-*` addresses -> worker; `support@` -> worker; catch-all -> forward. Worker env `FORWARD_TO` forwards every original.
* **Alerts**: email from `admin@` (standard From, operator decision) to `admin@` (routes back in; protected by the own-mail loop guard, **proven live**: 3 drops, 0 drafts, no repeats). Push configured. SMS through the Mac connector.
* **Hero firewall rule** for Hero's /24 still shows **0 packets** (calls arrive on the registration flow); a fresh inbound INVITE from another Hero address is unproven.
* **Consent**: only the owner's own click writes a consent. Never write one for them.

---------------------------------------------------------------------------------------------------

## 4. In flight / unverified at handoff

1. **SVG tooling check (done, read after the handoff was first written)**: the production image already has **Pillow 13.0.0 and numpy 2.5.4** (pinned in the lock); `cairosvg`, `resvg_py` and `svglib` are not installed; **`resvg_py` 0.5.0 resolves as a prebuilt wheel for Python 3.12 on Linux** (dry run, nothing installed). The real logo (`trendibizz.com/brand/logo-refresh.svg`, 416 bytes) is **a text SVG**: `<text font-family="Arial,sans-serif">Trendi</text>` with colours `#302044` and `#7142d6`, no scripts or external references.
2. A scheduled check (`trig_016uSZSupqQEvRmiBPC5wysH`, 01:13Z) will try to report the already-finished phone-input deploy into the old session: ignore it.
3. Not confirmed by the operator: the test **text** arrived on their phone; a **third test call** after the greeting change (single read-back, no "um" in the email, quick questions); web push on a phone; the red error / password-suggest look after reload.
4. Uncommitted at handoff: `api/tests/test_owner_notification_phone.py` (committed together with this file).

---------------------------------------------------------------------------------------------------

## 5. Open items

### 5A. Operator only
1. **Message Conrad**: grant telephone consent in his portal; his invite **expires 11:31 NZDT 14 Nov**; he should disable carrier voicemail if ring-first is ever used. For Pukeko I recommended **no ring-first** (he is Deaf): the assistant answers at once and emails the lead.
2. In the **Trendi Support** workspace (`/owner-ui`, Business ID `trendi-support`): give `email_read` and `email_send` consent. Then (agent) re-enable its mailbox: `update inbound_mailboxes set enabled=true where tenant_id=(select id from tenants where slug='trendi-support');` and decide whether to move `support@` to it.
3. Turn on **phone alerts** on their phone (`/owner-ui` -> "Phone alerts"; iPhone: add to Home Screen first) and press "Send a test alert". Confirm the test text arrived. Make a third test call.
4. Decide: **take-over ordering** (it still pauses the case before the owner's phone rings), per-caller cap on the AI path, `HEALTH_ALERT_TO`, crawler policy, Hero origin list/API, ChatGPT Hub steps, go-live secret rotations, delete `~/audit-20261113/` after moving the venv (it also holds scripts you may want to keep).

### 5B. Build backlog (priority order)
1. **Onboarding Phase 0** (`ONBOARDING_REDESIGN_2026-11-13.md`): server module `brand_from_site.py` + `GET /owner/onboarding/brand-suggestion` using `public_fetch.PublicClient` (public-only fetch) returning name, **PNG logo as a `data:image/` string <= ~290 KB raw** (the brand store limit is 400,000 characters), accent colour, contact line, socials, platform (generator/paths), timezone + country; one review screen replacing wizard steps 2-5 with a colour picker (never a hex box); step 6 becomes platform-aware ("Install on my site" / "Email this to my web person" / "I'll paste it") with a **live check of the customer's site**; hosted chat link + QR.
2. Put **web push in the Studio** (the operator does not use `/owner-ui`); long term unify `/studio` and `/owner-ui` into one Consent Hub.
3. Provider **SMS** (customer-facing texts; the Mac connector is now only a stopgap and still depends on a Mac staying awake and Messages signed in).
4. WordPress plugin first (**Pukeko is on WordPress 7.1.4 + Elementor**), then Shopify / Wix / Webflow / Tag Manager.
5. Per-caller cap on the AI answer path; persist bridge logs; consent gate on the owner-ring path; the earlier session-18 flood/safety backlog (in-memory caps reset on restart, etc.).

---------------------------------------------------------------------------------------------------

## 6. The logo/colour plan (answers "find a better method than SVG")

* Most business logos are SVG (trendibizz.com's header logo is). Our media tools compose with raster images, so **rasterise the SVG on our side** instead of falling back to a small touch icon.
* Recommended: **`resvg`** through a pure wheel (`resvg-py`, no system libraries, safe: no scripts, no external fetch). Search results support the "no system libraries" claim; **verify the wheel resolves in our image** (section 4, item 1) and add it **to `api-requirements.lock`** (rule 1). `cairosvg` needs the native Cairo library: avoid.
* Pipeline: fetch candidates (JSON-LD logo, header `<img>`, touch icon, `og:image`) with the public-only fetcher -> reject anything over the size cap -> if SVG: **render to a transparent 512 px PNG** (this also removes any script risk because only the PNG is stored) -> check magic bytes -> store as the brand logo.
* **Take the accent colour from the finished logo**, not from CSS: the dominant saturated, non-neutral colour (median-cut on the PNG; Pillow and numpy are already in the image). On trendibizz.com `theme-color` is the page **background** (`#f5f7fb` light / `#14213d` dark); that logo's own colours are **purple (`#7142d6`) and dark purple (`#302044`)**. The lime `#c8f560` is the Concierge portal's default accent, not that site's brand colour.
* **Font gotcha**: a logo drawn with live `<text>` (like this one) needs a font on the server, and the slim image has none, so it would render blank. Either bundle one sans-serif font file in the image and pass it to `resvg` (the result will not match the site's exact typeface), or, when the SVG contains `<text>`, show the rendered preview **and** the touch icon / `og:image` as alternatives and let the customer pick. Logos whose text is already converted to paths render exactly.
* If no logo is found: offer the site's touch icon, then a generated monogram in the accent colour. Always let the customer replace it. The review screen's preview is what makes any imperfect render safe.
* Commercial brand-data APIs exist but are unevaluated here; not recommended before the free route is tried.

---------------------------------------------------------------------------------------------------

## 7. Rollback points (all verified to exist at the time they were made)

Images `trendi-concierge-api:before-20261113-{push,swpath,valmsg,phone,clean,ack,s19}` and `before-20261112-*`; file backups `/opt/trendi/backups/api-20261113{,b..p}/` (each holds the files it replaced, plus `api.env.bak` and the lockfile where relevant);
`/opt/trendi/backups/studio-20261113{,b,c,d}`; host hardening `/opt/trendi/backups/harden-20261112-211444/`; website `/opt/trendi/backups/website-20261113/`; the `trendi-support` tenant can be deleted with `DELETE /admin/tenants/trendi-support` (nothing depends on it yet).
Support route undo: delete the Cloudflare rule above and `delete from inbound_mailboxes where recipient='support@trendibizz.com';`.

## 8. Secrets and sensitive material

* `VAPID_PRIVATE_KEY` is in `/opt/trendi/shared/api.env` (public key is not secret). The AMI secret, Hero SIP password and Pukeko report/calendar tokens from the earlier transcripts still need rotating at go-live.
* An invite token and Pukeko's public widget key appeared in operator screenshots. The invite is consumed; the widget key is public. Never print tokens or keys.
* Per-call transcript of the operator's real calls is in the staging tenant CRM.

## 9. Rules for the next session

1. No mutating test without the operator's say-so (one test alert was approved and used). Keep a kill switch and rollback ready first.
2. Consent records belong to the business owner; never write them.
3. The operator wants **full files** when code is handed over, **no core code changes unless clearly instructed**, fewer prompts and less noise, and **no invented numbers** (usage, counts, dates).
4. Warn plainly before anything outward (emails, texts, Cloudflare, DNS). Read-only audits first.
5. Check the deploy checklist in section 1 every time, especially the lockfile and recreating `social`.

## 10. First ten minutes of the next session

1. Read this file, then `ONBOARDING_REDESIGN_2026-11-13.md`.
2. `git log --oneline | head`, then run the read-only audit `~/audit-20261113/audit19.sh` (outputs `audit19_out.txt`), check `docker ps` and the healthcheck log.
3. Read `~/audit-20261113/svg_tools_check_out.txt`.
4. Ask the operator for: the 4 redesign decisions (WordPress first? unify portals? Hero API? SMS/Places budget?) and whether the test text and push worked.
5. Start Onboarding Phase 0 (5B-1) unless told otherwise.
