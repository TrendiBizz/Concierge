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

The old website-worktree copies and local runtime files are deliberately
preserved until deployment configuration, launchd schedules, external volume
mounts, DNS/API endpoints and restore paths have been verified. The old path
may still be used by running services. Merely copying code does not switch a
running service. Do not delete originals before an authorized cutover and a
tested rollback. No live social posting or customer messaging is enabled by
this migration.

The website retains its design, SEO and minimal widget/API client. It must
not acquire new backend product sources.

Run offline verification from the **Concierge repo root**:

```sh
python3 scripts/check-repository-boundary.py --website-root ../trendi-site --allow-legacy
python3 -m unittest discover -s concierge-stack/tests
cd concierge-stack/social-service && cargo test --locked
```

The transitional allowance must be removed after runtime cutover and removal
of redundant files from the website repository. Docker Compose needs
customer/private runtime environment files that are never versioned; use
`docker compose config` with appropriately provided secrets in the
authorized runtime, not blank production substitutes.

## Outstanding integration checks

The platform-to-Rust HTTP contract, tenant-isolated onboarding browser flow,
real permission grants, OAuth provider reviews, SIP/customer phone routing,
consented recording, private CRM connection and full restore test are distinct
from the source-copy verification. Keep the original deployment until these
are validated. No production deployment is implied by this commit.
