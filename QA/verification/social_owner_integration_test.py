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

    def test_oauth_start_finish_use_authenticated_tenant_and_owner_role(self):
        async def run(role):
            identity={"slug":"customer-a","name":"A","tenant_id":"a","role":role}
            async def current_user(): return identity
            app.dependency_overrides[owner_auth.current_user]=current_user
            try:
                with patch.object(social_bridge,"start_mastodon_oauth",
                                  new_callable=AsyncMock) as start, \
                     patch.object(social_bridge,"finish_mastodon_oauth",
                                  new_callable=AsyncMock) as finish:
                    start.return_value={"authorization_url":"https://example.org/oauth/authorize",
                                        "state":"x"*43}
                    finish.return_value={"account_id":"linked"}
                    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                                 base_url="http://testserver") as client:
                        first=await client.post("/owner/social/oauth/mastodon/start")
                        second=await client.post("/owner/social/oauth/mastodon/finish",json={
                            "state":"x"*43,"code":"test-authorisation-code"})
                    return first.status_code,second.status_code,start,finish
            finally:
                app.dependency_overrides.clear()
        for denied_role in ("viewer","editor"):
            first,second,start,finish=asyncio.run(run(denied_role))
            self.assertEqual((first,second),(403,403))
            start.assert_not_awaited()
            finish.assert_not_awaited()
        first,second,start,finish=asyncio.run(run("owner"))
        self.assertEqual((first,second),(200,200))
        self.assertEqual(start.await_args.args[0]["slug"],"customer-a")
        self.assertEqual(finish.await_args.args[0]["slug"],"customer-a")
        self.assertEqual(finish.await_args.args[1:],
                         ("x"*43,"test-authorisation-code"))

    def test_disconnect_is_owner_only(self):
        async def run(role):
            identity={"slug":"customer-a","name":"A","tenant_id":"a","role":role}
            async def current_user(): return identity
            app.dependency_overrides[owner_auth.current_user]=current_user
            try:
                with patch.object(social_bridge,"disconnect_mastodon",
                                  new_callable=AsyncMock) as disconnect:
                    disconnect.return_value={"ok":True}
                    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                                 base_url="http://testserver") as client:
                        response=await client.delete(
                            "/owner/social/oauth/mastodon/accounts/"+("a"*32))
                    return response.status_code, disconnect
            finally:
                app.dependency_overrides.clear()
        denied,call=asyncio.run(run("editor"))
        self.assertEqual(denied,403)
        call.assert_not_awaited()
        allowed,call=asyncio.run(run("owner"))
        self.assertEqual(allowed,200)
        self.assertEqual(call.await_args.args[0]["slug"],"customer-a")

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
