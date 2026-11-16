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

---

# Follow-up: the QR opened a sign-in screen, not an install (same day)

## What the operator saw

Scanning the install QR on a phone landed on the Studio's sign-in screen, which asks for an email
address to send a link. "What is the point of the QR code if you have to do this?"

## Cause

`/studio/install` was a **route inside the Studio's single-page app**. The server answered the URL
with the app shell, and the SPA decided what to render. Anything that put the SPA in its signed-out
or stale state — a stored session, a cached bundle from before the route existed, or the auth gate
winning the render — produced the sign-in screen instead of the install offer. The page could be
correct in a headless browser and still wrong on a phone that had used the Studio before.

## Fix

The install page is now its **own HTML document**, not a route in the app:

- `web/portal/public/install.html` — no React, no router, no auth, no email field. It links the
  manifest, registers the worker, captures `beforeinstallprompt` itself, and shows exactly one of:
  already installed / one-tap install (phone) / Safari Share → Add to Home Screen (iPhone) /
  browser-menu route (other phones) / QR + "install on this computer" (desktop).
- `main.py` serves it at `/studio/install` **before** the `/studio/{path}` catch-all, with
  `no-store` and `noindex`. If the file is missing (a deploy in progress) it falls back to the
  shell rather than 404.
- `install-qr.svg` is a static asset on the same page, so a desktop still gets a scannable code.
- The SPA branch and `Install.tsx` were deleted: one implementation, not two.
- Desktop now always shows the QR even when the desktop browser offers an install — the point of
  the page is the phone in the person's hand.

## Proof

- Live `/studio/install` returns `<!doctype html><title>Install Concierge</title>` with **zero**
  app bundle references — it cannot render a login screen.
- Emulated Pixel 8 at 390px: one visible section, `one-tap`, buttons "Install Concierge" and
  "Open without installing".
- Emulated desktop at 1440px: one visible section, `desktop`, with the QR and "Install on this
  computer".
- `tests/test_pwa_install.py` (13 tests) now asserts the document is standalone (no email field, no
  `location.pathname`), that the static route is declared before the catch-all, and that the
  desktop branch precedes the install-prompt branch.
- `tsc` clean, portal built, Studio and API deployed, `verify-deploy` OK.

## Honest limit, unchanged

No web page can install itself without a gesture. On Android the QR now lands directly on a page
whose only action is **Install Concierge** (one tap). On iPhone, Apple requires Safari's
Share → **Add to Home Screen** (three taps); no site can bypass that.

---

# Follow-up: iPhone Chrome cannot install, and now says why (same day)

## The question

"The QR doesn't work on an iPhone using Chrome — it asks you to use Safari."

## The answer

That is Apple's rule, not a defect in the page. On iOS, **"Add to Home Screen" exists only in
Safari**. Chrome, Firefox, Edge and the in-app browsers (Instagram, Facebook) on iOS are WebKit
shells that Apple does not give the install action to, and `beforeinstallprompt` is not fired on
iOS at all — so there is no button a site can offer there. No web page can switch the browser
either; only the person can. Apple documents the feature as a Safari feature
([Apple Support](https://support.apple.com/fr-ne/guide/iphone/iphea86e5236/26/ios/26)); the Chrome
support forum carries the same report
([Chrome help thread](https://support.google.com/chrome/thread/272737774/add-a-website-to-home-screen-option-is-not-available-in-chrome?hl=en)).
This deployment is in New Zealand, outside the EU changes to browser engines, so the Safari-only
path is the one that applies.

## What changed

Saying "use Safari" without a reason reads like the site is broken, so the iPhone path now:

- names the browser it detected — "On iPhone, install from Safari — not **Chrome**";
- says plainly that Chrome on iPhone cannot add a web app to the Home Screen and that no site can
  change that;
- gives the three Safari taps;
- offers **Copy the link for Safari**, because copying and pasting is the only reliable way across
  from Chrome (no URL scheme is offered — an untested `x-safari-` link would be a button that does
  nothing);
- checks iOS **before** the install-prompt branch: Apple never fires that prompt, and if a browser
  ever did on iOS the button would be dead.

Detected: `CriOS` (Chrome), `FxiOS` (Firefox), `EdgiOS` (Edge), `OPiOS` (Opera), `GSA` (Google
app), `Instagram`, `Facebook`.

## Proof

- Emulated iPhone (390×844, iOS 18.2 Chrome UA): one visible section, `ios`; heading "On iPhone,
  install from Safari — not Chrome"; buttons "Copy the link for Safari". Screenshot:
  `install-iphone-chrome-2026-11-16.png`.
- Emulated Android: `one-tap`, "Install Concierge".
- Emulated desktop: `desktop`, the QR.
- `tests/test_pwa_install.py` (14) asserts the browser detection, the explanation, the copy button,
  and that no untested URL scheme is offered.
- Suite: 1444 passed, 19 skipped, 29 failed (the known local-Postgres outage). Deployed; Live page
  confirmed.
