# HANDOFF — Trendi Concierge

**Read first:** `AGENTS.md` in this repo (the working agreement — enforced by tooling, and it now
includes the website's technical SEO contract), then the QA record matching the area you touch.
Records from 2026-11-15: `SYSTEM_AUDIT_2026-11-15.md` (audit), `SEO_PASS_2026-11-15.md` (content),
`SEO_GROWTH_2026-11-15.md` (growth implementation), `EMAIL_ENGAGEMENT_2026-11-15.md`,
`CENTRAL_REPO_2026-11-15.md`.
Records from 2026-11-16: `GEO_DAILY_2026-11-16.md`, and — read these before trusting any tool —
`DEPLOY_GATE_MISDIAGNOSIS_2026-11-16.md` (why `verify-deploy` was red and why no publish was
needed), `HARNESS_GIT_ENV_2026-11-16.md` (why git fails in the agent shell), `TEST_ENV_2026-11-16.md`
(the command that actually runs the suite).

## 1. Project and repo

- **Repo:** `/Users/jo/work-staging/concierge-integration`, branch `main` (deployed).
  Measured at `be9a647`; the last code commit is `edc5dd1` (Hermes master, dashboard, Workwatch and the pen-test umbrella lane) and
  the handoff commits after it are docs-only. `main` is pushed to `origin/main`. This
  session drove the Docker→Podman cutover (see §3 and
  `QA/verification/PODMAN_MIGRATION_2026-11-17.md`) and retired Twenty, adding the Studio pipeline
  board (`QA/verification/STUDIO_PIPELINE_AND_TWENTY_RETIREMENT_2026-11-17.md`). The Hermes rollout
  is recorded in `QA/verification/HERMES_ROLLOUT_2026-11-17.md` (local-only — git-ignored because this
  repo is public) and §2 item 13 / §3 "Hermes on the VPS". The Hermes master migration is §2 item
  14 / §3 "Hermes master on the Mac" and `QA/verification/MASTER_HERMES_MIGRATION_2026-11-17.md`.
  **Hermes UI:** `http://127.0.0.1:9120` (user `jo`; password in
  `concierge-stack/hermes/hermes.env`, mode 600; loopback only). The dashboard's Cron page
  shows the jobs, including Workwatch, and the Chat page can select any profile.
  Working tree clean apart from ignored `outputs/`.
  The status pass and both handoff corrections are in
  `QA/verification/STATUS_HERMES_2026-11-17.md`.

- **Pen-test umbrella:** `Trendiisales/pentest-research-engine` at `9622d03`; Rust
  workspace `rust/`, GUI `http://127.0.0.1:9130` (loopback only), docs
  `docs/UMBRELLA.md`. It drives PRE, T3MP3ST, Ghidra and the scanners behind one
  signed-authorization/scope gate. Live proof and open items:
  `QA/verification/PENTEST_UMBRELLA_2026-11-17.md`.

- **Live:** `https://trendibizz.com` (site, 45 indexable URLs), `https://concierge.trendibizz.com/studio/`
  (portal), `https://chat.trendibizz.com/demo/pukeko-construction` (widget).
- **VPS:** `root@152.42.239.240`, key = repo file `./Concierge`
  (`ssh -o BatchMode=yes -o IdentitiesOnly=yes -i ./Concierge root@…`).
  Release dir `/opt/trendi/releases/20261108-vps`.
- **Deploy — do not improvise.**
  - Site: `KEY=./Concierge ./scripts/vps/deploy-site.sh`. Refuses a dirty tree, runs
    `python3 scripts/seo/site_seo.py check`, stamps `.deploy-manifest.json`, verifies, then pings
    IndexNow for the pages that changed.
  - Host tooling (`scripts/vps/`, including the health check): `KEY=./Concierge ./scripts/vps/sync-tooling.sh`.
    **New this session** — without it, editing the health check left `verify-deploy` red forever.
  - API: `KEY=./Concierge ./scripts/vps/deploy-api.sh` (copies `api/app`+`api/static`, rebuilds,
    recreates api+social, verifies). `redeploy-api.sh` now removes social before recreating api — a
    single `up --force-recreate api social` is refused by Podman and once left the API down.
  - Portal: `KEY=./Concierge ./scripts/vps/deploy-studio.sh`.
- **Verify before claiming anything is deployed:** `KEY=./Concierge ./scripts/vps/verify-deploy.sh`
  → must print `OK: repo and box agree` (currently api/app 110 · api/static 7 · scripts/vps 42 ·
  website/site 62 — green at `be9a647`).
- **Tests:** `cd api && PYTHONPATH="$(cd .. && pwd)/QA/verification/shims" \
  TEST_DATABASE_URL=postgresql://postgres:pw@127.0.0.1:55433/postgres \
  /Users/jo/work-staging/venv-concierge/bin/python -m pytest -q` → **1527 passed, 19 skipped**. The interpreter,
  the shims and `Pillow` are all required; the old bare `python3 -m pytest -q` collects 101 errors
  (`QA/verification/TEST_ENV_2026-11-16.md`).
- **Agent shell git:** if every git command dies with `missing config key GIT_CONFIG_KEY_0`, it is the
  harness, not the repo — prefix `env -u GIT_CONFIG_COUNT` until the harness restarts
  (`QA/verification/HARNESS_GIT_ENV_2026-11-16.md`).
- **Health (on the box):** `python3 scripts/vps/healthcheck.py --no-alert` →
  **46 ok / 2 warn (`inbound:onboarding`, `sms:inbound`) / 0 fail**.
- **Website technical SEO:** `python3 scripts/seo/site_seo.py check` (the deploy gate),
  `python3 scripts/seo/site_seo.py sitemap --write` (the sitemap is generated, never hand-edited).
- **Earlier record:** `HANDOFF_ARCHIVE_2026-11-15_1430.md` holds the session-by-session detail
  (§6a–§6q, §7, §8). Nothing there was dropped; the worklist below is the current list.

## 2. What the 2026-11-15 sessions did

The first three streams are recorded in their own files. The last one is this session:

1. **Audit** — 12 defects found and fixed (invitation sign-in crash, service-worker recovery, settings
   nav, missing h1s, mobile overflow, baked-in SSH key, silent backup failure, missing restore drill,
   unmonitored SIP firewall, `api.env` sourcing bug, stale cron copy). See `SYSTEM_AUDIT_2026-11-15.md`.
2. **SEO content pass** — nine thin money pages grown to 903–1,238 words, ten snippets trimmed,
   `/ai-visibility` turned into a guides index, a bulk "worldwide" geo rewrite reverted in seven
   places, and a `site:pages` health guard. See `SEO_PASS_2026-11-15.md`.
3. **Email engagement + mail auth** — first-party click tracking, Brevo events on the timeline,
   HTML alternative, pending-invites list, `email:auth` check. DKIM was never missing (Brevo
   publishes at `brevo1`/`brevo2`) — that false alarm is recorded so it is not re-raised.
4. **One central repository, enforced** — the site publishes only from this repo, with a deploy
   manifest and a checksum parity check. See `CENTRAL_REPO_2026-11-15.md`.
5. **SEO growth implementation (this session)** — the outside audit's seven ideas, implemented as far
   as they can be without inventing facts. Full detail in `SEO_GROWTH_2026-11-15.md`; the short version:
   - A **technical SEO contract** now gates every deploy and is checked live (`site:seo`): canonical,
     `noindex`, `dateModified`, snippet length, internal links, sitemap parity, `robots.txt` policy,
     IndexNow key. `site:data` guards the research data's freshness.
   - **Seven live defects fixed**, found by the guard on its first run: 21 AppleDouble files committed
     to the web root; `/glossary` (1,043 words) `noindex` and missing from the sitemap; 11 pages with
     no `dateModified`; 13 wrong sitemap `lastmod` values, one malformed `<url>`, one missing `lastmod`;
     the research page linked from nowhere; a Dataset with no `distribution`; and a calculator parser
     that turned junk input into "1 missed call a week".
   - **New:** `/ai-receptionist-nz` (NZ hub), `/tools/missed-call-cost-calculator` (link magnet with a
     shareable URL), the crawler research as a **living data page** (refresh log, CSV distribution,
     freshness check), IndexNow submission on deploy (HTTP 200 for 24 changed URLs), and
     `scripts/vps/sync-tooling.sh` after the deploy gate exposed that host tooling had no publish path.
   - 54 new tests (1413 total at that point; 1420 today), three mutation proofs, deploy verified, live health 46 ok / 0 fail.

6. **The "red deploy gate" of 2026-11-16 was a missing merge, not a pending publish (corrected this
   session).** The previous handoff said the box carried NZ$/GST hand edits and needed an approved
   publish. Measured instead: the box's two calculator files hash-match its own deploy manifest and
   the repo at `08cbdda` — it was never edited. Local `main` had simply diverged from `origin/main` at
   `7f6e223` and never took `21cda5b` ("remove FREE, GST and NZ$") and its four successors. Local
   `main` was the side carrying the GST wording; publishing it would have put that live. Merged
   `origin/main` instead (`82c2af6`), kept origin's stronger `noindex` guard, dropped the duplicate
   local loop. `verify-deploy.sh` is now **`OK: repo and box agree`** with no deploy performed. See
   `QA/verification/DEPLOY_GATE_MISDIAGNOSIS_2026-11-16.md`.

7. **Tooling defects found and fixed this session** (all three: fixed, tested, documented):
   the harness subprocess env scrub that broke every git command
   (`QA/verification/HARNESS_GIT_ENV_2026-11-16.md`), the documented test command that could not run
   (`QA/verification/TEST_ENV_2026-11-16.md`), and `Pillow` missing from `requirements-dev.txt`.

8. **Invitation QR — 2026-11-16 (this session).** The token page no longer shows only a raw link:
   both Studio (`/studio`, Team → Create invitation) and the legacy owner page (`/owner-ui`) draw a
   QR for the same `#invite=` URL, with a print download. The encoder is vendored under
   `api/static/qrcode.js`, served at `/owner/qrcode.js`; the inner SVG is hidden from assistive tech
   so the labelled wrapper is announced once. Verified by 3 Python tests, a clean portal build, and
   decoding real Chrome screenshots of both pages with OpenCV. Deployed and checked live:
   `/owner/qrcode.js` 200, the live `/owner-ui` produces a decodable QR, `/studio/` serves the new
   bundle. Full record: `QA/verification/INVITATION_QR_2026-11-16.md`.

   The same deploy uncovered and fixed a real tooling gap: `verify-deploy.sh` never compared
   `api/static`, and the documented API deploy copied only `api/app`, so `owner.html`, `widget.js`
   and `qrcode.js` could be committed but never reach the box. Added `scripts/vps/deploy-api.sh`
   (copies both, rebuilds, restarts, verifies), extended `verify-deploy.sh`, and updated `AGENTS.md`.
   A first version of the script omitted the host from the SSH argv and failed with
   `hostname contains invalid characters`; fixed and re-tested.

9. **Quotation system rebuilt — 2026-11-16 (this session).** The quote was a title, lines and a
   tax percent. It is now a document and a lifecycle: per-line units and discounts, a job discount
   with tax on the discounted amount, a quote date and valid-until, frozen per-quote terms, a
   customer who need not be an existing enquiry, `viewed_at`, and a typed acceptance name.
   Lifecycle is draft → reviewed → sent → accepted/declined (+ void), with edit (optimistic
   locking), duplicate, explicit resend, and manual acceptance that issues the invoice. One
   renderer now produces both the printable document and the customer page (the two HTML strings
   had drifted). The Studio page was rebuilt as a builder with live totals; its old block was
   moved out of `CrmQuotes.tsx`. Proof: `api/tests/test_quotations_system.py` (25 tests, two
   mutation proofs), 1402 passed with the 29 known DB-outage failures, `tsc` clean, portal built,
   deployed and verified live. Full record: `QA/verification/QUOTATION_SYSTEM_2026-11-16.md`.

10. **Install QR fixed — 2026-11-16 (this session).** The QR in Studio → Setup was drawn from the
   hosted chat page (`chat.trendibizz.com/demo/<slug>`), and the app was not installable anyway:
   the shell never linked `manifest.webmanifest`, so Chrome never fired `beforeinstallprompt` and
   the header's Install button never appeared. Fixed: manifest + apple-touch-icon + theme meta are
   linked, the manifest carries `id`/`display_override`/shortcuts, the install offer is captured at
   startup (`src/installPrompt.ts`), a public `/studio/install` page explains the one tap (Android)
   or Share → Add to Home Screen (iPhone), and Setup now shows a downloadable **install** QR. The
   chat page keeps its link but lost its QR and is labelled "not the app". Proof: 12 tests, two
   mutations, and the live page's QR decoded with OpenCV to
   `https://concierge.trendibizz.com/studio/install`; headless Chrome on the live page rendered the
   one-tap Install button. **Follow-up the same day:** on a phone that URL opened the Studio's
   sign-in screen instead, because it was a route inside the SPA. It is now a standalone document
   served by `main.py` before the catch-all — no router, no auth, no email field — with the SPA
   branch and `Install.tsx` deleted. Same day again: iPhone users could not find Safari's Share
   button, so the page now draws the icon, names the in-app browsers, and gives the Edit Actions
   recovery. Then the copy button was shown *in Safari* (the only control people noticed), so
   Safari now gets the three steps alone and other browsers get the copy card; a `navigator.share`
   button was built and removed because the Web Share sheet does not carry Add to Home Screen. The
   installed app can now finish sign-in by pasting the emailed link, because a home-screen app has
   its own storage and the link opens in Safari. **iOS has no one-tap install** — only Safari's
   Share → Add to Home Screen; a native App Store app is the only simpler route and is an operator
   decision. Record: `QA/verification/PWA_INSTALL_QR_2026-11-16.md`.

11. **Social marks, mobile controls and a stricter SEO gate — 2026-11-16 (this session).** The
   Studio's social connections were text buttons ("Connect linkedin organization"); they are now
   connection cards with the official full-colour marks and a clear state, and the composer marks
   each connected account. The public footer's five text links became colour-mark buttons on all
   40 pages, each with a visually hidden name so the link stays describable. Two real site defects
   were found and fixed on the way: the closing call-to-action was **white on white** (a
   same-specificity cascade loss; measured live, now purple on white) and the eyebrow above the
   purple band was purple on purple. The chat launcher and language pill collapse to 56px / 44px
   marks on a phone instead of covering the page. The SEO gate gained six rules (JSON-LD must
   parse and exist, `alt` on every image, no skipped heading levels, unique descriptions, absolute
   `og:image`) and found four real heading jumps, now fixed. Proof and the headless-Chrome
   false-alarm note (a `--window-size=390` screenshot is cropped, not a mobile layout) are in
   `QA/verification/SOCIAL_ICONS_AND_SEO_2026-11-16.md`.

12. **Studio sales pipeline board + Twenty CRM retired — 2026-11-17 (this session).** A drag-and-drop
    kanban over the same five lead stages (`new → contacted → booked → won → lost`) the dashboard and
    weekly summary already use: `GET /owner/crm/pipeline` (the `sales.pipeline()` board) and
    `POST /owner/crm/leads` (add an offline opportunity), with `Pipeline.tsx` in Studio → Sales. Cards
    also have a stage menu so it works on touch. Twenty CRM was deleted entirely — compose `crm`
    profile, bridge, API delivery queue, Grok-agent push and volumes — it had never been used. Proof:
    1523 API tests, portal `tsc`/build, `verify-deploy.sh`.
    Record: `QA/verification/STUDIO_PIPELINE_AND_TWENTY_RETIREMENT_2026-11-17.md`.

13. **Hermes rollout — 2026-11-17 (deployed, idle by design).** The customer-facing Hermes layer is
    live on the box: `hermes-gateway` on `127.0.0.1:4420` (host network, read-only, all caps
    dropped) authenticates to the API through `HERMES_GATEWAY_*`; the per-tenant
    `hermes-trendi-support` container is healthy with only `todo`, `memory` and `session_search`
    enabled; Studio → Home gained **Needs you** (approve/edit/discard a prepared reply) and the
    read-only **Ask** box, and Setup has the 7am-note switch (`35f3efd`). The 7am note is on for
    `trendi-support` only. **Nothing calls the customer gateway's `POST /v1/runs` yet**, so no customer
    case has ever been planned:
    `hermes_actions`, `hermes_case_state` and `hermes_tenant_settings` are all empty and the
    gateway's default is `shadow` / 0.8. Full account and the defects found on the way:
    `QA/verification/HERMES_ROLLOUT_2026-11-17.md` — **local-only, git-ignored** because this repo is
    public, so a fresh clone will not have it; this handoff carries the state that matters. The
    "Still to do" lettered list in that record is partly stale — (b), (c) and (d) are done as of
    `35f3efd`.

14. **Hermes master + subagents — 2026-11-17 (now owns the Trendi routines).** The Mac
    `hermes-concierge` runs the Grok Bot schedules as six Hermes profiles (`trendi-master`
    plus `seo-engine`, `trendi-desk`, `pen-test`, `site-watch`, `workwatch`) and 14 cron
    jobs: **12 active, 2 paused** (tamper watch, Ego Lite). The package is `hermes/`
    (manifest, idempotent installer, 24 tests, Mac runtime). The **dashboard** is at
    `http://127.0.0.1:9120` (loopback only, password in
    `concierge-stack/hermes/hermes.env`). **Workwatch is active** (Mon 08:00, notes mounted
    read-only; first report `Status: quiet` for 2026-11-10..16). The VPS customer Hermes is
    unchanged and still has no trigger. Live proof, the defects found while installing, and
    the open items: `QA/verification/MASTER_HERMES_MIGRATION_2026-11-17.md`; the worklist is
    §3 "Hermes master on the Mac" M1–M10.

15. **Authorized pen-test umbrella — 2026-11-17.** The Rust workspace at
    `9622d03` (`Trendiisales/pentest-research-engine`) has the authorization/scope
    gate, the audit chain, the report, the CLI and the Axum umbrella GUI at
    `http://127.0.0.1:9130`. It integrates PRE (`~/go/bin/pre`, PWA `:8765`),
    T3MP3ST (`:3333`, War Room), Ghidra (`~/bin/analyzeHeadless`) and the host
    scanners. The offer, methodology, tool matrix and runbook are in the repo's
    `docs/`. Live proof: 33 Rust tests, clippy clean, 26 tools, T3MP3ST 70 tools /
    12 findings, a dry-run gate and an out-of-scope refusal. Open items P1–P8 in §3
    and `QA/verification/PENTEST_UMBRELLA_2026-11-17.md`.

## 3. Outstanding — the real worklist

**2026-11-17 — the Docker → Podman migration on the VPS is DONE** (production `trendi` + `asterisk` run on
Podman; the Docker engine is disabled but kept installed, `/var/lib/docker` untouched; a real reboot was
survived; the 23:10 "unidentified" reboot was that reboot test). Remaining migration open items live in
`QA/verification/PODMAN_MIGRATION_2026-11-17.md` "Still open": the Hermes `network_mode: host`/`cap_drop`
re-test (both containers **are** running under Podman — gateway `healthz` 200 on host networking, customer
container healthy with its `cap_add` set — but the boundary re-test itself has not been written up), keep
Docker installed for a week, and operator items (delete the one-day DO token; approve or
decline the Version 1 announcement email — do NOT send it without Jo). **The Twenty CRM was retired on
2026-11-17** — see `QA/verification/STUDIO_PIPELINE_AND_TWENTY_RETIREMENT_2026-11-17.md`.

### Hermes master on the Mac — owns the Trendi work (live 2026-11-17)

The Grok Bot schedules and procedures for Trendi/Concierge now run in Hermes as a
master plus five persistent subagents on the Mac: `hermes-concierge` (loopback only),
profiles `trendi-master`, `seo-engine`, `trendi-desk`, `pen-test`, `site-watch` and
`workwatch`. **14 cron jobs: 12 active, 2 paused** (tamper watch, Ego Lite). The 12
Grok Trendi automations are mapped in `hermes/JOBS.md`; the Omega bots
are a separate project and are not in scope. The package is `hermes/`; the live proof,
the dashboard and the defects found while installing are in
`QA/verification/MASTER_HERMES_MIGRATION_2026-11-17.md`.

M1. **Pause the Grok cloud copies.** The six Workwatch launchd labels are disabled, but
    the Grok Bot cloud automations cannot be paused from this repo. Jo must pause (not
    delete) the 11 Trendi automations in Grok Bot, or they may double-run with Hermes.
    The list is in `hermes/JOBS.md` under "Pause the remaining Trendi automations".
M2. **First scheduled runs:** 2026-11-18 at 07:00 social drafts, 07:30 deep dive, 07:40
    daily monitor, 08:00 master brief. Check `~/.workwatch/reports/hermes/*/latest.md`
    and the master brief. A lane with no dated routine report is `UNANSWERED`, not quiet.
M3. **The first manual monitor run flagged** `/sitemap.xml` and `/llms.txt` changed with
    no `changes.csv` row, plus two new queries. The test re-runs seeded the state, so the
    current report is quiet. Verify the change was planned before trusting the next run.
M4. **Tamper watch is paused** — it needs a read-only Cloudflare token on the Mac and the
    tamper kit in `trendi-site/scripts/security/` (`JOBS.md` T1).
M5. **Workwatch weekly — DONE 2026-11-17.** Active Mon 08:00 (job
    `b8c9000b442b`), `~/.workwatch/notes` mounted read-only, first report
    `Status: quiet` for 2026-11-10..16 (481 bytes). It is the `workwatch` lane in the
    master brief and is visible in the dashboard's Cron page. The routine still refuses
    raw shell history, credentials and personal detail.
M6. **Pen Test profile + umbrella — updated 2026-11-17.** The profile now points at the
    umbrella (`:9130`) and the authorized-testing rules; there is still no scheduled
    routine. The biweekly news and social drafts cover the defensive content lane; the
    engagement work is P1–P8 below.
M7. **The image is `:stable`.** Pin `HERMES_IMAGE` to the digest printed by
    `hermes/runtime/start-master.sh` so a restart cannot change the agent.
M8. **The reports tree is `0777`** on the Mac mount so the container user can write. It
    holds no secrets, but it is world-writable; revisit if the Mac is shared.
M9. **The Mac must be awake.** `--catch-up on` runs a missed job once on wake. The VPS is
    not involved in these schedules.
M10. **The VPS customer Hermes is unchanged** — still restricted to todo, memory and
    session_search. The Mac master is the operator agent, not the customer planner.

### Authorized pen-testing umbrella — live 2026-11-17

The Rust umbrella is the single console for authorized testing:
`http://127.0.0.1:9130` (loopback only). Repo `Trendiisales/pentest-research-engine`
at `9622d03`, docs `docs/UMBRELLA.md`; proof
`QA/verification/PENTEST_UMBRELLA_2026-11-17.md`. It drives PRE, T3MP3ST, Ghidra and
the host scanners; the Rust engine enforces the signed authorization and scope before
any active step.

P1. **Full scan ready; no customer run yet.** The landing tab is the one-field full
    scan (address + engagement + acknowledgement) and defaults to the valid
    `Trendi (self-owned)` engagement with `trendibizz.com` filled in. `engagements/trendi-self` is valid
    for `trendibizz.com` (self-authorization) and the preview listed 10 stages;
    `engagements/pukeko` exists but is **invalid until its signed permission is
    attached**. Run the own address first, then Pukeko.
P2. **T3MP3ST missions launch in the War Room**, not the umbrella. The umbrella reads
    health/arsenal/findings and links to `:3333/ui/`; T3MP3ST's agent session,
    approvals and receipts stay native. A unified mission launcher needs its API and
    approval model mapped deliberately.
P3. **Ghidra is detected but no real binary has been analyzed.** Run one lab binary,
    keep the project under `<root>/ghidra/`, and record the output.
P4. **PRE active is armed only for `trendibizz.com`.** A customer target needs its own
    `pre.yaml` scope; the umbrella gate runs first.
P5. **Missing host tools:** feroxbuster, dalfox, rustscan, naabu, semgrep, trivy,
    grype, osv-scanner, gitleaks, radare2, jadx, apktool, binwalk. The Tools tab has
    the install commands; T3MP3ST's bundled arsenal covers several.
P6. **The Rust runner is not a root boundary.** Keep the root-owned
    `~/.config/pentest-router/pentest-exec` until the Rust executor is installed; do
    not run a customer test on a shared Mac without it.
P7. **The authorization/contract/insurance package has not been legally reviewed.**
    `docs/PENETRATION_TESTING_SERVICE.md` §3 has the minimum contents; counsel and
    insurance are needed before the first paid test.
P8. **Pricing is not set.** `hermes/BUSINESS.md` §7 is a shape, not a quote.

### Hermes on the VPS (customer planner) — deployed, still not triggered

The Mac master above now owns the Trendi routines. This section is the customer-facing
per-tenant planner; it is separate, restricted, and still has no trigger.

H1. **Nothing triggers a customer run.** The VPS `POST /v1/runs` exists and the gateway
    can reach Concierge, but no inbound-message hook, scheduler or Studio button calls
    it. `hermes_actions` is empty, so no customer plan has ever been validated or
    executed. **Next:** pick the first trigger (the inbound-email hook is the natural
    one, because drafts already land in `email_drafts`), keep the tenant in `shadow`, and
    run one case that has a real lead. `trendi-support` has no leads at all; use a tenant
    that does. Do not enable a non-shadow autonomy level until one shadow plan has been
    read end to end.
H2. **The customer image floats.** `hermes-trendi-support` runs `nousresearch/hermes-agent:stable`
    (now v0.23.1); only the internal auxiliary is pinned by digest (v0.23.0). **Next:** pin
    `HERMES_IMAGE` to a digest in `hermes.sh`/the compose env before the first real run, so a
    restart cannot change the planner underneath a live tenant.
H3. **Source parity does not cover Hermes.** `verify-deploy.sh` compares `api/app`, `api/static`,
    `scripts/vps` and `website/site`; the gateway is built on the box from
    `concierge-stack/{hermes-gateway,core-rs}`, and `scripts/asterisk` is not compared either. A
    change to those sources alone can drift silently. **Next:** extend the parity check (or add a
    dedicated `sync-hermes.sh`) and run it before any gateway rebuild.
H4. **Minor, clear before the first run:** `hermes tools list` on the customer container prints
    `install out of sync (pnpm: not installed or outdated)`. The tool *set* is provably correct
    (todo, memory, session_search); the warning is a self-check, not a reason to widen the toolset.
    Rebuild the docker-managed artifact once and confirm it goes quiet. The gateway's `network_mode:
    host` is deliberate (it must reach API/Hermes on loopback) and it holds no DB or provider
    credentials — keep it that way.
H5. **The 7am note has still never delivered — and that is correct so far.** `trendi-support` has
    `daily_summary = true` but measured 0 new leads, 0 overdue tasks and 0 waiting leads, and
    `daily_text` deliberately sends nothing on a quiet day. There is no `daily:*` outbox row and no
    log line that distinguishes "ran and was quiet" from "never ran". **Next:** prove it on a
    morning with one real or seeded lead, and add a heartbeat/log line so a silent loop is visible.
    The operator's "check after 07:00" item is therefore answered: no email was due.
H6. **Committed code cites a record that is not in the repo.** `hermes-gateway/README.md`,
    `tests/acceptance.rs` and two older QA records cite `HERMES_CONCIERGE_FRAMEWORK_2026-11-09.md`,
    which `.gitignore` excludes along with every `QA/verification/HERMES_*` (the repo is public;
    the Hermes design notes have never been committed). A fresh clone therefore has dangling
    references and no Hermes design history. **Next:** decide the home for Hermes design records —
    a private docs repo, or a redacted framework summary committed here — then repoint the
    citations. Do not simply remove the ignore: that would publish the full design notes.

### Operator only (cannot be fixed from this repo)

1. **DECIDED 2026-11-16 — prices are tax-inclusive (option A), and Stripe still adds 15%.** Jo:
   "we include the tax for nzd" → the USD figure on the page is the total every customer pays; prices
   stay $250 / $2,700 (SEO since changed to USD 500 / 500, below); no currency change, no GST wording. **Blocked on Jo** creating
   four tax-inclusive Stripe prices and repointing the four Payment Links (a price's tax behaviour is
   immutable — new prices are required; automatic tax stays on). **Then I finish:** update
   `products.js` + the buy links in `pricing.html`, turn the "Do prices include tax?" FAQ (currently
   the non-answer `Prices are in USD. `) into a real answer, add a test that fails on a non-answer,
   deploy and verify. The copy must not ship before Stripe is inclusive or the page lies. Full steps
   and the revenue consequence (~13% less per NZ sale) in
   `QA/verification/PRICING_TAX_INCLUSIVE_2026-11-16.md`.
   **RESOLVED 2026-11-16, commit `912452f`:** Jo supplied the replacement tax-inclusive SEO links
   (`00wcN70IP4hJdwU8FpcEw06` USD 500/month, `7sY7sNgHN6pR50obRBcEw05` USD 500 deposit); the dead
   `28E8wR…`/`28EcN7…` links are gone from the repo and from live HTML, prices read USD 500 / USD 500,
   the tax FAQ answers "Yes", and `site:prices` guards against both regressions. Deployed and
   `verify-deploy.sh` is clean. Remaining: Cloudflare still caches an old `/products.js` (purge or wait).
   See `QA/verification/DEAD_PAYMENT_LINKS_2026-11-16.md`.
2. **CLOSED 2026-11-16 — yearly is not contradictory.** `products.js` carries a live yearly link
   (`6oU28s8OH7b76528aQ04804`, USD 2,700/year, price `price_1UbnwwJVm2iwIxUdMoJ9g2Ve`), `/pricing` and
   `/concierge` both advertise it, and all four buy links returned HTTP 200 on 2026-11-16. The old
   "yearly link is empty" claim was stale. Only Jo's confirmation that yearly is still wanted remains.
3. **Rotate secrets:** the VPS root SSH key (was readable inside the API image) and the live Stripe
   secret key; rotate the Stripe webhook secret too.
4. **LinkedIn MDP review**, **TikTok token**, **Conrad's snippet**, **Ahrefs mail rule**,
   **replacement Concierge payment link**, **Cloudflare JS detections** — unchanged from the archive.
5. **Inbound SMS has never arrived** (`sms:inbound` warn, 1 paired phone). Needs a text sent to the
   business number.
6. **RETIRED 2026-11-17 — the Twenty CRM stack** (`crm` profile) is gone: compose profile, bridge, API
   delivery queue, Grok-agent push and the volumes were deleted; it had never been used. The Studio's own
   pipeline/contacts/quotes are the CRM. See `QA/verification/STUDIO_PIPELINE_AND_TWENTY_RETIREMENT_2026-11-17.md`.
7. **Search Console and Bing Webmaster — and the two halves are not in the same state.** Measured
   2026-11-16: the domain TXT already carries
   `google-site-verification=avVhzA1EiofmOxiN_MaeFFNEsykt1q8QAfbrLBSStMA`, so Google ownership is
   very likely already proven — the GSC job may only be "add `https://trendibizz.com/sitemap.xml`"
   (43 URLs, HTTP 200, lastmods 2026-11-15). There is **no** Bing verification record. Bing feeds
   ChatGPT search. Without Search Console there is no data on which page is served for which query —
   the one thing the content work cannot measure itself. IndexNow covers Bing's crawl signal on every
   deploy, but not the dashboard. See `QA/verification/OPERATOR_FACTS_2026-11-16.md`.
8. **No web analytics** — a click is recorded, the landing visit is not. Needs an account (Plausible
   is the sane pick: cookieless, no consent banner).
9. **Named author / team page** — schema `author` is the Organization until a real named author with a
   bio exists.

### Security / hygiene still open

10. UDP 10000–10099 (RTP) is reachable from the internet; Docker DNAT bypasses ufw and only 5060 is
    filtered. Closing rules are in the header of `scripts/vps/harden_host.sh`.
11. containerd holds ~65 GB of old images (disk 47%). Keep 2–3 `before-*` tags, prune the rest.
12. `/opt/trendi/releases` is world-readable and its test fixtures embed ~32 DSNs and a `whsec_`;
    containers still run as root without `no-new-privileges`.
13. **RESOLVED 2026-11-17** — `/var/run/reboot-required` is clear after the Podman-migration reboot;
    `trendi-sip-firewall.service` is `active` and health is 0 fail.
14. **Commit-time teeth are not installed** — the enforcement catches drift after the fact. A
    `pre-push` hook running the suite plus branch protection on `origin` still needs a decision.
15. **Secrets stay off-repo by design.** `/opt/trendi/shared/api.env` is the source of truth; never
    commit it or copy it into a release tree.

### Unverified product surface (unchanged from the archive)

16. Phone answering end to end: inbound call to the business number, outbound AI callback, transfer
    to the owner, voicemail, and RTP only after item 10.
17. Inbound email and inbound SMS round trips (SMS blocked on item 5).
18. Social publishing to Meta/Google/LinkedIn/TikTok on a real tenant, and the review-request flow.
19. Owner-facing flows only touched by automation: quotes → invoice, designs and CAD uploads,
    marketing-media library, reports export.
20. Anything in §6/§7 of `HANDOFF_ARCHIVE_2026-11-15_1430.md` not named above.

### SEO growth — what the outside audit asked for and what is left

21. **Shareable report pages + "Checked by Trendi" badge** for `/tools/site-check` and
    `/tools/robots-ai-check`. Not built: both tools render results into the DOM as they run, so a
    report needs a stable result record, a URL-encoded store and a page that renders a stored result.
    Half-building it ships broken shared links. **Next:** define the result record → store in the URL
    fragment → `/tools/report/…` renders it → `/brand/checked-by-trendi.svg` badge links to the tool.
22. **City pages (Auckland/Wellington/Christchurch).** Not built, deliberately: the audit's own
    condition is a real case study per city, and there is none published. **Next:** one real case
    study (Pukeko Construction is a live tenant) with real numbers, then one page per city.
23. **Partner co-branded pages.** Needs named partners. **Next:** `website/partners.json` + a generator
    that emits `/partners/<slug>` when the first partner agrees.
24. **"Real questions from callers" data page.** Needs anonymised, consented transcripts from a real
    tenant. Publishing invented "top questions" is the one thing this site says it does not do.
25. **Publishing cadence** — two posts a month on the existing cluster; the first is queued in
    `HANDOFF_ARCHIVE_2026-11-15_1430.md`: "we asked ChatGPT, Perplexity and Google AI Overviews the
    same 12 NZ business questions".
26. **Living data page refresh** — the December 2026 re-fetch is promised on the page and on the
    refresh log. `site:data` warns at 45 days and fails at 120, so it cannot go quiet, but the refresh
    itself is manual: re-run the collection, replace `research/ai-crawler-blocking-2026/data.csv`,
    bump `temporalCoverage` + `dateModified` + the refresh log, then deploy (IndexNow fires itself).
27. **Link earning** — pitch the crawler study to NZ business press; get the two tools listed in NZ
    small-business and agency directories.

### Quotations (from the 2026-11-16 rebuild)

34a. **Walk the quote flow once with real data.** Production has **no `quotations` rows**, so
   draft → approve → send → customer opens → accepts → invoice → confirm payment has never run
   end to end outside tests. **Next:** in Studio → Quotes, write one real quote (a walk-in
   customer is enough), approve it, send it to an address you control, open the link, accept with
   a typed name, then confirm the invoice appears. If anything breaks, it is a bug to fix in that
   session, not a note.
34d. **The Studio's Social page has not been seen signed in.** The connection cards are covered by
   types, the production build and source tests, but they sit behind authentication, so no
   screenshot of the real cards exists. **Next:** sign in, open Social, connect or inspect one
   account, and confirm the marks, states and button labels read correctly.
34e. **The mobile checks are device emulation, not a handset.** 390px emulation shows no overflow
   and the compact controls measure 56px and 44px, but nobody has held the phone. **Next:** open
   trendibizz.com on an Android and an iPhone, check the launcher, the language pill and the footer
   marks, and scroll the whole page once.

34c. **The install path is proven in Chrome, not on a phone.** The live page's QR decodes to the
   install URL and headless Chrome offered the install, but no physical Android or iPhone has
   installed it. **Next:** scan the Setup QR with one of each, install, open from the home screen
   and sign in; note the iOS "Add to Home Screen" route separately, because Apple gives no prompt.

34b. **No browser test for the builder.** The checks are `tsc`, the build, lint and source-shape
   tests; a click-through regression (e.g. the send dialog after an edit) would not be caught.
   **Next:** if the flow is touched again, add a Playwright pass against the Studio with a mocked
   API, or at minimum assert the state machine in a component test.

### Repository hygiene

28. **Delete `/Users/jo/work-staging/trendibizz-live/site.legacy-20261115`** once another deploy cycle
    proves nothing writes to the old layout.
29. **`scripts/seo/geo-daily.py` — scheduled, and its change detection was broken (fixed 2026-11-16).**
    It now runs on a daily schedule and records Bing visibility. Its `len(text)` fingerprint was
    defeated by Cloudflare's per-request challenge script (`__CF$cv$params`), so every run reported
    all pages changed and re-pinged IndexNow for the whole site; the fingerprint now strips that
    script and hashes the content plus the page's own `dateModified`. Fixed, 3 tests
    (`api/tests/test_geo_daily.py`), mutation-proved, state re-seeded for all 43 URLs — see
    `QA/verification/GEO_DAILY_2026-11-16.md`. **Verified on the first real cron day after the
    fix (2026-11-17):** the 07:00 run reported 43/43 changed because the state file still held
    pre-fix fingerprints (one-time migration), and an immediate second run reported
    `changed: 0` / `IndexNow: nothing changed` — so the fingerprint is stable and no new noise
    source exists. See `QA/verification/GEO_DAILY_2026-11-17.md`. **Next:** if IndexNow fires for
    pages nobody edited on a run that is *not* the first after a fingerprint change, suspect a new
    response-noise source before touching the threshold.

30. **CLOSED 2026-11-16 — the calculator "drift" was a missing merge, not box hand edits.** The box
    was never edited: its two calculator files hash-match `.deploy-manifest.json` and the repo at
    `08cbdda`. Local `main` had diverged from `origin/main` at `7f6e223`, so it still carried the
    NZ$/GST/NZD calculator text that `21cda5b` had already removed upstream — the *repo* was the
    side contradicting the no-GST decision, and the proposed publish would have put it live. Fixed by
    merging `origin/main` (`82c2af6`); `verify-deploy.sh` is `OK: repo and box agree` with nothing
    published. See `QA/verification/DEPLOY_GATE_MISDIAGNOSIS_2026-11-16.md`.
31. **A `googlebot`-only `noindex` was invisible to the deploy gate until 2026-11-16.** `/glossary`
    and `/research/ai-crawler-blocking-2026` carried `googlebot: noindex` beside `robots: index`, so
    Google was told not to index a 1,043-word guide and the living data page. Fixed in the repo and
    now caught by `site_seo.py`; the live pages already said `index`, so no deploy is needed for that
    pair. The merge kept `origin/main`'s stronger guard, which reads `robots`, `googlebot` **and**
    `bingbot` and reports disagreement between them; a `bingbot` case is now tested. See
    `QA/verification/GEO_DAILY_2026-11-16.md`.
32. **The harness git-env patch is local to this machine and will not survive a `dsh` upgrade.** It
    lives in the installed `@deepseek-ai/dsh-subprocess` (whole `GIT_CONFIG_*` family no longer
    inherited); the regression test is `~/.dsh/tooling-tests/subprocess-env-scrub.test.mjs`. **Next:**
    upstream the fix; after any `dsh` upgrade, run that test — if it fails, reapply the patch before
    trusting git, the deploy gate or the suite.
33. **The test environment is undocumented outside a QA record.** `venv-concierge`, the shims path and
    now `Pillow` are all required to run the suite; a new machine or session will hit 101 collection
    errors. **Next:** one checked-in script (`scripts/dev/test-suite.sh`) that asserts the interpreter,
    exports the shims path and runs the suite — then the AGENTS.md command becomes one line again.

34. **Local test Postgres was not running during the invitation-QR session.** The suite reported
    **1377 passed, 19 skipped, 29 failed**; every failure was
    `ConnectionRefusedError ('127.0.0.1', 55433)`, not an assertion. Start the test database
    (the command in §1 assumes it) and re-run the DB-backed subset before treating the suite as
    green. The QR change itself is covered by pure tests that passed.

## 4. Next action

**Nothing is blocked on a deploy.** `verify-deploy.sh` prints `OK: repo and box agree`; the
last code commit is `edc5dd1` (the `hermes/` package is Mac-only, not part of the VPS
comparison), and the handoff commits after it are docs-only.
The Docker→Podman move is done and reboot-tested; Twenty is retired; the Studio pipeline board is
live; the Hermes master is installed on the Mac. Do not run `deploy-site.sh` expecting to fix
drift — check `verify-deploy.sh` first.

**Next, in this order:**

0. **Walk the new pipeline board signed in** (item 12): Studio → Sales → Pipeline, drag one deal
   between two stages, add one offline opportunity, and confirm the dashboard/Reports numbers agree.
   The routes are live and tested; nobody has clicked it signed in yet.
1. **Quotations:** item 34a — write, approve, send and accept one real quote, because the new
   system has never carried real data. Everything it does is covered by tests, but tests are not
   a customer.
2. **Hermes master, first scheduled morning** (M1–M3): open `http://127.0.0.1:9120`
   (user `jo`, password in `concierge-stack/hermes/hermes.env`) and check the Cron page;
   on 2026-11-18 check the 07:00 social drafts, 07:30 deep dive, 07:40 monitor and 08:00
   master brief in `~/.workwatch/reports/hermes/`; pause the 11 Grok cloud copies (M1) so
   they cannot double-run; and confirm the `sitemap.xml`/`llms.txt` change the first
   manual monitor flagged (M3).
3. **Pen-test full scan** (P1–P3): open `http://127.0.0.1:9130`, choose **Trendi
   (self-owned)**, tick the authorization and run the full arsenal on
   `trendibizz.com`. Then attach Pukeko's signed permission and run it there. Keep
   T3MP3ST missions in its War Room. Set the authorization template, legal review,
   insurance and prices (P7–P8) before selling.
4. **VPS customer Hermes, first real plan** (H1): choose the trigger. If it is the inbound-email
   hook, keep the tenant in `shadow`, send one real enquiry to a tenant that has a case, and read
   the plan before letting anything execute. Pin the customer image first (H2), and extend source
   parity before the next gateway rebuild (H3).
5. **Cloudflare `/products.js`** — the tax-inclusive buy links shipped in `912452f`; purge the cached
   file if it still serves the old links (the only remaining follow-up from that item).
6. Verify `trendibizz.com` in Google Search Console (the DNS TXT already proves ownership — likely
   just submit the sitemap) and Bing Webmaster (no Bing verification exists), then submit
   `https://trendibizz.com/sitemap.xml` (item 7). Bing feeds ChatGPT search.
7. Rotate the VPS root SSH key, the live Stripe secret and the Stripe webhook secret (item 3).

Everything else in §3 is unchanged and uncancelled: the phone/SMS/email round trips (items 5,
16–18), the security/hygiene list (10–15), and the SEO content list (21–27) all still stand.

The GEO check is green on the technical side and empty on the commercial side: trendibizz.com is in
Bing's index (`site:` at position 10) but absent for all five target prompts. The cheapest next
content move is a dedicated `/ai-receptionist-for-small-business` page — the only one of the five
with no page behind it (item 25 covers the rest of the content list).

Before any future session ends, run `KEY=./Concierge ./scripts/vps/verify-deploy.sh`. If it is not
`OK: repo and box agree`, the session is not finished. Remember the `env -u GIT_CONFIG_COUNT`
prefix until the harness restarts (item 32).
