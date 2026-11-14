# The blank pages, the Social errors, and the Cloudflare page printed at a customer

Five reports in one evening, all real. What was underneath them:

## 1. Social went blank, and other lazy pages could too

**Cause.** My deploy used `rsync --delete` over `/opt/trendi/shared/studio`, and `/studio/assets/*`
was served with **no cache headers at all**. So: a window opened before a deploy kept an old hash,
the deploy deleted that chunk, the lazy `import()` of `Social-*.js` answered **404**, the promise
rejected, React unmounted the tree → an empty dark page, no message. The HTML itself was already
`no-store`, so this was purely the assets.

**Fix, in three parts.**
1. Assets are content-addressed, so they are now `Cache-Control: public, max-age=31536000, immutable`.
2. Deploys no longer delete old chunks; anything older than 7 days is pruned instead.
3. The app now listens for `vite:preloadError` and reloads **once** (guarded by `sessionStorage`
   so a bad build cannot loop), and an `ErrorBoundary` shows "That page did not load" with a
   Reload button instead of a blank screen.

**Proof.** Blocked the real `Engage-BXHhnJTA.js` chunk with a 404: the page auto-reloaded and
rendered (no blank page). Normal Social tab renders 1,009 characters.

## 2. "Social service unavailable" — `docker ps` was lying

**Cause.** `social` runs with `network_mode: service:api`, i.e. inside the api container's network
namespace. I rebuilt and recreated **api alone**, so `social` was left running in the namespace of
a container that no longer existed. It stayed "Up" and the api could not reach `127.0.0.1:4390`.

**Fix.** `scripts/vps/redeploy-api.sh` — the only supported way to deploy the api. It always
recreates `api social` together and then *proves* social answers from inside the api container.

**Proof.** `POST /owner/social/oauth/{x,tiktok}/start` returned **503** before; after recreating
social, providers report all seven enabled and `Connect x` opens `https://x.com/i/oauth2/authorize`
(verified in Chrome, popup URL captured). Side effect: the previously connected TikTok account was
in the old container's anonymous volume, so it needs reconnecting.

## 3. "Connect X gave a tiktok screen"

Same cause. With the social process stranded, the popup kept whatever page it had. After the fix,
`Connect x` → **x.com/i/oauth2/authorize** and `Connect linkedin organization` →
**www.linkedin.com/oauth/v2/authorization**. Verified both.

## 4. LinkedIn "Bummer, something went wrong"

Our request is correct: `client_id=78cjxz2hf0d5wl`, `redirect_uri=https://concierge.trendibizz.com/owner/social/oauth/callback`,
`scope=r_organization_admin w_organization_social`. LinkedIn's own error page means **their app
configuration** rejects it — the redirect URL must be registered on the app, and
`w_organization_social` requires the app to have the *Share on LinkedIn* / *Marketing Developer
Platform* product approved. That is in LinkedIn's developer console, not our code, so it is an
open item for the operator with the exact values above.

## 5. The Media page printed Cloudflare's error page at the customer

**Cause.** Two faults. The media render call waited **200 seconds**, but Cloudflare abandons an
origin at about 100 and serves its own "The origin web server returned an invalid or incomplete
response to Cloudflare" page. And each page carried its **own copy** of the fetch helper, so my
first fix only changed one of six — the Media page passed the raw text straight through.

**Fix.** `RENDER_TIMEOUT_SECONDS = 85` (finish before the edge gives up) with honest messages for
timeout/unavailable; and one shared `api.ts` with `describeFailure()`, used by every page. Edge
statuses (502/504/520–524) now read *"That took too long at our end (520). Nothing was lost — try
again."* Upstream HTML is never rendered.

**Proof.** Intercepted `/owner/media/assets` with a 520 + Cloudflare's exact HTML: the page shows
the friendly sentence and **zero** occurrences of "Cloudflare".

## Also fixed

* **Tickbox removed from Bookings** — pressing *Save booking settings* is the acknowledgement.
* **Duplicate page headings** — the hero names the page, then the page named it again as an H1
  (`Social`, `Social`). All nine removed; every page now has exactly one H1 (verified 1 on Social,
  Marketing media, Bookings, Reports, Team, Your CRM, Quotes, Contacts, Products, Designs).
* **Setup had no heading at all** once its duplicate was removed: the hero was hidden on that tab.
  Restored — Setup shows one H1 again.

Guards: `tests/test_studio_shell.py` now 15, covering preload recovery, the error boundary,
immutable assets, the recreate-social rule, "no page reimplements the api helper", the 85s
deadline, and one-heading-per-page. Mutated the deadline back to 200s and watched
`test_media_rendering_finishes_before_the_edge_gives_up` go **red**. Suite **1168**.
