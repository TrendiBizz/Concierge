"""Disposable PostgreSQL integration of owner permissions; never contacts providers."""
from __future__ import annotations

import asyncio
import os
from uuid import uuid4

os.environ["DATABASE_URL"] = f"postgresql://postgres:test@127.0.0.1:{os.environ.get('CONCIERGE_TEST_POSTGRES_PORT', '55432')}/postgres"
os.environ["OUTBOX_ENABLED"] = "false"
os.environ["ADMIN_TOKEN"] = "synthetic-admin"

import httpx
from app import db, owner_auth
from app.main import app


async def main():
    await db.init()
    pool = db.pool()
    alpha, beta = [], []
    async def create(slug):
        tenant_id = uuid4()
        user_id = uuid4()
        await pool.execute(
            """INSERT INTO tenants(id,slug,name,public_key)
               VALUES($1,$2,$3,$4)""",
            tenant_id, slug, slug, "synthetic-" + slug,
        )
        await pool.execute(
            """INSERT INTO tenant_users(id,tenant_id,email,role,password_hash)
               VALUES($1,$2,'test@example.invalid','owner','test-only')""",
            user_id, tenant_id,
        )
        return tenant_id, user_id
    try:
        alpha = await create("synthetic-alpha-" + uuid4().hex[:8])
        beta = await create("synthetic-beta-" + uuid4().hex[:8])
        current = alpha
        async def identity():
            return {"tenant_id": current[0], "id": current[1], "role": "owner"}
        app.dependency_overrides[owner_auth.current_user] = identity
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            url = "/owner/onboarding/authorizations"
            body = {"channel": "email_read", "authorized": True,
                    "acknowledgement": True}
            r = await client.post(url, json=body)
            assert r.status_code == 200, r.text
            current = beta
            r = await client.get(url)
            assert r.status_code == 200 and not r.json()["email_read"]["authorized"]
            current = alpha
            r = await client.get(url)
            assert r.json()["email_read"]["authorized"]
            r = await client.post(url, json={**body, "authorized": False})
            assert r.status_code == 200
            assert (await client.get(url)).json()["email_read"]["authorized"] is False
            logs = await pool.fetch(
                """SELECT authorized FROM tenant_channel_authorization_audit
                   WHERE tenant_id=$1 ORDER BY id""", alpha[0],
            )
            assert [row["authorized"] for row in logs] == [True, False], logs
            r = await client.get("/owner/onboarding/readiness")
            assert r.status_code == 200, r.text
            assert r.json()["customer_activation_enabled"] is False
            assert r.json()["channels"]["email_read"]["active"] is False
            print("DISPOSABLE_PG_AUTHORIZATION_PASS: tenant isolation, revocation, audit, readiness")
    finally:
        app.dependency_overrides.clear()
        for ids in (alpha, beta):
            if ids:
                await pool.execute("DELETE FROM tenants WHERE id=$1", ids[0])
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
