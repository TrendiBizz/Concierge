# Wave CRM — Product Audit & Rebuild Specification

**Research date:** 2026-11-16
**Subject:** Wave CRM (https://wavecrm.com.au), an Australian membership-management CRM/AMS for chambers of commerce, industry bodies and associations, built and operated by SafeCo (ABN 52 640 780 043), Queensland.
**Method:** Read-only fetching of the public marketing site, the Xero App Store listing, the public tenant login pages, and 39 first-party YouTube video descriptions on the official Wave CRM channel. No forms submitted, no demos requested, no accounts created, nothing signed up for.

**One-line summary:** Wave CRM is a single-tenant-per-subdomain, flat-priced ($412.85/mo + GST) Australian membership CRM that bundles member records and renewals, a branded member portal with directory/resources/digital wallet cards, drag-and-drop EDM campaigns, trigger-based scheduled communications, an in-house event ticketing engine (SafeTicket-derived, replacing Eventbrite), CPD compliance tracking, and a certified two-way Xero invoicing integration — with unlimited members and assisted migration as headline inclusions.

---

## 0. Evidence base and confidence

| Source type | What it gave us | Confidence |
|---|---|---|
| Marketing site (7 pages) | Feature claims, pricing, hosting claims, positioning, roadmap | High for claims; medium for depth (marketing language) |
| Xero App Store listing | Independent-ish confirmation of two-way Xero integration and product description | High |
| Public tenant login page (`ausagritech.wavecrm.com.au`) | Auth flow, MFA, multi-account sign-in, branding-per-tenant, T&C linkage | High (observed directly) |
| 39 official YouTube video descriptions @waveawesomecrm | **The richest source.** Actual admin navigation paths, field names, statuses, report names, workflow order | High — but descriptions, not frame-level UI |
| Screenshots on marketing site | Alt text + surrounding copy only | Low–medium; I did **not** render the images |

Three explicit caveats used throughout this document:

- **[STATED]** — written on a first-party page or in a first-party video description.
- **[OBSERVED]** — something I directly observed by fetching a live URL (e.g. HTTP behaviour, page markup).
- **[INFERENCE]** — my reasoning from the above, not stated by Wave.

Video descriptions are cited as `youtube.com/watch?v=<id>`; the description text is the evidence, not the video frames.

---

## 1. What Wave is, and who it is for

Wave describes itself as "a CRM platform made in sunny Queensland", "Wave© 2026 is a product of SafeCo", and positions explicitly at membership organisations: "Wave has been specifically designed for membership organisations, including chambers of commerce, industry bodies and associations" ([home](https://wavecrm.com.au/)).

Origins and current team, from the About page: Nathan and Sandy met via Brisbane Junior Chamber of Commerce in 2018; SafeVisit (contact tracing) in 2020, then SafeTicket, then Wave launched in 2022 ([about](https://wavecrm.com.au/about)). Named team: Nathan (Co-Founder), Sandy (Co-Founder), Keely (Designer), Chris (Developer), Travis (Developer) ([about](https://wavecrm.com.au/about)). Note that Keely, Sandy and Nathan are the on-camera presenters in the video library, i.e. a small team doing its own onboarding/training content.

Aggregate usage claims (note: the home page and the feature pages **disagree**, which is a data-quality flag on the marketing site, not necessarily on the product):

| Metric | Home page | Feature pages |
|---|---|---|
| Members served | 51,411 ([home](https://wavecrm.com.au/)) | "Inboxes reached 51.4K" ([email-campaigns](https://wavecrm.com.au/email-campaigns)) |
| Events hosted | 2,465 ([home](https://wavecrm.com.au/)) | 2,799 ([event-management](https://wavecrm.com.au/event-management)) |
| Tickets sold | 75,316 ([home](https://wavecrm.com.au/)) | 92,738 ([event-management](https://wavecrm.com.au/event-management)) |
| EDMs sent | 7.609M+ ([home](https://wavecrm.com.au/)) | 9.4M ([email-campaigns](https://wavecrm.com.au/email-campaigns)) |
| Revenue via platform | $17.73M "local economic benefit" ([home](https://wavecrm.com.au/)) | $17.73M "Revenue Generated" ([event-management](https://wavecrm.com.au/event-management)) |

`[INFERENCE]` The site is mid-rebuild: newer feature pages carry updated stats and the older home page copy has not been reconciled. Treat all figures as marketing, not telemetry.

Client logos visible on the site include Caloundra Chamber, Canberra Business Chamber, Logan Chamber, Valley Chamber, Townsville Chamber, Gold Coast North Chamber, GIWA, TSBE, Visit Sunshine Coast, ATAINZ, Committee for Adelaide, NSW Tourism Association, Caravan Parks Association of Queensland and ~50 more ([home](https://wavecrm.com.au/), [member-experience](https://wavecrm.com.au/member-experience)). `[OBSERVED]` The volume and diversity (chambers, industry associations, a NZ institute) confirms the target segment is 1–10 staff associations with committee governance, not enterprise.

---

## 2. Feature inventory by area

### 2.1 Membership records & renewals

- **Member create/edit.** "Audience → Members → Create new member": choose a **division** and **membership package**, decide **Active or Pending**, set an **expiry date (or Lifetime)**, enter member details, add **tags** and settings (including Xero, billing and direct-debit related options), fill in **arbitrary fields** ([0s-N06807uQ](https://www.youtube.com/watch?v=0s-N06807uQ)). `[STATED — video description]`
- **Membership statuses.** Cancel flow offers **Expired, Suspended, Disabled, Cancelled**, plus **Stop Next Renewal**, a required **reason under Notes**, tag updates and **Stop Communication** (unsubscribe) ([t4MExa7Oqu8](https://www.youtube.com/watch?v=t4MExa7Oqu8)). `[STATED]`
- **Member types / tiers.** "Membership package" (also called membership tier/level) drives price, portal access, Xero account code and user limits. **Add-ons** are optional extras alongside packages with fixed or variable pricing, availability control, quantity limits and per-package eligibility ([_9hNMjhC344](https://www.youtube.com/watch?v=_9hNMjhC344)). `[STATED]`
- **Package change without a new record.** Updating "Membership Level" from the member record produces new pricing, a new order/invoice, and preserves the member ([LEZHcMJhwl0](https://www.youtube.com/watch?v=LEZHcMJhwl0)). `[STATED]`
- **Renew expired members.** From the existing record: Billing & Orders → generate renewal invoice → send it → share the payment page link → confirm payment → membership returns to Active ([rlF5p5tDAdc](https://www.youtube.com/watch?v=rlF5p5tDAdc)). `[STATED]`
- **Automated renewals.** "Automatically create renewal Orders for eligible members, with recurring payment or invoicing based on membership configuration" ([xero-invoicing](https://wavecrm.com.au/xero-invoicing)). **Force Renew** keeps recurring renewal invoices issuing even when a member falls behind or status changes — "particularly useful for monthly memberships" ([G76ZL5sdN1A](https://www.youtube.com/watch?v=G76ZL5sdN1A)). `[STATED]`
- **Renewal visibility.** Membership status, expiry dates, upcoming renewal activity, whether Auto Renewal is active and when the next renewal processes ([xero-invoicing](https://wavecrm.com.au/xero-invoicing)). `[STATED]`
- **Applications → member conversion.** Form submissions under **Tools → Application forms** are reviewed, **Update Status → Approved**, then **Process Application → Create Member**; approving does *not* create the member ([K3n1RlYQZX0](https://www.youtube.com/watch?v=K3n1RlYQZX0)). `[STATED]`
- **Fields carried from application to member.** First name, last name, email and mobile copy automatically; questions marked **bind to key field** fill the matching member field; unlinked answers land in **Additional Information**; a "packages" field carries the chosen membership through ([socTts99ZFs](https://www.youtube.com/watch?v=socTts99ZFs)). `[STATED]` — this is the single most useful sentence in the corpus for data-model work.
- **Custom fields ("Arbitrary Fields").** Under **Account → Settings → Arbitrary Fields**, split into **Member Fields**, **Member User Fields** and **Auto Generate Numbers**. Each field has **Visible**, **Editable**, **Show on Report** flags. Field types: Text, Dropdown, Date, Email, Phone, Multi Checkbox, Checkbox, Multi Select ([uuoctxiYATc](https://www.youtube.com/watch?v=uuoctxiYATc)). `[STATED]`
- **Subscribers vs members are separate.** Subscribers are communicable contacts without membership; managed under **Audience → Subscribers**, with create, **import**, **export**, and tags. Membership status and subscription status are independent — an expired member remains subscribed unless unsubscribed ([zZrA5DcBZO0](https://www.youtube.com/watch?v=zZrA5DcBZO0)). `[STATED]`

### 2.2 Member portal / self-service

- **Member Hub** — "their own digital space to access membership details, explore events, view invoices and manage payments" ([member-experience](https://wavecrm.com.au/member-experience)).
- **Portal home** — banner image, configurable background and text colours, welcome title and welcome message, announcements, outstanding invoices surfaced on the dashboard ([tR8sVrH2df4](https://www.youtube.com/watch?v=tR8sVrH2df4), [tE2FZzbN6D0](https://www.youtube.com/watch?v=tE2FZzbN6D0)). `[STATED]` Settings live at **Account → Settings → Member Portal**.
- **Member-editable data** — the portal supports updating personal details, business details, billing contacts, payment methods, profile/banner/service images, bios, social links and directory visibility ([PgZ8zy91vt8](https://www.youtube.com/watch?v=PgZ8zy91vt8), [hN7DsIT_lAA](https://www.youtube.com/watch?v=hN7DsIT_lAA)). `[STATED]`
- **Portal sections seen in the walkthrough:** home screen, Resource Centre, Member Files, Events (view + register), Member Directory, Invoices & Payments, member details, directory profile, business/billing ([PgZ8zy91vt8](https://www.youtube.com/watch?v=PgZ8zy91vt8) chapter list). `[STATED]`
- **Multi-user memberships with Owner vs User.** One membership can have several portal users. **Owners**: view/update personal info, access and pay invoices, view previous invoices, use Directory and Resource Centre. **Users**: cannot access invoices or payment sections, cannot edit certain membership details, but can use Directory/Resource Centre where enabled ([hAJe8-g1cgU](https://www.youtube.com/watch?v=hAJe8-g1cgU)). `[STATED]`
- **Package-gated portal access.** Per package under **Account → Settings → Membership Settings → [package] → Configuration → Access Level**: **Member Resources**, **Member Users** (with an optional **maximum users limit**), **Community** (= Directory Listing + Public profile) ([Q2LAjjbQiDo](https://www.youtube.com/watch?v=Q2LAjjbQiDo)). `[STATED]`
- **Admin can impersonate.** "Login as User" from **Audience → Members → [member] → Account Access** — and Wave's own training recommends an incognito window so you don't log yourself out ([hAJe8-g1cgU](https://www.youtube.com/watch?v=hAJe8-g1cgU)). `[STATED]`
- **Digital membership cards** (Oct 2026) — branded cards in **Apple Wallet / Google Wallet**, **QR code scanning for live membership verification**, expiry date displayed, automatic removal from the wallet on expiry ([0NVkVjG6nqA](https://www.youtube.com/watch?v=0NVkVjG6nqA), [member-experience](https://wavecrm.com.au/member-experience)). `[STATED]`

### 2.3 Member directory & resources

- **Member Directory** — searchable, members discover/promote each other; can be restricted to members only ("peer to peer directory it is") ([member-experience](https://wavecrm.com.au/member-experience)).
- **Directory contact details are decoupled from the member record.** Since Sept 2026 the email/phone/other contact details shown publicly "no longer need to be identical to what's stored against the Member record", and admins can override on a member's behalf ([GOmhbt5Idq8](https://www.youtube.com/watch?v=GOmhbt5Idq8)). `[STATED]` — this is a real modelling decision worth copying: a `directory_profile` (or listing) distinct from `member`.
- **Member Resources** — file/folder library with **access restricted per membership**; folders and individual files each carry access settings ([YQbJd5a_gBE](https://www.youtube.com/watch?v=YQbJd5a_gBE)); "structure content based on membership tiers, incentivise member upgrades" ([member-experience](https://wavecrm.com.au/member-experience)). `[STATED]`
- **Posts** — CMS-lite content for the portal: create post, **generate a URL**, publish/unpublish, control access, build content with a drag-and-drop editor, organise posts into navigation folders ([zdsdNu5djUo](https://www.youtube.com/watch?v=zdsdNu5djUo)). `[STATED]` — this is the "website/CMS" seam.
- **Member Files** — member-uploaded documents surfaced in the portal ([PgZ8zy91vt8](https://www.youtube.com/watch?v=PgZ8zy91vt8)). `[STATED]`

### 2.4 Email campaigns (EDM) & segmentation

- **Drag-and-drop editor**, rows, hero images, titles, body text, CTA buttons, social links, colour/spacing styling, reusable content blocks, **anchor links** to jump within a long email, **Media Library** ([email-campaigns](https://wavecrm.com.au/email-campaigns), [y7nQDXuOgkE](https://www.youtube.com/watch?v=y7nQDXuOgkE), [vaQauva8tZY](https://www.youtube.com/watch?v=vaQauva8tZY)). `[STATED]`
- **Send now or schedule**; mobile preview before send; "Optimised HTML Output" claimed to render in Outlook/desktop/mobile ([email-campaigns](https://wavecrm.com.au/email-campaigns)). `[STATED]`
- **Segmentation:** "Select recipients based on membership, industry, location, ticket purchase. And then filter them out based on membership, industry, location, ticket purchase" ([email-campaigns](https://wavecrm.com.au/email-campaigns)). `[STATED]` — note the phrasing implies inclusion and exclusion filters over the same four dimensions.
- **Personalisation wildcards** including a **Company wildcard** added Sept 2026 ([GOmhbt5Idq8](https://www.youtube.com/watch?v=GOmhbt5Idq8)). `[STATED]`
- **Sender identities.** **Account → Settings → Email Settings → Customise Sender**: add rows of (local part before @, display name), pick per campaign from a **Sender** dropdown; the **sending domain must be set up first**; there is a **default sender** ([etM0ld1LBV8](https://www.youtube.com/watch?v=etM0ld1LBV8)). `[STATED]` — and Wave publishes guidance on "One Domain, Many Senders" ([video](https://www.youtube.com/@waveawesomecrm)).
- **Reporting.** Campaign report shows subject, total recipients (e.g. 1,142), campaign date, then **Opened 41.3%, Clicked 9.0%, Bounced 1.8%, Blocked 1.0%**, per-recipient engagement, **link clicks with unique vs total per URL**, and **Download as CSV** ([email-campaigns](https://wavecrm.com.au/email-campaigns), [LUK3FbEC1_A](https://www.youtube.com/watch?v=LUK3FbEC1_A)). `[STATED]`
- **"No tiered usage"** — "No tiered usage, say goodbye to that monkey business" ([home](https://wavecrm.com.au/)) — but see the fair-usage rule in §3.

### 2.5 Scheduled / triggered communications

- **Email Templates** + **Email Sequences** = "Drip Campaigns … automated sequenced communications based on membership triggers" ([home](https://wavecrm.com.au/)).
- Worked example: two expiry reminders (14 days before, 3 days before expiry) built as templates with a **Renew Membership** button linking to renewal, then combined into a sequence using the **"Before Member Expiry"** trigger ([4kho0w1LTdI](https://www.youtube.com/watch?v=4kho0w1LTdI)). `[STATED]`
- `[INFERENCE]` Trigger vocabulary is membership-lifecycle-shaped (before/after expiry, join, cancellation, at-risk CPD). The corpus only evidences "Before Member Expiry" by name; do not treat the others as confirmed.

### 2.6 SMS

- **Thin evidence.** "Email and SMS campaign+" is listed as included in the flat fee, with "+ Fair usage rule applies" ([home](https://wavecrm.com.au/)); SMS was a Q4 2023 roadmap item: "SMS Facility — Improve your engagement and cutthru through with SMS marketing." ([home](https://wavecrm.com.au/)).
- **No** SMS walkthrough exists among the 39 video descriptions, and no SMS page exists on the site. `[INFERENCE]` SMS ships as an outbound broadcast channel with per-account fair-use limits, but its UI, provider, opt-out handling and segment targeting are **unverified**. See §8.

### 2.7 Events & ticketing

Strongest-evidenced module; it is the SafeTicket engine productised into Wave.

- **Event setup:** dates, times, location, **capacity**, public or private, **virtual or in-person**, member vs non-member pricing, **earlybird**, **members only**, **tables or individuals or both**, dietary requirements, **additional questions**, add-to-calendar ([event-management](https://wavecrm.com.au/event-management), [y_BmQNMLuh4](https://www.youtube.com/watch?v=y_BmQNMLuh4)). `[STATED]`
- **Speakers & sponsors** — "Add, edit and manage speakers and sponsors across your event — all in one shareable place" ([event-management](https://wavecrm.com.au/event-management)).
- **Vouchers / discount codes** — name, code, **maximum redemptions**, **expiry**, and three types: **Percentage Off, Dollar Off, Fixed Price**, set per ticket; tested on the booking page ([uavwn3NuJYQ](https://www.youtube.com/watch?v=uavwn3NuJYQ)). `[STATED]`
- **Bookings dashboard** — "Search, filter and manage every booking. See attendees, payment status, ticket types and refund history across all your events in one place", with a summary stat bar of total attendees, gross revenue, transaction fees, refunded amounts and outstanding balances ([event-management](https://wavecrm.com.au/event-management)). `[STATED]`
- **Ticket holder lists** per session/event; **payments & refunds** tracking.
- **Event runsheets** — room setup, menu/catering, equipment, schedule, special requests, notes; **printable or save-as-PDF**, "shareable document" ([event-management](https://wavecrm.com.au/event-management), [G8ntvbkwYeY](https://www.youtube.com/watch?v=G8ntvbkwYeY)). `[STATED]`
- **Operational extras** — **duplicate event** carrying tickets, vouchers, questions, speakers and sponsors ([DSVcK40tmSY](https://www.youtube.com/watch?v=DSVcK40tmSY)); **resend ticket / booking confirmation / tax receipt** and access the attendee invoice ([mWgCGTTCDU](https://www.youtube.com/watch?v=mWgCGTTCDU)); **export attendee list as CSV** ([G8ntvbkwYeY](https://www.youtube.com/watch?v=G8ntvbkwYeY)). `[STATED]`
- **Xero tracking per ticket type** — event ticket types connect to Xero tracking categories and product codes (Sept 2026) ([GOmhbt5Idq8](https://www.youtube.com/watch?v=GOmhbt5Idq8)).
- `[INFERENCE]` Ticketing is not delegated to SafeTicket at runtime any more; the roadmap said "an improved integration with our event ticketing technology (SafeTicket) with the ability to seamlessly generate events within Wave" ([home](https://wavecrm.com.au/)), but the current UI is native Wave ("Create, manage and run events … directly inside Wave CRM", [event-management](https://wavecrm.com.au/event-management)). Treat ticketing as an in-app module with a shared SafeCo lineage.

### 2.8 CPD (continuing professional development)

- **Programs** — set program **dates**, **required points**, **points categories**; programs can be open to **members and non-members**; dashboard splits current / upcoming / past ([cpd-management](https://wavecrm.com.au/cpd-management)). `[STATED]`
- **Cycle structures** — Oct 2026 added refinements to **calendar-year, fixed-term and anniversary-based** CPD cycles ([G76ZL5sdN1A](https://www.youtube.com/watch?v=G76ZL5sdN1A)). `[STATED]`
- **Progress tracking** — approved, pending and remaining points; **category breakdown**; **submission history** (activities, completion dates, points, approval status) ([cpd-management](https://wavecrm.com.au/cpd-management)). `[STATED]`
- **Compliance status thresholds** — set **percentage thresholds** for **At Risk / On Track / Completed** ([cpd-management](https://wavecrm.com.au/cpd-management)). `[STATED]`
- **Submission review** — pending submissions reviewed from one central location, opened directly for assessment ([cpd-management](https://wavecrm.com.au/cpd-management)). `[STATED]`
- **Participant portal** — own CPD dashboard, self-service record submission, monitoring ([cpd-management](https://wavecrm.com.au/cpd-management)). `[STATED]`
- **Activities** — configure available CPD activities and how points are awarded per program ([cpd-management](https://wavecrm.com.au/cpd-management)).

### 2.9 Payments (Stripe, direct debit)

- **Stripe cards** — "Credit card transactions powered through Stripe*… *Standard Stripe processing fee applies." ([home](https://wavecrm.com.au/)).
- **Direct deposit / bank transfer** — "No fee for direct deposit/bank transfers" ([home](https://wavecrm.com.au/)).
- **Direct debit facility** — roadmap Q4 2023: "Offer your members the ability to setup a direct debit payment for easier recurring membership payments with minimal processing fees." ([home](https://wavecrm.com.au/)). `[INFERENCE]` Live, since the create-member form exposes direct-debit-related settings ([0s-N06807uQ](https://www.youtube.com/watch?v=0s-N06807uQ)) — but the mechanism (bank feed, BECS/ABA file, Stripe BECS, third party) is **not stated anywhere I could read**.
- **Payment workflows** — "Support card, recurring and invoice-based payment workflows" ([xero-invoicing](https://wavecrm.com.au/xero-invoicing)).
- **Self-service payment** — "Members can pay from their email, or view, download and pay via their Member Portal" ([xero-invoicing](https://wavecrm.com.au/xero-invoicing)); a **payment page link** can be shared manually ([rlF5p5tDAdc](https://www.youtube.com/watch?v=rlF5p5tDAdc)).
- **Credit notes** — against a member payment: pick the order, confirm payment method, create credit note, choose **credit amount and tax behaviour**, add an internal note ([c9LzkiERMqs](https://www.youtube.com/watch?v=c9LzkiERMqs)). `[STATED]`
- **Custom orders** — for anything not tied to a membership (sponsorships, one-offs): issue and due dates, customer from the member list, **line items and pricing**, **GST/tax settings**, send invoice and collect payment ([QTQbhaGAiGw](https://www.youtube.com/watch?v=QTQbhaGAiGw)). `[STATED]`

### 2.10 Xero integration (two-way) and invoicing/reconciliation

- **Certified.** "we are Xero Certified Partners" / "Certified Xero App Partner", linking to the App Store listing ([xero-invoicing](https://wavecrm.com.au/xero-invoicing)). The listing exists and describes exactly this: "Wave CRM is a membership CRM with two-way Xero integration. Manage members, events and payments in one platform, and automatically sync invoices and transactions with Xero to reduce admin, simplify reconciliation and improve financial visibility." ([apps.xero.com/au/app/wave](https://apps.xero.com/au/app/wave)).
- **Direction of flow, stated three times:** "Create invoices in Wave CRM, which sync with Xero, and keep payment information aligned between Wave CRM and Xero. Wave CRM's current integration is confirmed as two-way." ([xero-invoicing](https://wavecrm.com.au/xero-invoicing)).
- **Three-step reconciliation narrative on the page:** (1) Wave CRM Auto Renewal creates the Member Order; (2) the Order pushes directly to Xero as an authorised invoice; (3) online or bank payment reconciles both systems automatically ([xero-invoicing](https://wavecrm.com.au/xero-invoicing)). `[STATED]`
- **Setup, from the walkthrough:** **Integration → Xero** → connect the Xero organisation → assign each **membership package an account code** (plus optional **bank account** and **tracking categories**) → choose the Xero connection in **Membership Settings** → **Map Customers → Sync ContactIDS** to match members to Xero contacts **by email** → push invoices ([jgub3kpw-L8](https://www.youtube.com/watch?v=jgub3kpw-L8)). `[STATED]` — the email-based contact mapping is a real operational constraint worth copying/improving.
- **Scope of invoicing:** "Manage invoicing across memberships, events and one-off charges in Wave CRM" ([xero-invoicing](https://wavecrm.com.au/xero-invoicing)).
- **Idempotency-shaped plumbing visible in the page's mock UI:** "Wave CRM order: ORD-2026-9041 $395.00 AUD" ↔ "Xero Invoice INV-05118, Account: 200 - Subscriptions • GST: 10%, Reconciled" ([xero-invoicing](https://wavecrm.com.au/xero-invoicing)). `[STATED as a UI mock; INFERENCE that order↔invoice is 1:1 with a reconciliation flag]`

### 2.11 Website / CMS

- **Roadmap Q3 2023:** "Integrated Homepage — A self-managed homepage as part of our Wave ecosystem so that you can have your own website without hassle or complicated IT management." ([home](https://wavecrm.com.au/)).
- **FAQ:** "Wave has the ability to work in with your existing website with minimal fuss, or, we can help create the website you need and want." ([home](https://wavecrm.com.au/)).
- **In-product CMS surface:** **Posts** with generated URLs, publish/unpublish, drag-and-drop content, access control and navigation folders ([zdsdNu5djUo](https://www.youtube.com/watch?v=zdsdNu5djUo)); the About/Tour video for the Member Portal shows the portal as the members' web front door ([PgZ8zy91vt8](https://www.youtube.com/watch?v=PgZ8zy91vt8)).
- `[OBSERVED]` Tenant hosts do serve public routes: on `https://ausagritech.wavecrm.com.au`, `/` 302s to login, `/login` returns 200, `/cpd` 302s, `/directory` returns **405** (exists, wrong method), while `/events`, `/posts`, `/join` 404. `[INFERENCE]` Public routing is per-tenant configurable rather than a fixed app map.

### 2.12 Reporting

Six named report areas in **Reporting** (left-hand menu) — the most precise module spec in the corpus ([JgmnqDv137o](https://www.youtube.com/watch?v=JgmnqDv137o), [jaytARdds6g](https://www.youtube.com/watch?v=jaytARdds6g)):

1. **Organisation Insight** — revenue by membership category; paying vs active member numbers; annual membership fees and associated revenue; member distribution by **state, industry, membership level, cancelled members**; reporting on configured **custom member fields**.
2. **Revenue Insight** — total / paid / pending / refunded / cancelled orders, average order amount, date range, filters by **revenue source, status, payment type, amount**, revenue graph, **CSV export**.
3. **Comparison Report** — pick a base period and a comparison period; period-over-period figures.
4. **Add-on Report** — add-on quantities, revenue, associated orders, invoice numbers, customers, payment statuses, unit prices; opens linked invoices; export.
5. **Member Events Report** — bookings by date booked, event, quantity, revenue, payment status; opens invoices; export.
6. **Eligible Members Report** — members meeting **financial history and tenure** criteria — explicitly framed for **AGM voting rights and constitutional rules** ([G76ZL5sdN1A](https://www.youtube.com/watch?v=G76ZL5sdN1A)). `[STATED]`
7. **Activity Log** — audit trail of recorded activity and changes to member records; **new activity entries can be created against member records**; filterable; exportable ([jaytARdds6g](https://www.youtube.com/watch?v=jaytARdds6g)). `[STATED]`

### 2.13 Admin, roles & permissions

- **Custom Roles & Permissions** (Oct 2026) — "Create custom roles with detailed **Read, Write and Delete** permissions across Wave's tools. Configure read-only access or restrict users to specific areas such as **marketing, finance or membership management**. The new Role Permissions system will **replace the previous Role setting**." ([G76ZL5sdN1A](https://www.youtube.com/watch?v=G76ZL5sdN1A)). `[STATED]`
- **Two permission planes** must not be confused: **staff** roles (admin dashboard) and **portal** roles (Owner vs User), plus **package-level access levels** (Member Resources / Member Users / Community). `[STATED across Q2LAjjbQiDo, hAJe8-g1cgU]`
- **Member user limits** — max Member Users per package, overridable per member record; introducing a lower limit does not revoke existing access ([GOmhbt5Idq8](https://www.youtube.com/watch?v=GOmhbt5Idq8), [G76ZL5sdN1A](https://www.youtube.com/watch?v=G76ZL5sdN1A)). `[STATED]`
- **Company Settings** — includes a **Default Country** that drives phone country codes across member records, application forms and subscriber records (Sept 2026) ([GOmhbt5Idq8](https://www.youtube.com/watch?v=GOmhbt5Idq8)). `[STATED]`
- **Divisions** — members are grouped by division at creation ([0s-N06807uQ](https://www.youtube.com/watch?v=0s-N06807uQ)). `[STATED]` `[INFERENCE]` This is the multi-branch/multi-region construct for federated chambers.

### 2.14 Data migration

- **Assisted migration is a priced inclusion, not a self-service tool:** "Assistance with migration" in the pricing inclusions ([home](https://wavecrm.com.au/)); "Let us handle the migration for you. Simply give us your data and we will handle the setup" ([home](https://wavecrm.com.au/)); "Our team will be at the ready to assist you with all the technical difficulties, from data migration, onboarding and any day-to-day hassle." ([home](https://wavecrm.com.au/)). `[STATED]`
- **Self-service import exists for at least one entity:** "import subscriber lists" under Audience → Subscribers ([zZrA5DcBZO0](https://www.youtube.com/watch?v=zZrA5DcBZO0)). `[STATED]`
- **Exports:** subscriber exports and application-form/submission data exports were *fixed* in Oct 2026 ("to address previous errors and unexpected results") ([G76ZL5sdN1A](https://www.youtube.com/watch?v=G76ZL5sdN1A)); CSV exports from reporting and attendee lists ([JgmnqDv137o](https://www.youtube.com/watch?v=JgmnqDv137o), [G8ntvbkwYeY](https://www.youtube.com/watch?v=G8ntvbkwYeY)). `[STATED]`
- No stated bulk member-import tool, field-mapping UI, or documented migration data dictionary anywhere public. `[INFERENCE]` Migration is a services engagement behind the scenes.

### 2.15 Support

- **Local, human, multi-channel:** "No faceless support. No disappearing into an email-only queue or ticket system of the abyss… Give us a call, send a text, drop us an email or jump on a video call." ([about](https://wavecrm.com.au/about)); "Local tech support" in the inclusions ([home](https://wavecrm.com.au/)).
- **Contact routes:** info@wavecrm.com.au, 0432 504 801, video call/Teams, "over a coffee" ([about](https://wavecrm.com.au/), [home](https://wavecrm.com.au/)).
- **In-app support addresses:** `support@wavecrm.com.au` on the admin login screen ("Issue with logging in? Contact support@wavecrm.com.au") and per-tenant `admin@<clientdomain>` on the member login ([login page, observed](https://ausagritech.wavecrm.com.au/dashboard/login), [member login, observed](https://ausagritech.wavecrm.com.au/login)). `[OBSERVED]`
- **No public help centre / knowledge base exists.** `help.`, `support.`, `docs.`, `knowledge.`, `app.wavecrm.com.au` do not resolve. `[OBSERVED — DNS/connection failure]` The de facto knowledge base is the **YouTube channel** (11 playlists, ~30 recent uploads, all described as "Full walkthrough" step-by-steps) — `[OBSERVED]` via [@waveawesomecrm](https://www.youtube.com/@waveawesomecrm).
- **Feature requests** are an explicit inclusion: "Feature requests" ([home](https://wavecrm.com.au/)) and "you're now a partner of Wave… we ensure you to have a say in the future of Wave" ([home](https://wavecrm.com.au/)).

---

## 3. Pricing, limits, terms and target market

**Price:** **$412.85/mo (plus GST)**, "flat fee… That's it. No hidden fees or weird business." ([home](https://wavecrm.com.au/)). Restated as "$412.85 /mo. (**minimum term applies**)" ([home](https://wavecrm.com.au/)). No public tiering, no per-seat pricing, no public pricing page (`/pricing` → 404 `[OBSERVED]`).

**Inclusions (as listed):**
- Assistance with migration
- **Unlimited members**
- Email and SMS campaign **+** (footnote: "+ Fair usage rule applies. Refer to our T&C for more information.")
- Local tech support
- Feature requests

All from [home](https://wavecrm.com.au/).

**Explicit limits and unknowns:**

| Item | Status |
|---|---|
| Member numbers | Unlimited — stated ([home](https://wavecrm.com.au/)) |
| Email volume | "No tiered usage" ([home](https://wavecrm.com.au/)) **but** fair-usage rule applies ([home](https://wavecrm.com.au/)) — numeric ceiling not published |
| SMS volume | Same fair-usage footnote; no allowance published ([home](https://wavecrm.com.au/)) |
| Staff seats | **Not stated anywhere** — no seat limit published |
| Portal users per membership | Configurable **max users limit** per package, overridable per member ([Q2LAjjbQiDo](https://www.youtube.com/watch?v=Q2LAjjbQiDo)) — i.e. a product limit, not a commercial one |
| Minimum term | "Minimum term applies" — **length not published** ([home](https://wavecrm.com.au/)) |
| Setup/migration fee | Not published; migration is included in the fee ([home](https://wavecrm.com.au/)) |
| Stripe fees | Pass-through: "Standard Stripe processing fee applies"; bank transfer no fee ([home](https://wavecrm.com.au/)) |
| SMS/email overage pricing | Not published |

**The "T&C" the pricing footnote points to is effectively missing.** `[OBSERVED]` `/terms`, `/terms-and-conditions`, `/terms-conditions`, `/privacy`, `/privacy-policy`, `/pricing`, `/faq` all 404 on wavecrm.com.au, and no page in the fetched HTML contains any link to terms or privacy — the footer carries only Homepage/About, sibling products, and contact details (verified by grepping all 7 page sources). The only terms reachable anywhere in the Wave estate are linked from the **member-facing login page of a tenant**, and they point at **SafeTicket/SafeVisit's** 2020-era pages:

- [getsafeticket.com.au/policy/terms](https://getsafeticket.com.au/policy/terms) — "Effective Date: 01 January 2020", governing entity "**ParkCollect Pty Ltd ACN 640 780 043 trading as SafeVisit AU**" (same ACN as SafeCo's ABN 52 640 780 043), covering www.safevisit.com.au / www.getsafeticket.com.au / booking.safevisit.com.au. Governing law Queensland.
- [getsafeticket.com.au/policy/privacy](https://getsafeticket.com.au/policy/privacy) — effective 1 July 2020, last edited 23 Nov 2020; cites Privacy Act 1988 (Cth), APPs and GDPR where applicable; describes third parties including "Leadpages, Active Campaign, MailChimp"; states data kept in Australia; describes security as "Verification security code to provide account & dashboard access" and "Storing electronic data with reputable third party storage providers".

`[INFERENCE]` These terms predate Wave (2022 launch), are written for a contact-tracing/ticketing product ("WHAT WE DO: We are a platfom that enables you the customer to pre-order, pre-pay and pick up any orders"), and do not address membership CRM, fair usage, minimum term, SMS allowances, data ownership or exit. **A rebuild should treat "what is the fair usage rule?" as a genuine open question for the vendor** — it is referenced as binding but is not publicly readable.

**Target market:** chambers of commerce, industry bodies, associations, membership organisations — explicitly ([home](https://wavecrm.com.au/), [about](https://wavecrm.com.au/)). Sized for organisations that currently run on "MailChimp, EventBrite, Xero, WordPress with broken plugins, and somehow all ending up back in spreadsheets" ([about](https://wavecrm.com.au/)) — i.e. 1–10 staff, committee-governed, no dedicated IT. Wave also pitches *what it replaces*: "MailChimp, Klavyio, Eventbrite, Humanitix, Google Forms, Jot Forms, a variety of Wordpress plugins, and we hope you can FINALLY ditch those spreadsheets." ([home](https://wavecrm.com.au/)). That replacement list is the clearest statement of competitive scope.

---

## 4. Integrations

| Integration | Evidence | Confidence |
|---|---|---|
| **Xero** — certified, two-way, invoices + payments + contact mapping + tracking categories | [xero-invoicing](https://wavecrm.com.au/xero-invoicing), [apps.xero.com/au/app/wave](https://apps.xero.com/au/app/wave), [jgub3kpw-L8](https://www.youtube.com/watch?v=jgub3kpw-L8) | High |
| **Stripe** — card payments, standard processing fee pass-through | [home](https://wavecrm.com.au/) | High |
| **SafeTicket** — same owner (SafeCo); roadmap: "improved integration with our event ticketing technology (SafeTicket) with the ability to seamlessly generate events within Wave" | [home](https://wavecrm.com.au/), [getsafeticket.com.au](https://getsafeticket.com.au/) | High that the lineage exists; current runtime coupling unclear (ticketing looks native) |
| **Apple Wallet / Google Wallet** — digital membership cards | [0NVkVjG6nqA](https://www.youtube.com/watch?v=0NVkVjG6nqA) | High |
| **Client's existing website** — "work in with your existing website with minimal fuss"; Wave can also build the site | [home](https://wavecrm.com.au/) | Medium (mechanism unstated — embed? subdomain? SSO?) |
| **Email sending domain** — customer must configure their sending domain before adding sender addresses | [etM0ld1LBV8](https://www.youtube.com/watch?v=etM0ld1LBV8) | High |
| **"Add to calendar"** on events | [home](https://wavecrm.com.au/) | Medium (likely .ics/Google) |
| **Google Analytics** on the marketing site only (`G-ECYLF08M77`) | [observed] page source | High (but not product) |
| **Forms** — native Application Forms and Sign Up Forms, so no Jotform/Google Forms needed | [S_9DdXBZSoE](https://www.youtube.com/watch?v=S_9DdXBZSoE), [home](https://wavecrm.com.au/) | High |
| **API** — "subscriber/API improvements" in Sept 2026 release notes implies a public or internal API exists | [GOmhbt5Idq8](https://www.youtube.com/watch?v=GOmhbt5Idq8) | Low — **no documentation found** |
| **Zapier / webhooks / Make** | No mention on any page or in any of 39 descriptions | Absent as far as evidence goes |

Sibling SafeCo products, listed in every footer: [SafeTicket](https://getsafeticket.com.au/), [MODC.](https://modc.com.au/), [LuckyDoor](https://luckydoor.com.au/) ([home](https://wavecrm.com.au/)). Only SafeTicket has any stated relationship to Wave. `[INFERENCE]` MODC (a "mod" of something — likely digital membership/offers) and LuckyDoor (likely door/check-in) may share components with Wave's wallet cards and event check-in, but **nothing publicly states an integration**; do not build on this.

---

## 5. Hosting, data sovereignty, security, privacy

**Stated:**
- "We have our own private data storage provisioned through **Amazon Web Service (AWS) based in Sydney**. All of the data we capture is stored **sovereignly in Australia only**, and given that we are a local company, are bound to the **Australian Privacy Act**." ([home](https://wavecrm.com.au/) FAQ). Same claim as "Data Assurity — Being Queensland locals, you have the assurance that our solution meets all state and national data privacy and handling." ([home](https://wavecrm.com.au/)).
- "Our Queensland based team are all locals. Nothing outsourced or offshored here." ([home](https://wavecrm.com.au/)).
- Privacy position inherited from SafeVisit/SafeTicket policy: Privacy Act 1988 (Cth) + APPs, GDPR where applicable, data kept in Australia, breach/complaint route to OAIC, right to erasure, 30-day access requests ([getsafeticket.com.au/policy/privacy](https://getsafeticket.com.au/policy/privacy)).

**Observed (technical):**
- Assets are served from **CloudFront** (`d3lmfedpy3s6ny.cloudfront.net` for marketing, `dgz66cwajspiu.cloudfront.net` for the app), with **signed/encoded asset paths** (base64-encoded path+revision in the URL) — consistent with private-origin S3 behind CloudFront ([observed](https://wavecrm.com.au/), [observed](https://ausagritech.wavecrm.com.au/dashboard/login)).
- **Tenant model:** one subdomain per client (`<slug>.wavecrm.com.au`) with per-tenant logo, per-tenant support email, and separate `/dashboard/login` (staff) vs `/login` (member) entry points ([observed](https://ausagritech.wavecrm.com.au/dashboard/login), [observed](https://ausagritech.wavecrm.com.au/login)). `[INFERENCE]` Either per-tenant database/schema or a strict tenant-scope; not determinable from outside.
- **Auth (admin):** email + password, **Remember Me**, forgot-password, then a **mandatory one-time passcode** "sent to your registered mobile number (or email)" — i.e. **MFA is on by default for admins** ([observed](https://ausagritech.wavecrm.com.au/dashboard/login)).
- **Auth (member):** email → **"Which account is this sign-in for?"** account chooser → password, with "Reset or create password here", plus a separate **"Looking for administrator login? click here"** and links to Terms & Conditions / Privacy Policies ([observed](https://ausagritech.wavecrm.com.au/login)). The account chooser confirms one person can hold roles across multiple memberships/accounts.
- **A `/dev/login` route is linked from the admin login page** ([observed](https://ausagritech.wavecrm.com.au/dashboard/login)). `[INFERENCE]` A non-production login path is reachable in production; worth flagging to the vendor, and worth **not** replicating.
- **Marketing-site stack:** Vue 3 (global build), axios, CSRF token, Lottie player, Google Fonts, Google Tag Manager ([observed] page source). `[INFERENCE]` Laravel-style backend (CSRF token + Blade-served Vue), though not proven.
- **App templates ship raw mustache expressions** to the browser (`{{ errors.form }}` etc.) — server-rendered-with-client-hydration ([observed](https://ausagritech.wavecrm.com.au/dashboard/login), [observed](https://wavecrm.com.au/)). Cosmetic, but it tells you the front end is a single global Vue app per page rather than SSR.

**Not stated anywhere:** uptime/SLA, backup frequency and retention, disaster recovery, penetration testing / IRAP / SOC2, encryption at rest, data-residency options, sub-processor list for the CRM product, breach notification commitments specific to Wave, or what happens to your data on exit.

---

## 6. Implied data model

Everything below marked **[STATED]** is directly evidenced by a field, status or label in a first-party source. Anything **[INFERENCE]** is my synthesis of relationships — Wave has never published a schema.

```
Tenant (account/subscription to Wave)
 ├── Company Settings (name, logo, default country, portal branding)
 ├── Division 1..n                     STATED (create member: "choose a division")
 ├── MembershipPackage 1..n           STATED (aka tier/level)
 │     ├── price, billing period, term
 │     ├── Xero account code, bank account, tracking categories   STATED
 │     ├── AccessLevel {member_resources, member_users(+max), community}  STATED
 │     └── allowed Add-ons 1..n                                   STATED
 ├── MembershipAddOn 1..n             STATED (fixed|variable price, qty limits, eligibility)
 ├── Member 1..n                      STATED
 │     ├── status: Active|Pending|Expired|Suspended|Disabled|Cancelled  STATED
 │     ├── expiry_date | Lifetime                                  STATED
 │     ├── division, package, tags                                 STATED
 │     ├── billing / direct-debit / Xero settings                  STATED
 │     ├── ArbitraryField values 1..n  (Visible, Editable, Report) STATED
 │     ├── AccountAccess → MemberUser 1..n (Owner|User)            STATED
 │     ├── DirectoryProfile (public contact overrides, images)     STATED
 │     ├── MemberFile 1..n                                         STATED
 │     └── ActivityLogEntry 1..n                                   STATED
 ├── Subscriber 1..n                  STATED (contact-only; tags; subscribed flag)
 ├── Order 1..n                       STATED (ORD-2026-9041)
 │     ├── line items, issue/due date, tax/GST, customer, status   STATED
 │     ├── revenue source {membership, event, add-on, custom}      STATED/INFER
 │     ├── Invoice 0..1              STATED (INV-05118 ↔ Xero invoice)
 │     │     └── Payment 0..n        STATED (card|bank|direct debit)
 │     └── CreditNote 0..n           STATED (amount, tax behaviour, note)
 ├── Renewal / AutoRenewal            STATED (next renewal, Force Renew, Stop Next Renewal)
 ├── Event 1..n                       STATED
 │     ├── TicketType 1..n           STATED (member/non-member, table/individual, Xero tracking)
 │     ├── Voucher 1..n              STATED (pct|dollar|fixed price, max redemptions, expiry)
 │     ├── Question 1..n             STATED ("additional questions", dietary)
 │     ├── Speaker / Sponsor 1..n    STATED
 │     ├── RunSheet 1..1             STATED
 │     └── Booking 1..n → Attendee, PaymentStatus, Refund, Ticket  STATED
 ├── CpdProgram 1..n                  STATED (dates, points, categories, cycle type)
 │     ├── CpdActivity 1..n          STATED (points awarding rules)
 │     └── CpdSubmission 1..n        STATED (activity, completion date, points, approved|pending)
 ├── Campaign (EDM) 1..n              STATED (subject, content rows, segment, schedule, report)
 │     └── CampaignReport           STATED (opens, clicks, bounces, blocked, link clicks)
 ├── EmailTemplate 1..n               STATED
 ├── EmailSequence 1..n → trigger    STATED ("Before Member Expiry")
 ├── Form 1..n                       STATED (ApplicationForm | SignUpForm)
 │     └── Submission 1..n → status, notifications, bindings, file uploads  STATED
 ├── Resource (folder/file) 1..n     STATED (per-membership access)
 ├── Post 1..n                       STATED (URL, publish state, access, folder)
 ├── MembershipCard                  STATED (Apple/Google Wallet, QR verify, expiry)
 ├── SenderIdentity 1..n             STATED (local part, display name, default)
 ├── User (staff) → Role → Permissions  STATED (Read/Write/Delete per tool area)
 └── ActivityLog                      STATED (audit + manually created entries)
```

**Field-level detail worth copying:**

- `Member.custom_fields[]` needs three orthogonal booleans: **visible in portal**, **member-editable**, **show on report** ([uuoctxiYATc](https://www.youtube.com/watch?v=uuoctxiYATc)).
- `FormQuestion.maps_to_field` (Wave calls it "bind to key field") plus an `unmapped → Additional Information` catch-all and a `packages` special case ([socTts99ZFs](https://www.youtube.com/watch?v=socTts99ZFs)).
- `DirectoryProfile.contact_*` deliberately duplicated from `Member.contact_*` with admin override ([GOmhbt5Idq8](https://www.youtube.com/watch?v=GOmhbt5Idq8)).
- `Member.subscription_status` is **independent** of `Member.membership_status` ([zZrA5DcBZO0](https://www.youtube.com/watch?v=zZrA5DcBZO0)). This single modelling decision is what lets a lapsed member keep receiving EDMs, and it is very likely the detail a Wave buyer would notice if you got it wrong.
- `Order ↔ XeroInvoice` mapping is by **member email → Xero ContactID**, synced explicitly via "Map Customers → Sync ContactIDS" ([jgub3kpw-L8](https://www.youtube.com/watch?v=jgub3kpw-L8)).
- `MembershipPackage.user_limit` with `Member.user_limit_override`, and a **non-retroactive** rule when lowering the limit ([GOmhbt5Idq8](https://www.youtube.com/watch?v=G76ZL5sdN1A)).

---

## 7. UI observations

**I did not render any screenshot.** What follows is (a) UI text I observed in page markup, and (b) layout described in first-party copy and video descriptions. Treat as "described", not "seen".

**Admin navigation** (assembled from walkthrough step-paths — high confidence, this is the clearest artefact in the corpus):

```
Audience
  ├── Members            → member list, Create new member, member record
  │     └── member record tabs: Account Access, Billing & Orders, Additional Details, Notes, Tags
  └── Subscribers        → create, import, export, tags
Events
  └── event wizard (settings → Save & Next → vouchers → questions → publish)
Tools
  └── Application forms  → forms list, entries, Settings → Notifications & email
Reporting
  ├── Organisation Insight
  ├── Revenue Insight
  ├── Comparison Report
  ├── Add-on Report
  ├── Member Events Report
  ├── Eligible Members Report
  └── Activity Log
Integration
  └── Xero               → connect org, account codes, Map Customers, Sync ContactIDS
Account
  └── Settings
        ├── Company Settings       (incl. Default Country)
        ├── Email Settings         → Customise Sender
        ├── Membership Settings    → packages → Configuration → Access Level
        ├── Member Portal          (banner, colours, welcome title/message)
        └── Arbitrary Fields       (Member Fields, Member User Fields, Auto Generate Numbers)
+ email campaigns, scheduled communications, CPD, resources, posts (surfaced per walkthroughs)
```

**Layout patterns described:**

- **List + summary stat bar.** The bookings dashboard leads with total attendees, gross revenue, transaction fees, refunded and outstanding above the list ([event-management](https://wavecrm.com.au/event-management)). The events dashboard shows views, tickets sold and gross revenue ([event-management](https://wavecrm.com.au/event-management)). `[STATED]`
- **Campaign report as a table block.** Subject line, Total Recipients, Campaign Date, then a "Contact engagement" table (Opened/Clicked/Bounced/Blocked with counts and percentages) and a "Link Clicks" table with URL / Unique / Total, plus "Download as CSV" ([email-campaigns](https://wavecrm.com.au/email-campaigns)). `[STATED]`
- **Reconciliation panel as a two-column diff.** "Wave CRM order: ORD-2026-9041 $395.00 AUD" beside "Xero Invoice INV-05118, Account: 200 - Subscriptions • GST: 10%, Reconciled", rendered over a "Connected Organisation: Wave / Sync Active" header ([xero-invoicing](https://wavecrm.com.au/xero-invoicing)). `[STATED as mock]` — this is a nice, reproducible UI idiom for any two-way sync screen.
- **CPD dashboard** as program cards (current/upcoming/past) with at-risk counts, and a member progress view split into approved / pending / remaining with a per-category breakdown ([cpd-management](https://wavecrm.com.au/cpd-management)). `[STATED]`
- **Settings pages are tabular editors** — "click + to add a row, enter the part of the address before the @ and a display name, then Save" for sender identities ([etM0ld1LBV8](https://www.youtube.com/watch?v=etM0ld1LBV8)); arbitrary fields list with type and settings columns ([uuoctxiYATc](https://www.youtube.com/watch?v=uuoctxiYATc)). `[STATED]`
- **Member creation is one long form** walked "top to bottom": division/package → status/expiry → member details → tags & settings → custom fields → Save ([0s-N06807uQ](https://www.youtube.com/watch?v=0s-N06807uQ)). `[STATED]`
- **Event setup is a wizard** with explicit "Save & Next" steps ([uavwn3NuJYQ](https://www.youtube.com/watch?v=uavwn3NuJYQ)). `[STATED]`
- **The EDM builder** is a stacked-row editor (hero image, title section, supporting images, body text, CTA button, social links) with background/text colour controls and spacing/padding ([y7nQDXuOgkE](https://www.youtube.com/watch?v=y7nQDXuOgkE)). `[STATED]`

**Member-facing portal** (from the walkthrough chapter list, [PgZ8zy91vt8](https://www.youtube.com/watch?v=PgZ8zy91vt8)): home screen with banner + welcome message + announcements + outstanding invoices; nav menu; Resource Centre; Member Files; Events (browse + register); Member Directory; Invoices & Payments; personal details; directory profile; business details & billing. The account chooser and Owner/User split sit in front of it ([observed login](https://ausagritech.wavecrm.com.au/login), [hAJe8-g1cgU](https://www.youtube.com/watch?v=hAJe8-g1cgU)).

**Marketing-site UI quirks** (relevant if you clone the site): the contact modal uses a "How should we get in touch — Call me back / Send me an email / Talk to me on LinkedIn" radio, and the site renders un-rendered Vue mustache placeholders in its fallback HTML ([observed](https://wavecrm.com.au/)).

---

## 8. What is unknown, and how to find it out

Ordered by how much it would change a rebuild.

| # | Unknown | Why it matters | How to resolve |
|---|---|---|---|
| 1 | **The fair-usage rule** for email and SMS (the only stated numeric limit) | Directly shapes infrastructure and unit economics | Ask the vendor for the T&C document; it is referenced at [home](https://wavecrm.com.au/) but not published. Request a demo and ask for it in writing |
| 2 | **Minimum term length**, notice period, exit and data-return terms | Commercial parity, not just feature parity | Same request; a trial login or contract sample answers it |
| 3 | **SMS provider, allowances, opt-out/STOP handling, sender IDs** | Zero public evidence; AUD-per-message economics matter in AU | Demo question. Also check whether SMS is Twilio/MessageMedia/ClickSend by inspecting an outbound SMS in a trial |
| 4 | **Direct debit mechanism** — BECS/ABA file, Stripe BECS, or bank feed? | Changes the payment architecture entirely | Demo question; ask for the direct-debit setup guide |
| 5 | **Public/consumable API**, webhooks, Zapier | Sept 2026 notes mention "subscriber/API improvements" ([GOmhbt5Idq8](https://www.youtube.com/watch?v=G76ZL5sdN1A)) but nothing is documented | Ask for API docs; check for `/api` or OpenAPI on a tenant host (read-only) |
| 6 | **Backups, DR, RTO/RPO, encryption at rest, pen-test reports, sub-processors** | Enterprise/procurement blockers; nothing published | Security questionnaire via demo |
| 7 | **Staff seat limits and per-user pricing** | "Unlimited members" is stated; seats are not | Demo question |
| 8 | **Migration mechanics** — what formats, which entities, field mapping, who does what | "We handle it" is a promise, not a spec | Ask for their migration checklist / data dictionary |
| 9 | **Exact trigger vocabulary** in Scheduled Communications | Only "Before Member Expiry" is named publicly | Trial login, or a walkthrough request |
| 10 | **Website/CMS depth** — is there a real page builder, or only Posts + portal? | Determines whether Wave is a website replacement | Ask whether "Integrated Homepage" (2023 roadmap) shipped, and in what form |
| 11 | **Multi-currency / NZ support** — ATAINZ is a NZ client | Affects tax and GST/VAT modelling | Demo question (they have at least one NZ client, so presumably yes) |
| 12 | **Whether `/dev/login` is intentionally public** | Security hygiene signal | Report to `support@wavecrm.com.au`; not needed for rebuild |
| 13 | **Concurrency/scale ceiling** — largest tenant, member counts | Capacity planning | Demo question |

**Read-only fetches that would still add value (not done here):** a live tenant's public event booking page (to capture the attendee purchase flow end-to-end — booking pages 404 on the one tenant probed), the Xero App Store *reviews* page body (JS-rendered; only the meta description was extractable), and the 11 YouTube playlists' individual contents (playlist IDs extract but the playlist pages served only a shell to this client).

---

## 9. Minimum viable parity

The smallest feature set that a current Wave buyer would accept as "the same thing". Anything below this line and it is a different, cheaper product; anything above is upside.

**Must have (a buyer would walk without these):**

1. **Tenant + branding** — subdomain per client, custom logo, portal banner/colours/welcome message ([observed](https://ausagritech.wavecrm.com.au/login), [tR8sVrH2df4](https://www.youtube.com/watch?v=tR8sVrH2df4)).
2. **Member records** with division, package, status (Active/Pending/Expired/Suspended/Disabled/Cancelled), expiry-or-lifetime, tags, and **custom fields with visible/editable/report flags** ([0s-N06807uQ](https://www.youtube.com/watch?v=0s-N06807uQ), [uuoctxiYATc](https://www.youtube.com/watch?v=uuoctxiYATc)).
3. **Packages/tiers + add-ons**, each package carrying price, term, Xero account code and portal access level ([Q2LAjjbQiDo](https://www.youtube.com/watch?v=Q2LAjjbQiDo), [_9hNMjhC344](https://www.youtube.com/watch?v=_9hNMjhC344)).
4. **Subscribers as a separate audience** with independent subscribe/unsubscribe state, tags, CSV import and export ([zZrA5DcBZO0](https://www.youtube.com/watch?v=zZrA5DcBZO0)).
5. **Orders → invoices → payments → credit notes**, with GST, and **renewal generation** (auto + force + manual for lapsed) ([QTQbhaGAiGw](https://www.youtube.com/watch?v=QTQbhaGAiGw), [rlF5p5tDAdc](https://www.youtube.com/watch?v=rlF5p5tDAdc), [c9LzkiERMqs](https://www.youtube.com/watch?v=c9LzkiERMqs)).
6. **Stripe card payments** + a shareable payment link + pay-from-invoice-email ([home](https://wavecrm.com.au/), [rlF5p5tDAdc](https://www.youtube.com/watch?v=rlF5p5tDAdc)).
7. **Two-way Xero sync** — push invoices, pull payment status, per-package account codes, per-ticket-type tracking categories, contact mapping ([xero-invoicing](https://wavecrm.com.au/xero-invoicing), [jgub3kpw-L8](https://www.youtube.com/watch?v=jgub3kpw-L8)).
8. **Application forms → approve → process into member**, plus **sign-up forms** for new memberships/renewals, with key-field binding and email notifications ([K3n1RlYQZX0](https://www.youtube.com/watch?v=K3n1RlYQZX0), [S_9DdXBZSoE](https://www.youtube.com/watch?v=S_9DdXBZSoE)).
9. **Member portal** — login with account chooser, Owner/User roles, membership details, invoices and payment, events browsing/registration, directory, resources, profile editing, member files ([PgZ8zy91vt8](https://www.youtube.com/watch?v=PgZ8zy91vt8), [hAJe8-g1cgU](https://www.youtube.com/watch?v=hAJe8-g1cgU)).
10. **EDM campaigns** — drag-and-drop builder, media library, scheduling, segmentation by membership/industry/location/ticket purchase, open/click/bounce reporting with CSV export ([email-campaigns](https://wavecrm.com.au/email-campaigns)).
11. **Scheduled communications** — templates + sequences with at least the membership-expiry triggers ([4kho0w1LTdI](https://www.youtube.com/watch?v=4kho0w1LTdI)).
12. **Events & ticketing** — event setup with member/non-member pricing, tickets/tables, vouchers, questions, speakers/sponsors, bookings dashboard, refunds, runsheet PDF, attendee CSV export ([event-management](https://wavecrm.com.au/event-management), [uavwn3NuJYQ](https://www.youtube.com/watch?v=uavwn3NuJYQ)).
13. **Reporting** — at minimum Organisation Insight, Revenue Insight, Member Events, and an Activity Log ([JgmnqDv137o](https://www.youtube.com/watch?v=JgmnqDv137o), [jaytARdds6g](https://www.youtube.com/watch?v=jaytARdds6g)).
14. **Roles & permissions** at Read/Write/Delete granularity across tool areas ([G76ZL5sdN1A](https://www.youtube.com/watch?v=G76ZL5sdN1A)).
15. **Assisted migration** offered as a service, and **Australian data hosting** stated as a commitment ([home](https://wavecrm.com.au/)).

**Strong differentiators that a buyer will specifically ask about (build if you want to win, not just match):**

- **CPD management** with programs, points categories, cycle types and At Risk/On Track/Completed thresholds ([cpd-management](https://wavecrm.com.au/cpd-management)) — an unusual module; it is what makes Wave credible to professional bodies rather than just chambers.
- **Digital membership cards** in Apple/Google Wallet with live QR verification and auto-expiry removal ([0NVkVjG6nqA](https://www.youtube.com/watch?v=0NVkVjG6nqA)).
- **Eligible Members report** for constitutional voting/AGM rights ([G76ZL5sdN1A](https://www.youtube.com/watch?v=G76ZL5sdN1A)).
- **Event runsheets** as a printable/shareable PDF ([G8ntvbkwYeY](https://www.youtube.com/watch?v=G8ntvbkwYeY)).
- **Portal Posts** as light CMS with generated URLs ([zdsdNu5djUo](https://www.youtube.com/watch?v=zdsdNu5djUo)).

**Deliberately out of scope for MVP:** SMS (until the allowance question is answered), website hosting/CMS beyond Posts, and any API/webhook surface (unproven that Wave has one).

---

## Appendix A — Source index

Marketing site (all fetched 2026-11-16):
- https://wavecrm.com.au/ · https://wavecrm.com.au/about · https://wavecrm.com.au/email-campaigns · https://wavecrm.com.au/event-management · https://wavecrm.com.au/cpd-management · https://wavecrm.com.au/xero-invoicing · https://wavecrm.com.au/member-experience
- 404 confirmed: `/sitemap.xml`, `/terms`, `/terms-and-conditions`, `/terms-conditions`, `/privacy`, `/privacy-policy`, `/pricing`, `/faq`, `/tc`

Third-party and sibling:
- https://apps.xero.com/au/app/wave · https://getsafeticket.com.au/ · https://getsafeticket.com.au/policy/terms · https://getsafeticket.com.au/policy/privacy · https://modc.com.au/ · https://luckydoor.com.au/

Live app surfaces observed (read-only):
- https://ausagritech.wavecrm.com.au/dashboard/login (staff login, MFA)
- https://ausagritech.wavecrm.com.au/login (member login, account chooser, T&C links)
- https://ausagritech.wavecrm.com.au/ (302 → login), `/cpd` (302), `/directory` (405), `/events` `/posts` `/join` (404)

First-party video library — https://www.youtube.com/@waveawesomecrm (11 playlists; the ~30 most recent uploads were read in full). Videos cited:
`VOsmJClJF-c`, `etM0ld1LBV8`, `Q2LAjjbQiDo`, `0s-N06807uQ`, `uavwn3NuJYQ`, `K3n1RlYQZX0`, `tR8sVrH2df4`, `2tCcsGKojCU`, `jgub3kpw-L8`, `t4MExa7Oqu8`, `_9hNMjhC344`, `0NVkVjG6nqA`, `G76ZL5sdN1A`, `XDyn0xEuqQI`, `PgZ8zy91vt8`, `S_9DdXBZSoE`, `y_BmNMLuh4`, `4kho0w1LTdI`, `y7nQDXuOgkE`, `QTQbhaGAiGw`, `tE2FZzbN6D0`, `zZrA5DcBZO0`, `mWgCGTTCDU`, `JgmnqDv137o`, `DSVcK40tmSY`, `LEZHcMJhwl0`, `uuoctxiYATc`, `LdJzsxoWwfs`, `jaytARdds6g`, `vaQauva8tZY`, `hAJe8-g1cgU`, `G8ntvbkwYeY`, `GOmhbt5Idq8`, `YQbJd5a_gBE`, `rlF5p5tDAdc`, `zdsdNu5djUo`, `c9LzkiERMqs`, `LUK3FbEC1_A`, `hN7DsIT_lAA`, `socTts99ZFs`

Wave playlist taxonomy (de facto documentation structure — a useful sitemap for an equivalent help centre): Getting Started · Members & Membership Management · Member Portal & Member Experience · Member Portal Help · Billing, Invoices, Payments & Renewals · Email Campaigns & Member Communications · Scheduled Communications · Events & Ticketing · Forms, Applications & Signup · Product Updates & Release Notes · Client Stories & Use Cases.

## Appendix B — Claims I deliberately did not make

- I did not confirm the number of staff accounts, seat limits, or per-seat cost.
- I did not confirm that SMS is live in-product, nor its provider.
- I did not confirm direct debit is live, nor its mechanism.
- I did not confirm a public API exists.
- I did not confirm MODC or LuckyDoor integrate with Wave.
- I did not view any screenshot or video frame; all UI notes are from descriptions and page markup.
- I did not verify Wave's AWS Sydney hosting claim independently.
