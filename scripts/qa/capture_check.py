"""Exercise customer capture against a live API without ever emailing or texting anyone.

Run inside the api container:

    docker exec -i -e PYTHONPATH=/srv -w /srv trendi-api-1 python3 - < scripts/qa/capture_check.py

Two lessons are baked in, both learned the hard way:

* **Mute the object you pass, not just the row.** The first version cleared `notify_email` in the
  database but went on using the tenant dict it had already read, so every run still emailed the
  operator a "[WARM] New lead" alert. The dict handed to the tool is the one that matters.
* **Owner alerts are exempt from a paused tenant** by design, so pausing suppresses replies to the
  customer while the owner notification still goes out. Muting the address is the only safe hold.
"""
import asyncio
import sys

from app import db, tools

TENANT_SLUG = "trendi-meta-review"
MESSAGE = "Hi it's Sarah from Acme Construction, can you call me on 021 555 7788"
EXPECTED = {"name": "Sarah", "company": "Acme Construction", "phone": "+64215557788"}


async def main() -> int:
    await db.init()
    pool = db.pool()
    t = dict(await pool.fetchrow("SELECT * FROM tenants WHERE slug=$1", TENANT_SLUG))
    if not t:
        print(f"tenant {TENANT_SLUG} not found")
        return 2
    saved = (t.get("notify_email"), t.get("notify_phone"))
    await pool.execute("UPDATE tenants SET notify_email='', notify_phone='' WHERE id=$1", t["id"])
    # THE FIX: the dict the tool sees must be the muted one, or the alert still goes to the owner.
    t["notify_email"], t["notify_phone"] = "", ""
    try:
        tools.run_tool.__globals__  # noqa: B018  (make the dependency explicit)
        ctx = {"channel": "chat", "conversation_id": None, "page_url": "https://trendibizz.com/",
               "utm": {}, "last_message": MESSAGE}
        result = await tools.run_tool(t, "capture_lead", {"message": "quote please"}, ctx)
        row = await pool.fetchrow("""
            SELECT l.name, l.company, l.phone, c.case_key
            FROM leads l LEFT JOIN customer_cases c ON c.id = l.case_id
            WHERE l.tenant_id=$1 AND l.phone=$2 ORDER BY l.created_at DESC LIMIT 1""",
            t["id"], EXPECTED["phone"])
        captured = dict(row) if row else {}
        ok = (result.get("ok") and captured.get("name") == EXPECTED["name"]
              and captured.get("company") == EXPECTED["company"])
        print("tool result:", result)
        print("captured:   ", captured or "NOTHING CAPTURED")
        print("PASS" if ok else "FAIL")
        return 0 if ok else 1
    finally:
        await pool.execute("DELETE FROM leads WHERE tenant_id=$1 AND phone=$2", t["id"], EXPECTED["phone"])
        await pool.execute("DELETE FROM customer_cases WHERE tenant_id=$1 AND case_key=$2",
                           t["id"], "phone:" + EXPECTED["phone"])
        await pool.execute("UPDATE tenants SET notify_email=$2, notify_phone=$3 WHERE id=$1",
                           t["id"], saved[0] or "", saved[1] or "")
        restored = await pool.fetchrow("SELECT notify_email FROM tenants WHERE id=$1", t["id"])
        print("notifications restored to:", restored["notify_email"])
        await db.close()


sys.exit(asyncio.run(main()))
