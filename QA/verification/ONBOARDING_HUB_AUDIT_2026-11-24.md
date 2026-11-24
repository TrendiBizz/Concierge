# Onboarding Hub audit, 2026-11-24

State found: hub (OnboardingHub.tsx, TabGuideDrawer.tsx, /guide, migration 0005, progress API) was uncommitted, unpushed, undeployed.

Defects found and fixed (all covered by the suite, 1955 passed):
1. `GET /owner/onboarding/preview-slots` called nonexistent `booking.available_slots` -> 500. Now loops `booking._slots_on` per day.
2. `GET /owner/onboarding/progress` counted a nonexistent `documents` table -> 500. Now `count(DISTINCT url) FROM chunks`.
3. `Setup` unused after hub swap broke `tsc -b`. Kept as exported `LegacySetup`.
4. guide.html: description 167 chars, no dateModified, not in sitemap. Fixed; `site_seo.py check` OK, `seo-gate.sh` PASS.
5. Tests tied to old state updated for the new page / hub (a2ui inventory, footer count 41->42, wizard header now asserts the 7-stage hub).

Mutation check: before the fixes, the hub test failed on both 500s (documents, available_slots).
