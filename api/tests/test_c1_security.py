"""Regression tests for C1 critical security vulnerabilities:
1. Cross-tenant IDOR on GET /owner/billing/invoices
2. Stored XSS on public /receipt/{token}
3. Unbound 6-digit login code on POST /owner/auth/code/verify
4. Outbound webhook SSRF in portability.py, events.py, and webhook registration
5. Missing CSP / X-Frame-Options / security headers on Studio & public HTML
6. Unrevoked sign-out token in Studio (App.tsx -> POST /owner/auth/logout)
"""
from __future__ import annotations

import asyncio
import datetime
import os
import pathlib
import re
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import asyncpg
import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import (
    db,
    events,
    main as app_main,
    owner_auth,
    platform_billing,
    portability,
    public_fetch,
)
from app.routers import admin as admin_router

DSN = os.environ.get("TEST_DATABASE_URL")
needs_db = pytest.mark.skipif(not DSN, reason="needs TEST_DATABASE_URL (a real Postgres)")
SCHEMA = (pathlib.Path(__file__).resolve().parents[1] / "app" / "schema.sql").read_text()
REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]


async def _fresh_pool():
    pool = await asyncpg.create_pool(DSN, min_size=1, max_size=4)
    async with pool.acquire() as conn:
        await conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await conn.execute(SCHEMA.replace("__DIM__", "1536"))
    db._pool = pool
    return pool


# ------------------------------------------------------------------ 1. Cross-tenant IDOR

@needs_db
def test_owner_billing_invoices_is_strictly_scoped_to_callers_tenant():
    async def run():
        pool = await _fresh_pool()
        try:
            t_a = await pool.fetchval(
                "INSERT INTO tenants (slug, name, public_key) VALUES ('alpha','Alpha','pk_a') RETURNING id"
            )
            t_b = await pool.fetchval(
                "INSERT INTO tenants (slug, name, public_key) VALUES ('beta','Beta','pk_b') RETURNING id"
            )
            await platform_billing.issue(
                email="a@alpha.test", name="Alice", business="Alpha Ltd",
                plan="Concierge", amount_cents=19900, currency="USD", tenant_id=t_a,
            )
            await platform_billing.issue(
                email="b@beta.test", name="Bob", business="Beta Ltd",
                plan="Concierge", amount_cents=50000, currency="USD", tenant_id=t_b,
            )
            # Unprovisioned invoice (tenant_id IS NULL) must never leak to any tenant either.
            await platform_billing.issue(
                email="c@orphan.test", name="Carol", business="Orphan Ltd",
                plan="Concierge", amount_cents=99900, currency="USD", tenant_id=None,
            )

            app_main.app.dependency_overrides[owner_auth.current_user] = lambda: {
                "id": uuid.uuid4(), "tenant_id": t_a, "role": "owner",
                "email": "a@alpha.test", "slug": "alpha", "name": "Alpha",
            }
            try:
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app_main.app), base_url="http://t"
                ) as client:
                    resp = await client.get("/owner/billing/invoices")
                    assert resp.status_code == 200, resp.text
                    rows = resp.json()
                    assert len(rows) == 1
                    assert rows[0]["customer_email"] == "a@alpha.test"
                    assert all(r["customer_email"] != "b@beta.test" for r in rows)
                    assert all(r["customer_email"] != "c@orphan.test" for r in rows)
            finally:
                app_main.app.dependency_overrides.clear()
        finally:
            await pool.close()
            db._pool = None

    asyncio.run(run())


# ------------------------------------------------------------------ 2. Stored XSS on /receipt/{token}

def test_receipt_html_escapes_all_untrusted_fields():
    payload = '<script>alert("xss")</script><img src=x onerror=alert(1)>'
    rendered = platform_billing.invoice_html({
        "number": f"TRB-{payload}",
        "customer_email": f'victim+{payload}@example.com',
        "customer_name": payload,
        "business_name": f'"><svg/onload=alert(1)>',
        "currency": f'NZD{payload}',
        "amount_cents": 115_000,
        "gst_cents": 15_000,
        "description": payload,
        "issued_on": datetime.date(2026, 11, 21),
        "paid_at": datetime.datetime(2026, 11, 21, 9, 0),
    })
    assert "<script>" not in rendered
    assert "<img " not in rendered
    assert "<svg" not in rendered
    assert "&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;" in rendered
    assert "&lt;svg/onload=alert(1)&gt;" in rendered


# ------------------------------------------------------------------ 3. Unbound 6-digit login code

@needs_db
def test_six_digit_code_is_bound_to_email_and_purpose():
    async def run():
        pool = await _fresh_pool()
        try:
            tenant = await pool.fetchval(
                "INSERT INTO tenants (slug, name, public_key) VALUES ('acme','Acme','pk_acme') RETURNING id"
            )
            await pool.execute(
                "INSERT INTO tenant_users(tenant_id,email,role,password_hash,active) "
                "VALUES($1,'victim@acme.test','owner','no-password',true)",
                tenant,
            )
            code = await owner_auth.make_code(tenant, "victim@acme.test", "owner")

            # Cross-email redemption must fail and must NOT consume the victim's code.
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app_main.app), base_url="http://t"
            ) as client:
                wrong_email = await client.post(
                    "/owner/auth/code/verify",
                    json={"email": "attacker@evil.test", "code": code},
                )
                assert wrong_email.status_code == 400

                # Link endpoint / accept_invite without expected_purpose="code" must reject a code.
                with pytest.raises(ValueError, match="not recognised"):
                    await owner_auth.accept_invite(code)

                # Correct email (case/whitespace insensitive) redeems the code once.
                good = await client.post(
                    "/owner/auth/code/verify",
                    json={"email": "  VICTIM@Acme.test ", "code": code},
                )
                assert good.status_code == 200, good.text
                body = good.json()
                assert body["access_token"]
                assert body["email"] == "victim@acme.test"

                # Replaying the same code fails immediately (no grace window for codes).
                replay = await client.post(
                    "/owner/auth/code/verify",
                    json={"email": "victim@acme.test", "code": code},
                )
                assert replay.status_code == 400

            # A non-code invite (purpose='invite') cannot be redeemed through /owner/auth/code/verify
            # even if its token happens to be 6 digits.
            fake_code = "654321"
            await pool.execute(
                "INSERT INTO tenant_invites(tenant_id,email,role,purpose,token_hash,expires_at) "
                "VALUES($1,'victim@acme.test','owner','invite',$2,now()+interval '10 minutes')",
                tenant, owner_auth.digest(fake_code),
            )
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app_main.app), base_url="http://t"
            ) as client:
                wrong_purpose = await client.post(
                    "/owner/auth/code/verify",
                    json={"email": "victim@acme.test", "code": fake_code},
                )
                assert wrong_purpose.status_code == 400
        finally:
            await pool.close()
            db._pool = None

    asyncio.run(run())


# ------------------------------------------------------------------ 4. Outbound webhook SSRF

@pytest.mark.parametrize("bad_url", [
    "http://hooks.example.com/crm",
    "https://127.0.0.1/hook",
    "https://127.0.0.1:4390/v1/customers",
    "https://localhost/hook",
    "https://sub.localhost/hook",
    "https://169.254.169.254/latest/meta-data/",
    "https://10.0.0.5/hook",
    "https://172.16.0.1/hook",
    "https://192.168.1.1/hook",
    "https://[::1]/hook",
    "https://[::ffff:127.0.0.1]/hook",
    "https://[fd00::1]/hook",
    "https://email-auth:8090/verify",
    "https://user:secret@hooks.example.com/hook",
    "https://hooks.example.com:8443/hook",
])
def test_webhook_url_validation_rejects_ssrf_targets(bad_url):
    with pytest.raises(ValueError):
        public_fetch.validate_public_https_url(bad_url)
    with pytest.raises(ValidationError):
        admin_router.TenantCreate(name="Acme", lead_webhook_url=bad_url)
    with pytest.raises(ValidationError):
        admin_router.TenantUpdate(lead_webhook_url=bad_url)


@pytest.mark.parametrize("private_ip", [
    "127.0.0.1", "10.0.0.1", "172.18.0.5", "192.168.0.10",
    "169.254.169.254", "::1", "fd00::1", "::ffff:127.0.0.1",
])
def test_post_public_blocks_dns_resolving_to_private_ips(monkeypatch, private_ip):
    loop = SimpleNamespace(
        getaddrinfo=AsyncMock(return_value=[(2, 1, 6, "", (private_ip, 443))])
    )
    monkeypatch.setattr(public_fetch.asyncio, "get_running_loop", lambda: loop)
    called = []

    def fail_transport(request):
        called.append(request)
        return httpx.Response(200)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(fail_transport)) as client:
            with pytest.raises(ValueError, match="public internet"):
                await public_fetch.post_public(
                    "https://rebind.example/hook", content=b"{}", headers={}, client=client,
                )

    asyncio.run(run())
    assert not called, "private IP was contacted despite SSRF guard"


def test_post_public_pins_resolved_public_ip_and_refuses_redirects(monkeypatch):
    monkeypatch.setattr(public_fetch, "public_addresses", AsyncMock(return_value=["1.1.1.1"]))
    seen = []

    def redirect_transport(request):
        seen.append({
            "host": request.url.host,
            "header_host": request.headers.get("host"),
            "sni": request.extensions.get("sni_hostname"),
            "path": request.url.path,
        })
        return httpx.Response(302, headers={"Location": "https://127.0.0.1/secret"})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(redirect_transport)) as client:
            resp = await public_fetch.post_public(
                "https://hooks.example.com/crm",
                content=b'{"ok":true}',
                headers={"Content-Type": "application/json"},
                client=client,
            )
            assert resp.status_code == 302

    asyncio.run(run())
    assert len(seen) == 1, "redirect must never be followed"
    assert seen[0]["host"] == "1.1.1.1"
    assert seen[0]["header_host"] == "hooks.example.com"
    assert seen[0]["sni"] == "hooks.example.com"


def test_events_post_blocks_internal_webhook_without_network_call(monkeypatch):
    updates = []

    class FakePool:
        async def execute(self, sql, *args):
            updates.append((sql, args))

    monkeypatch.setattr(events.db, "pool", lambda: FakePool())
    monkeypatch.setattr(events.public_fetch, "public_addresses", AsyncMock(side_effect=AssertionError("should fail before DNS")))
    tenant = {"slug": "acme", "name": "Acme", "lead_webhook_url": "http://169.254.169.254/latest/meta-data/"}
    asyncio.run(events._post(tenant, "lead.created", {}, lead_id="lead-1"))
    assert updates and updates[0][1] == ("lead-1", "blocked")


def test_owner_set_webhook_endpoint_rejects_internal_targets(monkeypatch):
    app_main.app.dependency_overrides[owner_auth.current_user] = lambda: {
        "id": uuid.uuid4(), "tenant_id": uuid.uuid4(), "role": "owner",
        "email": "o@acme.test", "slug": "acme", "name": "Acme",
    }
    try:
        client = TestClient(app_main.app)
        for bad in ("https://127.0.0.1:4390/v1/customers", "https://169.254.169.254/latest", "http://example.com/hook"):
            resp = client.post("/owner/webhooks", json={"url": bad, "secret": "s" * 24})
            assert resp.status_code == 400, f"{bad} was accepted: {resp.status_code}"
    finally:
        app_main.app.dependency_overrides.clear()


# ------------------------------------------------------------------ 5. Security headers & CSP

def _assert_safe_csp(csp: str, *, allow_nonce: bool = False):
    assert csp, "missing Content-Security-Policy header"
    assert "frame-ancestors 'none'" in csp
    script_directives = [p.strip() for p in csp.split(";") if p.strip().startswith("script-src")]
    for directive in script_directives:
        assert "'unsafe-inline'" not in directive, f"unsafe-inline in {directive}"
        assert "'unsafe-eval'" not in directive, f"unsafe-eval in {directive}"
        if allow_nonce:
            assert "'nonce-" in directive


def test_studio_and_public_html_endpoints_emit_security_headers(tmp_path, monkeypatch):
    (tmp_path / "index.html").write_text("<!doctype html><html><body>Studio</body></html>", encoding="utf-8")
    (tmp_path / "install.html").write_text(
        "<!doctype html><html><body><script>console.log(1)</script></body></html>", encoding="utf-8"
    )
    monkeypatch.setattr(app_main, "STUDIO_DIR", tmp_path)

    client = TestClient(app_main.app)

    # Studio shell
    for path in ("/studio", "/studio/", "/privacy"):
        resp = client.get(path)
        assert resp.status_code == 200, path
        assert resp.headers.get("x-frame-options") == "DENY", path
        assert resp.headers.get("x-content-type-options") == "nosniff", path
        assert resp.headers.get("referrer-policy") == "no-referrer", path
        assert resp.headers.get("permissions-policy"), path
        _assert_safe_csp(resp.headers.get("content-security-policy", ""))

    # Nonce-protected pages with inline scripts
    for path in ("/studio/install", "/owner-ui", "/onboarding", "/admin-ui", "/owner/social/oauth/callback"):
        r1 = client.get(path)
        r2 = client.get(path)
        assert r1.status_code == 200, path
        assert r1.headers.get("x-frame-options") == "DENY", path
        assert r1.headers.get("x-content-type-options") == "nosniff", path
        assert r1.headers.get("referrer-policy") == "no-referrer", path
        csp1 = r1.headers.get("content-security-policy", "")
        csp2 = r2.headers.get("content-security-policy", "")
        _assert_safe_csp(csp1, allow_nonce=True)
        m1 = re.search(r"'nonce-([A-Za-z0-9_-]+)'", csp1)
        m2 = re.search(r"'nonce-([A-Za-z0-9_-]+)'", csp2)
        assert m1 and m2 and m1.group(1) != m2.group(1), f"nonce must rotate per request on {path}"
        assert f'<script nonce="{m1.group(1)}">' in r1.text, f"nonce missing in HTML body on {path}"

    # Public /receipt/{token}
    fake_invoice = {
        "number": "TRB-0001", "customer_email": "a@b.test", "customer_name": "Alice",
        "business_name": "Acme", "currency": "NZD", "amount_cents": 11500, "gst_cents": 1500,
        "description": "Concierge", "issued_on": datetime.date(2026, 11, 21),
        "paid_at": datetime.datetime(2026, 11, 21, 9, 0),
    }

    class FakeReceiptPool:
        async def fetchrow(self, sql, *args):
            return fake_invoice

    monkeypatch.setattr(platform_billing.db, "pool", lambda: FakeReceiptPool())
    receipt = client.get("/receipt/tok-123")
    assert receipt.status_code == 200
    assert receipt.headers.get("x-frame-options") == "DENY"
    assert receipt.headers.get("x-content-type-options") == "nosniff"
    assert receipt.headers.get("referrer-policy") == "no-referrer"
    _assert_safe_csp(receipt.headers.get("content-security-policy", ""))
    assert "default-src 'none'" in receipt.headers["content-security-policy"]

    # Caddyfile fallback headers for concierge.trendibizz.com
    caddyfile = (REPO_ROOT / "scripts" / "vps" / "Caddyfile").read_text(encoding="utf-8")
    owner_block = caddyfile.split("handle @owner {", 1)[1].split("handle @crm", 1)[0]
    for hdr in ("X-Frame-Options", "X-Content-Type-Options", "Referrer-Policy", "Permissions-Policy"):
        assert hdr in owner_block, f"{hdr} missing from Caddyfile @owner block"


# ------------------------------------------------------------------ 6. Sign-out revokes server session

def test_studio_sign_out_calls_logout_endpoint():
    app_tsx = (REPO_ROOT / "web" / "portal" / "src" / "App.tsx").read_text(encoding="utf-8")
    assert "async function signOut()" in app_tsx
    assert "fetch('/owner/auth/logout'" in app_tsx
    assert "Authorization: 'Bearer ' + current" in app_tsx
    assert "onClick={() => void signOut()}" in app_tsx


@needs_db
def test_logout_revokes_bearer_session_in_database():
    async def run():
        pool = await _fresh_pool()
        try:
            tenant = await pool.fetchval(
                "INSERT INTO tenants (slug, name, public_key) VALUES ('acme','Acme','pk_acme') RETURNING id"
            )
            token = await owner_auth.make_invite(tenant, "owner@acme.test", "owner", "invite")
            session = await owner_auth.accept_invite(token)
            bearer = session["access_token"]
            headers = {"Authorization": f"Bearer {bearer}"}

            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app_main.app), base_url="http://t"
            ) as client:
                before = await client.get("/owner/me", headers=headers)
                assert before.status_code == 200

                out = await client.post("/owner/auth/logout", headers=headers)
                assert out.status_code == 200

                after = await client.get("/owner/me", headers=headers)
                assert after.status_code == 401
        finally:
            await pool.close()
            db._pool = None

    asyncio.run(run())
