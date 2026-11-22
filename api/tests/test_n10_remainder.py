"""N10 Remainder tests:
- Automated SPF / DKIM / DMARC DNS verification
- Attachment byte storage & authenticated download
- Gmail / M365 send-as OAuth disabled cleanly until credentialed
"""
from __future__ import annotations

import asyncio
import os
import pathlib

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient

from app import db, email_domain, owner_auth, tenants
from app.config import get_settings
from app.main import app

DSN = os.environ.get("TEST_DATABASE_URL")
needs_db = pytest.mark.skipif(not DSN, reason="needs TEST_DATABASE_URL (a real Postgres)")
SCHEMA = (pathlib.Path(__file__).resolve().parents[1] / "app" / "schema.sql").read_text()


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


@needs_db
def test_spf_dkim_dmarc_check_attachments_and_send_as_disabled(monkeypatch):
    records = {
        "example.co.nz": ["v=spf1 include:spf.brevo.com ~all"],
        "_dmarc.example.co.nz": ["v=DMARC1; p=quarantine; rua=mailto:dmarc@example.co.nz"],
        "concierge._domainkey.example.co.nz": ["v=DKIM1; k=rsa; p=MIIBIjANBgkqhki"],
    }

    async def fake_dns_txt(name: str) -> list[str]:
        return records.get(name, [])

    monkeypatch.setattr(email_domain, "dns_txt", fake_dns_txt)
    monkeypatch.setattr(get_settings(), "gmail_oauth_client_id", "", raising=False)
    monkeypatch.setattr(get_settings(), "ms_client_id", "", raising=False)

    async def _go(pool):
        t = await tenants.create("Mail Co", "https://mailco.example", "mail-co")
        inv = await owner_auth.make_invite(t["id"], "owner@mailco.test", "owner", "invite")
        sess = await owner_auth.accept_invite(inv)
        headers = {"Authorization": f"Bearer {sess['access_token']}"}

        draft_id = await pool.fetchval(
            "INSERT INTO email_drafts(tenant_id, sender, subject, inbound_body, reply_body) "
            "VALUES($1, 'c@test.nz', 'Plans', 'Attached', 'Thanks') RETURNING id",
            t["id"],
        )
        att = await email_domain.store_attachment(t["id"], draft_id, "floorplan.pdf", "application/pdf", b"%PDF-1.4 demo")

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            # 1. Automated SPF/DKIM/DMARC check
            chk = await client.get("/owner/email/domain-check?domain=example.co.nz", headers=headers)
            assert chk.status_code == 200
            body = chk.json()
            assert body["ready"] is True
            assert body["spf"]["ok"] is True
            assert body["dkim"]["ok"] is True
            assert body["dmarc"]["ok"] is True and body["dmarc"]["policy"] == "quarantine"

            # 2. Attachment list & byte download
            lst = await client.get(f"/owner/email/drafts/{draft_id}/attachments", headers=headers)
            assert lst.status_code == 200 and len(lst.json()) == 1
            dl = await client.get(f"/owner/email/attachments/{att['id']}", headers=headers)
            assert dl.status_code == 200 and dl.content == b"%PDF-1.4 demo"

            # 3. Gmail / M365 send-as disabled until credentialed
            sa = await client.get("/owner/email/send-as", headers=headers)
            assert sa.status_code == 200
            provs = {p["provider"]: p for p in sa.json()["providers"]}
            assert provs["gmail"]["enabled"] is False
            assert provs["m365"]["enabled"] is False
            conn_res = await client.post("/owner/email/send-as/gmail/connect", headers=headers)
            assert conn_res.status_code == 409
    run(_go)
