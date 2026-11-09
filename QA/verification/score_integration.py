"""Integration check for lead scoring against a THROWAWAY Postgres (port 55432). Never the live DB."""
import asyncio
import json
import os
import sys

URL = f"postgresql://postgres:test@127.0.0.1:{os.environ.get('CONCIERGE_TEST_POSTGRES_PORT', '55432')}/postgres"
os.environ["DATABASE_URL"] = URL
os.environ["OUTBOX_ENABLED"] = "false"

# Resolve paths relative to THIS repository, not a developer's ~/work-staging scratch copies.
# Those stale copies used to be prepended ahead of the checkout, so a suite could silently test
# code from another branch or another day. CI never noticed because the paths did not exist there;
# locally they did. The repository the suite lives in is always the right one to test.
_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(_REPO, "QA", "verification", "shims"))
sys.path.insert(0, os.path.join(_REPO, "api"))

from app import automation, db, scoring, tenants  # noqa: E402

results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(("PASS  " if ok else "FAIL  ") + name + ("" if ok else f"  {detail}"))


async def main():
    await db.init()
    await db.init()  # schema must be idempotent
    p = db.pool()
    check("schema applied twice", True)
    cols = {r["column_name"] for r in await p.fetch(
        "SELECT column_name FROM information_schema.columns WHERE table_name='leads'")}
    check("leads has score columns", {"score", "score_label", "score_reasons", "scored_at"} <= cols, cols)

    tid = await p.fetchval(
        "INSERT INTO tenants (slug, name, public_key, notify_email, timezone) "
        "VALUES ('t', 'Test Co', 'pk_test', 'owner@example.com', 'Pacific/Auckland') RETURNING id")
    conv = await p.fetchval(
        "INSERT INTO conversations (tenant_id, session_id) VALUES ($1, 's1') RETURNING id", tid)
    for i in range(4):
        await p.execute("INSERT INTO messages (conversation_id, role, content) VALUES ($1, 'user', $2)", conv, f"m{i}")
    await p.execute("INSERT INTO messages (conversation_id, role, content) VALUES ($1, 'assistant', 'reply')", conv)

    hot_row = await p.fetchrow(
        "INSERT INTO leads (tenant_id, conversation_id, name, email, phone, message, channel, page_url, consent_contact) "
        "VALUES ($1,$2,'Pat Lee','pat@example.com','+6421000000',"
        "'How much is a full service and can I book for tomorrow?','chat','https://t.nz/pricing',true) RETURNING *",
        tid, conv)
    tenant = await tenants.get_by_id(tid)

    # Real path: on_lead_created scores, stores and queues the owner alert.
    await automation.on_lead_created(tenant, dict(hot_row))
    stored = await p.fetchrow("SELECT score, score_label, score_reasons, scored_at FROM leads WHERE id=$1", hot_row["id"])
    check("hot lead stored as hot", stored["score_label"] == "hot" and stored["score"] >= 70, dict(stored))
    check("reasons stored as json list", isinstance(json.loads(stored["score_reasons"]), list) and stored["scored_at"] is not None)
    alert = await p.fetchrow("SELECT subject, body FROM outbox WHERE dedupe_key=$1", f"lead:{hot_row['id']}:owner")
    check("owner alert subject tagged [HOT]", alert is not None and alert["subject"].startswith("[HOT] "), alert and alert["subject"])
    check("owner alert body shows score and why", alert is not None and "Score:" in alert["body"] and "Why:" in alert["body"])
    turns_reason = [r for r in json.loads(stored["score_reasons"]) if "conversation" in r]
    check("turn count read from messages (4 user msgs)", len(turns_reason) == 1)

    cold_row = await p.fetchrow(
        "INSERT INTO leads (tenant_id, name, email, message, channel) VALUES ($1,'','a@b.co','hi','chat') RETURNING *", tid)
    await automation.on_lead_created(tenant, dict(cold_row))
    cold = await p.fetchrow("SELECT score, score_label FROM leads WHERE id=$1", cold_row["id"])
    alert2 = await p.fetchrow("SELECT subject FROM outbox WHERE dedupe_key=$1", f"lead:{cold_row['id']}:owner")
    check("cold lead stored as cold", cold["score_label"] == "cold" and cold["score"] == 10, dict(cold))
    check("cold alert has no tag", alert2 is not None and not alert2["subject"].startswith("["), alert2 and alert2["subject"])

    booked_src = await p.fetchrow(
        "INSERT INTO leads (tenant_id, name, phone, message, channel) VALUES ($1,'Sam','+6421111111','Booked appointment','chat') RETURNING *", tid)
    booked = await scoring.apply(dict(booked_src), booked=True)
    check("booking adds 30", booked["score"] == 25 + 5 + 30 and "Booked" in " ".join(scoring.reasons_of(booked)), booked["score"])

    rows = await p.fetch("SELECT id FROM leads WHERE tenant_id=$1 AND score >= $2", tid, 40)
    check("min_score filter query works", len(rows) == 2, len(rows))
    rpt = await p.fetch("SELECT name, message, channel, status, score_label, created_at FROM leads WHERE tenant_id=$1", tid)
    check("report query works", len(rpt) == 3)

    await db.close()


asyncio.run(main())
print(f"\n{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
