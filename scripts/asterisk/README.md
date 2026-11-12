# Asterisk phone adapter for independent Concierge businesses

This adds a private AudioSocket service to the existing Concierge API code.
Each provisioned business receives a different private listener and its own
Grok session using its existing knowledge/tools. No Twilio SDK/account is used.

## Configuration

Create an operator-owned route JSON based on `routes.example.json`. `number`
is the actual verified SIP ingress destination, which can differ from the
business's public mobile number. `source_cidr` is the verified carrier/PBX SIP
source. Use separate exact destinations for separate businesses; shared trunks
are routed by trusted source and exact destination. Unknown calls are rejected.

**Registration trunks.** A carrier that authenticates a line by number and
password (Hero Internet, and most residential/small-business VoIP lines)
registers instead of exposing a fixed signalling network. Use the object form:

```json
{
  "routes": [{"tenant": "example-business", "number": "+6492431347", "port": 9510}],
  "trunk":  {"server": "sip.hero.co.nz", "username": "092431347",
             "password": "<line password>", "transport": "udp", "port": 5060}
}
```

The renderer emits a `registration`/`auth`/`aor`/`endpoint`/`identify` set and
pins `match=<server>`, so the registrar is the only accepted source. A trunk
with exactly **one** route also accepts any dialled form (`+64…`, `0…`, `64…`)
on its own authenticated line, because carriers differ in what they put in the
Request-URI; with two or more routes only the exact DID entries map, and
anything else hangs up. Only UDP registration is rendered — TLS needs
certificates this script does not place.

```
python3 scripts/asterisk/render_routes.py /private/business-routes.json scripts/asterisk/generated bridge 152.42.239.240
```

The routes file contains the line password: keep it `0600` outside the repo
(e.g. `/opt/trendi/shared/asterisk-routes.json`). Verify the registration with
`asterisk -rx "pjsip show registrations"` — it must say `Registered` — before
creating any `phone_numbers` row.

Set `ASTERISK_ROUTES` to the same rows without `source_cidr` (tenant, number,
port), `CONCIERGE_API_IMAGE`, `CONCIERGE_ENV_FILE` and `CONCIERGE_NETWORK`.
The environment file is the existing private API environment with database and
Grok credentials. Enable PHONE_RECEPTIONIST_ENABLED and the specific business's
phone setting/telephone authorization. Register and enable its exact ingress
in phone_numbers only after the operator has verified the connection.

```
docker compose -f scripts/asterisk/compose.yml up -d --build
```

The default Compose exposes no SIP or media ports. Connect the PBX to the
verified provider network using an explicit deployment override. If internet
SIP is required, configure the provider's actual TLS/authentication/RTP/NAT
settings and firewall; the sample IP-matched UDP endpoint is not a complete
internet SIP deployment. Never expose AudioSocket, ARI or the database publicly.
The private PBX IP is fixed and the bridge accepts only that peer. Ensure the
chosen private subnet doesn't overlap the deployment's other networks.

Without Docker, run `PYTHONPATH=api python -m app.asterisk_bridge`; default bind
and allowed peers are loopback. One process owns these ports, not HTTP workers.

## Behavior

- Standard AudioSocket PCM16 little-endian mono 8kHz is sent directly to Grok
  using its supported 8kHz PCM format. No separate STT or TTS service.
- Call UUID replay is rejected globally. Limits and owner consent are checked
  per business; telephone authorization is rechecked during the call.
- Incoming transcript and tool operations use the route's fixed business ID.
- Saved caller messages update that business's CRM enquiry and queue an
  operational owner SMS to its saved owner_number exactly once on finalization.
- Delivery uses the existing outbox worker and configured business SMS
  transport. Queued is not delivered. The adapter does not create SIM access.
- Grok asks recording permission before enabling capture. With business recording
  authorization and an explicit caller yes, actual received/played audio is mixed
  into bounded mono 8kHz WAV and attached to the same CRM enquiry. Withdrawal
  discards captured audio. No pre-consent audio is retained.
- Caller-requested text or recording copies use the existing consented-contact,
  readback/confirmation and private expiring-link path. Delivery is queued after
  saving the call; a queue result never means sent. No automatic callback or
  arbitrary carrier voicemail deposit is implemented.
- Caller ID is not transported by the AudioSocket UUID protocol. The agent
  asks for callback details; it never invents a caller number.
- Closing AudioSocket hangs up its dialplan leg. Failed/disconnected calls
  retain their partial transcript and a status for reconciliation.

## Verification

Unit/regression: `PYTHONPATH=api python -m pytest api/tests/test_asterisk_bridge.py -q`.
The QA scripts under `QA/verification/asterisk_*integration.py` use a disposable
fixture database; the live script uses actual Asterisk and Grok but synthetic
speech. They never run a send worker, make a PSTN call or send a real message.
A genuine forwarded mobile call and delivery receipt are separate activation
gates. An Asterisk container does not itself provide a publicly dialable number.
