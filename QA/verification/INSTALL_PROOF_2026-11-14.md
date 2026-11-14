# A whole customer, end to end, on a fictitious business

A throwaway business was created for Trendi itself so the complete path could be walked in
production: create → sign-in email → install key → install check → a conversation → a lead in the
owner's CRM.

| Field | Value |
|---|---|
| Business | Trendi Bizz (fictitious test business) |
| Slug | `trendi-fictitious` |
| Owner | `support@trendibizz.com` |
| Install key | `pk_hgUihLyYXLuU7lGGlngFDkQX` |
| Snippet | `<script src="https://chat.trendibizz.com/widget.js" data-key="pk_hgUihLyYXLuU7lGGlngFDkQX" defer></script>` |
| Hosted page | https://chat.trendibizz.com/demo/trendi-fictitious |

## What each step returned

| Step | Result |
|---|---|
| `POST /admin/tenants` | created, key and snippet returned |
| Sign-in email to support@trendibizz.com | **sent**, attempts 1, no error; invite unused and valid 24 h |
| `GET /api/v1/widget-config?key=…` | **200** — name and greeting for this business |
| `GET /demo/trendi-fictitious` | **200**, page carries `widget.js` and this key |
| `install-check` on that page | `found:true, script:true, key:true` — "Your chat window is installed on this page." |
| Chat turn 1 ("Do you do kitchens?") | **200**, real answer; conversation stored with 2 messages |
| Chat turn 2 (name, email, phone) | **200**, `lead_captured:true` |
| `GET /owner/crm` as the owner | **200**, one lead: "Jo — support@trendibizz.com — Test visitor asking to book a quote" |

## Two things learned on the way

1. **The demo page lives on `chat.trendibizz.com`, not `concierge.trendibizz.com`.** A 404 on the
   concierge host is a wrong host, not a broken feature — the API answers 200 and the Studio builds
   the correct URL. Checked rather than assumed, because it looked like a defect for a minute.
2. **A chat with no contact details creates a conversation but no CRM lead** — by design: the lead
   appears only once the visitor leaves a name/email/phone. Worth knowing when a business says "I
   can see the chat but no enquiries".

## Left in place

The business is kept on purpose so the operator can sign in as support@trendibizz.com and see a
populated CRM. It is fictitious and does no outbound messaging. Delete it with
`DELETE /admin/tenants/trendi-fictitious` when it stops being useful.
