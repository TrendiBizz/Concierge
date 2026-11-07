# Scaling Concierge to many customers, and plugging in their own software

Status: DESIGN ONLY (2026-11-07). Nothing here is built except what is marked "exists today".
Decision owner: Jo. Nothing in this document changes the live assistant until Jo approves a step.

## 1. What Jo asked for

- Concierge is sold as a subscription (USD 200 a month, 3-month minimum, yearly plan 15% off; see `PRODUCT.md`).
- Each customer's Concierge is set up around THEIR business: their own phone number, text (SMS) and email details,
  their hours and their own pages.
- Everything it records goes into THEIR CRM, and they choose how they are told (email or text; voicemail planned).
- Customers who already have a CRM, email system and so on must be able to connect them.
- The Trendi Grok voice assistant and its core functionality stay ours, identical for every customer.
- It must be easy to replicate and scale when there are more customers.

## 2. Where we are today (exists today)

The stack is single-customer. Facts from the code:

| Concern | Today | Problem at 2+ customers |
|---|---|---|
| Business identity and wording | `BUSINESS_NAME` env var; `KNOWLEDGE` text in `agent/agent.py` written about Trendi's three services | One business only |
| Owner alerts | `OWNER_EMAIL` env var, always email | No choice of channel or recipient per customer |
| Email sending | one SMTP account (`SMTP_*`, Brevo) | One sender identity |
| SMS | `SMS_PROVIDER=mac` (your Mac and iPhone) or Telnyx (untested) | The Mac cannot send for many customers or from their numbers |
| Bookings | `BOOKING_*` env vars, one SQLite file | One calendar |
| Data | `data/` (SQLite, `messages.jsonl`, `outbox.jsonl`, `transcripts/`) | Everyone's data would be mixed |
| Phone routing | one LiveKit dispatch rule, `agentName: trendi-concierge` | No way to tell which business was called |
| Backups | restic of all of `data/` | Cannot restore or delete one customer alone |

What already works in our favour: the SMS layer is already behind a small contract (`sms_providers.py`: `sent`,
`failed`, `unverified`), statuses are honest everywhere, and transcripts, call guard and backups are separate modules.

## 3. The principle: core is ours, everything else is data or an adapter

1. **Core (never forked per customer).** The Grok voice assistant, conversation rules and honesty guards, call guard,
   transcript writer, status contract (`sent` only when confirmed), booking engine, backups. One codebase, one version.
2. **Customer profile (data).** Name, greeting wording, knowledge text, hours, voice, notification choices, which adapters to
   use and their settings. Changing a profile never changes behaviour rules. A profile cannot switch off the honesty rules.
3. **Adapters (code we write, configured per customer).** Each outside system sits behind a small interface that returns
   the same honest statuses. A customer's own CRM or email is connected by an adapter we write and test, never by
   changing core code. That is how "their software" plugs in while "our core stays ours".

Trendi itself becomes **customer zero**: the current setup moves into a profile called `trendi`. If the model works for
us, it works for the next customer, and every step below keeps Trendi's own assistant running.

## 4. The customer profile

One folder per customer, created by a script, never hand-edited in several places:

```
customers/<slug>/
  profile.yaml      # non-secret settings
  knowledge.md      # what the assistant may say about this business (loaded from their pages, reviewed by us)
  secrets.env       # API keys and passwords (git-ignored; later a secrets manager)
data/<slug>/        # that customer's database, messages, outbox, transcripts (git-ignored)
```

`profile.yaml` fields (all validated; unknown or missing values stop provisioning with a plain message):

- `business_name`, `greeting_name`, `timezone`, `voice` (one of an approved list), `language`
- `hours` (open, close, days, slot minutes, notice, horizon): today's `BOOKING_*`
- `phone`: inbound number(s) for this customer and how callers reach a human (`transfer_number`)
- `email`: sender address and domain (DKIM set up for THEIR domain, or their own SMTP login)
- `sms`: sender number and provider
- `notify`: who is told, how (`email`, `text`, later `voicemail`), for what (new message, booking, daily digest), quiet hours
- `crm`: adapter name and its settings (section 6)
- `calendar`: adapter name (built-in, later Google or Outlook)
- `retention`: transcript days (default 30)
- `plan`: monthly or yearly, start date, minimum-term end date (for billing and renewals only)

## 5. Knowing which business was called

- **Phone:** the called number tells us the customer. LiveKit passes the dialled number to the agent as a SIP attribute;
  a small lookup (`number -> slug`) loads that profile when the call starts. One agent worker serves all customers
  (a LiveKit worker already handles many calls at once), so adding a customer is data, not a new server.
- **Website chat:** the widget key identifies the customer.
- **Console and tests:** `--customer <slug>`.
- **Their number:** a customer either forwards their existing number to the number we hold for them, or ports it to our
  SIP provider. Conditional call forwarding is the lowest-risk start. NZ number and carrier support are still unconfirmed.

## 6. Adapters (how their software plugs in)

Every adapter implements the same shape and returns `sent`, `queued`, `failed` or `unverified`. The agent only ever
says something was done when the status is `sent`.

| Port | Built-in (ours) | Customer's own, added as demand appears |
|---|---|---|
| **Mailer** (send email) | Brevo SMTP from the customer's authenticated domain (exists today for Trendi) | Their SMTP login; Google or Microsoft mail |
| **SmsSender** | Hosted provider with the customer's own number (NZ-to-NZ sending still unconfirmed for Telnyx and Twilio); Mac gateway only for Trendi | Their account at a provider |
| **Notifier** | Email and text now; voicemail later | none (we own this) |
| **CRM** | Built-in simple lead list with CSV export and owner view (rule-based scoring exists locally) | **Generic webhook first** (one JSON POST to any URL their system accepts), then named connectors (for example a hosted CRM) only when two or more customers ask for the same one |
| **Calendar** | Built-in slots (exists today) | Google or Outlook calendar |
| **Telephony** | LiveKit SIP | their SIP trunk |

Why webhook first: it connects almost anything (including tools like Zapier or Make) without us writing and maintaining a
connector per product. Named connectors come later, one at a time, each with its own tests.

### Loading their CRM reliably (the "outbox")

1. Every recorded event (message, booking, call summary) is first written to OUR own append-only log for that customer.
   That log is the source of truth and is what backups protect.
2. A sync step delivers each event to the customer's CRM adapter, with a stable id (booking id or message id) so a retry
   never creates a duplicate, and automatic retries with back-off.
3. If their CRM is down or rejects the data, the event stays queued, we tell the customer through their chosen channel,
   and nothing is lost. The agent never claims "added to your CRM" unless the adapter said `sent`.

## 7. Telling the customer what was recorded ("their choice")

`notify` in the profile decides channel, recipients and triggers. Today `agent.py` always emails `OWNER_EMAIL`; that
becomes one Notifier reading the profile. A customer can choose email, text, or both, per trigger, plus a daily digest.

**Voicemail is not built and not designed in detail.** Sketch: an outbound call to the customer's number that reads a
short spoken summary and leaves it if unanswered, using LiveKit outbound SIP plus text-to-speech. It needs outbound calling
set up with a carrier, consent wording, and cost per call. Until then the site says "planned".

## 8. Replicating a customer (the onboarding path)

Scripts, in the same style as `set-key.sh` and `set-backup.sh` (secrets typed hidden, never in chat):

1. `new-customer.sh <slug>`: creates `customers/<slug>/` from a template, a data folder, and prints the checklist.
2. `customer-check.sh <slug>`: runs real checks and prints only pass or fail: profile validates; test email from their
   sender; test text; test CRM push; scripted chat conversation using their knowledge; a dry-run booking.
3. Switch-on is a separate, explicit step per channel (matches the site's "set up and tested before it is switched on").
4. `customer-export.sh <slug>` and `customer-delete.sh <slug>`: their data in one folder makes handover and deletion
   possible, and restic tags per customer make restoring one customer possible.

Onboarding checklist per customer: business name and hours; website to load as knowledge; their number and how callers
reach a person; email domain (DNS records for DKIM); SMS number; where recorded data should go (built-in list, their CRM,
webhook URL); how and when they want to be told; who may be told; agreed start date and plan.

## 9. How it scales (phases with triggers)

| Phase | When | What changes |
|---|---|---|
| 0 | now | Single customer (Trendi). Mac for SMS. |
| 1 | first paying customer | Profiles, per-customer data folders, called-number routing, Notifier and CRM adapters (built-in list and webhook), provisioning scripts, move to the VPS (Linux), hosted SMS provider. Trendi = customer zero. |
| 2 | about 5 to 25 customers | Postgres with a customer id on every row instead of SQLite and files; secrets manager; per-customer usage metering (call minutes, messages) and an admin view; Stripe subscriptions and customer portal; monitoring and alerts; per-customer backups. |
| 3 | 25 and beyond | More agent workers behind LiveKit; rate limits per customer; named CRM connectors on demand; audio recording through LiveKit egress; maybe customer-facing dashboard. |

Do the cheap thing first and move up only when a number forces it: SQLite and files are fine for the first few customers
because each customer's data is already separate.

## 10. Risks and decisions Jo needs to make

- **Cost at USD 200 a month is unknown.** Voice minutes (xAI), phone minutes, texts and email all cost money per use.
  Before selling many, measure real cost per customer per month and decide a fair-use limit. No limits are published
  today. Metering (Phase 2) is the tool, but a rough cost estimate from a test month should come first.
- **Legal and privacy.** Trendi would hold callers' personal data on behalf of each customer (a processor role). Terms
  currently cover SEO and do not cover Concierge (renewal, cancellation, refunds, data handling). A data processing
  agreement, the privacy policy, and call-recording consent per customer are needed before launch. Not legal advice; a
  lawyer should review.
- **Phone numbers and carriers.** NZ number availability, porting and call forwarding are unconfirmed.
- **SMS from the customer's own number.** The Mac gateway cannot do this at scale; a hosted provider that can send from
  an NZ number to NZ mobiles must be confirmed (Telnyx and Twilio are unconfirmed).
- **Email deliverability** is per customer domain: DNS records each time, and reputation to watch.
- **Support load** grows with each custom connection. The webhook-first rule limits it.

## 11. Proposed build order (each step small, tested, and Trendi keeps working)

1. **Profile loader.** Read `customers/trendi/profile.yaml` and expose the same values the env vars give today. Tests prove
   Trendi behaves exactly as now. (No behaviour change; this is the safe first step.)
2. **Per-customer data folders and the agent reading the profile** (name, hours, knowledge, owner contact) instead of env
   vars and the hard-coded Trendi text. Needs Jo's go-ahead because it edits `agent/agent.py`.
3. **Notifier** (email and text, per profile) replacing the fixed owner email.
4. **CRM outbox** with the built-in list and the webhook adapter, plus retry and idempotency.
5. **Provisioning scripts** (`new-customer.sh`, `customer-check.sh`, export and delete).
6. **Called-number routing** and the VPS move; hosted SMS provider.
7. Voicemail notices, named connectors and Postgres only when a customer or a measured limit needs them.

Steps 1 to 5 can be built and tested on the Mac without any new accounts. Nothing here touches production, DNS or paid
accounts without separate authorisation.
