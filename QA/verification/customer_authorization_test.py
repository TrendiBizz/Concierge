"""No-network end-to-end owner-authorization API regression tests."""
from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from app import channel_authorization, owner_auth, outbox
from app.main import app


class MemoryDb:
    def __init__(self):
        self.records = {}
        self.audit = []
        self.pool = self

    def acquire(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    def transaction(self):
        return self

    async def fetchrow(self, sql, tenant, channel, authorized, actor):
        self.records[(tenant, channel)] = {"authorized": authorized, "updated_at": None}
        return self.records[(tenant, channel)]

    async def execute(self, sql, tenant, channel, authorized, actor):
        self.audit.append((tenant, channel, authorized, actor))

    async def fetch(self, sql, tenant):
        return [
            {"channel": channel, **value}
            for (owner, channel), value in self.records.items()
            if owner == tenant
        ]


class ChannelAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.db = MemoryDb()

    async def query(self, user, method, path, body=None):
        if user is not None:
            async def auth():
                return user
            app.dependency_overrides[owner_auth.current_user] = auth
        try:
            with patch.object(channel_authorization.db, "pool", return_value=self.db):
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=app),
                    base_url="http://testserver",
                ) as client:
                    return await client.request(method, path, json=body)
        finally:
            app.dependency_overrides.clear()

    def test_authentication_owner_only_and_explicit_acknowledgement(self):
        owner = {"tenant_id": "a", "id": "u1", "role": "owner"}
        viewer = {"tenant_id": "a", "id": "u2", "role": "viewer"}
        path = "/owner/onboarding/authorizations"
        body = {"channel": "email_read", "authorized": True, "acknowledgement": True}
        self.assertEqual(asyncio.run(self.query(None, "POST", path, body)).status_code, 401)
        self.assertEqual(asyncio.run(self.query(viewer, "POST", path, body)).status_code, 403)
        self.assertEqual(
            asyncio.run(self.query(owner, "POST", path, {**body, "acknowledgement": False})).status_code,
            400,
        )
        self.assertEqual(
            asyncio.run(self.query(owner, "POST", path, {**body, "channel": "all"})).status_code,
            422,
        )
        self.assertEqual(len(self.db.audit), 0)
        self.assertEqual(asyncio.run(self.query(owner, "POST", path, body)).status_code, 200)
        self.assertFalse(asyncio.run(self.query(owner, "POST", path, body)).json()["active"])

    def test_isolation_read_revoke_and_audit(self):
        alice = {"tenant_id": "a", "id": "ua", "role": "owner"}
        bob = {"tenant_id": "b", "id": "ub", "role": "owner"}
        path = "/owner/onboarding/authorizations"
        body = {"channel": "call_recording", "authorized": True, "acknowledgement": True}
        self.assertEqual(asyncio.run(self.query(alice, "POST", path, body)).status_code, 200)
        b = asyncio.run(self.query(bob, "GET", path)).json()
        self.assertFalse(b["call_recording"]["authorized"])
        a = asyncio.run(self.query(alice, "GET", path)).json()
        self.assertTrue(a["call_recording"]["authorized"])
        self.assertFalse(a["call_recording"]["provider_verified"])
        body["authorized"] = False
        self.assertEqual(asyncio.run(self.query(alice, "POST", path, body)).status_code, 200)
        a = asyncio.run(self.query(alice, "GET", path)).json()
        self.assertFalse(a["call_recording"]["authorized"])
        self.assertEqual(self.db.audit, [
            ("a", "call_recording", True, "ua"),
            ("a", "call_recording", False, "ua"),
        ])

    def test_revocation_blocks_email_and_sms_at_send_time(self):
        async def check(channel):
            row = {
                "id": 7, "tenant_id": "tenant-a", "channel": channel,
                "kind": "reminder", "to_addr": "dest@example.invalid",
            }
            with patch.object(outbox.tenants, "get_by_id",
                              new_callable=AsyncMock, return_value={"id": "tenant-a"}) as fetch, \
                 patch.object(channel_authorization, "is_authorized",
                              new_callable=AsyncMock, return_value=False) as permitted, \
                 patch.object(outbox, "_finish", new_callable=AsyncMock) as finished, \
                 patch.object(outbox.mailer, "send_email", new_callable=AsyncMock) as email, \
                 patch.object(outbox.sms, "send_sms", new_callable=AsyncMock) as sms:
                await outbox._deliver(row)
                fetch.assert_awaited_once_with("tenant-a")
                permitted.assert_awaited_once_with(
                    "tenant-a", "sms_send" if channel == "sms" else "email_send",
                )
                finished.assert_awaited_once_with(7, "skipped", "channel_authorization_missing")
                email.assert_not_awaited()
                sms.assert_not_awaited()
        asyncio.run(check("email"))
        asyncio.run(check("sms"))

    def test_never_activates_on_owner_declaration(self):
        result = channel_authorization.readiness(
            {"sms_send": {"authorized": True},
             "email_read": {"authorized": False}},
            {"sms_send": True, "email_read": True},
        )
        self.assertFalse(result["sms_send"]["active"])
        self.assertFalse(result["sms_send"]["provider_verified"])
        self.assertIn("real_provider_verification", result["sms_send"]["missing"])
        self.assertIn("owner_authorization", result["email_read"]["missing"])


if __name__ == "__main__":
    unittest.main()
