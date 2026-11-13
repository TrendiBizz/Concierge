# Permission-only onboarding — redesign (2026-11-13)

**Principle.** The customer gives us their website and says *yes*. We do the work, show the result, and they confirm.
They never paste code, never type what we can read, never share a password, never hunt for a hidden page.

**Targets.** Live in ≤ 10 minutes · typed fields ≤ 2 (website, own mobile) · permission clicks ≤ 5 · code pasted: 0 · passwords shared with us: 0.

---------------------------------------------------------------------------------------------------

## 1. What a customer has to do today (observed 13 Nov, first real onboarding)

* **Two separate portals**: the setup wizard (`/studio`) and the permissions page (`/owner-ui`). Consent lives in a different place from setup; the health check even raised a false alarm because a tenant existed before its owner had consented.
* **Typing what we can read**: business name, website, greeting, notification email, phone (international form only: `0278817368` was refused with an unhelpful message), brand name, contact line, a **hex colour code**, a logo upload.
* **Website import is a separate click** after the website was already entered.
* **Paste an embed code** into their website (step 6). Nothing checks it worked.
* **Password** with a 12-character minimum and an unreadable error ("[object Object]").
* **Wrong defaults for a New Zealand business**: new tenants were `America/Chicago`, the server's country code is `1`. Both silently affect alert hours and phone numbers.
* **SMS** depended on a Mac app that jammed for two days; **phone** is one number per business with carrier forwarding left to the customer; **email** needs a Cloudflare rule per mailbox.
* **Stages**: invite email → password → setup → permissions (elsewhere) → test. At least five separate places.

Fixed today along the way: password counter and 12 prominence, red errors, password-manager support, readable validation messages, local phone numbers, NZ defaults for the new tenant, social service reattached after API restarts (a procedure gap: **always recreate `social` after recreating `api`**).

---------------------------------------------------------------------------------------------------

## 2. The flow: Discover → Propose → Permit → Provision → Verify → Go live

**Always visible: "Pause everything"** (the kill switch already exists server-side; surface it).

### 2.1 Discover (public information only, no permission needed)

| We find | From | Evidence 13 Nov |
|---|---|---|
| Services, hours, prices, FAQs | site crawl (already built, safe public-only fetch) | 125 chunks from 15 pages |
| Name | `og:site_name`, JSON-LD, `<title>` | trendibizz.com → "Trendi" |
| Logo | JSON-LD, header `<img>`, `apple-touch-icon`, `og:image` | trendibizz.com's header logo is **SVG (text-based)**; our media tools need PNG, so **render it to PNG with `resvg`** (a prebuilt wheel exists; Pillow/numpy already in the image), with a font caveat for `<text>` logos; fall back to the PNG touch icon |
| Accent colour | the dominant saturated colour **of the rendered logo**, then CSS variables | **not `theme-color`**: on trendibizz.com that is the page background (`#f5f7fb` / `#14213d`); that logo is purple (`#7142d6`) |
| Contact | `mailto:` / `tel:` / JSON-LD | Pukeko: `conrad@…`; Trendi: `admin@…` |
| Website platform | `generator` meta + path signals | **Pukeko = WordPress 7.1.4 + Elementor**; trendibizz.com = static site |
| Social accounts | links on the site | Trendi: Facebook, Instagram, LinkedIn, TikTok, YouTube; Pukeko: Facebook, Instagram |
| Timezone + country | `.nz` / address / Google Business Profile | replaces the `America/Chicago` + `1` defaults |
| Hours, phone, address, categories | Google Business Profile (Places API; needs a key and a budget; to evaluate) | not yet tested |
| Legal name | NZ company register (public; optional) | not yet tested |
| Persona, greeting, FAQ, booking rules | drafted by the assistant from the above | not yet built |

### 2.2 Propose: one review screen replaces wizard steps 2–5
"Here is your business as we understand it": name, logo, colour (a picker, never a hex box), contact line, greeting, hours, services.
One button **Looks right**; every field editable inline. Anything we could not find is the only thing we ask.

### 2.3 Permit: one Consent Hub (replaces the scattered permission page)
One page of capability cards. Each card says in plain words **what we will do, what data it touches, who can see it, how to undo it**.
The owner's own click is the only thing that ever writes a consent record (the platform already enforces this; we never write one for them).

| Capability | Permission route (customer clicks Approve) | We then do automatically |
|---|---|---|
| Chat on their website | WordPress: our plugin or a WordPress application password · Shopify / Wix / Webflow: an app they approve · Google Tag Manager: they grant access · anything else: **"email this to my web person"** with the exact snippet | install, then **check their live site** and show a tick |
| Email inbox | forward to the address we create (one-tap guides per provider); Gmail/Microsoft sign-in later (restricted-scope review needed) | mailbox, Cloudflare route, a test email round trip |
| Phone | (a) tap-to-dial carrier forwarding codes (no-answer/busy) with an automatic test call · (b) a number we provision (needs the carrier's API: ask Hero) | route, consent check, test call |
| Alerts | phone notifications through the portal (built today) + email | test alert |
| Customer texts | our SMS provider, pay per message (replaces the Mac connector) | sender setup, STOP/START handling |
| Calendar | Google / Microsoft sign-in | availability and booking rules |
| Social | existing sign-in flows | drafts only until they approve each post |
| Payments | Stripe Connect sign-in | quotes to invoices |
| Recording + AI notice | one consent showing the exact words callers will hear | greeting configured |

Consent ledger: versioned wording, time, who, from where; **revoke is one button** and takes effect at once (the bridge already re-checks telephone consent every 5 seconds).

### 2.4 Provision + Verify: a live checklist
Test alert received · test email round trip · chat detected on their site · test call · calendar visible.
Each failure shows a plain sentence and one button; we retry automatically. Go-live needs no more than **Switch on**.

---------------------------------------------------------------------------------------------------

## 3. How far "do it for them" goes (the answer to "why not a bot?")

1. **Official sign-in / API with consent** (default): the platform's own Approve screen, exact scopes shown, revocable.
2. **Guided one-tap**: tap-to-dial codes, deep links, copy-to-clipboard, auto-verify.
3. **Hand-off**: "email this to my web person" with a live check.
4. **Operator-assisted** (high-touch customers only): our team uses OpenBot-style tools on a screen-share, with the customer's written consent, nothing stored, session logged.

**Never**: an unattended bot that logs into a customer's website or email with their password. Credential custody, brittle UI automation, 2FA/captcha dead ends, platform terms and the reputational "a bot logged into my site" all say no.

---------------------------------------------------------------------------------------------------

## 4. Reuse (already built and proven)
Channel authorisations with audit trigger · go-live gate · owner invites · SSRF-safe public fetch (`public_fetch.py`) and crawler · reply addresses + Cloudflare routing · phone cutover script with rollback · outbound flood guard and kill switch · health check · portal push alerts · the brand store (`/owner/media/brand`, logo as a `data:image/` string up to 400,000 characters).

## 5. Plan

* **Phase 0 (this week):** site reader (name, logo as PNG, accent colour, contact, socials, platform, timezone, country) → single review screen; platform-aware install step with "email my web person" and a **live-site check**; hosted chat link + QR code for sites we cannot touch; NZ defaults derived from the site.
* **Phase 1:** Consent Hub unifying `/studio` and `/owner-ui`; automatic email provisioning; verification checklist; visible Pause; provider SMS.
* **Phase 2:** WordPress plugin first (Pukeko is on WordPress), then Shopify, Wix, Webflow, Tag Manager; Google Calendar and Business Profile.
* **Phase 3:** phone provisioning (ask Hero for an API) or the tap-to-dial forwarding assistant with an automatic test call.
* **Phase 4:** operator-assisted mode; measure time-to-live, fields typed, drop-off per step.

## 6. Risks to design for
NZ Privacy Act 2020 (collection notice, call-recording notice) · Unsolicited Electronic Messages Act (opt-out on every text and email) · Google restricted scopes review (Gmail) and Meta app review take weeks · platform terms of service · fetching customer URLs server-side must stay public-only (reuse `public_fetch`) · carrier forwarding codes differ by carrier and must be checked per carrier before promising one-tap.

## 7. Decisions needed from the operator
1. Platform order: WordPress first (Pukeko), then which of Shopify / Wix / Webflow?
2. Unify `/studio` and `/owner-ui` now (recommended) or keep both?
3. Ask Hero whether they have an API to provision numbers and report call status.
4. Budget OK for a Places API key and an SMS provider?
