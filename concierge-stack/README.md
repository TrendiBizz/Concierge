# Concierge stack: Grok Voice phone assistant

A voice assistant for Trendi that runs on your Mac now and on a VPS later. It asks which service
the caller wants (Concierge, SEO and AI visibility, or penetration testing), answers from
`PRODUCT.md`, books consultations, takes messages, and hangs up when finished.

## Run it on your Mac (no server, Docker or phone number)
```bash
./concierge-stack/set-key.sh      # type your xAI key, hidden. Saved to concierge-stack/.env only.
./concierge-stack/run-local.sh    # talk to Grok through your Mac mic and speakers
```
macOS asks for microphone permission the first time. Python 3.11 to 3.13 is needed (your Mac's
default 3.15 is too new), so the scripts use 3.12.

What it saves, in `concierge-stack/data/` (git-ignored, contains callers' details):
| File | What |
|---|---|
| `concierge.db` | Booked consultations (SQLite). Two calls can never take the same slot. |
| `messages.jsonl` | Messages left for the team. |
| `outbox.jsonl` | Every email and text it tried to send, with status `sent`, `queued` or `failed`. |

## How the pieces fit
| Piece | File | Notes |
|---|---|---|
| Voice agent and conversation rules | `agent/agent.py` | Grok Voice via LiveKit's xAI plugin |
| Booking | `agent/booking.py` | Mon to Fri 9 to 5 NZ time, 30-minute slots, 2 hours notice, 14 days ahead. Change in `.env`. |
| Email and text | `agent/notify.py` | Email via any SMTP provider, text from your Mac's Messages app (`SMS_PROVIDER=mac`, `agent/sms_providers.py`) or Telnyx. **Until configured, messages only go to `outbox.jsonl` and the agent says the team will send them. It never claims "sent" unless the provider accepted it.** |
| Hang-up | `CallGuard` in `agent/agent.py` | Hangs up after a spoken farewell even if the model forgets, after 45 seconds of silence, and after 15 minutes at most. |
| Message replies | `agent/acknowledge.py`, `save_message` in `agent/agent.py` | After taking a message the agent asks how the team should follow up (email or phone call), then whether the caller wants a quick acknowledgement by text, email or none, and only if they do, a short summary or a brief acknowledgement. Only the chosen reply is sent, and a summary containing a price, a promise or the word "free" is replaced by the brief one. |
| Call transcripts | `agent/transcripts.py` | Text of every call, one line per turn, saved to `data/transcripts/` (owner-only, git-ignored, no phone number in the file name). Old files are deleted after `TRANSCRIPT_RETENTION_DAYS` (30 days). Messages, the outbox and bookings are never auto-deleted. **Text only: audio is not recorded.** |
| Owner alerts | `agent/notify.py` | New bookings and messages are emailed to `OWNER_EMAIL` (sent through Brevo SMTP once `.env` is set; queued otherwise). |
| Phone line (VPS later) | `docker-compose.voice.yml`, `livekit/` | LiveKit server and SIP bridge |
| Ops tools (VPS later) | `docker-compose.ops.yml` | Uptime Kuma, Activepieces, Listmonk |

## Tests
```bash
concierge-stack/.venv/bin/python -m unittest discover -s concierge-stack/tests -v   # offline, free
./concierge-stack/tests/run-chat-check.sh                                           # uses your xAI key, a few cents
```
The chat check drives the real agent with a Grok **text** model and typed caller lines. It checks
service routing, prices, booking, honest confirmation status and hang-up. It cannot judge how the
voice sounds, so the Mac microphone test is still needed.

## Turning on real email and text
Add to `concierge-stack/.env` (no code changes):
- Email: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_FROM` (Amazon SES, Postmark, Brevo or similar).
  Set up SPF, DKIM and DMARC for the sending domain first.
  Brevo is set up for `trendibizz.com` (DKIM and DMARC verified, sender `admin@trendibizz.com`).
  Run `./concierge-stack/set-email.sh` to store the SMTP login and key, then
  `./concierge-stack/tests/send-test-email.sh you@example.com` to send one real test.
  A test email was delivered to an inbox (not spam) on 2026-11-07. A full voice booking with
  email confirmation has not been tested yet.
- Text from your own number: `SMS_PROVIDER=mac`. The Mac sends through Messages using your iPhone's
  Text Message Forwarding. A send is reported `sent` only when Messages' database confirms it left as
  an SMS; otherwise `failed` or `unverified` (treated as not sent). For that, give the Terminal (or app)
  running the agent Full Disk Access. Check with `./concierge-stack/tests/send-test-sms.sh --check`,
  and send one real test to another person's phone with `send-test-sms.sh NUMBER`.
  It works only while this Mac and the iPhone are on and online. After the VPS move the agent needs a
  relay on the Mac (designed in `sms_providers.py`, not built) or a hosted provider.
- Text via Telnyx instead: `TELNYX_API_KEY`, `SMS_FROM` (a real number; NZ does not allow sender IDs).
  The Telnyx request format is from memory and is untested.

## Calling it from a real phone
A phone call needs a phone line that reaches the agent: a NZ number from a carrier with a SIP
trunk, or a Twilio or Telnyx number bridged to LiveKit, and the Mac or a VPS reachable from the
internet. Do this after the Mac microphone test is happy. Your mobile can then be the number that
dials in, and `HUMAN_TRANSFER_NUMBER` for transfers.

## Backups
Encrypted offsite backup of `data/` (bookings database, messages, outbox, transcripts) with restic to a
Cloudflare R2 bucket (free tier). Scripts: `set-backup.sh` (hidden entry of the R2 keys; shows a generated
backup password once, save it in a password manager), `backup.sh`, and `restore-test.sh` (restores the newest
snapshot to a temporary folder, checks it, prints only counts). Tested end to end against a local repository
with fake data, then against the real R2 bucket on 2026-11-07 (first backup uploaded, restore test passed; at that time it held only a couple of messages and the outbox, no bookings or transcripts yet). `BACKUP_KEEP_DAYS` (30 days) removes old backup snapshots. A transcript deleted from the Mac can still sit in
older snapshots, so its longest life is the transcript retention plus the backup retention (about 60 days). Audio is not recorded, so none is backed up.

**Schedule.** `install-backup-schedule.sh` installs two macOS launchd jobs: a backup daily at 03:15 and a restore
test on the 1st of each month at 03:45 (`--uninstall` removes them). A job missed while the Mac was asleep runs when
it wakes; if the Mac stays off there are no backups for those days. `scheduled-run.sh` runs each job, appends to
`~/Library/Logs/trendi-concierge-backup.log` and shows a macOS notification on failure. Installed and triggered once
by hand on 2026-11-07 (it uploaded a snapshot). The monthly restore test has not yet had its first scheduled run.

## Scaling to more customers
Design only, not built: see `docs/SCALING-AND-INTEGRATIONS.md` (one profile per customer, data folder per customer,
adapters for their CRM, email and SMS, and the core Trendi assistant unchanged for everyone).

## Known gaps (as of this commit)
Cannot be fixed without something from you or an outside party:
1. **No phone line yet.** Needs a NZ number and carrier, and confirmation that they sell NZ numbers.
2. **Text and email depend on this Mac.** Email works through Brevo (free plan, 300 a day) and a real
   test email arrived. Text works from the Mac (a real test text was reported received) but the full
   booking flow with confirmations has not been tested by a live voice call, and the VPS relay is not built.
3. **Two booking systems.** `PRODUCT.md` says the website chat service (`chat.trendibizz.com`, not in this repo) has its own appointments. This phone booking list is separate, so a chat visitor and a caller could take the same time. Fixing it needs that service's API or database.
4. **Owner sees bookings only by email** (with a calendar invite). There is no shared calendar yet.
5. **No cancel or reschedule by phone.** The agent takes a message instead.
6. **Audio is not recorded.** Transcripts are saved locally, which matches "recorded and transcribed" in the greeting only in part. LiveKit's built-in `record` option uploads to LiveKit Cloud, so it is not used. Audio needs LiveKit egress on the VPS, to storage you control. The retention period is still a placeholder and the transcripts need to be in the encrypted offsite backup.
7. **Legal.** Privacy, Terms, consent for text and email, and data retention are parked until last.
8. **No backups** of `data/`. Needed on a VPS.

Unproven until tested live: phone transfer, phone hang-up, the `livekit/sip` config details,
Telnyx sending, and the voice (not text) hang-up guard.

## Not scaffolded
Chatwoot (inbox) and Cal.diy (appointments). Chatwoot's licence is unconfirmed, and Cal.diy's image
is unverified. The built-in booking above covers phone consultations for now.
