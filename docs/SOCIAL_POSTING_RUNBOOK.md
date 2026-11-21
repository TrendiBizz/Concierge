# Trendi Facebook and Instagram posting runbook

This is the exact, reproducible process used on **19 November 2026** to publish one approved Concierge post to the Trendi Facebook Page and Instagram @trendi456. Follow it in order. Do not invent a shortcut.

Times below are Pacific/Auckland (NZDT / NZST).

Nothing is posted, scheduled, or deleted without Jo's yes. The Monday job only writes drafts.

---

## Never rules

- Post only to the **Trendi Facebook Page** and **Instagram @trendi456**.
- Never post to Jo's personal Facebook, personal Instagram, personal LinkedIn, or any other personal account.
- In the staging database, the LinkedIn account row (`<personal LinkedIn account id, see staging DB>`, display name the owner's personal name) is a personal account. Never put that id, or the TikTok account id, on a post.
- Never use the word **"free"** in copy, hashtags, or image text.
- Never invent statistics, testimonials, review counts, "trusted by", client names, results, or lead/sales promises.
- Never include a personal name, personal phone, photo of a person, or any street, postal or locality address.
- Never print, log, commit, or paste a password, token, vault key, OTP, or `social.env` value. Source secrets in-process. If you need a secret you do not have, see [How to get credentials/passwords](#how-to-get-credentialspasswords).
- If Meta returns a permission or app-review error, **stop**. Report the exact error (no secrets). Do not retry around it, and do not use a signed-in browser to post instead.
- Do not unpublish or delete a live post without Jo's yes.

---

## What the 19 November 2026 live test published

Jo's words at 19:48 NZDT, 19 November 2026: "run one now and we check if it works." That was a yes to publish **one** post: the Friday 20 November draft in `~/Reports/trendi-social/2026-11-20.md`, exactly as drafted, no edits.

Both posts went live at **8:04 PM NZDT** on 19 November 2026:

| Channel | Ids | Permalink |
|---|---|---|
| Facebook Page (Graph id `270235042840463`) | Photo `122256877430274524`; page post `270235042840463_122256877430274524` | https://www.facebook.com/photo.php?fbid=122256877430274524&set=a.122125411898274524&type=3 |
| Instagram @trendi456 (Graph id `17841465235622550`) | Media `18102104729402015`; shortcode `Df6gGOHHTSq` | https://www.instagram.com/p/Df6gGOHHTSq/ |

Image: 1080×1080 PNG at https://trendibizz.com/media/social/2026-11-20-concierge.png (repo path `website/media/social/2026-11-20-concierge.png`, commit `5d30545`). Local copy: `~/Reports/trendi-social/2026-11-20-concierge.png`.

The public Facebook Page URL id is `61558235720533` (New Pages Experience). The Graph API Page id is `270235042840463`. Use the Graph id for API calls. Public Page: https://www.facebook.com/profile.php?id=61558235720533. Public Instagram: https://www.instagram.com/trendi456/.

---

## 1. Draft generation (weekly job)

This step only writes files. It does not post.

1. A Mac launchd job named `com.jo.trendi-social` starts at **07:15 every Monday**.
2. Plist: `/Users/jo/Library/LaunchAgents/com.jo.trendi-social.plist`.
3. It runs `/Users/jo/jo-jobs/trendi-social/run.sh`.
4. The script reads:
   - Prompt: `/Users/jo/jo-jobs/trendi-social/prompt.md`
   - Approved facts: `/Users/jo/jo-jobs/trendi-social/facts.md`
5. It calls `claude -p` on Jo's Claude subscription (OAuth login, no API key), with Read/Write/Glob/Grep only.
6. If `$HOME/.claude_oauth_env` exists, `run.sh` sources it. Never echo that file.
7. It writes **three drafts**, for the next Monday, Wednesday and Friday (including today if today is one of those days).
8. About three of every four posts are about Concierge (AI receptionist and AI office, missed calls, call forwarding, live price USD $250 a month with a 3-month minimum). The rest may be a true SEO or AI-visibility point, still bound by `facts.md`.
9. Logs: `/Users/jo/Library/Logs/jo-jobs/trendi-social.log` and `trendi-social.out`.

To run it by hand:

```bash
/Users/jo/jo-jobs/trendi-social/run.sh
```

### Claude CLI login refresh

The first weekly run on 19 November 2026 failed with an expired Claude OAuth session, so that first batch was written by hand from `facts.md`. Later Monday runs still need a working login.

If the log says the OAuth session expired, or `claude` is not signed in:

1. On Jo's Mac, in Terminal, run `claude` and complete the subscription login (not an API key).
2. Re-run `/Users/jo/jo-jobs/trendi-social/run.sh`.
3. Do not put a Claude API key in the job, in chat, or in git.

### Where the drafts land

Look in `/Users/jo/Reports/trendi-social/`:

| File | What it is |
|---|---|
| `YYYY-MM-DD.md` | Facebook text, Instagram caption, and `IMAGE TEXT` for that posting day |
| `week-YYYY-MM-DD.md` | The same three posts in one file |
| `latest.md` | Short index of the most recent batch |

Each daily file starts as `Status: needs Jo` and `Publish: DO NOT POST` until Jo says otherwise.

To pause drafts without uninstalling the job:

```bash
touch /Users/jo/jo-jobs/trendi-social/PAUSE
```

The next Monday run exits without writing. Remove the file to resume. The 19 November live post was published while this PAUSE file was **not** present.

### Draft shape (do not invent a different format)

Facebook: no emojis, no em dashes, no exclamation marks, no "free"; full `https://` URL in the body; up to three hashtags.

Instagram: line breaks, at most three emojis, "Link in bio" plus the path (Instagram will not make a raw URL clickable), 8–12 hashtags.

`IMAGE TEXT`: one headline and exactly three bullets. No "free", no personal info, no invented numbers.

If a draft is flagged **NEEDS JO**, it usually mentions call forwarding from the owner's own mobile. That Studio feature shipped 19 November 2026, but the public marketing URLs were 404 that day. Do not post it until Jo has approved the wording, or a public page exists. The Wednesday 25 November draft had this flag and was **not** part of the 19 November live test.

---

## 2. Jo's approval gate

Stop here until Jo says yes.

1. Open the three files in `~/Reports/trendi-social/` (or show Jo the text).
2. Check: facts match `facts.md` and the live site, price is USD $250 a month with a 3-month minimum, no "free", no invented numbers, no personal details, the Facebook link is a real public page (`https://trendibizz.com/ai-office`, `/concierge`, or `/missed-call-text-back` as appropriate).
3. Jo must say which draft may go out, and that it may go live. A general "keep posting" is not enough. For the 19 November test, "run one now and we check if it works" applied only to the Friday 20 November draft, exactly as written.
4. Do not edit approved copy. If a change is needed, go back to Jo.
5. Until that yes, do not build a public image, deploy, or call the publish API.

Recommended public times, once Jo has approved a week: **10:00** Monday, Wednesday and Friday, Pacific/Auckland. The 19 November test went out immediately at 8:04 PM because Jo asked to run one now.

---

## 3. Build the 1080×1080 image card

Instagram Graph publishing requires a public HTTPS image. Facebook uses the same card.

1. Take the `IMAGE TEXT` from the approved daily file. For 20 November 2026 it was:

   - Headline: An AI receptionist and AI office
   - Answers chat, and phone, email or SMS once tested
   - USD $250 a month, 3-month minimum
   - No promise of leads or sales

2. Make a clean 1080×1080 PNG on navy Trendi brand:
   - Navy `#14213D`, Signal Lime `#C6F432`, wordmark from `website/brand/logo-horizontal-dark.svg` (the dark logo on a navy field). Brand rules are in `website/brand/BRAND.md`.
   - No personal info, no "free", no extra claims beyond the `IMAGE TEXT`.
3. The 19 November card was rendered with Chrome headless from `~/Reports/trendi-social/card-work/card.html`, then checked at exactly 1080×1080:

```bash
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
OUT="$HOME/Reports/trendi-social/2026-11-20-concierge.png"
"$CHROME" --headless=new --disable-gpu --hide-scrollbars --no-first-run \
  --force-device-scale-factor=1 --window-size=1080,1080 \
  --user-data-dir=/tmp/trendi-card-chrome \
  --screenshot="$OUT" \
  "file://$HOME/Reports/trendi-social/card-work/card.html"
sips -g pixelWidth -g pixelHeight -g format "$OUT"
```

4. Keep the local PNG next to the draft. Reuse this method for later cards, changing only the `IMAGE TEXT` and the filename (`YYYY-MM-DD-concierge.png`).
5. Inspect the PNG before hosting. Reject it if it is not 1080×1080, if it contains "free", or if it contains personal information.

---

## 4. Host the image so Meta can fetch it

The Graph publishers send Facebook `url` and Instagram `image_url`. Both must be `https`, with no port, user, password, or fragment. A loopback or `upload:` URL is not enough unless `SOCIAL_PUBLIC_MEDIA_BASE` is a public HTTPS base that Meta can reach. Staging social-service binds to `127.0.0.1:4390`, so Meta cannot fetch from it. On 19 November the card was hosted as a static asset on trendibizz.com.

1. Copy the PNG into the website tree only:

```bash
REPO=/Users/jo/work-staging/concierge-integration
mkdir -p "$REPO/website/media/social"
cp "$HOME/Reports/trendi-social/YYYY-MM-DD-concierge.png" \
   "$REPO/website/media/social/YYYY-MM-DD-concierge.png"
```

2. **Commit that file first.** `scripts/vps/deploy-site.sh` refuses uncommitted or untracked files under `website/`. Do not commit session handoff files or other untracked work.

```bash
cd /Users/jo/work-staging/concierge-integration
python3 scripts/seo/site_seo.py check
git add website/media/social/YYYY-MM-DD-concierge.png
git commit -m "Add Concierge social image card (1080x1080) for YYYY-MM-DD."
```

3. Deploy only through the supported site script, from the repo root, with the deploy SSH key **path** (never print the key):

```bash
cd /Users/jo/work-staging/concierge-integration
KEY=./Concierge ./scripts/vps/deploy-site.sh
```

That script: runs `scripts/seo/site_seo.py check`, rsyncs the committed `website/` tree to the VPS, writes `.deploy-manifest.json`, and runs `scripts/vps/verify-deploy.sh`. If `site_seo.py check` fails, stop and do not claim a successful deploy.

Known check issue, 19 November 2026: `verify-deploy.sh` compares the live site against the old local mirror `/Users/jo/work-staging/trendibizz-live/site`, not against repo `website/`, so it can exit non-zero even when the rsync was correct. After a PNG-only deploy, prove the file another way: SHA-256 of the repo file, the VPS file, and a public GET must match. The 19 November card hash was `65ddfc984666dcc5f67442f283ee4436aeb1611028e4546e158399e307ea4d2c`. Do not treat a stale-mirror fail as proof that the PNG is missing if those three hashes agree and the URL returns 200.

4. Confirm Meta can fetch it:

```bash
URL="https://trendibizz.com/media/social/YYYY-MM-DD-concierge.png"
curl -sI -A "facebookexternalhit/1.1" "$URL"
curl -s -A "facebookexternalhit/1.1" -o /tmp/meta-card.png "$URL"
cmp /tmp/meta-card.png "$HOME/Reports/trendi-social/YYYY-MM-DD-concierge.png"
rm -f /tmp/meta-card.png
```

Expect HTTP 200, `content-type: image/png`, and a byte-for-byte match. If this fails, stop. Do not publish.

---

## 5. Load the post into staging social-service

Use only the Mac staging service, not the VPS candidate copy, unless you are cancelling leftover test rows (see below).

| Item | Value |
|---|---|
| Bind | `127.0.0.1:4390` |
| Health | `http://127.0.0.1:4390/health` must return `{"ok":true}` |
| Customer | `trendi-oauth-staging` |
| Database | `/Users/jo/work-staging/concierge-integration/.private/oauth-staging/social.db` |
| Env file | `/Users/jo/work-staging/concierge-integration/.private/oauth-staging/social.env` |
| Launchd | `com.trendi.concierge-oauth-social-staging` |
| Runner | `/Users/jo/work-staging/concierge-integration/.private/oauth-staging/run-social-staging.sh` |
| Binary | `/Users/jo/work-staging/concierge-integration/concierge-stack/social-service/target/debug/concierge-social` |
| Facebook account id | `TLCzXubqgbYuzfzpj6bbsRrAGQ5t_yhF` (network `facebook`, external id `270235042840463`, display name Trendi) |
| Instagram account id | `SxCzb_jaib2BpLK_AoIEQZsjf7AO4lEC` (network `instagram`, external id `17841465235622550`, display name trendi456) |

Before loading, confirm `needs_reauth` is 0 for those two rows, and that you will pass **only** those two account ids (one per post, because the Facebook and Instagram captions are different).

### 5a. Stop the scheduler first

The long-running staging runner sets `SOCIAL_ENABLE_PUBLISH=true`, but `SOCIAL_ENABLE_FACEBOOK_PUBLISH` and `SOCIAL_ENABLE_INSTAGRAM_PUBLISH` are not `true`. The server therefore starts a 15-second scheduler **without** Facebook or Instagram connectors. If you approve a post with `scheduled_at` now, that scheduler can mark it Failed with "No connector for facebook". `SOCIAL_ENABLE_LINKEDIN_ORGANIZATION_PUBLISH` is `true` on this service, which is another reason never to attach the LinkedIn account id.

On 19 November the safe sequence was:

```bash
launchctl bootout "gui/$(id -u)/com.trendi.concierge-oauth-social-staging"
# Confirm 127.0.0.1:4390 is down, then start API-only (publish off):
```

Start the API with the same env file and database, but `SOCIAL_ENABLE_PUBLISH=false`. Source `social.env` in the process; never `echo` or `set -x` that script.

```bash
# Pattern only: values stay in the environment, not in the terminal.
set -a
source /Users/jo/work-staging/concierge-integration/.private/oauth-staging/social.env
set +a
export SOCIAL_DB=/Users/jo/work-staging/concierge-integration/.private/oauth-staging/social.db
export SOCIAL_BIND=127.0.0.1:4390
export SOCIAL_ENABLE_PUBLISH=false
exec /Users/jo/work-staging/concierge-integration/concierge-stack/social-service/target/debug/concierge-social
```

Wait until `curl -fsS http://127.0.0.1:4390/health` returns `{"ok":true}`.

### 5b. Cancel leftover scheduled test rows if they could fire

Do **not** publish old test copy. If a row in a live scheduler is `scheduled` and already due, move it to `draft`. On 19 November the Mac staging database had no leftover posts. The VPS candidate database at `/opt/trendi/candidate-social/social.db` had three overdue "Isolated release verification" rows (`a8oYVlZUKPs4K3lBqK2vv6xt_XrqH66v`, `dIZM1zOpNRlmgq3_bCeTUd11QOIH9rQq`, `HFNHxiGqnwbjr6Ys3_V7pAHMOk0ytdiV`), originally scheduled 9 November 2026, 12:58 AM NZDT. VPS `SOCIAL_ENABLE_PUBLISH` was already off. They were still moved to `draft` (body status included) and were not published. A fourth row, `VH1GWx98OHHYpHRDJfXTYit5kw-DMZJY`, stayed `pending_approval` and was left alone.

### 5c. Create, submit, and approve two posts

Authenticate as the concierge operator with `Authorization: Bearer $SOCIAL_CONCIERGE_KEY`. Source the env file; never print the header.

Create **two** posts, because social-service stores one `content` / `link` / `hashtags` body per post:

1. Facebook only, account `TLCzXubqgbYuzfzpj6bbsRrAGQ5t_yhF`. `content` is the Facebook body including "Read how it works:"; `link` is `https://trendibizz.com/ai-office`; `hashtags` are `#AIReceptionist #AIoffice #SmallBusiness`. At publish time these are joined with newlines, which matches the draft.
2. Instagram only, account `SxCzb_jaib2BpLK_AoIEQZsjf7AO4lEC`. Put the entire Instagram caption, including hashtags and "Link in bio: trendibizz.com/ai-office", in `content`. Leave `link` and `hashtags` empty so a raw URL line is not added.

Both posts use:

```json
"media": ["https://trendibizz.com/media/social/YYYY-MM-DD-concierge.png"]
```

Routes, in order, for customer `trendi-oauth-staging`:

1. `POST /v1/customers/trendi-oauth-staging/posts` with the JSON above (`account_ids` must be exactly the one target account).
2. `POST /v1/customers/trendi-oauth-staging/posts/:id/submit` — runs guardrails. Instagram requires media. Forbidden phrases on this customer were empty on 19 November; still do not use "free".
3. `POST /v1/customers/trendi-oauth-staging/posts/:id/approval-request` with `{"scheduled_at": <unix seconds, now>}`. The response includes a one-time approval `token`. Do not print or log that token.
4. `POST /v1/customers/trendi-oauth-staging/approvals/:token/approve`. The post becomes `scheduled`. If `scheduled_at` was in the past, the service stores `max(requested, now)`.

On 19 November the created ids were:

- Facebook post `_0yDl_4_doemXVFSVX3kdaHsG63Fgp7g`
- Instagram post `wxetgXQNUvyGJ_b3VWS9iI8uqJkw6wSf`

Confirm each approved post still has only the intended account id before publishing.

---

## 6. Publish with `publish-reviewed-post`

The operator binary is:

`/Users/jo/work-staging/concierge-integration/concierge-stack/social-service/target/debug/publish-reviewed-post`

Usage: `publish-reviewed-post CUSTOMER POST_ID`

It will refuse unless `SOCIAL_ENABLE_PUBLISH` is the exact string `true`. It also needs `SOCIAL_DB` (absolute path above) and `SOCIAL_VAULT_KEY`. Unlike the long-running server, this binary **always registers Facebook and Instagram connectors**. It does not register LinkedIn. It delivers only that one post, then prints `Selected post delivery state: ...`.

Source env in-process, then:

```bash
export SOCIAL_ENABLE_PUBLISH=true
export SOCIAL_DB=/Users/jo/work-staging/concierge-integration/.private/oauth-staging/social.db
# SOCIAL_VAULT_KEY already comes from social.env
/Users/jo/work-staging/concierge-integration/concierge-stack/social-service/target/debug/publish-reviewed-post \
  trendi-oauth-staging POST_ID
```

Run it once for the Facebook post id, then once for the Instagram post id. Do not pass a LinkedIn or TikTok post.

The binary decrypts the Page/IG tokens from `social.db` with `SOCIAL_VAULT_KEY` and the vault label `{customer_id}|{network}|{external_id}` (for example `trendi-oauth-staging|facebook|270235042840463`). It never prints those tokens. Facebook posts to `https://graph.facebook.com/{version}/{page-id}/photos` with `caption` and `url`. Instagram, with `SOCIAL_INSTAGRAM_LOGIN_MODE=facebook`, uses `https://graph.facebook.com/{version}/{ig-id}/media` (`image_url`, `caption`), waits until `status_code=FINISHED`, then `/{ig-id}/media_publish`. Graph version comes from `SOCIAL_META_GRAPH_VERSION` (a `v` plus digits and dots).

Expect `Selected post delivery state: Published`. On 19 November both runs reported that.

Note from the 19 November run: the service's `classify()` helper turns some Meta HTTP 400 bodies into the generic string "Facebook rejected post content" / "Instagram rejected post content". If you need the exact Meta message, capture `error.type`, `error.code`, `error.error_subcode`, and `error.message` from the Graph response (never `access_token`). Do not retry the publish call in order to see the message if a permission error is already confirmed.

---

## 7. Read-only verification, `post_results`, and the publish log

Do this after a successful publish, with a token opened in-process from the vault. Never print the token. Do not POST again.

Facebook: `permalink_url` is **not** a field on the raw photo id. Use the page-post id, or `id,link,created_time,from` on the photo id.

```text
GET https://graph.facebook.com/{version}/{photo-id}?fields=id,link,created_time,from
GET https://graph.facebook.com/{version}/{page-id}_{photo-id}?fields=id,permalink_url,is_published,created_time,status_type
```

On 19 November the second call returned `is_published=true`, `status_type=added_photos`, and the photo.php permalink. The Page feed also showed a matching `added_photos` item at the same created time (`2026-11-19T07:04:11+0000` = 8:04:11 PM NZDT).

Instagram:

```text
GET https://graph.facebook.com/{version}/{media-id}?fields=id,permalink,shortcode,timestamp,media_type
```

On 19 November this returned HTTP 200, `media_type=IMAGE`, and https://www.instagram.com/p/Df6gGOHHTSq/ (`2026-11-19T07:04:24+0000` = 8:04:24 PM NZDT).

`publish-reviewed-post` writes `post_results` (`ok=1`, `external_post_id`, no error) and sets the post status to `published`. Confirm:

```bash
sqlite3 /Users/jo/work-staging/concierge-integration/.private/oauth-staging/social.db \
  "SELECT id,status FROM posts; SELECT post_id,account_id,ok,external_post_id,error,at FROM post_results;"
```

You will see account ids and provider post ids. You must not see tokens.

Write a publish log under `~/Reports/trendi-social/` (the 19 November file is `publish-2026-11-19.md`) with: date and time in NZDT, draft file, both permalinks and ids, image path and public URL, social.db post ids, and any errors. Update the draft file's status line from `DO NOT POST` to the permalinks. There is no `social` table in `~/jo-data/jo.db`; do not invent one. Do not put tokens in the log.

Then restore the staging launchd service: stop the API-only process, then:

```bash
launchctl bootstrap "gui/$(id -u)" /Users/jo/Library/LaunchAgents/com.trendi.concierge-oauth-social-staging.plist
# or, if the job is already loaded: launchctl kickstart -k "gui/$(id -u)/com.trendi.concierge-oauth-social-staging"
curl -fsS http://127.0.0.1:4390/health
```

Leave any unrelated process on `127.0.0.1:4391` alone unless you know what it is. On 19 November a pre-existing `concierge-social` process was already listening there (started 8 November 2026).

---

## 8. Error handling

| Problem | What to do |
|---|---|
| Claude OAuth expired, or `latest.md` missing after `run.sh` | Refresh `claude` in Terminal, then re-run the draft job. Do not post anything. |
| Draft has "free", an em dash, a personal detail, or a number not in `facts.md` | Do not post. Fix the draft and get Jo's yes again if the wording changed. |
| `site_seo.py check` fails | Stop. Do not deploy or publish. |
| Public image URL is not 200, or Meta user-agents cannot fetch it | Stop. Do not publish. |
| Account `needs_reauth=1`, or Graph returns 401/403 | Stop. Use the official Meta OAuth reauth in the next section. Do not harvest browser cookies or paste tokens into chat. |
| Meta 400/403 with permission, OAuth, capability, "(#200)", "(#10)", "(#3)", "app review", or "not been approved" | **Stop.** Report the exact `error.type`, `error.code`, `error.error_subcode`, and `error.message`. Do not retry. Do not post from a browser instead. |
| `publish-reviewed-post` reports Failed, or "No connector for {network}" | Do not retry blindly. Check whether the long-running scheduler raced (section 5a). If a network already succeeded, leave that live post alone and report the failed network. |
| Timeout / "outcome uncertain" / "Reconciliation required" | Treat as failed for manual reconciliation. The post may already be live. Check Graph read-only and the public permalink before doing anything else. Never automatically retry an ambiguous timeout. |
| Post landed on a personal account | Stop. Tell Jo. Remove it only after Jo's yes (section 9). |

---

## 9. Rollback or deleting a post (needs Jo's yes)

A published Facebook or Instagram post is public. Taking it down is irreversible from the audience's point of view and needs Jo's explicit yes, naming which post.

After that yes, delete only the named post through the official Graph API (or Meta Business Suite switched to the Trendi Page / @trendi456), then record the deletion in the publish log. Do not delete comments, other posts, or ads. Do not use a personal profile to remove a Page post without switching to the Page.

Drafts and scheduled rows that have **not** gone live may be moved from `scheduled` to `draft` without a public deletion, which is how the three overdue VPS test rows were cancelled. That is not the same as deleting a live post.

---

## How to get credentials/passwords

Never include a secret value, token, password, or OTP in this document, in chat, in logs, or in git. Ask for *access*, not for someone to paste the secret into the conversation.

### Where each secret lives

| Secret | Where it lives | How to use it |
|---|---|---|
| Social operator and vault keys | `/Users/jo/work-staging/concierge-integration/.private/oauth-staging/social.env` (mode should stay private). Names: `SOCIAL_CONCIERGE_KEY`, `SOCIAL_AGENT_KEY`, `SOCIAL_VAULT_KEY`. Also present: `SOCIAL_FACEBOOK_CLIENT_ID`, `SOCIAL_FACEBOOK_CLIENT_SECRET`, and the TikTok / LinkedIn client names in that same file. | `set -a; source social.env; set +a` in a script. Never `cat`, `echo`, or `set -x` the file. |
| Page and Instagram access tokens | Encrypted column `token_enc` in `social.db`, opened with `SOCIAL_VAULT_KEY` and label `{customer}\|facebook\|270235042840463` or `{customer}\|instagram\|17841465235622550`. | Let `publish-reviewed-post` open them. Do not dump `token_enc` or the opened token. |
| Staging database path | Env name `SOCIAL_DB`. The runner overrides it to the absolute path in the table in section 5. The raw env value may be a short relative path; do not use that short path in sqlite or the publisher. | Export the absolute path shown in section 5. |
| Publish switches | Env names `SOCIAL_ENABLE_PUBLISH`, `SOCIAL_ENABLE_FACEBOOK_PUBLISH`, `SOCIAL_ENABLE_INSTAGRAM_PUBLISH`. They must equal the exact string `true` to enable that switch. | For a one-shot, set `SOCIAL_ENABLE_PUBLISH=true` only in the `publish-reviewed-post` process. Do not turn the per-network flags on in the long-running server unless you intend the 15-second scheduler to post. |
| Site deploy SSH key | File `/Users/jo/work-staging/concierge-integration/Concierge` (the path is passed as `KEY=./Concierge`). | `KEY=./Concierge ./scripts/vps/deploy-site.sh`. Never print the file. |
| Claude CLI login | Claude subscription OAuth on the Mac, optionally `$HOME/.claude_oauth_env`. | Run `claude` in Terminal. Never add an API key to the job. |
| Meta / Instagram 2FA | macOS login Keychain, generic-password service `jo-otp` (index in `jo-otp-index`). These are TOTP seeds, **not** Page tokens and not API keys. | See the OTP steps below. |
| Anything else in Keychain | Named generic-password items, for example via `security find-generic-password -s <service> -w`. | Read in-process. Never print `-w` output. |

The global `SOCIAL_AGENT_KEY` cannot do tenant operations (it is rejected with "Global agent key has no tenant permissions"). Do not rotate or print it for this job.

### OTP (Ente Auth via `~/.local/bin/otp`)

The tool reads Ente Auth TOTP secrets that were imported into Keychain service `jo-otp`. It never prints those secrets.

```bash
otp list          # labels only
otp code NAME     # current 6–8 digit code for the first label containing NAME
```

When a Meta or host prompt asks for a 2FA code:

1. Run `otp code` with the matching label (use `otp list` if you are unsure of the name).
2. **Type the digits straight into the prompt.** Do not read them aloud in chat, do not put them in a log, and do not commit them.
3. If the tool says `no match`, do not try to extract the Keychain item another way. Ask Jo in chat to import the Ente export with `otp import FILE` (the tool shreds the file) or to type the code himself into the prompt.

### Meta OAuth reauth, when `needs_reauth=1`

Page and IG tokens are long-lived grants stored in the vault, not Keychain passwords. If `needs_reauth` is 1, or Graph says authorization was rejected:

1. Tell Jo that the Trendi Page and/or @trendi456 grant must be renewed. Do not ask him to paste a token.
2. With the staging API up, and `SOCIAL_CONCIERGE_KEY` sourced, start the official flow:

   `POST /v1/customers/trendi-oauth-staging/oauth/meta/facebook/start`

   or `.../oauth/meta/instagram/start`

3. The callback path is `/owner/social/oauth/callback` (public hostname comes from `SOCIAL_FACEBOOK_CALLBACK`, which must stay in env and out of this document's values).
4. Jo signs in as the Trendi Page / @trendi456, not a personal profile, and finishes the consent screen. If 2FA appears, use `otp` as above, typed into the prompt.
5. Finish with `POST /v1/customers/trendi-oauth-staging/oauth/meta/{facebook|instagram}/finish` using the `state` and `code` from the callback, still without logging them.
6. Confirm the same account ids as in section 5, `needs_reauth=0`, and `external_id` still `270235042840463` / `17841465235622550`.
7. Then retry the approved publish once, still through social-service, still without a browser post.

### What to say in chat when a secret is missing

Ask Jo for a **decision and a place**, not for the secret itself. Examples:

- "The Claude CLI login on the Mac has expired. Please run `claude` once in Terminal, then I will re-run the draft job. Please do not paste a key here."
- "Staging `social.env` has no usable `SOCIAL_VAULT_KEY` (or the file is missing). Please restore that file on the Mac from the usual private copy. Please do not paste the key into chat."
- "Facebook/Instagram shows `needs_reauth`. I will start the social-service Meta OAuth flow for the Trendi Page and @trendi456 only. Please complete the browser consent, and type any 2FA code into the prompt (I can type it from `otp` if the label is there). Please do not paste passwords or tokens here."
- "I do not have a 2FA label for this prompt in `otp list`. Please type the code into the prompt yourself, or import the Ente export with `otp import`."

If Jo pastes a secret into chat anyway, do not repeat it, do not write it into the repo or the publish log, and move it into the proper store (`social.env` or Keychain) only if Jo asked for that and the value is not already there. Then ask him to delete the chat paste if he can.

---

## 10. Pause, stop, and older draft jobs

Pause or resume the Monday draft job as in section 1 (`PAUSE`, or `launchctl bootout` / `launchctl bootstrap` on `com.jo.trendi-social`). That only stops drafts. It cannot un-post.

Older jobs that are **not** this Concierge pipeline:

- OpenBot Workwatch `~/OpenBot/Shared/workwatch/ops/bin/run_social.sh` used to write SEO/security drafts to `~/.workwatch/reports/social/`. That stopped after OpenBot ownership was revoked on 15 November 2026.
- The LinkedIn Playwright job `com.trendi.linkedin-weekly` and `scripts/social/linkedin_weekly_post.py` must not be pointed at Facebook or Instagram.
- Before 17 November 2026, some live Page posts were made through a signed-in browser after Jo's ok. That path is not this runbook, and Grok routines remain paused. Do not go back to browser posting to work around a Meta API error.

---

## 11. Quick command index

```bash
# Drafts
/Users/jo/jo-jobs/trendi-social/run.sh

# Site SEO check and deploy (after committing the PNG only)
cd /Users/jo/work-staging/concierge-integration
python3 scripts/seo/site_seo.py check
KEY=./Concierge ./scripts/vps/deploy-site.sh

# Staging health
curl -fsS http://127.0.0.1:4390/health

# Operator publish (env sourced, keys not printed)
publish-reviewed-post trendi-oauth-staging POST_ID

# Results (no tokens)
sqlite3 /Users/jo/work-staging/concierge-integration/.private/oauth-staging/social.db \
  "SELECT id,status FROM posts; SELECT post_id,account_id,ok,external_post_id,error,at FROM post_results;"
```
