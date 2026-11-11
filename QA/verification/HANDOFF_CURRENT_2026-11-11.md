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
