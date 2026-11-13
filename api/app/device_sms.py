"""Carrier-independent, tenant-bound SMS through a customer's paired phone.

The device uses outbound HTTPS and a scoped token. Claiming is irreversible:
lost/ambiguous sends need reconciliation, never an automatic second send.
"""
import hashlib
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal

from . import channel_authorization, db, tenants
from .config import get_settings

router = APIRouter(prefix="/api/v1/device-sms")
NUMBER = re.compile(r"^\+[1-9]\d{6,14}$")


class AwaitingReceipt(RuntimeError):
    """The durable phone job exists, but sending is not yet confirmed."""


class ReconciliationRequired(RuntimeError):
    pass


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def device_auth(request: Request) -> dict:
    header = request.headers.get("Authorization", "")
    token = header.removeprefix("Bearer ") if header.startswith("Bearer ") else ""
    if len(token) < 40 or len(token) > 256:
        raise HTTPException(401, "Device authentication required")
    row = await db.pool().fetchrow(
        "SELECT * FROM sms_devices WHERE token_hash=$1 AND enabled", token_hash(token)
    )
    if not row:
        raise HTTPException(401, "Device authentication required")
    tenant = await tenants.get_by_id(row["tenant_id"])
    receiving_receipt=request.url.path.endswith("/receipt")
    if (not tenant or (not receiving_receipt and (not tenant.get("sms_enabled") or tenant.get("sms_transport") != "device"
            or tenant.get("sms_from") != row["from_number"]))):
        raise HTTPException(403, "Device connection is not active for this business")
    return dict(row)


async def enqueue(tenant: dict, recipient: str, body: str, request_key: str,
                  outbox_id: int | None = None, operational: bool = False) -> str:
    if not tenant.get("sms_enabled") or tenant.get("sms_transport")!="device":
        raise ValueError("Paired-phone SMS is not enabled for this business")
    if not NUMBER.fullmatch(recipient) or not body.strip() or len(body) > 1500:
        raise ValueError("Invalid SMS recipient or body")
    if not await channel_authorization.is_authorized(tenant["id"], "sms_send"):
        raise ValueError("Business has not authorized outgoing SMS")
    device = await db.pool().fetchrow(
        "SELECT * FROM sms_devices WHERE tenant_id=$1 AND enabled", tenant["id"]
    )
    if not device or device["from_number"] != tenant.get("sms_from"):
        raise ValueError("This business has no matching phone connection")
    if outbox_id:
        # Activating a phone must not replay historical queued texts.
        valid = await db.pool().fetchval(
            "SELECT 1 FROM outbox WHERE id=$1 AND tenant_id=$2 AND created_at >= $3",
            outbox_id, tenant["id"], device["created_at"],
        )
        if not valid:
            raise ReconciliationRequired("Historical SMS requires owner review")
        operational = bool(await db.pool().fetchval(
            "SELECT 1 FROM outbox WHERE id=$1 AND tenant_id=$2 AND kind='owner_alert'",
            outbox_id, tenant["id"]))
    row = await db.pool().fetchrow(
        """INSERT INTO device_sms_jobs(tenant_id,device_id,outbox_id,request_key,recipient,body,operational)
           VALUES($1,$2,$3,$4,$5,$6,$7) ON CONFLICT(tenant_id,request_key)
           DO UPDATE SET request_key=EXCLUDED.request_key RETURNING *""",
        tenant["id"], device["id"], outbox_id, request_key, recipient, body, operational,
    )
    if row["recipient"] != recipient or row["body"] != body or row["device_id"] != device["id"]:
        raise ReconciliationRequired("SMS identity or content changed; review required")
    if row["status"] == "sent":
        return row["receipt"]
    if row["status"] in ("failed", "uncertain", "cancelled"):
        raise ReconciliationRequired("SMS outcome requires owner review")
    raise AwaitingReceipt(str(row["id"]))


@router.post("/poll")
async def poll(device: dict = Depends(device_auth)):
    await db.pool().execute("UPDATE sms_devices SET last_seen=now() WHERE id=$1", device["id"])
    if not await channel_authorization.is_authorized(device["tenant_id"], "sms_send"):
        return {"job": None}
    cancelled = await db.pool().fetch(
        """UPDATE device_sms_jobs j SET status='cancelled',finished_at=now()
           WHERE j.device_id=$1 AND j.status='queued' AND NOT j.operational AND (
             EXISTS(SELECT 1 FROM opt_outs o WHERE o.tenant_id=j.tenant_id AND o.contact=j.recipient)
             OR EXISTS(SELECT 1 FROM outbox o JOIN tenants t ON t.id=o.tenant_id
                       WHERE o.id=j.outbox_id AND o.campaign_id IS NOT NULL AND NOT t.campaigns_enabled))
           RETURNING outbox_id""", device["id"])
    for row in cancelled:
        if row["outbox_id"]:
            await db.pool().execute(
                "UPDATE outbox SET status='skipped',last_error='Recipient opted out or campaign disabled' "
                "WHERE id=$1 AND tenant_id=$2 AND status IN ('sending','awaiting_receipt')",
                row["outbox_id"], device["tenant_id"])
    expired = await db.pool().fetch(
        """UPDATE device_sms_jobs SET status='uncertain',finished_at=now()
           WHERE device_id=$1 AND status='claimed' AND claimed_at<now()-interval '5 minutes'
           RETURNING outbox_id""", device["id"]
    )
    for row in expired:
        if row["outbox_id"]:
            await db.pool().execute(
                "UPDATE outbox SET status='failed',last_error='Phone receipt missing; reconcile before retry' "
                "WHERE id=$1 AND tenant_id=$2 AND status IN ('sending','awaiting_receipt')",
                row["outbox_id"], device["tenant_id"],
            )
    job = await db.pool().fetchrow(
        """UPDATE device_sms_jobs SET status='claimed',claimed_at=now() WHERE id IN (
           SELECT id FROM device_sms_jobs WHERE device_id=$1 AND tenant_id=$2 AND status='queued'
           AND (outbox_id IS NULL OR (
             extract(hour from now() at time zone (SELECT timezone FROM tenants WHERE id=$2)) >= $3
             AND extract(hour from now() at time zone (SELECT timezone FROM tenants WHERE id=$2)) < $4))
           ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED) RETURNING id,recipient,body""",
        device["id"], device["tenant_id"],
        get_settings().sms_quiet_start_hour, get_settings().sms_quiet_end_hour,
    )
    return {"job": ({"id": str(job["id"]), "recipient": job["recipient"],
                     "body": job["body"], "from_number": device["from_number"]} if job else None)}


class Receipt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: uuid.UUID
    status: Literal["sent", "failed", "uncertain"]
    receipt: str = Field(default="", max_length=200)


@router.post("/receipt")
async def receipt(body: Receipt, device: dict = Depends(device_auth)):
    if body.status == "sent" and not body.receipt:
        raise HTTPException(422, "A verified Messages receipt is required")
    row = await db.pool().fetchrow(
        """UPDATE device_sms_jobs SET status=$4,receipt=$5,finished_at=now()
           WHERE id=$1 AND tenant_id=$2 AND device_id=$3 AND status='claimed' RETURNING outbox_id""",
        body.job_id, device["tenant_id"], device["id"], body.status, body.receipt,
    )
    if not row:
        previous = await db.pool().fetchrow(
            "SELECT status,receipt FROM device_sms_jobs WHERE id=$1 AND tenant_id=$2 AND device_id=$3",
            body.job_id, device["tenant_id"], device["id"],
        )
        if not previous:
            # Not a job of this device (for example after a data reset). Acknowledge so the connector can
            # drop it: refusing made it retry the same receipt forever and never ask for new work again
            # (the connector was stuck from 2026-11-11 until this was changed).
            return {"ok": False, "note": "Unknown phone job; receipt ignored"}
        if previous["status"] == body.status and previous["receipt"] == body.receipt:
            return {"ok": True}
        if previous["status"] == "uncertain" and body.status in ("sent", "failed"):
            # A late, device-verified result for a job the server gave up on after the 5 minute claim window.
            # That is exactly the evidence reconciliation needs, so apply it. Nothing is ever sent again.
            row = await db.pool().fetchrow(
                """UPDATE device_sms_jobs SET status=$4,receipt=$5,finished_at=COALESCE(finished_at,now())
                   WHERE id=$1 AND tenant_id=$2 AND device_id=$3 AND status='uncertain' RETURNING outbox_id""",
                body.job_id, device["tenant_id"], device["id"], body.status, body.receipt,
            )
        if not row:
            # Already finalised another way (cancelled, failed, a different verdict): keep the server's record
            # and tell the connector to stop retrying.
            return {"ok": True, "state": previous["status"], "note": "Job already finalised; receipt not applied"}
    if row["outbox_id"]:
        await db.pool().execute(
            """UPDATE outbox SET status=$3,last_error=$4,
               sent_at=CASE WHEN $3='sent' THEN now() ELSE sent_at END
               WHERE id=$1 AND tenant_id=$2 AND status IN ('sending','awaiting_receipt')""",
            row["outbox_id"], device["tenant_id"], "sent" if body.status == "sent" else "failed",
            "" if body.status == "sent" else "Phone did not confirm send; reconcile before retry",
        )
    if body.status == "sent":
        await db.pool().execute("UPDATE sms_devices SET verified_at=now(),last_seen=now() WHERE id=$1", device["id"])
    return {"ok": True}


class Incoming(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message_id: str = Field(min_length=1, max_length=200)
    sender: str = Field(pattern=r"^\+[1-9]\d{6,14}$")
    to: str = Field(pattern=r"^\+[1-9]\d{6,14}$")
    body: str = Field(min_length=1, max_length=1500)


@router.post("/inbound")
async def inbound(body: Incoming, device: dict = Depends(device_auth)):
    if body.to != device["from_number"] or body.sender == device["from_number"]:
        raise HTTPException(403, "Message does not belong to the connected business line")
    if not await channel_authorization.is_authorized(device["tenant_id"], "sms_read"):
        raise HTTPException(403, "Business has not authorized incoming SMS")
    inserted = await db.pool().fetchval(
        "INSERT INTO device_sms_inbound(device_id,message_id) VALUES($1,$2) "
        "ON CONFLICT DO NOTHING RETURNING message_id", device["id"], body.message_id,
    )
    if not inserted:
        return {"ok": True, "duplicate": True}
    tenant = await tenants.get_by_id(device["tenant_id"])
    # Reuse the same Grok, CRM, STOP/START and consent path as carrier webhooks.
    from .main import _sms_reply
    reply = await _sms_reply(tenant, body.sender, body.body, confirm_stop=True)
    if reply:
        try:
            await enqueue(tenant, body.sender, reply, "inbound:"+body.message_id,
                          operational=body.body.strip().upper() in {"STOP","STOPALL","UNSUBSCRIBE","CANCEL","END","QUIT","START","UNSTOP","HELP"})
        except AwaitingReceipt:
            pass
    await db.pool().execute("UPDATE sms_devices SET inbound_verified_at=now(),last_seen=now() WHERE id=$1",device["id"])
    return {"ok": True}
