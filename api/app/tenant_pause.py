"""One switch a business owner can throw to stop Concierge acting for them.

Pausing is meant to be immediate and complete across every channel: while it is on, no model
call produces an answer, nothing is queued to a customer, and nothing is published. Inbound is
still captured, so pausing never costs the owner a lead -- that is the difference between "the
robot is quiet" and "the business stopped listening".

This is deliberately a separate switch from the operator's outbound kill switch (flood_guard),
which pauses the whole deployment. A customer must never be able to pause every other business.
"""
import logging

from . import db

log = logging.getLogger("concierge.pause")

# What a website visitor is told while the business has paused the assistant. It is the same
# thing a receptionist would say, and it is not the model speaking: pausing means no model call.
HOLDING_REPLY = "Thanks — we have your message. Someone will get back to you shortly."


async def state(tenant_id) -> dict:
    row = await db.pool().fetchrow(
        "SELECT paused_at, paused_by FROM tenants WHERE id=$1", tenant_id)
    if not row:
        return {"paused": False, "since": None, "by": None}
    return {
        "paused": row["paused_at"] is not None,
        "since": row["paused_at"].isoformat() if row["paused_at"] else None,
        "by": row["paused_by"],
    }


async def set_paused(tenant_id, paused: bool, by: str) -> dict:
    await db.pool().execute(
        "UPDATE tenants SET paused_at=CASE WHEN $2 THEN now() ELSE NULL END, "
        "paused_by=CASE WHEN $2 THEN $3 ELSE NULL END WHERE id=$1",
        tenant_id, bool(paused), (by or "")[:200],
    )
    return await state(tenant_id)


async def is_paused(tenant: dict) -> bool:
    """Read through every time: a pause must take effect on the very next message.

    Fails open. A transient database error must not silently silence every business's assistant;
    the error is logged loudly instead. The action the owner takes (messaging us) is what fixes a
    stuck pause, so a wrong "paused" answer from a broken read would be the worse failure.
    """
    if tenant.get("paused_at"):
        return True
    try:
        return bool(await db.pool().fetchval(
            "SELECT paused_at IS NOT NULL FROM tenants WHERE id=$1", tenant["id"]))
    except Exception:  # noqa: BLE001 - see docstring
        log.exception("could not read pause state for tenant %s", tenant.get("slug"))
        return False
