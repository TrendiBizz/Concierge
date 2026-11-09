# Trendi Concierge — new-session handoff, 8 November 2026

## Read this first

The website and CRM are already running on the DigitalOcean VPS. **The latest social publishing upgrade is uncommitted local work and has NOT been deployed.** Do not tell Jo everything is finished. Jo wants working software, live verification and accurate progress, not more promises.

This handoff was requested explicitly by Jo. The next session should continue the implementation and deployment, preserving existing customer data and connections. No subagents unless current instructions explicitly authorize them. Read `/Users/jo/.codex/RTK.md` and any applicable repository instructions first.

## Customer requirements and decisions

- Customer links their own social accounts, writes one post, uploads media once, reviews platform-specific adaptations, then approves/schedules them together.
- Support Facebook Pages, Instagram professional accounts, LinkedIn personal profiles AND company Pages, TikTok VIDEO, and Google Business Profile.
- Remove Mastodon and Bluesky from the offered customer experience and public website. Preserve historical records; do not delete accounts/data indiscriminately.
- Put as much new backend logic as practical in Rust. Python remains the existing authentication/transport bridge.
- Website headline: **Your office, handled.** Explain receptionist, sales follow-up, scheduling and office admin, plus the built-in CRM capturing calls, emails, texts and website chats as enquiries and responding through configured channels.
- Concierge pricing requested: $400/month; annual base $4,800 less 15% = **$4,080/year**. Verify actual live pricing and checkout match; do not assume this handoff verifies billing.
- Test contact: admin@trendibizz.com; +64 27 881 7368. These are not evidence that phone/SMS providers are activated.
- Google consent: Jo explicitly approved **kiwi18@gmail.com** as temporary support email. Jo subsequently requested a tracked reminder to replace it with **support@trendibizz.com**. The unchecked item is saved in `QA/verification/SOCIAL_CHANNEL_ACTIVATION_MATRIX_2026-11-08.md`. Configure an eligible support Google Group/address, update consent branding, and verify the displayed address before closing it.
- User authorized migration/deployment and adding this Mac's Concierge public SSH key. Do not ask for those permissions again. Follow any actual browser security confirmation requirements at the action that triggers them, and explain the source if asking.
- Do not send real social posts without explicit approved content and destination. Never silently replay uncertain or old publishing jobs.

## Workspaces and preservation

- Product: `/Users/jo/work-staging/concierge-integration`, branch `integration/concierge-v1`, HEAD `dfe44b7`.
- Website: `/Users/jo/work-staging/trendi-site-web`, branch `concierge-site`, HEAD `0a4dc75`.
- Product has many modified/new Rust, API, owner UI and VPS files. They are the unfinished upgrade; preserve them. Run `git status --short` before editing.
- Preserve unrelated untracked product `QA/verification/office-shots/`, `QA/verification/tiktok-review/`, and website `scripts/security/.cache/`.
- SSH key: product root `Concierge`; public key `Concierge.pub`. Excluded from Git. Never print or commit private keys, tokens, credentials, database dumps or private configuration.

## Live VPS — already migrated and verified

- Host **152.42.239.240**, Ubuntu 24.04 amd64, 8 GB RAM, 2 CPUs, 160 GB disk, 2 GB swap.
- SSH: `ssh -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -i /Users/jo/work-staging/concierge-integration/Concierge root@152.42.239.240`.
- Release root `/opt/trendi/releases/20261108-vps/{product,website}`; private settings `/opt/trendi/shared` (directory 700, files 600).
- Compose command prefix: `docker compose --env-file /opt/trendi/shared/compose.env -f /opt/trendi/releases/20261108-vps/product/scripts/vps/compose.yml --profile crm --profile public`.
- Last checked this handoff: all 11 `trendi-*` containers running; API, CRM and databases report healthy.
- Public website: https://trendibizz.com/concierge
- Owner portal: https://concierge.trendibizz.com/owner-ui
- Widget API: https://chat.trendibizz.com
- CRM: https://crm.trendibizz.com
- Public response release header `X-Trendi-Release: 20261108-vps`.
- Canonical tenant slug **trendi-oauth-staging**, display name Trendi Concierge, owner admin@trendibizz.com. Existing users/passwords/sessions and four connected accounts preserved. Old prototype tenant `concierge` is archived; do not use its public key.
- API loopback 8000; gateway loopback 8080. Rust sidecar shares API network namespace and listens 127.0.0.1:4390. Social SQLite/encrypted vault volume is mounted at `/data`, UID 10002.
- Live images before new upgrade: API `trendi-concierge-api:vps` ID prefix `0e360d50506ca8e12`; social `trendi-concierge-social:vps` prefix `817dbc09c557498f6`.
- Website Node adapter loads the original worker from mounted website tree; static files can update without rebuilding website image. See `scripts/vps/website.mjs`.
- VPS Cloudflare tunnels: main `c25e268f-ce3b-4ca6-bb0a-85d538bee4f3`, owner `56b212ec-c55c-44e7-bbc2-40d76b44aaa7`. Mac production services/tunnels were stopped to prevent two writers. Do not restart them alongside the VPS.
- Existing SMTP via Brevo STARTTLS 2525 tested, signed inbound test created a CRM enquiry, approved reply delivered and receipt verified. Automatic inbound mailbox forwarding still pending; phone/SMS provider setup pending.
- Cloudflare Bot Fight Mode and script monitoring enabled; managed WAF, browser integrity check, DDoS, HTTPS/HSTS, TLS 1.3, minimum TLS 1.2 active. Search/AI crawlers allowed. Bot Preference Sync enabled. Earlier checks: 21 SEO checks and 12 origin/security checks passed.
- Encrypted R2/restic backups configured privately. Daily backup 03:15 Auckland, monthly restore test on day 1 at 03:45. Previous genuine restore verified 23 Concierge/121 Twenty tables plus social SQLite/settings/uploads. **NEW social `/data/media` needs inclusion and restore verification.**
- Private migration material: product `.private/vps-migration-20261108`; additional artifacts `/Users/jo/work-staging/trendi-vps-migration/`.
- Operational reference: `scripts/vps/README.md`, `QA/verification/VPS_RELEASE_2026-11-08.md`.

## Latest local implementation — written, not deployed

Rust sources under `concierge-stack/social-service/src/`:

- `composer.rs`: shared brief to separately editable account variants, limits, hashtags, Unicode-aware shortening, tenant/account ownership checks, media requirements and explicit warnings/errors. Offers five platforms plus LinkedIn organization destination.
- `adaptation.rs`: one batch xAI/Grok request for platform-specific text using source facts only; rejects invalid mappings, invented numeric claims, length/guardrail failures. Falls back to deterministic previews with a warning. Needs private `SOCIAL_ADAPT_API_KEY` and `SOCIAL_ADAPT_MODEL` configuration from existing operator settings; never expose the key.
- `tiktok_publish.rs`: creator-info lookup, current privacy options, explicit consent, interaction restrictions, duration/caption validation, owned file upload or verified URL pull, and asynchronous status receipts. TikTok private/audited app restrictions still apply.
- `linkedin_pages.rs`: approved administrator/content administrator organization discovery with actual required scopes and encrypted organization account storage.
- `linkedin_media.rs`: official image/video initialization, native uploads, range/ETag validation, finalization and processing checks.
- `media.rs`: tenant-owned bounded uploads, ffprobe/ffmpeg normalization, opaque IDs, video poster for Google Business Profile, encrypted expiring download capability URLs.
- `model.rs`, `connector.rs`, `store.rs`, `scheduler.rs`: post options, local asset references, Processing status, exact revision/media/options approval, provider receipt handling and scope checks.
- `linkedin.rs`, `tiktok.rs`, `token_refresh.rs`, publishing adapters and `api.rs` updated for new flows.

Python/owner UI:

- `api/app/social_bridge.py`, `api/app/main.py`: owner-authenticated compose/upload endpoints; options transported to Rust; public capability-based provider media download proxy.
- `api/static/owner.html`: destination checkboxes, one file upload, per-platform editable previews, TikTok creator privacy/consent controls, and approve/schedule-all UI. Existing individual approval controls retained. Needs syntax and browser integration verification.

Ops:

- `scripts/vps/Dockerfile.social` installs ffmpeg; `compose.yml` raises social memory allowance to 512 MB; `Caddyfile` allows `/api/v1/social-media/*` on owner host.
- New media env: `SOCIAL_MEDIA_DIR=/data/media`, `SOCIAL_PUBLIC_MEDIA_BASE=https://concierge.trendibizz.com/api/v1/social-media`.
- Publishing remains disabled. Do not turn it on as a shortcut to provider approval/testing.

## Current verification and known code gaps

Latest `/tmp/trendi-social-test.log` reports **66 Rust tests passed**, zero failures (37 + 5 + 11 + 4 + 6 + 3). This does not prove real platform publishing, owner browser flow, media normalization or deployment readiness.

Resolve before release:

1. Facebook video adapter may return `pending:facebook:*`, but scheduler/store currently recognize only `pending:tiktok:*`. Generalize pending processing/reconciliation before marking video published.
2. Scheduler asset loading/signing errors currently can escape with `?` after claiming a job. Handle per-post failure without leaving jobs in Publishing or aborting unrelated work.
3. TikTok registration in `main.rs` still requires `SOCIAL_TIKTOK_VERIFIED_MEDIA_ORIGINS` via `env::var(...) ?`; native file upload should work without that optional setting.
4. Exercise ffmpeg/ffprobe against real image/video samples. Add bounded process execution time; ensure stored dimensions match the normalized output. Validate actual Instagram JPEG/aspect/video requirements and derivatives. Do not claim automatic media adaptation is complete prematurely.
5. Confirm TikTok creator consent, music/branded-content requirements and server-measured duration cannot be bypassed by client options. Verify LinkedIn upload/organization permissions against official docs.
6. Remove remaining runtime offering of Mastodon and legacy accounts from destination selection; retain historical data. Update hardcoded owner status/provider readiness (`live_publishing: false` currently) to truthful actual capability state.
7. Check extracted owner inline JavaScript syntax and perform browser tests for upload, preview edits, account isolation, approval revision binding, scheduling, retry/partial-save behavior and logout state reset.
8. Ensure public media URLs/limits/expiration work through Caddy and are not protected by owner login; enforce tenant ownership and no arbitrary remote upload destinations.
9. Include new social media storage in encrypted backups and exercise restore.

## Website outstanding

Verified live at handoff: headline is “Your office, handled.” **Mastodon and Bluesky are still present live.** No current upgrade edits have been applied to the website repo.

Update `site/concierge.html` and scoped `site/concierge-social.css` as needed; preserve shared styling. Genuine brand SVGs already exist under `site/brand/social-logos/`, documented by `docs/SOCIAL_BRAND_ASSETS.md`. Keep five supported platform logos and show LinkedIn company Pages, TikTok video, Google Business Profile and the one-composer/review workflow truthfully. Clearly distinguish implemented capability from pending provider approval/activation. Update `docs/CONCIERGE_FEATURE_COVERAGE.md`.

## External provider gates — not complete

- **Google Business Profile:** Google Cloud project `trendi-seo` did not yet have OAuth client/auth branding configured. Started branding setup, name Trendi Concierge, temporary support kiwi18@gmail.com approved. Latest browser action selected that address and clicked Next; re-read actual UI before continuing. Need external audience, contact details, consent setup, OAuth web client and Business Profile API entitlement/approval. Callback `https://concierge.trendibizz.com/owner/social/oauth/callback`. Private env names `SOCIAL_GOOGLE_CLIENT_ID`, `SOCIAL_GOOGLE_CLIENT_SECRET`, `SOCIAL_GOOGLE_CALLBACK`. Do not assume an OAuth client alone grants Business Profile API access.
- **LinkedIn:** existing app **266722540**, Trendi Concierge, public client ID `78bllssrxg4wgp`. Company association currently **Not verified**. Inspect Products tab and verify/request Community Management access. Organization discovery/posting needs actual grants `r_organization_admin` and `w_organization_social`, and customer reconsent. Member login alone is insufficient.
- **TikTok:** existing Login Kit account linking is not proof of approved Content Posting API. Verify app access, `video.publish`, audit/private visibility restrictions and end-to-end upload/status flow. Do not publish a real test without approved content/account.
- **Meta:** existing Facebook account preserved; wider customer access needs approved permissions/review. Instagram professional account linking and actual publishing still need verification.

Use official current provider documentation for unstable API requirements. Key references: TikTok Content Posting / creator-info docs; Microsoft LinkedIn Community Management organization ACL, Posts and media APIs; Google Business Profile basic setup, prerequisites and localPosts APIs.

## Browser resumption

Prior CUA bindings may persist: Chrome `providerBrowser`, Google tab `googleSetup`, LinkedIn tab `linkedinSetup`. First call after compaction must be `await cua.rewriteDocumentation()` before further CUA work. Inspect fresh UI snapshots; never assume an unobserved form advanced. Last Google page was `https://console.cloud.google.com/auth/overview/create?project=trendi-seo`; LinkedIn app Products tab.

Any actual sensitive access/credential creation or agreement confirmation required by the browser tool must be handled at that step with a concrete reviewable result. Jo's approved support-email choice is not blanket agreement to unrelated legal terms. If CUA work concludes, use its required completion_summary call before moving on.

## Recommended continuation order

1. Inspect working tree and this handoff; preserve all existing work/data.
2. Fix the code gaps above, run meaningful Rust/API/frontend/media checks, and update public site offerings/copy.
3. Finish provider configuration that can be completed; document precise external approval gates rather than claiming activation.
4. Build native amd64 candidate images on the VPS (Mac images may be ARM). Use one build job, copied databases/social vault, publishing/outbox disabled, isolated ports such as API 8002/social 4391. Never run candidate jobs against live data or send externally by accident.
5. Test owner upload → Rust adaptation → editable previews → exact approval → scheduling and tenant isolation on candidate. Verify signed media retrieval and provider status semantics.
6. Take fresh backup, deploy tested images/UI/site, run health/smoke/security checks and media restore verification. Preserve original customer accounts and encrypted tokens.
7. Commit/push only intended files, without unrelated screenshots/caches/private material. Record actual release identifiers and remaining provider gates.
8. Give Jo working live URLs and concise evidence. Explicitly distinguish live functionality, locally tested code and external activation still pending.
