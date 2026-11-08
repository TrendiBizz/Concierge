# Paired Mac phone continuation — 9 November 2026

This supersedes the **phone deployment, pairing and synthetic-audio** state in
`SESSION_HANDOFF_2026-11-09_PROVIDER_ACTIVATION_VOICE_X.md`. It does not supersede
that file's provider or concurrent Meta-review updates. No new paid service,
driver, carrier route, forwarding change or social publication was performed by
this phone continuation. Preserve all existing data and unrelated changes.

## Deployed and paired

- Existing checkout reused: `/Users/jo/work-staging/concierge-integration`.
- Live API is now `trendi-concierge-api:vps`, image
  `sha256:6b6d05b68df41f6e85f8a14f28f1611a53c7c0714087700ca063ecf7ed6693d7`.
  Its `device_sms.py` SHA256 matched local source before deployment:
  `f61fe8261bee02edb03e437eaccb8abd8b8b737d371e39383a54897f618d0664`.
- Rollback tag `trendi-concierge-api:pre-phone` retains the prior
  `f110b463b95b9a5c2e2de43ce56e90bdd0035112c22ca75a16e70408ca5ec148` image.
  API, social (shared API network namespace) and gateway were deliberately
  recreated. Caddy validation passed. Eleven production containers remained
  running; API, CRM and PostgreSQL health checks passed.
- Public `/owner-ui` serves the phone controls. Unauthenticated device polling
  returns 401. Existing social image is unchanged; loaded
  `SOCIAL_ENABLE_PUBLISH=false` was verified. Restricted Meta review timer remains
  active and separate from global delivery.
- Only `trendi-oauth-staging` was paired. Existing `sms_read` and `sms_send`
  authorization records were checked before provisioning. Its SMS fields are
  now `sms_enabled=true`, `sms_transport=device`, `sms_from=+64278817368`.
  Before pairing they were false / empty / empty. Campaigns remain disabled.
- One enabled tenant-scoped device exists; PostgreSQL stores only its token hash.
  Private configuration is `/Users/jo/.config/trendi-phone/config.json` (600),
  parent directory 700. Never display its token or commit it.
- LaunchAgent `/Users/jo/Library/LaunchAgents/com.trendi.phone-connector.plist`
  runs the existing signed `/Users/jo/Applications/Trendi Phone Connector.app`.
  Its durable journal is `~/.config/trendi-phone/state/device.sqlite` (600).
  Logs contain status/error class only, without bodies, recipients or credentials.
- Cloudflare rejected the default `Python-urllib` header with 403 / 1010 before
  API arrival. An otherwise identical authenticated poll using the truthful
  `TrendiPhoneConnector/1.0` header returned 200 with no job. The companion now
  sends that header; no Cloudflare security setting was weakened.
- Rebuilding the app for that fix invalidated its earlier ad-hoc Full Disk
  Access identity. A real background probe failed; the UI later showed its
  access toggle on, and a new launchd probe returned
  `PASS background phone connector receipt access`. Normal connector heartbeats
  are now current. **Do not ask for Full Disk Access again unless a fresh probe
  actually fails. Avoid rebuilding this app unless source changes require it.**

## Actual SMS evidence — still unverified

Exactly one connection test was queued after a current background heartbeat:

- Job `e92b54cb-86a5-4f79-9f06-577726f60037`.
- To the paired owner's own Spark number, +64 27 881 7368.
- Exact body: `Trendi Concierge SMS connection test. No reply needed.`
- Stable request key: `phone-test:20261109-first-live`.
- Final server and Mac journal status: **failed**; empty receipt; journal acked.
- Read-only Messages query found **zero** outgoing rows with this exact recipient
  and body. No successful send or carrier delivery is claimed. The helper's
  exact failure reason was not retained, so cancellation versus timeout is not
  established. Native human Send confirmation was preserved throughout.
- `verified_at` and `inbound_verified_at` remain NULL. No device inbound SMS is
  recorded. No historical outbox SMS existed at activation (only three sent
  emails); old texts were not imported or replayed.

**Do not replay this failed job.** A fresh controlled test needs the owner's
availability for the native confirmation. A second phone controlled by the owner
must send a new business enquiry to the Spark number to prove inbound delivery,
Grok/CRM handling and a separately confirmed reply. Self-messages are excluded
from inbound processing to prevent loops. There is no real incoming SMS or
carrier-delivered Grok reply evidence yet. UI readiness intentionally requires
both actual send and receive verification.

## Free call route — synthetic runtime probe passed

Source: `native-audio-tap-probe.swift`; measurements:
`native-audio-tap-probe-20261109.jsonl`. Built local test bundle:
`/Users/jo/Applications/Trendi Audio Probe.app`.

The probe created a tap containing only its dedicated tone-generator child and
exposed it through a temporary public aggregate device. A separate reader
process resolved that device by UID and read its input. HAL object IDs are
client-local and must not be passed directly between processes.

- 997 Hz generated tone, low amplitude; 48,000 Hz input.
- 289,280 reader frames; RMS 0.0028000793; peak 0.0043727853;
  5,930 positive crossings; synthetic-signal check passed.
- Public aggregate input had two channels. The included speaker-only subdevice
  had **zero physical microphone input channels**. No microphone or other
  application was tapped; no audio recording was saved.
- `mutedWhenTapped` was used. `TapAutoStart` was absent because Apple restricts
  that option to private aggregates.
- Aggregate destruction status 0, tap destruction status 0, all three audio
  defaults equal before/after. No temporary audio device remains from this test.
- Native CUA `getApp('com.apple.mobilephone')` again timed out. No alternative
  UI technology was used. Phone's acceptance/selection of the public input,
  actual Continuity caller-audio process capture, echo behavior, answer/hangup,
  and two-way cellular Grok audio remain **unproven**.

This is runtime proof of an isolated local audio path, not carrier integration.
Do not enable all-call handling or mark telephone ready. Live settings remain
`PHONE_RECEPTIONIST_ENABLED=false`, `PHONE_VOICE_PROVIDER=grok`, no verified phone
tenants and zero enabled `phone_numbers` rows. No SIP route has been purchased
or configured.

Apple reference: https://developer.apple.com/documentation/coreaudio/capturing-system-audio-with-core-audio-taps
and installed Core Audio SDK headers. The Apple documentation JSON was read to
verify capture permission disclosure and tap/aggregate behavior.

## Validation and recovery

- Previously completed candidate validation: 85 API unit tests and 38 disposable
  PostgreSQL/API checks. No API code changed after that candidate was built.
- Mac companion: **7 tests pass**, including a new failing-then-passing regression
  test for the client identity header. Receipt isolation, history/SIM/iMessage
  exclusions, authentication-message exclusions and crash non-replay tests pass.
- Swift compilation, owner JavaScript syntax and `git diff --check` pass.
- Existing encrypted VPS backup succeeded before deployment.
- Private `/opt/trendi/shared/mac-phone-recovery.tar.gz` contains the scoped
  config, a consistent SQLite send-journal backup, signed app and LaunchAgent.
  It contains **no Messages database**. Keep it root-only and include it in the
  existing encrypted backup. Restoring a journal must never replay failed,
  claimed, started or uncertain sends.
- To stop only the Mac companion:
  `launchctl bootout gui/$(id -u)/com.trendi.phone-connector`.
  Stop the LaunchAgent before rolling back to the old API. Preserve all device
  and job tables; disable the paired device and restore only the canonical
  tenant's former SMS settings rather than deleting evidence. Recreate API and
  social together when rolling images back because they share a network namespace.

## External approval/evidence blocks

| Area | What is proven | Remaining block |
| --- | --- | --- |
| Spark SMS | Deployed device API, private pairing, live heartbeat, native confirmation gate, negative self-test receipt | A confirmed actual send plus controlled incoming SMS/Grok reply; no automatic replay |
| Spark calls / Grok | Synthetic public audio input works across processes; defaults preserved | Phone selection, real caller-audio capture, two-way Grok cellular call, answer/hangup |
| Meta | Own-account publishing evidence is in the main handoff; restricted review worker separate from global delivery | Genuine adequate end-to-end recording and processor-country validation; draft not submitted |
| Google Business Profile | Application submitted, case 7-0643000042292 | Provider allowlisting/quota, still zero at prior verification |
| LinkedIn Pages | Application 266706827 submitted | Development Tier approval and actual organization grant |
| LinkedIn profile | Existing connection preserved | Actual w_member_social grant and authorized publish evidence |
| TikTok | Login Kit review retained | Content Posting permission/audit absent |
| X | Deployed official adapter/configuration | Account OAuth connection and live test; last recorded balance $0; no purchase authorized |
| Support mailbox | No mailbox/MX change made | support@trendibizz.com setup and eligible Google branding identity |

Provider rows carry forward the prior verified state; this phone continuation
did not re-submit applications, buy credits or publish social posts. Concurrent
Meta work may have newer finite publishing/evidence updates in the main handoff;
preserve those and never infer a new publishing authorization from this file.
