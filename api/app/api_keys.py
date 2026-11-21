"""Tenant-scoped API keys and the small public REST API (N6 phase 1).

Unlocks Zapier / Make / any script: an owner creates a key in Studio, the key is shown once, and
only its SHA-256 hash is stored. Keys are read-only and always scoped to one tenant; every query
below filters on the tenant of the key, never on anything the caller sends.
"""
from __future__ import annotations

import hashlib
import secrets

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from . import db, owner_auth, portability

owner_router = APIRouter(tags=["api-keys"])
api_router = APIRouter(prefix="/api/v1", tags=["public-api"])

KEY_PREFIX = "cnc_"
MAX_KEYS = 10


def _hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


async def create_key(tenant_id, name: str) -> dict:
    count = await db.pool().fetchval(
        "SELECT count(*) FROM tenant_api_keys WHERE tenant_id=$1 AND revoked_at IS NULL", tenant_id)
    if count >= MAX_KEYS:
        raise HTTPException(409, f"At most {MAX_KEYS} active keys")
    key = KEY_PREFIX + secrets.token_urlsafe(32)
    row = await db.pool().fetchrow(
        "INSERT INTO tenant_api_keys (tenant_id, name, prefix, key_hash) VALUES ($1,$2,$3,$4) "
        "RETURNING id, created_at", tenant_id, name.strip()[:80], key[:8], _hash(key))
    return {"id": str(row["id"]), "name": name.strip()[:80], "key": key,
            "created_at": row["created_at"].isoformat()}


async def list_keys(tenant_id) -> list[dict]:
    rows = await db.pool().fetch(
        "SELECT id, name, prefix, scope, created_at, last_used_at, revoked_at FROM tenant_api_keys "
        "WHERE tenant_id=$1 ORDER BY created_at DESC", tenant_id)
    return [{"id": str(r["id"]), "name": r["name"], "prefix": r["prefix"], "scope": r["scope"],
             "created_at": r["created_at"].isoformat(),
             "last_used_at": r["last_used_at"].isoformat() if r["last_used_at"] else None,
             "revoked": r["revoked_at"] is not None} for r in rows]


async def revoke_key(tenant_id, key_id) -> bool:
    result = await db.pool().execute(
        "UPDATE tenant_api_keys SET revoked_at=now() WHERE id=$1 AND tenant_id=$2 AND revoked_at IS NULL",
        key_id, tenant_id)
    return result.endswith(" 1")


async def authenticate(authorization: str = Header(default="")) -> dict:
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.startswith(KEY_PREFIX) or len(token) > 128:
        raise HTTPException(401, "Bearer API key required")
    row = await db.pool().fetchrow(
        "UPDATE tenant_api_keys SET last_used_at=now() WHERE key_hash=$1 AND revoked_at IS NULL "
        "RETURNING tenant_id", _hash(token))
    if not row:
        raise HTTPException(401, "Invalid or revoked API key")
    return {"tenant_id": row["tenant_id"]}


# ---- owner (Studio) management ---------------------------------------------------------------
class KeyIn(BaseModel):
    name: str = Field(default="", max_length=80)


@owner_router.get("/owner/api-keys")
async def owner_list_keys(user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    return {"keys": await list_keys(user["tenant_id"]), "events": list(portability.EVENTS)}


@owner_router.post("/owner/api-keys")
async def owner_create_key(body: KeyIn, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    return await create_key(user["tenant_id"], body.name)


@owner_router.delete("/owner/api-keys/{key_id}")
async def owner_revoke_key(key_id: str, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    try:
        ok = await revoke_key(user["tenant_id"], key_id)
    except Exception:  # malformed uuid
        raise HTTPException(404, "Key not found") from None
    if not ok:
        raise HTTPException(404, "Key not found")
    return {"revoked": True}


# ---- public read API -------------------------------------------------------------------------
@api_router.get("/contacts")
async def api_contacts(key: dict = Depends(authenticate), limit: int = Query(200, ge=1, le=1000)):
    return {"contacts": (await portability.export_contacts(key["tenant_id"]))[:limit]}


@api_router.get("/enquiries")
async def api_enquiries(key: dict = Depends(authenticate), limit: int = Query(50, ge=1, le=200)):
    rows = await db.pool().fetch(
        "SELECT id, name, company, phone, email, message, channel, status, created_at FROM leads "
        "WHERE tenant_id=$1 ORDER BY created_at DESC LIMIT $2", key["tenant_id"], limit)
    return {"enquiries": [{**{k: r[k] for k in ("name", "company", "phone", "email", "message",
                                               "channel", "status")},
                           "id": str(r["id"]), "created_at": r["created_at"].isoformat()}
                          for r in rows]}


@api_router.get("/appointments")
async def api_appointments(key: dict = Depends(authenticate), limit: int = Query(50, ge=1, le=200)):
    rows = await db.pool().fetch(
        "SELECT id, name, phone, email, starts_at, ends_at, notes, status FROM appointments "
        "WHERE tenant_id=$1 ORDER BY starts_at DESC LIMIT $2", key["tenant_id"], limit)
    return {"appointments": [{**{k: r[k] for k in ("name", "phone", "email", "notes", "status")},
                              "id": str(r["id"]), "starts_at": r["starts_at"].isoformat(),
                              "ends_at": r["ends_at"].isoformat()} for r in rows]}


@api_router.get("/events")
async def api_events(key: dict = Depends(authenticate)):
    """The event names a webhook can receive (for Zapier/Make trigger setup)."""
    return {"events": list(portability.EVENTS)}
