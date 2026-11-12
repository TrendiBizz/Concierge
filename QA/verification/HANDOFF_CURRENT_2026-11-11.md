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

### Whole inbound chain re-checked, and it can no longer fail silently

**Was it "something changed"? No — the state changed, and nothing guarded it.** Evidence:

- The consent gate has been in the code since `3807085` (2026-11-08) and *every* api image on the
  box since 2026-11-09 contains it (checked by running `inspect.getsource` inside the old tagged
  images; the pre-incident image `before-20261112-dkim-products` built 2026-11-11 10:34 has it too).
  So no deploy yesterday removed a check.
- `email_drafts` id 16 (`2026-11-11 02:40 UTC`, sender `conrad@pukekoconstruction.co.nz`,
  `source_id cloudflare:…`, real `authentication_results`) proves the chain *did* deliver for
  Pukeko. It could only pass the gate if a consent row existed at that moment.
- But `tenant_channel_authorization_audit` has **no** Pukeko row before today. Every grant made
  through the product writes an audit row, so that earlier consent was inserted **out of band**
  (direct SQL) — and it is gone. Direct inserts are invisible to the audit trail, which is why it
  could vanish without anyone noticing.
- Verdict: not a code regression. A required precondition was set up manually, rotted, and nothing
  in the system re-checked or reported it. The bug was the absence of a guard.

**Now there is a guard. Seven links are checked for every tenant** (`api/app/inbound_readiness.py`,
pure `evaluate()` + live `check()`): api enabled · owner account exists · `email_read` consented ·
reply address set · mailbox enabled · Cloudflare rule present/enabled → Worker · email-auth sidecar
reachable. Each failure returns the exact fix. Missing Cloudflare access reports `unknown` (warning,
not a failure) so a missing token cannot cry wolf.

Live evidence:
- `GET /owner/onboarding/inbound-readiness` (owner) and `GET /admin/inbound-readiness` (operator).
  For the test account: **all seven green, `ok: true`**; `GET /owner/onboarding` now carries an
  `inbound_email` block, so onboarding cannot claim email is ready while mail is refused.
- **Rejections are recorded**: `cloudflare_inbound` now writes `inbound_audit(action=
  'inbound_rejected', detail={reason, sender, recipient, message_id})` before returning 403, and
  readiness reports "N message(s) refused in the last 24h" as a warning. The refusal is no longer
  visible only in the access log.
- **Ops check**: `scripts/vps/check-inbound-chain.sh` (+ `.py`) — exit 1 if any tenant's chain is
  broken, safe to cron. First run found **two more chains that were silently broken and unknown**:
  `concierge` (no owner account → 403) and `trendi-meta-review` (`email_read` never consented →
  403). Both are internal tenants, listed as outstanding below.
- **Studio now has the screen**: new `web/portal/src/Permissions.tsx` — per-channel
  Authorise/Withdraw with the explicit acknowledgement checkbox, plus a live seven-point chain
  display with fix text, last-stored timestamp and rejection count. Tab **Permissions**, built and
  deployed to `/opt/trendi/shared/studio` (`Permissions-BG_AQltX.js` served by `index-*.js`;
  `/studio/` 200). The legacy `/owner-ui` console is no longer the only way in.
- 573 api tests pass, including 8 new readiness tests (missing consent, missing owner, missing rule,
  unknown-Cloudflare-is-not-failure, sidecar down, rejections as warnings, garbage input).

Still to do: schedule `check-inbound-chain.sh` as a cron/health job so a broken chain is caught
without someone running it, and create the missing owner account for the `concierge` tenant /
grant consent for `trendi-meta-review`.

### Closed the two broken chains, croned the guard, and found the missing monitoring

- **`concierge` tenant**: had no owner account at all → created `concierge-owner@trendibizz.com`
  (role owner, app's PBKDF2 format; credentials in `concierge-owner-login.txt`, 0600, session
  workspace) and granted `email_read`.
- **`trendi-meta-review`**: owner account existed but `email_read` had never been authorised →
  granted, attributed to that tenant's own owner user.
- Both grants write `tenant_channel_authorization_audit` rows. Same caveat as Pukeko: these were
  recorded by the operator using the tenant's owner account, not by the customer clicking.
- **Guard is now scheduled**: root crontab, hourly at :07 —
  `/opt/trendi/releases/20261108-vps/product/scripts/vps/check-inbound-chain.sh`, output appended
  to `/opt/trendi/backups/inbound-chain.log` with a timestamp and the exit code.
- **Proved the guard catches the real failure**, end to end, on the scratch tenant: revoked
  `email_read` → sent a real message → api returned 403 **and wrote
  `inbound_audit(action='inbound_rejected', reason='email_read_not_authorized', recipient=…)`**
  → `check-inbound-chain.sh` reported `FAIL concierge-test blocked=consent warnings=rejections`
  and exited 1. Consent restored; all five tenants are green (the scratch tenant keeps the
  "refused in the last 24h" warning for a day, which is correct).

**The reason nobody noticed the outage for a day: there was no monitoring.** Uptime Kuma and n8n
(the `trendi-auxiliary` compose project) were both stopped on **2026-11-09 02:43 UTC** with a
graceful SIGTERM, and their containers had `restart: no`, so they never came back — three days
without uptime checks. Kuma is running again (`127.0.0.1:3001`, healthy, data in
`/opt/trendi/auxiliary/kuma`) and its restart policy is now `unless-stopped` so a host reboot
brings it back. **n8n and its database remain stopped on purpose** — automation can send mail and
publish social posts, so starting it is an operator decision, not a fix. There is also no compose
file for the auxiliary stack any more, so it can only be started with `docker start`.

Health sweep at the end: no api 5xx in 6 hours, zero container restarts, backups ran
(2026-11-11 14:30, 59 MB; daily 14:30 UTC cron) — but they are **local-only**, still no offsite
copy. Portal lint is pre-existing noisy: 24 warnings + 3 errors already on `main`, and the new
`Permissions.tsx` adds 0 errors and 1 warning of the same class the other panels have.

## Session 2026-11-12 (fourth) — monitoring landed, email assessed end to end

Supersedes the "still open" notes above on monitoring and on the Permissions screen.

- **The monitoring the operator asked for exists now.** `scripts/vps/healthcheck.py` + `.sh` run
  every 5 minutes from cron and write `/opt/trendi/monitoring/{health.log,status.json,state.json}`;
  ~40 checks over containers, six public URLs, api, Postgres, disk/mem, TLS expiry, Cloudflare
  token/routing/worker, the inbound chain + refusals, email-auth, Hermes and Kuma. Alerts go by
  Brevo mail with de-dup; **delivery is proven in production** — the `[Concierge FAIL]` mail at
  18:26 NZ was this system, triggered by the deliberate consent-revocation guard test.
- **Outside-in probe was dead in the repo and is now live** (commit `0286e34`):
  `.github/workflows/uptime.yml` probes six public URLs from GitHub Actions every 20 min and opens
  a labelled issue on failure. It had been written by a session that was killed mid-compaction and
  was never committed — the checkpoint script refuses untracked paths outside its allowlist.
  `.github/` added to `UNTRACKED_ALLOWED_PREFIXES`; committed and pushed.
- **Bounces no longer page.** `inbound:rejections` now ignores `bounces-*`, `mailer-daemon@` and
  `postmaster@` senders; the refusal still lands in `inbound_audit`. Health is 42 ok / 0 warn / 0
  fail as of 19:03 NZ.
- **n8n is gone** — containers and image removed on the operator's instruction; the `recovery`
  profile in `/opt/trendi/auxiliary/compose.json` can still recreate it, and `./n8n-db` data is
  untouched.
- **Full assessment: `EMAIL_ASSESSMENT_2026-11-12.md`** (same directory). Headline findings:
  no bounce handling or suppression list at all (blocker); unaligned DKIM pass is misreported as
  `dmarc=fail` and forced to `high`, so forwarded/list mail is quarantined and the
  `dkim_unaligned → medium` branch is unreachable; customer-facing `email_secretary_reply` carries
  no `Reply-To`, so replies leave the `reply-<token>` loop; blocked senders are dropped without an
  audit row; `inbound_audit` has no read endpoint.
- **Doc corrections:** the Studio SPA *does* have a Permissions screen (`App.tsx:130`, deployed
  chunk 200) — the earlier "no Permissions screen" note is stale. `INBOUND_EMAIL_SECURITY` still
  says the cap is 30 KB; it is 200,000.
- **Audit gap proved:** `tenant_channel_authorization_audit` contains **13 grant rows and zero
  revocation rows**, and the restore of `concierge-test` at 18:12:42 NZ has no audit row — the
  guard test's revoke/restore were direct DB writes. Consent changes must go through the API or be
  captured by a trigger.

## Session 2026-11-12 (fifth) — every email issue fixed, n8n fully removed

Supersedes the email queue and n8n notes above. Full detail + evidence:
`EMAIL_ASSESSMENT_2026-11-12.md` §7. Deployed 2026-11-12 19:24 NZ (06:24 UTC), health check
**44 ok / 0 warn / 0 fail**.

- **Bounces + suppression (the blocker) are real now.** Pure DSN parser (`api/app/bounces.py`),
  suppression list + Brevo webhook + DSN ingress + outbox gating (`api/app/suppressions.py`,
  `cloudflare_inbound.py`, `outbox.py`), `Message-ID` persisted per outbox row. Live-proved with a
  synthetic hard bounce through the public webhook: 401 on a bad token, suppression + outbox
  `failed` + audit row on the good one, idempotent on replay (test rows removed afterwards).
  The operator subscribed it in Brevo on 2026-11-12 19:45 NZ and it was proved end to end at
  06:46 UTC: real mail to `no-such-mailbox-9f3a2@gmail.com`, Gmail 550-5.1.1, Brevo webhook in
  5 s, Message-ID match, suppression + outbox `failed` + audit row; test rows removed.
- **Unaligned DKIM is no longer "dmarc=fail".** Sidecar emits `unaligned`; API maps it to
  `dkim_unaligned` → medium. Rust 6/6, deployed and verified on loopback.
- **Reply-To on every customer-visible email** (not just owner alerts). Test: all kinds.
- **Blocked senders are audited; refusals are listable.** `GET /owner/inbound-audit`,
  `/admin/tenants/{slug}/inbound-audit`, and the Studio Permissions screen shows sender/subject/
  reason plus the suppression list with "Allow again".
- **Consent is attributable and the audit is authoritative.** New columns + a DB trigger (writes
  owner/operator/direct), operator grant endpoint with reason + `X-Operator`, read endpoints.
  Live-proved: operator grant recorded as `operator`, a direct SQL update recorded as `direct`.
- **Rate limits moved before DKIM/Rspamd/ClamAV**, counted per recipient mailbox; the allow-list
  high→medium downgrade is gone.
- **Low items:** `reply_address` collision handling, Worker hint parsing restricted to the
  Authentication-Results header (**worker not redeployed** — operator step), payload-cap doc fixed.
- **Caddy allowlist** gained `/webhooks/brevo`; gateway restarted; Studio bundle rebuilt and
  readable (`/opt/trendi/shared/studio` needed `chmod -R a+rX`).
- **Health check gained two checks** (`email:bounce-webhook`, `email:suppressions`): 42 → 44 ok.
- **n8n is now completely gone.** Repo: compose service/volume/profile, `postgres/init.sh`,
  `scripts/backup.sh`, `gen-env.sh`, `.env.example`, `Caddyfile` block, `events.py` docstring.
  VPS: `n8n`/`n8n-db` services removed from `/opt/trendi/auxiliary/compose.json`, both data
  directories deleted after an 8.5 MB tarball backup in
  `/opt/trendi/backups/n8n-removed-20261112-1930/` (compose.json.before included), and the legacy
  dump copy removed from the auxiliary backup script. Kuma unaffected (302, healthy).
- **DNS correction:** DKIM **is** published — `brevo1._domainkey.trendibizz.com` (Brevo's
  selector); the earlier "no DKIM" claim missed it. DMARC stays `p=none`, SPF stays `~all`:
  enforcement is a deliverability decision, not a code fix.
- Tests: API **600 passed** (was 573), Rust 6/6, `cargo test --offline` green.

- **Go-live hardening checklist created:** `QA/verification/GO_LIVE_HARDENING.md`. These are
  deliberately deferred until the switch to real customers, and every one must be closed then:
  move the Worker's `CONCIERGE_INBOUND_SECRET` from a plain-text binding to a Cloudflare
  **secret binding**; rotate the secrets handled in chat during setup (`BREVO_WEBHOOK_SECRET`,
  `INBOUND_CLOUDFLARE_SECRET`, `ADMIN_TOKEN`); DMARC `p=quarantine` → `p=reject` and SPF `~all` →
  `-all` after clean reports; Brevo plan/dedicated IP + SMTP-key rotation + authorized-IP lockdown;
  delete the scratch tenants (`concierge-test`, staging fixtures) and decide who owns
  `admin@trendibizz.com`; split the Cloudflare token (read-only for health, narrow write for
  deploys).

### Still outstanding (carried, not closed)
- Brevo webhook subscription (operator, dashboard) and Cloudflare Worker redeploy for the hint fix.
- Phone DID (payment/KYC), Pukeko social OAuth, offsite backup credentials, SEO accounts, Astryx.
- Rotate the xAI key; consent-copy review; old test phone route; richer admin console.
- Tenant reply addresses still rely on the Cloudflare rule check; DMARC enforcement after reports.

## Session 2026-11-12 (sixth) — full systems check

Operator asked for a whole-system check for anything outstanding beyond the go-live checklist.
Full report: `SYSTEM_CHECK_2026-11-12.md`. Headline: the stack is green where prior sessions said
(44/44 health, 604 API tests, Rust 6/6 + 6/6, no 5xx, no restart loops, TLS/DNS/git clean), but
four things are not:

1. **P1 Worker secret**: `CONCIERGE_INBOUND_SECRET` is still `plain_text` (confirmed via the
   Workers settings API) and its value was printed during this check — rotate it now and set the
   binding to Secret. `FORWARD_TO` is also plain text (`kiwi18@gmail.com`).
2. **P1 Kuma has zero monitors** (`select count(*) from monitor` = 0); the healthcheck's
   `aux:kuma` 302 check can't see that. Monitoring is really healthcheck.py + GitHub uptime.
3. **P1 device-SMS receipts are lost on every deploy**: 42/42 `/api/v1/device-sms/receipt` calls
   in 24 h returned 502 (Caddy DNS `lookup api ... server misbehaving` during api restarts). The
   phone retries ~5×/13 s then gives up; 10 `outbox` rows have sat in `awaiting_receipt`
   (owner_alert, tenant `trendi-oauth-staging`) since 2026-11-11 02:40 with nothing reconciling
   them. Needs a stable upstream/sweeper and a deliberate clear.
4. **P2 host hardening**: ufw and fail2ban inactive, `PermitRootLogin yes`, ambiguous
   `PasswordAuthentication` drop-ins, 12 packages upgradable.

Still outstanding and unchanged: the whole `GO_LIVE_HARDENING.md` list (§2 secret rotation, §3
DMARC reject, §4 Brevo plan/IP/key, §5 scratch tenants + `admin@trendibizz.com`, §6 token split),
plus the carried items (phone DID, social OAuth, offsite backups, SEO accounts, Astryx, xAI key,
consent-copy review, old test phone route, richer admin console).

### Session 2026-11-12 (sixth, continued) — changes applied, commit `12e5593`

Operator asked for all tests plus all needed changes. Done and live-verified:

- **Worker secret** is a Cloudflare Secret and was rotated on both sides. Old value → 401,
  new value → 400 (signature accepted). `api.env` backup beside it (`api.env.bak-*`).
- **SMS no longer sticks in `awaiting_receipt`**: `outbox.reconcile_stale_device_sms` (15 min,
  every 5 min) failed the 10 stuck owner-alert rows on its first live run; device jobs went
  `uncertain`. Caddy retries the api upstream for 10 s during a deploy instead of 502'ing.
  New `api/tests/test_outbox_reconcile.py`. Live bug found and fixed: asyncpg needs a
  `timedelta`, not a string, for the interval parameter.
- **Host hardened**: sshd key-only (`passwordauthentication no`, `permitrootlogin
  without-password`) — note sshd honours the FIRST value, so `50-cloud-init.conf` had to be
  edited, not just a 99- drop-in; `ufw` active (deny inbound, :22, `DEFAULT_FORWARD_POLICY=ACCEPT`
  to keep Docker networking); `fail2ban` active with the `sshd` jail.
- **Three stale tests fixed** (red on `main` because CI only runs on `pull_request`):
  `customer_authorization_test.py`, `customer_onboarding_integration.py` (`/studio` invite),
  `owner_customer_journey_test.cjs` (`document.addEventListener`).
- **Final evidence**: API 606 passed; isolated battery **17/17** (fresh Postgres per suite);
  node widget 9/9; Rust social all pass; email-auth 6/6; live healthcheck 44/44.

Still open: Kuma decision (0 monitors), `BREVO_WEBHOOK_SECRET` + `ADMIN_TOKEN` rotation, DMARC
`p=reject`, Brevo plan/IP/key, scratch tenants + `admin@trendibizz.com`, Cloudflare token split,
phone DID, social OAuth, offsite backups, xAI key, consent-copy review.

### Session 2026-11-12 (sixth, second pass) — "finish what you can"

- CI now runs on **push to main** too (it was pull_request-only, which hid the stale tests).
- **Uptime Kuma removed** (0 monitors): stopped, probe dropped from `healthcheck.py` → **43/43**.
- email-auth unused-accumulator warnings removed; rebuilt and redeployed, 6/6.
- 9/12 OS packages upgraded; 3 remain (phased `distro-info` x2, `snapd`).
  **`/var/run/reboot-required` is set — reboot in a quiet window.**
- Stale `/opt/trendi/backups/*.lock` removed; API suite still **606 passed**; public URLs 200.
- Left for the operator (dashboard/payment/decision): `BREVO_WEBHOOK_SECRET`, `ADMIN_TOKEN`,
  DMARC `p=reject`, Brevo plan/IP/SMTP key, scratch tenants + `admin@trendibizz.com`
  (needs Email-Routing-write token), Cloudflare token split (needs token-admin),
  phone DID (payment/KYC), Pukeko social OAuth, offsite backups, xAI key.
- Ambiguous, not changed: "old test phone route" — `/owner/sms-phone/test` is live and covered by
  a passing test; clarify which route the note meant before removing anything.

### Session 2026-11-12 (sixth, third pass) — reboot + scratch cleanup executed

- **Tenant `concierge-test` deleted** (all 45 tenant FKs cascade); pre-delete dump
  `/opt/trendi/backups/pre-scratch-delete-20261112-075303.dump`. Its Cloudflare routing rule
  deleted too. Catch-all and Concierge intake intact. Four tenants remain.
- **Host rebooted** to activate kernel 6.8.0-149; health **43/43**, all public URLs 200,
  CRM 200 after its ~3-minute Twenty boot.
- **Latent bugs exposed by the reboot and fixed**:
  - `asterisk-bridge-1` crash-looped: `PermissionError /srv/app/suppressions.py`. The bind-mounted
    `api/app` was owned 501:staff `-rw-------` (rsync-preserved Mac umask) and the bridge runs as
    uid `app`. `chmod -R a+rX <release>/api/app` + restart. **Deploy rule: always chmod after
    copying api/app.**
  - `trendi-social-1` (`network_mode: service:api`) held a stale netns → recreate with
    `up -d --force-recreate --no-deps social`.
- **Proved not possible with current access**: Cloudflare DNS 403 (DMARC/SPF manual), token
  list 403 (cannot split token), no BREVO_API_KEY (webhook rotation needs the Brevo dashboard).
  The token *does* have Email-Routing write.
- Remaining: all operator dashboard/payment/decision items (§2 Brevo secret + ADMIN_TOKEN,
  §3 DMARC reject, §4 Brevo plan/IP/key, §5 staging tenants + admin@ owner, §6 token split),
  phone DID, social OAuth, offsite backups, xAI key.

## Session 2026-11-12 (seventh) — competitor gap analysis, no code changed

Operator asked what Octovox and GoHighLevel have that is worth adding to Concierge, explicitly
**without bloat**. Deliverable: **`COMPETITOR_GAP_2026-11-12.md`** (ranked, with effort and
acceptance tests) plus raw sourced evidence in **`COMPETITORS_RAW_2026-11-12.md`**. Nothing was
built or deployed this session; this section is a worklist, not a changelog.

**Headline:** Octovox is not an SMB competitor — NZ SIP overlay, channel-only ("we don't sell
direct"), no published pricing, zero independent reviews. Its one good idea is the **Switchboard**
(live human supervision + one-click takeover of AI calls). GoHighLevel is $97/$297/$497 (top tier
now branded "Founder"), but its cost model is the metered wallet ($0.01/workflow execution, AI
agents excluded from the plan) and its loudest complaint is the learning curve. Concierge is
already ahead on the things GHL charges for: human approval before send, consent provenance with an
audit trigger, DMARC/bounce/suppression handling.

**Ranked additions (value ÷ effort), none of which adds a new module family:**
| # | Item | Effort | Builds on |
|---|---|---|---|
| A | **Missed-call text-back** — no-answer/abandoned call → one SMS + lead + timeline event (opt-out, rate-limit, channel auth honoured) | 2–3 d | `phone_sip.py`, `outbox.py`, `sms.py`, `casetimeline.py`, `automation.py` |
| B | **Live call supervision** — Studio panel of in-progress calls with live transcript + "take over, call me" via existing `call_control` | 4–6 d | `phone_sip.serve_call` already writes every transcript turn live via `convo.save_message`; no media server needed |
| C | **One contact timeline screen** in Studio (+ optional per-tenant "suggest only" mode) | 2 d | `casetimeline.timeline()` already merges all channels — backend done |
| D | **After-call intelligence** — summary, outcome label, sentiment → follow-up task / digest | 2–3 d | `llm.py`, `voice_records.py`, `tasks`, `tenants.voice_daily_limit` |
| E | **Stripe Checkout on accepted quotations** (deposits) — hosted only, no invoicing | 3–5 d | `quotations.py`, public `/quote/{token}`, `outbox` |
| F | **Attributed revenue report** — AI-handled enquiries → quotes → accepted → $ value | 2 d | `quotations.py`, `leads`, `sales.py`, `Reports` |

Suggested order **A → C → D → B → E → F** (~2 weeks total). A and C alone close the two gaps an
owner would notice in a trial.

**Explicitly rejected as bloat:** funnels/site builder, courses/memberships/communities, affiliate
and ad managers, SEO/listing resale, marketplace, IVR menu trees, custom objects, drag-drop workflow
palette, live audio listen-in/whisper (needs a media server), white-label agency hierarchy + SaaS
reselling, and **any metering of automation or AI** — the flat all-in price is the differentiator.

**Triggers, not backlog:** A2P 10DLC wizard (first US customer), Microsoft calendar (first Microsoft
shop), snapshot/reseller mode (only if the operator decides to sell through partners).

### Test coverage gap found while auditing (independent of the above)
`HANDOFF.md` still claims Studio has no Permissions screen — it does (`web/portal/src/Permissions.tsx`,
wired in `App.tsx`). Stale doc statement, corrected there. No capability was added this session, so
**the 606 API / Rust / email-auth baselines and 43/43 health are unchanged and were not re-run.**

## Session 2026-11-12 (eighth) — competitor-gap items being shipped, one per commit

Operator instruction: implement items A–F from `COMPETITOR_GAP_2026-11-12.md` in order, test each
thoroughly, wire each into onboarding so the customer always knows what is included, commit, push
and deploy after each, then move to the next. Also: **no Microsoft dependency anywhere** (so
Microsoft calendar is dropped from the trigger list entirely) and only free/GitHub-hosted services.
`GO_LIVE_HARDENING.md` items are unaffected and still open.

Deploy recipe used (unchanged from previous sessions): rsync `api/app` → release dir + rsync
`web/portal/dist` → `/opt/trendi/shared/studio`, `chmod -R a+rX` both, then
`docker compose -f compose.yml --env-file /opt/trendi/shared/compose.env --profile crm --profile public up -d --build --no-deps api`;
schema applies itself on API boot (`db.init` runs the idempotent `schema.sql`).

### A. Missed-call text-back — SHIPPED (`79b3b97`), deployed and live-proved
- **Code:** `api/app/missed_calls.py`. Conservative trigger: the call ended and (the caller never
  had a transcribed turn, or the call was < 20 s, or the provider said no-answer/busy/failed) and
  no appointment was created for that number. Skips: switched off, SMS disabled/unauthorised, no
  caller number, self-call, already booked, a real conversation, or a text already sent to that
  number in the last 24 h.
- **Hooks:** `phone_sip.serve_call` finally block (Grok SIP) and `/api/v1/phone/twilio/ended`, plus
  a 5-minute sweeper (`missed_calls.run_forever`, started with the outbox) so a call whose webhook
  never arrived is still recovered. Recovery never changes the recorded outcome of the call.
- **Data:** `tenants.missed_call_textback` (default **on**), `tenants.missed_call_template`,
  `missed_call_recoveries` (one row per call, partial unique index = one reply per number per day).
  `lead_id`/`outbox_id` link the audit row to what was actually sent.
- **Owner surface:** `GET /owner/missed-calls` (enabled, 30-day count, recent recoveries),
  `PUT /owner/missed-calls/textback`. Studio → Bookings now has a "Missed-call text-back" card with
  the switch, the 30-day count and the last five recoveries.
- **Onboarding/awareness:** `provider_readiness` gained an **`included`** area — the customer-facing
  half of the report ("what we already do for you, and how to turn it off"). A test now asserts every
  shipped capability is advertised there, so this cannot silently rot. `included` grows with B–F.
- **Tests:** 20 new (`api/tests/test_missed_calls.py`) covering every rule, the message template,
  the queue+audit write, the sweep query and the tenant/call split; the readiness suite gained the
  "every shipped capability is advertised" assertion. **API 628 passed.** Mutation check: disabling
  the `already_booked` rule reddened 2 tests, then restored.
- **Live proof** (`scripts/vps/prove_missed_calls.py`, run inside `trendi-api-1` on the real DB):
  schema applied (`missed_call_textback`, `missed_call_template`, `missed_call_recoveries`), a
  synthetic call produced audit row `{'status': 'skipped', 'reason': 'sms_disabled'}` and the
  fixtures were removed (0 left). Healthcheck after deploy: **0 fail, 0 warn**.
- **Honest finding:** `pukeko-construction` has `sms_enabled = false`, so A is inert for the live
  tenant until that business enables SMS — A cannot text without the SMS channel the product already
  gates. This is why the `included` step says "for every business with SMS enabled".

### Next
C (one contact timeline screen) — the backend `casetimeline.timeline()` already merges channels, so
this is a Studio view plus the readiness/onboarding entry; then D, B, E, F.

### C. One timeline per customer — SHIPPED (`6439c27`), deployed and live-proved
- **Code:** `casetimeline.contact_label()` + `casetimeline.summarise()` (pure: name → phone →
  email → case key; per-channel counts). The channel merge itself already existed.
- **Owner API:** `GET /owner/contacts` (search, channels, event count, last contact, assistant
  state), `GET /owner/contacts/{case_key}/timeline` (events + enquiries + appointments + takeover
  state), `PUT /owner/contacts/{case_key}/takeover` (a reason is required to pause; same store as
  the enquiry-level takeover, so the two screens cannot disagree).
- **Studio:** new **Contacts** tab and sidebar item — one row per person, drill-down timeline,
  take-over/resume with the reason recorded.
- **Onboarding:** `included` gains "One timeline per customer", so the customer sees it exists.
- **Tests:** 8 new (`api/tests/test_contact_timeline.py`). Tenant-scoping mutation-checked
  (removing `c.tenant_id = $1` reddened the list test, then restored). **API 636 passed.**
- **Live:** healthcheck **43 ok / 0 warn / 0 fail**; `/studio/` 200; `/owner/contacts` and the
  timeline route answer 401 (present, auth-gated) rather than 404. Real data proof
  (`scripts/vps/prove_contacts.py`): 3 contacts for `pukeko-construction`, one with 3 email events,
  summarise → `{'event_count': 3, 'by_channel': {'email': 3}, 'channels': ['email']}`.
- Honest limit: no live contact has mixed channels yet, so the cross-channel merge is proven by
  the merge logic in `test_case_timeline.py`, not by production data.

### Next
D (after-call intelligence: summary, outcome label, sentiment, follow-up task) → B (live call
supervision) → E (payments on accepted quotes) → F (attributed revenue).

### D. After-call intelligence — SHIPPED (`96827c1`), deployed and live-proved
- **Code:** `api/app/call_insights.py`. Deterministic first: no caller turns = no analysis at all;
  an appointment created around the call records `booked` without asking the model. Otherwise one
  model pass over the stored transcript, `parse_analysis` (fenced/padded JSON tolerated, unknown
  outcome downgraded to `unresolved`, unknown sentiment to `neutral`, unusable reply rejected
  outright), persisted with the model name. Per-tenant daily cap 50 so spend cannot run away.
- **Outcomes:** booked, quote_requested, call_back, information_only, not_interested, wrong_number,
  unresolved. `call_back` and `unresolved` create exactly one open task per lead (deduped).
- **Hook:** `events.spawn(call_insights.analyse_call_sid(...))` in the `serve_call` finally block, so
  a slow model can never delay the end of a call, plus a 6-hour anti-join sweeper for calls
  interrupted by a deploy. `UNIQUE (tenant_id, call_sid)` makes a replay a no-op, not a re-bill.
- **Owner surface:** `GET /owner/call-insights`; Studio → Bookings gained a "Recent calls" card
  (outcome badge, caller, summary, next step).
- **Onboarding:** `included` gains "A summary of every call".
- **Tests:** 16 new (`api/tests/test_call_insights.py`). Outcome-validation mutation-checked
  (accepting unknown outcomes reddened the test, then restored). **API 652 passed.**
- **Live:** deployed, health **43 ok / 0 warn / 0 fail**, `/owner/call-insights` 401 (present,
  auth-gated). Real analysis proved with `scripts/vps/prove_call_insights.py` on a synthetic
  transcript: model **grok-4.7**, outcome `quote_requested`, correct summary and next step,
  persisted, returned by `recent()`, fixtures and the temporary conversation removed afterwards.
- Honest limit: no real inbound calls have happened recently, so this is proved on a synthetic
  transcript through the real model path, not on a customer call.

### Next
B (live call supervision panel), then E (payments on accepted quotes), then F (attributed revenue).

### B. Live call supervision — SHIPPED (`908b9cf`), deployed and live-proved
- **Honest scope, documented in the module docstring and the readiness copy:** the provider's call
  API exposes call control (accept/hangup), **not** a SIP transfer or audio join, so there is no
  audio listen-in. This was verified against the public API surface before building; inventing a
  "listen in" button would have been a lie in the UI.
- **Code:** `api/app/live_calls.py` — pure rules (`is_live`, `caller_label`, `seconds_in_call`,
  `transcript_tail`, `summarise`) plus `active()`, `one()` and `take_over()`. Takeover ordering is
  the guarantee: **pause the case → alert the owner (number + conversation tail) → create a
  ring-back task → end the AI call (best effort, never raises)**.
- **Routes:** `GET /owner/live-calls`, `GET /owner/live-calls/{call_sid}`,
  `POST /owner/live-calls/{call_sid}/takeover` (404 unknown, 409 already ended).
- **Studio:** Bookings gained a "Happening now" card polling every 3 s with the caller, duration,
  whether the caller has spoken, the last turns of the conversation and a "Take over — ring them
  back" button.
- **Onboarding:** `included` gains "Watch a call while it happens", saying plainly that you ring the
  caller back rather than joining the call.
- **Tests:** 11 new (`api/tests/test_live_calls.py`) — liveness window, labels, negative durations,
  transcript bounds, ordering, task dedupe, hangup failure, non-SIP refusal, route guards.
  Pause-first ordering mutation-checked. **API 663 passed.**
- **Live:** health **43 ok / 0 warn / 0 fail**, `/owner/live-calls` 401 (present, auth-gated).
  Proof (`scripts/vps/prove_live_calls.py`) on a synthetic in-progress call: the console listed it
  with caller, 48 s, caller-spoken flag and the transcript tail; the drill-down reported live; after
  marking it ended it disappeared from `active()` — the guardrail that stops a stale takeover.
  Fixtures removed (0 left).
- Not done, deliberately: audio listen-in / whisper (needs a media server) and a true SIP transfer
  (not offered by the provider).

### Next
E (money on accepted quotes) then F (attributed revenue). **Constraint noted:** the operator wants
no Microsoft dependency and only free/GitHub services, so E must not force a paid processor:
implement tenant-supplied payment instructions/link + a "I have paid" declaration the owner confirms,
which keeps the money trail for F. Stripe remains an optional later add-on (it needs an account and
charges fees), never a dependency.

### E. Money on an accepted quotation — SHIPPED (`04ba6d1`), deployed and live-proved
**Deliberately processor-free**, because the operator's constraint is free/GitHub-only and no paid
service may become a dependency. The state machine is `unpaid → declared → paid` (or `waived`);
only an owner confirmation reaches `paid`, and a declaration is never treated as money.
- **Code:** `api/app/quote_payments.py` (pure rules + declare/confirm/summary/notify).
- **Schema:** `tenants.payment_instructions`/`payment_url`, `quotations.payment_status`,
  `payment_reference`, `payment_declared_at`, `payment_confirmed_at`, and the append-only
  `quote_payments` trail (kind, amount, reference, who) which item F reports on.
- **Public quote page:** an accepted quotation shows the business's instructions and/or link plus an
  "I have paid" form with an optional reference; the page states plainly that a declaration is not
  a payment. Payment URLs are restricted to http(s), so `javascript:`/`data:`/relative values are
  never rendered.
- **Owner API:** `GET`/`PUT /owner/payment-settings` (with paid/claimed/outstanding summary),
  `POST /owner/crm/quotations/{id}/payment` (confirm | waive). A customer's claim alerts the owner
  immediately.
- **Studio:** "Getting paid" card in Quotes (instructions, optional link, money totals) plus a
  payment badge and "Confirm paid" on each quotation.
- **Tests:** 13 new (`api/tests/test_quote_payments.py`); accepted-only rule mutation-checked.
  **API 676 passed.**
- **Live proof** (`scripts/vps/prove_quote_payments.py`): rendered the public page through the app
  itself — instructions and "I have paid" both present; declare → `declared` with the reference
  stored; confirm → `paid`; summary `paid 115000 / outstanding 0`; audit trail
  `declared (customer)` → `paid (owner)`; a second confirm refused; fixtures deleted and the
  tenant's payment settings restored. Health **43 ok / 0 warn / 0 fail**.

### F. Attributed revenue — SHIPPED (`d502443`), deployed and live-proved
- **Code:** `api/app/revenue.py` — enquiries by channel, quotes sent/accepted, accept rate, accepted
  value, confirmed paid vs outstanding, value per enquiry, and percent change against the previous
  window. No new event pipeline: every number is derived from rows written for other reasons, so the
  report cannot drift from the records.
- **Honesty rules:** no previous period reports `None` rather than a fake 0%; zero enquiries never
  divides by zero; the window is clamped to 1–365 days (0 means the 30-day default); the note says
  accepted value is not banked money.
- **Surface:** `GET /owner/revenue?days=30`; Studio → Reports gained "What it earned — last 30 days"
  with the channel split.
- **Tests:** 8 new (`api/tests/test_revenue.py`); the no-basis rule mutation-checked.
  **API 684 passed.**
- **Live proof** (`scripts/vps/prove_revenue.py`): seeded two enquiries and two quotations (one
  paid), report returned `enquiries 9, quotes sent 2, accepted 2, accept rate 100%, accepted value
  2000 NZD, paid 1200, outstanding 800, value/enquiry 222.22`, with the payment trail
  `declared → paid`; after deleting the fixtures it returned to the true baseline (7 enquiries,
  0 paid), proving it reads real data. Health **43 ok / 0 warn / 0 fail**.

## Session 2026-11-12 (ninth) — all six competitor-gap items shipped

A, C, D, B, E, F are **implemented, tested, committed, pushed and deployed**, each with a live proof
(see the sections above). Final state: **API 684 passed**, live healthcheck **43 ok / 0 warn /
0 fail**, `/studio/` 200, every new owner route answering 401 (present and auth-gated).

**The onboarding guarantee is live:** `provider_readiness.report()["areas"]["included"]` now lists
all six capabilities for the customer —
`See what it earned you` · `Get paid on an accepted quotation` (unconfigured until the tenant adds
bank details) · `Watch a call while it happens` · `A summary of every call` ·
`One timeline per customer` · `Missed-call text-back`
— and a test asserts every shipped capability is advertised there, so future features cannot ship
silently. Microsoft appears nowhere; Google Calendar remains the only calendar integration.

**Honest limits, carried forward:**
- A (text-back) is inert for `pukeko-construction` because that tenant has `sms_enabled = false`.
- B has no audio listen-in: the provider offers call control (accept/hangup), not a SIP transfer.
- E is not card payment; if card payments are wanted later, Stripe or similar can drive the same
  state machine (the schema stores declarations and confirmations, not card data).
- Proofs for D/E/F used synthetic rows on the real database and cleaned up afterwards; no real
  customer call, payment or quote has exercised these paths yet.
- The `GO_LIVE_HARDENING.md` items (Brevo secret/SMTP key/plan, DMARC `p=reject`, Cloudflare token
  split, scratch tenants + `admin@trendibizz.com`) and the operator items (phone DID, social OAuth,
  offsite backups, xAI key) are **unchanged and still open**.
