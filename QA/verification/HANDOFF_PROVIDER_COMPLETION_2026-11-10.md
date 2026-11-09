# Provider completion — 10 November 2026

PR: https://github.com/TrendiBizz/Concierge/pull/9 (py/finish-concierge). Review corrections prepared on codex/provider-completion. This checkpoint records verification before push and merge; consult PR state for the final merge result. No production release was deployed.

## Completed verification and corrections

Reviewed PR9 including mutation incident 0196cbf. Fixed customer replies incorrectly answering other customers' messages, per-message follow-up wiring and uniqueness, email messages marked answered before successful delivery, and a test helper leaking mocks. Fixed phone repair accepting arbitrary text, dry-run schema writes and non-atomic application. New regression tests failed before fixes; transaction rollback was also mutation-checked. No mutation probe remains.

Full Python 3.13 suite: 354 passed. ./scripts/rust-gate.sh: GATE-ALL-OK after cargo fmt for all four crates. Provider-readiness regressions: 19 passed. Disposable local PostgreSQL used for integration tests; never run schema-resetting tests against production.

Readiness now excludes Mastodon, distinguishes dashboard action, missing configuration and missing code, checks actual SIP configuration shape, preserves existing Stripe checkout, and no longer claims all blockers are dashboard work or payments do not exist.

## Production phone dry run

Executed patched maintenance CLI in existing API container, using a direct pool and read-only transaction, without db.init/schema migration. Three tenants surveyed:

| Field | Rows | Phone values | Repair candidates | Manual decisions |
| --- | ---: | ---: | ---: | ---: |
| leads.phone | 1 | 1 | 0 | 0 |
| appointments.phone | 0 | 0 | 0 | 0 |
| outbox.to_addr | 8 | 3 | 0 | 0 |
| opt_outs.contact | 0 | 0 | 0 | 0 |

Exit 0. No --apply: zero changes required. The pasted claim of current malformed +021 rows was not reproduced. This is normalization validation, not a real carrier dialability test. No customer contact values recorded here. Production currently lacks PR9 case tables; global default country code is 1. No database data, schema, application release or containers changed.

## Actual external status

Read-only dashboard verification in this session:

- Meta app 676274422041376: **Review in progress**, six permissions (instagram_content_publish, instagram_basic, business_management, pages_read_engagement, pages_show_list, pages_manage_posts). Already submitted; do not duplicate.
- LinkedIn Pages app 266706827: company verified; Community Management API Development Tier **Review in progress**. Already submitted.
- TikTok app 7705532547380250645 production: **In review**, Login Kit/user.info.basic only. Uploaded demo is listed. This request does not cover video publishing; Content Posting API approval remains separate if publishing is required.
- Google: previous approved session enabled Business Profile API and connected Trendi using kiwi18@gmail.com. OAuth remains External Testing; production verification has not been submitted. Prepare actual scopes, branding/domain/privacy and review evidence before moving public. Posting remains disabled.
- Telephony: no real carrier number/call acceptance completed. No number purchased and no call made.

## Stripe correction

The user was right that Stripe already existed. Trendi website source /Users/jo/work-staging/trendi-site-web/site/products.js contains working SEO monthly and deposit Payment Links; both checkout pages were verified in the preceding session without a purchase. The separate payments/server/server.js non-gateway comment does not describe the whole business.

Concierge monthly/yearly stripeLink settings are empty in inspected website history. Preserve existing SEO links; verify the intended existing Concierge product/link in Stripe before filling one. Source USD versus checkout-description NZD wording remains unresolved; do not silently change charge currency or prices. Automatic subscription activation/webhook reconciliation is not implemented by the manual invoicing module. Provider readiness reports this as code work if required, rather than claiming a dashboard approval fixes it.

## Remaining work and constraints

Wait for provider decisions already requested. Google public OAuth review, TikTok publishing review if required, Concierge billing link/currency confirmation and real carrier acceptance remain separate gates. No paid provider purchase, external posts/messages, monetary setting changes or live publishing was performed. DSH dropped and Mastodon excluded as requested. Original Rust worktree's uncommitted Google/Stripe handoff additions were preserved.
