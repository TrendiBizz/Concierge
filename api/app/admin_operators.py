"""Per-operator admin credentials and immutable admin audit trail.

Replaces reliance on a single shared static ADMIN_TOKEN while remaining backward-compatible
with existing scripts/healthchecks that still present ADMIN_TOKEN.
"""
from __future__ import annotations

import hashlib
import secrets
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from . import db
from .security import require_admin

router = APIRouter(prefix="/admin", tags=["admin-operators"])


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def verify_operator_token(token: str) -> dict | None:
    """Look up an active per-operator admin token. Returns operator dict or None."""
    if not token or len(token) > 256:
        return None
    try:
        pool = db.pool()
    except RuntimeError:
        return None
    row = await pool.fetchrow(
        "SELECT id, name, email, role FROM admin_operators WHERE token_hash=$1 AND active",
        _digest(token),
    )
    if not row:
        return None
    await pool.execute("UPDATE admin_operators SET last_used_at=now() WHERE id=$1", row["id"])
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "email": row["email"],
        "role": row["role"],
        "legacy": False,
    }


async def record_audit(
    operator: dict | None,
    *,
    action: str,
    path: str,
    method: str,
    ip: str = "",
    detail: str = "",
) -> None:
    """Best-effort append to admin_audit_log; never breaks the underlying admin call."""
    try:
        pool = db.pool()
    except RuntimeError:
        return
    op_id = operator.get("id") if operator and not operator.get("legacy") else None
    op_name = (operator or {}).get("name") or "legacy-admin-token"
    try:
        await pool.execute(
            "INSERT INTO admin_audit_log(operator_id, operator_name, action, path, method, ip, detail) "
            "VALUES($1, $2, $3, $4, $5, $6, $7)",
            op_id, op_name[:120], action[:120], path[:300], method[:16], ip[:80], detail[:500],
        )
    except Exception:
        pass


class OperatorCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=3, max_length=320)
    role: Literal["operator", "superadmin"] = "operator"


@router.get("/operators", dependencies=[Depends(require_admin)])
async def list_operators():
    rows = await db.pool().fetch(
        "SELECT id, name, email, role, active, created_at, last_used_at "
        "FROM admin_operators ORDER BY created_at DESC"
    )
    return {
        "operators": [
            {
                "id": str(r["id"]),
                "name": r["name"],
                "email": r["email"],
                "role": r["role"],
                "active": r["active"],
                "created_at": r["created_at"].isoformat(),
                "last_used_at": r["last_used_at"].isoformat() if r["last_used_at"] else None,
            }
            for r in rows
        ]
    }


@router.post("/operators", status_code=201, dependencies=[Depends(require_admin)])
async def create_operator(body: OperatorCreate):
    raw_token = "adm_" + secrets.token_urlsafe(32)
    email = body.email.strip().lower()
    row = await db.pool().fetchrow(
        "INSERT INTO admin_operators(name, email, role, token_hash) "
        "VALUES($1, $2, $3, $4) RETURNING id, created_at",
        body.name.strip(), email, body.role, _digest(raw_token),
    )
    return {
        "id": str(row["id"]),
        "name": body.name.strip(),
        "email": email,
        "role": body.role,
        "token": raw_token,  # shown once
        "created_at": row["created_at"].isoformat(),
    }


@router.delete("/operators/{operator_id}", dependencies=[Depends(require_admin)])
async def revoke_operator(operator_id: str):
    res = await db.pool().execute(
        "UPDATE admin_operators SET active=false WHERE id=$1", operator_id
    )
    if res.endswith("0"):
        raise HTTPException(404, "Operator not found")
    return {"ok": True}


@router.get("/audit-log", dependencies=[Depends(require_admin)])
async def get_audit_log(limit: int = Query(default=100, ge=1, le=500)):
    rows = await db.pool().fetch(
        "SELECT id, operator_id, operator_name, action, path, method, ip, detail, created_at "
        "FROM admin_audit_log ORDER BY created_at DESC LIMIT $1",
        limit,
    )
    return {
        "entries": [
            {
                "id": r["id"],
                "operator_id": str(r["operator_id"]) if r["operator_id"] else None,
                "operator_name": r["operator_name"],
                "action": r["action"],
                "path": r["path"],
                "method": r["method"],
                "ip": r["ip"],
                "detail": r["detail"],
                "created_at": r["created_at"].isoformat(),
            }
            for r in rows
        ]
    }
