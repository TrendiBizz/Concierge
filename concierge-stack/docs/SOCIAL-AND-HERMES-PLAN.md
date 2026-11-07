# Social media and Hermes: the plan (direction set by Jo, 2026-11-07)

Jo's direction: the CURRENT project stays the core. Do not re-centre on, or rebuild around, the separate platform.
Use Hermes Agent as the integration layer for the heavy lifting. For SocialSync, take the CORE IDEA and fit it to this
project. If Hermes (or an existing tool) already does something, use theirs and add only what is missing.
(This supersedes the "platform is the core" recommendation in `PLATFORM-AND-SOCIALSYNC-FINDINGS.md`.)

Facts below come from the projects' own docs and READMEs as read by research helpers, not from running them. Items marked
unconfirmed were not seen directly.

## 1. What Hermes already has (use theirs)

| Need | Hermes |
|---|---|
| Post to X | Bundled `xurl` skill: official X API, OAuth 2.0 PKCE. Posts immediately (no scheduling). Posting needs paid X API credits in practice (inferred from its error messages). Its "confirm before write" is a prompt rule, not an enforced gate. |
| Plan content | Optional `social-media-content-calendar` skill (planning only, does not publish) |
| Run things on a schedule | Built-in cron (cron expressions, one-shot, intervals), delivers results by email, text, Telegram and others. Agent jobs only run while the gateway is up. |
| Email and text channels | Email gateway (IMAP and SMTP), Twilio SMS gateway (needs a public HTTPS webhook URL), Gmail and Google Calendar through the bundled `google-workspace` skill |
| Draft with approval | Telegram Business plugin only (Send, Edit, Discard). Nothing equivalent for email or text. |
| Call outside services | MCP client (stdio and HTTP, per-server tool allow-lists), skills, plugins |
| Use from our code | Docker image `nousresearch/hermes-agent` (tags `stable`, `latest`, X.Y.Z), OpenAI-compatible API server on 127.0.0.1:8642 with a Bearer key, `POST /v1/runs` async runs |

What Hermes does NOT have (confirmed absent in the catalogues read; the 1,064-plugin marketplace was only partly visible):
LinkedIn, Facebook Pages, Instagram or Google Business Profile posting; Buffer/Ayrshare-style services; a media library;
brand rules or forbidden-claims checks; an enforced approval step for outbound posts; separation between customers.

Cautions from its docs: the API server keeps terminal and file tools by default (restricting them is documented only
generally, unconfirmed for the API platform); run it in Docker, loopback only, with a strong key; no multi-customer
isolation model is documented, so use one Hermes profile or container per customer if customers' credentials are ever held
there, or keep credentials elsewhere.

## 2. What exists on GitHub like SocialSync

| | Postiz | Mixpost |
|---|---|---|
| Repo, size | gitroomhq/postiz-app, about 41k stars, releases every few days (latest v2.25.3 on 24 Oct, year not shown) | inovector/MixPost, about 3k stars (not confirmed current) |
| Licence | **AGPL-3.0** (running unmodified imposes no source release; a modified version offered over a network must offer its source; no trademark rights; not legal advice) | Sources conflict. Lite free (limited platforms); Pro USD 299 once; **Enterprise USD 1,199 once for building a SaaS**; one year of updates included |
| Networks | About 30 to 34 (X, LinkedIn, LinkedIn Page, Facebook, Instagram, Threads, TikTok, YouTube, Google Business Profile, Pinterest, Reddit, Bluesky and more) | Lite 3 platforms; Pro all (per a competitor's comparison) |
| Linking customers' accounts | **Invite links**: the customer authorises on the platform's own screen and never sees our account; the channel then appears under us. Channels can be grouped by customer. | Multi-tenant workspaces, unlimited |
| Customer separation | "Customer groups" inside one organisation. Not separate tenants; stronger isolation is unconfirmed. | Real workspaces (stronger) |
| API and agents | Public API (key in the Authorization header), Node SDK, n8n node, **MCP server** (Streamable HTTP; tools include `schedulePostTool`, `integrationList`, `postsListTool`, `mediaListTool`, `uploadFromUrlTool`) | Pro includes API and MCP (per Blotato) |
| Approval before publishing | **None enforced**: "Approval is a conversation, not a state". Drafts exist, and preview links with no login. An agent can schedule directly. | Pro has approval flows (per Blotato) |
| Self-hosting | Docker Compose with Postgres, Redis and Temporal; 2 vCPU and 2 GB minimum, 4 to 8 GB recommended; HTTPS reverse proxy; **you must register your own developer app for X, LinkedIn, Facebook, Instagram, Threads, Google Business Profile, TikTok, YouTube and others** (about 10 smaller networks need none) | Laravel and PHP |
| Hosted | **Postiz Cloud with pre-approved platform apps**: 7-day trial, then Standard USD 29, Team 39, Pro 49, **Ultimate 99 for 100 channels ("agencies")** per month. API, MCP and customer groups on every plan. Whether client channels count against the cap, and any white-label option, are unconfirmed. | Self-hosted only |

Others named but not read: Socioboard, TryPost, OpenPost.

## 3. How it fits (the design)

```
Customer (links accounts once, by invite link)
        |
   Postiz  <-- publishes to LinkedIn, Facebook, Instagram, X ... (our own developer apps; free)
        ^
        | Postiz MCP / API (drafts only)
   Hermes (Docker, loopback)  --- drafts posts from the customer's website pages and recent Concierge activity
        |
   Guardrail check (SocialSync's core idea, ours)  --- brand facts, forbidden claims, platform limits
        |
   Approval  ("Reply YES to post") by text or email  --- ours, because Postiz and Hermes do not enforce one
```

1. **Linking is Postiz's** (invite link per customer). Painless for the customer.
2. **Drafting, scheduling the work and talking to the customer is Hermes's** (LLM, cron, email and text gateways).
3. **What is missing everywhere, and so is ours to build** (SocialSync's core idea):
   - **Guardrails**: per-customer verified facts, forbidden claims, warning patterns, and per-platform limits. SocialSync's
     `guardrails.js` is about 180 lines of plain rules (character limits, link length, hashtag and media limits, a
     "claim contradicts a verified fact" regex check, forbidden phrases, warnings). It ports to Python in one small module,
     exposed to Hermes as a tool.
   - **An approval gate**: nothing is scheduled or published until the customer says yes. Agents may only create DRAFTS.
   - A small photo library and a draft record only if Postiz's own media and drafts are not enough.
4. Everything stays per customer: one rules file, one set of channels, one approval contact.

## 4. Free first (Jo's rule: free now, pay only once there are paying clients)

**Cost today:** Hermes (MIT) and self-hosted Postiz (AGPL) are free software. The only running cost is the xAI usage Hermes
makes with the key already in use.

**Not free, so NOT adopted yet** (listed in section 2 for later only): Postiz Cloud (USD 29 to 99 a month), Mixpost Pro and
Enterprise (USD 299 and 1,199), posting services such as Ayrshare and Buffer, and X posting through the API (needs paid
credits in practice).

**Free options that already link accounts (checked on the vendors' own pages, 2026-11-07; limits can change)**

| Service | Free plan | Linking and approvals | API, scheduling, agents |
|---|---|---|---|
| **Upload-Post** | USD 0, no card: 2 profiles, 10 uploads a month, API, SDK and MCP included | Hosted connect link per customer. Its FAQ says **it holds the approved platform apps**, so no Meta or LinkedIn review for us. White-label link from its paid Professional plan (listed at USD 33 or 50, inconsistent). | `Authorization: Apikey`, `POST /api/upload_text` and `/upload_photos`, `scheduled_date` for scheduling, hosted MCP. **No drafts found.** Networks listed include Facebook, Instagram, LinkedIn, X, Google Business, TikTok, YouTube. Reseller terms not found. |
| **Zernio** (formerly Late) | First 2 accounts free, all features, unlimited posts, API | Hosted or white-label connect flow not confirmed; whose platform apps are used not confirmed | `POST /v1/posts` with `scheduledFor`, hosted MCP. No drafts found. Paid: USD 6 per account for accounts 3 to 10. |
| **Buffer Free** | 3 channels, 10 scheduled posts per channel, **API on the free plan** (150 requests per 15 minutes), drafts supported | Customers would authorise our app into their own Buffer account (inferred); no hosted connect API found | GraphQL API, MCP. Paid: USD 5 per channel. |
| **Postproxy** | 10 posts a month, API | Unclear | Unclear |
| **Meta Business Suite** | Free for Facebook and Instagram (Business or Creator accounts) | The customer's own login | Manual, no API for us |

All of these are tiny (2 to 3 accounts) and the numbers come from vendor pages, so they PROVE the flow, they do not carry many customers.

**The free route**
1. **Now (free, no approvals):** SocialSync-style drafts, our guardrails and approval, and Hermes drafting. Publishing stays manual
   (copy or Share) exactly as SocialSync works today.
2. **Proof of linking and publishing (free):** Upload-Post's free plan with one or two test customers. Best fit: hosted connect
   link, approved apps already held, API and MCP on the free plan. Because it has no drafts, our own draft and approval step
   is needed anyway, which is what we are adding. Read its terms before using it for anyone's accounts.
3. **At scale (free software, our time):** self-hosted Postiz with our OWN developer apps (needs approvals). Networks that need no
   developer app (Bluesky, Lemmy, Nostr, WordPress, Medium, Dev.to, Hashnode) work straight away.
4. **X:** no paid API posting; manual, or through a free tier above where X is allowed (limits apply).
5. **When clients pay:** Jo chooses a paid tier (for example Postiz Cloud, Zernio per account, Upload-Post Basic at USD 24).

**LinkStack (checked):** an open-source Laravel app for "link in bio" pages (a Linktree alternative), AGPL-3.0, Docker image,
many users per install, admin panel and themes. **It does not connect to social networks, post or schedule**: it is a page
of links to a person's profiles. No API or webhooks found. It is a different category from SocialSync. At most it could be an
optional free extra, a link page for each customer's profiles. Not part of the posting design.

**herdr (checked):** a Rust terminal workspace (like tmux) for running several AI coding agents side by side (Apache-2.0, about
49k stars). No social accounts, posting or OAuth. It only detects Hermes inside its terminal panes. Not part of this design.

**Per-network requirements for building our own connectors (Meta, LinkedIn, X, TikTok, YouTube, Google Business Profile,
Pinterest, Bluesky, Mastodon):** see `SOCIAL-NETWORKS-ACCESS.md`. Short version: Bluesky, Mastodon and LinkedIn personal
profiles need no approval; X costs cents per post; Meta (Facebook, Instagram, Threads) needs one Business Verification and App
Review that unlocks all three; LinkedIn company pages, Google Business Profile, TikTok and Pinterest each need their own approval.

**Postiz code review (read the source, 2026-11-07):** see `POSTIZ-CODE-REVIEW.md`. One install CAN serve many customers: the tenant is
the Organization (own API key, channels, posts, media, team); a self-hosted install has no channel limit; the developer apps are
one set for the whole install, so approvals are done once. All the major networks are already built in, so we do NOT need to build
connectors into SocialSync. Cautions: heavy stack (Temporal, Elasticsearch), no approval gate, channel tokens look unencrypted
at rest, AGPL.

**Open questions:** customer separation inside one Postiz organisation; AGPL and the customer's linked-account access need a
lawyer's view before launch; Postiz needs Postgres, Redis and Temporal (2 to 8 GB of RAM), so check the Mac and the future
VPS can run it.

## 5. Build order

1. Hermes running in Docker (loopback, strong key, xAI model) and answering a test. DONE 2026-11-07: `concierge-stack/hermes/start-hermes.sh`, `ask-hermes.sh`.
2. Guardrail module (Python) with tests, ported from SocialSync, as an MCP tool for Hermes and a gate in front of every draft.
3. Connect Hermes to Upload-Post's free plan for the proof (its API or MCP; our approval gate decides when anything is sent), and later to self-hosted Postiz.
4. End-to-end test with one test customer: link by invite, Hermes drafts from site content, guardrails pass or block,
   draft lands in Postiz, approval by text or email, then schedule.
5. Put SocialSync's current code under git and into backups (it is in neither today), and decide whether any of it is kept.
6. Then the earlier items: reword the website to match what is proven, and the remaining Concierge core pieces, using
   Hermes (Gmail, Calendar, email and text gateways) where it already does them.
