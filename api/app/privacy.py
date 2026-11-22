"""Privacy Act 2020 & AU Privacy / Call-Recording compliance, in the product.

Covers:
  * Public privacy statement entry point + rate-limited DSAR submission (email and/or phone)
  * Full DSAR erasure across all personal-data tables (leads, cases, addresses, events, messages,
    appointments, tasks, quotations, invoices, phone_calls, voice_recordings, call_insights,
    email_drafts, outbox, site_enquiries, contact_consents)
  * Per-subject DSAR access export (JSON bundle including transcripts)
  * Per-tenant non-audio retention settings + on-demand / scheduled purge
  * AU all-party strict opt-in call-recording consent mode toggle
  * Privacy breach register (72-hour OPC deadline tracking) + immutable privacy audit log
"""

from __future__ import annotations

import html
import json
import re
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from . import contact, db, owner_auth, privacy_retention
from .security import RateLimiter

router = APIRouter(prefix="/owner/privacy", tags=["privacy"])
public_router = APIRouter(prefix="/privacy", tags=["privacy"])

STATEMENT_URL = "https://trendibizz.com/privacy.html"
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")
CHANNELS = ("email", "sms", "voice", "chat", "post")
_dsar_ip_limiter = RateLimiter(10, 3600)


class PrivacyRequest(BaseModel):
    email: str = Field(default="", max_length=320)
    phone: str = Field(default="", max_length=40)
    kind: str = Field(default="delete", pattern=r"^(delete|access)$")
    note: str = Field(default="", max_length=2000)


async def _log_audit(conn, tenant_id, actor: str, action: str, subject: str = "", detail: dict | None = None) -> None:
    await conn.execute(
        "INSERT INTO privacy_audit_log(tenant_id, actor, action, subject, detail) "
        "VALUES($1, $2, $3, $4, $5::jsonb)",
        tenant_id, (actor or "system")[:120], action[:80], subject[:200], json.dumps(detail or {}),
    )


def _page(body: str, title: str = "Privacy") -> HTMLResponse:
    document = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="index, follow"><title>{html.escape(title)} — Concierge</title>
<style>
body{{font-family:system-ui,-apple-system,sans-serif;margin:0;color:#15191f;background:#f6f8fa}}
.page{{max-width:620px;margin:8vh auto;background:#fff;padding:36px;border-radius:16px;box-shadow:0 8px 30px rgba(0,0,0,.08)}}
h1{{font-size:26px;margin:0 0 12px}} p{{line-height:1.55}} .muted{{color:#5a6673}}
label{{display:block;margin:18px 0 6px;font-weight:600}} input,textarea{{width:100%;padding:12px;border:1px solid #c9d1da;border-radius:8px;font:inherit}}
button{{margin-top:18px;background:#c8f560;color:#101408;border:0;padding:13px 20px;border-radius:999px;font-weight:700;cursor:pointer}}
a{{color:#15191f}}
</style></head><body><div class="page">{body}</div></body></html>"""
    return HTMLResponse(document)


@public_router.get("", response_class=HTMLResponse)
async def privacy_page():
    """The entry point someone reaches when they want to know or ask us to stop."""
    return _page(f"""
<h1>Privacy</h1>
<p>We hold what you tell us — your enquiry, the messages you send, and for phone calls a recording
and transcript. We use it to answer you and to do the work you asked for.</p>
<p>The full statement is at <a href="{STATEMENT_URL}">{STATEMENT_URL}</a>.</p>
<h2 style="font-size:18px;margin-top:28px">See or delete what we hold</h2>
<p class="muted">Enter the email address and/or phone number the business would have for you. This goes straight to that
business, who must respond within 20 working days.</p>
<form method="post" action="/privacy/request">
<label for="email">Your email</label>
<input id="email" name="email" type="email" autocomplete="email">
<label for="phone">Your phone number (optional)</label>
<input id="phone" name="phone" type="tel" autocomplete="tel">
<label for="kind">What would you like?</label>
<select id="kind" name="kind" style="width:100%;padding:12px;border:1px solid #c9d1da;border-radius:8px;font:inherit">
<option value="access">Tell me what you hold about me</option>
<option value="delete">Delete what you hold about me</option>
</select>
<label for="note">Anything we should know (optional)</label>
<textarea id="note" name="note" rows="3"></textarea>
<button type="submit">Send this request</button>
</form>""")


@public_router.post("/request", response_class=HTMLResponse)
async def privacy_request(request: Request):
    """Record the request and tell the business. Rate-limited per IP; matches email or phone."""
    ip = request.client.host if request.client else "unknown"
    if not _dsar_ip_limiter.check(ip):
        raise HTTPException(429, "Too many privacy requests. Please try again later.")
    from . import forms
    form = await forms.read_form(request)
    email = str(form.get("email") or "").strip().lower()
    raw_phone = str(form.get("phone") or "").strip()
    phone = contact.normalize_phone(raw_phone, default_cc="64") if raw_phone else ""
    kind = str(form.get("kind") or "delete")
    note = str(form.get("note") or "")[:2000]
    if kind not in ("delete", "access"):
        kind = "delete"
    if email and not EMAIL.match(email):
        return _page("<h1>Check that email</h1><p>That does not look like an email address.</p>"
                     "<p><a href='/privacy'>Try again</a></p>", "Check that email")
    if not email and not phone:
        return _page("<h1>Check your details</h1><p>Please enter an email address or phone number.</p>"
                     "<p><a href='/privacy'>Try again</a></p>", "Check your details")

    tenant_ids: set = set()
    if email:
        rows = await db.pool().fetch(
            "SELECT DISTINCT tenant_id FROM leads WHERE lower(email)=$1 "
            "UNION SELECT DISTINCT tenant_id FROM customer_cases WHERE lower(primary_email)=$1 "
            "UNION SELECT DISTINCT tenant_id FROM customer_addresses WHERE kind='email' AND lower(value)=$1",
            email,
        )
        tenant_ids.update(r["tenant_id"] for r in rows)
    if phone:
        rows = await db.pool().fetch(
            "SELECT DISTINCT tenant_id FROM leads WHERE phone=$1 "
            "UNION SELECT DISTINCT tenant_id FROM customer_cases WHERE primary_phone=$1 "
            "UNION SELECT DISTINCT tenant_id FROM customer_addresses WHERE kind='phone' AND value=$1 "
            "UNION SELECT DISTINCT tenant_id FROM phone_calls WHERE from_number=$1",
            phone,
        )
        tenant_ids.update(r["tenant_id"] for r in rows)

    if not tenant_ids:
        await db.pool().execute(
            "INSERT INTO privacy_requests(email,phone,kind,note) VALUES($1,$2,$3,$4)",
            email, phone, kind, note.strip(),
        )
    for tenant_id in tenant_ids:
        await db.pool().execute(
            "INSERT INTO privacy_requests(tenant_id,email,phone,kind,note) VALUES($1,$2,$3,$4,$5)",
            tenant_id, email, phone, kind, note.strip(),
        )
    from . import owner_notifications, tenants
    subject_label = email or phone
    for tenant_id in tenant_ids:
        tenant = await tenants.get_by_id(tenant_id)
        if not tenant or not (tenant.get("notify_email") or "").strip():
            continue
        await owner_notifications.queue(
            tenant, "Privacy request: " + kind,
            f"A privacy request was made from the website.\n\nEmail: {email or '-'}\nPhone: {phone or '-'}\n"
            f"Request: {kind}\nNote: {note[:500] or '-'}\n\n"
            f"See it in Studio, then record what you did.\n",
            f"privacy:{tenant_id}:{subject_label}:{kind}:{date.today().isoformat()}",
        )
    return _page("""
<h1>Request received</h1>
<p>Thank you. We have passed this to the business that holds your details and recorded it with them.
They must respond within 20 working days.</p>
<p class="muted">If you do not hear back, reply to any email they have sent you.</p>
<p><a href="/privacy">Back</a></p>""", "Request received")


@router.get("/requests")
async def list_requests(user: dict = Depends(owner_auth.current_user)):
    rows = await db.pool().fetch(
        "SELECT id,email,phone,kind,note,status,created_at,handled_at FROM privacy_requests "
        "WHERE tenant_id=$1 ORDER BY created_at DESC LIMIT 200", user["tenant_id"])
    return [dict(row) for row in rows]


def _subject_phones(phone: str) -> list[str]:
    if not phone:
        return []
    out = {phone.strip()}
    norm = contact.normalize_phone(phone, default_cc="64")
    if norm:
        out.add(norm)
    return [p for p in out if p]


@router.post("/requests/{request_id}/erase")
async def erase(request_id: str, user: dict = Depends(owner_auth.current_user)):
    """Carry out a complete DSAR deletion across all tables holding personal data."""
    owner_auth.require_role(user, "owner")
    row = await db.pool().fetchrow(
        "SELECT * FROM privacy_requests WHERE id=$1 AND tenant_id=$2", request_id, user["tenant_id"])
    if not row:
        raise HTTPException(404, "Request not found")
    email = (row["email"] or "").strip().lower()
    phone = (row.get("phone") or "").strip() if hasattr(row, "get") else (row["phone"] or "").strip()
    phones = _subject_phones(phone)
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            matched_leads = await conn.fetch(
                "SELECT id, conversation_id FROM leads WHERE tenant_id=$1 AND ("
                "($2 <> '' AND lower(email)=$2) OR (cardinality($3::text[]) > 0 AND phone = ANY($3::text[])))",
                user["tenant_id"], email, phones,
            )
            for lead in matched_leads:
                await conn.execute(
                    "UPDATE leads SET name='', email='', phone='', message='', company='', "
                    "erased_at=now() WHERE id=$1", lead["id"],
                )
                await conn.execute("DELETE FROM enquiry_sources WHERE lead_id=$1", lead["id"])
                if lead["conversation_id"]:
                    await conn.execute("DELETE FROM messages WHERE conversation_id=$1", lead["conversation_id"])
            summary = await _erase_subject_everywhere(
                conn, user["tenant_id"], email=email, phones=phones,
                prematched_lead_ids=[r["id"] for r in matched_leads],
                prematched_conv_ids=[r["conversation_id"] for r in matched_leads if r["conversation_id"]],
            )
            await conn.execute(
                "UPDATE privacy_requests SET status='done', handled_at=now(), handled_by=$2 WHERE id=$1",
                request_id, user.get("email") or "owner",
            )
            await _log_audit(
                conn, user["tenant_id"], user.get("email") or "owner", "dsar_erase",
                subject=email or phone, detail={"request_id": str(request_id), **summary},
            )
    return {"erased_leads": summary["leads"], "summary": summary, "status": "done"}


async def _erase_subject_everywhere(
    conn, tenant_id, *, email: str = "", phones: list[str] | None = None,
    prematched_lead_ids: list | None = None, prematched_conv_ids: list | None = None,
) -> dict:
    """Erase/anonymize the subject across EVERY table that holds personal data."""
    phones = phones or []
    lead_rows = await conn.fetch(
        "SELECT id, conversation_id, case_id FROM leads WHERE tenant_id=$1 AND ("
        "($2 <> '' AND lower(email)=$2) OR (cardinality($3::text[]) > 0 AND phone = ANY($3::text[])))",
        tenant_id, email, phones,
    )
    lead_ids = list({r["id"] for r in lead_rows} | set(prematched_lead_ids or []))
    conv_ids = list({r["conversation_id"] for r in lead_rows if r["conversation_id"]} | set(prematched_conv_ids or []))

    case_rows = await conn.fetch(
        "SELECT id FROM customer_cases WHERE tenant_id=$1 AND ("
        "($2 <> '' AND (lower(primary_email)=$2 OR lower(display_name)=$2)) "
        "OR (cardinality($3::text[]) > 0 AND primary_phone = ANY($3::text[])) "
        "OR id IN (SELECT case_id FROM customer_addresses WHERE tenant_id=$1 AND "
        "(($2 <> '' AND kind='email' AND lower(value)=$2) OR (cardinality($3::text[]) > 0 AND kind='phone' AND value = ANY($3::text[])))))",
        tenant_id, email, phones,
    )
    case_ids = list({r["id"] for r in case_rows} | {r["case_id"] for r in lead_rows if r["case_id"]})

    # Leads + enquiry_sources + messages
    for lid in lead_ids:
        await conn.execute(
            "UPDATE leads SET name='', email='', phone='', message='', company='', erased_at=now() WHERE id=$1", lid
        )
        await conn.execute("DELETE FROM enquiry_sources WHERE lead_id=$1", lid)
    if conv_ids:
        await conn.execute("DELETE FROM messages WHERE conversation_id = ANY($1::uuid[])", conv_ids)

    # Customer cases, addresses, events, appointments
    for cid in case_ids:
        await conn.execute(
            "UPDATE customer_cases SET display_name='Erased', primary_phone='', primary_email='', "
            "company='', erased_at=now() WHERE id=$1", cid,
        )
        await conn.execute("DELETE FROM customer_addresses WHERE tenant_id=$1 AND case_id=$2", tenant_id, cid)
        await conn.execute("UPDATE case_events SET body='', source_key='' WHERE case_id=$1", cid)
        await conn.execute(
            "UPDATE appointments SET name='Erased', phone='', email='', notes='' "
            "WHERE tenant_id=$1 AND lead_id IN (SELECT id FROM leads WHERE case_id=$2)",
            tenant_id, cid,
        )

    # Appointments matching directly by email/phone/lead_id
    await conn.execute(
        "UPDATE appointments SET name='Erased', phone='', email='', notes='' WHERE tenant_id=$1 AND ("
        "($2 <> '' AND lower(email)=$2) OR (cardinality($3::text[]) > 0 AND phone = ANY($3::text[])) "
        "OR (cardinality($4::uuid[]) > 0 AND lead_id = ANY($4::uuid[])))",
        tenant_id, email, phones, lead_ids,
    )

    # Tasks, quotations, invoices (keep invoice financial totals, scrub notes/contact)
    if lead_ids:
        await conn.execute(
            "UPDATE tasks SET title='Erased request', notes='' WHERE tenant_id=$1 AND lead_id = ANY($2::uuid[])",
            tenant_id, lead_ids,
        )
        q_ids = [
            r["id"] for r in await conn.fetch(
                "SELECT id FROM quotations WHERE tenant_id=$1 AND lead_id = ANY($2::uuid[])", tenant_id, lead_ids
            )
        ]
        await conn.execute(
            "UPDATE quotations SET notes='', contact='{}'::jsonb WHERE tenant_id=$1 AND lead_id = ANY($2::uuid[])",
            tenant_id, lead_ids,
        )
        if q_ids:
            await conn.execute(
                "UPDATE invoices SET notes='' WHERE tenant_id=$1 AND quotation_id = ANY($2::uuid[])",
                tenant_id, q_ids,
            )

    # Voice recordings (via conversations) & phone_calls & call_insights
    rec_deleted = 0
    if conv_ids:
        rec_deleted = int(await conn.fetchval(
            "WITH d AS (DELETE FROM voice_recordings WHERE tenant_id=$1 AND conversation_id = ANY($2::uuid[]) RETURNING 1) "
            "SELECT count(*) FROM d",
            tenant_id, conv_ids,
        ) or 0)
    call_sids = [
        r["call_sid"] for r in await conn.fetch(
            "SELECT call_sid FROM phone_calls WHERE tenant_id=$1 AND ("
            "(cardinality($2::text[]) > 0 AND from_number = ANY($2::text[])) "
            "OR session_id IN (SELECT session_id FROM conversations WHERE id = ANY($3::uuid[])))",
            tenant_id, phones, conv_ids,
        )
    ]
    await conn.execute(
        "UPDATE phone_calls SET from_number='' WHERE tenant_id=$1 AND ("
        "(cardinality($2::text[]) > 0 AND from_number = ANY($2::text[])) "
        "OR session_id IN (SELECT session_id FROM conversations WHERE id = ANY($3::uuid[])))",
        tenant_id, phones, conv_ids,
    )
    insights_erased = int(await conn.fetchval(
        "WITH u AS ("
        "  UPDATE call_insights SET summary='', next_step='' WHERE tenant_id=$1 AND ("
        "    (cardinality($2::uuid[]) > 0 AND lead_id = ANY($2::uuid[])) "
        "    OR (cardinality($3::text[]) > 0 AND call_sid = ANY($3::text[]))) "
        "  RETURNING 1"
        ") SELECT count(*) FROM u",
        tenant_id, lead_ids, call_sids,
    ) or 0)

    # Email drafts, outbox, site_enquiries, contact_consents
    drafts_erased = 0
    if email:
        drafts_erased = int(await conn.fetchval(
            "WITH u AS ("
            "  UPDATE email_drafts SET sender='', subject='Erased', inbound_body='', reply_body='' "
            "  WHERE tenant_id=$1 AND lower(sender)=$2 RETURNING 1"
            ") SELECT count(*) FROM u",
            tenant_id, email,
        ) or 0)
        await conn.execute(
            "UPDATE site_enquiries SET name='Erased', email='', message='' WHERE lower(email)=$1", email
        )
    outbox_targets = ([email] if email else []) + phones
    outbox_erased = 0
    if outbox_targets or lead_ids:
        outbox_erased = int(await conn.fetchval(
            "WITH u AS ("
            "  UPDATE outbox SET to_addr='', subject='Erased', body='' WHERE tenant_id=$1 AND ("
            "    (cardinality($2::text[]) > 0 AND lower(to_addr) = ANY($2::text[])) "
            "    OR (cardinality($3::uuid[]) > 0 AND lead_id = ANY($3::uuid[]))) "
            "  RETURNING 1"
            ") SELECT count(*) FROM u",
            tenant_id, [t.lower() for t in outbox_targets], lead_ids,
        ) or 0)

    consent_keys = ([email] if email else []) + [p.lower() for p in phones]
    if consent_keys:
        await conn.execute(
            "DELETE FROM contact_consents WHERE tenant_id=$1 AND lower(contact_key) = ANY($2::text[])",
            tenant_id, consent_keys,
        )

    return {
        "leads": len(lead_ids),
        "cases": len(case_ids),
        "voice_recordings": rec_deleted,
        "call_insights": insights_erased,
        "email_drafts": drafts_erased,
        "outbox": outbox_erased,
    }


async def _erase_person_everywhere(conn, tenant_id, lead_id, email: str) -> dict:
    """Backward-compatible helper retained for existing callers/tests."""
    return await _erase_subject_everywhere(conn, tenant_id, email=email.lower(), phones=[])


# ---- Per-subject DSAR access export (IPP 6) -------------------------------------------------
async def _build_subject_export(conn, tenant_id, *, email: str = "", phone: str = "") -> dict:
    email = (email or "").strip().lower()
    phones = _subject_phones(phone)
    leads = [
        dict(r) for r in await conn.fetch(
            "SELECT id, conversation_id, case_id, name, email, phone, company, message, status, created_at "
            "FROM leads WHERE tenant_id=$1 AND ("
            "($2 <> '' AND lower(email)=$2) OR (cardinality($3::text[]) > 0 AND phone = ANY($3::text[]))) "
            "ORDER BY created_at DESC",
            tenant_id, email, phones,
        )
    ]
    lead_ids = [r["id"] for r in leads]
    conv_ids = [r["conversation_id"] for r in leads if r["conversation_id"]]

    cases = [
        dict(r) for r in await conn.fetch(
            "SELECT id, case_key, display_name, primary_phone, primary_email, company, created_at "
            "FROM customer_cases WHERE tenant_id=$1 AND ("
            "($2 <> '' AND lower(primary_email)=$2) OR (cardinality($3::text[]) > 0 AND primary_phone = ANY($3::text[])))",
            tenant_id, email, phones,
        )
    ]
    case_ids = list({r["id"] for r in cases} | {r["case_id"] for r in leads if r["case_id"]})

    messages = [
        dict(r) for r in await conn.fetch(
            "SELECT conversation_id, role, content, created_at FROM messages "
            "WHERE conversation_id = ANY($1::uuid[]) ORDER BY created_at ASC",
            conv_ids,
        )
    ] if conv_ids else []

    case_events = [
        dict(r) for r in await conn.fetch(
            "SELECT case_id, channel, direction, body, occurred_at FROM case_events "
            "WHERE case_id = ANY($1::uuid[]) ORDER BY occurred_at ASC",
            case_ids,
        )
    ] if case_ids else []

    appointments = [
        dict(r) for r in await conn.fetch(
            "SELECT id, name, email, phone, starts_at, ends_at, status, notes FROM appointments "
            "WHERE tenant_id=$1 AND (($2 <> '' AND lower(email)=$2) OR (cardinality($3::text[]) > 0 AND phone = ANY($3::text[])) "
            "OR (cardinality($4::uuid[]) > 0 AND lead_id = ANY($4::uuid[]))) ORDER BY starts_at DESC",
            tenant_id, email, phones, lead_ids,
        )
    ]

    email_drafts = [
        dict(r) for r in await conn.fetch(
            "SELECT id, sender, subject, inbound_body, reply_body, status, created_at FROM email_drafts "
            "WHERE tenant_id=$1 AND $2 <> '' AND lower(sender)=$2 ORDER BY created_at DESC",
            tenant_id, email,
        )
    ] if email else []

    call_insights = [
        dict(r) for r in await conn.fetch(
            "SELECT call_sid, summary, outcome, sentiment, next_step, created_at FROM call_insights "
            "WHERE tenant_id=$1 AND cardinality($2::uuid[]) > 0 AND lead_id = ANY($2::uuid[]) ORDER BY created_at DESC",
            tenant_id, lead_ids,
        )
    ] if lead_ids else []

    consents_rows = [
        dict(r) for r in await conn.fetch(
            "SELECT contact_key, channel, granted, source, note, recorded_at FROM contact_consents "
            "WHERE tenant_id=$1 AND lower(contact_key) = ANY($2::text[]) ORDER BY recorded_at DESC",
            tenant_id, [k for k in ([email] + [p.lower() for p in phones]) if k],
        )
    ] if (email or phones) else []

    return {
        "subject": {"email": email, "phone": phone},
        "leads": leads,
        "cases": cases,
        "messages": messages,
        "case_events": case_events,
        "appointments": appointments,
        "email_drafts": email_drafts,
        "call_insights": call_insights,
        "consents": consents_rows,
    }


@router.get("/requests/{request_id}/export")
async def export_request_subject(request_id: str, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    row = await db.pool().fetchrow(
        "SELECT * FROM privacy_requests WHERE id=$1 AND tenant_id=$2", request_id, user["tenant_id"]
    )
    if not row:
        raise HTTPException(404, "Request not found")
    async with db.pool().acquire() as conn:
        bundle = await _build_subject_export(conn, user["tenant_id"], email=row["email"] or "", phone=row["phone"] or "")
        await _log_audit(
            conn, user["tenant_id"], user.get("email") or "owner", "dsar_export",
            subject=row["email"] or row["phone"] or "", detail={"request_id": str(request_id)},
        )
    return bundle


@router.get("/export")
async def export_subject(
    email: str = Query(default="", max_length=320),
    phone: str = Query(default="", max_length=40),
    user: dict = Depends(owner_auth.current_user),
):
    owner_auth.require_role(user, "owner")
    if not email.strip() and not phone.strip():
        raise HTTPException(400, "Provide email or phone to export")
    async with db.pool().acquire() as conn:
        bundle = await _build_subject_export(conn, user["tenant_id"], email=email, phone=phone)
        await _log_audit(
            conn, user["tenant_id"], user.get("email") or "owner", "dsar_export",
            subject=email.strip().lower() or phone.strip(),
        )
    return bundle


# ---- Non-audio retention policy & manual trigger --------------------------------------------
class RetentionPolicy(BaseModel):
    retention_days_messages: int = Field(ge=0, le=3650)
    retention_days_leads: int = Field(ge=0, le=3650)
    retention_days_outbox: int = Field(ge=0, le=3650)
    retention_days_email_drafts: int = Field(ge=0, le=3650)


@router.get("/retention")
async def get_retention(user: dict = Depends(owner_auth.current_user)):
    row = await db.pool().fetchrow(
        "SELECT retention_days_messages, retention_days_leads, retention_days_outbox, "
        "retention_days_email_drafts, call_recording_consent_mode FROM tenants WHERE id=$1",
        user["tenant_id"],
    )
    return dict(row)


@router.put("/retention")
async def set_retention(body: RetentionPolicy, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    async with db.pool().acquire() as conn:
        await conn.execute(
            "UPDATE tenants SET retention_days_messages=$2, retention_days_leads=$3, "
            "retention_days_outbox=$4, retention_days_email_drafts=$5 WHERE id=$1",
            user["tenant_id"], body.retention_days_messages, body.retention_days_leads,
            body.retention_days_outbox, body.retention_days_email_drafts,
        )
        await _log_audit(conn, user["tenant_id"], user.get("email") or "owner", "retention_updated", detail=body.model_dump())
    return body.model_dump()


@router.post("/retention/run")
async def run_retention_now(user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    counts = await privacy_retention.purge_for_tenant(user["tenant_id"])
    async with db.pool().acquire() as conn:
        await _log_audit(conn, user["tenant_id"], user.get("email") or "owner", "retention_purge_run", detail=counts)
    return {"purged": counts}


# ---- AU strict opt-in call-recording consent mode -------------------------------------------
class RecordingModeBody(BaseModel):
    mode: Literal["opt_out", "strict_opt_in"]


@router.get("/recording-mode")
async def get_recording_mode(user: dict = Depends(owner_auth.current_user)):
    mode = await db.pool().fetchval(
        "SELECT call_recording_consent_mode FROM tenants WHERE id=$1", user["tenant_id"]
    )
    return {"mode": mode or "opt_out"}


@router.put("/recording-mode")
async def set_recording_mode(body: RecordingModeBody, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    async with db.pool().acquire() as conn:
        await conn.execute(
            "UPDATE tenants SET call_recording_consent_mode=$2 WHERE id=$1",
            user["tenant_id"], body.mode,
        )
        await _log_audit(conn, user["tenant_id"], user.get("email") or "owner", "recording_mode_updated", detail={"mode": body.mode})
    return {"mode": body.mode}


# ---- Breach register (Part 6 72h OPC readiness) & privacy audit log -------------------------
class BreachCreate(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    description: str = Field(default="", max_length=4000)
    affected_count: int = Field(default=0, ge=0)


class BreachUpdate(BaseModel):
    status: Literal["open", "investigating", "notified_opc", "closed"]
    description: str | None = Field(default=None, max_length=4000)


@router.get("/breaches")
async def list_breaches(user: dict = Depends(owner_auth.current_user)):
    rows = await db.pool().fetch(
        "SELECT id, title, severity, description, affected_count, status, detected_at, due_72h_at, notified_at, created_by, created_at "
        "FROM privacy_breaches WHERE tenant_id=$1 ORDER BY created_at DESC LIMIT 100",
        user["tenant_id"],
    )
    return [dict(r) for r in rows]


@router.post("/breaches", status_code=201)
async def create_breach(body: BreachCreate, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    async with db.pool().acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO privacy_breaches(tenant_id, title, severity, description, affected_count, created_by) "
            "VALUES($1, $2, $3, $4, $5, $6) RETURNING *",
            user["tenant_id"], body.title.strip(), body.severity, body.description.strip(),
            body.affected_count, user.get("email") or "owner",
        )
        await _log_audit(
            conn, user["tenant_id"], user.get("email") or "owner", "breach_recorded",
            subject=body.title.strip(), detail={"breach_id": str(row["id"]), "severity": body.severity},
        )
    return dict(row)


@router.patch("/breaches/{breach_id}")
async def update_breach(breach_id: str, body: BreachUpdate, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    async with db.pool().acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE privacy_breaches SET status=$3, "
            "description=COALESCE($4, description), "
            "notified_at=CASE WHEN $3='notified_opc' AND notified_at IS NULL THEN now() ELSE notified_at END "
            "WHERE id=$1 AND tenant_id=$2 RETURNING *",
            breach_id, user["tenant_id"], body.status, body.description,
        )
        if not row:
            raise HTTPException(404, "Breach record not found")
        await _log_audit(
            conn, user["tenant_id"], user.get("email") or "owner", "breach_updated",
            subject=str(breach_id), detail={"status": body.status},
        )
    return dict(row)


@router.get("/audit")
async def privacy_audit(limit: int = Query(default=100, ge=1, le=500), user: dict = Depends(owner_auth.current_user)):
    rows = await db.pool().fetch(
        "SELECT id, actor, action, subject, detail, created_at FROM privacy_audit_log "
        "WHERE tenant_id=$1 ORDER BY created_at DESC LIMIT $2",
        user["tenant_id"], limit,
    )
    return [dict(r) for r in rows]


class Consent(BaseModel):
    channel: str = Field(pattern=r"^(email|sms|voice|chat|post)$")
    granted: bool
    source: str = Field(default="", max_length=120)
    note: str = Field(default="", max_length=500)


@router.post("/contacts/{contact_key}/consent")
async def record_consent(contact_key: str, body: Consent, user=Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    key = contact_key.strip().lower()[:200]
    if not key:
        raise HTTPException(400, "Who is this for?")
    row = await db.pool().fetchrow(
        "INSERT INTO contact_consents(tenant_id,contact_key,channel,granted,source,note) "
        "VALUES($1,$2,$3,$4,$5,$6) RETURNING *",
        user["tenant_id"], key, body.channel, body.granted, body.source.strip(), body.note.strip())
    return dict(row)


@router.get("/contacts/{contact_key}/consent")
async def consents(contact_key: str, user=Depends(owner_auth.current_user)):
    rows = await db.pool().fetch(
        "SELECT channel,granted,source,recorded_at FROM contact_consents "
        "WHERE tenant_id=$1 AND contact_key=$2 ORDER BY recorded_at DESC LIMIT 100",
        user["tenant_id"], contact_key.strip().lower()[:200])
    return [dict(row) for row in rows]
