# Pukeko activation audit — every link, as Conrad

Before handing a sign-in link to a real customer, the account was exercised as him: every Studio
screen's API, every social connect flow, and every link in his onboarding guide.

## Owner API — 26 endpoints, 26 healthy after fixes

`/owner/me`, `/crm`, `/contacts`, `/crm/quotations`, `/products`, `/quote-profiles`, `/designs`,
`/onboarding`, `/onboarding/authorizations`, `/social/status`, `/social/accounts`, `/social/posts`,
`/media/brand`, `/media/assets`, `/media/usage`, `/revenue`, `/call-insights`, `/supervision`,
`/live-calls`, `/missed-calls`, `/team`, `/webhooks`, `/payment-settings`, `/calendar` — all `200`.
`/owner/invitations` is `405` on GET because it is POST-only; the portal only posts to it.

## Social connects — 7 networks, all returning real provider authorisation URLs

| Network | Start endpoint | Provider URL |
|---|---|---|
| TikTok | 200 | tiktok.com/v2/auth/authorize |
| YouTube / Google Business | 200 | accounts.google.com/o/oauth2/v2/auth |
| X | 200 | x.com/i/oauth2/authorize |
| LinkedIn (personal) | 200 | linkedin.com/oauth/v2/authorization |
| LinkedIn (organisation) | 200 | linkedin.com/oauth/v2/authorization |
| Facebook | 200 | facebook.com/dialog/oauth |
| Instagram | 200 | facebook.com/dialog/oauth |

Each URL was followed: they land on the provider's own login pages, and every `redirect_uri` points
at `https://concierge.trendibizz.com/owner/social/oauth/callback`. `live_publishing` is `false` — the
posts go to approval before anything is published, which is the intended behaviour.

## Links in his onboarding

| Link | Result |
|---|---|
| `concierge.trendibizz.com/guide/bonsai-cladding` | 200 |
| `bonsaibim.org` | 200 |
| `blender.org/download` | 403 to a scripted request — Blender's bot protection; loads normally in a browser |
| `concierge.trendibizz.com/studio/` | 200 |
| `trendibizz.com` | 200 |
| `robots.txt` | 200 |

## Faults found and fixed in this audit

**1. The customer picker called an endpoint that does not exist.** Designs.tsx fetched
`/owner/crm/leads`; the enquiry list lives on `/owner/crm` (`{leads, appointments, tasks}`). The
`catch` swallowed the 404 and rendered "No enquiries yet", so a measured model could never be given
to a customer — the quoting feature was silently unusable. Now reads `/owner/crm`; live check returns
8 leads for Pukeko. Guard test: `api/tests/test_portal_calls_real_endpoints.py` reads the portal
source and requires every literal API path to exist in the API's route table (a complete path must
match exactly; a path ending in `/` may be a concatenation prefix). Proved with a probe file calling
`/owner/nope` — the test goes red.

**2. Mastodon was still in the product.** It has no credentials on this deployment: the bridge
answered `503`, the API passed it on as `502`, and the owner saw `error code: 502` from the edge.
The previous session's instruction was to delete it. Now removed completely: the three
`/owner/social/oauth/mastodon/*` endpoints, the three bridge calls, the `status` provider flag, the
legacy `owner.html` disconnect button, and the portal's mastodon special-case. Start now returns
`404`; `status.providers` lists only `facebook, google_business, instagram, linkedin,
linkedin_organization, tiktok, x`. Guard: `api/tests/test_mastodon_is_gone.py`.

Suite: **1074 passed**.

## Still outstanding (not blocking activation)

- `/healthz` and `/health` are not exposed publicly (404) — they are internal.
- DWG/PDF plans cannot be measured; only IFC.
- Conrad's login is still the demo address `pukeko-demo@trendibizz.com`.
