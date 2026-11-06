"""Follow-up engine: a durable queue of SMS / email messages with retries, opt-outs and quiet hours."""

import asyncio
import logging
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from . import db, mailer, sms, tenants
from .config import get_settings
from .contact import contact_key

log = logging.getLogger("concierge.outbox")

MAX_ATTEMPTS = 3
# Kinds that go to the business owner, not a visitor: never blocked by opt-outs.
OWNER_KINDS = {"owner_alert"}


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
) -> bool:
    """Queue a message. Returns False if an identical dedupe_key already exists."""
    result = await db.pool().execute(
        """
        INSERT INTO outbox (tenant_id, kind, channel, to_addr, subject, body, send_at, dedupe_key,
                            appointment_id, lead_id)
        VALUES ($1, $2, $3, $4, $5, $6, COALESCE($7, now()), $8, $9, $10)
        ON CONFLICT (dedupe_key) WHERE dedupe_key IS NOT NULL DO NOTHING
        """,
        tenant_id, kind, channel, to_addr, subject, body, send_at, dedupe_key, appointment_id, lead_id,
    )
    return result.endswith("1")


async def cancel_for_appointment(appointment_id) -> int:
    result = await db.pool().execute(
        "UPDATE outbox SET status = 'cancelled' WHERE appointment_id = $1 AND status = 'pending'",
        appointment_id,
    )
    return int(result.split()[-1])


async def opt_out(tenant_id, contact: str) -> None:
    await db.pool().execute(
        "INSERT INTO opt_outs (tenant_id, contact) VALUES ($1, $2) ON CONFLICT DO NOTHING",
        tenant_id, contact_key(contact, get_settings().default_country_code),
    )


async def opt_in(tenant_id, contact: str) -> None:
    await db.pool().execute(
        "DELETE FROM opt_outs WHERE tenant_id = $1 AND contact = $2",
        tenant_id, contact_key(contact, get_settings().default_country_code),
    )


async def is_opted_out(tenant_id, contact: str) -> bool:
    found = await db.pool().fetchval(
        "SELECT 1 FROM opt_outs WHERE tenant_id = $1 AND contact = $2",
        tenant_id, contact_key(contact, get_settings().default_country_code),
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

    if row["kind"] not in OWNER_KINDS and await is_opted_out(row["tenant_id"], row["to_addr"]):
        await _finish(row["id"], "skipped", "opted_out")
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
        await sms.send_sms(row["to_addr"], row["body"], tenant.get("sms_from"))
    elif row["channel"] == "email":
        if not settings.email_configured:
            await _finish(row["id"], "skipped", "email_not_configured")
            return
        await mailer.send_email(row["to_addr"], row["subject"] or f"Message from {tenant['name']}", row["body"])
    else:
        await _finish(row["id"], "failed", f"unknown channel {row['channel']}")
        return
    await _finish(row["id"], "sent")


async def process_once() -> int:
    """Send everything that is due. Safe to run from several workers (SKIP LOCKED)."""
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


async def run_forever(stop: asyncio.Event) -> None:
    interval = max(get_settings().outbox_poll_seconds, 1)
    while not stop.is_set():
        try:
            await process_once()
        except Exception:
            log.exception("outbox loop error")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass
