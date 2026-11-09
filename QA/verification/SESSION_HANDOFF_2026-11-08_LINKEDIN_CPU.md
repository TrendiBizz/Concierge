# Trendi Concierge session handoff — LinkedIn OAuth + Mac.hub CPU — 2026-11-08

## Scope and repository
- Authoritative repo: `TrendiBizz/Concierge` on `integration/concierge-v1`.
- Public `Trendiisales/trendi-site` is the existing website, NOT a replacement or separate Concierge backend.
- Prior pushed code commit: `6d2a638` (`Accept omitted LinkedIn OAuth scope only after userinfo verification`).
- This handoff is the only newly staged file in the current turn; no other tracked code changes were present.
- Preserve untracked `QA/verification/office-shots/` and `QA/verification/tiktok-review/`; they were not added or modified in this session.

## LinkedIn OAuth — unresolved, do not imply success
- LinkedIn Developer App credentials and callback are privately configured in `.private/oauth-staging/social.env`. Never print, commit or copy secrets into chat.
- Callback: `https://concierge.trendibizz.com/owner/social/oauth/callback`.
- Staging Rust service runs natively on Mac.hub at `127.0.0.1:4390`; owner staging API runs in Docker on `127.0.0.1:8001` and is exposed at `https://concierge.trendibizz.com/owner-ui` via a dedicated Cloudflare staging tunnel.
- Last prior real OAuth failure: Rust `linkedin_oauth_failure phase=scope_validation`; customer message `LinkedIn did not grant the requested permissions`. Earlier generic HTTP 400 errors were clarified through allowlisted safe error messages.
- `6d2a638` changes LinkedIn token handling: if LinkedIn omits the `scope` response field, only accept a valid authenticated `/v2/userinfo` lookup for basic OIDC connection; explicit incomplete scopes still fail. Never infer `w_member_social`, and social publishing stays disabled.
- A newer screenshot still displayed the previous scope error, but no confirmed successful new attempt after the last fix. Do not assume fresh execution from a screenshot alone. Check sanitized Rust staging logs and tenant account DB to correlate timestamps, then investigate without repeated user verification cycles.
- Direct SQLite evidence at handoff: exactly one connected Facebook account, one Instagram account, and one TikTok sandbox account; **zero LinkedIn**. DB integrity was OK in prior check. OAuth tokens are stored encrypted and tenant bound.
- Preserve LiveKit/Grok voice, recording, CRM, production services and existing connected channels. No production deployment or live publishing authorized.
- Past checks passed: Rust cargo tests and Clippy; browser lost-opener OAuth callback regression; Python owner integration 14 tests; isolated staging health HTTP 200. These are not proof of real LinkedIn OAuth certification.

## Mac.hub heat / CPU — urgent next-session priority
- Device: Mac.hub (macOS, 16 GiB RAM; 10 logical CPUs).
- At approximately 16:34 NZDT on 2026-11-08, load averages 6.92 / 6.94 / 6.95; swap used 16169.94 MiB out of 17408 MiB allocated.
- Highest sampled CPU processes:
  - PID 1951 ChatGPT/Codex renderer: 99.0%.
  - PID 1190 ChatGPT/Codex renderer: 90.2%.
  - PID 1952 ChatGPT/Codex renderer: 89.8%.
  - PID 54578 Apple Virtualization VM: 55.8%.
  - PID 72339 Google Drive: 42.3%.
  - PID 414 WindowServer: 38.9%.
- These are three *renderer subprocesses of one ChatGPT app*, not three separate installations. They are likely a major contributor to heat; exact renderer workload is not established.
- No active Rust/Cargo/browser-testing jobs from this task at the time of inspection. We did NOT kill, force quit or restart any customer application or production process.
- **NEXT PRIORITY:** Take a fresh low-overhead CPU/swap sample, inspect parent IDs and process activity for these three renderers, and advise or obtain approval before stopping an app. Avoid expensive builds and long repeated test runs while the Mac is hot. Do NOT stop Docker / VM or Google Drive automatically: Concierge and other user services may depend on them.

## Safe next steps
1. Check Mac temperature/performance and app renderer process trees using lightweight commands. Ask before terminating any app or service. User requested CPU diagnosis in the new session.
2. Check `git status`, remote branch state and verify this handoff push. Preserve unrelated untracked directories.
3. For LinkedIn, first confirm whether a genuinely new OAuth callback occurred after commit `6d2a638`; inspect *only sanitized* Rust logs (`linkedin_oauth_failure phase=...`) and SQLite network counts, no raw OAuth codes or tokens. Do not ask user to retry blindly.
4. If scope validation persists, determine what LinkedIn actually supplies in a privacy-preserving way and compare with approved OIDC product scopes; never bypass actual `/v2/userinfo` verification or posting permissions.
5. Only perform further code changes, tests, commits and pushes after managing Mac CPU pressure. Keep production deployment and live publishing off without explicit approval.

## Previous relevant commits
- `c05da20` — separate LinkedIn OIDC linking from publishing grant.
- `5bdc4aa` — callback survives OAuth popup opener separation.
- `3c3d78a` — safe linked provider errors in bridge.
- `cb32bbe` — privacy-safe LinkedIn failure-stage diagnostics.
- `6d2a638` — scope response omission handling.

## Verification of services in this session
- `http://127.0.0.1:4390/health` returned HTTP 200.
- `http://127.0.0.1:8001/owner-ui` returned HTTP 200.
- Staging DB counts: Facebook=1, Instagram=1, TikTok=1; LinkedIn=0.
