# Builders page knowledge re-ingest — 2026-11-25

**Cause:** the CAD purge (`purge-cad-data.sh`) deleted 12 stale chunks of https://trendibizz.com/ai-office-builders
on trendi-support and trendi-oauth-staging, so the assistant had no knowledge of that page.

**Fix:** new `scripts/vps/recrawl-tenants.sh` (dry run by default) calls the admin crawl endpoint
(`ingest.ingest_site`, replaces crawled chunks, keeps `manual:` chunks) for both tenants, max 80 pages.

**Proof (box DB, after crawl):**
| tenant | chunks / urls | builders-page chunks | match ifc/dwg/design upload | embedding dim |
|---|---|---|---|---|
| trendi-support | 322 / 43 -> 353 / 45 | 0 -> 5 | 0 | 384 |
| trendi-oauth-staging | 322 / 43 -> 353 / 45 | 0 -> 5 | 0 | 384 |

Run: `KEY=./Concierge ./scripts/vps/recrawl-tenants.sh --apply trendi-support trendi-oauth-staging`.
No code under test changed (ops script only); crawler/ingest paths covered by existing suite.
