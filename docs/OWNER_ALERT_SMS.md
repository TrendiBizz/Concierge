# Owner alert texts and the Mac phone connector

Owner SMS leaves the VPS as a `device_sms_jobs` row. The Mac connector (`scripts/devices/mac_sms_agent.py`,
launchd `com.trendi.phone-connector`) claims it and asks the iMessage bridge (`~/imessage-bridge-grok`) to send.
The bridge shows a native macOS dialog (Cancel is default, 60 s limit, hard-coded in `bin/confirm_imessage_send.m`)
and a person must click **Send**. No click, a locked/asleep Mac, or a Cancel makes the bridge raise
`send cancelled by user or timed out (60s dialog limit)`; the connector reports `failed`; the server records
"Phone did not confirm send; reconcile before retry".

Consequences handled in the API: after 3 unconfirmed owner texts in a row the API stops queueing owner SMS
(`owner_notifications.sms_unconfirmable`) and lets one probe text through every 2 hours. Robot/vendor mail is
email only. Do not weaken the bridge's dialog to "fix" this; use email/web push, or pick an unattended route deliberately.
