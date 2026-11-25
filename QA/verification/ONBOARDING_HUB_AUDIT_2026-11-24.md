# Onboarding Hub audit, 2026-11-24

State found: hub (OnboardingHub.tsx, TabGuideDrawer.tsx, /guide, migration 0005, progress API) was uncommitted, unpushed, undeployed.

Defects found and fixed (all covered by the suite, 1955 passed):
1. `GET /owner/onboarding/preview-slots` called nonexistent `booking.available_slots` -> 500. Now loops `booking._slots_on` per day.
2. `GET /owner/onboarding/progress` counted a nonexistent `documents` table -> 500. Now `count(DISTINCT url) FROM chunks`.
3. `Setup` unused after hub swap broke `tsc -b`. Kept as exported `LegacySetup`.
4. guide.html: description 167 chars, no dateModified, not in sitemap. Fixed; `site_seo.py check` OK, `seo-gate.sh` PASS.
5. Tests tied to old state updated for the new page / hub (a2ui inventory, footer count 41->42, wizard header now asserts the 7-stage hub).

Mutation check: before the fixes, the hub test failed on both 500s (documents, available_slots).

## Follow-up 2026-11-25
- Hermes leftovers deleted (untracked files only: concierge-stack/hermes, concierge-stack/action-gateway build dir 3.1 GB, 5 QA/verification/HERMES* docs).
- healthcheck.sh: runs on the box (cron every 5 min), not the Mac. On the box: ok=true, 51 ok / 0 fail. One warning: test-1..test-3 tenants "still onboarding" - fails after the grace window unless they finish onboarding or are flagged is_test.
- Slot preview, second defect: API returned strings, UI renders `s.label || s.start`, so every badge read "Slot". New public `booking.next_slots()` returns {start,label}; test now asserts non-empty and shape (mutation-checked: renaming `label` fails it).
- Portal bundle: lazy-loaded Companies, SavedReplies, Knowledge, Privacy, Billing, Invoices, Integrations, OnboardingHub, TabGuideDrawer; en.json excluded from the locale glob (removed the INEFFECTIVE_DYNAMIC_IMPORT warning). Main chunk 868 -> 780 kB (gzip 270 -> 246). A vendor-split was tried and rejected: total gzip rose (about 490 kB). Remaining weight is the design system; the 941 kB o3dv chunk is the already-lazy 3D viewer.

## 2026-11-25 follow-up: 3D piece removed (Jo: "remove the 3d piece completely", whole Designs tab + API)
- Cause: 3D viewer (online-3d-viewer, ~941 kB chunk) and the IFC takeoff flow served one trade; Jo chose to drop it entirely.
- Removed: portal Designs tab/nav/route, `online-3d-viewer` dep (both lockfiles), `api/app/designs.py`, `ifc_takeoff.py`, `guides.py` (/guide/bonsai-cladding), `quote_profiles.py` (/owner/quote-profiles, only used by Designs), `ifcopenshell` requirement, `designs_dir` config, Bonsai/Conrad docs, the "Quote from a plan or 3D model" button, the design_id/takeoff path in quotation draft (draft now needs a brief or enquiry; model failure returns 422 instead of a measured fallback).
- Left on purpose (irreversible, Jo to decide): DB tables `design_uploads` and `quote_profiles` with their data, `/opt/trendi/shared/designs` volume mount and files, orphaned i18n strings.
- Proof: `npm run build` clean, no o3dv chunk, main chunk 779 kB; pytest 1922 passed, 42 skipped (suite shrank by the deleted tests). Mutation check: removing the 422 refusal fails test_quotation_draft_route.
- Deploy: deploy-api.sh + deploy-studio.sh. First verify showed DRIFT (rsync never deletes); added the four api files to `scripts/vps/removed-paths.txt`, redeployed, prune moved them to `removed/<date>/` on the box. `verify-deploy.sh`: "OK: repo and box agree".

## 3D/Designs removal, part 2 (2026-11-25): tables, uploads, copy sweep

Jo approved dropping the data. Production before the change (read-only): `design_uploads` 0 rows, `quote_profiles` 1 row
(tenant 271485f2…, "Nu-Wall cladding", rate 0, default), `design_links` 1 row (created 2026-11-11, expired 2026-11-18).
`/opt/trendi/shared/designs`: 4 files, 28K (3 test .stl/.ifc files, no customer data).

- **Migration `0006_drop_design_tables`**: drops `design_uploads`, `quote_profiles`, `design_links` (downgrade recreates structure only).
  Verified locally: stamp 0005, upgrade, downgrade, upgrade all succeed. Removed the three tables from `schema.sql`, `rls.py`, `admin.py` status count.
- **Uploads**: `scripts/vps/archive-designs.sh` moves the folder to `/opt/trendi/shared/removed/designs-<date>/` (reversible, nothing deleted).
  Removed the `/data/designs` mount from `compose.yml` and the `shared/designs` backup exclude. `probe_owner_routes.py` no longer reads a `designs` table.
- **Copy sweep**: `website/ai-office-builders.html` still offered plan upload, DWG review and IFC wall-area cladding quotes (two FAQ pairs in JSON-LD and
  visible text, one attachments bullet): removed. Orphan i18n keys removed from all portal locales (6 `copy` keys + nav `Designs`, 210 entries).
  No other offer found in website/, api/app, api/static, docs, scripts.
- **Proof**: suite 1922 passed / 42 skipped; portal build clean; `seo-gate.sh` GATE RESULT: PASS.

## CAD / drawings data purge (2026-11-25)

Jo: "remove all data pertaining to CAD or drawings", "no mention on the site".
- **Site (FACT)**: grep of `website/` and `api/static/` for cad|dwg|ifc|3d|bonsai|drawing|cladding|design upload|floor plan: 0 files.
  Live: all 45 URLs in trendibizz.com/sitemap.xml fetched, 0 matches.
- **DB scan** (`scripts/vps/scan-cad-data.sh`, read-only, counts only). Real leftovers found:
  12 stale knowledge chunks of the old `trendibizz.com/ai-office-builders` crawl on tenants `trendi-support` and `trendi-oauth-staging`
  (6 each; text still offered "IFC model... wall areas for cladding quotes", "PDF and DWG plans", "design upload link", so the receptionist could repeat it),
  and 1 `ui_translation_cache` row ("Designs and CAD").
- **Left alone on purpose**: Pukeko Construction (271485f2) is a real cladding business, so "cladding" in its persona, greeting and KB is its trade, not the feature.
  Other outbox/case_events hits are noise (URL-encoded `3D=`, ordinary "drawings or samples"). Already-sent outbox mail is history. test-1/2/3 untouched.
- **Purge** (`scripts/vps/purge-cad-data.sh --apply`): deleted 12 chunks, 1 cache row, and `/opt/trendi/shared/removed/designs-20261124` (4 test .stl/.ifc files, listed first).
  Re-scan: 0 chunks match ifc|dwg|design upload.
- **Closes the earlier unverified item**: `design_uploads`, `quote_profiles`, `design_links` count in information_schema on the box = 0.
- **Follow-up**: the two Trendi tenants have no KB for the builders page until re-ingested from the clean live page.

## Onboarding sufficiency check (2026-11-25)

Scope covered: concierge-start.html promises ("invite you into your private portal", "test each channel before it goes live", "you review, then we go live",
"we never ask for a password"), the 7-stage hub, the invite email, and the progress API. Traced to tests: invite email link/first steps/no-price/no-password-paste
(`test_owner_invite_email.py`), progress read/save, sandbox test chat (dry run, 0 leads), test alert ([TEST] email), slot preview (`test_onboarding_hub_20261124.py`).
- **Defect: "Launch Concierge" was cosmetic.** `PUT /owner/onboarding/progress {launched:true}` stamped `launched_at` with no server check, and nothing reads
  `launched_at` (grep: no consumer). A business with no knowledge and no alert email saw a "Launched" badge, so the hub implied readiness it had not verified.
  The UI also swallowed the error and always continued.
- **Fix**: shared `_onboarding_auto_checks()`; first launch is refused with 409 ("Before you launch, add: ...") unless identity, knowledge (>=1 page) and an alert email exist.
  Re-saving after launch keeps the original `launched_at`. UI shows the reason and does not mark Launch done on refusal.
- **Test**: hub test asserts 409 + `launched_at` still null, then success after a knowledge chunk, then idempotent re-launch. Mutation check: disabling the gate fails it.
- **Proof**: suite 1922 passed / 42 skipped; portal build clean.
- **Not covered (UNKNOWN)**: no real end-to-end channel test (phone, SMS, email delivery) was run; policy forbids real SMS/calls and mail replay to production.
  "We verify each agreed channel before switching it on" remains a staff process on the box, not something the hub enforces: `launched` does not enable or disable any channel.
