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


## Marketing media (Imagination Studio) — 2026-11-11
- Concierge side is built and deployed: `media_jobs`, `/owner/media/status|jobs`,
  file proxy and a **Marketing media** panel in the owner portal.
- It is not connected yet: set `STUDIO_URL` (private host) and `STUDIO_KEY`
  (Studio access key) in `/opt/trendi/shared/api.env`, then restart `api`.
- Studio host must be a supported Mac (48 GB+ for images, 96–128 GB for video),
  DGX Spark (128 GB) or supported NVIDIA GPU; run `oneshot-setup.sh --image-only`
  first (33 GB). Expose over Tailscale, never public; the key goes in
  `X-Studio-Key`. Full video install is ~182 GB weights.
- Workflow: owner prompts in the portal → Studio queues still/clip → Concierge
  records status and proxies outputs → owner approves into social drafts. No
  auto-publishing. Not used for CAD or quotations.
