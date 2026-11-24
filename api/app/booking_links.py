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
    s = get_settings()
    portal_base = (getattr(s, "owner_portal_url", "") or "").strip()
    if portal_base:
        base = portal_base.rstrip("/").rsplit("/owner-ui", 1)[0]
    else:
        base = s.public_base_url.rstrip("/")
    return f"{base}/booking/{make_manage_token(tenant_id, appointment_id)}"


class OwnerAppointmentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    starts_at: datetime
    ends_at: datetime | None = None
    phone: str = Field(default="", max_length=40)
    email: str = Field(default="", max_length=200)
    notes: str = Field(default="", max_length=500)
    consent_contact: bool = True


class OwnerAppointmentUpdate(BaseModel):
    status: str | None = Field(default=None, pattern="^(booked|completed|cancelled|no_show)$")
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=500)


@owner_router.post("", status_code=201)
async def owner_create_appointment(body: OwnerAppointmentCreate, user: dict = Depends(owner_auth.current_user)):
    """Create an appointment directly from Studio CRM (with conflict check, contact link, reminders & calendar sync)."""
    owner_auth.require_role(user, "editor")
    from . import automation, calendar_connection, casetimeline, portability, tenants
    from .contact import is_email, normalize_phone

    tenant = await tenants.get_by_id(user["tenant_id"])
    if not tenant:
        raise HTTPException(404, "Tenant not found")
    start = body.starts_at if body.starts_at.tzinfo else body.starts_at.replace(tzinfo=timezone.utc)
    duration = timedelta(minutes=int(tenant.get("slot_minutes") or 30))
    end = body.ends_at if body.ends_at else (start + duration)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    if end <= start:
        raise HTTPException(400, "End time must be after start time")
    phone = normalize_phone(body.phone, casetimeline.tenant_country_code(tenant)) or body.phone.strip()[:40]
    email = body.email.strip() if is_email(body.email) else ""
    case = await casetimeline.reconcile(
        tenant["id"], phone=phone, email=email, name=body.name.strip(),
        default_cc=casetimeline.tenant_country_code(tenant), source="manual",
    )
    case_id = case["id"] if case else None
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", str(tenant["id"]))
            clash = await conn.fetchval(
                "SELECT 1 FROM appointments WHERE tenant_id=$1 AND status='booked' AND starts_at < $3 AND ends_at > $2 LIMIT 1",
                tenant["id"], start, end,
            )
            if clash:
                raise HTTPException(409, "Another booked appointment overlaps that time")
            lead = await conn.fetchrow(
                "INSERT INTO leads(tenant_id,name,email,phone,message,channel,status,consent_contact,case_id) "
                "VALUES($1,$2,$3,$4,$5,'manual','booked',$6,$7) RETURNING *",
                tenant["id"], body.name.strip(), email, phone,
                f"Booked appointment for {automation.fmt_local(tenant, start)}. {body.notes.strip()}".strip(),
                body.consent_contact, case_id,
            )
            appt = await conn.fetchrow(
                "INSERT INTO appointments(tenant_id,lead_id,starts_at,ends_at,name,phone,email,notes,consent_contact,calendar_sync_requested) "
                "VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,true) RETURNING *",
                tenant["id"], lead["id"], start, end, body.name.strip(), phone, email, body.notes.strip(), body.consent_contact,
            )
    appt_dict = dict(appt)
    await portability.emit(tenant["id"], "appointment.booked", {
        "appointment_id": str(appt["id"]), "starts_at": start.isoformat(), "ends_at": end.isoformat(),
        "name": body.name.strip(), "phone": phone, "email": email, "notes": body.notes.strip(),
        "case_key": case["case_key"] if case else "",
    })
    if case:
        try:
            await casetimeline.record(
                tenant["id"], case_key=case["case_key"], channel="chat", direction="outbound",
                source_key=f"appointment:{appt['id']}",
                body=f"Booked appointment for {automation.fmt_local(tenant, start)}."
                     + (f" {body.notes.strip()}" if body.notes.strip() else ""),
            )
        except Exception:
            pass
    await calendar_connection.sync_one(appt["id"])
    await calendar_connection.notify_synced(appt["id"])
    appt_dict["id"] = str(appt_dict["id"])
    appt_dict["starts_at"] = appt_dict["starts_at"].isoformat()
    appt_dict["ends_at"] = appt_dict["ends_at"].isoformat()
    return appt_dict


@owner_router.patch("/{appointment_id}")
async def owner_update_appointment(appointment_id: str, body: OwnerAppointmentUpdate, user: dict = Depends(owner_auth.current_user)):
    """Update status, reschedule, or edit notes on an appointment from Studio CRM."""
    owner_auth.require_role(user, "editor")
    from . import automation, calendar_connection, outbox, portability, tenants

    tenant = await tenants.get_by_id(user["tenant_id"])
    existing = await db.pool().fetchrow(
        "SELECT * FROM appointments WHERE id=$1::uuid AND tenant_id=$2",
        appointment_id, user["tenant_id"],
    )
    if not existing:
        raise HTTPException(404, "Appointment not found")
    new_status = body.status or existing["status"]
    new_start = (body.starts_at if body.starts_at.tzinfo else body.starts_at.replace(tzinfo=timezone.utc)) if body.starts_at else existing["starts_at"]
    if body.ends_at:
        new_end = body.ends_at if body.ends_at.tzinfo else body.ends_at.replace(tzinfo=timezone.utc)
    elif body.starts_at:
        new_end = new_start + (existing["ends_at"] - existing["starts_at"])
    else:
        new_end = existing["ends_at"]
    if new_end <= new_start:
        raise HTTPException(400, "End time must be after start time")
    new_notes = body.notes if body.notes is not None else existing["notes"]
    rescheduled = (new_start != existing["starts_at"] or new_end != existing["ends_at"])
    status_changed = (new_status != existing["status"])

    async with db.pool().acquire() as conn:
        async with conn.transaction():
            if rescheduled and new_status == "booked":
                await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", str(user["tenant_id"]))
                clash = await conn.fetchval(
                    "SELECT 1 FROM appointments WHERE tenant_id=$1 AND id<>$2::uuid AND status='booked' "
                    "AND starts_at < $4 AND ends_at > $3 LIMIT 1",
                    user["tenant_id"], appointment_id, new_start, new_end,
                )
                if clash:
                    raise HTTPException(409, "Another booked appointment overlaps that time")
            row = await conn.fetchrow(
                "UPDATE appointments SET status=$3, starts_at=$4, ends_at=$5, notes=$6, "
                "calendar_state=CASE WHEN $7 THEN 'pending' ELSE calendar_state END, "
                "calendar_retry_at=CASE WHEN $7 THEN now() ELSE calendar_retry_at END "
                "WHERE id=$1::uuid AND tenant_id=$2 RETURNING *",
                appointment_id, user["tenant_id"], new_status, new_start, new_end, new_notes,
                rescheduled or new_status in ("cancelled", "no_show"),
            )
    appt = dict(row)
    if status_changed and tenant:
        await automation.on_appointment_status(tenant, appt, new_status)
        if new_status in ("cancelled", "no_show"):
            await portability.emit(tenant["id"], f"appointment.{new_status}", {
                "appointment_id": str(appt["id"]), "starts_at": appt["starts_at"].isoformat(),
                "ends_at": appt["ends_at"].isoformat(), "name": appt["name"],
            })
            await calendar_connection.sync_one(appt["id"])
    elif rescheduled and tenant:
        await outbox.cancel_for_appointment(appt["id"])
        await portability.emit(tenant["id"], "appointment.rescheduled", {
            "appointment_id": str(appt["id"]), "starts_at": appt["starts_at"].isoformat(),
            "ends_at": appt["ends_at"].isoformat(), "name": appt["name"], "notes": appt["notes"],
        })
        await calendar_connection.sync_one(appt["id"])
    appt["id"] = str(appt["id"])
    appt["starts_at"] = appt["starts_at"].isoformat()
    appt["ends_at"] = appt["ends_at"].isoformat()
    return appt


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
    from . import automation
    tenant_id, appointment_id = verify_manage_token(token)
    row = await db.pool().fetchrow(
        "SELECT a.id, a.name, a.starts_at, a.ends_at, a.status, t.name AS business_name, t.timezone "
        "FROM appointments a JOIN tenants t ON t.id=a.tenant_id "
        "WHERE a.id=$1 AND a.tenant_id=$2",
        appointment_id, tenant_id,
    )
    if not row:
        raise HTTPException(404, "Booking not found")
    biz = html.escape(row["business_name"] or "Your booking")
    who = html.escape(row["name"] or "Customer")
    status = html.escape(row["status"] or "booked")
    when = html.escape(automation.fmt_local({"timezone": row["timezone"] or "UTC"}, row["starts_at"]))
    tok = html.escape(token)
    actions = ""
    if row["status"] == "booked":
        actions = (
            f"<form method='post' action='/booking/{tok}/cancel' style='margin:16px 0'>"
            f"<button type='submit'>Cancel this booking</button></form>"
            f"<div style='margin:16px 0'><h2>Reschedule</h2>"
            f"<input id='new-time' type='datetime-local' /> "
            f"<button type='button' onclick=\"(async()=>{{const v=document.getElementById('new-time').value;if(!v)return;"
            f"const r=await fetch('/booking/{tok}/reschedule',{{method:'POST',headers:{{'Content-Type':'application/json'}},"
            f"body:JSON.stringify({{starts_at:new Date(v).toISOString()}})}});if(r.ok)location.reload();else alert((await r.json()).detail||'Could not reschedule');}})()\">"
            f"Save new time</button></div>"
        )
    return HTMLResponse(
        f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>Manage booking — {biz}</title></head><body style='font-family:system-ui,sans-serif;max-width:560px;margin:40px auto;padding:0 16px'>"
        f"<h1>{biz}</h1><p>Booking for <strong>{who}</strong></p>"
        f"<p>Time: {when} · Status: <strong>{status}</strong></p>{actions}"
        f"</body></html>"
    )


@public_router.post("/{token}/cancel")
async def public_booking_cancel(token: str):
    from . import automation, calendar_connection, owner_notifications, portability, tenants
    tenant_id, appointment_id = verify_manage_token(token)
    row = await db.pool().fetchrow(
        "UPDATE appointments SET status='cancelled', calendar_state='pending', calendar_retry_at=now() "
        "WHERE id=$1 AND tenant_id=$2 AND status='booked' RETURNING *",
        appointment_id, tenant_id,
    )
    if not row:
        raise HTTPException(404, "Booking not found or already cancelled")
    appt = dict(row)
    tenant = await tenants.get_by_id(tenant_id)
    if tenant:
        await automation.on_appointment_status(tenant, appt, "cancelled")
        when = automation.fmt_local(tenant, appt["starts_at"])
        await owner_notifications.queue(
            tenant,
            f"Appointment cancelled: {appt['name']} — {when}",
            f"{appt['name']} cancelled their booking for {when}.\nPhone: {appt.get('phone') or '-'}\nEmail: {appt.get('email') or '-'}",
            f"appt:{appt['id']}:cancelled",
        )
        await portability.emit(tenant["id"], "appointment.cancelled", {
            "appointment_id": str(appt["id"]), "starts_at": appt["starts_at"].isoformat(),
            "ends_at": appt["ends_at"].isoformat(), "name": appt["name"],
        })
        await calendar_connection.sync_one(appt["id"])
    return {"id": str(row["id"]), "status": row["status"]}


class RescheduleBody(BaseModel):
    starts_at: datetime
    ends_at: datetime | None = None


@public_router.post("/{token}/reschedule")
async def public_booking_reschedule(token: str, body: RescheduleBody):
    from . import automation, calendar_connection, outbox, owner_notifications, portability, tenants
    tenant_id, appointment_id = verify_manage_token(token)
    existing = await db.pool().fetchrow(
        "SELECT * FROM appointments WHERE id=$1 AND tenant_id=$2",
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
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", str(tenant_id))
            clash = await conn.fetchval(
                "SELECT 1 FROM appointments WHERE tenant_id=$1 AND id<>$2 AND status='booked' "
                "AND starts_at < $4 AND ends_at > $3 LIMIT 1",
                tenant_id, existing["id"], start, end,
            )
            if clash:
                raise HTTPException(409, "That time is no longer available")
            updated = await conn.fetchrow(
                "UPDATE appointments SET starts_at=$3, ends_at=$4, calendar_state='pending', calendar_retry_at=now() "
                "WHERE id=$1 AND tenant_id=$2 RETURNING *",
                appointment_id, tenant_id, start, end,
            )
    await outbox.cancel_for_appointment(existing["id"])
    tenant = await tenants.get_by_id(tenant_id)
    if tenant and updated:
        appt = dict(updated)
        when = automation.fmt_local(tenant, start)
        await owner_notifications.queue(
            tenant,
            f"Appointment rescheduled: {appt['name']} — {when}",
            f"{appt['name']} moved their booking to {when}.\nPhone: {appt.get('phone') or '-'}\nEmail: {appt.get('email') or '-'}",
            f"appt:{appt['id']}:rescheduled:{int(start.timestamp())}",
        )
        await portability.emit(tenant["id"], "appointment.rescheduled", {
            "appointment_id": str(appt["id"]), "starts_at": start.isoformat(),
            "ends_at": end.isoformat(), "name": appt["name"], "notes": appt.get("notes", ""),
        })
        await calendar_connection.sync_one(appt["id"])
    return {
        "id": str(existing["id"]),
        "status": "booked",
        "starts_at": start.isoformat(),
        "ends_at": end.isoformat(),
    }
