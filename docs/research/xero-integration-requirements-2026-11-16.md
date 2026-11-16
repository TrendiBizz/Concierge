# Xero two-way accounting integration — build requirements (AU/NZ)

**Date:** 2026-11-16
**Scope:** What it takes to build a two-way Xero Accounting integration for a SaaS app (Python/FastAPI + Postgres) that bills memberships and events, sold to Australian (and possibly NZ) organisations — the same shape as a membership CRM that syncs contacts ↔ members, invoices ↔ membership/event invoices, payments ↔ reconciling, credit notes, and GST.
**Sources:** Xero's own developer documentation (`developer.xero.com`), Xero's OpenAPI description (`XeroAPI/Xero-OpenAPI`), Xero's OIDC discovery document, and Xero's developer GitHub samples. Every claim below carries its URL.

---

## How this was sourced (and one access caveat)

`developer.xero.com` documentation pages are **JavaScript-rendered**: the HTML returned to a plain fetch (and to the Wayback Machine's 12 Nov 2026 capture) contains only the `<title>`. `web_fetch` on those URLs returns the title and nothing else.

Rather than guess, this report uses the **content the pages themselves load**: each page's Gatsby page-data JSON contains the page's original markdown (`pageContext.doc.node.rawMarkdownBody`; API-reference pages carry it under `pageContext.info`). That is the same text the browser renders, served by `developer.xero.com` itself. Verifiable per page:

```
https://developer.xero.com/__gatsby/page-data/documentation/guides/oauth2/scopes/page-data.json
```

Facts were cross-checked against three sources that are rendered or machine-readable and *were* directly fetchable:

- Xero's OpenAPI description, v20.1.0 — https://github.com/XeroAPI/Xero-OpenAPI/blob/master/xero_accounting.yaml (raw: `https://raw.githubusercontent.com/XeroAPI/Xero-OpenAPI/master/xero_accounting.yaml`)
- Xero's OIDC discovery document — https://identity.xero.com/.well-known/openid-configuration
- Xero developer pricing (server-rendered) — https://developer.xero.com/pricing

Where a statement is my inference rather than Xero's words it is marked **[inference]**. Where a question genuinely cannot be answered from public documentation it is listed in the final section.

---

## Verdict

Building this is very doable and the API is well-documented, but the binding constraints are **commercial and structural, not API-technical**. Two facts dominate the plan: (1) a new app starts on the **free Starter Tier with a hard limit of 5 tenant connections**, and Xero limits each organisation to **5 uncertified apps** — so the "sell it to many organisations" phase requires either Core Tier (50 connections) or certification (Plus Tier, up to 1,000) and therefore a real review process; and (2) Xero is **switching from broad to granular scopes** — apps created on/after **2 March 2026** get granular scopes automatically, and broad scopes disappear by **September 2027**. For an Australian/NZ membership-and-events biller the correct architecture is: **authorization-code flow with `offline_access`** (one app, many org tenants), a queue-and-batch write layer that respects **60 calls/minute/tenant, 5 concurrent, 1,000 calls/day/tenant on Starter**, **`Idempotency-Key` on every mutating call**, **`TaxType` read from each org's `/TaxRates` rather than hard-coded**, and **webhooks** (contacts, invoices, credit notes, payments) to drive read-back instead of polling. The genuinely hard parts are not coding: they are token lifecycle at scale, per-tenant rate budgeting, GST/tax-type mapping per org, credit-note allocation being a two-call operation, and the commercial step-change at 5 connections.

---

## 1. Auth and token lifecycle

### Flows that exist

| Flow | Grant type | Doc |
|---|---|---|
| Standard authorization code ("code flow") | `authorization_code` + client secret | https://developer.xero.com/documentation/guides/oauth2/auth-flow/ |
| PKCE extension | `authorization_code` + `code_verifier` (no client secret) | https://developer.xero.com/documentation/guides/oauth2/pkce-flow/ |
| Custom Connections ("machine-to-machine") | `client_credentials`, tenanted, **one organisation only** | https://developer.xero.com/documentation/guides/oauth2/custom-connections/ |
| Client credentials (plain) | `client_credentials`, **non-tenanted** app-data endpoints only | https://developer.xero.com/documentation/guides/oauth2/client-credentials/ |

The identity provider confirms exactly three grants and S256 PKCE support:

> `grant_types_supported: ["authorization_code", "client_credentials", "refresh_token"]`, `code_challenge_methods_supported: ["S256"]`, `token_endpoint_auth_methods_supported: ["client_secret_basic", "client_secret_post"]`
> — https://identity.xero.com/.well-known/openid-configuration

Endpoints: authorize `https://login.xero.com/identity/connect/authorize`, token `https://identity.xero.com/connect/token`, revocation `https://identity.xero.com/connect/revocation` (same URL). Discovery doc: `https://identity.xero.com/.well-known/openid-configuration` (https://developer.xero.com/documentation/guides/oauth2/overview/#openid-connect-discovery).

**There is no "private app" / "public app" OAuth 1.0 distinction any more.** The developer portal's second axis is the *integration type* chosen at "New App": Custom connection (https://developer.xero.com/documentation/guides/oauth2/custom-connections/), or the code/PKCE app (Auth Code grant type) (https://developer.xero.com/documentation/guides/oauth2/auth-flow/). **[inference]** The old "private/public" wording survives in marketplace-culture memory, not in the current OAuth 2.0 docs; treat "private app" as meaning either a Custom Connection (single org, M2M) or an uncertified app used with one client.

Xero's own comparison table (https://developer.xero.com/documentation/guides/oauth2/overview/):

| | Code flow | PKCE | Custom Connection |
|---|---|---|---|
| Best for | Web server apps that can store a secret | Mobile/desktop apps, no secret (SPAs not supported) | Back-end, machine-to-machine |
| Connection limit | 5 (Starter Tier) | 5 (Starter Tier) | One |
| Eligible for marketplace | Yes | Yes | No |
| Offline access | Yes | Yes | Yes |
| Cost | Free (Starter) | Free (Starter) | Monthly fee on the Xero org: $10/m AUD inc GST, $10/m NZD ex GST, £5 GBP, $5 USD |
| Regional availability | Global | Global | UK, AU, NZ, US only |

### Which flow for which case

**(a) Pilot with one accounting firm's client** — a **Custom Connection** is the cheapest path in effort *if* the client will pay $10/month and is in AU/NZ/UK/US: Xero runs the consent flow by email, you get a `client_id`/`client_secret`, and you exchange them directly for an access token with `grant_type=client_credentials&scope=...` (step 5 of https://developer.xero.com/documentation/guides/oauth2/custom-connections/). It connects to exactly one organisation, cannot reach Practice Manager or Xero HQ, and — importantly — **does not count toward the five-uncertified-app limit**, and can be connected to the **Demo Company free for development** (same page). The catch: it is one-org-per-app, so it does not generalise, and it is *not eligible for the App Store*.

If the pilot must generalise (or the client won't buy a subscription), use the **code flow** with 5 Starter connections — but note the pilot alone then consumes one of the 5 app-wide connections and one of the org's 5 uncertified-app slots (https://developer.xero.com/documentation/guides/oauth2/limits/).

**(b) Product sold to many organisations** — **authorization code flow** (web app, client secret held server-side). Custom Connections are structurally wrong here: they top out at one organisation each and need a paid subscription per org (https://developer.xero.com/documentation/guides/oauth2/custom-connections/). The code flow supports many tenants, is marketplace-eligible, and is the only flow referenced by the certification checkpoints (https://developer.xero.com/documentation/xero-app-store/app-partner-guides/certification-checkpoints/).

PKCE is *not* the right choice for a FastAPI backend: it exists for clients that cannot keep a secret, and PKCE apps **cannot** use the client-credentials grant or the `app.connections` scope for managing connections (https://developer.xero.com/documentation/guides/oauth2/client-credentials/; https://developer.xero.com/documentation/best-practices/managing-connections/connections/).

### Token lifetimes

> "Token expiry times: id_token: 5 minutes; access_token: 30 minutes; refresh_token: 60 days"
> — https://developer.xero.com/documentation/guides/oauth2/auth-flow/#token-expiry

Access tokens are JWTs; refresh tokens are valuable strings ("store this in a secure location… if it's compromised it would allow anyone to generate new access_tokens for that user with the same permissions") — https://developer.xero.com/documentation/guides/oauth2/token-types/.

The authorization `code` "may only be exchanged once and expires 5 minutes after issuance" — https://developer.xero.com/documentation/guides/oauth2/auth-flow/.

### Refresh rules and rotation

- A refresh token is only issued if you request **`offline_access`** — https://developer.xero.com/documentation/guides/oauth2/scopes/#offline-access
- "Every time you use a `refresh_token`, you will get a new one along with the new `access_token`. You will need to use this `refresh_token` in the future." — https://developer.xero.com/documentation/guides/oauth2/token-types/
- **Rotation is mandatory-safe**: "Each time you refresh the token, you receive a new pair of access and refresh tokens. The previous refresh token is then invalid." — https://developer.xero.com/documentation/best-practices/data-integrity/managing-tokens/
- **Grace window**: "If your app doesn't receive the response, or fails to save the new token, you can retry using your existing refresh token for a grace period of 30 minutes. After 30 minutes your previous refresh token will expire and the user will need to re-authorise." — https://developer.xero.com/documentation/guides/oauth2/auth-flow/
- Refresh request: `POST https://identity.xero.com/connect/token`, `Authorization: Basic base64(client_id:client_secret)`, body `grant_type=refresh_token&refresh_token=...` (PKCE apps keep the trailing `:` with empty secret) — https://developer.xero.com/documentation/guides/oauth2/token-types/

**Concurrency hazard [inference, but the rotation rule is documented]:** because each refresh invalidates the previous token, two workers refreshing the same connection concurrently will lock each other out. Serialise refresh per connection (row-level lock / single-flight) and persist the new pair in the same transaction.

### Re-consent behaviour

- Scopes are **additive**: "Each subsequent time your app sends a user through the flow, any new scopes will be added to previously consented scopes. It's not possible to remove scopes from an existing access token. The only way to reduce consented scopes is to revoke the token and start again." — https://developer.xero.com/documentation/guides/oauth2/scopes/
- Re-authorising the same user+app **supersedes** the previous token set: "If the authorisation process is repeated for the same combination of Xero user and App, the newly issued set of tokens will supersede the previous set." — https://developer.xero.com/documentation/best-practices/data-integrity/managing-tokens/
- Connections persist independently of tokens: "Connections will continue to exist and stay active indefinitely even if no API calls are being made or if the access token expires." — https://developer.xero.com/documentation/guides/oauth2/tenants/
- A reconnect shows up as `createdDateUtc` ≠ `updatedDateUtc` on the connection — https://developer.xero.com/documentation/guides/oauth2/auth-flow/
- Disconnect paths: `DELETE https://api.xero.com/connections/{connectionId}`; or revoke the refresh token at `/connect/revocation` (which "remove[s] all their connections to your app") — https://developer.xero.com/documentation/guides/oauth2/auth-flow/
- Granular-scope migration expects re-consent for stragglers: apps created before 2 March 2026 with broad scopes have until September 2027 — https://developer.xero.com/faq/granular-scopes

### Storing tokens safely (Xero's own guidance)

From https://developer.xero.com/documentation/best-practices/data-integrity/managing-tokens/:

- Encrypt tokens at rest; never store them plaintext "even in internal databases".
- Store `access_token_expires_at` and `refresh_token_expires_at` alongside the tokens.
- Overwrite the stored refresh token immediately on rotation, and "avoid race conditions during rotation".
- Keying: `access_token` is per Xero-user+app; **`tenant_id`** goes in `xero-tenant-id` on every call; a **ConnectionID** is the unique user↔tenant link. Also store `tenant_name` (for UI) and `authEventId` (debugging).
- Suggested storage shape is a user/token record with a nested `tenants[]` array (their example includes `your_app_user_id`, `xero_user_id`, `access_token`, `refresh_token`, expiry timestamps, and per-tenant `xero_tenant_id`, `tenant_name`, `tenant_short_code`, `tenant_type`, `connected_at`).
- Use a secrets manager (AWS Secrets Manager / Azure Key Vault / GCP Secret Manager) for the key material.

Additional non-negotiable from certification: "Never show or store sensitive data like the access token, client id and client secret in the client side of the application" — https://developer.xero.com/documentation/xero-app-store/app-partner-guides/certification-checkpoints/

---

## 2. Scopes

### The 2026 change you must build against

Broad accounting scopes are being replaced by granular ones. Apps created **on or after 2 March 2026** "will use the new granular scopes" automatically; older apps keep broad scopes until **September 2027** — https://developer.xero.com/faq/granular-scopes, restated at https://developer.xero.com/documentation/guides/oauth2/scopes/ and in certification checkpoint 4 (https://developer.xero.com/documentation/xero-app-store/app-partner-guides/certification-checkpoints/).

Key mapping from https://developer.xero.com/documentation/guides/oauth2/scopes/:

| Deprecated | Granular replacement |
|---|---|
| `accounting.transactions` | `accounting.invoices`, `accounting.payments`, `accounting.banktransactions`, `accounting.manualjournals` |
| `accounting.transactions.read` | `accounting.invoices.read`, `accounting.payments.read`, … |

`accounting.invoices` covers **CreditNotes, Invoices, LinkedTransactions, Quotes, PurchaseOrders, RepeatingInvoices**. `accounting.payments` covers **BatchPayments, Overpayments, Payments, Prepayments**. `accounting.contacts` covers **Contacts, ContactGroups**. `accounting.settings` covers **Accounts, BrandingThemes, Currencies, Items, InvoiceReminders, Organisation, TaxRates, TrackingCategories, Users** — all read-write, with `accounting.settings.read` as the GET-only variant. Source for each row: the scopes table on https://developer.xero.com/documentation/guides/oauth2/scopes/.

### Minimum scope set for our three flows

For a membership/events biller that creates contacts, invoices, payments, credit notes and reads tax rates, items and tracking categories:

```
offline_access
accounting.contacts          # create/update contacts (→ members)
accounting.invoices          # ACCREC invoices + credit notes
accounting.payments          # apply/delete payments
accounting.settings          # TaxRates, Items, TrackingCategories, Organisation, Currencies, Accounts
```

Optional: `openid profile email` only if you also do Sign In with Xero; `app.connections` only if you manage connections via client-credentials tokens (web apps on the code grant; https://developer.xero.com/documentation/best-practices/managing-connections/connections/).

`offline_access` is not optional in practice — it is required for a refresh token (https://developer.xero.com/documentation/guides/oauth2/scopes/#offline-access) and certification requires it outright: "Using the offline_access scope is a requirement for certification" (https://developer.xero.com/documentation/xero-app-store/app-partner-guides/certification-checkpoints/).

If the app only ever **reads** tax rates/items (never writes accounts or items), `accounting.settings.read` suffices for that piece; there is no narrower tax-rate scope — TaxRates sits inside settings (scopes table, same URL).

### Webhooks need no scope

Webhooks are configured per-app in the developer portal, not authorised per tenant: "Webhooks are configured on a per-app basis and we will send you events for every Xero organisation connected to the app… you would need to use the offline_access scope in order to maintain the connection longer than 30 minutes." — https://developer.xero.com/documentation/guides/webhooks/overview/

### What breaks if `accounting.settings` is omitted

Per the scopes table (https://developer.xero.com/documentation/guides/oauth2/scopes/), without it every call to these endpoints is unauthorised:

- **`/TaxRates`** — the source of `TaxType` codes used on line items. Without it you cannot look up an org's GST rates, so you are forced to hard-code `OUTPUT`/`OUTPUT2`, which is exactly what Xero tells you not to do ("Do not hard code a mapping"; "you can't use the Name field" — https://developer.xero.com/documentation/best-practices/data-integrity/taxes/). Hard-coding is also a certification failure risk (checkpoint 8).
- **`/Items`** — no Products & Services mapping; you must use free-text line items with `AccountCode` instead.
- **`/Accounts`** — no chart-of-accounts mapping, which certification checkpoint 7 requires for any app that creates data ("you will need mapping functionality so that users can select one or more account codes").
- **`/Organisation`** — no base currency, no `IsDemoCompany`, no `ShortCode` for deep links, no `TaxNumber`/country to know whether the org is AU or NZ.
- **`/TrackingCategories`**, **`/Currencies`** — no region/class tracking, no multi-currency setup.

Practical consequence for us: without `accounting.settings` we cannot safely decide GST treatment per organisation, and cannot satisfy certification checkpoints 7 and 8. The failure mode is 401/403 at call time, not at consent time — so it surfaces in production, on a customer's first invoice. **[inference]** This is why the scope must be requested from day one: scopes are additive on re-consent but you cannot remove them, and adding a scope later forces every existing customer through the consent screen again.

---

## 3. Limits, throttling and batch strategy

### The numbers (per tenant)

> "Concurrent Limit: 5 calls in progress at one time. Minute Limit: 60 calls per minute. Daily Limit: 1,000 calls per day for starter, 5,000 calls per day for higher tiers… App Minute Limit: 10,000 calls per minute" (across all tenants)
> — https://developer.xero.com/documentation/guides/oauth2/limits/

Restated with the 24-hour framing ("over a 24 hour period between a single tenant/app connection") at https://developer.xero.com/documentation/best-practices/api-call-efficiencies/rate-limits/.

Tier ceilings and their price points: Starter 5 connections / 1,000 calls per day per org; Core 50 / 5,000; Plus 1,000; Advanced 10,000; Enterprise unlimited — https://developer.xero.com/pricing.

### What a 429 looks like

Response headers on a minute-limit breach (verbatim example from https://developer.xero.com/documentation/best-practices/api-call-efficiencies/rate-limits/):

```
Retry-After: "24"
Xero-Correlation-Id: "4efa3aed-8317-4103-a8d7-c1c32d6e23fd"
X-AppMinLimit-Remaining: "9929"
X-MinLimit-Remaining: "0"
X-DayLimit-Remaining: "4531"
X-Rate-Limit-Problem: "minute"
Content-Length: "0"
```

- `X-Rate-Limit-Problem` names the limit hit (`minute` / `day` / concurrency) and `Retry-After` gives seconds to wait (both documented at https://developer.xero.com/documentation/guides/oauth2/limits/ and the rate-limits page above).
- "No matter the limit you've hit, we've also given you the time (in seconds) of how long you'll have to wait" — https://developer.xero.com/documentation/best-practices/api-call-efficiencies/rate-limits/
- Remaining-quota headers (`X-DayLimit-Remaining`, `X-MinLimit-Remaining`, `X-AppMinLimit-Remaining`) arrive on **successful** calls; use them proactively.
- "Requests are counted against a fixed window which will reset at different times for each tenant" — https://developer.xero.com/documentation/guides/oauth2/limits/. Do not assume a shared clock.

### Retry/backoff expectations

Xero's stated position: "When you reach a rate limit the Retry-After header will tell you how long to wait before making another call. You should pause requests to that tenant until that time. We cannot reset the limit for you." And when that tenant's minute window reopens, "Always honour this header to prevent further throttling" — https://developer.xero.com/documentation/best-practices/api-call-efficiencies/rate-limits/.

For certification they "will check your usage of the API and the frequency of hitting rate limits, and we may ask you to implement ways of reducing your rate limit errors" — same page.

**[inference]** Concretely: a per-tenant token bucket (60/min, 5 in flight) plus a `Retry-After`-driven sleep keyed on the tenant, not global exponential backoff. Global backoff on a single tenant's 429 will stall every other customer.

### Recommended batch strategy

- **Batch writes**: "you can create more than one Invoice in a single PUT or POST Invoices API call. While there's no upper limit in the number of nodes that can be sent at one time, a ceiling of about 50 nodes per request is practical – this will ensure a request does not exceed the maximum size of 3.5MB." — https://developer.xero.com/documentation/guides/oauth2/limits/. "When you PUT or POST an invoice, you can do up to 50 invoices in a single call" — https://developer.xero.com/documentation/best-practices/data-integrity/creating-invoices/. Request-size cap is 10MB overall (limits page).
- **Page size**: default 100, max 1000, min 1; out-of-range values are silently clamped ("`?page=1&pageSize=5000` will return 1000 items") — https://developer.xero.com/documentation/api/accounting/requests-and-responses/. A `pagination` object (`page`, `pageSize`, `pageCount`, `itemCount`) comes back in the response — same page.
- **`summaryOnly=true`** on GET Contacts and GET Invoices "to retrieve a smaller version of the response object… excluding computation-heavy fields like LineItems on invoices and detailed Addresses or Balances on contacts" — https://developer.xero.com/documentation/best-practices/api-call-efficiencies/rate-limits/ and https://developer.xero.com/documentation/api/accounting/requests-and-responses/. Caveat: "This query parameter works with other filters, but not when filtering on the fields that are excluded in the response."
- **`If-Modified-Since`** for deltas, with the explicit caveat that "Not all changes will trigger a change of the UpdatedDateUTC field. These include changes to partially paid transactions which don't generate a journal such as DueDate or SentToContact, and Contact fields pulled from other sources such as Balances, IsSupplier, and isCustomer. As a result, transactions with these changes may not be returned with an If-Modified-Since query." — https://developer.xero.com/documentation/api/accounting/requests-and-responses/
- Xero recommends only GETting invoices from the **past two years** for backfill — https://developer.xero.com/documentation/best-practices/api-call-efficiencies/if-modified-since/
- **Queue, don't block a request**: "it's recommended that an app is structured to schedule or queue this in a job so there's no user expectation of an immediate response" — https://developer.xero.com/documentation/best-practices/api-call-efficiencies/rate-limits/
- Endpoints that support `page`/`pageSize`: Contacts, Invoices, BankTransactions, CreditNotes, ManualJournals, Payments, Quotes, PurchaseOrders — https://developer.xero.com/documentation/best-practices/api-call-efficiencies/paging/.
- GET Payments has its own **high-volume threshold**: responses >100k payments, or unoptimised `where`/`order` fields pushing past that, are rejected with **400** — https://developer.xero.com/documentation/api/accounting/payments/

### System volume limits worth knowing

Xero is "designed for volumes of up to 5,000 Sales invoices… per month"; contacts lists >10,000 "could cause performance issues"; tracked items >4,000 trigger performance problems (create/update ≤100 items per request) — https://developer.xero.com/documentation/guides/oauth2/limits/

---

## 4. Endpoint-by-endpoint flow recipes

Base URL `https://api.xero.com/api.xro/2.0`. Required headers on every call:

```
Authorization: Bearer {access_token}
xero-tenant-id: {tenantId}
Accept: application/json
```

(https://developer.xero.com/documentation/guides/oauth2/token-types/#calling-the-api)

Default success response is **XML**; set `Accept: application/json` for JSON (https://developer.xero.com/documentation/api/accounting/requests-and-responses/). JSON dates come back as .NET format `"\/Date(1439434356790)\/"` (ms since epoch) with some `…String` companions — same page. **[inference]** In FastAPI, parse both the numeric and the `…String` variants; don't trust `DateString` alone for sorting.

**Idempotency**: send `Idempotency-Key` on **POST/PUT/PATCH only** (ignored on GET). Max 128 characters; keys cached **6 minutes**; replaying a key with a *different* request returns **400** (`Idempotency Key: KEY_VALUE is used with a different request.`); keys longer than 128 chars return 400. Idempotency is checked **after** rate limiting, so duplicate attempts still consume quota. If Xero's idempotency layer is degraded it returns 500 rather than risk a double-write. Recommended key generation: "four UUIDs… concatenated". — https://developer.xero.com/documentation/best-practices/data-integrity/idempotency/ and parameter definition in https://raw.githubusercontent.com/XeroAPI/Xero-OpenAPI/master/xero_accounting.yaml (`idempotencyKey`, "128 character max")

### 4.1 Member → Contact

`POST /Contacts` (create/update), `PUT /Contacts` (create only — "A PUT method will create new data in Xero, whereas a POST will either create new data or update existing data") — https://developer.xero.com/documentation/api/accounting/requests-and-responses/

Field mapping that matters (https://developer.xero.com/documentation/api/accounting/contacts/):

| Xero field | Use |
|---|---|
| `ContactID` | **The** foreign key. "We recommend all developers use ContactID to uniquely reference contacts in Xero and do not rely on ContactName" |
| `Name` | Member/org display name (required when creating) |
| `FirstName`/`LastName`, `EmailAddress`, `Phones[]` | Individual members |
| `ContactNumber` | "read only in the Xero UI, used to identify contacts in external systems… displayed as Contact Code". **Only one contact number per contact** — check for an existing value from another integration before writing (https://developer.xero.com/documentation/best-practices/data-integrity/contacts/) |
| `AccountNumber` | User-defined, writable via API — a safer second external key |
| `TaxNumber` ("also known as the ABN (Australia), GST Number (New Zealand)") | Member ABN/GST number |
| `IsCustomer` / `IsSupplier` | **Not settable at create.** "When an invoice (type ACCREC) is raised against the contact, the field 'IsCustomer' will be set to true" — https://developer.xero.com/documentation/best-practices/data-integrity/contacts/ |
| `Addresses[]`, `ContactGroups` | Billing address; segmentation |

Certification expects duplicate-avoidance and an explicit mapping option: "This process can include matching contact names and email addresses… Do avoid using the contact name as a unique reference" (contact mapping page above). Practical dedupe order **[inference]**: `ContactID` → `ContactNumber` → `AccountNumber` → exact `EmailAddress` → `Name`, with a human-confirm step when only a name matches.

Read-back: `GET /Contacts?IDs=guid1,guid2` (comma-separated, explicit fast path) or `?where=EmailAddress=="x"` (optimised equals fields: `Name`, `EmailAddress`, `AccountNumber`; `searchTerm` does a case-insensitive search across Name/First/Last/ContactNumber/CompanyNumber/EmailAddress) — https://developer.xero.com/documentation/api/accounting/contacts/. Note: "changes to the Balances, IsCustomer or IsSupplier values will not trigger a contact to be returned with the Modified-After filter"; archived contacts are excluded from GET by default.

### 4.2 Period → Invoice

`POST /Invoices` (up to 50 per call). Core fields (https://developer.xero.com/documentation/api/accounting/invoices/):

| Field | Notes |
|---|---|
| `Type` | `ACCREC` for sales invoices (vs `ACCPAY` bills) — https://developer.xero.com/documentation/best-practices/data-integrity/creating-invoices/ |
| `Contact` | `{"ContactID": ...}` for an existing member, or `{"Name": ...}` to create-on-the-fly |
| `Date`, `DueDate` | `YYYY-MM-DD`; **both optional** — omit `DueDate` and Xero applies the org's default |
| `Reference` | Free text (e.g. "Membership 2026", "Event #123") |
| `InvoiceNumber` | ACCREC must be unique (max 255 chars); "when missing will auto-generate from your Organisation Invoice Settings" — https://developer.xero.com/documentation/api/accounting/invoices/ |
| `LineItems[]` | `Description`, `Quantity`, `UnitAmount`, `AccountCode`, `TaxType`, optionally `ItemCode`, `DiscountRate`, `Tracking[]` |
| `LineAmountTypes` | `Exclusive` (default for invoices/credit notes/POs), `Inclusive`, `NoTax` — https://developer.xero.com/documentation/api/accounting/types/ |
| `Status` | `DRAFT` (**default if omitted**), `SUBMITTED`, `AUTHORISED` — https://developer.xero.com/documentation/best-practices/user-experience/invoice-status/ |
| `CurrencyCode` | Non-base currency; the currency **must already exist in the org** or the call errors |
| `Url` | Deep-link back into our app from the Xero invoice screen (certification: "Recommended") |

Status semantics that matter for billing (https://developer.xero.com/documentation/best-practices/user-experience/invoice-status/):
- `DRAFT` — "No journals are created… won't be used in any reports"; can hold incomplete line items.
- `AUTHORISED` — creates journals, is visible as "Approved", and **only AUTHORISED invoices accept payments**; status flips to `PAID` when fully paid.
- Valid transitions: DRAFT→{DRAFT,SUBMITTED,AUTHORISED,DELETED}; SUBMITTED→{SUBMITTED,AUTHORISED,DRAFT,DELETED}; AUTHORISED→{AUTHORISED,VOIDED}. You cannot update an invoice that is fully paid, part-paid, has credit notes applied, or is in a locked period (creating-invoices page).

Example minimal ACCREC (from https://developer.xero.com/documentation/best-practices/data-integrity/creating-invoices/):

```json
{"Invoices":[{"Type":"ACCREC","Contact":{"Name":"Lobelia Smith"},
 "LineItems":[{"Description":"Consult 11-Aug 2025","Quantity":1,"UnitAmount":300,"AccountCode":"260"}],
 "Date":"2025-08-11","Reference":"PTE 971","Status":"DRAFT"}]}
```

**Bulk-write error handling**: append `?summarizeErrors=false` when sending multiple entities so every entity comes back with `StatusAttributeString` of `OK`/`WARNING`/`ERROR`; validation problems then return **HTTP 200** with per-item errors rather than a 400 for the whole batch. "We strongly recommend that your integration: log all validation warnings… surface warnings to users… do not suppress or ignore warnings." — https://developer.xero.com/documentation/api/accounting/requests-and-responses/

Read-back: `GET /Invoices?Statuses=AUTHORISED&ContactIDs=...`, `?IDs=...`, `?page=n&pageSize=1000`, `?summaryOnly=true`, `If-Modified-Since: 2026-01-01T00:00:00`, or `?where=Status=="AUTHORISED" AND DueDate>DateTime(2026,01,01)` — https://developer.xero.com/documentation/api/accounting/requests-and-responses/ and https://developer.xero.com/documentation/best-practices/api-call-efficiencies/filtering/. Keep `where` simple (`==` preferred); long complex queries time out.

### 4.3 Payment → reconcile

`PUT /Payments` (not POST — POST on `/Payments` is only for **deleting/reversing** by setting `{"Status":"DELETED"}`). Payments "cannot be modified, only created and deleted" — https://developer.xero.com/documentation/api/accounting/payments/

Required shape: **one** identifier object (`Invoice` / `CreditNote` / `Prepayment` / `Overpayment`) plus an `Account` (bank account, or an account with "enable payments" switched on), `Date`, `Amount`. Optional `Reference`, `IsReconciled`, `CurrencyRate`, `BankAmount`.

```json
{"Invoice":{"InvoiceID":"96df0dff-..."},
 "Account":{"Code":"001"},
 "Date":"2009-09-08",
 "Amount":32.06}
```
— verbatim example, https://developer.xero.com/documentation/api/accounting/payments/

Constraints:
- `Amount` "must be less than or equal to the outstanding amount owing on the invoice" (payments page).
- The invoice must be `AUTHORISED` — payments can only be applied to approved AR/AP invoices (invoice-status page).
- Payment accounts must be `BANK` type or have payments enabled; this is certification checkpoint 7 ("Payments: mapping payments is required if you are POST-ing payments to Xero… accounts where payments to them have been enabled") — https://developer.xero.com/documentation/api/accounting/payments/ and https://developer.xero.com/documentation/xero-app-store/app-partner-guides/certification-checkpoints/
- Multi-currency: if either the payment account or the invoice is in a non-base currency, the payment is multicurrency; specify `BankAmount` (preferred) which lets Xero compute `CurrencyRate`, or set `CurrencyRate` — https://developer.xero.com/documentation/api/accounting/payments/ and https://developer.xero.com/documentation/best-practices/data-integrity/multicurrency/
- Batch alternative: `BatchPayments` for paying multiple invoices in one transaction (payments page).
- `IsReconciled`: "Conversion related apps can utilise the IsReconciled flag in scenarios when a matching bank statement line is not available" — this is the lever for a payments provider that has already settled funds.

Reconciling read-back: `GET /Payments` (supports `If-Modified-Since`, `where`, `page`/`pageSize`; watch the 100k threshold) and invoice `AmountDue`/`AmountPaid`/`Status`.

### 4.4 Cancellation → credit note

Create the credit note, **then allocate it in a second call**. Both verbs exist (https://developer.xero.com/documentation/api/accounting/creditnotes/):

- `POST /CreditNotes` — "Use this method to **create or update** a credit note."
- `PUT /CreditNotes` — "The PUT method can be used to **create** CreditNotes **or allocate** CreditNotes to outstanding Invoices."

Allocation (a separate call, and a separate URL):

> "Credit notes must have a Status of `AUTHORISED` to be available for allocation." and "You cannot create and allocate a credit note in a single call. The create and allocation must be done in two separate calls"
> — https://developer.xero.com/documentation/api/accounting/creditnotes/

```
PUT https://api.xero.com/api.xro/2.0/CreditNotes/{CreditNoteID}/Allocations
{ "Amount": 60.50, "Invoice": { "InvoiceID": "..." } }
```
(`AppliedAmount` instead of `Amount` for XML; `Date` on an allocation is read-only and is the later of the invoice and credit-note dates.) Un-allocate with `DELETE /CreditNotes/{CreditNoteID}/Allocations/{AllocationID}`.

Useful fields: `CreditNoteID`, `Type` (`ACCRECCREDIT` for sales), `Status`, `LineItems`, `CurrencyCode`, `Reference`, `RemainingCredit`, `Allocations[]`. `Date` defaults to today in the org's timezone if omitted; `CreditNoteNumber` auto-generates for ACCRECCREDIT when missing.

**This two-call design is the most common bug in this flow [inference]**: a retry between the two calls leaves an unallocated credit note. Both calls must carry idempotency keys, and the allocation call must be re-driven from stored state, not from a user click.

### 4.5 Reading back changes (the "two-way" half)

Three mechanisms, in preference order:

1. **Webhooks** for change notification → then a targeted GET by `resourceId` (or comma-separated `IDs`).
2. **`If-Modified-Since`** delta sweeps for backfill/reconciliation (documented caveats above — partial-payment fields and balance-derived contact fields do not bump `UpdatedDateUTC`).
3. **`where` / `IDs` / `ContactIDs` / `Statuses`** targeted fetches.

Ordering/consistency: default ordering across Contacts, Payments, Credit Notes, Invoices and Bank Transactions is `UpdatedDateUTC ASC, [ID] ASC` (secondary ordering by ID applied by default) — https://developer.xero.com/documentation/api/accounting/requests-and-responses/. Use `?order=...` only on optimised fields.

---

## 5. Webhooks

### Event types available

Configured **per app**, delivered for **every** connected organisation — https://developer.xero.com/documentation/guides/webhooks/overview/

| Category | Types | Meaning |
|---|---|---|
| Contact | CREATE / UPDATE | "An existing contact has been updated (including when contacts are archived)" |
| Invoice | CREATE / UPDATE | "...(including when invoices are archived)" |
| Credit Note | CREATE / UPDATE | |
| Payment | CREATE / UPDATE | **UPDATE means the payment was deleted/removed** |
| Overpayment / Prepayment | CREATE / UPDATE | |
| Subscription | CREATE / UPDATE | Xero App Store subscriptions only |

Event-category reference pages: `/documentation/guides/webhooks/contacts`, `/invoices`, `/credit-notes`, `/payments`, `/overpayments`, `/prepayments`, `/subscriptions` (all under https://developer.xero.com/documentation/guides/webhooks/overview/).

### Payload shape

```json
{
  "events": [{
    "resourceUrl": "https://api.xero.com/api.xro/2.0/Invoices",
    "resourceId": "717f2bfc-c6d4-41fd-b238-3f2f0c0cf777",
    "eventDateUtc": "2025-10-21T01:15:39.902",
    "eventType": "Update",
    "eventCategory": "INVOICE",
    "tenantId": "c2cc9b6e-9458-4c7d-93cc-f02b81b0594f",
    "tenantType": "ORGANISATION"
  }],
  "lastEventSequence": 1,
  "firstEventSequence": 1,
  "entropy": "S0m3r4Nd0mt3xt"
}
```
— https://developer.xero.com/documentation/guides/webhooks/invoices/ and the overview page. Events carry **no business data** — only the resource to fetch. `data` objects exist only for certain categories (the overview table notes "Only certain event categories may include a data object").

### HMAC signature verification

- Header: **`x-xero-signature`**, a "hashed signature of the payload" — https://developer.xero.com/documentation/guides/webhooks/overview/
- Algorithm: "If the payload is hashed using **HMACSHA256** with your webhook signing key and base64 encoded, it should match the signature in the header." (same page)
- **Sign the raw request body bytes**, before any JSON parsing or re-serialisation **[inference — standard HMAC practice; Xero specifies only HMAC-SHA256 over "the payload"]**.
- Failure handling is a *requirement*, not a nicety: return **401** for incorrectly signed payloads, **2xx** for correct ones.

### Intent-to-receive (subscription) step

Creating a webhook (or changing its URL, or re-enabling a disabled one) leaves it in status **"Intent to receive required"**; no events flow until you click **Validate** in the portal. Xero then sends a series of POSTs with an **empty events array**:

```json
{"events": [], "lastEventSequence": 0, "firstEventSequence": 0, "entropy": "..."}
```

> "To gain Intent to receive validation, the receiving url must respond with a 2xx status for all **correctly signed payloads** and status: 401 Unauthorized for all **incorrectly signed payloads**."
> — https://developer.xero.com/documentation/guides/webhooks/overview/

Statuses: `Intent to receive required` → `Intent to receive in progress` (up to 30 s) → `OK`; failure returns to `required` with the fail reason shown. Then `Retry`, then `Disabled`. (same page, "The webhooks status" table)

### What a receiver must do

1. HTTPS on port 443.
2. Respond **within 5 seconds** with a 2xx.
3. No cookies in the response.
4. **401** when the signature doesn't match.
5. Acknowledge **before** doing the work: "Store the payload to a queue for future asynchronous processing" is Xero's own sample-app pattern (https://github.com/XeroAPI/XeroWebhooksReceiver).
6. Be **idempotent and replay-safe**: "Consumer apps must ensure they implement idempotency logic and support message replayability" (webhooks overview). Use `firstEventSequence`/`lastEventSequence` + `resourceId` + `eventDateUtc` to dedupe.

### Retry / failure behaviour

- "When you fail to respond correctly to a webhook we will immediately retry. Any subsequent retry attempts we will space them out by **15 minutes** until a successful response is given."
- "If after **24 hours** we still have not received a successful response we will disable your subscription and send an email notification to each of the collaborators."
- "Any events that happen while your subscription is in the Retry or Disabled states will be saved for up to **31 days** and replayed in order once your subscription is healthy again."
- Re-enable requires completing the ITR process again.

All from https://developer.xero.com/documentation/guides/webhooks/overview/ ("Delivery failures").

Operational consequence **[inference]**: a webhook outage longer than 24 h disables the subscription and requires a human to re-validate in the developer portal, and events older than 31 days are gone — so webhooks alone are not a complete reconciliation strategy. Run a nightly `If-Modified-Since` sweep as a safety net.

---

## 6. Tax: GST for Australia and New Zealand

### How tax is referenced

- Line items carry a **`TaxType`** code. "Use the TaxType element to specify tax rates – **you can't use the Name field**." — https://developer.xero.com/documentation/best-practices/data-integrity/taxes/
- `TaxType` is auto-generated by Xero per organisation; system tax types cannot be modified; custom ones are `TAX001`, `TAX002`… — https://developer.xero.com/documentation/api/accounting/types/
- Retrieve them per org: `GET /TaxRates` (optionally `/TaxRates/{TaxType}`), and filter by `CanApplyToRevenue` when choosing sales rates — https://developer.xero.com/documentation/api/accounting/taxrates/ and https://developer.xero.com/documentation/best-practices/data-integrity/creating-invoices/
- Tax rates are constrained by account type: "Sending a line item with a tax rate that can't be used with the line's account code will generate the error `The TaxType code 'xxx' cannot be used with account code 'xxx'`." The per-country table on https://developer.xero.com/documentation/api/accounting/taxrates/ lists which account classes each rate allows.

### Default rates by country (verbatim from Xero's tables)

**Australia** — https://developer.xero.com/documentation/api/accounting/types/ (Tax Types → Australia)

| TaxType | Rate | Name |
|---|---|---|
| `OUTPUT` | 10.00 | GST on Income |
| `INPUT` | 10.00 | GST on Expenses |
| `EXEMPTOUTPUT` | 0.00 | GST Free Income |
| `EXEMPTEXPENSES` | 0.00 | GST Free Expenses (system defined) |
| `BASEXCLUDED` | 0.00 | BAS Excluded |
| `GSTONIMPORTS` | 0.00 | GST on Imports (system defined) |

**New Zealand** — same page (Tax Types → New Zealand)

| TaxType | Rate | Name |
|---|---|---|
| `OUTPUT2` | 15.00 | GST on Income |
| `INPUT2` | 15.00 | GST on Expenses |
| `ZERORATED` | 0.00 | Zero Rated |
| `NONE` | 0.00 | No GST (system defined) |
| `GSTONIMPORTS` | 0.00 | GST on Imports (system defined) |

Note the asymmetry that causes real bugs **[inference]**: NZ zero-rated is `ZERORATED`, AU GST-free is `EXEMPTOUTPUT`/`BASEXCLUDED`; "tax exempt" is `NONE` in both but means different things on a return. Xero's worked example elsewhere uses `ZERORATEDOUTPUT` for a zero-rated sales line in a UK-style org (https://developer.xero.com/documentation/best-practices/data-integrity/creating-invoices/), which reinforces that the code must be looked up per org, not remembered.

Sales-tax returns: "In Australia, New Zealand and the United Kingdom, Xero supports the filing of sales tax returns. It's important that if you do create a tax rate in these regions, a report tax type is included in any creation request" — https://developer.xero.com/documentation/best-practices/data-integrity/taxes/. Report tax types are listed under https://developer.xero.com/documentation/api/accounting/types/#report-tax-types.

### Inclusive vs exclusive

- `LineAmountTypes`: `Exclusive` | `Inclusive` | `NoTax` — https://developer.xero.com/documentation/api/accounting/types/
- Defaults: "Invoices, Credit Notes, and Purchase Orders will be Tax Exclusive by default if LineAmountTypes isn't specified. Receipts and Bank Transactions (including Prepayments and Overpayments) will be Tax Inclusive by default, and Manual Journals will be No Tax by default." — https://developer.xero.com/documentation/best-practices/data-integrity/taxes/
- Arithmetic: exclusive — UnitAmount 10.00 @10% → line 10.00, tax 1.00. Inclusive — UnitAmount 10.00 @10% → line 10.00, tax 0.91 (calculated by "adding the tax rate to 1 and dividing the rounded line total by the rate, rounding to two decimal places then subtracting"). Each line's tax is calculated and **rounded separately**; tax rates can have 4 dp but tax amounts round to 2 dp. (same page)
- UI trap: "Tax Inclusive invoices show as Tax Exclusive on the view screen in Xero once approved. The invoice is still Inclusive and shows that way through the API." (same page)

For Australian consumer-facing membership pricing, prices are normally GST-inclusive (ACCC/ACL convention), so our amounts must be sent as `Inclusive` or pre-divided **[inference — commercial convention, not a Xero rule]**. Sending inclusive amounts as `Exclusive` silently overcharges GST by 10%, so this must be an explicit per-org setting, not a default.

### Tax-exempt / zero-rated members

- Zero-rated and exempt rates exist as distinct `TaxType`s per country (above). Do not substitute `NONE` for a genuine zero-rated supply — `NONE` means "no tax" and drops the line out of the GST return **[inference, supported by the AU table listing `BASEXCLUDED` and `EXEMPTOUTPUT` separately]**.
- The alternative "lump the total tax into a line item with `TaxType: None`" technique is explicitly **invalid for AU, NZ and UK**: "Note: This approach is not valid for customers in Australia, New Zealand or the United Kingdom" — https://developer.xero.com/documentation/best-practices/data-integrity/taxes/
- If we let Xero calculate: "specify the AccountCode for each line item and leave the TaxType and TaxAmount empty. Xero will automatically use the Tax Rate set up in Xero for the AccountCode you specified." But be careful — "You can't use the Name field", and "If you don't supply a TaxType then Xero will use the default tax rate on the Chart of Accounts account that the line item is coded to. All other defaults such as Contacts or Inventory Items are disregarded." — https://developer.xero.com/documentation/best-practices/data-integrity/creating-invoices/ and taxes page.
- Xero asks you to "avoid posting the specific tax amounts unless you've discussed it with your Developer Evangelist first" (taxes page).

### Multi-currency caveats

- Check `BaseCurrency` per org via `/Organisation` (or `/Organisation/Actions` → `UseMulticurrency`) before sending a foreign-currency invoice — https://developer.xero.com/documentation/api/accounting/organisation/ and https://developer.xero.com/documentation/best-practices/data-integrity/creating-invoices/
- The currency must **already be registered** in the org, otherwise "you will receive an error when trying to post an invoice or bill"; `GET /Currencies` to check, `PUT /Currencies` to add — same page.
- `CurrencyRate`: 1 for base-currency invoices; otherwise a rate; payments can supply `BankAmount` and let Xero derive the rate (preferred over setting `CurrencyRate`) — https://developer.xero.com/documentation/api/accounting/payments/ and https://developer.xero.com/documentation/best-practices/data-integrity/multicurrency/
- Xero returns **CurrencyRate validation warnings** (1:1 rate, inverse rate, suspect rate) — log them, don't ignore them: https://developer.xero.com/documentation/api/accounting/requests-and-responses/ and https://developer.xero.com/documentation/best-practices/data-integrity/multicurrency/
- Certification treats multicurrency as **Required** even if the org isn't multicurrency today ("they may have historical multicurrency data or may upgrade") — https://developer.xero.com/documentation/xero-app-store/app-partner-guides/certification-checkpoints/

---

## 7. App types, certification, and selling commercially

### What exists now

Current OAuth 2.0 docs describe: **code flow (web app)**, **PKCE (native)**, **Custom Connection (M2M, single org)** — https://developer.xero.com/documentation/guides/oauth2/overview/. There is no "private/public app" toggle in the OAuth 2.0 model; the commercial question is answered by **tier + certification**, not app type.

### Tiers and what they gate

From https://developer.xero.com/pricing (rendered page) and https://developer.xero.com/documentation/guides/oauth2/limits/:

| Tier | Max connections | Certification | Security assessment | App Store |
|---|---|---|---|---|
| Starter (default, free) | 5 | — | — | No |
| Core | 50 | — | — | No |
| Plus | 1,000 | Required | Required (initial + annual) | Optional |
| Advanced | 10,000 | Required | Required | Optional |
| Enterprise | No limit | Required | Required | Required |

Per-tenant API volume stays 1,000/day on Starter and 5,000/day on every higher tier (pricing page).

Additionally: **"each organisation or practice is limited to connecting a maximum of five uncertified apps. There is no limit on connecting certified apps."** — https://developer.xero.com/documentation/guides/oauth2/limits/. Custom Connection apps "do not count toward the five uncertified app limit" — https://developer.xero.com/documentation/guides/oauth2/custom-connections/

### Can an unverified/internal integration be used commercially?

**Yes, within limits** — nothing requires certification to operate. But the ceiling arrives fast and is externally imposed:

- 5 connections total on Starter (https://developer.xero.com/pricing)
- and each customer org can hold at most 5 uncertified apps total, across *all* vendors — so an org already using 5 uncertified apps cannot connect ours at all (https://developer.xero.com/documentation/guides/oauth2/limits/)
- no App Store listing below Plus, and listing requires certification (https://developer.xero.com/documentation/xero-app-store/app-partner-guides/certification-checkpoints/)
- connecting more than 5 tenants requires Core (https://developer.xero.com/documentation/guides/oauth2/overview/)

Xero's own advice: "We recommend applying to be listed on the Xero App Store once you've onboarded at least **10 beta customers**" (https://developer.xero.com/documentation/guides/oauth2/limits/), and "Apps can beta test with at 5 customers on the Starter Tier" (https://developer.xero.com/documentation/xero-app-store/app-success-tips/building-a-great-app/).

### What certification requires

Checkpoints from https://developer.xero.com/documentation/xero-app-store/app-partner-guides/certification-checkpoints/ (and the matrix at https://developer.xero.com/documentation/best-practices/overview/cert-matrix/):

1. **Connection** — setup page; display tenant name and connection status; Connect/Disconnect/Reconnect buttons; **DELETE `/connections/{id}` on disconnect** ("Do not rely on the access/refresh tokens to expire"); handle disconnect from Xero's side; support 1:1 or multi-org; offboarding process. No pop-ups/new tabs in the auth flow; never collect Xero credentials.
2. **Branding and naming** — app name reflects go-to-market name, **cannot contain the word "Xero"**; use Xero's connect/disconnect buttons and standard logo.
3. **App Launcher** — set a "Login URL for launcher" in the portal.
4. **Scopes** — minimal scopes, explained; `offline_access` **required**; granular scopes.
5. **Error handling** — surface Xero's error messages to users; logs page recommended.
6. **Data integrity** — ACTIVE account codes, non-archived contacts, correct handling of currencies/tax; avoid system account codes 800/610 except overpayments.
7. **Account and payment mapping** — user-selectable account codes; payments need payment-enabled accounts; never hard-code defaults.
8. **Taxes** — map Xero tax rates, or create with permission; don't post specific tax amounts.

Also **Required** in the matrix: App Store listing + App Store subscriptions (high effort), root
branding, multicurrency (high effort), rounding, Sign Up with Xero, webhooks (for subscription events). **Recommended**: App Launcher, collaborators, contacts mapping, deep linking, idempotency, invoice status choice, invoice URL, `If-Modified-Since`, paging, rate-limit handling, tracking categories, taxes, security.

Security assessment kicks in at Plus and, separately, "once you reach **1000 connections**" (security row in the matrix; https://developer.xero.com/faq/xero-ecosystem-security-requirements-update).

Certification upgrades you to Plus: "Once certified you'll be upgraded to the Plus Tier" (certification-checkpoints).

---

## 8. Testing

- **Demo company** is Xero's recommended path: free, pre-populated with dummy data, unlimited invoices, can be reset at any time, country can be switched, resets itself **28 days after creation**, cannot invite other users. Connect it exactly like a real org; after a reset you must **reconnect your app**. — https://developer.xero.com/documentation/development-accounts/
- Access: log in at https://my.xero.com/ and enter/reset the demo company; change its country there too (same page).
- **API Explorer** (https://api-explorer.xero.com/) lets you make live calls against the demo company and see full headers/status — recommended for debugging rate-limit headers (https://developer.xero.com/documentation/best-practices/api-call-efficiencies/rate-limits/).
- **Custom Connections can be attached to the Demo Company for free** for development (https://developer.xero.com/documentation/guides/oauth2/custom-connections/).
- **App Metrics**: developer portal → app → History → Metrics, with rate-limit-hit counts (>1,000 minute, >1,000 day, concurrent violations) — https://developer.xero.com/documentation/best-practices/api-call-efficiencies/rate-limits/
- **Webhook testing**: point the webhook at a tunnel (`ngrok http --bind-tls=true 5000`), then create/modify a contact in a connected org — https://github.com/XeroAPI/XeroWebhooksReceiver.
- **Xero trial organisation** alternative: unlimited invoices, 30 days before billing, no pre-populated data, cannot be reset or country-switched — https://developer.xero.com/documentation/development-accounts/

What behaves differently from production:
- Demo data resets every 28 days and on country change; connections break and must be re-made (development-accounts page).
- `IsDemoCompany: true` is exposed on `/Organisation` (https://developer.xero.com/documentation/best-practices/data-integrity/managing-tokens/).
- Partner-edition orgs (cashbook/ledger) can be connected but have **no invoicing**, so API-created invoices "could not be edited or modified" — avoid them in tests (https://developer.xero.com/documentation/guides/oauth2/limits/).
- Early-plan orgs cap approved AR invoices (20/month) and return `You have reached the limit of invoices you can approve.` with HTTP 400 (same page).
- There is **no Xero-provided sandbox that mirrors production org configuration** — the demo company is the sanctioned substitute **[inference: Xero documents only demo company + trial + API Explorer]**. That means account codes, tax rates, tracking categories and payment accounts in a real customer org are unmapped territory until you run against it.

---

## 9. What we must obtain, and what the product must expose

### Must obtain from the customer

1. **Their Xero organisation** (tenant) — which org, and confirmation of its country (AU vs NZ) because tax type codes differ.
2. **Admin consent**: a user with a role that can authorise API connections. For cashbook/ledger (partner edition) orgs, "Authorisation of connections… must be done by a member of the practice staff – managed client or cashbook client roles cannot authorize an API connection" (https://developer.xero.com/documentation/guides/oauth2/limits/).
3. **Consent to the specific scopes** on the Xero consent screen — non-negotiable, per user, with the ability for them to see the org list and pick orgs.
4. **Mapping decisions**: which sales account code(s) for memberships vs events, which tax rate(s) for standard/zero-rated/exempt, whether prices are GST-inclusive, which bank/payment account to post payments to.
5. **For a Custom Connection pilot**: the client must **purchase a Custom Connection subscription** for their org ($10/m AUD inc GST) before authorisation will work — orgs without sufficient subscriptions "will be displayed but will be unavailable for connection" (https://developer.xero.com/documentation/guides/oauth2/custom-connections/).
6. **Webhook receiver URL** on our side (HTTPS, 443) — theirs is not needed, but their org admin must not block it.

### Must expose in our product

- A **"Connect Xero" button** that redirects (full-page, no pop-up) to `https://login.xero.com/identity/connect/authorize` with `response_type=code`, `client_id`, `redirect_uri`, `scope`, and a per-user `state` (https://developer.xero.com/documentation/guides/oauth2/auth-flow/).
- **Tenant selection**: a Xero login may expose several orgs; after the callback, call `GET https://api.xero.com/connections` (optionally `?authEventId=`) and let the user pick which org maps to which of our tenants (https://developer.xero.com/documentation/guides/oauth2/tenants/). Multiple users connecting the same org counts only once toward our limit, so model connections, not users.
- **Connection status + tenant name** display, with **Disconnect** (calls `DELETE https://api.xero.com/connections/{connectionId}`), and **Reconnect** when tokens die (certification checkpoint 1).
- **Re-auth when tokens expire**: refresh proactively; when refresh fails (60-day lapse, revoked token, removed user, deleted/reset org), surface a clear "Reconnect Xero" action rather than a raw error. Xero's documented 403 body for a bad/unauthorised tenant header is `{"title":"Forbidden","status":403,"detail":"AuthenticationUnsuccessful",...}` (https://developer.xero.com/documentation/best-practices/user-experience/error-handling/).
- **Mapping UI** for accounts, tax rates, items, tracking categories — and the ability to override defaults (checkpoints 6–8).
- **An error/log surface** showing failed syncs with Xero's own message text and, ideally, a deep link to the record (`ShortCode`-based URLs; https://developer.xero.com/documentation/best-practices/user-experience/deep-linking/).
- **Invoice status choice** per org (DRAFT vs AUTHORISED) and **`Url`** set on invoices for the Xero→our-app link (matrix, Recommended).
- **Webhook receiver** + queue + idempotent processor + nightly `If-Modified-Since` safety sweep.

---

## 10. What Jo must do (in order)

1. **Create the app** at https://developer.xero.com/app/manage → "New App". Choose the integration type deliberately: **Web app** (Auth Code grant) for the general product; **Custom connection** only for a single-org pilot.
2. **Decide the flow** (code flow recommended) and record the decision; if a Custom Connection pilot is chosen, confirm the pilot client's country is AU/NZ/UK/US and that they will buy the $10/month subscription.
3. **Register the redirect URI(s)** — must be **https**, except `http://localhost/` for local testing; **`http://127.0.0.1` cannot be used**. Store it identically in the portal and in backend config.
4. **Generate the client secret** and store it in a secrets manager (never in the repo, never client-side).
5. **Fix the scope list** (`offline_access accounting.contacts accounting.invoices accounting.payments accounting.settings`, plus `openid profile email` only if doing SSO) and have a written justification per scope for certification.
6. **Provision Postgres tables** for: connections/tokens (encrypted, with `access_token_expires_at`, `refresh_token_expires_at`, `auth_event_id`), tenant↔our-org mapping, per-org settings (country, base currency, tax mapping, account mapping, payment account, inclusive/exclusive), sync log with `Xero-Correlation-Id`, and an idempotency-key store (key, endpoint, body hash, response, created_at).
7. **Build the OAuth round-trip** (authorize → callback → token exchange → `GET /connections` → tenant selection) with CSRF `state` and no pop-ups.
8. **Build the token service**: single-flight refresh per connection, rotate atomically, 30-minute grace retry, and a "needs re-consent" state.
9. **Stand up the demo company** for development (https://my.xero.com/) and connect it; get `client_id`/`secret` into `.env` for dev only.
10. **Build the write pipeline** with a per-tenant rate limiter (60/min, 5 concurrent), batch size ≤50, `summarizeErrors=false`, and an `Idempotency-Key` on every POST/PUT.
11. **Implement the four flow recipes** (contact, invoice, payment, credit note + separate allocation) against the demo company, with read-back verification after each write.
12. **Create the webhook subscription** in the portal: choose categories (Contact, Invoice, Credit Note, Payment at minimum), set the HTTPS URL, record the **webhook signing key**, then complete **Intent to receive** by returning 2xx/401 correctly within 5 s.
13. **Decide the tier/commercial path now**, not at 5 customers: Starter for pilot → Core (50) for early customers → certification for Plus (1,000) and App Store listing. Budget the certification work (App Store listing, subscriptions, multicurrency, rounding) before promising scale.
14. **Ask the pilot customer for**: org country, admin user who will consent, chart-of-accounts mapping, tax-rate mapping, price GST basis, payment account.
15. **Plan the disconnect/offboarding flow** (DELETE connection, revoke token tokens, purge tokens) — required by certification and needed for the 5-connection ceiling.

---

## 11. Requirement → our implementation → risk

| Requirement | Our implementation | Risk |
|---|---|---|
| OAuth 2.0 code flow with client secret | FastAPI routes `/integrations/xero/connect`, `/callback`; `state` in signed cookie; token exchange via httpx | Redirect-URI mismatch (https-only; 127.0.0.1 forbidden) blocks the pilot at step 1 |
| `offline_access` + refresh | Store refresh + expiry; refresh at T-5min; rotate atomically | Concurrent refresh kills the connection (previous token invalidated); needs single-flight per connection |
| Token storage | Encrypted columns (KMS/managed key), never plaintext; per-connection rows | Decryption key mishandled = every customer's Xero data exposed; certification checkpoint 1 forbids secrets client-side |
| Multi-tenant mapping | `xero_connections` table: our_org_id, xero_tenant_id, tenant_name, tenant_type, auth_event_id | Cross-tenant posting (paying org A's invoice against org B) is a documented failure mode and a data-leak |
| Scope minimalism | `offline_access accounting.contacts accounting.invoices accounting.payments accounting.settings` | Adding `accounting.settings` later forces every customer through re-consent; omitting it breaks tax/account mapping entirely |
| Granular scopes (post-2 Mar 2026) | New app ⇒ granular scopes automatically | Broad-scope examples found online may not be requestable for this app; don't copy old tutorials |
| Rate limits (60/min, 5 concurrent, 1,000–5,000/day per tenant) | Per-tenant token bucket + job queue (Postgres/Redis); read `X-MinLimit-Remaining` | A bulk month-end run of 400 invoices blows a 1,000/day Starter budget in one morning |
| 429 handling | Honour `Retry-After`, keyed per tenant; never global backoff | Global backoff stalls all customers when one org throttles |
| Idempotency | `Idempotency-Key` (4 concatenated UUIDs, ≤128 chars) stored per request; 6-minute window | Keys expire in 6 min — a retry after that creates a duplicate invoice; Xero's own advice is to GET and verify instead |
| Contact identity | `ContactID` as FK, plus `ContactNumber`/`AccountNumber` as extern keys | `ContactNumber` is single-valued and may already be set by another integration |
| `IsCustomer` behaviour | Never set it; rely on first ACCREC invoice flipping it | Logic that filters on `IsCustomer` before invoicing finds nothing |
| Invoice creation | `POST /Invoices`, `Type=ACCREC`, `LineItems` with `AccountCode` + `TaxType`, `Date`, `DueDate`, `Reference`, `Status`, `CurrencyCode` | Default status is DRAFT (no journals, invisible to reports); forgetting `Status: AUTHORISED` means no revenue is recognised |
| Bulk invoice writes | ≤50 per call, `summarizeErrors=false`, per-item status handling | With `summarizeErrors=true` (or default) errors hide and some invoices silently fail |
| Payment application | `PUT /Payments` with invoice + payment-enabled bank account + date + amount | Invoice must be AUTHORISED; wrong account type fails; POST on `/Payments` deletes, it doesn't create |
| Credit notes | `POST` or `PUT /CreditNotes` (status `AUTHORISED`), then `PUT /CreditNotes/{id}/Allocations` | Two calls ⇒ partial state; retry between them leaves unallocated credit |
| Tax treatment | Read `/TaxRates` per org; map AU `OUTPUT` 10% / `EXEMPTOUTPUT` / `BASEXCLUDED` and NZ `OUTPUT2` 15% / `ZERORATED` / `NONE`; store mapping per org | Hard-coded codes break on custom rates and fail certification; wrong inclusive/exclusive overcharges GST by 10% |
| Multi-currency | Check `BaseCurrency` + `UseMulticurrency`; `PUT /Currencies` if needed; `BankAmount` on payments; log rate warnings | Posting a currency the org hasn't registered errors out; rate warnings ignored corrupt revenue |
| Webhooks | HTTPS endpoint, HMAC-SHA256 `x-xero-signature` over raw body, 2xx/401 within 5 s, queue then process idempotently | 24 h of failures disables the subscription; >31-day-old events are unrecoverable |
| Read-back / drift | Webhooks + nightly `If-Modified-Since` sweep (last 2 years for invoices) | `If-Modified-Since` misses DueDate/SentToContact and contact balance changes ⇒ silent drift |
| Connection lifecycle UI | Tenant name, status, Connect/Disconnect/Reconnect, `DELETE /connections/{id}` | Certification fails without it; orphaned connections consume the 5-connection allowance |
| 5-connection ceiling | Starter for pilot; plan Core upgrade at ~5 customers | The 5th customer is a hard stop; each org's 5-uncertified-app limit may block us even then |
| Certification | Checkpoints 1–8, App Store listing + subscriptions, multicurrency, rounding, `offline_access` | Scope creep or missing account mapping fails review; certification is a project, not a form |
| Demo company testing | Connect demo org; expect 28-day reset and reconnect | Tests that "passed" stop working after a reset; demo account codes differ from the customer's org |
| Operational visibility | Store `Xero-Correlation-Id` on every call; error page with Xero's message | Without correlation IDs, Xero support cannot investigate |

---

## 12. Questions that cannot be answered without Xero account access

These are the things no amount of public documentation resolves — they require a real app in the developer portal and/or a real organisation:

1. **Actual scope assignment for our app.** The docs say apps created on/after 2 March 2026 get granular scopes, but the portal is where you see which scopes are *offered and assignable* to this specific app (and whether `accounting.settings` is selectable or split further). Only visible at https://developer.xero.com/app/manage.
2. **Whether our redirect URI and app name pass validation** (https enforcement, "Xero" in the name, duplicate-name checks) — portal-side behaviour not fully documented.
3. **The exact webhook `Intent to receive` sequence** we will receive (how many posts, timing, whether any non-empty payloads appear during validation) — documented only in outline ("a series of HTTPS POST requests", up to 30 s).
4. **Which tax types actually exist in the pilot org**, their rates, names, `CanApplyToRevenue` flags, and any custom `TAX001` rates — `/TaxRates` per org. The default tables are per-country defaults, not guarantees.
5. **Which account codes, tracking categories, items and payment-enabled bank accounts exist in the pilot org** — and therefore whether our mapping assumptions hold. Also whether the org uses `UseMulticurrency` and what its base currency is.
6. **Whether the pilot org's admin can authorise an API connection** (role/permissions, partner-edition restrictions), and whether the org has already used its 5 uncertified-app slots.
7. **Real rate-limit headroom and 429 cadence for our call pattern** — the metrics tab (History → Metrics) requires a live app with traffic.
8. **Whether our app lands on Starter vs an existing higher tier**, and what Xero will charge (plan movement is portal/billing-side).
9. **Whether a Custom Connection pilot org actually has a purchased Custom Connection subscription** — portal shows orgs as "unavailable for connection" until then.
10. **The current certification queue, review turnaround, and whether our specific use case (membership billing + events) triggers extra checkpoints** — the docs say "Additional requirements may apply depending on the functionality of your app" without saying which.
11. **App Store commercial terms** (revenue share, referral/connection fees) — referenced by the docs but the numbers live behind the partner agreement, not the developer docs.
12. **How the demo company's reset interacts with webhook subscriptions** in practice (whether the subscription stays `OK` or requires re-validation) — not documented.

---

## Source index

Docs (page-data URLs shown because the rendered pages are JS-only; each `#` anchor below is the canonical human URL):

- OAuth overview — https://developer.xero.com/documentation/guides/oauth2/overview/
- Code flow — https://developer.xero.com/documentation/guides/oauth2/auth-flow/
- PKCE flow — https://developer.xero.com/documentation/guides/oauth2/pkce-flow/
- Custom Connections — https://developer.xero.com/documentation/guides/oauth2/custom-connections/
- Client credentials — https://developer.xero.com/documentation/guides/oauth2/client-credentials/
- Token types — https://developer.xero.com/documentation/guides/oauth2/token-types/
- Tenants — https://developer.xero.com/documentation/guides/oauth2/tenants/
- Scopes — https://developer.xero.com/documentation/guides/oauth2/scopes/
- OAuth limits — https://developer.xero.com/documentation/guides/oauth2/limits/
- Error handling — https://developer.xero.com/documentation/best-practices/user-experience/error-handling/
- Managing connections — https://developer.xero.com/documentation/best-practices/managing-connections/connections/
- Managing tokens and IDs — https://developer.xero.com/documentation/best-practices/data-integrity/managing-tokens/
- Idempotency — https://developer.xero.com/documentation/best-practices/data-integrity/idempotency/
- Contact mapping — https://developer.xero.com/documentation/best-practices/data-integrity/contacts/
- Creating invoices — https://developer.xero.com/documentation/best-practices/data-integrity/creating-invoices/
- Taxes — https://developer.xero.com/documentation/best-practices/data-integrity/taxes/
- Multicurrency — https://developer.xero.com/documentation/best-practices/data-integrity/multicurrency/
- Rate limits — https://developer.xero.com/documentation/best-practices/api-call-efficiencies/rate-limits/
- Paging — https://developer.xero.com/documentation/best-practices/api-call-efficiencies/paging/
- Filtering — https://developer.xero.com/documentation/best-practices/api-call-efficiencies/filtering/
- If-Modified-Since — https://developer.xero.com/documentation/best-practices/api-call-efficiencies/if-modified-since/
- Invoice status — https://developer.xero.com/documentation/best-practices/user-experience/invoice-status/
- Certification matrix — https://developer.xero.com/documentation/best-practices/overview/cert-matrix/
- Certification checkpoints — https://developer.xero.com/documentation/xero-app-store/app-partner-guides/certification-checkpoints/
- Webhooks overview — https://developer.xero.com/documentation/guides/webhooks/overview/
- Webhooks: invoices / contacts / credit notes / payments — https://developer.xero.com/documentation/guides/webhooks/invoices/ etc.
- Development accounts (demo company) — https://developer.xero.com/documentation/development-accounts/
- HTTP requests and responses — https://developer.xero.com/documentation/api/accounting/requests-and-responses/
- Accounting API types — https://developer.xero.com/documentation/api/accounting/types/
- Contacts / Invoices / Payments / CreditNotes / TaxRates / Items / Organisation — https://developer.xero.com/documentation/api/accounting/{contacts,invoices,payments,creditnotes,taxrates,items,organisation}/
- Granular scopes FAQ — https://developer.xero.com/faq/granular-scopes
- Pricing — https://developer.xero.com/pricing

Machine-readable / first-party code:

- OpenAPI (Accounting, v20.1.0) — https://github.com/XeroAPI/Xero-OpenAPI/blob/master/xero_accounting.yaml
- OpenAPI (Webhooks) — https://github.com/XeroAPI/Xero-OpenAPI/blob/master/xero-webhooks.yaml
- OIDC discovery — https://identity.xero.com/.well-known/openid-configuration
- Webhook receiver sample — https://github.com/XeroAPI/XeroWebhooksReceiver
- Custom Connection starter — https://github.com/XeroAPI/xero-node-custom-connections-starter
- Official Python SDK — https://github.com/XeroAPI/xero-python
