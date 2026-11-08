"""Two-customer journey against disposable PostgreSQL and a private Rust fixture.

No production credentials, social-provider requests, messages or paid APIs.
Run only with the isolated test database on 127.0.0.1:55432.
"""
import base64
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
import logging
import os
from pathlib import Path
import secrets
import socket
import subprocess
import tempfile
import time
import unittest
from urllib.parse import parse_qs, urlsplit
from unittest.mock import AsyncMock, patch

os.environ.update({
    "DATABASE_URL": "postgresql://postgres:test@127.0.0.1:55432/postgres",
    "ADMIN_TOKEN": "isolated-onboarding-operator",
    "OUTBOX_ENABLED": "false",
    "EMAIL_DRAFTS_ENABLED": "false",
    "SOCIAL_SERVICE_ENABLED": "true",
})
from fastapi.testclient import TestClient
import httpx
from app import db, ingest, rag, social_bridge, tenants
from app.main import app

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpx2").setLevel(logging.WARNING)
ROOT = Path(__file__).resolve().parents[2]
VECTOR = [1.0] + [0.0] * 383


class CustomerJourney(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stack = ExitStack()
        cls.addClassCleanup(cls.stack.close)
        directory = cls.stack.enter_context(tempfile.TemporaryDirectory(prefix="concierge-two-customer-"))
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        cls.social_url = f"http://127.0.0.1:{port}"
        cls.social_key = secrets.token_hex(32)
        env = {
            "PATH": os.environ.get("PATH", ""),
            "SOCIAL_CONCIERGE_KEY": cls.social_key,
            "SOCIAL_AGENT_KEY": secrets.token_hex(32),
            "SOCIAL_VAULT_KEY": base64.b64encode(secrets.token_bytes(32)).decode(),
            "SOCIAL_DB": str(Path(directory) / "synthetic.db"),
            "SOCIAL_BIND": f"127.0.0.1:{port}",
            "SOCIAL_ENABLE_PUBLISH": "false",
        }
        for provider in ("LINKEDIN", "FACEBOOK", "TIKTOK"):
            env[f"SOCIAL_{provider}_CLIENT_ID"] = "synthetic-app-id"
            env[f"SOCIAL_{provider}_CLIENT_KEY"] = "synthetic-app-key"
            env[f"SOCIAL_{provider}_CLIENT_SECRET"] = "synthetic-app-secret"
            env[f"SOCIAL_{provider}_CALLBACK"] = "https://example.test/owner/social/oauth/callback"
        log = cls.stack.enter_context(open(Path(directory) / "fixture.log", "w"))
        process = subprocess.Popen([str(ROOT / "concierge-stack/social-service/target/debug/concierge-social")],
                                   env=env, stdout=log, stderr=subprocess.STDOUT)
        def cleanup():
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
        cls.stack.callback(cleanup)
        for _ in range(50):
            try:
                if httpx.get(cls.social_url + "/health", timeout=0.2).status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.1)
        else:
            raise RuntimeError("Isolated Rust fixture did not start")
        # Only the private fixture port differs from the production allowlist.
        # Tenant routing, HTTP requests, auth and the Rust store remain real.
        cls.stack.enter_context(patch.object(social_bridge, "_configuration",
                                            return_value=(cls.social_url, cls.social_key)))
        cls.client = cls.stack.enter_context(TestClient(app, raise_server_exceptions=False))
        cls.client.portal.call(lambda: db.pool().execute("DELETE FROM owner_login_limits"))
        cls.operator = {"X-Admin-Token": os.environ["ADMIN_TOKEN"]}
        cls.actors = {}
        cls.invites = {}
        cls.redemptions = {}
        cls.businesses = {}
        suffix = secrets.token_hex(4)
        for name in ("a", "b"):
            slug = f"journey-{name}-{suffix}"
            created = cls.client.post("/admin/tenants", headers=cls.operator,
                                      json={"name": f"Synthetic Business {name.upper()}", "slug": slug})
            if created.status_code != 200:
                raise RuntimeError("Test business creation failed")
            cls.businesses[name] = created.json()
            for role in (["owner"] if name == "a" else ["owner", "viewer"]):
                email = f"{role}-{name}@example.test"
                issued = cls.client.post(f"/admin/tenants/{slug}/owner-invitations", headers=cls.operator,
                                         json={"email": email, "role": role})
                if issued.status_code != 201:
                    raise RuntimeError("Test invitation creation failed")
                cls.invites[name, role] = issued.json()
                redeemed = cls.client.post("/owner/auth/redeem", json={
                    "token": issued.json()["invitation_token"], "password": "SyntheticTestPassphrase123!"})
                if redeemed.status_code != 200:
                    raise RuntimeError("Test invitation redemption failed")
                cls.redemptions[name, role] = redeemed.json()
                login = cls.client.post("/owner/auth/login", json={
                    "slug": slug, "email": email, "password": "SyntheticTestPassphrase123!"})
                if login.status_code != 200:
                    raise RuntimeError("Test customer login failed")
                cls.actors[name, role] = {"Authorization": "Bearer " + login.json()["access_token"]}

    def headers(self, business, role="owner"):
        return self.actors[business, role]

    def test_simultaneous_same_name_customers_receive_distinct_workspaces(self):
        name = "Synthetic simultaneous " + secrets.token_hex(4)
        base = tenants.slugify(name)
        original = tenants.get_by_slug
        barrier = asyncio.Barrier(2)
        async def simultaneous_lookup(slug):
            found = await original(slug)
            if slug == base:
                await barrier.wait()
            return found
        with patch.object(tenants, "get_by_slug", side_effect=simultaneous_lookup):
            with ThreadPoolExecutor(max_workers=2) as workers:
                futures = [workers.submit(self.client.post, "/admin/tenants", headers=self.operator,
                                          json={"name": name}) for _ in range(2)]
                responses = [future.result(timeout=10) for future in futures]
        self.assertEqual([response.status_code for response in responses], [200, 200])
        self.assertNotEqual(responses[0].json()["id"], responses[1].json()["id"])
        self.assertNotEqual(responses[0].json()["slug"], responses[1].json()["slug"])

    def test_long_business_names_still_support_social_account_setup(self):
        response = self.client.post("/admin/tenants", headers=self.operator,
                                    json={"name": "Synthetic " + "a" * 145})
        self.assertEqual(response.status_code, 200)
        business = response.json()
        self.assertLessEqual(len(business["slug"]), 101)
        self.assertEqual(self.client.portal.call(lambda: social_bridge.accounts(business)), [])

    def test_invitation_link_and_business_identity(self):
        for name in ("a", "b"):
            issued = self.invites[name, "owner"]
            self.assertTrue("invitation_url" in issued, "Customers need a usable invitation link")
            url = urlsplit(issued["invitation_url"])
            self.assertEqual(url.scheme, "https")
            self.assertEqual(url.path, "/owner-ui")
            self.assertEqual(url.query, "")
            self.assertEqual(parse_qs(url.fragment)["invite"], [issued["invitation_token"]])
            self.assertEqual(self.redemptions[name, "owner"]["slug"], self.businesses[name]["slug"])
            denied = self.client.post("/owner/auth/redeem", json={
                "token": issued["invitation_token"], "password": "SyntheticTestPassphrase123!"})
            self.assertEqual(denied.status_code, 400)

    def test_customer_edits_own_business_data(self):
        response = self.client.patch("/owner/onboarding/profile", headers=self.headers("a"), json={
            "name": "Synthetic A updated", "site_url": "https://a.example.test",
            "greeting": "Welcome to A", "notify_email": "updates-a@example.test", "timezone": "Pacific/Auckland"})
        self.assertEqual(response.status_code, 200)
        a = self.client.get("/owner/onboarding", headers=self.headers("a")).json()
        b = self.client.get("/owner/onboarding", headers=self.headers("b")).json()
        self.assertEqual(a["business"]["name"], "Synthetic A updated")
        self.assertEqual(a["business"]["site_url"], "https://a.example.test")
        self.assertEqual(b["business"]["name"], "Synthetic Business B")
        self.assertEqual(b["business"]["site_url"], "")
        blocked = self.client.patch("/owner/onboarding/profile", headers=self.headers("b", "viewer"),
                                    json={"greeting": "Not allowed"})
        self.assertEqual(blocked.status_code, 403)
        forged = self.client.patch("/owner/onboarding/profile", headers=self.headers("b"),
                                   json={"tenant_id": self.businesses["a"]["id"], "phone_enabled": True})
        self.assertEqual(forged.status_code, 422)

    def test_customer_knowledge_is_private_and_replacement_is_scoped(self):
        async def vectors(texts):
            return [VECTOR for _ in texts]
        with patch.object(ingest, "embed_documents", side_effect=vectors):
            saved = self.client.post("/owner/knowledge", headers=self.headers("a"), json={
                "title": "Business information", "text": "Synthetic A-only opening hours and services."})
            self.assertEqual(saved.status_code, 201)
            aid = saved.json()["document_id"]
            self.assertEqual(self.client.get("/owner/knowledge", headers=self.headers("b")).json(), [])
            self.assertEqual(self.client.delete(f"/owner/knowledge/{aid}", headers=self.headers("b")).status_code, 404)
            self.assertEqual(self.client.post("/owner/knowledge", headers=self.headers("b", "viewer"), json={
                "title": "Forbidden", "text": "Viewer cannot upload."}).status_code, 403)
            b = self.client.post("/owner/knowledge", headers=self.headers("b"), json={
                "title": "Business information", "text": "Synthetic B-only private product data."})
            self.assertEqual(b.status_code, 201)
            updated = self.client.post("/owner/knowledge", headers=self.headers("a"), json={
                "title": "Business information", "text": "Updated synthetic A-only information."})
            self.assertEqual(updated.status_code, 201)
            self.assertEqual(len(self.client.get("/owner/knowledge", headers=self.headers("a")).json()), 1)
            async def retrieval():
                ta = await tenants.get_by_slug(self.businesses["a"]["slug"])
                tb = await tenants.get_by_slug(self.businesses["b"]["slug"])
                with patch.object(rag, "embed_query", new_callable=AsyncMock, return_value=VECTOR):
                    return await rag.retrieve(ta["id"], "business"), await rag.retrieve(tb["id"], "business")
            a_hits, b_hits = self.client.portal.call(retrieval)
            self.assertTrue(a_hits and b_hits)
            self.assertTrue(all("A-only" in row["content"] for row in a_hits))
            self.assertTrue(all("B-only" in row["content"] for row in b_hits))
            self.assertEqual(self.client.delete(f"/owner/knowledge/{b.json()['document_id']}", headers=self.headers("b")).status_code, 200)
            self.assertEqual(len(self.client.get("/owner/knowledge", headers=self.headers("a")).json()), 1)

    def test_business_upload_validation(self):
        from app.owner_knowledge import BusinessDocument
        self.assertEqual(BusinessDocument(title="Windows file", text="First\r\nSecond").text, "First\nSecond")
        for payload in (
            {"title": "Empty", "text": "  "},
            {"title": "Binary", "text": "bad\x00content"},
            {"title": "Huge", "text": "é" * 50_001},
            {"title": "Forged", "text": "content", "tenant_id": self.businesses["b"]["id"]},
        ):
            response = self.client.post("/owner/knowledge", headers=self.headers("a"), json=payload)
            self.assertEqual(response.status_code, 422)

    def test_failed_knowledge_embedding_keeps_saved_customer_data(self):
        async def exercise():
            tenant = await tenants.get_by_slug(self.businesses["a"]["slug"])
            with patch.object(ingest, "embed_documents", new_callable=AsyncMock, return_value=[VECTOR]):
                await ingest.ingest_text(tenant, "atomic-replacement", "Keep this synthetic saved data.")
            with patch.object(ingest, "embed_documents", new_callable=AsyncMock, side_effect=RuntimeError("synthetic unavailable")):
                try:
                    await ingest.ingest_text(tenant, "atomic-replacement", "New data that cannot embed.")
                except RuntimeError:
                    pass
                else:
                    raise AssertionError("Synthetic embedding failure did not happen")
            return await db.pool().fetchval("SELECT count(*) FROM chunks WHERE tenant_id=$1 AND url=$2", tenant["id"], "manual:atomic-replacement")
        self.assertEqual(self.client.portal.call(exercise), 1, "Failed replacement must retain existing data")

    def test_social_accounts_states_and_drafts_do_not_cross_customers(self):
        raw_headers = {"Authorization": "Bearer " + self.social_key}
        account_ids = {}
        states = {}
        for name in ("a", "b"):
            status = self.client.get("/owner/social/status", headers=self.headers(name))
            self.assertEqual(status.status_code, 200)
            for provider in ("facebook", "instagram", "linkedin", "tiktok"):
                self.assertTrue(status.json()["providers"][provider])
            self.assertEqual(self.client.get("/owner/social/accounts", headers=self.headers(name)).json(), [])
            slug = self.businesses[name]["slug"]
            seeded = httpx.post(f"{self.social_url}/v1/customers/{slug}/accounts", headers=raw_headers, json={
                "network": "linkedin", "external_id": "synthetic-member", "display_name": f"Synthetic member {name}",
                "access_token": "synthetic-credential-not-a-provider-token", "refresh_token": None})
            self.assertEqual(seeded.status_code, 200)
            account_ids[name] = seeded.json()["id"]
            accounts = self.client.get("/owner/social/accounts", headers=self.headers(name))
            self.assertEqual(len(accounts.json()), 1)
            for secret_name in ("access_token", "token_enc", "refresh_token", "refresh_enc"):
                self.assertNotIn(secret_name, accounts.text)
            started = self.client.post("/owner/social/oauth/linkedin/start", headers=self.headers(name))
            self.assertEqual(started.status_code, 200)
            states[name] = started.json()["state"]
        self.assertNotEqual(account_ids["a"], account_ids["b"])
        self.assertNotEqual(states["a"], states["b"])
        crossed = self.client.post("/owner/social/oauth/linkedin/finish", headers=self.headers("b"),
                                   json={"state": states["a"], "code": "synthetic-code-never-exchanged"})
        self.assertEqual(crossed.status_code, 400)
        self.assertEqual(self.client.post("/owner/social/oauth/linkedin/start", headers=self.headers("b", "viewer")).status_code, 403)
        foreign = self.client.post("/owner/social/posts", headers=self.headers("b"),
                                   json={"content": "Synthetic foreign-account attempt", "account_ids": [account_ids["a"]]})
        self.assertNotIn(foreign.status_code, (200, 201))
        own = self.client.post("/owner/social/posts", headers=self.headers("a"),
                               json={"content": "Synthetic A private draft", "account_ids": [account_ids["a"]]})
        self.assertEqual(own.status_code, 200)
        self.assertEqual(len(self.client.get("/owner/social/posts", headers=self.headers("a")).json()), 1)
        self.assertEqual(self.client.get("/owner/social/posts", headers=self.headers("b")).json(), [])
        blocked = self.client.delete(f"/owner/social/oauth/linkedin/accounts/{account_ids['a']}", headers=self.headers("b"))
        self.assertNotEqual(blocked.status_code, 200)
        self.assertFalse(self.client.get("/owner/social/accounts", headers=self.headers("a")).json()[0]["needs_reauth"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
