# UI libraries wired across trendibizz.com and Studio — 2026-11-27

## Goal
Pick the best UI library / pattern per spot (one standout per page) across both the static marketing site (`website/`) and Studio (`web/portal/`, React 19 + Vite + Astryx), brand-restyled with zero CSP or Astryx-rule regressions.

## What went where

### Static site (`website/`, vanilla TrendiUI module)
- **Site-wide utility (`website/main.js`, `website/ui/trendi-ui.css`, all 56 HTML pages):**
  - Cmd/Ctrl-K command menu (`TrendiUI.commandMenu` over `/ui/search-index.json`) + compact header `Search ⌘K` trigger.
  - Mobile bottom sheet (`TrendiUI.sheet`, drag-down-to-close) for `#menu-btn` on viewports `<= 760px` (dropdown fallback above 760px).
  - Sonner-style copy toasts (`TrendiUI.toast`) on `#start-copy` (`main.js`) and `#mc-copy` (`tools/missed-call-cost-calculator.js`).
- **One standout per page:**
  - `/tools/missed-call-cost-calculator` → `TrendiUI.ticker` on week / month / year lost revenue figures.
  - `/pricing` & `/ai-office-cost` → `TrendiUI.ticker` on a progressive "Per month / 3-month minimum" toggle (`$199` ↔ `$597`, `$499` ↔ `$1,497`; static crawler HTML untouched).
  - `/tools/site-check` & `/tools/robots-ai-check` → `TrendiUI.aiStatus` thinking steps while fetching and checking (with `main.js` updated to recognize `[aria-busy="true"]` as pending).

### Studio (`web/portal/`, real MIT React libraries + Astryx kept)
- `sonner` (`2.0.8`) in `src/Notify.tsx` — replaces Astryx toast while keeping `useNotify()` signature unchanged for all 7 call sites.
- `cmdk` (`1.1.1`) in `src/CmdK.tsx` — grouped, fuzzy-ranked `⌘K` palette.
- `@number-flow/react` (`0.6.2`) in `src/Home.tsx` (4 KPI tiles), `src/Pipeline.tsx` (open/weighted/won totals), `src/Quotes.tsx` (live quote total).
- `vaul` (`1.1.2`) in `src/TabGuideDrawer.tsx` — bottom sheet with drag handle on `<= 760px`, right drawer on desktop.
- Brand restyling in `src/shell.css`: self-hosted Plus Jakarta Sans (`public/fonts/plus-jakarta-sans-var.woff2`), `#7c5cff` / `--c-accent` tokens, `prefers-reduced-motion: reduce`.

## Verification
- `pytest api/tests/test_site_trendi_ui.py` — 8 passed (command score, sheet release, toast stack, ticker parts, CSP/site rules, search index freshness, all 56 HTML pages wired, Studio real libraries + build output).
- `python3 scripts/seo/site_seo.py check` — OK: 56 pages.
- `./scripts/seo-gate.sh` — PASS=22 FAIL=0 WARN=0 (`GATE RESULT: PASS`).
- `PLAYWRIGHT=... node QA/verification/trendi_ui_browser_smoke.cjs /tmp/tui-smoke` — strict `style-src 'self'` CSP, zero JS/CSP errors; verified `homeSearchBtnOpensCmdk`, `homeMobileSheetOpens`, `sheetClosedByDrag`, `pricingToggleVal: "$597"`, `calcYearTicker: "393,120"`, `calcCopyToast: "Shareable link copied"`, `siteCheckAiThinking: true`.
- `cd web/portal && pnpm run lint && pnpm run build` — 0 errors, built in ~500ms.
- Full pytest suite + repo deploy scripts (`deploy-site.sh`, `deploy-studio.sh`) + `verify-deploy.sh` run before sign-off.
