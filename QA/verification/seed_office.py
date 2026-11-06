"""Seed the THROWAWAY database (port 55432) for the office-features browser test."""
import asyncio
import json

import asyncpg


async def main():
    c = await asyncpg.connect("postgresql://postgres:test@127.0.0.1:55432/postgres")
    tid = await c.fetchval(
        "INSERT INTO tenants (slug, name, public_key, notify_email, timezone, lead_value_cents, sla_minutes, sla_min_score) "
        "VALUES ('demo', 'Demo Plumbing', 'pk_demo', 'owner@demo.example', 'Pacific/Auckland', 40000, 15, 70) RETURNING id")

    async def lead(name, status, score, label, msg, value=0, age_min=30, phone="", email="", reason=""):
        return await c.fetchval(
            "INSERT INTO leads (tenant_id, name, phone, email, message, channel, status, score, score_label, score_reasons, "
            "value_cents, consent_contact, lost_reason, won_at, lost_at, created_at) "
            "VALUES ($1,$2,$3,$4,$5,'chat',$6,$7,$8,$9::jsonb,$10,true,$11,"
            "CASE WHEN $6='won' THEN now() END, CASE WHEN $6='lost' THEN now() END, now() - make_interval(mins => $12)) RETURNING id",
            tid, name, phone, email, msg, status, score, label, json.dumps(["+25 Gave a phone number"]), value, reason, age_min)

    hana = await lead("Hana Ngata", "new", 88, "hot", "Burst pipe, can someone come today? Need a quote.", phone="+6421555001", email="hana@example.com")
    tom = await lead("Tom Baker", "new", 52, "warm", "How much for a hot water cylinder replacement?", age_min=300, email="tom@example.com")
    sam = await lead("Sam Li", "new", 15, "cold", "Just browsing", age_min=600, email="sam@example.com")
    priya = await lead("Priya Shah", "contacted", 75, "hot", "Quote for bathroom reno please", value=120000, age_min=900, phone="+6421555002")
    bo = await lead("Bo King", "booked", 70, "hot", "Booked appointment", age_min=1200, phone="+6421555003")
    await lead("Anna Won", "won", 80, "hot", "Reno finished", value=180000, age_min=3000)
    await lead("Lee Lost", "lost", 40, "warm", "Wanted a cheaper quote", age_min=3000, reason="Went with a cheaper quote")

    async def task(title, lead_id, due_sql, kind="manual", source="manual", status="open"):
        await c.execute(
            f"INSERT INTO tasks (tenant_id, lead_id, title, notes, due_at, kind, source, status, completed_at) "
            f"VALUES ($1,$2,$3,'', {due_sql}, $4, $5, $6, CASE WHEN $6='done' THEN now() END)",
            tid, lead_id, title, kind, source, status)
    await task("Follow up: Hana Ngata", hana, "now() - interval '20 minutes'", "follow_up", "system")
    await task("Follow up: Tom Baker", tom, "now() + interval '1 day'", "follow_up", "system")
    await task("Follow up: Sam Li", sam, "now() + interval '1 day'", "follow_up", "system")
    await task("Call supplier about the cylinder", None, "now() - interval '1 day'")
    await task("Order parts for Priya's bathroom", priya, "now() + interval '2 days'")
    await task("Send January invoices", None, "now() - interval '5 days'", status="done")

    await c.execute(
        "INSERT INTO appointments (tenant_id, lead_id, starts_at, ends_at, name, phone, notes) "
        "VALUES ($1,$2, now() + interval '2 days', now() + interval '2 days 30 minutes', 'Bo King', '+6421555003', 'Leaking tap, bring washers')",
        tid, bo)
    await c.close()
    print("seeded")


asyncio.run(main())
