# Concierge code ownership migration

This directory is owned by **TrendiBizz/Concierge**, not by the public website.
The copied contents originated from **Trendiisales/trendi-site** branch
`concierge-stack`, commit `ceabab7`.

## Ownership

- `agent/`, `livekit/`: LiveKit + Grok voice implementations and SIP templates.
- `social-service/`: independent Rust social API, OAuth groundwork and tests.
- `socialsync/`: legacy social user interface and supporting Node code.
- `hermes/`: Concierge agent launch tooling.
- `tests/`: voice and messaging verification.
- `backup.sh`, `restore-test.sh`, associated scripts: encrypted backup tooling.
- `platform-website/`: separate historical product website prototype, **not**
  the current Trendi public website in the other repository.

Do not move runtime databases, credentials, customers' messages, local volume
contents, `.env`, `backup.env`, `social.env`, or unencrypted backups into Git.

## Deployment transition

**Code ownership cutover verified on Mac.hub (2026-11-07):** The 142 tracked
product files were removed from the `trendi-site` branch `concierge-stack`.
That website checkout no longer contains an active `concierge-stack` tree.
The private `.env`, `backup.env`, and customer data were checksum-matched to
the canonical Concierge paths and the old runtime was moved to a local,
Git-ignored, owner-only `.migration-rollback/` archive inside this directory.

The launchd daily backup and monthly isolated restore jobs now run the
**Concierge** repository scripts. A new encrypted backup was uploaded from
the canonical location, then restored successfully, including 121 Twenty
tables. The voice Python 3.12 environment was independently rebuilt and all
54 tests passed. Compose config was validated with the private local env.

The running core platform, Twenty, Caddy and Hermes services were preserved,
not redeployed. Runtime production migration of individual voice/social
providers, live social publishing, customer messaging, account OAuth,
multi-customer SIP routing and authorized recording are **not** represented
as live-certified. They require separate real-provider authorization/tests.

The website retains its design, SEO and minimal widget/API client. It must
not acquire new backend product sources.

Run offline verification from the **Concierge repo root**:

```sh
python3 scripts/check-repository-boundary.py --website-root ../trendi-site
python3 -m unittest discover -s concierge-stack/tests
cd concierge-stack/social-service && cargo test --locked
```

The strict ownership check now passes without any transitional allowance. Docker Compose needs
customer/private runtime environment files that are never versioned; use
`docker compose config` with appropriately provided secrets in the
authorized runtime, not blank production substitutes.

## Outstanding integration checks

The platform-to-Rust HTTP contract, tenant-isolated onboarding browser flow,
real permission grants, OAuth provider reviews, SIP/customer phone routing,
consented recording, private CRM connection and full restore test are distinct
from the source-copy verification. Keep the original deployment until these
are validated. No production deployment is implied by this commit.
