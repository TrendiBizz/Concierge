"""Outbound webhooks (to Zapier, a CRM, any HTTP endpoint) for lead and appointment events."""

import asyncio
import json
import logging

import httpx

from . import db, public_fetch, scoring

log = logging.getLogger("concierge.events")

_background: set[asyncio.Task] = set()


def spawn(coro) -> None:
    """Run a coroutine in the background, keeping a reference so it is not garbage-collected."""
    task = asyncio.create_task(coro)
    _background.add(task)
    task.add_done_callback(_background.discard)


async def _post(tenant: dict, event: str, sections: dict, lead_id=None) -> None:
    url = tenant.get("lead_webhook_url")
    if not url:
        return
    from . import flood_guard  # local import: events is imported very early
    if not flood_guard.memory_allow("webhook", tenant["slug"], 60, 3600):
        log.warning("webhook %s for %s dropped: more than 60 an hour", event, tenant["slug"])
        return
    payload = {"event": event, "tenant": {"slug": tenant["slug"], "name": tenant["name"]}, **sections}
    status = "error"
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=False) as client:
            resp = await public_fetch.post_public(
                url,
                content=json.dumps(payload, default=str),
                headers={"Content-Type": "application/json"},
                timeout=8.0,
                client=client,
            )
            status = f"ok:{resp.status_code}" if resp.is_success else f"http:{resp.status_code}"
    except ValueError as exc:
        status = "blocked"
        log.warning("webhook %s blocked for %s: %s", event, tenant["slug"], exc)
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
