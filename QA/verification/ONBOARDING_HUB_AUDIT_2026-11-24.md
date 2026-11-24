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
