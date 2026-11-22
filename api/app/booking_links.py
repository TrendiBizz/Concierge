"""N6 Customer self-serve booking reschedule & cancel links.

Signed HMAC tokens tied to (tenant_id, appointment_id) let a customer view, reschedule, or
cancel their own appointment without needing an account or exposing sequential IDs.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import html
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from . import db, owner_auth
from .config import get_settings

public_router = APIRouter(prefix="/booking", tags=["booking-links"])
owner_router = APIRouter(prefix="/owner/appointments", tags=["booking-links"])


def _secret() -> bytes:
    s = get_settings()
    raw = (s.unsubscribe_secret or s.admin_token or "trendi-booking-dev-key").strip()
    return hashlib.sha256(b"trendi:booking:v1:" + raw.encode("utf-8")).digest()


def make_manage_token(tenant_id, appointment_id) -> str:
    payload = f"{tenant_id}:{appointment_id}".encode("utf-8")
    b64 = base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")
    mac = hmac.new(_secret(), payload, hashlib.sha256).hexdigest()[:24]
    return f"{b64}.{mac}"


def verify_manage_token(token: str) -> tuple[str, str]:
    b64, sep, mac = (token or "").partition(".")
    if not sep or not b64 or not mac:
        raise HTTPException(400, "Invalid booking link")
    try:
        payload = base64.urlsafe_b64decode((b64 + "=" * (-len(b64) % 4)).encode("ascii"))
    except Exception:
        raise HTTPException(400, "Invalid booking link") from None
    expected = hmac.new(_secret(), payload, hashlib.sha256).hexdigest()[:24]
    if not hmac.compare_digest(mac, expected):
        raise HTTPException(400, "Invalid booking link")
    parts = payload.decode("utf-8").split(":")
    if len(parts) != 2:
        raise HTTPException(400, "Invalid booking link")
    return parts[0], parts[1]


def manage_url(tenant_id, appointment_id) -> str:
    base = get_settings().public_base_url.rstrip("/")
    return f"{base}/booking/{make_manage_token(tenant_id, appointment_id)}"


@owner_router.get("/{appointment_id}/manage-link")
async def owner_get_manage_link(appointment_id: str, user: dict = Depends(owner_auth.current_user)):
    row = await db.pool().fetchrow(
        "SELECT id FROM appointments WHERE id=$1 AND tenant_id=$2",
        appointment_id, user["tenant_id"],
    )
    if not row:
        raise HTTPException(404, "Appointment not found")
    token = make_manage_token(user["tenant_id"], row["id"])
    return {"token": token, "url": manage_url(user["tenant_id"], row["id"])}


@public_router.get("/{token}", response_class=HTMLResponse)
async def public_booking_page(token: str):
    tenant_id, appointment_id = verify_manage_token(token)
    row = await db.pool().fetchrow(
        "SELECT a.id, a.name, a.starts_at, a.ends_at, a.status, t.name AS business_name "
        "FROM appointments a JOIN tenants t ON t.id=a.tenant_id "
        "WHERE a.id=$1 AND a.tenant_id=$2",
        appointment_id, tenant_id,
    )
    if not row:
        raise HTTPException(404, "Booking not found")
    biz = html.escape(row["business_name"] or "Your booking")
    who = html.escape(row["name"] or "Customer")
    status = html.escape(row["status"] or "booked")
    when = html.escape(row["starts_at"].isoformat())
    return HTMLResponse(
        f"<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        f"<title>Manage booking — {biz}</title></head><body>"
        f"<h1>{biz}</h1><p>Booking for <strong>{who}</strong></p>"
        f"<p>Time: {when} · Status: <strong>{status}</strong></p>"
        f"<form method='post' action='/booking/{html.escape(token)}/cancel'>"
        f"<button type='submit'>Cancel this booking</button></form>"
        f"</body></html>"
    )


@public_router.post("/{token}/cancel")
async def public_booking_cancel(token: str):
    tenant_id, appointment_id = verify_manage_token(token)
    row = await db.pool().fetchrow(
        "UPDATE appointments SET status='cancelled', calendar_state='pending' "
        "WHERE id=$1 AND tenant_id=$2 AND status='booked' RETURNING id, status",
        appointment_id, tenant_id,
    )
    if not row:
        raise HTTPException(404, "Booking not found or already cancelled")
    return {"id": str(row["id"]), "status": row["status"]}


class RescheduleBody(BaseModel):
    starts_at: datetime
    ends_at: datetime | None = None


@public_router.post("/{token}/reschedule")
async def public_booking_reschedule(token: str, body: RescheduleBody):
    tenant_id, appointment_id = verify_manage_token(token)
    existing = await db.pool().fetchrow(
        "SELECT id, starts_at, ends_at, status FROM appointments WHERE id=$1 AND tenant_id=$2",
        appointment_id, tenant_id,
    )
    if not existing or existing["status"] != "booked":
        raise HTTPException(404, "Active booking not found")
    start = body.starts_at if body.starts_at.tzinfo else body.starts_at.replace(tzinfo=timezone.utc)
    if start <= datetime.now(timezone.utc):
        raise HTTPException(400, "New time must be in the future")
    duration = existing["ends_at"] - existing["starts_at"]
    end = body.ends_at if body.ends_at else (start + duration)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    if end <= start:
        raise HTTPException(400, "End time must be after start time")
    await db.pool().execute(
        "UPDATE appointments SET starts_at=$3, ends_at=$4, calendar_state='pending', calendar_retry_at=now() "
        "WHERE id=$1 AND tenant_id=$2",
        appointment_id, tenant_id, start, end,
    )
    return {
        "id": str(existing["id"]),
        "status": "booked",
        "starts_at": start.isoformat(),
        "ends_at": end.isoformat(),
    }
