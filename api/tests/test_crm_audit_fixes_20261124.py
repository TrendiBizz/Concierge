"""Regression tests for the 24 Nov 2026 deep CRM audit fixes (QA/verification/CRM_AUDIT_FIXES_2026-11-24.md)."""
from __future__ import annotations

import asyncio
import os
import pathlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import asyncpg
import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app import (
    calendar_connection,
    casetimeline,
    contact,
    db,
    email_secretary,
    enquiries,
    ical,
    integrations,
    missed_calls,
    owner_auth,
    owner_issues,
    owner_notifications,
    portability,
    site_enquiry,
    tenants,
)
from app.main import app
from app.social import publishers

DSN = os.environ.get("TEST_DATABASE_URL")
needs_db = pytest.mark.skipif(not DSN, reason="needs TEST_DATABASE_URL (a real Postgres)")
REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SCHEMA = (REPO_ROOT / "api" / "app" / "schema.sql").read_text()


async def _fresh_pool():
    pool = await asyncpg.create_pool(DSN, min_size=1, max_size=4)
    async with pool.acquire() as conn:
        await conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await conn.execute(SCHEMA.replace("__DIM__", "384"))
    db._pool = pool
    return pool


def run(fn):
    async def wrapper():
        pool = await _fresh_pool()
        try:
            await fn(pool)
        finally:
            await pool.close()
            db._pool = None
    asyncio.run(wrapper())


def test_timezone_country_code_inference_and_national_normalization():
    assert casetimeline.tenant_country_code({"timezone": "Pacific/Auckland"}) == "64"
    assert casetimeline.tenant_country_code({"timezone": "Australia/Sydney"}) == "61"
    assert casetimeline.tenant_country_code({"timezone": "Europe/London"}) == "44"
    assert casetimeline.tenant_country_code({"timezone": "America/New_York"}) == "1"
    assert contact.normalize_phone("021 123 4567", casetimeline.tenant_country_code({"timezone": "Pacific/Auckland"})) == "+64211234567"


@needs_db
def test_sms_unconfirmable_matches_all_receipt_timeout_variants_and_studio_link(monkeypatch):
    async def go(pool):
        t = await tenants.create("SMS Co", "https://smsco.example", "sms-co")
        for err in ("Android gateway never confirmed delivery", "gateway did not confirm within 15m", "delivery receipt missing"):
            await pool.execute(
                "INSERT INTO outbox(tenant_id, channel, kind, to_addr, body, status, last_error) "
                "VALUES($1,'sms','owner_alert','+64210000001','hi','failed',$2)",
                t["id"], err,
            )
        assert await owner_notifications.sms_unconfirmable(pool, t["id"]) is True

        monkeypatch.setattr(owner_notifications, "get_settings", lambda: SimpleNamespace(public_base_url="https://portal.example"))
        body = owner_notifications.sms_body("Voice enquiry", "x" * 2000)
        assert "https://portal.example/studio/" in body
        assert "/owner-ui" not in body
    run(go)


def test_missed_calls_skips_voicemail_calls():
    action, reason = missed_calls.decide(
        tenant={"missed_call_textback": True, "sms_enabled": True},
        call={"status": "voicemail", "from_number": "+64211112222", "to_number": "+6490000000"},
        caller_turns=0,
        has_appointment=False,
        recovered_recently=False,
        sms_authorized=True,
    )
    assert action == "skip" and reason == "voicemail_left"


@needs_db
def test_email_secretary_reply_and_reply_failed_sweep_without_lead_id(monkeypatch):
    async def go(pool):
        import hashlib
        from app import channel_authorization, chat as chat_mod
        t = await tenants.create("Mail Co", "https://mailco.example", "mail-co")
        await pool.execute(
            "UPDATE tenants SET notify_email='owner@mailco.example', notify_phone='+64211110000', email_auto_reply=true WHERE id=$1",
            t["id"],
        )
        async def always_auth(*a, **k):
            return True
        monkeypatch.setattr(channel_authorization, "is_authorized", always_auth)
        src_key = "msg-42@example.com"
        src_hash = hashlib.sha256(src_key.encode()).hexdigest()
        lead_id = await pool.fetchval(
            "INSERT INTO leads(tenant_id, name, email, channel, source_key) VALUES($1,'Pat','pat@example.com','email',$2) RETURNING id",
            t["id"], src_hash,
        )
        await pool.execute(
            "INSERT INTO email_drafts(tenant_id, source_id, sender, subject, inbound_body, reply_body, status) "
            "VALUES($1,$2,'pat@example.com','Quote question','Need quote','Draft','draft')",
            t["id"], src_key,
        )
        await pool.execute(
            "INSERT INTO email_secretary_jobs(tenant_id, source_key, sender, subject, body, status) "
            "VALUES($1,$2,'pat@example.com','Quote question','Need quote','pending')",
            t["id"], src_key,
        )
        async def fake_turn(*a, **k):
            return {"reply": "Thanks Pat, we can quote that today."}
        monkeypatch.setattr(chat_mod, "run_turn", fake_turn)
        await email_secretary.process_once()

        row = await pool.fetchrow(
            "SELECT kind, lead_id FROM outbox WHERE tenant_id=$1 AND kind='email_secretary_reply'",
            t["id"],
        )
        assert row is not None
        assert str(row["lead_id"]) == str(lead_id)

        # Failed customer reply with NULL lead_id (e.g. approved_reply or enquirer_ack) must still alert owner.
        await pool.execute(
            "INSERT INTO outbox(tenant_id, channel, kind, to_addr, body, status, last_error, created_at) "
            "VALUES($1,'email','approved_reply','orphan@example.com','Hi','failed','SMTP 550', now() - interval '5 minutes')",
            t["id"],
        )
        opened = await owner_issues.sweep_reply_failed()
        assert opened == 1
        notice = await pool.fetchrow(
            "SELECT subject, body FROM outbox WHERE tenant_id=$1 AND kind='owner_issue'",
            t["id"],
        )
        assert notice is not None
        assert "orphan@example.com" in notice["body"]
        assert "/studio/" in notice["body"]
    run(go)


@needs_db
def test_enquiries_capture_persists_attribution_and_backfills_contact_and_rescores():
    async def go(pool):
        t = await tenants.create("Attr Co", "https://attr.example", "attr-co")
        await pool.execute("UPDATE tenants SET timezone='Pacific/Auckland' WHERE id=$1", t["id"])
        t = dict(await pool.fetchrow("SELECT * FROM tenants WHERE id=$1", t["id"]))
        res1 = await enquiries.capture(
            t, "chat", "conv-1", "Hi, do you do urgent repairs?",
            page_url="https://attr.example/repairs", utm={"utm_source": "google"},
            automated=True,
        )
        lead1 = await pool.fetchrow("SELECT * FROM leads WHERE id=$1", res1["id"])
        assert lead1["page_url"] == "https://attr.example/repairs"
        assert lead1["phone"] == ""

        # Turn 2 supplies phone & email — must backfill and re-score upwards.
        res2 = await enquiries.capture(
            t, "chat", "conv-1", "My number is 0215551234, please call asap",
            name="Jordan", email="jordan@example.com", phone="0215551234",
            consent_contact=True, automated=True,
        )
        assert str(res2["id"]) == str(res1["id"])
        lead2 = await pool.fetchrow("SELECT * FROM leads WHERE id=$1", res1["id"])
        assert lead2["name"] == "Jordan"
        assert lead2["email"] == "jordan@example.com"
        assert lead2["phone"] == "+64215551234"
        assert lead2["consent_contact"] is True
        assert lead2["score"] > lead1["score"]
    run(go)


@needs_db
def test_owner_appointments_crud_timeline_webhook_test_and_ical_rotation(monkeypatch):
    async def go(pool):
        t = await tenants.create("Book Co", "https://bookco.example", "book-co")
        await pool.execute(
            "UPDATE tenants SET notify_email='owner@bookco.example', timezone='Pacific/Auckland' WHERE id=$1",
            t["id"],
        )
        inv = await owner_auth.make_invite(t["id"], "owner@bookco.test", "owner", "invite")
        sess = await owner_auth.accept_invite(inv)
        headers = {"Authorization": f"Bearer {sess['access_token']}"}

        emitted = []
        async def spy_emit(tid, ev, payload):
            emitted.append((ev, payload))
        monkeypatch.setattr(portability, "emit", spy_emit)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # 1. Create appointment manually via POST /owner/appointments
            start = (datetime.now(timezone.utc) + timedelta(days=3)).replace(second=0, microsecond=0)
            r = await client.post("/owner/appointments", headers=headers, json={
                "name": "Alex", "email": "alex@example.com", "phone": "021 777 8888",
                "starts_at": start.isoformat(), "notes": "Site inspection",
            })
            assert r.status_code == 201, r.text
            appt = r.json()
            assert appt["status"] == "booked"
            assert any(ev == "appointment.booked" for ev, _ in emitted)

            # Conflict check on overlapping slot
            r_dup = await client.post("/owner/appointments", headers=headers, json={
                "name": "Other", "starts_at": start.isoformat(),
            })
            assert r_dup.status_code == 409

            # 2. Verify /owner/crm includes currency and starts_at
            crm = (await client.get("/owner/crm", headers=headers)).json()
            assert crm["currency"] == "NZD"
            assert crm["appointments"][0]["starts_at"]

            # 3. Verify contact timeline includes primary_phone/email/assigned_to/company_id
            contacts = (await client.get("/owner/contacts", headers=headers)).json()["contacts"]
            assert contacts
            tl = (await client.get(f"/owner/contacts/{contacts[0]['case_key']}/timeline", headers=headers)).json()
            assert tl["primary_email"] == "alex@example.com"
            assert tl["primary_phone"] == "+64217778888"
            assert "assigned_to" in tl and "company_id" in tl

            # 4. Update appointment status via PATCH /owner/appointments/{id}
            p = await client.patch(f"/owner/appointments/{appt['id']}", headers=headers, json={"status": "no_show"})
            assert p.status_code == 200 and p.json()["status"] == "no_show"
            assert any(ev == "appointment.no_show" for ev, _ in emitted)

            # ICS feed emits STATUS:CANCELLED for no_show & includes X-WR-TIMEZONE
            feed = ical.build(
                dict(await pool.fetchrow("SELECT * FROM tenants WHERE id=$1", t["id"])),
                [dict(await pool.fetchrow("SELECT * FROM appointments WHERE id=$1", appt["id"]))],
            )
            assert "X-WR-TIMEZONE:Pacific/Auckland" in feed
            assert "STATUS:CANCELLED" in feed

            # 5. Rotate ICS calendar feed token
            old_tok = await pool.fetchval("SELECT calendar_token FROM tenants WHERE id=$1", t["id"])
            rot = await client.post("/owner/calendar/rotate-token", headers=headers)
            new_tok = await pool.fetchval("SELECT calendar_token FROM tenants WHERE id=$1", t["id"])
            assert rot.status_code == 200 and new_tok != old_tok and new_tok in rot.json()["calendar_url"]

            # 6. Lead stage history endpoint
            lead_r = await client.post("/owner/crm/leads", headers=headers, json={
                "name": "Casey", "email": "casey@example.com", "phone": "021 999 0000", "message": "Need a quote",
            })
            assert lead_r.status_code == 201
            lead_id = lead_r.json()["id"]
            await client.patch(f"/owner/crm/leads/{lead_id}", headers=headers, json={"status": "contacted"})
            hist = (await client.get(f"/owner/crm/leads/{lead_id}/events", headers=headers)).json()
            assert any(e["to_status"] == "contacted" for e in hist["events"])

            # 7. Webhook events listing
            ev_res = await client.get("/owner/webhooks/events", headers=headers)
            assert ev_res.status_code == 200 and "events" in ev_res.json()
    run(go)


@needs_db
def test_google_calendar_sync_patches_rescheduled_events(monkeypatch):
    async def go(pool):
        t = await tenants.create("GCal Co", "https://gcal.example", "gcal-co")
        t0 = datetime.now(timezone.utc) + timedelta(days=2)
        t1 = t0 + timedelta(minutes=30)
        appt_id = await pool.fetchval(
            "INSERT INTO appointments(tenant_id, name, email, starts_at, ends_at, status, consent_contact, calendar_sync_requested, calendar_state) "
            "VALUES($1,'Sam','sam@example.com',$2,$3,'booked',true,true,'pending') RETURNING id",
            t["id"], t0, t1,
        )
        await pool.execute(
            "INSERT INTO calendar_connections(tenant_id, calendar_id, enabled) VALUES($1,'primary',true)",
            t["id"],
        )
        async def fake_conn(tid):
            return {"calendar_id": "primary", "enabled": True}
        monkeypatch.setattr(calendar_connection, "connection", fake_conn)
        calls = []
        moved_start = t0 + timedelta(hours=2)
        moved_end = moved_start + timedelta(minutes=30)
        await pool.execute("UPDATE appointments SET starts_at=$2, ends_at=$3 WHERE id=$1", appt_id, moved_start, moved_end)

        async def fake_request(tenant_id, method, path, **kwargs):
            calls.append((method, path, kwargs.get("json")))
            if method == "GET":
                return httpx.Response(200, json={
                    "id": "evt-99",
                    "status": "confirmed",
                    "start": {"dateTime": t0.isoformat()},
                    "end": {"dateTime": t1.isoformat()},
                    "attendees": [{"email": "sam@example.com"}],
                    "extendedProperties": {"private": {"concierge_appointment": str(appt_id), "concierge_tenant": str(t["id"])}},
                })
            return httpx.Response(200, json={
                "id": "evt-99",
                "status": "confirmed",
                "start": {"dateTime": moved_start.isoformat()},
                "end": {"dateTime": moved_end.isoformat()},
                "attendees": [{"email": "sam@example.com"}],
                "extendedProperties": {"private": {"concierge_appointment": str(appt_id), "concierge_tenant": str(t["id"])}},
            })

        monkeypatch.setattr(calendar_connection, "request", fake_request)
        await calendar_connection.sync_one(appt_id)
        assert await pool.fetchval("SELECT calendar_state FROM appointments WHERE id=$1", appt_id) == "synced"
        assert any(m == "PATCH" for m, _, _ in calls)
    run(go)


@needs_db
def test_servicem8_skips_blank_turn1_greeting_and_sends_mobile_phone(monkeypatch):
    async def go(pool):
        t = await tenants.create("SM8 Co", "https://sm8.example", "sm8-co")
        await integrations._save(t["id"], "servicem8", {"api_key": "k" * 16})
        sent = []

        import json as _json
        async def fake_http(method, url, **kw):
            raw = kw.get("content")
            body = _json.loads(raw) if isinstance(raw, (str, bytes)) else (kw.get("json") or {})
            sent.append((url, body))
            return httpx.Response(200, headers={"x-record-uuid": f"U{len(sent)}"}, json={})

        monkeypatch.setattr(integrations, "http", fake_http)
        # Blank turn-1 greeting with no contact details must be skipped
        await integrations.dispatch(t["id"], "customer.enquiry", {
            "lead_id": "L-blank", "case_key": "k-blank", "channel": "chat", "message": "hi",
        })
        assert sent == []

        # Enquiry with phone creates company with mobile + job
        await integrations.dispatch(t["id"], "customer.enquiry", {
            "lead_id": "L-real", "case_key": "k-real", "name": "Taylor",
            "phone": "+64215556666", "channel": "phone", "message": "Need roof repair",
        })
        assert any("company.json" in u and body.get("mobile") == "+64215556666" for u, body in sent)
        assert any("job.json" in u for u, _ in sent)
    run(go)


def test_social_video_publishers_use_video_and_reels_endpoints(monkeypatch):
    async def go():
        calls = []

        async def fake_req(method, url, **kw):
            calls.append((method, url, kw.get("data")))
            if url.endswith("/videos"):
                return 200, {"id": "fb-vid-1"}, 0
            if url.endswith("/media"):
                return 200, {"id": "ig-cont-1"}, 0
            if "fields=status_code" in url:
                return 200, {"status_code": "FINISHED"}, 0
            if url.endswith("/media_publish"):
                return 200, {"id": "ig-reel-1"}, 0
            return 200, {"id": "ok"}, 0

        monkeypatch.setattr(publishers, "_request_with_retry", fake_req)
        fb = await publishers._publish_facebook("123", "tok", "Check this clip", "", "https://cdn.example/demo.mp4", dry_run=False)
        assert fb.ok and fb.external_post_id == "fb-vid-1"
        assert any(u.endswith("/123/videos") and d.get("file_url") == "https://cdn.example/demo.mp4" for m, u, d in calls if m == "POST")

        ig = await publishers._publish_instagram("456", "tok", "New reel", "https://cdn.example/reel.mp4", dry_run=False)
        assert ig.ok and ig.external_post_id == "ig-reel-1"
        assert any(u.endswith("/456/media") and d.get("media_type") == "REELS" and d.get("video_url") == "https://cdn.example/reel.mp4" for m, u, d in calls if m == "POST")
    asyncio.run(go())


@needs_db
def test_site_enquiry_captures_into_trendi_support_crm():
    async def go(pool):
        t = await tenants.create("Trendi Support", "https://trendibizz.com", "trendi-support")
        await pool.execute("UPDATE tenants SET notify_email='admin@trendibizz.com' WHERE id=$1", t["id"])
        res = await site_enquiry.submit(
            kind="concierge", name="Morgan", email="morgan@example.com",
            website="https://clinic.example", message="Interested in Concierge for our clinic",
            ip="203.0.113.42", user_agent="pytest",
        )
        assert res["ok"] is True
        lead = await pool.fetchrow("SELECT * FROM leads WHERE tenant_id=$1 AND email='morgan@example.com'", t["id"])
        assert lead is not None
        assert "clinic" in (lead["message"] or "")
        outbox_row = await pool.fetchrow("SELECT dedupe_key, lead_id FROM outbox WHERE kind='owner_alert' AND dedupe_key LIKE 'site-enquiry:%'")
        assert outbox_row is not None
        assert str(outbox_row["lead_id"]) == str(lead["id"])
    run(go)
