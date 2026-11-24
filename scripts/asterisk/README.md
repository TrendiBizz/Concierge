# Asterisk phone adapter for independent Concierge businesses

This adds a private AudioSocket service to the existing Concierge API code.
Each provisioned business receives a different private listener and its own
Gemini 3.8 Live session using its existing knowledge/tools. No Twilio SDK/account is used.

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
Gemini credentials (`GEMINI_API_KEY`). Enable PHONE_RECEPTIONIST_ENABLED and the specific business's
phone setting/telephone authorization. Register and enable its exact ingress
in phone_numbers only after the operator has verified the connection.

The PBX is built from `scripts/asterisk/Containerfile` and started by the repo's Asterisk scripts
(`scripts/asterisk/cutover_to_tenant.sh`); add any new one-off container step to a script there first.

The default Compose exposes no SIP or media ports. Connect the PBX to the
verified provider network using an explicit deployment override. If internet
SIP is required, configure the provider's actual TLS/authentication/RTP/NAT
settings and firewall; the sample IP-matched UDP endpoint is not a complete
internet SIP deployment. Never expose AudioSocket, ARI or the database publicly.
The private PBX IP is fixed and the bridge accepts only that peer. Ensure the
chosen private subnet doesn't overlap the deployment's other networks.

Without a container, run `PYTHONPATH=api python -m app.asterisk_bridge`; default bind
and allowed peers are loopback. One process owns these ports, not HTTP workers.

## Media server — take-over, listen-in, whisper (AMI)

The PBX is the only place that owns the caller's media, so call *control* lives here. A scoped
Asterisk Manager Interface user is generated into `generated/manager.conf` and mounted into the
PBX; the listener is **never published to the host** and is reachable only over the private
application network, where the API talks to it at `AMI_HOST=pbx`, `AMI_PORT=5038`.

```
python3 scripts/asterisk/render_routes.py <routes.json> scripts/asterisk/generated bridge \
        <public-ip> --manager-secret-file <file-with-32-byte-secret>
chown 100:101 scripts/asterisk/generated/manager.conf   # the asterisk user in the image
chmod 640 scripts/asterisk/generated/manager.conf
```

The AMI user is limited to `read = call,reporting` and `write = call,originate`: enough to list
channels, read/set a channel variable, redirect a call and originate a supervisor leg — and not
enough to run CLI commands or change configuration.

What the API does with it (`api/app/call_control.py`):

| Mode | AMI action | Effect for the caller |
|---|---|---|
| take-over | `Setvar CONCIERGE_TRANSFER` + `Redirect` to `business-<slug>-takeover` | The assistant is cut off and the owner's phone rings through the same trunk; the caller is bridged to the human. Nobody answers in 30 s? The caller falls back into the assistant. |
| listen | `Originate … ChanSpy(<channel>,qr)` | The owner hears the live call; the caller hears nothing and is not told a supervisor joined. |
| whisper | `… ChanSpy(<channel>,qw)` | The owner is audible to the caller only — coaching the caller without the assistant hearing. |
| join | `… ChanSpy(<channel>,qB)` | The owner barges in as a third party. |

The console sees this per call (`/owner/live-calls`): `engine` is `asterisk` for the carrier line,
and `media_control` states which of the four controls are real for that call.

Ops gotchas learned the hard way:

- **Bring this stack up with both compose files** (`-f compose.yml -f compose.public.yml`). With
  only `compose.yml`, Compose treats the `phone` network as disposable and tries to remove it
  while the bridge and the internal voice shell are still attached; the PBX ends up disconnected.
- The PBX is on both `phone` (media, internal) and the application network (AMI). It is still not
  host-published, so nothing about the SIP exposure changes.
- `ChanSpy` needs `app_chanspy.so`, which the Debian/Ubuntu `asterisk` package loads by default.
  Verify with `asterisk -rx "module show like chanspy"`.

## Rust telephone shell (live container; Python bridge is the fallback)

The `shell` service in `scripts/vps/compose.yml` runs `asterisk_shell` (`concierge-stack/core-rs`) at
172.30.91.3 on the phone network. It owns the AudioSocket listeners, 20 ms pacing and the Gemini Live websocket; the
database, permissions, recordings, CRM and tools stay in Python, reached over `/internal/voice/*`
(`api/app/voice_internal.py`). The Python bridge keeps running at .4 the whole time. Which one answers calls is
decided by one thing only: the host in the dialplan's `AudioSocket(...)` line.

Switch a line to the Rust shell, on the VPS as root (changes only `generated/extensions.conf` and reloads the
dialplan; no restart, no data change; refuses if a call is in progress):

```
bash scripts/asterisk/cutover_to_rust_shell.sh
```

Undo (restores the backup the apply printed, reloads the dialplan; the Python bridge is still running):

```
bash scripts/asterisk/cutover_to_rust_shell.sh --rollback /opt/trendi/backups/rust-shell-cutover-<timestamp>
```

After switching, place one call and check: the greeting, audio both ways, a transcript in the CRM, recording only after
explicit consent, `end_call`, and the owner SMS queued once.

Proof that the shell and the real Python API agree: `QA/verification/asterisk_rust_shell_integration.py` runs the
compiled shell against the real FastAPI app and a real PostgreSQL database with a fake Gemini Live server and fake callers
(see its docstring for how to run it).

## Behavior

- Standard AudioSocket PCM16 little-endian mono 8kHz is upsampled to 16kHz for Gemini Live
  and 24kHz Gemini Live audio is downsampled to 8kHz for Asterisk. No separate STT or TTS service.
- Call UUID replay is rejected globally. Limits and owner consent are checked
  per business; telephone authorization is rechecked during the call.
- Incoming transcript and tool operations use the route's fixed business ID.
- Saved caller messages update that business's CRM enquiry and queue an
  operational owner SMS to its saved owner_number exactly once on finalization.
- Delivery uses the existing outbox worker and configured business SMS
  transport. Queued is not delivered. The adapter does not create SIM access.
- The Gemini Live receptionist asks recording permission before enabling capture. With business recording
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
fixture database; the live script uses actual Asterisk and Gemini Live but synthetic
speech. They never run a send worker, make a PSTN call or send a real message.
A genuine forwarded mobile call and delivery receipt are separate activation
gates. An Asterisk container does not itself provide a publicly dialable number.

## AI-link failover voicemail (N3, off by default)

If the AI voice link fails while the caller is still on the line, the dialplan can fall back to the
owner's ring number (when `ring_owner` is set) and then a recorded voicemail. Enable it by rendering with
`--voicemail-dir /var/spool/concierge-voicemail`, mounting that directory into both the PBX and the API,
setting `VOICEMAIL_SPOOL_DIR` for the API, and installing a short generic `concierge-voicemail-greeting`
sound ("we can't take your call right now; leave your name, number and message after the tone; it will
be recorded"). The API sweep (`app/voicemail_fallback.py`) turns each file into a CRM enquiry, stores the
recording and alerts the owner through the paired phone. Not enabled in production: needs the mount and greeting recording.
