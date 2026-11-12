# ChatGPT Business Hub kit — trendibizz.com (prepared 2026-11-13)

Source: the Rankability "ChatGPT Profile Audit Kit" (PDF, audit prompt, product-feed prompt, CSV
template; Business Hub is in beta, screens can change). This file records what is **done on the
website side**, what **only the owner can do inside the signed-in ChatGPT Business Hub**, and the two
prompts pre-filled for the Claude browser extension.

## 1. Website-side status (all verified live, 2026-11-13)

| Kit item | State | Evidence |
|---|---|---|
| Product feed file (CSV, 9 required columns + optional) | **Done** | `https://trendibizz.com/chatgpt-products.csv`, 3 rows, `text/csv`, no BOM, 0 validation problems |
| Every feed link loads, 200, no redirect | **Done** | 15 of 15 links OK (product, image, seller, terms, privacy) |
| Product images: direct PNG, one per product | **Done** | `/brand/products/<item_id>.png`, 1200x1200, `image/png` |
| Prices match the live site, `97.00 USD` format | **Done** | `400.00 USD`, `4080.00 USD`, `1500.00 USD` match /ai-receptionist-cost and /pricing |
| Availability uses the five allowed values | **Done** | `in_stock` |
| Hosted URL so the feed stays current | **Done** | regenerate with `scripts/build_chatgpt_product_feed.py`, then redeploy (section 5) |
| Organization / Offer / Service schema | **Already present** | JSON-LD on `/`, `/pricing`, `/concierge`, `/ai-receptionist-cost`, `/about`, `/contact` |
| LocalBusiness schema | Not applicable | online-only / software business, no storefront |
| robots.txt allows OAI-SearchBot | **Yes** | already allowed |
| robots.txt allows ChatGPT-User | **Done in the origin** | explicit `Allow: /` added; the public copy is held in Cloudflare's cache until it expires (section 4) |
| robots.txt allows GPTBot | **No, by existing policy** | see decision in section 3 |
| `llms.txt` accurate | **Fixed** | the cost line said "USD 00/month"; now "USD $400/month" |
| Sitemap | Already present | `https://trendibizz.com/sitemap.xml` |

Left out of the feed on purpose (kit rules): **penetration testing** (quoted on enquiry, no listed
price) and the **USD $1,000 deposit** (a payment option for the SEO service, not a product).
Choices made that were not specified: brand and seller name `Trendi`; Concierge-yearly links to
`/ai-receptionist-cost` (the page that states the yearly price), Concierge-monthly to `/concierge`,
SEO to `/seo`; `target_countries` left empty so the countries are chosen in the hub; category
`Software`, `is_digital` true.

## 2. Only the owner can do these (signed-in ChatGPT Business Hub)

The assistant cannot sign in to ChatGPT or open the hub for you, and the kit's own rules say not to.
Do these in Chrome with the Claude extension, using the prompts in section 6.

1. **Claim / verify the business profile** (blue "Claimed business" check). The name cannot be edited
   after claiming, so claim under the real name: **Trendi** (legal entity TRENDI LIMITED, New Zealand).
2. **Description (300-character limit, cuts off silently).** Use this text, 262 characters:
   > Trendi helps businesses get found and get answered. Concierge is an AI receptionist for small business: website chat, enquiry capture, bookings and follow-up. We also provide done-for-you SEO and AI visibility. Based in New Zealand, serving businesses worldwide.
3. **Category:** one only; pick the closest software / business-services option and match the Google
   listing if the same option exists.
4. **Photos:** first photo is the cover; upload squares of 1080x1080 or larger, including the logo
   (no logo field yet). The three product PNGs above can be reused. Add real photos of the team or
   product screens; avoid stock images. Click Submit after photo changes.
5. **Contact:** phone, a business email someone reads, `https://trendibizz.com`. Address and hours
   must match the website and any Google listing word for word. (A profile address cannot be hidden.)
6. **Products page:** add the feed. Prefer a **hosted URL** feed pointing at
   `https://trendibizz.com/chatgpt-products.csv` so prices stay current; otherwise upload the file.
   Confirm only when the preview shows 0 rows with errors; check the Issues tab afterwards.
7. **Look again after a week:** Overview (Mentions, Profile views, Website clicks) and the Agent
   builder's availability.

## 3. Decision needed: AI training crawlers

The site deliberately blocks training crawlers (`GPTBot`, `ClaudeBot`, `CCBot`, `Google-Extended`,
`Applebot-Extended`, `Bytespider`, `Amazonbot`, `FacebookBot`) while allowing AI *search* and
user-triggered fetchers (`OAI-SearchBot`, `ChatGPT-User`, `Claude-SearchBot`, `Claude-User`,
`PerplexityBot`, `Perplexity-User`). The kit's checklist asks for GPTBot to be allowed, so an audit
will mark that line down. Blocking GPTBot does not stop OAI-SearchBot (the crawler that controls
search appearance), so this does not cost visibility in ChatGPT search. **Left as is.** To allow
training crawlers instead, change `User-agent: GPTBot` (and `ClaudeBot`) to `Allow: /` in
`website/robots.txt` and redeploy. This is a policy choice, not a bug.

## 4. Known timing item

Cloudflare caches `/robots.txt`. Right after deploy the public URL still returned the old copy
(`cf-cache-status: HIT`) while the origin already had the new lines. It will refresh when the cache
expires; the current API token cannot purge cache. Check with:
`curl -s https://trendibizz.com/robots.txt | grep -c ChatGPT-User` (expect 1; `?cb=1` bypasses the cache).

## 5. Keeping the feed current

Prices are defined in `scripts/build_chatgpt_product_feed.py` **and** on the site pages. When a price
changes: edit both, run `python3 scripts/build_chatgpt_product_feed.py` (needs Pillow for the images;
`--check` validates only), then deploy `website/chatgpt-products.csv`, `website/brand/products/*.png`
(and `robots.txt` / `llms.txt` when changed) to the VPS **site root**
`/opt/trendi/releases/20261108-vps/website/site/` (not the project root above it) and `chmod -R a+rX`.
Verify with the live link check used on 2026-11-13 (every URL 200, image `image/png`, prices match).

## 6. The two prompts, pre-filled (paste into the Claude browser extension on the Hub tab)

### 6a. Audit (read-only)
```
Audit my ChatGPT business profile. The ChatGPT Business hub is open in my current tab. If it isn't, or I'm not signed in, stop and tell me.

Business to audit: Trendi (the one that's open)
My website: https://trendibizz.com
My Google listing: find it by searching "Trendi trendibizz.com"; if none exists, say so
Type of business: online-only or software

Rules:
- This is a read-only audit. Don't save, submit, upload, delete or dismiss anything, and don't change settings. If a page shows an active Save button just from opening it, leave without saving.
- Report only what you saw. If you couldn't check something, say so; don't guess.
- Three things are platform limits, not defects, so note them without marking the profile down: the business name can't be edited, the address can't be hidden or set as a service area, and the Get directions button always shows.
- Also note, without marking down: trendibizz.com deliberately blocks the training crawlers GPTBot and ClaudeBot in robots.txt while allowing OAI-SearchBot, ChatGPT-User, Claude-SearchBot and Claude-User.
- When you finish, return my tab to the profile's Overview page.

[then the "Where to look", "What to check" and "Report format" sections exactly as in 1015c715-chatgpt-profile-audit-prompt.txt]
```
The full unmodified prompt is the attached `chatgpt-profile-audit-prompt.txt`; only the four bracketed
lines and the one extra robots note above differ.

### 6b. Product feed
```
Add my products to my ChatGPT Business profile using the Products page in the ChatGPT Business hub (open in my current tab, or tell me if it isn't).

Business / brand name: Trendi
Where my products and prices are listed: https://trendibizz.com/ai-receptionist-cost and https://trendibizz.com/pricing. A finished, validated feed already exists at https://trendibizz.com/chatgpt-products.csv; check it against those pages instead of rebuilding it.
What to list: every paid plan with a listed price (Concierge monthly and yearly, SEO and AI visibility monthly). Skip penetration testing (quoted on enquiry, no listed price) and the USD $1,000 deposit (a payment option, not a product).
Countries I sell in and currency: worldwide, USD
Where each product should link: product page / pricing page (as in the CSV)
Image to use: the PNGs already listed in the CSV (https://trendibizz.com/brand/products/)
Physical or digital: digital or software

[then the "Steps" and the closing rule exactly as in 036d17a7-chatgpt-product-feed-prompt.txt]
In step 5, prefer a hosted URL feed pointing at https://trendibizz.com/chatgpt-products.csv if the hub offers it; otherwise upload the CSV.
```

## 7. What exists for Claude and other assistants (honest scope)

There is no Anthropic equivalent of the ChatGPT Business Hub profile or product feed that this
project can register with. What is in place for Claude and others: `Claude-SearchBot` and
`Claude-User` allowed in robots.txt, `llms.txt` (now with the correct price), a sitemap, and
Organization / Offer / FAQ schema, all of which any assistant can read. Comparable listings that
need the owner's own accounts and are **not done**: Google Business Profile, Bing Places and Bing
Webmaster Tools (with IndexNow), Apple Business Connect, and Google Merchant Center for a product feed.
