# QA Verification — iPhone Home Screen monochrome 'C' icon fix (2026-11-27)

## Cause
`https://concierge.trendibizz.com/apple-touch-icon.png` and `/apple-touch-icon-precomposed.png` both returned **HTTP 404**. When iOS Safari adds a web app to the Home Screen (especially if added before metadata finishes loading or from a sub-path), it probes `/apple-touch-icon.png` at the domain root; receiving 404 caused iOS 18 Dark Mode to generate a black-and-grey fallback **"C"** monogram instead of the coloured purple Concierge bell (`web/portal/public/apple-touch-icon.png`, 180×180 RGB PNG). In addition, `index.html` and `install.html` omitted `sizes="180x180"` on `<link rel="apple-touch-icon">`.

## Fix
- Added `@router.get("/apple-touch-icon.png")` and `@router.get("/apple-touch-icon-precomposed.png")` in `api/app/routers/public.py` serving `STUDIO_DIR / "apple-touch-icon.png"` (`200 image/png`, `Cache-Control: public, max-age=86400`).
- Added `sizes="180x180"` and bumped `?v=20261127` on `<link rel="apple-touch-icon">` in `web/portal/index.html` and `web/portal/public/install.html`.
- Added regression test `test_root_apple_touch_icon_routes_exist_and_html_declares_180x180` in `api/tests/test_pwa_install.py`.

## Proof
- `pytest -q tests/test_pwa_install.py`: all passed.
- Deployed via `scripts/vps/deploy-api.sh` and `scripts/vps/deploy-studio.sh`; verified with `scripts/vps/verify-deploy.sh` (`OK: repo and box agree`) and live `curl` check confirming HTTP 200 `image/png` on `/apple-touch-icon.png` and `/apple-touch-icon-precomposed.png`.
