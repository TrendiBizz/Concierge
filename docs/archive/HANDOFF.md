# HANDOFF — Trendi Concierge

**Read first:** `AGENTS.md` in this repo (the working agreement — enforced by tooling, and it now
includes the website's technical SEO contract), then the QA record matching the area you touch.
Records from 2026-11-15: `SYSTEM_AUDIT_2026-11-15.md` (audit), `SEO_PASS_2026-11-15.md` (content),
`SEO_GROWTH_2026-11-15.md` (growth implementation), `EMAIL_ENGAGEMENT_2026-11-15.md`,
`CENTRAL_REPO_2026-11-15.md`.
Records from 2026-11-16: `GEO_DAILY_2026-11-16.md`, and — read these before trusting any tool —
`DEPLOY_GATE_MISDIAGNOSIS_2026-11-16.md` (why `verify-deploy` was red and why no publish was
needed), `HARNESS_GIT_ENV_2026-11-16.md` (why git fails in the agent shell), `TEST_ENV_2026-11-16.md`
(the command that actually runs the suite). Tamper watch / M4: `TAMPER_WATCH_2026-11-17.md`.


## Where the rest went

Full 2026-11-19 text (sections 1-3: project/repo, what the sessions did, the outstanding worklist) is
archived verbatim in `docs/archive/HANDOFF_FULL_2026-11-19.md`. Read the part you need, not the file.
Archive line numbers for the worklist subsections:

- L226: Hermes master on the Mac — owns the Trendi work (live 2026-11-17)
- L304: TrendiPen review lane — tracked privately
- L309: Hermes on the VPS (customer planner) — deployed, still not triggered
- L351: Operator only (cannot be fixed from this repo)
- L395: Security / hygiene still open
- L409: Unverified product surface (unchanged from the archive)
- L419: SEO growth — what the outside audit asked for and what is left
- L452: Quotations (from the 2026-11-16 rebuild)
- L479: Repository hygiene

## 4. Next action

**Nothing is blocked on a deploy.** `verify-deploy.sh` prints `OK: repo and box agree`; the
last code commit is `edc5dd1` (the `hermes/` package is Mac-only, not part of the VPS
comparison), and the handoff commits after it are docs-only.
The Docker→Podman move is done and reboot-tested; Twenty is retired; the Studio pipeline board is
live; the Hermes master is installed on the Mac. Do not run `deploy-site.sh` expecting to fix
drift — check `verify-deploy.sh` first.

**Next, in this order:**

0. **Walk the new pipeline board signed in** (item 12): Studio → Sales → Pipeline, drag one deal
   between two stages, add one offline opportunity, and confirm the dashboard/Reports numbers agree.
   The routes are live and tested; nobody has clicked it signed in yet.
1. **Quotations:** item 34a — write, approve, send and accept one real quote, because the new
   system has never carried real data. Everything it does is covered by tests, but tests are not
   a customer.
2. **Hermes master, first scheduled morning** (M1–M3): open `http://127.0.0.1:9120`
   (user `jo`, password in `concierge-stack/hermes/hermes.env`) and check the Cron page;
   on 2026-11-18 check the 07:00 social drafts, 07:30 deep dive, 07:40 monitor and 08:00
   master brief in `~/.workwatch/reports/hermes/`; pause the 11 Grok cloud copies (M1) so
   they cannot double-run; and confirm the `sitemap.xml`/`llms.txt` change the first
   manual monitor flagged (M3).
3. **Security review console:** open `http://127.0.0.1:9130`, choose
   **Trendi (self-owned)**, tick the authorization and run the full review. Capture the
   findings and refresh the timestamped report. Keep other tool missions in their native
   console. Set the authorization template, legal review, insurance and prices before
   selling. The detailed open list is in the private operator notes.
4. **VPS customer Hermes, first real plan** (H1): choose the trigger. If it is the inbound-email
   hook, keep the tenant in `shadow`, send one real enquiry to a tenant that has a case, and read
   the plan before letting anything execute. Pin the customer image first (H2), and extend source
   parity before the next gateway rebuild (H3).
5. **Cloudflare `/products.js`** — the tax-inclusive buy links shipped in `912452f`; purge the cached
   file if it still serves the old links (the only remaining follow-up from that item).
6. Verify `trendibizz.com` in Google Search Console (the DNS TXT already proves ownership — likely
   just submit the sitemap) and Bing Webmaster (no Bing verification exists), then submit
   `https://trendibizz.com/sitemap.xml` (item 7). Bing feeds ChatGPT search.
7. Rotate the VPS root SSH key, the live Stripe secret and the Stripe webhook secret (item 3).

Everything else in §3 is unchanged and uncancelled: the phone/SMS/email round trips (items 5,
16–18), the security/hygiene list (10–15), and the SEO content list (21–27) all still stand.

The GEO check is green on the technical side and empty on the commercial side: trendibizz.com is in
Bing's index (`site:` at position 10) but absent for all five target prompts. The cheapest next
content move is a dedicated `/ai-receptionist-for-small-business` page — the only one of the five
with no page behind it (item 25 covers the rest of the content list).

Before any future session ends, run `KEY=./Concierge ./scripts/vps/verify-deploy.sh`. If it is not
`OK: repo and box agree`, the session is not finished. Remember the `env -u GIT_CONFIG_COUNT`
prefix until the harness restarts (item 32).

**2026-11-18 social drafts.** Facebook + Instagram drafts adapted from the LinkedIn draft
`~/.workwatch/reports/trendi_content/linkedin/2026-11-10.md` are in
`QA/verification/SOCIAL_FB_IG_DRAFTS_2026-11-18.md`. Unverified that this is the text that was posted
to LinkedIn. Nothing posted to Facebook/Instagram; Instagram needs a 1080x1080 image (not made).
