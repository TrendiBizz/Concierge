# The install QR — and why the old one opened the chat widget (2026-11-16)

## What the operator saw

The QR handed out as "the app" opened `chat.trendibizz.com` — the hosted chat page — and installed
nothing. The ask was a QR a phone can capture that puts the whole Concierge system on the phone.

## Two separate causes

**1. The QR was for the wrong thing.** In Studio → Setup, the hosted-chat block drew
`QrCode value={hosted}` where `hosted = https://chat.trendibizz.com/demo/<slug>`, under copy that
said "print the QR code for your van, quotes and signage" next to app-install language. It was
working exactly as written; it just pointed at the chat page. The *invitation* QR was not at fault:
it encodes `onboarding_url + "#invite=<token>"` = `https://concierge.trendibizz.com/studio#invite=…`.

**2. The app was not installable at all, so even a correct QR could only open a tab.**
`web/portal/public/manifest.webmanifest` existed, every icon existed, `sw-v2.js` registered — but
`index.html` **never linked the manifest**. Chrome's install criteria were therefore never met:
`beforeinstallprompt` never fired, and the header's "Install app" button (which listened for that
event, inside the signed-in shell, after sign-in) never appeared. Measured live before the fix:

```
curl -s https://concierge.trendibizz.com/studio/ | grep 'rel="manifest"'   # 0 matches
curl -s .../studio/manifest.webmanifest                                    # 200 — nobody asked for it
```

## The fix

- `web/portal/index.html`: links the manifest, the 180×180 `apple-touch-icon`, adds
  `theme-color`, the Apple standalone meta tags, a real description, and the title `Concierge`
  (it said `portal`).
- `manifest.webmanifest`: `id: /studio/`, `display_override`, `lang`, `categories`,
  `prefer_related_applications: false`, and two shortcuts. Existing icons were already correct.
- `src/installPrompt.ts` (new): captures `beforeinstallprompt` at startup, before React mounts and
  before sign-in, and exposes `promptInstall()`, `isInstalled()`, `isIOS()`, `isMobile()` and
  `installUrl()`. The shell now subscribes to it instead of owning a listener that fired too late.
- `src/Install.tsx` (new): the public page a QR points at, at `/studio/install` (the API's
  `studio_file` already falls back to the shell for a dot-free path):
  - installed → "already on this phone";
  - phone + install offer → one **Install Concierge** tap;
  - iPhone → Safari Share → Add to Home Screen, with the reason;
  - phone without an offer → the browser-menu route (not "scan this with the phone you are on");
  - desktop → the QR, the URL, a downloadable SVG, and an optional "install on this computer".
  It says plainly that a QR opens the page and the phone does the install.
- `src/QrCode.tsx`: the QR drawing and SVG download moved out of `App.tsx` so both the invitation
  and the install page use one implementation.
- Studio → Setup: a new **"Put Concierge on your phone"** block with the install QR and a
  `concierge-install-qr.svg` download. The hosted-chat block keeps its link and copy button but no
  QR, and now says "it is not the Concierge app". The old "print the QR for your van" sentence is
  gone — that sentence is what made a chat QR look like an app QR.

## Proof

- `api/tests/test_pwa_install.py` — 12 tests: manifest linked; manifest meets install criteria;
  every declared icon exists at the size it claims (PNG IHDR, not the filename); the install page is
  reachable without signing in and the branch sits before the login gate; the server falls back to
  the shell for `/studio/install`; the prompt is captured before `createRoot`; iPhone/Android copy;
  the QR encodes the install page and the chat QR is gone; a phone without an offer is not told to
  scan itself.
- Two mutations, each watched go red then restored:
  - remove `<link rel="manifest">` → manifest test fails;
  - point the QR back at `hosted` → QR-target test fails.
- Live after `deploy-studio.sh`:
  - `/studio/` links the manifest and apple-touch-icon; title is `Concierge`;
  - `/studio/manifest.webmanifest` serves the new manifest;
  - `/studio/install` → 200;
  - **headless Chrome on the live page fired `beforeinstallprompt`** — the page rendered "One tap to
    install" with an **Install Concierge** button, which is only possible once Chrome accepts the
    app as installable;
  - the desktop rendering shows the QR and the URL;
  - **the QR on the live page decodes to `https://concierge.trendibizz.com/studio/install`**
    (OpenCV `QRCodeDetector` on the headless Chrome screenshot — not `chat.trendibizz.com`).
- Suite: **1413 passed, 19 skipped, 29 failed** — the same 29 local-Postgres connection failures
  as before (HANDOFF item 34).
- `tsc -b` clean, `npm run build` succeeds.

## Honest limit, stated in the product

A web page cannot add itself to a home screen. The QR opens the install page; Android installs with
one tap, iPhone needs Safari's Share → Add to Home Screen. Both the QR block and the install page
say so rather than promising a silent install.

Screenshots of the live page:
`pwa-install-page-desktop-2026-11-16.png` (Chrome offering the one-tap install) and
`pwa-install-qr-desktop-2026-11-16.png` (the QR that decodes to the install URL).

**Not yet verified:** installation on a physical iPhone and Android handset. The browser accepted
the app and offered the prompt in headless Chrome; a real phone is the remaining proof.
