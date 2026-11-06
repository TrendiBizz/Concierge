"""Integration check: to-dos, sales pipeline, weekly summary and calendar feed, through the real app on a THROWAWAY Postgres."""
import os
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

os.environ.update({
    "DATABASE_URL": "postgresql://postgres:test@127.0.0.1:55432/postgres",
    "OUTBOX_ENABLED": "false",
    "ADMIN_TOKEN": "admin-test-token",
    "PUBLIC_BASE_URL": "https://chat.example.test",
})
sys.path.insert(0, os.path.expanduser("~/work-staging/shims"))
sys.path.insert(0, os.path.expanduser("~/work-staging/concierge-office/api"))

from fastapi.testclient import TestClient  # noqa: E402

from app import automation, db, sales, tasks, tenants  # noqa: E402
from app.main import app  # noqa: E402

results = []
H = {"X-Admin-Token": "admin-test-token"}
NZ = ZoneInfo("Pacific/Auckland")


def check(name, ok, detail=""):
    ok = bool(ok)
    results.append(ok)
    print(("PASS  " if ok else "FAIL  ") + name + ("" if ok else f"  -> {detail}"))


with TestClient(app) as client:
    run = client.portal.call
    p = db.pool()

    async def seed():
        return await p.fetchval(
            "INSERT INTO tenants (slug, name, public_key, notify_email, timezone, lead_value_cents) "
            "VALUES ('off', 'Office Co', 'pk_off', 'owner@off.example', 'Pacific/Auckland', 50000) RETURNING id")
    tid = run(seed)

    async def tenant():
        return await tenants.get_by_id(tid)

    async def new_lead(name, hot=False, **kw):
        cols = dict(email="", phone="", message="", channel="chat", page_url=None, consent=False, value=0)
        cols.update(kw)
        if hot:
            cols.update(phone="+6421000001", email=f"{name.split()[0].lower()}@x.example", consent=True, channel="sms",
                        message="Can I book a quote for tomorrow? Need a price today", page_url="https://off.nz/pricing")
        return dict(await p.fetchrow(
            "INSERT INTO leads (tenant_id, name, email, phone, message, channel, page_url, consent_contact, value_cents) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9) RETURNING *",
            tid, name, cols["email"], cols["phone"], cols["message"], cols["channel"], cols["page_url"], cols["consent"], cols["value"]))

    # ------------------------------------------------------------ automatic follow-up to-do
    hot = run(lambda: new_lead("Hana Ngata", hot=True))

    async def created(lead):
        t = await tenant()
        await automation.on_lead_created(t, lead)
        return await p.fetch("SELECT * FROM tasks WHERE lead_id = $1", lead["id"])
    rows = run(lambda: created(hot))
    check("new lead gets exactly one follow-up to-do", len(rows) == 1 and rows[0]["kind"] == "follow_up" and rows[0]["source"] == "system", rows)
    t0 = dict(rows[0])
    check("title names the lead", t0["title"] == "Follow up: Hana Ngata", t0["title"])
    mins = (t0["due_at"] - datetime.now(timezone.utc)).total_seconds() / 60
    check("hot lead: due in about an hour", 55 <= mins <= 61, mins)
    check("notes carry what the lead asked", "book a quote" in t0["notes"])
    again = run(lambda: tasks.create_follow_up({"id": tid, "timezone": "Pacific/Auckland"}, hot))
    check("a second follow-up for the same lead is refused (idempotent)", again is None and len(run(lambda: p.fetch("SELECT 1 FROM tasks WHERE lead_id=$1", hot["id"]))) == 1)

    cold = run(lambda: new_lead("Sam Li", message="just looking"))
    crow = run(lambda: created(cold))[0]
    local_due = crow["due_at"].astimezone(NZ)
    check("cold lead: due at 9am local, in the future", local_due.hour == 9 and local_due.minute == 0 and crow["due_at"] > datetime.now(timezone.utc), local_due)

    # ------------------------------------------------------------ status changes through the API
    r = client.patch(f"/admin/leads/{hot['id']}", headers=H, json={"status": "contacted"})
    check("PATCH status -> contacted", r.status_code == 200 and r.json()["status"] == "contacted", r.text[:200])
    t1 = run(lambda: p.fetchrow("SELECT status, completed_at FROM tasks WHERE lead_id=$1", hot["id"]))
    check("follow-up to-do completes itself", t1["status"] == "done" and t1["completed_at"] is not None, dict(t1))
    ev = run(lambda: p.fetch("SELECT from_status, to_status FROM lead_events WHERE lead_id=$1", hot["id"]))
    check("stage change recorded in history", [(e["from_status"], e["to_status"]) for e in ev] == [("new", "contacted")], ev)

    r = client.patch(f"/admin/leads/{hot['id']}", headers=H, json={"status": "contacted"})
    check("repeating the same status adds no history", r.status_code == 200 and len(run(lambda: p.fetch("SELECT 1 FROM lead_events WHERE lead_id=$1", hot["id"]))) == 1)

    r = client.patch(f"/admin/leads/{cold['id']}", headers=H, json={"status": "lost", "lost_reason": "Chose a competitor"})
    lost = r.json()
    check("lost stores date and reason", r.status_code == 200 and lost["lost_reason"] == "Chose a competitor" and lost["lost_at"] is not None, r.text[:200])
    check("lost also completes its follow-up", run(lambda: p.fetchval("SELECT status FROM tasks WHERE lead_id=$1", cold["id"])) == "done")

    future = (datetime.now(timezone.utc) + timedelta(days=3)).replace(microsecond=0)
    r = client.patch(f"/admin/leads/{hot['id']}", headers=H, json={"next_action_at": future.isoformat()})
    t2 = run(lambda: p.fetchrow("SELECT status, due_at FROM tasks WHERE lead_id=$1", hot["id"]))
    check("setting a follow-up date reopens the to-do at that time", r.status_code == 200 and t2["status"] == "open" and abs((t2["due_at"] - future).total_seconds()) < 1, dict(t2))
    r = client.patch(f"/admin/leads/{hot['id']}", headers=H, json={"next_action_at": "2026-12-01T10:00:00"})
    check("a date without a timezone is accepted (read as UTC)", r.status_code == 200)

    check("notes-only update still works", client.patch(f"/admin/leads/{hot['id']}", headers=H, json={"notes": "called, left voicemail"}).json()["notes"] == "called, left voicemail")
    check("unknown lead -> 404", client.patch("/admin/leads/00000000-0000-0000-0000-000000000000", headers=H, json={"status": "won"}).status_code == 404)
    check("bad lead id -> 400", client.patch("/admin/leads/not-a-uuid", headers=H, json={"status": "won"}).status_code == 400)
    check("empty update -> 400", client.patch(f"/admin/leads/{hot['id']}", headers=H, json={}).status_code == 400)

    # ------------------------------------------------------------ booking moves the lead to 'booked'
    async def booking():
        t = await tenant()
        lead = await new_lead("Bo King", phone="+6421000009", message="Booked appointment", consent=True)
        appt = dict(await p.fetchrow(
            "INSERT INTO appointments (tenant_id, lead_id, starts_at, ends_at, name, phone, consent_contact) "
            "VALUES ($1,$2, now() + interval '2 days', now() + interval '2 days 30 minutes', 'Bo King', '+6421000009', true) RETURNING *",
            tid, lead["id"]))
        await automation.on_appointment_booked(t, appt, lead)
        return lead["id"], await p.fetchval("SELECT status FROM leads WHERE id=$1", lead["id"]), await p.fetchval("SELECT count(*) FROM lead_events WHERE lead_id=$1 AND to_status='booked'", lead["id"])
    bid, bstatus, bevents = run(booking)
    check("a booking moves its lead to the booked stage", bstatus == "booked" and bevents == 1, (bstatus, bevents))

    # ------------------------------------------------------------ to-do API
    r = client.post("/admin/tenants/off/tasks", headers=H, json={"title": "Order parts for Hana", "due_at": "2026-12-05T09:00:00"})
    manual = r.json()
    check("create a manual to-do", r.status_code == 201 and manual["kind"] == "manual" and manual["status"] == "open", r.text[:200])
    check("naive due date stored as UTC", manual["due_at"].startswith("2026-12-05T09:00:00"), manual["due_at"])
    check("empty title rejected", client.post("/admin/tenants/off/tasks", headers=H, json={"title": "  "}).status_code in (400, 422))
    check("a to-do can be tied to a lead of this client", client.post("/admin/tenants/off/tasks", headers=H, json={"title": "Send quote", "lead_id": str(hot["id"])}).status_code == 201)

    async def other_tenant_lead():
        t2id = await p.fetchval("INSERT INTO tenants (slug, name, public_key) VALUES ('other','Other','pk_other') RETURNING id")
        return await p.fetchval("INSERT INTO leads (tenant_id, name) VALUES ($1,'Stranger') RETURNING id", t2id)
    stranger = run(other_tenant_lead)
    check("cannot attach another client's lead (404)", client.post("/admin/tenants/off/tasks", headers=H, json={"title": "x", "lead_id": str(stranger)}).status_code == 404)
    check("bad lead id on a to-do -> 400", client.post("/admin/tenants/off/tasks", headers=H, json={"title": "x", "lead_id": "nope"}).status_code == 400)

    open_list = client.get("/admin/tenants/off/tasks", headers=H).json()
    check("open list excludes done, ordered by due date", all(x["status"] == "open" for x in open_list) and [x["due_at"] for x in open_list if x["due_at"]] == sorted(x["due_at"] for x in open_list if x["due_at"]), [x["title"] for x in open_list])
    check("list shows the lead's name", any(x["lead_name"] == "Hana Ngata" for x in open_list))
    r = client.patch(f"/admin/tasks/{manual['id']}", headers=H, json={"status": "done"})
    check("complete a to-do", r.status_code == 200 and r.json()["status"] == "done" and r.json()["completed_at"], r.text[:200])
    check("done list contains it, open list does not", any(x["id"] == manual["id"] for x in client.get("/admin/tenants/off/tasks?status=done", headers=H).json())
          and not any(x["id"] == manual["id"] for x in client.get("/admin/tenants/off/tasks", headers=H).json()))
    r = client.patch(f"/admin/tasks/{manual['id']}", headers=H, json={"status": "open"})
    check("reopen clears the completed time", r.json()["status"] == "open" and r.json()["completed_at"] is None, r.text[:200])
    check("rename and clear the due date", client.patch(f"/admin/tasks/{manual['id']}", headers=H, json={"title": "Order parts", "due_at": None}).json()["due_at"] is None)
    check("unknown to-do -> 404", client.patch("/admin/tasks/999999", headers=H, json={"status": "done"}).status_code == 404)
    check("delete a to-do", client.delete(f"/admin/tasks/{manual['id']}", headers=H).status_code == 200 and client.delete(f"/admin/tasks/{manual['id']}", headers=H).status_code == 404)

    # ------------------------------------------------------------ pipeline and summary
    async def more_leads():
        a = await new_lead("Won Big", value=200000)
        b = await new_lead("Won Small")                       # no value: falls back to the $500 average
        c = await new_lead("Open Valued", value=100000)
        d = await new_lead("Open Default")
        return a, b, c, d
    a, b, c, d = run(more_leads)
    client.patch(f"/admin/leads/{a['id']}", headers=H, json={"status": "won"})
    client.patch(f"/admin/leads/{b['id']}", headers=H, json={"status": "won"})
    client.patch(f"/admin/leads/{c['id']}", headers=H, json={"status": "contacted"})

    r = client.get("/admin/tenants/off/pipeline", headers=H)
    pl = r.json()
    counts = {s: pl["stages"][s]["count"] for s in pl["stages"]}
    check("pipeline groups every lead by stage", r.status_code == 200 and counts == {"new": 1, "contacted": 2, "booked": 1, "won": 2, "lost": 1}, counts)
    check("won value uses own value or the average", pl["won_value_cents"] == 200000 + 50000, pl["won_value_cents"])
    open_expected = sum(l["effective_value_cents"] for s in ("new", "contacted", "booked") for l in pl["stages"][s]["leads"])
    weighted_expected = round(sum(l["effective_value_cents"] * sales.STAGE_ODDS[s] for s in ("new", "contacted", "booked") for l in pl["stages"][s]["leads"]))
    check("open and weighted totals add up", pl["open_value_cents"] == open_expected and pl["weighted_value_cents"] == weighted_expected, (pl["open_value_cents"], open_expected))
    check("leads without a value use the client average ($500)", any(l["name"] == "Open Default" and l["effective_value_cents"] == 50000 for l in pl["stages"]["new"]["leads"]))
    check("pipeline reports the stage odds", pl["odds"]["booked"] == 0.6 and pl["average_lead_value_cents"] == 50000)

    run(lambda: p.execute("INSERT INTO tasks (tenant_id, title, due_at) VALUES ($1, 'Overdue thing', now() - interval '1 day')", tid))
    sm = client.get("/admin/tenants/off/sales-summary?days=7", headers=H).json()
    check("summary counts this week's new leads and wins", sm["new_leads"] == 7 and sm["won"] == 2 and sm["won_value_cents"] == 250000, sm)
    check("summary win rate = won / (won + lost)", sm["lost"] == 1 and sm["win_rate"] == round(2 / 3, 2), (sm["won"], sm["lost"], sm["win_rate"]))
    check("summary shows overdue to-dos and pipeline", sm["overdue_todos"] >= 1 and sm["open_value_cents"] == pl["open_value_cents"])
    check("summary leads_waiting is None while alerts are off", sm["leads_waiting"] is None)
    check("days is clamped (0 -> 1, huge -> 365)", client.get("/admin/tenants/off/sales-summary?days=0", headers=H).json()["days"] == 1 and client.get("/admin/tenants/off/sales-summary?days=99999", headers=H).json()["days"] == 365)

    # ------------------------------------------------------------ weekly digest
    monday_local = datetime(2026, 11, 9, 10, 0, tzinfo=NZ)
    check("test date is a Monday", monday_local.weekday() == 0)
    check("digest is off by default", run(lambda: sales.check_digests(monday_local)) == 0)
    check("PATCH weekly_digest on", client.patch("/admin/tenants/off", headers=H, json={"weekly_digest": True}).status_code == 200)
    check("no digest outside Monday daytime", run(lambda: sales.check_digests(datetime(2026, 11, 10, 10, 0, tzinfo=NZ))) == 0 and run(lambda: sales.check_digests(datetime(2026, 11, 9, 6, 0, tzinfo=NZ))) == 0)
    check("Monday 10am: one digest queued", run(lambda: sales.check_digests(monday_local)) == 1)
    dg = run(lambda: p.fetchrow("SELECT subject, body, to_addr, kind FROM outbox WHERE dedupe_key LIKE 'digest:%'"))
    check("digest goes to the owner with the numbers", dg["to_addr"] == "owner@off.example" and dg["kind"] == "owner_alert" and "Your week at Office Co" in dg["subject"] and "Won: 2" in dg["body"], dict(dg))
    check("only one digest per week", run(lambda: sales.check_digests(monday_local)) == 0 and run(lambda: sales.check_digests(monday_local + timedelta(hours=3))) == 0)
    check("next week gets its own", run(lambda: sales.check_digests(monday_local + timedelta(days=7))) == 1)

    # ------------------------------------------------------------ calendar feed
    tenant_json = client.get("/admin/tenants/off", headers=H).json()
    url = tenant_json["calendar_url"]
    check("calendar feed URL is shown to the owner", url and url.startswith("https://chat.example.test/api/v1/calendar/") and url.endswith(".ics"), url)
    path = url.replace("https://chat.example.test", "")
    r = client.get(path)
    check("feed is served as text/calendar with no login", r.status_code == 200 and r.headers["content-type"].startswith("text/calendar"), (r.status_code, r.headers.get("content-type")))
    check("feed contains the booked appointment", "BEGIN:VCALENDAR" in r.text and "SUMMARY:Bo King - Office Co" in r.text.replace("\r\n ", "") and "Phone: +6421000009" in r.text.replace("\r\n ", "").replace("\\n", "\n"), r.text[:300])
    check("feed is private (not cached publicly)", "private" in r.headers.get("cache-control", ""))
    check("wrong token -> 404", client.get("/api/v1/calendar/not-a-real-token.ics").status_code == 404)
    run(lambda: p.execute("UPDATE appointments SET status='cancelled' WHERE tenant_id=$1", tid))
    check("a cancelled appointment is marked cancelled in the feed", "STATUS:CANCELLED" in client.get(path).text)
    created_t = run(lambda: tenants.create("Fresh Co", None))
    check("new clients get a calendar token immediately", bool(created_t.get("calendar_token")))
    run(lambda: p.execute("UPDATE tenants SET calendar_token = NULL WHERE id = $1", created_t["id"]))
    run(lambda: tenants.ensure_calendar_tokens())
    check("existing clients are backfilled at startup", bool(run(lambda: p.fetchval("SELECT calendar_token FROM tenants WHERE id=$1", created_t["id"]))))

    # ------------------------------------------------------------ admin protection
    for method, route in [("get", "/admin/tenants/off/tasks"), ("get", "/admin/tenants/off/pipeline"), ("get", "/admin/tenants/off/sales-summary"), ("delete", "/admin/tasks/1")]:
        check(f"{route} needs the admin token", getattr(client, method)(route).status_code == 401)

print(f"\n{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
