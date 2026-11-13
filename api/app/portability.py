"""Getting a customer's data out, and new activity in, when they already run their own CRM.

A business that lives in HubSpot, Pipedrive, Zoho or a spreadsheet must not be trapped here. Two
directions, both deliberately plain:

  out  ``export_contacts`` produces the whole customer list as JSON or CSV, addresses included,
       in a shape any CRM can import (one row per address, plus one row per customer).
  push ``emit`` queues an event when something happens, and ``deliver_pending`` sends it to the
       tenant's own endpoint signed with HMAC-SHA256, so their side can prove it came from us.

Nothing here decides what a customer's CRM means; it only refuses to lock their data up.
"""
import asyncio
import csv
import hashlib
import hmac
import io
import json
import logging
import time

import httpx

from . import db

log = logging.getLogger("concierge.portability")

EVENTS = ("customer.created", "customer.enquiry")

CUSTOMER_COLUMNS = ["case_key", "display_name", "primary_phone", "primary_email",
                    "addresses", "channels", "last_seen"]


async def export_contacts(tenant_id) -> list[dict]:
    """Every customer, with every address they can be reached at."""
    rows = await db.pool().fetch(
        """
        SELECT c.case_key, c.display_name, c.primary_phone, c.primary_email, c.updated_at,
               COALESCE((SELECT string_agg(DISTINCT e.channel, '|') FROM case_events e
                         WHERE e.case_id = c.id), '') AS channels,
               COALESCE((SELECT string_agg(a.kind || ':' || a.value, '|' ORDER BY a.kind, a.value)
                         FROM customer_addresses a WHERE a.case_id = c.id), '') AS addresses
        FROM customer_cases c
        WHERE c.tenant_id = $1
        ORDER BY c.display_name, c.created_at
        """,
        tenant_id,
    )
    out = []
    for r in rows:
        item = dict(r)
        item["channels"] = [c for c in (item["channels"] or "").split("|") if c]
        item["addresses"] = [a for a in (item["addresses"] or "").split("|") if a]
        item["last_seen"] = item["updated_at"].isoformat()
        item.pop("updated_at", None)
        out.append(item)
    return out


def to_csv(contacts: list[dict]) -> str:
    """One row per address, so a spreadsheet or any CRM importer keeps every way to reach them."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["customer", "case_key", "kind", "address", "channels", "last_seen"])
    for contact in contacts:
        name = contact.get("display_name") or contact.get("case_key") or ""
        addresses = contact.get("addresses") or []
        if not addresses:
            writer.writerow([name, contact.get("case_key", ""), "", "", "|".join(contact.get("channels", [])),
                             contact.get("last_seen", "")])
            continue
        for address in addresses:
            kind, _, value = address.partition(":")
            writer.writerow([name, contact.get("case_key", ""), kind, value,
                             "|".join(contact.get("channels", [])), contact.get("last_seen", "")])
    return buffer.getvalue()


def parse_import(text: str) -> list[dict]:
    """Parse a CSV a customer's own CRM exported.

    Forgiving about the header, strict about the data: a column named phone/mobile/telephone and
    email/e-mail/mail are treated as addresses, anything else is ignored rather than guessed at.
    """
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    rows = []
    for raw in reader:
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
        phone = next((row[k] for k in ("phone", "mobile", "telephone", "phone number", "tel") if row.get(k)), "")
        email = next((row[k] for k in ("email", "e-mail", "mail", "email address") if row.get(k)), "")
        name = next((row[k] for k in ("name", "customer", "full name", "contact", "company") if row.get(k)), "")
        extra = row.get("address", "") or row.get("addresses", "")
        rows.append({"name": name, "phone": phone, "email": email, "extra": extra})
    return rows


async def import_contacts(tenant_id, rows: list[dict], default_cc: str = "1") -> dict:
    """Create or merge each person, and remember every address they gave us.

    Idempotent by construction: ``reconcile`` matches on any known address, so importing the same
    file twice updates rather than duplicating.
    """
    from . import casetimeline

    created, addresses, skipped = 0, 0, []
    for row in rows:
        phones = [p for p in str(row.get("extra", "")).split(";")] if row.get("extra") else []
        try:
            case = await casetimeline.reconcile(
                tenant_id, phone=row.get("phone", ""), email=row.get("email", ""),
                name=row.get("name", ""), default_cc=default_cc)
        except Exception as exc:  # one bad row must not abandon the whole file
            skipped.append({"row": row, "reason": str(exc)[:120]})
            continue
        if not case:
            skipped.append({"row": row, "reason": "no usable phone or email"})
            continue
        created += 1
        for extra_phone in phones:
            try:
                await casetimeline.add_address(tenant_id, case["id"], kind="phone",
                                               value=extra_phone, label="imported",
                                               default_cc=default_cc)
                addresses += 1
            except ValueError:
                continue
        addresses += 1
    return {"contacts": created, "addresses": addresses, "skipped": skipped}


# ---------------------------------------------------------------- push side
async def set_webhook(tenant_id, url: str, secret: str) -> dict:
    await db.pool().execute(
        """
        INSERT INTO tenant_webhooks (tenant_id, url, secret, active) VALUES ($1,$2,$3,true)
        ON CONFLICT (tenant_id) DO UPDATE SET url=$2, secret=$3, active=true
        """,
        tenant_id, url, secret)
    return {"url": url, "active": True}


async def get_webhook(tenant_id) -> dict | None:
    row = await db.pool().fetchrow(
        "SELECT url, active, created_at FROM tenant_webhooks WHERE tenant_id=$1", tenant_id)
    if not row:
        return None
    return {"url": row["url"], "active": row["active"],
            "created_at": row["created_at"].isoformat()}


async def delete_webhook(tenant_id) -> None:
    await db.pool().execute("DELETE FROM tenant_webhooks WHERE tenant_id=$1", tenant_id)


def signature(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


async def emit(tenant_id, event: str, payload: dict) -> None:
    """Queue an event. Never raises: a CRM hook must not break the customer's own conversation."""
    if event not in EVENTS:
        raise ValueError(f"Unsupported event: {event}")
    try:
        # No endpoint configured means no CRM to feed: do not queue rows nobody will collect.
        configured = await db.pool().fetchval(
            "SELECT 1 FROM tenant_webhooks WHERE tenant_id=$1 AND active", tenant_id)
        if not configured:
            return
        await db.pool().execute(
            "INSERT INTO webhook_events (tenant_id, event, payload) VALUES ($1,$2,$3::jsonb)",
            tenant_id, event, json.dumps(payload))
        asyncio.create_task(deliver_pending(tenant_id))
    except Exception:
        log.exception("could not queue %s for tenant %s", event, tenant_id)


async def deliver_pending(tenant_id, limit: int = 20) -> dict:
    """Send queued events to the tenant's endpoint, signed. Failures stay queued for a retry."""
    hook = await db.pool().fetchrow(
        "SELECT url, secret FROM tenant_webhooks WHERE tenant_id=$1 AND active", tenant_id)
    if not hook:
        return {"sent": 0, "failed": 0, "reason": "no webhook configured"}
    rows = await db.pool().fetch(
        "SELECT id, event, payload, attempts FROM webhook_events "
        "WHERE tenant_id=$1 AND delivered_at IS NULL AND attempts < 5 "
        "ORDER BY created_at LIMIT $2", tenant_id, limit)
    sent = failed = 0
    async with httpx.AsyncClient(timeout=10) as client:
        for row in rows:
            # jsonb comes back as a JSON *string* from asyncpg. Nesting that string directly would
            # hand the customer's CRM `"data": "{...}"` -- a string where an object belongs -- so
            # decode it first. A test caught this by asserting on the delivered body, not the queue.
            payload = row["payload"]
            if isinstance(payload, str):
                payload = json.loads(payload)
            body = json.dumps({"event": row["event"], "data": payload,
                               "sent_at": int(time.time())}).encode()
            try:
                response = await client.post(
                    hook["url"], content=body,
                    headers={"Content-Type": "application/json",
                             "X-Concierge-Event": row["event"],
                             "X-Concierge-Signature": signature(hook["secret"], body)})
                if response.status_code >= 300:
                    raise RuntimeError(f"HTTP {response.status_code}")
                await db.pool().execute(
                    "UPDATE webhook_events SET delivered_at=now(), attempts=attempts+1 WHERE id=$1",
                    row["id"])
                sent += 1
            except Exception as exc:
                await db.pool().execute(
                    "UPDATE webhook_events SET attempts=attempts+1, last_error=$2 WHERE id=$1",
                    row["id"], str(exc)[:200])
                failed += 1
    return {"sent": sent, "failed": failed}
