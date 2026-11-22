"""N9 Security Hardening tests: Postgres RLS tenant walls, token encryption at rest,
owner MFA (TOTP + recovery codes + passkeys + logout-all), and per-operator admin auth/audit.
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import pathlib
import uuid

import asyncpg
import pytest
from httpx import ASGITransport, AsyncClient

from app import (
    calendar_connection,
    crypto_vault,
    db,
    integrations,
    owner_auth,
    owner_mfa,
    portability,
    rls,
    tenants,
)
from app.main import app

DSN = os.environ.get("TEST_DATABASE_URL")
needs_db = pytest.mark.skipif(not DSN, reason="needs TEST_DATABASE_URL (a real Postgres)")
SCHEMA = (pathlib.Path(__file__).resolve().parents[1] / "app" / "schema.sql").read_text()
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "test-admin-token")


async def _fresh_pool():
    pool = await asyncpg.create_pool(DSN, min_size=1, max_size=4)
    async with pool.acquire() as conn:
        await conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await conn.execute(SCHEMA.replace("__DIM__", "384"))
        await conn.execute(rls.rls_migration_sql())
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


def _b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def test_crypto_vault_roundtrip_aad_and_tamper():
    ct = crypto_vault.encrypt_text("super-secret-token", aad="tenant:1")
    assert crypto_vault.is_encrypted(ct)
    assert "super-secret-token" not in ct
    assert crypto_vault.decrypt_text(ct, aad="tenant:1") == "super-secret-token"
    with pytest.raises(ValueError):
        crypto_vault.decrypt_text(ct, aad="tenant:2")
    tampered = ct[:-2] + ("AA" if not ct.endswith("AA") else "BB")
    with pytest.raises(ValueError):
        crypto_vault.decrypt_text(tampered, aad="tenant:1")
    assert crypto_vault.decrypt_text("legacy-plain", allow_plaintext=True) == "legacy-plain"
    with pytest.raises(ValueError):
        crypto_vault.decrypt_text("legacy-plain", allow_plaintext=False)


def test_totp_rfc6238_and_replay_guard():
    secret = owner_mfa.generate_totp_secret()
    uri = owner_mfa.provisioning_uri(secret, "owner@example.com")
    assert uri.startswith("otpauth://totp/")
    assert secret in uri
    t = 1700000000.0
    code = owner_mfa.totp_code(secret, for_time=t)
    assert len(code) == 6 and code.isdigit()
    step = owner_mfa.verify_totp(secret, code, for_time=t)
    assert step is not None
    assert owner_mfa.verify_totp(secret, code, for_time=t, last_step=step) is None
    assert owner_mfa.verify_totp(secret, "000000", for_time=t) is None


@needs_db
def test_postgres_rls_enforces_tenant_walls():
    async def _go(pool):
        t_a = await tenants.create("rls-alpha", "RLS Alpha", "")
        t_b = await tenants.create("rls-beta", "RLS Beta", "")
        await pool.execute(
            "INSERT INTO leads(tenant_id, name, email) VALUES($1, 'Alice', 'a@alpha.test'), ($2, 'Bob', 'b@beta.test')",
            t_a["id"], t_b["id"],
        )
        for tbl in ("leads", "platform_invoices", "tenant_webhooks"):
            row = await pool.fetchrow(
                "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname=$1", tbl
            )
            assert row and row["relrowsecurity"] is True and row["relforcerowsecurity"] is True

        role = "rls_test_role_" + uuid.uuid4().hex[:8]
        async with pool.acquire() as conn:
            await conn.execute(f"CREATE ROLE {role} NOLOGIN")
            await conn.execute(f"GRANT USAGE ON SCHEMA public TO {role}")
            await conn.execute(f"GRANT SELECT, INSERT ON leads TO {role}")
        try:
            async with db.tenant_conn(t_a["id"]) as conn:
                await conn.execute(f"SET LOCAL ROLE {role}")
                rows = await conn.fetch("SELECT name, tenant_id FROM leads")
                assert len(rows) == 1
                assert rows[0]["name"] == "Alice"
                assert rows[0]["tenant_id"] == t_a["id"]
                with pytest.raises(asyncpg.InsufficientPrivilegeError):
                    await conn.execute(
                        "INSERT INTO leads(tenant_id, name, email) VALUES($1, 'Mallory', 'm@beta.test')",
                        t_b["id"],
                    )
        finally:
            async with pool.acquire() as conn:
                await conn.execute(f"REVOKE ALL ON leads FROM {role}")
                await conn.execute(f"REVOKE USAGE ON SCHEMA public FROM {role}")
                await conn.execute(f"DROP ROLE IF EXISTS {role}")
    run(_go)


@needs_db
def test_token_encryption_calendar_webhook_and_integrations(tmp_path, monkeypatch):
    async def _go(pool):
        t = await tenants.create("enc-tenant", "Enc Tenant", "")
        monkeypatch.setattr(calendar_connection.get_settings(), "calendar_credentials_dir", str(tmp_path))
        calendar_connection.save_token(t["id"], {"access_token": "tok-example", "expires_at": 9999999999})
        raw_disk = calendar_connection.token_path(t["id"]).read_text()
        assert crypto_vault.is_encrypted(raw_disk)
        assert "tok-example" not in raw_disk
        assert await calendar_connection.access_token(t["id"]) == "tok-example"

        monkeypatch.setattr("app.public_fetch.validate_public_https_url", lambda u: u)
        await portability.set_webhook(t["id"], "https://hooks.example.com/in", "hook-example")
        stored = await pool.fetchval("SELECT secret FROM tenant_webhooks WHERE tenant_id=$1", t["id"])
        assert crypto_vault.is_encrypted(stored)
        assert "hook-example" not in stored
        assert crypto_vault.decrypt_text(stored, aad=f"webhook:{t['id']}") == "hook-example"

        await integrations._save(t["id"], "servicem8", {"api_key": "key-example"})
        row = await integrations._row(t["id"], "servicem8")
        assert "key-example" not in str(row["credentials"])
        assert integrations._creds(row)["api_key"] == "key-example"
    run(_go)


@needs_db
def test_owner_mfa_totp_passkeys_and_logout_all():
    async def _go(pool):
        t = await tenants.create("mfa-co", "MFA Co", "")
        inv = await owner_auth.make_invite(t["id"], "owner@mfaco.test", "owner", "invite")
        session = await owner_auth.accept_invite(inv)
        headers = {"Authorization": f"Bearer {session['access_token']}"}

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/owner/auth/mfa", headers=headers)
            assert r.status_code == 200 and r.json()["totp_enabled"] is False

            setup = (await client.post("/owner/auth/mfa/totp/setup", headers=headers)).json()
            secret = setup["secret"]
            code = owner_mfa.totp_code(secret)
            conf = await client.post("/owner/auth/mfa/totp/confirm", headers=headers, json={"code": code})
            assert conf.status_code == 200
            recovery_codes = conf.json()["recovery_codes"]
            assert len(recovery_codes) == 8

            inv2 = await owner_auth.make_invite(t["id"], "owner@mfaco.test", "owner", "recovery")
            r2 = await client.post("/owner/auth/invite", json={"token": inv2})
            assert r2.status_code == 200
            body2 = r2.json()
            assert body2["mfa_required"] is True
            assert "totp" in body2["methods"]
            assert "access_token" not in body2

            r3 = await client.post("/owner/auth/mfa/verify", json={"mfa_token": body2["mfa_token"], "code": recovery_codes[0]})
            assert r3.status_code == 200
            assert r3.json()["access_token"]

            opts = await client.post("/owner/auth/passkeys/register/options", headers=headers)
            assert opts.status_code == 200
            challenge = opts.json()["challenge"]
            _, origin = owner_mfa._rp_info()
            cdj = _b64u(json.dumps({"type": "webauthn.create", "challenge": challenge, "origin": origin}).encode())
            reg = await client.post(
                "/owner/auth/passkeys/register/verify",
                headers=headers,
                json={"credential_id": "cred_abc12345", "public_key_spki": _b64u(b"0" * 32), "client_data_json": cdj, "name": "MacBook TouchID"},
            )
            assert reg.status_code == 201
            pk_id = reg.json()["id"]
            listed = (await client.get("/owner/auth/passkeys", headers=headers)).json()["passkeys"]
            assert len(listed) == 1 and listed[0]["name"] == "MacBook TouchID"
            assert (await client.delete(f"/owner/auth/passkeys/{pk_id}", headers=headers)).status_code == 200

            sess_list = (await client.get("/owner/auth/sessions", headers=headers)).json()["sessions"]
            assert len(sess_list) >= 1
            lo = await client.post("/owner/auth/logout-all", headers=headers)
            assert lo.status_code == 200 and lo.json()["revoked"] >= 1
            assert (await client.get("/owner/me", headers=headers)).status_code == 401
    run(_go)


@needs_db
def test_per_operator_admin_auth_and_audit_log(monkeypatch):
    monkeypatch.setattr("app.security.get_settings", lambda: type("S", (), {"admin_token": ADMIN_TOKEN})())
    async def _go(pool):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post(
                "/admin/operators",
                headers={"X-Admin-Token": ADMIN_TOKEN},
                json={"name": "Jo Ops", "email": "jo@trendibizz.com", "role": "superadmin"},
            )
            assert r.status_code == 201
            op = r.json()
            op_token = op["token"]
            assert op_token.startswith("adm_")

            r_list = await client.get("/admin/operators", headers={"X-Admin-Token": op_token})
            assert r_list.status_code == 200
            assert any(o["id"] == op["id"] for o in r_list.json()["operators"])

            audit = await client.get("/admin/audit-log", headers={"X-Admin-Token": op_token})
            assert audit.status_code == 200
            assert any(e["path"] == "/admin/operators" and e["method"] == "POST" for e in audit.json()["entries"])

            rev = await client.delete(f"/admin/operators/{op['id']}", headers={"X-Admin-Token": ADMIN_TOKEN})
            assert rev.status_code == 200
            r_dead = await client.get("/admin/operators", headers={"X-Admin-Token": op_token})
            assert r_dead.status_code == 401
    run(_go)
