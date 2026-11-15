# The "red deploy gate" was a missing merge, not a pending publish — 2026-11-16

## The claim this corrects

`HANDOFF.md` §3 item 30 (as left by the previous session) said the box carried hand edits to
`tools/missed-call-cost-calculator.html`/`.js` from 2026-11-15 that had never come back into the
repo, that those edits carried NZ$ labels plus a GST FAQ contradicting the operator's "one USD
price, no GST wording" decision, and that the fix was an approved `deploy-site.sh` publish. §4 made
that publish the first action of the next session.

Both halves of that story were wrong, and the direction was inverted.

## What was actually true

Measured against the live box (`root@152.42.239.240`):

| Fact | Value |
|---|---|
| box `website/site/.deploy-manifest.json` commit | `08cbdda` |
| manifest sha256, `tools/missed-call-cost-calculator.html` | `8263bd84…d46` |
| sha256 of the live file | `8263bd84…d46` |
| sha256 of that file at `08cbdda` in the repo | `8263bd84…d46` |
| same three for the `.js` | `95a07ff7…aa0` |

The box matches its own manifest exactly, and the manifest matches the repo at `08cbdda`. **The box
was never hand-edited.** The live files are the *USD, no-GST, no-NZ$* versions.

The repo looked different because **local `main` had never merged `origin/main`**. The two lines
diverge at `7f6e223`:

- `origin/main` (deployed, `08cbdda`): `21cda5b` "site: remove FREE, GST and NZ$ from the
  missed-call calculator", `a50225f`, `0b43764`, `1f64e46`, `08cbdda`.
- local `main` (`a8b6d8b`): `b6f2eca` (geo-daily fingerprint), `2b83e8c` (a locally re-done
  googlebot `noindex` guard), `a8b6d8b` (handoff) — none of the five commits above.

So local `main` still carried the pre-`21cda5b` calculator text: `NZ$` labels, a `GST and tax`
bullet, a "before or after GST?" FAQ and `priceCurrency: NZD`. Publishing that, as the handoff
proposed, would have **put the GST wording live** — the exact thing the operator decision forbids.

## Fix

Merge `origin/main` into local `main`, then resolve the overlap honestly:

- `scripts/seo/site_seo.py`: both sides had fixed the same defect. Kept origin's implementation
  (reads `robots|googlebot|bingbot`, flags disagreement with the generic tag) and deleted the
  duplicated local loop plus the now-dead `robots` variable the auto-merge left behind.
- `api/tests/test_site_seo.py`: kept origin's disagreement test, kept the local "allowed where
  `noindex` is the policy" test, and added a `bingbot` case (origin's guard covers it, nothing
  tested it).
- Calculator files, `website/_headers`, `llms.txt`, `test_missed_call_calculator.py`: took origin
  (clean, no conflicts).

## Proof

- `scripts/seo/site_seo.py check` → `OK: 45 pages — canonical, robots, h1, snippet, dates, links,
  sitemap and IndexNow key all agree`.
- Mutation: changed the merged regex back to `name="(robots)"` → the two crawler-specific tests
  failed; restored → 44 passed.
- `scripts/vps/verify-deploy.sh` → **`OK: repo and box agree`** (api/app 107, scripts/vps 38,
  website/site 61). The gate is green with **no publish performed and none needed**.
- Full suite: 1420 passed (see `TEST_ENV_2026-11-16.md` for the command that actually runs).

## What this changes in the worklist

Item 30 is closed by a merge, not a deploy. Item 31 remains true: the `googlebot`-only `noindex`
was invisible to the gate and is now caught — the merged guard is the stronger of the two fixes.
The list of operator-only decisions (§3 items 1–9) is untouched by any of this.
