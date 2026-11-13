"""Follow-up engine: a durable queue of SMS / email messages with retries, opt-outs and quiet hours."""

import asyncio
import logging
import time as _time
from datetime import datetime, time, timedelta, timezone
from email.utils import make_msgid
from zoneinfo import ZoneInfo

from . import casetimeline, channel_authorization, db, device_sms, flood_guard, mailer, sms, suppressions, tenants, unsub, tenant_pause
from .config import get_settings
from .contact import contact_key

log = logging.getLogger("concierge.outbox")

MAX_ATTEMPTS = 3
# Kinds that go to the business owner, not a visitor: never blocked by opt-outs.
OWNER_KINDS = {"owner_alert"}
# Transactional mail the customer has already paid for or asked for. It is not marketing, so the
# opt-out, pause and channel-authorisation gates do not apply to it — an invoice must not be
# silently "skipped" because the business had not authorised email sending yet.
TRANSACTIONAL_KINDS = {"owner_alert", "customer_invoice"}


def next_allowed_send(tz: ZoneInfo, when: datetime, start_hour: int = 8, end_hour: int = 21) -> datetime:
    """Move `when` to the next moment inside the allowed sending window (local time)."""
    local = when.astimezone(tz)
    if start_hour <= local.hour < end_hour:
        return when
    day = local.date() if local.hour < start_hour else local.date() + timedelta(days=1)
    return datetime.combine(day, time(start_hour), tzinfo=tz).astimezone(timezone.utc)


async def enqueue(
    tenant_id,
    kind: str,
    channel: str,
    to_addr: str,
    body: str,
    subject: str = "",
    send_at: datetime | None = None,
    dedupe_key: str | None = None,
    appointment_id=None,
    lead_id=None,
    campaign_id=None,
) -> bool:
    """Queue a message. Returns False if an identical dedupe_key already exists."""
    result = await db.pool().execute(
        """
        INSERT INTO outbox (tenant_id, kind, channel, to_addr, subject, body, send_at, dedupe_key,
                            appointment_id, lead_id, campaign_id)
        VALUES ($1, $2, $3, $4, $5, $6, COALESCE($7, now()), $8, $9, $10, $11)
        ON CONFLICT (dedupe_key) WHERE dedupe_key IS NOT NULL DO NOTHING
        """,
        tenant_id, kind, channel, to_addr, subject, body, send_at, dedupe_key, appointment_id, lead_id,
        campaign_id,
    )
    return result.endswith("1")


async def cancel_for_appointment(appointment_id) -> int:
    result = await db.pool().execute(
        "UPDATE outbox SET status = 'cancelled' WHERE appointment_id = $1 AND status = 'pending'",
        appointment_id,
    )
    return int(result.split()[-1])


async def _optout_cc(tenant_id) -> str:
    """The dialling country to canonicalise an opt-out key with.

    This MUST be the tenant's own country, not the global default. Using the global setting (which
    defaults to '1', US) meant a number outside +1 failed to parse, so the RAW string was stored as
    the opt-out key. The same person's other spellings then did not match it, and we kept texting
    someone who had unsubscribed. That is a compliance failure, not a cosmetic one.
    """
    from . import casetimeline, tenants
    tenant = await tenants.get_by_id(tenant_id) if tenant_id else None
    return casetimeline.tenant_country_code(tenant)


async def opt_out(tenant_id, contact: str) -> None:
    await db.pool().execute(
        "INSERT INTO opt_outs (tenant_id, contact) VALUES ($1, $2) ON CONFLICT DO NOTHING",
        tenant_id, contact_key(contact, await _optout_cc(tenant_id)),
    )


async def opt_in(tenant_id, contact: str) -> None:
    await db.pool().execute(
        "DELETE FROM opt_outs WHERE tenant_id = $1 AND contact = $2",
        tenant_id, contact_key(contact, await _optout_cc(tenant_id)),
    )


async def is_opted_out(tenant_id, contact: str) -> bool:
    found = await db.pool().fetchval(
        "SELECT 1 FROM opt_outs WHERE tenant_id = $1 AND contact = $2",
        tenant_id, contact_key(contact, await _optout_cc(tenant_id)),
    )
    return bool(found)


async def _finish(row_id: int, status: str, error: str = "") -> None:
    await db.pool().execute(
        "UPDATE outbox SET status = $2, last_error = $3, sent_at = CASE WHEN $2 = 'sent' THEN now() ELSE sent_at END "
        "WHERE id = $1",
        row_id, status, error[:500],
    )


async def _deliver(row: dict) -> None:
    settings = get_settings()
    tenant = await tenants.get_by_id(row["tenant_id"])
    if tenant is None:
        await _finish(row["id"], "skipped", "tenant_deleted")
        return

    if row['kind'] == 'email_secretary_reply' and (not tenant.get('email_auto_reply') or not await channel_authorization.is_authorized(tenant['id'], 'email_read')):
        await _finish(row['id'], 'skipped', 'email_secretary_authorization_revoked')
        return

    # Recheck authorization at actual delivery time. Queued work must not bypass
    # a customer's revocation; operational owner alerts remain separate.
    if (row["kind"] not in TRANSACTIONAL_KINDS or row["channel"] == "sms") and row["channel"] in ("email", "sms"):
        permission = "email_send" if row["channel"] == "email" else "sms_send"
        if not await channel_authorization.is_authorized(row["tenant_id"], permission):
            await _finish(row["id"], "skipped", "channel_authorization_missing")
            return

    if row["kind"] not in TRANSACTIONAL_KINDS and await is_opted_out(row["tenant_id"], row["to_addr"]):
        await _finish(row["id"], "skipped", "opted_out")
        return

    # A supposedly-delivered email can still hard-bounce. Once an address is suppressed (DSN,
    # provider webhook, or an operator block) nothing is sent to it again; without this a dead
    # mailbox was retried forever and the outbox kept claiming delivery.
    if row["channel"] == "email" and await suppressions.is_suppressed(row["tenant_id"], row["to_addr"]):
        await _finish(row["id"], "suppressed", "address_suppressed")
        return

    # Human takeover, rechecked at delivery time. A reply queued BEFORE the owner took over would
    # otherwise still arrive afterwards, which is the window that checking only at queue time leaves
    # open. Owner alerts are exempt: takeover silences replies to the CUSTOMER, never the owner's own
    # notification, which is the very message they need in order to act.
    if row["kind"] not in TRANSACTIONAL_KINDS and row["channel"] in ("email", "sms"):
        try:
            if await casetimeline.is_paused_for(
                row["tenant_id"],
                phone=row["to_addr"] if row["channel"] == "sms" else "",
                email=row["to_addr"] if row["channel"] == "email" else "",
                default_cc=casetimeline.tenant_country_code(tenant),
            ):
                await _finish(row["id"], "skipped", "human_takeover")
                return
        except Exception:  # noqa: BLE001 - a lookup failure must not block a legitimate reply
            log.exception("takeover check failed for outbox row %s", row["id"])

    if row.get("campaign_id") and not tenant.get("campaigns_enabled"):
        await _finish(row["id"], "skipped", "campaigns_disabled")  # kill switch, checked at send time
        return

    # Flood guard: every email and text leaves through here, so the limits live here.
    if row["channel"] in ("email", "sms"):
        if row["kind"] == "email_secretary_reply" and flood_guard.automated_message(row["to_addr"]):
            await _finish(row["id"], "skipped", "flood_guard:automated_recipient")
            return
        reason = await flood_guard.check(row)
        if reason:
            log.warning("flood guard blocked outbox %s (%s, %s): %s",
                        row["id"], row["channel"], row["kind"], reason)
            await _finish(row["id"], "skipped", f"flood_guard:{reason}")
            return

    # The owner switching Concierge off must stop messages reaching *their customers*. This sits
    # after the specific checks so a suppressed address or a takeover still reports its own
    # reason, and before the dispatch so nothing is actually sent.
    # Owner alerts are deliberately exempt: a paused business still needs to know who tried to
    # reach it, and the enquiry itself is captured.
    if row["kind"] not in TRANSACTIONAL_KINDS and await tenant_pause.is_paused(tenant):
        await _finish(row["id"], "skipped", "tenant_paused")
        return

    if row["channel"] == "sms":
        if not sms.sender_ready(tenant):
            await _finish(row["id"], "skipped", "sms_not_configured")
            return
        allowed = next_allowed_send(
            ZoneInfo(tenant["timezone"]), datetime.now(timezone.utc),
            settings.sms_quiet_start_hour, settings.sms_quiet_end_hour,
        )
        if allowed > datetime.now(timezone.utc):
            # Quiet hours: put it back for the morning; this does not count as an attempt.
            await db.pool().execute(
                "UPDATE outbox SET status = 'pending', attempts = attempts - 1, send_at = $2 WHERE id = $1",
                row["id"], allowed,
            )
            return
        try:
            await sms.send_sms(row["to_addr"], row["body"], tenant.get("sms_from"),
                               tenant=tenant, request_key="outbox:"+str(row["id"]), outbox_id=row["id"])
        except device_sms.AwaitingReceipt:
            # The device may complete during this HTTP/DB turn. Preserve its
            # terminal receipt instead of overwriting it with a queued state.
            await db.pool().execute(
                "UPDATE outbox SET status='awaiting_receipt' WHERE id=$1 AND status='sending'", row["id"])
            return
        except device_sms.ReconciliationRequired:
            await _finish(row["id"], "held", "Phone SMS requires owner reconciliation")
            return
    elif row["channel"] == "email":
        if not settings.email_configured:
            await _finish(row["id"], "skipped", "email_not_configured")
            return
        headers = None
        if row.get("campaign_id"):
            link = unsub.url_for(row["tenant_id"], row["to_addr"])
            headers = {"List-Unsubscribe": f"<{link}>", "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"}
        if tenant.get("reply_address"):
            # EVERY customer-visible message carries the tenant reply address, not only owner
            # alerts. Without it, a customer answering an auto-reply went to the global admin@
            # inbox, so the reply-<token> loop, tenant attribution and the consent gate were all
            # bypassed (2026-11-12 email assessment, 3.3).
            headers = {**(headers or {}), "Reply-To": tenant["reply_address"]}
        body = row["body"]
        if row["kind"] in OWNER_KINDS and tenant.get("name"):
            body = body.rstrip() + f"\n\n— {tenant['name']}"
            if tenant.get("site_url"):
                body += f"\n{tenant['site_url']}"
        # Record the Message-ID before sending, so a bounce that comes back (through the
        # Cloudflare Worker or the Brevo webhook) can be matched to exactly this outbox row.
        sender = getattr(settings, "smtp_from", "") or ""
        message_id = row.get("message_id") or make_msgid(
            domain=(sender.rsplit("@", 1)[-1] or None))
        if not row.get("message_id"):
            try:
                await db.pool().execute(
                    "UPDATE outbox SET message_id=$2 WHERE id=$1", row["id"], message_id[:500])
            except Exception:  # noqa: BLE001 - never lose a send over a bookkeeping write
                # Matching then falls back to the recipient address; the mail still goes out.
                log.warning("could not persist message id for outbox row %s", row["id"])
        headers = {**(headers or {}), "Message-ID": message_id}
        await mailer.send_email(
            row["to_addr"], row["subject"] or f"Message from {tenant['name']}", body, headers,
            from_name=tenant.get("name") or None,
        )
        if row["kind"] == "email_secretary_reply":
            await casetimeline.mark_replied(
                row["tenant_id"], email=row["to_addr"], channel="email",
                default_cc=casetimeline.tenant_country_code(tenant),
            )
    else:
        await _finish(row["id"], "failed", f"unknown channel {row['channel']}")
        return
    await _finish(row["id"], "sent")


async def process_once() -> int:
    """Send everything that is due. Safe to run from several workers (SKIP LOCKED)."""
    if await flood_guard.paused():
        return 0  # operator kill switch: everything stays queued
    pool = db.pool()
    # Recover rows claimed by a worker that died mid-send.
    await pool.execute(
        "UPDATE outbox SET status = 'pending' WHERE status = 'sending' AND claimed_at < now() - interval '10 minutes'"
    )
    rows = await pool.fetch(
        """
        UPDATE outbox SET status = 'sending', attempts = attempts + 1, claimed_at = now()
        WHERE id IN (
            SELECT id FROM outbox WHERE status = 'pending' AND send_at <= now()
            ORDER BY send_at LIMIT 20 FOR UPDATE SKIP LOCKED
        )
        RETURNING *
        """
    )
    for record in rows:
        row = dict(record)
        try:
            await _deliver(row)
        except Exception as exc:  # one bad message must never stop the queue
            log.warning("outbox %s failed (attempt %s): %s", row["id"], row["attempts"], exc)
            if row["attempts"] >= MAX_ATTEMPTS:
                await _finish(row["id"], "failed", str(exc))
            else:
                await pool.execute(
                    "UPDATE outbox SET status = 'pending', last_error = $2, send_at = now() + $3 * interval '1 minute' "
                    "WHERE id = $1",
                    row["id"], str(exc)[:500], row["attempts"] * 2,
                )
    return len(rows)


# How long an SMS may wait for the phone's receipt before it is declared unconfirmed.
# /poll expires jobs the phone *claimed* but never receipted; this covers the case where
# the phone stops polling altogether (unpaired, revoked, app closed, lost receipt during a
# deploy), which previously left the row in awaiting_receipt forever and the owner never
# learned the alert did not go out.
STALE_SMS_INTERVAL = timedelta(minutes=15)
SMS_RECONCILE_SECONDS = 300


async def reconcile_stale_device_sms(breach: timedelta = STALE_SMS_INTERVAL) -> int:
    """Mark SMS rows whose phone never confirmed the send as failed, never silently in-flight.

    The owner must be able to tell "sent" from "we do not know". Nothing is retried here:
    a send that may have happened is reconciled by a human, per the device-SMS contract.
    """
    stalled = await db.pool().fetch(
        """UPDATE device_sms_jobs j SET status='uncertain', finished_at=now()
           FROM outbox o
           WHERE j.outbox_id=o.id AND j.status IN ('queued','claimed')
             AND o.channel='sms' AND o.status IN ('sending','awaiting_receipt')
             AND o.send_at < now() - $1::interval
           RETURNING j.outbox_id""",
        breach,
    )
    failed = 0
    for row in stalled:
        if row["outbox_id"] is None:
            continue
        await db.pool().execute(
            "UPDATE outbox SET status='failed', last_error=$2 "
            "WHERE id=$1 AND status IN ('sending','awaiting_receipt')",
            row["outbox_id"], "Phone never confirmed send; reconcile before retry",
        )
        failed += 1
    return failed


async def run_forever(stop: asyncio.Event) -> None:
    interval = max(get_settings().outbox_poll_seconds, 1)
    last_sweep = 0.0
    while not stop.is_set():
        try:
            await process_once()
        except Exception:
            log.exception("outbox loop error")
        if _time.monotonic() - last_sweep >= SMS_RECONCILE_SECONDS:
            last_sweep = _time.monotonic()
            try:
                stalled = await reconcile_stale_device_sms()
                if stalled:
                    log.warning("reconciled %s unconfirmed SMS row(s) as failed", stalled)
            except Exception:
                log.exception("sms receipt reconciliation error")
            try:
                # Imported here: channel_health imports this module.
                from . import channel_health
                await channel_health.escalate_failed_owner_alerts()
            except Exception:
                log.exception("owner alert escalation error")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass
