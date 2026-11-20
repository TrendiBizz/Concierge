# Owner alert texts and the Mac phone connector

Owner SMS leaves the VPS as a `device_sms_jobs` row. The Mac connector (`scripts/devices/mac_sms_agent.py`,
launchd `com.trendi.phone-connector`) claims it and asks the iMessage bridge (`~/imessage-bridge-grok`) to send.
The bridge shows a native macOS dialog (Cancel is default, 60 s limit, hard-coded in `bin/confirm_imessage_send.m`)
and a person must click **Send**. No click, a locked/asleep Mac, or a Cancel makes the bridge raise
`send cancelled by user or timed out (60s dialog limit)`; the connector reports `failed`; the server records
"Phone did not confirm send; reconcile before retry".

Consequences handled in the API: owner SMS is used only when the tenant has no usable alert email AND the connector is
confirming texts (`owner_notifications.delivery_route`; after 3 unconfirmed texts in a row it is not reliable until a
2 hour probe interval passes). There is no SMS->email fallback copy: a failed alert becomes ONE "ACTION NEEDED" notice
(`owner_issues`). Robot/vendor mail produces no alert. Do not weaken the bridge's dialog to "fix" this.

## Alert design (2026-11-21)
`enquiry_alerts.notify` = the one alert per enquiry, per-channel template. `owner_issues` = at most one ACTION NEEDED
notice per enquiry per problem (alert_undelivered, unanswered, reply_failed). `owner_notifications.queue` = one-off
notices (payment, take-over), one channel.
