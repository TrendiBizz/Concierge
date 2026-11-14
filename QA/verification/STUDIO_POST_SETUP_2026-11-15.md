# Studio after setup: green blocks, the wizard that came back, and an edge error printed raw

## 1. The three green blocks (Marketing media and the post picker)

Not a rendering bug. The file itself is solid green:

```
/tmp/upload.jpg: JPEG image data, 320x320, comment "Lavc62.28.102"
size: (320, 320) | most common colours: [(102400, (0, 129, 0))]
```

One 823-byte, 320×320, single-colour JPEG — encoded by FFmpeg (`Lavc62.28.102`), the classic
`ffmpeg -f lavfi -i color=green` placeholder — uploaded three times by `support@trendibizz.com`
on 14 Nov (06:38 and 06:53 UTC = 19:38 and 19:53 NZDT, which is what the cards showed). Three rows,
one storage path: the dedupe keeps one file and the rows are per upload.

So the tiles were truthful. What made them unreadable was our own caption: the upload handler
built its name from a hash and **discarded the customer's filename**, so every tile said "Image".

**Fixed:** `media_assets.original_name` (new column), `safe_original_name()` in
`api/app/media_studio.py` (strips any directory part, control characters and separators, caps at
120 chars), the Studio sends `X-Filename` (URI-encoded) with the raw-body upload, and the tile
shows the name under the kind badge, with it as the alt/title text in the post picker.
The three test rows were deleted (`DELETE 3`; one real showcase asset remains).

Guards: `api/tests/test_media_upload_name.py` (5). Mutation: making `safe_original_name` return
`""` turns 4 of them red; restored → 5 passed.

## 2. "Set up your business" shown to a business that is set up

`Setup` always started at step 1 and always rendered the Welcome wizard, regardless of state, so
ACME Ltd — name, website, notifications, channels all present — was told to set itself up again.

**Fixed:** `const alreadySetUp = Boolean(business.name.trim() && business.site_url.trim())`. When
true, step 1 is a summary — "<business> is set up", the website, the notification address — with
*Edit business details* and *Back to dashboard*. The wizard itself is unchanged and reachable.

## 3. The Permissions page explained the delivery chain to the owner

Owners were shown eleven engineering steps (Cloudflare routing, DKIM/DMARC, worker intake) as the
page's main content. **Fixed:** those checks now sit behind a `<details>` disclosure labelled
"Show the delivery-chain checks", and the page leads with either "Every step of inbound email is
working for this business." or a count of what is blocked. Toggles and their Help text are
unchanged.

Guards: `api/tests/test_setup_after_setup.py` (3, covering §2, §3 and §4). Mutation: un-gating the
welcome step (`{step === 1 ? (`) turns the guard red; restored → 3 passed.

## 4. Cloudflare's own error sentence, printed at the owner

The Home dashboard carried *"The origin web server returned an invalid or incomplete response to
Cloudflare. This typically indicates the origin is overloaded or misconfigured."*

The cause was a real, transient edge 502: `trendi-api-1`, `trendi-website-1` and `trendi-social-1`
had all been restarted minutes earlier (two deploys were landing at once — the other agent was
deploying the same site). At the time of the screenshot the API was healthy
(`trendi-api-1 Up (healthy)`, health check `ok 39, warn 1, fail 0`, `/studio` 200), so nothing was
broken by the time it was reported.

The defect is that a 5xx `detail` field was passed straight through to the screen.
**Fixed:** `describeFailure()` now trusts a `detail` only for `status < 500`, free of HTML and
under 200 characters; everything else becomes "That took too long at our end (502). Nothing was
lost — try again." Guard in `test_setup_after_setup.py`; mutation restoring `Boolean(detail)` made
it red.

## Deploy

`api/app/media_studio.py` + `api/app/schema.sql` (ALTER applied live) → `redeploy-api.sh`;
portal → `deploy-studio.sh` (three `/studio` 200s). Live bundle contains "is set up",
"Show the delivery-chain checks" and `X-Filename`. Suite: **1203 passed, 36 skipped**.

## 5. Why a hard refresh changed nothing: the service worker

After the deploy above, the server was serving the new build (`index-Citt6YJl.js` contained the
setup summary, `Permissions-B_ZHRu89.js` contained the disclosure) and the owner still saw the old
screens after Ctrl+R. The cause was `web/portal/public/sw.js`:

- `const CACHE = 'concierge-studio-v1'` — a constant, so **nothing ever invalidated the cache**
  across deploys, and `activate` only deleted caches whose name differed from itself.
- navigation was network-first **with a cached-shell fallback**, so the one time the network
  hiccuped (an API restart during the deploy) the owner was served yesterday's `index.html` from
  the worker's own cache — which pulled yesterday's hashed chunks, themselves cache-first.
- the file was served with **no `Cache-Control` at all** and Cloudflare answered `cf-cache-status:
  HIT`, so even the worker script itself could not be refreshed promptly.

**Fixed:**

- `sw-v2.js` (new URL, so an old registration cannot answer for it): cache name carries the build
  id (`concierge-studio-<build>`), a navigation is `fetch(..., {cache: 'no-store'})` and the cached
  shell is used **only** when `navigator.onLine === false`, and `activate` purges every other cache.
- Registration: `updateViaCache: 'none'`, `getRegistrations()` unregisters any other `/studio/`
  worker, and a one-time `controllerchange` reload moves the tab onto the new build by itself.
- `deploy-studio.sh` stamps `__BUILD__` with the new asset hash — **before** the copy. The first
  attempt stamped after the rsync to staging, so staging shipped a literal `__BUILD__`; caught by
  comparing the served file (`const CACHE = 'concierge-studio-__BUILD__'`) with the deployed one.
- `/studio/sw-v2.js` is served `Cache-Control: no-cache` + `Service-Worker-Allowed: /studio/`
  (measured after: `cf-cache-status: EXPIRED`, revalidated every visit).

Proof on the live site: `const CACHE = 'concierge-studio-CshImAud'`, old `/studio/sw.js` no longer
exists on disk (404s), shell carries the setup fix and the `sw-v2` registration.

Guard: `test_the_service_worker_can_never_pin_a_browser_to_an_old_build` — asserts the stamped name,
the no-store navigation, the offline-only fallback, that `sw.js` is gone, the `updateViaCache`
registration, the unregister call, and that the stamp precedes the copy. Mutations that turn it red:
dropping `{cache: 'no-store'}`, and moving the stamp after the copy.

## 6. The Permissions page should not exist after setup

§3 hid the delivery chain behind a disclosure, which was not the ask. The owner's words: *"this
screen and permissions do not need to be shown on the screen after setup they should be available
to use but why are we displaying this"* — a console of eleven switches does not belong in the
sidebar of a business that finished setup, whatever it says inside.

**Fixed by deleting the page and asking where the channel is used:**

- `Permissions.tsx` is gone; the sidebar entry, the `<Tab value="permissions">`, the route and the
  `PermissionsPage` lazy import are all removed.
- New `ChannelAsk` component renders on the page that needs the channel and only when that channel
  is not yet allowed: **Texts** asks for `sms_read`/`sms_send`, **Enquiries** for
  `telephone`/`call_recording`, **Social** for `social`. One button — "Allow" — using the same
  `/owner/onboarding/authorizations` endpoint, so nothing about the underlying permission model
  changed. Email read/send still live in Setup, where they are part of setup.

Guards: `test_permissions_are_asked_for_where_the_channel_is_used` (asserts the page, nav entry,
tab, route and import are gone and each `ChannelAsk` mount is live — gating one behind `false`
turns it red) and two retargeted guards in `test_studio_shell.py` that used to read the deleted
file (`test_the_permissions_page_is_gone_and_the_ask_is_inline`,
`test_a_customer_who_grants_nothing_still_gets_the_celebration` — the celebration now provably hangs
off finishing setup, not off granting everything).

Deployed: shell `index-D5V7PJxD.js` (no Permissions, carries "handle your texts"), worker cache
`concierge-studio-D5V7PJxD`. Suite **1206 passed, 36 skipped**.

## 7. Setup and permissions: available for changes, not waiting for attention

§6 removed the Permissions page outright, which overshot. The owner's clarification: *"once
installation they should both be under something, not gone but not requiring the customer to see
them after install has been completed, the reason they should still be available is if the
customer wants to make changes."*

**Final shape:**

- **Both pages live in the Settings group**: `Setup` and `Channels and permissions` (the page
  restored and renamed, because "Permissions" described our model, not the owner's job).
- **Every sidebar group folds**, and **Settings starts folded**. The choice is remembered in
  `localStorage['concierge:nav-folded']`, so an owner who opens it keeps it open, and one who
  never does is never asked to set anything up again.
- The **in-place asks stay** (§6): Texts, Enquiries and Social still offer "Allow" on the page
  itself the first time, so a new channel does not need a trip to Settings.

Guards: `test_setup_and_permissions_live_under_settings_and_fold_away` (both entries inside the
Settings group, `folded[group.group] ?? isSettings`, the persisted key, and all three inline asks)
and `test_the_permissions_page_still_exists_for_later_changes` in `test_studio_shell.py` (the lazy
import and the sidebar entry must exist — the reverse of yesterday's assertion, which is the point:
the page is available, not prominent). Mutation: defaulting groups to unfolded turns the first red.

Deployed shell `index-BNo2FfyP.js` (contains "Channels and permissions" and the fold key). Suite
**1206 passed, 36 skipped**.
