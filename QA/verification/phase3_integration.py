"""Integration check: per-client scoring weights + response-time alerts, via the real app on a THROWAWAY Postgres."""
import json
import os
import sys

os.environ.update({
    "DATABASE_URL": f"postgresql://postgres:test@127.0.0.1:{os.environ.get('CONCIERGE_TEST_POSTGRES_PORT', '55432')}/postgres",
    "OUTBOX_ENABLED": "false",
    "ADMIN_TOKEN": "admin-test-token",
    "PUBLIC_BASE_URL": "https://chat.example.test",
})

# Resolve paths relative to THIS repository, not a developer's ~/work-staging scratch copies.
# Those stale copies used to be prepended ahead of the checkout, so a suite could silently test
# code from another branch or another day. CI never noticed because the paths did not exist there;
# locally they did. The repository the suite lives in is always the right one to test.
_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(_REPO, "QA", "verification", "shims"))
sys.path.insert(0, os.path.join(_REPO, "api"))

from fastapi.testclient import TestClient  # noqa: E402

from app import db, scoring, sla, tenants  # noqa: E402
from app.main import app  # noqa: E402

results = []
H = {"X-Admin-Token": "admin-test-token"}


def check(name, ok, detail=""):
    results.append(ok)
    print(("PASS  " if ok else "FAIL  ") + name + ("" if ok else f"  -> {detail}"))


with TestClient(app) as client:
    run = client.portal.call
    p = db.pool()

    async def seed():
        tid = await p.fetchval(
            "INSERT INTO tenants (slug, name, public_key, notify_email, timezone) "
            "VALUES ('p3', 'Phase Three Co', 'pk_p3', 'owner@p3.example', 'Pacific/Auckland') RETURNING id")
        return tid
    tid = run(seed)

    # ------------------------------------------------------------ scoring weights over the API
    r = client.get("/admin/tenants/p3/scoring", headers=H)
    rows = {w["key"]: w for w in r.json()["weights"]}
    check("GET scoring lists defaults", r.status_code == 200 and rows["phone"]["value"] == 25 and rows["hot_at"]["value"] == 70, r.text[:200])

    r = client.patch("/admin/tenants/p3", headers=H, json={"scoring": {"phone": 40}})
    check("PATCH valid weights accepted", r.status_code == 200, r.text[:200])
    check("PATCH unknown key rejected (422)", client.patch("/admin/tenants/p3", headers=H, json={"scoring": {"bogus": 1}}).status_code == 422)
    check("PATCH out-of-range rejected (422)", client.patch("/admin/tenants/p3", headers=H, json={"scoring": {"phone": 999}}).status_code == 422)
    check("PATCH warm>=hot rejected (422)", client.patch("/admin/tenants/p3", headers=H, json={"scoring": {"warm_at": 95}}).status_code == 422)
    rows = {w["key"]: w for w in client.get("/admin/tenants/p3/scoring", headers=H).json()["weights"]}
    check("override stored and shown (phone 40, email still 10)", rows["phone"]["value"] == 40 and rows["email"]["value"] == 10, rows["phone"])

    async def add_lead(name, **kw):
        cols = {"name": name, "email": "", "phone": "", "message": "", "status": "new", "score": 0,
                "score_label": "cold", "age_minutes": 0, "consent_contact": False}
        cols.update(kw)
        return await p.fetchval(
            "INSERT INTO leads (tenant_id, name, email, phone, message, status, score, score_label, consent_contact, created_at) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9, now() - make_interval(mins => $10)) RETURNING id",
            tid, cols["name"], cols["email"], cols["phone"], cols["message"], cols["status"], cols["score"],
            cols["score_label"], cols["consent_contact"], cols["age_minutes"])

    leadx = run(lambda: add_lead("Rescore Me", phone="+6421000099", email="r@e.co"))
    out = client.post("/admin/tenants/p3/rescore", headers=H).json()
    row = run(lambda: p.fetchrow("SELECT score, score_label FROM leads WHERE id=$1", leadx))
    check("rescore applies the client's weights (40+10+5=55? name 'Rescore Me' +5)", row["score"] == 40 + 10 + 5 and out["rescored"] >= 1, (dict(row), out))
    client.patch("/admin/tenants/p3", headers=H, json={"scoring": {}})
    client.post("/admin/tenants/p3/rescore", headers=H)
    row = run(lambda: p.fetchrow("SELECT score FROM leads WHERE id=$1", leadx))
    check("reset to defaults + rescore returns to 25+10+5=40", row["score"] == 40, dict(row))

    # ------------------------------------------------------------ response-time alerts
    async def reset_leads():
        await p.execute("DELETE FROM outbox WHERE tenant_id=$1", tid)
        await p.execute("DELETE FROM appointments WHERE tenant_id=$1", tid)
        await p.execute("DELETE FROM leads WHERE tenant_id=$1", tid)
    run(reset_leads)

    A = run(lambda: add_lead("Hot Waiting", phone="+6421000001", score=82, score_label="hot", age_minutes=30))
    run(lambda: add_lead("Too Fresh", phone="+6421000002", score=82, score_label="hot", age_minutes=5))
    run(lambda: add_lead("Cold Waiting", phone="+6421000003", score=20, score_label="cold", age_minutes=30))
    run(lambda: add_lead("Already Contacted", phone="+6421000004", score=82, score_label="hot", age_minutes=30, status="contacted"))
    E = run(lambda: add_lead("Has Booking", phone="+6421000005", score=82, score_label="hot", age_minutes=30))
    run(lambda: p.execute("INSERT INTO appointments (tenant_id, lead_id, starts_at, ends_at, name) "
                          "VALUES ($1,$2, now() + interval '1 day', now() + interval '1 day 30 minutes', 'x')", tid, E))
    run(lambda: add_lead("Five Days Old", phone="+6421000006", score=82, score_label="hot", age_minutes=60 * 24 * 5))
    run(lambda: add_lead("Three Days Old", phone="+6421000007", score=82, score_label="hot", age_minutes=60 * 24 * 3))

    async def tenant_row():
        return await tenants.get_by_id(tid)

    check("alerts are OFF by default (sla_minutes 0)", run(lambda: sla.check_once()) == 0)
    r = client.patch("/admin/tenants/p3", headers=H, json={"sla_minutes": 15, "sla_min_score": 70})
    check("PATCH sla settings accepted", r.status_code == 200, r.text[:200])
    check("PATCH sla_minutes out of range rejected", client.patch("/admin/tenants/p3", headers=H, json={"sla_minutes": 99999}).status_code == 422)

    waiting = client.get("/admin/tenants/p3/sla", headers=H).json()
    names = {w["name"] for w in waiting["waiting"]}
    check("dashboard list: hot, new, unbooked, over target (7-day window)",
          names == {"Hot Waiting", "Five Days Old", "Three Days Old"}, names)
    check("list carries minutes + reasons fields", all("minutes_waiting" in w and "reasons" in w for w in waiting["waiting"]))

    queued = run(lambda: sla.check_once())
    check("alerts queued only for leads under 2 days old (just 'Hot Waiting')", queued == 1, queued)
    alert = run(lambda: p.fetchrow("SELECT subject, body, send_at, to_addr FROM outbox WHERE dedupe_key = $1", f"lead:{A}:sla"))
    check("alert subject names label, wait and lead", alert is not None and alert["subject"].startswith("[ACTION] HOT lead waiting 3") and "Hot Waiting" in alert["subject"], alert and alert["subject"])
    check("alert goes to the owner", alert is not None and alert["to_addr"] == "owner@p3.example")
    from zoneinfo import ZoneInfo
    local_hour = alert["send_at"].astimezone(ZoneInfo("Pacific/Auckland")).hour
    check("alert is scheduled inside 8am-9pm local", 8 <= local_hour < 21, local_hour)
    check("second check sends nothing (one alert per lead)", run(lambda: sla.check_once()) == 0)
    check("lead marked alerted", run(lambda: p.fetchval("SELECT sla_alerted_at IS NOT NULL FROM leads WHERE id=$1", A)))

    client.patch(f"/admin/leads/{A}", headers=H, json={"status": "contacted"})
    names = {w["name"] for w in client.get("/admin/tenants/p3/sla", headers=H).json()["waiting"]}
    check("marking contacted removes the lead from the waiting list", "Hot Waiting" not in names, names)

    run(lambda: p.execute("UPDATE tenants SET notify_email = NULL WHERE id=$1", tid))
    run(lambda: p.execute("UPDATE leads SET sla_alerted_at = NULL"))
    run(lambda: add_lead("Needs An Owner Email", phone="+6421000008", score=90, score_label="hot", age_minutes=40))
    check("no notify_email -> no alert, no crash", run(lambda: sla.check_once()) == 0)

print(f"\n{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
