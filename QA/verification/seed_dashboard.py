"""Seed the THROWAWAY database (port 55432) with demo data for the dashboard browser test."""
import asyncio

import asyncpg


async def main():
    c = await asyncpg.connect("postgresql://postgres:test@127.0.0.1:55432/postgres")
    tid = await c.fetchval(
        "INSERT INTO tenants (slug, name, public_key, notify_email, timezone, sla_minutes, sla_min_score) "
        "VALUES ('demo', 'Demo Plumbing', 'pk_demo', 'owner@demo.example', 'Pacific/Auckland', 15, 70) RETURNING id")

    async def lead(name, email, phone, msg, score, label, age_min, status="new", reasons=None, consent_mkt=False):
        import json
        await c.execute(
            "INSERT INTO leads (tenant_id, name, email, phone, message, channel, status, score, score_label, score_reasons, "
            "consent_contact, consent_marketing, consent_marketing_basis, created_at) "
            "VALUES ($1,$2,$3,$4,$5,'chat',$6,$7,$8,$9::jsonb,true,$10,$11, now() - make_interval(mins => $12))",
            tid, name, email, phone, msg, status, score, label, json.dumps(reasons or []), consent_mkt,
            "opted in on booking form" if consent_mkt else "", age_min)

    await lead("Hana Ngata", "hana@example.com", "+6421555001", "Burst pipe in the kitchen, can someone come today? Need a quote.",
               88, "hot", 42, reasons=["+25 Gave a phone number", "+10 Gave an email address", "+20 Asked about price, booking or timing", "+10 Agreed to be contacted"])
    await lead("Tom Baker", "tom@example.com", "", "How much for a hot water cylinder replacement?", 52, "warm", 300)
    await lead("Sam Li", "sam@example.com", "", "Just browsing", 15, "cold", 600)
    await lead("Priya Shah", "priya@example.com", "+6421555002", "Quote for bathroom reno please", 75, "hot", 90, status="contacted")
    await lead("Old Customer One", "old1@example.com", "+6421555003", "Gutters last year", 45, "warm", 60 * 24 * 90, status="lost", consent_mkt=True)
    await lead("Old Customer Two", "old2@example.com", "+6421555004", "Tap repair last year", 30, "cold", 60 * 24 * 120, status="contacted", consent_mkt=True)
    await c.execute("INSERT INTO conversations (tenant_id, session_id) VALUES ($1, 's1')", tid)
    await c.close()
    print("seeded")


asyncio.run(main())
