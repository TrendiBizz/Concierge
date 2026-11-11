# Astryx Native — release watch

## Status
- `@astryxdesign/native` is currently **0.0.0-bootstrap.0**, described on npm as
  "Placeholder published to claim the npm name during trusted publishing setup.
  Do not install." (checked 2026-11-11).
- Check: `npm view @astryxdesign/native version` and
  `npm view @astryxdesign/native description`
- Repo: https://github.com/meta/astryx/tree/main/packages/native

## Watching
- Scheduled task `schedule-df99a8a8-0abe-4b82-a9d9-e9cbf8a06c8e` runs every
  **Monday 09:00 Pacific/Auckland** in a new session and reports whether the
  package is still a placeholder or a real release.
- When it ships: read the package requirements, scaffold an Expo/React Native
  app, reuse the existing owner APIs (auth, CRM, quotes, media), and replace the
  PWA for owners who want a native app. Keep the PWA as the no-install fallback.

## Interim mobile
- The portal is an installable PWA: PNG 192/512 + maskable icons,
  apple-touch-icon, install prompt in the header, offline shell service worker.
- Verified live: manifest and all icons return 200; login page renders headless.

## Check 2026-11-12 00:20 NZ (session 2026-11-12)
- Still a placeholder: `npm view @astryxdesign/native version` → **0.0.0-bootstrap.0**
  (`dist-tags.latest = 0.0.0-bootstrap.0`, `bootstrap = 0.0.0-bootstrap.1`).
- The canary tag now exists: **0.7.14-canary.gfdb9213** (published 2026-11-11T10:26Z).
  A canary is not a production release: no stability promise, Apple-only, and it is
  not what `latest` resolves to. Keep the PWA as the mobile path.
- Next check: the weekly Monday 09:00 NZ task, or `npm view @astryxdesign/native dist-tags`
  when a real release is suspected.
