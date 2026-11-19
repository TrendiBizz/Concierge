# YouTube customer channel verification

Cause: customer-owned YouTube channels were missing from the approval publishing path.
Fix: Google PKCE linking, encrypted grants, renewal/revocation, video metadata validation, bounded resumable uploads, scheduler gates, owner UI, bridge parity and network listings.
Proof: social-service 83 tests pass; strict Clippy passes. Eight offline YouTube tests cover encrypted grants, single-use tenant state, scope refusal, invalid grants, private default, approvals/switches, 308 ranges, 5xx status reconciliation and safe errors. Native core: 128 pass, including YouTube bridge/error parity. Python integration tests: 12 pass. SocialSync: 20 pass. JavaScript syntax and Swift parsing pass.
Mutation: changed the default visibility to Public; the dedicated privacy test failed, then restored Private and reran the full service suite successfully.
Known baseline: API full suite has 1538 passes, 60 skips and one website CSS cache-version failure in tests/test_social_icons.py. No website files changed.
No real provider requests, credentials, messages or uploads; no containers, deployment, commit or push.
