"""Privacy Act 2020, in the product rather than in a policy document.

Three things an information privacy principle actually requires of a business like this, and which
were missing:

  * a statement the customer can reach, with a way to ask what is held;
  * a path to have their information deleted, not just a policy saying we would;
  * a record of whether someone agreed to be contacted on a given channel — we store call
    recordings and transcripts, and "they enquired once" is not consent to keep texting.

The statement itself lives on the marketing site; this module serves the entry point on the product
host, records the request, and gives the owner the erasure tool.
"""

from __future__ import annotations

import html
import re

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from . import db, owner_auth

router = APIRouter(prefix="/owner/privacy", tags=["privacy"])
public_router = APIRouter(prefix="/privacy", tags=["privacy"])

STATEMENT_URL = "https://trendibizz.com/privacy.html"
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")
CHANNELS = ("email", "sms", "voice", "chat", "post")


class PrivacyRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    kind: str = Field(default="delete", pattern=r"^(delete|access)$")
    note: str = Field(default="", max_length=2000)


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
<p class="muted">Enter the email address the business would have for you. This goes straight to that
business, who must respond.</p>
<form method="post" action="/privacy/request">
<label for="email">Your email</label>
<input id="email" name="email" type="email" required autocomplete="email">
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
    """Record the request and tell the business. Never silently absorb it."""
    from . import forms
    form = await forms.read_form(request)
    email = str(form.get("email") or "").strip().lower()
    kind = str(form.get("kind") or "delete")
    note = str(form.get("note") or "")[:2000]
    if kind not in ("delete", "access"):
        kind = "delete"
    if not EMAIL.match(email):
        return _page("<h1>Check that email</h1><p>That does not look like an email address.</p>"
                     "<p><a href='/privacy'>Try again</a></p>", "Check that email")
    rows = await db.pool().fetch(
        "SELECT t.id FROM tenants t JOIN leads l ON l.tenant_id=t.id "
        "WHERE lower(l.email)=$1 GROUP BY t.id", email)
    tenant_ids = [row["id"] for row in rows]
    if not tenant_ids:
        await db.pool().execute(
            "INSERT INTO privacy_requests(email,kind,note) VALUES($1,$2,$3)", email, kind, note.strip())
    for tenant_id in tenant_ids:
        await db.pool().execute(
            "INSERT INTO privacy_requests(tenant_id,email,kind,note) VALUES($1,$2,$3,$4)",
            tenant_id, email, kind, note.strip())
    # One line to the business, through the outbox so it is recorded and retried.
    from . import owner_notifications, tenants
    for tenant_id in tenant_ids:
        tenant = await tenants.get_by_id(tenant_id)
        if not tenant or not (tenant.get("notify_email") or "").strip():
            continue
        await owner_notifications.queue(
            tenant, "Privacy request: " + kind,
            f"A privacy request was made from the website.\n\nEmail: {email}\n"
            f"Request: {kind}\nNote: {note[:500] or '-'}\n\n"
            f"See it in Studio, then record what you did.\n",
            f"privacy:{tenant_id}:{email}:{kind}:{note[:40]}")
    return _page("""
<h1>Request received</h1>
<p>Thank you. We have passed this to the business that holds your details and recorded it with them.
They must respond within 20 working days.</p>
<p class="muted">If you do not hear back, reply to any email they have sent you.</p>
<p><a href="/privacy">Back</a></p>""", "Request received")


@router.get("/requests")
async def list_requests(user: dict = Depends(owner_auth.current_user)):
    rows = await db.pool().fetch(
        "SELECT id,email,kind,note,status,created_at,handled_at FROM privacy_requests "
        "WHERE tenant_id=$1 ORDER BY created_at DESC LIMIT 200", user["tenant_id"])
    return [dict(row) for row in rows]


@router.post("/requests/{request_id}/erase")
async def erase(request_id: str, user: dict = Depends(owner_auth.current_user)):
    """Carry out a deletion: strip the person's details from everything we can, keep the audit."""
    owner_auth.require_role(user, "owner")
    row = await db.pool().fetchrow(
        "SELECT * FROM privacy_requests WHERE id=$1 AND tenant_id=$2", request_id, user["tenant_id"])
    if not row:
        raise HTTPException(404, "Request not found")
    email = row["email"].lower()
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            leads = await conn.fetch(
                "SELECT id, conversation_id FROM leads WHERE tenant_id=$1 AND lower(email)=$2",
                user["tenant_id"], email)
            for lead in leads:
                # Keep the row for the business's own records and audit; remove the person.
                await conn.execute(
                    "UPDATE leads SET name='', email='', phone='', message='', company='', "
                    "erased_at=now() WHERE id=$1", lead["id"])
                await conn.execute("DELETE FROM enquiry_sources WHERE lead_id=$1", lead["id"])
                if lead["conversation_id"]:
                    await conn.execute(
                        "DELETE FROM messages WHERE conversation_id=$1", lead["conversation_id"])
                await _erase_person_everywhere(conn, user["tenant_id"], lead["id"], email)
            await conn.execute(
                "UPDATE privacy_requests SET status='done', handled_at=now(), handled_by=$2 WHERE id=$1",
                request_id, user.get("email") or "owner")
    return {"erased_leads": len(leads), "status": "done"}


async def _erase_person_everywhere(conn, tenant_id, lead_id, email: str) -> dict:
    """Erase the person from every table that holds them, not just the enquiry row.

    The first version blanked `leads` and deleted the enquiry's messages, then reported "done".
    The customer still existed in `customer_cases`, their whole `case_events` history, their
    appointments, their quotes and their calls — so the request was answered but the data was not
    gone. Records stay (the business needs its numbers); the person is removed from them.
    """
    cases = await conn.fetch(
        "SELECT id FROM customer_cases WHERE tenant_id=$1 AND (lower(primary_email)=$2 OR lower(display_name)=$2)",
        tenant_id, email)
    case_ids = [row["id"] for row in cases]
    for case_id in case_ids:
        await conn.execute(
            "UPDATE customer_cases SET display_name='Erased', primary_phone='', primary_email='', "
            "company='', erased_at=now() WHERE id=$1", case_id)
        await conn.execute(
            "UPDATE case_events SET body='', source_key='' WHERE case_id=$1", case_id)
        await conn.execute(
            "UPDATE appointments SET name='Erased', phone='', email='', notes='' "
            "WHERE tenant_id=$1 AND lead_id IN (SELECT id FROM leads WHERE case_id=$2)",
            tenant_id, case_id)
    await conn.execute(
        "UPDATE tasks SET title='Erased request', notes='' WHERE tenant_id=$1 AND lead_id=$2",
        tenant_id, lead_id)
    # A quote keeps its numbers and lines; the person's name, phone and email go.
    await conn.execute(
        "UPDATE quotations SET notes='', contact='{}'::jsonb WHERE tenant_id=$1 AND lead_id=$2",
        tenant_id, lead_id)
    # phone_calls has no lead_id: it links through the conversation's session_id.
    await conn.execute(
        "UPDATE phone_calls SET from_number='' WHERE tenant_id=$1 AND session_id IN "
        "(SELECT c.session_id FROM conversations c JOIN leads l ON l.conversation_id = c.id "
        "WHERE l.id = $2)", tenant_id, lead_id)
    await conn.execute(
        "DELETE FROM contact_consents WHERE tenant_id=$1 AND lower(contact_key)=$2", tenant_id, email)
    return {"cases": len(case_ids)}


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
