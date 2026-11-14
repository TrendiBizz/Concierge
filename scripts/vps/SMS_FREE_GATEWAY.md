# Free inbound and outbound SMS: the phone-as-gateway route

**Short answer: yes.** An Android phone with a SIM, running the open-source
[android-sms-gateway](https://github.com/capcom6/android-sms-gateway) app (Apache-2.0), receives a
text from *any* number in the world and forwards it to this API; replies are sent back through the
same SIM. The transport is already written and tested here — `SMS_PROVIDER=smsgate`, webhook
`POST /api/v1/smsgate/{public_key}`, HMAC-signed. Nothing is switched on yet.

## What "free" means, honestly

| Item | Cost |
|---|---|
| The app, the protocol, this integration | **$0** — open source, self-hosted, no per-message fee |
| Receiving a text | **$0** — incoming SMS is free on every NZ mobile plan |
| Sending a reply | **the SIM's own SMS allowance** — $0 on a plan with unlimited texts; a few cents on prepaid |
| The number | whatever you already pay for that SIM |
| A spare handset | $0 if you have one; it must stay powered and online |

There is no metered API in the path, which is the whole point: Twilio charges per message, this
does not. What this cannot do is be free *and* handle thousands of messages a day, or use an
alphanumeric sender ID — the handset sends one text at a time at human speed, and the number *is*
the identity.

## One-time setup (about 15 minutes, needs the phone in your hand)

1. **The phone.** Any Android 8+ handset with a SIM that can send and receive texts. Leave it on
   charge, connected to Wi-Fi, and exempt the app from battery optimisation (Settings → Apps →
   android-sms-gateway → Battery → Unrestricted). If the system sleeps the app, texts stop
   arriving — that is the number one failure with this design.
2. **The app.** Install `android-sms-gateway` (F-Droid / GitHub releases; it is also on Google
   Play). Grant it SMS and notification permissions, and set it as the **default SMS app** so it
   sees every incoming message.
3. **Choose a mode.**
   - **Cloud (simplest, still free):** the app registers with the project's public relay; this API
     then reaches the phone without any inbound port. Set `SMSGATE_BASE_URL=https://api.sms-gate.app/3rdparty/v1`
     (the exact URL is shown in the app under *Settings → Connection*).
   - **Private server:** run the app's own local server and expose it over HTTPS. More control,
     more to break; the VPS would need to reach the phone.
   Either way, copy the **username and password** the app shows into `SMSGATE_USERNAME` and
   `SMSGATE_PASSWORD`.
4. **The webhook.** In the app: *Settings → Webhooks → Add*:
   - URL: `https://chat.trendibizz.com/api/v1/smsgate/<tenant public_key>`
   - Event: **`sms:received`**
   - Copy the **Signing Key** it generates into `SMSGATE_SIGNING_KEY` on the server.
5. **Server config** in `/opt/trendi/shared/api.env`:
   ```
   SMS_PROVIDER=smsgate
   SMSGATE_BASE_URL=<the URL from the app>
   SMSGATE_USERNAME=<from the app>
   SMSGATE_PASSWORD=<from the app>
   SMSGATE_SIGNING_KEY=<from the app's webhook screen>
   SMSGATE_SEND_PATH=/3rdparty/v1/messages   # cloud mode; the private server uses /message
   SMSGATE_SIM_NUMBER=1
   ```
   Then `docker restart trendi-api-1` (the settings are read at startup).
6. **The tenant.** `UPDATE tenants SET sms_transport='smsgate', sms_enabled=true, sms_from='+64...'`
   and grant the channel: `sms_read` and `sms_send` in `tenant_channel_authorizations` for that
   business. Without `sms_read` the webhook answers 403 "Business has not authorized incoming SMS".
7. **Prove it.**
   ```
   python3 scripts/vps/smsgate_check.py            # env, gateway, webhook, tenant
   ```
   then text the SIM from another phone. Within a second or two the API records the message, the
   AI answers, and the reply leaves through the SIM. `device_sms_inbound` stays empty — that table
   belongs to the *paired-phone* transport, not this one. Watch `messages` instead:
   ```
   SELECT m.role, left(m.content,60), m.created_at FROM messages m
   JOIN conversations c ON c.id=m.conversation_id WHERE c.channel='sms'
   ORDER BY m.created_at DESC LIMIT 5;
   ```

## The one thing that is genuinely unverified

`validate_smsgate_signature()` signs `body + X-Timestamp` with HMAC-SHA256. It was written from
the app's documented scheme, never against a real webhook from the phone, and the code says so.
The first real text settles it: if the webhook logs `403 Invalid signature`, flip the
concatenation order in `api/app/sms.py` (timestamp + body) and redeploy — nothing else changes.

## When not to use this

- **Volume.** A handset is fine for a business's real inbox (tens a day). If Concierge's own
  product needs to send on behalf of *many* businesses, each tenant needs its own SIM and handset,
  or a paid provider (Twilio) per number.
- **Compliance.** Google's Play policy and carrier terms prohibit bulk/unsolicited messaging from a
  personal SIM. This is for a business answering its own customers.
- **International replies.** Receiving is free; replying to an overseas number costs whatever the
  carrier charges for an international SMS.
