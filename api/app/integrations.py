"""N6 phase 2-3: connectors to a tenant's own Xero, Microsoft 365, ServiceM8, Tradify and Fergus.

Design rules
  * Every connector is DISABLED until its credentials exist. `available()` tells Studio what can be
    connected; calling a disabled provider is a clean 409, never a half-working request.
  * Connectors hang off the same events as outbound webhooks (`portability.emit`), so a call, chat
    or booking writes into the customer's system once, with no extra wiring in the channels.
  * Pushes are idempotent: `integration_links` remembers the external id for each local record.
  * A failing provider records `last_error` and never touches the customer's conversation.
  * Secrets (client secrets, tokens, API keys) are never returned by any endpoint or logged.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from . import crypto_vault, db, owner_auth
from .config import get_settings

log = logging.getLogger("concierge.integrations")
owner_router = APIRouter(prefix="/owner/integrations", tags=["integrations"])
callback_router = APIRouter(prefix="/integrations", tags=["integrations"])

PROVIDERS = ("xero", "m365", "servicem8")
LABELS = {"xero": "Xero", "m365": "Microsoft 365 Calendar", "servicem8": "ServiceM8"}
XERO_SCOPES = "offline_access accounting.contacts accounting.transactions"
MS_SCOPES = "offline_access Calendars.ReadWrite"
SERVICEM8 = "https://api.servicem8.com/api_1.0"


# ---- availability ----------------------------------------------------------------------------
def available() -> dict[str, dict]:
    s = get_settings()
    state = {
        "xero": (bool(s.xero_client_id and s.xero_client_secret), "oauth", "needs Xero app client id/secret"),
        "m365": (bool(s.ms_client_id and s.ms_client_secret), "oauth", "needs Microsoft Entra app client id/secret"),
        "servicem8": (True, "api_key", ""),  # the customer pastes their own ServiceM8 API key
    }
    return {p: {"label": LABELS[p], "enabled": ok, "method": method,
                "unavailable_reason": "" if ok else reason}
            for p, (ok, method, reason) in state.items()}


def _require(provider: str) -> None:
    if provider not in PROVIDERS:
        raise HTTPException(404, "Unknown integration")
    info = available()[provider]
    if not info["enabled"]:
        raise HTTPException(409, f"{info['label']} is not enabled on this server yet")


# ---- signed OAuth state ----------------------------------------------------------------------
def _key() -> bytes:
    s = get_settings()
    secret = (s.unsubscribe_secret or s.admin_token or "").strip()
    if not secret:
        raise HTTPException(503, "Integration signing secret is not configured")
    return secret.encode()


def make_state(tenant_id, provider: str, ttl: int = 900) -> str:
    body = base64.urlsafe_b64encode(json.dumps(
        {"t": str(tenant_id), "p": provider, "x": int(time.time()) + ttl}).encode()).decode().rstrip("=")
    return body + "." + hmac.new(_key(), body.encode(), hashlib.sha256).hexdigest()[:32]


def read_state(state: str, provider: str) -> str:
    """Return the tenant id a valid, unexpired state was issued for."""
    body, _, mac = state.partition(".")
    good = hmac.new(_key(), body.encode(), hashlib.sha256).hexdigest()[:32]
    if not mac or not hmac.compare_digest(mac, good):
        raise HTTPException(400, "Invalid connection state")
    data = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    if data.get("p") != provider or data.get("x", 0) < time.time():
        raise HTTPException(400, "Connection link expired, start again")
    return data["t"]


def redirect_uri(provider: str) -> str:
    return f"{get_settings().public_base_url.rstrip('/')}/integrations/{provider}/callback"


# ---- HTTP seam (tests replace this) ----------------------------------------------------------
async def http(method: str, url: str, **kw) -> httpx.Response:
    async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
        return await client.request(method, url, **kw)


# ---- storage ---------------------------------------------------------------------------------
async def _row(tenant_id, provider):
    return await db.pool().fetchrow(
        "SELECT * FROM tenant_integrations WHERE tenant_id=$1 AND provider=$2", tenant_id, provider)


def _creds(row) -> dict:
    c = row["credentials"]
    data = json.loads(c) if isinstance(c, str) else dict(c or {})
    if isinstance(data, dict) and "_enc" in data and isinstance(data["_enc"], str):
        aad = f"integration:{row['tenant_id']}:{row['provider']}"
        return json.loads(crypto_vault.decrypt_text(data["_enc"], aad=aad, allow_plaintext=False))
    return data


async def _save(tenant_id, provider, creds: dict, status="connected", account="") -> None:
    enc = {"_enc": crypto_vault.encrypt_text(json.dumps(creds), aad=f"integration:{tenant_id}:{provider}")}
    await db.pool().execute(
        """INSERT INTO tenant_integrations (tenant_id, provider, status, credentials, external_account, connected_at)
           VALUES ($1,$2,$3,$4::jsonb,$5,now())
           ON CONFLICT (tenant_id, provider) DO UPDATE SET status=$3, credentials=$4::jsonb,
             external_account=CASE WHEN $5<>'' THEN $5 ELSE tenant_integrations.external_account END,
             last_error='', connected_at=now()""",
        tenant_id, provider, status, json.dumps(enc), account)


async def _link(tenant_id, provider, kind, local_key):
    return await db.pool().fetchval(
        "SELECT external_id FROM integration_links WHERE tenant_id=$1 AND provider=$2 AND kind=$3 AND local_key=$4",
        tenant_id, provider, kind, local_key)


async def _set_link(tenant_id, provider, kind, local_key, external_id):
    await db.pool().execute(
        "INSERT INTO integration_links (tenant_id,provider,kind,local_key,external_id) VALUES ($1,$2,$3,$4,$5) "
        "ON CONFLICT DO NOTHING", tenant_id, provider, kind, local_key, external_id)


# ---- OAuth (Xero, Microsoft) -----------------------------------------------------------------
def _oauth_cfg(provider: str) -> dict:
    s = get_settings()
    if provider == "xero":
        return {"auth": "https://login.xero.com/identity/connect/authorize",
                "token": "https://identity.xero.com/connect/token", "scopes": XERO_SCOPES,
                "id": s.xero_client_id, "secret": s.xero_client_secret}
    base = f"https://login.microsoftonline.com/{s.ms_tenant}/oauth2/v2.0"
    return {"auth": base + "/authorize", "token": base + "/token", "scopes": MS_SCOPES,
            "id": s.ms_client_id, "secret": s.ms_client_secret}


def authorize_url(tenant_id, provider: str) -> str:
    c = _oauth_cfg(provider)
    return c["auth"] + "?" + urlencode({
        "response_type": "code", "client_id": c["id"], "redirect_uri": redirect_uri(provider),
        "scope": c["scopes"], "state": make_state(tenant_id, provider)})


async def _token_call(provider: str, data: dict) -> dict:
    c = _oauth_cfg(provider)
    resp = await http("POST", c["token"], data={**data, "client_id": c["id"], "client_secret": c["secret"]})
    if resp.status_code >= 300:
        raise RuntimeError(f"{LABELS[provider]} token request failed (HTTP {resp.status_code})")
    tok = resp.json()
    return {"access_token": tok["access_token"], "refresh_token": tok.get("refresh_token", ""),
            "expires_at": int(time.time()) + int(tok.get("expires_in", 1800)) - 60}


async def complete_oauth(tenant_id, provider: str, code: str) -> None:
    creds = await _token_call(provider, {"grant_type": "authorization_code", "code": code,
                                         "redirect_uri": redirect_uri(provider)})
    account = ""
    if provider == "xero":
        resp = await http("GET", "https://api.xero.com/connections",
                          headers={"Authorization": "Bearer " + creds["access_token"]})
        conns = resp.json() if resp.status_code == 200 else []
        if not conns:
            raise RuntimeError("No Xero organisation was authorised")
        creds["xero_tenant_id"] = conns[0]["tenantId"]
        account = conns[0].get("tenantName", "")
    await _save(tenant_id, provider, creds, account=account)


_REFRESH_LOCKS: dict[tuple[str, str], asyncio.Lock] = {}


async def _fresh(tenant_id, provider: str) -> dict:
    key = (str(tenant_id), provider)
    lock = _REFRESH_LOCKS.setdefault(key, asyncio.Lock())
    async with lock:
        row = await _row(tenant_id, provider)
        if not row or row["status"] != "connected":
            raise RuntimeError("not connected")
        creds = _creds(row)
        if provider in ("xero", "m365") and creds.get("expires_at", 0) <= time.time():
            new = await _token_call(provider, {"grant_type": "refresh_token", "refresh_token": creds["refresh_token"]})
            creds.update({k: v for k, v in new.items() if v})
            await _save(tenant_id, provider, creds)
        return creds


# ---- connectors ------------------------------------------------------------------------------
def _name(p: dict) -> str:
    return (p.get("name") or p.get("company") or p.get("email") or p.get("phone") or "Customer").strip()[:120]


async def _xero(tenant_id, event: str, p: dict) -> None:
    creds = await _fresh(tenant_id, "xero")
    headers = {"Authorization": "Bearer " + creds["access_token"], "xero-tenant-id": creds["xero_tenant_id"],
               "Accept": "application/json", "Content-Type": "application/json"}
    key = p.get("case_key") or (p.get("contact") or {}).get("case_key") or ""
    if event in ("customer.created", "customer.enquiry") and key:
        if await _link(tenant_id, "xero", "contact", key):
            return
        contact = {"Name": _name(p), "EmailAddress": p.get("email", ""),
                   "Phones": [{"PhoneType": "MOBILE", "PhoneNumber": p.get("phone", "")}] if p.get("phone") else []}
        r = await http("POST", "https://api.xero.com/api.xro/2.0/Contacts", headers=headers,
                       content=json.dumps({"Contacts": [contact]}))
        if r.status_code >= 300:
            raise RuntimeError(f"Xero contact create failed (HTTP {r.status_code})")
        await _set_link(tenant_id, "xero", "contact", key, r.json()["Contacts"][0]["ContactID"])
    elif event == "quote.accepted":
        qid = p.get("quote_id", "")
        if not qid or await _link(tenant_id, "xero", "invoice", qid):
            return
        contact = p.get("contact") or {}
        inv = {"Type": "ACCREC", "Status": "DRAFT", "LineAmountTypes": "Inclusive",
               "Contact": {"Name": _name(contact), "EmailAddress": contact.get("email", "")},
               "Reference": f"Quote {p.get('number', '')}".strip(),
               "LineItems": [{"Description": f"Accepted quotation {p.get('number', '')}".strip(),
                              "Quantity": 1, "UnitAmount": round((p.get("total_cents") or 0) / 100, 2)}]}
        r = await http("POST", "https://api.xero.com/api.xro/2.0/Invoices", headers=headers,
                       content=json.dumps({"Invoices": [inv]}))
        if r.status_code >= 300:
            raise RuntimeError(f"Xero invoice create failed (HTTP {r.status_code})")
        await _set_link(tenant_id, "xero", "invoice", qid, r.json()["Invoices"][0]["InvoiceID"])


async def m365_busy(tenant_id, start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
    """Return busy intervals from Microsoft 365 calendar when connected; empty otherwise."""
    row = await db.pool().fetchrow(
        "SELECT 1 FROM tenant_integrations WHERE tenant_id=$1 AND provider='m365' AND status='connected'",
        tenant_id,
    )
    if not row:
        return []
    try:
        creds = await _fresh(tenant_id, "m365")
        qs = urlencode({"startDateTime": start.astimezone(timezone.utc).isoformat(),
                        "endDateTime": end.astimezone(timezone.utc).isoformat(),
                        "$select": "start,end,showAs,isCancelled"})
        r = await http("GET", f"https://graph.microsoft.com/v1.0/me/calendarView?{qs}",
                       headers={"Authorization": "Bearer " + creds["access_token"], "Prefer": 'outlook.timezone="UTC"'})
        if r.status_code >= 300:
            return []
        out: list[tuple[datetime, datetime]] = []
        for ev in (r.json() or {}).get("value", []):
            if ev.get("isCancelled") or ev.get("showAs") == "free":
                continue
            s_raw = (ev.get("start") or {}).get("dateTime")
            e_raw = (ev.get("end") or {}).get("dateTime")
            if s_raw and e_raw:
                st = datetime.fromisoformat(s_raw.replace("Z", "+00:00"))
                en = datetime.fromisoformat(e_raw.replace("Z", "+00:00"))
                if st.tzinfo is None:
                    st = st.replace(tzinfo=timezone.utc)
                if en.tzinfo is None:
                    en = en.replace(tzinfo=timezone.utc)
                out.append((st, en))
        return out
    except Exception:
        return []


async def _m365(tenant_id, event: str, p: dict) -> None:
    if event not in ("appointment.booked", "appointment.cancelled", "appointment.no_show", "appointment.rescheduled"):
        return
    aid = p.get("appointment_id", "")
    if not aid:
        return
    creds = await _fresh(tenant_id, "m365")
    headers = {"Authorization": "Bearer " + creds["access_token"], "Content-Type": "application/json"}

    def _utc_iso(raw: str) -> str:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%S")

    existing_id = await _link(tenant_id, "m365", "event", aid)
    if event in ("appointment.cancelled", "appointment.no_show"):
        if existing_id:
            r = await http("DELETE", f"https://graph.microsoft.com/v1.0/me/events/{existing_id}", headers=headers)
            if r.status_code not in (200, 204, 404):
                raise RuntimeError(f"Outlook event delete failed (HTTP {r.status_code})")
        return
    if event == "appointment.rescheduled":
        if existing_id:
            patch_body = {
                "start": {"dateTime": _utc_iso(p["starts_at"]), "timeZone": "UTC"},
                "end": {"dateTime": _utc_iso(p["ends_at"]), "timeZone": "UTC"},
            }
            r = await http("PATCH", f"https://graph.microsoft.com/v1.0/me/events/{existing_id}",
                           headers=headers, content=json.dumps(patch_body))
            if r.status_code >= 300:
                raise RuntimeError(f"Outlook event reschedule failed (HTTP {r.status_code})")
        return
    if existing_id:
        return
    body = {"subject": f"Appointment: {_name(p)}", "body": {"contentType": "text", "content": p.get("notes", "")},
            "start": {"dateTime": _utc_iso(p["starts_at"]), "timeZone": "UTC"},
            "end": {"dateTime": _utc_iso(p["ends_at"]), "timeZone": "UTC"}}
    if p.get("email"):
        body["attendees"] = [{"emailAddress": {"address": p["email"], "name": _name(p)}, "type": "required"}]
    r = await http("POST", "https://graph.microsoft.com/v1.0/me/events",
                   headers=headers, content=json.dumps(body))
    if r.status_code >= 300:
        raise RuntimeError(f"Outlook event create failed (HTTP {r.status_code})")
    await _set_link(tenant_id, "m365", "event", aid, r.json()["id"])


async def _servicem8(tenant_id, event: str, p: dict) -> None:
    creds = await _fresh(tenant_id, "servicem8")
    headers = {"X-API-Key": creds["api_key"], "Content-Type": "application/json", "Accept": "application/json"}
    if event == "customer.enquiry":
        lead = p.get("lead_id", "")
        if not lead or await _link(tenant_id, "servicem8", "job", lead):
            return
        # Skip empty turn-1 chat greetings with no contact details; wait until enriched.
        if p.get("channel") == "chat" and not (p.get("name") or p.get("email") or p.get("phone")):
            return
        key = p.get("case_key", "")
        company = await _link(tenant_id, "servicem8", "client", key) if key else None
        if not company:
            comp_payload = {"name": _name(p), "email": p.get("email", ""), "active": 1}
            if p.get("phone"):
                comp_payload["mobile"] = p["phone"]
            r = await http("POST", SERVICEM8 + "/company.json", headers=headers,
                           content=json.dumps(comp_payload))
            if r.status_code >= 300:
                raise RuntimeError(f"ServiceM8 client create failed (HTTP {r.status_code})")
            company = r.headers.get("x-record-uuid", "")
            if key:
                await _set_link(tenant_id, "servicem8", "client", key, company)
        job = {"company_uuid": company, "status": "Quote", "active": 1,
               "job_description": f"[{p.get('channel', '')}] {p.get('message', '')}".strip()[:2000]}
        r = await http("POST", SERVICEM8 + "/job.json", headers=headers, content=json.dumps(job))
        if r.status_code >= 300:
            raise RuntimeError(f"ServiceM8 job create failed (HTTP {r.status_code})")
        await _set_link(tenant_id, "servicem8", "job", lead, r.headers.get("x-record-uuid", ""))


CONNECTORS = {"xero": _xero, "m365": _m365, "servicem8": _servicem8}


async def dispatch(tenant_id, event: str, payload: dict) -> None:
    """Send an event to every connected integration (with 1 transient retry). Never raises."""
    try:
        rows = await db.pool().fetch(
            "SELECT provider FROM tenant_integrations WHERE tenant_id=$1 AND status='connected'", tenant_id)
    except Exception:
        log.exception("integration lookup failed")
        return
    for r in rows:
        provider = r["provider"]
        connector = CONNECTORS.get(provider)
        if not connector:
            continue
        last_exc: Exception | None = None
        for attempt in range(2):
            try:
                await connector(tenant_id, event, payload)
                await db.pool().execute(
                    "UPDATE tenant_integrations SET last_sync_at=now(), last_error='' WHERE tenant_id=$1 AND provider=$2",
                    tenant_id, provider)
                last_exc = None
                break
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if attempt == 0:
                    await asyncio.sleep(0.5)
        if last_exc is not None:
            log.warning("integration %s failed for %s: %s", provider, event, type(last_exc).__name__)
            await db.pool().execute(
                "UPDATE tenant_integrations SET last_error=$3 WHERE tenant_id=$1 AND provider=$2",
                tenant_id, provider, str(last_exc)[:200])


# ---- Studio API ------------------------------------------------------------------------------
class ApiKeyIn(BaseModel):
    api_key: str = Field(min_length=8, max_length=200)


@owner_router.get("")
async def list_integrations(user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    rows = {r["provider"]: r for r in await db.pool().fetch(
        "SELECT * FROM tenant_integrations WHERE tenant_id=$1", user["tenant_id"])}
    out = []
    for provider, info in available().items():
        r = rows.get(provider)
        out.append({"provider": provider, **info,
                    "status": r["status"] if r else "disconnected",
                    "account": r["external_account"] if r else "",
                    "last_error": r["last_error"] if r else "",
                    "last_sync_at": r["last_sync_at"].isoformat() if r and r["last_sync_at"] else None})
    return {"integrations": out}


@owner_router.post("/{provider}/connect")
async def connect(provider: str, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    _require(provider)
    if provider not in ("xero", "m365"):
        raise HTTPException(400, "This integration connects with an API key, not a sign-in")
    return {"authorize_url": authorize_url(user["tenant_id"], provider)}


@owner_router.post("/servicem8/key")
async def servicem8_key(body: ApiKeyIn, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    r = await http("GET", SERVICEM8 + "/company.json?%24top=1", headers={"X-API-Key": body.api_key.strip()})
    if r.status_code in (401, 403):
        raise HTTPException(400, "ServiceM8 rejected that API key")
    if r.status_code >= 300:
        raise HTTPException(502, "Could not reach ServiceM8")
    await _save(user["tenant_id"], "servicem8", {"api_key": body.api_key.strip()}, account="ServiceM8")
    return {"connected": True}


@owner_router.delete("/{provider}")
async def disconnect(provider: str, user: dict = Depends(owner_auth.current_user)):
    owner_auth.require_role(user, "owner")
    if provider not in PROVIDERS:
        raise HTTPException(404, "Unknown integration")
    await db.pool().execute(
        "UPDATE tenant_integrations SET status='disconnected', credentials='{}'::jsonb "
        "WHERE tenant_id=$1 AND provider=$2", user["tenant_id"], provider)
    return {"disconnected": True}


@callback_router.get("/{provider}/callback")
async def oauth_callback(provider: str, code: str = Query(""), state: str = Query(""), error: str = Query("")):
    if provider not in ("xero", "m365"):
        raise HTTPException(404, "Unknown integration")
    _require(provider)
    tenant_id = read_state(state, provider)
    home = get_settings().onboarding_url
    if error or not code:
        return RedirectResponse(f"{home}?integration={provider}&result=denied", status_code=303)
    try:
        await complete_oauth(tenant_id, provider, code)
    except Exception as exc:  # noqa: BLE001
        log.warning("oauth callback failed for %s: %s", provider, type(exc).__name__)
        return RedirectResponse(f"{home}?integration={provider}&result=failed", status_code=303)
    return RedirectResponse(f"{home}?integration={provider}&result=connected", status_code=303)
