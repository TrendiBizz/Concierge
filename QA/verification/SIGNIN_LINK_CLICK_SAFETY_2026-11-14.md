# What happens when a customer clicks our sign-in link

Re-tested on a fresh fictitious business, **ACME Ltd** (`acme`), owner `support@trendibizz.com`,
because a link that misbehaves costs the customer their trust on the very first click.

## The bug that mattered: a second click signed them out

`accept_invite` ran `DELETE FROM tenant_sessions WHERE user_id=$1` on every sign-in. So:

* they open the email on their phone, get in, start working;
* later they click the same email on the desktop, or the page reloads and the app redeems again —
* and the tab they were **working in** silently dies. `GET /owner/me` on the first session → **401**.

Reproduced on ACME before the fix:

```
click 1 → 200, session A, /owner/me(A) 200
click 2 → 200, session B, /owner/me(B) 200
                          /owner/me(A) 401   ← the tab they were using
```

**Fixed:** signing in no longer deletes their live sessions; only *expired* sessions are pruned.
After the fix, on the same tenant:

```
click 1 → 200   /owner/me(A) 200
click 2 → 200   /owner/me(B) 200
                /owner/me(A) 200   ← still signed in
```

## The refusals now tell the truth

Every refusal used to read *"This link has expired or has already been used"*, including when the
link was **clipped** — which is what mail clients do to long URLs, and what people do when they
paste. Sending them to ask for a new link (which gets clipped the same way) was the wrong advice.

| Case (all live, on ACME) | Response |
|---|---|
| Whole link, customer click | **200** |
| Same link again (refresh / second device) | **200**, other session untouched |
| Clipped link (25 chars) | **400** *"That link is not complete. Ask for a new one below and it will work."* |
| Random token | **400** same honest message |
| Empty body | **422** |
| Link past its date (backdated in the database) | **400** *"This link has expired."* |
| Link used beyond the 30-minute grace (backdated) | **400** *"This link has already been used."* |
| `/studio` with no fragment | **200**, page renders normally |

## Deploys must not eject a working customer

Sessions are database rows, not memory. Proved by redeploying the API mid-test:

```
before restart: /owner/me → 200
after  restart: /owner/me → 200
```

## ACME end to end

| Step | Result |
|---|---|
| Tenant created (`acme`), key `pk_rWTp9POGxbx4dD7A2rqi5RzX` | ok |
| Invitation email sent to support@trendibizz.com | **sent** |
| Delivered copy checked | no cladding, no web-person language, "have us do it for you" present |
| `widget-config` | **200**, name *ACME Ltd* |
| Hosted page `/demo/acme` | **200**, carries the key |
| `install-check` | `found: true` — "Your chat window is installed on this page." |
| Install request ("set it up for me") | **200**, appears in the operator queue |
| Live chat on the widget | **200**, `lead_captured: true`, sensible reply |
| Sessions after an API restart | **200** |

Tests: 1153. New: using a link twice does not sign the other tab out; a clipped link is not
reported as expired.
