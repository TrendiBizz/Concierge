# Why Cloudflare is throttling us

Answer: **the zone has a rate-limiting rule on the `/api/v1/` path prefix, set far too low for a
chat product — about three requests per ten seconds per IP, with a ten-second block.** Static pages
and assets are not affected. I measured it rather than guessed.

## Measurements (from one client IP, 13 Nov 2026, 18:40–19:00 NZ)

| Probe | Result |
|---|---|
| 12 × `GET /api/v1/widget-config`, 1s apart | `200 200 429 429 429 429 429 429 429 429 429 200` |
| 6 × `GET /api/v1/widget-config` rapid | `404 404 404 429 429 429` |
| 6 × `GET /api/v1/<non-existent path>` rapid | `404 404 429 429 429 429` |
| 6 × `GET /widget.js` rapid | `200` × 6 |
| 6 × `GET /demo/...` rapid | `200` × 6 |
| 6 × `GET /nope-not-a-page` rapid | `404` × 6 |

The 429 body is Cloudflare's own page — `error code: 1015` — and the response carries
`retry-after: 10`. So it is not our application's limiter (that returns JSON
`{"detail":"Too many requests, please slow down"}`), and it is not the whole zone: only `/api/v1/*`
is covered, on both `chat.` and `concierge.` hostnames.

Same moment, from the VPS itself (different egress IP): `200` with the tenant config. So the rule is
per client IP, not per origin.

## Why the limit is wrong for this product

A single visitor costs at least two API calls before they type (`widget-config`, then
`widget-logo`), and every message costs more. Three requests per ten seconds means:

- one visitor reloading the page twice can block themselves;
- two people in the same office or home behind one NAT IP block each other;
- our own testing from one IP blocks itself — which is exactly how this was found.

The observable symptom is the worst kind: the widget simply never appears, and the business never
learns that a customer was turned away.

## What I fixed (ours)

`widget.js` used to make the config request once, swallow the failure (`catch(function () {})`) and
render nothing — silent. Now it:

1. **retries** at 0 / 0.9 / 2.5 / 6 seconds, which rides out a ten-second block;
2. **caches the config in `sessionStorage` for five minutes**, so a reload no longer spends API
   calls against the limit;
3. on final failure, if it is a hosted page meant to be chatting (`data-autoopen`), **says so**
   instead of showing an empty page.

Verified live: the demo page now returns `200` for `widget-config` and `widget-logo` and renders the
composer, and the deployed script contains both the cache and the fallback.

## What needs a Cloudflare token with the right scope — operator action

The rule cannot be read or changed with the credentials on the box. `CLOUDFLARE_API_TOKEN` and
`CF_API_TOKEN` both pass `/user/tokens/verify` ("This API Token is valid and active") but every
rate-limit and ruleset call returns `Authentication error (10000)`; zone settings return
`Unauthorized to access requested resource (9109)`. So the tokens are scoped to DNS/Workers only.

To fix at the edge, either:

- **raise or remove the rule for `/api/v1/*`** and instead rate-limit the genuinely abusable
  endpoints (`/api/v1/chat`, `/api/v1/voice/token`, `/owner/auth/*`) at a level a real conversation
  cannot reach; or
- **exclude the widget endpoints** (`/api/v1/widget-config`, `/api/v1/widget-logo`, `/api/v1/chat*`)
  from the rule entirely.

Dashboard path: Security → WAF → Rate limiting rules (or the zone's Rules → Rate limiting rules).
Whichever is chosen, re-run the twelve-request probe above and expect twelve `200`s.
