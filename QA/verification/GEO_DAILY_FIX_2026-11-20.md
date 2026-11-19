# GEO daily fingerprint defect — 2026-11-20

**Status:** fixed, tested, deployed to the script (repo-only; no site change, no publish).

## Symptom

`scripts/seo/geo-daily.py` reported `changed since last run: 44` — every page in the
44-URL sitemap — on every run, and therefore POSTed all 44 URLs to IndexNow every morning.
The 2026-11-19 report showed 44 too; earlier reports show 39/43/19, and at least one report
in the archive carries a "Note on 'changed since last run: 43'" showing this was noticed
before but never root-caused.

The repeated full-site IndexNow ping is not cosmetic: it tells Bing "everything changed"
every day, which is noise the crawler has to discount, and it hides genuine edits.

## Root cause

Cloudflare stamps a **fresh CSP `nonce`** on the Web Analytics beacon it injects into every
response:

```
<script type="module" src="https://static.cloudflareinsights.com/beacon.min.js/..."
  integrity="sha512-..." nonce="RbodAT2XZmZUMRFIr2SWvA==" data-cf-beacon='...'></script>
```

The previous fix for Cloudflare noise (2026-11-15/16) only stripped script blocks whose text
matched `__CF$cv$params` / `cdn-cgi/challenge-platform`. The Insights beacon matches none of
those markers, so it survived into `fingerprint()`, and its nonce differs on every request →
a different SHA-256 for an unchanged page.

Proof of the mechanism — two fetches of `https://trendibizz.com/` on 2026-11-20 had identical
byte length (24571) and differed on exactly one line, the nonce:

    A: ... nonce="RbodAT2XZmZUMRFIr2SWvA==" ...
    B: ... nonce="drKEzrFJ4lWMZmKc+4KKtA==" ...
    diff lines total: 1

## Fix

`scripts/seo/geo-daily.py`:

1. `CF_MARKERS` extended with `static.cloudflareinsights.com` and `data-cf-beacon`, so the
   injected beacon block is dropped like the challenge scripts already were.
2. New `NONCE = re.compile(r'nonce="[^"]*"')`, applied in `fingerprint()` as
   `NONCE.sub('nonce=""', stable)` — a CSP nonce is per-response noise on any script, not just
   Cloudflare's, so it is normalised rather than only-pattern-matched.

## Tests

`scripts/seo/test_geo_daily.py` (new, no network):

- `test_rotating_cloudflare_nonce_does_not_change_fingerprint` — same page, two different
  nonces and ray IDs, must fingerprint identically.
- `test_real_content_change_is_still_detected` — a real H1 edit must still change the hash
  (guards against "fixing" the instability by making the fingerprint useless).

Mutation proof — reverting the fix (dropping the NONCE normalisation and the beacon marker)
turns the first test red, restoring it turns it green:

    2 passed                        # with fix
    1 failed, 1 passed              # fix reverted
    2 passed                        # fix restored

Operational proof — three consecutive runs against the live site:

    RUN 1 (re-baseline after the old fingerprints): changed 44, IndexNow HTTP 200 for 44
    RUN 2:                                         changed 0,  IndexNow: nothing changed
    RUN 3:                                         changed 0,  IndexNow: nothing changed

Run 1's single full-site ping was unavoidable: the stored state held fingerprints taken with
the buggy function, so the first corrected run had to re-baseline. Steady state is now 0.

## Note for tomorrow

If `2026-11-21` reports 44 again, the noise source is something other than the nonce — do not
re-baseline blindly; diff two raw fetches of one page (as above) before touching the state file.

## Recommendation from this run (unchanged by the fix)

All five target prompts are absent from Bing while `site:trendibizz.com` is present at
position 1. Coverage check against `website/`:

| Prompt | Dedicated page? |
| --- | --- |
| AI receptionist cost | `ai-office-cost.html` (19 mentions, in title + H1) |
| best AI receptionist | `best-ai-office.html` (20 mentions, in title + H1) |
| AI answering service vs human | `ai-answering-service-vs-human.html` |
| AI receptionist | `virtual-receptionist.html` (10 mentions; title says "Virtual receptionist") |
| **AI receptionist for small business** | **none** — max 6 scattered mentions, no page |

Weakest prompt is **"AI receptionist for small business"**: it is the only one of the five
with no page whose title/H1/intent matches it. Next action is a dedicated page, not more
edits to existing ones.
