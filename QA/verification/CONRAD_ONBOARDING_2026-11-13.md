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
