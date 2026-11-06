"""Drives the real FastAPI app (admin + public routes + capture tool) against the THROWAWAY Postgres."""
import asyncio
import json
import os
import re
import sys

os.environ.update({
    "DATABASE_URL": "postgresql://postgres:test@127.0.0.1:55432/postgres",
    "OUTBOX_ENABLED": "false",
    "ADMIN_TOKEN": "admin-test-token",
    "PUBLIC_BASE_URL": "https://chat.example.test",
    "SMTP_HOST": "smtp.example.test",
    "SMTP_FROM": "hello@example.test",
})
sys.path.insert(0, os.path.expanduser("~/work-staging/shims"))
sys.path.insert(0, os.path.expanduser("~/work-staging/concierge-core/api"))

from fastapi.testclient import TestClient  # noqa: E402

from app import db, tenants  # noqa: E402
from app.main import app  # noqa: E402
from app.tools import run_tool  # noqa: E402

results = []
H = {"X-Admin-Token": "admin-test-token"}


def check(name, ok, detail=""):
    results.append(ok)
    print(("PASS  " if ok else "FAIL  ") + name + ("" if ok else f"  -> {detail}"))


with TestClient(app) as client:
    async def seed():
        p = db.pool()
        tid = await p.fetchval(
            "INSERT INTO tenants (slug, name, public_key, notify_email, campaigns_enabled) "
            "VALUES ('routes', 'Route Co', 'pk_routes', 'o@r.example', true) RETURNING id")
        lead_id = await p.fetchval(
            "INSERT INTO leads (tenant_id, name, email, status, created_at) "
            "VALUES ($1,'Kim Wu','kim@example.com','new', now() - interval '90 days') RETURNING id", tid)
        return tid, lead_id

    loop = client.portal if hasattr(client, "portal") and client.portal else None
    tid, lead_id = client.portal.call(seed)

    # admin auth is enforced
    r = client.post("/admin/tenants/routes/campaigns", json={"name": "x", "channel": "email", "subject": "s", "body": "b"})
    check("admin routes reject missing token", r.status_code in (401, 403), r.status_code)

    body = {"name": "Win-back", "channel": "email", "subject": "Hi from {business}", "body": "Hello {first}"}
    r = client.post("/admin/tenants/routes/campaigns", json=body, headers=H)
    check("create draft -> 201", r.status_code == 201, r.text)
    cid = r.json()["campaign"]["id"]
    check("nobody eligible until marketing consent exists", r.json()["preview"]["recipients"] == 0, r.json()["preview"])
    check("bad template rejected with 400", client.post("/admin/tenants/routes/campaigns", headers=H,
          json={**body, "body": "Hi {nope}"}).status_code == 400)

    r = client.patch(f"/admin/leads/{lead_id}/marketing-consent", headers=H, json={"consent": True, "basis": "Opted in on paper form, May 2026"})
    check("record marketing consent with basis", r.status_code == 200 and r.json()["consent_marketing"] is True and "paper form" in r.json()["consent_marketing_basis"], r.text)
    check("consent needs a basis", client.patch(f"/admin/leads/{lead_id}/marketing-consent", headers=H,
          json={"consent": True, "basis": "x"}).status_code == 422)

    r = client.get(f"/admin/campaigns/{cid}/preview", headers=H)
    check("preview now sees Kim", r.status_code == 200 and r.json()["recipients"] == 1, r.text)
    r = client.post(f"/admin/campaigns/{cid}/send", headers=H, json={"expected_recipients": 9})
    check("wrong audience size -> 409", r.status_code == 409, r.text)
    r = client.post(f"/admin/campaigns/{cid}/send", headers=H, json={"expected_recipients": 1})
    check("send -> queued 1", r.status_code == 200 and r.json()["queued"] == 1, r.text)

    async def link_from_queue():
        return await db.pool().fetchval("SELECT body FROM outbox WHERE campaign_id = $1", cid)
    mail_body = client.portal.call(link_from_queue)
    token = re.search(r"/api/v1/unsubscribe/(\S+)", mail_body).group(1)

    page = client.get(f"/api/v1/unsubscribe/{token}")
    check("GET unsubscribe shows a confirm page, does not unsubscribe", page.status_code == 200 and "<form" in page.text)

    async def opted():
        return await db.pool().fetchval("SELECT count(*) FROM opt_outs WHERE tenant_id = $1", tid)
    check("still not opted out after GET (scanner-safe)", client.portal.call(opted) == 0)
    check("bad token page -> 404", client.get("/api/v1/unsubscribe/garbage").status_code == 404)

    done = client.post(f"/api/v1/unsubscribe/{token}", data="List-Unsubscribe=One-Click",
                       headers={"Content-Type": "application/x-www-form-urlencoded"})
    check("POST (one-click) unsubscribes", done.status_code == 200 and "unsubscribed" in done.text.lower(), done.text[:200])
    check("opt-out recorded", client.portal.call(opted) == 1)

    st = client.get(f"/admin/campaigns/{cid}", headers=H).json()
    check("campaign shows delivery counts", st["delivery"].get("cancelled") == 1, st)
    check("list endpoint works", len(client.get("/admin/tenants/routes/campaigns", headers=H).json()) == 1)

    # capture_lead tool: marketing consent only when explicitly given
    async def capture(args, ctx=None):
        t = await tenants.get_by_id(tid)
        res = await run_tool(t, "capture_lead", args, {"channel": "chat", **(ctx or {})})
        return res, await db.pool().fetchrow(
            "SELECT consent_contact, consent_marketing, consent_marketing_basis FROM leads WHERE email = $1 ORDER BY created_at DESC LIMIT 1",
            args["email"])

    res, row = client.portal.call(capture, {"name": "A", "email": "a1@example.com", "message": "hi", "consent_to_contact": True})
    check("contact consent alone does NOT grant marketing consent", row["consent_contact"] and not row["consent_marketing"], dict(row))
    res, row = client.portal.call(capture, {"name": "B", "email": "b1@example.com", "message": "hi", "consent_to_contact": True, "consent_to_marketing": True})
    check("explicit marketing consent is recorded with a basis", row["consent_marketing"] and "agreed to promotions" in row["consent_marketing_basis"], dict(row))
    res, row = client.portal.call(capture, {"name": "C", "email": "c1@example.com", "message": "hi"}, {"sms_inbound": True})
    check("texting us first is contact consent, not marketing", row["consent_contact"] and not row["consent_marketing"], dict(row))

print(f"\n{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
