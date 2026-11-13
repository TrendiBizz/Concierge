# Onboarding Conrad inside the product

The guide existed only as a markdown file in the repo — useless to a tradesman on a building site. It
is now part of Concierge, reachable from the screen he will be working on, and printable.

## What was built

1. **A public, printable guide**: `https://concierge.trendibizz.com/guide/bonsai-cladding`
   (`api/app/guides.py`). Install Blender + Bonsai, draw and cast walls, cut openings, add the wall
   quantities, export IFC4, upload, takeoff, price. Includes the sanity check, the two usual mistakes,
   and an explicit "not covered yet" section. `@media print` styling so it prints or saves as PDF.
   `200 · 7883 bytes · <title>Cladding quotes from a 3D model — Concierge</title>`.
2. **An in-app walkthrough**: a "New to this? Start here" card at the top of **Designs and CAD**, four
   numbered steps, links to blender.org and bonsaibim.org, and a link to the printable guide.
   Verified in the deployed bundle `Designs-z5j36Kvx.js`.
3. **His workspace prepared**: default quoting method **Nu-Wall cladding** created for
   `pukeko-construction` (10% waste, net cladding area, 15% GST, rate deliberately $0 — his number).
   Verified: `/owner/quote-profiles` returns 1 profile for that tenant; Designs tab `200`.
4. **Operator checklist**: `docs/CONRAD_ONBOARDING.md` — account, invite link, first run-through,
   pre-handover checks, and the limits to state plainly.

## Faults found on the way

**The guide 404'd publicly.** The reverse proxy only forwards a fixed list of paths for
`concierge.trendibizz.com`, and `/guide/*` was not on it, so the API was never reached even though
`127.0.0.1:8000/guide/bonsai-cladding` answered 200. Fixed by adding `/guide/*` to the `@owner` path
matcher in `scripts/vps/Caddyfile`.

**`caddy reload` cannot work here.** The Caddy global block sets `admin off`, so the admin API is not
listening and `caddy reload` fails with `dial tcp [::1]:2019: connect: connection refused`. The
config is a bind mount, so a container recreate is required:
`docker compose ... up -d --force-recreate gateway`. Recorded because "reload the proxy" is the
obvious wrong next step.

**Verification after the change:** guide `200`; `/studio/` `200`; `trendibizz.com` `200`; the
site-wide proxy recreate did not take anything else down.

## Tests

`api/tests/test_guide_pages.py` — six assertions on the rendered page: title, both free tools linked,
the `Qto_WallBaseQuantities` step present, product navigation named, the sanity rule and the PDF/DWG
limit stated, and printable CSS. **1069 tests pass.**

## Outstanding for the operator

- His login is **`pukeko-demo@trendibizz.com`**, a demo address. Change it to Conrad's real email and
  send him a fresh single-use sign-in link. Nobody should be working in a demo account.
- The rate is his to set. It ships empty on purpose.

## Activation email — sent to Conrad

His real address was in the CRM: **Conrad Schiess, `conrad@pukekoconstruction.co.nz`** (lead created
11 Nov, channel email). The demo login `pukeko-demo@trendibizz.com` was replaced with it in
`tenant_users`, so the account he signs into is his, and a future recovery link goes to him.

A single-use link (30 days) was minted for that address and the invitation emailed from the product's
own mailer through the configured SMTP. The email carries the sign-in link, the printable guide link,
the five first steps (rate per m², upload, IFC takeoff, price, review in Quotes), and the honest
limits (IFC only; PDF/DWG cannot be measured).

Sending from a shell had no audit trail — see fault 81 below. The recorded path was added and proved
separately on our own mailbox (queued → `sent`, attempts 1, no error).

## Fault 81 — an operator-sent invitation left no record

**Cause.** `mailer.send_email()` called directly from a container shell bypasses the outbox: no row in
`outbox`, no status, no retry, nothing to point at when a client says "I never got it".

**Fix.** `api/app/owner_invites.py` — composes the invitation and queues it via `outbox.enqueue`
(tenant-scoped, deduped by `owner-invite:<tenant>:<email>`), exposed as
`POST /admin/tenants/{slug}/owner-invite` (admin token). Returns the link as well, so the operator can
hand it over directly if email fails.

**Evidence.** Called against our own review tenant: `{"queued": true, ...}` then outbox row
`sent | attempts=1 | no error`.

**Test.** `api/tests/test_owner_invite_email.py` — the composed email carries the link and guide, names
the business and the first steps, never claims a price the business has not set, the route exists, and
the module queues through the outbox rather than importing the mailer.
