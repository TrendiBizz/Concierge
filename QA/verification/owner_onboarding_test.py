"""Offline tenant-owner onboarding regressions; no real DB or messages."""
import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
from app import owner_auth, owner_onboarding
from app.main import app


class OnboardingTests(unittest.TestCase):
    def test_validation_rejects_bad_email_and_timezone(self):
        from pydantic import ValidationError
        for bad in ("not-an-email", "example@localhost", "a @example.com"):
            with self.assertRaises(ValidationError):
                owner_onboarding.OwnerBusinessProfile(notify_email=bad)
        with self.assertRaises(ValidationError):
            owner_onboarding.OwnerBusinessProfile(timezone="Other/NotARealZone")
        good=owner_onboarding.OwnerBusinessProfile(
            greeting=" Welcome ", notify_email="OWNER@EXAMPLE.COM",
            timezone="Pacific/Auckland")
        self.assertEqual(good.greeting, "Welcome")
        self.assertEqual(good.notify_email, "owner@example.com")
        self.assertEqual(owner_onboarding.OwnerBusinessProfile(notify_email="").notify_email,"")

    def test_overview_scopes_phone_lookup_to_authenticated_tenant(self):
        async def run():
            tenant={"id":"tenant-a","slug":"a","name":"Business A","site_url":"https://a.example",
                    "phone_enabled":True,"notify_email":"owner@example.com"}
            pool=MagicMock()
            pool.fetch=AsyncMock(return_value=[{"e164":"+64000000000","enabled":True}])
            config=SimpleNamespace(social_service_enabled=False,
                                   email_configured=False,sms_configured=False,
                                   twenty_bridge_url="",twenty_bridge_tenant_slug="")
            with patch.object(owner_onboarding.tenants,"get_by_id",new_callable=AsyncMock,
                              return_value=tenant) as get_tenant, \
                 patch.object(owner_onboarding.db,"pool",return_value=pool), \
                 patch.object(owner_onboarding,"get_settings",return_value=config):
                result=await owner_onboarding.overview("tenant-a")
            get_tenant.assert_awaited_once_with("tenant-a")
            self.assertEqual(pool.fetch.await_args.args[1],"tenant-a")
            self.assertFalse(result["customer_activation_enabled"])
            self.assertTrue(result["channels"]["telephone"]["configured"])
            self.assertFalse(result["channels"]["telephone"]["verified"])
            self.assertEqual(result["business"]["name"],"Business A")
        asyncio.run(run())

    def test_only_owner_can_edit_and_slug_is_from_session(self):
        async def run(role):
            identity={"slug":"tenant-a","tenant_id":"tenant-id-a","role":role,"email":"owner@example.com"}
            async def auth(): return identity
            app.dependency_overrides[owner_auth.current_user]=auth
            try:
                with patch.object(owner_onboarding,"update_profile",new_callable=AsyncMock) as write:
                    write.return_value={"greeting":"Welcome", "notify_email":"","timezone":"Pacific/Auckland"}
                    async with httpx.AsyncClient(
                        transport=httpx.ASGITransport(app=app),
                        base_url="http://testserver"
                    ) as client:
                        response=await client.patch("/owner/onboarding/profile",json={
                            "greeting":"Welcome", "notify_email":"", "timezone":"Pacific/Auckland"
                        })
                    return response,write
            finally:
                app.dependency_overrides.clear()
        for role in ("viewer","editor"):
            response,write=asyncio.run(run(role))
            self.assertEqual(response.status_code,403)
            write.assert_not_awaited()
        response,write=asyncio.run(run("owner"))
        self.assertEqual(response.status_code,200)
        self.assertEqual(write.await_args.args[0],"tenant-a")
        self.assertEqual(write.await_args.args[1].greeting,"Welcome")

    def test_overview_requires_login(self):
        async def run():
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                         base_url="http://testserver") as client:
                return await client.get("/owner/onboarding")
        response=asyncio.run(run())
        self.assertIn(response.status_code,(401,403))


if __name__=="__main__":
    unittest.main()
