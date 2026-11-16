# Live payment links deactivated; site still points at them — 2026-11-16

> **RESOLVED 2026-11-16 in commit `912452f`.** Jo created two tax-inclusive USD links on
> `acct_1UUZfy` and deactivated the old ones on purpose. `/pricing` and `/seo` now point at
> `buy.stripe.com/00wcN70IP4hJdwU8FpcEw06` (USD 500/month) and `buy.stripe.com/7sY7sNgHN6pR50obRBcEw05`
> (USD 500 deposit); every SEO price on the site is USD 500, tax included, no GST wording.
> Deployed with `deploy-site.sh` + `sync-tooling.sh`; `verify-deploy.sh` exit 0. Live proof: both new
> links appear twice on `https://trendibizz.com/pricing`; no `28E8wR`/`28EcN7` on any HTML page,
> `llms.txt` or `sitemap.xml`; both Stripe links return HTTP 200 "Stripe Checkout", not "no longer
> active". Cause of the original defect: Stripe-side deactivation while the site kept the old URLs.
> Regression guard: `healthcheck.py` `site:prices` now fails on either retired link or a non-answer tax
> FAQ (`api/tests/test_site_price_drift.py`, mutation-checked: emptying `RETIRED_PAYMENT_LINKS` turns
> `test_a_retired_stripe_link_is_reported` red).
> **Open at time of writing:** Cloudflare was still serving a cached `/products.js` (cf-cache-status HIT,
> cached 02:02 GMT) containing the old links although the origin is correct; it ages out on its own or
> needs a purge by someone with Cloudflare access.

The text below is the original incident record, kept as written.

## What is live right now (measured 2026-11-16 15:03 NZDT)

| CTA on the site | Link | Rendered result |
|---|---|---|
| `/pricing` "Start monthly, USD $1,500" (SEO) | `buy.stripe.com/28E8wRbntdSjcsQg7RcEw03` | **The link is no longer active.** |
| `/pricing` "Pay deposit" (USD $1,000) | `buy.stripe.com/28EcN7bnt6pRgJ6f3NcEw04` | **The link is no longer active.** |
| `/concierge` + `/pricing` Concierge monthly | `buy.stripe.com/dRm7sM6GzeDz9he3UA04802` | live — "$250.00 per month" |
| `/concierge` + `/pricing` Concierge yearly | `buy.stripe.com/6oU28s8OH7b76528aQ04804` | live — "$2,700.00 per year" |

## This is a regression, not a previous state

`/tmp/co_pricing_seo_monthly_28E8wR_.png`, captured by the 2026-11-15 session at 14:39, shows the
**same** `28E8wR…` URL live, with:

```
Trendi — Monthly                        $1,500.00
Subtotal                                $1,500.00
GST (15%)                                 $225.00
Total due today                         $1,725.00
```

That is the overcharge this work stream exists to remove. At 15:03 today the same URL renders
"The link is no longer active." So the two SEO-account links (`acct_1UUZfyRoqx25tip0` — the
Concierge links live on the separate `acct_1PcJbgJVm2iwIxUd`) were deactivated between 2026-11-15
15:48 and 2026-11-16 15:03.

## The state of the site has not changed at all

`git status` clean, local HEAD == `origin/main` == `08217fb`, and inside the repo:

- `website/products.js` still carries `dRm7sM…` and `6oU28s…`;
- `website/pricing.html` still carries `28E8wR…` and `28EcN7…`;
- the "Do prices include tax?" FAQ still answers only `Prices are in USD. `;
- `KEY=./Concierge ./scripts/vps/verify-deploy.sh` → `OK: repo and box agree`.

So whatever was changed today happened in Stripe only. The website was not updated to the
replacement links, which means the two SEO CTAs — including the one on `/pricing` that sells the
$1,500/month retainer — currently dead-end the buyer.

## What is needed to close this

1. **The two replacement SEO links** (`buy.stripe.com/...`), or reactivation of the two retired
   ones. Not present in this repo, and not recoverable from the Chrome profile on this machine —
   its last Stripe dashboard visits are 2026-11-15 15:48, before the change.
2. Confirmation that the Concierge prices are now tax-inclusive. Their checkout pages show
   `$250.00` / `$2,700.00` before an address is entered, which does not distinguish inclusive from
   exclusive — Stripe only shows the tax line once it knows the customer's location.

## Gap this exposed

Nothing in the gates checks that a published buy link still opens a checkout. `site:prices` compares
card text against `products.js` and forbids the word "GST"; `site_seo` checks the page contract.
Both stayed green while two of four payment links were dead. A plain HTTP fetch cannot detect it
either — a retired link still returns 200 and renders the notice in JavaScript, so only a rendered
page or an authenticated Stripe lookup can tell. The durable fix is a monitor using a restricted
Stripe key (`payment_links` read) in the health check; that is a decision about holding a Stripe
key, so it is recorded here rather than added silently.
