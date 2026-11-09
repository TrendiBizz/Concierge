"""Isolated end-to-end tests of the Hermes gateway operations. Requires disposable Postgres at 127.0.0.1:55432.

Never contacts providers, never queues an outbound message: replies become human-reviewed drafts or to-dos.
"""
import json
import os
from pathlib import Path
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

os.environ.update({
    "DATABASE_URL": "postgresql://postgres:test@127.0.0.1:55432/postgres",
    "OUTBOX_ENABLED": "false",
    "ADMIN_TOKEN": "test-admin-only",
    "HERMES_GATEWAY_ENABLED": "true",
    "HERMES_GATEWAY_KEY": "gateway-key-for-tests-only-0123456789",
    "DEFAULT_COUNTRY_CODE": "64",
})
from fastapi.testclient import TestClient  # noqa: E402
from app import db, hermes_ops  # noqa: E402
from app.main import app  # noqa: E402

KEY = {"x-hermes-gateway-key": "gateway-key-for-tests-only-0123456789"}
n = 0


def check(label, condition):
    global n
    assert condition, label
    n += 1
    print("PASS", label)


with TestClient(app) as client:
    run = client.portal.call
    pool = db.pool()

    async def seed():
        a = await pool.fetchval("INSERT INTO tenants (slug,name,public_key,timezone) VALUES ('alpha','Alpha','pk_a','Pacific/Auckland') RETURNING id")
        b = await pool.fetchval("INSERT INTO tenants (slug,name,public_key) VALUES ('beta','Beta','pk_b') RETURNING id")
        conv = await pool.fetchval("INSERT INTO conversations (tenant_id,session_id,channel) VALUES ($1,'sess-1','chat') RETURNING id", a)
        await pool.execute("INSERT INTO messages (conversation_id,role,content) VALUES ($1,'user','Can you quote me for a service?')", conv)
        lead = await pool.fetchval(
            "INSERT INTO leads (tenant_id,conversation_id,name,email,phone,message) VALUES ($1,$2,'Ann','ann@example.com','+64 21 123 456','Can you quote me?') RETURNING id", a, conv)
        blead = await pool.fetchval("INSERT INTO leads (tenant_id,name,email,message) VALUES ($1,'Bob','bob@example.com','hi') RETURNING id", b)
        dim = await pool.fetchval("SELECT atttypmod FROM pg_attribute WHERE attrelid='chunks'::regclass AND attname='embedding'")
        await pool.execute("INSERT INTO chunks (tenant_id,url,title,content,embedding) VALUES ($1,'https://x.test/p','Prices','Standard service is $120.',array_fill(0,ARRAY[$2::int])::vector)", a, dim)
        actor = await pool.fetchval("SELECT gen_random_uuid()")
        for ch in ("email_send", "sms_send"):
            await pool.execute("INSERT INTO tenant_channel_authorizations (tenant_id,channel,authorized,actor_id) VALUES ($1,$2,true,$3)", a, ch, actor)
        return a, b, lead, blead

    alpha, beta, lead, blead = run(seed)
    ctx_url = f"/internal/hermes/cases/{lead}/policy-context"
    exec_url = f"/internal/hermes/cases/{lead}/execute"

    def context():
        r = client.get(ctx_url, params={"tenant_id": str(alpha)}, headers=KEY)
        assert r.status_code == 200, r.text
        return r.json()

    def action(op, key, version, params=None):
        return {"op": op, "idempotency_key": key, "dedupe_key": f"hermes:{alpha}:{lead}:{key}", "fingerprint": f"fp-{op}-{key}", "case_version": version, "params": params or {}}

    def delivery(channel="email", recipient="ann@example.com", body="Standard service is $120.", key="task-1:email", fp="fp-d1", mode="needs_approval"):
        return {"channel": channel, "recipient": recipient, "subject": "Your quote", "body": body, "mode": mode, "fingerprint": fp, "dedupe_key": key, "send_at": ""}

    def post(bundle, **kw):
        return client.post(exec_url, headers=KEY, json={"task_id": "task-1", "tenant_id": str(alpha), **bundle}, **kw)

    def count(sql, *a):
        return run(lambda: pool.fetchval(sql, *a))

    # ---- dark by default, authentication -------------------------------------------------------------------------------
    with patch.object(hermes_ops, "get_settings", lambda: SimpleNamespace(hermes_gateway_enabled=False, hermes_gateway_key="k" * 30)):
        r = client.get(ctx_url, params={"tenant_id": str(alpha)}, headers={"x-hermes-gateway-key": "k" * 30})
        check("disabled: the routes do not exist, even with the right key", r.status_code == 404)
    with patch.object(hermes_ops, "get_settings", lambda: SimpleNamespace(hermes_gateway_enabled=True, hermes_gateway_key="")):
        check("enabled without a key configured: still 404", client.get(ctx_url, params={"tenant_id": str(alpha)}, headers=KEY).status_code == 404)
    check("missing key is refused", client.get(ctx_url, params={"tenant_id": str(alpha)}).status_code == 401)
    check("wrong key is refused", client.get(ctx_url, params={"tenant_id": str(alpha)}, headers={"x-hermes-gateway-key": "nope"}).status_code == 401)

    # ---- policy context: server-derived, tenant-scoped ----------------------------------------------------------------
    c = context()
    check("context names the case's own contacts", set(c["case_contacts"]) == {"ann@example.com", "+6421123456"})
    check("channels authorized by the business", c["email_send_authorized"] and c["sms_send_authorized"])
    check("price evidence comes from business content", "$120" in c["knowledge_evidence"])
    check("defaults to shadow, not paused", c["autonomy"] == "shadow" and c["automation_paused"] is False and c["timezone"] == "Pacific/Auckland")
    check("case version is a millisecond clock", isinstance(c["case_version"], int) and c["case_version"] > 1_700_000_000_000)
    r = client.get(f"/internal/hermes/cases/{blead}/policy-context", params={"tenant_id": str(alpha)}, headers=KEY)
    check("another tenant's case is not found", r.status_code == 404)
    r = client.get(ctx_url, params={"tenant_id": str(beta)}, headers=KEY)
    check("a case is not visible through another tenant", r.status_code == 404)

    r = client.get(f"/internal/hermes/cases/{lead}/brief", params={"tenant_id": str(alpha)}, headers=KEY)
    check("the brief carries the case text and conversation, bounded", r.status_code == 200 and r.json()["lead"]["message"] == "Can you quote me?" and r.json()["messages"][0]["role"] == "user")
    check("the brief names the business, not its credentials", r.json()["business"]["name"] == "Alpha" and "key" not in json.dumps(r.json()).lower())
    check("another tenant's case has no brief", client.get(f"/internal/hermes/cases/{blead}/brief", params={"tenant_id": str(alpha)}, headers=KEY).status_code == 404)

    # ---- shadow mode executes nothing ---------------------------------------------------------------------------------
    v = c["case_version"]
    r = post({"actions": [action("schedule_followup", "k-shadow", v)], "delivery": delivery()})
    check("shadow mode refuses to execute", r.status_code == 409 and r.json()["detail"]["error"] == "shadow_mode")
    check("shadow mode left no trace", count("SELECT count(*) FROM hermes_actions") == 0 and count("SELECT count(*) FROM email_drafts") == 0)

    run(lambda: pool.execute("INSERT INTO hermes_tenant_settings (tenant_id, autonomy) VALUES ($1,'draft_review')", alpha))

    # ---- delivery becomes a human-reviewed draft, idempotently ---------------------------------------------------------
    r = post({"delivery": delivery()})
    check("email delivery becomes a draft", r.status_code == 200 and r.json()["delivery"]["state"] == "draft_created" and r.json()["delivery"]["needs_human_approval"])
    draft_id = r.json()["delivery"]["draft_id"]
    r = post({"delivery": delivery()})
    check("the same delivery again is a duplicate, not a second draft", r.json()["delivery"]["duplicate"] is True and r.json()["delivery"]["draft_id"] == draft_id)
    check("exactly one draft exists", count("SELECT count(*) FROM email_drafts") == 1)
    check("the draft is awaiting a human", count("SELECT status FROM email_drafts WHERE id=$1", draft_id) == "draft")
    r = post({"delivery": delivery(fp="a-different-fingerprint")})
    check("a reused key with different content is a conflict", r.status_code == 409 and r.json()["detail"]["error"] == "key_reuse")
    r = post({"delivery": delivery(mode="auto", key="task-2:email", fp="fp-d2", body="Hello Ann")})
    check("'auto' still only drafts (no auto-send exists)", r.json()["delivery"]["state"] == "draft_created" and r.json()["delivery"]["needs_human_approval"])
    r = post({"delivery": delivery(mode="shadow_only", key="task-3:email", fp="fp-d3")})
    check("a shadow-only delivery cannot execute", r.status_code == 409)

    # ---- recipients, consent, channels ---------------------------------------------------------------------------------
    r = post({"delivery": delivery(recipient="attacker@evil.test", key="task-4:email", fp="fp-d4")})
    check("a recipient outside the case is refused", r.status_code == 409 and r.json()["detail"]["error"] == "recipient_not_on_case")
    run(lambda: pool.execute("INSERT INTO opt_outs (tenant_id, contact) VALUES ($1,'ann@example.com')", alpha))
    r = post({"delivery": delivery(key="task-5:email", fp="fp-d5")})
    check("an opted-out recipient is refused at execution", r.status_code == 409 and r.json()["detail"]["error"] == "recipient_opted_out")
    run(lambda: pool.execute("DELETE FROM opt_outs WHERE tenant_id=$1", alpha))
    run(lambda: pool.execute("UPDATE tenant_channel_authorizations SET authorized=false WHERE tenant_id=$1 AND channel='email_send'", alpha))
    r = post({"delivery": delivery(key="task-6:email", fp="fp-d6")})
    check("a revoked channel is refused at execution", r.status_code == 409 and r.json()["detail"]["error"] == "channel_not_authorized")
    run(lambda: pool.execute("UPDATE tenant_channel_authorizations SET authorized=true WHERE tenant_id=$1 AND channel='email_send'", alpha))
    r = post({"delivery": delivery(channel="sms", recipient="+64 21 123 456", body="We open at 9am.", key="task-7:sms", fp="fp-d7")})
    check("an SMS reply becomes a to-do for the owner, never a send", r.status_code == 200 and r.json()["delivery"]["state"] == "task_created")

    # ---- actions: follow-ups, escalation, unsupported, read-only -------------------------------------------------------
    v = context()["case_version"]
    due = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    r = post({"actions": [action("schedule_followup", "k-f1", v, {"title": "Call Ann", "due_at": due})]})
    check("a follow-up becomes a to-do with its due date", r.status_code == 200 and r.json()["actions"][0]["state"] == "task_created")
    check("the to-do is attributed to Hermes", count("SELECT source FROM tasks WHERE id=$1", r.json()["actions"][0]["task_id"]) == "hermes")
    r = post({"actions": [action("schedule_followup", "k-f1", v, {"title": "Call Ann", "due_at": due})]})
    check("the same follow-up again is a duplicate", r.json()["actions"][0]["duplicate"] is True and count("SELECT count(*) FROM tasks WHERE source='hermes' AND title='Call Ann'") == 1)
    check("a due date without a timezone is refused", post({"actions": [action("schedule_followup", "k-f2", v, {"due_at": "2026-12-01T09:00:00"})]}).status_code == 422)
    check("an unreadable due date is refused", post({"actions": [action("schedule_followup", "k-f3", v, {"due_at": "tomorrow"})]}).status_code == 422)
    r = post({"actions": [action("request_booking", "k-b1", v, {"slot": "2026-11-12T10:00"})]})
    check("a booking request is handed to a person (no executor yet)", r.json()["actions"][0]["state"] == "needs_human")
    r = post({"actions": [action("get_case_context", "k-r1", v), action("prepare_reply", "k-r2", v)]})
    check("read-only and reply-preparation ops do nothing on their own", [x["state"] for x in r.json()["actions"]] == ["noop", "noop"])
    check("an operation outside the list is refused", post({"actions": [action("run_shell", "k-x", v)]}).status_code == 422)
    check("unknown fields are refused", client.post(exec_url, headers=KEY, json={"task_id": "t", "tenant_id": str(alpha), "actions": [], "tenant": "evil"}).status_code == 422)

    # ---- stale plans ---------------------------------------------------------------------------------------------------
    old = context()["case_version"]
    run(lambda: pool.execute("UPDATE leads SET updated_at = now() + interval '5 seconds' WHERE id=$1", lead))
    check("a customer-visible change moves the case version", context()["case_version"] > old)
    r = post({"actions": [action("schedule_followup", "k-stale", old, {"title": "stale"})]})
    check("a plan made against an older version is refused", r.status_code == 409 and r.json()["detail"]["error"] == "stale_case")

    # ---- atomicity -------------------------------------------------------------------------------------------------------
    v = context()["case_version"]
    before = (count("SELECT count(*) FROM tasks"), count("SELECT count(*) FROM hermes_actions"))
    r = post({"actions": [action("schedule_followup", "k-atomic", v, {"title": "should not exist"})], "delivery": delivery(recipient="attacker@evil.test", key="task-8:email", fp="fp-d8")})
    check("one bad part refuses the whole bundle", r.status_code == 409)
    check("nothing from a refused bundle was written", (count("SELECT count(*) FROM tasks"), count("SELECT count(*) FROM hermes_actions")) == before)

    # ---- human takeover --------------------------------------------------------------------------------------------------
    r = client.put(f"/internal/hermes/cases/{lead}/automation", headers=KEY, json={"tenant_id": str(alpha), "paused": True})
    check("a person can take over a case", r.status_code == 200 and r.json()["automation_paused"] is True)
    c = context()
    check("takeover shows in the policy context and moves the version", c["automation_paused"] is True and c["case_version"] >= v)
    v = c["case_version"]
    r = post({"actions": [action("schedule_followup", "k-p1", v, {"title": "x"})]})
    check("takeover blocks customer-affecting actions", r.status_code == 409 and r.json()["detail"]["error"] == "automation_paused")
    r = post({"delivery": delivery(key="task-9:email", fp="fp-d9")})
    check("takeover blocks deliveries", r.status_code == 409 and r.json()["detail"]["error"] == "automation_paused")
    r = post({"actions": [action("escalate_case", "k-e1", v, {"reason": "customer asked for a person"})]})
    check("escalation is still allowed under takeover", r.status_code == 200 and r.json()["actions"][0]["state"] == "escalated")
    check("escalation stays paused", context()["automation_paused"] is True)
    r = client.put(f"/internal/hermes/cases/{blead}/automation", headers=KEY, json={"tenant_id": str(alpha), "paused": True})
    check("takeover cannot target another tenant's case", r.status_code == 404)
    client.put(f"/internal/hermes/cases/{lead}/automation", headers=KEY, json={"tenant_id": str(alpha), "paused": False})
    check("takeover can be released", context()["automation_paused"] is False)

    # ---- wire contract with the Rust gateway ---------------------------------------------------------------------------
    # The gateway's own tests pin this exact JSON; posting it here proves the two sides still agree. Only ids and the
    # case version (which depend on this database) are substituted.
    fixture = json.loads((Path(__file__).resolve().parents[2] / "concierge-stack/hermes-gateway/tests/fixtures/execute_bundle.json").read_text())
    fixture["tenant_id"] = str(alpha)
    for a in fixture["actions"]:
        a["case_version"] = context()["case_version"]
    r = client.post(exec_url, headers=KEY, json=fixture)
    check("the gateway's pinned bundle is accepted by the real endpoint", r.status_code == 200 and r.json()["delivery"]["state"] == "draft_created", )
    check("its follow-up and draft really exist", r.json()["actions"][0]["state"] == "task_created" and r.json()["delivery"]["needs_human_approval"] is True)
    check("the same pinned bundle again is a pure duplicate", client.post(exec_url, headers=KEY, json=fixture).json()["delivery"]["duplicate"] is True)

    # ---- the invariant that matters most ----------------------------------------------------------------------------------
    check("nothing was ever queued for sending", count("SELECT count(*) FROM outbox") == 0)
    check("no draft was approved by anything but a human", count("SELECT count(*) FROM email_drafts WHERE status <> 'draft'") == 0)

print(f"{n}/{n} hermes ops checks passed")
