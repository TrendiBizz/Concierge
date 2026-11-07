"""Outbound webhooks (to n8n, Zapier, a CRM...) for lead and appointment events."""

import asyncio
import hashlib
import json
import logging
from urllib.parse import urlsplit

import httpx

from . import db, scoring
from .config import get_settings

log = logging.getLogger("concierge.events")

_background: set[asyncio.Task] = set()


def spawn(coro) -> None:
    """Run a coroutine in the background, keeping a reference so it is not garbage-collected."""
    task = asyncio.create_task(coro)
    _background.add(task)
    task.add_done_callback(_background.discard)


def twenty_bridge_payload(tenant: dict, event: str, sections: dict) -> dict | None:
    """Adapt Concierge events to the existing Twenty lead bridge's flat /lead schema.

    No secrets are included. It never sends to Twenty unless operator configuration
    explicitly selects exactly this tenant. A booking attaches a new note to a
    matching person when the bridge can identify them.
    """
    if event not in ("lead.created", "appointment.booked"):
        return None
    lead = sections.get("lead") or {}
    appt = sections.get("appointment") or {}
    person = lead if lead else appt
    if not isinstance(person, dict):
        return None
    contact = {"email": str(person.get("email") or "").strip(),
               "phone": str(person.get("phone") or "").strip()}
    if not any(contact.values()):
        return None
    parts = str(person.get("name") or "").strip().split(None, 1)
    first = parts[0] if parts else ""
    last = parts[1] if len(parts) > 1 else ""
    if event == "lead.created":
        detail = str(lead.get("message") or "")[:1400]
    else:
        detail = ("Appointment booked: " + str(appt.get("starts_at") or "") +
                  " | " + str(appt.get("notes") or ""))[:1400]
    return {
        "first_name": first[:80], "last_name": last[:80],
        "email": contact["email"][:200], "phone": contact["phone"][:40],
        "company": str(tenant.get("name") or "")[:120],
        "source": "Concierge " + str(lead.get("channel") or "booking"),
        "message": detail,
    }


def _bridge_enabled(tenant: dict) -> bool:
    settings=get_settings()
    return bool(settings.twenty_bridge_url and settings.twenty_bridge_tenant_slug
                and tenant.get("slug")==settings.twenty_bridge_tenant_slug)


def _bridge_url() -> str | None:
    url=get_settings().twenty_bridge_url
    parsed=urlsplit(url)
    if (parsed.scheme != "http" or parsed.hostname not in (
            "127.0.0.1","localhost","host.docker.internal","twenty-bridge")
        or parsed.port != 4410 or parsed.path != "/lead" or parsed.query
        or parsed.fragment or parsed.username or parsed.password):
        log.error("Twenty bridge URL rejected; only internal port 4410 supported")
        return None
    return url


async def queue_twenty(tenant: dict, event: str, source_id: str,
                       sections: dict) -> bool:
    """Persist before attempting delivery; one item per tenant/event/source ID."""
    if not _bridge_enabled(tenant):
        return False
    payload=twenty_bridge_payload(tenant,event,sections)
    if payload is None:
        return False
    if not source_id:
        raise ValueError("Twenty event needs an idempotent source identifier")
    result=await db.pool().execute(
        """INSERT INTO twenty_deliveries(tenant_id,event,source_id,payload)
           VALUES($1,$2,$3,$4::jsonb)
           ON CONFLICT(tenant_id,event,source_id) DO NOTHING""",
        tenant["id"],event,str(source_id),json.dumps(payload))
    return result.endswith("1")


async def _twenty_finish(row_id: int,status: str,error: str="",
                         retry_seconds: int=0) -> None:
    await db.pool().execute(
        """UPDATE twenty_deliveries SET status=$2,last_error=$3,
           next_at=CASE WHEN $4>0 THEN now()+$4*interval '1 second'
                        ELSE next_at END,
           delivered_at=CASE WHEN $2='sent' THEN now() ELSE delivered_at END
           WHERE id=$1""",
        row_id,status,error[:300],retry_seconds)


async def process_twenty_once() -> int:
    """Claim saved events. Timeout/crash outcomes stay uncertain, never double-send."""
    if not get_settings().twenty_bridge_url:
        return 0
    url=_bridge_url()
    if url is None:
        return 0
    pool=db.pool()
    # After a crash the remote CRM may have created the note. Never replay
    # these rows automatically without reconciling with Twenty first.
    await pool.execute(
        """UPDATE twenty_deliveries SET status='uncertain',
           last_error='Worker interrupted during CRM delivery; reconcile manually'
           WHERE status='sending' AND claimed_at < now()-interval '10 minutes'""")
    rows=await pool.fetch(
        """UPDATE twenty_deliveries SET status='sending',attempts=attempts+1,claimed_at=now()
           WHERE id IN (
              SELECT id FROM twenty_deliveries
              WHERE status='pending' AND next_at<=now()
              ORDER BY next_at,id LIMIT 20 FOR UPDATE SKIP LOCKED
           ) RETURNING id,tenant_id,event,source_id,payload,attempts""")
    for record in rows:
        row=dict(record)
        tenant=await pool.fetchrow("SELECT slug FROM tenants WHERE id=$1",row["tenant_id"])
        if not tenant or tenant["slug"]!=get_settings().twenty_bridge_tenant_slug:
            await _twenty_finish(row["id"],"failed","Tenant is not authorised for this CRM")
            continue
        try:
            async with httpx.AsyncClient(timeout=8.0,follow_redirects=False) as client:
                payload = row["payload"]
                if isinstance(payload,str):
                    payload=json.loads(payload)
                if not isinstance(payload,dict):
                    raise ValueError("Invalid stored CRM payload")
                # Stable, tenant-scoped event receipt shared with the private
                # CRM bridge. No PII appears in the id or filesystem filename.
                identity=json.dumps([str(row['tenant_id']),row['event'],str(row['source_id'])],
                                    ensure_ascii=True,separators=(',',':'))
                payload={**payload,'delivery_id':hashlib.sha256(identity.encode('utf-8')).hexdigest()}
                headers={}
                auth_file=getattr(get_settings(),"twenty_bridge_auth_file","")
                if auth_file:
                    from pathlib import Path
                    secret=Path(auth_file).read_text().strip()
                    if len(secret)<32:
                        raise ValueError("Missing internal CRM bridge authentication")
                    headers["Authorization"]="Bearer "+secret
                elif urlsplit(url).hostname=="twenty-bridge":
                    raise ValueError("Private Docker bridge requires an authentication secret")
                response=await client.post(url,json=payload,headers=headers)
            if response.status_code==429 and row["attempts"]<5:
                await _twenty_finish(row["id"],"pending","Rate limited",min(300,2**row["attempts"]*15))
            elif response.status_code==200:
                data=response.json()
                if data.get("ok") is True and data.get("twenty_id") and data.get("note") is True:
                    await _twenty_finish(row["id"],"sent")
                else:
                    await _twenty_finish(row["id"],"uncertain",
                        "CRM person or note not fully confirmed; reconcile manually")
            elif response.status_code in (400,401,403,413):
                await _twenty_finish(row["id"],"failed",
                    f"Bridge rejected request (HTTP {response.status_code})")
            else:
                await _twenty_finish(row["id"],"uncertain",
                    f"CRM outcome unknown (HTTP {response.status_code}); reconcile manually")
        except (httpx.HTTPError,ValueError):
            await _twenty_finish(row["id"],"uncertain",
                "CRM response missing or invalid; reconcile manually")
    return len(rows)


async def run_twenty_forever(stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            await process_twenty_once()
        except Exception:
            log.exception("Twenty CRM delivery worker failed")
        try:
            await asyncio.wait_for(stop.wait(),timeout=20)
        except asyncio.TimeoutError:
            pass


async def _post(tenant: dict, event: str, sections: dict, lead_id=None) -> None:
    url = tenant.get("lead_webhook_url")
    if not url:
        return
    payload = {"event": event, "tenant": {"slug": tenant["slug"], "name": tenant["name"]}, **sections}
    status = "error"
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(
                url,
                content=json.dumps(payload, default=str),
                headers={"Content-Type": "application/json"},
            )
            status = f"ok:{resp.status_code}" if resp.is_success else f"http:{resp.status_code}"
    except httpx.HTTPError as exc:
        log.warning("webhook %s failed for %s: %s", event, tenant["slug"], exc)
    if lead_id is not None and event == "lead.created":
        await db.pool().execute("UPDATE leads SET webhook_status = $2 WHERE id = $1", lead_id, status)


def emit(tenant: dict, event: str, lead_id=None, **sections) -> None:
    if tenant.get("lead_webhook_url"):
        spawn(_post(tenant, event, sections, lead_id))


def lead_view(lead: dict) -> dict:
    utm = lead.get("utm")
    return {
        "id": str(lead["id"]),
        "name": lead["name"],
        "email": lead["email"],
        "phone": lead["phone"],
        "message": lead["message"],
        "channel": lead["channel"],
        "score": lead.get("score"),
        "score_label": lead.get("score_label"),
        "score_reasons": scoring.reasons_of(lead),
        "page_url": lead.get("page_url"),
        "utm": json.loads(utm) if isinstance(utm, str) else (utm or {}),
        "created_at": lead["created_at"].isoformat(),
    }


def appointment_view(appt: dict, tz_label: str = "") -> dict:
    return {
        "id": str(appt["id"]),
        "starts_at": appt["starts_at"].isoformat(),
        "ends_at": appt["ends_at"].isoformat(),
        "name": appt["name"],
        "phone": appt["phone"],
        "email": appt["email"],
        "notes": appt["notes"],
        "status": appt["status"],
        "timezone": tz_label,
    }
