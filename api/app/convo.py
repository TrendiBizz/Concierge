"""Conversation helpers shared by web chat, voice logging, tools and SMS."""

import json
import re

from fastapi import HTTPException

from . import db


def clean_utm(utm: dict[str, str] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, value in (utm or {}).items():
        if key.startswith("utm_") and len(out) < 10:
            out[key[:40]] = str(value)[:200]
    return out


def clean_session(session_id: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "", session_id)[:64]
    if len(cleaned) < 8:
        raise HTTPException(status_code=400, detail="Invalid session_id")
    return cleaned


async def get_or_create(tenant: dict, session_id: str, channel: str, page_url: str | None, utm: dict | None):
    row = await db.pool().fetchrow(
        """
        INSERT INTO conversations (tenant_id, session_id, channel, page_url, utm)
        VALUES ($1, $2, $3, $4, $5::jsonb)
        ON CONFLICT (tenant_id, session_id, channel)
        DO UPDATE SET page_url = COALESCE(conversations.page_url, EXCLUDED.page_url)
        RETURNING id
        """,
        tenant["id"],
        session_id,
        channel,
        (page_url or "")[:500] or None,
        json.dumps(clean_utm(utm)),
    )
    return row["id"]


async def save_message(conversation_id, role: str, content: str, flag: str | None = None) -> None:
    await db.pool().execute(
        "INSERT INTO messages (conversation_id, role, content, flag) VALUES ($1, $2, $3, $4)",
        conversation_id,
        role,
        content[:4000],
        flag,
    )


async def get_pending_booking(conversation_id) -> dict | None:
    raw = await db.pool().fetchval("SELECT pending_booking FROM conversations WHERE id = $1", conversation_id)
    if raw is None:
        return None
    return json.loads(raw) if isinstance(raw, str) else raw


async def set_pending_booking(conversation_id, value: dict | None) -> None:
    await db.pool().execute(
        "UPDATE conversations SET pending_booking = $2::jsonb WHERE id = $1",
        conversation_id,
        json.dumps(value) if value is not None else None,
    )
