# Concierge customer activation verification — 2026-11-07

Canonical repository: `TrendiBizz/Concierge`, branch `integration/concierge-v1`.

## Executed verification

- Isolated PostgreSQL: 14 complete suites passed, zero failed.
- Phone provider simulation: 29/29 checks passed. Signed webhooks, tenant number ownership, authorization denial, opt-in recording, forged recording callback rejection, provider receipt with mocked HTTP. **No actual PSTN call or audio file was recorded.**
- Cloudflare email simulation: 17/17 checks passed. Signed inbound route, mailbox isolation, authorization denial, replay dedupe, no send.
- Concierge API: 52/52 unit tests passed.
- Owner browser: successful owner/viewer login and profile UI, seven permission controls, owner grant/revocation, viewer cannot edit; zero JavaScript errors.
- Rust social: cargo build/test/fmt/clippy passed; a local disposable HTTP contract passed with fake credentials and publisher OFF.
- Existing Grok/LiveKit agent: 54 offline tests passed. The previously working Trendi-specific voice agent remains preserved. **It is not proof of tenant-specific live SIP routes.**
- SocialSync Node: 19/19 tests passed.
- Strict repository boundary check: passed.

## New customer permissions and runtime safeguards

- Owner-facing channel permissions: telephone, call recording, inbound email, outbound email, inbound SMS, outbound SMS, social accounts.
- Tenant-scoped ownership, append-only authorization event trail and revocation.
- Signed inbound phone/email/SMS requires matching business authorization.
- Outbound SMS/email checks business permission **again when sending**; queued work cannot override a revocation. Owner operational alerts are separate.
- Recording is independently off by default (`PHONE_RECORDING_ENABLED=false`). It requires enabled telephone service, customer authorization, live call ID, explicit caller phrase `I consent to recording`, and a successful Twilio Recording API response. Audio is NOT downloaded or stored by this implementation; only recording IDs and status. Signed recording callback updates receipt state.
- Readiness never claims an owner checkbox equals provider verification, customer activation, or caller consent.

## Cannot legitimately certify without real external evidence

| Channel | Required independent evidence |
| --- | --- |
| Social OAuth | Trendi-approved provider application, HTTPS redirect domain, authorized test accounts, real login/consent, token lifecycle + revoke proof. Rust currently supports LinkedIn/Mastodon OAuth; Bluesky pilot app-password is NOT customer OAuth, and major other networks still need official connectors/reviews. |
| Telephone | Verified customer number/trunk, provider credentials, inbound signed live call, two-tenant routing to correct business, transfer and failover, tested billing and emergency rules. The original LiveKit/Grok implementation is Trendi-specific; Twilio ConversationRelay is a separate multi-tenant simulated path and must not be presented as the same live engine. |
| Recording | Real caller's informed consent; provider-approved project; genuine Twilio recording, signed callback, playback/retrieval controls, encryption, retention and deletion drill, legal review. Do not enable for paid calls without authorization. |
| Customer inbound email | Authorized Cloudflare domain routing, MX DNS, valid signed webhook and real email to customer mailbox. |
| Customer outbound email | Owner-approved sender domain/SMTP or API grant, SPF/DKIM/DMARC and real test delivery, opt-out/revocation. |
| Customer texts | Verified sender number/provider access, signed inbound and outbound SMS, STOP, opt-in/opt-out, test delivery, cross-tenant isolation. |
| End-to-end customer activation | Two actual businesses consenting, provider approvals, complete setup from the owner portal, smoke tests, confirmed CRM events, restores, and user-approved production deployment. |

No app review, number purchase, live provider messaging, recording, production deploy, or main-branch merge is claimed. No paid-provider changes were made.

The release is **code-verified for the safeguards above but NOT production-certified** until the external evidence is completed. The two repositories remain separate as directed. Retain this distinction in customer-facing claims.
