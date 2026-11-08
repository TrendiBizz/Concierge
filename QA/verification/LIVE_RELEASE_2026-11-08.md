# Trendi Concierge live release — 8 November 2026

User authorised production deployment, activation and live testing to their own
phone and admin@trendibizz.com. Production now runs the current canonical API
source, rather than the former prototype application. Production databases and
the encrypted social database were backed up before rollout and again before
workspace unification. Private rollback configuration and dumps are retained in
`.private/live-release-20261108/`; no credentials are committed.

## Live result

- Website: https://trendibizz.com/concierge, Cloudflare production deployment
  `6bcc4248-ff87-4058-98fd-a9a3eef56c21`.
- Published pricing: USD $400 monthly; annual list USD $4,800 less 15% = USD
  $4,080, saving $720. Existing minimum-term and GST wording is retained. SEO and
  pentesting services and their existing payment links are preserved.
- Website explicitly describes the built-in CRM and enquiry capture/replies for
  connected calls, emails, texts and website chat, with channel activation conditions.
- Public owner portal: https://concierge.trendibizz.com/owner-ui. It now uses the
  canonical production API/database on loopback 8000. The original connected
  workspace slug remains `trendi-oauth-staging`, displayed as **Trendi Concierge**.
  Existing owner password, sessions and all four social accounts are preserved.
- That same workspace now owns the existing public widget key, current knowledge,
  conversations and live test enquiry. The original public prototype tenant is
  archived, with a different unpublished key; it holds no active business data.
- Current API image: `concierge-api:live-crm-20261108`; all **49** app/static files
  were compared byte-for-byte with canonical source. Native Rust social service
  was re-executed from the current binary using its existing private database and
  configuration. No tokens were copied or OAuth grants repeated.
- Owner portal now shows tenant-scoped CRM enquiries, appointments and tasks and
  allows owners/editors to progress enquiries through the pipeline. Anonymous,
  other-tenant and viewer writes are rejected.

## Actual live checks

The public Grok chat endpoint was exercised. An initial test caught obsolete
prototype seed knowledge advertising unrelated tiers. The pre-release database
retains that material for rollback; 21 specifically identified prototype documents
were retired from active RAG only after current Trendi website content embedded
successfully. Active business knowledge contains 28 real embedding chunks. A fresh
live answer then correctly quoted **$400 monthly / $4,080 annually** and the built-in
CRM. This was a real provider response, not a model stub.

A controlled test event was signed and posted through the actual public authenticated
email ingress. It created one CRM enquiry and a review-required reply draft. The
approved test reply passed through the real durable outbox and Brevo SMTP:
`status=sent`, `attempts=1`, no error. Gmail independently confirmed the message
arrived in the user's inbox with subject **Re: Trendi Concierge live deployment
test**. The test enquiry remains in the CRM and is clearly labelled as a test.
This verifies signed ingress and actual outbound delivery; it is not a test of an
external mailbox provider automatically forwarding an incoming email to the API.

Real browser verification confirmed the published page, built-in CRM copy and
both prices. API and public owner portal returned 200; unauthenticated public CRM
returned 401. Twenty CRM and the existing Docker stack remain running.

## Activation limits — do not call these live

- **Automatic incoming mailbox intake:** the signed API is active and the mailbox
  mapping is prepared, but the existing Cloudflare credentials return HTTP 403,
  error 10000, on Email Routing settings/rules. Email Worker/mailbox forwarding was
  not changed. A credential with the required Email Routing access or an owner
  dashboard setup is still needed; preserve existing mail forwarding.
- **SMS:** no Twilio or SMS Gateway credentials are configured in the canonical
  API. The separate legacy Mac/iPhone provider is not an integrated inbound SMS
  adapter. No SMS was sent and no handset delivery is claimed.
- **Telephone:** the canonical PSTN adapter has no configured provider number or
  credentials. It remains off; no real call, transfer or recording was performed.
  Existing LiveKit/Grok code/configuration is preserved. Its source pricing was
  updated, without claiming a newly tested telephone service.
- **Social publishing:** remains disabled. Preserved account connections are not
  proof of production publishing approval or LinkedIn company Page access.
- **Payments:** Concierge subscription checkout links remain unset. This release
  publishes the agreed prices; it does not claim to have charged a subscription.

## Regression verification

- Python unit/config checks: **73 passed**.
- New actual PostgreSQL enquiry/owner CRM suite: **14 passed**, including concurrent
  replay dedupe, email capture independent of AI, SMS capture during AI failure,
  contact enrichment without duplicate enquiries and owner/viewer/tenant boundaries.
- Signed email ingress integration: **17 passed**.
- Simulated phone/recording regression: **29 passed**; explicitly not real calls.
- Offline owner/operator JavaScript contracts: **8 passed**.
- Website client contracts: **10 passed**.
- Production website SEO gate: **21 passed**, no failures or warnings. Security
  preflight passed with the existing six reviewed scanner notices.
- Fixed IndexNow's macOS Bash compatibility; both IndexNow endpoints returned 200.

The owned disposable release QA database used loopback 55432 and synthetic data
only, and was removed after verification. Unrelated office-shots and tiktok-review
artifacts were preserved.
