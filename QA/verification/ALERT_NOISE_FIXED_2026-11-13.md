# Why you kept getting alert emails, and what now stops it

The operator asked how faults were "still occurring" after a full system check. Two things were true:
the last two FAIL mails (**18:05**, **18:10**) were sent **before** the 18:17 fix landed, and the
alerting itself had three defects of its own that kept producing mail that did not represent a fault.

## What was actually wrong with the alerting

**1. Every deploy paged as a failure.** The container check treated `Up 3 seconds (health: starting)`
as a FAIL, so each deploy made two emails: the false FAIL, then a "recovered" mail when it came back.
The 18:05 and 18:10 mails were exactly this — my own restarts.

Now: a critical container restarted within 10 minutes puts the whole run into **deploy grace** — it
reports, sends nothing, and does not touch alert state, because the "recovery" that follows a deploy
is not a recovery.

**Proof:**
```
$ docker restart trendi-api-1 && python3 scripts/vps/healthcheck.py
deploy grace: trendi-api-1 restarted within 10 minutes; not alerting
counts: {'ok': 38, 'warn': 2, 'fail': 0}
state unchanged: yes
```

**2. The SMS gap reminded forever about something only the phone app can fix.** `sms:inbound` means the
paired iPhone has never POSTed a text to the API. No reminder changes that. It is still reported in
status and counts, but it is **status-only** and never emailed.

**Proof:** `test_a_check_that_nobody_here_can_fix_is_never_emailed` — and it does not touch alert state.
A real problem (`inbound:chain`) still emails in the same test.

**3. Alert emails had no timestamp in the log.** Auditing "when did that mail go out" was impossible.
Every alert line now begins with its UTC time.

## The worse fault underneath: a broken checker went silent

While fixing the above I deployed a health check with a TypeError. It crashed on every run — and cron
only appends stderr to a log, so **alerting would have gone completely silent** and nothing would have
said so. That is the failure mode that matters: the checker is the thing that tells you when things
are broken.

**Fix:** `scripts/vps/watchdog.py`, installed at `*/10 * * * *`, deliberately separate and
dependency-free (it does not import the health check). If `status.json` has not been refreshed within
15 minutes it emails `[Concierge FAIL] health check has stopped running`.

**Proof, both directions:**
```
healthy:   watchdog: healthy (1 min since last check)                     exit=0
stale:     watchdog: STALE - would email: The health check has not completed for 87 minutes
           (expected every 5). Last check: 2026-11-13T04:00. Alerting may be silent.   exit=1
```

## State now

```
healthcheck:  39 ok · 1 warn (sms:inbound, status-only, never mailed) · 0 fail
alert state:  unchanged since 04:36 UTC — nothing has been mailed since the 18:17 fix
tests:        1042 passed
```

## The rule that would have caught this sooner

Every alert must name a condition the operator can act on, and a deploy must never generate one.
Status-only gaps are reported, not mailed; deploys are silent; a dead checker screams.
