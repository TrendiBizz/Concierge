"""Owner-alert resilience and channel health for email, SMS (phone device) and voice.

Why this exists (2026-11-12 audit): the SMS phone device went silent for ~45 hours and an
owner-alert address was blocklisted by the mail provider. Every alert for those channels was
recorded as failed and then simply dropped, so a real enquiry would have reached nobody.

Two jobs, both read-mostly and safe to run repeatedly:

* ``escalate_failed_owner_alerts`` - an owner alert that ended ``failed`` / ``held`` /
  ``suppressed`` on one channel is re-queued once on the other channel. The fallback row carries
  a ``fb:`` dedupe key, so it is created at most once and is never itself escalated (no loops).
* ``channel_report`` - a plain status for each of email, SMS and voice that the owner portal and
  the healthcheck can show, so "the phone is offline" is visible instead of silent.
"""

import logging
from datetime import timedelta

from . import db, outbox

log = logging.getLogger("concierge.channel_health")

# The phone polls constantly while the app is open. Beyond this it is treated as offline.
DEVICE_OFFLINE_AFTER = timedelta(minutes=15)
# Only recent alerts are worth escalating; older ones are history, not live enquiries.
ESCALATION_WINDOW_HOURS = 24
FAILED_STATES = ("failed", "held", "suppressed")


def _fallback(row: dict) -> tuple[str, str, str, str] | None:
    """Return (channel, to_addr, subject, body) for the other channel, or None if unavailable."""
    subject = row.get("subject") or "New enquiry"
    body = row["body"]
    if row["channel"] == "sms":
        target = (row.get("notify_email") or "").strip()
        if not target or target == row.get("to_addr"):
            return None
        note = "(Sent by email because the text message could not be confirmed.)\n\n"
        return "email", target, subject, note + body
    if row["channel"] == "email":
        target = (row.get("notify_phone") or "").strip()
        if not target or target == row.get("to_addr"):
            return None
        # SMS is short: keep the first 300 characters of the alert.
        return "sms", target, "", body[:300]
    return None


async def escalate_failed_owner_alerts() -> int:
    """Re-queue recent failed owner alerts on the other channel. Returns rows newly queued."""
    rows = await db.pool().fetch(
        """
        SELECT o.id, o.tenant_id, o.channel, o.to_addr, o.subject, o.body,
               t.notify_phone, t.notify_email
        FROM outbox o JOIN tenants t ON t.id = o.tenant_id
        WHERE o.kind = 'owner_alert'
          AND o.status = ANY($1::text[])
          AND o.created_at > now() - make_interval(hours => $2)
          AND COALESCE(o.dedupe_key, '') NOT LIKE 'fb:%'
        ORDER BY o.id
        LIMIT 50
        """,
        list(FAILED_STATES), ESCALATION_WINDOW_HOURS,
    )
    queued = 0
    for record in rows:
        row = dict(record)
        fallback = _fallback(row)
        if fallback is None:
            continue
        channel, to_addr, subject, body = fallback
        try:
            created = await outbox.enqueue(
                row["tenant_id"], "owner_alert", channel, to_addr, body, subject=subject,
                dedupe_key=f"fb:{row['id']}:{channel}",
            )
        except Exception:  # noqa: BLE001 - one bad row must not stop the sweep
            log.exception("could not escalate outbox row %s", row["id"])
            continue
        if created:
            queued += 1
            log.warning("owner alert %s failed on %s; re-queued on %s", row["id"], row["channel"], channel)
    return queued


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
