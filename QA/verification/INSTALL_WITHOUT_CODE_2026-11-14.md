# Stop telling tradesmen to find a web person

The last step of onboarding handed the customer a `<script>` tag, told them to paste it before
`</body>`, and — if the site was one we could not identify — suggested they **send it to whoever
looks after the website**. For a builder, a plumber or a kitchen fitter that is where setup ends:
most have never edited their site, many have nobody to send it to, and the ones who do wait days
for a stranger to act. It also put our install in the hands of a third party we cannot hold to
anything.

## What the screen does now

Three doors, in the order a non-technical person can use them.

1. **"Easiest: we put it on your site for you."** A short form — their website, what it is built
   with (they can answer *I am not sure*), their name, and a phone number. One button files the
   request. We install it and email them when it is live. Nobody else is involved.
2. **"Or use a chat page we host — working right now."** No site access at all: a link to share,
   a QR code to print, and copy-to-clipboard. This is a real answer, not a consolation prize.
3. **Behind a disclosure: the one line of code.** For the minority who do edit their site or
   already have someone who does. The Content-Security-Policy note lives here, where it matters,
   instead of frightening everybody on the way past.

The API also stopped describing platforms as *"Email this to my web person"*: WordPress, Wix,
Squarespace, Shopify and Webflow now each carry an instruction for their own dashboard, and
anything unrecognised says **"We can add it for you"**.

## How it works

* `install_requests` table: business, website, platform, contact name/phone, note, status.
* `POST /owner/install-request` (owner session) files it and emails the operator.
* `GET /owner/install-requests` — the customer can see what they asked for and where it is.
* `GET /admin/install-requests?status=` and `POST /admin/install-requests/{id}/status` — the
  operator's queue, `new → contacted → done` (or `cannot`).

## Live proof (production, fictitious business)

| Step | Result |
|---|---|
| Customer files the request (WordPress, phone, note) | **200**, `{"status":"new"}`, id returned |
| Operator queue `GET /admin/install-requests` | shows *Trendi Bizz (fictitious test business)*, `https://trendibizz.com`, `wordpress`, the phone number, `new` |
| Operator email *"Install request — Trendi Bizz…"* | **sent**, attempts 1, to admin@trendibizz.com |
| Operator closes it (`status=done`) | accepted |

Tests: `tests/test_install_requests.py` (6) — including one that reads the Studio source and fails
if any of the three "find someone else" phrases ever come back. Suite **1151**.

## Also removed: the cladding story

Every customer's welcome email explained 3D cladding takeoff (Blender, Bonsai, `.ifc`) as if it
were the product, and the Designs screen opened the same way. That is one client's workflow, not
the product's. The invitation now describes what Concierge does for any trade; the takeoff wording
survives only where the feature actually is, described neutrally, and it is no longer in the email
or the landing text of Designs.

## Still to do for the zero-knowledge promise

The "we do it" path is a real, recorded, queued job — but a person still does the work. The next
step to make it genuinely instant is a WordPress plugin (Plugins → Add New → search → Install →
Activate, no code, inside the dashboard they already use), then the equivalent for Wix and
Squarespace. Tracked in the handoff.
