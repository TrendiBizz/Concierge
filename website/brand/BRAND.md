# Trendi brand guide

One identity everywhere: the public website, the customer workspace (`/owner-ui`), onboarding, the admin console, the Studio app, the install page, browser tabs, home-screen icons and social share images. If a page needs a colour or logo that is not on this sheet, change this sheet first.

## Logo

| File | Use |
|---|---|
| `logo-refresh.svg` / `logo-horizontal.svg` | Default logo on light backgrounds (wordmark + arrow mark). Same artwork, two names. |
| `logo-horizontal-dark.svg` | Logo on dark backgrounds (white wordmark) |
| `mark-refresh.svg`, `favicon.svg`, `logo-symbol.svg` | The arrow mark alone: browser tab, app icon, avatars |
| `apple-touch-icon.png`, `icon-512.png`, `og-image.png` | Generated: `python3 scripts/brand/make_pwa_icons.py` (icons) and the share image from `logo-refresh.svg` |

The mark is a purple rounded tile with a white up-right arrow. The wordmark is lowercase **trendi**.

### Rules
- Never recolour, stretch, rotate, outline or add shadows to the logo.
- Minimum size: mark 16 px, horizontal logo 90 px wide.
- Do not draw a second logo. Pages that need the logo inline copy `logo-refresh.svg`; they do not redraw it.
- Customer workspaces may show a business's own logo or initials for that business. Trendi's own mark is the default.

## Colour

| Name | Hex | Use |
|---|---|---|
| Trendi Purple | `#7142D6` | Logo tile, primary buttons, active states, theme colour |
| Deep Purple | `#5830AE` | Button hover, pressed, emphasis |
| Link Purple | `#6540AA` | Text links |
| Ink | `#30243E` | Body text and headings |
| Muted | `#71657E` | Secondary text |
| Page | `#FCFBFF` | Page background |
| Tint | `#F2EDFC` | Panels, code blocks, table headers |
| Line | `#E8DFF1` | Borders and dividers (`#D8C8EB` for stronger lines) |
| Focus | `#7142D6` | Keyboard focus ring |
| Dark theme colour | `#30243E` | `theme-color` for dark mode |

Status colours stay semantic and are not brand colours: success `#247451`, warning `#895A17`, danger `#B83F50`.

## Type

- **Website:** Plus Jakarta Sans, self-hosted (`/fonts/plus-jakarta-sans-var.woff2`). App pages served from another origin use the system font stack.
- **Wordmark:** drawn in the SVG. Never retype it in a font.
- Headlines: bold, tight tracking. Body: regular, generous line height.

## Retired
The navy `#14213D` + lime `#C6F432` "t" logo and the Studio's lime `#C8F560` "C" tile are retired. Do not reintroduce them.
