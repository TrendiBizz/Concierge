# The alert emails, and the re-audit after the operator's fixes (2026-11-15)

## 1. Why the "health check failing" email arrived every hour

The mail carried `fail=1` and one failure: `inbound-chain | trendi-fictitious: consent`.

`trendi-fictitious` is *"Trendi Bizz (fictitious test business)"*, created 2026-11-14. It has a
reply address, so `inbound_readiness.check_all()` included it — and it can never pass, because the
`consent` link needs a real owner to authorise email read, and a fake business has no owner. The
hourly check therefore reported **one permanent failure among six healthy tenants**, and
`alert.sh` mailed it.

**Fix.** `tenants.is_test` marks a deliberate test business. Readiness still reports it (so the gap
stays visible) but a test tenant can no longer fail the chain or trigger an alert. Applied to the
live database; `trendi-fictitious.is_test = true`, all six real tenants `false`.

Proof (live, after deploy):
```
$ scripts/vps/check-inbound-chain.sh
OK   acme … OK concierge … OK pukeko-construction
TEST trendi-fictitious          blocked=consent      (test tenant: reported, not alerted on)
OK   trendi-meta-review … OK trendi-oauth-settings … OK trendi-support
0 of 7 tenant chain(s) broken        exit=0
$ healthcheck.sh  → {"ok": true, "counts": {"ok": 38, "warn": 1, "fail": 0}}
```

## 2. Two defects in the alerting path itself

**(a) The report file was not always JSON.** `healthcheck.sh` ended with
`exec python3 … 2>&1 | tee -a "$LOG"`, and cron ran `healthcheck.sh > /tmp/healthcheck.json 2>&1`.
Both merged the check's stderr into the report, so whenever the check printed a note
("deploy grace: … restarted within 10 minutes; not alerting") the file began with that line and
`json.load` failed. Fix: the wrapper keeps stderr on stderr, cron now writes
`2>/tmp/healthcheck.err`, and the crontab is recorded in `scripts/vps/crontab.txt`.
Proof: restarted the API to force the deploy-grace note, ran the cron line —
`stderr had: deploy grace: …; report parses as JSON: True`.

**(b) The mail could not say what failed.** `alert.sh` looked for a `checks` key; no report has
ever had one (the report has `failures`/`warnings`), so every mail said *"Failing checks: see
payload"* — the exact mail Jo received. Parsing, wording and "is this even JSON" now live in one
pure, tested place: `scripts/vps/alert_body.py`. Proof, dry run against the very payload that
produced the bad mail:
```
$ alert.sh --dry-run
Subject: ALERT: Concierge health check failing (inbound:chain)
Counts: ok=37, warn=1, fail=1
FAIL inbound:chain: trendi-support: consent
```
`--dry-run` also means the wording can be checked without sending mail.

**(c) The SMS warning is not a fault.** `sms:inbound` ("1 of 1 paired phone(s) have never
delivered a text in") is in `STATUS_ONLY_CHECKS` and is dropped before mailing — now guarded by
tests, so it can never be the reason a mail is sent. It clears when somebody texts the business
number from another phone (`sms_devices.inbound_verified_at` is set by the device's inbound POST).

Mutation proofs: healthcheck ignoring `is_test` → the test-tenant guard fails; readiness counting
test tenants as live → its guard fails; dropping the JSON-first parse → the polluted-payload guard
fails. All restored. Full suite **1223 passed**.

## 3. The four items Jo fixed — verified

| Item | Result |
|---|---|
| Stripe currency text | **Fixed.** "Monthly plan: USD $1,500/month … GST added for New Zealand customers only." The page shows $1,725.00 for a NZ buyer (1,500 + 15%). |
| Merchant name | **Fixed.** The deposit checkout now reads "Pay Trendibizz.com" (was `9429051967215`). |
| YouTube bio | **Fixed.** Reads "…Run a site check at trendibizz.com." — no "free". |
| CSP / Cloudflare | **Partly.** See below. |

## 4. Found while re-auditing — and fixed here

**The Concierge payment link is dead.** `products.js` pointed the monthly Concierge button at
`buy.stripe.com/fZu28s5Cv2URctqgHm04800`, which now answers *"The link is no longer active."* Every
visitor who chose Concierge reached a dead checkout. The file's own comment documents the intended
fallback — an empty link keeps the button as "Email to start" — so the link is emptied and the
page falls back honestly. Paste a replacement when the new link exists.

**Twenty stale Cloudflare JS-detection snippets were baked into our HTML** (`(function(){function
c(){var b=a.contentDocument…})()`, 20 copies over 12 pages). Cloudflare injects that script itself;
our copies were blocked by our own `script-src 'self' …` and logged a CSP violation on every load.
Removed from 12 pages: violations went **2 → 1 per page**.
The one that remains is injected **at the edge** — it is not in the origin HTML any more — so it
cannot be removed from this side: Cloudflare → Security → Settings → **JavaScript detections off**
(or a CF-managed nonce on the CSP). It is console noise only: emails, chat and menus all work.

## 5. Still open
- **A replacement Concierge payment link** (Stripe, with Trendibizz.com as the business name).
  Until then the Concierge button says "Email to start".
- **Cloudflare JavaScript detections** — turn off, or the last CSP violation stays.
- **One text to the business number** to clear `sms:inbound`.
