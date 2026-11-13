# Click-path audit — every surface a customer touches — 2026-11-13

Method: (1) call every owner-facing GET route on production with a real session —
`scripts/verify/probe_owner_routes.py`; (2) drive the Studio in a real headless Chromium
(Playwright) through every tab, the pause switch, the whole setup walkthrough, and the public
chat page; (3) read the resulting screenshots. Shell tests were not accepted as evidence for a
screen.

## What was clicked, and the result

| Surface | Result |
|---|---|
| Sign-in link (email → one click) | lands signed in, no password |
| Sidebar: Home, Setup, Permissions, Enquiries, Contacts, Bookings, Quotes, Products, Reports, Social, Marketing media, Designs | all render, no JS errors, no 5xx |
| Pause everything → confirm → resume | pauses, shows "Concierge is paused.", resumes |
| Setup: welcome → website → read → review → "Looks right" → install step → capability cards → "Open my workspace" | completes end to end |
| Review screen | 5 of 5 images drawn (logo now renders) |
| Public hosted chat | loads, greeting appears, message sends, conversation renders |
| Public chat flood guard | answers "You're sending messages quickly — please wait a moment" under repeated sends |
| Every owner GET route (43) | 34 ok, 0 x 5xx after the fix below (rest are POST-only or need path ids) |

Not covered here: the operator page `/owner-ui`, the CRM (separate app), and a real phone
scanning the QR. Those stay on the handoff's outstanding list.

## Bugs this audit found and fixed

**`GET /owner/contacts` returned 500** — the Contacts tab was dead. The query ordered by
`COALESCE(last_at, …)` where `last_at` is a *select alias*; Postgres only allows an alias as a
bare ORDER BY item, so it failed at prepare time with `column "last_at" does not exist`. Fixed by
repeating the subquery. Proved against a real Postgres 16 running the real schema: the old SQL
errors, the new SQL returns rows.

**Permissions was unreachable in the default layout** — it existed as a tab but had no sidebar
entry, so in the default Sidebar layout the consent page could not be opened at all. Added to the
Workspace group. This is the page where a business grants the rights everything else depends on.

**Every logo failed to render in production** — the API image was built from a *stale*
`api-requirements.lock` on the server that omitted `resvg_py`, so `rasterise_svg` silently
returned None for every logo and the owner was told "we found a logo on your site but could not
turn it into an image" — blaming the customer's website for our missing dependency. Three fixes:
the repo's lock and Dockerfile are now on the box; the image is rebuilt from them; and the
absent-renderer path logs loudly once instead of returning silence
(`api/tests/test_logo_renderer_present.py`). Verified in the new image (`resvg_py` renders a PNG)
and live (9,873-byte logo, brand accent picked up from it).

**Setup could not be completed: the website was rejected at save** — the reader accepts
`trendibizz.com`, then `PATCH /owner/onboarding/profile` answered 422 "Enter a public HTTPS
website address" for the identical text, leaving the customer stuck on the review screen after a
successful read. The validator now normalises exactly as `brand_from_site.normalise_site` does
(adds `https://`, upgrades `http://`) and still refuses credentials, fragments and junk
(`api/tests/test_profile_website_normalised.py`, mutation-checked).

## Tooling mistakes made during the audit (recorded, not hidden)

* Named a scratch script `inspect.py`, which shadowed the stdlib and broke Playwright's import.
* Used one-time sign-in links twice; the second run silently showed the sign-in form and looked
  like a broken app.
* Ran `git checkout -- app/brand_from_site.py` to undo a mutation and wiped an uncommitted fix in
  the same file; had to re-apply it.
* Trusted `innerText` diffs for the chat reply when the real state was the flood guard; the
  screenshot settled it.

## Standing harness

`scripts/verify/probe_owner_routes.py` calls every owner GET route with a real session, exits
non-zero on any 5xx, and never prints a token. It is the check that would have caught the
Contacts 500 before a customer did.

---

# Round two — the gaps I had listed as unverified

## Operator page `/owner-ui` — audited

Loaded signed in through an invite link and inventoried every control: 63 interactive elements
(enquiries, quotes, calendar, business setup, marketing media, business information, customer
channel permissions, phone, drafts, senders, social, invites). Page errors: **0**. 5xx: **0**.
The read-only refresh controls (`Refresh`, `Refresh text messages`, `Refresh email reply status`,
`Refresh social drafts`) were dispatched and completed without error. One 400 appeared on
`/owner/auth/invite` — that was my own doing: the page was opened with a one-time link the Studio
had already spent. A real tap on some controls is blocked by the sticky header in a headless
viewport; the handlers were exercised directly instead.

## CRM (`crm.trendibizz.com`) — entry verified, not click-audited

`/login` reaches Twenty's own welcome screen ("Welcome, Concierge.") with no JS errors and no 5xx.
The CRM is a vendored Twenty install, not our UI, and a full click-audit needs a CRM account we do
not hold. **Blocker recorded, not worked around:** credentials. Cloudflare also rate-limited this
IP (`error 1015`) during the audit, which is why the check was repeated through a real browser.

## QR code — decoded from the screen a customer actually sees

The earlier proof decoded a matrix built from the library. This closes the stronger claim: the QR
**as rendered on the live setup screen** was captured and decoded by an independent reader
(OpenCV in a throwaway container):

```
captured : the only 146x146 graphic on the install step
decoded  : 'https://chat.trendibizz.com/demo/trendi-meta-review'
shown    : https://chat.trendibizz.com/demo/trendi-meta-review
MATCH
```

That URL was then loaded in a phone viewport (390x844, mobile UA, touch) and the composer was
present, so the destination works on a phone. **The only part still unproven is a physical camera
scan** — that needs a phone, and it is the one gap I cannot close from here.

## The widget on trendibizz.com — hidden defect, decision needed

The homepage does load `chat.trendibizz.com/widget.js` (HTTP 200) and requests
`/api/v1/widget-config`. Nothing renders. The console shows why:

```
Executing inline script violates 'script-src 'self' https://static.cloudflareinsights.com https://chat.trendibizz.com'
Applying inline style violates 'style-src 'self''
```

The site's CSP is served from `/website/site/_headers` **inside the website container** — that file
is not in this repo, so the site's headers are another case of server drift. The widget needs
inline styles; the page forbids them; the widget gives no visible error, it simply never appears.

Fixing this on our own site means relaxing `style-src` (adding `'unsafe-inline'`) or changing the
widget to load an external stylesheet. That is a public security change, so it is **left for the
operator to decide**, not applied unilaterally. Note this is not only our site: **any customer site
with a strict CSP will lose the widget the same silent way**, so the install instructions should
name the directives the widget needs.
