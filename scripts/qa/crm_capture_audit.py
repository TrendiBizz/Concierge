"""Audit what the CRM actually captured, versus what each enquiry carried.

Run inside the api container:

    docker exec -i -e PYTHONPATH=/srv -w /srv trendi-api-1 python3 - < scripts/qa/crm_capture_audit.py

Read-only. Reports four things per tenant: coverage of each identity field, enquiries that never
became a customer, customers with no history, and duplicate customers for one person.
"""
import asyncio

from app import db

async def counts(pool, sql, *args):
    return await pool.fetchval(sql, *args)

async def main():
    await db.init()
    p = db.pool()
    tenants = await p.fetch("SELECT id, slug FROM tenants ORDER BY slug")
    for t in tenants:
        tid = t["id"]
        leads = await counts(p, "SELECT count(*) FROM leads WHERE tenant_id=$1", tid)
        if not leads:
            continue
        print(f"\n=== {t['slug']} — {leads} leads")
        rows = await p.fetch("""
            SELECT channel,
                   count(*) AS total,
                   count(*) FILTER (WHERE coalesce(name,'')<>'') AS has_name,
                   count(*) FILTER (WHERE coalesce(phone,'')<>'') AS has_phone,
                   count(*) FILTER (WHERE coalesce(email,'')<>'') AS has_email,
                   count(*) FILTER (WHERE coalesce(company,'')<>'') AS has_company,
                   count(*) FILTER (WHERE case_id IS NOT NULL) AS linked
            FROM leads WHERE tenant_id=$1 GROUP BY 1 ORDER BY 2 DESC""", tid)
        for r in rows:
            print(f"  {r['channel']:<6} total={r['total']:<4} name={r['has_name']:<4} "
                  f"phone={r['has_phone']:<4} email={r['has_email']:<4} company={r['has_company']:<3} "
                  f"case={r['linked']}")
        # An enquiry with an email or phone but no customer record is a capture failure.
        orphan = await p.fetch("""
            SELECT id, channel, coalesce(name,''), phone, email, created_at
            FROM leads WHERE tenant_id=$1 AND case_id IS NULL
              AND (coalesce(phone,'')<>'' OR coalesce(email,'')<>'')
            ORDER BY created_at DESC LIMIT 5""", tid)
        print(f"  enquiries with contact details but NO customer record: {len(orphan)}")
        for o in orphan:
            print("    ", {k: str(v)[:40] for k, v in dict(o).items()})
        # Customers with no history explain a bare CRM screen.
        bare = await counts(p, """
            SELECT count(*) FROM customer_cases c WHERE c.tenant_id=$1
              AND NOT EXISTS (SELECT 1 FROM case_events e WHERE e.case_id=c.id)""", tid)
        named = await counts(p, """
            SELECT count(*) FROM customer_cases WHERE tenant_id=$1 AND coalesce(display_name,'')<>''""", tid)
        cases = await counts(p, "SELECT count(*) FROM customer_cases WHERE tenant_id=$1", tid)
        print(f"  customers={cases} named={named} with_no_history={bare}")
        dupes = await p.fetch("""
            SELECT coalesce(primary_email, primary_phone) AS identity, count(*) AS n
            FROM customer_cases WHERE tenant_id=$1
            GROUP BY 1 HAVING count(*) > 1 ORDER BY 2 DESC LIMIT 3""", tid)
        print(f"  duplicate customers for one identity: {len(dupes)}")
        for d in dupes:
            print("    ", dict(d))
    await db.close()

asyncio.run(main())
