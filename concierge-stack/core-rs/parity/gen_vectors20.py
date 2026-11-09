"""Batch-20 golden vectors: the outbox worker (`outbox.process_once` and its delivery decisions) from the live module, with a fake database,
scripted collaborators and a fixed clock. No message is sent: every sender is a recording fake.

    cd api && PYTHONPATH=../QA/verification/shims:. python ../concierge-stack/core-rs/parity/gen_vectors20.py > ../concierge-stack/core-rs/parity/vectors20.json
"""
import asyncio
import json
import random
import sys
from datetime import datetime, timezone
from types import SimpleNamespace

sys.path.insert(0, ".")
from app import channel_authorization, db, device_sms, mailer, outbox, sms, tenants, unsub  # noqa: E402

rng = random.Random(20261127)
UTC = timezone.utc
CUR = {}


class FixedDT(datetime):
    @classmethod
    def now(cls, tz=None):
        d = datetime.fromtimestamp(CUR["now"], UTC)
        return d.astimezone(tz) if tz else d.replace(tzinfo=None)


outbox.datetime = FixedDT
KINDS = ["owner_alert", "booking_confirmation", "campaign", "approved_reply", "email_secretary_reply", "enquirer_ack", "review_request"]
CHANNELS = ["sms", "email", "sms", "email", "fax", ""]
TZS = ["Pacific/Auckland", "UTC", "America/New_York", "Asia/Kolkata"]
cases = []
for case in range(700):
    CUR["now"] = int(datetime(2026, rng.randint(1, 12), rng.randint(1, 28), 0, 0, tzinfo=UTC).timestamp()) + rng.randint(0, 86399)
    n_rows = rng.choice([0, 1, 1, 2, 3])
    rows = []
    for i in range(n_rows):
        rows.append({"id": 100 * case + i, "tenant_id": "t-1", "kind": rng.choice(KINDS), "channel": rng.choice(CHANNELS), "to_addr": rng.choice(["+64211234567", "a@b.co", "x"]),
                     "subject": rng.choice(["", "Hello"]), "body": "body", "campaign_id": rng.choice([None, None, 7]), "attempts": rng.choice([1, 1, 2, 3])})
    tenant = rng.choice([None, {"id": "t-1", "name": "Acme", "timezone": rng.choice(TZS), "sms_from": rng.choice([None, "+1"]), "email_auto_reply": rng.choice([True, False]),
                                "campaigns_enabled": rng.choice([True, False])}] + [{"id": "t-1", "name": "Acme", "timezone": rng.choice(TZS), "sms_from": "+1", "email_auto_reply": True,
                                                                                      "campaigns_enabled": True}] * 4)
    cfg = SimpleNamespace(sms_quiet_start_hour=rng.choice([8, 8, 9]), sms_quiet_end_hour=rng.choice([21, 21, 20]), email_configured=rng.choice([True, True, False]), outbox_poll_seconds=20)
    script = {"auth": {p: rng.choice([True, True, True, False]) for p in ["email_send", "sms_send", "email_read"]}, "opted_out": rng.choice([False, False, False, True]),
              "ready": rng.choice([True, True, True, False]), "sms": rng.choice(["ok", "ok", "ok", "awaiting", "recon", "boom"]), "email": rng.choice(["ok", "ok", "ok", "boom", "long"])}
    eff = []

    async def get_by_id(tid, tenant=tenant):
        eff.append(["tenant", [tid]])
        if script.get("tenant_boom"):
            raise RuntimeError("db down")
        return dict(tenant) if tenant else None

    async def is_auth(tid, perm, script=script):
        eff.append(["authorized", [tid, perm]])
        return script["auth"][perm]

    async def opted(tid, contact, script=script):
        eff.append(["opted_out", [tid, contact]])
        return script["opted_out"]

    def ready(t, script=script):
        eff.append(["sender_ready", []])
        return script["ready"]

    async def send_sms(to, body, frm, **kw):
        eff.append(["send_sms", [to, body, frm, kw["request_key"], kw["outbox_id"]]])
        if script["sms"] == "awaiting":
            raise device_sms.AwaitingReceipt("x")
        if script["sms"] == "recon":
            raise device_sms.ReconciliationRequired("x")
        if script["sms"] == "boom":
            raise RuntimeError("sms provider down")

    async def send_email(to, subject, body, headers=None):
        eff.append(["send_email", [to, subject, body, headers]])
        if script["email"] == "boom":
            raise RuntimeError("smtp refused")
        if script["email"] == "long":
            raise RuntimeError("e" * 700)

    def url_for(tid, to):
        eff.append(["unsub_url", [tid, to]])
        return "https://u.example/" + to

    class Pool:
        async def execute(self, sql, *a):
            eff.append(["execute", sql.split("SET")[1].split("WHERE")[0].strip()[:60], [x.isoformat() if isinstance(x, datetime) else x for x in a]])

        async def fetch(self, sql, *a):
            eff.append(["claim", []])
            return rows

    tenants.get_by_id, channel_authorization.is_authorized, outbox.is_opted_out = get_by_id, is_auth, opted
    sms.sender_ready, sms.send_sms, mailer.send_email, unsub.url_for = ready, send_sms, send_email, url_for
    db.pool = lambda: Pool()
    outbox.get_settings = lambda cfg=cfg: cfg
    n = asyncio.run(outbox.process_once())
    cases.append({"now": CUR["now"], "rows": rows, "tenant": tenant, "cfg": vars(cfg), "script": script, "out": n, "effects": eff})
json.dump(cases, sys.stdout, ensure_ascii=True, separators=(",", ":"), default=str)
