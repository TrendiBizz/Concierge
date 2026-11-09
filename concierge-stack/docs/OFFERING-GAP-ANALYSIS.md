# Concierge: what is promised, what is built, and what GoHighLevel has that is worth copying

> **CORRECTION (2026-11-07, later the same day).** This analysis judged the product by the voice stack alone and so
> overstated the gaps. A separate platform already exists on Jo's Mac (`TrendiBizz/Concierge`: multi-tenant core API,
> booking, reminders, two-way text, review requests, a Twenty CRM with a lead bridge, calendars, an inbound email bridge,
> SocialSync). Read `PLATFORM-AND-SOCIALSYNC-FINDINGS.md` first. Section 2's "not built" column is true of THIS voice stack
> only. The real gaps are connection (the voice assistant does not use the platform), identity across modules, proof
> against real providers, and a phone line. Sections 3 to 6 (what is worth adding and what is bloat) still stand as a
> checklist to compare against the platform.

Date: 2026-11-07. Written for Jo to decide what to build. GoHighLevel facts come from third-party summaries and reviews,
not its official documentation, so treat them as a guide to the market, not as exact specifications.

## 1. The promise (Jo's words)

"A complete turnkey solution": answering calls, replying to emails, sending texts, capturing data from calls for the
CRM, appointments in the calendar, meetings and scheduling, all of it where required.

## 2. What is actually built today

| Part of the promise | Status in this voice stack | Gap |
|---|---|---|
| Answering calls | Voice assistant built and tested on the Mac console. Greeting, service questions, messages, bookings, hang-up guard, transcripts all work. | **No phone number or line yet.** |
| Sending texts | Outbound text built, from Jo's own number through the Mac (Trendi only). | **Cannot receive or reply to texts.** Mac gateway does not scale or work from a customer's number. |
| Replying to emails | Sending email works (Brevo). | **Not built.** It cannot read or answer incoming email. |
| Capturing call data for the CRM | Saved locally (messages file, bookings database, transcripts) and emailed to the owner. | **CRM delivery not built** (design only: `SCALING-AND-INTEGRATIONS.md`). |
| Appointments and scheduling | Built-in slots (hours, notice, no double booking) and an email invite. | **No Google or Outlook calendar. No meeting links. No cancel or reschedule.** |
| Reminders, follow-up, lead scoring | Described on the website and in the phone assistant's own knowledge text. | **Not built in this voice stack.** The separate chat service (not in this repo) may have some of it. Either build it or stop describing it. |

So the first job is not copying GoHighLevel. It is making the promise true: inbound email, two-way text, calendar,
CRM delivery and a phone line.

## 3. What GoHighLevel offers (secondhand) and what to do about it

Per third-party summaries, GoHighLevel bundles: a CRM and pipelines, a unified inbox (text, email, social, calls), missed-call
text-back, web chat, an AI voice agent and chat bot, calendars and booking, review requests and reputation tools, email and
text campaigns, a workflow builder, funnels and a website builder, forms, payments, courses, a social planner,
reporting, and white-label reselling.

### Worth adding (small, directly serves "answer, record, book, follow up")

| # | Feature | Why it earns its place | Notes |
|---|---|---|---|
| 1 | **Calendar sync, reschedule and cancel, optional meeting link** | You promised calendar and meetings; it is the core of booking. | Google and Outlook first. Built-in slots stay as the fallback. |
| 2 | **Appointment reminders and no-show follow-up** (text or email, with a reschedule link) | Fewer no-shows; owners notice immediately. | Needs a working text channel. |
| 3 | **Missed-call and after-hours text-back** | Never loses a caller whose call drops or who rings after hours. | A text with a booking link. |
| 4 | **Two-way text and email inbox**, replies handled by the assistant or passed to the owner | Makes "replying to emails" true. | Start in "draft for owner approval" mode for email; automatic replies only after trust is earned. |
| 5 | **One contact timeline per person** (calls, transcripts, texts, emails) | This is the built-in CRM view for customers who have no CRM. | Also what a webhook sends to their own CRM. |
| 6 | **Review requests after a visit** (their own Google review link) | A small, high-value local-business feature. | Never filter who is asked based on how happy they seem; that breaks Google's rules. |
| 7 | **Weekly owner summary** (calls answered, leads, bookings, after-hours calls, follow-ups due) | Shows the value every week and reduces cancellations. The SEO service already has a weekly report. | By their chosen channel. |
| 8 | **Light lead follow-up nudges** (for example one follow-up after one day and one after three, stopping when they reply) | Part of "follow-up" you already advertise. | Needs consent and an unsubscribe or STOP reply. |

### Later, only when customers ask

Text-to-pay or deposit links (Stripe; the payment rules in `PRODUCT.md` apply), WhatsApp, Facebook and Instagram messages
(platform approvals needed), Google Business Profile messages, call routing rules, other languages, voicemail notices.

### Leave out (this is the bloat)

Website and funnel builder, courses and memberships, social media planner, full email and text campaign builder,
drag-and-drop workflow builder, proposals, invoices and e-signing, affiliate management, a dialer or call-centre tools,
blogging, surveys, white-label reselling.

## 4. The test for any new feature

It goes in only if it helps the owner **answer, record, book or follow up** on an enquiry, and we can run it for them.
If the customer must build and manage it themselves, that is GoHighLevel's model, not ours. GoHighLevel is a toolbox the
customer assembles; Concierge is the finished service we set up and run.

## 5. Suggested order

1. Make the promise true: phone line, hosted text channel, CRM delivery adapters, calendar sync.
2. Reminders, missed-call and after-hours text-back (protect revenue, simple, mostly outbound).
3. Two-way inbox with email drafts for approval, then the contact timeline.
4. Review requests, weekly summary, follow-up nudges.

## 6. Cost and legal cautions

- Each feature adds real cost per use (texts, email, calendar calls, voice minutes). At USD 200 a month, measure cost per
  customer before promising anything unlimited, and write a fair-use rule.
- Reminders, follow-up nudges and review requests are commercial electronic messages: under New Zealand's Unsolicited
  Electronic Messages Act they need consent and an unsubscribe route. Booking confirmations the caller asked for are
  probably fine. Have a lawyer confirm.
- Until a feature is built and tested, the website and the phone assistant must not say Concierge does it, or must say
  it is planned.
