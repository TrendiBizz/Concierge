"""Integration check for reactivation campaigns against a THROWAWAY Postgres (port 55432). Never the live DB."""
import asyncio
import os
import sys
from datetime import datetime, timezone

os.environ.update({
    "DATABASE_URL": f"postgresql://postgres:test@127.0.0.1:{os.environ.get('CONCIERGE_TEST_POSTGRES_PORT', '55432')}/postgres",
    "OUTBOX_ENABLED": "false",
    "UNSUBSCRIBE_SECRET": "integration-secret",
    "PUBLIC_BASE_URL": "https://chat.example.test",
    "SMTP_HOST": "smtp.example.test",
    "SMTP_FROM": "hello@example.test",
    "SMS_PROVIDER": "smsgate",
    "SMSGATE_BASE_URL": "https://gw.example.test",
    "SMSGATE_USERNAME": "u",
    "SMSGATE_PASSWORD": "p",
    "CAMPAIGN_EMAIL_PER_HOUR": "60",
    "CAMPAIGN_COOLDOWN_DAYS": "30",
})
sys.path.insert(0, os.path.expanduser("~/work-staging/shims"))
sys.path.insert(0, os.path.expanduser("~/work-staging/concierge-core/api"))

import uuid  # noqa: E402

from app import campaigns, channel_authorization, db, outbox, tenants, unsub  # noqa: E402

results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(("PASS  " if ok else "FAIL  ") + name + ("" if ok else f"  -> {detail}"))


async def raises(coro, needle):
    try:
        await coro
    except campaigns.CampaignError as exc:
        return needle in str(exc)
    return False


async def main():
    await db.init()
    await db.init()
    p = db.pool()
    tid = await p.fetchval(
        "INSERT INTO tenants (slug, name, public_key, notify_email, sms_enabled) "
        "VALUES ('t', 'Test Co', 'pk_t', 'owner@test.example', true) RETURNING id")

    async def lead(name, email="", phone="", consent=True, status="contacted", days=60, score=0):
        return await p.fetchval(
            "INSERT INTO leads (tenant_id, name, email, phone, status, score, consent_marketing, created_at) "
            "VALUES ($1,$2,$3,$4,$5,$6,$7, now() - make_interval(days => $8)) RETURNING id",
            tid, name, email, phone, status, score, consent, days)

    await lead("Pat Lee", "pat@example.com", "+6421000001", score=60)               # eligible
    await lead("Pat Again", "PAT@example.com", days=90)                              # duplicate of Pat (case-insensitive)
    await lead("No Consent", "noconsent@example.com", consent=False)                 # no marketing consent
    await lead("Opted Out", "optout@example.com")                                    # will opt out
    await lead("Too Recent", "recent@example.com", days=3)                           # newer than 30 days
    await lead("Already Booked", "booked@example.com", status="booked")              # status excluded
    await lead("Sam Cooke", "sam@example.com", score=20)                             # eligible
    await lead("Phone Only", phone="+6421000002")                                    # no email: not in email campaign
    await outbox.opt_out(tid, "optout@example.com")

    tenant = await tenants.get_by_id(tid)
    check("tenant row carries campaigns_enabled (default off)", tenant["campaigns_enabled"] is False)

    camp = await campaigns.create(tenant, "Win-back", "email", "We miss you at {business}",
                                  "Hi {first}, it has been a while. Book again any time.", {})
    prev = await campaigns.preview(tenant, camp)
    check("preview counts only eligible (Pat, Sam)", prev["recipients"] == 2, prev)
    sk = prev["skipped"]
    check("skip reasons reported", sk["opted_out"] == 1 and sk["duplicate"] == 1, sk)
    check("preview blocked while campaigns are off", prev["ready"] is False and any("switched off" in x for x in prev["problems"]))
    check("sample contacts are masked", all("***" in s["contact"] for s in prev["sample_recipients"]), prev["sample_recipients"])
    check("sample message personalised", prev["sample_message"].startswith("Hi Pat"), prev["sample_message"])

    check("send refused while off", await raises(campaigns.send(tenant, camp, 2), "switched off"))
    await p.execute("UPDATE tenants SET campaigns_enabled = true WHERE id = $1", tid)
    tenant = await tenants.get_by_id(tid)
    check("send refused when audience size is wrong", await raises(campaigns.send(tenant, camp, 5), "Audience changed"))
    check("nothing queued by the refusals", await p.fetchval("SELECT count(*) FROM outbox WHERE campaign_id=$1", camp["id"]) == 0)

    result = await campaigns.send(tenant, camp, 2)
    rows = await p.fetch("SELECT * FROM outbox WHERE campaign_id=$1 ORDER BY send_at", camp["id"])
    check("2 messages queued", result["queued"] == 2 and len(rows) == 2, result)
    check("sends are staggered 60s apart (60/hour)", (rows[1]["send_at"] - rows[0]["send_at"]).total_seconds() == 60,
          [r["send_at"] for r in rows])
    check("body personalised + unsubscribe footer", "Hi Pat" in rows[0]["body"] and "/api/v1/unsubscribe/" in rows[0]["body"]
          and "Test Co" in rows[0]["body"], rows[0]["body"])
    check("subject rendered", rows[0]["subject"] == "We miss you at Test Co", rows[0]["subject"])
    check("campaign marked queued", (await campaigns.get(camp["id"]))["status"] == "queued")
    check("cannot send twice", await raises(campaigns.send(tenant, await campaigns.get(camp["id"]), 2), "already queued"))

    camp2 = await campaigns.create(tenant, "Second", "email", "Again", "Hello {first}", {})
    prev2 = await campaigns.preview(tenant, camp2)
    check("cooldown excludes people just messaged", prev2["recipients"] == 0 and prev2["skipped"]["cooldown"] == 2, prev2)

    # unsubscribe through the real token
    link = unsub.url_for(tid, "pat@example.com")
    token = link.rsplit("/", 1)[1]
    done = await campaigns.unsubscribe(token)
    check("unsubscribe accepted", done is not None and done["tenant_name"] == "Test Co", done)
    check("contact is now opted out", await outbox.is_opted_out(tid, "pat@example.com"))
    st = await campaigns.stats(camp["id"])
    check("Pat's pending message cancelled, Sam's still pending", st.get("cancelled") == 1 and st.get("pending") == 1, st)
    check("forged token rejected", await campaigns.unsubscribe(token[:-3] + "xxx") is None)

    # Delivery re-checks the customer's channel authorization before anything else, so the tenant must have
    # authorized its sending channels for this step to reach (and prove) the campaign kill switch.
    owner = uuid.uuid4()
    for channel in ("email_send", "sms_send"):
        await channel_authorization.record_authorization(
            tid, owner, channel_authorization.ChannelAuthorization(channel=channel, authorized=True, acknowledgement=True))

    # delivery-time kill switch
    await p.execute("UPDATE tenants SET campaigns_enabled = false WHERE id = $1", tid)
    pending = dict(await p.fetchrow("SELECT * FROM outbox WHERE campaign_id=$1 AND status='pending'", camp["id"]))
    await outbox._deliver(pending)
    after = await p.fetchrow("SELECT status, last_error FROM outbox WHERE id=$1", pending["id"])
    check("kill switch skips queued messages at send time", after["status"] == "skipped" and after["last_error"] == "campaigns_disabled", dict(after))

    # cancel path
    await p.execute("UPDATE tenants SET campaigns_enabled = true WHERE id = $1", tid)
    tenant = await tenants.get_by_id(tid)
    await lead("Late Lead", "late@example.com", score=10)
    camp3 = await campaigns.create(tenant, "Third", "email", "Hi", "Hello {first}", {})
    pv3 = await campaigns.preview(tenant, camp3)
    await campaigns.send(tenant, camp3, pv3["recipients"])
    n = await campaigns.cancel(await campaigns.get(camp3["id"]))
    check("cancel stops pending messages", n >= 1 and (await campaigns.stats(camp3["id"])).get("pending") is None, n)

    # SMS campaign: ends with STOP line, only phone numbers
    sms_camp = await campaigns.create(tenant, "Text", "sms", "", "Hi {first}, {business} has openings this week.", {})
    sp = await campaigns.preview(tenant, sms_camp)
    check("sms audience uses phone numbers only (Pat, Phone Only)", sp["recipients"] == 2, sp)
    await campaigns.send(tenant, sms_camp, sp["recipients"])
    srow = await p.fetchrow("SELECT body FROM outbox WHERE campaign_id=$1 LIMIT 1", sms_camp["id"])
    check("sms ends with STOP line", srow["body"].endswith("Reply STOP to opt out."), srow["body"])

    await db.close()


asyncio.run(main())
print(f"\n{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
