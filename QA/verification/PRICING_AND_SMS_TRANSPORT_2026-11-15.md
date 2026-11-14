# Concierge price change, GST-inclusive copy, and what the inbound SMS path needs (2026-11-15)

## 1. Prices and the GST promise

Operator decision: Concierge is **USD $250 a month**, 3-month minimum, and **USD $3,000 a year,
10% off when paid in full = USD $2,700** (equivalent to USD $225/month, saving USD $300). SEO is
unchanged at USD $1,500/month with a USD $1,000 deposit. GST is no longer "added at checkout": the
published price includes it.

Changed on the live site (17 files) — `products.js` (plan data, `gstNote`) plus the hard-coded
cards and FAQ copy on /concierge, /pricing, /ai-receptionist, /ai-receptionist-cost,
/virtual-receptionist, /missed-call-text-back, /after-hours-answering, /ai-receptionist-*,
/concierge-start, /index, /seo.

**Second defect, found while doing it.** The price cards are hard-coded in the HTML while the plan
panel reads `products.js`, so changing one left the other stale: /concierge still said `$400` and
its yearly blurb read *"12 months at USD $250 is USD $4,800. Save USD $720 … equivalent to USD
$340 a month"* — three wrong numbers in one sentence. Fixed, and the arithmetic is now right:
12 × $250 = $3,000; pay in full, save $300, $2,700, which is $225/month.

**Guard.** `site_price_drift()` in `scripts/vps/healthcheck.py` compares the rendered cards with
the plan data and fails if "GST is added" returns to any of /pricing, /terms or /concierge. Live:
`counts: {"ok": 39, "warn": 1, "fail": 0}`. Tests: `api/tests/test_site_price_drift.py` (5).

## 2. The text that did not arrive

The paired phone (`trendi-oauth-staging`, `sms_transport=device`) polls for outbound work —
`last_seen` advanced 20:29 → 20:47 — but no inbound text has ever reached the API:

```
sms_devices.inbound_verified_at = (empty)
device_sms_inbound              = 0 rows
```

The server side is not the problem: `POST /api/v1/device-sms/inbound` answers
`401 {"detail":"Device authentication required"}` with a junk token, so the route, the gateway and
the auth layer all work. The phone app never calls it. Its source is not in this repo, so this
cannot be fixed here.

## 3. Could a test number process a text? Yes — but nothing is switched on

The platform has three SMS transports, and two of them take inbound webhooks that funnel into the
same reply path (`_sms_reply`: Grok answer, CRM capture, STOP/consent, reply send):

| Transport | Inbound webhook | Gate |
|---|---|---|
| `device` (paired phone) | `POST /api/v1/device-sms/inbound` | device bearer token |
| `twilio` | `POST /api/v1/sms/{public_key}` | `SMS_PROVIDER=twilio` + `TWILIO_AUTH_TOKEN`, X-Twilio-Signature |
| `smsgate` (self-hosted Android gateway) | `POST /api/v1/smsgate/{public_key}` | `SMS_PROVIDER=smsgate` + signing key |

Live state: `SMS_PROVIDER=none`; `TWILIO_ACCOUNT_SID / AUTH_TOKEN / FROM_NUMBER /
MESSAGING_SERVICE_SID` exist as empty keys; `SMSGATE_USERNAME` empty and no signing key. So both
webhooks answer **503 "SMS is not configured"** today, whatever number points at them.

Routing is ready: `PUBLIC_BASE_URL=https://chat.trendibizz.com`, and both webhook paths reach the
API there (`{"detail":"Unknown key"}` on a junk key — the expected pre-auth answer).

**To make a test number work** (pick one):
- **Twilio trial number** — set `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER`,
  `SMS_PROVIDER=twilio`, redeploy; set the Messaging webhook to
  `https://chat.trendibizz.com/api/v1/sms/<tenant public_key>`; grant the tenant `sms_read`.
  Trial accounts can only text verified numbers.
- **self-hosted Android gateway** (the phone we already have) — install `capcom6/android-sms-gateway`
  on it, set `SMS_PROVIDER=smsgate` with the signing key, point its `sms:received` webhook at
  `https://chat.trendibizz.com/api/v1/smsgate/<tenant public_key>`, grant `sms_read`. This is the
  one that also fixes customer replies from the real business number, because the handset itself
  receives the texts.
