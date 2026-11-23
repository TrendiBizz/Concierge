# /api/robots restored (2026-11-24)

**Cause.** `/tools/robots-ai-check` fetches `GET /api/robots?url=<host>`. That route lived in the Cloudflare-era
`_worker.js` (loaded from the box by `scripts/vps/website.mjs`, not tracked in this repo). The Concierge cutover
removed the worker, so the path fell through to the static site's 404 (`baselines/CHANGES.md`, worker_scripts row).

**Fix.** `api/app/robots_fetch.py` + `GET /api/robots` in `api/app/routers/public.py` (FastAPI), and a `@robots`
route in `scripts/vps/Caddyfile` (same pattern as `/api/enquiry`). SSRF-safe: https/443 only, every hop resolved and
pinned to a public IP, <=5 redirects, 8 s timeout, 512 KiB cap, 20 requests/min/IP. No page change.

**Proof.** `api/tests/test_robots_api.py` (51 tests); full suite 1819 passed, 42 skipped; `seo-gate.sh` PASS.
Mutation check: before the scheme guard in `clean_host`, the `ftp://` case failed; with it, it passes.
Not yet verified on the live box (deploy is a separate step).
