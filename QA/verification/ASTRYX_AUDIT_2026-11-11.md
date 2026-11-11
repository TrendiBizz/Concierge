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
