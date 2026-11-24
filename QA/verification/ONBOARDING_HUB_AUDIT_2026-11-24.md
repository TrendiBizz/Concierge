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
