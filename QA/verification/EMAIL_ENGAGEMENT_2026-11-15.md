# Email engagement and deliverability — 2026-11-15

Asked: "how do I set a pixel in my email to know when it is read", then "tell me what else we can
use that is the best solution", then "implement all of these where viable".

The answer to the first question is that a pixel is the wrong instrument. It is fetched by Apple
Mail Privacy Protection and Gmail's image proxy whether or not a person reads the message, and by
corporate security scanners the moment mail is delivered. This pass replaced it with the two
signals that mean something, and found a deliverability defect that outranks both.

## What was built

**Click tracking, first-party.** A link in an owner or campaign email is rewritten to
`https://concierge.trendibizz.com/studio/l/<token>`. The destination is stored server-side in
`email_link`, keyed by an unguessable token, so the redirect cannot be pointed at an arbitrary URL
and there is no open-redirect surface. `GET /studio/l/{token}` records the first click in
`email_engagement` and 302s to the stored destination; repeat clicks return the same page and are
recorded once (`ON CONFLICT (token, kind) DO NOTHING`).

**Provider events.** `POST /webhooks/brevo` already handled bounces, blocks, complaints and
unsubscribes. It now recognises `delivered`, `opened` and `click`, records them against the outbox
message id, and returns before the suppression path — hard bounces still reach suppressions, so
suppressing an address is never lost to a mislabelled event.

**HTML alternative, plain text kept.** `mailer.send_email(..., html=...)` attaches a
`text/html` part to a `text/plain` part. The plain part is mandatory: text-only clients show it and
filters expect it. Tracking is off unless `TRACKED_LINKS_BASE` is set, and only for `owner_alert`,
`campaign` and `email_secretary_reply` — a customer's transactional mail keeps its own links.

**The nudge list.** `GET /admin/pending-invites` and `scripts/vps/pending_invites.py` answer the
question that actually matters — who was invited and never signed in — from
`tenant_invites.used_at`, not from an open flag. Live output:

```
1 owner(s) invited and never signed in:
  pukeko-construction   conrad@pukekoconstruction.co.nz   invited 2026-11-15  last email 2026-11-15T03:07  engaged -
```

**A deliverability check.** `healthcheck.py` gained `email:auth`: SPF present and a real `v=spf1`
policy, DMARC present and enforcing, and a DKIM record at the selector the domain actually
publishes (probing 13 common selectors, or `SMTP_DKIM_SELECTOR` when set). It warns rather than
fails because only the operator can publish the record.

## Bug found: the domain publishes DMARC p=quarantine and no DKIM at all

| Record | Result |
|---|---|
| SPF | present (`include:spf.web-hosting.com`, `_spf.mx.cloudflare.net`) |
| DMARC | `v=DMARC1; p=quarantine; rua=mailto:rua@dmarc.brevo.com` |
| DKIM | **absent at all 13 selectors probed** (`brevo`, `mail`, `sib`, `s1`, `s2`, `default`, `k1`, `google`, `privateemail`, `selector1`, `selector2`, `smtp`, `dkim`) |
| Sending host | `smtp-relay.brevo.com:2525` (Brevo transactional relay), From `admin@trendibizz.com` |

A domain that tells the world to quarantine unauthenticated mail, and then sends mail without DKIM,
is asking inboxes to junk its own invitations. This is the strongest candidate explanation for a
customer not seeing their sign-in email. It cannot be fixed from this repo: the DKIM keypair is
generated in the Brevo domain-authentication panel, which then issues the TXT record to publish.
`email:auth` now reports it on every health run.

## Correction: the DKIM alarm was wrong (same session, found while auditing the deploy)

The first version of `email:auth` probed 13 selectors and reported "no DKIM record at any of them".
That was a false alarm, and the cause was twofold:

1. **The selector list was too short.** Brevo publishes the keys at `brevo1` and `brevo2`
   (CNAMEs to `b1/b2.<domain>.dkim.brevo.com`), and signs with `s=brevo1`. The list held `brevo`
   and `mail`, which resolve to nothing.
2. **The probe accepted any TXT answer.** `dig +short TXT brevo1._domainkey...` prints the CNAME
   target as well as the key, so a CNAME line could be mistaken for a key in one direction and a
   valid key was never reached in the other.

Verified by hand:

```
$ dig +short TXT brevo1._domainkey.trendibizz.com
b1.trendibizz-com.dkim.brevo.com.
brevo5.dkim.brevo.com.
"k=rsa;p=MIIBIjANBgkq…"           <- valid key, dkim=pass for Brevo mail
```

The deployed check had already been corrected on the box (selector `brevo1`/`brevo2`, plus an
`is_dkim_key()` helper that requires a real `p=` value) and never came back to the repo. Both halves
are now in the repo with regression tests, and the live check reports `email:auth` ok — health is
**43 ok / 1 warn (`sms:inbound`) / 0 fail**.

Lesson, and the reason this section exists: the deployed file was *newer* than the repo, so a
green health check was hiding a divergence. `scripts/vps/verify-deploy.sh` now compares
`api/app`, `scripts/vps` and `website/site` against the box by checksum and exits non-zero on any
difference.

## Deploy parity audit (the question "is all this pushed, committed and deployed")

`git`: HEAD `f9abbc1` = `origin/main`, working tree clean. `scripts/vps/verify-deploy.sh` against
the box: **api/app 107 files match, scripts/vps 36 match, website/site 58 match.**

Three drifts were found and closed in the process:

| Drift | What it was | Resolution |
|---|---|---|
| `scripts/vps/healthcheck.py` | the box carried a newer DKIM fix than the repo | ported back into the repo, with tests |
| `api/app` (4 files) | the repo carried committed work the box had never run — `automated_mail.py` (a Microsoft account-verification email had been treated as a customer enquiry and forwarded as an owner SMS containing a security code), `automation.py`, `cloudflare_inbound.py`, `inbound_email.py` (body-aware classify) | `rsync api/app/` + `redeploy-api.sh`; the API now runs repo state |
| `scripts/vps` (10 files) | `deploy-studio.sh`, `harden_host.sh`, `smsgate_check.py`, seven `prove_*.py`, `order-phone-did.sh`, `rotate-cloudflare-token.sh` differed or were absent on the release tree | synced; the repo version of `rotate-cloudflare-token.sh` is the corrected one (box-local `/healthz`, `api.env` read as data) |
| `website/site` | another session had deployed a newer site (about.html description gained "for businesses worldwide") after my mirror snapshot | mirror refreshed **from** the box; both now agree on 58 files |

Two false positives in the new tool were fixed before trusting it: `md5sum` prints two spaces where
macOS `md5 -r` prints one, macOS leaves `._*` AppleDouble files, and the two platforms order paths
differently without `LC_ALL=C`. The first run reported every file as different.

## Proof (live, on the box)

- Tables created by the idempotent schema on restart: `email_link`, `email_engagement`.
- Public redirect: `GET https://concierge.trendibizz.com/studio/l/selftest-9x2` → `302`
  `https://trendibizz.com/ai-visibility`, twice, with **one** engagement row afterwards — dedupe
  verified live, not only in the test.
- Real send: a re-invite to the fictitious test tenant produced two `email_link` rows for outbox
  4226 (the sign-in link and the site URL) and the message sent.
- Provider event: `POST /webhooks/brevo?token=…` with a synthetic `opened` for that message id
  returned `{"processed":1,"results":[{"recorded":"open"}]}` and wrote one `open` row.
- Health: 42 ok / 2 warn / 0 fail — `sms:inbound` (unchanged) and `email:auth` (the DKIM gap).

## Two defects found and fixed during the build

1. **The tracked path was unreachable.** The edge proxy in front of `concierge.trendibizz.com`
   forwards `/studio/*` and `/webhooks/*` to the API and answers everything else itself:
   `https://concierge.trendibizz.com/l/<token>` returned the edge's empty 404 (content-length 0,
   `x-trendi-release`), while `/healthz` and `/api/v1/*` are equally blocked. The redirect moved to
   `/studio/l/{token}` (registered before the SPA catch-all `/studio/{path:path}`), and a test pins
   `engagement.TRACKED_PATH`.
2. **Provider engagement events would have been swallowed.** They were falling through to
   `suppressions.record_event`, which ignores unknown names — harmless — but the same branch
   ordering meant a future misclassification could stop a bounce being suppressed. The handler now
   returns before the suppression path for engagement kinds, and a test asserts the two routes are
   disjoint.

## Tests

`api/tests/test_email_engagement.py` (26) and `api/tests/test_email_auth_health.py` (7), plus a
`html=` kwarg added to the capture helper in `test_email_reply_to.py`. Mutation-checked:

| Mutation | Result |
|---|---|
| Remove `ON CONFLICT (token, kind) DO NOTHING` from the click insert | dedupe test red |
| Remove the `continue` so engagement events reach suppressions | routing test red |
| Remove the DKIM rule from `email_auth_problems` | 4 tests red |
| Drop the HTML alternative from the mailer | multipart test red |
| Point `TRACKED_PATH` back at `/l` | path test red |

Full suite: **1,340 passed**.

## Deliberately not done

- **No pixel.** Rejected for the reasons above; there is no 1x1 image anywhere in the codebase.
- **No site analytics.** Plausible (or equivalent) needs an account and a domain decision, so the
  click currently lands on the destination with nothing counting the visit. Operator item.
- **Tracking stays off for customer-facing mail.** `TRACKED_LINKS_BASE` is set on the box and
  covers owner alerts, campaigns and secretary replies only.

## Operator items created

1. **Publish DKIM for trendibizz.com** in Brevo → Senders & IP → Domains (authenticate the domain),
   then add the TXT records Brevo issues. `email:auth` will go green on the next health run.
2. **Add site analytics** so a click can be attributed (Plausible self-serve, cookieless, no consent
   banner needed).
3. **Disclose link tracking** in `/privacy` before it is used on any customer-facing mail.

## Deploy trail

- API: `rsync api/app/` + `scripts/vps/redeploy-api.sh` (container recreated, not restarted —
  `docker restart` does not reload `env_file`, which is why the first tracked send produced no
  links).
- `TRACKED_LINKS_BASE=https://concierge.trendibizz.com` appended to `/opt/trendi/shared/api.env`.
- `healthcheck.py` and `pending_invites.py` deployed to the release tree.
