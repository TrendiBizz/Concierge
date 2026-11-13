# Brand from the website — measured 2026-11-13 (session 20)

Answers the operator's "find a better method than svg" and records what the reader
actually does. Everything below was measured, not assumed; the throwaway container
runs are reproducible with the commands at the end.

## The short answer

Do not fall back to a touch icon. Render the SVG on our side with **resvg** (the
`resvg_py` wheel), and **install a font in the API image**. Both halves are required:

| Setup | Result on the real logo |
|---|---|
| resvg, no font in the image | purple tile draws, **the word "trendi" is missing** (0 ink in the wordmark area) |
| resvg + `fonts-liberation` | the whole logo renders, 512×137, correct lettering and spacing |

That second row is why the earlier plan ("bundle a font") was not enough on its own,
and why the first row is worse than a small touch icon: a logo that is missing its
wordmark looks deliberate rather than broken.

## Why a font is needed, and why substitution is not a guess

`resvg_py.svg_to_bytes` signature (0.5.0) accepts `width`, `height`, `font_family`,
`sans_serif_family`, `font_files`, `font_dirs`, … and `width` scales while keeping
the aspect ratio (180×48 → 512×137).

Measured behaviour: resvg resolves an **exact** family and does **not** fall back.

| SVG text | Family | Rendered |
|---|---|---|
| `trendi` | `Arial,sans-serif` | nothing (0 px) |
| `trendi` | `DejaVu Sans` | 2194 px |
| `trendi` | `Liberation Sans` | 1774 px |
| `HELLO` | no `font-family` | nothing (0 px) |

`fonts-liberation` ships fontconfig metric aliases for Arial, Helvetica, Times New
Roman and Courier New, which is why the Arial-named wordmark resolves once that
package is installed. `DejaVu Sans` renders too, but is not an Arial match.

## What the reader returns, and what it refuses to claim

`api/app/brand_from_site.py`, served by `GET /owner/onboarding/brand-suggestion`
(owner role, read-only — no tenant field, brand row or consent is written).

It returns name, logo as a `data:image/png` URI (capped at 290,000 raw bytes so the
`data:` string stays under the brand store's 400,000-character column), accent
colour, contact line, social accounts, platform + install hint, timezone and
dialling country, and a list of plain-language notes.

Two rules that came out of measuring:

1. **Text state is measured, not assumed.** The renderer compares the direct render
   against a render forced to use a family that cannot exist (that baseline holds
   every path but no lettering). It reports `""` (site font existed), `substituted`
   (redrawn in Liberation Sans — close, not identical) or `missing` (words could not
   be drawn, so the image is incomplete and the owner is told to upload their own).
   Without this, the reader would either warn about a perfect render or stay silent
   about a blank wordmark.
2. **The accent comes only from the logo actually kept**, and prefers a vivid
   mid-tone over a dark wordmark that covers more pixels. A brand whose only colour
   is dark still gets its own colour in the second pass; only a logo with no
   saturated colour falls back. The accent therefore follows the chosen image:
   trendibizz.com's JSON-LD logo is `logo-symbol.svg`, which is lime, so the
   default proposal is **#c6f432**; choosing the `logo-refresh.svg` wordmark instead
   yields **#7142d6**. Neither is `theme-color` `#f5f7fb` (the page background) nor
   the near-black `#302044` lettering, and the review screen shows every image as a
   thumbnail so the customer picks the one they mean.

## The real logo, end to end

`https://trendibizz.com/brand/logo-refresh.svg` — 416 bytes, `<text font-family="Arial,sans-serif">trendi</text>`,
`#302044` lettering, `#7142d6` tile, no scripts or external references.

Result through the module with the font installed: `512×137`, 6043 bytes,
13,119 px of wordmark ink, accent `#7142d7`, no warning note. The three sibling
logos (`logo-symbol`, `favicon`, `mark-refresh`) are path-only and render exactly,
untouched. Verified again inside the running production container on 13 Nov
14:5x: all four candidates render (9,873 / 6,043 / 9,873 / 8,456 bytes); the
JSON-LD symbol is chosen by default and the wordmark is offered alongside it.

## Cost

`resvg_py==0.5.0` is pinned in `scripts/vps/api-requirements.lock` (the image builds
from that file, not `api/requirements.txt`). It resolves to a prebuilt
manylinux wheel for CPython 3.12 on both `x86_64` (the VPS) and `aarch64`.
`fonts-liberation` is installed in `scripts/vps/Dockerfile.api` — a few hundred KB,
no compiler, no system Cairo. `cairosvg` was rejected: it needs the native Cairo
library.

## Reproduce

```bash
# the SVG
curl -s -A "ConciergeBot/1.0 (indexing at the site owner's request)" \
  -o logo.svg https://trendibizz.com/brand/logo-refresh.svg

# render with the font the image ships
docker run --rm -v "$PWD:/out" -w /out python:3.12-slim sh -c '
  apt-get update -qq && apt-get install -y -qq fonts-liberation >/dev/null 2>&1
  pip install --quiet resvg_py==0.5.0 pillow
  python -c "import resvg_py; open(\"out.png\",\"wb\").write(resvg_py.svg_to_bytes(svg_string=open(\"logo.svg\").read(), width=512))"'
```

## Not done yet

The review screen that consumes this proposal (wizard steps 2–5 replaced by one
"Looks right" screen with a colour picker), the platform-aware install step with a
live site check, and the hosted chat link + QR code. The endpoint and its tests are
in place; nothing consumes it in `/studio` yet.
