# Trendi Facebook and Instagram posting runbook

This is the full, plain-English path from a draft to a live post on the Trendi Facebook Page and Instagram. It is written so anyone can follow it without guessing.

**Nothing is posted automatically.** Every public post needs Jo's go-ahead first. Never post to a personal Facebook profile or a personal Instagram account.

Times below are Pacific/Auckland.

Updated: 19 November 2026.

---

## 1. What you are posting to

1. **Facebook:** the Trendi Page only, Page id `61558235720533`, public URL: [facebook.com/profile.php?id=61558235720533](https://www.facebook.com/profile.php?id=61558235720533). The Page had 17 followers when checked on 19 November 2026.
2. **Instagram:** the business account **@trendi456** only, public URL: [instagram.com/trendi456](https://www.instagram.com/trendi456/).
3. **Do not use** Jo's personal Facebook, personal Instagram, or any other personal social account. If Meta asks you to switch from a personal login into the Page, switch to the Page first, then post. Deselect Instagram cross-posting when you are posting Instagram separately.

---

## 2. Draft generation (this is what now runs every week)

1. A Mac launchd job named `com.jo.trendi-social` starts at **07:15 every Monday**.
2. It runs `/Users/jo/jo-jobs/trendi-social/run.sh`.
3. That script calls `claude -p` on Jo's Claude subscription (OAuth login, no API key), using the prompt at `/Users/jo/jo-jobs/trendi-social/prompt.md` and the approved facts at `/Users/jo/jo-jobs/trendi-social/facts.md`.
4. Each run writes **three drafts**, for that week's Monday, Wednesday and Friday (or the next three of those days, if it is a catch-up run).
5. About three of every four posts are about Concierge: AI receptionist and AI office, missed calls, call forwarding from the owner's own mobile, and the live price of USD $250 a month with a 3-month minimum. The remaining post may be a true SEO or AI-visibility point. There is no "free" wording, no invented statistics or testimonials, and no personal name, phone or address.
6. The job **only writes files**. It does not open Facebook or Instagram, does not call the Meta API, and does not schedule anything.

To run it by hand, on the Mac:

```bash
/Users/jo/jo-jobs/trendi-social/run.sh
```

Logs go to `/Users/jo/Library/Logs/jo-jobs/trendi-social.log`.

### Older draft jobs (still around, not the Concierge pipeline)

- **OpenBot Workwatch**, 07:00 daily, used to run `~/OpenBot/Shared/workwatch/ops/bin/run_social.sh`. It wrote SEO or security-news drafts (not Concierge) to `~/.workwatch/reports/social/<date>.md`. Those drafts ran from 6 to 15 November 2026, then stopped after OpenBot ownership was revoked on 15 November. A one-off patched run on 19 November produced another SEO/security draft; that is not the Concierge series.
- **Hermes `trendi-social-drafts`**, also 07:00 daily, lives in `hermes/schedules.yaml` and `hermes/routines/trendi-social-drafts.md`. It is meant to write the same SEO/security drafts into Hermes reports (`~/trendi-reports/workwatch/`). On 19 November at 07:00 it wrote a stub saying it would not draft an appsec post without a DeepSeek route. The Hermes API on port 8642 was not up later that day. This job does not publish.
- **Twice-monthly post brief** and **LinkedIn weekly draft** are separate. LinkedIn has its own Playwright script (`scripts/social/linkedin_weekly_post.py`) and launchd job `com.trendi.linkedin-weekly`. That path is not used for Facebook or Instagram.

---

## 3. Where the drafts land

Look in `/Users/jo/Reports/trendi-social/`:

| File | What it is |
|---|---|
| `YYYY-MM-DD.md` | The Facebook text, Instagram caption and image brief for that posting day |
| `week-YYYY-MM-DD.md` | The same three posts in one file, dated with the first posting day |
| `latest.md` | A short index of the most recent batch |

Each daily file is marked `Status: needs Jo` and `Publish: DO NOT POST` until Jo says otherwise.

---

## 4. Review and approval (Jo)

1. Open the three files in `~/Reports/trendi-social/` (or ask the bot to show the text).
2. Check: facts are true, price is USD $250 a month with the 3-month minimum, no "free", no invented numbers, no personal details, the link is `https://trendibizz.com/ai-office` or `/concierge` (missed-call posts may use `/missed-call-text-back`).
3. If a draft is flagged **NEEDS JO**, it usually means it mentions call forwarding from the owner's own mobile. That is a real Studio feature (shipped 19 November 2026) but it is **not yet on the public website** (those URLs were 404 on 19 November). Approve the wording, or wait until a public page exists, before posting it.
4. Say which drafts may go out, on which days, and whether to use Meta Business Suite scheduling or to paste them by hand. Until that yes, **stop here**.

---

## 5. Image creation

1. Each draft includes an `IMAGE TEXT` block: one headline (up to 12 words) and exactly three bullets.
2. **This step does not run automatically today.** No image file is generated by the Monday job.
3. Make a square 1080 x 1080 card from that text (or reuse a signed-off brand card). Faceless cards are fine. Do not put personal photos, invented numbers, or the word "free" on the image.
4. Save the file next to the draft, for example `~/Reports/trendi-social/YYYY-MM-DD.png`, and keep it with the post when you publish.
5. Instagram needs an image (or carousel). Facebook can take the same image plus the link.

---

## 6. Publish to the Facebook Page

**Working method today: Jo (or someone Jo has asked) pastes the approved draft by hand.**

1. Sign in to [Meta Business Suite](https://business.facebook.com/) or open the Trendi Page, and switch to the **Trendi Page**, not a personal profile.
2. Create a new post (or a scheduled post).
3. Paste the Facebook section from `~/Reports/trendi-social/YYYY-MM-DD.md`. Keep the full `https://trendibizz.com/...` link in the body.
4. Attach the image if you have one.
5. If Instagram is connected to the Page, **deselect Instagram cross-posting** when you are posting Instagram separately, so the caption formats do not get mixed.
6. Publish now, or schedule for **10:00 Pacific/Auckland** on that Monday, Wednesday or Friday.
7. Confirm the post is Public and that it appeared on the Page, not on a personal profile.

### Facebook methods that do not work today

- **Meta Graph API.** There is no Facebook Page access token in the Mac Keychain (no `graph.facebook.com` internet password, and no generic-password Page token). The only related Keychain items found on 19 November were `jo-otp` one-time-password entries labelled `:Instagram` and `:MetaApi (kiwi18@gmail.com)`. Those are 2FA secrets, not posting tokens, and must never be printed or used as API keys.
- **A brand auto-poster.** There is no Facebook equivalent of the LinkedIn Playwright script. Do not point that LinkedIn script at Facebook.
- **Concierge `social-service` / SocialSync.** That is for Concierge *customers* connecting their own Pages in the product. It is not the Trendi brand posting path.
- **OpenBot browser posting.** OpenBot's browser was not signed into Facebook or Instagram (28 October 2026). OpenBot ownership of this work was revoked on 15 November 2026.

---

## 7. Publish to Instagram (@trendi456)

**Working method today: Jo pastes the approved caption by hand, with an image.**

1. Open Instagram as **@trendi456** (app, or Instagram in Meta Business Suite if that account is linked). Do not post from a personal profile.
2. Create a feed post. Upload the 1080 x 1080 image.
3. Paste the Instagram caption, including hashtags. Instagram will not make a URL in the caption clickable, so keep "Link in bio" and make sure the @trendi456 bio points at `https://trendibizz.com/ai-office` (or the path used in that post).
4. Publish now, or schedule for **10:00 Pacific/Auckland** on that Monday, Wednesday or Friday, if scheduling is available on the account.
5. Confirm the post is on @trendi456, not on a personal account.

The same Graph API and auto-poster gaps listed in step 6 apply here. There is no Instagram Graph token in the Keychain either.

---

## 8. Suggested posting times

| Step | When (Pacific/Auckland) |
|---|---|
| Drafts written | Monday 07:15, three posts for Mon/Wed/Fri |
| Jo reviews | Monday morning, before 10:00 if the Monday post is to go out that day |
| Publish or schedule | Monday, Wednesday and Friday at 10:00 |
| First batch written 19 November 2026 | Friday 20, Monday 23 and Wednesday 25 November 2026 |

These publish times are a recommendation only. Nothing is scheduled until Jo says so.

---

## 9. How to verify a post went live

1. Open the public Trendi Page and @trendi456 in a private browser window (so you are not looking at a draft-only view).
2. Check the text, the image, the link (Facebook) or the bio link (Instagram), and that the post is Public.
3. Copy the public post URLs into a short note under `~/Reports/trendi-social/`, for example a line in `posted-log.md`: date, channel, URL, and "posted by Jo". Do not invent entries. This log file is not created automatically today.
4. If the post is missing, is on a personal profile, or has the wrong caption, take it down or move it, and do not retry an automatic method (there isn't a safe one yet).

---

## 10. How to pause or stop the draft job

To pause drafts but keep the job installed:

```bash
touch /Users/jo/jo-jobs/trendi-social/PAUSE
```

The next Monday run will exit without writing drafts and will show a notification. Remove the file to resume:

```bash
rm /Users/jo/jo-jobs/trendi-social/PAUSE
```

To stop the job completely:

```bash
launchctl bootout gui/$(id -u) /Users/jo/Library/LaunchAgents/com.jo.trendi-social.plist
```

To start it again:

```bash
launchctl bootstrap gui/$(id -u) /Users/jo/Library/LaunchAgents/com.jo.trendi-social.plist
```

This only stops draft generation. It cannot "un-post" anything, because the job never posts.

---

## 11. What to do if a step fails

| Problem | What to do |
|---|---|
| No new files in `~/Reports/trendi-social/` after Monday 07:15 | Read `/Users/jo/Library/Logs/jo-jobs/trendi-social.log`. If Claude hit a usage limit, run `/Users/jo/jo-jobs/trendi-social/run.sh` later the same day. |
| Drafts contain "free", an em dash, a personal detail, or a number that is not in `facts.md` | Do not post. Edit the file, or re-run the job after fixing `facts.md`. |
| Call-forwarding draft is flagged NEEDS JO | Decide whether to post with a link to `/ai-office` or `/concierge`, or wait until a public forwarding page is live. |
| Claude CLI not logged in, or OAuth session expired | Sign in to the Claude CLI on the Mac with the subscription login (never an API key), then re-run `run.sh`. The first batch on 19 November was written by hand into `~/Reports/trendi-social/` after the CLI returned an expired session, so later Monday runs still need that login refreshed. |
| The Mac was off at 07:15 | This launchd job does not catch up on its own. Run `run.sh` by hand when the Mac is back. |
| A post was published to a personal account by mistake | Remove it from that account. Post again only on the Trendi Page or @trendi456, after Jo's yes. |
| Someone asks to "just hook up the Graph API" | That needs a long-lived **Page** access token stored in the Keychain under a named item, with posting limited to Page id `61558235720533` and Instagram @trendi456, plus Jo's written approval. This is **not set up today**. Do not reuse 2FA items, browser cookies, or personal login sessions to invent one. |

---

## 12. What does not work today (summary)

These are missing or blocked, and must stay marked until they are built and approved:

1. Automatic publishing to Facebook or Instagram.
2. Meta Graph API posting (no Page token in the Keychain).
3. Automatic image file generation.
4. An automatic "what went live" log.
5. A public web page for call forwarding (Studio has the setup step; the marketing URLs were 404 on 19 November 2026).
6. Hermes as a reliable publisher: it only writes drafts, this morning's social run did not produce Concierge copy, and the Hermes API was not running later on 19 November.
7. The old daily SEO/security social drafts as a way to promote Concierge: different topic, and they were never an auto-poster.

---

## 13. How this used to work, and why posting stopped

1. From late October 2026, a "Trendi daily SEO / security social drafts" routine wrote LinkedIn, Instagram and Facebook copy at 07:00. The first archived three-channel set is dated 28 October 2026. Copy rules lived in `~/jo-brain/trendi/social.md` and `~/OpenBot/Shared/workwatch/ops/social/PROMPT.md`. **Jo had to paste and approve every post.** The standing rule was "drafts only; Jo posts".
2. Those drafts were about SEO or penetration-testing news, not Concierge. They ended with "Run a quick check, link in our profile."
3. OpenBot Workwatch ran the Mac script through 15 November 2026 (`~/.workwatch/reports/social/` has files for 6–15 November). Ownership of the OpenBot agents was revoked on 15 November, and there are no draft files for 16, 17 or 18 November.
4. Hermes was set up to take the 07:00 job over. Its first recorded social run on 19 November wrote a "no drafts today" stub instead of posts, because that day was an appsec topic and the job refused to use Claude for it.
5. On the public Trendi Facebook Page, the latest post visible without logging in on 19 November 2026 was a public reel at **10:00 on Monday 2 November 2026**, beginning "Would you rather find the holes in your website first?". Instagram @trendi456 had at least two public carousel posts ([DfLLgcblHWD](https://www.instagram.com/trendi456/p/DfLLgcblHWD/), [DfDWRHMlliu](https://www.instagram.com/trendi456/p/DfDWRHMlliu/)); their dates were not visible without a logged-in session, so they are not stated here.
6. The new Monday job above is the replacement for Facebook and Instagram promotion, with Concierge as the main topic, still stopping at drafts until Jo approves a publish method and the first batch.
