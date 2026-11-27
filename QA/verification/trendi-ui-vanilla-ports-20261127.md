# Trendi UI vanilla ports — 2026-11-27

## Why
Jo's UI-libraries rule (`~/.claude/rules_ondemand/ui-libraries.md`, video sent 2026-11-27): use Sonner, Vaul,
cmdk, NumberFlow and Beautiful UI instead of hand-built parts. `website/` is static HTML, so the React
libraries cannot drop in. Jo: "we can still use the ideas and modify them accordingly for ourselves so it's not
wasted." So the ideas are ported to one small vanilla module, styled on the site's brand tokens.

## What
- `website/ui/trendi-ui.js` (24.7 KB, 7.8 KB gzip) — `TrendiUI.toast` (Sonner), `.sheet` (Vaul), `.commandMenu`
  (cmdk), `.ticker` (NumberFlow), `.aiStatus` thinking/stream/approve/done (Beautiful UI).
- `website/ui/trendi-ui.css` — brand tokens only (`--font` Plus Jakarta Sans, `--accent` purple, `--radius`).
- `website/ui/search-index.json` + `scripts/seo/build_search_index.py` — Cmd-K index from sitemap pages only.
- **Wired into all 56 site pages (2026-11-27):**
  - Every page loads `/ui/trendi-ui.css` + `/ui/trendi-ui.js` before `main.js`.
  - Every page gets Cmd/Ctrl-K site search (`TrendiUI.commandMenu`) + header `Search` trigger button (`.tui-search-btn`).
  - Phones (`<=760px`) get the Vaul-style drag-to-close bottom sheet (`TrendiUI.sheet`) on `#menu-btn`.
  - Copy buttons (`#start-copy`, `#setup-copy`, `#mc-copy`) fire Sonner-style toasts (`TrendiUI.toast`).
  - One standout per page:
    - `/tools/missed-call-cost-calculator`: NumberFlow-style rolling digit ticker (`TrendiUI.ticker`) on weekly/monthly/yearly lost amounts.
    - `/pricing`: `Per month` / `3-month minimum` toggle rolling `$199→$597` and `$499→$1,497` (`TrendiUI.ticker`).
    - `/tools/site-check` & `/tools/robots-ai-check`: Beautiful UI thinking steps (`TrendiUI.aiStatus`) while checks run.

## Licences (sources cloned to `~/work-staging/ui-tools/`, read 2026-11-27)
Sonner MIT (c) 2023 Emil Kowalski; Vaul MIT (c) 2023 Emil Kowalski (README: "This repo is unmaintained");
cmdk MIT (c) 2022 Paco Coursey; NumberFlow MIT (c) 2024 Maxwell Barvian; Beautiful UI MIT (c) 2026 Shane Levine
(beautifului.dev/license). Only cmdk's `commandScore` is copied (credit + MIT notice in the file header);
everything else is our own code written from each library's behaviour and constants (Sonner: 3 visible, 14px
gap, 4 s life, 45px swipe, alt+T, pause on hover/hidden tab; Vaul: 0.4 px/ms flick or 25% height closes,
cubic-bezier(.32,.72,0,1) 0.5 s; NumberFlow: digits roll, symbols still, aria-label holds the value).
RareUI: rareui.in now 301-redirects to a different domain; not used.

## Defects found and fixed this session
1. **Sheet did not close on drag-down when the pointer left the sheet** (smoke run: pointerup never reached
   the dialog). Cause: no pointer capture. Fix: `dlg.setPointerCapture` on pointerdown. Proof: smoke
   `sheetClosedByDrag: true`; test asserts the capture call.
2. **Cmd-K "pric" put "AI receptionist cost…" above "Concierge pricing…"** (equal cmdk scores, file order won).
   Fix: tie-break by earliest position of the query in the label. Proof: `test_command_score_ranks_like_cmdk`
   `tie` case; mutation (remove tie-break) fails it.
3. **Approval-card radios rendered 50px wide** — site `styles.css` sizes every input. Fix: explicit radio size
   in `.tui-ai-option input`. Proof: smoke screenshot after fix.

## Proof
- `api/tests/test_site_trendi_ui.py` — 6 pass. Mutation checks, each failing as expected: Vaul close fraction
  0.25→0.5; toast visible 3→4; upward-drag guard removed; non-brand font in CSS; stale search index;
  Cmd-K tie-break removed.
- `QA/verification/trendi_ui_browser_smoke.cjs` — Chromium, page served with `style-src 'self'` CSP, phone
  viewport: errors `[]`, ticker aria-label `$18,990.00` with reels at 1899000, 4 toasts / 1 hidden / aria-live
  polite, stream text complete, approval resolves "Edit first", Ctrl-K opens with focus in input, Esc closes,
  drag closes sheet.
- `python3 scripts/seo/site_seo.py check` → OK (56 pages).

## Needs Jo's yes before deploy
Which pages load the module and which single standout each gets (see plan in the session report).
