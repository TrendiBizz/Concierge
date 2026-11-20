"""Owner-alert resilience and channel health for email, SMS (phone device) and voice.

Why this exists (2026-11-12 audit): the SMS phone device went silent for ~45 hours and an
owner-alert address was blocklisted by the mail provider. Every alert for those channels was
recorded as failed and then simply dropped, so a real enquiry would have reached nobody.

``channel_report`` gives a plain status for each of email, SMS and voice that the owner portal and the
healthcheck can show, so "the phone is offline" is visible instead of silent. There is NO failover that
re-sends an owner alert on another channel (it produced duplicate alerts); a failed enquiry alert becomes
one "ACTION NEEDED" notice instead -- see ``owner_issues``.
"""

import logging
from datetime import datetime, timedelta, timezone

from . import db, outbox

log = logging.getLogger("concierge.channel_health")

# The phone polls constantly while the app is open. Beyond this it is treated as offline.
DEVICE_OFFLINE_AFTER = timedelta(minutes=15)

async def sms_device_health(tenant_id) -> dict:
    """Status of the tenant's SMS phone device: paired, verified, and recently seen."""
    device = await db.pool().fetchrow(
        """SELECT enabled, last_seen, verified_at, inbound_verified_at,
                  now() - last_seen AS silent_for
           FROM sms_devices WHERE tenant_id = $1 AND enabled""",
        tenant_id,
    )
    if device is None:
        return {"state": "not_configured", "ok": False,
                "message": "No SMS phone is paired. Alerts will go by email."}
    if device["last_seen"] is None or device["silent_for"] > DEVICE_OFFLINE_AFTER:
        return {"state": "offline", "ok": False,
                "message": "The SMS phone has not checked in recently. Open the app on that phone; "
                           "alerts are being sent by email meanwhile."}
    if device["verified_at"] is None:
        return {"state": "unverified", "ok": False, "message": "The SMS phone has not been verified yet."}
    return {"state": "online", "ok": True, "message": "SMS phone online."}


async def email_health(tenant_id) -> dict:
    """Whether recent owner-alert emails are being refused (blocklist, suppression, bounces)."""
    counts = await db.pool().fetchrow(
        """SELECT count(*) FILTER (WHERE status IN ('failed','suppressed')) AS bad,
                  count(*) FILTER (WHERE status = 'sent') AS good
           FROM outbox
           WHERE tenant_id = $1 AND channel = 'email' AND kind = 'owner_alert'
             AND created_at > now() - interval '24 hours'""",
        tenant_id,
    )
    bad, good = counts["bad"], counts["good"]
    if bad and not good:
        return {"state": "refused", "ok": False,
                "message": "Owner-alert emails are being refused. Check the address is not blocklisted."}
    return {"state": "ok", "ok": True, "message": "Email alerts are being delivered."}


async def voice_health(tenant_id) -> dict:
    """Whether recent calls reached the assistant, from the call records."""
    counts = await db.pool().fetchrow(
        """SELECT count(*) FILTER (WHERE status IN ('failed','disconnected')) AS bad,
                  count(*) FILTER (WHERE status = 'completed') AS good
           FROM phone_calls
           WHERE tenant_id = $1 AND started_at > now() - interval '7 days'""",
        tenant_id,
    )
    bad, good = counts["bad"], counts["good"]
    if bad and not good:
        return {"state": "failing", "ok": False,
                "message": "Recent calls have failed or dropped and none has completed."}
    if not bad and not good:
        return {"state": "untested", "ok": False, "message": "No call has completed yet. Make a test call."}
    return {"state": "ok", "ok": True, "message": "Calls are completing."}


async def channel_report(tenant_id) -> dict:
    """Combined status the portal and healthcheck can show for one tenant."""
    report = {
        "email": await email_health(tenant_id),
        "sms": await sms_device_health(tenant_id),
        "voice": await voice_health(tenant_id),
    }
    report["all_ok"] = all(item["ok"] for item in report.values())
    return report


# A delivered owner alert (real or test) within this window proves the business can be reached.
PROOF_WINDOW_DAYS = 7


async def proven_channels(tenant_id) -> list[str]:
    """Alert channels that actually delivered (status 'sent') to this business recently.

    'sent' for SMS means the phone itself confirmed it, so this is delivery evidence, not intent.
    """
    rows = await db.pool().fetch(
        """SELECT DISTINCT channel FROM outbox
           WHERE tenant_id = $1 AND kind = 'owner_alert' AND status = 'sent'
             AND created_at > now() - make_interval(days => $2)""",
        tenant_id, PROOF_WINDOW_DAYS,
    )
    return sorted(row["channel"] for row in rows)


async def go_live_blockers(tenant: dict) -> list[str]:
    """Reasons a business must not have its phone switched on yet. Empty list = ready.

    A phone line that answers customers but cannot tell the owner is worse than no phone line:
    the enquiry is taken and then silently lost.
    """
    problems = []
    if not (tenant.get("notify_phone") or "").strip():
        problems.append("Set the owner's mobile number for alerts.")
    if not (tenant.get("notify_email") or "").strip():
        problems.append("Set the owner's alert email address.")
    if not await proven_channels(tenant["id"]):
        problems.append("Send a test alert and confirm it arrived: no alert has been delivered "
                        f"in the last {PROOF_WINDOW_DAYS} days.")
    return problems


async def send_test_alert(tenant: dict) -> dict:
    """Queue a clearly labelled test alert on every configured alert channel."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    text = (f"Test alert from Trendi Concierge for {tenant.get('name') or 'your business'}. "
            "If you can read this, new enquiries will reach you.")
    queued = []
    for channel, target, subject in (
        ("email", tenant.get("notify_email"), "Test alert - Trendi Concierge"),
        ("sms", tenant.get("notify_phone"), ""),
    ):
        target = (target or "").strip()
        if not target:
            continue
        created = await outbox.enqueue(
            tenant["id"], "owner_alert", channel, target, text, subject=subject,
            dedupe_key=f"test:{tenant['id']}:{channel}:{stamp}",
        )
        if created:
            queued.append(channel)
    return {"queued": queued}
