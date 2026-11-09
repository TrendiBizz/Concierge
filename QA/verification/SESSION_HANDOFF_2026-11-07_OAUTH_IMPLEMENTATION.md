# Trendi Concierge — OAuth continuation handoff, 2026-11-07

## Resume point
Read this and the preceding `QA/verification/SESSION_HANDOFF_2026-11-07_CRM_NOTE_CONFIRMATION.md` plus `/Users/jo/work-staging/trendi-site/concierge-stack/HANDOFF.md`.

Worktrees on Mac.hub:
- `/Users/jo/work-staging/trendi-site`, branch `concierge-stack`, first OAuth local commit `e70f46f` (Mastodon), next LinkedIn/consent commit is recorded in git log.
- `/Users/jo/work-staging/concierge-integration`, branch `integration/concierge-v1`, first OAuth local commit `7833358`, next LinkedIn portal commit is recorded in git log.
- Unrelated `QA/verification/office-shots/` remains untracked and MUST remain untouched.

## Built locally
- Rust Mastodon OAuth 2.0 auth-code + PKCE-S256, 256-bit state, tenant-bound encrypted verifier, SHA-256 state digest, 10-minute single-use state, verified identity + scopes, encrypted tokens, secure provider-side revocation.
- Rust LinkedIn 3-legged OAuth, fixed official LinkedIn auth/token and userinfo endpoints, one-time tenant-bound state, OIDC identity and `openid profile w_member_social` scopes, encrypted credentials, OAuth expiry, reconnect preserving account id, local unlink (NOT provider revocation; customers must revoke in LinkedIn connected apps).
- `src/store.rs` maintains account consent scope/time, token expiry and disconnect timestamps; expired accounts are not usable for posting.
- Existing Concierge authenticated owner portal and Python proxy now provide Connect Mastodon/LinkedIn popup buttons and unlink actions, without sending app credentials, Rust keys, or customer passwords to browser. Callback uses owner portal same-origin `postMessage`, matching popup window and state; only owner role may link.
- No actual external provider account linked. No social posting/messaging enabled or production services changed. No Postiz source translation, no new repo.

## Verification
- Rust `cargo test --locked`: 33 passed; `cargo fmt --check` and `cargo clippy --locked --all-targets -- -D warnings` PASS.
- Concierge platform tests: 52 passed; Python CRM/owner tests: 16 passed; voice suite: 54 passed.
- Browser JavaScript syntax `node --check` PASS.
- Existing Twenty host bridge healthy on `127.0.0.1:4410/health` with configured true.
- Docker services all running unchanged. Both worktrees `git diff --check` passed.

## Real-world OAuth activation prerequisites — NOT authorized/performed
1. Choose and authorize a staging HTTPS hostname/owner-ui callback. Register one Trendi Mastodon developer application on the selected instance with `read:accounts write:statuses`; provide the exact client id/secret and callback through private gitignored runtime config.
2. Register one Trendi LinkedIn developer app with Sign in with LinkedIn using OpenID Connect and Share on LinkedIn; confirm `openid profile w_member_social` permissions. Provider approvals/app review may apply. Credentials private; never paste in chat.
3. Configure `SOCIAL_MASTODON_ORIGIN`, `SOCIAL_MASTODON_CLIENT_ID`, `SOCIAL_MASTODON_CLIENT_SECRET`, `SOCIAL_MASTODON_CALLBACK` and/or `SOCIAL_LINKEDIN_CLIENT_ID`, `SOCIAL_LINKEDIN_CLIENT_SECRET`, `SOCIAL_LINKEDIN_CALLBACK` only after approval, with callbacks exact HTTPS same-origin `/owner-ui`.
4. Explicit approval for staging only; use disposable consenting test account and tenant; test true redirect, consent denial, wrong tenant, replay, token expiry, refresh/re-link and revocation/disconnect. Do not turn on publishing.
5. Mastodon implementation only supports one operator-pinned instance. Multi-instance Mastodon registration and stricter provider-specific network audit remain to build. LinkedIn local unlink is not provider-side revoke.
6. Bluesky needs **AT Protocol** full DPoP/PAR/client metadata/DID OAuth, and is NOT supported by the above implementation. Meta Facebook/Instagram/Threads, TikTok, YouTube, Pinterest, X and Google Business Profile need individual official API app approvals and integration work. No generic arbitrary redirect shortcut.
7. Cross-provider publishing, media and live tests NOT implemented. Existing Rust publisher remains OFF.
8. CRM private Docker bridge needs separate staging activation approval. Twenty exactly-once delivery still blocked on CRM-side event idempotency and phone-only deduplication. Unknown delivery marked `uncertain` and must not auto-retry.
9. Customer-specific voice routing/recording/permissions/reply mapping and real call-back CRM validation pending separate real-world approvals. Existing proven LiveKit/Grok assistant preserved.
10. Website/SEO final design review, legal/privacy, provider approvals, billing and production deploy require explicit separate authorization.

## Restrictions
No push, merge, deploy, DNS, real social connection, live posting/messaging, paid provider changes, service restart, or genuine customer data changes without separate user approval. Preserve LiveKit/Grok, existing loopback Twenty bridge and all services. No secret leakage; do not touch `QA/verification/office-shots/`.

## Local verification commands (macOS zsh)
```sh
cd /Users/jo/work-staging/trendi-site/concierge-stack/social-service && cargo test --locked && cargo fmt --check && cargo clippy --locked --all-targets -- -D warnings
cd /Users/jo/work-staging/concierge-integration && PYTHONPATH=QA/verification/shims:api /Users/jo/work-staging/venv-concierge/bin/python -m pytest api/tests/test_units.py -q
cd /Users/jo/work-staging/concierge-integration && PYTHONPATH=QA/verification/shims:api /Users/jo/work-staging/venv-concierge/bin/python -m unittest QA.verification.twenty_bridge_adapter_test QA.verification.social_owner_integration_test -q
```
