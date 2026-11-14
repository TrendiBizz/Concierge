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

## 4. Collision with the 09:48 Workwatch deploy (recorded so it is not repeated)

At 09:48 NZDT a Workwatch session deployed the same site with **USD $2,550 a year / "15% off"**,
then committed only `website/site-i18n.json` (`8ccbd26`). Jo's later instruction supersedes that:
**$3,000 a year, 10% off when paid in full = $2,700**. Two agents editing the same live tree is
how a wrong price reaches customers, so the sequence is written down here:

1. Pulled the live tree again (to keep the bot's i18n cleanup) instead of pushing my older copy.
2. Re-applied the operator's figures to that tree, including the yearly blurb.
3. Deployed, then verified the rendered pages: `/concierge` shows `USD $250`, `$2,700`,
   "10% off when paid in full", "including GST"; `/pricing` shows `$1,500` and `$1,000`.
4. Copied the changed files back into `website/` and rebased on `8ccbd26` → `e8b036d`.

Live `products.js` now reads `monthly: { price: 250 }`, `yearly: { price: 2700 }`,
`gstNote: "All prices are quoted in USD and include GST."`

Full suite: **1227 passed**.

## 5. The free solution for inbound *and* outbound SMS (built here, waiting on one phone)

The operator asked for a free way to receive texts from anywhere and reply, and refused the
"not possible" answer — correctly, because it is possible. `scripts/vps/SMS_FREE_GATEWAY.md` is
the setup guide; `scripts/vps/smsgate_check.py` is the readiness proof.

The transport already existed (`SMS_PROVIDER=smsgate`, `POST /api/v1/smsgate/{public_key}`,
HMAC-signed, open-source [android-sms-gateway](https://github.com/capcom6/android-sms-gateway) on
an Android phone). What was missing was (a) anyone being told it solves the problem for $0, and
(b) a way to see *which* of the four moving parts is missing without a live text. That is what the
checker does — it reads `api.env`, probes the gateway's send endpoint, probes our webhook's
signature gate, and names every gap:

```
$ python3 scripts/vps/smsgate_check.py
provider          : (unset)
webhook bad sig   : https://chat.trendibizz.com/api/v1/smsgate/probe-key -> 403
  MISSING  SMS_PROVIDER is 'unset', must be 'smsgate'
  MISSING  SMSGATE_BASE_URL is empty … (4 more)
```

**Cost reality, stated plainly:** the app and integration are $0, receiving is $0 on any NZ plan,
sending costs whatever that SIM's plan charges (free on unlimited-text plans, a few cents on
prepaid), and no per-message API is in the path. It cannot be both free and high-volume, and it
cannot use an alphanumeric sender — the number *is* the identity.

**Guard.** `api/tests/test_smsgate_check.py` pins the checker's signature against the API's own
validator, so the two can never drift into "every real text gets 403". Mutation: reversing the
concatenation order in the checker (`timestamp + body`) turns the suite red; restored → 4 passed.

**Harness defect found while running that mutation.** The first restore appeared to fail — the
test stayed red after the file was put back. Cause: `spec_from_file_location` writes bytecode next
to the script, and the restored file had the same size and an mtime inside the same second, so the
**.pyc stayed valid and the mutated code kept running**. `rm -rf scripts/vps/__pycache__` cleared
it. Anyone mutating a script that is imported by path must clear that cache before trusting a
green result; otherwise a restore looks like a fix that did not work.
