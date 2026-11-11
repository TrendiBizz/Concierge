# Languages and native app assessment — 2026-11-11

## Astryx i18n
- `@astryxdesign/core` ships **30 locales** (en + 29 translations; 31 JSON files
  including `pseudo`): af-ZA, ar-SA, ca-ES, cs-CZ, da-DK, de-DE, el-GR, es-ES,
  fi-FI, fr-FR, he-IL, hu-HU, it-IT, ja-JP, ko-KR, nl-NL, no-NO, pl-PL, pt-BR,
  pt-PT, ro-RO, ru-RU, sr-SP, sv-SE, tr-TR, uk-UA, vi-VN, zh-CN (plus en).
- `InternationalizationProvider` from `@astryxdesign/core/i18n` sets the locale;
  catalogs are passed as `messages`; runtime swap works; RTL is supported and
  Persian/Hebrew/Islamic calendars are available.
- Concierge supports **12 locales initially**: en, fr-FR, es-ES, de-DE, pt-BR,
  zh-CN, ja-JP, ko-KR, ar-SA, nl-NL, it-IT, pl-PL. More can be added by copying
  the compact catalog and adding the locale code.

## Detection and switching
Precedence implemented in the portal:
1. explicit `?lang=` query
2. saved preference (`localStorage: concierge.locale`)
3. browser language (`navigator.language`)
4. IP country via Cloudflare `CF-IPCountry` → `/owner/locale`
5. English fallback

Verified: `CF-IPCountry: FR` → `fr-FR`; `JP` → `ja-JP`. RTL is applied for
`ar`/`he`.

## Limits
- Astryx strings (component labels, aria text) switch automatically.
- **Our product copy is still English.** Full language support needs translation
  files for the portal screens; that is the next piece.
- AI conversations already receive a rule to reply in the visitor's language.
- The website widget chrome is still English; it needs a small string catalog.

## Native
`@astryxdesign/native` is **experimental, canary-only**, with a SwiftUI binding
for **iOS/macOS only**, 12 core contracts; Android and React Native are not
built. It is explicitly not supported for production. So "take Astryx and make
our own native" is possible but means one of:
1. **SwiftUI app using the canary Swift package** — Apple only, experimental.
2. **React Native/Expo app** — cross-platform, but Astryx web components cannot
   be reused; we'd rebuild the UI against our APIs.
3. **Capacitor shell around the PWA** — fastest store-ready route, still a
   webview, with native push/notifications possible.

Recommendation: keep the PWA now (installable, offline shell, install prompt),
watch the canary (`schedule-df99a8a8-…`), and choose Capacitor if a store
presence is needed before Astryx Native stabilises.


## Update: all 30 locales enabled
- All 30 Astryx catalogs are copied into `web/portal/src/locales` and loaded
  dynamically per locale.
- The header and login page have a language dropdown (native names).
- Nav/tab and login labels are translated for all 30 via a cached/machine
  translation file `src/i18n/strings.json` (generated with Cloudflare Workers AI;
  review before selling as fully localised).
- Product page copy beyond the nav/login labels is still English; translating the
  full portal copy is the remaining content task.


## Final localisation state — 2026-11-11
- All 30 locales enabled and loaded dynamically.
- Full portal copy (133 extracted strings + 24 nav/login strings) is translated
  for every locale through a runtime text layer; dynamic/interpolated values
  (names, dates, amounts) are left alone.
- **Human review:** English (source) and Afrikaans (owner review file
  `QA/verification/AFRIKAANS_REVIEW.csv`). The other 28 locales are
  machine-translated and must be reviewed before being sold as fully localised.
- Verified: French login renders the full copy in French.


## Afrikaans review applied — 2026-11-11
- Owner-supplied corrections applied to all 24 nav/login and 133 UI strings.
- Three entries were adjusted from the supplied sheet because they looked like
  typos: "Review and sign off" -> "Hersien en teken af" (not "Herfris"),
  "Refresh" -> "Verfris" (not "erfris"); "Tenants" was kept as "Huurders"
  (owner's wording, though "Tenante"/"Kliënte" may read better).
- Only English and Afrikaans are exposed; the other 28 locales remain hidden
  until reviewed.


## All locales exposed with feedback note — 2026-11-11
- All 30 locales are selectable again. English and Afrikaans are reviewed;
  the other 28 are labelled in-product: automated translation, not reviewed by
  a native speaker, with a mailto feedback link.
- Verified in French: full French copy plus the feedback note.
