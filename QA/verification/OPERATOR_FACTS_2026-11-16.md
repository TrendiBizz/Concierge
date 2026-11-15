# Operator facts re-checked live — 2026-11-16

Read-only checks done before handing the Search Console / Stripe decisions back to Jo. Nothing was
changed in Stripe, Search Console or Bing; no purchase was made.

## Search Console / Bing (worklist item 7)

| Check | Result |
|---|---|
| `dig TXT trendibizz.com` | contains `google-site-verification=avVhzA1EiofmOxiN_MaeFFNEsykt1q8QAfbrLBSStMA` |
| `https://trendibizz.com/sitemap.xml` | HTTP 200, 43 `<loc>` entries, lastmods 2026-11-15 |
| `https://trendibizz.com/robots.txt` | allows Googlebot/Bingbot/OAI-SearchBot/PerplexityBot/Claude-SearchBot, blocks training crawlers |
| Bing verification TXT | **absent** — `tiktok-developers`, `ahrefs`, `brevo`, `google` are the only TXT records |
| Nameservers | `vern.ns.cloudflare.com`, `gigi.ns.cloudflare.com` (Cloudflare) |

So Google ownership is very likely already proven (the TXT is present and stable), and Bing is not.
The old item 7 wording — "verify the property" for both — was half-wrong: the Google half is probably
just "add the sitemap"; the Bing half is a real setup step.

## Pricing and tax (worklist items 1 and 2)

Live `products.js` (matches the repo; `verify-deploy.sh` is green):

```
concierge: {
  checkout: true,
  monthly: { price: 250,  stripeLink: "https://buy.stripe.com/dRm7sM6GzeDz9he3UA04802" },
  yearly:  { price: 2700, stripeLink: "https://buy.stripe.com/6oU28s8OH7b76528aQ04804" }
}
```

All four buy links return **HTTP 200**:

- Concierge monthly `dRm7sM6GzeDz9he3UA04802`
- Concierge yearly `6oU28s8OH7b76528aQ04804`
- SEO monthly `28E8wRbntdSjcsQg7RcEw03`
- Deposit `28EcN7bnt6pRgJ6f3NcEw04`

**Item 2 is closed**: the yearly link is not empty. The in-file comment records Jo's 2026-11-15
direction ("yearly is buyable from day one"), the Stripe price id (`price_1UbnwwJVm2iwIxUdMoJ9g2Ve`,
USD 2,700/year) and "automatic tax on". `/pricing` and `/concierge` both advertise it, so copy and
link agree. What remains is Jo confirming yearly is still wanted, not a code defect.

**Item 1 stands, and the page makes it worse than "no page mentions GST".** Both the pricing cards and
the card-level blurb say "Prices in USD." The FAQ entry that asks *"Do prices include tax?"* answers
literally `Prices are in USD. ` — it does not answer the question it asks. Stripe's checkout adds tax
on top (measured 2026-11-15: $250 → $287.50, i.e. 15%); the live checkout page is JS-rendered, so that
15% figure is still the 15 Nov measurement, not a fresh scrape.

The health guard `site:prices` (`scripts/vps/healthcheck.py:402`) forbids the literal string `GST` on
`/pricing` and `/terms` and compares the cards against `products.js`. So:

- **Option A — tax-inclusive prices in Stripe.** Customer pays exactly the advertised number; the
  invoice shows the tax component. No repo copy change, guard stays green, totals match the page.
- **Option B — keep tax exclusive, say so.** Change the FAQ answer to e.g. "Prices are in USD; sales
  tax, where it applies, is added at checkout." Accurate, guard-safe (no "GST"), but the advertised
  number still is not what the customer pays.

Either way the FAQ answer must stop being a non-answer. The amounts themselves are not in conflict
with `products.js` (cards and plan data agree), so nothing needs a price edit in the repo today.
