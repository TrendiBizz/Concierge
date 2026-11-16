# Invitation QR — 2026-11-16

## Symptom

The team-invitation token was shown only as a raw private link (`/studio#invite=…` in Studio, the
textarea in `/owner-ui`). The person inviting had no way to hand that one-time token to a phone
except by typing or messaging the URL. That is the exact friction the hosted-chat QR already solved
for chat links, and the invitation flow did not have it.

## What changed

- **Studio `Team` panel** (`web/portal/src/App.tsx`): after an invitation is created, the result shows
  the link *and* a locally drawn QR. The QR is labelled `QR code for this invitation`; a second
  higher-resolution SVG is available as `Download the QR to print`.
- **Legacy `/owner-ui`** (`api/static/owner.html`): the same result block now draws the QR with the
  vendored `qrcode-generator` library, behind `inviteQrSvg()`, and offers the print download.
- **Encoder asset** (`api/static/qrcode.js`): `qrcode-generator@2.0.4`, MIT, vendored from the same
  package the Studio already uses. Served at `/owner/qrcode.js` (`api/app/main.py`) under `/owner/`,
  the only prefix the public proxy forwards.
- **Scan reliability/accessibility**: quiet zone is 4 modules (not 1–2); the inner `<svg>` is
  `aria-hidden="true" focusable="false"` and the wrapping element carries `role="img"` plus a text
  label, so assistive technology does not announce the QR twice.
- No QR service is contacted: the token is encoded in the browser, so a one-time invitation never
  leaves the page.

## Proof

- `api/tests/test_owner_invite_qr.py`: **3 passed**. Pins the invitation-result wiring, the
  `/owner/qrcode.js` response (200, `application/javascript`), and that the encoder loads before the
  inline code that calls it.
- Studio build: `cd web/portal && pnpm run build` → **built**, no TypeScript errors.
- Python suite: **1377 passed, 19 skipped**; the 29 failures were all
  `ConnectionRefusedError ('127.0.0.1', 55433)` because the local test Postgres was not running.
  They are not related to this change; the DB-backed subset has to be re-run once Postgres is up.
- The QR was rendered by the real page in headless Chrome and decoded by an independent reader
  (OpenCV `QRCodeDetector`), not by the library that drew it:

  ```text
  exact page:  /owner-ui, screenshot QA/verification/invitation-qr-owner-ui-2026-11-16.png
  decoded : 'https://concierge.trendibizz.com/studio#invite=SampleToken_1234567890abcdefghij'
  MATCH

  Studio page: Team → Create invitation, screenshot
  QA/verification/invitation-qr-studio-2026-11-16.png
  decoded : 'https://concierge.trendibizz.com/studio#invite=SampleToken_1234567890abcdefghij'
  MATCH
  ```

## Deployment gap found and fixed

`verify-deploy.sh` compared `api/app`, `scripts/vps` and `website/site`, but not `api/static` — the
directory that holds `owner.html`, `widget.js` and now `qrcode.js`. The API image copies
`api/static` at build time (`scripts/vps/Dockerfile.api`), so a static-only UI fix could be committed
and "verified" while the box kept serving the old page. Added:

- `scripts/vps/deploy-api.sh` — rsyncs **both** `api/app/` and `api/static/`, then runs the existing
  `redeploy-api.sh`.
- `verify-deploy.sh` now compares `api/static` too.
- `AGENTS.md` uses `deploy-api.sh` for API changes.

## Known limit

The invitation email body is still plain text with the sign-in link; the QR is shown where the token
is generated (and downloadable/printable), not embedded as an image in the message. Embedding would
require a server-side QR image and would put a one-time credential in an email image request.
