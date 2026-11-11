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
