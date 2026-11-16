# Pricing: tax becomes inclusive — decision and pending work (2026-11-16)

## Decision (Jo, 2026-11-16)

> "we include the tax for nzd so fix this"

Resolved as **option A**: the USD price on the page is the total the customer pays, for every
customer, with any tax already inside that number. Prices stay USD $250 / $2,700 / $1,500 / $1,000.
No currency change: NZ customers are not switched to NZD; the NZD/GST wording stays off the site.

Jo will make the Stripe changes; this record is the exact list, so the repo side can be finished the
moment the new links exist.

## Why this cannot be finished from the repo alone

The overcharge is created by Stripe, not by the page. `api.env` on the box holds only
`STRIPE_WEBHOOK_SECRET` — there is no live secret key, so prices and Payment Links cannot be changed
by any script here. Checkout runs through four hosted Payment Links:

| Plan | Advertised | Current payment link |
|---|---|---|
| Concierge monthly | USD 250 / month | `https://buy.stripe.com/dRm7sM6GzeDz9he3UA04802` |
| Concierge yearly | USD 2,700 / year | `https://buy.stripe.com/6oU28s8OH7b76528aQ04804` |
| SEO monthly | USD 1,500 / month | `https://buy.stripe.com/28E8wRbntdSjcsQg7RcEw03` |
| SEO deposit | USD 1,000 | `https://buy.stripe.com/28EcN7bnt6pRgJ6f3NcEw04` |

Measured 2026-11-15: the first adds 15% at checkout ($250 → $287.50), and the same on the other
three. That is `tax_behavior = exclusive` on the prices.

## The exact Stripe change (Jo)

A Stripe price's tax behaviour **cannot be edited after creation**. Make a new price per plan:

1. **Stripe → Product catalog → [product] → Add another price.** For each of the four:
   - Concierge: `USD 250.00`, recurring monthly, **Tax behavior: Inclusive**
   - Concierge: `USD 2,700.00`, recurring yearly, **Inclusive**
   - SEO and AI visibility: `USD 1,500.00`, recurring monthly, **Inclusive**
   - SEO deposit: `USD 1,000.00`, one-time, **Inclusive**
2. **Stripe → Payment links** — create a new link for each (or edit each link's line item) pointing
   at the new inclusive price, with **Automatic tax on**, exactly as the current links have. Keep the
   old links alive until the new ones are confirmed working, then deactivate the old ones.
3. Archive the four old exclusive prices so nobody picks them again.

**Cost of the decision, stated plainly:** with an inclusive price, an NZ sale of USD 250 is
`250 / 1.15 ≈ 217.39` net of GST instead of the full 250 — about 13% less revenue per sale than
today's exclusive price, where the customer absorbs the 15%. That is what "include the tax" means in
practice; it is a deliberate choice, not a side effect.

## The repo change this unlocks (me, same session once links exist)

1. `website/products.js` — replace the two concierge `stripeLink` values; comment the new price ids.
2. `website/pricing.html` — the two SEO/deposit buy links; the "Do prices include tax?" FAQ, which
   currently answers only `Prices are in USD. `, becomes a real answer: "Yes — the price shown is the
   full amount you pay. Prices are in USD and include tax." Also the fine print "Prices in USD."
   → "Prices in USD, tax included." **The word "GST" must not appear** — `site:prices` fails on it.
3. A test in `api/tests/` that fails if the tax FAQ ever goes back to a non-answer (answer shorter
   than a sentence, or missing "include"/"plus"), mutation-checked.
4. `site_seo.py check`, suite, `deploy-site.sh`, `verify-deploy.sh`.

**Order matters:** the copy must not ship before Stripe is inclusive, or the page would claim
"tax included" while checkout still adds 15%. The copy change waits for the links.
