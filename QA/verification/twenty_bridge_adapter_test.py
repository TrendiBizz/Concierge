"""Offline verification of durable, tenant-scoped Twenty CRM adapter.

All network and database calls are mocked. Does not create real CRM records.
"""
import asyncio
import hashlib
import json
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app import events


class TwentyBridgeAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tenant = {"id": "tid-a", "slug": "concierge", "name": "Concierge"}
        self.lead = {"id": "l1", "name": "Jane Example", "email": "jane@example.org",
                     "phone": "+64210000000", "message": "Please call me",
                     "channel": "chat"}
        self.config=SimpleNamespace(twenty_bridge_url="http://127.0.0.1:4410/lead",
                                    twenty_bridge_tenant_slug="concierge")

    def test_bridge_payload_matches_flat_schema(self):
        data=events.twenty_bridge_payload(self.tenant,"lead.created",{"lead":self.lead})
        self.assertEqual(data["first_name"],"Jane")
        self.assertEqual(data["last_name"],"Example")
        self.assertEqual(data["source"],"Concierge chat")
        self.assertEqual(data["email"],"jane@example.org")
        self.assertNotIn("tenant",data)
        self.assertNotIn("event",data)

    def test_booking_note_mapping(self):
        data=events.twenty_bridge_payload(self.tenant,"appointment.booked",{
            "appointment":{"name":"Jane Example","email":"jane@example.org",
                           "starts_at":"2026-11-09T13:00:00Z","notes":"Consultation"}})
        self.assertIn("Appointment booked",data["message"])
        self.assertIn("Consultation",data["message"])

    def test_unrelated_event_and_missing_contact_ignored(self):
        self.assertIsNone(events.twenty_bridge_payload(self.tenant,"other",{"lead":self.lead}))
        self.assertIsNone(events.twenty_bridge_payload(self.tenant,"lead.created",
                          {"lead":{"name":"No contact"}}))

    def test_queue_only_for_named_tenant(self):
        async def run():
            with patch.object(events,"get_settings",return_value=self.config), \
                 patch.object(events.db,"pool") as pool:
                result=await events.queue_twenty(
                    {"id":"tid-b","slug":"other","name":"Other"},"lead.created","l1",
                    {"lead":self.lead})
                self.assertFalse(result)
                pool.assert_not_called()
        asyncio.run(run())

    def test_persist_event_before_delivery_with_dedupe(self):
        async def run():
            pool=MagicMock()
            pool.execute=AsyncMock(return_value="INSERT 0 1")
            with patch.object(events,"get_settings",return_value=self.config), \
                 patch.object(events.db,"pool",return_value=pool):
                result=await events.queue_twenty(self.tenant,"lead.created","l1",
                                                   {"lead":self.lead})
            self.assertTrue(result)
            args=pool.execute.await_args.args
            self.assertEqual(args[0].count("ON CONFLICT"),1)
            self.assertEqual(args[1],"tid-a")
            self.assertEqual(args[2],"lead.created")
            self.assertEqual(args[3],"l1")
            self.assertEqual(json.loads(args[4])["email"],"jane@example.org")
        asyncio.run(run())

    def test_process_confirmed_deduped_delivery(self):
        async def run():
            pool=MagicMock()
            pool.execute=AsyncMock(return_value="UPDATE 1")
            pool.fetch=AsyncMock(return_value=[{
                "id":1,"tenant_id":"tid-a","event":"lead.created","source_id":"l1",
                "payload":json.dumps({"email":"jane@example.org","first_name":"Jane"}),
                "attempts":1}])
            pool.fetchrow=AsyncMock(return_value={"slug":"concierge"})
            response=MagicMock(status_code=200)
            response.json.return_value={"ok":True,"twenty_id":"id-from-crm","note":True}
            client=AsyncMock()
            client.post.return_value=response
            ctx=AsyncMock()
            ctx.__aenter__.return_value=client
            with patch.object(events,"get_settings",return_value=self.config), \
                 patch.object(events.db,"pool",return_value=pool), \
                 patch.object(events.httpx,"AsyncClient",return_value=ctx), \
                 patch.object(events,"_twenty_finish",new_callable=AsyncMock) as finish:
                count=await events.process_twenty_once()
                self.assertEqual(count,1)
                sent=client.post.await_args.kwargs["json"]
                self.assertEqual(sent["email"],"jane@example.org")
                identity=json.dumps(["tid-a","lead.created","l1"],ensure_ascii=True,separators=(',',':'))
                self.assertEqual(sent["delivery_id"],hashlib.sha256(identity.encode()).hexdigest())
                finish.assert_awaited_once_with(1,"sent")
        asyncio.run(run())

    def test_person_created_but_note_failed_requires_reconciliation(self):
        async def run():
            pool=MagicMock()
            pool.execute=AsyncMock(return_value="UPDATE 1")
            pool.fetch=AsyncMock(return_value=[{
                "id":3,"tenant_id":"tid-a","event":"appointment.booked","source_id":"a3",
                "payload":{"email":"jane@example.org"},"attempts":1}])
            pool.fetchrow=AsyncMock(return_value={"slug":"concierge"})
            response=MagicMock(status_code=200)
            response.json.return_value={"ok":True,"twenty_id":"person-created","note":False}
            client=AsyncMock()
            client.post.return_value=response
            ctx=AsyncMock()
            ctx.__aenter__.return_value=client
            with patch.object(events,"get_settings",return_value=self.config), \
                 patch.object(events.db,"pool",return_value=pool), \
                 patch.object(events.httpx,"AsyncClient",return_value=ctx), \
                 patch.object(events,"_twenty_finish",new_callable=AsyncMock) as finish:
                await events.process_twenty_once()
                self.assertEqual(finish.await_args.args[1],"uncertain")
        asyncio.run(run())

    def test_timeout_requires_manual_reconciliation_no_blind_retry(self):
        async def run():
            pool=MagicMock()
            pool.execute=AsyncMock(return_value="UPDATE 1")
            pool.fetch=AsyncMock(return_value=[{
                "id":2,"tenant_id":"tid-a","event":"lead.created","source_id":"l2",
                "payload":{"email":"jane@example.org"},"attempts":1}])
            pool.fetchrow=AsyncMock(return_value={"slug":"concierge"})
            client=AsyncMock()
            client.post.side_effect=events.httpx.ReadTimeout("timeout")
            ctx=AsyncMock()
            ctx.__aenter__.return_value=client
            with patch.object(events,"get_settings",return_value=self.config), \
                 patch.object(events.db,"pool",return_value=pool), \
                 patch.object(events.httpx,"AsyncClient",return_value=ctx), \
                 patch.object(events,"_twenty_finish",new_callable=AsyncMock) as finish:
                await events.process_twenty_once()
                self.assertEqual(finish.await_args.args[1],"uncertain")
        asyncio.run(run())

    def test_inflight_delivery_conflict_requires_reconciliation(self):
        async def run():
            pool=MagicMock()
            pool.execute=AsyncMock(return_value="UPDATE 1")
            pool.fetch=AsyncMock(return_value=[{
                "id":4,"tenant_id":"tid-a","event":"lead.created","source_id":"l4",
                "payload":{"email":"jane@example.org","first_name":"Jane"},
                "attempts":1}])
            pool.fetchrow=AsyncMock(return_value={"slug":"concierge"})
            response=MagicMock(status_code=409)
            client=AsyncMock()
            client.post.return_value=response
            ctx=AsyncMock()
            ctx.__aenter__.return_value=client
            with patch.object(events,"get_settings",return_value=self.config), \
                 patch.object(events.db,"pool",return_value=pool), \
                 patch.object(events.httpx,"AsyncClient",return_value=ctx), \
                 patch.object(events,"_twenty_finish",new_callable=AsyncMock) as finish:
                await events.process_twenty_once()
                self.assertEqual(finish.await_args.args[1],"uncertain")
                self.assertEqual(client.post.await_count,1)
        asyncio.run(run())

    def test_invalid_external_bridge_url_does_not_send(self):
        async def run():
            bad=SimpleNamespace(twenty_bridge_url="http://attacker.invalid:4410/lead",
                                twenty_bridge_tenant_slug="concierge")
            with patch.object(events,"get_settings",return_value=bad), \
                 patch.object(events.db,"pool") as pool, \
                 patch.object(events.httpx,"AsyncClient") as client:
                self.assertEqual(await events.process_twenty_once(),0)
                pool.assert_not_called()
                client.assert_not_called()
        asyncio.run(run())


if __name__=="__main__":
    unittest.main()
