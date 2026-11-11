# Astryx audit — what we use, what is left

Checked 2026-11-11 against the installed `@astryxdesign/*` packages and the
174-component index.

## Used
- **@astryxdesign/core** — Button, Card, Heading, TextInput, TextArea, FileInput,
  Theme, defineTheme; CSS reset + astryx.css.
- **@astryxdesign/theme-neutral** — base theme, extended per tenant with
  `defineTheme` (accent + on-accent tokens).
- **@astryxdesign/cli** — `init` (AGENTS.md/GEMINI.md), `component`, `template`,
  `docs`.
- **Page templates** — the Home dashboard follows the analytics-dashboard
  template (tiles → charts → table); login and forms follow the basic templates.
- **Charts** — the Astryx dashboard template itself uses **recharts**, so the
  Reports/Home charts use recharts. `@astryxdesign/charts` is still
  `0.0.0-bootstrap.0`, not installable.

## Available but not adopted (with reason)
- **@astryxdesign/richtext 0.7.13** — real package; a rich-text editor could
  replace the plain social/email composer later. Not adopted yet because the
  backend stores plain text and the social APIs expect text; adding HTML would
  need sanitising.
- **@astryxdesign/vega** — `0.0.0-bootstrap.0`, placeholder.
- **@astryxdesign/lab** — `0.0.0-bootstrap.0`, placeholder.
- **@astryxdesign/native** — placeholder (“Do not install”); PWA is the interim.
  Weekly watch task `schedule-df99a8a8-0abe-4b82-a9d9-e9cbf8a06c8e`.
- **@astryxdesign/build** — only needed for StyleX source compilation; we use the
  prebuilt CSS.

## Component candidates for future screens
Table, Tabs, Toast, Dialog, ProgressBar, AppShell/SideNav, DatePicker, Badge.
They are not required for the current screens but are the next step for a
denser CRM/quotes UI.


## Re-audit after bundle split — 2026-11-11
- Used now: Button, Card, Heading, TextInput, TextArea, FileInput, Badge,
  ProgressBar, Banner, Theme/defineTheme, i18n provider, CLI, dashboard
  template, recharts (per Astryx's own template).
- Bundle split: dashboard (recharts) is lazy-loaded into `Home` (~363 KB);
  locale catalogs and per-locale nav/copy strings are dynamic; the main entry
  fell from ~995 KB to ~571 KB, with the 3D viewer in its own ~919 KB lazy chunk.
- Not adopted yet:
  - **Table** — best next addition for CRM/quotes/social lists (density and
    column layout); current cards are deliberate but table would scale better.
  - **Dialog** — use for owner sign-off and destructive actions instead of
    immediate buttons.
  - **Toast** — transient success/error messages; currently inline status text.
  - **Tabs / AppShell / SideNav** — cleaner navigation when the portal grows past
    the current 10 tabs.
  - **DatePicker** — better scheduling than a plain text field.
  - **Richtext (`@astryxdesign/richtext` 0.7.13)** — real package, but the backend
    and social providers store plain text; adopt only with HTML sanitising.
  - **charts / vega / lab** — bootstrap placeholders; do not use.
  - **native** — canary Apple-only; PWA remains the mobile option.


## Components and lazy loading — 2026-11-11
- Added **Table** for CRM enquiries and quotations, **Dialog** for owner sign-off,
  **Badge** statuses, **ProgressBar** media quotas, **Banner** translation note,
  and a **light/dark/system** toggle using `Theme mode`.
- Lazy loading: `Home` (recharts) is a separate 363 KB chunk; locale catalogs and
  per-locale nav/copy strings are dynamic. Main entry is ~589 KB, 3D viewer
  ~919 KB lazy. Next route-level split: Media, Designs, Social.
- Still not adopted: Tabs/AppShell/SideNav (nav is still a wrapped button bar),
  Toast (inline status remains), DatePicker (text schedule field), Richtext
  (plain-text backend/social APIs).


## Tabs, DatePicker and route-level lazy — 2026-11-11
- Header navigation uses Astryx **TabList/Tab**; schedule field uses
  **DateTimeInput**.
- Designs is now a lazy route chunk (`Designs`), like the dashboard; o3dv and
  locale/translation chunks remain lazy.
- Main entry is still large (~1.1 MB raw) because Table, Dialog, TabList and
  DateTimeInput are imported by the main shell. Next route-level split: CRM,
  Quotes, Media, Social (each pulls heavy components) — extract them to files
  and `React.lazy`; the current main entry is the honest remaining cost.
- Still not adopted: Toast provider, AppShell/SideNav shell, Richtext
  (plain-text backend), full side-nav.


## Final route split — 2026-11-11
- Extracted lazy chunks: `Home` (dashboard/recharts), `CrmQuotes`, `Engage`
  (Social + Media), `Designs`, plus the 3D viewer and per-locale catalogs.
- Main entry is now ~382 KB raw (~119 KB gzip); Home ~363 KB raw, CrmQuotes
  ~155 KB, Engage ~250 KB, 3D viewer ~919 KB, all lazy.
- Header uses Astryx TabList/Tab; social schedule uses DateTimeInput.
- Remaining: Toast (no provider export), AppShell/SideNav, Richtext (plain-text
  data contract).
