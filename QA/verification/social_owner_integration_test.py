"""Safe, offline tenant-owner access checks for the Rust social proxy."""
import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import HTTPException
from app import owner_auth, social_bridge
from app.main import app


class SocialOwnerTests(unittest.TestCase):
    def test_disabled_by_default(self):
        with patch.object(social_bridge, "get_settings",
                          return_value=SimpleNamespace(
                              social_service_enabled=False,
                              social_service_url="http://127.0.0.1:4390",
                              social_concierge_key="")):
            with self.assertRaises(HTTPException) as error:
                social_bridge._configuration()
            self.assertEqual(error.exception.status_code, 503)

    def test_external_service_endpoint_is_rejected(self):
        with patch.object(social_bridge, "get_settings",
                          return_value=SimpleNamespace(
                              social_service_enabled=True,
                              social_service_url="https://attacker.example",
                              social_concierge_key="x"*40)):
            with self.assertRaises(HTTPException) as error:
                social_bridge._configuration()
            self.assertEqual(error.exception.status_code, 503)

    def test_tenant_slug_is_taken_from_authenticated_owner(self):
        async def run():
            tenant = {"slug":"customer-one","name":"One","tenant_id":"a","role":"owner"}
            with patch.object(social_bridge, "_request", new_callable=AsyncMock) as request:
                request.return_value = {}
                await social_bridge.accounts(tenant)
                self.assertEqual(request.await_args_list[0].args[1],
                                 "/v1/customers/customer-one/rules")
                self.assertEqual(request.await_args_list[1].args[1],
                                 "/v1/customers/customer-one/accounts")
        asyncio.run(run())

    def test_owner_routes_require_authenticated_session_and_role(self):
        async def run(role):
            identity={"slug":"customer-a","name":"A","tenant_id":"a","role":role}
            async def current_user():return identity
            app.dependency_overrides[owner_auth.current_user]=current_user
            try:
                with patch.object(social_bridge,"create_draft",new_callable=AsyncMock) as creator, \
                     patch.object(social_bridge,"decide",new_callable=AsyncMock) as decider:
                    creator.return_value={"id":"draft"}
                    decider.return_value={"status":"scheduled"}
                    client=httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                             base_url="http://testserver")
                    async with client:
                        d=await client.post("/owner/social/posts",json={
                            "content":"Hello","account_ids":["test_account_1234567890"]})
                        a=await client.post("/owner/social/approvals/token1234567890123456/approve")
                    return d.status_code,a.status_code,creator,decider
            finally:
                app.dependency_overrides.clear()
        d,a,creator,decider=asyncio.run(run("viewer"))
        self.assertEqual((d,a),(403,403))
        creator.assert_not_awaited()
        decider.assert_not_awaited()
        d,a,creator,decider=asyncio.run(run("editor"))
        self.assertEqual((d,a),(200,403))
        creator.assert_awaited_once()
        decider.assert_not_awaited()
        d,a,creator,decider=asyncio.run(run("owner"))
        self.assertEqual((d,a),(200,200))
        creator.assert_awaited_once()
        decider.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
