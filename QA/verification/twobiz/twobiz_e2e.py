"""Two real businesses through the real code paths against a throwaway Postgres.

SAFETY: this script refuses to run unless DATABASE_URL already ends in the throwaway database
name. The previous version set os.environ after config.get_settings() had been cached, which
silently targeted production. The check below makes that class of mistake impossible.
"""
import asyncio, json, os, sys

from app.config import get_settings

_url = get_settings().database_url
if not _url.endswith("/concierge_twobiz_verify"):
    print("REFUSING TO RUN: target is", _url.rsplit("/", 1)[-1], "not concierge_twobiz_verify")
    sys.exit(2)


async def main():
    from app import db, tenants, casetimeline, owner_notifications, acknowledgements
    from app import quotations, booking, owner_onboarding

    await db.init()
    pool = db.pool()

    A = await tenants.create("Harbour Dental", "https://harbour.example", slug="harbour-dental")
    B = await tenants.create("Southern Plumbing", "https://southern.example", slug="southern-plumbing")
    await tenants.update("harbour-dental", {
        "timezone": "Pacific/Auckland", "default_country_code": "64",
        "notify_email": "owner-a@harbour.example", "notify_phone": "+64211111111",
        "sms_enabled": True, "slot_minutes": 30, "min_notice_hours": 0,
        "business_hours": {d: [["09:00", "17:00"]] for d in ("mon", "tue", "wed", "thu", "fri")},
    })
    await tenants.update("southern-plumbing", {
        "timezone": "America/Chicago", "default_country_code": "1",
        "notify_email": "owner-b@southern.example", "notify_phone": "+13125550199",
        "sms_enabled": True, "slot_minutes": 30, "min_notice_hours": 0,
        "business_hours": {d: [["08:00", "16:00"]] for d in ("mon", "tue", "wed", "thu", "fri")},
    })
    A = await tenants.get_by_slug("harbour-dental")
    B = await tenants.get_by_slug("southern-plumbing")
    print("TENANT A", A["slug"], A["timezone"], str(A["id"])[:8])
    print("TENANT B", B["slug"], B["timezone"], str(B["id"])[:8])

    for t in (A, B):
        for ch in ("email_read", "email_send", "sms_read", "sms_send", "call_recording"):
            await pool.execute(
                "INSERT INTO tenant_channel_authorizations(tenant_id,channel,authorized,actor_id) "
                "VALUES($1,$2,true,$1) ON CONFLICT(tenant_id,channel) DO UPDATE SET authorized=true",
                t["id"], ch)

    # --- steps 1/2/6: one customer, two businesses, two separate cases
    ca = await casetimeline.reconcile(A["id"], phone="021 555 123", email="hana@example.com", name="Hana")
    cb = await casetimeline.reconcile(B["id"], phone="312 555 0199", email="hana@example.com", name="Hana")
    print("STEP 2  case A =", ca["case_key"], "| case B =", cb["case_key"])
    assert ca["case_key"] != cb["case_key"] and ca["id"] != cb["id"]

    for t, case, ch, sk, body in (
        (A, ca, "sms", "provider-msg-1", "Do you have appointments this week?"),
        (B, cb, "email", "provider-msg-1", "Our hot water is leaking"),
    ):
        first = await casetimeline.record(t["id"], case_key=case["case_key"], channel=ch,
                                          direction="inbound", source_key=sk, body=body)
        replay = await casetimeline.record(t["id"], case_key=case["case_key"], channel=ch,
                                           direction="inbound", source_key=sk, body=body)
        assert first is not None and replay is None, f"{t['slug']}: retry must collapse"
        print(f"STEP 6  {t['slug']:18} first=inserted replay=deduped")

    ta = await casetimeline.timeline(A["id"], ca["case_key"])
    tb = await casetimeline.timeline(B["id"], cb["case_key"])
    assert len(ta) == 1 and len(tb) == 1 and ta[0]["body"] != tb[0]["body"]
    assert await casetimeline.timeline(B["id"], ca["case_key"]) == []
    print("STEP 6  timelines A=1 B=1, cross-tenant read returned []")

    # --- step 4: each owner reaches only their own destinations
    assert await owner_notifications.queue(A, "SMS enquiry", "Original A", "e2e:1") == ["email", "sms"]
    assert await owner_notifications.queue(B, "Email enquiry", "Original B", "e2e:2") == ["email", "sms"]
    rows = await pool.fetch("SELECT tenant_id, channel, to_addr FROM outbox ORDER BY id")
    got = {}
    for r in rows:
        got.setdefault(str(r["tenant_id"]), set()).add((r["channel"], r["to_addr"]))
    assert got[str(A["id"])] == {("email", "owner-a@harbour.example"), ("sms", "+64211111111")}, got[str(A["id"])]
    assert got[str(B["id"])] == {("email", "owner-b@southern.example"), ("sms", "+13125550199")}, got[str(B["id"])]
    print("STEP 4  each owner reached only their own two destinations")

    # --- step 5: acknowledgement is the enquirer's, not the owner's
    convo = await pool.fetchrow(
        "INSERT INTO conversations(tenant_id,session_id,channel) VALUES($1,'e2e-1','chat') RETURNING id", A["id"])
    lead = await pool.fetchrow(
        "INSERT INTO leads(tenant_id,conversation_id,channel,message) VALUES($1,$2,'chat','hi') RETURNING id",
        A["id"], convo["id"])
    r1 = await acknowledgements.request(A, {"requested": True, "channel": "email",
                                            "recipient": "hana@example.com"}, {"conversation_id": convo["id"]})
    assert r1["ok"] is False and r1["needs_confirmation"] is True
    r2 = await acknowledgements.request(A, {"requested": True, "channel": "email",
                                            "recipient": "hana@example.com", "confirmed": True},
                                        {"conversation_id": convo["id"]})
    assert r2["status"] == "queued"
    acks = await pool.fetch("SELECT tenant_id, to_addr FROM outbox WHERE kind='enquirer_ack'")
    assert len(acks) == 1 and acks[0]["to_addr"] == "hana@example.com"
    assert str(acks[0]["tenant_id"]) == str(A["id"])
    print("STEP 5  ask waits for confirmation; ack addressed to the enquirer and owned by A")

    # --- step 7b: quotations, isolation, replay
    qa = await quotations.create(quotations.QuoteDraft(
        lead_id=lead["id"], title="Dental quote", currency="NZD", tax_basis_points=1500,
        lines=[quotations.QuoteLine(description="Exam", quantity="2", unit_price_cents=12500)]),
        user={"tenant_id": A["id"], "role": "owner"})
    assert qa["total_cents"] == 28750, qa["total_cents"]
    assert len(await quotations.listing(user={"tenant_id": A["id"], "role": "owner"})) == 1
    assert len(await quotations.listing(user={"tenant_id": B["id"], "role": "owner"})) == 0
    print("STEP 7b quote total =", qa["total_cents"], "| A sees 1, B sees 0")
    reviewed = await quotations.change_status(qa["id"], quotations.QuoteStatus(
        status="reviewed", version=qa["version"]), user={"tenant_id": A["id"], "role": "owner"})
    try:
        await quotations.change_status(qa["id"], quotations.QuoteStatus(
            status="accepted", version=qa["version"]), user={"tenant_id": A["id"], "role": "owner"})
        raise AssertionError("stale replay must be refused")
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 409
    print("STEP 7b reviewed -> v", reviewed["version"], "; stale replay refused 409")

    # --- step 7: availability in each business's own timezone
    av_a = await booking.availability(A, "2026-11-12")
    av_b = await booking.availability(B, "2026-11-12")
    assert av_a["slots"] and av_b["slots"]
    assert av_a["timezone"] == "Pacific/Auckland" and av_b["timezone"] == "America/Chicago"
    print("STEP 7  A slots =", len(av_a["slots"]), av_a["timezone"],
          "| B slots =", len(av_b["slots"]), av_b["timezone"])

    # --- readiness differs per business
    ra = owner_onboarding.booking_readiness(await tenants.get_by_slug("harbour-dental"))
    rb = owner_onboarding.booking_readiness(await tenants.get_by_slug("southern-plumbing"))
    assert ra["open_days"] == 5 and rb["open_days"] == 5
    await tenants.update("southern-plumbing", {"business_hours": {d: [] for d in ("mon", "tue", "wed", "thu", "fri")}})
    rb2 = owner_onboarding.booking_readiness(await tenants.get_by_slug("southern-plumbing"))
    ra2 = owner_onboarding.booking_readiness(await tenants.get_by_slug("harbour-dental"))
    # `ready` means enabled AND usable, and booking is disabled for both, so ready is False for
    # both. The per-business discriminator is the reason and the open-day count, which must move
    # for B alone.
    assert rb2["open_days"] == 0 and rb2["reason"], rb2
    assert ra2["open_days"] == 5 and ra2["reason"] == "", ra2
    print("READY   emptying B's hours flipped B only: B open_days =", rb2["open_days"],
          "reason set =", bool(rb2["reason"]), "| A open_days =", ra2["open_days"],
          "reason =", repr(ra2["reason"]))

    print()
    print("ALL TWO-BUSINESS END-TO-END CHECKS PASSED")


asyncio.run(main())
