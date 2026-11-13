# SMS, tested live with the real number (13 Nov 2026, 17:44 NZ)

The operator asked for the number to be used rather than reasoned about. It was.

## Sending: proven, right now

```
outbox id 1252 -> to +64278817368, status "sent", attempts 1
queued 04:44:05 UTC  ->  sent 04:44:16 UTC  (11 seconds)
body: "Trendi delivery test 04:44 UTC. Please ignore."
```

The paired phone collected the job (its `last_seen` advanced to 04:44:27) and the message arrived on
the handset at 17:44 NZ — confirmed by the operator's own Messages screenshot, which also shows the
earlier 13:44 alert arriving. **Sending works end to end, today, on this number.**

## Receiving: still nothing, and now we know why

```
device_sms_inbound rows: 0
sms_devices.inbound_verified_at: null
conversations with channel='sms': none, ever
```

The same screenshot shows the phone **receiving** SMS — the test message appears in the thread as a
delivered message. So the handset gets texts, and the platform still sees none. That is the finding:
**the paired-phone side is not forwarding inbound messages to the API at all.** It is not an
authorisation rejection (the tenant holds `sms_read` and `sms_send`, both granted 7 Nov) and it is not
a server fault (the route is covered by 49 passing tests). Nothing is being sent from the phone to
`/api/v1/device-sms/inbound`.

The phone app is not in this repository — it is the external paired-phone client — so the next move is
to check the app's configuration for inbound forwarding. That is a concrete, attributable gap rather
than a shrug.

## Proof hygiene learned here

Two of my own healthcheck defects surfaced while doing this, both fixed:

* a warning-only alert was labelled `[Concierge FAIL]`, which reads as an outage (bug 43);
* running the check by hand rewrote alert state and produced spurious "NEW PROBLEMS"/"RECOVERED"
  mails (bug 44). `--no-alert` now makes a manual run side-effect free — proven by running it and
  confirming the state file's mtime did not change.
