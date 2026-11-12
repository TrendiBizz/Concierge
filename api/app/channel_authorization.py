"""Explicit per-tenant channel authorization declarations.

An owner's authorization is distinct from provider ownership verification,
caller recording consent and actual deployment activation. This module never
enables external providers or starts a recording.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field

from . import db

Channel = Literal["telephone", "call_recording", "email_read", "email_send", "sms_read", "sms_send", "social"]
CHANNELS = ("telephone", "call_recording", "email_read", "email_send", "sms_read", "sms_send", "social")


class ChannelAuthorization(BaseModel):
    channel: Channel
    authorized: bool
    acknowledgement: bool = Field(
        description="Owner confirms the business controls this channel and has authority to authorize its use."
    )


async def record_authorization(
    tenant_id, actor_id, body: ChannelAuthorization, *,
    actor_kind: str = "owner", actor_label: str = "",
) -> dict:
    """Store a consent decision. The audit row is written by a database trigger.

    `actor_kind` distinguishes a real owner clicking (owner), an operator granting
    on the customer's behalf (operator), or an out-of-band direct-SQL change
    (direct, written by the trigger itself). That is the difference between "the
    customer agreed" and "we say they agreed".
    """
    if body.authorized and not body.acknowledgement:
        raise ValueError("Explicit authorization acknowledgement required")
    # No provider is activated by storing permission; revocation is immediate
    # for readiness reporting and leaves the audit log intact.
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('concierge.actor_kind', $1, true), "
                "set_config('concierge.actor_label', $2, true)",
                actor_kind, (actor_label or "")[:200],
            )
            row = await conn.fetchrow(
                """INSERT INTO tenant_channel_authorizations
                   (tenant_id,channel,authorized,actor_id,updated_at)
                   VALUES ($1,$2,$3,$4,now())
                   ON CONFLICT (tenant_id,channel) DO UPDATE SET
                     authorized=EXCLUDED.authorized,
                     actor_id=EXCLUDED.actor_id,
                     updated_at=now()
                   RETURNING authorized,updated_at""",
                tenant_id, body.channel, body.authorized, actor_id,
            )
    return {
        "channel": body.channel,
        "authorized": bool(row["authorized"]),
        "updated_at": row["updated_at"],
        "actor_kind": actor_kind,
        "provider_verified": False,
        "active": False,
    }


async def ownership(tenant_id) -> dict | None:
    """The tenant's owner principal, used when an operator grants on their behalf."""
    return await db.pool().fetchrow(
        """SELECT u.id FROM tenant_users u
           WHERE u.tenant_id=$1 AND u.role='owner' AND u.active AND u.password_hash <> ''
           ORDER BY u.created_at LIMIT 1""",
        tenant_id,
    )


async def audit_log(tenant_id, limit: int = 100) -> list[dict]:
    rows = await db.pool().fetch(
        """SELECT id,channel,authorized,actor_id,actor_kind,actor_label,created_at
           FROM tenant_channel_authorization_audit WHERE tenant_id=$1
           ORDER BY id DESC LIMIT $2""",
        tenant_id, limit,
    )
    return [dict(row) for row in rows]


async def is_authorized(tenant_id, channel: str) -> bool:
    """Fail closed if authorization is absent, revoked, or tenant mismatched."""
    if channel not in CHANNELS:
        return False
    return bool(await db.pool().fetchval(
        """SELECT authorized FROM tenant_channel_authorizations
           WHERE tenant_id=$1 AND channel=$2""",
        tenant_id, channel,
    ))


async def authorizations(tenant_id) -> dict:
    rows = await db.pool().fetch(
        """SELECT channel,authorized,updated_at
           FROM tenant_channel_authorizations WHERE tenant_id=$1""",
        tenant_id,
    )
    state = {r["channel"]: r for r in rows}
    return {
        key: {
            "authorized": bool(state[key]["authorized"]) if key in state else False,
            "updated_at": state[key]["updated_at"] if key in state else None,
            "provider_verified": False,
            "active": False,
        }
        for key in CHANNELS
    }


def readiness(channels: dict, checks: dict[str, bool]) -> dict:
    """Never activate from owner claims alone."""
    return {
        key: {
            "authorized": bool(value["authorized"]),
            "configured": bool(checks.get(key, False)),
            "provider_verified": False,
            "active": False,
            "missing": (
                (["owner_authorization"] if not value["authorized"] else [])
                + (["provider_configuration"] if not checks.get(key, False) else [])
                + ["real_provider_verification", "operator_activation"]
            ),
        }
        for key, value in channels.items()
    }
