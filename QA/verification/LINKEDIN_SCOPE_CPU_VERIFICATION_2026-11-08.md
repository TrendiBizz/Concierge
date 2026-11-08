# LinkedIn scope formatting and Mac.hub resource verification — 8 November 2026

Repository: TrendiBizz/Concierge; branch: integration/concierge-v1; starting commit: 80ff264. Times are NZDT.

## LinkedIn diagnosis and change

- Staging binary built at 16:27:42 and started at 16:28:07; commit 6d2a638 was recorded at 16:28:14. The final scope-validation error log write was 16:30:47, after that binary started. The two old failure records have no per-event timestamps or scope metadata. At least one failure followed the prior staging restart; the provider's returned scope string is unknown.
- Ordinary spaces, tabs, line breaks and leading/trailing whitespace already worked. A loopback HTTP regression running the real finish path reproduced the exact permission error with synthetic `scope: "openid,profile"`. Before the fix, `cargo test --locked -j 1 --lib linkedin_finish_scope_formatting_and_profile_verification -- --nocapture` failed with `LinkedIn did not grant the requested permissions`. No live credentials or codes were replayed.
- Scope responses now normalize commas and whitespace into a deduplicated space-delimited list before exact permission checks and consent storage. Renewal uses the same normalization. Outgoing authorization still requests exactly `openid profile`.
- Explicit incomplete scopes, near-match names, delimiter-only input and double-encoded input still fail. Missing/blank scope metadata still requires successful authenticated userinfo with a valid subject. No posting scope is inferred.
- The HTTP regression covers token parsing, bearer-authenticated profile lookup, encryption, tenant isolation, one-use state, failed profile lookup, missing identity, formatting and nonpublishing grants.
- Scope-validation failures log only a timestamp and boolean separator/permission metadata. Successful storage logs a timestamp. No raw provider values, identities, codes or credentials are logged.
- Limit: comma formatting is a reproduced implementation bug and leading explanation, not a capture of the live response. Previous logs cannot prove the real failure's cause. New safe diagnostics distinguish formatting from an incomplete grant.

Official references: [authorization code flow](https://learn.microsoft.com/en-us/linkedin/shared/authentication/authorization-code-flow) documents space-delimited token scopes; [token introspection](https://learn.microsoft.com/en-us/linkedin/shared/authentication/token-introspection) documents comma-delimited scopes; [OIDC](https://learn.microsoft.com/en-us/linkedin/consumer/integrations/self-serve/sign-in-with-linkedin-v2) documents basic scopes and userinfo. Separator normalization preserves exact permission checks.

## Verification and isolated staging

- All 55 Rust tests passed, including the HTTP regression; Clippy all targets with warnings denied passed. Formatting and diff checks passed.
- All 14 Python owner/social tests passed. Browser callback regression passed: lost opener reconnects to the signed-in owner tab; publishing remains disabled.
- Builds and checks used one job at reduced scheduling priority and cached dependencies. No Docker image rebuild.
- Corrected native binary started only in the dedicated OAuth Rust staging launch agent at 16:59:49.
- Rust staging health (4390), staging owner UI (8001), production API health (8000): HTTP 200.
- All 13 running Docker containers retained exactly the same start times across the staging restart, including CRM, production API, databases and Hermes.
- Authenticated readiness: LinkedIn, Facebook, Instagram, TikTok true. Global and LinkedIn publication flags remain disabled.
- SQLite quick_check: ok. Account counts remain Facebook=1, Instagram=1, TikTok=1, LinkedIn=0. No stored account was disconnected or modified by these checks.
- Real LinkedIn connection remains unverified. Computer Use refused access to the existing Google Chrome session because Chrome access was not approved. At verification time no new live authorization flow or developer setup had been requested or performed.
- Voice/Grok, CRM, recording, production configuration and other provider code were unchanged; no live call or recording was initiated. No production deployment or social publishing.

## Mac.hub CPU and memory

- At initial inspection (16:48:55), previous hot renderer PIDs 1951, 1190 and 1952 were already absent. Current ChatGPT parent PID 3158 started at 16:43:25, before this session's actions. This session did not restart ChatGPT. The exact earlier workload cannot be recovered from vanished processes.
- Renderer PID 3250 measured about 7% CPU; other renderers were near idle. The sustained 16:49:37 sample showed 71.8% total CPU idle. macOS recorded no thermal/performance warning. These readings do not establish a permanent renderer fix.
- Initial swap: 17,807 MiB. Docker VM footprint: about 8,210 MiB. Container CPU was low; Docker/VM and Google Drive were preserved.
- Idle LM Studio backend PID 87107 retained about 5.2 GiB resident memory, with PPID 1, 0% CPU and no established TCP connections. LM Studio was not running; CLI and REST inventories reported no loaded model. Normal `lms unload --all` returned no models to unload.
- The user explicitly approved unloading this model. Only its verified orphan backend received graceful SIGTERM. No GUI application, Docker VM/container, Google Drive or production Concierge service was terminated.
- Reported memory availability rose immediately from 17% to 56%. At 17:00:16 it was 34%; swap fell to 12,185 MiB (about 5.5 GiB less than initially); CPU idle was 62.25%; no swapouts occurred in the 3-second sample. About 1 MiB/s swapins remained. Pressure improved but had not disappeared.
- Remaining leaders were WindowServer, Google Drive, Spotlight, Chrome and Docker VM. Further app termination or Docker memory changes require separate authorization and dependency checks.

## Preserved files

Untracked QA/verification/office-shots/ and QA/verification/tiktok-review/ were untouched and excluded from commits. Private credentials and media were not printed, copied into chat or staged.

## Real LinkedIn connection confirmed — 17:10:28 NZDT

This result supersedes the earlier unverified-connection status above.

- The user completed LinkedIn's member verification and OAuth flow; the owner portal displayed `linkedin account connected. Posting remains disabled until separately approved.`
- Independent read-only SQLite verification found exactly one LinkedIn account, with encrypted credentials present, needs_reauth=false, one tenant, granted scopes `openid profile`, and no disconnected_at timestamp.
- The staging log confirms `linkedin_oauth_success phase=account_storage at=1794111028`, matching consent authorization time in the DB.
- Facebook, Instagram and TikTok each remain at one account. SQLite quick_check is ok.
- Global and LinkedIn publication flags remain disabled. Rust staging, staging portal and production API health all returned HTTP 200.
- Basic LinkedIn member account linking is now verified in staging. Company-Page authorization, publishing, production deployment and disconnect/reconnect certification were not performed. The working connection was preserved.
- No raw token, code, identity payload or provider scope response was exposed. Successful completion does not retrospectively prove the exact raw formatting of earlier failed responses.
