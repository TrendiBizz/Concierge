"""Automated non-audio retention purge (NZ Privacy Act IPP 9 / AU APP 11).

Audio recordings already have a 30-day purge in `voice_records.py`. This module adds
per-tenant configurable retention windows for non-audio personal data:
  - `retention_days_messages` (default 365; 0 = disabled)
  - `retention_days_leads` (default 730; 0 = disabled)
  - `retention_days_outbox` (default 180; 0 = disabled)
  - `retention_days_email_drafts` (default 365; 0 = disabled)

Expired messages/outbox/email_drafts are purged or anonymized; expired leads are anonymized
(keeping aggregate counts intact while removing personal identifiers).
"""
from __future__ import annotations

import asyncio
import logging

from . import db

log = logging.getLogger("concierge.privacy_retention")


async def purge_for_tenant(tenant_id) -> dict[str, int]:
    """Run retention purge for a single tenant according to its configured retention windows."""
    row = await db.pool().fetchrow(
        "SELECT retention_days_messages, retention_days_leads, "
        "retention_days_outbox, retention_days_email_drafts "
        "FROM tenants WHERE id=$1",
        tenant_id,
    )
    if not row:
        return {"messages": 0, "leads": 0, "outbox": 0, "email_drafts": 0}
    counts = {"messages": 0, "leads": 0, "outbox": 0, "email_drafts": 0}
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            msg_days = int(row["retention_days_messages"] or 0)
            if msg_days > 0:
                counts["messages"] = int(await conn.fetchval(
                    "WITH d AS ("
                    "  DELETE FROM messages m USING conversations c "
                    "  WHERE m.conversation_id = c.id AND c.tenant_id = $1 "
                    "    AND m.created_at < now() - make_interval(days => $2) "
                    "  RETURNING 1"
                    ") SELECT count(*) FROM d",
                    tenant_id, msg_days,
                ) or 0)

            outbox_days = int(row["retention_days_outbox"] or 0)
            if outbox_days > 0:
                counts["outbox"] = int(await conn.fetchval(
                    "WITH u AS ("
                    "  UPDATE outbox SET to_addr='', subject='Purged (retention)', body='' "
                    "  WHERE tenant_id=$1 AND status IN ('sent','failed','skipped','cancelled') "
                    "    AND to_addr <> '' "
                    "    AND created_at < now() - make_interval(days => $2) "
                    "  RETURNING 1"
                    ") SELECT count(*) FROM u",
                    tenant_id, outbox_days,
                ) or 0)

            draft_days = int(row["retention_days_email_drafts"] or 0)
            if draft_days > 0:
                counts["email_drafts"] = int(await conn.fetchval(
                    "WITH u AS ("
                    "  UPDATE email_drafts SET sender='', subject='Purged (retention)', "
                    "    inbound_body='', reply_body='' "
                    "  WHERE tenant_id=$1 AND sender <> '' "
                    "    AND created_at < now() - make_interval(days => $2) "
                    "  RETURNING 1"
                    ") SELECT count(*) FROM u",
                    tenant_id, draft_days,
                ) or 0)

            lead_days = int(row["retention_days_leads"] or 0)
            if lead_days > 0:
                counts["leads"] = int(await conn.fetchval(
                    "WITH u AS ("
                    "  UPDATE leads SET name='', email='', phone='', message='', company='', "
                    "    erased_at=COALESCE(erased_at, now()) "
                    "  WHERE tenant_id=$1 AND erased_at IS NULL "
                    "    AND created_at < now() - make_interval(days => $2) "
                    "  RETURNING 1"
                    ") SELECT count(*) FROM u",
                    tenant_id, lead_days,
                ) or 0)
    return counts


async def purge_all_tenants() -> dict[str, int]:
    rows = await db.pool().fetch(
        "SELECT id FROM tenants WHERE retention_days_messages > 0 "
        "OR retention_days_leads > 0 OR retention_days_outbox > 0 OR retention_days_email_drafts > 0"
    )
    totals = {"messages": 0, "leads": 0, "outbox": 0, "email_drafts": 0}
    for r in rows:
        res = await purge_for_tenant(r["id"])
        for k in totals:
            totals[k] += res[k]
    return totals


async def run_forever(stop: asyncio.Event, interval_seconds: int = 3600) -> None:
    while not stop.is_set():
        try:
            await purge_all_tenants()
        except Exception:
            log.warning("Non-audio retention purge will retry")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval_seconds)
        except asyncio.TimeoutError:
            pass
