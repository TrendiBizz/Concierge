# What the carriers actually offer us for SMS (2026-11-15)

Question: we have a number with Hero; can we receive and send texts with no Android phone or SIM?
Answer, from their own site: **Hero can send, it cannot receive.**

## Hero Internet ([sms-gateway.html](https://www.hero.net.nz/sms-gateway.html), [rates.html](https://www.hero.net.nz/rates.html), [mobile-connect.html](https://www.hero.net.nz/mobile-connect.html))

- **SMS Gateway = outbound only.** Two ways to send: an **email-to-SMS gateway** and a **JSON API**.
  Their copy: *"an SMS gateway for customers who wish to send SMS messages either by using our email
  to SMS gateway or web service API."* Nothing about receiving.
- **Price:** `SMS Messages: 15c+GST per message` (≈17.25c), with *"On-net Hero Internet Messaging is
  FREE"*. That is cheap and NZ-local, and needs no hardware.
- **No two-way SMS on a DID.** Their phone-number pages talk about calls ("phone lines", "receive at
  one time"). There is no SMS-on-a-number product.
- **Mobile Connect explicitly leaves SMS where it is:** *"SMS stays on your handset… Keep your SIM.
  Keep your SMS."* That is a statement that Hero's cloud PBX does not take SMS off the handset — so a
  Hero DID cannot be our inbound SMS endpoint.
- Their **JSON API** ([hero-api.html](https://www.hero.net.nz/hero-api.html)) is voice-only: call
  setup and CDR billing.

Conclusion: Hero is a good **outbound** sender for a business that already has an account. It is not
an inbound path, so it cannot make Concierge an SMS receptionist on its own.

## What that leaves for inbound, with no hardware

A number has to be owned by somebody. The providers that sell a **two-way** number in NZ, with an
API both ways and no phone:

| Provider | Number cost | Inbound | Notes |
|---|---|---|---|
| Twilio | ~USD $1.15/mo (NZ) | webhook | transport already implemented here (`/api/v1/sms/{public_key}`); free trial credit, verified-recipient limits on trial |
| Voip.ms | ~USD $0.85/mo | SMS URL callback | cheapest two-way; needs a new adapter (small, same shape as smsgate) |
| Telnyx | ~USD $1/mo | webhook | needs a new adapter |

A completely free inbound path does not exist: inbound SMS terminates on a carrier-owned number, and
either we pay a small monthly rental or we run a handset with a SIM. That is the boundary, and it is
worth stating plainly rather than promising otherwise.

## The combination that is cheapest and needs no hardware

**Inbound:** one two-way number (Voip.ms ≈ $0.85/mo or Twilio ≈ $1.15/mo). **Outbound:** the same
number, or Hero at 15c+GST when the customer is on-net (free).

Nothing in the code is blocked on this choice — `sms.py` switches on `SMS_PROVIDER`, and
`scripts/vps/smsgate_check.py` now verifies either route (it grew a Twilio branch: env trio, webhook
probe, tenant grants) so the first live text is a config change, not a code change.
