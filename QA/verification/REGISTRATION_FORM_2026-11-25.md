# Registration form (/concierge-start -> POST /api/enquiry) — 2026-11-25

Ask (Jo): "ensure the registration form is working for customers, test it".

## Live proof (production, browser-like UA)
- `/concierge-start` 200 text/html; `/concierge-start.js` 200 application/javascript.
- Bad email -> 400 "Enter an email address we can reply to."; bad website -> 400; `{}` / bad kind / extra field -> 422; honeypot `trap` -> 200 `{"ok":true,"id":null}`, nothing stored.
- One labelled submission ("TEST Registration - ignore", registration-test@example.com): 200, id 1d339dbd-a4ff-4530-856d-81235aee5c8d.
  - `site_enquiries` row present (status new, plan monthly, channels Calls).
  - CRM lead created (lead_id 687f2fe1-be32-438e-a347-490e0e6e5bbe) and `outbox` row 13559 owner_alert to admin@trendibizz.com: status sent, attempts 1, within ~15 s.
  - By design the visitor gets NO auto-reply (site_enquiry.py: "cannot be used to mail a stranger"); the page promises a reply within one business day by the operator.
- Test rows left in place (labelled TEST); no admin delete route exists. Status can be set to spam if wanted.

## Defect found
FastAPI answers schema failures (422) with `detail` as a list. Both form scripts showed `res.data.detail` raw, so a visitor would read "[object Object]" and, in main.js, lose the mail fallback. The real forms block these inputs (type=email, required), so reach is small (odd browsers, autofill quirks), but the fallback loss is real.

## Fix
`website/main.js` and `website/concierge-start.js` use the detail only when it is a string; otherwise generic text plus mail fallback.
Test: `test_a_schema_error_list_is_never_shown_as_text`. Mutation check: reverted main.js to raw detail -> test failed; restored -> passes.

## Not covered
Used/expired owner-link refusal after grace and the live 409 launch refusal on an empty account remain untested live.
