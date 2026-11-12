# Voice supervision and take-over — what the Octovox console actually needs, and whether Concierge should build it

2026-11-12 NZ. Operator question: *"Octovox sells a console we can't copy without building a media
server, which is exactly the bloat you ruled out — what has Astryx or GitHub got that fulfils this,
and how do we build and integrate it with Concierge if there is legitimate value?"*

Method: primary-source reads only — the xAI SIP/realtime docs and REST reference, Asterisk 20/22
docs, GitHub LICENSE files, and the Concierge tree as it stands at `30389a4`. Every claim about the
current code was checked against the tree. Nothing was deployed, no live call was made, and no
provider request that costs money was sent.

---

## 0. The finding that changes the plan

**xAI does support SIP transfer, and the shipped "no transfer" claim is wrong.**

`POST https://api.x.ai/v1/realtime/calls/{call_id}/refer` takes `{"target_uri": "tel:+64…"}` or
`sip:user@host`, and is documented as a real SIP REFER that **blocks until the destination answers**:

| Status | Meaning |
|---|---|
| `200` `{}` | Transfer completed — the REFER succeeded **and** the destination answered (not just ringing) |
| `400` | `target_uri` is not a `tel:` or `sip:` URI |
| `404` | No SIP participant on this call |
| `502` | Rejected downstream; body carries the carrier's SIP code (e.g. `SIP 403 Forbidden`) |
| `504` | Transfer timed out |
| `500` | Internal error |

On a failed transfer ("the same realtime session stays connected … the caller remains on the call,
and the agent can keep talking"), so the fallback path is free. That is precisely the capability
`api/app/live_calls.py` was written believing did not exist.

The full call-control surface is exactly two actions: **`refer`** and **`hangup`**. There is no
listen-in, no conference, no mute, and no server→client caller-audio event. So:

- **Real take-over to a human: buildable today, no new infrastructure.**
- **Live audio listen-in / whisper / three-way: still not buildable on the Grok SIP path** — that part
  of the earlier scoping was right, for a different reason (the API simply has no primitive).

Sources: [SIP phone calls](https://docs.x.ai/developers/model-capabilities/audio/speech-to-speech/sip)
(call control + FAQ on transfer outcomes), [Voice REST reference](https://docs.x.ai/developers/rest-api-reference/inference/voice)
(`POST /v1/realtime/calls/{call_id}/refer`). Note the docs explicitly say there is **no separate
WebSocket transfer event** — the HTTP response is the outcome.

---

## 1. "The console" is four capabilities, not one

Octovox's Switchboard is a supervised-mode UI over four separable things. They have wildly
different costs, and only one of them is worth money to a Concierge customer:

| # | Capability | What it really is | Cost to add | Verdict |
|---|---|---|---|---|
| 1 | See calls in progress, live transcript, who is calling | read the rows the API already writes | **already shipped** | keep |
| 2 | **Take over and talk to the caller now** | a SIP REFER from the provider to a human number | **one endpoint, ~2–4 days** | **build** |
| 3 | Listen in silently / whisper / barge in | a media path you own (Asterisk) or a CPaaS conference + audio stream | weeks + a carrier + a new media/WebRTC surface | **do not build** |
| 4 | Supervise many calls at once (queue, sentiment per call, agent roster) | a call-centre product | months | **not this product** |

Concierge sells to a one-to-three-person trade business. There is no supervisor sitting behind the
owner, and no roster of agents. Capabilities 3 and 4 are Octovox's channel/call-centre business
(they sell channel-only, *"We don't sell direct. You do."*). Copying them is the bloat trap.

> **Update, 2026-11-12 (later the same day).** Row 3 was built anyway, on the Asterisk path only,
> because that path already existed and needed no new media product: `ChanSpy qr/qw/qB` gives
> listen-in, whisper and barge over the carrier DID's own trunk. What sank the "weeks + a new
> media/WebRTC surface" estimate was that the PBX was already in the media path — the missing piece
> was AMI, not audio. See `HANDOFF_CURRENT_2026-11-11.md` (fourteenth section) and
> `scripts/asterisk/README.md`. Row 3 remains **not** available on Grok SIP calls, and the
> browser softphone (WSS/DTLS/ICE + JsSIP) is still a separate project. Row 4 is still not built.

---

## 2. What each voice path can actually do

Concierge has two voice paths in the tree. They are not interchangeable.

| | **Grok SIP** (`phone_sip.py`, the path the docs call live) | **Asterisk + AudioSocket** (`asterisk_bridge.py`, parked) |
|---|---|---|
| Media lives at | xAI | our Asterisk container |
| Live transcript | yes (WebSocket events, already stored) | yes (bridge callbacks, already stored) |
| Caller ID | yes (`From` header on the incoming webhook) | **no** — AudioSocket carries only a UUID; the agent asks for a callback number |
| Transfer | **`refer` → `tel:`/`sip:`** | AMI `Redirect` on the caller channel (needs AMI enabled; the stack currently has no AMI/ARI) |
| Listen / whisper / barge | **no primitive** | `ChanSpy` built in (`w` whisper, `W` private whisper, `B` barge) |
| Conference | no — only by REFER'ing the caller into a conference URI you control | `ConfBridge` built in |
| Extra dependency | none | a carrier trunk with an outbound leg (or a SIP/WebRTC endpoint to the owner) |

Two facts worth recording from the Asterisk research because they will bite anyone who tries the
"obvious" implementation:

- **ARI `redirect` does not work here.** It requires the channel to be in a Stasis application and
  returns `409` otherwise. `AudioSocket()` is a dialplan application, not Stasis. The correct
  primitive is **AMI `Redirect`** (or `ChannelRedirect`/`BlindTransfer`), which has no such
  precondition.
- The dialplan already `Answer()`s before `AudioSocket()`, so a redirect to a context that
  `Dial()`s the owner does not need an answer step — but the generated dialplan never sets
  `${CALLERID}` into a channel variable, so a transfer context cannot currently know who it is
  transferring. Small dialplan change, not an architecture change.

---

## 3. What Astryx gives: nothing telephony, and it does not need to

`@astryxdesign/*` is a **React design system**. The installed packages are `core` and
`theme-neutral` (plus the CLI); there is no audio, media, telephony, or WebRTC package, and the
component index has no audio-player or waveform component. `@astryxdesign/native` is still a
placeholder (`0.0.0-bootstrap.0`).

So Astryx contributes the *console UI* and nothing else. For this feature the useful pieces are ones
already in the bundle: **Dialog** (confirm + show the caller/transcript before transferring),
**Toast/Banner** (transfer failed, falling back to ring-back), **Badge** (call state), **TabList**
(if the live panel ever becomes its own screen). No new Astryx adoption is required.

The browser softphone question (capability 3) would need **JsSIP** (MIT, 3.13.9, released
2026-10-20) or SIP.js (MIT but dormant since 2022-10). That is a WebRTC build, not a UI component —
and it is not needed for the REFER design.

---

## 4. What GitHub gives: the truth is "nothing you should adopt"

This was checked against LICENSE files and current releases, not blog posts.

| Option | Licence | What it adds | New media server? | Verdict |
|---|---|---|---|---|
| **xAI `refer`** (not GitHub — the provider) | — | real blind transfer of a live call to the owner's phone | **no** | **adopt** |
| **Asterisk** (already installed) | GPLv2 | AMI `Redirect`, `ChanSpy`, `ConfBridge`, WebRTC over WSS | no — it *is* the PBX we run | the only route to listen-in, on trigger |
| **LiveKit** (`TransferSIPParticipant`) | Apache-2.0 | SIP REFER — the same primitive, plus an SFU | **yes** — SFU + SIP bridge | reject: pays for infrastructure to get a REFER |
| **Fonoster** | MIT | whole CPaaS (≈10–11 containers incl. RTPEngine) | **yes** | reject: replaces the stack |
| **jambonz** | MIT source, **licence key required to self-host** | FreeSWITCH + drachtio + rtpengine | **yes** | reject: licensing + a competing platform |
| **FreeSWITCH** | MPL-1.1 | `uuid_transfer`, `eavesdrop` | yes (second PBX) | reject: duplicate PBX |
| **JsSIP** / **SIP.js** | MIT | browser softphone + REFER | no | only if a browser take-over is ever required |
| **coturn** | BSD-3 | TURN relay if WebRTC NAT traversal fails | no (a relay) | only with the WebRTC option |

**There is no off-the-shelf open-source "AI call supervisor console" to adopt.** The literal GitHub
search returns only lab-scale repos (single-digit stars). The console is a few hundred lines over a
transfer API plus the transcript the app already stores — which is what Concierge already has,
minus the transfer.

So the answer to "what has GitHub got that fulfils this" is: **nothing Concierge needs**. The gap
was never an open-source component; it was one provider endpoint that the previous research missed.

---

## 5. The build — a real take-over, on the path that already exists

Scope: **2–4 dev-days**, no new containers, no new provider, no new carrier. One new API call, one
state column set, one UI state.

### 5.1 API and model

`api/app/phone_sip.py`
- Add `refer(call_id, target)` next to `call_control`, same UUID validation, POST to
  `/v1/realtime/calls/{id}/refer` with `{"target_uri": target}`, 20 s client timeout (the provider
  blocks until answered; the HTTP call is long, so it must run **in the background**, never inside
  the request handler).
- Return `(outcome, detail)` where outcome ∈ `answered | rejected | timeout | unsupported | error`,
  mapping `200/400/404/502/504/500` and never raising.
- Add a tiny live-session registry (`_live: dict[call_sid, asyncio.Queue]`) so `serve_call` can be
  told to speak a scripted line before the hand-off (`conversation.item.create` with
  `type: "force_message"`, `interruptible: false` — an xAI extension documented for exactly this)
  and to resume the conversation if the transfer fails. Registration happens where `serve_call`
  opens the WebSocket; the queue is drained between `ws.recv()` timeouts.

`api/app/schema.sql`
```sql
ALTER TABLE phone_calls ADD COLUMN IF NOT EXISTS transfer_state text NOT NULL DEFAULT 'none';
ALTER TABLE phone_calls ADD COLUMN IF NOT EXISTS transfer_target text;
ALTER TABLE phone_calls ADD COLUMN IF NOT EXISTS transfer_at timestamptz;
ALTER TABLE phone_calls ADD COLUMN IF NOT EXISTS transfer_error text;
```
`transfer_state`: `none → requesting → connected | failed`; `phone_calls.status` becomes
`transferred` on success (the existing `in_progress`/`completed` values stay meaningful).

`api/app/live_calls.py`
- `transfer_target(tenant)`: per-tenant `transfer_number` if set, else `notify_phone`; normalise,
  return `None` if missing/invalid.
- `take_over(..., mode='transfer' | 'ring_back')`. Ordering stays the same and is the contract:
  **pause the case → audit → alert the owner → transfer**, with the alert carrying the number and the
  transcript tail either way, so a failed REFER still leaves the owner with everything they need.
- On `502/504`: send the "I couldn't reach them" line, queue the callback task, leave the AI on the
  call, set `transfer_state='failed'` with the carrier's SIP code in `transfer_error`.

`api/app/main.py`
- `POST /owner/live-calls/{call_sid}/takeover` accepts `{mode}` (default `transfer` when a target
  exists, else `ring_back`), returns immediately with `{state: 'requesting'}`; the existing 3 s poll
  picks up `connected`/`failed`. Do **not** hold the HTTP request open for the 45 s REFER.
- `GET /owner/live-calls` gains `transfer_state` and `can_transfer` per call, and the endpoint
  docstring loses the wrong "no SIP transfer" sentence.

`api/app/provider_readiness.py` — the `included` step's copy changes from *"the carrier does not
allow joining a call, so you ring the caller back"* to the two true statements: we can hand the
caller to your phone; we cannot silently listen in. A test already enforces that every shipped
capability is listed here, so this keeps that honest.

### 5.2 Studio

`web/portal/src/App.tsx`, "Happening now" card:
- Button label changes by capability: **"Take over — ring me now"** (transfer) vs the existing
  ring-back when no number is configured.
- On press: Astryx `Dialog` with caller, elapsed time, last few turns, and the target number;
  then the per-call state renders `Connecting…` → `Connected` / `Couldn't connect — ring them back`.
  `Toast` for the outcome. No new component package needed.
- Show the reason on failure (`transfer_error`), because "the carrier rejected the transfer" is an
  operator-fixable thing and a silent failure is not.

### 5.3 Onboarding and language

- "Take over" needs a **transfer number** per tenant. Add `tenants.transfer_number` (blank =
  `notify_phone`), surfaced in Setup next to the notification number, and a step in the
  `provider_readiness` onboarding list. Without it, the feature falls back to ring-back — no
  broken button.
- The greeting and disclosure don't change for a transfer (a transfer is not recording or
  monitoring). **If listen-in is ever built, the disclosure must change first** — see §7.

### 5.4 Tests (mirroring this repo's discipline)

- `refer` status mapping: 200 → `answered`; 502 with SIP body → `rejected` + detail; 504 →
  `timeout`; 400/404 → no retry; exception → `error`, never raised.
- `take_over(mode='transfer')`: case paused before the transfer attempt; exactly one audit row;
  exactly one owner alert; `connected` on 200; on 502 the callback task exists, the AI is still on
  the call, `transfer_state='failed'`.
- Idempotency: two presses within the REFER window send exactly one transfer.
- No target → falls back to `ring_back` (today's behaviour), not an error.
- Non-live call → `409`, unchanged.
- Capability honesty: the per-call `can_transfer` and the Studio label agree with the settings.

### 5.5 Ops / acceptance

The one thing that cannot be proved from a laptop: **a real forwarded call that is REFER'd to a real
mobile and answers.** Acceptance is: caller says "I need a plumber", owner presses take-over, owner's
phone rings, owner answers, caller hears the owner, the AI is gone, the call row says `transferred`.
Before that, the feature is "implemented", not "live".

Carrier check (must confirm before promising it): the trunk must allow call transfer. Twilio's own
SIP docs say to enable call transfer on the trunk when the application transfers mid-session;
Telnyx and Bandwidth both carry REFER. A carrier that strips/forbids REFER returns `502` and the
feature degrades to ring-back — that is the designed fallback, not a bug.

---

## 6. What it is worth (the honest case for and against)

**For.** The difference between "I'll get him to ring you back" and "hold on, I'm putting you
through" is the difference between a lead and a job. Octovox's entire pitch is that an owner trusts
an AI on the phone only if a human can take over. Concierge currently cannot take over — it can only
callback. The existing live panel already delivers the transcript and the "has not spoken" signal;
the missing 20 % is the hand-off.

**Cost.** Two to four dev-days, zero new infrastructure, one provider call, one column set, one
button state. No new container, no new vendor, no new media path, no new compliance surface.

**Against / what it does not fix.** It does not create a customer-dialable number. The phone DID is
still unbought, so this cannot be exercised by a customer until that happens. It does not give
listen-in, so the console stays "watch the words, not the audio" — which is also the privacy-easier
position. And in a one-person business the owner may simply not be able to answer; the callback task
remains the safety net.

**Verdict: build it.** It corrects a wrong premise in shipped code, it is the cheapest genuine
differentiator left on the list, and it is the only Octovox capability that maps to a Concierge
customer. Do not build the console around it.

---

## 7. If listen-in ever becomes a genuine requirement

Only then, and only with a customer paying for it:

- **Own the media**: the Asterisk path already exists. `ChanSpy` `w`/`W`/`B` gives listen, whisper,
  and barge with no new software; `ConfBridge` gives a supervisor join. Needs AMI enabled, the
  parked stack reactivated, a carrier trunk **with an outbound leg**, and a caller-ID fix
  (`${CALLERID}` into a channel variable in the generated dialplan).
- **Browser console**: Asterisk chan_pjsip WebRTC (WSS + DTLS + ICE) and JsSIP (MIT). coturn only if
  NAT traversal actually fails. This is a real hardening surface — treat it as its own project.
- **Not**: LiveKit / Fonoster / jambonz / FreeSWITCH. All add a media server or a competing platform
  to obtain a REFER or an eavesdrop that Asterisk already has.
- **Consent first**: silent monitoring changes what callers must be told. The disclosure in
  `phone_sip.serve_call` and `asterisk_bridge.prepare` would have to say a person may listen, before
  any code ships.

> **Done 2026-11-12:** `asterisk_bridge.greeting_disclosure()` adds exactly that sentence to the
> phone receptionist's instructions — but only when the media server is configured, so a line that
> cannot be monitored is not falsely told it might be. `phone_sip.serve_call` (the Grok SIP path)
> needs no change: nothing there can listen.

---

## 8. Corrections this research forces in existing material

| Where | Says now | Should say |
|---|---|---|
| `api/app/live_calls.py` docstring | "the provider's call API exposes call control (accept/hangup), **not** a SIP transfer" | the provider exposes `refer` and `hangup`; take-over can be a real transfer; there is still no audio join |
| `api/app/main.py` `owner_live_calls` docstring | same claim | same correction |
| `api/app/provider_readiness.py` `_included` | "the carrier does not allow joining a call, so you ring the caller back" | "we can put the caller through to your phone; we cannot silently listen in" |
| `QA/verification/COMPETITOR_GAP_2026-11-12.md` §3B and §4 | "the provider's call API … not a SIP transfer" / "no listen-in because no transfer" | transfer is available via REFER; listen-in is the part that needs owned media |
| `QA/verification/HANDOFF_CURRENT_2026-11-11.md` (B section) | "the provider offers no SIP transfer" | correct it, keep the listen-in limitation |

The docs claim `/accept` in the earlier session notes; xAI has no documented `accept` — the call is
joined by opening the WebSocket with `?call_id=`. Worth fixing wherever it is repeated.

---

## 9. Sources

- xAI: [SIP phone calls guide](https://docs.x.ai/developers/model-capabilities/audio/speech-to-speech/sip)
  (registration, `realtime.call.incoming`, call control, transfer status table, FAQ on failed
  transfers and session resumption); [Voice REST reference](https://docs.x.ai/developers/rest-api-reference/inference/voice)
  (`POST /v1/realtime/calls/{call_id}/refer`, `/hangup`, `POST /v2/phone-numbers`, WebSocket event
  list, `force_message`, `resumption`).
- SIP REFER: [RFC 3515](https://www.rfc-editor.org/rfc/rfc3515).
- Asterisk: [AMI Redirect](https://docs.asterisk.org/Asterisk_20_Documentation/API_Documentation/AMI_Actions/Redirect/),
  [ARI Channels](https://docs.asterisk.org/Asterisk_20_Documentation/API_Documentation/Asterisk_REST_Interface/Channels_REST_API/),
  [ChanSpy](https://docs.asterisk.org/Asterisk_20_Documentation/API_Documentation/Dialplan_Applications/ChanSpy/),
  [ConfBridge](https://docs.asterisk.org/Asterisk_20_Documentation/API_Documentation/Dialplan_Applications/ConfBridge/),
  [AudioSocket](https://docs.asterisk.org/Asterisk_20_Documentation/API_Documentation/Dialplan_Applications/AudioSocket/),
  [Asterisk for WebRTC](https://docs.asterisk.org/Configuration/WebRTC/Configuring-Asterisk-for-WebRTC-Clients/).
- Comparison providers: [OpenAI Realtime calls](https://developers.openai.com/api/docs/guides/realtime-conversations),
  [Telnyx Call Command](https://developers.telnyx.com/api/call-control/call-commands),
  [Twilio `<Refer>`](https://www.twilio.com/docs/voice/twiml/refer),
  [Twilio Conference participants](https://www.twilio.com/docs/voice/api/conference-participant).
- OSS: [LiveKit SIP protocol](https://github.com/livekit/protocol/blob/main/protobufs/livekit_sip.proto),
  [Fonoster](https://github.com/fonoster/fonoster), [jambonz licensing](https://docs.jambonz.org/self-hosting/overview/licensing),
  [FreeSWITCH](https://github.com/signalwire/freeswitch), [JsSIP](https://github.com/versatica/JsSIP),
  [SIP.js](https://github.com/onsip/SIP.js), [coturn](https://github.com/coturn/coturn).
- Repo: `api/app/phone_sip.py`, `api/app/live_calls.py`, `api/app/asterisk_bridge.py`,
  `scripts/asterisk/render_routes.py`, `api/app/schema.sql`, `web/portal/src/App.tsx`.

## 10. Not verified (be explicit)

- No xAI `refer` request was sent — no live call exists and a test would cost money and need a DID.
  The endpoint is documented; it is not proof-of-life from this environment.
- No carrier has confirmed REFER support for a Concierge number, because no carrier is currently
  bound to one.
- The Asterisk listen-in path (AMI redirect + ChanSpy) was not exercised; the parked stack has no
  AMI configured.
- Octovox's console was assessed from its public pages and the earlier `COMPETITORS_RAW` evidence,
  not from a trial account (they sell channel-only, quote-only, with no self-serve).
