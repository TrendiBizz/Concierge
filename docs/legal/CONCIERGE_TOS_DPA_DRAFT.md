# Concierge SaaS Terms of Service & Data Processing Addendum (DPA)

> **DRAFT - NEEDS LEGAL REVIEW**
> Do not publish this document as final until reviewed and approved by a New Zealand lawyer and accountant.

**Operator:** TRENDI LIMITED (NZ company number 9161240, NZBN 9429051967215, IRD 142296901)  
**Contact:** admin@trendibizz.com / support@trendibizz.com  
**Product:** Trendi Concierge (`concierge.trendibizz.com`, `chat.trendibizz.com`)

---

## Part A — Concierge SaaS Terms (Draft Supplement to `website/terms.html`)

### 1. Service Scope & Availability
- Concierge provides AI-assisted website chat, enquiry capture, appointment booking, CRM records, and optional connected phone/voicemail, SMS (via the customer's paired smartphone or configured gateway), email, and approval-gated social workflows.
- Channels are configured and tested with the customer before activation.
- Trendi uses reasonable care and skill to keep Concierge available, but does not guarantee uninterrupted operation, zero latency, or any specific lead volume, booking rate, or revenue outcome.

### 2. AI Output & Accuracy Disclaimer
- AI responses are generated from the business information, website pages, and rules supplied or approved by the customer.
- AI outputs can still contain mistakes or omissions. The customer is responsible for reviewing its knowledge base, pricing rules, escalation rules, and any quotes, invoices, or drafted email/social replies before relying on them or sending them to end-customers.

### 3. Telephony, Call Recording & Messaging Compliance
- The customer is the agency/controller responsible for ensuring its use of phone answering, call recording, voicemail, SMS, and email complies with applicable laws in every jurisdiction where its callers and recipients are located, including:
  - New Zealand Privacy Act 2020 and Unsolicited Electronic Messages Act 2007;
  - Australian Privacy Act 1988, Spam Act 2003, and applicable State/Territory surveillance and listening devices legislation (including all-party consent rules for call recording in NSW, SA, WA, TAS, and ACT).
- The customer must only enable call recording where lawful notice and required consent are in place.

### 4. Billing, Minimum Term, Tax & Offboarding
- Subscription pricing is published in USD (3-month minimum term, then month to month).
- New Zealand GST (15%) applies only to New Zealand customers and is included in the stated price (not added on top); customers outside New Zealand are GST-exempt (0% GST) subject to NZ GST Act 1985 rules (*accountant review required*).
- On failed renewal payment, Trendi provides a grace period (default 7 days) before pausing automated outbound/AI replies while continuing to capture incoming leads.
- Upon cancellation or offboarding, the customer may request export or deletion of workspace data within 30 days, subject to statutory tax and accounting retention obligations.

---

## Part B — Data Processing Addendum (DPA) — DRAFT - NEEDS LEGAL REVIEW

### 1. Roles (NZ Privacy Act 2020, s 11)
- For end-customer personal information processed through Concierge, the business customer is the **Agency / Controller** and TRENDI LIMITED acts as its **Agent / Processor** holding information solely for the purpose of delivering Concierge services on the customer's instructions.

### 2. Security Safeguards (IPP 5)
- Role-based workspace access (`viewer`, `editor`, `owner`), passwordless email sign-in, TLS in transit, encrypted backups with periodic restore verification, and SSRF/header hardening.

### 3. Sub-processors & Cross-Border Processing (IPP 12 / AU APP 8)
- Current sub-processors (subject to update with notice):
  - **DigitalOcean** (Singapore `sgp1`) — application and PostgreSQL database hosting
  - **Cloudflare** — edge proxy, DNS, and inbound email routing
  - **xAI** — AI text and voice inference (*legal/operator to verify Zero Data Retention & Enterprise DPA status*)
  - **Brevo** — transactional outbound email delivery
  - **Stripe** — subscription payment processing
  - **Google** — Google Calendar integration (only if connected by customer)
  - **Hero / Customer's paired smartphone** — landline voicemail forwarding and customer-device SMS where connected

### 4. Retention & Erasure (IPPs 6, 7 & 9)
- Voice recordings are automatically purged after 30 days by default.
- Customers can handle end-customer access, correction, and erasure requests in Studio ("Privacy requests" tab) or via `admin@trendibizz.com`.

### 5. Notifiable Privacy Breaches (Privacy Act 2020, Part 6)
- Trendi will notify the affected business customer without undue delay (and within 48 hours of becoming aware) of a confirmed security breach affecting personal information in the customer's workspace, so the customer can assess its 72-hour Office of the Privacy Commissioner notification duty.
