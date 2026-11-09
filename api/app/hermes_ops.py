"""Internal operations for the Hermes gateway (concierge-stack/hermes-gateway).

Dark by default: every route answers 404 unless HERMES_GATEWAY_ENABLED=true AND HERMES_GATEWAY_KEY is set, and the key is
compared in constant time. The gateway is the only intended caller; it has already verified a tenant-scoped capability and
validated Hermes's plan. This module does NOT rely on that: it re-checks tenant ownership, case version, human takeover,
opt-out, channel authorization and recipient identity, and records every action under an idempotency key.

Nothing here sends anything. A reply becomes a human-reviewed row in `email_drafts` (the owner approves it in the portal, which
queues the existing outbox), a to-do for the owner, or a case pause. "Auto" delivery is deliberately treated like
"needs approval" until an operator opts in with a separate, future setting.

A "case" is a lead. Its version is the newest of: the lead's last update, its conversation's last message and its Hermes
state, in milliseconds, so any customer-visible change makes a plan made earlier stale.
"""
import hmac
import json
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from . import channel_authorization, db, tenants
from .config import get_settings
from .contact import contact_key

ACTION_OPS = {"prepare_reply", "prepare_quote", "request_booking", "schedule_followup", "escalate_case",
              "get_case_context", "search_business_knowledge", "get_channel_readiness", "check_availability", "get_action_status"}
CUSTOMER_AFFECTING = {"request_booking", "schedule_followup"}
READ_ONLY = {"get_case_context", "search_business_knowledge", "get_channel_readiness", "check_availability", "get_action_status"}
EVIDENCE_CAP = 100_000


def require_gateway(x_hermes_gateway_key: str = Header(default="")) -> None:
    s = get_settings()
    if not s.hermes_gateway_enabled or not s.hermes_gateway_key:
        raise HTTPException(404, "Not found")  # indistinguishable from a route that does not exist
    if not hmac.compare_digest(x_hermes_gateway_key.encode(), s.hermes_gateway_key.encode()):
        raise HTTPException(401, "Invalid gateway key")


router = APIRouter(prefix="/internal/hermes", tags=["hermes"], dependencies=[Depends(require_gateway)])


async def _lead(conn, tenant_id, lead_id, lock: bool = False):
    row = await conn.fetchrow(f"SELECT * FROM leads WHERE tenant_id=$1 AND id=$2{' FOR UPDATE' if lock else ''}", tenant_id, lead_id)
    if not row:
        raise HTTPException(404, "Case not found")  # also the answer for another tenant's case
    return dict(row)


async def _version(conn, tenant_id, lead_id) -> int:
    return int(await conn.fetchval(
        """
        SELECT floor(extract(epoch FROM greatest(
                 l.created_at, l.updated_at, COALESCE(st.updated_at, l.created_at),
                 COALESCE((SELECT max(m.created_at) FROM messages m WHERE m.conversation_id = l.conversation_id), l.created_at)
               )) * 1000)::bigint
        FROM leads l LEFT JOIN hermes_case_state st ON st.tenant_id = l.tenant_id AND st.lead_id = l.id
        WHERE l.tenant_id = $1 AND l.id = $2
        """, tenant_id, lead_id))


async def _paused(conn, tenant_id, lead_id) -> bool:
    return bool(await conn.fetchval("SELECT automation_paused FROM hermes_case_state WHERE tenant_id=$1 AND lead_id=$2", tenant_id, lead_id))


async def _settings(conn, tenant_id) -> tuple[str, float]:
    row = await conn.fetchrow("SELECT autonomy, min_confidence FROM hermes_tenant_settings WHERE tenant_id=$1", tenant_id)
    return (row["autonomy"], float(row["min_confidence"])) if row else ("shadow", 0.8)


def _contacts(lead: dict) -> list[str]:
    cc = get_settings().default_country_code
    return sorted({k for k in (contact_key(lead.get("email") or "", cc), contact_key(lead.get("phone") or "", cc)) if k})


@router.get("/cases/{lead_id}/policy-context")
async def policy_context(lead_id: UUID, tenant_id: UUID):
    """Everything the gateway's policy needs, derived on the server. The gateway never accepts these from the model."""
    tenant = await tenants.get_by_id(tenant_id)
    if not tenant:
        raise HTTPException(404, "Case not found")
    pool = db.pool()
    lead = await _lead(pool, tenant_id, lead_id)
    contacts = _contacts(lead)
    suppressed = [r["contact"] for r in await pool.fetch("SELECT contact FROM opt_outs WHERE tenant_id=$1 AND contact = ANY($2::text[])", tenant_id, contacts)]
    chunks = await pool.fetch("SELECT content FROM chunks WHERE tenant_id=$1 AND content LIKE '%$%' ORDER BY id LIMIT 300", tenant_id)
    evidence = "\n".join([tenant.get("persona") or "", tenant.get("incentive") or "", *[c["content"] for c in chunks]])[:EVIDENCE_CAP]
    autonomy, min_confidence = await _settings(pool, tenant_id)
    return {
        "tenant_id": str(tenant_id), "case_id": str(lead_id), "case_version": await _version(pool, tenant_id, lead_id),
        "automation_paused": await _paused(pool, tenant_id, lead_id), "timezone": tenant.get("timezone") or "UTC",
        "default_country_code": get_settings().default_country_code,
        "email_send_authorized": await channel_authorization.is_authorized(tenant_id, "email_send"),
        "sms_send_authorized": await channel_authorization.is_authorized(tenant_id, "sms_send"),
        "case_contacts": contacts, "suppressed": suppressed, "knowledge_evidence": evidence,
        "autonomy": autonomy, "min_confidence": min_confidence, "approvals": {},
    }


class AutomationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: UUID
    paused: bool


@router.put("/cases/{lead_id}/automation")
async def set_automation(lead_id: UUID, body: AutomationBody):
    """Human takeover (paused=true) or release. Bumps the case version so queued plans go stale."""
    pool = db.pool()
    await _lead(pool, body.tenant_id, lead_id)
    await pool.execute(
        "INSERT INTO hermes_case_state(tenant_id, lead_id, automation_paused, updated_at) VALUES($1,$2,$3,now()) "
        "ON CONFLICT (tenant_id, lead_id) DO UPDATE SET automation_paused=EXCLUDED.automation_paused, updated_at=now()",
        body.tenant_id, lead_id, body.paused)
    return {"case_id": str(lead_id), "automation_paused": body.paused}


class Action(BaseModel):
    model_config = ConfigDict(extra="forbid")
    op: str = Field(max_length=64)
    idempotency_key: str = Field(min_length=1, max_length=128)
    dedupe_key: str = Field(max_length=300)
    fingerprint: str = Field(min_length=1, max_length=128)
    case_version: int
    params: dict = Field(default_factory=dict)


class Delivery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    channel: Literal["email", "sms"]
    recipient: str = Field(max_length=320)
    subject: str = Field(default="", max_length=300)
    body: str = Field(min_length=1, max_length=4000)
    mode: Literal["shadow_only", "needs_approval", "auto"]
    fingerprint: str = Field(min_length=1, max_length=128)
    dedupe_key: str = Field(min_length=1, max_length=300)
    send_at: str = ""


class Bundle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: str = Field(min_length=1, max_length=300)
    tenant_id: UUID
    actions: list[Action] = Field(default_factory=list, max_length=10)
    delivery: Delivery | None = None


def _conflict(code: str, detail: str = "") -> HTTPException:
    return HTTPException(409, {"error": code, "detail": detail})


async def _record(conn, tenant_id, lead_id, key: str, op: str, fingerprint: str, state: str, result: dict) -> dict | None:
    """First writer wins. Returns the stored result for an exact repeat, or None when this call created the record."""
    inserted = await conn.fetchrow(
        "INSERT INTO hermes_actions(tenant_id, idempotency_key, lead_id, op, fingerprint, state, result) VALUES($1,$2,$3,$4,$5,$6,$7::jsonb) "
        "ON CONFLICT (tenant_id, idempotency_key) DO NOTHING RETURNING 1", tenant_id, key, lead_id, op, fingerprint, state, json.dumps(result))
    if inserted:
        return None
    existing = await conn.fetchrow("SELECT lead_id, fingerprint, result FROM hermes_actions WHERE tenant_id=$1 AND idempotency_key=$2", tenant_id, key)
    if existing["fingerprint"] != fingerprint or existing["lead_id"] != lead_id:
        raise _conflict("key_reuse", "this idempotency key was used for a different request")
    stored = existing["result"]
    return json.loads(stored) if isinstance(stored, str) else dict(stored)


async def _task(conn, tenant_id, lead_id, title: str, notes: str, due_at: datetime | None = None) -> int:
    return int(await conn.fetchval(
        "INSERT INTO tasks (tenant_id, lead_id, title, notes, due_at, kind, source) VALUES ($1,$2,$3,$4,$5,'manual','hermes') RETURNING id",
        tenant_id, lead_id, title[:200], notes[:2000], due_at))


def _due(params: dict) -> datetime | None:
    raw = params.get("due_at")
    if not raw:
        return None
    try:
        due = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(422, {"error": "bad_due_at"}) from None
    if due.tzinfo is None:
        raise HTTPException(422, {"error": "due_at_needs_timezone"})
    return due


@router.post("/cases/{lead_id}/execute")
async def execute(lead_id: UUID, bundle: Bundle):
    """Execute a bundle the gateway validated. Re-verifies everything; all effects commit together or not at all."""
    tenant_id = bundle.tenant_id
    if not await tenants.get_by_id(tenant_id):
        raise HTTPException(404, "Case not found")
    async with db.pool().acquire() as conn:
        async with conn.transaction():
            lead = await _lead(conn, tenant_id, lead_id, lock=True)
            autonomy, _ = await _settings(conn, tenant_id)
            if autonomy == "shadow":
                raise _conflict("shadow_mode", "this business is in shadow mode; nothing executes")
            paused = await _paused(conn, tenant_id, lead_id)
            current = await _version(conn, tenant_id, lead_id)
            for a in bundle.actions:
                if a.op not in ACTION_OPS:
                    raise HTTPException(422, {"error": "unknown_operation", "op": a.op})
                if a.op in READ_ONLY:
                    continue
                if a.case_version != current:
                    raise _conflict("stale_case", f"planned against v{a.case_version}, case is v{current}")
                if paused and a.op in CUSTOMER_AFFECTING:
                    raise _conflict("automation_paused", a.op)
            d = bundle.delivery
            if d:
                if d.mode == "shadow_only":
                    raise _conflict("shadow_mode", "a shadow-only delivery cannot execute")
                if paused:
                    raise _conflict("automation_paused", "a person has taken over this case")
                if not await channel_authorization.is_authorized(tenant_id, "email_send" if d.channel == "email" else "sms_send"):
                    raise _conflict("channel_not_authorized")
                key = contact_key(d.recipient, get_settings().default_country_code)
                if key not in _contacts(lead):
                    raise _conflict("recipient_not_on_case")
                if await conn.fetchval("SELECT 1 FROM opt_outs WHERE tenant_id=$1 AND contact=$2", tenant_id, key):
                    raise _conflict("recipient_opted_out")
            results = []
            for a in bundle.actions:
                if a.op in READ_ONLY or a.op == "prepare_reply":
                    results.append({"op": a.op, "state": "noop"})  # replies travel as the delivery, never as an action
                    continue
                stored = await _record(conn, tenant_id, lead_id, a.idempotency_key, a.op, a.fingerprint, "done", {"op": a.op, "state": "pending"})
                if stored is not None:
                    results.append({**stored, "duplicate": True})
                    continue
                p = a.params
                if a.op == "schedule_followup":
                    tid = await _task(conn, tenant_id, lead_id, str(p.get("title") or "Follow up (suggested by Hermes)"), str(p.get("notes") or ""), _due(p))
                    out = {"op": a.op, "state": "task_created", "task_id": tid}
                elif a.op == "escalate_case":
                    tid = await _task(conn, tenant_id, lead_id, "Take over: " + str(p.get("reason") or "Hermes asked for a person")[:150], str(p.get("notes") or ""))
                    await conn.execute(
                        "INSERT INTO hermes_case_state(tenant_id, lead_id, automation_paused, updated_at) VALUES($1,$2,true,now()) "
                        "ON CONFLICT (tenant_id, lead_id) DO UPDATE SET automation_paused=true, updated_at=now()", tenant_id, lead_id)
                    out = {"op": a.op, "state": "escalated", "task_id": tid}
                else:  # request_booking / prepare_quote: no executor yet, so a person finishes it
                    tid = await _task(conn, tenant_id, lead_id, f"Hermes asked for: {a.op.replace('_', ' ')}", json.dumps(p, default=str)[:1800])
                    out = {"op": a.op, "state": "needs_human", "task_id": tid}
                await conn.execute("UPDATE hermes_actions SET result=$3::jsonb WHERE tenant_id=$1 AND idempotency_key=$2", tenant_id, a.idempotency_key, json.dumps(out))
                results.append(out)
            delivery_result = None
            if d:
                stored = await _record(conn, tenant_id, lead_id, d.dedupe_key, "delivery:" + d.channel, d.fingerprint, "done", {"state": "pending"})
                if stored is not None:
                    delivery_result = {**stored, "duplicate": True}
                elif d.channel == "email":
                    row = await conn.fetchrow(
                        "INSERT INTO email_drafts (tenant_id, source_id, sender, subject, inbound_body, reply_body) VALUES ($1,$2,$3,$4,$5,$6) "
                        "ON CONFLICT (tenant_id, source_id) WHERE source_id IS NOT NULL DO UPDATE SET source_id = EXCLUDED.source_id RETURNING id",
                        tenant_id, d.dedupe_key[:500], d.recipient.strip(), " ".join(d.subject.split())[:250],
                        (lead.get("message") or "(no inbound text)")[:20000], d.body[:10000])
                    delivery_result = {"state": "draft_created", "draft_id": int(row["id"]), "needs_human_approval": True}
                else:
                    tid = await _task(conn, tenant_id, lead_id, "Send this SMS reply (drafted by Hermes)", d.body)
                    delivery_result = {"state": "task_created", "task_id": tid, "needs_human_approval": True}
                await conn.execute("UPDATE hermes_actions SET result=$3::jsonb WHERE tenant_id=$1 AND idempotency_key=$2", tenant_id, d.dedupe_key, json.dumps(delivery_result))
    return {"task_id": bundle.task_id, "actions": results, "delivery": delivery_result}
