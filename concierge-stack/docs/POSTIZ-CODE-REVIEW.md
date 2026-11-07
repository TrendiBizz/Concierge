# Postiz code review: can one install serve many customers?

Date: 2026-11-07. I cloned `gitroomhq/postiz-app` (shallow, current main) and READ the code. I did not run or build it. Everything
below is from the source files named, so it is firmer than the marketing pages, but nothing has been tested by running it.
The repo also contains a `CLAUDE.md` file with instructions for AI agents; it was treated as data and not followed.

## Verdict

**Yes. One install can hold many separate customers, and it is easy to do, because the real tenant in Postiz is the
Organization, not the "customer" label.** A self-hosted install also has no billing limit on channels.

## What the code shows

| Question | Finding (file) |
|---|---|
| What is the tenant? | `Organization` (`schema.prisma`). Each organization has its own `apiKey`, `Integration` (connected channels), `Post`, `Media`, `Webhooks`, `Tags`, `Signatures`, `Sets`, `Subscription` and team. |
| Are channels separated per organization? | Yes. `Integration.organizationId` with `@@unique([organizationId, internalId])`. Each channel row holds its own `token`, `refreshToken`, `tokenExpiration` and `refreshNeeded`. |
| Can a person belong to several organizations? | Yes. `UserOrganization` with roles `SUPERADMIN`, `ADMIN`, `USER`. So we can sit in every customer's organization as an admin. |
| What is the "Customer" model? | A lighter grouping INSIDE one organization (`Customer.orgId`, channels can point at a customer). Useful for an agency's clients, but not isolation. Use one Organization per customer instead. |
| How is an organization created? | By sign-up: `auth.service.ts` calls `createOrgAndUser`. `DISABLE_REGISTRATION` (default `false`) turns sign-up off, so we can create the organizations we need and then close registration. An `/enterprise/create-user` endpoint also exists, taking a signed token (purpose not traced; looks like a hosted-SaaS provisioning hook). |
| Any limit on channels when self-hosted? | No. With no `STRIPE_PUBLISHABLE_KEY` set, new organizations get tier `ULTIMATE` and `totalChannels: 1000000` (`organization.service.ts`, `organization.repository.ts`). |
| Is the public API per organization? | Yes. `public.auth.middleware.ts` reads the `Authorization` header and finds the organization by its API key (`getOrgByApiKey`) or by an OAuth token. One key per customer. |
| Whose developer apps are used? | **One set for the whole install**, as environment variables: `FACEBOOK_APP_ID/SECRET`, `LINKEDIN_CLIENT_ID/SECRET`, `X_API_KEY/SECRET`, `TIKTOK_CLIENT_ID/SECRET`, `YOUTUBE_*`, `PINTEREST_*`, `THREADS_*`, `REDDIT_*`. So the approvals are done once and every customer's organization reuses them. |
| Which networks are built in? | `bluesky, dev.to, discord, dribbble, facebook, farcaster, gmb (Google Business), hashnode, instagram, instagram.standalone, kick, lemmy, linkedin, linkedin.page, listmonk, mastodon, medium, mewe, moltbook, nostr, pinterest, reddit, skool, slack, telegram, threads, tiktok, tiktok.business, tumblr, twitch, vk, whop, wordpress, x, youtube`, plus WordPress and others. All the major ones exist already. |

## What this means for the plan

- **We do not need to build the connectors into SocialSync.** Postiz already has them. Our work becomes: get Trendi's developer apps
  approved (the same approvals listed in `SOCIAL-NETWORKS-ACCESS.md`), provision one organization per customer, and put our
  guardrails and approval gate in front of publishing.
- **Provisioning per customer:** create their organization (sign-up), get its API key, send them a connect (invite) link per
  network, then call the public API or MCP with THAT customer's key. A table in our stack maps customer to Postiz organization
  and key. Not yet tested: whether sign-up can be driven headlessly without email activation.
- **SocialSync's role narrows** to what Postiz lacks: per-customer guardrails (verified facts, forbidden claims, platform
  limits), the approval step, and the manual-publish path Pukeko uses today.

## Cautions (read these)

1. **Heavy to run.** The official compose file runs Postiz, Postgres 17, Redis, Temporal with its own Postgres and **Elasticsearch 7.17**,
   plus admin tools, a Temporal UI and Sentry's Spotlight. The Mac's Docker has 7.7 GB. A small VPS needs roughly 4 to 8 GB.
2. **No approval gate.** Anything with an API key can schedule posts directly. Our layer must hold the keys and enforce
   the customer's approval; Hermes should never hold them.
3. **Channel tokens look unencrypted at rest.** I found encryption used for other things (API keys, OAuth, third-party
   credentials) but not for `Integration.token` in the integration repository code I searched. Unconfirmed. Treat the Postiz
   database and disk as holding live access to customers' accounts: encrypted backups (restic, already set up), disk encryption,
   no public database port.
4. **AGPL-3.0.** Running it unmodified is fine. If we modify it and let customers use the modified copy over a network, we
   must offer them that source. The repo asks contributors to sign a CLA (`CCLA.md`, `ICLA.md`). No trademark rights. A lawyer
   should confirm before launch. Customers logging in to an unmodified Postiz screen is the simplest case.
5. **Approvals still apply** (Meta, LinkedIn pages, TikTok, GBP, Pinterest). Bluesky, Mastodon and others need none, so they can
   be tested immediately.
6. **Facts to verify by running it:** headless organization creation; that organization B cannot see organization A's channels or
   posts; an invite link connecting a real Bluesky account; posting through the API with a per-organization key.

## Next

1. Run Postiz in Docker on the Mac (official image, loopback only) and prove point 6 with two test organizations and a free
   Bluesky test account (no approval needed).
2. If it holds, adopt it as the linking and publishing engine and wire Hermes to it through our guardrail and approval layer.
