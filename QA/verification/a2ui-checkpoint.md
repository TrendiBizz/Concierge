# A2UI task checkpoint
Objective: implement five structured chat moments in Concierge and every website HTML page; E2E every page desktop/mobile; PR, no deploy.
Canonical repo TrendiBizz/Concierge contains BOTH surfaces. Stale Trendiisales/trendi-site must not be edited per AGENTS.md.
Workspace: /Users/jo/jo-jobs/a2ui/implementation; branch feat/a2ui-sitewide-20261124; initial HEAD 02961d4. Original clone untouched.
Read brief including ADDED, brain offer/honesty/working habits, repo AGENTS and working order. Explicit brief price USD $250/month for Concierge; SEO offer remains unchanged.
Upstream cloned /Users/jo/jo-jobs/a2ui/upstream; Apache-2.0; official @a2ui/lit 0.16.0 supports protocol v0.8. Spec and renderer read. VPS directory inventory read only via ssh concierge-vps; no changes.
Modern Web Guidance forms read: semantic controls, labels, native constraints, submit result announcements, CSP-safe listeners.
Next: implement backend protocol envelopes/actions, official Lit adapter and widget stream integration; inventory and fix every HTML page; run local tests/screenshots, gate, full suite then PR. report.md must be written last, plus Downloads copy.

Milestone: backend v0.8 envelopes + authenticated/rate-limited action route implemented; official Lit adapter lazy loaded (~56 KB gzip), with semantic input/text templates and CSP-safe surface wrapper. Caddy source routes added; not applied live. Widget supports SSE and text fallback. All 46 HTML pages inventoried; four missing widget tags fixed. Browser runner uses real public handlers with model/tenant/storage stand-ins, blocks all external requests. Original API suite 1948 passed, 42 skipped. Browser sweep active in foreground runner (all five actions/page/viewport), evidence under ~/Reports/a2ui; no prod mutation.
Next: finish browser sweep and gate, add failure/fallback cases, formal schema checks and mutation check, re-run suite as needed, review diff, commit/push PR (no merge/deploy); update this checkpoint, then write report.md LAST and Downloads copy.

Milestone: 94 page/viewport cases and local SEO gate passed; official schemas passed; renderer-failure and save-retry checks passed; mutation check caught removed email validation. Final sweep is regenerating evidence after form-specific enquiry keys. Full API suite final run active. Upstream Zod audit advisory remains documented for release review. Next: final results, commit/pull --rebase/push PR, checkpoint, then report LAST.
