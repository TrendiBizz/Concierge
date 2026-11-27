# QA Verification — Studio phone sticky nav/topbar overlap (2026-11-27)

## Cause
In `web/portal/src/shell.css`, desktop rules set `position: sticky; top: 0` on both `.c-topbar` (`z-index: 20`, semi-transparent backdrop blur) and `.c-nav` (`background: transparent`). The `@media (max-width: 900px)` phone block stacked `"brand" "topbar" "nav" "content"` vertically, but never reset `position: sticky; top: 0` on either element, left `.c-nav` transparent, and left `.c-nav-group` in desktop `flex-direction: column` with `flex: 0 0 auto` (no `max-width: 100%`).

Why it was missed earlier:
- `api/tests/test_studio_shell.py::test_the_shell_has_no_horizontal_scroll_on_a_phone` checked only CSS substrings (`grid-template-columns`, `flex-wrap`, `overflow-y: auto`), not `position: static` or scrolled bounding-box overlap.
- The 2026-11-15 live 390px phone measurement checked horizontal width at `scrollY = 0`, before scrolling engaged the two competing `position: sticky; top: 0` elements.

On iPhone (390×844), scrolling past the brand header pinned `.c-topbar` (159px) and `.c-nav` (321px, transparent) at `top: 0` on top of each other (`overlap_topbar_nav = 148px` at `scrollY = 220`) and over `.c-content` (`Pause everything` card + `Your business` hero).

## Fix
Updated `@media (max-width: 900px)` in `web/portal/src/shell.css`:
- Reset `.c-topbar` and `.c-nav` to `position: static; top: auto;` with opaque `background: var(--c-page)`.
- Set `.c-nav-group` to `flex-direction: row; flex-wrap: wrap; flex: 0 1 auto; max-width: 100%;` and reset `.c-nav-label` / `.c-nav-item` widths so all nav items wrap cleanly inside 390px without clipping at the right edge.
- Added `max-width: 100%` / `minmax(min(..., 100%), 1fr)` guards for `.meta-select`, `.meta-picker-grid`, and `.social-connect`, and `white-space: normal` on `.c-brand-sub`.
- Rebuilt `web/portal/dist` (`pnpm run build`).
- Added regression test `api/tests/test_studio_shell.py::test_phone_topbar_and_nav_do_not_stick_over_content` and mutation-checked it.

## Proof
1. **Studio 390×844 Playwright check (before vs after)**:
   - Before (`scrollY = 220`): `topbar.pos="sticky"`, `nav.pos="sticky"`, `nav.bg="rgba(0,0,0,0)"`, `overlap_topbar_nav = 148px`.
   - After (`scrollY = 0` and `scrollY = 220`): `overflowX = 0`, `topbar.pos="static"`, `nav.pos="static"`, `nav.bg="rgb(27,27,27)"`, `overlap_topbar_nav = 0`, `overlap_nav_content = 0`, `overlap_nav_hero = 0`, `overlap_topbar_content = 0`. Verified visually by screenshot.
2. **Whole-site 390×844 Playwright audit**:
   - Audited all 56 HTML pages in `website/` (top + scrolled `scrollY = 320`, plus mobile Menu bottom-sheet open on `index.html`, visual checks on `index.html` and `pricing.html`): **0 horizontal overflow, 0 sticky/fixed overlaps, 0 tall headers**.
   - Audited all 4 HTML pages in `api/static/` (`admin.html`, `onboarding.html`, `owner.html`, `social-oauth-callback.html`): **0 horizontal overflow, 0 sticky/fixed overlaps, 0 tall headers**.
3. **Regression test + mutation check**:
   - `pytest -q api/tests/test_studio_shell.py`: 23 passed.
   - Mutation check (removing `position: static` from `.c-nav` in `@media (max-width: 900px)`): `test_phone_topbar_and_nav_do_not_stick_over_content` failed as expected, then passed once restored.
