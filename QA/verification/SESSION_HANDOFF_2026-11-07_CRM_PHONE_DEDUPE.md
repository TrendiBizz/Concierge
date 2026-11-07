# Trendi Concierge — CRM phone-only deduplication continuation, 2026-11-07

## Repository state
- Mac.hub: `/Users/jo/work-staging/concierge-integration`, branch `integration/concierge-v1`.
- Initial HEAD verified: `743d091`.
- Companion site worktree HEAD verified: `486644a`.
- Existing untracked `QA/verification/office-shots/` must remain untouched.

## Work in this continuation
- Reviewed the OAuth, CRM confirmation and main site handoffs.
- Updated `integrations/twenty/bridge/server.js` to attempt an existing-person phone match for phone-only leads before creating a new Twenty person.
- NZ phone matches require both normalized national digits and +64 calling code; non-NZ phone lookups use the E.164 field previously persisted by the bridge.
- Twenty failures, ambiguous matches, or malformed people responses fail closed before creating a person. This is not an exactly-once claim.
- Added two regression cases in `integrations/twenty/bridge/test/bridge.test.mjs`.
- Twenty uses a composite filter expression with `and(...)`, consistent with published REST grammar.

## Verification
- `node --test integrations/twenty/bridge/test/bridge.test.mjs`: 21 passed, 0 failed.
- Prior current-session verification: Rust `cargo test --locked` passed; CRM and owner integration unittest suite 16 passed.
- `git diff --check` passed.
- **The phone filter has not been tested against the actual local Twenty instance.** Mock tests assert assumptions and are not sufficient for provider certification.

## Still outstanding — do not claim completion
1. Read-only integration verification of Twenty's actual phone composite filter and response shape, then isolated disposable create/retry and note tests with explicit approval; establish durable CRM-side event-id dedupe before claiming exactly-once.
2. Mastodon/LinkedIn provider applications with HTTPS callback and genuine consenting staging OAuth tests. Meta, Bluesky, TikTok and other platform OAuth are not implemented.
3. Private Docker CRM overlay only after authorization.
4. Customer voice routing/recording, authenticated email/SMS inbox actions, provider consent mapping and real call QA.
5. Customer portal onboarding, website and SEO review, legal/provider approvals and deployment.
6. Do not push, merge, deploy, restart, enable publishing/messaging, operate on real customer data, or incur costs without separate approval.

## Re-run
```sh
cd /Users/jo/work-staging/concierge-integration
node --test integrations/twenty/bridge/test/bridge.test.mjs
git diff --check
git status --short
```
