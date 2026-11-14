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
