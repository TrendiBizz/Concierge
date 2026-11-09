# Current main API deployment and Grok SIP audit — 10 November 2026

## Cause and correction

Production API was healthy but stale relative to main b35614c (PR10), so the
merged phone conversation-copy and PR9 workflow changes were not running.
Rebuilt/redeployed current main API/static and locked dependencies, preserving
private settings and existing production Compose/services. Recreated API and
social together because they share a network namespace. Both healthy.

Deployed image:
sha256:7a16174bc7ccb01f68fa27de9608b4297626b80368af88b4523fe9b8d55ac2ae
Image label org.opencontainers.image.revision=b35614c. Compared all67 tracked
application/static file SHA256 values to the running container: identical.
customer_cases schema present after startup migration; private /healthz ok.

Runtime PHONE_RECEPTIONIST_ENABLED changed false→true. Preserved existing xAI
key and PHONE_VOICE_PROVIDER=grok. Set missing XAI_SIP_CONNECTIONS to {} rather
than inventing an enabled mapping or webhook secret. No tenant/number activated.
Added missing example settings, complete per-business setup documentation and
build source-revision label for future deployments.

## Real account audit, not an assumption

Read-only production database: three tenants, zero phone_numbers, zero tenants
with phone_enabled, one business telephone authorization. Existing xAI key is
present. Authenticated GET https://api.x.ai/v2/phone-numbers returned200 with
zero registered numbers and no next page. No existing number was overlooked.

xAI SIP number registration is available through its API; console access is not
inherently required. It registers an existing carrier/PBX number using an actual
SIP allowlist/digest and returns the webhook signing secret once. It does not
provision a new public number through that API. See official instructions:
https://docs.x.ai/developers/model-capabilities/audio/speech-to-speech/sip

Remaining carrier prerequisite is a genuine compatible ingress number/trunk,
then private signed webhook mapping and business-specific activation. An owner's
contact smartphone number is not a SIP route. No purchase, account signup, fake
number/secret, external message, telephone call or authorization declaration was
made. Website voice remains separate and needs none of the SIP configuration.

## Verification and recovery

- Current main Python tests:356passed in12.95seconds (one upstream deprecation).
- Required scripts/rust-gate.sh passed GATE-ALL-OK for all four crates; log
  /tmp/concierge-rust-gate-20261110.log. No Rust source edits.
- API/social Compose health passed. Running application/static matches main.
- Public automated urllib probe hit Cloudflare403/error1010 before application;
  origin gateway checks: owner UI200, unauthenticated owner/provider-readiness401,
  unknown SIP route503. These are not called public-edge success.
- Unknown SIP route remains rejected; no registered signing secret exists to
  perform a genuine signed provider call. No claim of carrier acceptance.

Backups on VPS /opt/trendi/backups/main-api-20261110, root-only:
source-before.tgz, api.env.before, concierge-before.dump (pg_dump custom),
image-before.txt, build.log. Rollback image:
trendi-concierge-api:before-main-api-20261110.
Deployment script restores env/source/image on failed health and recreates
API/social. No rollback was needed. Database backup retained; new additive schema
is preserved on application rollback. Private env/credentials never committed.

Source deployment is b35614c; this subsequent commit adds documentation and build
revision metadata only. It is not a claim that the entire service/carrier path
has passed end-to-end acceptance.
