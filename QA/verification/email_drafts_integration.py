"""Isolated end-to-end email draft tests. Requires disposable Postgres at 127.0.0.1:55432.

This file deliberately never starts outbox workers or contacts SMTP or AI providers.
"""
import os
from types import SimpleNamespace
from unittest.mock import patch

os.environ.update({
    "DATABASE_URL": "postgresql://postgres:test@127.0.0.1:55432/postgres",
    "OUTBOX_ENABLED": "false",
    "EMAIL_DRAFTS_ENABLED": "true",
    "ADMIN_TOKEN": "test-admin-only",
})
from fastapi.testclient import TestClient  # noqa: E402
from app import db, email_drafts, llm, rag  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402

H = {"X-Admin-Token": "test-admin-only"}
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
        a = await pool.fetchval(
            "INSERT INTO tenants (slug,name,public_key) VALUES "
            "('alpha','Alpha','pk_alpha') RETURNING id")
        b = await pool.fetchval(
            "INSERT INTO tenants (slug,name,public_key) VALUES "
            "('beta','Beta','pk_beta') RETURNING id")
        return a,b

    alpha, beta = run(seed)
    data = {
        "sender": "client@example.test", "subject": "Question about opening hours",
        "inbound_body": "Can I book tomorrow?",
        "reply_body": "Thanks for reaching out. The team will confirm availability.",
        "source_id": "inbound:alpha:001",
    }
    base = "/admin/tenants/alpha/email-drafts"
    r = client.post(base, json=data)
    check("admin token required", r.status_code == 401)
    r = client.post(base, headers=H, json=data)
    check("draft created", r.status_code == 201 and r.json()["status"] == "draft")
    draft_id = r.json()["id"]
    check("inbound contents saved", r.json()["inbound_body"] == data["inbound_body"])

    r = client.post(base, headers=H, json={**data, "reply_body": "changed"})
    check("same provider message is idempotent", r.status_code == 201 and r.json()["id"] == draft_id)
    check("idempotency never overwrites owner draft", r.json()["reply_body"] == data["reply_body"])
    r = client.get(base, headers=H)
    check("draft appears in owner's list", r.status_code == 200 and len(r.json()) == 1)
    r = client.get("/admin/tenants/beta/email-drafts", headers=H)
    check("other tenant cannot list alpha drafts", r.status_code == 200 and r.json() == [])

    r = client.patch(f"/admin/tenants/beta/email-drafts/{draft_id}", headers=H,
                     json={"reply_body": "not allowed"})
    check("other tenant cannot edit draft", r.status_code == 404)
    r = client.post(f"/admin/tenants/beta/email-drafts/{draft_id}/approve", headers=H)
    check("other tenant cannot approve draft", r.status_code == 503)

    r = client.post(base, headers=H, json={**data, "source_id": "bad", "sender": "bad\nBcc: x@y.com"})
    check("header injection rejected", r.status_code == 400)
    r = client.patch(f"{base}/{draft_id}", headers=H, json={"reply_body": "Updated by owner"})
    check("owner can revise draft", r.status_code == 200 and r.json()["reply_body"] == "Updated by owner")

    r = client.post(f"{base}/{draft_id}/approve", headers=H)
    check("no send when outbound queue disabled", r.status_code == 503)
    pending = run(lambda: pool.fetchval("SELECT count(*) FROM outbox WHERE kind='approved_reply'"))
    check("disabled outbox has zero messages", pending == 0)

    settings = get_settings()
    settings.outbox_enabled = True  # worker did not start; change only inside test
    settings.smtp_host = "invalid.test"
    settings.smtp_from = "noreply@example.test"
    try:
        r = client.post(f"/admin/tenants/beta/email-drafts/{draft_id}/approve", headers=H)
        check("other tenant cannot approve even when SMTP configured", r.status_code == 409)
        r = client.post(f"{base}/{draft_id}/approve", headers=H)
        check("owner approves draft", r.status_code == 200 and r.json()["status"] == "approved")
        r = client.post(f"{base}/{draft_id}/approve", headers=H)
        check("repeat approval blocked", r.status_code == 409)
        rows = run(lambda: pool.fetch(
            "SELECT * FROM outbox WHERE kind='approved_reply' AND tenant_id=$1", alpha))
        check("exactly one queued outbound email", len(rows) == 1)
        check("queued only updated owner reply", rows[0]["body"] == "Updated by owner")
        check("sender is original correspondent", rows[0]["to_addr"] == data["sender"])
        check("queue cannot send without worker", rows[0]["status"] == "pending")
    finally:
        settings.outbox_enabled = False
        settings.smtp_host = ""
        settings.smtp_from = ""

    r = client.post(base, headers=H, json={
        **data, "source_id": "inbound:alpha:002", "reply_body": "Another reply"})
    new_id = r.json()["id"]
    r = client.post(f"{base}/{new_id}/discard", headers=H)
    check("owner can discard", r.status_code == 200 and r.json()["status"] == "discarded")
    r = client.patch(f"{base}/{new_id}", headers=H, json={"reply_body": "late"})
    check("discarded draft cannot be edited", r.status_code == 404)

    async def fake_complete(*args, **kwargs):
        return SimpleNamespace(content="Draft from AI. Human review is needed.")
    async def fake_retrieve(*args, **kwargs):
        return []  # no embedding provider is contacted; business knowledge retrieval is covered elsewhere
    with patch.object(llm, "complete", new=fake_complete), patch.object(rag, "retrieve", new=fake_retrieve):
        r = client.post(base, headers=H, json={
            "sender": "person@example.test", "subject": "New enquiry",
            "inbound_body": "Can I get a quote?", "generate": True})
    check("LLM creates only a draft", r.status_code == 201 and r.json()["status"] == "draft")
    check("LLM generated content persisted for review",
          r.json()["reply_body"] == "Draft from AI. Human review is needed.")
    pending = run(lambda: pool.fetchval("SELECT count(*) FROM outbox WHERE kind='approved_reply'"))
    check("generation does not queue an email", pending == 1)

print(f"{n}/{n} email draft checks passed")
