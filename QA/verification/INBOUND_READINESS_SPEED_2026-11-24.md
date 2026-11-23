# /admin/inbound-readiness speed (2026-11-24)

- Cause: `check_all` inspected tenants one after another, and each inspection asked Cloudflare for the
  same zone rule list plus the sidecar. 8 tenants -> 7.4-8.8 s, against a 10 s health-check timeout.
- Fix: Cloudflare rules and sidecar are probed once per call; tenants run concurrently with a 12 s
  per-tenant bound (a stuck one is reported as an `inspection` block). Response shape unchanged.
  No cache (not needed; avoids stale readiness).
- Proof: tests/test_inbound_readiness.py (concurrency bound, single probe, stuck tenant, rule parity).
  Mutation: sequential loop makes the concurrency test fail. Full suite 1764 passed; seo-gate PASS.
