"""Shared real-HTTP/real-DB action executor scenarios for Python and Rust.

Only called by the disposable database owner harness; never starts providers.
"""
import hashlib
import uuid
from concurrent.futures import ThreadPoolExecutor


def verify(py, rs, database, sql, request):
    key = {"x-action-gateway-key": "local-action-test-key-only"}
    tid = sql(database, "SELECT id FROM tenants WHERE slug='alpha'")
    foreign = sql(database, "SELECT id FROM tenants WHERE slug='beta'")
    lid = sql(database, f"INSERT INTO leads(tenant_id,name,email,phone,message) VALUES('{tid}','Ann','ann@example.test','+6421123456','Please quote the service') RETURNING id")
    path = f"/internal/actions/cases/{lid}"
    sql(database, f"UPDATE tenants SET default_country_code='64' WHERE id='{tid}'")
    sql(database, f"INSERT INTO chunks(tenant_id,url,content,embedding) VALUES('{tid}','https://test.invalid/prices','Service is $120.',array_fill(0,ARRAY[384])::vector)")
    sql(database, f"INSERT INTO tenant_channel_authorizations(tenant_id,channel,authorized,actor_id) VALUES('{tid}','email_send',true,gen_random_uuid()),('{tid}','sms_send',true,gen_random_uuid()) ON CONFLICT(tenant_id,channel) DO UPDATE SET authorized=true")

    def call(server, suffix, method="GET", data=None, auth=key):
        return request(server, path + suffix, method=method, data=data, extra_headers=auth)

    invalid_bundles=[{},[],False,{"task_id":"","tenant_id":"bad"},{"task_id":"valid","tenant_id":tid,"actions":[{}]},{"task_id":"valid","tenant_id":tid,"delivery":{"channel":"fax"}},{"task_id":"valid","tenant_id":tid,"unexpected":True}]
    for payload in invalid_bundles:
        a,b=call(py,"/execute","POST",payload),call(rs,"/execute","POST",payload)
        assert a==b,(payload,a,b)
    ctx_path = f"/policy-context?tenant_id={tid}"
    for suffix in (ctx_path, f"/brief?tenant_id={tid}", f"/policy-context?tenant_id={foreign}"):
        a, b = call(py, suffix), call(rs, suffix)
        assert a == b, (suffix, a, b)
    for server in (py, rs):
        assert call(server, ctx_path, auth={})[0] == 401
        assert call(server, ctx_path, auth={"x-action-gateway-key": "wrong"})[0] == 401
        context = call(server, ctx_path)
        assert context[0] == 200 and context[1]["default_country_code"] == "64", context
        assert context[1]["case_contacts"] == ["+6421123456", "ann@example.test"]
        assert "$120" in context[1]["knowledge_evidence"]
        # Each implementation begins with fresh scoped execution state.
        sql(database, f"DELETE FROM case_action_state WHERE lead_id='{lid}'; DELETE FROM case_actions WHERE lead_id='{lid}'; DELETE FROM tasks WHERE lead_id='{lid}'; DELETE FROM email_drafts WHERE tenant_id='{tid}' AND origin='concierge'; UPDATE case_action_settings SET autonomy='shadow' WHERE tenant_id='{tid}'")

        def version():
            result = call(server, ctx_path)
            assert result[0] == 200, result
            return result[1]["case_version"]

        def action(op, identity, params=None, revision=None):
            return {"op": op, "idempotency_key": identity, "dedupe_key": identity,
                    "fingerprint": "fp:" + identity, "case_version": version() if revision is None else revision,
                    "params": params or {}}

        def delivery(identity="email-draft", **overrides):
            return {"channel": "email", "recipient": "ann@example.test", "subject": " Your   quote ",
                    "body": "Service is $120.", "mode": "auto", "fingerprint": "fp:" + identity,
                    "dedupe_key": identity, **overrides}

        def execute(actions=(), reply=None, **overrides):
            return call(server, "/execute", "POST", {"task_id": "action-test", "tenant_id": tid,
                                                       "actions": list(actions), "delivery": reply, **overrides})

        def refusal(response, status, error):
            assert response[0] == status and response[1]["detail"]["error"] == error, response

        refusal(execute([action("schedule_followup", "shadow")]), 409, "shadow_mode")
        sql(database, f"UPDATE case_action_settings SET autonomy='draft_review' WHERE tenant_id='{tid}'")
        assert execute(tenant_id=foreign)[0] == 404
        made = execute(reply=delivery())
        assert made[0] == 200 and made[1]["delivery"]["needs_human_approval"] is True, made
        draft_id = made[1]["delivery"]["draft_id"]
        assert sql(database, f"SELECT subject||':'||status||':'||origin FROM email_drafts WHERE id={draft_id}") == "Your quote:draft:concierge"
        assert execute(reply=delivery())[1]["delivery"]["duplicate"] is True
        refusal(execute(reply=delivery(fingerprint="different")), 409, "key_reuse")
        refusal(execute(reply=delivery("bad-recipient", recipient="attacker@example.test")), 409, "recipient_not_on_case")
        refusal(execute(reply=delivery("shadow-delivery", mode="shadow_only")), 409, "shadow_mode")
        sql(database, f"INSERT INTO opt_outs(tenant_id,contact) VALUES('{tid}','ann@example.test') ON CONFLICT DO NOTHING")
        refusal(execute(reply=delivery("opt-out")), 409, "recipient_opted_out")
        sql(database, f"DELETE FROM opt_outs WHERE tenant_id='{tid}' AND contact='ann@example.test'; UPDATE tenant_channel_authorizations SET authorized=false WHERE tenant_id='{tid}' AND channel='email_send'")
        refusal(execute(reply=delivery("revoked-channel")), 409, "channel_not_authorized")
        sql(database, f"UPDATE tenant_channel_authorizations SET authorized=true WHERE tenant_id='{tid}' AND channel='email_send'")
        sms = execute(reply=delivery("sms-draft", channel="sms", recipient="021123456"))
        assert sms[0] == 200 and sms[1]["delivery"]["state"] == "task_created", sms
        assert sql(database, f"SELECT source FROM tasks WHERE id={sms[1]['delivery']['task_id']}") == "concierge"
        follow = action("schedule_followup", "follow", {"title": "Call Ann", "due_at": "2026-12-01T09:00:00+13:00"})
        first = execute([follow])
        assert first[0] == 200 and first[1]["actions"][0]["state"] == "task_created", first
        assert execute([follow])[1]["actions"][0]["duplicate"] is True
        assert sql(database, f"SELECT count(*) FROM tasks WHERE lead_id='{lid}' AND title='Call Ann'") == "1"
        for date, error in (("tomorrow", "bad_due_at"), ("2026-12-01T09:00:00", "due_at_needs_timezone")):
            refusal(execute([action("schedule_followup", "bad-" + error, {"due_at": date})]), 422, error)
        assert execute([action("request_booking", "booking", {"slot": "2026-12-01T09:00"})])[1]["actions"][0]["state"] == "needs_human"
        assert execute([action("get_case_context", "read"), action("prepare_reply", "reply")])[1]["actions"] == [{"op": "get_case_context", "state": "noop"}, {"op": "prepare_reply", "state": "noop"}]
        refusal(execute([action("run_shell", "unknown")]), 422, "unknown_operation")
        assert execute(untrusted="no")[0] == 422
        refusal(execute([action("schedule_followup", "stale", revision=0)]), 409, "stale_case")
        before = sql(database, f"SELECT (SELECT count(*) FROM tasks WHERE lead_id='{lid}')||':'||(SELECT count(*) FROM case_actions WHERE lead_id='{lid}')")
        refusal(execute([action("schedule_followup", "atomic")], delivery("atomic-delivery", recipient="attacker@example.test")), 409, "recipient_not_on_case")
        after = sql(database, f"SELECT (SELECT count(*) FROM tasks WHERE lead_id='{lid}')||':'||(SELECT count(*) FROM case_actions WHERE lead_id='{lid}')")
        assert before == after, (before, after)
        assert call(server, "/automation", "PUT", {"tenant_id": tid, "paused": True})[0] == 200
        refusal(execute([action("schedule_followup", "paused")]), 409, "automation_paused")
        refusal(execute(reply=delivery("paused-delivery")), 409, "automation_paused")
        escalated = execute([action("escalate_case", "escalate")])
        assert escalated[0] == 200 and escalated[1]["actions"][0]["state"] == "escalated", escalated
        assert call(server, ctx_path)[1]["automation_paused"] is True
        assert call(server, "/automation", "PUT", {"tenant_id": foreign, "paused": True})[0] == 404
        assert call(server, "/automation", "PUT", {"tenant_id": tid, "paused": False})[0] == 200
        # Simultaneous repeats have one durable effect, independent of the Rust
        # gateway's process-local ledger. This remains safe after gateway restart.
        repeated = action("schedule_followup", "concurrent", {"title": "Exactly once"})
        with ThreadPoolExecutor(max_workers=4) as executor:
            replies = list(executor.map(lambda _: execute([repeated]), range(4)))
        assert all(r[0] == 200 for r in replies), replies
        assert sum(not r[1]["actions"][0].get("duplicate", False) for r in replies) == 1
        assert sql(database, f"SELECT count(*) FROM tasks WHERE lead_id='{lid}' AND title='Exactly once'") == "1"
        assert sql(database, "SELECT count(*) FROM outbox") == "0"
        assert sql(database, "SELECT count(*) FROM email_drafts WHERE status<>'draft'") == "0"
    print("PASS: Python/Rust action context, draft-only delivery, consent/recipient/tenant checks, stale plans, takeover, transaction rollback and concurrent durable idempotency")
