"""One-off live proof for competitor-gap item C (one timeline per customer). Read-only."""
import asyncio

from app import casetimeline, db


async def main():
    await db.init()
    tenant = await db.pool().fetchrow("SELECT id, slug FROM tenants WHERE slug = 'pukeko-construction'")
    tid = tenant["id"]
    rows = await db.pool().fetch(
        """
        SELECT c.case_key, c.display_name, c.primary_phone, c.primary_email,
               c.automation_paused,
               (SELECT count(*) FROM case_events e WHERE e.case_id = c.id) AS event_count,
               (SELECT string_agg(DISTINCT e.channel, ',') FROM case_events e
                 WHERE e.case_id = c.id) AS channels
        FROM customer_cases c WHERE c.tenant_id = $1
        ORDER BY c.updated_at DESC LIMIT 5
        """, tid)
    print(f"tenant={tenant['slug']} contacts={len(rows)}")
    for row in rows:
        data = dict(row)
        print(" -", casetimeline.contact_label(data), "| events:",
              data["event_count"], "| channels:", data["channels"] or "-")
    if rows:
        key = rows[0]["case_key"]
        events = await casetimeline.timeline(tid, key, limit=200)
        summary = casetimeline.summarise(events)
        print("timeline for", casetimeline.contact_label(dict(rows[0])), "->", summary)
        if events:
            print("newest event:", events[0]["channel"], events[0]["direction"],
                  (events[0]["body"] or "")[:80].replace("\n", " "))
    total = await db.pool().fetchval(
        "SELECT count(*) FROM customer_cases WHERE tenant_id = $1", tid)
    print("total cases for tenant:", total)
    await db.close()


asyncio.run(main())
