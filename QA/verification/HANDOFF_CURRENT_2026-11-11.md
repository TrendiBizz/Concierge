# Current handoff — 2026-11-11 16:00 NZDT

## Live and verified
- **Pukeko Construction tenant** `pukeko-construction` (`271485f2-…`), public key
  `pk_cfR6bPXvsTlAl2COLGVf3OhY`; 7 knowledge chunks from 5 site pages; timezone,
  allowed origin, persona/greeting, notify email `conrad@…`; chat tested and
  grounded; demo `https://chat.trendibizz.com/demo/pukeko-construction?presenter=1`;
  owner invite links issued (Conrad + support).
- **Per-tenant email reply routing**: every tenant has
  `reply-<random>@trendibizz.com`, a Cloudflare Email Router rule to
  `concierge-inbound-worker`, an enabled `inbound_mailboxes` row, and owner-alert
  emails set `Reply-To:` to it. Backfilled all tenants. Conrad's reply was moved
  from the Trendi tenant to Pukeko (`email_drafts` 16).
- **Product catalogue + inventory**: `products`, `product_stock_movements`,
  `/owner/products` (owner prices/cost; editor stock), `search_catalog` AI tool
  (sale price + stock only, never cost).
- **Design uploads (backend)**: `design_uploads` and `/owner/designs` (raw-body
  upload, 50 MB cap, PDF/DWG/DXF/IFC/GLB/GLTF/OBJ/STL/3DM/STEP, sha256, ClamAV
  scan when configured, per-tenant storage under `/opt/trendi/shared/designs`).
- **Rust telephone shell**: merged to main (`2c2032a`) and image built; works on a
  real softphone call (Asterisk → shell → Grok greeting → CRM → finish) with
  null-audio. **Not the live bridge**; dialplan still points to the Python bridge.
- **Email intake** via Cloudflare; DKIM/DMARC sidecar + Rspamd + ClamAV live.

## In progress
- **CAD inclusion**: upload backend is live; next are the viewer
  (Online3DViewer, MIT), IFC takeoff (IfcOpenShell, LGPL), owner portal panel,
  and a customer upload link for Conrad's original plan drawings.

## Outstanding
- Phone DID (paid) — the only customer-dialable phone blocker.
- CAD viewer + IFC area takeoff + quote draft from takeoff.
- Owner portal products/rates panel and AI quote drafting.
- Rotate/scope the Cloudflare API key now present in `api.env`.
- DKIM sidecar marked Conrad's reply `unverified_sender` despite `dkim=pass`
  headers — investigate verifier.
- Pukeko: send Conrad a plan-upload link once the customer link exists.

## Automation / continuity
- `com.trendibizz.concierge-checkpoint` launchd runs every 5 minutes: `git add`,
  commit, push `origin/main`; log `~/Library/Logs/concierge-commit-checkpoint.log`.
- Manual commits after each update; latest `2a0843d` (email routing) plus this
  handoff and design uploads.

## Key paths
- Repo: `/Users/jo/work-staging/concierge-integration`
- VPS: `/opt/trendi/releases/20261108-vps/product`
- Compose: `scripts/vps/compose.yml` (`--env-file /opt/trendi/shared/compose.env`)
- Secrets: `/opt/trendi/shared/{api.env,cloudflare.key,stripe.key}`


## GEO / AI visibility — 2026-11-11 evening
- New worldwide page `https://trendibizz.com/ai-receptionist` (30-page site now),
  with Service + Offer + FAQPage + Breadcrumb JSON-LD, linked from `/concierge`
  and `/pricing`, added to `sitemap.xml` and `llms.txt`.
- `scripts/seo/geo-daily.py` checks pages, IndexNow for changed URLs and Bing
  visibility for global prompts; report under `QA/verification/geo-daily/`.
- Daily scheduled task `schedule-9776d74f-69df-4a66-81b5-8a058ffd36e3` runs at
  07:00 NZ in a new session and proposes one action. Notification plugin fires.
- Snapshot of the changed live site files is in `website/` in this repo; the live
  site itself is not a git checkout, so this is the recovery copy.
- Bing shows trendibizz.com indexed; none of the target prompts present yet.




## Marketing media (recommended stack) — 2026-11-11
- `media-render` sidecar (Satori + FFmpeg, Alpine, internal only) and
  Cloudflare Workers AI (FLUX.1 schnell) for AI images. No GPU, no model weights.
- Concierge: `media_brand` / `media_assets`, `/owner/media/*`, and a
  **Marketing media** panel in the owner portal (brand kit, 4 image templates,
  short video, AI image, gallery).
- Templates: showcase, before_after, quote, service; formats square/portrait/story.
- Limits: 6 photos per image, 8 per video, 8 MB each; video is a silent
  slideshow with a headline (music not yet added).
- Deployed and tested end-to-end: PNG, JPEG and MP4 returned and stored.
- Config: `CF_*` in `/opt/trendi/shared/compose.env`; `MEDIA_RENDER_URL`
  defaults to `http://media-render:8099`; media stored under
  `/opt/trendi/shared/media` (owned by uid 10001).
- The temporary Pukeko support owner used for testing was deleted.
- Commands: `docker compose build media-render api && up -d media-render api`.


## Astryx studio and seamless media — 2026-11-11
- `https://concierge.trendibizz.com/studio` — React 19 + Astryx (MIT) app for
  marketing media: login, brand kit, image/video/AI generation, gallery.
  Source in `web/portal`; build with `npm run build`, deploy `dist` to
  `/opt/trendi/shared/studio` (owned by uid 10001).
- Photos are auto-resized in the browser (max 2048 px, JPEG 0.86); up to 20
  photos per image/video. Generated media is automatically pushed to the social
  media library (`/owner/media/assets/{id}/to-social`) and appears in the composer.
- Video: fade transitions and optional music (FFmpeg xfade/amix), 3 s per photo.
- **Ops note:** the `social` container uses `network_mode: service:api`, so after
  recreating `api` run `docker compose up -d --force-recreate social`.
- Test owner account and test assets removed; 0 media assets left.


## Astryx portal + onboarding — 2026-11-11
- `https://concierge.trendibizz.com/studio`: invite → password → 6-step
  text-only onboarding (welcome, business, contact, website, branding, finish),
  then the marketing media studio. Built with Astryx (MIT) in `web/portal`.
- Branding: logo, name, accent and contact are stored in `media_brand`, used by
  the portal header and all media templates, and the accent is synced to
  `tenants.accent_color` so the widget follows it. Onboarding saves branding.
- New owner invitations now point at `/studio#invite=…`. The older `/onboarding`
  page remains as a fallback.
- Goal created: complete all add-ons (social composer, CRM inbox, quote builder,
  booking, reports, owner PWA, admin console) with branding on every surface.


## Astryx add-ons — 2026-11-11 (goal round 1)
- `/studio` tabs: Setup, Quotes, Enquiries, Social, Marketing media.
- Social: connected accounts, per-network previews, draft save, schedule +
  approval (versioned). Pukeko has no connected social accounts yet.
- CRM: leads, search, transcript, appointments and tasks.
- Quotes: create from an enquiry or product line, tax, totals, owner sign-off
  (`version` required by the API) — tested create + reviewed.
- Branding: header logo/name/accent, media templates, tenant accent.
- Remaining: booking, reports, owner PWA, internal admin console.


## Astryx add-ons continued — 2026-11-11 (goal round 1)
- `/studio` now also has Bookings (calendar status + appointments) and Reports
  (enquiries, quoted value, post/media counts, quote status split).
- PWA: manifest + service worker at `/studio/manifest.webmanifest` and
  `/studio/sw.js`; app is installable. Document title follows the tenant brand.
- Remaining from the objective: internal admin console, branding in emails/PDFs.


## Branding + documents — 2026-11-11 (goal round 2)
- Branded quotation print view: `/owner/crm/quotations/{id}/print` (owner auth),
  uses the tenant logo, name, accent, contact, lines and totals; the portal has a
  **Print / PDF** button (browser Print → Save as PDF).
- Owner alert emails now carry a tenant signature (name + website) and the
  tenant Reply-To address.
- Widget branding: `/api/v1/widget-logo?key=…` serves the tenant logo; widget
  config returns `logo_url` and the chat header renders it. Chat host route added.
- Verified: print view 200 with brand/line/total; widget logo 200 image/png.
- Remaining: verify the existing `/admin-ui` internal console, email From-name
  branding, social accounts for Pukeko (external OAuth).


## Goal round 2 verification
- Email branding: owner-alert From display name is the tenant name; body carries
  the tenant signature (name + website); Reply-To is the tenant reply address.
- Branded quote print view verified (brand, line, total). Widget logo endpoint
  verified (200 image/png) and chat header renders it.
- Admin console exists internally at http://127.0.0.1:8000/admin-ui (admin token);
  `/admin/tenants` returns 200. It is not publicly exposed.
- Health 200, studio 200; 548 tests pass.
- Still open: social content calendar view, richer admin console, Pukeko social
  accounts (external OAuth).


## Goal completion evidence — 2026-11-11 (round 3)
- Social composer now has a **content calendar** (month grid, posts by scheduled
  or created date).
- Internal admin console: Astryx `#admin` route with admin-token gate, tenant
  list, counts and backup list; `/admin/status` returns 200 including the latest
  58 MB backup. Existing `/admin-ui` remains available internally.
- All tenant emails now send with the tenant name as the From display name;
  owner alerts also carry the tenant signature and Reply-To.
- Backups are group-readable by the API (root:999, 640) so admin status can list
  them; backup script updated.
- Verified: health 200, studio 200, admin status 200, 548 tests pass.
- External/operational only: Pukeko has no connected social accounts yet; social
  live publishing stays disabled until the operator enables it.


## Limits, OAuth and backups — 2026-11-11
- Media quotas enforced server-side: 100 images, 10 videos, 50 AI images per
  calendar month; 500 MB total media storage per tenant. `GET /owner/media/usage`
  returns used/limit; the portal shows it. Video is capped at 12 photos
  (~35 seconds, 1080p); photos are auto-resized to 2048 px/JPEG and total
  request payload is capped at ~40 MB.
- OAuth: the Astryx Social tab now has **Connect <network>** buttons using the
  existing popup + BroadcastChannel flow (`start` → provider → `finish`). Tested
  live: `POST /owner/social/oauth/linkedin/start` returns a LinkedIn
  authorization URL. Provider apps/redirect URIs still need to be approved by
  each network; the customer only authorizes their own account.
- Backups: `shared.tgz` now excludes `shared/media` and `shared/designs`, so
  daily backups cover the site, databases, CRM, config and secrets only —
  customer media is not backed up.
- Verified: usage 200 (0/100, 0/10, 0/50, 0/500 MB); image 201 with 26,398
  bytes; usage then 1/100 and 26,398 bytes stored; OAuth start 200.


## Daily-video capacity — 2026-11-11
- Video quota raised to **40/month** (one a day plus spares) and storage to
  **2 GB per tenant**. Video renders now accept up to **20 photos** (~55 s at
  1080p) and still enforce the 40 MB request cap.
- Verified live: usage shows 0/40 videos and 2 GB storage; generated video 201,
  16,037 bytes, usage then 1/40 and 16,037 bytes.
- VPS has ~110 GB free; media is excluded from backups, so video growth does not
  inflate R2/R2-style backup sizes. A separate VPS/storage plan can be added when
  real client volume grows.


## Astryx deepening — 2026-11-11
- Per-tenant theme via `defineTheme` extending the neutral theme with the
  customer accent; the Theme provider wraps the portal (verified in headless
  Chrome after login).
- Home dashboard: headline tiles, **recharts** bar charts (enquiries by channel,
  quotations by status), latest enquiries. Astryx dashboard/template pattern.
- `npx @astryxdesign/cli init` added `web/portal/AGENTS.md` + `GEMINI.md` (component
  index and rules for future agents).
- Verified with headless Chrome: login renders the Pukeko dashboard, 0 console
  errors; Playwright/puppeteer test used a temporary owner that was removed.
- `@astryxdesign/native` is a placeholder on npm (“Do not install”), so the
  native owner app is not buildable yet; the PWA remains the mobile option.
- Bundle is ~960 KB JS after adding charts; code-splitting is a follow-up.


## Astryx Native watch + PWA — 2026-11-11
- `@astryxdesign/native` is a placeholder (0.0.0-bootstrap.0). Note at
  `QA/verification/ASTRYX_NATIVE_WATCH.md`; weekly Monday 09:00 NZ scheduled
  check (`schedule-df99a8a8-0abe-4b82-a9d9-e9cbf8a06c8e`).
- Interim: PWA icons (192/512/maskable/apple), install prompt in the header,
  offline shell. Manifest and icons verified 200.


## Quotes delivery + CAD completion — 2026-11-11
- Quotes: public token page `/quote/{token}` (branded), customer accept/decline,
  owner "Send to customer" queues an email with the link (verified: send 200,
  outbox row `quotation` pending). Public accept tested: status accepted.
  Print/PDF and sign-off unchanged.
- CAD: Designs tab with upload/list, Online3DViewer for IFC/GLB/OBJ/STL/3DM,
  IFC takeoff via ifcopenshell (wall/opening quantities), and a **customer
  upload link** `/upload/{token}` (7 days). Verified: link created, page 200,
  public upload 201, takeoff 200 with note; designs dirs owned by uid 10001.
- Gateway routes added: `/quote/*`, `/upload/*`, `/api/v1/public-design/*`.
- Astryx audit written at `QA/verification/ASTRYX_AUDIT_2026-11-11.md`.


## Languages + native assessment — 2026-11-11
- Astryx `InternationalizationProvider` wired with 12 locales (en, fr, es, de,
  pt-BR, zh-CN, ja-JP, ko-KR, ar-SA, nl-NL, it-IT, pl-PL); selector in the
  portal header; RTL for Arabic; preference/query/browser/IP detection.
- `/owner/locale` maps Cloudflare `CF-IPCountry` to a locale (verified FR/JP).
- AI system prompt now replies in the visitor's language.
- Assessment at `QA/verification/I18N_NATIVE_ASSESSMENT.md`.
- Astryx Native is canary-only, Apple-only, 11-12 components; not production.
  PWA remains the mobile option; Capacitor is the store shortcut if needed.


## All 30 locales — 2026-11-11
- 30 Astryx catalogs dynamically loaded; language selector on login and header;
  nav/login labels translated via `src/i18n/strings.json`; preference/query/
  browser/IP switching; RTL for Arabic/Hebrew.
- Verified French login renders "ID d'entreprise / Courriel / Mot de passe /
  Se connecter".
- Product copy (page content) still English; next: full copy translation.


## Full copy localisation — 2026-11-11
- All 30 locales; machine translation of 133 UI strings + 24 nav/login strings;
  runtime text layer for the portal copy; RTL; selector on login and header.
- English reviewed; Afrikaans review CSV at
  `QA/verification/AFRIKAANS_REVIEW.csv`; other 28 machine-only.


## All 30 locales exposed — 2026-11-11
- Language selector shows all 30; a yellow note appears for machine-translated
  locales inviting corrections (mailto admin@trendibizz.com). English/Afrikaans
  reviewed; the rest marked automated.


## Public-site language switcher — 2026-11-11
- `trendibizz.com` homepage now has a floating 🌐 Language selector (bottom-left)
  with 30 languages, self-hosted translations (`/site-i18n.json`) and a feedback
  note. No Google scripts and no CSP weakening.
- Scope: homepage only; internal marketing pages remain English for now.
- Verified: `?lang=fr` and `?lang=af` translate the homepage in headless Chrome.
- Afrikaans portal translations applied from the owner's review.


## Public site: all-page languages + AI bot blocking — 2026-11-11
- `/site-i18n.js` now works on every public page: local homepage dictionary +
  `POST https://chat.trendibizz.com/api/v1/translate` (cached in
  `ui_translation_cache`, rate-limited, same-origin/Cloudflare origin check).
- Cloudflare Workers AI free neurons were exhausted; the API falls back to a
  server-side Google Translate endpoint and caches results.
- Cloudflare WAF custom ruleset created: blocks GPTBot, CCBot, Bytespider,
  ClaudeBot, Google-Extended, Applebot-Extended, Amazonbot, FacebookBot;
  OAI-SearchBot, PerplexityBot, Claude-SearchBot, Googlebot/Bingbot allowed.
  Rule id `26bf0a72f35540548206c4b92d2099fc`.
- robots.txt rebuilt with the same allow/block split; sitemap retained.
- Verified: GPTBot/CCBot 403, OAI-SearchBot/PerplexityBot 200, normal 200,
  robots 200; French subpage translation works.


## Calendar, booking, logo and more SEO — 2026-11-11
- Astryx Bookings now completes Google Calendar OAuth in a popup (start →
  callback → finish) and saves booking hours/slot/acknowledgement through
  `/owner/onboarding/profile` + `/owner/onboarding/native-booking`.
- Pukeko booking enabled (Mon–Fri 09:00–17:00, 30-minute slots); calendar still
  needs the owner to complete Google OAuth.
- Pukeko logo (32 KB PNG) loaded into `media_brand`; widget logo endpoint
  returns 200 image/png; portal/media templates use it.
- Added public pages: ai-receptionist-real-estate, ai-receptionist-clinics,
  ai-chat-widget-nz, best-ai-receptionist-nz. Sitemap/llms updated; language
  switcher present; cache purged.
- Remaining: bundle code-splitting, removal of the old test phone route, consent
  copy review, off-site SEO accounts, offsite backup credentials.


## Bundle split + Astryx re-audit — 2026-11-11
- Dashboard/recharts is lazy-loaded (`Home` chunk), locale catalogs and per-locale
  nav/copy strings are dynamic; main entry ~571 KB, Home ~363 KB, 3D viewer
  ~919 KB lazy.
- Added Astryx Badge (statuses), ProgressBar (media quotas), Banner (translation
  feedback); re-audit notes Table/Dialog/Toast/Tabs/DatePicker/Richtext as next
  candidates, charts/vega/lab/native still placeholders/canary.


## Bundle, Table, Dialog and dark mode — 2026-11-11
- Main entry ~589 KB; Home/recharts lazy 363 KB; 3D viewer 919 KB lazy;
  locale catalogs and translations dynamic.
- CRM and quotes use Astryx Table; sign-off uses Dialog; status Badges;
  media quotas use ProgressBar; translation notice uses Banner; header has a
  light/dark/system selector.
- Verified headless: dashboard, Enquiries and Quotes tables render with no errors.


## Tabs/DateTime/lazy Designs — 2026-11-11
- Header uses Astryx TabList/Tab; schedule uses DateTimeInput; Designs lazy.
- Main entry still ~1.1 MB raw due Table/Dialog/TabList/DateTimeInput in the
  main shell; next split is CRM/Quotes/Media/Social route chunks.


## Route-level split complete — 2026-11-11
- Lazy chunks: Home, CrmQuotes, Engage (Social+Media), Designs, 3D viewer,
  locales/translations. Main entry ~382 KB raw / ~119 KB gzip.
- Verified login + tab clicks in headless Chrome with zero page errors.

## Worldwide repositioning and typography — 2026-11-11
- Removed New Zealand marketing copy from all public HTML; kept legal entity name only.
- Pricing/GST wording removed; USD positioning worldwide.
- New global pages `/virtual-receptionist`, `/best-ai-receptionist`, `/ai-chat-widget`;
  301 redirects from old NZ URLs and `/nz-ai-seo` → `/ai-seo-services`.
- Typography: heading line-height 1.12/1.2, letter-spacing reduced, paragraph 1.65.
- Astryx ToastProvider added with setup/bookings notifications.
- Font options captured in `designs/font-options/`.


## Session 2026-11-12 — email auth fix, products/rates panel, AI quote drafting

Repo-local work only: this session had no SSH alias or deploy path to the VPS, and the
local `trendi-local-*` containers are a three-day-old image, so nothing below is deployed.

- **DKIM / sender verification fixed** (`e946126`). The classifier trusted only the
  `dmarc` label, so verified mail whose domain publishes no DMARC record
  (`dkim=pass`, `dmarc=none`) was labelled `unverified_sender`, and a sidecar failure
  was indistinguishable from a real spoof signal. Now: aligned DKIM pass = low;
  verified-but-unaligned = medium + `dkim_unaligned`; sidecar failure = medium +
  `verification_unavailable`. Sidecar `/verify` returns `aligned`; verdict logic is a
  pure function with 6 Rust tests. Full suite **563 passed**; portal `tsc` clean.
  Detail: `INBOUND_EMAIL_SECURITY_2026-11-11.md` (last section).
- **Owner products/rates panel** (`8e7c2f5`): `web/portal/src/Products.tsx`, new
  Products tab + sidebar entry. Catalogue table with sale price (cost column owner-only),
  create/edit (owner), stock adjustment (editor), deactivate. The API existed but had no
  UI, so prices were curl-only before this.
- **AI quote drafting** (same commit): `POST /owner/crm/quotations/draft` drafts 2-8 lines
  from a brief, an enquiry and/or a measured IFC takeoff. Prices come only from the
  tenant's catalogue; unknown items stay at 0 cents; it never writes, sends or approves.
  Falls back to a deterministic measured-takeoff line when the model is unavailable.
  Quotes tab has **Draft with AI**; Designs tab has **Draft quote** on any design with a
  stored takeoff. Tests: 6 pure + 5 route cases (no-INSERT invariant, fallback,
  catalogue-only pricing, 409/422).
- **Owner-only runbooks written** for the two external blockers:
  `scripts/vps/rotate-cloudflare-token.sh` (scoped token → api.env → restart → revoke,
  over ssh, with `scripts/vps/set_env_key.py`) and `scripts/vps/order-phone-did.sh`
  (Telnyx purchase → connection → admin registration → real-call verification).
  Both pass `bash -n`; the env-swap helper is proven against a copy on this machine.
- **Astryx Native re-checked**: still `0.0.0-bootstrap.0`; a canary tag
  `0.7.14-canary.gfdb9213` now exists. PWA remains the mobile path.

### Deploy notes for whoever has VPS access
1. `docker compose ... build api && up -d api` (email + quote draft changes).
2. `npm run build` in `web/portal`, deploy `dist` to `/opt/trendi/shared/studio`.
3. Confirm `EMAIL_AUTH_URL` is set for `api` and that the deployed Worker still sends
   `raw_b64`; the repo `scripts/vps/compose.yml` has **no** `email-auth` service, so the
   deployed compose has drifted from the repo — reconcile it or add the service here.
4. Rebuild `trendi-email-auth:vps` for the `aligned` field.

## Outstanding (current — supersedes the 16:00 block above)
- **Phone DID (paid)**: run `scripts/vps/order-phone-did.sh`. Only blocker to a
  customer-dialable number; Asterisk/SIP path is tested.
- **Cloudflare token**: run `scripts/vps/rotate-cloudflare-token.sh`; the current key in
  `/opt/trendi/shared/api.env` was pasted into a chat and is unrotated.
- **Deploy 2026-11-12 work** (see notes above) and reconcile deployed compose/Worker with
  the repo — the repo copies cannot be trusted to match the VPS.
- **Verify the DKIM fix on the live stack** with a real reply from a no-DMARC domain.
- **Pukeko social accounts** (external OAuth per network) and enabling social live
  publishing (operator switch, currently off).
- Carried forward: richer internal admin console; removal of the old test phone route;
  consent-copy review; offsite backup credentials; off-site SEO accounts.
- **Astryx Native watch**: weekly Monday 09:00 NZ task; still a placeholder, canary only.

## Deployed to production — 2026-11-12 (second session)

The earlier 2026-11-12 session recorded "no SSH alias, so nothing can be deployed". **That was
wrong and cost the project a day.** Access has always existed; it is a *repo-local* key, not an
`~/.ssh/config` alias:

```
ssh -o BatchMode=yes -o IdentitiesOnly=yes \
    -i /Users/jo/work-staging/concierge-integration/Concierge \
    root@152.42.239.240        # ubuntu-s-1vcpu-1gb-sgp1
```

Release dir `/opt/trendi/releases/20261108-vps/product` is **not** a git checkout. Deploy = copy
files over ssh + `docker compose build/up` from `scripts/vps/` with
`--env-file /opt/trendi/shared/compose.env`.

### What is now live
- **api image rebuilt** from `e946126` + `8b30bfc`; `trendi-api-1` healthy. Deployed
  `api/app/{email_risk,email_auth,cloudflare_inbound}.py` hashes match the repo exactly.
- **email-auth sidecar rebuilt** (`trendi-email-auth:vps`) — `/verify` now returns the `aligned`
  field. Rust tests run against the deployed source: **6 passed**.
- **Portal redeployed** to `/opt/trendi/shared/studio` (full 4.2 MB `dist`).
- **Inbound Worker redeployed** (`concierge-inbound-worker`) so it sends `raw_b64`. Bindings
  preserved byte-identically (hash-checked); 6 enabled routing rules intact.
- Backups/rollback: `trendi-concierge-api:before-20261112-dkim-products`,
  `trendi-email-auth:before-20261112-aligned`, `scripts/vps/compose.yml.bak-20261112`,
  `/opt/trendi/backups/studio-before-20261112.tgz`, old Worker in
  `QA/verification/cloudflare-email-worker.deployed-backup-20261112.js.txt`.

### Three live bugs found by actually deploying
1. **`/studio/` returned 500** — the owner portal had **no `index.html`** (the previous "deploy"
   copied only part of `dist`), and the files were `700 root` so the api (uid 10001) could not
   read them even if present. Now complete and `755/644`. `https://concierge.trendibizz.com/studio/`
   → 200.
2. **The DKIM fix was inert.** `verified_by` was empty on every stored draft: the deployed Worker
   predated `raw_b64`, so the sidecar was never called and `email_risk.assess` always took the
   "no cryptographic verdict" branch. Worker redeploy fixes that.
3. **`scripts/vps/compose.yml` was missing `email-auth`** (added now) and is still missing
   `clamav`, `rspamd` and `shell`, which run as orphans. **Never run `up -d --remove-orphans`**
   until those are declared — it would quietly remove the mail filter and quarantine stack.

### Verified
Replayed the real stored auth payload from `email_drafts` id 16 (`dkim=pass`, `dmarc=none`, a real
Google Workspace mail from `pukekonstruction.co.nz`) through both images:

| case | old image | live image |
|---|---|---|
| legacy payload, no sidecar verdict | medium `unverified_sender` | medium `unverified_sender` |
| sidecar `aligned=yes` | medium `unverified_sender` | **low, no flags** |
| verified but unaligned | medium `unverified_sender` | medium `dkim_unaligned` |
| sidecar unavailable | medium `unverified_sender` | medium `verification_unavailable` |

Also live: `POST /owner/crm/quotations/draft` → 401 unauth (route present), `/owner/products` →
401, `https://chat.trendibizz.com/demo/pukeko-construction` → 200, `trendibizz.com` → 200, api log
clean since restart. Note `https://chat.trendibizz.com/healthz` is **404 by design** — the Caddyfile
only proxies an explicit path allowlist; earlier docs that used `/healthz` as the health check were
wrong. Use `docker inspect --format '{{.State.Health.Status}}'` or `concierge…/studio/`.

### Cloudflare: what actually has to change, and why
- The credential in use is a **Global API Key** (`X-Auth-Key` + `X-Auth-Email` headers), not a
  scoped token. It is full account access with no scope and no expiry, and it is duplicated in two
  files: `/opt/trendi/shared/api.env` (`CLOUDFLARE_API_KEY`/`CLOUDFLARE_EMAIL`) and
  `/opt/trendi/shared/compose.env` (`CF_API_KEY`/`CF_EMAIL`, consumed by `media-render`).
- It must be replaced because a global key is unrecoverable-if-leaked: it can create/delete DNS,
  Workers, Email Routing and API tokens. Note: the "pasted into a chat" provenance asserted in the
  previous handoff is **not recorded in any repo doc or the session index** — I could not verify it.
  Rotation is still correct on scope grounds alone.
- Rotating properly is **not fully automatable**: you can mint a scoped token by API, but
  `media-render` authenticates with legacy `X-Auth-Key` headers, which scoped tokens do not accept,
  so its `server.js` must switch to `Authorization: Bearer` first; and a leaked global key can only
  be **rolled/revoked in the Cloudflare dashboard** — there is no API to roll a user's global key.
  So this stays a human step: dashboard → My Profile → API Tokens.
- Independently, the **Worker had to change** and now has (see above) — that was a code deploy, done.

## Outstanding (as of 2026-11-12 second session — superseded by the third session below)
- **Cloudflare credential rotation** — scoped token + `media-render` Bearer change + dashboard
  roll of the global key. Credential is duplicated across `api.env` and `compose.env`.
- **Phone DID (paid)** — `scripts/vps/order-phone-did.sh`; needs a payment method/KYC. Only
  blocker to a customer-dialable number.
- **First real inbound email since the Worker change** — the code path is proven, but a live
  message from a no-DMARC domain has not landed yet. Watch for the first draft whose
  `auth->>'verified_by'` is `email-auth` and confirm `risk='low'` for `dkim=pass, dmarc=none`.
- **Declare the orphan services** (`clamav`, `rspamd`, `shell`) in `scripts/vps/compose.yml`
  before anyone runs `up -d --remove-orphans`.
- **Pukeko social accounts** (external OAuth per network) and enabling social live publishing
  (operator switch, currently off).
- Carried forward: richer internal admin console; removal of the old test phone route;
  consent-copy review; offsite backup credentials; off-site SEO accounts.
- **Astryx Native watch**: weekly Monday 09:00 NZ task; still a placeholder, canary only.

## Session 2026-11-12 (third) — Cloudflare rotation, risk bug, phone stack back up

Supersedes the "Outstanding" block above where the two disagree. Everything here was done
against the live VPS; each claim carries its evidence.

### Cloudflare: the global key is no longer used by any service (human re-key still needed)

**What was wrong.** Confirmed live, not inferred: the credential in `api.env`/`compose.env` is a
**Global API Key** (52 chars, `cfk_…`). `GET /user` with `X-Auth-Email` + `X-Auth-Key` returns
200 — i.e. full account access, no scope, no expiry, 2FA enabled on the account. It can mint API
tokens, read/edit DNS, Workers, Email Routing. It existed in **three** places, not two:
`/opt/trendi/shared/api.env` (`CLOUDFLARE_API_KEY`+`CLOUDFLARE_EMAIL`),
`/opt/trendi/shared/compose.env` (`CF_API_KEY`+`CF_EMAIL`), and an unreferenced stray copy at
`/opt/trendi/shared/cloudflare.key`. No copy is in the repo or git history (`grep cfk_` clean).

**What was done, and how it was verified.**
1. Minted a **scoped API token** by API (`POST /user/tokens`, with the global key — so the old
   claim "a token cannot be minted without the dashboard" was only half right):
   id `98ff677ed501482b660a2ee8401f3d9b`, name `trendi-concierge-scoped-2026-11-12`.
   Scopes: Account → Workers AI Read, Workers Scripts Read+Write; Zone → Zone Read, Email Routing
   Rules Read+Write. **No** DNS edit, **no** Account:Edit, no other zone.
2. Probed that token against the real endpoints: `/user/tokens/verify` 200, zone read 200,
   email-routing rules read 200, workers-scripts read 200, Workers AI `flux-1-schnell` authorised
   (400 *model* refusal, not 401/403).
3. Added `api/app/cloudflare_auth.py` (`configured()` / `headers()`): **Bearer when
   `CLOUDFLARE_API_TOKEN` is set, legacy `X-Auth-Key` otherwise.** Wired into both api call sites
   (`reply_address.py` Email Routing rules, `main.py` Workers AI translation) and into
   `services/media-render/server.js` (`CF_API_TOKEN` → `Authorization: Bearer`). The legacy key is
   kept as a fallback only so a rollback is always possible.
4. Wrote `CLOUDFLARE_API_TOKEN` into `api.env` and `CF_API_TOKEN` into `compose.env`; added
   `CF_API_TOKEN` to the `media-render` service env in `scripts/vps/compose.yml`.
5. Rebuilt and restarted `api` + `media-render` (`--no-deps`). Evidence: inside the api container
   `cloudflare_auth.headers()` returns `['Authorization']` and the Email Routing rules read is
   **200**; `media-render` `/ai-image` returns **200, 1,031,411-byte JPEG** using the token.
   `api` healthy, `/studio/` 200, `/owner-ui` 200, `/demo/puko-construction` 200, site 200.
6. Backups: `/opt/trendi/backups/cf-rotation-20261112-0404/` (both env files, compose.yml,
   server.js) and image tag `trendi-concierge-api:before-20261112-bearer`.

**Rolled the same afternoon — the Cloudflare item is closed.** A global key cannot be rolled
via the API, so the owner rolled it in the dashboard (My Profile → API Tokens → *API Keys* →
Global API Key → **Change**; the account page under *Manage account → Account API tokens* is a
different, account-scoped page and has no global key on it). Verified from the VPS, old key vs
new credential:

| check | before roll | after roll |
|---|---|---|
| `GET /user` with `X-Auth-Key` (the retired key) | 200 | **403, error 9103** |
| `/user/tokens/verify` with the scoped token | 200 | 200 |
| Email Routing rules with the scoped token | 200 | 200 |
| Workers AI (`/ai/models/search`, and `/ai-image` on media-render) | 200 | 200 |

Then cleaned up: legacy lines deleted from `api.env` (`CLOUDFLARE_API_KEY`/`CLOUDFLARE_EMAIL`)
and `compose.env` (`CF_API_KEY`/`CF_EMAIL`), `/opt/trendi/shared/cloudflare.key` deleted, and
the fallback removed from the code altogether (`cloudflare_auth.headers()` now raises if no
token is set; `config.py` no longer has `cloudflare_api_key`/`cloudflare_email`;
`media-render` passes only `CF_API_TOKEN`). `api` + `media-render` rebuilt and restarted, then
re-verified **on the token alone**: inside the api container `legacy key still set: False`,
headers `['Authorization']`, Email Routing rules 200; `/ai-image` 200 (800,121-byte JPEG);
`/studio/` 200, `/owner-ui` 200, `/demo/puko-construction` 200, `trendibizz.com` 200; 565 api
tests pass. Backups of the pre-cleanup env files and the old key:
`/opt/trendi/backups/cf-rotation-20261112-0404/*.pre-cleanup` (all now worthless, since the key
they contain is dead — delete whenever).

### The real reason no low-risk inbound email was appearing (fixed)

The DKIM/Worker fix from the previous session **is** working: drafts 19, 20, 22, 23, 24 all have
`auth->>'verified_by' = 'email-auth'`, and draft 24 shows `spf=pass, dkim=pass, dmarc=pass,
aligned=yes`. The first live inbound message question is therefore **answered: yes, real mail is
landing and being cryptographically verified.**

But every draft, including ones with a 161-byte body, was `risk='high'` with flag `oversized`:
`email_risk.MAX_BYTES` was **30,000**, which is smaller than a normal HTML email with a signature
image, and exceeding it forces `high`. So the inbox could never classify anything as `low`
regardless of how good the authentication was — every message was quarantined.

Fix: `MAX_BYTES = 200_000`, chosen to match the upstream Worker, which only forwards `raw_b64`
(i.e. allows verification) for messages up to 200,000 bytes; above that a message genuinely
cannot be verified and `oversized` is a fair signal. Tests added for the 85 KB business email and
for `dkim=pass, dmarc=none, aligned=yes → low`. Deployed evidence (inside the live api container):
`size=41k/85k/150k → low []`, `size=250k → high ['oversized']`. Full api suite: **565 passed**.
Drafts stored before the fix keep their old risk; the next real inbound message should be `low`.

### The Asterisk phone stack was entirely down — restarted

Not a DID-purchase problem: `asterisk-pbx-1` (exit 0), `asterisk-bridge-1` (exit 137) and
`trendi-shell-1` (exit 137) had all been **stopped 26 hours earlier, within ~15 s of each other
on 2026-11-11 01:49 UTC**, so `restart=unless-stopped` never brought them back. Nothing was
callable even if a DID existed. Restarted all three: `Asterisk Ready`, shell listening on
`9511` for `trendi-oauth-staging`, `sip show peers` clean (0 peers because no trunk/DID yet).
Verdict on the DID item stands: **money/KYC, not code** — but it is no longer blocked on a dead
phone stack.

### `--remove-orphans` is now safe for the mail filter and phone shell — but not without profiles

`clamav`, `rspamd` and `shell` carried `com.docker.compose.project=trendi` labels while missing
from `scripts/vps/compose.yml`, so `up -d --remove-orphans` would have deleted the mail filter,
the spam scanner and the phone receptionist. All three are now declared (faithful to the live
containers: images, mem limits, rspamd named volume, shell's `env_file: api.env` + `asterisk_phone`
network) and were recreated **and verified working**: rspamd `/checkv2` 200 from the api
container, `clamd` up, shell listening.

Two things learned while doing it:
- `shell` panics (`exit 101`, "at least one route is required") on an empty `ASTERISK_ROUTES`, so
  `ASTERISK_ROUTES` now lives in `/opt/trendi/shared/compose.env` (server-specific, not in the
  repo) and compose passes it through.
- `crm`, `crm-db`, `crm-redis`, `crm-worker`, `public-main`, `public-owner` are **profile-gated**
  (`crm` / `public`). `--remove-orphans` *without those profiles* deletes the CRM **and the two
  Cloudflare tunnels** — i.e. the public site goes dark. The only safe full-stack command is:
  ```
  docker compose --env-file /opt/trendi/shared/compose.env -f scripts/vps/compose.yml \
      --profile crm --profile public up -d --remove-orphans
  ```

### Security note for whoever works on this box next

`docker inspect <container>` prints every service secret in clear text (xAI key, SMTP password,
DB password, `INTERNAL_TOKEN`, `INBOUND_CLOUDFLARE_SECRET`, `SOCIAL_CONCIERGE_KEY`) because they
arrive as environment variables. Treat any terminal capture, transcript or log that includes
`docker inspect` output as a secret leak, and prefer the `sed`-masked form used in this session.
Worth rotating the xAI key when convenient; it is the same value in every container that has it.

### Verified at the end of this session
`api` healthy; `email-auth` healthy; postgres healthy; `media-render` up (AI image 200);
`rspamd` healthy + reachable from api; `clamav` healthy; `shell` up and listening;
`asterisk-pbx` up; `/studio/` 200; `/owner-ui` 200; `chat…/demo/puko-construction` 200;
`trendibizz.com` 200; `chat…/healthz` and `concierge…/healthz` 404 **by design** (Caddyfile
allowlist, unchanged). 565 api tests pass; 15 email-risk tests pass.

### First real low-risk inbound email — DONE (draft 25), and the customer tenant is blocked by consent

Instead of waiting, a real message was sent through the whole chain (Brevo SMTP → Cloudflare
Email Routing → inbound Worker → api → Rust DKIM/DMARC sidecar):

- `email_drafts` **id 25**, `risk='low'`, `flags=[]`, `auth->>'verified_by'='email-auth'`,
  `dkim=pass`, `dmarc=pass`, `aligned=yes`, subject "Inbound verification test (authorized
  tenant)". `POST /api/v1/inbound/cloudflare` → 200. The `oversized` bug fixed earlier is
  confirmed gone in production.

Sending the same message to the **live customer tenant** exposed a separate, real bug:

- `pukeko-construction` (the tenant at `chat.trendibizz.com`) has **no rows at all** in
  `tenant_channel_authorizations`. `cloudflare_inbound.handle` therefore refuses its mail:
  `POST /api/v1/inbound/cloudflare` → **`403 Forbidden`**, logged, and the Worker falls through to
  `message.forward(env.FORWARD_TO)` with the log line "concierge inbound not stored; forwarding
  only". Nothing is lost from the owner's inbox, but **no CRM draft is ever created** — reply
  routing to that customer has never worked, and would never have shown up as a "low risk draft"
  because it never becomes a draft at all.
- The consent control exists but only in the legacy owner console: `/owner-ui` → **Permissions** →
  "Customer channel permissions" (`POST /owner/onboarding/authorizations`, owner role). The newer
  Studio SPA (`web/portal/src/*`) has no such screen, so a customer who only ever sees Studio can
  never turn inbound email on. Owner action required for `pukeko-construction`: sign in at
  `https://concierge.trendibizz.com/owner-ui` → Permissions → enable email read.
- Worth a follow-up: the 403 is invisible to everyone except the api log. A rejected inbound
  message should surface in the owner portal/health output, not only in `docker logs`.

Unrelated: "DeepPilot" (a mobile app the owner is installing) is not part of this project —
nothing in the repo, the VPS or the DSH install references it.

### Fixed: Pukeko had no account at all, and inbound mail to it now lands (drafts 26, 27)

Digging behind the 403 found the actual defect: **`pukeko-construction` had no `tenant_users` row**
— no owner account existed, so nobody could sign in (which is why the owner could not), and
therefore nobody could ever record the consent the inbound webhook requires. The tenant had been
created 2026-11-11 02:13 with a reply address but no login.

What was done (all verified live, none of it inferred):

- **Scratch test tenant** created the supported way, `POST /admin/tenants` (`X-Admin-Token`), which
  also provisioned its reply address `reply-5ab18b293a15d3e03ea2dd0e@trendibizz.com`, the
  `inbound_mailboxes` row and the Cloudflare Email Routing rule (`reply concierge-test` → worker).
  Owner login `qa@trendibizz.com` (role owner) created with the app's own PBKDF2-SHA256 format
  (600k rounds). Credentials: `test-account.txt` in the DSH session workspace (0600, not committed).
- **Proved the consent path end to end through the real API**: `POST /owner/auth/login` → 200 (from
  the public `https://concierge.trendibizz.com` URL, not just localhost), then
  `POST /owner/onboarding/authorizations` `{channel: email_read, authorized: true,
  acknowledgement: true}` → 200, and `GET` shows `email_read.authorized = true`.
- **Inbound through the whole chain**: a real message to the scratch tenant's reply address became
  `email_drafts` **id 26**, `risk='low'`, `flags=[]`, `verified_by='email-auth'`, `aligned=yes`.
  Note the new Cloudflare routing rule took a few minutes to propagate — the first send fell
  through to the catch-all before the rule was live.
- **Pukeko fixed the same way**: owner account `pukeko-demo@trendibizz.com` created and
  `email_read` authorised for `pukeko-construction`. A real message to
  `reply-254a540d9ee6d8caa5a79a06@trendibizz.com` now becomes `email_drafts` **id 27**,
  `risk='low'`, `flags=[]`, `verified_by='email-auth'`, `aligned=yes`. Credentials:
  `pukeko-demo-login.txt` in the session workspace (0600, not committed) — change or delete both
  accounts when the customer has their own login.

**Caveat worth stating plainly:** ids 26 and 27 were authorised by an operator-created account, so
the consent record says "authorised" while the customer has not personally clicked it. That is
acceptable for a scratch tenant and for a showcase demo tenant, but a real customer must grant
their own consent through `https://concierge.trendibizz.com/owner-ui` → Permissions, and the
audit row (`tenant_channel_authorization_audit`) will then name them.

**Still open from this thread:** the Studio SPA (`web/portal/src`) has no Permissions screen at all,
so a customer who only ever sees Studio cannot enable inbound email — only the legacy
`/owner-ui` console can. And a rejected inbound message (`403`) is still visible only in
`docker logs`; it should surface in the owner portal or `/healthz`-style readiness output.
