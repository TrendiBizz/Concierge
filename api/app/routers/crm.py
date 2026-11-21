"""CRM, pipeline, tasks, companies, contacts, calendar, scoring/SLA, revenue, business profile,
and payment/billing-glue routes.

Moved out of app/main.py unchanged; paths and behaviour are identical. main.py re-exports the
handlers, helpers, and request models so existing imports (tests, tooling) keep working.
"""
import asyncio
import sys
import uuid
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .. import (
    automation, calendar_connection, casetimeline, db, hermes_orchestrator, ical, llm,
    owner_ask, owner_auth, portability, quotations, quote_payments, revenue, sales, scoring,
    sla, tasks, tenants, voice_records,
)
from ..security import require_admin

router = APIRouter()
admin = [Depends(require_admin)]


def _main():
    return sys.modules[__package__.rsplit(".", 1)[0] + ".main"]


# ------------------------------------------------------------------ models & helpers
class LeadUpdate(BaseModel):
    status: Literal["new", "contacted", "booked", "won", "lost"] | None = None
    notes: str | None = Field(default=None, max_length=4000)
    value_cents: int | None = Field(default=None, ge=0, le=100_000_000)
    lost_reason: str | None = Field(default=None, max_length=300)   # only used together with status = lost
    next_action_at: datetime | None = None                          # also moves the lead's follow-up to-do

    @field_validator("next_action_at")
    @classmethod
    def _aware(cls, value):
        return value if value is None or value.tzinfo else value.replace(tzinfo=timezone.utc)


class AppointmentUpdate(BaseModel):
    status: Literal["booked", "completed", "cancelled", "no_show"]


def _aware(value):
    """A date typed without a timezone is taken as UTC, so it can never be misread as local time."""
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    notes: str = Field(default="", max_length=2000)
    due_at: datetime | None = None
    lead_id: str | None = None

    @field_validator("due_at")
    @classmethod
    def _aware(cls, value):
        return _aware(value)


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=2000)
    due_at: datetime | None = None
    status: Literal["open", "done"] | None = None

    @field_validator("due_at")
    @classmethod
    def _aware(cls, value):
        return _aware(value)


# ------------------------------------------------------------------ admin CRM / scoring / SLA / tasks / calendar
@router.get("/admin/tenants/{slug}/scoring", dependencies=admin)
async def admin_scoring(slug: str):
    """The scoring weights in force for this client, with defaults, for the dashboard editor."""
    tenant = await _main()._require_tenant(slug)
    return {"weights": scoring.describe(tenant)}


@router.post("/admin/tenants/{slug}/rescore", dependencies=admin)
async def admin_rescore(slug: str):
    """Recompute every lead's score with the client's current weights."""
    tenant = await _main()._require_tenant(slug)
    return await scoring.rescore_tenant(tenant)


@router.get("/admin/tenants/{slug}/sla", dependencies=admin)
async def admin_sla(slug: str):
    """Response-time settings and the leads currently waiting longer than the target."""
    tenant = await _main()._require_tenant(slug)
    waiting = await sla.overdue(tenant)
    return {
        "sla_minutes": tenant.get("sla_minutes") or 0,
        "sla_min_score": tenant.get("sla_min_score") if tenant.get("sla_min_score") is not None else 70,
        "waiting": [
            {
                "id": str(w["id"]), "name": w["name"], "phone": w["phone"], "email": w["email"],
                "message": w["message"], "channel": w["channel"], "score": w["score"],
                "score_label": w["score_label"], "reasons": scoring.reasons_of(w),
                "minutes_waiting": w["minutes_waiting"], "alerted": w["sla_alerted_at"] is not None,
                "created_at": w["created_at"].isoformat(),
            }
            for w in waiting
        ],
    }


@router.get("/admin/tenants/{slug}/tasks", dependencies=admin)
async def admin_list_tasks(slug: str, status: Literal["open", "done", "all"] = "open"):
    tenant = await _main()._require_tenant(slug)
    return await tasks.list_tasks(tenant["id"], status)


@router.post("/admin/tenants/{slug}/tasks", dependencies=admin, status_code=201)
async def admin_create_task(slug: str, body: TaskCreate):
    tenant = await _main()._require_tenant(slug)
    if body.lead_id:
        try:
            found = await db.pool().fetchval("SELECT 1 FROM leads WHERE id = $1::uuid AND tenant_id = $2", body.lead_id, tenant["id"])
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid lead id")
        if not found:
            raise HTTPException(status_code=404, detail="Unknown lead")
    try:
        return await tasks.create(tenant["id"], body.title, body.notes, body.due_at, lead_id=body.lead_id)
    except tasks.TaskError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.patch("/admin/tasks/{task_id}", dependencies=admin)
async def admin_update_task(task_id: int, body: TaskUpdate):
    try:
        row = await tasks.update(task_id, body.model_dump(exclude_unset=True))
    except tasks.TaskError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if row is None:
        raise HTTPException(status_code=404, detail="Unknown to-do")
    return row


@router.delete("/admin/tasks/{task_id}", dependencies=admin)
async def admin_delete_task(task_id: int):
    if not await tasks.delete(task_id):
        raise HTTPException(status_code=404, detail="Unknown to-do")
    return {"deleted": True}


@router.get("/admin/tenants/{slug}/pipeline", dependencies=admin)
async def admin_pipeline(slug: str):
    return await sales.pipeline(await _main()._require_tenant(slug))


@router.get("/admin/tenants/{slug}/sales-summary", dependencies=admin)
async def admin_sales_summary(slug: str, days: int = 7):
    return await sales.summary(await _main()._require_tenant(slug), min(max(days, 1), 365))


@router.get("/api/v1/calendar/{token}.ics")
async def calendar_feed(token: str):
    """Read-only appointment feed to subscribe to from Google / Apple / Outlook Calendar. The token is the credential."""
    tenant = await tenants.get_by_calendar_token(token)
    if tenant is None:
        raise HTTPException(status_code=404, detail="Unknown calendar")
    rows = await db.pool().fetch(
        "SELECT * FROM appointments WHERE tenant_id = $1 AND starts_at > now() - interval '30 days' ORDER BY starts_at",
        tenant["id"],
    )
    return Response(
        content=ical.build(tenant, [dict(r) for r in rows]),
        media_type="text/calendar; charset=utf-8",
        headers={"Cache-Control": "private, max-age=300"},
    )


@router.patch("/admin/leads/{lead_id}", dependencies=admin)
async def admin_update_lead(lead_id: str, body: LeadUpdate):
    data = body.model_dump(exclude_unset=True)
    data = {k: v for k, v in data.items() if v is not None}
    if not data:
        raise HTTPException(status_code=400, detail="Nothing to update")
    status = data.pop("status", None)
    reason = data.pop("lost_reason", "") or ""
    row = None
    try:
        if data:
            parts = [f"{col} = ${i}" for i, col in enumerate(data, start=2)]
            row = await db.pool().fetchrow(
                f"UPDATE leads SET {', '.join(parts)}, updated_at = now() WHERE id = $1::uuid RETURNING *",
                lead_id, *data.values(),
            )
            if row is None:
                raise LookupError
        if status:
            row = await sales.change_status(lead_id, status, reason)  # records history, tidies the follow-up
            if row is None:
                raise LookupError
        if "next_action_at" in data and row is not None:
            await tasks.set_follow_up_due(dict(row), data["next_action_at"])
    except LookupError:
        raise HTTPException(status_code=404, detail="Unknown lead")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid lead id")
    return dict(row)


@router.get("/admin/tenants/{slug}/appointments", dependencies=admin)
async def admin_appointments(slug: str, status: str | None = None, limit: int = 100):
    tenant = await _main()._require_tenant(slug)
    rows = await db.pool().fetch(
        "SELECT * FROM appointments WHERE tenant_id = $1 AND ($2::text IS NULL OR status = $2) "
        "ORDER BY starts_at DESC LIMIT $3",
        tenant["id"], status, min(max(limit, 1), 500),
    )
    return [dict(r) for r in rows]


@router.patch("/admin/appointments/{appointment_id}", dependencies=admin)
async def admin_update_appointment(appointment_id: str, body: AppointmentUpdate):
    try:
        row = await db.pool().fetchrow(
            "UPDATE appointments SET status = $2 WHERE id = $1::uuid RETURNING *", appointment_id, body.status
        )
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid appointment id")
    if row is None:
        raise HTTPException(status_code=404, detail="Unknown appointment")
    appt = dict(row)
    tenant = await tenants.get_by_id(appt["tenant_id"])
    await automation.on_appointment_status(tenant, appt, body.status)
    if body.status in ("cancelled", "no_show"):
        await calendar_connection.sync_one(appt["id"])
    return appt


# ------------------------------------------------------------------ owner CRM, tasks, companies & contacts
@router.get("/owner/crm")
async def owner_crm(user: dict = Depends(owner_auth.current_user)):
    m = _main()
    tenant = await tenants.ensure_calendar_token(await m._require_tenant(user["slug"]))
    leads, appointments, todos = await asyncio.gather(
        m.admin_leads(user["slug"]), admin_appointments(user["slug"]),
        tasks.list_tasks(user["tenant_id"], "all"))
    return {"leads": leads, "appointments": appointments, "tasks": todos,
            "calendar_url": m._origin_of(m.settings.owner_portal_url) + "/api/v1/calendar/" + tenant["calendar_token"] + ".ics"}


@router.get("/owner/crm/pipeline")
async def owner_crm_pipeline(user: dict = Depends(owner_auth.current_user)):
    """The sales board: every open lead grouped by stage, with per-stage and weighted value totals.

    Same engine as the admin dashboard (`sales.pipeline`), so the board, the report and the weekly
    summary can never disagree about what is in the pipeline.
    """
    tenant = await _main()._require_tenant(user["slug"])
    return await sales.pipeline(tenant)


class OpportunityCreate(BaseModel):
    name: str = Field(default="", max_length=160)
    company: str = Field(default="", max_length=160)
    email: str = Field(default="", max_length=254)
    phone: str = Field(default="", max_length=40)
    message: str = Field(default="", max_length=2000)
    value_cents: int = Field(default=0, ge=0, le=100_000_000)


@router.post("/owner/crm/leads", status_code=201)
async def owner_create_opportunity(body: OpportunityCreate, user: dict = Depends(owner_auth.current_user)):
    """Add a deal the owner heard about offline (a walk-in, a referral) to the sales board."""
    owner_auth.require_role(user, "editor")
    if not any((body.name, body.company, body.email, body.phone, body.message)):
        raise HTTPException(status_code=422, detail="Add a name, company, email or phone")
    row = await db.pool().fetchrow(
        "INSERT INTO leads(tenant_id,name,company,email,phone,message,channel,status,value_cents) "
        "VALUES($1,$2,$3,$4,$5,$6,'manual','new',$7) RETURNING *",
        user["tenant_id"], body.name.strip(), body.company.strip(), body.email.strip(),
        body.phone.strip(), body.message.strip(), body.value_cents)
    return dict(row)


@router.get("/owner/crm/leads/{lead_id}/transcript")
async def owner_crm_transcript(lead_id: uuid.UUID, user: dict = Depends(owner_auth.current_user)):
    exists = await db.pool().fetchval(
        "SELECT 1 FROM leads WHERE tenant_id=$1 AND id=$2", user["tenant_id"], lead_id)
    if not exists:
        raise HTTPException(404, "Enquiry not found")
    rows = await db.pool().fetch(
        "SELECT m.role,m.content,m.created_at FROM leads l "
        "JOIN conversations c ON c.id=l.conversation_id AND c.tenant_id=l.tenant_id "
        "JOIN messages m ON m.conversation_id=c.id "
        "WHERE l.tenant_id=$1 AND l.id=$2 AND m.role IN ('user','assistant') "
        "ORDER BY m.id LIMIT 1000", user["tenant_id"], lead_id)
    return [dict(row) for row in rows] if rows else [
        {'role': 'user', 'content': row['original_text'], 'created_at': row['created_at']}
        for row in await db.pool().fetch('SELECT original_text,created_at FROM enquiry_sources WHERE tenant_id=$1 AND lead_id=$2 ORDER BY created_at', user['tenant_id'], lead_id)]


@router.get("/owner/crm/leads/{lead_id}/recordings")
async def owner_crm_recordings(lead_id: uuid.UUID, user: dict = Depends(owner_auth.current_user)):
    return await voice_records.recordings_for_lead(user["tenant_id"], lead_id)


@router.get("/owner/voice-recordings/{session_id}")
async def owner_voice_recording(session_id: uuid.UUID, user: dict = Depends(owner_auth.current_user)):
    row = await voice_records.audio_for_owner(user["tenant_id"], session_id)
    return _main().private_audio_response(row, "concierge-recording." + row["mime_type"].split("/")[1])


@router.post("/owner/voice-recordings/{session_id}/share")
async def owner_share_voice_recording(session_id: uuid.UUID, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    token = await voice_records.share(user["tenant_id"], session_id)
    return {"url": _main().settings.public_base_url.rstrip("/") + "/api/v1/voice/recordings/shared/" + token, "expires_in_hours": 24}


class VoiceCopyRequest(BaseModel):
    recipient: str = Field(min_length=1, max_length=254)
    channel: Literal["sms", "email"]
    content: Literal["text", "recording"]
    request_id: uuid.UUID
    session_id: uuid.UUID | None = None


@router.post("/owner/crm/leads/{lead_id}/deliver")
async def owner_deliver_voice_copy(lead_id: uuid.UUID, body: VoiceCopyRequest, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    tenant = await tenants.get_by_id(user["tenant_id"])
    return await voice_records.deliver(tenant, lead_id, **body.model_dump())


class OwnerTaskCreate(TaskCreate):
    pass


@router.get("/owner/tasks")
async def owner_tasks(status: Literal["open", "done", "all"] = "open",
                      user: dict = Depends(owner_auth.current_user)):
    """The owner's own to-do list. Tasks existed but only admins could reach them."""
    owner_auth.require_role(user, "viewer")
    return await tasks.list_tasks(user["tenant_id"], status)


@router.post("/owner/tasks", status_code=201)
async def owner_task_create(body: OwnerTaskCreate, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    if body.lead_id:
        try:
            found = await db.pool().fetchval(
                "SELECT 1 FROM leads WHERE id=$1::uuid AND tenant_id=$2", body.lead_id, user["tenant_id"])
        except Exception:
            raise HTTPException(400, "Invalid lead id")
        if not found:
            raise HTTPException(404, "Unknown lead")
    try:
        return await tasks.create(user["tenant_id"], body.title, body.notes, body.due_at,
                                  lead_id=body.lead_id)
    except tasks.TaskError as exc:
        raise HTTPException(400, str(exc))


@router.patch("/owner/tasks/{task_id}")
async def owner_task_update(task_id: int, body: TaskUpdate,
                            user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    if not await db.pool().fetchval("SELECT 1 FROM tasks WHERE id=$1 AND tenant_id=$2",
                                    task_id, user["tenant_id"]):
        raise HTTPException(404, "Unknown to-do")
    try:
        row = await tasks.update(task_id, body.model_dump(exclude_unset=True))
    except tasks.TaskError as exc:
        raise HTTPException(400, str(exc))
    if row is None:
        raise HTTPException(404, "Unknown to-do")
    return row


@router.delete("/owner/tasks/{task_id}")
async def owner_task_delete(task_id: int, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    if not await db.pool().fetchval("SELECT 1 FROM tasks WHERE id=$1 AND tenant_id=$2",
                                    task_id, user["tenant_id"]):
        raise HTTPException(404, "Unknown to-do")
    return {"deleted": await tasks.delete(task_id)}


class CompanyBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    domain: str = Field(default="", max_length=200)
    notes: str = Field(default="", max_length=1000)


class CompanyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    domain: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=1000)
    parent_id: str | None = None


class Assignee(BaseModel):
    user_id: str | None = None


async def _require_member(tenant_id, user_id: str) -> str | None:
    """An assignee must be someone who can actually get in to this workspace."""
    if user_id in (None, "", "unassigned"):
        return None
    try:
        found = await db.pool().fetchval(
            "SELECT id FROM tenant_users WHERE id=$1::uuid AND tenant_id=$2 AND active", user_id, tenant_id)
    except Exception:
        raise HTTPException(400, "Invalid team member id")
    if not found:
        raise HTTPException(404, "That person is not on your team")
    return str(found)


async def _require_company(tenant_id, company_id: str) -> str:
    try:
        found = await db.pool().fetchval(
            "SELECT id FROM companies WHERE id=$1::uuid AND tenant_id=$2", company_id, tenant_id)
    except Exception:
        raise HTTPException(400, "Invalid company id")
    if not found:
        raise HTTPException(404, "Unknown company")
    return str(found)


@router.get("/owner/companies")
async def owner_companies(user: dict = Depends(owner_auth.current_user)):
    """Companies, each with the people and open value attached to it."""
    rows = await db.pool().fetch(
        """
        SELECT c.id, c.name, c.domain, c.notes, c.parent_id,
               (SELECT count(*) FROM customer_cases k WHERE k.company_id = c.id) AS contacts,
               (SELECT count(*) FROM leads l JOIN customer_cases k ON l.case_id = k.id
                 WHERE k.company_id = c.id AND l.status IN ('new','contacted','booked')) AS open_deals,
               (SELECT coalesce(sum(l.value_cents),0) FROM leads l JOIN customer_cases k ON l.case_id = k.id
                 WHERE k.company_id = c.id AND l.status IN ('new','contacted','booked')) AS open_value_cents
          FROM companies c WHERE c.tenant_id = $1 ORDER BY c.name
        """, user["tenant_id"])
    return [dict(row) for row in rows]


@router.post("/owner/companies", status_code=201)
async def owner_company_create(body: CompanyBody, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    try:
        row = await db.pool().fetchrow(
            "INSERT INTO companies (tenant_id, name, domain, notes) VALUES ($1,$2,$3,$4) RETURNING *",
            user["tenant_id"], body.name.strip(), body.domain.strip(), body.notes.strip())
    except Exception:
        raise HTTPException(409, "You already have a company with that name")
    return dict(row)


@router.patch("/owner/companies/{company_id}")
async def owner_company_update(company_id: str, body: CompanyUpdate,
                               user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    sent = body.model_dump(exclude_unset=True)
    # `parent_id: null` is a real instruction ("stand this company on its own"), not an absent
    # value. Filtering None out of everything made un-nesting impossible: the route answered
    # "Nothing to update" and the page silently left the old parent in place.
    fields = {k: v for k, v in sent.items() if v is not None or k == "parent_id"}
    if not fields:
        raise HTTPException(400, "Nothing to update")
    if "parent_id" in fields:
        fields["parent_id"] = (await _require_company(user["tenant_id"], fields["parent_id"])
                               if fields["parent_id"] else None)
    parts = [f"{col} = ${i}" for i, col in enumerate(fields, start=3)]
    row = await db.pool().fetchrow(
        f"UPDATE companies SET {', '.join(parts)}, updated_at = now() "
        "WHERE id = $1::uuid AND tenant_id = $2 RETURNING *",
        company_id, user["tenant_id"], *fields.values())
    if row is None:
        raise HTTPException(404, "Unknown company")
    return dict(row)


@router.delete("/owner/companies/{company_id}")
async def owner_company_delete(company_id: str, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    gone = await db.pool().fetchval(
        "DELETE FROM companies WHERE id=$1::uuid AND tenant_id=$2 RETURNING id",
        company_id, user["tenant_id"])
    if gone is None:
        raise HTTPException(404, "Unknown company")
    return {"deleted": True}


@router.put("/owner/contacts/{case_key}/company")
async def owner_contact_company(case_key: str, body: dict,
                                user: dict = Depends(owner_auth.current_user)):
    """Put a person inside a company, or take them out of one."""
    owner_auth.require_role(user, "editor")
    company_id = await _require_company(user["tenant_id"], body.get("company_id")) if body.get("company_id") else None
    row = await db.pool().fetchrow(
        "UPDATE customer_cases SET company_id=$3, updated_at=now() "
        "WHERE tenant_id=$1 AND case_key=$2 RETURNING case_key",
        user["tenant_id"], case_key.strip().lower()[:200], company_id)
    if row is None:
        raise HTTPException(404, "Unknown contact")
    return {"case_key": row["case_key"], "company_id": company_id}


@router.put("/owner/contacts/{case_key}/assignee")
async def owner_contact_assignee(case_key: str, body: Assignee,
                                 user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    assignee = await _require_member(user["tenant_id"], body.user_id)
    row = await db.pool().fetchrow(
        "UPDATE customer_cases SET assigned_to=$3, updated_at=now() "
        "WHERE tenant_id=$1 AND case_key=$2 RETURNING case_key",
        user["tenant_id"], case_key.strip().lower()[:200], assignee)
    if row is None:
        raise HTTPException(404, "Unknown contact")
    return {"case_key": row["case_key"], "assigned_to": assignee}


@router.put("/owner/crm/leads/{lead_id}/assignee")
async def owner_lead_assignee(lead_id: str, body: Assignee,
                              user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    assignee = await _require_member(user["tenant_id"], body.user_id)
    try:
        row = await db.pool().fetchrow(
            "UPDATE leads SET assigned_to=$3, updated_at=now() "
            "WHERE id=$1::uuid AND tenant_id=$2 RETURNING id, assigned_to",
            lead_id, user["tenant_id"], assignee)
    except Exception:
        raise HTTPException(404, "Enquiry not found")
    if row is None:
        raise HTTPException(404, "Enquiry not found")
    return {"id": str(row["id"]),
            "assigned_to": str(row["assigned_to"]) if row["assigned_to"] else None}


class BulkAssign(BaseModel):
    case_keys: list[str] = Field(min_length=1, max_length=200)
    user_id: str | None = None


@router.post("/owner/contacts/bulk-assign")
async def owner_contacts_bulk_assign(body: BulkAssign, user: dict = Depends(owner_auth.current_user)):
    """Give a batch of people the same owner, or take the owner off all of them.

    A team that cannot reassign twenty contacts at once will not use ownership at all.
    """
    owner_auth.require_role(user, "editor")
    assignee = await _require_member(user["tenant_id"], body.user_id)
    keys = [key.strip().lower()[:200] for key in body.case_keys if key.strip()]
    updated = await db.pool().fetch(
        "UPDATE customer_cases SET assigned_to=$3, updated_at=now() "
        "WHERE tenant_id=$1 AND case_key = ANY($2::text[]) RETURNING case_key",
        user["tenant_id"], keys, assignee)
    return {"updated": len(updated), "assigned_to": assignee, "case_keys": [r["case_key"] for r in updated]}


def _csv_row(*cells) -> str:
    out = []
    for cell in cells:
        text = "" if cell is None else str(cell)
        out.append('"' + text.replace('"', '""') + '"' if any(ch in text for ch in ',"\n') else text)
    return ",".join(out)


@router.get("/owner/reports/export.csv")
async def owner_reports_export(days: int = 30, user: dict = Depends(owner_auth.current_user)):
    """What a business needs to hand to an accountant or a spreadsheet.

    The reports page could show the numbers but not let them leave, and it had no lost-reason or
    source breakdown at all -- the two questions every owner asks first.
    """
    owner_auth.require_role(user, "viewer")
    rows = await db.pool().fetch(
        """
        SELECT l.status, l.channel, l.lost_reason, count(*) AS enquiries,
               coalesce(sum(l.value_cents),0) AS value_cents
          FROM leads l
         WHERE l.tenant_id = $1 AND l.created_at > now() - make_interval(days => $2)
         GROUP BY l.status, l.channel, l.lost_reason
         ORDER BY l.status, enquiries DESC
        """, user["tenant_id"], max(1, min(days, 365)))
    quotes = await db.pool().fetch(
        """
        SELECT status, count(*) AS quotes, coalesce(sum(total_cents),0) AS total_cents
          FROM quotations WHERE tenant_id = $1 AND created_at > now() - make_interval(days => $2)
         GROUP BY status ORDER BY status
        """, user["tenant_id"], max(1, min(days, 365)))
    lines = ["section,stage_or_status,channel,lost_reason,count,value_cents"]
    for row in rows:
        lines.append(_csv_row("enquiries", row["status"], row["channel"], row["lost_reason"],
                              row["enquiries"], row["value_cents"]))
    for row in quotes:
        lines.append(_csv_row("quotes", row["status"], "", "", row["quotes"], row["total_cents"]))
    return Response("\n".join(lines) + "\n", media_type="text/csv",
                    headers={"Content-Disposition": "attachment; filename=concierge-report.csv"})


@router.patch("/owner/crm/leads/{lead_id}")
async def owner_crm_update(lead_id: str, body: LeadUpdate, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    try:
        exists = await db.pool().fetchval("SELECT 1 FROM leads WHERE tenant_id=$1 AND id=$2::uuid",
                                          user["tenant_id"], lead_id)
    except Exception:
        raise HTTPException(404, "Enquiry not found")
    if not exists:
        raise HTTPException(404, "Enquiry not found")
    updated = await admin_update_lead(lead_id, body)
    if body.status:
        await db.pool().execute(
            "UPDATE lead_events SET actor=$2 WHERE lead_id=$1::uuid AND actor='' "
            "AND id = (SELECT max(id) FROM lead_events WHERE lead_id=$1::uuid)",
            lead_id, user.get("email") or "")
    return updated


class CaseTakeoverRequest(BaseModel):
    paused: bool


@router.get("/owner/crm/leads/{lead_id}/case")
async def owner_lead_case(lead_id: str, user: dict = Depends(owner_auth.current_user)):
    """The customer's unified case: every channel, one history, plus the response deadline.

    Scoped to the caller's tenant by joining through `leads`, so a lead id from another business
    resolves to nothing rather than to their data.
    """
    tenant = await tenants.get_by_id(user["tenant_id"])
    lead = await db.pool().fetchrow(
        "SELECT id, case_id, name, phone, email, message, status, created_at, channel "
        "FROM leads WHERE tenant_id=$1 AND id=$2::uuid",
        user["tenant_id"], lead_id)
    if not lead:
        raise HTTPException(404, "Enquiry not found")

    events = []
    case = None
    if lead["case_id"]:
        case = await db.pool().fetchrow(
            "SELECT case_key, primary_phone, primary_email, automation_paused, takeover_at "
            "FROM customer_cases WHERE tenant_id=$1 AND id=$2",
            user["tenant_id"], lead["case_id"])
        if case:
            events = await casetimeline.timeline(
                user["tenant_id"], case["case_key"], limit=200)

    return {
        "lead_id": str(lead["id"]),
        "case_key": case["case_key"] if case else None,
        "automation_paused": bool(case["automation_paused"]) if case else False,
        "takeover_at": case["takeover_at"].isoformat() if case and case["takeover_at"] else None,
        "channels_seen": sorted({e["channel"] for e in events}),
        "event_count": len(events),
        "events": [
            {
                "channel": e["channel"],
                "direction": e["direction"],
                "body": e["body"],
                "occurred_at": e["occurred_at"].isoformat() if e["occurred_at"] else None,
                "answered_at": e["answered_at"].isoformat() if e["answered_at"] else None,
            }
            for e in events
        ],
        "deadline": hermes_orchestrator.deadline_state(
            tenant or {}, {"created_at": lead["created_at"]}),
    }


class ContactTakeover(BaseModel):
    paused: bool
    reason: str = ""


class PaymentSettings(BaseModel):
    instructions: str = ""
    url: str = ""


class QuotePaymentAction(BaseModel):
    action: str = "confirm"       # confirm | waive
    reference: str = ""


@router.get("/owner/revenue")
async def owner_revenue(days: int = 30, user: dict = Depends(owner_auth.current_user)):
    """What the AI brought in, in money, with the previous period beside it."""
    return await revenue.report(user["tenant_id"], days)


class BusinessDetails(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=160)
    gst_number: str = Field(default='', max_length=32)
    nzbn: str = Field(default='', max_length=32)
    business_address: str = Field(default='', max_length=500)
    business_phone: str = Field(default='', max_length=64)
    quote_terms: str = Field(default='', max_length=4000)
    quote_valid_days: int = Field(default=30, ge=1, le=365)
    allow_deposit: bool = True
    deposit_percent: int = Field(default=50, ge=0, le=100)
    invoice_payment_terms_days: int = Field(default=7, ge=0, le=120)


class AskBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=1000)


@router.post("/owner/ask")
async def owner_ask_route(body: AskBody, user: dict = Depends(owner_auth.current_user)):
    """Read-only questions about the owner's own business. No tools, nothing is sent or changed."""
    tenant = await tenants.get_by_id(user["tenant_id"])
    try:
        return {"answer": await owner_ask.ask(tenant, body.question)}
    except llm.LLMNotConfigured:
        raise HTTPException(503, "Ask is not available right now")


@router.get("/owner/business")
async def owner_business(user: dict = Depends(owner_auth.current_user)):
    row = await db.pool().fetchrow(
        'SELECT name,gst_number,nzbn,business_address,business_phone,quote_terms,quote_valid_days,'
        'allow_deposit,deposit_percent,invoice_payment_terms_days '
        'FROM tenants WHERE id=$1', user["tenant_id"])
    return dict(row)


@router.put("/owner/business")
async def owner_business_update(body: BusinessDetails, user: dict = Depends(owner_auth.current_user)):
    """The details every quotation prints: who issued it, their GST number, and how long it holds."""
    owner_auth.require_role(user, "editor")
    row = await db.pool().fetchrow(
        'UPDATE tenants SET name=$2, gst_number=$3, nzbn=$4, business_address=$5, business_phone=$6, '
        'quote_terms=$7, quote_valid_days=$8, allow_deposit=$9, deposit_percent=$10, '
        'invoice_payment_terms_days=$11 WHERE id=$1 '
        'RETURNING name,gst_number,nzbn,business_address,business_phone,quote_terms,quote_valid_days,'
        'allow_deposit,deposit_percent,invoice_payment_terms_days',
        user["tenant_id"], body.name.strip(), body.gst_number.strip(), body.nzbn.strip(),
        body.business_address.strip(), body.business_phone.strip(), body.quote_terms.strip(),
        body.quote_valid_days, body.allow_deposit, body.deposit_percent,
        body.invoice_payment_terms_days)
    return dict(row)


@router.get("/owner/payment-settings")
async def owner_payment_settings(user: dict = Depends(owner_auth.current_user)):
    """How this business asks to be paid, and what money is in flight. Processor-free by design."""
    tenant = await db.pool().fetchrow(
        "SELECT payment_instructions, payment_url FROM tenants WHERE id=$1", user["tenant_id"])
    return {
        "instructions": (tenant["payment_instructions"] if tenant else "") or "",
        "url": (tenant["payment_url"] if tenant else "") or "",
        "summary": await quote_payments.summary(user["tenant_id"]),
    }


@router.put("/owner/payment-settings")
async def owner_set_payment_settings(
    body: PaymentSettings, user: dict = Depends(owner_auth.current_user)
):
    owner_auth.require_role(user, "owner")
    url = body.url.strip()
    if url and not url.lower().startswith(("http://", "https://")):
        raise HTTPException(422, "The payment link must start with http:// or https://")
    await db.pool().execute(
        "UPDATE tenants SET payment_instructions=$2, payment_url=$3 WHERE id=$1",
        user["tenant_id"], body.instructions.strip()[:2000], url[:500])
    return {"ok": True}


@router.post("/owner/crm/quotations/{quote_id}/payment")
async def owner_quote_payment(
    quote_id: str, body: QuotePaymentAction, user: dict = Depends(owner_auth.current_user)
):
    """Confirm the money arrived (the only path to paid) or waive it."""
    owner_auth.require_role(user, "owner")
    if body.action not in ("confirm", "waive"):
        raise HTTPException(422, "action must be confirm or waive")
    row = await db.pool().fetchrow(
        "SELECT * FROM quotations WHERE tenant_id=$1 AND id=$2::uuid",
        user["tenant_id"], quote_id)
    if not row:
        raise HTTPException(404, "Quotation not found")
    quote = quotations.view(row)
    result = await quote_payments.confirm(
        quote, by=user.get("email") or "owner", waive=body.action == "waive")
    if not result.get("ok"):
        raise HTTPException(409, result.get("reason") or "That quotation cannot be updated")
    return result


@router.get("/owner/contacts")
async def owner_contacts(
    limit: int = 50, q: str = "", user: dict = Depends(owner_auth.current_user)
):
    """One row per customer, not per enquiry — the list behind the unified timeline.

    Covers the competitor-gap item C: GoHighLevel's real moat is a single Conversations inbox, and
    Concierge already merges the channels at the case level (casetimeline). This exposes it.
    """
    rows = await db.pool().fetch(
        """
        SELECT c.case_key, c.display_name, c.company, c.primary_phone, c.primary_email,
               c.assigned_to, c.company_id,
               (SELECT u.email FROM tenant_users u WHERE u.id = c.assigned_to) AS assignee_email,
               (SELECT co.name FROM companies co WHERE co.id = c.company_id) AS company_name,
               c.automation_paused, c.takeover_at, c.updated_at,
               (SELECT count(*) FROM case_events e WHERE e.case_id = c.id) AS event_count,
               (SELECT string_agg(DISTINCT e.channel, ',') FROM case_events e
                 WHERE e.case_id = c.id) AS channels,
               (SELECT max(e.occurred_at) FROM case_events e WHERE e.case_id = c.id) AS last_at
        FROM customer_cases c
        WHERE c.tenant_id = $1
          AND ($2 = '' OR c.display_name ILIKE '%' || $2 || '%'
               OR c.primary_phone LIKE '%' || $2 || '%'
               OR c.primary_email ILIKE '%' || $2 || '%')
        -- Postgres will not accept a select alias inside an expression here: ORDER BY last_at
        -- works, ORDER BY COALESCE(last_at, ...) does not, and it failed at prepare time with
        -- "column last_at does not exist". Repeat the subquery instead; it is one index hit.
        ORDER BY COALESCE((SELECT max(e.occurred_at) FROM case_events e WHERE e.case_id = c.id),
                          c.updated_at) DESC
        LIMIT $3
        """,
        user["tenant_id"], q.strip(), max(1, min(limit, 200)),
    )
    contacts = []
    for row in rows:
        item = dict(row)
        channels = [c for c in (item.pop("channels", "") or "").split(",") if c]
        item["channels"] = sorted(channels)
        item["label"] = casetimeline.contact_label(item)
        item["last_at"] = item["last_at"].isoformat() if item.get("last_at") else None
        item["updated_at"] = item["updated_at"].isoformat() if item.get("updated_at") else None
        item["takeover_at"] = item["takeover_at"].isoformat() if item.get("takeover_at") else None
        contacts.append(item)
    return {"contacts": contacts, "count": len(contacts)}


class AddressIn(BaseModel):
    kind: Literal["phone", "email"]
    value: str = Field(min_length=1, max_length=200)
    label: str = Field(default="", max_length=60)


class ImportIn(BaseModel):
    format: Literal["csv", "json"] = "csv"
    data: str = Field(default="", max_length=2_000_000)
    contacts: list[dict] = Field(default_factory=list)


class WebhookIn(BaseModel):
    url: str = Field(min_length=8, max_length=500)
    secret: str = Field(min_length=16, max_length=200)


async def _case_id_for(user: dict, case_key: str):
    row = await db.pool().fetchrow(
        "SELECT id FROM customer_cases WHERE tenant_id=$1 AND case_key=$2",
        user["tenant_id"], case_key)
    if not row:
        raise HTTPException(404, "Customer not found")
    return row["id"]


@router.get("/owner/contacts/{case_key}/addresses")
async def owner_addresses(case_key: str, user: dict = Depends(owner_auth.current_user)):
    case_id = await _case_id_for(user, case_key)
    return {"addresses": await casetimeline.list_addresses(user["tenant_id"], case_id)}


@router.post("/owner/contacts/{case_key}/addresses", status_code=201)
async def owner_add_address(case_key: str, body: AddressIn,
                            user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    case_id = await _case_id_for(user, case_key)
    try:
        tenant = await db.pool().fetchrow("SELECT * FROM tenants WHERE id=$1", user["tenant_id"])
        address = await casetimeline.add_address(
            user["tenant_id"], case_id, kind=body.kind, value=body.value, label=body.label,
            default_cc=casetimeline.tenant_country_code(dict(tenant) if tenant else None))
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return address


@router.delete("/owner/contacts/{case_key}/addresses/{address_id}")
async def owner_remove_address(case_key: str, address_id: int,
                               user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "editor")
    case_id = await _case_id_for(user, case_key)
    try:
        removed = await casetimeline.remove_address(user["tenant_id"], case_id, address_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    if not removed:
        raise HTTPException(404, "Address not found")
    return {"removed": True}


@router.get("/owner/export/contacts")
async def owner_export_contacts(format: Literal["json", "csv"] = "json",
                                user: dict = Depends(owner_auth.current_user)):
    """Take your customer list with you: JSON for a CRM importer, CSV for a spreadsheet.

    This is the promise that nobody is locked in. It is a plain GET so it also works from a
    browser address bar, with the session cookie.
    """
    contacts = await portability.export_contacts(user["tenant_id"])
    if format == "csv":
        return Response(content=portability.to_csv(contacts), media_type="text/csv",
                        headers={"Content-Disposition": 'attachment; filename="customers.csv"'})
    return {"contacts": contacts, "count": len(contacts)}


@router.post("/owner/import/contacts")
async def owner_import_contacts(body: ImportIn, user: dict = Depends(owner_auth.current_user)):
    """Bring your existing customer list in. Safe to run twice: matches on any known address."""
    owner_auth.require_role(user, "editor")
    if body.format == "csv":
        rows = portability.parse_import(body.data)
    else:
        rows = [{"name": c.get("name") or c.get("display_name") or "",
                 "phone": c.get("phone") or c.get("primary_phone") or "",
                 "email": c.get("email") or c.get("primary_email") or "",
                 "extra": c.get("extra") or ""} for c in body.contacts]
    if not rows:
        raise HTTPException(400, "Nothing to import: no rows found")
    tenant = await db.pool().fetchrow("SELECT * FROM tenants WHERE id=$1", user["tenant_id"])
    result = await portability.import_contacts(
        user["tenant_id"], rows,
        default_cc=casetimeline.tenant_country_code(dict(tenant) if tenant else None))
    return result


@router.get("/owner/webhooks")
async def owner_get_webhook(user: dict = Depends(owner_auth.current_user)):
    """Where new customers are pushed, if this business runs its own CRM."""
    return {"webhook": await portability.get_webhook(user["tenant_id"])}


@router.post("/owner/webhooks")
async def owner_set_webhook(body: WebhookIn, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    if not body.url.startswith("https://"):
        raise HTTPException(400, "Use an https address for your CRM endpoint")
    return await portability.set_webhook(user["tenant_id"], body.url.strip(), body.secret)


@router.delete("/owner/webhooks")
async def owner_delete_webhook(user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    await portability.delete_webhook(user["tenant_id"])
    return {"removed": True}


@router.post("/owner/webhooks/deliver")
async def owner_deliver_webhook(user: dict = Depends(owner_auth.current_user)):
    """Retry anything queued, for when their endpoint was down."""
    owner_auth.require_role(user, "owner")
    return await portability.deliver_pending(user["tenant_id"])


@router.get("/owner/contacts/{case_key}/timeline")
async def owner_contact_timeline(
    case_key: str, limit: int = 200, user: dict = Depends(owner_auth.current_user)
):
    """Everything that ever happened with one customer, newest first, across every channel."""
    case = await db.pool().fetchrow(
        "SELECT * FROM customer_cases WHERE tenant_id=$1 AND case_key=$2",
        user["tenant_id"], case_key,
    )
    if not case:
        raise HTTPException(404, "Contact not found")
    events = await casetimeline.timeline(user["tenant_id"], case_key, limit=limit)
    leads = await db.pool().fetch(
        "SELECT id, status, channel, message, created_at FROM leads "
        "WHERE tenant_id=$1 AND case_id=$2 ORDER BY created_at DESC LIMIT 50",
        user["tenant_id"], case["id"],
    )
    lead_ids = [row["id"] for row in leads]
    appointments = await db.pool().fetch(
        "SELECT starts_at, status, name FROM appointments "
        "WHERE tenant_id=$1 AND lead_id = ANY($2::uuid[]) ORDER BY starts_at DESC LIMIT 50",
        user["tenant_id"], lead_ids,
    ) if lead_ids else []
    summary = casetimeline.summarise(events)
    return {
        "case_key": case_key,
        "label": casetimeline.contact_label(dict(case)),
        "phone": case["primary_phone"],
        "email": case["primary_email"],
        "automation_paused": bool(case["automation_paused"]),
        "takeover_at": case["takeover_at"].isoformat() if case["takeover_at"] else None,
        **summary,
        "events": [
            {
                "channel": e["channel"],
                "channel_label": casetimeline.CHANNEL_LABELS.get(e["channel"], e["channel"].title()),
                "direction": e["direction"],
                "body": e["body"],
                "occurred_at": e["occurred_at"].isoformat() if e["occurred_at"] else None,
                "answered_at": e["answered_at"].isoformat() if e["answered_at"] else None,
            }
            for e in events
        ],
        "enquiries": [
            {"id": str(row["id"]), "status": row["status"], "channel": row["channel"],
             "message": row["message"],
             "created_at": row["created_at"].isoformat() if row["created_at"] else None}
            for row in leads
        ],
        "appointments": [
            {"starts_at": row["starts_at"].isoformat() if row["starts_at"] else None,
             "status": row["status"], "name": row["name"]}
            for row in appointments
        ],
    }


@router.put("/owner/contacts/{case_key}/takeover")
async def owner_contact_takeover(
    case_key: str, body: ContactTakeover, user: dict = Depends(owner_auth.current_user)
):
    """Pause or resume the assistant for one customer, from the unified timeline.

    Same store as the enquiry-level takeover, so the two screens can never disagree about who is
    handling the customer.
    """
    if body.paused and not body.reason.strip():
        raise HTTPException(422, "Say why you are taking over; it is recorded for the customer's history")
    changed = await casetimeline.set_takeover(
        user["tenant_id"], case_key=case_key, paused=body.paused,
        by=f"{user.get('email') or user.get('role') or 'owner'}: {body.reason}".strip(": "),
    )
    if not changed:
        raise HTTPException(404, "Contact not found")
    return {"paused": body.paused, "case_key": case_key}


@router.post("/owner/crm/leads/{lead_id}/takeover")
async def owner_lead_takeover(
    lead_id: str, body: CaseTakeoverRequest, user: dict = Depends(owner_auth.current_user)
):
    """Take over, or hand back, one customer.

    Pausing stops the assistant replying to that person on every channel, which is what an owner
    needs the moment they start answering themselves. It is deliberately available to any signed-in
    member of the business: the person handling the customer is exactly who needs to press it.
    """
    lead = await db.pool().fetchrow(
        "SELECT case_id FROM leads WHERE tenant_id=$1 AND id=$2::uuid", user["tenant_id"], lead_id)
    if not lead:
        raise HTTPException(404, "Enquiry not found")
    if not lead["case_id"]:
        raise HTTPException(409, "This enquiry has no conversation history to take over yet")

    case = await db.pool().fetchrow(
        "SELECT case_key FROM customer_cases WHERE tenant_id=$1 AND id=$2",
        user["tenant_id"], lead["case_id"])
    if not case:
        raise HTTPException(404, "Customer case not found")

    changed = await casetimeline.set_takeover(
        user["tenant_id"], case_key=case["case_key"], paused=body.paused,
        by=str(user.get("email") or user.get("id") or "owner"),
    )
    return {"lead_id": lead_id, "automation_paused": bool(body.paused), "updated": changed}
