# Hero SMS — N4 readiness

Hero Internet remains the voice carrier through the existing Asterisk trunk. No new carrier account or number is required by this change. Do not replace its SIP credentials or purchase anything.

## Disabled until configured

Production had no HERO SMS keys on 21 November 2026. Status: **needs Hero credentials**.

Jo must supply, through the existing secret store:

- Confirmation that the existing Hero phone account has SMS API access, the SMS API username and phone password, and which business/account is billed.
- Confirmation of approved destinations and sender/reply routing. A voice DID does not prove unsolicited inbound SMS or MMS support.
- Hero's delivery receipt API or webhook specification, authentication method, message correlation identifier and test fixtures.
- Hero's MMS support confirmation and inbound attachment API/authentication/size/type specifications.

The settings are `SMS_PROVIDER=hero`, `HERO_SMS_USERNAME`, `HERO_SMS_PASSWORD` and explicit `HERO_SMS_ENABLED=true`. Keep the last setting false until those details are confirmed. Tenant SMS permissions, opt-outs, quiet hours and flood limits still apply to queued messages. No real SMS or calls were used for testing.

## Current supported contract

The [official Hero instructions](https://herointernet.supporthero.io/article/show/119030-sms-gateway-instructions?lang=en) document a form POST to `https://hero.co.nz/sms.php` with `username`, `password`, `destination` and `message`. Credentials are sent in the body and redirects are disabled. The documented message limit is 160 characters; longer messages fail explicitly rather than silently truncating or sending multiple billable parts.

The success code indicates queue acceptance only. It includes no message ID or delivery receipt. Concierge records `sms_delivery_status=queued`, leaves the outbox `awaiting_receipt`, and moves it to `held` after 24 hours without confirmation. It never claims delivered or automatically resends an ambiguous submission. An operator must reconcile held messages against Hero before taking action. Do not clear the submission marker to force retries without reconciliation.

Hero's instructions describe replies arriving by email and say unsolicited inbound SMS requires a separate provider arrangement. Neither a DLR callback format nor an MMS format is published there. These portions of N4 remain blocked on Hero specifications; no speculative public callback or remote-media fetcher is exposed.

## Existing transports

The existing Twilio adapter now requests a signed, row-bound StatusCallback, verifies account, recipient and provider message ID, and records terminal delivery/failure without regressing on reordered callbacks. This completes existing code; do not add or fund a Twilio account. A downstream `sent` event is not final delivery. Only `delivered` confirms delivery.

Handset transports (`smsgate` and paired devices) are deprecated for new commercial onboarding. Existing explicit tenant choices remain compatible until a carrier migration is configured. No live handset HMAC validation is claimed.

## Deployment and rollback

Hold the shared deploy lock before merging and deployment. Pull main in the canonical clone, tag the running images with `scripts/vps/tag-rollback.sh`, and deploy through `scripts/vps/deploy-api.sh`. Verify health, SEO gate, file parity, healthz and widget response before releasing the lock. If checks fail, check out the recorded pre-deploy main commit in the canonical clone and use `scripts/vps/deploy-api.sh` to restore that committed source; verify again and record the failure. The rollback image tag remains available as evidence and recovery protection. No destructive schema migration is needed: the new nullable columns and index are additive and applied by the existing schema startup.
