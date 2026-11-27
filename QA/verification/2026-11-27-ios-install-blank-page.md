# QA Verification — iPhone "Install app" blank page (2026-11-27)

## Cause
When tapping **Install app** in Studio on iPhone (`location.href = '/studio/install'`), the active service worker (`web/portal/public/sw-v2.js`) intercepted the `mode === 'navigate'` request and called:
```js
const response = await fetch(event.request, {cache: 'no-store'});
```
In WebKit / iOS Safari, passing an `init` object (`{cache: 'no-store'}`) to `fetch(event.request, init)` for a `navigate`-mode `Request` throws a `TypeError` (WebKit rejects constructing a `Request` with overrides from a `navigate` `Request`). Because `navigator.onLine` was `true`, `sw-v2.js` re-threw the error, leaving iPhone Safari on a blank page.

Secondary defects in the same flow:
- `sw-v2.js` intercepted `/studio/install` and overwrote the offline `/studio/` cache entry with `/studio/install` HTML.
- `web/portal/src/App.tsx` rendered the **Install app** button even when `isInstalled()` was already `true` (standalone home-screen app).
- `web/portal/public/install.html` had no **Back to Concierge** button in the iOS section.

## Fix
- `web/portal/public/sw-v2.js`:
  - Bypass the service worker completely for `/studio/install` and `/studio/install/` so Safari navigates natively.
  - Fetch SPA navigations by URL string (`fetch(event.request.url, {cache: 'no-store', credentials: 'same-origin'})`), sanitize redirected responses for WebKit, and only cache `status === 200` responses for `/studio/` under `'/studio/'`.
- `web/portal/src/App.tsx`: hide **Install app** when `isInstalled()` is true.
- `web/portal/public/install.html`: add a **Back to Concierge** link in the `#ios` card.
- `api/tests/test_setup_after_setup.py`: updated `test_the_service_worker_can_never_pin_a_browser_to_an_old_build` to enforce `fetch(event.request.url, {cache: 'no-store'`, forbid `fetch(event.request, {cache:`, and assert `/studio/install` bypass.

## Proof
- Rebuilt `web/portal/dist` (`pnpm run build`).
- `pytest -q api/tests/test_setup_after_setup.py api/tests/test_pwa_install.py api/tests/test_studio_shell.py`: all passed.
- Mutation check: restoring `fetch(event.request, {cache: 'no-store'})` in `sw-v2.js` caused `test_the_service_worker_can_never_pin_a_browser_to_an_old_build` to fail (exit 1), then pass once restored.
- Full test suite + `deploy-studio.sh` + `verify-deploy.sh` passed.
